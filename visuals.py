# -*- coding: utf-8 -*-
"""Simulador de visuais: o catálogo de chapéus e capas do jogo instalado e as contas do "look".

Tudo vem do próprio jogo de quem usa: a lista de itens (System\\iteminfo_new.lub) diz o nome, o desenho (ClassNum)
e onde cada item equipa; as tabelas do data.grf dizem qual sprite é cada desenho. Visual novo que a Gravity põe no
jogo aparece aqui sozinho, sem atualizar o programa.
"""

import re
import unicodedata

# as quatro posições de visual, na ordem da tela: (chave do look, nome)
SLOTS = (("top", "Topo"), ("mid", "Meio"), ("low", "Baixo"), ("robe", "Capa"))
LETTER = {"top": "t", "mid": "m", "low": "l", "robe": "r"}
LOOK_KEYS = ("job", "sex", "hair", "hair_color", "cloth_color", "top", "mid", "low", "robe", "weapon", "shield",
             "option")
DEFAULT_LOOK = dict(job=0, sex=1, hair=1, hair_color=0, cloth_color=0, top=0, mid=0, low=0, robe=0, weapon=0,
                    shield=0, option=0, effects=[])
MAX_RESULTS = 300             # a lista de cada posição mostra no máximo isto (o resto aparece ao digitar)
MAX_EFFECTS = 3               # efeitos ligados ao mesmo tempo (no jogo é uma pedra por posição)
SHRINK = "miniatura"          # efeito sem arquivo: o personagem fica com metade do tamanho
PALE = "palidez"              # efeito sem arquivo: o personagem fica esbranquiçado
SHADOW = "sombra"             # efeito sem arquivo: uma cópia escura do personagem atrás dele, para cima e à direita
SPECIAL = (SHRINK, PALE, SHADOW)
# Pedras Gráficas: o jogo não diz qual efeito cada pedra liga (isso fica no servidor). Esta ligação veio do
# simulador do LATAM Tools (github.com/adsonpleal/latamvisuais, licença MIT): item da pedra -> efeito de chapéu
# (o nome do arquivo .str) ou SHRINK. As pedras que não estão aqui ainda não têm efeito conhecido.
# Fantasmas é o efeito do Banishing Buster e Dragão Alado o mesmo dragão do Kung Fu Panda em azul (dito por quem
# joga, 2026-11-15; os dois conferem com os GIFs do jogo).
STONES = {25058: "ljosalfar", 25059: "rl_banishing_buster", 25138: SHRINK, 25205: SHRINK, 25226: "waterfield2",
          25224: PALE, 25177: SHADOW, 25225: "red_wave", 25136: "blue_wave",
          1000319: "blessing_of_angels", 1000345: "time_accessory", 1000365: "magical_feather",
          1000875: "valhalla_idol", 1001069: "flowersmoke", 1001175: "c_romance_rose_tw", 1001252: "resonatetaego",
          1002193: "ros_bluespirit", 1002194: "ros_redspirit", 1002585: "digital_space"}
_POS = re.compile(r"(?i)^\s*(?:Equipa em|Equipado em|Posição)\s*:\s*(.+)$")
_COLOR = re.compile(r"\^[0-9a-fA-F]{6}")
_WORDS = (("t", ("topo", "superior")), ("m", ("meio",)), ("l", ("baixo",)), ("r", ("capa",)))


# Visuais só de efeito cujo nome interno não diz o efeito (vem em coreano): nome interno do item -> efeito.
# "[Visual] Fúria dos Shuras" usa o mesmo efeito da pedra Raios Vermelhos (dito por quem joga, 2026-11-15).
RESOURCE_FX = {"C홍염의폭렬파동": "red_wave"}


def fx_key(text):
    """Nome interno de um item ou de um efeito reduzido ao que os dois têm em comum ("C_Snow_Powder" e
    "HAT_EF_SNOW_POWDER" -> "snowpowder")."""
    text = re.sub(r"[^a-z0-9]", "", (text or "").lower())
    for cut in ("hatef", "effect"):
        text = text.replace(cut, "")
    return text[1:] if text.startswith("c") and len(text) > 5 else text


def slots_of(tbl):
    """{item: letras das posições} dos itens do jogo que têm desenho (ClassNum) e equipam na cabeça ou nas costas:
    t topo, m meio, l baixo, r capa ("Equipa em: Topo e Meio" -> "tm"). `tbl`: a tabela do iteminfo."""
    out = {}
    for item, info in tbl.items():
        if not isinstance(item, int) or not isinstance(info, dict):
            continue
        view = info.get("ClassNum")
        if not isinstance(view, int) or view <= 0:
            continue
        desc = info.get("identifiedDescriptionName") or {}
        where = None
        for k in sorted(k for k in desc if isinstance(k, int)):
            if isinstance(desc[k], str):
                m = _POS.match(_COLOR.sub("", desc[k]).strip())
                if m:
                    where = m.group(1).lower()
                    break
        if not where:
            continue
        letters = "".join(letter for letter, words in _WORDS if any(w in where for w in words))
        if letters:
            out[item] = letters
    return out


