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
LEX_SKILLS = (78, 5072)       # Lex Aeterna e Vituperatum aplicam o status 22
WEB, WEB_SKILL = 129, 405     # Prisão de Teia: status no alvo e a skill


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

# Áreas no chão do Mestre Elemental. O replay não traz status de quem está em cima: vale a posição de cada um no
# instante do golpe. Chave = −skill (não colide com os ids de status). "src": vale para quem bate de dentro da área;
# "dst": para o alvo que está em cima dela. Valores do rAthena (battle_attr_fix), na mesma parcela do elemento em
# que entram Pólen e Cometa: Vulcão/Dilúvio/Furacão somam para o atacante; cada Insígnia abre o alvo para o
# elemento que vence o dela (Terra → fogo, Fogo → água, Água → vento, Vento → terra).
FIELD_PCT = (10, 14, 17, 19, 20)
INSIGNIA_PCT = 50
AREAS = {-285: ("src", "Fire"), -286: ("src", "Water"), -287: ("src", "Wind"),
         -2468: ("dst", "Fire"), -2465: ("dst", "Water"), -2466: ("dst", "Wind"), -2467: ("dst", "Earth")}
AREA_KIND = _("Área no chão")


def effect_name(key):
    """Nome de um efeito: status (id positivo) ou área no chão (−skill)."""
    return meter.skill_name(-key) if key < 0 else meter.status_name(key)


def area_pct(key, level):
    if AREAS[key][0] == "dst":
        return INSIGNIA_PCT
    return FIELD_PCT[max(1, min(level or 5, 5)) - 1]


def area_rule(key, level):
    side, el = AREAS[key]
    name = dd.ELEMENT_PT.get(el, el).lower()
    if side == "src":
        return _("+%d%% no dano de %s de quem bate de dentro da área (rAthena)") % (area_pct(key, level), name)
    return _("+%d%% no dano de %s no alvo que está em cima dela (rAthena)") % (area_pct(key, level), name)


def live_areas(c, x):
    """{chave: áreas que estiveram no chão durante a luta}."""
    out = {}
    for key in AREAS:
        areas = c.areas_of(-key, x.start, x.end)
        if areas:
            out[key] = areas
    return out


def area_bonus(c, live, info, h):
    """[(chave, quem pôs a área, bônus em %)] das áreas que valem neste golpe."""
    out = []
    for key, areas in live.items():
        side, el = AREAS[key]
        if info["el"] != el:
            continue
        if side == "src":
            e = c.entities.get(h.raw)
            if h.raw != h.src and e is not None and e.kind != "pc":
                continue                         # golpe de invocação: a posição dela não se vê
            pos = c.pos_at(h.src, h.t)
        else:
            pos = c.pos_at(h.dst_raw, h.t)
        a = next((a for a in areas if c.in_area(a, pos, h.t)), None)
        if a is not None:
            out.append((key, c.resolve(a["src"]), area_pct(key, a["level"])))
    return out


def area_uptime(c, x, key, areas, player=None):
    """[(início, fim)] em que a área valia: o chefe em cima dela (Insígnias) ou, nas de atacante, o jogador
    escolhido dentro dela (sem jogador escolhido: a área no chão)."""
    if AREAS[key][0] == "dst":
        return [sp for p in x.phases for sp in c.inside_spans(areas, p["aid"], p["start"], p["end"])]
    if player:
        return c.inside_spans(areas, player, x.start, x.end)
    return [sp for a in areas for sp in c.area_spans(a)]


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


