"""Analises sobre os eventos guardados pelo Combat (mesmas contas do Ragna Recap /
ragreplaystats: por jogador, por monstro, habilidades do monstro, janela de DPS).

Todas as funcoes recebem um intervalo `rng` = (t0, t1) em ms do replay (inclusivo)
e devolvem listas de dicts prontas para tabela/grafico.
"""

import collections
import math

import meter
import rrf
from i18n import _


def _in(rng, t):
    return rng is None or rng[0] <= t <= rng[1]


def out_hits(c, rng):
    return [h for h in c.hits if h.out and _in(rng, h.t)]


def in_hits(c, rng):
    return [h for h in c.hits if not h.out and _in(rng, h.t)]


def _mob_key(h, group):
    return h.dst if group else h.dst_raw


def job_of(c, aid):
    if aid == c.me:
        return meter.job_name(c.session.job)
    e = c.entities.get(aid)
    if e is None:
        return ""
    if e.kind == "pc":
        return meter.job_name(e.job)
    return {"homun": _("Homúnculo"), "merc": _("Mercenário"), "elem": _("Elemental"), "abr": "ABR",
            "bionic": _("Planta"), "mob": _("Invocação")}.get(e.kind, "")


def source_label(c, h):
    """Nome da skill, com a invocacao na frente quando nao foi o proprio jogador."""
    name = meter.skill_name(h.skill, meter.pretty_aegis(c.skill_aegis.get(h.skill)) if h.raw == c.me else None)
    if h.raw != h.src:
        e = c.entities.get(h.raw)
        if e is not None and e.kind not in ("unknown",):
            return "%s: %s" % (c.name_of(h.raw), name)
    return name


def killing_blows(c, rng=None):
    """AID morto -> (dono do ultimo golpe aliado antes da morte, quando morreu)."""
    last = {}
    out = {}
    deaths = sorted((t, aid) for aid, t in c.deaths.items() if _in(rng, t))
    if not deaths:
        return out
    pending = {aid: t for t, aid in deaths}
    for h in c.hits:
        if h.out and h.dst_raw in pending and h.t <= pending[h.dst_raw]:
            last[h.dst_raw] = h.src
    for t, aid in deaths:
        if aid in last:
            out[aid] = (last[aid], t)
    return out


def players(c, rng, dur_ms):
    agg = {}
    for h in out_hits(c, rng):
        a = agg.get(h.src)
        if a is None:
            a = agg[h.src] = dict(aid=h.src, total=0, hits=0, crits=0, misses=0, max_hit=0, mobs=set(), times=[])
        a["times"].append(h.t)
        a["total"] += h.dmg
        a["hits"] += 1
        a["crits"] += h.crit
        a["misses"] += h.miss
        if h.dmg > a["max_hit"]:
            a["max_hit"] = h.dmg
        a["mobs"].add(h.dst)
    kills = collections.Counter(k for k, _t in killing_blows(c, rng).values())
    total = sum(a["total"] for a in agg.values()) or 1
    rows = []
    for a in agg.values():
        rows.append(dict(aid=a["aid"], name=c.name_of(a["aid"]), job=job_of(c, a["aid"]), me=a["aid"] == c.me,
                         total=a["total"], dps=a["total"] * 1000.0 / max(1, dur_ms), share=a["total"] / total,
                         adps=a["total"] * 1000.0 / meter.active_ms(sorted(a["times"])),
                         hits=a["hits"], crits=a["crits"], misses=a["misses"], max_hit=a["max_hit"],
                         mobs=len(a["mobs"]), kills=kills.get(a["aid"], 0)))
    rows.sort(key=lambda r: -r["total"])
    return rows


def _cast_avg(c, rng, src_filter):
    acc = {}
    for t, src, raw, _dst, skill, ms in c.casts:
        if _in(rng, t) and src_filter(src, raw):
            a = acc.setdefault(skill, [0, 0])
            a[0] += 1
            a[1] += ms
    return {k: (v[1] / v[0] if v[0] else None) for k, v in acc.items()}


def player_skills(c, rng, aid, dur_ms):
    agg = collections.OrderedDict()
    for h in out_hits(c, rng):
        if h.src != aid:
            continue
        key = (h.raw, h.skill)
        a = agg.get(key)
        if a is None:
            a = agg[key] = dict(name=source_label(c, h), skill=h.skill, total=0, hits=0, multi=0, max_hit=0)
        a["total"] += h.dmg
        a["hits"] += 1
        a["multi"] += h.hits
        a["max_hit"] = max(a["max_hit"], h.dmg)
    casts = _cast_avg(c, rng, lambda src, raw: src == aid)
    total = sum(a["total"] for a in agg.values()) or 1
    rows = []
    for a in agg.values():
        rows.append(dict(a, avg=a["total"] / a["hits"], avg_multi=a["multi"] / a["hits"],
                         cast=casts.get(a["skill"]), share=a["total"] / total,
                         dps=a["total"] * 1000.0 / max(1, dur_ms)))
    rows.sort(key=lambda r: -r["total"])
    return rows


