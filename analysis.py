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
# Aquila (Destruição da Aeronave): vida da wiki por dificuldade. A dificuldade vem da redução de dano do chefe
# no estado normal (Alívio: 10% Econômica, 50% Executiva, 80% Primeira Classe; 99% é o modo de defesa).
AQUILA = (21531, 21588)       # normal e em sobrecarga
for _mob in AQUILA:
    BOSS_LEVELS[_mob] = [(_("Econômica"), 300000000), (_("Executiva"), 500000000), (_("Primeira Classe"), 600000000)]
RELIEVE_LEVEL = {_mob: {10: 0, 50: 1, 80: 2} for _mob in AQUILA}
BOSS_USUAL = {20994: 1, 21531: 1, 21588: 1}   # o nível que os grupos costumam fazer (Betelgeuse: todos os abates)
# Regeneração (fração do HP máx. por segundo). O replay não mostra o HP, mas nos abates o dano além do HP
# cresce com a duração da luta: ~0,8M/s no Nível 1 (~6% do HP por minuto), mais ~18M de overkill.
BOSS_REGEN = {20994: 0.001}
# Chefes com regeneração só numa forma e dano que o replay não mostra (frações do HP máx.). Aquila: os valores mais
# prováveis, ajustados em 7 lutas (4 abates e 1 luta incompleta na Executiva, 2 sem abate na Primeira Classe):
# regenera só em sobrecarga, ~0,55% por segundo na Executiva (os 4 abates fecham com erro de até ~11M, 2% do HP)
# e pelo menos ~1,05% na Primeira Classe (senão a luta de 24 min sem abate teria matado o chefe); cada quebra de
# defesa (o Tetra Vortex que ele lança em si mesmo) tira ~4,5%. A Econômica não tem lutas: vai como a Executiva.
# Não é certeza: o replay não mostra o HP dele. `regen` é por dificuldade, na ordem de BOSS_LEVELS.
BOSS_MODEL = {_mob: dict(regen=(0.0055, 0.0055, 0.011), form=21588, hidden=0.045,
                         hidden_skills=(2218, 2219, 2220, 2221))
              for _mob in AQUILA}


def boss_regen(model, mob, hp):
    """Regeneração do modelo para a dificuldade cuja vida é `hp` (a da Executiva se não achar)."""
    regen = model["regen"]
    if not isinstance(regen, tuple):
        return regen
    levels = [v for _n, v in BOSS_LEVELS.get(mob, [])]
    i = levels.index(hp) if hp in levels else BOSS_USUAL.get(mob, 0)
    return regen[min(i, len(regen) - 1)]
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
        by_relief = relieve_level(c, key)
        if by_relief is not None:
            i, pct = by_relief
            return levels[i][1], levels[i][0], _("pela redução de dano do chefe (%d%%)") % pct
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


def relieve_level(c, key):
    """(índice da dificuldade, %) pela redução de dano do chefe no estado normal, ou None (chefe sem essa regra)."""
    e = c.entities.get(key)
    table = RELIEVE_LEVEL.get(e.job if e is not None else 0)
    if not table:
        return None
    aids = {key} | {k for k, v in c.alias.items() if v == key}
    vals = sorted({c.status_val.get((a, ef, s), 0) for a, ef, s, _e in c.statuses() if a in aids and ef == 1166})
    for v in vals:
        if v in table:
            return table[v], v
    return None


def form_windows(c, aids, form, start, end):
    """[(início, fim)] em que o chefe estava na forma `form` (pelas trocas de sprite; a forma ao aparecer conta)."""
    out, on, since = [], False, start
    first = [c.entities[a].job for a in aids if a in c.entities]
    if first and first[0] == form:
        on = True
    for t, cls in sorted(x for a in aids for x in c.sprite_log.get(a, ())):
        if t > end:
            break
        if cls == form and not on:
            on, since = True, max(start, t)
        elif cls != form and on:
            on = False
            if t > since:
                out.append((since, t))
    if on:
        out.append((since, end))
    return out


