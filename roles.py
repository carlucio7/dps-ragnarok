# -*- coding: utf-8 -*-
"""Os cartões de classe e de papel do resumo da sessão: o que quem grava fez pelo grupo, medido no replay.

Os limites saíram das 311 gravações daqui (as do usuário e as dos amigos, 2026-11-22):
- Redenção: o dano dos aliados protegidos chega como um golpe de quem usou nele mesmo (skill 0); num Betelgeuse
  o Guardião Imperial absorveu 420M (mil vezes a vida dele); passou de 10 vidas em 6 das 32 gravações com Redenção.
- Lex Aeterna: nas 66 lutas de chefe com um Cardeal, a média ficou em 0,2 por segundo; o pico de 10 s passou de
  2 por segundo em 8 delas (a sugestão do usuário: "mais de duas por segundo durante luta importante").
- "Oi, tchau": o maior grupo de abates da mesma skill em 1 s passou de 20 em 7 de ~670 jogadores-gravação (todas do
  Mestre Celestial do usuário, com a Explosão Galáctica); o Magus de um amigo chegou a 18 com a Cascata de Cristal.
- Dano creditado: o que os efeitos de quem grava renderam nos golpes do grupo (contrib.credit); 30% ou mais do dano
  da luta em ~13% das lutas (o Pólen do Magus em ~1/4 das dele, a Lex do Cardeal, a Garra Sombria do Executor).
- Buffs de grupo: o buff que um sacerdote põe no grupo chega como um uso de cada membro nele mesmo (o Mestre
  Celestial "usava" 141 rodadas de Clementia); o de quem lançou vem logo depois do pacote de conjuração dele (em
  todos os 965 buffs do Cardeal do usuário, até 35 ms depois), e o de outro sacerdote não. "Podem ir" na caçada: os
  Cardeais dos amigos fizeram de 0,3 a 1,9 rodadas de 5 buffs ou mais por minuto.
- KS: outro jogador de fora do grupo começou o monstro pelo menos 1 s antes e deu 10% do dano ou mais, e quem
  grava deu o golpe que matou: 20 ou mais numa gravação em 11 das 311 (as caçadas cheias de jor_ab02 e clock_01).
- MVP: o aviso de quem ganhou (0x010c). Nas 70 vezes em que quem grava ganhou, os outros tinham dado no máximo 6,6%
  do dano antes do primeiro golpe dele: ganhar chegando depois, com o prato servido, é raro.
- Item de cura que acabou: o Elixir Dourado (110 mil usos nas gravações) acabou uma vez no meio da caçada; os que
  "acabam" a cada uso (a Ancilla, feita e bebida na hora) ficam de fora.
"""

import bisect
import collections

import meter

REDEMPTION = 255              # Redenção (Devotion)
LEX_SKILLS = (78, 5072)       # Lex Aeterna e Vituperatum
RES_SKILLS = (54,)            # Ressuscitar
LEX_WINDOW_MS = 10000         # o pico da Lex: os usos em 10 s
MULTI_WINDOW_MS = 1000        # o "Oi, tchau": abates da mesma skill em 1 s
KILL_BLOW_MS = 3000           # o golpe que matou: o último de quem grava até isso antes da morte
RES_CONFIRM_MS = 3000         # a ressurreição chegou até isso depois do uso
MAX_FIGHTS = 4                # lutas de chefe olhadas (as de mais dano)
CAST_SLACK_MS = 500           # o buff de quem lançou chega até isso depois do fim da conjuração dele
# buffs que os outros jogadores veem uns nos outros (os de HIDDEN, como o Benedictum, só aparecem em quem grava) e
# que um suporte põe no grupo: os do Dedo Duro e mais Suffragium, Magnificat, Glória, Renovatio e Expiatio
EXTRA_BUFFS = (16, 20, 21, 336, 340)
# os buffs de uma rodada do sacerdote (o "Podem ir" na caçada): Aumentar Agilidade, Bênção, Angelus, Impositio,
# Suffragium, Magnificat, Glória, Assumptio, Clementia, Canto Candidus, Praefatio, Renovatio, Expiatio, Sacramentum,
# Mediale Votum, Argutus Vita e Telum, Presens Acies, Competentia, Religio e Benedictum
ROUND_BUFFS = frozenset((29, 34, 33, 66, 67, 74, 75, 361, 2041, 2042, 2045, 2050, 2053, 2515, 5269, 5271, 5272,
                         5275, 5278, 5281, 5282))
