# -*- coding: utf-8 -*-
"""Aviso de item ("item ping"): a pessoa marca itens e, quando um deles cai, o widget toca um som curto e mostra
onde ele caiu, para copiar o /navi (quem tela sem querer ou é puxado para longe sabe para onde voltar).

Aqui ficam as partes sem tela: a lista de itens do jogo para a busca, o som e o acompanhamento dos itens marcados
que caíram (pego, levado por outro jogador, ficou para trás, sumiu do chão). Só os itens marcados são
acompanhados: os outros drops não são olhados de novo, então marcar itens não pesa numa sessão longa."""

import math
import struct
import unicodedata

TONES = (("grave", 660.0), ("medio", 990.0), ("agudo", 1480.0), ("bem agudo", 2090.0))   # tom -> Hz
TONE_HZ = dict(TONES)
DEFAULT_TONE = "medio"
VOLUMES = (10, 25, 40, 60, 80, 100)
ITEM_LIFE_MS = 60000      # um item fica no chão por 1 minuto
LEFT_GRACE_MS = 1500      # saiu da vista e não entrou na bolsa até isto depois: ficou para trás
SIGHT_CELLS = 16          # mais longe que isto do item, ele já saiu da tela
FRESH_MS = 5000           # ao pegar uma gravação em curso, só avisa do que caiu nos últimos segundos
MAX_WATCH = 30            # itens marcados acompanhados ao mesmo tempo (os mais novos)