def hidden_hits(c, aids, skills, start, end):
    """Instantes em que o chefe usou em si mesmo uma skill que tira vida sem pacote de dano (um por quebra)."""
    out = []
    for u in sorted(c.uses):
        if start <= u[0] <= end and u[4] in skills and (u[1] in aids or u[2] in aids) and u[3] in aids:
            if not out or u[0] - out[-1] > 2000:
                out.append(u[0])
    return out


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
            if dst:                               # skill usada numa célula (Chuva de Meteoros...) não tem alvo
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
LETHAL_MS = 1600          # a vida só cai ~1 s depois do pacote do golpe: quem matou pode não ser o último golpe
LAND_MS = 1200            # ...e depois disso o golpe já caiu: quem aparece vivo mais tarde não morreu dele
BOOM_BEFORE_MS = 500      # a morte vem até isto depois da Autodestruição
BOOM_AFTER_MS = 150       # ...ou um pouco antes, pela ordem dos pacotes
BOOM_REACH = 8            # a explosão alcança ~5 células; a posição do monstro é a do último passo (folga)
BOOM_CHASE_MS = 3000      # quem batia na vítima até isto antes da explosão estava colado nela
OFFSCREEN_MIN_MS = 15000  # sobrecarga do Aquila: o golpe dele dobra a cada ~5 s; antes disto não mata ninguém
OFFSCREEN_LAND_MS = 1000  # o golpe dele cai ~1 s depois de sair
FUSION_KILL_PCT = 0.25    # a União mata quem ataca com 20% de HP ou menos: acima disto (com folga) a causa é outra


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


def boom_near(c, aid, t, recent=()):
    """A Autodestruição que pegou `aid` na morte em t: (instante, monstro) ou None. Vale a de um monstro a até
    BOOM_REACH células, ou a de um que batia na vítima logo antes (estava colado). No Aquila ela tira um valor fixo
    de HP sem pacote de dano, então a morte fica sem golpe no replay."""
    me = c.pos_at(aid, t)
    best = None
    for when, mob, xy in reversed(c.booms):
        if when < t - BOOM_BEFORE_MS:
            break
        if when > t + BOOM_AFTER_MS:
            continue
        dist = max(abs(xy[0] - me[0]), abs(xy[1] - me[1])) if xy is not None and me is not None else None
        chased = any(h.raw == mob and when - BOOM_CHASE_MS <= h.t <= when for h in recent)
        if chased or (dist is not None and dist <= BOOM_REACH):
            rank = (0 if chased else 1, dist if dist is not None else 0)
            if best is None or rank < best[0]:
                best = (rank, when, mob)
    return best[1:] if best is not None else None


def offscreen_boss(c, t):
    """O Aquila em sobrecarga e fora da tela pouco antes de t: (chefe, ms de sobrecarga) ou None. De fora da tela
    o golpe dele não chega ao replay (nem aparece no jogo), e em sobrecarga ele acerta de longe e cada vez mais
    forte."""
    at = t - OFFSCREEN_LAND_MS
    ms = c.overload_at(at)
    if ms is None or ms < OFFSCREEN_MIN_MS:
        return None
    for boss, e in c.entities.items():
        if e.kind == "mob" and e.job in AQUILA and c.in_sight(boss, at) is False:
            return boss, ms
    return None