ROUND_MS = 30000              # uma rodada: ROUND_KINDS buffs diferentes ou mais em 30 s
ROUND_KINDS = 5
KS_LEAD_MS = 1000             # KS: o outro começou a bater pelo menos isto antes do primeiro golpe de quem grava...
KS_SHARE = 0.10               # ...e deu pelo menos isto do dano no monstro
LATE_MIN_MS = 3000            # MVP chegando depois: o primeiro golpe dele pelo menos isto depois do primeiro dos outros
RUN_MIN_USES = 3              # item de cura que acabou: usado pelo menos isto antes (a Ancilla "acaba" a cada uso)
RUN_FIGHT_MS = 5000           # ...numa luta de chefe (até isto antes do começo ou depois do fim)...
RUN_HURT_MS = 10000           # ...ou apanhando (um golpe levado até isto antes, ou 2 s depois)
RUN_SKIP = frozenset((12333,))   # a Ancilla: o Arcebispo faz e bebe na hora (acaba a cada rodada, de propósito)
# sem a lista de itens do jogo (ainda carregando): os elixires do Biólogo e as poções brancas e azuis
HEALS_FALLBACK = frozenset((1100003, 1100004, 1100005, 501, 502, 503, 504, 505, 545, 546, 547, 607, 608, 11502,
                            11503, 12424, 12425, 12426, 12427))


def life(c, aid):
    """A vida máxima de `aid` (a mediana dos pacotes de vida), ou None."""
    import statistics
    maxes = [m for _t, _h, m in (getattr(c, "hp_log", None) or {}).get(aid, []) if m]
    if maxes:
        return statistics.median(maxes)
    return (getattr(c, "max_hp_seen", None) or {}).get(aid)


def _cast_index(c):
    """{(quem conjurou, skill): [quando a conjuração acabou]}, montado uma vez por gravação (refeito se chegaram
    conjurações novas)."""
    got = getattr(c, "_role_casts", None)
    if got is None or got[0] != len(c.casts):
        idx = collections.defaultdict(list)
        for u in c.casts:
            idx[(u[2], u[4])].append(u[0] + (u[5] or 0))
        for v in idx.values():
            v.sort()
        got = (len(c.casts), idx)
        c._role_casts = got
    return got[1]


def own_cast(c, who, t, skill, idx=None):
    """O uso de `skill` por `who` em `t` foi lançado por ele? O buff de grupo de outro sacerdote também chega como um
    uso de cada membro nele mesmo; o de quem lançou vem logo depois do pacote de conjuração dele (o jogo manda o
    pacote mesmo sem tempo de conjuração)."""
    ends = (idx if idx is not None else _cast_index(c)).get((who, skill))
    if not ends:
        return False
    i = bisect.bisect_right(ends, t + 50)
    return i > 0 and t - ends[i - 1] <= CAST_SLACK_MS


def absorbed(c, who=None):
    """O dano dos aliados que passou para `who` pela Redenção: dict(total, hits, allies (protegidos), uses, life (a
    vida máxima dele ou None), peak (o maior golpe absorvido)), ou None se ele não usou a Redenção."""
    who = c.me if who is None else who
    used = [u for u in c.uses if u[4] == REDEMPTION and u[2] == who]
    if not used:
        return None
    first = used[0][0] - 1000
    hits = [d for t, a, d, sk in getattr(c, "self_hits", ()) if a == who and t >= first and d > 0 and not sk]
    allies = {u[3] for u in used if u[3] and u[3] != who}
    return dict(total=sum(hits), hits=len(hits), allies=len(allies), uses=len(used), life=life(c, who),
                peak=max(hits) if hits else 0)


