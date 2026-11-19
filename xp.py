# -*- coding: utf-8 -*-
"""Estimativa da XP de base dos abates de quem grava.

O replay não grava a XP ganha: só a XP total no início de cada gravação (sessão, chunk 1015). A estimativa é

    XP de um abate = XP do monstro × penalidade de nível ÷ 100 (arredondada para baixo) × parte do dano × fator

- XP do monstro: data/mob_exp.json (rAthena, mais os monstros novos com a XP do Divine Pride).
- Penalidade de nível: a mesma tabela do rAthena e do Divine Pride (nível do monstro − nível do jogador).
- Parte do dano: quanto do dano no monstro foi de quem grava (grupo dividindo XP não entra).
- Fator: [(1 + evento, VIP e Cetro) × (1 + itens e Njord) + manual e Kafra] × Milagre (dobra), medido com a
  XP exata que o servidor manda pela rede (ver BONUSES). Os bônus que aparecem como status (manual,
  Njord, Milagre, VIP...) são seguidos golpe a golpe; o que o replay não mostra (evento do servidor, algum item)
  vira uma correção sobre a lista, medida com XP exata: duas gravações seguidas do mesmo personagem (a XP no
  começo da seguinte) ou uma subida de nível no meio da gravação (o jogo manda o nível novo, e a XP de cada nível
  é conhecida). Gravações curtas não calibram, e cada medida pesa pela XP que ela cobre.
"""

import bisect
import datetime
import json
import os
import re
import statistics
import sys
import threading
import weakref

_DATA = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "data")

try:
    with open(os.path.join(_DATA, "mob_exp.json"), encoding="utf-8") as _f:
        MOB_EXP = {int(k): v for k, v in json.load(_f).items()}
except (OSError, ValueError):
    MOB_EXP = {}

# diferença (nível do monstro − nível do jogador) -> % da XP (a do rAthena e do iRO Wiki; o Petite 16+ níveis acima
# rende 434 = 1.086 × 40% nos bancos de dados). Um replay parecia mostrar 100% nos 16+ acima: eram Hodes contados
# como Petite pelo AID reaproveitado (_all_kills), e com o monstro certo a regra de 40% fecha
PENALTY_UP = ((16, 40), (15, 115), (14, 120), (13, 125), (12, 130), (11, 135), (10, 140), (9, 135), (8, 130),
              (7, 125), (6, 120), (5, 115), (4, 110), (3, 105))
PENALTY_DOWN = ((-31, 10), (-26, 35), (-21, 60), (-16, 85), (-11, 90), (-6, 95))
# a próxima gravação começou até 3 min depois do fim desta. Parar e começar outra no jogo leva de 1,5 a 3 min (nome do
# arquivo, o resumo na tela...): com 1 min, nenhum reinício de calibração do usuário em 2026-11-18 media. Nos
# intervalos medidos, os abates fora da gravação somaram no máximo ~25 s de farm (até ~4% num trecho de 10 min).
CALIBRATE_GAP_S = 180
KILL_MAP_SHARE = 0.95         # a medida é do mapa que deu 95% da XP dos abates (o caminho pela cidade não conta)
CALIBRATE_MIN_KILLS = 3
CALIBRATE_MIN_MS = 10 * 60000  # trecho curto não calibra (30 s de gravação davam um fator 20% errado)...
CALIBRATE_MIN_FRAC = 0.01     # ...a não ser que já tenha rendido 1% do nível (o que vier primeiro)
CALIBRATE_KEEP = 60           # medidas guardadas por personagem (cada mapa usa as dele; a média pesa pela XP coberta)
# memória longa: valem as medidas de até 30 dias antes da mais nova (de qualquer personagem). O jogo muda a cada
# ~15 dias e os eventos duram um fim de semana ou um mês: quando uma medida nova discorda das antigas do mesmo mapa,
# as antigas desse mapa saem (o evento mudou)
CALIBRATE_FRESH_S = 30 * 86400
CHANGE_FIT = (0.12, 0.20)     # discordância que conta como mudança no mapa: trecho longo (150+ abates) e curto
#                              (eventos mudam 20% ou mais; abates divididos no grupo já fazem 8% de diferença)
CHANGE_LONG_KILLS = 150
BASE_SPREAD = 0.08            # o normal do personagem: os mapas que rendem até 8% acima do que rende menos
SERVER_RECENT_S = 24 * 3600   # o evento do servidor mudou: saem as medidas do último dia (feitas com o % errado)
LEARN_KEEP, LEARN_UNKNOWN = 1000, 300  # registro do que o programa aprende (para o relatório; arquivo próprio)
LEARN_DROP_RECS = 1000                 # gravações com drops guardadas no registro
LEARN_QUESTS = 500                     # recompensas de missão aprendidas guardadas no registro (para o relatório)
# efeitos de drop que o replay mostra em quem grava: Chiclete (CASH_RECEIVEITEM, com o %), bônus de drop por período
# (do item ou da conta, como o VIP e o Manual Kafra), EXP e drop, exclusivo
DROP_EFST = (252, 922, 938, 983, 1084, 1086, 1119)
DROP_ALONE_MS = 350           # o item cai até 0,3 s depois da morte: abate sem outra morte tão perto diz de quem caiu
PACE_MS = 10 * 60000          # o tempo até o nível usa o ritmo dos últimos 10 min de farm
WARMUP_MS, WARMUP_FRAC = 10 * 60000, 0.01   # a previsão só aparece depois de 10 min de farm ou 1% do nível
FARM_FRAC = 0.4               # o farm começa no 1º minuto que rende 40% do melhor minuto (antes: preparação)

# XP de cada nível nas classes 4 do LATAM: a tabela do rAthena até o nível 219 e, do 220 em diante, a do nível
# anterior × 1,22, arredondada para baixo (o rAthena usa × 1,14 aí). Conferido nos replays: sai exatamente o que o
# jogo mandou nos níveis 200, 201, 224 e do 240 ao 248. 250 é o máximo.
FOURTH_JOBS = set(range(4252, 4265)) | set(range(4278, 4282)) | set(range(4302, 4309)) | {4316}
TABLE_4TH_FROM = 220
MAX_LEVEL_4TH = 250


_BASE_EXP = None


def _base_exp():
    """{classe: {nível: XP}} da tabela do rAthena (data/base_exp.json, tools/build_base_exp.py), lida uma vez."""
    global _BASE_EXP
    if _BASE_EXP is None:
        _BASE_EXP = {}
        try:
            with open(os.path.join(_DATA, "base_exp.json"), encoding="utf-8") as f:
                for g in json.load(f).get("groups", []):
                    # o último nível vem com 999999999 (não há nível seguinte): fica de fora
                    levels = {int(k): int(v) for k, v in g.get("exp", {}).items()
                              if int(v) != 999999999 and int(k) < int(g.get("max") or 9999)}
                    for job in g.get("jobs", []):
                        _BASE_EXP[int(job)] = levels
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    return _BASE_EXP


def table_need(job, level):
    """XP do nível `level` (para chegar ao seguinte) pela tabela conhecida, ou None. As classes seguem a tabela do
    rAthena, que confere com o que o jogo manda (classe 2 no 76, 3ª classe do 134 ao 190, 4ª classe no 200 e no
    201), menos onde o ROLatam ainda não reduziu a XP: as classes 1 e 2 do 79 ao 98 (já gravadas no
    data/base_exp.json, tools/build_base_exp.py) e a 4ª classe a partir do 220: cada nível pede 22% a mais que o
    anterior."""
    table = _base_exp().get(job, {})
    if job in FOURTH_JOBS:
        if level >= MAX_LEVEL_4TH:
            return None
        if level >= TABLE_4TH_FROM:
            need = table.get(TABLE_4TH_FROM - 1)
            for _i in range(level - TABLE_4TH_FROM + 1):
                need = need * 122 // 100 if need else None
            return need
    return table.get(level)


def penalty(diff):
    for d, rate in PENALTY_UP:
        if diff >= d:
            return rate
    for d, rate in PENALTY_DOWN:
        if diff <= d:
            return rate
    return 100


_CACHE = {}


def _names_version():
    try:
        import clientdata
        return clientdata.NAMES.version
    except Exception:  # noqa: BLE001
        return 0


def _kill_state(c):
    """Os abates da gravação, refeitos só quando chega algo novo. O dano em cada monstro é somado aos poucos (só
    os golpes que ainda não entraram): numa sessão longa, reler todos os golpes a cada desenho travava o widget."""
    st = _CACHE.get("k")
    hits, deaths = c.hits, c.death_log
    first = hits[0] if hits else None
    names = _names_version()
    if (st is None or st["c"]() is not c or st["n"] > len(hits) or st["nd"] > len(deaths)
            or (st["n"] and st["first"] is not first) or st["names"] != names):
        st = _CACHE["k"] = dict(c=weakref.ref(c), n=0, nd=0, first=first, mine={}, total={}, life={}, sig=None,
                                res=([], 0), times=[], ordered=True, names=names)
    _lives(c, st)
    sig = (c.version, len(deaths), len(hits))
    if st["sig"] != sig:
        st["sig"] = sig
        st["res"] = _all_kills(c, st["life"])
        times = st["times"] = [r["t"] for r in st["res"][0]]
        st["ordered"] = all(a <= b for a, b in zip(times, times[1:]))
    return st


def _lives(c, st):
    """Soma o dano por vida de cada monstro: o jogo reaproveita o AID (o monstro que renasce e, depois de trocar de
    mapa, um outro qualquer), então cada morte fecha a soma daquele AID e o próximo começa do zero. Golpes e mortes
    que ainda não entraram, em ordem de tempo (o golpe que matou vem antes da morte no mesmo instante):
    st["life"][índice da morte em c.death_log] = (dano de quem grava, dano de todos) na vida que acabou nela."""
    hits, deaths = c.hits, c.death_log
    i, j, nh, nd = st["n"], st["nd"], len(hits), len(deaths)
    if i >= nh and j >= nd:
        return
    mine, total, life, me = st["mine"], st["total"], st["life"], c.me
    while i < nh or j < nd:
        if j >= nd or (i < nh and hits[i].t <= deaths[j][0]):
            h = hits[i]
            i += 1
            if h.dmg > 0:
                d = h.dst
                total[d] = total.get(d, 0) + h.dmg
                if h.src == me:
                    mine[d] = mine.get(d, 0) + h.dmg
        else:
            aid = deaths[j][1]
            life[j] = (mine.pop(aid, 0), total.pop(aid, 0))
            j += 1
    st["n"], st["nd"], st["first"] = nh, nd, (hits[0] if hits else None)


def kills(c, rng=None):
    """Abates em que quem grava bateu: (linhas, abates sem XP conhecida).
    linha: t, aid, mob, name, lv, share (parte do dano), pen (%), xp (sem o fator)."""
    st = _kill_state(c)
    if rng is None:
        return st["res"]
    rows = st["res"][0]
    if st["ordered"]:
        rows = rows[bisect.bisect_left(st["times"], rng[0]):bisect.bisect_right(st["times"], rng[1])]
    else:
        rows = [r for r in rows if rng[0] <= r["t"] <= rng[1]]
    return rows, sum(1 for r in rows if r["xp"] is None)


def level_at(c, t):
    """Nível de base de quem grava no instante t (o do começo, mais as subidas no meio da gravação)."""
    lv = c.session.base_level or 1
    for when, new in getattr(c, "level_ups", ()):
        if when <= t:
            lv = new
    return lv


