# -*- coding: utf-8 -*-
"""Visual do personagem de quem gravou, montado com os sprites do jogo instalado.

Lê do data.grf só o necessário: corpo (sprite\\인간족\\몸통), cabeça (머리통), chapéus (악세사리), capa e
visual de capa (로브), arma e escudo, as paletas de cabelo e de roupa e as tabelas do cliente que dão o nome
de cada arquivo (accessoryid/accname, spriterobeid/spriterobename, weapontable). O ClassNum de cada item (o
número do visual) vem do System\\iteminfo_new.lub. Nada do jogo vai junto com o programa: sem o jogo
instalado, a aba mostra só a lista do equipamento.

Alguns arquivos do .grf vêm cifrados (flags 2 e 4): são decifrados como no grfio/des do rAthena (GPL), um
DES de uma volta só nos primeiros blocos e depois a cada `ciclo` blocos, com troca de bytes a cada 7.
Os formatos .spr e .act seguem o que a comunidade documentou (roBrowser, ferramentas de GRF).
"""

import base64
import math
import os
import re
import struct
import threading
import zlib

import gamecache
import gdip
import lub

WARDROBE_FILE = "sprites_do_personagem.json"      # tabelas do guarda-roupa guardadas em disco (gamecache)
BESTIARY_FILE = "sprites_dos_monstros.json"       # id do monstro -> nome do arquivo do sprite
HUMAN = "data\\sprite\\인간족\\"
DORAM = "data\\sprite\\도람족\\"
ACC = "data\\sprite\\악세사리\\"
ROBE = "data\\sprite\\로브\\"
SHIELD = "data\\sprite\\방패\\"
PAL = "data\\palette\\"
LUA = "data\\luafiles514\\lua files\\datainfo\\"
PREFIXES = (HUMAN, DORAM, ACC, ROBE, SHIELD, PAL, LUA)
MONSTER = "data\\sprite\\몬스터\\"
SEX = {0: "여", 1: "남"}

# grupos de ação do .act de jogador (cada grupo tem 8 direções)
IDLE, WALK, SIT, PICK, READY, ATTACK, HURT, FREEZE, DEAD, FREEZE2, ATTACK2, ATTACK3, CAST = range(13)
ACTIONS = [(IDLE, "Parado"), (WALK, "Andando"), (SIT, "Sentado"), (READY, "Em guarda"), (ATTACK, "Atacando"),
           (CAST, "Conjurando"), (HURT, "Levando dano"), (DEAD, "Caído")]
HEAD_DIRS = [(0, "Frente"), (1, "Esquerda"), (2, "Direita")]
BACK_DIRS = {3, 4, 5}                 # de costas: capa e escudo por cima do corpo
DIRECTIONS = ["↓", "↙", "←", "↖", "↑", "↗", "→", "↘"]   # para onde o boneco olha (↓ = de frente)

# nome do sprite do corpo por classe (o cliente guarda isso no executável)
_CLASSIC = ["초보자", "검사", "마법사", "궁수", "성직자", "상인", "도둑", "기사", "프리스트", "위저드", "제철공", "헌터",
            "어세신", "페코페코_기사", "크루세이더", "몽크", "세이지", "로그", "연금술사", "바드", "무희", "신페코크루세이더",
            "결혼", "슈퍼노비스", "건너", "닌자", "산타", "여름", "한복", "옥토버패스트", "여름2"]
_TRANS = ["초보자", "검사", "마법사", "궁수", "성직자", "상인", "도둑", "로드나이트", "하이프리", "하이위저드", "화이트스미스",
          "스나이퍼", "어쌔신크로스", "로드페코", "팔라딘", "챔피온", "프로페서", "스토커", "크리에이터", "클라운", "집시",
          "페코팔라딘"]
_BABY = ["초보자", "검사", "마법사", "궁수", "성직자", "상인", "도둑", "기사", "프리스트", "위저드", "제철공", "헌터",
         "어세신", "페코페코_기사", "크루세이더", "몽크", "세이지", "로그", "연금술사", "바드", "무희", "신페코크루세이더",
         "슈퍼노비스"]
_THIRD = ["룬나이트", "워록", "레인져", "아크비숍", "미케닉", "길로틴크로스"]
_THIRD2 = ["로얄가드", "소서러", "민스트럴", "원더러", "슈라", "제네릭", "쉐도우체이서"]
JOB_SPRITE = dict(enumerate(_CLASSIC))
JOB_SPRITE.update({4001 + i: n for i, n in enumerate(_TRANS)})
JOB_SPRITE.update({4023 + i: n for i, n in enumerate(_BABY)})
JOB_SPRITE.update({4046: "태권소년", 4047: "권성", 4048: "권성융합", 4049: "소울링커"})
JOB_SPRITE.update({4054 + i: n for i, n in enumerate(_THIRD)})
JOB_SPRITE.update({4060 + i: n for i, n in enumerate(_THIRD)})
JOB_SPRITE.update({4066 + i: n for i, n in enumerate(_THIRD2)})
JOB_SPRITE.update({4073 + i: n for i, n in enumerate(_THIRD2)})
JOB_SPRITE.update({4080: "페코페코_룬나이트", 4081: "페코페코_룬나이트", 4082: "그리폰가드", 4083: "그리폰가드",
                   4084: "레인져늑대", 4085: "레인져늑대", 4086: "마도기어", 4087: "마도기어"})
JOB_SPRITE.update({4096 + i: n for i, n in enumerate(_THIRD + _THIRD2)})
JOB_SPRITE.update({4109: "페코페코_룬나이트", 4110: "그리폰가드", 4111: "레인져늑대", 4112: "마도기어",
                   4190: "슈퍼노비스", 4191: "슈퍼노비스", 4211: "kagerou", 4212: "oboro", 4215: "rebellion",
                   4218: "summoner", 4239: "성제", 4240: "소울리퍼", 4241: "성제", 4242: "소울리퍼", 4243: "성제융합",
                   4244: "성제융합"})
_FOURTH = ["dragon_knight", "meister", "shadow_cross", "arch_mage", "cardinal", "windhawk", "imperial_guard", "biolo",
           "abyss_chaser", "elemetal_master", "inquisitor", "troubadour", "trouvere"]
JOB_SPRITE.update({4252 + i: n for i, n in enumerate(_FOURTH)})
JOB_SPRITE.update({4278: "wolf_windhawk", 4279: "meister_madogear1", 4280: "dragon_knight_chicken",
                   4281: "imperial_guard_chicken", 4302: "sky_emperor", 4303: "soul_ascetic", 4304: "shinkiro",
                   4305: "shiranui", 4306: "night_watch", 4307: "hyper_novice", 4308: "spirit_handler",
                   4316: "sky_emperor2"})
