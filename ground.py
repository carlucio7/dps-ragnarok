# -*- coding: utf-8 -*-
"""Chão para a prévia dos visuais: um pedaço do terreno de um mapa do jogo, plano, visto no ângulo da câmera.

Não é o mapa em 3D (sem relevo, sem prédios, sem sombras): só as texturas do chão de cada quadrado do mapa (.gnd do
data.grf), desenhadas com o GDI+ no mesmo achatamento vertical que o jogo dá ao chão. Serve para dar noção de
perspectiva e de tamanho: uma célula do jogo tem 35 pixels de largura na escala dos personagens.
"""

import struct

import gdip
import sprites
import streffect

CELL = 35.0                   # largura de uma célula do jogo em pixels do personagem
SQUASH = streffect.SQUASH     # o chão é achatado na vertical como os efeitos (a câmera olha de cima)
TEX = "data\\texture\\"
# terrenos oferecidos: (nome para mostrar, mapa, célula onde o personagem fica)
PLACES = [("Prontera", "prontera", (156, 190)), ("Campo de Prontera", "prt_fild08", (170, 362)),
          ("Payon", "payon", (173, 100)), ("Morroc", "morocc", (160, 100)), ("Geffen", "geffen", (120, 68)),
          ("Lutie", "xmas", (148, 128)), ("Comodo", "comodo", (190, 150)), ("Alberta", "alberta", (116, 62))]
PREFIXES = tuple("data\\%s.gnd" % m for _n, m, _c in PLACES) + (TEX,)    # o que o chão lê do data.grf


def parse(data):
    """O .gnd: dict(w, h, textures=[nomes], tiles=[(u×4, v×4, textura)], top=[superfície de cima de cada quadrado]).
    Um quadrado do .gnd são 2 × 2 células do jogo."""
    if data[:4] != b"GRGN":
        raise ValueError("não é um .gnd")
    w, h, _zoom, ntex, tlen = struct.unpack_from("<iifii", data, 6)
    p = 26
    textures = [data[p + i * tlen:p + (i + 1) * tlen].split(b"\0")[0].decode("cp949", "replace")
                for i in range(ntex)]
    p += ntex * tlen
    nlight, lw, lh, _cells = struct.unpack_from("<iiii", data, p)
    p += 16 + nlight * (lw * lh * 4)
    ntiles = struct.unpack_from("<i", data, p)[0]
    p += 4
    # superfície: u×4, v×4, textura, (mapa de luz e cor, que aqui não servem); quadrado: alturas×4, superfície de
    # cima, (frente, lado). Lidos em bloco (iter_unpack): um unpack por campo levava ~0,1 s num mapa como Prontera.
    if ntiles < 0 or w < 0 or h < 0 or len(data) < p + ntiles * 40 + w * h * 28:
        raise ValueError(".gnd cortado")
    tiles = [(t[:4], t[4:8], t[8]) for t in struct.iter_unpack("<8fh6x", data[p:p + ntiles * 40])]
    p += ntiles * 40
    top = [t[0] for t in struct.iter_unpack("<16xi8x", data[p:p + w * h * 28])]
    return dict(w=w, h=h, textures=textures, tiles=tiles, top=top)