def boss_fights(c, limit=MAX_FIGHTS):
    """As lutas de chefe da gravação (MVPs e chefes, sem os bonecos de treino), as de mais dano primeiro:
    [dict(key, name, mob, first, last, total, ttk)]."""
    import dedoduro as dd
    try:
        rows = [f for f in dd.boss_fights(c, None) if not f.get("dummy")]
    except Exception:  # noqa: BLE001 - sem lutas
        return []
    rows.sort(key=lambda f: -f["total"])
    out = []
    for f in rows[:limit]:
        e = c.entities.get(f["key"])
        out.append(dict(key=f["key"], name=f["name"].replace(" ★", "").split(" (")[0], mob=e.job if e else None,
                        first=f["first"], last=f["last"], total=f["total"], ttk=f.get("ttk"), mvp=f.get("mvp")))
    return out


def lex_fights(c, who=None, fights=None):
    """A Lex Aeterna de `who` em cada luta de chefe: [dict(fight, n (usos no chefe), peak (o maior número de usos em
    LEX_WINDOW_MS, por segundo), rate (usos por segundo na luta toda), secs)], só as lutas em que ele usou."""
    who = c.me if who is None else who
    out = []
    for f in (boss_fights(c) if fights is None else fights):
        lo, hi = f["first"] - 2000, f["last"] + 500
        ts = sorted(u[0] for u in c.uses if u[4] in LEX_SKILLS and u[2] == who and u[3] == f["key"]
                    and lo <= u[0] <= hi)
        if not ts:
            continue
        best = j = 0
        for i, t in enumerate(ts):
            while ts[j] < t - LEX_WINDOW_MS:
                j += 1
            best = max(best, i - j + 1)
        secs = max(1.0, (f["last"] - f["first"]) / 1000.0)
        out.append(dict(fight=f, n=len(ts), peak=best * 1000.0 / LEX_WINDOW_MS, rate=len(ts) / secs, secs=secs))
    return out


def multi_kill(c, who=None, window=MULTI_WINDOW_MS):
    """O maior grupo de monstros que `who` derrubou com a mesma skill em `window` ms (o golpe que matou cada um é o
    último golpe nele até a morte, e foi de `who` até KILL_BLOW_MS antes dela): dict(n, skill, t, mob (o monstro que
    mais caiu no grupo)) ou None sem abates. Uma passada só pelos golpes, junto com as mortes em ordem (o mesmo AID
    volta em outros monstros)."""
    who = c.me if who is None else who
    deaths = sorted((t, aid) for t, aid in c.death_log
                    if (c.entities.get(aid) is not None and c.entities[aid].kind == "mob"))
    if not deaths:
        return None
    last = {}
    kills = collections.defaultdict(list)          # skill -> [(t do golpe, monstro)]
    i, n = 0, len(deaths)
    for h in c.hits:
        while i < n and deaths[i][0] < h.t:
            _settle(c, deaths[i], last, who, kills)
            i += 1
        if h.out and h.dmg > 0:
            last[h.dst_raw] = h
    while i < n:
        _settle(c, deaths[i], last, who, kills)
        i += 1
    best = None
    for skill, rows in kills.items():
        rows.sort()
        j = 0
        for k, (t, _m) in enumerate(rows):
            while rows[j][0] < t - window:
                j += 1
            if best is None or k - j + 1 > best["n"]:
                mobs = collections.Counter(m for _t, m in rows[j:k + 1] if m)
                best = dict(n=k - j + 1, skill=skill, t=t, mob=mobs.most_common(1)[0][0] if mobs else None)
    return best


def _settle(c, death, last, who, kills):
    t, aid = death
    h = last.pop(aid, None)
    if h is None or h.src != who or h.t < t - KILL_BLOW_MS:
        return
    was = c.death_who.get((t, aid))
    e = c.entities.get(aid)
    kills[h.skill].append((h.t, was[1] if was else (e.job if e is not None else None)))


def revived(c, who=None):
    """Quantas vezes `who` trouxe um aliado de volta com Ressuscitar: (vezes, aliados diferentes). Vale o uso seguido
    da volta dele (o pacote de ressurreição até RES_CONFIRM_MS depois); sem esse pacote na gravação, o uso."""
    who = c.me if who is None else who
    uses = [(u[0], u[3]) for u in c.uses if u[4] in RES_SKILLS and u[2] == who and u[3] and u[3] != who]
    if not uses:
        return 0, 0
    back = collections.defaultdict(list)
    for t, aid in getattr(c, "res_log", ()):
        back[aid].append(t)
    have_log = bool(back)
    done = []
    for t, aid in uses:
        if not have_log or any(t <= r <= t + RES_CONFIRM_MS for r in back.get(aid, ())):
            done.append(aid)
    return len(done), len(set(done))