DORAM_JOBS = {4218, 4220, 4308}
FLYING = 0x8000                       # OPTION_FLYING: Imperador Celeste em voo (sky_emperor2)
MADOGEAR = 0x400000
FLYING_SPRITE = {4302: "sky_emperor2", 4047: "권성융합", 4239: "성제융합"}
MADO_SPRITE = {4253: "meister_madogear1", 4058: "마도기어", 4064: "마도기어", 4100: "마도기어"}
SHIELD_NAMES = {1: "_가드", 2: "_버클러", 3: "_쉴드", 4: "_미러쉴드"}

# slots (máscara do rAthena) de onde sai cada parte do visual: o visual (costume) vale mais que o normal
VIEW_SLOTS = {"top": (1024, 256), "mid": (2048, 512), "low": (4096, 1), "robe": (8192, 4)}


def job_sprite(job, option=0):
    if option & FLYING and job in FLYING_SPRITE:
        return FLYING_SPRITE[job]
    if option & MADOGEAR and job in MADO_SPRITE:
        return MADO_SPRITE[job]
    return JOB_SPRITE.get(job)


# ------------------------------------------------------------------ .grf (com os arquivos cifrados)

_MASK = (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01)
_IP = (58, 50, 42, 34, 26, 18, 10, 2, 60, 52, 44, 36, 28, 20, 12, 4, 62, 54, 46, 38, 30, 22, 14, 6,
       64, 56, 48, 40, 32, 24, 16, 8, 57, 49, 41, 33, 25, 17, 9, 1, 59, 51, 43, 35, 27, 19, 11, 3,
       61, 53, 45, 37, 29, 21, 13, 5, 63, 55, 47, 39, 31, 23, 15, 7)
_FP = (40, 8, 48, 16, 56, 24, 64, 32, 39, 7, 47, 15, 55, 23, 63, 31, 38, 6, 46, 14, 54, 22, 62, 30,
       37, 5, 45, 13, 53, 21, 61, 29, 36, 4, 44, 12, 52, 20, 60, 28, 35, 3, 43, 11, 51, 19, 59, 27,
       34, 2, 42, 10, 50, 18, 58, 26, 33, 1, 41, 9, 49, 17, 57, 25)
_TP = (16, 7, 20, 21, 29, 12, 28, 17, 1, 15, 23, 26, 5, 18, 31, 10, 2, 8, 24, 14, 32, 27, 3, 9,
       19, 13, 30, 6, 22, 11, 4, 25)
_S = bytes.fromhex(
    "ef0341fdd8741e4726effb22b3d8841e39aca76062c1cdba5c969059053b7a8540fd1ec8e78a8b21da43649f2d14b172"
    "f55bc8b69c3776ec39a0a305526e0fd9a7dd0d789e0be3956036364ff9605aa31124d287c85275ecbbc14cba24fe8f19"
    "da1366af49d090068c6afb91378d0d78bf4911f423e5ce3b55bca257e82274ce2ceac1bf4a241fc27947a27cb6d96815"
    "80565d0133fdf4aede30079be5839b6849b42e831fc2b57ca219d8e57c2f83daf76b90fec4015a9761a63d400b58e63d"
    "4dd1b20f28bde478f64a0f938b17d1a43aecc93593567ecb5520a0fe6c89176217624bb1b4ded187c9143c4a7ea8e27d"
    "a09ff65c6a098df00fe35325953628cb")
_SUBST = {0x00: 0x2B, 0x2B: 0x00, 0x6C: 0x80, 0x01: 0x68, 0x68: 0x01, 0x48: 0x77, 0x60: 0xFF, 0x77: 0x48,
          0xB9: 0xC0, 0xC0: 0xB9, 0xFE: 0xEB, 0xEB: 0xFE, 0x80: 0x6C, 0xFF: 0x60}


def _perm(src, table):
    out = bytearray(8)
    for i, j in enumerate(table):
        j -= 1
        if src[j >> 3] & _MASK[j & 7]:
            out[i >> 3] |= _MASK[i & 7]
    return out


def _round(b):
    e = (((b[7] << 5) | (b[4] >> 3)) & 0x3F, ((b[4] << 1) | (b[5] >> 7)) & 0x3F,
         ((b[4] << 5) | (b[5] >> 3)) & 0x3F, ((b[5] << 1) | (b[6] >> 7)) & 0x3F,
         ((b[5] << 5) | (b[6] >> 3)) & 0x3F, ((b[6] << 1) | (b[7] >> 7)) & 0x3F,
         ((b[6] << 5) | (b[7] >> 3)) & 0x3F, ((b[7] << 1) | (b[4] >> 7)) & 0x3F)
    sb = bytearray(4)
    for i in range(4):
        sb[i] = (_S[i * 64 + e[i * 2]] & 0xF0) | (_S[i * 64 + e[i * 2 + 1]] & 0x0F)
    tp = bytearray(4)
    for i, j in enumerate(_TP):
        j -= 1
        if sb[j >> 3] & _MASK[j & 7]:
            tp[i >> 3] |= _MASK[i & 7]
    for i in range(4):
        b[i] ^= tp[i]


def _des_block(buf, off):
    b = _perm(buf[off:off + 8], _IP)
    _round(b)
    buf[off:off + 8] = _perm(b, _FP)


def decode(buf, flags, packed):
    """Decifra no lugar um arquivo do .grf (flags 2 = misto, 4 = só o começo)."""
    n = len(buf) // 8
    if flags & 2:
        digits, i = 1, 10
        while i <= packed:
            digits += 1
            i *= 10
        cycle = 1 if digits < 3 else digits + 1 if digits < 5 else digits + 9 if digits < 7 else digits + 15
        for i in range(min(20, n)):
            _des_block(buf, i * 8)
        j = -1
        for i in range(20, n):
            if i % cycle == 0:
                _des_block(buf, i * 8)
                continue
            j += 1
            if j % 7 == 0 and j != 0:
                s = buf[i * 8:i * 8 + 8]
                buf[i * 8:i * 8 + 8] = bytes((s[3], s[4], s[6], s[0], s[1], s[2], s[5], _SUBST.get(s[7], s[7])))
    elif flags & 4:
        for i in range(min(20, n)):
            _des_block(buf, i * 8)


def _key(name):
    return name.encode("cp949", "replace").lower()