# HP dos chefes por dificuldade (calculadora da LATAM Tools; a base do medidor tem só o da dificuldade
# máxima). O replay não diz a dificuldade: ela é deduzida do dano (ver boss_hp) ou escolhida na análise.
BOSS_LEVELS = {20994: [(_("Selado"), 500000000), (_("Nível 1"), 800000000), (_("Nível 2"), 1100000000),
                       (_("Nível 3"), 1400000000), (_("Nível 4"), 1700000000), (_("Nível 5"), 2000000000)]}
BOSS_USUAL = {20994: 1}       # o nível que os grupos costumam fazer (Betelgeuse: todos os abates dos replays)
# Regeneração (fração do HP máx. por segundo). O replay não mostra o HP, mas nos abates o dano além do HP
# cresce com a duração da luta: ~0,8M/s no Nível 1 (~6% do HP por minuto), mais ~18M de overkill.
BOSS_REGEN = {20994: 0.001}
LEVEL_SLACK = 0.05            # folga do dano: overkill de cada fase, ou a morte que o replay não mostrou
HP_CHOICE = {}                # (gravação, chave do chefe) -> nível escolhido na análise


def _choice_key(c, key):
    return (tuple(c.session.recorded_at), c.session.player, key)


def caught_midway(c, key):
    """A gravação começou com o chefe já na tela (o pacote de aparecimento dele não está no replay): o dano de
    antes não aparece, então mesmo um abate só diz o mínimo do HP. Nos replays, a 1ª fase sempre aparece de 0 a
    3 s antes do 1º golpe; sem isso, a luta já estava em andamento."""
    return key not in c.spawned


def boss_hp(c, key, total, killed, dur_ms=0):
    """(HP, rótulo, como) do chefe para as contas (clímax, golpes fortes, curva de HP).

    Com tabela de dificuldades, o dano esperado de um nível é o HP mais o que ele regenera em `dur_ms`. Morto, o
    nível cujo dano esperado mais se aproxima do dano feito; vivo (ou gravado com a luta em andamento), o nível de
    costume, ou o menor que comporta o dano visto se ele passou disso. Sem tabela: o HP que o servidor manda, o
    dano total se morreu, ou a base."""
    e = c.entities.get(key)
    midway = caught_midway(c, key)
    mob_id = e.job if e is not None else 0
    levels = BOSS_LEVELS.get(mob_id)
    if levels:
        pick = HP_CHOICE.get(_choice_key(c, key))
        if pick is not None:
            return levels[pick][1], levels[pick][0], _("escolhido")
        grow = 1 + BOSS_REGEN.get(mob_id, 0) * dur_ms / 1000.0      # HP + o que regenerou na luta
        when = _dur(dur_ms)
        if killed and not midway:
            i = min(range(len(levels)), key=lambda k: abs(math.log(max(1, total) / (levels[k][1] * grow))))
            return levels[i][1], levels[i][0], _("deduzido: morreu com %s de dano em %s de luta") % (
                _full(total), when)
        fit = [i for i, (_n, hp) in enumerate(levels) if hp * grow >= total * (1 - LEVEL_SLACK)]
        least = fit[0] if fit else len(levels) - 1
        usual = BOSS_USUAL.get(mob_id, 0)
        why = _("a gravação começou com a luta em andamento") if midway else _("não morreu")
        if least <= usual:
            return levels[usual][1], levels[usual][0], _("deduzido: %s, %s de dano visto em %s de luta "
                                                         "(o nível mais comum)") % (why, _full(total), when)
        return levels[least][1], levels[least][0], _("deduzido: %s, %s de dano visto em %s de luta (no "
                                                     "mínimo este nível)") % (why, _full(total), when)
    _mob, max_hp, _boss = monster_info(c, key)
    if e is not None and e.max_hp and e.max_hp > 0:
        return e.max_hp, "", _("informado pelo servidor")
    if killed and midway:
        return total, "", _("no mínimo o dano visto (a gravação começou com a luta em andamento)")
    if killed:
        return total, "", _("dano até morrer")
    if max_hp >= total:
        return max_hp, "", _("da base de dados")
    return total, "", _("no mínimo o dano visto")


def hp_levels(c, key):
    """[(rótulo, HP)] das dificuldades do chefe (vazio se não há tabela)."""
    e = c.entities.get(key)
    return BOSS_LEVELS.get(e.job if e is not None else 0, [])


def choose_hp(c, key, index):
    """Fixa a dificuldade (índice em hp_levels) ou volta para a dedução (None)."""
    if index is None:
        HP_CHOICE.pop(_choice_key(c, key), None)
    else:
        HP_CHOICE[_choice_key(c, key)] = index