def lex_consumed(c, x):
    """Golpes (id) que gastaram uma Lex Aeterna: cada aplicação no chefe dobra o próximo golpe com dano nele.

    A aplicação é o uso da skill no chefe (Lex Aeterna, Vituperatum) ou o status ligando sem uso visto. Não dá para
    usar só o status: com o Cardeal lançando várias por segundo, o jogo liga o status uma vez e só desliga no fim da
    sequência, embora cada Lex seja gasta pelo golpe seguinte (no replay de 4 min, 2 trechos de status e 21 Lex
    gastas, cada uma até ~200 ms depois do uso). Lex de novo num alvo que ainda tem uma não acumula."""
    aids = set(x.boss_aids)
    events = [(u[0], 0, u[3]) for u in c.uses if u[4] in LEX_SKILLS and u[3] in aids]
    seen = {(t, a) for t, _k, a in events}
    for a, ef, s, e in c.statuses():
        if ef == LEX and a in aids:
            if not any(abs(s - t) <= 300 and a == b for t, b in seen):
                events.append((s, 0, a))
            events.append((e, 2, a))                 # o status desligou: a Lex foi gasta (talvez fora da tela)
    events += [(h.t, 1, h) for h in x.hits if h.dmg > 0]
    events.sort(key=lambda e: (e[0], e[1]))          # no mesmo ms: uso, golpe e só depois o status desligando
    # as fases do chefe nunca estão vivas juntas: uma Lex pendente vale para a luta
    pending, out = False, set()
    for _t, kind, obj in events:
        if kind == 0:
            pending = True
        elif kind == 2:
            pending = False
        elif pending:
            pending = False
            out.add(id(obj))
    return out


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
    lex_hits = lex_consumed(c, x)
    live = live_areas(c, x)
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
        for akey, _who, b in area_bonus(c, live, info, h):
            ele[akey] = b
        base = 100.0 + sum(ele.values())
        for efst, b in ele.items():
            contrib[efst] += h.dmg * b / base
            affected[efst] += h.dmg
            n[efst] += 1
        for efst, b in mul.items():
            contrib[efst] += h.dmg * b / (100.0 + b)
            affected[efst] += h.dmg
            n[efst] += 1
        if id(h) in lex_hits:               # Lex Aeterna: este golpe veio dobrado
            contrib[LEX] += h.dmg / 2.0
            affected[LEX] += h.dmg
            n[LEX] += 1
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
        rule = EFFECTS[efst][1] if efst in EFFECTS else _("dobra o próximo golpe depois de cada uso: %d golpes dobrados") % n[efst]
        if not on and not contrib[efst]:
            used = efst == dd.VOLCANIC_ASH and any(u[4] == dd.ASH_SKILL and x.start - 5000 <= u[0] <= x.end
                                                   for u in c.casts)
            if not used:
                continue
            rule = _("usada, mas o status nunca apareceu no chefe: imune")
        if efst == LEX:
            up = None           # o status fica ligado na sequência inteira de Lex: "ativo" não diz nada aqui
        rows.append(dict(key=efst, efst=efst, name=meter.status_name(efst), where=where, rule=rule,
                         uptime=up, affected=affected[efst], contrib=contrib[efst], hits=n[efst],
                         share=contrib[efst] / float(total) if total else 0.0))
    for akey, areas in live.items():
        on = area_uptime(c, x, akey, areas, player)
        up = dd._total(dd._intersect(dd._merge(on), wins)) / float(win_ms) if on else 0.0
        rows.append(dict(key=akey, efst=akey, name=effect_name(akey), kind_txt=AREA_KIND,
                         where="boss" if AREAS[akey][0] == "dst" else "me",
                         rule=area_rule(akey, max(a["level"] for a in areas)), uptime=up, affected=affected[akey],
                         contrib=contrib[akey], hits=n[akey], share=contrib[akey] / float(total) if total else 0.0))
    # Prisão de Teia: só o reconhecimento. A skill não pode ser usada em várias instâncias; lá o efeito só aparece
    # pelo autocast do Arco de Trepadeira. A leitura fica para esse caso, sem medir quanto ela rende.
    web_on = [(s, e_) for p in x.phases for s, e_, _v in _spans(c, p["aid"], WEB)]
    web_used = sum(1 for u in c.uses if u[4] == WEB_SKILL and x.start - 5000 <= u[0] <= x.end)
    if web_on or web_used:
        rule = (_("o próximo golpe de fogo sai dobrado e a teia some (rAthena)") if web_on
                else _("usada %d vez(es), mas o status não apareceu no chefe") % web_used)
        up = dd._total(dd._intersect(dd._merge(web_on), wins)) / float(win_ms) if web_on else 0.0
        rows.append(dict(key=WEB, efst=WEB, name=meter.status_name(WEB), where="boss", rule=rule, uptime=up,
                         affected=0, contrib=0, hits=0, share=0.0))
    rows.sort(key=lambda r: -r["contrib"])
    return rows, total


# --- dano creditado a cada jogador ------------------------------------------------------------------------------

# skills que põem cada efeito no chefe (data/efst.json, do rAthena); o Avanço Sísmico deixa um status no chefe
# (1402) que o rAthena não liga à skill
APPLY_SKILLS = {1402: (5296,)}
APPLY_WINDOW = (4000, 300)    # quem usou a skill até 4 s antes (ou 0,3 s depois) de o status aparecer no chefe


def _apply_skills(efst):
    if efst in APPLY_SKILLS:
        return set(APPLY_SKILLS[efst])
    return set((meter.EFST.get(str(efst)) or {}).get("s") or ())