def fold(text):
    """Texto para comparar na busca: minúsculas e sem acento ("Chapéu" acha "chapeu")."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()


class Catalog:
    """Os itens de cada posição: {chave: [(nome para busca, nome, item, desenho)]} em ordem de nome."""

    def __init__(self, slots, classnum, acc, robe, name_of):
        self.letters = dict(slots)    # item -> letras das posições que ele ocupa ("tm" = topo e meio)
        self.rows = {key: [] for key, _n in SLOTS}
        for item, letters in slots.items():
            view = classnum.get(item)
            if not view:
                continue
            name = name_of(item)
            for key, _n in SLOTS:
                if LETTER[key] in letters and view in (robe if key == "robe" else acc):
                    self.rows[key].append((fold(name), name, item, view))
        for rows in self.rows.values():
            rows.sort()

    def search(self, key, text="", limit=MAX_RESULTS):
        """Itens da posição cujo nome tem todas as palavras de `text` (sem ligar para acento e maiúsculas)."""
        words = fold(text).split()
        rows = self.rows.get(key, ())
        if words:
            rows = [r for r in rows if all(w in r[0] for w in words)]
        return [(name, item, view) for _f, name, item, view in rows[:limit]]

    def count(self, key, text=""):
        words = fold(text).split()
        rows = self.rows.get(key, ())
        return sum(1 for r in rows if all(w in r[0] for w in words)) if words else len(rows)

    def name_of_view(self, key, view, item=None):
        """Nome para mostrar do que está na posição: o do item escolhido ou o primeiro item com esse desenho."""
        if not view:
            return None
        rows = self.rows.get(key, ())
        hit = next((r for r in rows if r[2] == item and r[3] == view), None) if item else None
        hit = hit or next((r for r in rows if r[3] == view), None)
        return hit[1] if hit else None


def wear(look, items, held, key, row, letters=""):
    """Veste (ou tira, com row None) um item na posição `key`. row = (nome, item, desenho); `letters` = as posições
    que o item ocupa. Um visual de duas ou três posições (Topo e Meio...) ocupa todas: o desenho fica na primeira e
    as outras ficam presas a ele (held[posição] = (item, desenho, nome)); pôr outra coisa numa delas, ou tirar,
    solta o visual inteiro. Mexe em look, items e held; devolve as posições que mudaram."""
    changed = set()

    def release(k):
        hit = held.get(k)
        for k2 in ([s for s, h in held.items() if h[0] == hit[0]] if hit else [k]):
            look[k2] = 0
            items[k2] = None
            held.pop(k2, None)
            changed.add(k2)

    release(key)
    if row:
        name, item, view = row
        keys = [k for k, _n in SLOTS if k != "robe" and LETTER[k] in (letters or "")]
        if key == "robe" or key not in keys:
            keys = [key]
        for k in keys:
            release(k)
        look[keys[0]] = view
        items[keys[0]] = item
        if len(keys) > 1:
            for k in keys:
                held[k] = (item, view, name)
    return changed


TINY_ICON = 8                 # ícone cuja parte desenhada tem até isto num dos lados mal dá para reconhecer


def tiny_icon(w, h, px):
    """O ícone é minúsculo (ou vazio)? px = [(r, g, b, a)] de um ícone w x h."""
    xs = [i % w for i, p in enumerate(px) if p[3]]
    if not xs:
        return True
    ys = [i // w for i, p in enumerate(px) if p[3]]
    return max(xs) - min(xs) + 1 <= TINY_ICON or max(ys) - min(ys) + 1 <= TINY_ICON


def clean(look):
    """Um look só com as chaves conhecidas e números inteiros (o que vem da configuração pode ter qualquer coisa)."""
    out = dict(DEFAULT_LOOK)
    for k in LOOK_KEYS:
        v = (look or {}).get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        out[k] = int(v)
    out["hair"] = max(1, out["hair"])
    effects = (look or {}).get("effects")
    out["effects"] = [str(e) for e in effects if isinstance(e, str)][:MAX_EFFECTS] if isinstance(effects, list) else []
    return out


def saved_looks(cfg):
    """{nome: look} dos looks guardados (cfg "looks"), já limpos."""
    return {str(name): clean(look) for name, look in ((cfg or {}).get("looks") or {}).items()
            if isinstance(look, dict)}