def norm(text):
    """Minúsculas e sem acentos, para a busca."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).split())


# ------------------------------------------------------------------ lista de itens do jogo

_CAT = {"sig": None, "rows": []}


def loading():
    """A lista de itens do jogo ainda está sendo lida?"""
    import xp
    return xp.GEAR.loading


def catalog():
    """[(id, nome, nome para a busca)] de todos os itens, em ordem alfabética: os do jogo instalado (o
    System\\iteminfo_new.lub, lido numa thread pelo xp.GEAR) mais os da base do medidor, que valem sozinhos quando o
    jogo não foi achado."""
    import clientdata
    import i18n
    import meter
    import xp
    xp.GEAR.start(xp._iteminfo_path())
    game = xp.GEAR.display or {}
    sig = (len(game), i18n.LANG, clientdata.NAMES.version)
    if _CAT["sig"] != sig:
        ids = set(game)
        for k in meter.ITEMS:
            try:
                ids.add(int(k))
            except ValueError:
                pass
        rows = []
        for i in ids:
            name = meter.item_name(i)
            if name == "Item %d" % i:              # a base não tem: o nome que o jogo instalado mostra
                name = game.get(i)
            if name:
                rows.append((i, name, norm(name)))
        rows.sort(key=lambda r: (r[2], r[0]))
        _CAT["sig"], _CAT["rows"] = sig, rows
    return _CAT["rows"]


def search(query, limit=200, rows=None):
    """Itens cujo nome tem todas as palavras digitadas (sem ligar para acentos ou maiúsculas), ou o item com
    aquele número. Primeiro os que começam com o texto. [(id, nome)]"""
    rows = catalog() if rows is None else rows
    text = norm(query)
    if not text:
        return []
    words = text.split()
    head, rest = [], []
    number = int(text) if text.isdigit() else None
    for i, name, key in rows:
        if number is not None and i == number:
            head.insert(0, (i, name))
        elif all(w in key for w in words):
            (head if key.startswith(text) else rest).append((i, name))
    return (head + rest)[:limit]


# ------------------------------------------------------------------ som

_WAV = {}


def wav(volume=40, tone=DEFAULT_TONE):
    """Um toque curto de sino (~0,3 s) no tom escolhido. WAV 16 bits mono gerado na hora."""
    volume = max(0, min(100, int(volume)))
    freq = TONE_HZ.get(tone, TONE_HZ[DEFAULT_TONE])
    key = (volume, freq)
    if key in _WAV:
        return _WAV[key]
    rate = 22050
    n = int(rate * 0.34)
    buf = []
    for i in range(n):
        x = i / float(rate)
        attack = min(1.0, x * 300.0)                 # sem estalo no começo
        w = 2 * math.pi * freq * x
        buf.append(attack * (math.exp(-x * 9.0) * math.sin(w) + 0.35 * math.exp(-x * 13.0) * math.sin(2 * w)
                             + 0.12 * math.exp(-x * 18.0) * math.sin(3 * w)))
    tail = int(rate * 0.02)
    for i in range(tail):                            # nem no fim
        buf[n - 1 - i] *= i / float(tail)
    peak = max(abs(v) for v in buf) or 1.0
    data = b"".join(struct.pack("<h", int(32767 * 0.5 * volume / 100.0 * v / peak)) for v in buf)
    head = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(data)))
    _WAV[key] = head + data
    return _WAV[key]


# ------------------------------------------------------------------ itens marcados que caíram

def navi(info):
    """O comando do jogo que aponta o lugar: /navi mapa x/y (None se o lugar não é conhecido)."""
    if not info or info.get("x") is None or not info.get("map"):
        return None
    return "/navi %s %d/%d" % (info["map"], info["x"], info["y"])


class Tracker:
    """Acha, a cada leitura do replay, os itens marcados que acabaram de cair e segue cada um até ser pego, levado
    por outro jogador ou sumir do chão. Devolve eventos (tipo, dados):
      "drop"    caiu um item marcado: dados = dict(item, count, map, x, y, t, mob, left, drop)
      "mvp"     um item marcado veio como prêmio de MVP (vai direto para a bolsa: sem lugar)
      "left"    um que caiu saiu da vista de quem grava sem ser pego (telou, foi puxado, andou para longe)
      "got"     quem grava pegou · "taken" outro jogador pegou · "expired" passou o tempo do item no chão"""

    def __init__(self):
        self.c = None
        self.n_drops = self.n_mvp = self.n_pick = 0
        self.watch = []

    def sync(self, c):
        """Passa a contar a partir de agora (gravação aberta já encerrada, ou nenhum item marcado)."""
        self.c = c
        self.n_drops, self.n_mvp, self.n_pick = len(c.drops), len(c.mvp_items), len(c.pickups)
        self.watch = []

    def poll(self, c, wanted, live=True):
        if not live or (not wanted and not self.watch):
            self.sync(c)
            return []
        if (c is not self.c or len(c.drops) < self.n_drops or len(c.mvp_items) < self.n_mvp
                or len(c.pickups) < self.n_pick):
            # gravação nova (ou zerada): o que caiu antes de o programa abrir o arquivo não avisa
            self.c, self.watch = c, []
            floor = c.now - FRESH_MS
            self.n_drops = next((i for i, d in enumerate(c.drops) if d["t"] >= floor), len(c.drops))
            self.n_mvp = next((i for i, m in enumerate(c.mvp_items) if m[0] >= floor), len(c.mvp_items))
            self.n_pick = len(c.pickups)
        out = []
        for d in c.drops[self.n_drops:]:
            if d["fell"] and d["item"] in wanted:
                info = dict(item=d["item"], count=d["count"], map=c.map, x=d["x"], y=d["y"], t=d["t"], mob=d["mob"],
                            left=False, drop=d)
                self.watch.append(info)
                out.append(("drop", info))
        self.n_drops = len(c.drops)
        for t, item in c.mvp_items[self.n_mvp:]:
            if item in wanted:
                out.append(("mvp", dict(item=item, count=1, map=c.map, x=None, y=None, t=t, mob=None, left=False,
                                        drop=None)))
        self.n_mvp = len(c.mvp_items)
        picked = [p["item"] for p in c.pickups[self.n_pick:]]
        self.n_pick = len(c.pickups)
        del self.watch[:-MAX_WATCH]
        keep = []
        me = c.pos_at(c.me, c.now) if self.watch else None
        for w in self.watch:
            d = w["drop"]
            if d["mine"] or w["item"] in picked:
                out.append(("got", w))
                if w["item"] in picked:
                    picked.remove(w["item"])
            elif d["by"] not in (None, c.me):
                out.append(("taken", w))
            elif c.now - w["t"] > ITEM_LIFE_MS:
                out.append(("expired", w))
            else:
                keep.append(w)
                if not w["left"]:
                    gone = d["gone"] is not None and c.now - d["gone"] >= LEFT_GRACE_MS
                    moved = (c.map or "").lower() != (w["map"] or "").lower()
                    far = me is not None and max(abs(me[0] - w["x"]), abs(me[1] - w["y"])) > SIGHT_CELLS
                    if gone or moved or far:
                        w["left"] = True
                        out.append(("left", w))
        self.watch = keep
        return out
