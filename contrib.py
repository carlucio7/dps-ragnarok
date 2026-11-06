"""Quanto dano cada buff e debuff rendeu numa luta contra chefe.

Estimativa pelo efeito conhecido de cada um (fórmulas do rAthena e textos do próprio cliente), aplicada golpe a
golpe só onde o efeito vale (elemento, físico ou mágico, corpo a corpo): é quanto o dano daquele golpe cairia sem
ele. Os efeitos de elemento do alvo (Vício Mágico, Pólen, Cinzas) somam na mesma parcela (100% + bônus) e dividem
o ganho entre si; os outros multiplicam o dano à parte.
"""

import collections

import analysis as an
import dedoduro as dd
import meter
from i18n import _

LEX = 22


def _ele(bonus):
    return ("ele", bonus)


def _mul(bonus):
    return ("mul", bonus)


# efst -> (onde, regra mostrada, função(golpe, val1, chefe?) -> ("ele"|"mul", bônus em %) ou None)
EFFECTS = {
    1142: ("boss", _("+50% em todo o dano (todas as propriedades)"), lambda h, v, b: _ele(50)),
    dd.FLORESCER: ("boss", _("+100% no dano de fogo (resistência a fogo −100%)"),
                   lambda h, v, b: _ele(100) if h["el"] == "Fire" else None),
    1182: ("boss", _("+100% no dano de terra"), lambda h, v, b: _ele(100) if h["el"] == "Earth" else None),
    dd.VOLCANIC_ASH: ("boss", _("+50% no dano de fogo (iRO Wiki); chefes costumam ser imunes"),
                      lambda h, v, b: _ele(50) if h["el"] == "Fire" else None),
    dd.DARK_CLAW: ("boss", _("+30% por nível no dano físico corpo a corpo (metade em chefe)"),
                   lambda h, v, b: _mul((v or 150) / (2.0 if b else 1.0)) if h["phys"] and h["short"] else None),
    1402: ("boss", _("+50% no dano físico"), lambda h, v, b: _mul(50) if h["phys"] else None),
    1319: ("boss", _("+5% no dano físico de longe em chefe (+10% nos outros)"),
           lambda h, v, b: _mul(5 if b else 10) if h["phys"] and not h["short"] else None),
    1403: ("me", _("+5% por nível no dano físico"), lambda h, v, b: _mul(5 * (v or 10)) if h["phys"] else None),
}
NAME = {1142: None}          # nomes vêm de meter.status_name (com o nome do simulador, ex.: Cometa)


def classify(x, h):
    """Tipo do golpe: físico/mágico, corpo a corpo e elemento (como o Dedo Duro vê)."""
    sk = (dd.SKILL_DB.get(str(h.skill)) or {}) if h.skill else {}
    kind = sk.get("t", "W") if h.skill else "W"
    rng = sk.get("r", 1) if h.skill else 1
    el = dd.hit_element(h.skill)
    if el == "Weapon":
        el = dd.weapon_element(x, h.src, h.t) if h.raw == h.src else None
    return dict(phys=kind == "W", magic=kind == "M", short=kind == "W" and 0 <= (rng or 0) < 5, el=el)


def _spans(c, aid, efst):
    return sorted((s, e, c.status_val.get((a, ef, s))) for a, ef, s, e in c.statuses(aid) if ef == efst)


def fight(c, key, rng=None, player=None):
    """Contribuição de cada efeito numa luta contra `key` (todos os jogadores ou só `player`).
    Devolve (linhas, dano total considerado)."""
    if not any(h.out and h.dst == key and an._in(rng, h.t) for h in c.hits):
        return [], 0
    x = dd.Ctx(c, key, rng)
    e = c.entities.get(key)
    boss = bool(e and (e.boss or c.is_mvp(key)))
    hits = [h for h in x.hits if player is None or h.src == player]
    total = sum(h.dmg for h in hits)
    contrib, affected, n = collections.Counter(), collections.Counter(), collections.Counter()
    spans = {}

    def active(aid, efst, t):
        k = (aid, efst)
        if k not in spans:
            spans[k] = _spans(c, aid, efst)
        return next((v for s, e_, v in spans[k] if s <= t < e_), False)
    lex_used = set()
    for h in hits:
        if h.dmg <= 0:
            continue
        info = classify(x, h)
        ele, mul = {}, {}
        for efst, (where, _rule, fn) in EFFECTS.items():
            v = active(h.dst_raw if where == "boss" else h.src, efst, h.t)
            if v is False:
                continue
            r = fn(info, v, boss)
            if r is None:
                continue
            (ele if r[0] == "ele" else mul)[efst] = r[1]
        base = 100.0 + sum(ele.values())
        for efst, b in ele.items():
            contrib[efst] += h.dmg * b / base
            affected[efst] += h.dmg
            n[efst] += 1
        for efst, b in mul.items():
            contrib[efst] += h.dmg * b / (100.0 + b)
            affected[efst] += h.dmg
            n[efst] += 1
        # Lex Aeterna: dobra o primeiro golpe depois de aplicada
        for s, e_, _v in spans.setdefault((h.dst_raw, LEX), _spans(c, h.dst_raw, LEX)):
            if s <= h.t < e_ and (h.dst_raw, s) not in lex_used:
                lex_used.add((h.dst_raw, s))
                contrib[LEX] += h.dmg / 2.0
                affected[LEX] += h.dmg
                n[LEX] += 1
                break
    rows = []
    wins = [w for p in x.phases for w in p["win"]]
    win_ms = dd._total(wins) or 1
    for efst in set(EFFECTS) | {LEX}:
        where = EFFECTS[efst][0] if efst in EFFECTS else "boss"
        if where == "boss":
            on = [(s, e_) for p in x.phases for s, e_, _v in _spans(c, p["aid"], efst)]
        else:
            on = [(s, e_) for a in ([player] if player else x.party) for s, e_, _v in _spans(c, a, efst)]
        up = dd._total(dd._intersect(dd._merge(on), wins)) / float(win_ms) if on else 0.0
        rule = EFFECTS[efst][1] if efst in EFFECTS else _("dobra o 1º golpe depois de aplicada")
        if not on and not contrib[efst]:
            used = efst == dd.VOLCANIC_ASH and any(u[4] == dd.ASH_SKILL and x.start - 5000 <= u[0] <= x.end
                                                   for u in c.casts)
            if not used:
                continue
            rule = _("usada, mas o status nunca apareceu no chefe: imune")
        rows.append(dict(key=efst, efst=efst, name=meter.status_name(efst), where=where, rule=rule,
                         uptime=up, affected=affected[efst], contrib=contrib[efst], hits=n[efst],
                         share=contrib[efst] / float(total) if total else 0.0))
    rows.sort(key=lambda r: -r["contrib"])
    return rows, total