def death_recap(c, aid, t):
    """O que aconteceu com `aid` nos 10 s antes de morrer em `t`."""
    recent = [h for h in c.hits if not h.out and h.dst_raw == aid and t - RECAP_MS <= h.t <= t + 300]
    hp = [s for s in c.hp_log.get(aid, []) if t - RECAP_MS <= s[0] <= t and s[1] is not None]
    # HP máx. muda com buffs; usa o maior valor visto (HP máx. informado ou HP atual)
    seen = [x for s in c.hp_log.get(aid, []) if s[0] <= t for x in (s[1], s[2]) if x]
    max_hp = max(seen) if seen else None
    killing = next((h for h in reversed(recent) if h.t <= t + 300 and t - h.t <= 3000 and h.dmg > 0), None)
    hp_before = None
    # quem matou nem sempre é o último golpe: a vida só cai ~1 s depois do pacote, e nesse meio tempo chegam golpes
    # menores (ex.: os reflexos seguintes da Dor Máxima). Vale o primeiro dos últimos LETHAL_MS que sozinho era
    # maior que a vida que encontrou, desde que a vítima não tenha aparecido viva depois de ele cair
    alive = [s for s in c.hp_log.get(aid, []) if s[1] is not None and s[1] > 1 and t - 60000 <= s[0] <= t]
    single = None
    for h in recent:
        if h.dmg <= 0 or h.miss or not t - LETHAL_MS <= h.t <= t + 300:
            continue
        found = [s[1] for s in alive if s[0] <= h.t]
        if found and h.dmg >= found[-1] and not any(s[0] > h.t + LAND_MS for s in alive):
            single = (h, found[-1])
            break
    if single is not None:
        killing, hp_before = single
    elif killing is not None:
        before = [s for s in hp if s[0] <= killing.t]
        hp_before = before[-1][1] if before else None
        # o pacote do golpe chega antes de a vida cair (às vezes mais de 1 s, ex.: Dor Máxima); uma cura no meio
        # muda a vida que ele encontrou, então vale a última leitura (com vida) antes da morte
        later = [s for s in hp if killing.t < s[0] < t and s[1] > 1]
        if later:
            hp_before = later[-1][1]
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
    # nenhum golpe explica a morte: a explosão de um monstro colado (os Robovacs do Aquila) ou o golpe do Aquila em
    # sobrecarga vindo de fora da tela
    special = special_src = special_t = overload_ms = None
    fusion_low = fusion and (hp_pct is None or hp_pct <= FUSION_KILL_PCT)
    if lethal is None and not fusion_low and (killing is None or unclear):
        boom = boom_near(c, aid, t, recent)
        off = None if boom is not None else offscreen_boss(c, t)
        if boom is not None:
            special, special_t, special_src = "boom", boom[0], boom[1]
        elif off is not None:
            special, special_t, special_src, overload_ms = "offscreen", t - OFFSCREEN_LAND_MS, off[0], off[1]
        if special is not None:
            hp_before = alive[-1][1] if alive else hp_before
            killing, unclear, overkill, fusion, fusion_cost = None, False, 0, False, None
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
    if special == "boom":
        rows.append(dict(rel=special_t - t, kind="dano", source=c.target_name(special_src),
                         name=meter.skill_name(meter.SELF_DESTRUCT) + _(" (sem número na tela)"),
                         dmg=None, hp=None, miss=False))
    elif special == "offscreen":
        rows.append(dict(rel=special_t - t, kind="dano", source=c.target_name(special_src),
                         name=_("golpe fora da tela"), dmg=None, hp=None, miss=False))
    rows.sort(key=lambda r: (r["rel"], r["kind"] != "dano"))
    hp_loss = None
    if len(hp) >= 2 and not recent and not traps:
        hp_loss = max(s[1] for s in hp) - hp[-1][1]
    if lethal is not None:
        killer, skill, hit = TRAP_NAME, _("Armadilha"), round(trap_est) if trap_est else 0
    elif special is not None:
        killer, hit = c.target_name(special_src), 0
        skill = meter.skill_name(meter.SELF_DESTRUCT) if special == "boom" else _("golpe fora da tela")
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
        no_hit=killing is None and lethal is None and special is None, hp_loss=hp_loss, unclear=unclear,
        fusion=fusion, hp_last=hp_last, hp_pct=hp_pct, fusion_cost=fusion_cost,
        special=special, special_src=special_src, overload_ms=overload_ms, kill_hit=killing,
    )


DEATH_CARD_MS = 5000      # o resumo de morte do widget olha os 5 s antes da morte
HEALED_FRAC = 0.95        # ...mas se a vida voltou a 95% ou mais nesse meio tempo, o que veio antes não conta
MAXPAIN_ATK = meter.MAXPAIN_ATK   # reflexo da Dor Máxima: ~11% de um golpe no chefe, no mesmo instante, em todos em volta
MAXPAIN_RATIO = (0.08, 0.14, 0.11)
MIXED_ELEMENT_SKILLS = {2217}   # Tetra Vortex: um golpe de cada propriedade (fogo, água, vento, terra)


def element_name(el):
    """Nome da propriedade para mostrar ('' quando não se sabe)."""
    if not el:
        return ""
    if el == "Mixed":
        return _("várias")
    import dedoduro
    return dedoduro.ELEMENT_PT.get(el, el)