def hp_choice(c, key):
    return HP_CHOICE.get(_choice_key(c, key))


def monster_info(c, key):
    e = c.entities.get(key)
    mob_id = e.job if e is not None else 0
    max_hp = e.max_hp if e is not None and e.max_hp and e.max_hp > 0 else 0
    if not max_hp:
        m = meter.MONSTERS.get(str(mob_id))
        max_hp = m.get("hp", 0) if m else 0
    return mob_id, max_hp, bool(e is not None and e.boss)


def monsters(c, rng, group=True):
    agg = {}
    for h in out_hits(c, rng):
        k = _mob_key(h, group)
        a = agg.get(k)
        if a is None:
            a = agg[k] = dict(key=k, total=0, hits=0, attackers=set(), first=h.t, last=h.t, members=set())
        a["total"] += h.dmg
        a["hits"] += 1
        a["attackers"].add(h.src)
        a["last"] = h.t
        a["members"].add(h.dst_raw)
    blows = killing_blows(c, None)
    rows = []
    for a in agg.values():
        mob_id, max_hp, boss = monster_info(c, a["key"])
        death = None
        killer = None
        for m in a["members"]:
            if m in blows and (death is None or blows[m][1] > death):
                killer, death = blows[m]
        if hp_levels(c, a["key"]):
            max_hp = boss_hp(c, a["key"], a["total"], death is not None,
                             (death if death is not None else a["last"]) - a["first"])[0]     # pela dificuldade
        phases = c.phases.get(a["key"], 0) if group else 0
        name = c.name_of(a["key"]) + (" ★" if boss or phases > 1 else "")
        if phases > 1:
            name += _(" (%d fases)") % phases
        rows.append(dict(key=a["key"], name=name, mob_id=mob_id, boss=boss, total=a["total"], hits=a["hits"],
                         attackers=len(a["attackers"]), max_hp=max_hp or None,
                         ttk=(death - a["first"]) if death is not None else None,
                         killer=c.name_of(killer) if killer is not None else "", first=a["first"], last=a["last"]))
    rows.sort(key=lambda r: -r["total"])
    return rows


def monster_players(c, rng, key, group=True):
    agg = collections.Counter()
    hits = collections.Counter()
    for h in out_hits(c, rng):
        if _mob_key(h, group) == key:
            agg[h.src] += h.dmg
            hits[h.src] += 1
    total = sum(agg.values()) or 1
    return [dict(aid=a, name=c.name_of(a), job=job_of(c, a), me=a == c.me, total=v, share=v / total, hits=hits[a])
            for a, v in agg.most_common()]


