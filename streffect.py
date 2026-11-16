# -*- coding: utf-8 -*-
"""Efeitos de chapéu do jogo (auras, brilhos, as "Pedras Gráficas"): lê a tabela de efeitos e os arquivos .str do
data.grf e desenha os quadros com o GDI+. Alguns efeitos o jogo desenha com um sprite comum (SPRITES).

Um .str é uma animação por camadas: cada camada tem texturas e quadros-chave (posição, os quatro cantos do
retângulo, giro, cor e transparência), e entre dois quadros-chave os valores andam um tanto por quadro. A maioria
das camadas é "aditiva" (o preto da textura não aparece e as cores somam luz); aqui o brilho de cada pixel vira
a transparência dele, o que dá o mesmo efeito por cima do personagem.
"""

import base64
import math
import struct

import gdip
import lub
import sprites

HAT = "data\\luafiles514\\lua files\\hateffectinfo\\"
EFF = "data\\texture\\effect\\"
ORIGIN = (320.0, 240.0)       # o centro do efeito no arquivo (tela de 640 x 480 da ferramenta de efeitos)
# Medido nos GIFs do jogo (Poça d'Água, hatEffectPos -10; Corações, -5): o efeito é desenhado achatado na vertical
# (o plano dele fica inclinado em relação à câmera) e o centro do arquivo fica acima da cabeça, descendo com o
# hatEffectPos de cada efeito.
ABOVE_FEET = 110.0            # altura do centro do efeito sobre os pés com hatEffectPos 0
POS_PX = 9.6                  # pixels por unidade de hatEffectPos (negativo = para baixo)
SQUASH = 0.76                 # achatamento vertical de tudo no efeito
STEP = 4                      # um quadro desenhado a cada 4 do arquivo (60 por segundo -> 15)
MAX_FRAMES = 60               # animação mais longa que isso pula mais quadros
MAX_HALF = 260                # metade do lado da área desenhada, no máximo (pixels do jogo)
NORMAL_DST = 6                # D3DBLEND_INVSRCALPHA: mistura comum; o resto é tratado como luz somada
# Efeitos que o jogo liga por número (não estão na tabela de chapéus) mas cujo arquivo .str vem no data.grf:
# nome -> (arquivo, hatEffectPos equivalente). Comparado quadro a quadro com o GIF do jogo da pedra Raios
# Vermelhos: os raios ficam atrás do personagem, a origem do arquivo a ~45 px dos pés, e o efeito recomeça assim
# que as camadas acabam (o arquivo tem um trecho vazio no fim que o jogo não mostra).
EXTRA = {"red_wave": ("red_wave\\ef_mon_explodngwave.str", -6.8),
         "blue_wave": ("blue_wave\\ef_mon_electric.str", -6.8)}
# Efeitos cujo arquivo fica fora do lugar dos outros: nome -> (acerto no hatEffectPosX, acerto no hatEffectPos).
# Cintilação (ljosalfar): no GIF do jogo as estrelas caem em cima da cabeça; pelo arquivo sairiam ~53 px à
# esquerda e ~38 px mais altas.
NUDGE = {"ljosalfar": (5.5, -4.0)}
SPR = "data\\sprite\\이팩트\\"
# Efeitos que o jogo liga por número e desenha com um sprite (não com um .str): nome -> (sprite, sem a extensão;
# ms por quadro; atrás do personagem). Espaço Digital (a pedra e o "[Visual] Holograma Futurista"): no GIF do
# jogo são os 14 quadros do sprite a ~120 ms cada, com o personagem na frente.
SPRITES = {"digital_space": ("digital_space\\digital_space", 120.0, True)}
KEEP = 8                      # efeitos prontos guardados ao mesmo tempo (os mais antigos saem)
DARK = 10                     # brilho até aqui conta como preto (transparente) nas texturas de luz
_DIV = None