def element_advice(defense, level=1, top=2):
    """Contra um alvo de propriedade `defense` (nível `level`): ([(ataque, %)] melhores, [(ataque, %)] a evitar),
    pela tabela de vantagem elemental do rAthena. A evitar = 50% ou menos."""
    import dedoduro
    table = (dedoduro.RATHENA.get("attr") or {}).get(str(max(1, min(4, level or 1)))) or {}
    rates = [(atk, row.get(defense)) for atk, row in table.items() if row.get(defense) is not None]
    if not rates:
        return [], []
    best_pct = max(p for _a, p in rates)
    best = sorted([(a, p) for a, p in rates if p == best_pct or (p > 100 and p >= best_pct - 25)], key=lambda r: -r[1])
    if best_pct <= 100:
        best = []
    avoid = sorted([(a, p) for a, p in rates if p <= 50], key=lambda r: r[1])
    return best[:top], avoid[:top]


def my_attack_element(c, t, window=15000):
    """Propriedade da maior parte do dano de quem grava nos últimos `window` ms (skill de elemento fixo, ou o da arma:
    conversor/encantamento ativo, senão Neutro). None sem golpes."""
    import dedoduro
    agg = {}
    st = [(ef, s, e, c.status_val.get((a, ef, s), -1)) for a, ef, s, e in c.statuses(c.me)
          if ef in dedoduro.ENDOWS or ef == dedoduro.WEAPONPROPERTY]
    for h in c.hits:
        if not h.out or h.src != c.me or h.dmg <= 0 or not t - window <= h.t <= t:
            continue
        el = dedoduro.hit_element(h.skill)
        if el == "Weapon":
            el = "Neutral"
            for ef, s, e, v in st:
                if s <= h.t <= e:
                    if ef in dedoduro.ENDOWS:
                        el = dedoduro.ENDOWS[ef]
                    elif 0 <= v < len(dedoduro.ELEMENTS):
                        el = dedoduro.ELEMENTS[v]
        agg[el] = agg.get(el, 0) + h.dmg
    return max(agg, key=agg.get) if agg else None


def attack_element(c, src, skill):
    """Propriedade de um ataque de monstro: a fixa da skill; ataque básico e skills que usam a arma são neutros
    (monstro não tem arma). Para jogadores (arma desconhecida) devolve None."""
    import dedoduro                     # importa aqui: dedoduro importa este módulo
    if skill in MIXED_ELEMENT_SKILLS:
        return "Mixed"
    el = dedoduro.hit_element(skill)
    if el != "Weapon":
        return el
    e = c.entities.get(src)
    return None if src == c.me or (e is not None and e.kind == "pc") else "Neutral"


def death_window_start(c, aid, t, max_hp=None, window=DEATH_CARD_MS):
    """Desde quando o dano conta para a morte em `t`: os `window` ms antes, cortados na última vez que a vida
    voltou a 95% ou mais (ex.: tomou um Cometa, se curou e morreu num Tetra Vortex: só o Tetra conta) ou
    na morte anterior (morreu, voltou e morreu de novo)."""
    start = t - window
    prev = None
    for st, hp, mx in c.hp_log.get(aid, []):
        if hp is None or st >= t:
            continue
        top = mx or max_hp
        # só uma subida até 95%+ é cura: uma leitura de vida cheia logo depois de um golpe pode ser só o dano que
        # ainda não caiu (o jogo manda o golpe antes de tirar a vida), e esse golpe tem que contar
        if start < st and top and hp >= HEALED_FRAC * top and prev is not None and hp > prev:
            start = st
        prev = hp
    for dt, a in c.death_log:
        if a == aid and start < dt < t:
            start = dt
    return start