def _buff_ids():
    import dedoduro as dd
    ids = set(EXTRA_BUFFS)
    for r in dd.GROUP_BUFFS + dd.DEFENSE_BUFFS:
        ids |= set(r.ids)
    return {e for e in ids if e not in dd.HIDDEN}


def buff_cover(c, who=None, fights=None):
    """Os buffs de `who` no grupo durante as lutas de chefe: a melhor luta, dict(fight, members (aliados que bateram
    no chefe), buffs ([status] que ele deu na luta), cover (média: a parte da luta, vivo, em que cada aliado teve os
    buffs dele), worst (o aliado menos coberto), given (buffs postos na luta)) ou None. Só os buffs que dá para ver
    nos outros: quem deu é quem lançou a skill do buff (own_cast) logo antes de ele aparecer."""
    import contrib
    import dedoduro as dd
    who = c.me if who is None else who
    best = None
    wanted = _buff_ids()
    idx = _cast_index(c)
    for f in (boss_fights(c) if fights is None else fights):
        try:
            x = dd.Ctx(c, f["key"], None)
        except Exception:  # noqa: BLE001 - luta sem golpes no recorte
            continue
        if who not in x.party:
            continue
        lo = x.start - dd.UNSEEN_MS
        # só as skills da classe dele, e lançadas por ele: o buff de grupo de outro (o Grito de Guerra do Engenheiro,
        # a Clementia do outro Cardeal) também chega como um uso de quem grava nele mesmo
        own = dd.JOB_SKILLS.get(dd.job_id(c, who)) or set()
        mine_uses = [u for u in c.uses if u[2] == who and lo <= u[0] <= x.end and u[4] in own
                     and own_cast(c, who, u[0], u[4], idx)]
        mine = {u[4] for u in mine_uses}
        cands = [e for e in wanted if contrib._apply_skills(e) & mine]
        members = [a for a in x.party if a != who and x.dmg.get(a, 0) > 0]
        if not cands or len(members) < 3:
            continue
        given = sum(1 for u in c.uses if u[2] == who and x.start <= u[0] <= x.end and u[3] in x.party)
        per = []
        used = set()
        before, after = contrib.APPLY_WINDOW
        mine_at = {e: sorted((u[0], u[3]) for u in c.uses if u[2] == who and u[4] in contrib._apply_skills(e) & own
                             and own_cast(c, who, u[0], u[4], idx))
                   for e in cands}
        for a in members:
            win = x.alive(a, [(x.start, x.end)])
            ups = []
            for e in cands:
                # dele: o status ligou logo depois de ele lançar a skill no aliado ou em si mesmo (os buffs de grupo,
                # como a Clementia, chegam como um uso de cada um em si mesmo, e o de quem lançou em si; por isso
                # o contrib.given_spans dava o buff ao próprio aliado)
                ts = mine_at[e]
                spans = [(s, en) for s, en, _v in contrib._spans(c, a, e)
                         if any(s - before <= t <= s + after and tgt in (a, who, 0) for t, tgt in ts)]
                up = dd._uptime(spans, win)
                if up is None:
                    continue
                if up > 0:
                    used.add(e)
                ups.append((e, up))
            per.append((a, ups))
        buffs = sorted(used)
        if len(buffs) < 2:
            continue
        covers = []
        by_buff = collections.defaultdict(list)
        for a, ups in per:
            vals = [u for e, u in ups if e in used]
            if vals:
                covers.append(sum(vals) / len(vals))
            for e, u in ups:
                if e in used:
                    by_buff[e].append(u)
        if len(covers) < 3:
            continue
        row = dict(fight=f, members=len(covers), buffs=buffs, cover=sum(covers) / len(covers), worst=min(covers),
                   given=given, per_buff={e: sum(v) / len(v) for e, v in by_buff.items()})
        if best is None or row["cover"] > best["cover"]:
            best = row
    return best