class Grf:
    """Índice só das pastas de sprites, paletas e tabelas do .grf; lê (e decifra) um arquivo por vez."""

    def __init__(self, path, prefixes=PREFIXES):
        self.path = path
        self.index = {}
        with open(path, "rb") as f:
            head = f.read(46)
            version = struct.unpack_from("<I", head, 42)[0]
            if version == 0x300:
                table, entry = struct.unpack_from("<Q", head, 30)[0] + 46 + 4, struct.Struct("<IIIBQ")
            elif version == 0x200:
                table, entry = struct.unpack_from("<I", head, 30)[0] + 46, struct.Struct("<IIIBI")
            else:
                raise ValueError("versão de .grf desconhecida: 0x%x" % version)
            f.seek(table)
            packed, _size = struct.unpack("<II", f.read(8))
            raw = zlib.decompress(f.read(packed))
        # só os nomes que começam com as pastas pedidas, achados por expressão regular (em C): a tabela tem
        # centenas de milhares de arquivos, e passar por todos num laço levava uns 0,3 s com a janela esperando
        pres = sorted({_key(p) for p in prefixes}, key=len, reverse=True)
        wanted = re.compile(b"(?:" + b"|".join(re.escape(p) for p in pres) + b")[^\\x00]*\\x00", re.I)
        limit = len(raw) - entry.size
        for m in wanted.finditer(raw):
            if m.end() <= limit:
                self.index[m.group()[:-1].lower()] = entry.unpack_from(raw, m.end())

    def has(self, name):
        return _key(name) in self.index

    def read(self, name):
        e = self.index.get(_key(name))
        if e is None:
            return None
        packed, aligned, real, flags, offset = e
        if not flags & 1:
            return None
        with open(self.path, "rb") as f:
            f.seek(offset + 46)
            buf = f.read(aligned if flags & 6 else packed)
        if flags & 6:
            buf = bytearray(buf)
            decode(buf, flags, packed)
        try:
            return zlib.decompressobj().decompress(bytes(buf[:packed]))[:real]
        except zlib.error:
            return None


# ------------------------------------------------------------------ .spr e .act

_RLE = re.compile(rb"\x00([\x00-\xff])", re.S)       # zeros comprimidos do .spr: (0, n) = n zeros
_OPAQUE = b"\0" + b"\xff" * 255                       # transparência da paleta: só o índice 0 é vazado