def _div():
    """Tabela [maior][valor] -> valor·255/maior (para separar o brilho da cor), feita uma vez."""
    global _DIV
    if _DIV is None:
        _DIV = [bytes(256)] + [bytes(min(255, v * 255 // m) for v in range(256)) for m in range(1, 256)]
    return _DIV


def tga_bgra(data):
    """(w, h, bytes BGRA de cima para baixo) de um .tga de 24 ou 32 bits, cru ou comprimido (RLE)."""
    idlen, _cmap, kind = data[0], data[1], data[2]
    w, h, bpp, desc = struct.unpack_from("<HHBB", data, 12)
    if kind not in (2, 10) or bpp not in (24, 32):
        raise ValueError("tga tipo %d de %d bits" % (kind, bpp))
    n, size, p = bpp // 8, w * h, 18 + idlen
    if kind == 2:
        raw = data[p:p + size * n]
    else:
        out = bytearray()
        while len(out) < size * n and p < len(data):
            c = data[p]
            p += 1
            count = (c & 0x7F) + 1
            if c & 0x80:
                out += data[p:p + n] * count
                p += n
            else:
                out += data[p:p + n * count]
                p += n * count
        raw = bytes(out[:size * n])
    if n == 3:
        buf = bytearray(b"\xff" * (size * 4))
        buf[0::4], buf[1::4], buf[2::4] = raw[0::3], raw[1::3], raw[2::3]
        raw = bytes(buf)
    if not desc & 0x20:                         # de baixo para cima: vira
        raw = b"".join(raw[y * w * 4:(y + 1) * w * 4] for y in range(h - 1, -1, -1))
    return w, h, raw


def bmp_bgra(data):
    """(w, h, bytes BGRA) de um .bmp de 8 ou 24 bits; o magenta do jogo vira transparente."""
    w, h, px = sprites.bmp_rgba(data)
    buf = bytearray(w * h * 4)
    buf[2::4] = bytes(p[0] for p in px)
    buf[1::4] = bytes(p[1] for p in px)
    buf[0::4] = bytes(p[2] for p in px)
    buf[3::4] = bytes(p[3] for p in px)
    return w, h, bytes(buf)


def glow(bgra):
    """Textura de luz somada -> cor cheia com a transparência igual ao brilho (o preto some)."""
    b, g, r, a = bgra[0::4], bgra[1::4], bgra[2::4], bgra[3::4]
    m = bytes(map(max, b, g, r))
    table = _div()
    out = bytearray(len(bgra))
    out[0::4] = bytes(table[k][v] for v, k in zip(b, m))
    out[1::4] = bytes(table[k][v] for v, k in zip(g, m))
    out[2::4] = bytes(table[k][v] for v, k in zip(r, m))
    # o quase preto das bordas das texturas some de vez (senão aparecia o contorno do retângulo)
    out[3::4] = bytes((k - DARK) * 255 // (255 - DARK) * x // 255 if k > DARK else 0 for k, x in zip(m, a))
    return bytes(out)


def tint(bgra, color):
    """A textura com a cor e a transparência do quadro-chave aplicadas (cada canal de uma vez)."""
    r, g, b, a = [max(0, min(255, int(round(c)))) for c in color]
    if (r, g, b, a) == (255, 255, 255, 255):
        return bgra
    out = bytearray(bgra)
    for off, k in ((0, b), (1, g), (2, r), (3, a)):
        if k != 255:
            out[off::4] = bgra[off::4].translate(bytes(v * k // 255 for v in range(256)))
    return bytes(out)


def parse(data):
    """O .str: dict(fps, frames, layers=[dict(tex=[nomes], keys=[quadros-chave])])."""
    if data[:4] != b"STRM":
        raise ValueError("não é um efeito .str")
    _version, fps, maxkey, nlayers = struct.unpack_from("<IIII", data, 4)
    p, layers = 36, []
    for _ in range(nlayers):
        ntex = struct.unpack_from("<i", data, p)[0]
        p += 4
        tex = []
        for _t in range(ntex):
            tex.append(data[p:p + 128].split(b"\0")[0].decode("cp949", "replace"))
            p += 128
        nkeys = struct.unpack_from("<i", data, p)[0]
        p += 4
        keys = []
        for _k in range(nkeys):
            frame, kind = struct.unpack_from("<iI", data, p)
            keys.append(dict(frame=frame, type=kind, pos=struct.unpack_from("<2f", data, p + 8),
                             xy=struct.unpack_from("<8f", data, p + 48),
                             aniframe=struct.unpack_from("<f", data, p + 80)[0],
                             anitype=struct.unpack_from("<I", data, p + 84)[0],
                             delay=struct.unpack_from("<f", data, p + 88)[0],
                             angle=struct.unpack_from("<f", data, p + 92)[0],
                             color=struct.unpack_from("<4f", data, p + 96),
                             src=struct.unpack_from("<I", data, p + 112)[0],
                             dst=struct.unpack_from("<I", data, p + 116)[0]))
            p += 124
        layers.append(dict(tex=tex, keys=keys))
    return dict(fps=fps or 60, frames=maxkey, layers=layers)


def _tex(value, ntex):
    """Qual textura da camada vale: o número do quadro-chave, dentro do que existe (valor inválido = a primeira)."""
    if not ntex:
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return 0
    return max(0, min(ntex - 1, int(value)))


def state(layer, frame):
    """O estado da camada num quadro: dict(pos, xy, angle, color, tex, dst) ou None se ela não aparece.
    (a mesma conta do cliente: o último quadro-chave de base até ali, mais o de movimento vezes os quadros.)"""
    keys = layer["keys"]
    src = to = None
    last = last_base = 0
    for i, k in enumerate(keys):
        if k["frame"] <= frame:
            if k["type"] == 0:
                src = i
            elif k["type"] == 1:
                to = i
        last = max(last, k["frame"])
        if k["type"] == 0:
            last_base = max(last_base, k["frame"])
    if src is None or (to is None and last < frame):
        return None
    a = keys[src]
    b = keys[to] if to is not None else None
    ntex = len(layer["tex"])
    if b is None or to != src + 1 or b["frame"] != a["frame"]:
        if b is not None and last_base <= a["frame"]:
            return None
        return dict(pos=a["pos"], xy=a["xy"], angle=a["angle"], color=a["color"], dst=a["dst"],
                    tex=_tex(a["aniframe"], ntex))
    d = frame - a["frame"]
    kind = b["anitype"]
    if kind == 1:
        ani = a["aniframe"] + b["aniframe"] * d
    elif kind == 2:
        ani = min(a["aniframe"] + b["delay"] * d, ntex - 1)
    elif kind == 3:
        ani = (a["aniframe"] + b["delay"] * d) % ntex if ntex else 0
    elif kind == 4:
        ani = (a["aniframe"] - b["delay"] * d) % ntex if ntex else 0
    else:
        ani = 0
    return dict(pos=(a["pos"][0] + b["pos"][0] * d, a["pos"][1] + b["pos"][1] * d),
                xy=tuple(x + y * d for x, y in zip(a["xy"], b["xy"])), angle=a["angle"] + b["angle"] * d,
                color=tuple(x + y * d for x, y in zip(a["color"], b["color"])), dst=a["dst"],
                tex=_tex(ani, ntex))


class HatEffects:
    """A tabela de efeitos de chapéu do jogo e os efeitos já abertos."""

    def __init__(self, grf_path):
        self.grf = sprites.Grf(grf_path, prefixes=(HAT, EFF) + tuple(SPR + f for f, _ms, _b in SPRITES.values()))
        self.table = {}               # nome (sem "HAT_EF_", minúsculas) -> dict(file, pos, posx, behind)
        try:
            raw = lub.run(self.grf.read(HAT + "hateffectinfo.lub") or b"", "cp949").get("hatEffectTable") or {}
        except (ValueError, struct.error, IndexError, KeyError):
            raw = {}
        for k, v in raw.items():
            if (isinstance(v, dict) and isinstance(v.get("resourceFileName"), str)
                    and self.grf.has(EFF + v["resourceFileName"])):      # efeito de outro servidor: o arquivo não vem
                name = str(k[1] if isinstance(k, tuple) or (hasattr(k, "__len__") and len(k) > 1 and not isinstance(k, str)) else k)
                name = name[7:] if name.upper().startswith("HAT_EF_") else name
                self.table[name.lower()] = dict(name=name, file=v["resourceFileName"],
                                                pos=float(v.get("hatEffectPos") or 0),
                                                posx=float(v.get("hatEffectPosX") or 0),
                                                behind=bool(v.get("isRenderBeforeCharacter")))
        for name, (dx, dy) in NUDGE.items():
            if name in self.table:
                self.table[name]["posx"] += dx
                self.table[name]["pos"] += dy
        for name, (file, pos) in EXTRA.items():
            if self.grf.has(EFF + file):
                self.table[name] = dict(name=name, file=file, pos=pos, posx=0.0, behind=True, trim=True)
        for name, (file, ms, behind) in SPRITES.items():
            if self.grf.has(SPR + file + ".spr") and self.grf.has(SPR + file + ".act"):
                self.table[name] = dict(name=name, file=file + ".spr", sprite=SPR + file, ms=ms, pos=0.0, posx=0.0,
                                        behind=behind)
        self.by_file = {e["file"].rsplit("\\", 1)[-1].rsplit(".", 1)[0].lower(): n for n, e in self.table.items()}
        self._ready = {}

    def effect_items(self):
        """Os itens que são só efeito (sem sprite), pela lista do jogo: [id do item]."""
        try:
            raw = lub.run(self.grf.read(HAT + "effecthatitemtable.lub") or b"", "cp949").get("effectHatItemTable")
        except (ValueError, struct.error, IndexError, KeyError):
            raw = None
        return [v for v in (raw or {}).values() if isinstance(v, int)]

    def find(self, key):
        """Nome na tabela a partir do nome do efeito ou do arquivo dele (ex.: "ljosalfar"), ou None."""
        key = (key or "").lower()
        if key in self.table:
            return key
        return self.by_file.get(key) or next((n for n, e in self.table.items() if key and key in e["file"].lower()),
                                             None)

    def texture(self, path, additive):
        data = self.grf.read(path)
        if not data:
            return None
        try:
            w, h, bgra = tga_bgra(data) if path.lower().endswith(".tga") else bmp_bgra(data)
        except (ValueError, struct.error, IndexError):
            return None
        return w, h, glow(bgra) if additive else bgra

    def frames(self, name):
        """A animação do efeito pronta para a tela: dict(frames=[PNG em base64], w, h, cx, cy, ms, behind), com
        (cx, cy) = onde ficam os pés do personagem dentro da imagem. None se não der para desenhar."""
        name = self.find(name)
        if name is None:
            return None
        if name not in self._ready:
            while len(self._ready) >= KEEP:        # cada efeito pronto guarda até uns MB de quadros
                self._ready.pop(next(iter(self._ready)))
            try:
                self._ready[name] = self._build(self.table[name]) if gdip.ready() else None
            except (ValueError, struct.error, IndexError, KeyError, ZeroDivisionError):
                self._ready[name] = None
        return self._ready[name]

    def _build_sprite(self, entry):
        """Efeito que é um sprite: os quadros da única ação dele, com a origem do sprite nos pés do personagem."""
        spr, act = self.grf.read(entry["sprite"] + ".spr"), self.grf.read(entry["sprite"] + ".act")
        if not spr or not act:
            return None
        part = sprites.Part("efeito", sprites.Sprite(spr), sprites.Act(act), None, False)
        made = sprites.smooth_frames(part, part.act.frames(0), with_origin=True)
        if made is None:
            return None
        w, h, frames, ox, oy = made
        return dict(frames=[base64.b64encode(sprites.png_rgba(w, h, gdip.swap_rb(f))).decode("ascii")
                            for f in frames],
                    w=w, h=h, cx=ox, cy=oy, ms=entry["ms"], behind=entry["behind"], name=entry["name"])

    def _build(self, entry):
        if entry.get("sprite"):
            return self._build_sprite(entry)
        data = self.grf.read(EFF + entry["file"])
        if not data:
            return None
        s = parse(data)
        folder = (EFF + entry["file"]).rsplit("\\", 1)[0] + "\\"
        step = STEP
        while s["frames"] // step > MAX_FRAMES:
            step += 1
        # o centro do arquivo em relação aos pés: (dx, dy), com y para baixo
        feet_x = ORIGIN[0] - entry["posx"] * POS_PX
        lift = ABOVE_FEET + entry["pos"] * POS_PX
        plan, textures, half = [], {}, 8.0
        for f in range(0, max(1, s["frames"]), step):
            draws = []
            for li, layer in enumerate(s["layers"]):
                st = state(layer, f)
                if st is None or st["tex"] is None or st["color"][3] <= 0.5:
                    continue
                additive = st["dst"] != NORMAL_DST
                tkey = (li, st["tex"], additive)
                if tkey not in textures:
                    textures[tkey] = self.texture(folder + layer["tex"][st["tex"]], additive)
                if textures[tkey] is None:
                    continue
                draws.append((tkey, st))
                x, y = st["pos"][0] - feet_x, SQUASH * (st["pos"][1] - ORIGIN[1]) - lift
                reach = max(abs(v) for v in st["xy"]) * 1.5
                half = max(half, abs(x) + reach, abs(y) + reach)
            plan.append(draws)
        while entry.get("trim") and len(plan) > 1 and not plan[-1]:
            plan.pop()                             # o trecho vazio do fim: o efeito recomeça direto
        half = int(min(MAX_HALF, math.ceil(half)))
        size = half * 2
        images, frames = {}, []
        try:
            for draws in plan:
                ops = []
                if len(images) > 400:              # só entre quadros: o quadro em curso ainda usa as imagens
                    for im in images.values():
                        im.close()
                    images = {}
                for tkey, st in draws:
                    tw, th, bgra = textures[tkey]
                    color = tuple(max(0, min(255, int(round(c / 8.0)) * 8)) for c in st["color"][:3]) + (
                        max(0, min(255, int(round(st["color"][3] / 4.0)) * 4)),)
                    ikey = (tkey, color)
                    if ikey not in images:
                        images[ikey] = gdip.Image(tw, th, tint(bgra, color))
                    xs, ys = st["xy"][:4], st["xy"][4:]
                    # cantos: 0 cima-esquerda, 1 cima-direita, 2 baixo-direita, 3 baixo-esquerda
                    m11, m12 = (xs[1] - xs[0]) / tw, (ys[1] - ys[0]) / tw
                    m21, m22 = (xs[3] - xs[0]) / th, (ys[3] - ys[0]) / th
                    if abs(m11 * m22 - m12 * m21) < 1e-7 or any(v != v for v in (m11, m12, m21, m22)):
                        continue                   # retângulo sem área neste quadro: nada a desenhar
                    cx, cy = (xs[1] + xs[3]) / 2.0, (ys[1] + ys[3]) / 2.0
                    # o giro do arquivo é anti-horário na tela (conferido nos raios da Fúria dos Shuras contra o
                    # GIF do jogo: com o sentido trocado os raios, que descem pelos lados do corpo, saíam deitados)
                    ang = -math.radians(st["angle"] * 360.0 / 1024.0)
                    ca, sa = math.cos(ang), math.sin(ang)
                    ox = st["pos"][0] - feet_x + half
                    oy = SQUASH * (st["pos"][1] - ORIGIN[1]) - lift + half
                    ops.append((images[ikey],
                                m11 * ca - m12 * sa, SQUASH * (m11 * sa + m12 * ca),
                                m21 * ca - m22 * sa, SQUASH * (m21 * sa + m22 * ca),
                                cx * ca - cy * sa + ox, SQUASH * (cx * sa + cy * ca) + oy, True))
                out = gdip.render(size, size, ops) if ops else bytes(size * size * 4)
                if out is None:
                    return None
                frames.append(base64.b64encode(sprites.png_rgba(size, size, gdip.swap_rb(out))).decode("ascii"))
        finally:
            for im in images.values():
                im.close()
        if not frames:
            return None
        return dict(frames=frames, w=size, h=size, cx=half, cy=half, ms=1000.0 * step / s["fps"],
                    behind=entry["behind"], name=entry["name"])
