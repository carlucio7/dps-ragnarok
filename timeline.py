"""Linha do tempo de uma luta: o que estava no chefe, quem morreu, o que o chefe usou e o dano no tempo.

Os dados saem daqui prontos para a aba "Linha do tempo" (analysis_ui), que sobrepõe gráficos e marcações:

  - faixas: status no chefe (Garra Sombria, Pólen, Avanço Sísmico, Dor Máxima...), cada uma com os trechos ativos;
  - pontos: mortes, ressurreições, skills do chefe, dano refletido pela Dor Máxima, usos da Garra Sombria,
    golpes fortes e Elo Celestial;
  - linhas: começo de cada fase e do clímax;
  - golpes: dano de cada jogador no chefe, dano recebido e HP estimado do chefe, para as curvas.
"""

import collections

import analysis as an
import dedoduro as dd
import meter
from i18n import _

PAD_MS = 3000                 # folga antes e depois da luta
REFLECT_JOIN_MS = 150         # reflexos da mesma Dor Máxima chegam juntos: viram um ponto só
RELIEVE = 1166                # Alívio no chefe: val1 = redução de dano em % (10 por nível; cada Alma viva +1 nível)
HEAL = 28                     # Curar: o servidor manda curas de efeitos sem quem lançou (fonte 0)
# curas sem autor: status no curado -> skill que cura sozinha (Mediale Votum a cada 2 s, Talismã de Proteção a cada 3 s)
HEAL_EFFECTS = ((1197, 5269), (1356, 5418))
HP_STEP_MS = 1000             # sem golpes, a curva de HP ganha um ponto por segundo (a regeneração aparece)
# faixas ligadas ao abrir (as outras aparecem desligadas na lista)
DEFAULT_ON = {dd.DARK_CLAW, dd.FLORESCER, 1402, dd.MAX_PAIN}
# cores das faixas (o resto usa a paleta dos jogadores)
LANE_COLORS = {dd.DARK_CLAW: "#a78bfa", dd.FLORESCER: "#4ade80", 1402: "#f59e0b", dd.MAX_PAIN: "#ef4444",
               1142: "#22d3ee", dd.VENOM_IMPRESS: "#a3e635"}
EVENT_COLORS = {"boss": "#f97316", "reflect": "#ef4444", "claw": "#a78bfa", "strong": "#fbbf24", "elo": "#38bdf8",
                "res": "#4ade80"}
# áreas no chão: cor de cada skill, as que começam desligadas e o que apaga uma área (skills usadas numa célula)
AREA_COLORS = {285: "#fb923c", 286: "#38bdf8", 287: "#bef264", 288: "#94a3b8", 405: "#e2e8f0", 2465: "#f87171",
               2466: "#60a5fa", 2467: "#a3e635", 2468: "#d6a38f"}
AREA_OFF = {288}              # Proteger Terreno não muda o dano: fica na lista, desligado


def fights(c, rng=None):
    """[(rótulo, chave)] das lutas contra chefe, MVPs primeiro."""
    return [(dd.fight_label(c, f), f["key"]) for f in dd.boss_fights(c, rng)]


def _lane(key, name, kind, color, on, items):
    return dict(key=key, name=name, kind=kind, color=color, on=on, items=items)