def buff_rounds(c, who=None):
    """As rodadas de buff de `who` (o "Podem ir" na caçada): cada vez que ele lançou ROUND_KINDS buffs de grupo
    diferentes ou mais (ROUND_BUFFS) em ROUND_MS, sem contar os que outro sacerdote pôs no grupo (own_cast).
    dict(n, skills ([skill] dele, a mais usada primeiro), first, last) ou None sem rodada."""
    who = c.me if who is None else who
    idx = _cast_index(c)
    ev = sorted((u[0], u[4]) for u in c.uses if u[2] == who and u[4] in ROUND_BUFFS
                and own_cast(c, who, u[0], u[4], idx))
    starts = []
    i, n = 0, len(ev)
    while i < n:
        j, kinds = i, set()
        while j < n and ev[j][0] <= ev[i][0] + ROUND_MS:
            kinds.add(ev[j][1])
            j += 1
        if len(kinds) >= ROUND_KINDS:
            starts.append(ev[i][0])
            end = ev[i][0] + ROUND_MS
            while i < n and ev[i][0] <= end:
                i += 1
        else:
            i += 1
    if not starts:
        return None
    count = collections.Counter(sk for _t, sk in ev)
    return dict(n=len(starts), skills=[sk for sk, _n in count.most_common(8)], first=starts[0], last=starts[-1])


def support_credit(c, who=None, fights=None):
    """O dano que os efeitos de `who` renderam nos golpes do grupo (contrib.credit), na luta em que mais renderam:
    dict(fight, via (o dano a mais), own (o dele), share (via / dano da luta), top (o efeito que mais rendeu),
    rank (1 = o maior dano creditado do grupo), total) ou None."""
    import contrib
    who = c.me if who is None else who
    best = None
    for f in (boss_fights(c) if fights is None else fights):
        try:
            rows, total = contrib.credit(c, f["key"])
        except Exception:  # noqa: BLE001 - luta sem golpes no recorte
            continue
        if not total:
            continue
        ranked = sorted((r for r in rows if r["aid"] is not None), key=lambda r: -r["total"])
        mine = next((r for r in ranked if r["aid"] == who), None)
        if mine is None or not mine["via"]:
            continue
        via = sum(mine["via"].values())
        top = max(mine["via"].items(), key=lambda kv: kv[1])[0]
        row = dict(fight=f, via=via, own=mine["own"], share=via / float(total), top=top, total=total,
                   rank=1 + ranked.index(mine), via_by=dict(mine["via"]))
        if best is None or row["share"] > best["share"]:
            best = row
    return best


def _players(c):
    """Os jogadores à vista (AIDs), com quem grava."""
    return {aid for aid, e in c.entities.items() if e.kind == "pc"} | {c.me}


def _job(c, aid):
    if aid == c.me:
        return getattr(c.session, "job", None)
    e = c.entities.get(aid)
    return e.job if e is not None and e.kind == "pc" else None