def timeline(c, rng, bucket_ms, src=None, key=None, group=True, top=8):
    """Dano por intervalo de tempo. Devolve (inicios_ms, [(aid, nome, valores)]).
    src filtra um jogador; key filtra um monstro."""
    hs = [h for h in out_hits(c, rng)
          if (src is None or h.src == src) and (key is None or _mob_key(h, group) == key)]
    if not hs:
        return [], []
    t0 = rng[0] if rng else hs[0].t
    t1 = rng[1] if rng else hs[-1].t
    t0 = min(t0, hs[0].t)
    t1 = max(t1, hs[-1].t)
    n = max(1, int((t1 - t0) // bucket_ms) + 1)
    series = collections.OrderedDict()
    totals = collections.Counter()
    for h in hs:
        v = series.get(h.src)
        if v is None:
            v = series[h.src] = [0] * n
        v[min(n - 1, int((h.t - t0) // bucket_ms))] += h.dmg
        totals[h.src] += h.dmg
    order = [a for a, _ in totals.most_common()]
    out = [(a, c.name_of(a), series[a]) for a in order[:top]]
    if len(order) > top:
        rest = [0] * n
        for a in order[top:]:
            for i, x in enumerate(series[a]):
                rest[i] += x
        out.append((None, "outros", rest))
    return [t0 + i * bucket_ms for i in range(n)], out


def skills_against(c, rng, key, group=True):
    agg = collections.OrderedDict()
    for h in out_hits(c, rng):
        if _mob_key(h, group) != key:
            continue
        k = (h.src, h.raw, h.skill)
        a = agg.get(k)
        if a is None:
            a = agg[k] = dict(name=source_label(c, h), player=c.name_of(h.src), job=job_of(c, h.src),
                              src=h.src, skill=h.skill, total=0, hits=0, multi=0)
        a["total"] += h.dmg
        a["hits"] += 1
        a["multi"] += h.hits
    casts = {}
    for t, src, _raw, _dst, skill, ms in c.casts:
        if _in(rng, t):
            v = casts.setdefault((src, skill), [0, 0])
            v[0] += 1
            v[1] += ms
    rows = []
    for (src, _raw, skill), a in agg.items():
        cv = casts.get((src, skill))
        rows.append(dict(a, avg=a["total"] / a["hits"], avg_multi=a["multi"] / a["hits"],
                         cast=(cv[1] / cv[0]) if cv else None))
    rows.sort(key=lambda r: -r["total"])
    return rows


def monster_skills(c, rng, key, target=None):
    """Habilidades usadas pelo monstro (dano + suporte/debuff + conjuracoes)."""
    agg = {}

    def acc(skill):
        a = agg.get(skill)
        if a is None:
            a = agg[skill] = dict(skill=skill, name=meter.skill_name(skill), hits=0, total=0, nodmg=0,
                                  targets=set(), casts=0, cast_ms=0)
        return a

    for h in in_hits(c, rng):
        if h.src == key and (target is None or h.dst == target):
            a = acc(h.skill)
            a["hits"] += 1
            a["total"] += h.dmg
            a["targets"].add(h.dst)
    for t, src, _raw, dst, skill in c.uses:
        if src == key and _in(rng, t) and (target is None or c.resolve(dst) == target):
            a = acc(skill)
            a["nodmg"] += 1
            a["targets"].add(dst)
    if target is None:
        for t, src, _raw, _dst, skill, ms in c.casts:
            if src == key and _in(rng, t):
                a = acc(skill)
                a["casts"] += 1
                a["cast_ms"] += ms
    rows = []
    for a in agg.values():
        rows.append(dict(name=a["name"], skill=a["skill"], hits=a["hits"], total=a["total"],
                         avg=(a["total"] / a["hits"]) if a["hits"] else 0, nodmg=a["nodmg"],
                         targets=len(a["targets"]), cast=(a["cast_ms"] / a["casts"]) if a["casts"] else None))
    rows.sort(key=lambda r: (-r["total"], -r["hits"], -r["nodmg"]))
    return rows


def monster_victims(c, rng, key):
    """Jogadores que o monstro atingiu (para o filtro das habilidades do monstro)."""
    agg = collections.Counter()
    for h in in_hits(c, rng):
        if h.src == key:
            agg[h.dst] += h.dmg
    for t, src, _raw, dst, _skill in c.uses:
        if src == key and _in(rng, t):
            agg[c.resolve(dst)] += 0
    return [(a, c.name_of(a)) for a, _ in agg.most_common() if c.is_friendly(a)]


def window_stats(c, aid, t0, t1):
    """Estatisticas da janela (aba Analise de DPS), como no Ragna Recap.
    O DPS usa do 1o ao ultimo golpe dentro da janela, nao as bordas da selecao."""
    hs = sorted((h for h in c.hits if h.out and h.src == aid and t0 <= h.t <= t1), key=lambda h: h.t)
    res = dict(window_ms=max(0, t1 - t0), events=len(hs), total=0, span_ms=0, dps=0, mean_gap=None,
               longest_gap=0, max_hit=0, avg_hit=0, distinct=0, top_skill="", top_skill_dmg=0, skills=[])
    if not hs:
        return res
    by_skill = collections.OrderedDict()
    longest = 0
    for i, h in enumerate(hs):
        res["total"] += h.dmg
        res["max_hit"] = max(res["max_hit"], h.dmg)
        k = (h.raw, h.skill)
        s = by_skill.get(k)
        if s is None:
            s = by_skill[k] = dict(name=source_label(c, h), total=0, hits=0, max_hit=0)
        s["total"] += h.dmg
        s["hits"] += 1
        s["max_hit"] = max(s["max_hit"], h.dmg)
        if i:
            longest = max(longest, h.t - hs[i - 1].t)
    span = hs[-1].t - hs[0].t
    res.update(span_ms=span, dps=(res["total"] * 1000.0 / span) if span > 0 else 0,
               mean_gap=(span / (len(hs) - 1)) if len(hs) > 1 else None, longest_gap=longest,
               avg_hit=res["total"] / len(hs), distinct=len(by_skill))
    total = res["total"] or 1
    skills = sorted(by_skill.values(), key=lambda s: -s["total"])
    for s in skills:
        s["share"] = s["total"] / total
        s["dps"] = (s["total"] * 1000.0 / span) if span > 0 else 0
    res["skills"] = skills
    res["top_skill"] = skills[0]["name"]
    res["top_skill_dmg"] = skills[0]["total"]
    return res


EDGE_MS = 5000      # folga nas bordas do encontro: conjuracao do chefe antes, morte logo depois


def scope_range(c, scope):
    """scope: None = sessao inteira; senao um Encounter. Devolve (rng, duracao_em_combate_ms).
    A sessao nao filtra nada (rng None)."""
    if scope is None:
        snap = c.snapshot(session=True)
        return None, snap["duration_ms"] if snap else 0
    live = c.is_live(scope)
    end = c.now if live else scope.last + EDGE_MS
    return (scope.start - EDGE_MS, end), scope.duration_ms(c.now if live else None)


# --- resumo do jogador e detalhes ----------------------------------------------

def summary(c, rng, dur_ms, aid=None):
    """Cartões da aba Resumo (como o "Resumo" do Ragna Recap, para quem gravou)."""
    aid = c.me if aid is None else aid
    mine = [h for h in out_hits(c, rng) if h.src == aid]
    taken = [h for h in in_hits(c, rng) if h.dst == aid]
    group = sum(h.dmg for h in out_hits(c, rng))
    dealt = sum(h.dmg for h in mine)
    best = max(mine, key=lambda h: h.dmg) if mine else None
    counts = collections.Counter(h.skill for h in mine if h.skill)
    top_skill, top_count = (counts.most_common(1)[0] if counts else (None, 0))
    blows = killing_blows(c, rng)
    kills = [k for k, (who, _t) in blows.items() if who == aid]
    boss_kills = sum(1 for k in kills if c.entities.get(k) is not None and c.entities[k].boss)
    span = (mine[-1].t - mine[0].t) if len(mine) > 1 else 0
    active = meter.active_ms(sorted(h.t for h in mine)) if mine else 0
    return dict(
        dealt=dealt, share=dealt / group if group else 0, group=group,
        dps=dealt * 1000.0 / max(1, dur_ms), effective_dps=(dealt * 1000.0 / span) if span else 0,
        active_ms=active, active_dps=(dealt * 1000.0 / active) if active else 0,
        hits=len(mine), misses=sum(h.miss for h in mine), crits=sum(h.crit for h in mine),
        best=dict(dmg=best.dmg, skill=source_label(c, best), target=c.target_name(best.dst), t=best.t) if best else None,
        top_skill=meter.skill_name(top_skill) if top_skill is not None else "", top_count=top_count,
        kills=len(kills), boss_kills=boss_kills,
        deaths=sum(1 for t, a in c.death_log if a == aid and _in(rng, t)),
        taken=sum(h.dmg for h in taken) + sum(trap_damage(c, x) for x in trap_hits(c, aid, *(rng or (None, None)))),
        taken_hits=len(taken) + len(trap_hits(c, aid, *(rng or (None, None)))),
        combat_ms=dur_ms, recorded_ms=c.now, entities=len(c.entities),
    )


def top_hits(c, rng, aid, n=10):
    hs = sorted((h for h in out_hits(c, rng) if h.src == aid), key=lambda h: -h.dmg)[:n]
    return [dict(t=h.t, name=source_label(c, h), target=c.target_name(h.dst), dmg=h.dmg, hits=h.hits) for h in hs]


def damage_taken(c, rng, aid):
    """Dano recebido por (monstro, habilidade)."""
    agg = collections.OrderedDict()
    for h in in_hits(c, rng):
        if h.dst != aid:
            continue
        k = (h.src, h.skill)
        a = agg.get(k)
        if a is None:
            a = agg[k] = dict(source=c.target_name(h.src), name=meter.skill_name(h.skill), total=0, hits=0, max_hit=0)
        a["total"] += h.dmg
        a["hits"] += 1
        a["max_hit"] = max(a["max_hit"], h.dmg)
    for x in trap_hits(c, aid, *(rng or (None, None))):
        a = agg.setdefault(("trap", 0), dict(source=TRAP_NAME, name=_("Armadilha"), total=0, hits=0, max_hit=0))
        dmg = trap_damage(c, x)
        a["total"] += dmg
        a["hits"] += 1
        a["max_hit"] = max(a["max_hit"], dmg)
    total = sum(a["total"] for a in agg.values()) or 1
    rows = [dict(a, share=a["total"] / total) for a in agg.values()]
    rows.sort(key=lambda r: -r["total"])
    return rows


def player_targets(c, rng, aid, group=True):
    """Monstros que o jogador atingiu."""
    agg = collections.OrderedDict()
    for h in out_hits(c, rng):
        if h.src != aid:
            continue
        k = _mob_key(h, group)
        a = agg.get(k)
        if a is None:
            a = agg[k] = dict(key=k, name=c.target_name(k) if group else c.name_of(k), total=0, hits=0, max_hit=0)
        a["total"] += h.dmg
        a["hits"] += 1
        a["max_hit"] = max(a["max_hit"], h.dmg)
    total = sum(a["total"] for a in agg.values()) or 1
    rows = [dict(a, share=a["total"] / total) for a in agg.values()]
    rows.sort(key=lambda r: -r["total"])
    return rows


def rolling_dps(values, bucket_ms, window_ms=5000):
    """DPS médio móvel (janela de `window_ms`) sobre o dano por intervalo."""
    k = max(1, int(round(window_ms / bucket_ms)))
    out, acc = [], 0
    for i, v in enumerate(values):
        acc += v
        if i >= k:
            acc -= values[i - k]
        out.append(acc * 1000.0 / (min(i + 1, k) * bucket_ms))
    return out


def share_text(c, rng, dur_ms, title):
    """Texto para colar no Discord/WhatsApp com o ranking do recorte."""
    rows = players(c, rng, dur_ms)
    lines = [_("%s — %s em combate") % (title, _dur(dur_ms))]
    for i, r in enumerate(rows[:10], 1):
        lines.append("%2d. %s (%s) — %s · %.1f%% · DPS %s" % (
            i, r["name"], r["job"] or "?", _full(r["total"]), r["share"] * 100, _full(round(r["dps"]))))
    return "\n".join(lines)


def _dur(ms):
    from fmt import dur
    return dur(ms)


def _full(v):
    from fmt import full
    return full(v)


# --- mortes ----------------------------------------------------------------------

RECAP_MS = 10000


TRAP_NAME = _("Armadilha do mapa")


def trap_hits(c, aid=None, t0=None, t1=None):
    """Armadilhas do mapa (Torre da Constelação) que atingiram aliados. O replay só traz o
    efeito visual e a queda de HP no mesmo instante: o dano é essa queda (% do HP máx.,
    irredutível). Quando a armadilha mata, a queda fica cortada no zero."""
    out = []
    for t, a in c.trap_log:
        if (aid is not None and a != aid) or (t0 is not None and not t0 <= t <= t1):
            continue
        log = c.hp_log.get(a, [])
        before = [x for x in log if x[0] < t and x[1] is not None]
        after = [x for x in log if t <= x[0] <= t + 400 and x[1] is not None]
        mx = max((v for x in log if x[0] <= t for v in (x[1], x[2]) if v), default=None)
        hb = before[-1][1] if before else None
        ha = min(x[1] for x in after) if after else None
        drop = (hb - ha) if hb is not None and ha is not None and hb > ha else None
        out.append(dict(t=t, aid=a, hp_before=hb, hp_after=ha, drop=drop, max_hp=mx,
                        pct=(drop / mx) if drop and mx and ha else None))
    return out


def trap_pct_near(c, t, window=20000):
    """% do HP máx. das armadilhas não letais por perto (a % depende da dificuldade e do HP
    do chefe, e é a mesma para todos naquele momento)."""
    pcts = sorted(x["pct"] for x in trap_hits(c, None, t - window, t + window) if x["pct"])
    return pcts[len(pcts) // 2] if pcts else None


def trap_damage(c, x):
    """Dano de uma armadilha: a queda de HP, ou a estimativa (% de HP máx.) quando ela matou."""
    if x["hp_after"]:
        return x["drop"] or 0
    pct = trap_pct_near(c, x["t"])
    return round(pct * x["max_hp"]) if pct and x["max_hp"] else (x["drop"] or 0)


def death_recap(c, aid, t):
    """O que aconteceu com `aid` nos 10 s antes de morrer em `t`."""
    recent = [h for h in c.hits if not h.out and h.dst_raw == aid and t - RECAP_MS <= h.t <= t + 300]
    hp = [s for s in c.hp_log.get(aid, []) if t - RECAP_MS <= s[0] <= t and s[1] is not None]
    # HP máx. muda com buffs; usa o maior valor visto (HP máx. informado ou HP atual)
    seen = [x for s in c.hp_log.get(aid, []) if s[0] <= t for x in (s[1], s[2]) if x]
    max_hp = max(seen) if seen else None
    killing = next((h for h in reversed(recent) if h.t <= t + 300 and t - h.t <= 3000 and h.dmg > 0), None)
    hp_before = None
    if killing is not None:
        before = [s for s in hp if s[0] <= killing.t]
        hp_before = before[-1][1] if before else None
    overkill = max(0, killing.dmg - hp_before) if killing is not None and hp_before is not None else 0
    # o último golpe visível não bastava para matar: foi algo fora da tela ou um efeito
    unclear = killing is not None and hp_before is not None and killing.dmg < hp_before
    hp_last = hp[-1][1] if hp else None
    hp_pct = (hp_last / max_hp) if hp_last is not None and max_hp else None
    # União Solar, Lunar e Estelar: atacar com 20% de HP ou menos mata na hora
    fusion = c.fused_at(aid, t) and (killing is None or unclear)
    fusion_cost = None
    if fusion and len(hp) >= 2:
        drops = sum(max(0, a[1] - b[1]) for a, b in zip(hp, hp[1:]))
        fusion_cost = max(0, drops - sum(h.dmg for h in recent))
    # armadilha do mapa no instante da morte
    traps = trap_hits(c, aid, t - RECAP_MS, t + 300)
    lethal = next((x for x in reversed(traps) if t - 400 <= x["t"] <= t + 300), None)
    trap_pct = trap_est = None
    if lethal is not None:
        trap_pct = lethal["pct"] or trap_pct_near(c, t)
        if trap_pct and (lethal["max_hp"] or max_hp):
            trap_est = trap_pct * (lethal["max_hp"] or max_hp)
        if lethal["hp_before"] is not None:
            hp_before = lethal["hp_before"]
        overkill = max(0, trap_est - lethal["hp_before"]) if trap_est and lethal["hp_before"] is not None else 0
        fusion = unclear = False
    window5 = [h for h in recent if h.t >= t - 5000]
    taken5 = sum(h.dmg for h in window5) + sum(x["drop"] or 0 for x in traps if x["t"] >= t - 5000)
    active = sorted({meter.status_name(e) for a, e, s, end in c.statuses(aid)
                     if s <= t <= end + 200 and meter.status_kind(e) not in ("Serviço", "Sistema")})
    rows = []
    for h in recent:
        rows.append(dict(rel=h.t - t, kind="dano", source=c.target_name(h.src),
                         name=meter.skill_name(h.skill) + (_(" (errou)") if h.miss else ""),
                         dmg=None if h.miss else h.dmg, hp=None, miss=h.miss))
    last_hp = None
    for st, hpv, _mx in hp:
        if hpv == last_hp:
            continue                            # o servidor repete o mesmo valor várias vezes
        last_hp = hpv
        rows.append(dict(rel=st - t, kind="hp", source="", name=_("HP atualizado"), dmg=None, hp=hpv, miss=False))
    for x in traps:
        dmg = x["drop"] if x["hp_after"] else (round(trap_est) if trap_est and x is lethal else x["drop"])
        pct = x["pct"] or (trap_pct if x is lethal else None)
        rows.append(dict(rel=x["t"] - t, kind="dano", source=TRAP_NAME,
                         name=_("Armadilha") + (_(" (%d%% do HP máx.)") % round(pct * 100) if pct else ""),
                         dmg=dmg, hp=x["hp_after"], miss=False))
    rows.sort(key=lambda r: (r["rel"], r["kind"] != "dano"))
    # quedas de HP sem golpe no mesmo instante, junto com algum efeito (mapa, debuff...)
    hit_times = [h.t for h in recent] + [x["t"] for x in traps]
    effects = c.effect_log.get(aid, [])
    my_attacks = [h.t for h in c.hits if h.out and h.src == aid and t - RECAP_MS <= h.t <= t]
    prev = None
    for st, hpv, _mx in hp:
        explained = prev is None or hpv >= prev[1] or any(prev[0] < ht <= st + 200 for ht in hit_times)
        if not explained and c.fused_at(aid, st) and any(abs(st - at) <= 400 for at in my_attacks):
            explained = True                      # custo de HP da União (2% por ataque)
        if not explained:
            near = sorted({e for et, e in effects if abs(et - st) <= 150})
            if near and not set(near) & set(rrf.MAP_DAMAGE_EFFECTS):        # armadilha já tem linha própria
                rows.append(dict(rel=st - t, kind="dano", source=_("Sem golpe visível"),
                                 name=_("HP perdido (efeitos no momento: %s)") % ", ".join(map(str, near)),
                                 dmg=prev[1] - hpv, hp=hpv, miss=False))
        prev = (st, hpv)
    rows.sort(key=lambda r: (r["rel"], r["kind"] != "dano"))
    hp_loss = None
    if len(hp) >= 2 and not recent and not traps:
        hp_loss = max(s[1] for s in hp) - hp[-1][1]
    if lethal is not None:
        killer, skill, hit = TRAP_NAME, _("Armadilha"), round(trap_est) if trap_est else 0
    else:
        killer = c.target_name(killing.src) if killing else ""
        skill = meter.skill_name(killing.skill) if killing else ""
        hit = killing.dmg if killing else 0
    return dict(
        t=t, aid=aid, name=c.name_of(aid), job=job_of(c, aid), me=aid == c.me,
        killer=killer, skill=skill, hit=hit, hp_before=hp_before, max_hp=max_hp, overkill=overkill,
        overkill_x=(hit / hp_before) if hit and hp_before else None,
        taken_5s=taken5, hits_5s=len(window5) + sum(1 for x in traps if x["t"] >= t - 5000), statuses=active,
        rows=rows, trap=lethal is not None, trap_pct=trap_pct, traps=len(traps),
        no_hit=killing is None and lethal is None, hp_loss=hp_loss, unclear=unclear,
        fusion=fusion, hp_last=hp_last, hp_pct=hp_pct, fusion_cost=fusion_cost,
    )


def deaths(c, rng=None):
    """Mortes de jogadores (você, o grupo e quem estava na tela) no recorte."""
    out = []
    for t, aid in c.death_log:
        if not _in(rng, t):
            continue
        e = c.entities.get(aid)
        if aid == c.me or (e is not None and e.kind == "pc"):
            out.append(death_recap(c, aid, t))
    return out


# --- buffs -----------------------------------------------------------------------

def _windows(c, rng):
    """Trechos em combate (encontros) dentro do recorte."""
    out = []
    for enc in c.encounters():
        a, b = enc.start, (c.now if c.is_live(enc) else enc.last)
        cuts = [a] + [x for p in enc.pauses for x in p] + [b]      # tira as trocas de fase
        for s, e in zip(cuts[::2], cuts[1::2]):
            if rng is not None:
                s, e = max(s, rng[0]), min(e, rng[1])
            if e > s:
                out.append((s, e))
    return out


def _overlap(s, e, windows):
    return sum(max(0, min(e, b) - max(s, a)) for a, b in windows)


def _dead_spans(c, aid):
    """Trechos em que `aid` estava morto: da morte até voltar a agir (bater ou receber buff)."""
    spans = []
    starts = sorted(s for a, e, s, _end in c.statuses(aid)
                    if meter.status_kind(e) in ("Grupo/suporte", "Consumível"))
    for t, a in c.death_log:
        if a != aid:
            continue
        # voltou quando bateu de novo ou recebeu um buff de verdade (alguns status chegam junto com a morte)
        back = [h.t for h in c.hits if h.out and h.src == aid and h.t > t][:1]
        back += [s for s in starts if s > t + 1000][:1]
        spans.append((t, min(back) if back else c.now))
    return spans


def _subtract(windows, holes):
    out = []
    for a, b in windows:
        parts = [(a, b)]
        for x, y in holes:
            nxt = []
            for s, e in parts:
                if y <= s or x >= e:
                    nxt.append((s, e))
                    continue
                if x > s:
                    nxt.append((s, x))
                if y < e:
                    nxt.append((y, e))
            parts = nxt
        out += parts
    return out


def buff_uptime(c, aid, rng):
    """Buffs de `aid`: % do tempo em combate (vivo) em que estiveram ativos."""
    wins = _subtract(_windows(c, rng), _dead_spans(c, aid))
    total = sum(b - a for a, b in wins)
    agg = {}
    first = wins[0][0] if wins else None
    for a, efst, s, e in c.statuses(aid):
        if rng is not None and (e < rng[0] or s > rng[1]):
            continue
        if meter.status_kind(efst) == "Sistema":
            continue
        r = agg.get(efst)
        if r is None:
            r = agg[efst] = dict(efst=efst, name=meter.status_name(efst), kind=meter.status_kind(efst),
                                 on_ms=0, count=0, at_start=False, active=False, left=None)
        r["on_ms"] += _overlap(s, e, wins)
        r["count"] += 1
        if first is not None and s <= first <= e:
            r["at_start"] = True
    for (a, efst), (s, tot, left) in c.status_on.items():
        if a == aid and efst in agg:
            agg[efst]["active"] = True
            if left and left < 9999 * 1000:
                agg[efst]["left"] = max(0, left - (c.now - s))
    merged = {}
    for r in agg.values():
        m = merged.get(r["name"])
        if m is None:
            merged[r["name"]] = r
        else:
            m["on_ms"] = max(m["on_ms"], r["on_ms"])
            m["count"] += r["count"]
            m["at_start"] = m["at_start"] or r["at_start"]
            m["active"] = m["active"] or r["active"]
            m["left"] = m["left"] if m["left"] is not None else r["left"]
    rows = []
    for r in merged.values():
        r["uptime"] = (r["on_ms"] / total) if total else None
        rows.append(r)
    order = {"Grupo/suporte": 0, "Consumível": 1, "Classe/outros": 2, "Outro": 3, "Serviço": 4}
    rows.sort(key=lambda r: (order.get(r["kind"], 9), -(r["uptime"] or 0), r["name"]))
    return rows, total


def mob_debuffs(c, rng, key, group=True):
    """Debuffs no monstro durante o tempo em que ele apanhou."""
    members = {key} | ({a for a, root in c.alias.items() if root == key} if group else set())
    span = [h.t for h in out_hits(c, rng) if _mob_key(h, group) == key]
    if not span:
        return [], 0
    win = [(span[0], span[-1])]
    total = span[-1] - span[0]
    agg = {}
    for a, efst, s, e in c.statuses():
        if a not in members or e < win[0][0] or s > win[0][1]:
            continue
        r = agg.get(efst)
        if r is None:
            r = agg[efst] = dict(efst=efst, name=meter.status_name(efst), on_ms=0, count=0,
                                 important=efst in meter.MOB_DEBUFFS)
        r["on_ms"] += _overlap(s, e, win)
        r["count"] += 1
    rows = [dict(r, uptime=(r["on_ms"] / total) if total else None) for r in agg.values()]
    rows.sort(key=lambda r: (not r["important"], -(r["uptime"] or 0)))
    return rows, total


def equipment(c, t):
    return [dict(slot=label, item=meter.item_text(it), item_id=it.item_id) for label, it in c.equipment_at(t)]
