# -*- coding: utf-8 -*-
"""Categoria de um item, para colorir os drops: equipamento, carta, carta de MVP, refino, alquimia/culinária e
itens dos episódios 17 em diante.

Equipamento e carta vêm da descrição do próprio jogo ("Tipo: Carta", "Tipo: Armadura"...), lida junto com os
bônus de XP dos itens (xp.GEAR), então os itens novos da LATAM entram também. Carta de MVP, materiais de refino,
grau e reforma, ingredientes de alquimia e culinária e itens dos episódios vêm de data/item_kind.json
(tools/build_item_kinds.py).
"""

import json
import os
import re
import sys

KINDS = ("mvpcard", "episode", "card", "equip", "refine", "alch")
NAMES = {"equip": "Equipamentos", "card": "Cartas", "mvpcard": "Cartas de MVP",
         "refine": "Refino, grau e reforma", "alch": "Alquimia e culinária",
         "episode": "Episódios 17 em diante"}
DEFAULT_COLORS = {"equip": "#7dd3fc", "card": "#f87171", "mvpcard": "#fbbf24", "refine": "#c084fc",
                  "alch": "#4ade80", "episode": "#fb923c"}
# "Tipo:" que não é equipamento de personagem
NOT_EQUIP = ("visual", "carta", "ovo", "munição", "isca", "acessório de mascote", "essência", "encantamento",
             "roupa", "item de treinamento", "item de domesticação", "neutro")
_TYPE = re.compile(r"(?i)^tipo\s*:\s*(.+)$")
_COLOR = re.compile(r"\^[0-9a-fA-F]{6}")

_DATA = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "data")
try:
    with open(os.path.join(_DATA, "item_kind.json"), encoding="utf-8") as _f:
        BUNDLED = {k: set(v) for k, v in json.load(_f).items()}
except (OSError, ValueError):
    BUNDLED = {}


def parse_kinds(items):
    """{item: "equip" | "card" | "refine"} pelas descrições do iteminfo (em português)."""
    out = {}
    for item, info in items.items():
        if not isinstance(item, int) or not isinstance(info, dict):
            continue
        desc = info.get("identifiedDescriptionName") or {}
        lines = [_COLOR.sub("", desc[k]).strip() for k in sorted(k for k in desc if isinstance(k, int))
                 if isinstance(desc[k], str)]
        kind = None
        for line in lines:
            m = _TYPE.match(line)
            if m:
                t = m.group(1).strip().lower()
                if t.startswith("carta"):
                    kind = "card"
                elif not t.startswith(NOT_EQUIP):
                    kind = "equip"
                break
        if kind is None and any(line.startswith("Refinarias:") for line in lines):
            kind = "refine"
        if kind:
            out[item] = kind
    return out


def kind(item, name=None):
    """Categoria do item ou None. name: nome em português, para quando o jogo não está instalado."""
    for key in ("mvpcard", "episode"):
        if item in BUNDLED.get(key, ()):
            return key
    try:
        import xp
        from_game = xp.GEAR.kinds.get(item)
    except ImportError:
        from_game = None
    if from_game in ("card", "equip"):
        return from_game
    for key in ("refine", "alch"):
        if item in BUNDLED.get(key, ()):
            return key
    if from_game:
        return from_game
    if name and name.startswith("Carta "):
        return "card"
    return None


def favorites_first(rows, favs, rest=None):
    """Linhas de drops com os favoritos no topo, na ordem em que foram marcados (o primeiro marcado primeiro);
    o resto na ordem de `rest` (chave de ordenação) ou na ordem que veio."""
    order = {item: i for i, item in enumerate(favs or [])}
    tail = len(order)
    if rest is None:
        return sorted(rows, key=lambda r: order.get(r["item"], tail))
    return sorted(rows, key=lambda r: (order.get(r["item"], tail), rest(r)))


def colors(cfg):
    """{categoria: cor ou None (sem cor)} com as escolhas da pessoa por cima das cores padrão."""
    saved = cfg.get("drop_colors") or {}
    out = {}
    for k in KINDS:
        v = saved.get(k, DEFAULT_COLORS[k])
        if v == "":                       # a pessoa escolheu "sem cor"
            out[k] = None
        else:
            out[k] = v if isinstance(v, str) and re.match(r"^#[0-9a-fA-F]{6}$", v) else DEFAULT_COLORS[k]
    return out


def color_of(item, cfg, name=None):
    k = kind(item, name)
    return colors(cfg).get(k) if k else None


def start():
    """Começa a ler as descrições do jogo (numa thread; xp.GEAR guarda as categorias)."""
    try:
        import xp
        xp.GEAR.start(xp._iteminfo_path())
    except ImportError:
        pass


def loading():
    try:
        import xp
        return xp.GEAR.loading
    except ImportError:
        return False