class Ground:
    """Lê os terrenos do jogo e desenha um pedaço em volta de uma célula."""

    def __init__(self, grf_path, grf=None):
        # `grf`: um índice já aberto que cubra estas pastas (a aba Visuais divide um com os efeitos e os ícones)
        self.grf = grf if grf is not None and grf.covers(PREFIXES) else sprites.Grf(grf_path, prefixes=PREFIXES)
        self.maps = {}                # mapa -> o .gnd lido (None se não deu)
        self.textures = {}            # (mapa, textura) -> (w, h, bytes BGRA) ou None

    def places(self):
        """Os terrenos que este jogo tem: [(nome, mapa, célula)]."""
        return [p for p in PLACES if self.grf.has("data\\%s.gnd" % p[1])]

    def gnd(self, name):
        if name not in self.maps:
            data = self.grf.read("data\\%s.gnd" % name)
            try:
                self.maps[name] = parse(data) if data else None
            except (ValueError, struct.error, IndexError):
                self.maps[name] = None
        return self.maps[name]

    def texture(self, name, index):
        g = self.gnd(name)
        key = (name, index)
        if key not in self.textures:
            tex = None
            if g and 0 <= index < len(g["textures"]):
                path = TEX + g["textures"][index]
                data = self.grf.read(path)
                try:
                    if data:
                        tex = streffect.tga_bgra(data) if path.lower().endswith(".tga") else streffect.bmp_bgra(data)
                except (ValueError, struct.error, IndexError):
                    tex = None
            self.textures[key] = tex
        return self.textures[key]

    def render(self, name, cell, width, height, feet, scale=1.0):
        """Imagem (bytes BGRA, width × height) do chão do mapa com a célula `cell` debaixo do ponto `feet` (x, y da
        imagem). `scale`: ampliação dos pixels do personagem. None se o mapa não der para desenhar."""
        g = self.gnd(name)
        if g is None or not gdip.ready():
            return None
        cw, ch = CELL * scale, CELL * SQUASH * scale          # uma célula na tela
        # a célula do personagem: o centro dela fica nos pés
        wx, wy = cell[0] + 0.5, cell[1] + 0.5
        left = wx - feet[0] / cw
        right = wx + (width - feet[0]) / cw
        south = wy - (height - feet[1]) / ch
        north = wy + feet[1] / ch
        images, ops = {}, []
        try:
            for ty in range(max(0, int(south // 2) - 1), min(g["h"], int(north // 2) + 2)):
                for tx in range(max(0, int(left // 2) - 1), min(g["w"], int(right // 2) + 2)):
                    surface = g["top"][ty * g["w"] + tx]
                    if not 0 <= surface < len(g["tiles"]):
                        continue
                    u, v, ti = g["tiles"][surface]
                    tex = self.texture(name, ti)
                    if tex is None:
                        continue
                    tw, th, bgra = tex
                    # o recorte da textura que este quadrado usa
                    x0, x1 = min(u) * tw, max(u) * tw
                    y0, y1 = min(v) * th, max(v) * th
                    px0, py0 = max(0, int(round(x0))), max(0, int(round(y0)))
                    px1, py1 = min(tw, int(round(x1))), min(th, int(round(y1)))
                    if px1 - px0 < 1 or py1 - py0 < 1:
                        continue
                    ikey = (ti, px0, py0, px1, py1)
                    if ikey not in images:
                        rows = [bgra[(yy * tw + px0) * 4:(yy * tw + px1) * 4] for yy in range(py0, py1)]
                        images[ikey] = gdip.Image(px1 - px0, py1 - py0, b"".join(rows))
                    img = images[ikey]
                    # cantos do quadrado na tela: sudoeste, sudeste e noroeste (o norte fica para cima)
                    sx0 = (tx * 2 - wx) * cw + feet[0]
                    sx1 = (tx * 2 + 2 - wx) * cw + feet[0]
                    sy0 = feet[1] - (ty * 2 - wy) * ch            # borda sul
                    sy1 = feet[1] - (ty * 2 + 2 - wy) * ch        # borda norte
                    corners = ((sx0, sy0), (sx1, sy0), (sx0, sy1))

                    def at(i):
                        return ((u[i] * tw - px0) - img.w / 2.0, (v[i] * th - py0) - img.h / 2.0)
                    p0, p1, p2 = at(0), at(1), at(2)
                    ax, ay = p1[0] - p0[0], p1[1] - p0[1]
                    bx, by = p2[0] - p0[0], p2[1] - p0[1]
                    det = ax * by - ay * bx
                    if abs(det) < 1e-6:
                        continue
                    Ax, Ay = corners[1][0] - corners[0][0], corners[1][1] - corners[0][1]
                    Bx, By = corners[2][0] - corners[0][0], corners[2][1] - corners[0][1]
                    m11 = (Ax * by - Bx * ay) / det
                    m21 = (Bx * ax - Ax * bx) / det
                    m12 = (Ay * by - By * ay) / det
                    m22 = (By * ax - Ay * bx) / det
                    dx = corners[0][0] - (p0[0] * m11 + p0[1] * m21)
                    dy = corners[0][1] - (p0[0] * m12 + p0[1] * m22)
                    ops.append((img, m11, m12, m21, m22, dx, dy, True))
            return gdip.render(int(width), int(height), ops) if ops else None
        finally:
            for im in images.values():
                im.close()