def kill_steals(c, who=None):
    """Os KS de `who`: monstros que um jogador de fora do grupo começou (pelo menos KS_LEAD_MS antes do primeiro golpe
    de `who`) e em que deu pelo menos KS_SHARE do dano, e que `who` matou (o último golpe, até KILL_BLOW_MS antes da
    morte). dict(n, mob (o monstro mais roubado), victims ([classe] dos jogadores roubados, a de mais KS primeiro))
    ou None. Uma passada só pelos golpes, com as mortes em ordem (o mesmo AID volta em outros monstros)."""
    who = c.me if who is None else who
    deaths = sorted((t, aid) for t, aid in c.death_log
                    if (c.entities.get(aid) is not None and c.entities[aid].kind == "mob"))
    if not deaths:
        return None
    pcs = _players(c)
    party = set(c.party) | {who}
    life_of = {}
    mobs, victims = collections.Counter(), collections.Counter()
    n = 0

    def settle(t, aid):
        nonlocal n
        acc = life_of.pop(aid, None)
        if acc is None:
            return
        src, last_t = acc["last"]
        first = acc["first"]
        if src != who or last_t < t - KILL_BLOW_MS or first == who or first not in pcs or first in party:
            return
        if acc["mine"] is None or acc["mine"] - acc["t0"] < KS_LEAD_MS:
            return
        total = sum(acc["by"].values())
        theirs = sum(v for s, v in acc["by"].items() if s in pcs and s not in party)
        if not total or theirs < KS_SHARE * total:
            return
        n += 1
        was = c.death_who.get((t, aid))
        e = c.entities.get(aid)
        mob = was[1] if was else (e.job if e is not None else None)
        if mob:
            mobs[mob] += 1
        victims[first] += 1

    i, nd = 0, len(deaths)
    for h in c.hits:
        while i < nd and deaths[i][0] < h.t:
            settle(*deaths[i])
            i += 1
        if not h.out or h.dmg <= 0:
            continue
        acc = life_of.get(h.dst_raw)
        if acc is None:
            acc = life_of[h.dst_raw] = dict(first=h.src, t0=h.t, by=collections.Counter(), mine=None, last=None)
        acc["by"][h.src] += h.dmg
        if h.src == who and acc["mine"] is None:
            acc["mine"] = h.t
        acc["last"] = (h.src, h.t)
    while i < nd:
        settle(*deaths[i])
        i += 1
    if not n:
        return None
    jobs = []
    for aid, _k in victims.most_common():
        job = _job(c, aid)
        if job and job not in jobs:
            jobs.append(job)
    return dict(n=n, mob=mobs.most_common(1)[0][0] if mobs else None, victims=jobs[:3])


def late_mvp(c, who=None):
    """O MVP que `who` ganhou chegando depois (o "Bem servido"): o aviso de MVP (0x010c) com ele, num chefe em que os
    outros já tinham dado HL_LATE_SHARE do dano ou mais antes do primeiro golpe dele (que veio pelo menos LATE_MIN_MS
    depois do primeiro dos outros). dict(mob, name, before (a parte dos outros antes dele), late (ms), mine (a parte
    dele no fim), others ([classe] de quem bateu antes), t) ou None; com mais de um, o de mais atraso."""
    who = c.me if who is None else who
    best = None
    for t, aid in getattr(c, "mvp_log", ()) or ():
        if aid != who:
            continue
        died = [(abs(dt - t), dt, a) for dt, a in c.death_log if t - 4000 <= dt <= t + 1500
                and c.entities.get(a) is not None and c.entities[a].kind == "mob"]
        if not died:
            continue
        _gap, dt, a = min(died)
        root = c.alias.get(a, a)
        on = [h for h in c.hits if h.out and h.dmg > 0 and h.dst == root and h.t <= dt + 500]
        mine = [h.t for h in on if h.src == who]
        if not on or not mine:
            continue
        first_me = mine[0]
        total = float(sum(h.dmg for h in on))
        before = sum(h.dmg for h in on if h.src != who and h.t < first_me)
        late = first_me - on[0].t
        if late < LATE_MIN_MS or before < HL_LATE_SHARE * total:
            continue
        others = collections.Counter()
        for h in on:
            if h.src != who and h.t < first_me:
                others[h.src] += h.dmg
        jobs = []
        for o, _d in others.most_common():
            job = _job(c, o)
            if job and job not in jobs:
                jobs.append(job)
        e = c.entities.get(a)
        row = dict(mob=e.job if e is not None else None, name=c.name_of(a), before=before / total, late=late,
                   mine=sum(h.dmg for h in on if h.src == who) / total, others=jobs[:3], t=t)
        if best is None or row["before"] > best["before"]:
            best = row
    return best


def heal_items():
    """Os itens que recuperam HP ou SP (da descrição do jogo; carregando, os elixires e as poções comuns)."""
    try:
        import xp
        got = xp.GEAR.heals
    except (ImportError, AttributeError):
        got = None
    return got or HEALS_FALLBACK