def death_card(c, aid, t, window=DEATH_CARD_MS):
    """Resumo curto de uma morte para o widget: o golpe final e as principais fontes de dano nos `window` ms antes
    (desde a última cura até 95% da vida, se houve), agrupadas por (monstro, skill), com a propriedade do ataque e a
    parte de cada uma no dano recebido."""
    rec = death_recap(c, aid, t)
    start = death_window_start(c, aid, t, rec["max_hp"], window)
    groups = collections.OrderedDict()

    def add(name, skill, element, dmg, src=None):
        g = groups.setdefault((name, skill), dict(source=name, skill=skill, element=element, dmg=0, hits=0,
                                                  mobs=set(), killing=False, job=None))
        g["dmg"] += dmg
        g["hits"] += 1
        if src is not None:
            g["mobs"].add(src)
            e = c.entities.get(src)
            if g["job"] is None and e is not None and e.kind != "pc" and src != c.me:
                g["job"] = e.job

    # o golpe que matou sempre conta: às vezes a vida só cai mais de 1 s depois do pacote do golpe, e uma cura no
    # meio desse tempo pareceria "antes" dele
    kh = rec["kill_hit"] or next((h for h in reversed(c.hits) if not h.out and h.dst_raw == aid and h.dmg > 0
                                  and not h.miss and t - 3000 <= h.t <= t + 300), None)
    for h in c.hits:
        if h.out or h.dst_raw != aid or h.miss or h.dmg <= 0 or not (start < h.t <= t + 300 or h is kh):
            continue
        add(c.name_of(h.src), meter.skill_name(h.skill), attack_element(c, h.src, h.skill), h.dmg, h.src)
    for r in rec["rows"]:                # armadilhas e HP perdido sem golpe visível
        if r["kind"] == "dano" and t + r["rel"] > start and r["dmg"] and r["source"] in (
                TRAP_NAME, _("Sem golpe visível")):
            add(r["source"], _("Armadilha") if r["source"] == TRAP_NAME else _("HP perdido"), None, r["dmg"])
    hp_seen = [(st, hp) for st, hp, mx in c.hp_log.get(aid, []) if start <= st <= t + 300 and hp is not None]
    if rec["special"]:
        # explosão sem pacote de dano / golpe de fora da tela: levou a vida que restava
        add(c.name_of(rec["special_src"]), rec["skill"], None, rec["hp_before"] or 0, rec["special_src"])
    elif not groups and rec["no_hit"]:
        # a vida caiu sem nenhum golpe no replay (efeito do mapa, algo fora da tela...): mostra quanto caiu
        before = [hp for st, hp in hp_seen if st < t and hp]
        if before:
            add(_("Sem golpe visível"), _("HP perdido"), None, before[-1])
    fusion = None
    if rec["fusion"]:
        # União Solar, Lunar e Estelar: cada ataque custa 2% da vida e atacar com 20% ou menos mata. O que a vida
        # caiu além dos golpes é dela, e é ela que matou
        drops = sum(max(0, a[1] - b[1]) for a, b in zip(hp_seen, hp_seen[1:]))
        hit_dmg = sum(g["dmg"] for g in groups.values())
        cost = max(0, drops - hit_dmg) or rec["hp_last"] or 0
        add(_("União Solar"), _("custo de HP dos ataques"), None, cost)
        fusion = groups[(_("União Solar"), _("custo de HP dos ataques"))]
    total = sum(g["dmg"] for g in groups.values())
    killer = c.name_of(rec["special_src"] if rec["special"] else (kh.src if kh is not None else 0))
    for g in groups.values():
        g["share"] = g["dmg"] / float(total) if total else 0.0
        g["count"] = len(g["mobs"])
        if fusion is not None:
            g["killing"] = g is fusion
        else:
            g["killing"] = (g["source"] == (TRAP_NAME if rec["trap"] else killer) and g["skill"] == rec["skill"])
        del g["mobs"]
    sources = sorted(groups.values(), key=lambda g: -g["dmg"])
    # Dor Máxima: o golpe no chefe que foi refletido (mesmo instante, o reflexo é ~11% dele)
    reflected = None
    if kh is not None and kh.skill == MAXPAIN_ATK and fusion is None:
        lo, hi, mid = MAXPAIN_RATIO
        trig = [h for h in c.hits if h.out and h.dst == kh.src and h.dmg > 0 and kh.t - 60 <= h.t <= kh.t + 30
                and lo <= kh.dmg / float(h.dmg) <= hi]
        if trig:
            h = min(trig, key=lambda x: abs(kh.dmg / float(x.dmg) - mid))
            reflected = dict(who=c.name_of(h.src), mine=h.src == aid, skill=meter.skill_name(h.skill), dmg=h.dmg)
    # o monstro do desenho: o do golpe final; numa armadilha, o que mais bateu; na União, nenhum (foi ela que matou)
    kill = next((g for g in sources if g["killing"]), None)
    sprite_mob = kill["job"] if kill is not None and kill["job"] else (None if fusion is not None else next(
        (g["job"] for g in sources if g["job"]), None))
    # quantas vezes `aid` já morreu neste encontro (contando esta): o título do widget vai mudando
    encs = [e for e in c.encounters() if e.start <= t]
    since = encs[-1].start if encs else 0
    nth = max(1, sum(1 for dt, a in c.death_log if a == aid and since <= dt <= t))
    return dict(rec, sources=sources, total=total, hits=sum(g["hits"] for g in sources), window=t - start, nth=nth,
                healed=start > t - window, reflected=reflected,
                killing_element=kill["element"] if kill is not None else None, sprite_mob=sprite_mob)