def appliers(c, x, efst):
    """[(início, fim, quem pôs ou None)] dos trechos de um efeito no chefe: quem usou a skill que põe o efeito
    logo antes de ele aparecer (uso, conjuração ou golpe da skill)."""
    sk = _apply_skills(efst)
    acts = sorted([(u[0], u[2]) for u in c.uses if u[4] in sk] + [(u[0], u[2]) for u in c.casts if u[4] in sk]
                  + [(h.t, h.src) for h in c.hits if h.out and h.skill in sk])
    before, after = APPLY_WINDOW
    out = []
    for p in x.phases:
        for s, e, v in _spans(c, p["aid"], efst):
            who = None
            for t, a in acts:
                if s - before <= t <= s + after:
                    who = a
            out.append((s, e, who, v))
    return out


def credit(c, key, rng=None):
    """Dano creditado a cada jogador numa luta contra `key`: a parte do dano que é dele (os golpes dele sem os
    efeitos dos outros) mais o que os efeitos que ele pôs renderam nos golpes de todo mundo.

    Num golpe com vários efeitos, o ganho (dano − dano sem nenhum) é dividido entre eles pelo peso de cada
    multiplicador (log): Lex ×2 e Pólen ×2 no mesmo golpe ficam com metade do ganho cada. Assim nada é contado
    duas vezes e tudo soma 100% do dano. Devolve (linhas, dano total); linha: aid (None = quem pôs não aparece no
    replay), own, via {efeito: dano}, total."""
    import math
    if not any(h.out and h.dst == key and an._in(rng, h.t) for h in c.hits):
        return [], 0
    x = dd.Ctx(c, key, rng)
    e = c.entities.get(key)
    boss = bool(e and (e.boss or c.is_mvp(key)))
    boss_fx = {efst: appliers(c, x, efst) for efst, (where, _r, _f) in EFFECTS.items() if where == "boss"}
    lex_hits = lex_consumed(c, x)
    lex_uses = sorted((u[0], u[2]) for u in c.uses if u[4] in LEX_SKILLS and u[3] in x.boss_aids)
    live = live_areas(c, x)
    me_spans = {}
    own, via = collections.Counter(), collections.defaultdict(collections.Counter)
    total = 0
    for h in x.hits:
        if h.dmg <= 0:
            continue
        total += h.dmg
        info = classify(x, h)
        ele, mul = [], []
        for efst, (where, _rule, fn) in EFFECTS.items():
            if where == "boss":
                on = [(who, v) for s, e_, who, v in boss_fx[efst] if s <= h.t < e_]
                if not on:
                    continue
                who, v = on[-1]
            else:
                k = (h.src, efst)
                if k not in me_spans:
                    me_spans[k] = _spans(c, h.src, efst)
                v = next((vv for s, e_, vv in me_spans[k] if s <= h.t < e_), False)
                if v is False:
                    continue
                who = h.src                     # buff no próprio jogador (ex.: Investida do Engenheiro)
            r = fn(info, v, boss)
            if r is not None:
                (ele if r[0] == "ele" else mul).append((efst, who, r[1]))
        ele += area_bonus(c, live, info, h)     # áreas no chão: o crédito vai para quem pôs a área
        factors = []                            # (efeito, quem, multiplicador)
        sum_ele = sum(b for _e, _w, b in ele)
        if sum_ele:
            whole = (100.0 + sum_ele) / 100.0   # os de elemento somam numa parcela só e dividem o log dela
            factors += [(ef, who, whole ** (b / sum_ele)) for ef, who, b in ele]
        factors += [(ef, who, (100.0 + b) / 100.0) for ef, who, b in mul]
        if id(h) in lex_hits:
            prev = [w for t, w in lex_uses if t <= h.t]
            factors.append((LEX, prev[-1] if prev else None, 2.0))
        f_all = 1.0
        for _e, _w, m in factors:
            f_all *= m
        base = h.dmg / f_all
        own[h.src] += base
        if f_all > 1:
            gain, ln_all = h.dmg - base, math.log(f_all)
            for ef, who, m in factors:
                via[who][ef] += gain * math.log(m) / ln_all
    rows = []
    for aid in set(own) | set(via):
        v = dict(via.get(aid) or {})
        rows.append(dict(aid=aid, own=own.get(aid, 0.0), via=v, total=own.get(aid, 0.0) + sum(v.values())))
    rows.sort(key=lambda r: -r["total"])
    return rows, total