def ran_out(c, who=None):
    """O item de cura (elixir, poção...) de quem grava que acabou no meio da luta (o "Tá fácil pra ninguém"): o uso que
    deixou 0 na bolsa, depois de pelo menos RUN_MIN_USES usos dele com sobra, numa luta de chefe ou apanhando.
    dict(item, t, uses (usos dele na gravação), fight (o nome do chefe ou None), mob (o chefe ou o monstro que mais
    bateu nele ali)) ou None (o primeiro)."""
    if who is not None and who != c.me:
        return None                       # só a bolsa de quem grava diz quanto sobrou
    heals = heal_items()
    log = [(t, item, left) for t, item, left in (getattr(c, "item_left", None) or ())
           if item in heals and item not in RUN_SKIP]
    if not log:
        return None
    total = collections.Counter(item for _t, item, _l in log)
    seen = collections.Counter()
    prev = {}
    fights = hurt = None
    for t, item, left in log:
        seen[item] += 1
        before, prev[item] = prev.get(item), left
        if left != 0 or before is None or before < 1 or seen[item] <= RUN_MIN_USES:
            continue
        if fights is None:
            fights = boss_fights(c, 20)
            hurt = sorted((h.t, h.src, h.dmg) for h in c.hits if not h.out and h.dst == c.me and h.dmg > 0)
        f = next((f for f in fights if f["first"] - RUN_FIGHT_MS <= t <= f["last"] + RUN_FIGHT_MS), None)
        lo = bisect.bisect_left(hurt, (t - RUN_HURT_MS,))
        hi = bisect.bisect_right(hurt, (t + 2000, float("inf")))
        near = hurt[lo:hi]
        if f is None and not near:
            continue
        mob = f["mob"] if f else None
        if mob is None and near:
            by = collections.Counter()
            for _t, src, d in near:
                by[src] += d
            e = c.entities.get(by.most_common(1)[0][0])
            mob = e.job if e is not None and e.kind == "mob" else None
        return dict(item=item, t=t, uses=total[item], fight=f["name"] if f else None, mob=mob)
    return None


def party_jobs(c, who=None, limit=4):
    """As classes dos outros do grupo (para a cena), as de quem mais bateu primeiro, sem repetir: [id da classe]."""
    who = c.me if who is None else who
    dmg = collections.Counter()
    for h in c.hits:
        if h.out and h.src in c.party:
            dmg[h.src] += h.dmg
    out = []
    for aid in sorted(c.party, key=lambda a: -dmg.get(a, 0)):
        if aid == who:
            continue
        e = c.entities.get(aid)
        job = e.job if e is not None and e.kind == "pc" else None
        if job and job not in out:
            out.append(job)
        if len(out) >= limit:
            break
    return out


def skill_name(sid):
    return meter.skill_name(sid) or ("#%d" % sid if sid else "")


# --- os limites dos cartões (das 311 gravações; ver o começo do arquivo) ------------------------------------------

HL_REDEEM_LIVES = 10          # Redentor: o dano absorvido passou de 10 vezes a vida de quem usou (6 de 32)
HL_LEX_PER_S = 2.0            # Lex Aeterna: o pico de 10 s numa luta de chefe (8 de 66 lutas)
HL_MULTI = 20                 # "Oi, tchau": monstros derrubados pela mesma skill em 1 s (7 de ~670)
HL_REVIVE = 4                 # "Quero um aumento": vezes que trouxe um aliado de volta (4 gravações de Cardeal)
HL_BUFF_COVER = 0.9           # "Podem ir" numa luta de chefe: a cobertura média dos aliados na luta...
HL_BUFF_WORST = 0.75          # ...e a do menos coberto...
HL_BUFF_KINDS = 3             # ...com pelo menos estes buffs diferentes...
HL_BUFF_MEMBERS = 4           # ...em pelo menos estes aliados que bateram no chefe (14 de 103)
HL_ROUNDS = 40                # "Podem ir" na caçada: rodadas de buff (uma hora de grupo bem buffado; 9 de 14 caçadas)
HL_ROUND_PARTY = 2            # ...num grupo com pelo menos estes outros
HL_KS = 20                    # "Bem servido": KS na gravação (11 de 311)...
HL_LATE_SHARE = 0.20          # ...ou o MVP com os outros tendo dado isto do dano antes do primeiro golpe dele
# "Sem mim era Wipe": a parte do dano da luta que os efeitos renderam, pelo efeito que mais rendeu (o Pólen do Magus
# passa de 25% em metade das lutas dele; a Garra Sombria e a Lex ficam em 3% a 13%; as áreas do Elementalista em 4%):
# assim cada classe de suporte ganha o cartão nas suas melhores lutas, ~1 em 5
CREDIT_MIN = {1183: 0.30, 1142: 0.30, 730: 0.22, 22: 0.20, 1402: 0.15, -2465: 0.12, -2466: 0.12, -2467: 0.12,
              -2468: 0.12, -285: 0.12, -286: 0.12, -287: 0.12}