def _killer_aid(c, aid, t):
    """Quem deu o último golpe com dano (até 3 s antes da morte)."""
    for h in reversed(c.hits):
        if not h.out and h.dst_raw == aid and h.dmg > 0 and t - 3000 <= h.t <= t + 300:
            return h.src
    return None


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


# --- áreas no chão ------------------------------------------------------------------

AREA_ERASERS = {483, 288, 285, 286, 287}   # Ganbantein, Proteger Terreno e os três campos (um troca o outro)
AREA_ERASE_MS = 300


def cell_players(c, cell, t, aids=None):
    """Jogadores que estavam em cima da célula no instante t (ou colados nela, a 1 célula, se ninguém estava
    exatamente em cima). Vazio quando não há ninguém."""
    if cell is None:
        return []
    if aids is None:
        aids = [a for a in list(c.pos_t) if a == c.me or (a in c.entities and c.entities[a].kind == "pc")]
    best, out = 2, []
    for a in aids:
        p = c.pos_at(a, t)
        if p is None:
            continue
        d = max(abs(p[0] - cell[0]), abs(p[1] - cell[1]))
        if d < best:
            best, out = d, [a]
        elif d == best:
            out.append(a)
    return out


def ground_use_on(c, u, aids=None):
    """Em cima de quem caiu uma skill usada numa célula (`u` é um uso de c.uses sem alvo). O Ganbantein do
    Betelgeuse cai na célula de um jogador (94 de 106 nos replays), quase sempre em quem o chefe está batendo."""
    return cell_players(c, c.ground_cells.get((u[0], u[2], u[4])), u[0], aids)


def area_eraser(c, area, t):
    """O uso (de c.uses) que apagou a área no instante t: alguém usou, na mesma hora, uma skill que apaga ou troca
    o que está no chão (Ganbantein, Proteger Terreno, outro campo). None quando só acabou o tempo."""
    for u in c.uses:
        if u[3] == 0 and abs(u[0] - t) <= AREA_ERASE_MS and u[4] in AREA_ERASERS:
            if u[4] == area["skill"] and abs(u[0] - area["t"]) <= AREA_ERASE_MS:
                continue                          # o próprio lançamento desta área
            return u
    return None


def area_end_cause(c, area, t):
    """Texto de por que a área saiu do chão no instante t (vazio quando só acabou o tempo). Quando foi skill de
    monstro, diz também em cima de quem ela caiu."""
    u = area_eraser(c, area, t)
    if u is None:
        return ""
    text = _("apagada por %s (%s)") % (meter.skill_name(u[4]), c.name_of(c.resolve(u[2])))
    if not c.is_friendly(u[2]):
        on = ground_use_on(c, u)
        if on:
            text += _(", que caiu em %s") % ", ".join(c.name_of(a) for a in on)
    return text


def equipment(c, t):
    return [dict(slot=label, item=meter.item_text(it), item_id=it.item_id) for label, it in c.equipment_at(t)]


EQUIP_MERGE_MS = 3000         # trocas seguidas (um conjunto inteiro) contam como uma


def equip_moments(c):
    """[(t, [rótulos dos slots que mudaram])]: o início da gravação e cada troca de equipamento de quem grava."""
    out = [(0, [])]
    prev = None
    for t, state in c.equip_log:
        if prev is None:
            prev = state
            continue
        changed = [label for bit, label in meter.EQUIP_SLOTS if state.get(bit) is not prev.get(bit)]
        prev = state
        if not changed:
            continue
        if len(out) > 1 and t - out[-1][0] <= EQUIP_MERGE_MS:
            out[-1] = (t, out[-1][1] + [x for x in changed if x not in out[-1][1]])
        else:
            out.append((t, changed))
    return out