def build(c, key, rng=None):
    """Tudo o que a aba precisa da luta contra `key` (chave do chefe, como no Dedo Duro)."""
    if not any(h.out and h.dst == key and an._in(rng, h.t) for h in c.hits):
        return None
    x = dd.Ctx(c, key, rng)
    t0, t1 = x.start - PAD_MS, x.end + PAD_MS
    players = x.party + [a for a in x.others if a not in x.party]
    pset = set(players) | {c.me}

    # golpes no chefe (curvas por jogador e HP) e dano recebido pelos jogadores
    out = [(h.t, h.src, h.dmg) for h in x.hits]
    taken = [(h.t, h.dst, h.dmg) for h in c.hits if not h.out and t0 <= h.t <= t1 and h.dst in pset]
    # HP estimado: começa cheio, perde o dano visto e regenera (fração do HP por segundo) até encher. Alguns chefes
    # só regeneram numa forma e perdem vida sem pacote de dano (an.BOSS_MODEL: Aquila em sobrecarga / quebra de defesa)
    e = c.entities.get(key)
    mob = e.job if e is not None else 0
    model = an.BOSS_MODEL.get(mob) if x.hp_table else None
    regen = (an.boss_regen(model, mob, x.hp) if model else an.BOSS_REGEN.get(mob, 0)) if x.hp_table else 0
    wins = an.regen_windows(c, x.boss_aids, model, x.start, x.end) if model else None
    hidden = an.hidden_losses(c, x.boss_aids, model, x.start, x.end) if model else []

    def gained(a, b):                      # regeneração entre a e b (só dentro das janelas, se houver)
        if wins is None:
            return regen * (b - a) / 1000.0
        return regen * sum(max(0, min(b, e2) - max(a, s2)) for s2, e2 in wins) / 1000.0
    steps = sorted([(t, d, 0.0) for t, _a, d in out] + [(t, 0, model["hidden"]) for t in hidden] + [(x.end, 0, 0.0)])
    hp, frac, last = [(x.start, 1.0)], 1.0, x.start
    for t, d, lost in steps:
        while regen and t - last > HP_STEP_MS and frac < 1.0:
            frac = min(1.0, frac + gained(last, last + HP_STEP_MS))
            last += HP_STEP_MS
            hp.append((last, frac))
        frac = max(0.0, min(1.0, frac + gained(last, t)) - (d / x.hp if x.hp else 0.0) - lost) if x.hp else 1.0
        last = t
        hp.append((t, frac))
    if x.killed:
        hp.append((x.end, 0.0))

    lanes = []
    # status no chefe: as regras do Dedo Duro + a Dor Máxima
    rules = [dd.Rule([dd.MAX_PAIN])] + dd.BOSS_DEBUFFS
    for i, rule in enumerate(rules):
        spans = [(max(s, t0), min(e, t1)) for s, e in dd._merge(x.boss_spans(rule.ids)) if e >= t0 and s <= t1]
        if spans:
            color = LANE_COLORS.get(rule.first, an_palette(i))
            lanes.append(_lane("st%d" % rule.first, rule.name, "span", color, rule.first in DEFAULT_ON, spans))
    # Alívio do chefe: um trecho por nível, com a redução de dano (as Almas vivas sobem o nível)
    relief = sorted((max(s, t0), min(e, t1), "-%d%%" % c.status_val.get((a, RELIEVE, s), 0))
                    for a, ef, s, e in c.statuses() if a in x.boss_aids and ef == RELIEVE and e >= t0 and s <= t1)
    if relief:
        lanes.insert(0, _lane("st%d" % RELIEVE, _("Alívio (redução de dano)"), "span", "#94a3b8", True, relief))
    # áreas no chão (Vulcão, Insígnias, Proteger Terreno, Prisão de Teia): uma faixa por skill, com os trechos em
    # que havia alguma no chão; cada começo e fim vai para a lista de eventos com quem pôs e o que a apagou
    area_spans, area_events = collections.defaultdict(list), []
    for a in c.areas:
        name = meter.skill_name(a["skill"])
        for s, e in c.area_spans(a):
            if e < t0 or s > t1:
                continue
            area_spans[a["skill"]].append((max(s, t0), min(e, t1)))
            who = c.resolve(a["src"])
            base = dict(kind="area", lane="ar%d" % a["skill"], aid=who, who=c.name_of(who), value=None)
            if s >= t0:
                area_events.append(dict(base, t=s, what=_("No chão: %s começou") % name,
                                        detail=_("nível %d") % a["level"]))
            if e <= t1 and e < c.now:
                cause = an.area_end_cause(c, a, e)
                area_events.append(dict(base, t=e, what=_("No chão: %s acabou") % name,
                                        detail=_("durou %s") % dd._secs(e - s) + (" · " + cause if cause else "")))
    for skill, spans in sorted(area_spans.items()):
        lane = _lane("ar%d" % skill, meter.skill_name(skill), "span", AREA_COLORS.get(skill, "#94a3b8"),
                     skill not in AREA_OFF, [tuple(sp) for sp in dd._merge(spans)])
        lane["area"] = True
        lanes.append(lane)

    events = []

    def ev(t, kind, lane, aid, what, detail="", value=None):
        who = c.name_of(aid) if aid is not None else (_("chefe") if kind in ("boss", "reflect") else "")
        events.append(dict(t=t, kind=kind, lane=lane, aid=aid, who=who, what=what, detail=detail, value=value))

    # mortes e ressurreições dos jogadores
    for d in an.deaths(c, (t0, t1)):
        if d["aid"] not in pset:
            continue
        ev(d["t"], "death", "deaths", d["aid"], _("morreu"), death_cause(d))
    for t, a in c.res_log:
        if t0 <= t <= t1 and a in pset:
            ev(t, "res", "deaths", a, _("ressuscitou"))
    # skills que o chefe usou (o dano que a Dor Máxima devolve fica nos pontos de reflexo)
    seen = set()
    for u in c.uses:
        if t0 <= u[0] <= t1 and (u[1] in x.boss_aids or u[1] == key) and u[4] != 717:
            k = (u[0] // 300, u[4])
            if k not in seen:
                seen.add(k)
                # skill jogada numa célula (Ganbantein, Chuva de Meteoros): em cima de quem caiu
                on = an.ground_use_on(c, u, pset) if u[3] == 0 else []
                ev(u[0], "boss", "boss", None, meter.skill_name(u[4]),
                   _("em cima de %s") % ", ".join(c.name_of(a) for a in on) if on else "")
                if on:
                    events[-1]["target"] = on[0]
    # dano devolvido pela Dor Máxima: um ponto por onda, com o total e quantos jogadores levaram
    back = sorted((h for h in c.hits if not h.out and h.src == key and h.skill in dd.REFLECT_SKILLS
                   and t0 <= h.t <= t1), key=lambda h: h.t)
    wave = []
    for h in back + [None]:
        if wave and (h is None or h.t - wave[-1].t > REFLECT_JOIN_MS):
            total = sum(w.dmg for w in wave)
            if total > 0:
                ev(wave[0].t, "reflect", "reflect", None, _("Dor Máxima devolveu %s") % an._full(total),
                   _("%d jogadores atingidos, maior: %s") % (len({w.dst for w in wave}), an._full(max(w.dmg for w in wave))),
                   value=total)
            wave = []
        if h is not None:
            wave.append(h)
    # Garra Sombria de cada Executor
    for a in players:
        if dd.JOB_SKILLS.get(dd.job_id(c, a), set()) & dd.DARK_CLAW_SKILLS:
            for t, _cd in dd.claw_casts(x, a):
                if t0 <= t <= t1:
                    ev(t, "claw", "claw", a, _("usou %s") % meter.skill_name(5001))
    # golpes fortes (mesmo limite do Dedo Duro) e Elo Celestial
    limit = dd.STRONG_HIT * x.hp
    for h in x.hits:
        if limit and h.dmg >= limit:
            ev(h.t, "strong", "strong", h.src, meter.skill_name(h.skill), an._full(h.dmg), value=h.dmg)
    for u in c.uses:
        if t0 <= u[0] <= t1 and u[4] == dd.ELO_SKILL and u[2] in pset:
            ev(u[0], "elo", "elo", u[2], _("usou %s") % meter.skill_name(dd.ELO_SKILL))
    # eventos individuais (só na lista): cada golpe e cada skill, dos jogadores e dos monstros
    for h in c.hits:
        if not t0 <= h.t <= t1:
            continue
        what = meter.skill_name(h.skill) if h.skill else _("ataque básico")
        if h.miss:
            detail = _("errou %s") % c.name_of(h.dst_raw)
        else:
            detail = _("%s em %s") % (an._full(h.dmg), c.name_of(h.dst_raw)) + (_(" (crítico)") if h.crit else "")
        if h.out and h.src in pset:
            if limit and h.dmg >= limit and h.dst == key:
                detail += " · " + _("golpe forte")
            ev(h.t, "hit", "hits", h.src, what, detail, value=h.dmg)
            events[-1]["target"] = h.dst_raw
        elif not h.out:
            ev(h.t, "mobhit", "mobhits", None, what, detail, value=h.dmg)
            events[-1].update(who=c.name_of(h.raw), mob=True, target=h.dst)
    effects = collections.defaultdict(list)       # curado -> [(status, início, fim)] dos efeitos que curam sozinhos
    for a, ef, st, en in c.statuses():
        if ef in dict(HEAL_EFFECTS):
            effects[a].append((ef, st, en))
    for u in c.uses:
        if t0 <= u[0] <= t1 and u[4] != 717:
            tgt = _(" em %s") % c.name_of(u[3]) if u[3] and u[3] != u[2] else ""
            if not u[2] and u[3] in pset:
                # sem quem lançou: o jogo mostra o efeito no curado (Mediale Votum, Talismã de Proteção...)
                if u[4] == HEAL:
                    seen = [sk for ef, sk in HEAL_EFFECTS
                            if any(e2 == ef and st <= u[0] <= en for e2, st, en in effects.get(u[3], ()))]
                    src = " / ".join(meter.skill_name(sk) for sk in (seen or [sk for _ef, sk in HEAL_EFFECTS]))
                    ev(u[0], "pskill", "pskills", u[3], _("recebeu cura de um efeito"),
                       (_("de %s") if seen else _("provavelmente de %s")) % src)
                else:
                    ev(u[0], "pskill", "pskills", u[3], _("recebeu %s de um efeito") % meter.skill_name(u[4]), "")
                events[-1]["target"] = u[3]
                continue
            if u[2] in pset or c.is_friendly(u[2]):
                ev(u[0], "pskill", "pskills", u[1] if u[1] in pset else u[2], _("usou %s") % dd.use_name(c, u),
                   ((c.name_of(u[2]) if u[2] != u[1] else "") + tgt).strip())
                events[-1]["target"] = u[3]
            else:
                on = an.ground_use_on(c, u, pset) if u[3] == 0 else []
                if on:
                    tgt = _("em cima de %s") % ", ".join(c.name_of(a) for a in on)
                ev(u[0], "mobskill", "mobskills", None, _("usou %s") % meter.skill_name(u[4]), tgt.strip())
                events[-1].update(who=c.name_of(u[2]), mob=True, target=on[0] if on else u[3])
    for u in c.casts:
        # conjuração instantânea (0 s, ex.: Cardeal com conjuração instantânea) só repete o "usou" que vem junto
        if t0 <= u[0] <= t1 and u[5] > 0:
            what = _("conjurou %s (%s)") % (meter.skill_name(u[4]), dd._secs(u[5]))
            tgt = _("em %s") % c.name_of(u[3]) if u[3] and u[3] != u[2] else ""
            if u[2] in pset or c.is_friendly(u[2]):
                ev(u[0], "pskill", "pskills", u[1] if u[1] in pset else u[2], what, tgt)
                events[-1]["target"] = u[3]
            else:
                ev(u[0], "mobskill", "mobskills", None, what, tgt)
                events[-1].update(who=c.name_of(u[2]), mob=True, target=u[3])
    for e_ in events:
        if e_["kind"] in ("boss", "reflect"):
            e_["mob"] = True
    events.sort(key=lambda e: e["t"])

    used = {e["lane"] for e in events}
    for k, name, color in (("deaths", _("Mortes"), None),            # None: cor do texto do tema ("boss", _("Skills do chefe"), EVENT_COLORS["boss"]),
                           ("reflect", _("Dano refletido"), EVENT_COLORS["reflect"]),
                           ("claw", _("Usos da %s") % meter.skill_name(5001), EVENT_COLORS["claw"]),
                           ("strong", _("Golpes fortes (≥ 0,5% do HP)"), EVENT_COLORS["strong"]),
                           ("elo", meter.skill_name(dd.ELO_SKILL), EVENT_COLORS["elo"])):
        if k in used:
            lanes.append(_lane(k, name, "point", color, k != "elo",
                               [e for e in events if e["lane"] == k]))
    # só na lista (são muitos para o gráfico). As skills dos jogadores começam ligadas: a lista segue os jogadores
    # marcados (quem gravou, de início), então dá para ver cada skill usada, inclusive as novas como Poder Esmagador
    # "dano" = cada golpe que acertou ou errou; "outras skills" = o que foi usado sem causar dano (buffs, curas,
    # debuffs) e as conjurações
    for k, name, color, on in (("hits", _("Dano dos jogadores, golpe a golpe"), None, False),
                               ("pskills", _("Outras skills dos jogadores"), None, True),
                               ("mobhits", _("Dano dos monstros, golpe a golpe"), EVENT_COLORS["boss"], False),
                               ("mobskills", _("Outras skills dos monstros"), EVENT_COLORS["boss"], False)):
        if k in used:
            lanes.append(_lane(k, name, "list", color, on, []))
    starts = [(p["appear"], x.phase_name(p) if x.multi else None) for p in x.phases]
    marks = [(t, label or _("Início")) for t, label in starts]
    if x.climax < x.end:
        marks.append((x.climax, _("Clímax")))
    dmg = collections.Counter(a for _t, a, _d in out)
    # quem bateu, do maior dano para o menor, e depois o resto do grupo, que não bate mas aparece na lista de
    # eventos (o Cardeal com a Lex Aeterna, por exemplo)
    order = sorted(dmg, key=lambda a: -dmg[a])
    for a in [c.me] + list(x.party):
        if a not in dmg and a not in order:
            order.append(a)
    return dict(key=key, name=c.target_name(key), t0=t0, t1=t1, start=x.start, end=x.end, killed=x.killed,
                out=out, taken=taken, hp=hp, hp_known=True, hp_max=x.hp, hp_label=x.hp_label, lanes=lanes,
                events=events,
                marks=sorted(marks), players=order, party=set(x.party), dmg=dmg,
                names={a: c.name_of(a) for a in order}, starts=starts, phase_dmg=dd.phase_damage(x),
                lane_events=status_events(c, lanes) + area_events)


def status_events(c, lanes):
    """Começo e fim de cada trecho das faixas de status, para a lista de eventos."""
    out = []
    for lane in lanes:
        if lane["kind"] != "span" or lane.get("area"):
            continue
        for item in lane["items"]:
            s, e = item[0], item[1]
            # status que está NO chefe (Garra Sombria, Pólen...): quem pôs nem sempre aparece, então "Quem" fica vazio
            if len(item) > 2:                   # trecho com valor (Alívio): só a mudança, com o valor novo
                out.append(dict(t=s, kind="status", lane=lane["key"], aid=None, who="",
                                what=_("No chefe: %s %s") % (lane["name"], item[2]),
                                detail=_("durou %s") % dd._secs(e - s), value=None))
                continue
            out.append(dict(t=s, kind="status", lane=lane["key"], aid=None, who="",
                            what=_("No chefe: %s começou") % lane["name"], detail="", value=None))
            out.append(dict(t=e, kind="status", lane=lane["key"], aid=None, who="",
                            what=_("No chefe: %s acabou") % lane["name"], detail=_("durou %s") % dd._secs(e - s),
                            value=None))
    return out


def death_cause(d):
    """Texto curto da causa da morte (como na aba Mortes)."""
    if d["trap"]:
        return _("Armadilha do mapa")
    if d["fusion"]:
        return _("União Solar, Lunar e Estelar (atacou com %s de HP)") % (
            "%d%%" % round(d["hp_pct"] * 100) if d.get("hp_pct") is not None else "?")
    if d["no_hit"]:
        return _("sem golpe visível (efeito, debuff ou algo fora da tela)")
    if d["special"] == "boom":
        return _("%s · %s (dano fixo, sem número na tela)") % (d["skill"], d["killer"])
    if d["special"] == "offscreen":
        return _("provável golpe de %s fora da tela (sobrecarga há %d s)") % (
            d["killer"], round(d["overload_ms"] / 1000.0))
    return "%s · %s · %s" % (d["skill"], d["killer"], an._full(d["hit"]))


def series(points, a, b, bucket, window):
    """Média móvel (centrada, `window` ms) por segundo de [(t, valor)] em baldes de `bucket` ms entre a e b."""
    n = max(1, int((b - a) // bucket) + 1)
    sums = [0.0] * n
    for t, v in points:
        if a <= t < a + n * bucket:
            sums[int((t - a) // bucket)] += v
    k = max(1, int(round(window / bucket)))
    half = k // 2
    pre = [0.0]
    for s in sums:
        pre.append(pre[-1] + s)
    out = []
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i - half + k)
        out.append((pre[hi] - pre[lo]) * 1000.0 / (k * bucket))
    return [a + i * bucket for i in range(n)], out


def an_palette(i):
    pal = ["#22d3ee", "#f472b6", "#a3e635", "#d6a38f", "#94a3b8", "#2dd4bf", "#e879f9", "#fde047"]
    return pal[i % len(pal)]