CREDIT_DEFAULT = 0.20


def _able(c, skills):
    """A classe de quem grava tem alguma destas skills?"""
    import dedoduro as dd
    return bool((dd.JOB_SKILLS.get(c.session.job) or set()) & set(skills))


def _credit_skills():
    import contrib
    out = set(LEX_SKILLS)
    for efst in contrib.EFFECTS:
        out |= contrib._apply_skills(efst)
    out |= {-k for k in contrib.AREAS}
    return out


def found(c, want):
    """Os cartões de classe e de papel que a gravação de quem grava ganhou: {"redeemer" | "lex" | "buffed" | "credit" |
    "aoe" | "revive" | "served" | "no_elixir": dados}. `want`: as chaves pedidas. As contas caras (o dano creditado,
    os buffs no grupo) só rodam para quem tem as skills: o Mestre Celestial não paga por elas."""
    out = {}
    if "aoe" in want:
        mk = multi_kill(c)
        if mk and mk["n"] >= HL_MULTI:
            out["aoe"] = mk
    if "revive" in want:
        n, allies = revived(c)
        if n >= HL_REVIVE:
            out["revive"] = dict(n=n, allies=allies)
    if "redeemer" in want:
        ab = absorbed(c)
        if ab and ab["life"] and ab["total"] >= HL_REDEEM_LIVES * ab["life"]:
            out["redeemer"] = ab
    if "served" in want:
        late = late_mvp(c)
        if late:
            out["served"] = dict(late, kind="mvp")
        else:
            ks = kill_steals(c)
            if ks and ks["n"] >= HL_KS:
                out["served"] = dict(ks, kind="ks")
    if "no_elixir" in want:
        ro = ran_out(c)
        if ro:
            out["no_elixir"] = ro
    need_fights = ("lex" in want and any(u[4] in LEX_SKILLS and u[2] == c.me for u in c.uses)) or \
        ("buffed" in want and _able(c, _buff_skills())) or ("credit" in want and _able(c, _credit_skills()))
    fights = boss_fights(c) if need_fights else []
    if "lex" in want and fights:
        lx = [x for x in lex_fights(c, None, fights) if x["peak"] >= HL_LEX_PER_S]
        if lx:
            out["lex"] = max(lx, key=lambda x: x["peak"])
    if "buffed" in want and fights and _able(c, _buff_skills()):
        bc = buff_cover(c, None, fights)
        if bc and bc["cover"] >= HL_BUFF_COVER and bc["worst"] >= HL_BUFF_WORST and \
                len(bc["buffs"]) >= HL_BUFF_KINDS and bc["members"] >= HL_BUFF_MEMBERS:
            out["buffed"] = bc
    if "buffed" in want and "buffed" not in out and _able(c, ROUND_BUFFS):
        others = len(set(c.party) - {c.me})
        if others >= HL_ROUND_PARTY:
            rr = buff_rounds(c)
            if rr and rr["n"] >= HL_ROUNDS:
                out["buffed"] = dict(rr, farm=True, members=others)
    if fights and ("credit" in want or "lex" in out) and _able(c, _credit_skills()):
        sc = support_credit(c, None, fights)
        if sc and sc["share"] >= CREDIT_MIN.get(sc["top"], CREDIT_DEFAULT) and "credit" in want:
            out["credit"] = sc
        if "lex" in out and sc and sc["fight"]["key"] == out["lex"]["fight"]["key"] and 22 in sc["via_by"]:
            out["lex"]["credit"] = sc["via_by"][22]
            out["lex"]["credit_share"] = sc["via_by"][22] / float(sc["total"])
    return out


def _buff_skills():
    import contrib
    out = set()
    for e in _buff_ids():
        out |= contrib._apply_skills(e)
    return out