def _png(w, h, color_type, rows, extra=b""):
    """PNG dos bytes já prontos (uma linha por vez, cada uma com o byte de filtro 0 na frente)."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)) + extra
            + chunk(b"IDAT", zlib.compress(rows, 1)) + chunk(b"IEND", b""))


def _scale_table(k):
    """Tabela de bytes que multiplica por k/255 (para tingir um canal inteiro de uma vez)."""
    return bytes(i * k // 255 for i in range(256))


def png_rgba(w, h, data):
    """PNG (bytes) dos bytes RGBA de cima para baixo."""
    return _png(w, h, 6, b"".join(b"\0" + data[y * w * 4:(y + 1) * w * 4] for y in range(h)))


class Sprite:
    """Imagens de um .spr: indexadas (com a paleta do arquivo) e RGBA. Nada é decodificado antes de ser pedido:
    um chefe tem dezenas de imagens e cada tela usa só as de uma ação."""

    def __init__(self, data):
        if data[:2] != b"SP":
            raise ValueError("não é .spr")
        ver = data[2] | data[3] << 8
        n_idx = struct.unpack_from("<H", data, 4)[0]
        n_rgba = struct.unpack_from("<H", data, 6)[0] if ver >= 0x200 else 0
        pos = 8 if ver >= 0x200 else 6
        self.palette = data[-1024:] if ver >= 0x101 and len(data) >= 1024 else bytes(1024)
        self._idx_src = []                # (w, h, bytes, comprimido?) de cada imagem indexada
        for _ in range(n_idx):
            w, h = struct.unpack_from("<HH", data, pos)
            pos += 4
            if ver >= 0x201:              # zeros comprimidos (0, n)
                size = struct.unpack_from("<H", data, pos)[0]
                pos += 2
                self._idx_src.append((w, h, data[pos:pos + size], True))
                pos += size
            else:
                self._idx_src.append((w, h, data[pos:pos + w * h], False))
                pos += w * h
        self._rgba_src = []               # (w, h, bytes ABGR de baixo para cima) de cada imagem RGBA
        for _ in range(n_rgba):
            w, h = struct.unpack_from("<HH", data, pos)
            pos += 4
            self._rgba_src.append((w, h, data[pos:pos + w * h * 4]))
            pos += w * h * 4
        self._idx = {}
        self._rgba = {}
        self._cache = {}

    def index(self, i):
        """(w, h, índices) da imagem indexada i."""
        got = self._idx.get(i)
        if got is None:
            w, h, src, packed = self._idx_src[i]
            if packed:
                src = _RLE.sub(lambda m: bytes(m.group(1)[0]), src)
            got = self._idx[i] = (w, h, bytes(src[:w * h]).ljust(w * h, b"\0"))
        return got

    def rgba_bytes(self, i):
        """(w, h, bytes RGBA de cima para baixo) da imagem RGBA i (no arquivo ela vem ABGR, de baixo para cima)."""
        got = self._rgba.get(i)
        if got is None:
            w, h, raw = self._rgba_src[i]
            raw = bytes(raw).ljust(w * h * 4, b"\0")
            out = bytearray(len(raw))
            out[0::4], out[1::4], out[2::4], out[3::4] = raw[3::4], raw[2::4], raw[1::4], raw[0::4]
            got = self._rgba[i] = (w, h, b"".join(bytes(out[y * w * 4:(y + 1) * w * 4]) for y in range(h - 1, -1, -1)))
        return got

    def size(self, kind, i):
        """(w, h) da imagem, ou None se não existir."""
        src = self._rgba_src if kind == 1 else self._idx_src
        return src[i][:2] if 0 <= i < len(src) else None

    def png(self, kind, i, palette=None, tint=None):
        """A imagem como PNG (bytes), feita direto dos bytes do arquivo, sem passar pixel por pixel.
        `tint`: (r, g, b, a) da camada do .act, quando ela tinge ou deixa a imagem translúcida."""
        if self.size(kind, i) is None:
            return None
        r, g, b, a = tint or (255, 255, 255, 255)
        if kind == 1:
            w, h, data = self.rgba_bytes(i)
            if (r, g, b, a) != (255, 255, 255, 255):
                out = bytearray(data)
                for ch, k in enumerate((r, g, b, a)):
                    if k != 255:
                        out[ch::4] = data[ch::4].translate(_scale_table(k))
                data = bytes(out)
            return _png(w, h, 6, b"".join(b"\0" + data[y * w * 4:(y + 1) * w * 4] for y in range(h)))
        w, h, idx = self.index(i)
        pal = palette or self.palette
        rgb = bytearray(768)
        for ch, k in enumerate((r, g, b)):
            plane = pal[ch:1024:4]
            rgb[ch::3] = plane.translate(_scale_table(k)) if k != 255 else plane
        alpha = _OPAQUE if a == 255 else b"\0" + bytes([a]) * 255

        def chunk(kind_, body):
            return struct.pack(">I", len(body)) + kind_ + body + struct.pack(">I", zlib.crc32(kind_ + body) & 0xFFFFFFFF)
        return _png(w, h, 3, b"".join(b"\0" + idx[y * w:(y + 1) * w] for y in range(h)),
                    chunk(b"PLTE", bytes(rgb)) + chunk(b"tRNS", alpha))

    def bgra(self, kind, i, palette=None, tint=None):
        """(w, h, bytes BGRA de cima para baixo) da imagem, com a paleta (e a cor da camada, `tint`) já aplicadas,
        ou None se não existir. Canal a canal, sem passar pixel por pixel: é o que o GDI+ desenha (gdip.py)."""
        if self.size(kind, i) is None:
            return None
        r, g, b, a = tint or (255, 255, 255, 255)
        if kind == 1:
            w, h, data = self.rgba_bytes(i)
            out = bytearray(len(data))
            for dst, src, k in ((0, 2, b), (1, 1, g), (2, 0, r), (3, 3, a)):
                plane = data[src::4]
                out[dst::4] = plane.translate(_scale_table(k)) if k != 255 else plane
            return w, h, bytes(out)
        w, h, idx = self.index(i)
        pal = palette or self.palette
        out = bytearray(w * h * 4)
        for dst, src, k in ((0, 2, b), (1, 1, g), (2, 0, r)):
            table = pal[src:1024:4]
            out[dst::4] = idx.translate(table.translate(_scale_table(k)) if k != 255 else table)
        out[3::4] = idx.translate(_OPAQUE if a == 255 else b"\0" + bytes([a]) * 255)
        return w, h, bytes(out)

    def image(self, kind, i, palette=None):
        """(w, h, [(r, g, b, a)]) da imagem i (kind 0 = indexada, 1 = RGBA); palette troca a do arquivo.
        É o caminho lento, pixel a pixel: serve o personagem e os desenhos parados."""
        if kind == 1:
            if not 0 <= i < len(self._rgba_src):
                return None
            key = ("rgba", i)
            img = self._cache.get(key)
            if img is None:
                w, h, data = self.rgba_bytes(i)
                img = self._cache[key] = (w, h, [tuple(data[k:k + 4]) for k in range(0, len(data), 4)])
            return img
        if not 0 <= i < len(self._idx_src):
            return None
        pal = palette or self.palette
        key = (i, id(pal))
        img = self._cache.get(key)
        if img is None:
            colors = [(pal[k * 4], pal[k * 4 + 1], pal[k * 4 + 2], 255) for k in range(256)]
            colors[0] = (0, 0, 0, 0)
            w, h, idx = self.index(i)
            img = self._cache[key] = (w, h, [colors[k] for k in idx])
        return img


class Layer:
    __slots__ = ("x", "y", "index", "mirror", "color", "sx", "sy", "kind", "rot")

    def __init__(self, x, y, index, mirror, color=(255, 255, 255, 255), sx=1.0, sy=1.0, kind=0, rot=0):
        self.x, self.y, self.index, self.mirror = x, y, index, mirror
        self.color, self.sx, self.sy, self.kind = color, sx, sy, kind
        self.rot = rot                # giro em graus (os monstros montados em peças usam)


class Act:
    """Ações de um .act: actions[i] = [(camadas, âncoras)], delays[i] = ms por quadro."""

    def __init__(self, data):
        if data[:2] != b"AC":
            raise ValueError("não é .act")
        ver = data[2] | data[3] << 8
        n_act = struct.unpack_from("<H", data, 4)[0]
        pos = 16
        self.actions = []
        for _a in range(n_act):
            n_fr = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            frames = []
            for _f in range(n_fr):
                pos += 32
                n_lay = struct.unpack_from("<I", data, pos)[0]
                pos += 4
                layers = []
                for _l in range(n_lay):
                    x, y, si, mirror = struct.unpack_from("<iiii", data, pos)
                    pos += 16
                    color, sx, sy, kind, rot = (255, 255, 255, 255), 1.0, 1.0, 0, 0
                    if ver >= 0x200:
                        color = tuple(data[pos:pos + 4])
                        pos += 4
                        if ver >= 0x204:
                            sx, sy = struct.unpack_from("<ff", data, pos)
                            pos += 8
                        else:
                            sx = sy = struct.unpack_from("<f", data, pos)[0]
                            pos += 4
                        rot, kind = struct.unpack_from("<ii", data, pos)
                        pos += 8
                        if ver >= 0x205:
                            pos += 8
                    layers.append(Layer(x, y, si, mirror, color, sx, sy, kind, rot))
                if ver >= 0x200:
                    pos += 4                         # som/evento do quadro
                anchors = []
                if ver >= 0x203:
                    n_anc = struct.unpack_from("<i", data, pos)[0]
                    pos += 4
                    for _k in range(max(0, n_anc)):
                        ax, ay = struct.unpack_from("<ii", data, pos + 4)
                        anchors.append((ax, ay))
                        pos += 16
                frames.append((layers, anchors))
            self.actions.append(frames)
        self.delays = [150.0] * n_act
        try:
            if ver >= 0x201:
                n_ev = struct.unpack_from("<i", data, pos)[0]
                pos += 4 + 40 * max(0, n_ev)
            if ver >= 0x202:
                self.delays = [max(40.0, 25.0 * d) for d in struct.unpack_from("<%df" % n_act, data, pos)]
        except struct.error:
            pass

    def frames(self, action):
        if not self.actions:
            return []
        return self.actions[action] if action < len(self.actions) else self.actions[action % len(self.actions)]


class Part:
    """Um pedaço do personagem (corpo, cabeça, chapéu...): .spr + .act + paleta opcional."""

    def __init__(self, name, spr, act, palette=None, anchored=True):
        self.name, self.spr, self.act, self.palette, self.anchored = name, spr, act, palette, anchored


# ------------------------------------------------------------------ montagem

def frame_of(action, count, frame, head_dir=0):
    """Quadro a usar: parado e sentado mostram a direção da cabeça (0 frente, 1 esq., 2 dir.); o resto anima."""
    if count <= 0:
        return 0
    return min(head_dir, count - 1) if action in (IDLE, SIT) else frame % count


def smooth_frames(part, frames, cache=None):
    """Os quadros de um monstro montados pelo GDI+ (gdip.py) no tamanho natural, todos na mesma moldura:
    (w, h, [bytes BGRA de cima para baixo]) ou None se não der (aí vale `compose`, pixel a pixel).
    As camadas sem escala nem giro entram pixel a pixel; as outras (peças em escala ou giradas, como as da
    Betelgeuse) entram suavizadas, na escala e no ângulo exatos. `frames`: [(camadas, âncoras)] do .act;
    `cache` guarda as imagens do .spr já convertidas, para quem monta várias ações do mesmo monstro."""
    if not gdip.ready():
        return None
    cache = {} if cache is None else cache
    per_frame, boxes = [], []
    for frame_layers, _anchors in frames:
        items = []
        for ly in frame_layers:
            size = part.spr.size(ly.kind, ly.index) if ly.index >= 0 else None
            if size is None:
                continue
            sw, sh = size
            sx, sy = abs(ly.sx) or 1.0, abs(ly.sy) or 1.0
            rot = getattr(ly, "rot", 0) % 360
            flip = -1.0 if ly.mirror else 1.0
            if rot == 0 and abs(sx - 1.0) < 0.005 and abs(sy - 1.0) < 0.005:
                left, top = int(round(ly.x - sw / 2.0)), int(round(ly.y - sh / 2.0))
                m = (flip, 0.0, 0.0, 1.0, left + sw / 2.0, top + sh / 2.0, False)
                box = (left, top, left + sw, top + sh)
            else:
                a = math.radians(rot)
                cos, sin = math.cos(a), math.sin(a)
                m = (flip * sx * cos, flip * sx * sin, -sy * sin, sy * cos, float(ly.x), float(ly.y), True)
                xs = [u * m[0] + v * m[2] + m[4] for u in (-sw / 2.0, sw / 2.0) for v in (-sh / 2.0, sh / 2.0)]
                ys = [u * m[1] + v * m[3] + m[5] for u in (-sw / 2.0, sw / 2.0) for v in (-sh / 2.0, sh / 2.0)]
                box = (int(math.floor(min(xs))), int(math.floor(min(ys))),
                       int(math.ceil(max(xs))), int(math.ceil(max(ys))))
            items.append((ly, m))
            boxes.append(box)
        per_frame.append(items)
    if not boxes:
        return None
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    w, h = max(b[2] for b in boxes) - x0, max(b[3] for b in boxes) - y0
    if w <= 0 or h <= 0 or w * h > 4000000:
        return None
    out = []
    try:
        for items in per_frame:
            draws = []
            for ly, m in items:
                tint = tuple(ly.color) if tuple(ly.color) != (255, 255, 255, 255) else None
                key = ("gdi", ly.kind, ly.index, tint)
                src = cache.get(key)
                if src is None:
                    src = cache[key] = gdip.Image(*part.spr.bgra(ly.kind, ly.index,
                                                                 part.palette if ly.kind == 0 else None, tint))
                draws.append((src, m[0], m[1], m[2], m[3], m[4] - x0, m[5] - y0, m[6]))
            data = gdip.render(w, h, draws)
            if data is None:
                return None
            out.append(data)
    except (ValueError, TypeError, OSError):
        return None
    return w, h, out


def compose(order, body, action, direction, frame, head_dir=0):
    """Desenha as partes na ordem `order`; cabeça e chapéus se prendem à âncora do corpo `body`.
    Devolve (w, h, pixels [(r, g, b, a)], x da origem, y da origem) ou None."""
    act_i = action * 8 + direction
    frames = body.act.frames(act_i)
    if not frames:
        return None
    anchors = frames[frame_of(action, len(frames), frame, head_dir)][1]
    body_anchor = anchors[0] if anchors else None
    draws = []
    for part in order:
        frames = part.act.frames(act_i)
        if not frames:
            continue
        layers, anchors = frames[frame_of(action, len(frames), frame, head_dir)]
        ox = oy = 0
        if part is not body and part.anchored and body_anchor and anchors:
            ox, oy = body_anchor[0] - anchors[0][0], body_anchor[1] - anchors[0][1]
        for ly in layers:
            if ly.index < 0:
                continue
            img = part.spr.image(ly.kind, ly.index, part.palette if ly.kind == 0 else None)
            if img is None:
                continue
            w, h, px = img
            sx, sy = abs(ly.sx) or 1.0, abs(ly.sy) or 1.0
            dw, dh = max(1, int(round(w * sx))), max(1, int(round(h * sy)))
            left = int(round(ox + ly.x - dw / 2.0))
            top = int(round(oy + ly.y - dh / 2.0))
            draws.append((left, top, dw, dh, w, h, px, sx, sy, ly.mirror, ly.color))
    if not draws:
        return None
    x0 = min(d[0] for d in draws)
    y0 = min(d[1] for d in draws)
    x1 = max(d[0] + d[2] for d in draws)
    y1 = max(d[1] + d[3] for d in draws)
    W, H = x1 - x0, y1 - y0
    out = [(0, 0, 0, 0)] * (W * H)
    for left, top, dw, dh, w, h, px, sx, sy, mirror, color in draws:
        cr, cg, cb, ca = color
        tint = (cr, cg, cb) != (255, 255, 255)
        for yy in range(dh):
            v = min(h - 1, int(yy / sy))
            row = v * w
            base = (top - y0 + yy) * W + (left - x0)
            for xx in range(dw):
                u = min(w - 1, int(xx / sx))
                if mirror:
                    u = w - 1 - u
                r, g, b, a = px[row + u]
                if a == 0:
                    continue
                if ca != 255:
                    a = a * ca // 255
                    if a == 0:
                        continue
                if tint:
                    r, g, b = r * cr // 255, g * cg // 255, b * cb // 255
                i = base + xx
                if a == 255:
                    out[i] = (r, g, b, 255)
                else:
                    br, bg_, bb, ba = out[i]
                    k = a / 255.0
                    out[i] = (int(r * k + br * (1 - k)), int(g * k + bg_ * (1 - k)), int(b * k + bb * (1 - k)),
                              max(a, ba))
    return W, H, out, -x0, -y0


def png(w, h, px):
    """PNG RGBA (bytes) dos pixels."""
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for p in px[y * w:(y + 1) * w]:
            raw += bytes(p)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def png_b64(w, h, px):
    return base64.b64encode(png(w, h, px)).decode("ascii")


# ------------------------------------------------------------------ o visual de quem gravou

def look_at(base, worn, classnum):
    """Visual num instante: `base` (do início da gravação: classe, sexo, cabelo, cores, chapéus...) com os
    chapéus, a capa, a arma e o escudo trocados pelos itens vestidos (`worn` = {bit do slot: Item}) quando o
    ClassNum deles é conhecido."""
    look = dict(base)
    if not classnum:
        return look
    for key, (visual, normal) in VIEW_SLOTS.items():
        view = 0
        for bit in (visual, normal):
            it = worn.get(bit)
            if it is not None and classnum.get(it.item_id):
                view = classnum[it.item_id]
                break
        look[key] = view
    weapon = worn.get(2)
    look["weapon"] = weapon.item_id if weapon is not None else 0
    shield = worn.get(32)
    look["shield"] = shield.item_id if shield is not None else 0
    return look


class Wardrobe:
    """Tabelas do cliente + leitura das partes do personagem (com cache)."""

    def __init__(self, grf_path):
        self.grf = Grf(grf_path)
        self.acc, self.robe, self.weapon, self.weapon_base, self.classnum = {}, {}, {}, {}, {}
        self._parts = {}
        self._pal = {}

        def table(name, glob):
            data = self.grf.read(LUA + name)
            if not data:
                return {}
            try:
                return lub.run(data, "cp949").get(glob) or {}
            except (ValueError, struct.error, IndexError, KeyError):
                return {}
        # as tabelas de nomes (acessórios, capas, armas) ficam guardadas enquanto o data.grf não mudar
        mark = gamecache.stamp(grf_path)
        saved = gamecache.load(WARDROBE_FILE, mark)
        if saved is None:
            ids = table("accessoryid.lub", "ACCESSORY_IDs")
            names = table("accname.lub", "AccNameTable")
            acc = {ids[k[1]]: v for k, v in names.items()
                   if isinstance(k, lub.Symbol) and len(k) > 1 and k[1] in ids and isinstance(v, str)}
            ids = table("spriterobeid.lub", "SPRITE_ROBE_IDs")
            names = table("spriterobename.lub", "RobeNameTable")
            robe = {ids[k[1]]: v for k, v in names.items()
                    if isinstance(k, lub.Symbol) and len(k) > 1 and k[1] in ids and isinstance(v, str)}
            weapon = {k: v for k, v in table("weapontable.lub", "WeaponNameTable").items()
                      if isinstance(k, int) and isinstance(v, str)}
            base = {k: v for k, v in table("weapontable.lub", "Expansion_Weapon_IDs").items()
                    if isinstance(k, int) and isinstance(v, int)}
            saved = dict(acc={str(k): v for k, v in acc.items()}, robe={str(k): v for k, v in robe.items()},
                         weapon={str(k): v for k, v in weapon.items()}, weapon_base={str(k): v for k, v in base.items()})
            if acc or robe or weapon:
                gamecache.save(WARDROBE_FILE, mark, saved)
        self.acc = {int(k): v for k, v in saved["acc"].items()}
        self.robe = {int(k): v for k, v in saved["robe"].items()}
        self.weapon = {int(k): v for k, v in saved["weapon"].items()}
        self.weapon_base = {int(k): v for k, v in saved["weapon_base"].items()}
        item_file = os.path.join(os.path.dirname(grf_path), "System", "iteminfo_new.lub")
        try:
            self.classnum = gamecache.items(item_file)["classnum"]
        except (OSError, ValueError, struct.error, IndexError, KeyError):
            self.classnum = {}

    def palette(self, path):
        if path not in self._pal:
            data = self.grf.read(path)
            self._pal[path] = data[:1024] if data and len(data) >= 1024 else None
        return self._pal[path]

    def part(self, name, base, palette=None, anchored=True, spr_path=None):
        """Parte pelo caminho sem extensão; None se faltar no .grf ou não der para ler.
        spr_path: .spr de outro lugar (capas que usam um .spr só para todas as classes)."""
        key = (base, palette, spr_path)
        if key not in self._parts:
            spr, act = self.grf.read(spr_path or base + ".spr"), self.grf.read(base + ".act")
            try:
                self._parts[key] = Part(name, Sprite(spr), Act(act),
                                        self.palette(palette) if palette else None, anchored) if spr and act else None
            except (ValueError, struct.error, IndexError):
                self._parts[key] = None
        return self._parts[key]

    def parts(self, look, direction):
        """Partes na ordem de desenho, o corpo e o que faltou: ([Part], Part, [nome que não achou])."""
        sex = SEX.get(look.get("sex", 1), "남")
        job = job_sprite(look.get("job", 0), look.get("option", 0))
        race = DORAM if look.get("job") in DORAM_JOBS else HUMAN
        missing = []
        if not job or not self.grf.has("%s몸통\\%s\\%s_%s.spr" % (race, sex, job, sex)):
            plain = JOB_SPRITE.get(look.get("job", 0))
            if plain and self.grf.has("%s몸통\\%s\\%s_%s.spr" % (race, sex, plain, sex)):
                job = plain
            else:
                missing.append("corpo")
                job = "초보자"
        cloth = look.get("cloth_color", 0)
        body = self.part("corpo", "%s몸통\\%s\\%s_%s" % (race, sex, job, sex),
                         "%s몸\\%s_%s_%d.pal" % (PAL, job, sex, cloth) if cloth else None, anchored=False)
        if body is None:
            return [], None, missing + ["corpo"]
        hair, hcol = look.get("hair", 1) or 1, look.get("hair_color", 0)
        head = self.part("cabeça", "%s머리통\\%s\\%d_%s" % (race, sex, hair, sex),
                         "%s머리\\머리%d_%s_%d.pal" % (PAL, hair, sex, hcol) if hcol else None)
        if head is None:
            missing.append("cabeça")
        hats = []
        seen = set()
        for key in ("low", "mid", "top"):
            view = look.get(key) or 0
            if not view or view in seen:
                continue
            seen.add(view)
            name = self.acc.get(view)
            p = None
            if name:
                for folder in ((sex + "_doram",) if race == DORAM else ()) + (sex,):
                    p = self.part(key, "%s%s\\%s%s" % (ACC, folder, sex, name))
                    if p:
                        break
            if p:
                hats.append(p)
            else:
                missing.append(key)
        robe = self.robe_part(look.get("robe") or 0, job, sex, race)
        if look.get("robe") and robe is None:
            missing.append("robe")
        weapon = self.weapon_part(look, job, sex)
        shield = self.shield_part(look, job, sex)
        back = direction in BACK_DIRS
        order = []
        if robe and not back:
            order.append(robe)            # de frente e de lado a capa fica atrás do corpo
        if shield and back:
            order.append(shield)
        order.append(body)
        if head:
            order.append(head)
        order += hats                     # baixo, meio e topo
        if weapon:
            order.append(weapon)
        if shield and not back:
            order.append(shield)
        if robe and back:
            order.append(robe)
        return order, body, missing

    def robe_part(self, view, job, sex, race):
        """Capa/visual de capa: <nome>\\<sexo>\\<classe>_<sexo>; algumas têm uma subpasta repetida
        (<nome>\\<nome>\\...) e outras um .spr só, na raiz, para todas as classes (<nome>\\<nome>.spr)."""
        name = self.robe.get(view) if view else None
        if not name:
            return None
        for folder in (name, name + "\\" + name):
            base = "%s%s\\%s\\%s_%s" % (ROBE, folder, sex, job, sex)
            if not self.grf.has(base + ".act"):
                continue
            spr = None
            if not self.grf.has(base + ".spr"):
                spr = "%s%s\\%s%s.spr" % (ROBE, name, name, "_doram" if race == DORAM else "")
            p = self.part("robe", base, anchored=False, spr_path=spr)
            if p:
                return p
        return None

    def weapon_part(self, look, job, sex):
        item = look.get("weapon") or 0
        view = self.classnum.get(item, item if 0 < item < 100 else 0)
        for v in (view, self.weapon_base.get(view)):
            name = self.weapon.get(v) if v else None
            if name:
                p = self.part("weapon", "%s%s\\%s_%s%s" % (HUMAN, job, job, sex, name), anchored=False)
                if p:
                    return p
        return None

    def shield_part(self, look, job, sex):
        item = look.get("shield") or 0
        view = self.classnum.get(item, item if 0 < item < 100 else 0)
        if not view:
            return None
        for suffix in ("_%d_방패" % view, SHIELD_NAMES.get(view, "\0") + "_방패"):
            p = self.part("shield", "%s%s\\%s_%s%s" % (SHIELD, job, job, sex, suffix), anchored=False)
            if p:
                return p
        return None

    def render(self, look, action, direction, frame=0, head_dir=0):
        """Quadro montado: (w, h, pixels, x da origem, y da origem, delay em ms, nº de quadros, faltou) ou None."""
        order, body, missing = self.parts(look, direction)
        if body is None:
            return None
        res = compose(order, body, action, direction, frame, head_dir)
        if res is None:
            return None
        act_i = action * 8 + direction
        delay = body.act.delays[act_i] if act_i < len(body.act.delays) else 150.0
        return res + (delay, max(1, len(body.act.frames(act_i))), missing)


# ------------------------------------------------------------------ carga em segundo plano

class Loader:
    """Abre o guarda-roupa (índice do .grf + tabelas) numa thread; `ready` diz quando dá para desenhar."""

    def __init__(self):
        self.path = None
        self.wardrobe = None
        self.error = None
        self._thread = None
        self.version = 0

    def start(self, grf_path):
        if not grf_path or (self.path == grf_path and (self.wardrobe or self._thread)):
            return
        self.path, self.wardrobe, self.error = grf_path, None, None

        def run():
            try:
                self.wardrobe = Wardrobe(grf_path)
            except (OSError, ValueError, struct.error, zlib.error) as e:
                self.error = str(e) or e.__class__.__name__
            finally:
                self._thread = None
                self.version += 1
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    @property
    def loading(self):
        return self._thread is not None


LOADER = Loader()


# ------------------------------------------------------------------ resumo da morte no widget: monstro, armadilha
# e o personagem caído

ITEM_ART = "data\\texture\\유저인터페이스\\collection\\"   # ilustrações grandes dos itens (fundo branco)
TRAP_ART = "트랩.bmp"                                       # o item Armadilha: uma armadilha de urso
ITEM_ICON = "data\\texture\\유저인터페이스\\item\\"         # ícones pequenos (24 × 24) dos itens
MOB_IDLE, MOB_WALK, MOB_ATTACK, MOB_HURT, MOB_DIE = 0, 1, 2, 3, 4   # ações dos .act dos monstros
ANIM_FRAMES = 16              # a animação de um monstro usa no máximo estes quadros (pula os do meio)


def crop(w, h, px):
    """Tira as bordas transparentes: (w, h, pixels) ou None se não sobrar nada."""
    rows = [y for y in range(h) if any(p[3] for p in px[y * w:(y + 1) * w])]
    if not rows:
        return None
    cols = [x for x in range(w) if any(px[y * w + x][3] for y in rows)]
    x0, x1, y0, y1 = cols[0], cols[-1] + 1, rows[0], rows[-1] + 1
    return x1 - x0, y1 - y0, [px[y * w + x] for y in range(y0, y1) for x in range(x0, x1)]


def resize(w, h, px, tw, th):
    """Redimensiona para tw x th: média de alguns pontos por pixel ao reduzir, vizinho mais próximo ao ampliar."""
    n = max(1, min(4, int(-(-max(w / float(tw), h / float(th)) // 1))))
    out = []
    for y in range(th):
        for x in range(tw):
            r = g = b = a = 0
            for j in range(n):
                sy = min(h - 1, int((y + (j + 0.5) / n) * h / th))
                for i in range(n):
                    pr, pg, pb, pa = px[sy * w + min(w - 1, int((x + (i + 0.5) / n) * w / tw))]
                    r += pr * pa
                    g += pg * pa
                    b += pb * pa
                    a += pa
            out.append((r // a, g // a, b // a, a // (n * n)) if a else (0, 0, 0, 0))
    return out


def bmp_rgba(data):
    """(w, h, pixels RGBA) de um .bmp de 8 ou 24 bits; magenta (o transparente do jogo) vira transparente."""
    off = struct.unpack_from("<I", data, 10)[0]
    w, h, _planes, bpp = struct.unpack_from("<iiHH", data, 18)
    ncol = struct.unpack_from("<I", data, 46)[0] or (1 << bpp if bpp <= 8 else 0)
    pal = [tuple(data[54 + 4 * i:54 + 4 * i + 3][::-1]) for i in range(ncol)]
    flip, h = h > 0, abs(h)
    stride = ((w * bpp + 31) // 32) * 4
    px = []
    for y in range(h):
        start = off + (h - 1 - y if flip else y) * stride
        row = data[start:start + stride]
        for x in range(w):
            if bpp == 8:
                r, g, b = pal[row[x]]
            elif bpp == 24:
                b, g, r = row[3 * x:3 * x + 3]
            else:
                raise ValueError("bmp de %d bits" % bpp)
            px.append((r, g, b, 0 if (r > 240 and g < 16 and b > 240) else 255))
    return w, h, px


def clear_background(w, h, px, tol=24):
    """O fundo da cor do canto e ligado às bordas vira transparente (sem mexer nos claros do desenho)."""
    bg = px[0]
    out, seen = list(px), set()
    stack = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    while stack:
        x, y = stack.pop()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h):
            continue
        seen.add((x, y))
        p = px[y * w + x]
        if abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > tol:
            continue
        out[y * w + x] = (0, 0, 0, 0)
        stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return w, h, out


def dead_pose(wardrobe, look, direction=0):
    """O personagem caído (último quadro da ação de morte), sem bordas: (w, h, pixels) ou None."""
    r = wardrobe.render(look, DEAD, direction, 0)
    if r is None:
        return None
    if r[6] > 1:
        r = wardrobe.render(look, DEAD, direction, r[6] - 1) or r
    return crop(r[0], r[1], r[2])


class Bestiary:
    """Sprites dos monstros do data.grf: o id do monstro vira o nome do arquivo pelas tabelas do cliente
    (npcidentity: JT_NOME -> id; jobname: JT_NOME -> arquivo). Também a ilustração do item Armadilha.
    Só lê o que for pedido, e guarda."""

    def __init__(self, grf_path):
        self.grf = Grf(grf_path, prefixes=(MONSTER, LUA, ITEM_ART, ITEM_ICON))

        def table(name, glob):
            data = self.grf.read(LUA + name)
            if not data:
                return {}
            try:
                return lub.run(data, "cp949").get(glob) or {}
            except (ValueError, struct.error, IndexError, KeyError):
                return {}
        mark = gamecache.stamp(grf_path)
        saved = gamecache.load(BESTIARY_FILE, mark)
        if saved is None:
            ids = table("npcidentity.lub", "jobtbl")
            names = table("jobname.lub", "JobNameTable")
            saved = {str(ids[k[1]]): v for k, v in names.items()
                     if isinstance(k, lub.Symbol) and len(k) > 1 and k[1] in ids and isinstance(v, str)}
            if saved:
                gamecache.save(BESTIARY_FILE, mark, saved)
        self.names = {int(k): v for k, v in saved.items()}
        self.cache = {}

    def has(self, mob):
        name = self.names.get(mob)
        return bool(name) and self.grf.has(MONSTER + name + ".spr")

    def has_trap(self):
        return self.grf.has(ITEM_ART + TRAP_ART)

    def has_item(self, art):
        return bool(art) and self.grf.has(ITEM_ART + art + ".bmp")

    def item(self, art):
        """A ilustração de um item (pelo nome do arquivo dela), sem o fundo branco: (w, h, pixels) ou None."""
        key = ("item", art)
        if key not in self.cache:
            img = None
            data = self.grf.read(ITEM_ART + art + ".bmp") if art else None
            if data:
                try:
                    img = crop(*clear_background(*bmp_rgba(data)))
                except Exception:  # noqa: BLE001 - imagem estranha: fica sem desenho
                    img = None
            self.cache[key] = img
        return self.cache[key]

    def has_icon(self, art):
        return bool(art) and self.grf.has(ITEM_ICON + art + ".bmp")

    def icon(self, art):
        """O ícone pequeno (24 × 24) de um item, pelo nome do arquivo: (w, h, pixels) ou None."""
        key = ("icon", art)
        if key not in self.cache:
            img = None
            data = self.grf.read(ITEM_ICON + art + ".bmp") if art else None
            if data:
                try:
                    img = bmp_rgba(data)
                except Exception:  # noqa: BLE001 - imagem estranha: fica sem ícone
                    img = None
            self.cache[key] = img
        return self.cache[key]

    def part(self, mob):
        """O sprite e as ações do monstro (Part), lidos do data.grf e guardados; None se não houver."""
        key = ("part", mob)
        if key not in self.cache:
            got = None
            name = self.names.get(mob)
            spr = self.grf.read(MONSTER + name + ".spr") if name else None
            act = self.grf.read(MONSTER + name + ".act") if name else None
            if spr and act:
                try:
                    got = Part(name, Sprite(spr), Act(act))
                except Exception:  # noqa: BLE001 - sprite estranho (GRF modificada): fica sem desenho
                    got = None
            self.cache[key] = got
        return self.cache[key]

    def idle(self, mob):
        """Primeiro quadro do monstro parado e de frente, sem bordas: (w, h, pixels) ou None."""
        if mob in self.cache:
            return self.cache[mob]
        img = None
        part = self.part(mob)
        if part is not None:
            try:
                frames = part.act.frames(0)
                got = smooth_frames(part, frames[:1]) if frames else None
                if got:                    # montado pelo GDI+: peças em escala e giradas saem certas e suaves
                    w, h, shots = got
                    img = crop(w, h, list(struct.iter_unpack("4B", gdip.swap_rb(shots[0]))))
                else:
                    res = compose([part], part, 0, 0, 0)
                    img = crop(*res[:3]) if res else None
            except Exception:  # noqa: BLE001 - sprite estranho (GRF modificada): fica sem desenho, sem travar
                img = None
        self.cache[mob] = img
        return img

    def trap(self):
        """A ilustração do item Armadilha (armadilha de urso), sem o fundo branco: (w, h, pixels) ou None."""
        if "trap" not in self.cache:
            img = None
            data = self.grf.read(ITEM_ART + TRAP_ART)
            if data:
                try:
                    img = crop(*clear_background(*bmp_rgba(data)))
                except Exception:  # noqa: BLE001 - imagem estranha: fica sem desenho
                    img = None
            self.cache["trap"] = img
        return self.cache["trap"]


class MonsterLoader:
    """Abre o bestiário numa thread e faz cada desenho pedido numa thread também (o widget não trava).
    Pedidos: ("mob", id do monstro), ("trap",), ("item", id, arquivo da ilustração) ou ("char", visual, itens
    vestidos) para o personagem caído (este usa o guarda-roupa da aba Equipamento, LOADER)."""

    def __init__(self):
        self.path = None
        self.book = None
        self.error = None
        self._thread = None
        self._busy = set()
        self.cache = {}

    def start(self, grf_path):
        if not grf_path or (self.path == grf_path and (self.book or self._thread)):
            return
        self.path, self.book, self.error = grf_path, None, None

        def run():
            try:
                self.book = Bestiary(grf_path)
            except Exception as e:  # noqa: BLE001 - GRF que não dá para ler: o resumo aparece sem o desenho
                self.error = str(e) or e.__class__.__name__
            finally:
                self._thread = None
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def expected(self, spec):
        """Vale reservar espaço: o desenho existe ou ainda está carregando (e não falhou antes)."""
        if not spec or self.cache.get(repr(spec), True) is None:
            return False
        if spec[0] == "char":
            return LOADER.error is None and (LOADER.wardrobe is not None or LOADER.loading)
        if self.book is None:
            return self._thread is not None
        if spec[0] == "item":
            return self.book.has_item(spec[2])
        if spec[0] == "icon":
            return self.book.has_icon(spec[2])
        return self.book.has_trap() if spec[0] == "trap" else self.book.has(spec[1])

    def image(self, spec):
        """A imagem pronta, ou None; se ainda não foi feita, começa numa thread e o próximo desenho pega."""
        if not spec:
            return None
        key = repr(spec)
        if key in self.cache:
            return self.cache[key]
        if spec[0] == "char":
            w = LOADER.wardrobe
            if w is None:
                return None
            base, worn = spec[1], spec[2]

            def make():
                look = look_at(dict(base), dict(worn), w.classnum) if worn else dict(base)
                return dead_pose(w, look)
        else:
            b = self.book
            if b is None:
                return None
            if spec[0] == "trap":
                make = b.trap
            elif spec[0] == "item":
                def make():
                    return b.item(spec[2])
            elif spec[0] == "icon":
                def make():
                    return b.icon(spec[2])
            else:
                def make():
                    return b.idle(spec[1])
        if key not in self._busy:
            self._busy.add(key)

            def run():
                try:
                    self.cache[key] = make()
                except Exception:  # noqa: BLE001 - desenho que falhou: o cartão usa a caveira
                    self.cache[key] = None
                finally:
                    self._busy.discard(key)
            threading.Thread(target=run, daemon=True).start()
        return None


MONSTERS = MonsterLoader()