def _all_kills(c, life=None):
    """As linhas dos abates. `life`: {índice da morte: (dano de quem grava, dano de todos) na vida que acabou nela},
    se já somado (_kill_state). O monstro de cada abate é o que tinha o AID na hora da morte (c.death_who): com o
    AID reaproveitado depois de trocar de mapa, 28 Hodes de um replay viravam Petites (e a XP saía 40% da certa)."""
    if life is None:
        st = dict(n=0, nd=0, mine={}, total={}, life={})
        _lives(c, st)
        life = st["life"]
    who = getattr(c, "death_who", None) or {}
    off = getattr(c, "off_life", None) or {}
    rows, unknown = [], 0
    for j, (t, aid) in enumerate(c.death_log):
        e = c.entities.get(aid)
        kind, job = who.get((t, aid)) or ((e.kind, e.job) if e is not None else (None, None))
        if kind != "mob" or c.is_friendly(aid):
            continue
        own, everyone = life.get(j, (0, 0))
        extra = off.get((t, aid))
        if extra:                        # monstros fora do filtro "Contar dano em": o abate vale XP do mesmo jeito
            own, everyone = own + extra[0], everyone + extra[1]
        if not own:
            continue
        share = own / float(everyone)
        if e is not None and e.job == job:
            name = c.name_of(aid)
        else:                            # o AID agora é de outro monstro: o nome do que morreu
            from i18n import _
            name = meter_name(job) or _("Monstro %d") % job
        data = MOB_EXP.get(job)
        if not data:                     # sem dado; XP 0 = o monstro não dá XP (instância, desafio...)
            unknown += 1
            rows.append(dict(t=t, aid=aid, mob=job, name=name, lv=None, share=share, pen=None, xp=None))
            continue
        pen = penalty(data[0] - level_at(c, t))
        rows.append(dict(t=t, aid=aid, mob=job, name=name, lv=data[0], share=share, pen=pen,
                         xp=(data[1] * pen // 100) * share))
    return rows, unknown


def by_monster(rows):
    """Resumo por monstro: nome, nível, abates, % de penalidade, XP sem o fator (desconhecida = None)."""
    agg = {}
    for r in rows:
        a = agg.get(r["mob"])
        if a is None:
            a = agg[r["mob"]] = dict(key=r["mob"], name=r["name"], lv=r["lv"], kills=0, pen=r["pen"],
                                     xp=0.0 if r["xp"] is not None else None)
        a["kills"] += 1
        if a["xp"] is not None and r["xp"] is not None:
            a["xp"] += r["xp"]
    return sorted(agg.values(), key=lambda a: (-(a["xp"] or 0), -a["kills"]))


def _seconds(when):
    try:
        return datetime.datetime(*when).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def need(c, cfg, level):
    """XP do nível `level` para quem grava: a que o jogo mandou no começo da gravação, a que ele mandou em outra
    gravação dessa classe (cfg["xp_levels"]) ou a da tabela conhecida, nessa ordem: o que veio do jogo vale mais
    que a tabela (a do rAthena já errou no ROLatam). None se não se sabe."""
    ses = c.session
    if level == ses.base_level and ses.next_exp:
        return ses.next_exp
    seen = ((cfg or {}).get("xp_levels") or {}).get(str(ses.job), {}).get(str(level))
    if isinstance(seen, (int, float)) and 0 < seen < 999999999:
        return seen
    return table_need(ses.job, level)


def anchors(c):
    """Pontos em que a XP de quem grava é exata: [(t, nível, XP no nível)] — o começo da gravação e cada subida
    de nível (XP 0 no nível novo; a sobra do abate ou da entrega que subiu fica de fora: costuma ser pouca, e onde
    não é, level_segments e learn_quests deixam o trecho de fora)."""
    ses = c.session
    if ses.base_exp is None or not ses.base_level:
        return []
    return [(0, ses.base_level, ses.base_exp)] + [(t, lv, 0) for t, lv in getattr(c, "level_ups", ())]


def level_segments(c, cfg):
    """Trechos da gravação com a XP real exata: de um ponto exato até a subida de nível seguinte.
    [(início, fim, XP real)]. Fica de fora o nível em que um abate sozinho vale 10% ou mais do nível, e o seguinte:
    a sobra do abate que subiu passa para o nível novo sem aparecer (um Salgueiro dá mais que o nível 1 inteiro)."""
    out = []
    an = anchors(c)
    cut = getattr(c, "reset_t", None)   # o Zerar apagou os abates de antes: trecho que começou antes dele não mede
    lumpy = False                       # o nível anterior tinha abates grandes: o começo deste não é exato
    for (t0, lv, x0), (t1, lv1, _x) in zip(an, an[1:]):
        nd = need(c, cfg, lv)
        was, lumpy = lumpy, bool(nd) and _lumpy(c, cfg, t0, t1, nd)
        if lv1 == lv + 1 and nd and not lumpy and not was and (cut is None or t0 >= cut):
            # o que os abates renderam de fato: a XP do nível mais o que as mortes sem seguro tiraram no caminho
            out.append((t0, t1, nd - x0 + death_loss(c, cfg, t0, x0, lv, t1)[0]))
    return out


LUMPY_FRAC = 0.10


def _lumpy(c, cfg, t0, t1, nd):
    """True se algum abate do trecho vale (pela lista, com os bônus) LUMPY_FRAC ou mais da XP do nível."""
    rows = estimate(c, dict(cfg or {}, xp_mode="lista"), (t0, t1))["rows"]
    return any((r.get("total") or 0) >= LUMPY_FRAC * nd for r in rows)


# Morte: sem seguro o jogo tira 5% da XP do nível (nunca deixa abaixo de 0). Sem perda: o jogo gasta o Seguro
# Estendido no instante da morte (manda como item usado por quem grava); o Seguro de Vida e o período sem penalidade
# da conta ("Pen. de Morte") aparecem como status ativos na hora
DEATH_LOSS = 0.05
INSURANCE_ITEMS = {6413}                         # Seguro Estendido
INSURANCE_EFST = {251, 941}                      # CASH_DEATHPENALTY (Seguro de Vida), AID_PERIOD_DEADPENALTY
INSURANCE_MS = 2000


def insured(c, t):
    """A morte de quem grava em t não tirou XP (seguro gasto ou ativo)?"""
    me = c.me
    if any(who == me and item in INSURANCE_ITEMS and t - 200 <= u <= t + INSURANCE_MS
           for u, who, item in getattr(c, "item_uses", ())):
        return True
    return any(ef in INSURANCE_EFST and st <= t <= e + 50 for _a, ef, st, e in c.statuses(me))


def lost_deaths(c, t0=0, t1=None):
    """Instantes em que quem grava morreu sem seguro no trecho (cada uma tirou 5% da XP do nível). A morte dos
    últimos 2 s ainda espera: o aviso de que o seguro foi gasto chega logo depois dela."""
    t1 = c.now if t1 is None else t1
    me = c.me
    return [t for t, aid in c.death_log if aid == me and t0 <= t <= t1 and not insured(c, t)
            and c.now - t >= INSURANCE_MS]


def died_in(c, t0, t1):
    """True se quem grava morreu sem seguro no trecho (perdeu XP). Com o Seguro Estendido gasto (ou o Seguro de
    Vida ativo) a morte não tira nada."""
    return bool(lost_deaths(c, t0, t1))


def death_loss(c, cfg, t0, x0, lv, t1):
    """(XP que as mortes sem seguro de quem grava tiraram entre t0 e t1, quantas foram): cada uma tira 5% da XP do
    nível `lv`, nunca mais do que havia (x0 em t0 mais os abates até a morte, pela lista)."""
    deaths = lost_deaths(c, t0, t1)
    nd = need(c, cfg, lv) if deaths else None
    if not nd:
        return 0.0, 0
    lcfg = dict(cfg or {}, xp_mode="lista")           # pela lista: a correção medida usa estes trechos
    lost = 0.0
    for td in deaths:
        here = x0 + (estimate(c, lcfg, (t0, td))["xp"] if td > t0 else 0.0) - lost
        lost += min(DEATH_LOSS * nd, max(0.0, here))
    return lost, len(deaths)


def death_text(n, pct):
    """Aviso curto das mortes sem seguro: "morte sem seguro −5%"."""
    from i18n import _
    p = "%.0f%%" % pct                                 # número inteiro: não depende da vírgula do idioma
    return (_("morte sem seguro −%s") % p) if n == 1 else (_("%d mortes sem seguro −%s") % (n, p))


def unsure(c, t0, t1):
    """O trecho tem XP que não vem dos abates (missão entregue): não calibra. A perda das mortes sem seguro é
    conhecida (5% do nível) e entra de volta na XP real do trecho (level_segments, exact_segments)."""
    return quest_in(c, t0, t1)


def quest_in(c, t0, t1):
    """True se quem grava concluiu ou entregou alguma missão no trecho: a XP da recompensa não vem de abate, então
    o trecho não serve para medir a XP dos abates (uma entrega de diária no Porão rendeu 3% do nível de uma vez).
    O fim de uma espera ("[Espera] ...") não conta: não dá XP. A missão que subiu o nível vem no mesmo instante da
    subida (LEVELUP_TICK_MS): conta para os dois trechos em volta dela. A entrega do lanche (handins) conta também."""
    return (any(t0 <= t <= t1 + LEVELUP_TICK_MS and not quest_wait(q) for t, q in getattr(c, "quests_done", ()))
            or bool(handins(c, (t0, t1 + LEVELUP_TICK_MS))))


# A entrega que sobe o nível chega no mesmo instante da subida (mesmo milissegundo, antes do pacote do nível): a XP
# dela é do nível que fechou, e a sobra passa para o nível novo sem aparecer
LEVELUP_TICK_MS = 50


def _at_levelup(ta, t, up=True):
    """True se a entrega em t foi a que subiu o nível no ponto exato ta (up: ta é uma subida, não o começo)."""
    return up and ta <= t <= ta + LEVELUP_TICK_MS


def _list_xp(c, cfg, rng):
    """XP dos abates do trecho pela lista de bônus (sem correção e sem missões), ou None se não dá para medir."""
    est = estimate(c, dict(cfg or {}, xp_mode="lista"), rng)
    return None if est["unknown"] or not est["kill_xp"] else est["kill_xp"]


def session_correction(c, cfg):
    """(real ÷ lista, XP real coberta) das subidas de nível desta gravação, ou None."""
    # os trechos já fecharam (terminam numa subida de nível): não mudam com o que chega depois
    sig = (id(c), len(getattr(c, "level_ups", ())), len(getattr(c, "quests_done", ())),
           len(getattr(c, "quests_added", ())), repr(sorted((cfg or {}).get("xp_bonuses", {}).items())))
    hit = _CACHE.get("sc")
    if hit and hit[0] == sig:
        return hit[1]
    real = est = 0.0
    for t0, t1, gain in level_segments(c, cfg):
        if unsure(c, t0, t1):
            continue
        e = _list_xp(c, cfg, (t0, t1))
        if e:
            real += gain
            est += e
    res = (real / est, real) if est else None
    _CACHE["sc"] = (sig, res)
    return res


def _all_samples(cfg):
    """{personagem: [medidas que ainda valem]} de todos os personagens. Medida: [razão, XP coberta, quando, origem,
    mapa, abates]. Valem as de até 30 dias antes da mais nova de qualquer personagem."""
    raw = {g: list((e or {}).get("samples") or []) for g, e in ((cfg or {}).get("xp_corr") or {}).items()}
    newest = max((_when(x[2]) for xs in raw.values() for x in xs if _when(x[2]) is not None), default=None)
    out = {}
    for g, xs in raw.items():
        keep = [x for x in xs if newest is None or _when(x[2]) is None or newest - _when(x[2]) <= CALIBRATE_FRESH_S]
        if keep:
            out[g] = keep
    return out


def _fresh_samples(c, cfg):
    """As medidas guardadas do personagem que ainda valem."""
    return _all_samples(cfg).get(str(c.session.gid), [])


def _weighted(samples):
    """(média das razões pesada pela XP de cada medida, nº de medidas) ou None."""
    w = sum(x[1] for x in samples)
    return (sum(x[0] * x[1] for x in samples) / w, len(samples)) if w else None


def _sample_map(x):
    return x[4] if len(x) >= 5 and x[4] else ""


def _sample_kills(x):
    return x[5] if len(x) >= 6 and x[5] else 100


def _baseline(samples):
    """O normal do personagem, para mapa que ele nunca mediu: a média dos mapas que rendem menos (até 8% acima do
    mais baixo). O Monster Spotlight só aumenta a XP, então os mapas sem evento ficam no grupo de baixo. Os mapas de
    outra versão no LATAM (foreign_map: a Biosfera rende uns 15% da lista) ficam de fora: puxariam o normal para
    baixo e todo mapa ainda sem medida sairia com a XP deles."""
    samples = [x for x in samples if not foreign_map(_sample_map(x))]
    by = {}
    for x in samples:
        if _sample_map(x):
            by.setdefault(_sample_map(x), []).append(x)
    means = {}
    for m, xs in by.items():
        w = _weighted(xs)
        if w:
            means[m] = w[0]
    if not means:
        w = _weighted(samples)
        return w[0] if w else None
    lo = min(means.values())
    w = _weighted([x for m, xs in by.items() if m in means and means[m] <= lo * (1 + BASE_SPREAD) for x in xs])
    return w[0] if w else None


MEASURED = ("mapa", "personagens", "registro")   # de onde vem a correção quando o mapa já tem medida exata


def predict(cfg, gid, mapname):
    """A correção de um personagem num mapa: (correção, de onde, nº de medidas) ou None. De onde:
    "mapa" — as medidas dele nesse mapa;
    "personagens" — o mapa medido por outros personagens: quanto ele rende a mais para eles (sobre o normal de cada
                    um), vezes o normal deste (1 se ele ainda não tem medida nenhuma);
    "registro" — o mapa medido em gravações anteriores que a configuração não guarda (a leitura da pasta, ou medidas
                 apagadas ao mudar os bônus): da mesma forma, quanto ele rendeu a mais sobre o normal da época;
    "personagem" — mapa que ninguém mediu: o normal dele."""
    allc = _all_samples(cfg)
    mine = allc.get(str(gid), [])
    m = map_key(mapname or "")
    if m:
        w = _weighted([x for x in mine if _sample_map(x) == m])
        if w:
            return w[0], "mapa", w[1]
    base_me = _baseline(mine) if mine else None
    if m:
        for source, groups, skip in (("personagens", allc, str(gid)), ("registro", _log_samples(cfg), None)):
            eff = weight = 0.0
            n = 0
            for g, xs in groups.items():
                on = [x for x in xs if _sample_map(x) == m] if g != skip else []
                b = _baseline(xs) if on else None
                w = _weighted(on) if on else None
                if b and w:
                    k = sum(_sample_kills(x) for x in on)       # entre personagens pesa pelos abates, não pela XP
                    eff += w[0] / b * k
                    weight += k
                    n += len(on)
            if weight:
                return (base_me or 1.0) * eff / weight, source, n
    if base_me:
        return base_me, "personagem", len(mine)
    return None


def _log_samples(cfg):
    """As medidas do registro de aprendizado no formato das guardadas ({personagem: [[razão, XP, quando, origem, mapa,
    abates]]}): sem as de trecho com entrega de missão e só as de até 30 dias antes da mais nova. O registro guarda
    tudo o que foi medido, também o que a configuração não tem: a leitura das gravações que já estavam na pasta e as
    medidas apagadas ao mudar os bônus. Como cada uma vale sobre o normal do personagem na época (predict), uma lista
    que mudou depois não atrapalha. Guardadas enquanto o registro não muda."""
    lrn = (cfg or {}).get("xp_learn")
    if not isinstance(lrn, dict) or not isinstance(lrn.get("measures"), list) or not lrn["measures"]:
        return {}
    key = (id(lrn), lrn.get("rev"), len(lrn["measures"]))
    hit = _CACHE.get("log")
    if hit and hit[0] == key:
        return hit[1]
    raw = [x for x in lrn["measures"] if isinstance(x, dict) and x.get("ratio") and x.get("map") and x.get("char")
           and not x.get("quests") and (x.get("gain") or 0) > 0]
    newest = max((_when(x.get("date")) for x in raw if _when(x.get("date")) is not None), default=None)
    out = {}
    for x in raw:
        w = _when(x.get("date"))
        if newest is not None and w is not None and newest - w > CALIBRATE_FRESH_S:
            continue
        out.setdefault(str(x["char"]), []).append([float(x["ratio"]), float(x["gain"]), x.get("date"), x.get("src"),
                                                   map_key(x["map"]), int(x.get("kills") or 0)])
    _CACHE["log"] = (key, out)
    return out


def stored_correction(c, cfg, mapname=None):
    """(correção, nº de medidas) ou None. Com `mapname`, as medidas feitas nesse mapa, se houver (cada mapa rende
    de um jeito: o Monster Spotlight dá mais só a alguns monstros de alguns mapas); senão, todas as do
    personagem, menos as dos mapas de outra versão no LATAM (foreign_map), que só valem para eles."""
    samples = _fresh_samples(c, cfg)
    if mapname:
        here = [x for x in samples if _sample_map(x) == map_key(mapname)]
        if here:
            return _weighted(here)
    return _weighted([x for x in samples if not foreign_map(_sample_map(x))])


def map_corrections(c, cfg):
    """{mapa: correção} dos mapas que têm medidas próprias do personagem."""
    by = {}
    for x in _fresh_samples(c, cfg):
        if _sample_map(x):
            by.setdefault(_sample_map(x), []).append(x)
    out = {}
    for m, xs in by.items():
        w = _weighted(xs)
        if w:
            out[m] = w[0]
    return out


def own_samples(c, cfg, mapname=None):
    """Quantas medidas o personagem tem no mapa (o atual, sem `mapname`)."""
    m = map_key(mapname or c.map or c.session.map)
    return sum(1 for x in _fresh_samples(c, cfg) if _sample_map(x) == m)


def _kill_corrections(c, cfg, source, corr):
    """Função t -> correção do abate em t: com as medidas guardadas, a do mapa em que ele aconteceu (predict); a
    da subida de nível desta gravação vale para a gravação inteira."""
    if not source or source[0] != "medido" or source[1] == "nivel":
        return lambda t: corr
    spans = sorted(c.map_spans())
    names = [map_key(m) for _s, _e, m in spans]
    if len(set(names)) <= 1:
        return lambda t: corr                            # um mapa só: a correção dele
    starts = [s for s, _e, _m in spans]
    memo = {}

    def at(t):
        i = bisect.bisect_right(starts, t) - 1
        m = names[i] if i >= 0 else ""
        if m not in memo:
            p = predict(cfg, c.session.gid, m) if m else None
            memo[m] = p[0] if p else corr
        return memo[m]
    return at


def _when(text):
    """Segundos de uma data "AAAA-MM-DD HH:MM" das medidas guardadas (None se não der para ler)."""
    try:
        return (datetime.datetime.strptime(text, "%Y-%m-%d %H:%M") - datetime.datetime(2000, 1, 1)).total_seconds()
    except (TypeError, ValueError):
        return None


def correction(c, cfg):
    """A correção que vale agora: a das subidas de nível desta gravação, senão a média guardada.
    (correção, origem) ou (None, None)."""
    sc = session_correction(c, cfg)
    if sc:
        return sc[0], "nivel"
    p = predict(cfg, c.session.gid, c.map or c.session.map)      # a do mapa em que quem grava está
    if p:
        return p[0], p[2]
    return None, None


def correction_kind(c, cfg):
    """De onde vem a correção agora: "nivel", "mapa", "personagens", "registro", "personagem" ou None."""
    if session_correction(c, cfg):
        return "nivel"
    p = predict(cfg, c.session.gid, c.map or c.session.map)
    return p[1] if p else None


def calibration_hint(c, cfg):
    """Mapa ainda sem medida (nem deste personagem, nem de outro, nem no registro de gravações anteriores), 10 min de
    farm nele e nenhuma subida de nível na gravação: a tela da XP sugere parar e gravar de novo (duas gravações
    seguidas dão a XP exata, e a previsão passa a valer para o mapa). Só quando gravar de novo mede mesmo este mapa: o
    trecho desde o começo da gravação não tem entrega de missão, monstro sem XP nem Zerar, e a XP dos abates dele é
    deste mapa (senão a pessoa reiniciava e o aviso voltava). Devolve o mapa ou None. Não aparece em replay que já
    acabou de gravar."""
    mode = cfg.get("xp_mode") if cfg.get("xp_mode") in MODES else "auto"
    if mode not in ("auto", "medido") or getattr(c, "finished", False) or not c.session.gid:
        return None
    if c.session.base_exp is None or getattr(c, "level_ups", None):
        return None
    here = map_key(c.map or c.session.map)
    p = predict(cfg, c.session.gid, here)
    if not here or (p and p[1] in MEASURED):
        return None
    spans = [s for s, _e, m in c.map_spans() if map_key(m) == here]
    rows = [r for r in kills(c, (spans[-1] if spans else 0, c.now))[0] if r["xp"]]
    if len(rows) < CALIBRATE_MIN_KILLS or c.now - rows[0]["t"] < CALIBRATE_MIN_MS:
        return None
    an = anchors(c)
    t0 = an[-1][0] if an else 0                      # o trecho que a gravação seguinte vai medir (exact_segments)
    cut = getattr(c, "reset_t", None)
    if (cut is not None and cut > t0) or kills(c, (t0, c.now))[1] or unsure(c, t0, c.now):
        return None
    return here if _kill_map(c, t0, c.now) == here else None


def meter_name(mob):
    """Nome do monstro pela base do programa (None se ela não conhece)."""
    import meter
    return meter.monster_name(mob)


def _learn(cfg):
    """O registro do que o programa aprende (cfg["xp_learn"]): medidas, mudanças nos mapas, evento do servidor e
    monstros sem XP na base. Só neste PC; o relatório (xpreport) mostra sem nada pessoal."""
    lrn = cfg.setdefault("xp_learn", {})
    for k, v in (("measures", []), ("unknown", {}), ("server", []), ("changes", []), ("drops", {}), ("names", {}),
                 ("quests", []), ("maps", {})):
        if not isinstance(lrn.get(k), type(v)):
            lrn[k] = v
    if not isinstance(lrn.get("secret"), str):
        # sorteio feito uma vez neste PC: as marcas dos registros no relatório (para não contar duas vezes o que vier
        # repetido em relatórios seguidos) não deixam descobrir o nome da gravação
        lrn["secret"] = os.urandom(8).hex()
        touch_learn(lrn)
    return lrn


def touch_learn(lrn):
    """Marca que o registro de aprendizado mudou: o widget grava o arquivo dele (aprendizado.json) na próxima vez
    que salvar a configuração."""
    lrn["rev"] = int(lrn.get("rev") or 0) + 1


def _measure_log(c, cfg, t0, t1, gain, ratio, mapname, src, when):
    """Uma medida para o registro: quando, mapa, duração, abates, real ÷ lista, classe e nível, mortes, missões,
    bônus (quanto do trecho cada um valeu), os monstros que mais renderam e quantos abates foram divididos."""
    rows = kills(c, (t0, t1))[0]
    base = {}
    for r in rows:
        if r["xp"]:
            base[r["mob"]] = base.get(r["mob"], 0.0) + r["xp"]
    tot = sum(base.values()) or 1.0
    mobs = [[m, round(100.0 * v / tot)] for m, v in sorted(base.items(), key=lambda kv: -kv[1])[:6]]
    bon = {}
    for k, v in sim_real(c, cfg, (t0, t1)).items():
        if v.get("cover") is None:
            if v.get("counted"):
                bon[k] = [100, v["pct"]]
        elif v["cover"] > 0.005:
            bon[k] = [round(100 * v["cover"]), v["pct"]]
    mine = [t for t, aid in c.death_log if aid == c.me and t0 <= t <= t1]
    lost = len(lost_deaths(c, t0, t1))
    # cada entrega de missão com os bônus ativos no instante: juntando relatórios, diz quais multiplicam a XP dela
    wins, sets = windows(c, cfg), settings(cfg, c)
    quest_at, edge = [], []
    ups = [t for t, _lv in getattr(c, "level_ups", ())]
    turned = list(getattr(c, "quests_done", ())) + [(t, q) for t, q, _i in handins(c)]
    for t, q in sorted(turned):
        if t0 <= t <= t1 + LEVELUP_TICK_MS:
            on = {}
            for b in BONUSES:
                if b["key"] in QUEST_LOG_KEYS:
                    pct = _pct_at(b, t, wins, sets)
                    if pct is not None:
                        on[b["key"]] = pct
            quest_at.append([q, on])
            # entregue no instante de uma subida: a sobra passou para o outro nível sem aparecer (não serve para medir)
            at_start = t0 in ups and t <= t0 + LEVELUP_TICK_MS
            at_end = abs(t - t1) <= LEVELUP_TICK_MS and any(abs(u - t1) <= LEVELUP_TICK_MS for u in ups)
            if at_start or at_end:
                edge.append(q)
    return dict(src=src, date=when, map=mapname, mins=round((t1 - t0) / 60000.0, 1), kills=len(rows), ratio=ratio,
                gain=int(gain), char=str(c.session.gid), job=c.session.job, level=level_at(c, t0), deaths=lost,
                insured=len(mine) - lost, quests=[x[0] for x in quest_at],
                quest_at=quest_at, edge=edge, bonus=bon, mobs=mobs, shared=sum(1 for r in rows if r["share"] < 0.999),
                party=len(c.party), spot_list=bool(event_spots(c)))


def _learn_recording(c, cfg, name, when, logs):
    """Guarda no registro as medidas desta gravação (refeitas se ela for lida de novo) e os monstros que não têm
    XP na base, com o mapa de cada abate."""
    lrn = _learn(cfg)
    lrn["measures"] = ([x for x in lrn["measures"] if not str(x.get("src", "")).startswith(name + "#")]
                       + logs)[-LEARN_KEEP:]
    from i18n import _
    for r in kills(c)[0]:                    # o nome que o jogo mostrou (monstros novos não estão na base)
        nm = r["name"]
        if (nm and not nm.startswith("\x1c") and nm != _("Monstro %d") % r["mob"] and str(r["mob"]) not in
                lrn["names"] and not meter_name(r["mob"])):
            lrn["names"][str(r["mob"])] = nm
    spans = sorted(c.map_spans())
    starts = [s for s, _e, _m in spans]
    unknown = {}
    for r in kills(c)[0]:
        if r["xp"] is None:
            i = bisect.bisect_right(starts, r["t"]) - 1
            m = map_key(spans[i][2]) if i >= 0 else map_key(c.session.map)
            u = unknown.setdefault(r["mob"], dict(name=r["name"], maps={}))
            u["maps"][m] = u["maps"].get(m, 0) + 1
    for mob, u in unknown.items():
        e = lrn["unknown"].setdefault(str(mob), dict(name=u["name"], recs={}, maps={}))
        e["name"], e["last"] = u["name"], when[:10]
        e["recs"][name] = sum(u["maps"].values())            # a mesma gravação conta uma vez
        for m, n in u["maps"].items():
            e["maps"][m] = max(e["maps"].get(m, 0), n)
        if len(e["recs"]) > 40:
            e["recs"] = dict(list(e["recs"].items())[-40:])
    if len(lrn["unknown"]) > LEARN_UNKNOWN:
        keep = sorted(lrn["unknown"].items(), key=lambda kv: kv[1].get("last", ""))[-LEARN_UNKNOWN:]
        lrn["unknown"] = dict(keep)
    log_map_mix(lrn, c, name, when)
    drops = drop_log(c)
    if drops:
        lrn["drops"][name] = dict(date=when[:10], mobs=drops)
        if len(lrn["drops"]) > LEARN_DROP_RECS:
            lrn["drops"] = dict(sorted(lrn["drops"].items(), key=lambda kv: kv[1].get("date", ""))[-LEARN_DROP_RECS:])
    touch_learn(lrn)                          # o widget salva quando muda (gravação sem XP exata também)


def drop_context(c):
    """Função t -> os bônus de drop ativos em quem grava no instante t, como texto curto ("252:100+983"; "-" sem
    nenhum): o efeito e, quando o jogo manda, o valor dele (o % do Chiclete)."""
    wins = []
    for ef in DROP_EFST:
        for s, e in c.lasting(ef):
            val = c.status_val.get((c.me, ef, s)) or 0
            wins.append((s, e, "%d:%d" % (ef, val) if val else "%d" % ef))

    def at(t):
        return "+".join(sorted({tag for s, e, tag in wins if s <= t <= e})) or "-"
    return at


def drop_log(c):
    """Drops da gravação para o registro: {monstro: {bônus de drop: [abates, {item: quantos caíram}]}}, dos monstros
    que quem grava matou dando a maior parte do dano (a chance de drop é a de quem mata), só nos abates isolados (sem
    outra morte de monstro até 0,35 s antes ou depois): numa rajada de mortes não dá para saber de quem caiu cada
    item, e contar os itens da rajada num abate só inflava a taxa."""
    ctx = drop_context(c)
    deaths = sorted((t, aid) for t, aid in c.death_log if c.entities.get(aid) is not None
                    and c.entities[aid].kind == "mob" and not c.is_friendly(aid))
    times = [t for t, _a in deaths]
    alone = set()                       # (aid, hora da morte): o jogo reaproveita o aid quando o monstro renasce
    for i, (t, aid) in enumerate(deaths):
        if (i == 0 or t - times[i - 1] > DROP_ALONE_MS) and (i + 1 == len(times) or times[i + 1] - t > DROP_ALONE_MS):
            alone.add((aid, t))
    by_death = {}
    for d in c.drops:
        if not d.get("fell"):
            continue
        j = bisect.bisect_right(times, d["t"]) - 1           # a última morte até o item cair
        if j >= 0 and d["t"] - times[j] <= DROP_ALONE_MS and (deaths[j][1], times[j]) in alone:
            by_death.setdefault((deaths[j][1], times[j]), []).append(d)
    out = {}
    for r in kills(c)[0]:
        if r["share"] < 0.5 or (r["aid"], r["t"]) not in alone:
            continue
        row = out.setdefault(str(r["mob"]), {}).setdefault(ctx(r["t"]), [0, {}])
        row[0] += 1
        for d in by_death.get((r["aid"], r["t"]), ()):
            row[1][str(d["item"])] = row[1].get(str(d["item"]), 0) + d["count"]
    return out


def _check_change(cfg, gid, x):
    """Medida nova que discorda das antigas do mesmo personagem no mesmo mapa (mais que 12% num trecho longo, 20%
    num curto): o mapa mudou (evento começou ou acabou). As medidas antigas desse mapa saem, de todos os personagens,
    e a mudança vai para o registro."""
    m = _sample_map(x)
    p = predict(cfg, gid, m) if m else None
    if not p or p[1] != "mapa":
        return False
    fit = CHANGE_FIT[0] if _sample_kills(x) >= CHANGE_LONG_KILLS else CHANGE_FIT[1]
    if abs(x[0] / p[0] - 1.0) <= fit:
        return False
    t_new = _when(x[2])
    for e in ((cfg.get("xp_corr") or {}).values()):
        e["samples"] = [y for y in e.get("samples", []) if _sample_map(y) != m
                        or (t_new is not None and _when(y[2]) is not None and _when(y[2]) >= t_new)]
    lrn = _learn(cfg)
    lrn["changes"] = (lrn["changes"] + [dict(date=x[2][:10], map=m, old=round(p[0], 3), new=round(x[0], 3))])[-100:]
    touch_learn(lrn)
    _CACHE.pop("sc", None)
    return True


def calibrate(c, cfg, xp_after):
    """Guarda em cfg["xp_corr"][personagem] as medidas de "XP real ÷ XP pela lista" desta gravação: cada trecho
    até uma subida de nível e o trecho até a gravação seguinte (se ela começou logo depois). Trecho com menos de
    10 min não conta. Também anota a XP do nível que o jogo mandou (cfg["xp_levels"]). Devolve a correção média
    nova ou None."""
    s = c.session
    if not getattr(c, "path", None) or not s.gid or not gear_ready():
        return None
    if s.base_level and s.next_exp and s.next_exp != 999999999:
        cfg.setdefault("xp_levels", {}).setdefault(str(s.job), {})[str(s.base_level)] = s.next_exp
    remember_manual(c, cfg)
    segs = exact_segments(c, cfg, xp_after)
    detect_spot(c, cfg, segs)                    # marcas automáticas de versões anteriores saem
    detect_server(c, cfg, segs)                  # antes de medir: a correção é sobre a lista já acertada
    when = "%04d-%02d-%02d %02d:%02d" % tuple(s.recorded_at[:5])
    name = os.path.basename(c.path)
    new, logs = [], []
    for t0, t1, gain, tag in segs:
        if not _big(c, cfg, t0, t1, gain):
            continue
        est = _list_xp(c, cfg, (t0, t1))
        if not est:
            continue
        m = _kill_map(c, t0, t1) or ""
        src = "%s#%s" % (name, tag)
        ratio = round(gain / est, 4)
        logs.append(_measure_log(c, cfg, t0, t1, gain, ratio, m, src, when))
        if not unsure(c, t0, t1):                     # trecho com missão entregue vai só para o registro
            new.append([ratio, gain, when, src, m, len(kills(c, (t0, t1))[0])])
    learn_quests(c, cfg, segs)
    _learn_recording(c, cfg, name, when, logs)
    if not new:
        return None
    entry = cfg.setdefault("xp_corr", {}).setdefault(str(s.gid), {})
    entry["samples"] = [x for x in entry.get("samples", []) if not x[3].startswith(name + "#")]
    for x in new:
        _check_change(cfg, s.gid, x)                 # o mapa mudou: as medidas antigas dele saem
    entry["samples"] = (entry["samples"] + new)[-CALIBRATE_KEEP:]
    return stored_correction(c, cfg)[0]


def exact_segments(c, cfg, xp_after=None):
    """Trechos da gravação com a XP real exata: [(início, fim, XP real, rótulo)]. Cada subida de nível fecha um; com
    `xp_after`, o último vai até o começo da gravação seguinte do personagem, se ela começou logo depois."""
    s = c.session
    segs = [(t0, t1, gain, "%d" % i) for i, (t0, t1, gain) in enumerate(level_segments(c, cfg))]
    an = anchors(c)
    cut = getattr(c, "reset_t", None)   # Zerar depois do último ponto exato: os abates do trecho não estão todos
    nxt = xp_after(c.path, s) if xp_after is not None and getattr(c, "path", None) else None
    if an and nxt and nxt.get("exp") is not None and (cut is None or an[-1][0] >= cut):
        start, other = _seconds(s.recorded_at), _seconds(nxt["when"])
        if start is not None and other is not None and other - (start + c.now / 1000.0) <= CALIBRATE_GAP_S:
            t0, lv, x0 = an[-1]                 # do último ponto exato até o começo da gravação seguinte
            gain = None
            if nxt["level"] == lv:
                gain = nxt["exp"] - x0
            elif nxt["level"] == lv + 1 and need(c, cfg, lv):
                gain = need(c, cfg, lv) - x0 + nxt["exp"]
            if gain and gain > 0:
                segs.append((t0, c.now, gain + death_loss(c, cfg, t0, x0, lv, c.now)[0], "fim"))
    return segs


def _big(c, cfg, t0, t1, gain):
    """O trecho serve para medir: 10 min ou 1% do nível, e pelo menos 3 abates."""
    nd = need(c, cfg, level_at(c, t0))
    big = t1 - t0 >= CALIBRATE_MIN_MS or (nd and gain >= CALIBRATE_MIN_FRAC * nd)
    return bool(big) and len(kills(c, (t0, t1))[0]) >= CALIBRATE_MIN_KILLS


def _manual_blind(c, t0, t1):
    """True se no trecho valeu um manual sem o valor (já ativo no começo da gravação) e sem um último % lembrado:
    a lista pode estar errada por causa dele, não do evento do servidor."""
    return any(v <= 0 and s < t1 and e > t0 for s, e, v in _lasting_vals(c, 250))


def _one_map(c, t0, t1):
    """O mapa do trecho, se ele se passou todo num mapa só (None se houve troca de mapa no meio)."""
    names = {map_key(m) for s, e, m in c.map_spans() if s < t1 and e > t0}
    return names.pop() if len(names) == 1 else None


def _kill_map(c, t0, t1):
    """O mapa do trecho pelos abates: o que deu pelo menos 95% da XP crua dos abates (map_key). A gravação que começa
    na cidade ou na entrada da torre e segue para o mapa de farm é medida do mapa de farm (antes ficava sem mapa, e o
    aviso de calibrar voltava). Sem abates com XP, o mapa único do trecho; None se a XP se divide entre mapas."""
    rows = [r for r in kills(c, (t0, t1))[0] if r["xp"]]
    if not rows:
        one = _one_map(c, t0, t1)
        return map_key(one) if one else None
    spans = sorted(c.map_spans())
    starts = [s for s, _e, _m in spans]
    by = {}
    for r in rows:
        i = bisect.bisect_right(starts, r["t"]) - 1
        m = map_key(spans[i][2]) if i >= 0 else map_key(c.session.map)
        by[m] = by.get(m, 0.0) + r["xp"]
    m, v = max(by.items(), key=lambda kv: kv[1])
    return m if m and v >= KILL_MAP_SHARE * sum(by.values()) else None


def detect_spot(c, cfg, segs=None, xp_after=None):
    """As marcas automáticas de spotlight por mapa (das versões anteriores) saem: agora cada mapa aprende quanto
    rende a mais com a XP exata (stored_correction por mapa) e a lista do evento conta monstro a monstro. As medidas
    feitas com uma marca automática saem junto (eram sobre a lista com ela). A marca feita à mão fica. Devolve o
    mapa que mudou ou None."""
    gone = [k for k, e in (cfg.get("xp_spot") or {}).items() if isinstance(e, dict) and e.get("auto")]
    for k in gone:
        del cfg["xp_spot"][k]
    entry = (cfg.get("xp_corr") or {}).get(str(c.session.gid))
    if gone and entry:
        drop = {map_key(k) for k in gone}
        entry["samples"] = [x for x in entry.get("samples", []) if _sample_map(x) not in drop]
    if gone:
        _CACHE.pop("sc", None)
    return map_key(gone[0]) if gone else None


def detect_server(c, cfg, segs=None, xp_after=None):
    """Deduz o evento do servidor da XP exata (só no modo automático). Em cada trecho exato que serve (sem entrega
    de missão, sem manual de valor desconhecido), a lista é refeita com o evento em 0, 50, 100 e 200%; se um deles
    fecha a 6% do real e o que está marcado erra mais de 12%, o programa marca esse (e esquece as medidas antigas,
    que eram sobre a lista errada). Devolve o % novo (0 = sem evento) ou None se nada mudou."""
    if (cfg.get("xp_mode") if cfg.get("xp_mode") in MODES else "auto") != "auto" or not _fresh(c) or not gear_ready():
        return None
    segs = exact_segments(c, cfg, xp_after) if segs is None else segs
    known = (cfg.get("xp_manual_last") or {}).get(str(c.session.gid))
    use = [(t0, t1, gain) for t0, t1, gain, _tag in segs
           if not unsure(c, t0, t1) and _big(c, cfg, t0, t1, gain) and (known or not _manual_blind(c, t0, t1))
           and not _foreign_in(c, t0, t1)]          # a lista de outra versão diz nada do evento
    real = sum(g for _a, _b, g in use)
    if not real:
        return None

    def ratio(pct):
        bon = dict(cfg.get("xp_bonuses") or {})
        bon["server"] = dict(on=pct > 0, pct=pct or 100)
        est = [_list_xp(c, dict(cfg, xp_bonuses=bon), (t0, t1)) for t0, t1, _g in use]
        return real / sum(est) if all(est) else None
    cur = settings(cfg)["server"]
    now = cur["pct"] if cur["on"] else 0
    fits = {pct: ratio(pct) for pct in set(SERVER_CHOICES) | {now}}
    if any(v is None for v in fits.values()):
        return None
    best = min(SERVER_CHOICES, key=lambda p: abs(fits[p] - 1.0))
    if best == now or abs(fits[best] - 1.0) > SERVER_FIT or abs(fits[now] - 1.0) < SERVER_MISS:
        return None
    t_rec = _when("%04d-%02d-%02d %02d:%02d" % tuple(c.session.recorded_at[:5]))
    recent = [x for xs in _all_samples(cfg).values() for x in xs
              if t_rec is not None and _when(x[2]) is not None and t_rec - _when(x[2]) <= SERVER_RECENT_S]
    if fits[now] > 1.0:
        # XP acima da lista num mapa, mas as medidas recentes de outros mapas (de qualquer personagem) fecham com
        # ela: é coisa do mapa (o spotlight dá mais a alguns monstros), não do servidor; a correção do mapa cuida
        here = {_kill_map(c, t0, t1) or "" for t0, t1, _g in use}
        other = [x for x in recent if _sample_map(x) and _sample_map(x) not in here
                 and not foreign_map(_sample_map(x))]
        w = _weighted([[x[0], _sample_kills(x)] for x in other])
        if w and abs(w[0] - 1.0) <= SERVER_FIT:
            return None
    cfg.setdefault("xp_bonuses", {})["server"] = dict(on=best > 0, pct=best or 100, auto=True)
    # as medidas do último dia foram feitas com o % errado; as mais velhas eram certas para a época delas
    for e in (cfg.get("xp_corr") or {}).values():
        e["samples"] = [x for x in e.get("samples", []) if x not in recent]
    lrn = _learn(cfg)
    lrn["server"] = (lrn["server"] + [dict(date="%04d-%02d-%02d" % tuple(c.session.recorded_at[:3]), old=now,
                                           new=best)])[-50:]
    touch_learn(lrn)
    _CACHE.pop("sc", None)
    return best


def learn_levels(c, cfg):
    """Ao vivo, a cada subida de nível: aprende a recompensa das missões dos níveis que acabaram de fechar (a conta de
    learn_quests), sem esperar a gravação seguinte começar. Com isso a missão que se repete a cada nível (as diárias
    da Sociedade de Monstros, renovadas com Água Mineral) já entra certa no nível seguinte da mesma gravação. Cada
    nível é visto uma vez; os rótulos são os mesmos da calibração (exact_segments), então a anotação no registro de
    aprendizado é trocada, não repetida, quando a gravação seguinte começa. True se aprendeu alguma."""
    if not QUEST_XP_ON or not gear_ready() or not getattr(c, "quests_done", None):
        return False
    upto = getattr(c, "quests_learned_upto", None)
    segs = [(t0, t1, gain, "%d" % i) for i, (t0, t1, gain) in enumerate(level_segments(c, cfg))
            if upto is None or t1 > upto]
    if not segs:
        return False
    c.quests_learned_upto = segs[-1][1]
    return learn_quests(c, cfg, segs)


def learn_quests(c, cfg, segs):
    """Aprende a XP das missões num trecho com XP exata: real − abates − as missões já conhecidas do trecho, quando
    isso pesa pelo menos um quarto dele (abaixo disso o erro dos abates engole a conta). Uma missão a medir: a
    recompensa dela. Várias entregues juntas (as diárias do mesmo NPC): o total dividido entre elas, valendo só
    quando forem entregues juntas de novo (sozinha, cada uma pode render bem diferente: em Hugel, de 8 a 48 milhões).
    Trecho sem abates também serve: gravar, entregar e gravar de novo dá a recompensa exata. A já conhecida só é
    reaprendida se errar mais de 15%. Fica de fora o trecho com uma entrega no instante de uma subida de nível, na
    ponta ou no começo: a sobra dela passa para o nível novo sem aparecer. Guarda a recompensa sem bônus em
    cfg["xp_quests"], que vale mais que a tabela (é o que o jogo pagou no LATAM). True se aprendeu alguma."""
    if not QUEST_XP_ON:
        return False
    corr0 = correction(c, cfg)[0]
    corr = corr0 or 1.0
    # sem medida exata dos abates (evento do servidor desmarcado, nenhum nível sem missão...) a lista pode errar
    # muito, e o erro iria todo para a missão: aí ela só é aprendida se pesar quase o trecho todo
    share_min = QUEST_LEARN_MIN if corr0 else QUEST_LEARN_BLIND
    lcfg = dict(cfg or {}, xp_mode="lista")
    learned = False
    name = os.path.basename(getattr(c, "path", None) or "")
    when = "%04d-%02d-%02d" % tuple(c.session.recorded_at[:3]) if c.session.recorded_at else ""
    for t0, t1, gain, tag in segs:
        qs = quest_rows(c, cfg, (t0, t1 + LEVELUP_TICK_MS))
        if not qs or any(_at_levelup(t0, q["t"], t0 > 0) for q in qs):
            continue
        if tag != "fim" and any(abs(q["t"] - t1) <= LEVELUP_TICK_MS for q in qs):
            continue                                  # a entrega subiu o nível: a sobra dela não aparece
        est = estimate(c, lcfg, (t0, t1))
        if est["unknown"]:
            continue
        kill = est["kill_xp"] * corr
        pending = [q for q in qs if q["xp"] is None or _quest_partners(cfg, q["quest"])]
        known = [q for q in qs if q not in pending]
        if pending:
            rest = gain - kill - sum(q["xp"] for q in known)
            if rest < share_min * gain:
                continue
            ids = sorted({q["quest"] for q in pending})
            entries = []
            for q in pending:                     # a mesma missão entregue mais de uma vez conta em cada entrega
                entry = dict(base=int(round(rest / len(pending) / q["mult"])), level=level_at(c, q["t"]),
                             mult=round(q["mult"], 3))
                if len(ids) > 1:
                    entry["with"] = [i for i in ids if i != q["quest"]]
                entries.append((q, entry))
            if any(whole_level(e["level"], e["base"] * e["mult"], e["mult"]) for _q, e in entries):
                continue                          # os abates do trecho não entraram: não é a recompensa
            for q, entry in entries:
                cfg.setdefault("xp_quests", {})[str(q["quest"])] = entry
                _quest_log(cfg, "%s#%s" % (name, tag), q["quest"], entry, when, None)
            learned = True
        elif known and len({q["quest"] for q in known}) == 1 and not known[0].get("handin"):
            # a única missão do trecho, entregue uma vez ou mais (a Água Mineral renova a espera da Sociedade de
            # Monstros: a mesma missão várias vezes no dia, cada entrega com a recompensa inteira)
            q = known[0]
            rest = gain - kill
            if rest < share_min * gain:
                continue
            entry = dict(base=int(round(rest / sum(x["mult"] for x in known))), level=level_at(c, q["t"]),
                         mult=round(q["mult"], 3))
            if whole_level(entry["level"], entry["base"] * entry["mult"], entry["mult"]):
                continue                              # os abates do trecho não entraram: não é a recompensa
            _quest_log(cfg, "%s#%s" % (name, tag), q["quest"], entry, when, q["base"])
            if abs(entry["base"] / q["base"] - 1.0) <= QUEST_RELEARN_FIT:
                continue                              # a recompensa conhecida confere
            cfg.setdefault("xp_quests", {})[str(q["quest"])] = entry
            learned = True
    return learned


def _quest_log(cfg, src, qid, entry, when, known):
    """Anota no registro de aprendizado uma recompensa medida (vai para o relatório): a missão, a recompensa sem
    bônus, o nível, o multiplicador da hora, as missões com que ela veio junto e a recompensa que o programa já
    conhecia (quando a medida só confere a tabela). A mesma gravação lida de novo troca a anotação."""
    lrn = _learn(cfg)
    obs = dict(src=src, quest=qid, base=entry["base"], level=entry.get("level"), mult=entry.get("mult"), date=when)
    if entry.get("with"):
        obs["with"] = list(entry["with"])
    if known:
        obs["known"] = int(round(known))
    lrn["quests"] = ([x for x in lrn["quests"] if not (x.get("src") == src and x.get("quest") == qid)]
                     + [obs])[-LEARN_QUESTS:]
    touch_learn(lrn)


def _quest_partners(cfg, qid):
    """As missões com que esta foi aprendida em grupo (o total do grupo dividido entre elas), ou um conjunto vazio."""
    learned = ((cfg or {}).get("xp_quests") or {}).get(str(qid))
    return set(learned.get("with") or ()) if isinstance(learned, dict) else set()


# Bônus de XP. Os detectáveis valem só enquanto o status está ativo em quem grava; os consumíveis (manuais)
# competem entre si: vale só o maior. A conta foi medida abate a abate com a XP exata que o servidor manda pela
# rede (capturas de 2026-11-11, mais de 1.300 abates; o replay não grava esses pacotes):
#
#     XP = XP do monstro × penalidade × [ (1 + g) × (1 + k) + p ] × (1 + primeiro passo)
#
#   g ("role" g): evento do servidor e os bônus de conta (VIP, Cetro);
#   k: o que aumenta a XP de cada abate e multiplica só o grupo g: texto dos itens e Banquete de Njord;
#   p: o que soma por fora, sobre a XP crua do monstro: manuais e o Kafra Buff (status "Manual de Mascar");
#   primeiro passo: Milagre (+100%, dobra tudo) ou, sem ele, o alvo da Oposição no dia certo (mark_pct).
# Fatores medidos com evento 100, VIP 20, Cetro 30 e Kafra 50: 3,000; com 15% de itens 3,375; com Njord 4,875;
# com Milagre o dobro; com manual de 100% mais 1,0 antes de dobrar. VIP + Cetro e Kafra valem os mesmos 50
# pontos em quem foi medido, então qual dos dois fica em g é o mais provável (o Kafra é da família dos manuais),
# não medido. O bônus das missões é outra conta: quest_mult.
# Evento do servidor e outros não aparecem no replay: a pessoa marca. val=True: o % vem do status quando o
# jogo manda (Njord 60, manual 50...).
BONUSES = [
    dict(key="server", name="Evento do servidor", pct=100, status=None, on=False, role="g"),
    dict(key="vip", name="VIP (Bônus de EXP II, 30 dias)", pct=20, status=984, on=True, lasting=True, role="g"),
    dict(key="scepter", name="Cetro do Coração Lunar (Bônus de EXP, 24 h)", pct=30, status=939, on=True, lasting=True,
         role="g"),
    dict(key="kafra", name="Kafra Buff / Manual Kafra (7 dias)", pct=50, status=1085, on=True, lasting=True, role="p"),
    dict(key="manual", name="Manual de combate (consumível)", pct=50, status=250, on=True, group="consumível",
         lasting=True, val=True, role="p"),
    dict(key="njord", name="Banquete de Njord", pct=60, status=78, on=True, val=True, role="k"),
    dict(key="miracle", name="Milagre Solar, Lunar e Estelar (multiplica os outros bônus)", pct=100,
         status="milagre", on=True, role="first"),
    # spotlight: os monstros da lista do evento rendem mais (event_spots, com o % de cada um); para os de fora da
    # lista vale o mapa marcado (cfg xp_spot, à mão ou pelo automático), com o % do mapa. Multiplica tudo
    dict(key="spot", name="Monster Spotlight (lista do evento ou mapa marcado)", pct=20, status="mapa", on=True,
         val=True, role="spot"),
    dict(key="gear", name="Equipamentos, visuais e cartas (texto dos itens)", pct=0, status="equipamento", on=True,
         val=True, role="k"),
    # bônus "[Durante o Evento]" do texto dos itens (ex.: Carta Baby Shark): o evento do item costuma acabar antes
    # do item sair do jogo, então fica desligado até a pessoa marcar
    dict(key="gear_event", name="Bônus de evento dos itens ([Durante o Evento])", pct=0, status=None, on=False),
    dict(key="other", name="Outros (equipamentos, cartas, alvos do ódio...)", pct=0, status=None, on=False),
]
# manuais de XP (consumíveis; não acumulam entre si), com o bônus do texto do item na LATAM (Divine Pride)
MANUALS = [("Manual de Combate", 50), ("Manual de Combate com Chiclete", 50), ("Manual de Campo Avançado", 100),
           ("Enciclopédia de Combate", 200), ("Manual de Combate HE", 200), ("Manual de Combate x3", 300)]
# "auto" (padrão): a lista, com a correção medida assim que existir uma, e o evento do servidor deduzido da XP exata
MODES = ("auto", "lista", "medido", "fixo")
SERVER_CHOICES = (0, 50, 100, 200)   # o evento do servidor costuma ser +50%, +100% ou +200%
SERVER_FIT, SERVER_MISS = 0.06, 0.12  # o evento deduzido tem de fechar a 6% do real, e o marcado errar mais de 12%
SPOT_CHOICES = (20.0, 50.0)           # os que o jogo usa: +20% nos mapas de nível alto, +50% nos de nível mais baixo


# Monster Spotlight: os monstros da lista do evento rendem mais (+50% até o nível 212, +20% do 213 em diante), só
# eles: medido com a XP exata no Lago do Abismo 4, no Formigueiro e no Labirinto, onde o mapa todo × 1,5 dava 16% a
# 26% a mais que o real. data/spotlight.json traz a lista de cada período do evento (a imagem oficial).
def _spot_events():
    try:
        with open(os.path.join(_DATA, "spotlight.json"), encoding="utf-8") as f:
            raw = json.load(f).get("events", [])
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for ev in raw:
        try:
            start = datetime.date(*(int(x) for x in ev["from"].split("-")))
            end = datetime.date(*(int(x) for x in ev["to"].split("-")))
            out.append((start, end, {int(k): float(v) for k, v in ev["mobs"].items()}))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return out


SPOT_EVENTS = _spot_events()


def spot_event(c):
    """(início, fim, {monstro: %}) do Monster Spotlight que valia no dia da gravação, ou None."""
    try:
        day = datetime.date(*c.session.recorded_at[:3])
    except (TypeError, ValueError, AttributeError):
        return None
    for ev in SPOT_EVENTS:
        if ev[0] <= day <= ev[1]:
            return ev
    return None


def event_spots(c):
    """{monstro: %} da lista do Monster Spotlight que valia no dia da gravação, ou {}."""
    ev = spot_event(c)
    return ev[2] if ev else {}


def spot_kills(c, rng=None):
    """Abates de quem grava em monstros da lista do spotlight no recorte: {%: {nome: abates}}."""
    spots = event_spots(c)
    out = {}
    if spots:
        for r in kills(c, rng)[0]:
            pct = spots.get(r["mob"])
            if pct:
                names = out.setdefault(pct, {})
                names[r["name"]] = names.get(r["name"], 0) + 1
    return out


def map_key(name):
    """Nome do mapa sem o prefixo da instância ("0ex1@jorlab" -> "jorlab"), em minúsculas."""
    return (name or "").split("@")[-1].strip().lower()


def spot_maps(cfg):
    """{mapa: %} dos mapas marcados como spotlight (cfg xp_spot: {mapa: {"pct", "when", "auto"}})."""
    out = {}
    for name, entry in ((cfg or {}).get("xp_spot") or {}).items():
        pct = entry.get("pct") if isinstance(entry, dict) else None
        if isinstance(pct, (int, float)) and pct > 0:
            out[map_key(name)] = float(pct)
    return out


def settings(cfg, c=None):
    """{chave: {"on", "pct"}} dos bônus, com os padrões para o que a pessoa ainda não mexeu. Com `c`, o manual leva
    também "last": o % do último manual visto nesse personagem (para quando o manual já estava ativo no começo da
    gravação e o jogo não manda o valor)."""
    saved = cfg.get("xp_bonuses") or {}
    out = {}
    for b in BONUSES:
        st = saved.get(b["key"]) or {}
        pct = st.get("pct")
        out[b["key"]] = dict(on=bool(st.get("on", b["on"])), pct=float(pct) if isinstance(pct, (int, float)) else b["pct"])
    if c is not None:
        last = (cfg.get("xp_manual_last") or {}).get(str(c.session.gid))
        if isinstance(last, (int, float)) and last > 0:
            out["manual"]["last"] = float(last)
    return out


MAX_AGE_S = 24 * 3600         # o automático só mexe na configuração com gravação de até um dia (None = qualquer)


def _fresh(c):
    """A gravação é de agora (até um dia)? Abrir um replay antigo não pode mudar o evento do servidor de hoje."""
    if MAX_AGE_S is None:
        return True
    start = _seconds(c.session.recorded_at)
    if start is None:
        return False
    import time
    return time.time() - (start + c.now / 1000.0) <= MAX_AGE_S


def remember_manual(c, cfg):
    """Guarda o % do último manual que o jogo mandou para quem grava (cfg["xp_manual_last"]). True se mudou."""
    vals = [(s, v) for s, _e, v in _lasting_vals(c, 250) if v > 0]
    if not vals or not c.session.gid or not _fresh(c):
        return False
    pct = max(vals)[1]
    store = cfg.setdefault("xp_manual_last", {})
    if store.get(str(c.session.gid)) == pct:
        return False
    store[str(c.session.gid)] = pct
    return True


def _moment(c):
    """O que a gravação tem agora, para guardar contas enquanto nada muda (as janelas dos bônus, o começo do
    farm): várias partes da tela pedem a mesma conta no mesmo desenho."""
    m = _CACHE.get("m")
    sig = (c.version, c.now, len(c.status_log), len(c.status_on), len(getattr(c, "equip_log", ())), id(GEAR.table),
           tuple(tuple(x) for x in c.miracles), len(c.death_log), len(c.hits))
    if m is None or m["c"]() is not c or m["sig"] != sig:
        m = _CACHE["m"] = dict(c=weakref.ref(c), sig=sig, wins={}, fac={}, farm=(), est={}, evi=None)
    return m


def windows(c, cfg=None):
    """Quando cada bônus detectável esteve ativo em quem grava: {chave: [(início, fim, valor)]}.
    cfg: para saber se os bônus "[Durante o Evento]" dos itens estão marcados."""
    event_on = settings(cfg or {})["gear_event"]["on"]
    off = event_off(cfg or {})
    spots = tuple(sorted(spot_maps(cfg).items()))
    store = _moment(c)["wins"]
    out = store.get((event_on, off, spots))
    if out is None:
        out = store[(event_on, off, spots)] = _windows(c, event_on, off, dict(spots))
    return dict(out)


def _windows(c, event_on, off, spots=None):
    mine = {}                        # status de quem grava, por efeito (uma passada só pelo registro)
    for s in c.statuses(c.me):
        mine.setdefault(s[1], []).append(s)
    out = {}
    for b in BONUSES:
        if b["status"] is None:
            continue
        if b["status"] == "milagre":
            out[b["key"]] = [(s, e, 0) for s, e in c.miracle_windows()]
            continue
        if b["status"] == "equipamento":
            out[b["key"]] = gear_windows(c, event_on, off)
            continue
        if b["status"] == "mapa":     # o tempo passado em cada mapa marcado como spotlight, com o % dele
            out[b["key"]] = [(s, e, spots[map_key(m)]) for s, e, m in c.map_spans()
                             if map_key(m) in spots] if spots else []
            continue
        sts = mine.get(b["status"], ())
        if b.get("lasting") and b.get("val"):    # manuais: não acabam com a morte e trazem o % no status
            out[b["key"]] = _lasting_vals(c, b["status"], sts)
            continue
        if b.get("lasting"):          # bônus de conta/período não acabam com a morte
            out[b["key"]] = [(s, e, 0) for s, e in c.lasting(b["status"], sts)]
            continue
        out[b["key"]] = sorted((s, e, c.status_val.get((a, ef, s)) or 0) for a, ef, s, e in sts)
    return out


def _lasting_vals(c, efst, sts=None):
    """[(início, fim, valor)] de um status de quem grava que não acaba com a morte, com o valor que o jogo
    mandou (0 = não veio: o status já estava ativo quando a gravação começou). `sts`: os status de quem grava, se
    já estiverem à mão."""
    out = []
    for a, ef, st, e in (c.statuses(c.me) if sts is None else sts):
        if ef == efst:
            out.append((st, c.lasting_end(a, ef, st, e), c.status_val.get((a, ef, st)) or 0))
    return sorted(out)


def _pct_at(b, t, wins, sets):
    """% do bônus num instante, ou None se ele não conta (desmarcado ou o status não estava ativo)."""
    st = sets[b["key"]]
    if not st["on"]:
        return None
    if b["status"] is None:
        return st["pct"]
    hit = None
    for s, e, v in wins.get(b["key"], ()):     # janelas em ordem de início: vale a última que cobre t
        if s <= t <= e:
            hit = v
    if hit is None:
        return None
    if b.get("val") and hit > 0:               # Njord e manuais trazem o % no próprio status
        return hit
    return st.get("last") or st["pct"]         # sem o valor: o último manual visto no personagem, senão o digitado


def parts_at(t, wins, sets):
    """Bônus (%) de cada papel num instante: {"g", "k", "p", "first"}, com a regra dos consumíveis (vale o maior)."""
    out, group = {"g": 0.0, "k": 0.0, "p": 0.0, "first": 0.0, "spot": 0.0}, {}
    for b in BONUSES:
        pct = _pct_at(b, t, wins, sets)
        if pct is None:
            continue
        role = b.get("role", "p")
        if b.get("group"):
            group[(role, b["group"])] = max(group.get((role, b["group"]), 0.0), pct)
        else:
            out[role] += pct
    for (role, _name), pct in group.items():
        out[role] += pct
    return out


def bonus_at(t, wins, sets):
    """Soma simples dos bônus num instante (%), sem o Milagre. Só para mostrar: a conta de verdade é factor_at."""
    a = parts_at(t, wins, sets)
    return a["g"] + a["k"] + a["p"]


# Alvos da Oposição (Bênção Solar, Lunar e Estelar no nível 5): o Solar rende +50% nos dias pares do mês, o Lunar
# +50% nos ímpares e o Estelar +100% nos dias múltiplos de 5 (regra do rAthena; medido: Jeniffer marcada como Lunar
# rendeu ×1,5 no dia 11, e os alvos Solar e Estelar não renderam nada a mais). Com Milagre todo monstro dobra e a
# marca não soma. O replay só mostra a marca quando a pessoa usa a Oposição durante a gravação.
MARK_PCT = (50.0, 50.0, 100.0)


def marks_of(c):
    """(data e hora do começo da gravação, [(t, casa, id do monstro)]) dos alvos da Oposição vistos, ou None."""
    rows = sorted((0 if already else t, slot, mob) for t, slot, mob, already in getattr(c, "hate_marks", ()))
    if not rows:
        return None
    try:
        start = datetime.datetime(*c.session.recorded_at[:6])
    except (TypeError, ValueError):
        return None
    return start, rows


def mark_pct(marks, t, mob):
    """% do primeiro passo para um abate de `mob` em t pelo alvo da Oposição (0 se não é alvo ou não é o dia)."""
    if not marks or mob is None:
        return 0.0
    start, rows = marks
    cur = {}
    for when, slot, m in rows:
        if when <= t:
            cur[slot] = m
    day = (start + datetime.timedelta(milliseconds=t)).day
    ok = (day % 2 == 0, day % 2 == 1, day % 5 == 0)
    return max([MARK_PCT[s] for s in range(3) if cur.get(s) == mob and ok[s]] or [0.0])


def factor_at(t, wins, sets, mob=None, marks=None, parts=None, spots=None):
    """Fator de XP de um abate: [(1 + g) × (1 + k) + p] × (1 + primeiro passo) × (1 + spotlight). `mob` e `marks`
    (marks_of) entram para o alvo da Oposição, quando não há Milagre. `parts`: os bônus do instante, se já
    calculados. `spots` (event_spots): o monstro da lista do spotlight vale o % dele, no lugar do mapa marcado."""
    a = parts_at(t, wins, sets) if parts is None else parts
    first = a["first"] or mark_pct(marks, t, mob)
    spot = a.get("spot", 0.0)
    if spots and mob in spots and (sets.get("spot") or {}).get("on", True):
        spot = spots[mob]
    return (((1.0 + a["g"] / 100.0) * (1.0 + a["k"] / 100.0) + a["p"] / 100.0) * (1.0 + first / 100.0)
            * (1.0 + spot / 100.0))


class _Parts:
    """parts_at com memória. Entre duas mudanças de qualquer bônus (um começa ou acaba) as janelas que cobrem o
    instante são as mesmas, então o resultado também: numa sessão longa são milhares de abates para poucas dezenas
    de trechos."""

    def __init__(self, wins, sets):
        self.wins, self.sets, self.memo = wins, sets, {}
        self.starts = sorted(s for ws in wins.values() for s, _e, _v in ws)
        self.ends = sorted(e for ws in wins.values() for _s, e, _v in ws)

    def at(self, t):
        # quantas janelas já começaram e quantas já acabaram: isso fixa quais cobrem o instante
        key = (bisect.bisect_right(self.starts, t), bisect.bisect_left(self.ends, t))
        a = self.memo.get(key)
        if a is None:
            a = self.memo[key] = parts_at(t, self.wins, self.sets)
        return a


def _parts(c, cfg, wins, sets):
    store = _moment(c)["fac"]
    key = (settings(cfg or {})["gear_event"]["on"], event_off(cfg or {}), repr(sorted(sets.items())),
           repr(sorted(spot_maps(cfg).items())))
    p = store.get(key)
    if p is None:
        p = store[key] = _Parts(wins, sets)
    return p


def detected(c, cfg=None):
    """{chave: fração da gravação em que o bônus esteve ativo} dos detectáveis (0 = não apareceu)."""
    span = max(1, c.now)
    out = {}
    for key, ws in windows(c, cfg).items():
        merged = []                    # janelas que se sobrepõem (manual renovado) contam uma vez
        for s, e, _v in sorted(ws):
            s, e = max(0, s), min(e, c.now)
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            elif e > s:
                merged.append([s, e])
        out[key] = min(1.0, sum(e - s for s, e in merged) / float(span))
    return out


def factor(c, cfg):
    """(fator fixo ou None, origem, correção sobre a lista). None = pela lista de bônus, golpe a golpe.
    origem: ("lista", None) | ("medido", "nivel" ou nº de medidas) | ("fixo", bônus %)."""
    mode = cfg.get("xp_mode") if cfg.get("xp_mode") in MODES else "auto"
    if mode in ("auto", "medido"):
        corr, how = correction(c, cfg)
        if corr:
            return None, ("medido", how), corr
    if mode == "fixo" and isinstance(cfg.get("xp_fixed"), (int, float)):
        return (100.0 + cfg["xp_fixed"]) / 100.0, ("fixo", cfg["xp_fixed"]), 1.0
    # "auto" sem nenhuma medida ainda: vale a lista, mas a previsão é só aproximada (a tela diz isso)
    return None, ("auto" if mode == "auto" else "lista", None), 1.0


# XP das missões: o replay mostra a entrega (a missão sai da lista), não quanto ela rende. A recompensa sem bônus vem
# do que o programa aprendeu ao fechar um nível (learn_quests, cfg["xp_quests"]: o que o jogo pagou no LATAM) ou da
# tabela data/quest_exp.json (tools/build_quest_exp.py: o medido no LATAM, o RewardEXP do jogo e os scripts do
# rAthena). Ela entra na posição no nível e no tempo até o próximo (progress), não no ritmo dos abates nem na
# calibração (trecho com entrega não mede os abates: quest_in). Missão sem recompensa conhecida fica fora da conta e
# a tela avisa; as de espera ("[Espera] ...", CoolTimeQuest) saem da lista sem dar XP.
# Bônus da missão: (1 + manual + Kafra) × Njord × Milagre (o Milagre dobra tudo, missões também: o usuário, a
# confirmar num teste); sem evento do servidor, VIP, Cetro, itens nem spotlight. Fecha com o Jantar do Diabo capturado
# em 2026-11-11 (698.346.800 do iRO Wiki × 2,5 × 1,6 × 2 = 5.586.774.400, exato) e a 3% com três diárias de Hugel
# (×2,0). Fica abaixo nas da Sociedade de Monstros (um Ferreiro 96→97 recebeu ×3,1 a ×3,5: talvez o +50% das
# missões dos episódios 17.1, 17.2 e 18 do Black Friday) e o Mímico da mesma captura do Jantar pagou só ×4 (o Milagre
# não contou nele?). A recompensa aprendida de cada missão corrige o que a regra erra; errar para menos não traz o
# "já subiu" (a regra anterior, com evento, VIP e Cetro, dava em Hugel mais XP que o trecho inteiro rendeu).
QUEST_XP_ON = True
QUEST_LEARN_MIN = 0.25               # só aprende a XP de uma missão que pese pelo menos isso do trecho exato
QUEST_LEARN_BLIND = 0.67             # ...ou isto, quando os abates ainda não têm medida exata (a lista pode errar muito)
QUEST_RELEARN_FIT = 0.15             # missão já conhecida só é reaprendida se o medido errar mais que isso
# bônus anotados em cada entrega de missão no registro de aprendizado (o relatório junta e mostra quais valem)
QUEST_LOG_KEYS = ("server", "vip", "scepter", "kafra", "manual", "njord", "miracle", "gear")

_QUEST_DATA = None


def _quest_data():
    """({missão: XP sem bônus}, {missões de espera}, {espera que nasce numa entrega: dict(base, items={item: XP})})
    de data/quest_exp.json, lido uma vez."""
    global _QUEST_DATA
    if _QUEST_DATA is None:
        exp, wait, handin = {}, set(), {}
        try:
            with open(os.path.join(_DATA, "quest_exp.json"), encoding="utf-8") as f:
                d = json.load(f)
            exp = {int(k): int(v) for k, v in (d.get("exp") or {}).items()}
            wait = {int(q) for q in d.get("zero") or ()}
            for q, v in (d.get("handin") or {}).items():
                handin[int(q)] = dict(base=int(v["base"]),
                                      items={int(i): int(x) for i, x in (v.get("items") or {}).items()})
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            pass
        _QUEST_DATA = (exp, wait, handin)
    return _QUEST_DATA


HANDIN_ITEM_MS = 200          # o item entregue sai da bolsa no mesmo instante em que a espera nasce


def handins(c, rng=None):
    """Entregas que não fecham missão nenhuma: o jogo só abre uma espera e paga na hora (o Lanche do Diabo da Torre
    do Relógio: entregam-se 100 do item do dia e nasce "[Espera] Lanche do Diabo"). [(t, espera, item ou None)]; o
    item é o que saiu da bolsa no mesmo instante, se for um dos que a tabela conhece."""
    table = _quest_data()[2]
    out = []
    for t, q in getattr(c, "quests_added", ()):
        if q in table and (rng is None or rng[0] <= t <= rng[1]):
            items = table[q]["items"]
            item = next((i for tt, i, _n in getattr(c, "bag_out", ()) if abs(tt - t) <= HANDIN_ITEM_MS and i in items),
                        None)
            out.append((t, q, item))
    return out


def quest_wait(qid):
    """True se a missão é de espera: ela sai da lista quando a espera acaba, sem dar XP."""
    return qid in _quest_data()[1]


def quest_base(qid, cfg):
    """Recompensa da missão sem bônus: a aprendida ao fechar um nível, senão a da tabela; None se não se sabe (ou
    com QUEST_XP_ON desligado). A aprendida que é a XP do nível inteiro não vale (whole_level)."""
    if not QUEST_XP_ON:
        return None
    learned = ((cfg or {}).get("xp_quests") or {}).get(str(qid))
    if (isinstance(learned, dict) and isinstance(learned.get("base"), (int, float)) and learned["base"] > 0
            and not whole_level(learned.get("level"), learned["base"] * (learned.get("mult") or 1.0),
                                learned.get("mult"))):
        return float(learned["base"])
    exp = _quest_data()[0].get(qid)
    return float(exp) if exp else None


_LEVEL_NEEDS = {}


def whole_level(level, pay, mult):
    """True se `pay` (o que a missão teria pago numa entrega) é a XP inteira do nível `level` em alguma tabela, ou a
    metade, um terço... (a mesma missão entregue mais de uma vez no trecho): a medida não contou os abates do trecho.
    A 1.10.0 fazia isso depois de um Zerar no meio da gravação (os abates de antes sumiam): a missão ficava valendo o
    nível todo e o "já subiu" aparecia logo depois de cada entrega dela. Uma medida de verdade não dá isso: o nível
    que só missões fecharam termina na entrega que subiu o nível, e essa fica de fora (learn_quests)."""
    if not isinstance(level, int) or not pay or level <= 0:
        return False
    needs = _LEVEL_NEEDS.get(level)
    if needs is None:
        needs = {t.get(level) for t in _base_exp().values()} | {table_need(min(FOURTH_JOBS), level)}
        needs.discard(None)
        needs = _LEVEL_NEEDS[level] = tuple(needs)
    for k in range(1, 7):
        tol = 0.5 * (mult or 1.0) * k + 2             # a recompensa fica guardada arredondada, sem o multiplicador
        if any(abs(pay * k - n) <= tol for n in needs):
            return True
    return False


QUEST_ROLES = {"manual": "p", "kafra": "p", "njord": "k", "miracle": "first"}   # os bônus que valem na missão


def quest_mult(t, wins, sets):
    """Multiplicador da XP de missão num instante: (1 + manual + Kafra) × (1 + Njord) × (1 + Milagre)."""
    pct = {"p": 0.0, "k": 0.0, "first": 0.0}
    for b in BONUSES:
        role = QUEST_ROLES.get(b["key"])
        if role:
            v = _pct_at(b, t, wins, sets)
            if v is not None:
                pct[role] += v
    return (1.0 + pct["p"] / 100.0) * (1.0 + pct["k"] / 100.0) * (1.0 + pct["first"] / 100.0)


def quest_rows(c, cfg, rng=None, wins=None, sets=None):
    """Missões entregues por quem grava no recorte: [dict(t, quest, base, mult, xp)] (xp None = recompensa que o
    programa ainda não conhece). As de espera ficam de fora: a saída delas da lista não é uma entrega. As entregas
    sem missão (o lanche, ver handins) entram com handin=True e o item entregue (a recompensa depende dele)."""
    done = [(t, q) for t, q in getattr(c, "quests_done", ())
            if (rng is None or rng[0] <= t <= rng[1]) and not quest_wait(q)]
    hand = handins(c, rng)
    if not done and not hand:
        return []
    wins = windows(c, cfg) if wins is None else wins
    sets = settings(cfg, c) if sets is None else sets
    delivered = {q for _t, q in done}
    out = []
    for t, q in done:
        base = quest_base(q, cfg)
        if base and not _quest_partners(cfg, q) <= delivered:
            base = None                     # aprendida em grupo: só vale quando o grupo é entregue junto
        mult = quest_mult(t, wins, sets)
        out.append(dict(t=t, quest=q, base=base, mult=mult, xp=base * mult if base else None))
    if hand:
        table = _quest_data()[2]
        for t, q, item in hand:
            base = float(table[q]["items"].get(item, table[q]["base"])) if QUEST_XP_ON else None
            mult = quest_mult(t, wins, sets)
            out.append(dict(t=t, quest=q, base=base, mult=mult, xp=base * mult if base else None, item=item,
                            handin=True))
        out.sort(key=lambda r: r["t"])
    return out


def quests_uncounted(c, cfg=None):
    """Quantas missões foram entregues desde o último ponto exato (começo da gravação ou subida de nível) sem a
    XP entrar na conta. Enquanto houver alguma, o nível mostrado está abaixo do real e o tempo até o próximo nível,
    acima: a tela avisa."""
    an = anchors(c)
    since = an[-1][0] if an else 0
    return sum(1 for q in quest_rows(c, cfg or {}, (since, c.now))
               if q["xp"] is None and not _at_levelup(since, q["t"], len(an) > 1))


# o que da configuração entra na conta da estimativa (a guardada vale enquanto isto e a gravação não mudarem)
EST_KEYS = ("xp_mode", "xp_fixed", "xp_bonuses", "xp_corr", "xp_manual_last", "xp_spot", "xp_event_off", "xp_quests",
            "xp_levels")


def estimate(c, cfg, rng=None):
    """XP de base estimada no recorte: dict(xp (abates + missões), kill_xp, quest_xp, quests (quest_rows),
    quests_unknown, base, kills, unknown, factor (médio dos abates), source, per_hour, per_min, per_min_pct (% do
    nível por minuto; ritmo só dos abates), rows (com "total" de cada abate)).
    Guardada enquanto a gravação e a configuração não mudam: a aba XP pedia a mesma conta ~10 vezes por desenho.
    As linhas dos abates são as mesmas em toda conta, então a guardada regrava nelas os totais dela."""
    store = _moment(c)["est"]
    # o registro de aprendizado entra pela versão dele (predict usa as medidas de lá: "registro")
    key = (tuple(rng) if rng is not None else None, repr([(cfg or {}).get(k) for k in EST_KEYS]), QUEST_XP_ON,
           ((cfg or {}).get("xp_learn") or {}).get("rev"))
    hit = store.get(key)
    if hit is not None:
        res, totals = hit
        for r, t in zip(res["rows"], totals):
            r["total"] = t
        return dict(res)
    res = _estimate(c, cfg, rng)
    if len(store) > 32:
        store.clear()
    store[key] = (res, [r.get("total") for r in res["rows"]])
    return dict(res)


def _estimate(c, cfg, rng=None):
    rows, unknown = kills(c, rng)
    f, source, corr = factor(c, cfg)
    wins = sets = None
    if f is None:
        wins, sets, marks = windows(c, cfg), settings(cfg, c), marks_of(c)
        parts = _parts(c, cfg, wins, sets)
        spots = event_spots(c)
        kcorr = _kill_corrections(c, cfg, source, corr)    # cada abate com a correção do mapa em que aconteceu
    total = base = 0.0
    for r in rows:
        if r["xp"] is None:
            r["total"] = None
            continue
        k = f if f is not None else (factor_at(r["t"], wins, sets, r["mob"], marks, parts.at(r["t"]), spots)
                                     * kcorr(r["t"]))
        r["total"] = r["xp"] * k
        base += r["xp"]
        total += r["total"]
    quests = quest_rows(c, cfg, rng, wins, sets)
    quest_xp = sum(q["xp"] for q in quests if q["xp"])
    span = (rng[1] - rng[0]) if rng else c.now
    long_enough = span and span > 60000
    per_min = total * 60000.0 / span if long_enough else None
    nxt = c.session.next_exp
    pct_min = (100.0 * per_min / nxt) if per_min is not None and nxt else None
    return dict(xp=total + quest_xp, kill_xp=total, quest_xp=quest_xp, quests=quests,
                quests_unknown=sum(1 for q in quests if q["xp"] is None), base=base, kills=len(rows), unknown=unknown,
                factor=(total / base) if base else (f or 1.0),
                source=source, correction=corr, per_hour=per_min * 60 if per_min is not None else None, per_min=per_min,
                per_min_pct=pct_min, per_hour_pct=pct_min * 60 if pct_min is not None else None,
                pct=(100.0 * (total + quest_xp) / nxt) if nxt else None,
                kills_per_min=len(rows) * 60000.0 / span if long_enough else None, span=span, rows=rows)


SIM_KEYS = ("server", "vip", "scepter", "kafra", "manual", "njord", "gear", "miracle")


def sim_real(c, cfg, rng=None):
    """Como cada bônus valeu de verdade no recorte, para o simulador mostrar ao lado de cada um:
    {chave: dict(counted (entra na conta da lista?), cover (fração do recorte em que esteve ativo; None para o que
    o replay não mostra, como o evento do servidor), ms (por quanto tempo), pct (o % que valeu))}."""
    sets, wins = settings(cfg, c), windows(c, cfg)
    t0, t1 = rng if rng else (0, c.now)
    span = max(1, t1 - t0)
    out = {}
    for b in BONUSES:
        key = b["key"]
        if key not in SIM_KEYS:
            continue
        st = sets[key]
        if b["status"] is None:
            out[key] = dict(counted=bool(st["on"]), cover=None, ms=None, pct=float(st["pct"]))
            continue
        merged, val = [], 0.0
        for s, e, v in sorted(wins.get(key, ())):
            s, e = max(s, t0), min(e, t1)
            if e <= s:
                continue
            val = max(val, v or 0)
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        pct = val if (b.get("val") and val > 0) else (st.get("last") or st["pct"])
        active = min(span, sum(e - s for s, e in merged))
        out[key] = dict(counted=bool(st["on"]), cover=active / float(span), ms=active, pct=float(pct))
    return out


def _overridden(c, cfg, over):
    """(janelas, ajustes) dos bônus com os trocados no simulador: `over` {chave: ("on", %) o recorte inteiro com
    esse %, ou ("off",) desligado}; o resto como valeu na gravação."""
    wins, sets = dict(windows(c, cfg)), dict(settings(cfg, c))
    for b in BONUSES:
        o = (over or {}).get(b["key"]) if b["key"] in SIM_KEYS else None
        if not o:
            continue
        if o[0] == "off":
            sets[b["key"]] = dict(sets[b["key"]], on=False)
            continue
        st = dict(sets[b["key"]], on=True, pct=float(o[1]))
        st.pop("last", None)
        sets[b["key"]] = st
        if b["status"] is not None:               # ativo o recorte inteiro (o % vai na janela, quando o bônus o traz)
            wins[b["key"]] = [(-1, 10 ** 15, float(o[1]) if b.get("val") else 0)]
    return wins, sets


def simulate(c, cfg, rng, over):
    """A XP dos abates do recorte trocando alguns bônus. `over`: {chave: ("on", %) para valer o tempo todo com esse
    %, ou ("off",) para não valer}; o que não está em `over` vale como valeu na gravação (as mesmas janelas e
    valores da estimativa). Mesma fórmula e mesma correção medida da estimativa: sem nada em `over` o resultado é
    o da lista de bônus. Devolve dict(xp, base, factor, per_min, per_hour)."""
    rows, _unknown = kills(c, rng)
    _f, source, corr = factor(c, cfg)
    kcorr = _kill_corrections(c, cfg, source, corr)
    wins, sets = _overridden(c, cfg, over)
    marks = marks_of(c)
    parts = _Parts(wins, sets)
    spots = event_spots(c)
    total = base = 0.0
    for r in rows:
        if r["xp"] is None:
            continue
        total += r["xp"] * factor_at(r["t"], wins, sets, r["mob"], marks, parts.at(r["t"]), spots) * kcorr(r["t"])
        base += r["xp"]
    span = (rng[1] - rng[0]) if rng else c.now
    per_min = total * 60000.0 / span if span and span > 60000 else None
    return dict(xp=total if base else None, base=base, factor=(total / base) if base else None, per_min=per_min,
                per_hour=per_min * 60 if per_min is not None else None)


def timeline(c, cfg, rng=None, bucket_ms=60000):
    """XP estimada por minuto e acumulada (em % do nível quando o jogo mandou quanto falta):
    [(início do minuto, XP no minuto, XP acumulada)]."""
    est = estimate(c, cfg, rng)
    start = rng[0] if rng else 0
    end = rng[1] if rng else c.now
    n = max(1, int((end - start + bucket_ms - 1) // bucket_ms))
    buckets = [0.0] * n
    for r in est["rows"]:
        if r.get("total"):
            buckets[min(n - 1, max(0, int((r["t"] - start) // bucket_ms)))] += r["total"]
    for q in est["quests"]:                      # a entrega de missão entra no minuto em que aconteceu
        if q["xp"]:
            buckets[min(n - 1, max(0, int((q["t"] - start) // bucket_ms)))] += q["xp"]
    out, acc = [], 0.0
    for i, v in enumerate(buckets):
        acc += v
        out.append((start + i * bucket_ms, v, acc))
    return out, est


# --- bônus de XP dos equipamentos, visuais e cartas (texto do item no jogo instalado) ---------------------

EXP_LINE = re.compile(r"(?i)^EXP (?:obtida|adquirida|recebida) (?:por|ao derrotar) monstros \+(\d+)%( adicional)?\.?$")
_SLOTS = re.compile(r"\s*\[\d\]$")


def _norm(name):
    return " ".join(_SLOTS.sub("", name or "").lower().split())


def parse_gear(items):
    """{item: [(%, nomes do conjunto ou None, só durante o evento?)]} das descrições (iteminfo em português).
    Fica de fora o que depende de algo que o replay não mostra (raça do monstro, refino, chance...)."""
    out = {}
    for item, info in items.items():
        if not isinstance(item, int) or not isinstance(info, dict):
            continue
        desc = info.get("identifiedDescriptionName") or {}
        lines = [re.sub(r"\^[0-9a-fA-F]{6}", "", desc[k]).strip() for k in sorted(k for k in desc if isinstance(k, int))
                 if isinstance(desc[k], str)]
        if not any("EXP" in line for line in lines):
            continue
        event, group, collecting, entries = False, None, False, []
        for line in lines:
            if line.startswith("---"):
                event, group, collecting = False, None, False
            elif line == "-":
                group, collecting = None, False
            elif line.lower().startswith("[durante o evento]"):
                event = True
            elif line.lower() == "conjunto":
                group, collecting = [], True
            elif collecting and "%" not in line and "+" not in line and not line.endswith("."):
                group.append(line)
            else:
                collecting = False
                m = EXP_LINE.match(line)
                if m:
                    entries.append((int(m.group(1)), tuple(group) if group else None, event))
        if entries:
            out[item] = entries
    return out


class _Gear:
    """Tabela dos bônus dos itens, lida numa thread (o iteminfo leva ~1 s)."""

    def __init__(self):
        self.table, self.names, self.kinds, self._thread = None, {}, {}, None
        self.display = {}             # item -> nome que o jogo mostra (a lista para a busca do aviso de item)
        self.art = {}                 # item -> nome do arquivo da ilustração dele no data.grf

    def start(self, path):
        if self.table is not None or self._thread is not None or not path:
            return

        def run():
            try:
                # o resumo da lista de itens vem do disco enquanto o arquivo do jogo não mudar (gamecache): rodar
                # o iteminfo inteiro leva mais de 1 s de processamento, e a janela fica lenta enquanto isso
                import gamecache
                d = gamecache.items(path)
                self.names, self.display, self.art, self.kinds = d["names"], d["display"], d["art"], d["kinds"]
                self.table = d["table"]
            except (OSError, ValueError, IndexError, KeyError):
                self.table = {}
            finally:
                self._thread = None
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    @property
    def loading(self):
        return self._thread is not None


GEAR = _Gear()


def _iteminfo_path():
    try:
        import clientdata
        grf = clientdata.NAMES.grf
    except ImportError:
        grf = None
    return os.path.join(os.path.dirname(grf), "System", "iteminfo_new.lub") if grf else None


def gear_ready():
    """A lista de itens do jogo já carregou (ou não há jogo instalado)? Antes disso o bônus dos itens vestidos não
    entra na conta, e medir contra a XP exata daria o resultado errado."""
    path = _iteminfo_path()
    GEAR.start(path)
    return not path or GEAR.table is not None


def event_off(cfg):
    """Itens cujo bônus "[Durante o Evento]" a pessoa desmarcou (o evento daquele item já acabou)."""
    out = set()
    for i in cfg.get("xp_event_off") or []:
        try:
            out.add(int(i))
        except (TypeError, ValueError):
            pass
    return frozenset(out)


def event_items(c):
    """{item: %} dos itens com bônus "[Durante o Evento]" vestidos em algum momento da gravação (guardado enquanto a
    gravação não muda: percorre todas as trocas de equipamento, ~80 ms num replay grande)."""
    GEAR.start(_iteminfo_path())
    m = _moment(c)
    if m["evi"] is None:
        m["evi"] = _event_items(c)
    return dict(m["evi"])


def _event_items(c):
    table = GEAR.table or {}
    out = {}
    for _t, state in getattr(c, "equip_log", None) or []:
        for it in state.values():
            for i in [it.item_id] + [x for x in it.cards if x]:
                pct = sum(p for p, _g, ev in table.get(i, ()) if ev)
                if pct:
                    out[i] = pct
    return out


def gear_bonus(worn, event_on, table=None, names=None, event_off=frozenset()):
    """(% de XP dos itens vestidos, [itens que deram bônus]) para {bit do slot: Item}.
    event_off: itens cujo bônus de evento não conta mesmo com event_on."""
    table = GEAR.table if table is None else table
    names = GEAR.names if names is None else names
    if not table or not worn:
        return 0, []
    ids = set()
    for it in worn.values():
        ids.add(it.item_id)
        ids.update(c for c in it.cards if c)
    worn_names = {names.get(i) for i in ids}
    total, who = 0, []
    for i in sorted(ids):
        got = 0
        for pct, group, event in table.get(i, ()):
            if event and (not event_on or i in event_off):
                continue
            if group and not all(_norm(n) in worn_names for n in group):
                continue
            got += pct
        if got:
            total += got
            who.append(i)
    return total, who


def gear_windows(c, event_on, event_off=frozenset()):
    """[(início, fim, %)] do bônus dos itens vestidos. Trocas de equipamento seguidas que dão a mesma % viram uma
    janela só, e a % de cada troca é calculada uma vez (há quem troque de equipamento mais de mil vezes numa
    sessão: refazer tudo a cada abate deixava a conta da XP cada vez mais lenta)."""
    GEAR.start(_iteminfo_path())
    if GEAR.table is None:
        return []
    log = getattr(c, "equip_log", None) or [(0, {})]
    g = _CACHE.get("g")
    key = (event_on, event_off, id(GEAR.table))
    if (g is None or g["c"]() is not c or g["first"] is not log[0] or g["key"] != key
            or len(g["pct"]) > len(log)):
        g = _CACHE["g"] = dict(c=weakref.ref(c), first=log[0], key=key, pct=[])
    pcts = g["pct"]
    for i in range(len(pcts), len(log)):
        pcts.append(gear_bonus(log[i][1], event_on, event_off=event_off)[0])
    out = []
    for i, (t, _state) in enumerate(log):
        pct = pcts[i]
        if not pct:
            continue
        end = log[i + 1][0] if i + 1 < len(log) else max(c.now, t)
        if out and out[-1][1] == t and out[-1][2] == pct:
            out[-1] = (out[-1][0], end, pct)
        else:
            out.append((t, end, pct))
    return out



def recordings_before(path, session, limit=20):
    """Gravações anteriores do mesmo personagem na mesma pasta, da mais nova para a mais velha:
    [{"path", "when"}]."""
    import meter
    if not path or not session.gid:
        return []
    folder = os.path.dirname(path)
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    out = []
    for name in names:
        p = os.path.join(folder, name)
        if not name.lower().endswith(".rrf") or os.path.normcase(p) == os.path.normcase(path):
            continue
        info = meter._xp_info(p)
        if info and info[0] == session.gid and info[1] < session.recorded_at:
            out.append(dict(path=p, when=info[1]))
    out.sort(key=lambda r: r["when"], reverse=True)
    return out[:limit]


def summary(c, cfg, rng=None):
    """Números para comparar duas gravações: duração, XP (total, por minuto e por hora, em % do nível quando dá),
    abates, abates por minuto e fator."""
    est = estimate(c, cfg, rng)
    return dict(span=est["span"], xp=est["xp"], pct=est["pct"], per_min=est["per_min"],
                per_min_pct=est["per_min_pct"], per_hour=est["per_hour"], per_hour_pct=est["per_hour_pct"],
                kills=est["kills"], kills_per_min=est["kills_per_min"], factor=est["factor"],
                level=c.session.base_level, unknown=est["unknown"])


def progress(c, cfg, t=None):
    """Onde quem grava está no nível no instante t (agora): dict(level, xp, need, pct, since) ou None. Parte do
    último ponto exato (começo da gravação ou a última subida de nível) mais a XP estimada desde então."""
    t = c.now if t is None else t
    an = [a for a in anchors(c) if a[0] <= t]
    up = len(an) > 1                    # o último ponto exato é uma subida de nível
    kept = getattr(c, "reset_level", None)
    if kept is not None and kept[0] <= t and (not an or an[-1][0] < kept[0]):
        an.append(kept)                 # o Zerar apagou os abates de antes: parte de onde estava no nível (keep_level)
        up = False
    if not an:
        return None
    ta, lv, x0 = an[-1]
    nd = need(c, cfg, lv)
    xpv = x0
    if t > ta:
        est = estimate(c, cfg, (ta, t))
        # a entrega no instante da subida foi o que subiu: a XP dela é do nível que fechou, não deste
        xpv += est["xp"] - sum(q["xp"] for q in est["quests"] if q["xp"] and _at_levelup(ta, q["t"], up))
    lost, deaths = death_loss(c, cfg, ta, x0, lv, t)       # morte sem seguro: −5% do nível cada
    xpv = max(0.0, xpv - lost)
    return dict(level=lv, xp=xpv, need=nd, pct=(100.0 * xpv / nd) if nd else None, since=ta, lost=lost,
                deaths=deaths)


def keep_level(c, cfg):
    """Antes do Zerar, que apaga os abates: guarda onde quem grava está no nível agora (progress usa isso como ponto
    de partida, senão a posição no nível voltava para trás). As medidas com XP exata deixam de fora o trecho cortado
    (level_segments, exact_segments)."""
    if not c.death_log:
        return
    pr = progress(c, cfg)
    if pr is not None:
        c.reset_level = (c.now, pr["level"], pr["xp"])


def death_note(c, cfg):
    """(mortes sem seguro desde o último ponto exato, % do nível que elas tiraram) ou None, para o aviso."""
    pr = progress(c, cfg)
    if not pr or not pr.get("deaths") or not pr.get("need"):
        return None
    return pr["deaths"], 100.0 * pr["lost"] / pr["need"]


def hunts(c):
    """Missões de caça em andamento de quem grava: [dict(quest, parts=[(contagem, meta)], count, goal)], da mais
    mexida para a menos (o jogo manda o progresso a cada abate que conta)."""
    out = []
    for quest, idents in getattr(c, "quest_hunts", {}).items():
        parts = [(cnt, goal) for _i, (cnt, goal, _t) in sorted(idents.items())]
        if parts:
            out.append(dict(quest=quest, parts=parts, count=sum(p[0] for p in parts), goal=sum(p[1] for p in parts),
                            t=max(t for _c, _g, t in idents.values())))
    out.sort(key=lambda r: -r["t"])
    return out


def farm_start(c):
    """Quando o farm começou de verdade: o começo do 1º minuto que rendeu pelo menos 40% do melhor minuto até agora
    (os primeiros minutos costumam ser preparação: buffs, ir até o mapa, alguns abates no caminho). None sem abates."""
    m = _moment(c)
    if not m["farm"]:
        m["farm"] = (_farm_start(c),)
    return m["farm"][0]


def _farm_start(c):
    rows = [r for r in kills(c)[0] if r["t"] <= c.now and r["xp"]]
    if not rows:
        return None
    mins = {}
    for r in rows:
        mins[r["t"] // 60000] = mins.get(r["t"] // 60000, 0.0) + r["xp"]
    best = max(mins.values())
    first = min(m for m, v in mins.items() if v >= FARM_FRAC * best)
    return max(rows[0]["t"], first * 60000)


def no_known_xp(c):
    """Há abates, mas nenhum que renda XP pela base do programa (monstros que ela ainda não tem, ou que não dão
    XP): a previsão não tem como sair do "calculando"."""
    rows, _unknown = kills(c)
    return bool(rows) and not any(r["xp"] for r in rows)


def warming_up(c, cfg):
    """True enquanto a previsão ainda não vale: menos de 10 min de farm e menos de 1% do nível ganho. Gravação que
    continua a anterior (carry_from) conta o farm do fim dela: reiniciar para calibrar não volta ao "calculando…"."""
    k = carry(c)
    if k is not None and k["warm"]:
        return False
    start = farm_start(c)
    if start is None and not (k and k["rows"]):
        return True
    farm = (c.now - start) if start is not None else 0
    if farm + (k["farm_ms"] if k else 0) >= WARMUP_MS:
        return False
    nd = need(c, cfg, c.session.base_level) if c.session.base_level else None
    got = (estimate(c, cfg, (0, c.now))["kill_xp"] if start is not None else 0.0) + (k["farm_xp"] if k else 0.0)
    return not (nd and got >= WARMUP_FRAC * nd)


def recent_parts(c, cfg):
    """O trecho que dá o ritmo recente: os últimos 10 min de farm (contando do começo do farm, não da gravação).
    (recorte desta gravação ou None, XP dos abates do fim da gravação anterior que completam os 10 min, tempo de
    caça deles), ou None enquanto aquece (warming_up). Sem gravação anterior ligada (carry_from): (recorte, 0, 0)."""
    if warming_up(c, cfg):
        return None
    start = farm_start(c)
    own = min(PACE_MS, c.now - start) if start is not None else 0
    rng = (c.now - own, c.now) if own > 0 else None
    k = carry(c)
    rest = PACE_MS - own
    rows = [(t, x) for t, x in k["rows"] if t >= -rest] if k is not None and rest > 0 else []
    if not rows:
        return (rng, 0.0, 0.0) if rng else None
    return rng, sum(x for _t, x in rows), _active_of(sorted(t for t, _x in rows), -rest, 0)


def recent_range(c, cfg):
    """O recorte desta gravação no ritmo recente (recent_parts), ou None."""
    parts = recent_parts(c, cfg)
    return parts[0] if parts else None


def recent_pace(c, cfg):
    """XP por minuto de caça no trecho recente (recent_parts), ou None enquanto aquece."""
    parts = recent_parts(c, cfg)
    if parts is None:
        return None
    rng, more, more_ms = parts
    got = estimate(c, cfg, rng)["kill_xp"] if rng else 0.0      # ritmo só dos abates
    ms = (active_ms(c, rng) if rng else 0.0) + more_ms
    rate = (got + more) * 60000.0 / ms if ms > 0 else 0.0
    return rate if rate > 0 else None


# Reiniciar a gravação (para calibrar) não zera o ritmo do "Até o próximo nível": a gravação que começa até 1 min
# depois do fim da anterior, do mesmo personagem, guarda os abates dos últimos 10 min de farm dela (só o tempo e a
# XP de cada um: a gravação anterior não fica presa na memória). O widget liga as duas quando passa de uma para a
# outra, e de novo quando mede a XP da anterior (a correção pode ter mudado com a medida).
CARRY_GAP_S = CALIBRATE_GAP_S


def carry(c):
    """O fim da gravação anterior que esta continua (carry_from): dict(rows [(ms antes do fim dela, XP)], farm_ms,
    farm_xp, warm (ela já tinha passado do aquecimento), gap (s entre as duas)), ou None."""
    return getattr(c, "carry", None)


def carry_from(c, prev, cfg):
    """Liga a gravação `c` à `prev` se `c` começou até 1 min depois do fim de `prev` (mesmo personagem). True se
    ligou. Abre uma gravação velha no meio (ou de outro personagem) e nada muda."""
    if c is None or prev is None or c is prev:
        return False
    s, p = c.session, prev.session
    if not s.gid or s.gid != p.gid:
        return False
    start, before = _seconds(s.recorded_at), _seconds(p.recorded_at)
    if start is None or before is None or start <= before:
        return False
    gap = start - (before + prev.now / 1000.0)
    if gap > CARRY_GAP_S:
        return False
    fs = farm_start(prev)
    rows, farm_ms, farm_xp = [], 0.0, 0.0
    if fs is not None:
        est = estimate(prev, cfg, (fs, prev.now))
        farm_ms, farm_xp = float(prev.now - fs), est["kill_xp"]
        rows = sorted((r["t"] - prev.now, r.get("total") or 0.0) for r in est["rows"] if r["t"] >= prev.now - PACE_MS)
    old = carry(prev)
    if old is not None and farm_ms < PACE_MS:
        # a anterior também continuava outra (reiniciou duas vezes seguidas): os abates de lá completam os 10 min
        # (o intervalo entre as gravações fica de fora do tempo de caça pela regra das pausas)
        rows = [(t - prev.now, x) for t, x in old["rows"] if t - prev.now >= -PACE_MS] + rows
        farm_ms += old["farm_ms"]
        farm_xp += old["farm_xp"]
    c.carry = dict(rows=rows, farm_ms=farm_ms, farm_xp=farm_xp, warm=not warming_up(prev, cfg), gap=gap)
    return True


# O ritmo do "Até o próximo nível" conta só o tempo caçando: o intervalo entre abates que passa de 30 s (ou de 3× o
# intervalo típico do trecho, numa caça lenta) é pausa e sai da conta (ir à cidade, trocar de mapa, esperar buff).
# Medido nas gravações de leveling de dois jogadores (2026-11-19): com o tempo todo, a previsão saía longa demais
# (mediana do erro 22% e 30%, os 20% piores acima de 49% e 101%); só com o tempo caçando, 20% e 27% (44% e 67%).
IDLE_GAP_MS = 30000
IDLE_TYPICAL = 3


def active_ms(c, rng):
    """Quanto do recorte foi caça: o recorte menos a parte de cada intervalo sem abate (contando as pontas) que passa
    do limite de pausa. Nunca menos que 1 min (ou o recorte, se for menor): dois abates seguidos não viram um ritmo."""
    t0, t1 = rng
    return _active_of(sorted(r["t"] for r in kills(c, rng)[0]), t0, t1)


def _active_of(times, t0, t1):
    """active_ms de uma lista ordenada de tempos de abate no recorte (t0, t1)."""
    inner = [b - a for a, b in zip(times, times[1:])]
    limit = max(IDLE_GAP_MS, IDLE_TYPICAL * statistics.median(inner)) if inner else IDLE_GAP_MS
    edges = [t0] + times + [t1]
    idle = sum(g - limit for g in (b - a for a, b in zip(edges, edges[1:])) if g > limit)
    span = t1 - t0
    return max(span - idle, min(span, 60000))


def time_to_level(c, cfg, per_min=None):
    """(ms até o próximo nível, XP que falta) ou (None, None). Usa a posição no nível (progress) e o ritmo dos
    últimos minutos (ou `per_min`, se vier); 0 se a estimativa já passou do nível."""
    pr = progress(c, cfg)
    rate = per_min or recent_pace(c, cfg)
    if pr is None or not pr["need"] or not rate or rate <= 0:
        return None, None
    left = pr["need"] - pr["xp"]
    if left <= 0:
        return 0, 0
    return left / rate * 60000.0, left


def span_text(ms):
    """Duração longa em palavras: "45 min", "3 h 20 min", "4 dias 6 h"."""
    from i18n import _
    minutes = int(ms // 60000)
    if minutes < 60:
        return _("%d min") % max(1, minutes)
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return _("%d h %02d min") % (hours, minutes)
    days, hours = divmod(hours, 24)
    return _("%d dias %d h") % (days, hours)


# --- simulador: "e se eu caçasse no mapa X?" -----------------------------------------------------------------------
#
# A mistura de monstros de um mapa vem dos abates da própria pessoa nele (o registro de aprendizado guarda, por
# gravação, quantos de cada monstro ela matou em cada mapa: é o que ela caça de verdade) ou, sem isso, de quantos
# nascem de cada um (data/map_spawns.json: a lista do /navi do jogo, com os mapas novos do LATAM; o rAthena só nos
# que o /navi não tem). A conta troca cada abate do recorte por um abate "médio" do mapa X, no mesmo instante (os
# bônus de cada momento valem igual: Njord, Milagre, manual...), com a penalidade de nível de cada monstro de X, o
# spotlight deles e a correção medida em X.

MAP_MIX_MIN = 30              # abates num mapa para a mistura da pessoa valer no lugar da do /navi
MAP_MIX_RECS = 20             # gravações guardadas por mapa no registro
LEARN_MAPS = 300              # mapas guardados no registro
MAP_MIX_PASS = 10             # menos abates que isto numa gravação: só passou pelo mapa (não entra)
MAP_LEVEL_SHARE = 0.05        # a faixa de nível de um mapa: só os monstros com pelo menos isto da mistura
_SPAWNS = None
_SPAWN_SRC = {}               # mapa -> "jogo" (o /navi do cliente do LATAM) | "rathena" (os que o /navi não tem)
_MAP_NAMES = {}               # mapa -> o nome dele no /navi
_NAVI_LEVELS = {}             # monstro -> o nível dele no /navi do LATAM


def spawn_table():
    """{mapa: [(monstro, quantos nascem)]} de data/map_spawns.json, lido uma vez: os do /navi do jogo ("maps") e os
    que só o rAthena tem ("rathena")."""
    global _SPAWNS
    if _SPAWNS is None:
        _SPAWNS = {}
        try:
            with open(os.path.join(_DATA, "map_spawns.json"), encoding="utf-8") as f:
                data = json.load(f)
            for key, source in (("maps", "jogo"), ("rathena", "rathena")):
                for m, mobs in (data.get(key) or {}).items():
                    if m not in _SPAWNS:
                        _SPAWNS[m] = [(int(mob), int(n)) for mob, n in mobs]
                        _SPAWN_SRC[m] = source
            _MAP_NAMES.update({str(m): str(n) for m, n in (data.get("names") or {}).items()})
            _NAVI_LEVELS.update({int(m): int(v) for m, v in (data.get("levels") or {}).items()})
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    return _SPAWNS


def latam_level(mob):
    """O nível do monstro no LATAM (o /navi do jogo), ou None."""
    spawn_table()
    return _NAVI_LEVELS.get(mob)


def map_title(mapname):
    """O nome do mapa no /navi do jogo ("" se não tiver)."""
    spawn_table()
    return _MAP_NAMES.get(map_key(mapname), "")


def _huntable(mix):
    """A parte da mistura que conta: monstros com XP conhecida, sem as plantas e os cogumelos (XP quase nada, ninguém
    caça). {monstro: peso}"""
    known = {m: w for m, w in mix.items() if MOB_EXP.get(m)}
    top = max((MOB_EXP[m][1] for m in known), default=0)
    return {m: w for m, w in known.items() if MOB_EXP[m][1] > 0 and MOB_EXP[m][1] >= 0.01 * top}


FOREIGN_SHARE = 0.3       # parte da mistura com outro nível no LATAM a partir da qual o mapa é "de outra versão"
_FOREIGN = {}
# A Biosfera de Varmundt (bl_grass, bl_lava, bl_ice, bl_death; os monstros "[Eco]" 21548 a 21578): no LATAM ela é a
# versão de antes da reforma coreana de 17/08/2022 (níveis 245 a 251 no /navi do jogo, uns 3M de HP); a nossa tabela
# é a coreana de depois dela (níveis 252 a 255, 21 a 31M de HP, XP "muito maior que antes" pela nota da Gravity).
# Medido no LATAM (RagnarokReplay_0004 → mtk farm, bl_lava, 24/10/2026, 17 abates sozinho em 63 s): a XP real foi
# 11 a 17% da lista com os bônus (conforme o evento do servidor daquele dia, que o replay não mostra). Só para o
# simulador explicar: a tabela não muda; uma caçada medida no mapa é que corrige (predict).
BIO_MOBS = range(21548, 21579)
BIO_LATAM = (0.11, 0.17)


def latam_other(mix):
    """Os monstros da mistura que contam (_huntable) com outro nível no LATAM (o /navi do jogo) que na nossa tabela de
    XP, que é a coreana: ([(monstro, nível da tabela, nível no LATAM)], parte deles na mistura de 0 a 1)."""
    known = _huntable(mix or {})
    wsum = float(sum(known.values()))
    other = [(m, MOB_EXP[m][0], latam_level(m)) for m in known
             if latam_level(m) and latam_level(m) != MOB_EXP[m][0]]
    return other, (sum(known[m] for m, _a, _b in other) / wsum if other and wsum else 0.0)


def foreign_map(mapname):
    """True se no LATAM o mapa é de outra versão que a da nossa tabela de XP: FOREIGN_SHARE ou mais da mistura dele
    (a do /navi do jogo) tem outro nível lá — a Biosfera (BIO_MOBS), algumas Ilusões. A XP medida num mapa assim vale
    só para ele: fica fora do "normal" do personagem (_baseline), da média geral e da comparação entre mapas que
    separa o spotlight do evento do servidor; e um trecho nele não decide o evento do servidor."""
    m = map_key(mapname or "")
    got = _FOREIGN.get(m)
    if got is None:
        spawns = spawn_table().get(m) if m else None
        got = _FOREIGN[m] = bool(spawns) and latam_other(dict(spawns))[1] >= FOREIGN_SHARE
    return got


def _foreign_in(c, t0, t1):
    """True se o trecho passou por algum mapa de outra versão (foreign_map)."""
    return any(foreign_map(m) for s, e, m in c.map_spans() if s < t1 and e > t0)


def map_levels(mix):
    """(nível médio, menor, maior) dos monstros que contam na mistura de um mapa (a média pelo peso de cada um; a
    faixa sem os raros), ou None."""
    hunt = _huntable(mix or {})
    wsum = float(sum(hunt.values()))
    if not wsum:
        return None
    avg = sum(MOB_EXP[m][0] * w for m, w in hunt.items()) / wsum
    main = [MOB_EXP[m][0] for m, w in hunt.items() if w >= MAP_LEVEL_SHARE * wsum] or [MOB_EXP[m][0] for m in hunt]
    return avg, min(main), max(main)


def log_map_mix(lrn, c, name, when):
    """Guarda no registro quantos de cada monstro quem grava matou em cada mapa nesta gravação (a mesma gravação lida
    de novo troca a anotação)."""
    spans = sorted(c.map_spans())
    starts = [s for s, _e, _m in spans]
    per = {}
    for r in kills(c)[0]:
        i = bisect.bisect_right(starts, r["t"]) - 1
        m = map_key(spans[i][2]) if i >= 0 else map_key(c.session.map)
        if m:
            mobs = per.setdefault(m, {})
            mobs[str(r["mob"])] = mobs.get(str(r["mob"]), 0) + 1
    maps = lrn.setdefault("maps", {})
    for m, mobs in per.items():
        if sum(mobs.values()) < MAP_MIX_PASS:
            continue
        e = maps.setdefault(m, dict(recs={}))
        e.setdefault("recs", {})[name] = mobs
        e["last"] = when[:10]
        if len(e["recs"]) > MAP_MIX_RECS:
            e["recs"] = dict(list(e["recs"].items())[-MAP_MIX_RECS:])
    if len(maps) > LEARN_MAPS:
        lrn["maps"] = dict(sorted(maps.items(), key=lambda kv: str(kv[1].get("last") or ""))[-LEARN_MAPS:])


def map_mix(cfg, mapname):
    """(mistura {monstro: peso}, origem "seus" | "jogo" | "rathena") do mapa, ou (None, None) se não se sabe."""
    m = map_key(mapname)
    own = {}
    entry = (((cfg or {}).get("xp_learn") or {}).get("maps") or {}).get(m) or {}
    for mobs in (entry.get("recs") or {}).values():
        for mob, n in (mobs or {}).items():
            try:
                own[int(mob)] = own.get(int(mob), 0) + int(n)
            except (TypeError, ValueError):
                continue
    if sum(own.values()) >= MAP_MIX_MIN:
        return own, "seus"
    spawns = spawn_table().get(m)
    if spawns:
        return dict(spawns), _SPAWN_SRC.get(m, "jogo")
    return None, None


def sim_maps(cfg, level=None):
    """Os mapas que dá para simular: [(mapa, origem, abates seus, (nível médio, menor, maior) ou None)]. Com `level`
    (o de quem gravou), primeiro os de monstros de nível mais perto do dele; sem, primeiro os que a pessoa caçou."""
    own = {}
    for m, e in ((((cfg or {}).get("xp_learn") or {}).get("maps")) or {}).items():
        n = sum(sum(v.values()) for v in (e.get("recs") or {}).values() if isinstance(v, dict))
        if n >= MAP_MIX_MIN:
            own[m] = n
    out = []
    for m in set(own) | set(spawn_table()):
        mix, source = map_mix(cfg, m)
        if mix:
            out.append((m, source, own.get(m, 0), map_levels(mix)))
    if level:
        out.sort(key=lambda r: (r[3] is None, abs(r[3][0] - level) if r[3] else 0, -r[2], r[0]))
    else:
        out.sort(key=lambda r: (r[1] != "seus", -r[2], r[0]))
    return out


def sim_map(c, cfg, rng, mapname, over=None):
    """A XP do recorte se cada abate dele (o mesmo número, nos mesmos instantes) fosse num monstro do mapa
    `mapname`, na proporção da mistura do mapa; `over`: os bônus trocados no simulador (como em simulate).
    dict(xp, base_xp (o recorte como foi, pela mesma conta), kills, per_kill, per_min, per_hour, source, corr,
    mobs=[dict(mob, name, lv, share (da mistura), pen, per_kill)], unknown (parte da mistura sem XP conhecida)) ou
    None (mapa sem mistura ou recorte sem abates)."""
    mix, source = map_mix(cfg, mapname)
    rows, _unk = kills(c, rng)
    if not mix or not rows:
        return None
    total_w = float(sum(mix.values()))
    unknown = 1.0 - sum(w for m, w in mix.items() if MOB_EXP.get(m)) / total_w if total_w else 1.0
    known = _huntable(mix)        # plantas e cogumelos (XP quase nada) ninguém caça: ficam de fora da média
    wsum = float(sum(known.values()))
    if not wsum:
        return None
    f, source_f, corr = factor(c, cfg)
    mode = cfg.get("xp_mode") if cfg.get("xp_mode") in MODES else "auto"
    p = predict(cfg, c.session.gid, mapname) if mode in ("auto", "medido") and f is None else None
    corr_x = p[0] if p else corr
    wins = sets = marks = parts = spots = None
    if f is None:
        if over:
            wins, sets = _overridden(c, cfg, over)
            parts = _Parts(wins, sets)
        else:
            wins, sets = windows(c, cfg), settings(cfg, c)
            parts = _parts(c, cfg, wins, sets)
        marks, spots = marks_of(c), event_spots(c)
    spot_x = spot_maps(cfg).get(map_key(mapname), 0.0)
    total = 0.0
    per_mob = {m: 0.0 for m in known}
    for r in rows:
        lv = level_at(c, r["t"])
        share = r["share"]
        if f is None:
            a = dict(parts.at(r["t"]), spot=spot_x)       # o spotlight é o do mapa X, não o do mapa de verdade
        for m, w in known.items():
            data = MOB_EXP[m]
            pen = penalty(data[0] - lv)
            k = f if f is not None else factor_at(r["t"], wins, sets, m, marks, a, spots) * corr_x
            v = (data[1] * pen // 100) * share * k
            per_mob[m] += v
            total += v * w / wsum
    n = len(rows)
    span = (rng[1] - rng[0]) if rng else c.now
    per_min = total * 60000.0 / span if span and span > 60000 else None
    base = estimate(c, cfg, rng)["kill_xp"]
    level = level_at(c, rng[1] if rng else c.now)
    from i18n import _
    mobs = [dict(mob=m, name=meter_name(m) or _("Monstro %d") % m, lv=MOB_EXP[m][0], share=w / wsum,
                 pen=penalty(MOB_EXP[m][0] - level), per_kill=per_mob[m] / n)
            for m, w in sorted(known.items(), key=lambda kv: -kv[1])]
    # monstros que no LATAM têm outro nível (o /navi do jogo) que o da nossa tabela de XP: lá eles são de outra versão
    # (a Biosfera, algumas Ilusões), e a XP da tabela pode não bater com a do LATAM
    other, share = latam_other(mix)
    return dict(xp=total, base_xp=base, kills=n, per_kill=total / n, per_min=per_min,
                per_hour=per_min * 60 if per_min is not None else None, source=source, corr=corr_x,
                mobs=mobs, unknown=unknown, map=map_key(mapname), latam_other=other,
                measured=bool(p and p[1] in MEASURED), latam_share=share,
                bio_share=sum(w for m, w in known.items() if m in BIO_MOBS) / wsum)
