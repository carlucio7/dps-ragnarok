"""Dedo Duro: o que faltou e o que deu errado em cada luta contra chefe.

Para cada chefe (MVPs primeiro), separado por fase e só no "clímax" da luta (depois que o
chefe perdeu os primeiros 10% do HP, quando o grupo já devia estar pronto):

  - buffs de grupo que faltaram em quem bate (só se a classe que dá o buff está no grupo);
  - debuffs que faltaram no chefe (idem), e a Garra Sombria sempre ativa contra Dor Máxima;
  - buffs de recarga longa ou de AP que sumiram de uma fase para outra ou depois de morrer;
  - quem ficou mais de 2 s morto até ser ressuscitado;
  - elemento: fogo durante o Florescer e ataques com desvantagem elemental;
  - arma com veneno x chefe com Potencializar Veneno;
  - quem bateu forte antes da Garra Sombria da fase e Mestre Celestial sem o Elo Celestial.

Quem está no grupo e quem está fora ficam em listas separadas: buffs de quem está fora do
grupo não chegam no replay, então para eles só dá para ver dano, mortes e skills.

Buffs dos outros que já estavam ativos quando a gravação começou só aparecem quando acabam
(só os seus vêm prontos no início). Até o primeiro aviso de um status, perto do começo da
gravação, o estado dele é desconhecido ("?") e não vira acusação.
"""

import collections

import analysis as an
import i18n
import meter
from fmt import dec, num
from i18n import _

RATHENA = meter._load("rathena.json")
JOB_SKILLS = {int(k): set(v.get("skills", ())) for k, v in (RATHENA.get("jobs") or {}).items()}
CLASS_SKILLS = set().union(*JOB_SKILLS.values()) if JOB_SKILLS else set()
SKILL_DB = RATHENA.get("skills") or {}
MOB_DB = RATHENA.get("mobs") or {}
ATTR = RATHENA.get("attr") or {}

CLIMAX_HP = 0.10              # ignora os primeiros 10% do HP do chefe (o grupo ainda está se preparando)
DEAD_LIMIT_MS = 2000          # mais que isso morto antes de voltar = demorou
WIPE_MS = 7000                # mais que isso morto = provável wipe (o grupo vai se reagrupar): fica fora do relatório
BAD = 0.5                     # tempo ativo no clímax abaixo disso = faltou
DARK_CLAW_MIN = 0.9           # contra Dor Máxima a Garra Sombria tem que ficar o tempo todo
POLLEN_MIN = 0.9              # o Pólen (Florescer) também: sem ele o fogo perde o dobro de dano
PHASE_LATE_MS = 4000          # debuff que chegou mais que isso depois do começo da fase = demorou
DPS_SHARE = 0.02              # quem fez menos que isso do dano do grupo não conta como atacante
MIN_WINDOW_MS = 5000          # trechos menores que isso não dão para julgar
BACK_MS = 15000               # buff que não voltou até 15 s depois de ressuscitar = perdido
UNSEEN_MS = 360000            # um buff dado antes de gravar dura no máximo isso (5–6 min)
ENDOW_UNSEEN_MS = 1200000     # conversores e encantamentos de arma duram até 20 min
LONG_CD_MS, BIG_AP = 20000, 50
HARD_CD_MS = 60000            # perdido ao morrer só é "difícil de renovar" com recarga longa ou AP alto
ALWAYS_MIN = 0.9              # buffs que têm que ficar o tempo todo (Manejo Perfeito, Talismã dos Elementos)
SHORT_MS = 60000              # buffs de 60 s ou menos: renovar toda hora é difícil, então faltar é só atenção
UNKNOWN = "?"
SEV_TEXT = {2: _("● grave"), 1: _("◐ atenção"), 0: _("○ info")}

ELEMENTS = ["Neutral", "Water", "Earth", "Fire", "Wind", "Poison", "Holy", "Dark", "Ghost", "Undead"]   # id do jogo
ELEMENT_PT = {"Neutral": _("Neutro"), "Water": _("Água"), "Earth": _("Terra"), "Fire": _("Fogo"), "Wind": _("Vento"),
              "Poison": _("Veneno"), "Holy": _("Sagrado"), "Dark": _("Sombrio"), "Ghost": _("Fantasma"), "Undead": _("Maldito")}
# Chefes que o rAthena não tem (conferido no Divine Pride)
BOSS_ELEMENTS = {20994: ("Neutral", 2)}          # Betelgeuse
# Status que trocam o elemento da arma (encantamentos, conversores e poções de ataque elemental)
ENDOWS = {90: "Fire", 91: "Water", 92: "Wind", 93: "Earth", 97: "Undead", 146: "Dark", 148: "Ghost", 17: "Holy",
          6: "Poison", 897: "Neutral", 898: "Water", 899: "Earth", 900: "Fire", 901: "Wind", 902: "Poison",
          903: "Holy", 904: "Dark", 905: "Ghost", 906: "Undead"}
WEAPONPROPERTY = 64           # conversores: val1 = id do elemento
ENDOW_IDS = set(ENDOWS) | {WEAPONPROPERTY}
POISON_WEAPON = {341, 6}      # Aplicar Toxina, Envenenar Arma
POISON_SKILLS = {2027, 138}   # quem tem essas skills pode envenenar a arma
VENOM_IMPRESS = 328           # Potencializar Veneno
DARK_CLAW = 730               # Garra Sombria
DARK_CLAW_SKILLS = {5001, 5294}   # Garra Sombria e a versão do Executor (Corvo Sombrio Fatal)
GAP_MIN_MS = 2000             # buraco na Garra menor que isso é só a troca entre um uso e outro
MAX_PAIN = 713                # Dor Máxima no chefe
REFLECT_SKILLS = {716, 717}   # Dor Máxima (usar) e o dano que ela devolve
FLORESCER = 1183              # Pólen (Florescer): o alvo perde resistência a fogo (100% com Clímax nv 4)
AG_CLIMAX = 5232
CLIMAX = 1152                 # Clímax (Intensificação) no Magus
ELO = 1392                    # Elo Celestial no Mestre Celestial (dos outros, o jogo só manda o fim do status)
ELO_SKILL = 5475              # o uso da skill todo mundo vê
ELO_MS = 900000               # dura até 15 min (nv 10) e sai ao morrer
STRONG_HIT = 0.005            # dano no chefe antes da Garra Sombria da fase acima disso do HP = erro
APPEAR_MS = 15000             # o monstro da fase apareceu até isso antes do 1º golpe: a fase começa ali
EXTRA_SOURCES = {1402: [5296], 1121: [361], 110: [361]}   # status sem skill no rAthena
# Buffs que o jogo não mostra nos outros jogadores (conferido nos replays): o início nunca chega e o fim
# só chega quando acaba sozinho (na morte, nem isso). Desses, só dá para cobrar de quem gravou.
HIDDEN = {1201, 1228, 1200, 1198, 1199, 1365, 331, 332, 1357, 1358, 1356}
HIDDEN_NOTE = _("dos outros jogadores o jogo não mostra esse buff: só dá para ver em quem gravou")


def _sources(ids):
    out = set()
    for efst in ids:
        out.update((meter.EFST.get(str(efst)) or {}).get("s", ()))
        out.update(EXTRA_SOURCES.get(efst, ()))
    return out


class Rule:
    """Um buff/debuff: status que contam, quem precisa, quem dá (classes) e o custo de renovar."""

    def __init__(self, ids, scope="all", core=True, only_seen=False, name=None, cost_from=(), cd_status=(),
                 always=False, short=False, single=False, no_renew=False, split_death=False):
        self.ids = set(ids)
        self.scope = scope            # quem precisa: all, W (físico) ou M (mágico)
        self.core = core              # dos principais: "nunca apareceu" vira atenção, não só informação
        self.only_seen = only_seen    # só para quem recebeu alguma vez (ex.: depende do tipo de arma)
        self.always = always          # tem que ficar o tempo todo: abaixo de 90% já é grave
        self.short = short            # dura 60 s ou menos: faltar é atenção (também vale o que o replay mostrar)
        self.single = single          # de alvo único: quem gravou talvez não precise, então é atenção
        self.no_renew = no_renew      # sai ao morrer e custa AP demais: só se cobra até a primeira morte
        self.split_death = split_death  # grave antes da 1ª morte; depois dela, não renovar é só atenção
        self._name = name
        self.first = ids[0]
        self.skills = _sources(ids)
        self.jobs = {j for j, sk in JOB_SKILLS.items() if sk & self.skills}
        own = (self.skills & CLASS_SKILLS) or self.skills      # sem as versões de guilda, mercenário e item
        costs = [SKILL_DB.get(str(s), {}) for s in own | set(cost_from)]
        self.cd = max([x.get("cd", 0) for x in costs] or [0])
        self.ap = max([x.get("ap", 0) for x in costs] or [0])
        self.cost_name = SKILL_DB.get(str(cost_from[0]), {}).get("n") if cost_from else None
        self.cd_status = set(cd_status)   # status no conjurador que marca o uso (ex.: Clímax no Magus)
        self.hidden = bool(self.ids & HIDDEN)

    @property
    def name(self):
        return self._name or meter.status_name(self.first)

    def hard(self):
        return self.cd >= HARD_CD_MS or self.ap >= BIG_AP

    def need(self):
        return ALWAYS_MIN if self.always else BAD

    def miss_sev(self, c=None):
        """Gravidade de faltar numa fase. Recarga alta ou AP: o que foi usado numa fase pode não voltar
        na seguinte. Curtos e de alvo único também são só atenção."""
        if self.single:
            return 1                  # alvo único nunca é grave: quem gravou talvez não precise
        if self.always:
            return 2
        if self.hard() or self.is_short(c):
            return 1
        return 2 if self.core else 1

    def absent_sev(self):
        """Gravidade de "ninguém recebeu" na luta inteira."""
        if self.single:
            return 1 if self.always else 0
        return 2 if self.always else (1 if self.core else 0)

    def is_short(self, c=None):
        if self.short:
            return True
        totals = [c.status_total.get(e, 0) for e in self.ids] if c is not None else []
        return bool(totals) and 0 < max(totals) <= SHORT_MS

    def cost_note(self):
        bits = []
        if self.cd >= LONG_CD_MS:
            bits.append(_("recarga %d s") % round(self.cd / 1000))
        if self.ap >= BIG_AP:
            bits.append(_("%d AP") % self.ap)
        if bits and self.cost_name:
            return _("precisa do Clímax (%s)") % " · ".join(bits)
        return " · ".join(bits)


def _rules(specs, **kw):
    return [Rule(ids, **dict(kw, **extra)) for ids, extra in specs]


# Buffs de grupo que contam para o dano (lista do simulador da LATAM Tools)
# (Bênção e Aumentar Agilidade contam também quando vêm da Clementia e do Canto Candidus: mesmo status.
# Eles e o Grito de Guerra saem ao morrer: faltar antes da 1ª morte é grave, não renovar depois é atenção.
# Força Violenta ficou de fora: quase não muda o dano. Reencarnação das Almas: nem todo Asceta tem, e
# custa AP, então é atenção.)
GROUP_BUFFS = _rules([
    ((10,), dict(split_death=True)), ((12,), dict(split_death=True)), ((15,), dict(short=True)),
    ((1201,), dict(no_renew=True)), ((1365,), {}), ((1359,), dict(always=True, single=True)),
    # Cardeal, alvo único: Benedictum (POW, CRT, CON), Religio (SPL, WIS, STA), Presens Acies (C.RATE),
    # Argutus Telum (atravessa resistência física) e Argutus Vita (resistência mágica)
    ((1228,), dict(scope="W", single=True)), ((1227,), dict(scope="M", single=True)),
    ((1200,), dict(single=True)), ((1199,), dict(scope="W", single=True)), ((1198,), dict(scope="M", single=True)),
    ((331,), dict(short=True)), ((332,), dict(short=True)),
    ((24,), dict(scope="W", always=True)), ((30,), dict(scope="W", split_death=True)),
    ((1357,), dict(scope="W", core=False)), ((340,), dict(scope="W", core=False)), ((920,), dict(scope="W", core=False)),
    ((23,), dict(scope="W", only_seen=True)), ((445,), dict(scope="W", only_seen=True, single=True)),
    ((1358,), dict(scope="M", core=False)), ((1271,), dict(scope="M")),
    ((1263,), dict(core=False)), ((1262,), dict(core=False)), ((1261,), dict(core=False)),
    ((715,), dict(core=False))])
# De proteção: aparecem na tabela, mas não viram alerta
DEFENSE_BUFFS = _rules([((19,), {}), ((9,), {}), ((1121, 473, 110), {}), ((1204,), {})], core=False)
# Debuffs no chefe
BOSS_DEBUFFS = _rules([
    ((DARK_CLAW,), {}), ((FLORESCER, 1182, 1184), dict(
                                                       cost_from=(AG_CLIMAX,), cd_status=(CLIMAX,))),
    ((1142,), {}), ((1402,), {}), ((1230,), {}), ((1231,), {}), ((655,), {}), ((VENOM_IMPRESS,), {}),
    ((1190,), dict(core=False)), ((1125,), dict(core=False)), ((1319,), dict(core=False)),
    ((1318,), dict(core=False)), ((1214,), dict(core=False)), ((395,), dict(core=False)),
    ((330,), dict(core=False)), ((1259,), dict(core=False)), ((1260,), dict(core=False)),
    ((1381,), dict(core=False)), ((1382,), dict(core=False))])
_KNOWN = set().union(*(r.ids for r in GROUP_BUFFS + DEFENSE_BUFFS))
_SKIP_KINDS = ("Sistema", "Consumível", "Serviço")


# --- intervalos ------------------------------------------------------------------

def _merge(spans):
    out = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def _total(windows):
    return sum(b - a for a, b in windows)


def _uptime(spans, windows):
    total = _total(windows)
    if total < MIN_WINDOW_MS:
        return None
    return sum(an._overlap(s, e, windows) for s, e in _merge(spans)) / total


def _intersect(a, b):
    out = []
    for s1, e1 in a:
        for s2, e2 in b:
            s, e = max(s1, s2), min(e1, e2)
            if e > s:
                out.append((s, e))
    return out


def _active(spans, t):
    return any(s <= t <= e for s, e in spans)


def _num(u):
    return u if isinstance(u, float) else None


def _worst(ups):
    known = [u for u in ups if isinstance(u, float)]
    return min(known) if known else None


def _pct(v):
    if v == UNKNOWN:
        return "?"
    return "—" if v is None else "%d%%" % round(v * 100)


def _secs(ms):
    return dec("%.1f s" % (ms / 1000.0))


def _when(t):
    """00:22,1 — com décimo de segundo, para o que acontece em menos de 1 s."""
    return an._dur(t) + dec(".%d" % (int(t) % 1000 // 100))


def _names(c, aids):
    return ", ".join(c.name_of(a) for a in aids)


# --- quem é quem ---------------------------------------------------------------------

def job_id(c, aid):
    if aid == c.me:
        return c.session.job
    e = c.entities.get(aid)
    return e.job if e is not None and e.kind == "pc" else None


def party_members(c):
    return sorted(a for a in ({c.me} | c.party) if job_id(c, a) is not None)


def _skill(sid):
    return SKILL_DB.get(str(sid)) or {}


def hit_element(sid):
    """Elemento fixo da skill, ou 'Weapon' quando usa o da arma (ataque básico também)."""
    sk = _skill(sid)
    if sid == 0 or not sk or sk.get("e") in ("Weapon", "Endowed", "Random"):
        return "Weapon"
    return sk.get("e") or "Neutral"


def boss_element(c, key):
    e = c.entities.get(key)
    mob = e.job if e is not None else 0
    if mob in BOSS_ELEMENTS:
        return BOSS_ELEMENTS[mob]
    m = MOB_DB.get(str(mob))
    return (m["e"], m["l"]) if m else None


def attr_rate(atk, defense):
    if defense is None:
        return None
    el, lvl = defense
    return ((ATTR.get(str(lvl)) or {}).get(atk) or {}).get(el)


def best_elements(defense):
    """Elementos com vantagem contra o chefe (vazio = nenhum passa de 100%)."""
    if defense is None:
        return []
    rates = [(attr_rate(e, defense) or 0, e) for e in ELEMENTS]
    top = max(r for r, _e in rates)
    return [] if top <= 100 else [(e, r) for r, e in rates if r == top]


# --- lutas contra chefes ---------------------------------------------------------------

def boss_fights(c, rng=None):
    """MVPs primeiro, depois outros chefes e por último os bonecos de treino."""
    rows = an.monsters(c, rng, group=True)
    top = max((r["total"] for r in rows), default=0)
    out = []
    for r in rows:
        e = c.entities.get(r["key"])
        if e is None:
            continue
        dummy = meter.DUMMY_MIN <= e.job <= meter.DUMMY_MAX
        mvp = c.is_mvp(r["key"]) and not dummy
        boss = bool(e.boss) and not dummy
        if not (mvp or boss or dummy) or (not mvp and r["total"] < top * 0.01):
            continue
        out.append(dict(r, rank=0 if mvp else (1 if boss else 2), mvp=mvp, dummy=dummy))
    out.sort(key=lambda r: (r["rank"], r["first"]))
    return out


def fight_label(c, f):
    tag = _("MVP") if f["mvp"] else (_("boneco") if f["dummy"] else _("chefe"))
    end = _("morto em %s") % an._dur(f["ttk"]) if f["ttk"] is not None else _("não morreu")
    return "%s%s · %s · %s–%s · %s" % ("★ " if f["mvp"] else "", f["name"].replace(" ★", ""), tag,
                                       an._dur(f["first"]), an._dur(f["last"]), end)


class Ctx:
    """Tudo o que as regras precisam sobre uma luta."""

    def __init__(self, c, key, rng):
        self.c = c
        self.key = key
        hits = [h for h in c.hits if h.out and h.dst == key and an._in(rng, h.t)]
        self.hits = hits
        first, last = {}, {}
        for h in hits:
            first.setdefault(h.dst_raw, h.t)
            last[h.dst_raw] = h.t
        order = sorted(first, key=first.get)
        self.start, self.end = hits[0].t, hits[-1].t
        self.killed = order[-1] in c.deaths and c.deaths[order[-1]] >= self.end - 5000
        if self.killed:
            self.end = max(self.end, c.deaths[order[-1]])
        self.total = sum(h.dmg for h in hits)
        # HP do chefe: pela dificuldade (deduzida do dano ou escolhida), o que o servidor manda ou a base
        self.hp, self.hp_label, self.hp_how = an.boss_hp(c, key, self.total, self.killed, self.end - self.start)
        self.hp_table = bool(an.hp_levels(c, key))
        # clímax: depois que o chefe perdeu 10% do HP (todas as fases são uma barra só). Sem tabela de
        # dificuldade, o HP só é conhecido quando ele morre (= dano total); antes disso conta o dano feito até agora
        base = self.hp if self.hp_table or self.killed else self.total
        goal, acc, self.climax = CLIMAX_HP * base, 0, self.end
        for h in hits:
            acc += h.dmg
            if acc >= goal:
                self.climax = h.t
                break
        # trechos em que o chefe estava apanhando: um wipe com minutos parados não entra na conta
        act = []
        for h in hits:
            if act and h.t - act[-1][1] <= c.gap_ms:
                act[-1][1] = h.t
            else:
                act.append([h.t, h.t])
        act[-1][1] = self.end
        self.active = [(a, b + 1000) for a, b in act]
        self.phases = []
        for i, a in enumerate(order):
            s = first[a]
            e = last[a] if i + 1 < len(order) else self.end
            cs = max(s, self.climax)
            win = _intersect([(cs, e)], self.active) if cs < e else []
            # a fase começa quando o monstro dela aparece (ele já pode agir antes do primeiro golpe); um
            # chefe visto muito antes de a luta começar conta do primeiro golpe
            seen = c.spawned.get(a)
            appear = seen if seen is not None and s - APPEAR_MS <= seen <= s else s
            self.phases.append(dict(n=i + 1, aid=a, start=s, appear=appear, end=e,
                                    climax_start=cs if cs < e else None, win=win))
        self.multi = len(self.phases) > 1
        self.whole = _("Todas as fases") if self.multi else _("Luta inteira")
        self.st = collections.defaultdict(list)        # aid -> [(efst, início, fim)]
        lo = self.start - UNSEEN_MS
        for a, efst, s, e in c.statuses():
            if e >= lo and s <= self.end:
                self.st[a].append((efst, s, e))
        self.boss_aids = set(order)
        self.party = party_members(c)
        pset = set(self.party)
        self.dmg = collections.Counter()
        kinds = collections.defaultdict(collections.Counter)
        for h in hits:
            self.dmg[h.src] += h.dmg
            kinds[h.src][_skill(h.skill).get("t", "W") if h.skill else "W"] += h.dmg
        party_dmg = sum(v for a, v in self.dmg.items() if a in pset) or 1
        self.role = {}
        for a in self.party:
            k = kinds.get(a, {})
            if self.dmg.get(a, 0) < DPS_SHARE * party_dmg:
                self.role[a] = "S"              # suporte / quase não bateu
            else:
                self.role[a] = "M" if k.get("M", 0) > k.get("W", 0) else "W"
        self.jobs = {a: job_id(c, a) for a in self.party}
        self.others = sorted(a for a in self.dmg if a not in pset and job_id(c, a) is not None)
        self.dead = {a: self.dead_spans(a) for a in self.party + self.others}
        self.first_death = {}
        for t, a in c.death_log:
            self.first_death.setdefault(a, t)

    def phase_name(self, p):
        return _("Fase %d") % p["n"] if self.multi else _("Clímax")

    def phase_at(self, t):
        for p in self.phases:
            if p["start"] - 1000 <= t <= p["end"] + 1000:
                if self.multi:
                    return self.phase_name(p)
                return _("Clímax") if t >= self.climax else _("Antes do clímax")
        return _("troca de fase") if self.start <= t <= self.end else self.whole

    def dead_spans(self, aid):
        """[(morte, quando voltou ou None)] dentro da luta. Volta = pacote de ressurreição; sem ele,
        o primeiro sinal de vida (HP do grupo acima de 0, um golpe dele) ou, no máximo, a morte seguinte."""
        c = self.c
        deaths = sorted(t for t, a in c.death_log if a == aid and self.start - 1000 <= t <= self.end + 1000)
        if not deaths:
            return []
        res = sorted(t for t, a in c.res_log if a == aid and t >= deaths[0])
        life = sorted([t for t, hp, _m in c.hp_log.get(aid, ()) if hp and t > deaths[0]] +
                      [h.t for h in self.hits if h.src == aid and h.raw == aid and h.t > deaths[0]])
        out = []
        for i, t in enumerate(deaths):
            nxt = deaths[i + 1] if i + 1 < len(deaths) else None
            back = next((r for r in res if r >= t and (nxt is None or r <= nxt)), None)
            exact = back is not None
            if back is None:
                back = next((x for x in life if x > t + 300 and (nxt is None or x <= nxt)), nxt)
            out.append((t, back, exact))
        return out

    def alive(self, aid, windows):
        holes = [(t, b if b is not None else self.end) for t, b, _x in self.dead.get(aid, ())]
        return an._subtract(windows, holes)

    def spans(self, aid, ids):
        return [(s, e) for efst, s, e in self.st.get(aid, ()) if efst in ids]

    def boss_spans(self, ids, aid=None):
        aids = {aid} if aid is not None else self.boss_aids
        return [sp for a in aids for sp in self.spans(a, ids)]

    def unknown(self, aid, ids, limit=UNSEEN_MS):
        """Trecho do começo da gravação em que não dá para saber se `aid` tinha o status."""
        if aid == self.c.me:
            return []                           # os seus buffs vêm prontos no início da gravação
        if set(ids) & HIDDEN:
            return [(0, self.c.now + 1)]        # dos outros, esses nunca dá para saber
        firsts = [self.c.status_first.get((aid, e)) for e in ids]
        if any(f is not None and (f[0] == 0 or not f[1]) for f in firsts):
            return []                           # o primeiro aviso foi o fim: estava ativo desde o início
        if all(f is None for f in firsts) and self.c.now >= limit:
            return []                           # um buff de antes da gravação teria acabado (e aparecido)
        end = min([f[0] for f in firsts if f is not None] + [limit])
        end = min(end, self.first_death.get(aid, end))   # morrer limpa tudo: dali em diante se sabe
        return [(0, end)] if end > 0 else []

    def member_up(self, aid, ids, windows, until=None):
        """% do trecho com o status; '?' quando quase todo o trecho é desconhecido."""
        windows = self.alive(aid, windows)
        if until is not None:
            windows = an._subtract(windows, [(until, self.end + 1)])
        if _total(windows) < MIN_WINDOW_MS:
            return None
        unk = self.unknown(aid, ids)
        known = an._subtract(windows, unk) if unk else windows
        if _total(known) < MIN_WINDOW_MS:
            return UNKNOWN
        return _uptime(self.spans(aid, ids), known)

    def providers(self, rule):
        return [a for a in self.party if self.jobs[a] in rule.jobs]

    def who_gives(self, rule, prov):
        return "%s (%s)" % (", ".join(sorted({meter.job_name(self.jobs[a]) for a in prov})), _names(self.c, prov))


def _alert(out, sev, phase, what, who, detail=""):
    out.append(dict(sev=sev, sev_txt=SEV_TEXT[sev], phase=phase, what=what, who=who, detail=detail))


def _phase_cols(row, ups):
    for i, u in enumerate(ups[:3]):
        row["p%d" % (i + 1)] = _pct(u)
    row["worst"] = _worst(ups)


# --- regras ----------------------------------------------------------------------

def recharge_note(x, rule, p, spans):
    """Se o último uso antes da fase ainda estava em recarga quando o clímax da fase começou."""
    if rule.cd < LONG_CD_MS:
        return ""
    starts = [a for a, _b in spans if 0 < a < p["start"]]
    starts += [a for who in x.providers(rule) for a, _b in x.spans(who, rule.cd_status) if 0 < a < p["start"]]
    if not starts:
        return ""
    last = max(starts)
    ready = last + rule.cd
    begin = p["climax_start"] or p["start"]
    if ready <= begin or ready - begin < 0.3 * max(1, p["end"] - begin):
        return ""
    txt = _("%s: recarga de %d s, usado em %s, só voltaria em %s") % (rule.name, rule.cd // 1000, an._dur(last),
                                                                   an._dur(ready))
    return txt + (_(" (depois do fim da fase)") if ready > p["end"] else "")


def _buff_rows(x, rules, kind, alerts):
    c = x.c
    rows = []
    dps = [a for a in x.party if x.role[a] != "S"]
    merged = collections.OrderedDict()       # (fase, gravidade, quem dá, quem ficou sem) -> [buffs, notas, %]
    absent = collections.OrderedDict()       # (gravidade, quem dá) -> buffs que ninguém recebeu
    for rule in rules:
        prov = x.providers(rule)
        if not prov:
            continue
        seen_on = {a for a in x.party if x.spans(a, rule.ids)}
        want = [a for a in dps if rule.scope == "all" or x.role[a] == rule.scope]
        if rule.only_seen:
            want = [a for a in want if a in seen_on]
        if not want:
            continue
        who_gives = x.who_gives(rule, prov)
        per_phase = collections.defaultdict(list)    # (fase, depois de morrer?) -> [(aid, %)]
        all_ups = {}
        for a in want:
            until = next((t for t, _b, _e in x.dead.get(a, ())), None) if rule.no_renew else None
            ups = [x.member_up(a, rule.ids, p["win"], until) for p in x.phases]
            all_ups[a] = ups
            note = rule.cost_note()
            if rule.hidden and a != c.me:
                note = HIDDEN_NOTE
            elif until is not None:
                note = _("sai ao morrer e custa AP demais: só conta até a 1ª morte (%s)") % an._dur(until)
            elif rule.always:
                note = _("tem que ficar o tempo todo") + (" · " + note if note else "")
            row = dict(key="%s|%d|%d" % (kind, min(rule.ids), a), aid=a, name=c.name_of(a),
                       job=meter.job_name(x.jobs[a]), buff=rule.name, kind=kind, me=a == c.me, note=note)
            _phase_cols(row, ups)
            rows.append(row)
            first = next((t for t, _b, _e in x.dead.get(a, ())), None) if rule.split_death else None
            for p, u in zip(x.phases, ups):
                if first is None:
                    if isinstance(u, float) and u < rule.need():
                        per_phase[(p["n"], False)].append((a, u))
                    continue
                # antes da 1ª morte e depois dela contam separado (a média da fase esconderia a falta)
                pre = x.member_up(a, rule.ids, p["win"], first)
                post = x.member_up(a, rule.ids, an._subtract(p["win"], [(0, first)]))
                if isinstance(pre, float) and pre < rule.need():
                    per_phase[(p["n"], False)].append((a, pre))
                elif isinstance(post, float) and post < rule.need():
                    per_phase[(p["n"], True)].append((a, post))
        if kind != "grupo":
            continue
        if not seen_on and not rule.hidden:
            vals = [u for ups in all_ups.values() for u in ups if u is not None]
            if any(isinstance(u, float) for u in vals):
                full = not any(_intersect(x.unknown(a, rule.ids), p["win"]) for a in want for p in x.phases)
                absent.setdefault((rule.absent_sev(), who_gives, full), []).append(rule)
            continue
        if not seen_on:
            continue
        party_spans = [sp for a in x.party for sp in x.spans(a, rule.ids)]
        for (n, after), miss in sorted(per_phase.items()):
            p = x.phases[n - 1]
            sev = 1 if after else rule.miss_sev(c)
            k = (n, sev, after, who_gives, tuple(sorted(a for a, _u in miss)))
            m = merged.setdefault(k, [[], [], {}])
            m[0].append(rule.name)
            note = recharge_note(x, rule, p, party_spans)
            if rule.hidden:
                m[1].append("%s: %s" % (rule.name, HIDDEN_NOTE))
            if note:
                m[1].append(note)
            elif rule.single:
                m[1].append(_("%s é de alvo único: quem gravou talvez não precise%s") % (
                    rule.name, _(" (em quem recebe, tem que ficar o tempo todo)") if rule.always else ""))
            elif rule.always:
                m[1].append(_("%s tem que ficar o tempo todo") % rule.name)
            elif rule.is_short(c):
                m[1].append(_("%s dura 60 s ou menos") % rule.name)
            for a, u in miss:
                m[2][a] = min(m[2].get(a, 1.0), u)
    for (sev, who_gives, full), lst in absent.items():
        if full:
            why = (_("nenhum membro do grupo recebeu em nenhuma fase (os buffs de quem está no grupo aparecem no "
                   "replay, não só os de quem gravou)"))
        else:
            why = (_("não apareceu em ninguém do grupo; no começo da gravação não dá para saber (buff dado antes "
                   "de gravar só aparece quando acaba)"))
        _alert(alerts, sev, x.whole, _("Ninguém do grupo recebeu ") + ", ".join(r.name for r in lst), who_gives,
               _("a classe que dá está no grupo, mas ") + why + "".join(
                   " · %s: %s" % (r.name, r.cost_note()) for r in lst if r.cost_note()))
    for (n, sev, after, who_gives, _aids), (names, notes, worst) in merged.items():
        what = (_("Sem %s depois de morrer") if after else _("Faltou %s")) % ", ".join(names)
        detail = _("quem dá: %s") % who_gives
        if after:
            detail += _(" · estava com o buff antes da 1ª morte, mas não recebeu de novo depois de ressuscitar")
        _alert(alerts, sev, x.phase_name(x.phases[n - 1]), what,
               ", ".join(_("%s %s") % (c.name_of(a), _pct(u)) for a, u in sorted(worst.items(), key=lambda m: m[1])),
               detail + "".join(" · " + t for t in notes))
    return rows


def _class_buffs(x, alerts):
    """Buffs da própria classe com recarga longa ou custo de AP: estavam numa fase e sumiram em outra."""
    c = x.c
    rows = []
    for a in x.party:
        tree = JOB_SKILLS.get(x.jobs[a], set())
        seen = {}
        for efst, _s, _e in x.st.get(a, ()):
            if (efst in _KNOWN or efst in seen or efst in ENDOW_IDS or efst == ELO
                    or meter.status_kind(efst) in _SKIP_KINDS):
                continue
            if _sources([efst]) & tree:
                rule = Rule([efst])
                if rule.cd >= LONG_CD_MS or rule.ap >= BIG_AP:
                    seen[efst] = rule
        for efst, rule in seen.items():
            ups = [x.member_up(a, {efst}, p["win"]) for p in x.phases]
            known = [u for u in ups if isinstance(u, float)]
            if not known:
                continue
            row = dict(key="classe|%d|%d" % (efst, a), aid=a, name=c.name_of(a), job=meter.job_name(x.jobs[a]),
                       buff=rule.name, kind="da classe", me=a == c.me, note=rule.cost_note())
            _phase_cols(row, ups)
            rows.append(row)
            best = max(known)
            for p, u in zip(x.phases, ups):
                if isinstance(u, float) and u < 0.2 and best >= BAD:
                    _alert(alerts, 1, x.phase_name(p), _("%s sumiu") % rule.name, c.name_of(a),
                           _("estava em %s de outra fase · %s") % (_pct(best), rule.cost_note()))
            if best < 0.2 and x.role[a] != "S" and len(known) == len(ups):
                _alert(alerts, 1, x.whole, _("%s fora do clímax") % rule.name, c.name_of(a),
                       _("usou na luta, mas ficou ativo em no máximo %s do clímax · %s") % (_pct(best), rule.cost_note()))
    return rows


def reflect_info(x):
    """O chefe reflete dano (Dor Máxima)? Quanto voltou com e sem a Garra Sombria."""
    c = x.c
    back = [h for h in c.hits if not h.out and h.src == x.key and h.skill in REFLECT_SKILLS
            and x.start <= h.t <= x.end]
    used = bool(back) or bool(x.boss_spans({MAX_PAIN})) or any(
        u[1] == x.key and u[4] in REFLECT_SKILLS for u in c.uses if x.start <= u[0] <= x.end)
    claw = x.boss_spans({DARK_CLAW})
    free = [h for h in back if not _active(claw, h.t)]
    return dict(used=used, hits=len(back), dmg=sum(h.dmg for h in back), no_claw_hits=len(free),
                no_claw_dmg=sum(h.dmg for h in free), victims=collections.Counter(h.dst for h in free))


def pollen_died(x, p):
    """O Magus morreu e ficou sem Clímax nesta fase (sem AP para usar de novo: não dá para cobrar)."""
    for m in [a for a in x.party if JOB_SKILLS.get(x.jobs[a], set()) & {AG_CLIMAX}]:
        climax = x.spans(m, {CLIMAX})
        for t in [t for t, _b, _e in x.dead.get(m, ()) if t <= p["end"]][-1:]:
            if not any(a > t for a, _b in climax if a <= p["end"]):
                return True
    return False


def pollen_cause(x, p):
    """Por que faltou Pólen numa fase. Cada fase do chefe é um monstro novo (chega sem Pólen). O Pólen
    não sai quando o Magus morre (fica até acabar), mas o Clímax sai, e depois de ressuscitar o Magus
    não tem AP para usar o Clímax de novo (125 AP, recarga 60 s). Com o Clímax ativo, o Florescer
    pode ser usado de novo a cada 6 s."""
    c = x.c
    bits = []
    spans = [sp for sp in x.boss_spans({FLORESCER}, p["aid"]) if sp[1] > p["start"]]
    if p["n"] > 1:
        if not spans:
            bits.append(_("a fase é um monstro novo e chega sem Pólen: não foi aplicado de novo"))
        elif min(a for a, _b in spans) - p["start"] > PHASE_LATE_MS:
            bits.append(_("a fase é um monstro novo e chega sem Pólen: só foi aplicado em %s (a fase começou em %s)")
                        % (an._dur(min(a for a, _b in spans)), an._dur(p["start"])))
    magus = [a for a in x.party if JOB_SKILLS.get(x.jobs[a], set()) & {AG_CLIMAX}]
    win = p["win"]
    for m in magus:
        name = c.name_of(m)
        climax = x.spans(m, {CLIMAX})
        with_climax = an._subtract(win, an._subtract(win, climax))       # trecho da fase com Clímax ativo
        cov = _total(with_climax)
        deaths = [t for t, _b, _e in x.dead.get(m, ()) if t <= p["end"]]
        if cov >= 2000:
            bits.append(_("%s estava com Clímax em %s do clímax da fase: dava para usar o Florescer (recarga 6 s)") %
                        (name, _pct(cov / max(1, _total(win)))))
        for t in deaths[-1:]:
            if any(a > t for a, _b in climax if a <= p["end"]):
                continue
            if t >= (p["climax_start"] or p["start"]) or cov < 2000:
                bits.append(_("%s morreu em %s e perdeu o Clímax — sem AP para usar de novo depois de ressuscitar") %
                            (name, an._dur(t)))
        if cov < 2000 and not deaths:
            before = [a for a, _b in climax if 0 < a < p["end"]]
            if before and max(before) + 60000 > (p["climax_start"] or p["start"]):
                bits.append(_("Clímax de %s em recarga até %s") % (name, an._dur(max(before) + 60000)))
            elif climax or not x.unknown(m, {CLIMAX}):
                bits.append(_("%s sem Clímax nesta fase (o Pólen só tira 100%% da resistência a fogo com Clímax nv 4)")
                            % name)
    return " · ".join(bits)


def _debuffs(x, alerts, refl, poisoned, gaps=()):
    c = x.c
    rows = []
    for rule in BOSS_DEBUFFS:
        prov = x.providers(rule)
        if not prov:
            continue
        who_gives = x.who_gives(rule, prov)
        ups = [_uptime(x.boss_spans(rule.ids, p["aid"]), p["win"]) for p in x.phases]
        seen = bool(x.boss_spans(rule.ids))
        claw = DARK_CLAW in rule.ids and refl["used"]
        venom = VENOM_IMPRESS in rule.ids
        pollen = FLORESCER in rule.ids
        need = DARK_CLAW_MIN if claw else (POLLEN_MIN if pollen else BAD)
        notes = []
        if claw:
            notes.append(_("o chefe usa Dor Máxima: tem que ficar o tempo todo"))
        if pollen:
            notes.append(_("tem que ficar o tempo todo; cada fase chega sem Pólen; o Pólen fica se o Magus morre, "
                         "o Clímax não"))
        if venom:
            notes.append((_("com veneno na arma: ") + _names(c, poisoned)) if poisoned else _("ninguém com veneno na arma"))
        if rule.cost_note():
            notes.append(rule.cost_note())
        row = dict(key="deb|%d" % min(rule.ids), debuff=rule.name, who=who_gives, note=" · ".join(notes))
        _phase_cols(row, ups)
        row["bad"] = any(u is not None and u < need for u in ups)
        rows.append(row)
        if venom and not poisoned:
            continue
        if not seen:
            if claw:
                _alert(alerts, 2, x.whole, _("Garra Sombria nunca apareceu no chefe"), who_gives,
                       _("o chefe usa Dor Máxima: %d golpes refletidos (%s de dano)") % (refl["hits"],
                                                                                       an._full(refl["dmg"])))
            elif venom:
                _alert(alerts, 1, x.whole, _("Potencializar Veneno nunca apareceu no chefe"), who_gives,
                       _("bateram com veneno na arma: %s") % _names(c, poisoned))
            else:
                _alert(alerts, 1 if rule.core else 0, x.whole, _("%s nunca apareceu no chefe") % rule.name, who_gives,
                       _("pode ser imunidade do chefe ou a skill não foi usada")
                       + (" · " + rule.cost_note() if rule.cost_note() else ""))
            continue
        for i, (p, u) in enumerate(zip(x.phases, ups)):
            if u is None or u >= need:
                continue
            if claw:
                detail = _("o chefe usa Dor Máxima e a Garra Sombria ficou só %s do clímax · %s") % (_pct(u), who_gives)
                big = max((g for g in gaps if g["phase"] == x.phase_name(p)), key=lambda g: g["dur"], default=None)
                if big is not None:
                    detail += _(" · no maior buraco (%s, %s): %s") % (an._dur(big["start"]), _secs(big["dur"]), big["who"])
            else:
                detail = _("no chefe só %s do clímax · quem aplica: %s") % (_pct(u), who_gives)
            note = pollen_cause(x, p) if pollen else recharge_note(x, rule, p, x.boss_spans(rule.ids))
            if note:
                detail += " · " + note
            if claw:
                sev = 2                       # contra Dor Máxima a Garra tem que ficar o tempo todo
            elif pollen:
                sev = 1 if pollen_died(x, p) else 2
            elif rule.hard() or rule.is_short(c):
                sev = 1                       # recarga alta ou AP: pode não ter voltado para esta fase
            else:
                sev = 2 if u < 0.2 and rule.core else 1
            _alert(alerts, sev, x.phase_name(p), _("%s %s") % (rule.name, _("faltou") if u < 0.2 else _("durou pouco")),
                   _("chefe"), detail)
    if refl["used"] and refl["no_claw_hits"]:
        _alert(alerts, 2, x.whole, _("Dor Máxima refletiu sem Garra Sombria"),
               ", ".join("%s %d×" % (c.name_of(a), n) for a, n in refl["victims"].most_common(4)),
               _("%d golpes refletidos (%s de dano) com a Garra Sombria desligada") % (
                   refl["no_claw_hits"], an._full(refl["no_claw_dmg"])))
    return rows


def _late(dead_ms):
    return round(dead_ms / 100.0) > DEAD_LIMIT_MS / 100      # 2,0 s não conta; 2,1 s sim


# --- Garra Sombria: buracos no chefe e a recarga de cada Executor ------------------------

def claw_casts(x, aid):
    """[(quando usou, recarga ms)] da Garra Sombria de `aid` (golpe ou uso da skill à vista)."""
    c = x.c
    seen = sorted({(u[0], u[4]) for u in c.uses if u[2] == aid and u[4] in DARK_CLAW_SKILLS} |
                  {(h.t, h.skill) for h in c.hits if h.out and h.raw == aid and h.skill in DARK_CLAW_SKILLS})
    out = []
    for t, sid in seen:
        if not out or t - out[-1][0] > 1500:              # o golpe e o uso chegam juntos
            out.append((t, _skill(sid).get("cd") or 60000))
    return out


def claw_gaps(x, refl_hits):
    """Trechos do clímax em que o chefe ficou sem Garra Sombria."""
    claw = _merge(x.boss_spans({DARK_CLAW}))
    pain = _merge(x.boss_spans({MAX_PAIN}))
    gaps = []
    for p in x.phases:
        for a, b in p["win"]:
            for s0, e0 in an._subtract([(a, b)], claw):
                if e0 - s0 >= GAP_MIN_MS:
                    gaps.append(dict(phase=x.phase_name(p), start=s0, end=e0, dur=e0 - s0,
                                     pain=any(an._overlap(s0, e0, [sp]) for sp in pain),
                                     refl=sum(1 for h in refl_hits if s0 <= h.t <= e0)))
    return gaps


def claw_state(x, aid, casts, t0, t1):
    """(estado, texto, ms disponível sem usar) da Garra de `aid` no buraco [t0, t1]."""
    dead = [(d, b if b is not None else x.end) for d, b, _e in x.dead.get(aid, ())]
    if any(d <= t0 < b for d, b in dead):
        return "morto", "morto", 0
    used = [(t, cd) for t, cd in casts if t <= t0]
    ready = used[-1][0] + used[-1][1] if used else 0
    free = an._subtract([(max(t0, ready), t1)], dead) if max(t0, ready) < t1 else []
    free_ms = _total(free)
    if ready > t0:
        txt = _("em recarga (%d s)") % round((ready - t0) / 1000.0)
        if free_ms >= 1000:
            txt += _(", depois disponível por %s") % _secs(free_ms)
        return "recarga", txt, free_ms
    if used:
        return "livre", _("disponível (usou em %s)") % an._dur(used[-1][0]), free_ms
    if t0 < 60000:
        return "livre", _("disponível? (nenhum uso visto desde o começo da gravação)"), free_ms
    return "livre", _("disponível (ainda não tinha usado na luta)"), free_ms


def claw_text(c, states):
    """'Garra Sombria de A estava em recarga (13 s); de B e C estavam disponíveis'."""
    by = collections.OrderedDict()
    order = {"recarga": 0, "livre": 1, "morto": 2}
    for aid, (kind, txt, _ms) in sorted(states.items(), key=lambda kv: order[kv[1][0]]):
        by.setdefault((kind, txt if kind != "livre" else _("disponível")), []).append(aid)
    parts = []
    for (kind, txt), aids in by.items():
        names = _(" e ").join(c.name_of(a) for a in aids)
        if kind == "livre":
            parts.append(_("de %s %s") % (names, _("estava disponível") if len(aids) == 1 else _("estavam disponíveis")))
        elif kind == "morto":
            parts.append(_("%s %s") % (names, _("estava morto") if len(aids) == 1 else _("estavam mortos")))
        else:
            parts.append(_("de %s %s %s") % (names, _("estava") if len(aids) == 1 else _("estavam"), txt))
    if not parts:
        return ""
    if i18n.LANG != "en" and parts[0].startswith("de "):
        return meter.skill_name(5001) + " " + "; ".join(parts)
    return meter.skill_name(5001) + ": " + "; ".join(parts)


def _claw(x, alerts, refl, aids, party):
    """Para cada buraco: quem tinha a Garra pronta e não usou. Contra Dor Máxima isso é grave."""
    c = x.c
    execs = [a for a in aids if JOB_SKILLS.get(job_id(c, a), set()) & DARK_CLAW_SKILLS]
    if not execs:
        return [], []
    hits = [h for h in c.hits if not h.out and h.src == x.key and h.skill in REFLECT_SKILLS]
    gaps = claw_gaps(x, hits)
    casts = {a: claw_casts(x, a) for a in execs}
    idle = collections.Counter()
    rows = []
    for g in gaps:
        states = {a: claw_state(x, a, casts[a], g["start"], g["end"]) for a in execs}
        for a, (_k, _t, ms) in states.items():
            if not refl["used"] or g["pain"] or g["refl"]:
                idle[a] += ms
        rows.append(dict(g, key="gap|%d" % g["start"], pain_txt=_("sim") if g["pain"] else "",
                         who=claw_text(c, states), bad=refl["used"] and (g["pain"] or g["refl"] > 0)))
    for a in execs:
        if idle[a] < 5000:
            continue
        uses = len([t for t, _cd in casts[a] if x.start <= t <= x.end])
        sev = 2 if refl["used"] else 1
        where = _("com Dor Máxima no chefe") if refl["used"] else _("no clímax")
        _alert(alerts, sev, x.whole, _("Garra Sombria pronta e sem usar"), c.name_of(a),
               _("ficou %s disponível enquanto o chefe estava sem Garra (%s); usou %d× na luta") % (
                   _secs(idle[a]), where, uses))
    return rows, execs


def claw_start(x, p):
    """Quando a Garra Sombria chegou no monstro da fase (None = não chegou)."""
    spans = [s for s, e in x.boss_spans({DARK_CLAW}, p["aid"]) if e >= p["start"]]
    casts = [h.t for h in x.hits if h.dst_raw == p["aid"] and h.skill in DARK_CLAW_SKILLS]
    return min(spans + casts, default=None)


def _before_claw(x, alerts, refl, aids):
    """Quem bateu forte no chefe antes da Garra Sombria da fase. Cada fase é um monstro novo, que chega
    sem a Garra; contra Dor Máxima esse dano volta para o grupo inteiro."""
    c = x.c
    if not any(JOB_SKILLS.get(job_id(c, a), set()) & DARK_CLAW_SKILLS for a in x.party + x.others):
        return
    limit = STRONG_HIT * x.hp
    if limit <= 0:
        return
    aids = set(aids)
    for p in x.phases:
        first = claw_start(x, p)
        if first is None:
            continue                          # a fase sem Garra nenhuma já aparece nos buracos da Garra
        dmg, top = collections.Counter(), {}
        for h in x.hits:
            if (h.dst_raw == p["aid"] and p["start"] <= h.t < first and h.src in aids
                    and h.skill not in DARK_CLAW_SKILLS):
                dmg[h.src] += h.dmg
                if h.dmg > top.get(h.src, (0,))[0]:
                    top[h.src] = (h.dmg, h.skill, h.t)
        bad = sorted((a for a, v in dmg.items() if v >= limit), key=lambda a: -dmg[a])
        if not bad:
            continue
        pain = [s for s, e in x.boss_spans({MAX_PAIN}, p["aid"]) if s < first and e > p["start"]]
        detail = [_("dano no chefe antes da Garra Sombria (limite: %s do HP, %s)") % (
                      dec("%.1f%%" % (STRONG_HIT * 100)), num(limit)),
                  _("a Garra só chegou em %s, %s depois do começo da fase") % (_when(first),
                                                                                 _secs(first - p["appear"]))]
        if pain:
            detail.append(_("Dor Máxima no chefe desde %s: esse dano volta para o grupo") % _when(min(pain)))
        for a in bad:
            v, sid, t = top[a]
            detail.append(_("maior golpe de %s: %s %s em %s") % (c.name_of(a), meter.skill_name(sid), num(v), _when(t)))
        sev = 2 if refl["used"] else 1
        who = ", ".join("%s %s (%s)" % (c.name_of(a), num(dmg[a]), dec("%.2f%%" % (100.0 * dmg[a] / x.hp)))
                        for a in bad)
        _alert(alerts, sev, x.phase_name(p) if x.multi else x.whole, _("Atacou antes da Garra Sombria"), who,
               " · ".join(detail))


def elo_spans(x, aid):
    """Quando `aid` estava com o Elo Celestial: o status (dos outros só chega o fim) e cada uso da skill,
    que todo mundo vê, até a morte seguinte."""
    c = x.c
    deaths = [t for t, a in c.death_log if a == aid]
    spans = list(x.spans(aid, {ELO}))
    for t in sorted({u[0] for u in c.uses if aid in (u[1], u[2]) and u[4] == ELO_SKILL}):
        spans.append((t, min([d for d in deaths if d > t] + [t + ELO_MS])))
    return _merge(spans)


def _elo(x, alerts, aids):
    """Mestre Celestial sem o Elo Celestial (buff dele mesmo): grave. Só conta até a primeira morte: sai ao
    morrer e custa 120 AP, que o Mestre Celestial não tem depois de ressuscitar."""
    c = x.c
    name = meter.skill_name(ELO_SKILL)
    rows = []
    miss = collections.defaultdict(dict)      # fase -> {aid: %}
    for a in aids:
        if ELO_SKILL not in JOB_SKILLS.get(job_id(c, a), set()) or not x.dmg.get(a):
            continue                      # quem bateu pouco também é cobrado (pode ser por isso); quem nem bateu, não
        spans = elo_spans(x, a)
        casts = [u[0] for u in c.uses if a in (u[1], u[2]) and u[4] == ELO_SKILL]
        unk = x.unknown(a, {ELO}, ELO_MS)
        if unk and casts:
            unk = [(0, min(unk[0][1], min(casts)))]
        first = next((t for t, _b, _e in x.dead.get(a, ())), None)

        def up(windows):
            win = x.alive(a, windows)
            known = an._subtract(win, unk) if unk else win
            if _total(win) < MIN_WINDOW_MS:
                return None
            return UNKNOWN if _total(known) < MIN_WINDOW_MS else _uptime(spans, known)

        ups = [up(an._subtract(p["win"], [(first, x.end + 1)]) if first is not None else p["win"])
               for p in x.phases]
        if a in x.party:
            note = _("buff do próprio Mestre Celestial: dura até 15 min, sai ao morrer e custa 120 AP")
            if first is not None:
                note = _("sai ao morrer e custa 120 AP: só conta até a 1ª morte (%s)") % an._dur(first)
            row = dict(key="classe|%d|%d" % (ELO, a), aid=a, name=c.name_of(a), job=meter.job_name(job_id(c, a)),
                       buff=name, kind="da classe", me=a == c.me, note=note)
            _phase_cols(row, ups)
            rows.append(row)
        for p, u in zip(x.phases, ups):
            if isinstance(u, float) and u < ALWAYS_MIN:
                miss[p["n"]][a] = u
    for n, who in sorted(miss.items()):
        _alert(alerts, 2, x.phase_name(x.phases[n - 1]), _("Faltou %s") % name,
               ", ".join("%s %s" % (c.name_of(a), _pct(u)) for a, u in sorted(who.items(), key=lambda m: m[1])),
               _("buff do próprio Mestre Celestial: tem que ficar o tempo todo até a 1ª morte (dura até 15 min; "
                 "depois de morrer não tem AP para usar de novo)"))
    return rows


def _deaths(x, aids, alerts, party):
    c = x.c
    rows = []
    slow = collections.OrderedDict()          # (jogador, fase) -> [(morte, tempo morto, exato?)]
    hard = collections.OrderedDict()          # (jogador, fase) -> {buff: custo}
    for a in aids:
        spans = x.dead.get(a, ())
        for i, (t, back, exact) in enumerate(spans):
            dead_ms = (back if back is not None else x.end) - t
            nxt = spans[i + 1][0] if i + 1 < len(spans) else x.end
            lost = []
            if party and back is not None and min(back + BACK_MS, x.end) <= nxt:
                before = {efst for efst, s0, e in x.st.get(a, ()) if s0 < t - 200 and t - 2000 <= e <= t + 2000}
                rules = [r for r in GROUP_BUFFS if r.ids & before and not (r.hidden and a != c.me)]
                rules += [r for r in (Rule([efst]) for efst in sorted(before - _KNOWN - ENDOW_IDS)
                                      if _sources([efst]) & JOB_SKILLS.get(x.jobs.get(a), set())
                                      and meter.status_kind(efst) not in _SKIP_KINDS) if r.cost_note()]
                for r in rules:
                    if not any(back - 500 <= s0 <= back + BACK_MS for s0, _e in x.spans(a, r.ids)):
                        lost.append(r)
            wipe = dead_ms > WIPE_MS
            if back is None:
                back_txt = _("não voltou")
            elif not exact:
                back_txt = _("voltou (sem aviso de ressurreição)")
            else:
                back_txt = _("na hora") if dead_ms <= 300 else _("ressuscitado")
            if wipe:
                back_txt += _(" · provável wipe")
            phase = x.phase_at(t)
            row = dict(key="%d|%d" % (t, a), aid=a, t=t, phase=phase, name=c.name_of(a),
                       job=meter.job_name(job_id(c, a)), dead_ms=dead_ms,
                       dead_txt=("≈ " if back is not None and not exact else "") + _secs(dead_ms),
                       back=back_txt, me=a == c.me, late=_late(dead_ms) and not wipe and back is not None,
                       lost=", ".join(r.name + (" (%s)" % r.cost_note() if r.cost_note() else "") for r in lost))
            rows.append(row)
            # quem não voltou (a luta acabou) e mortes de mais de 7 s (provável wipe) ficam fora do relatório
            if back is None or wipe:
                continue
            if _late(dead_ms):
                slow.setdefault((a, phase), []).append((t, dead_ms, exact))
            for r in lost:
                if r.hard() and not r.no_renew:
                    hard.setdefault((a, phase), {})[r.name] = r.cost_note()
    for (a, phase), lst in slow.items():
        what = _("Demorou para ressuscitar") + (_(" (%d×)") % len(lst) if len(lst) > 1 else "")
        _alert(alerts, 2, phase, what, c.name_of(a), _("ficou ") + ", ".join(
            _("%s%s morto em %s") % ("" if ex else "≈ ", _secs(ms), an._dur(t)) for t, ms, ex in lst))
    for (a, phase), names in hard.items():
        _alert(alerts, 1, phase, _("Perdeu buffs ao morrer"), c.name_of(a),
               _("não voltaram em %d s: %s") % (BACK_MS // 1000, ", ".join("%s (%s)" % kv for kv in names.items())))
    rows.sort(key=lambda r: r["t"])
    return rows


def weapon_element(x, aid, t):
    """Elemento que algum status pôs na arma no instante t (None = nenhum à vista)."""
    for efst, s, e in x.st.get(aid, ()):
        if s <= t <= e:
            if efst in ENDOWS:
                return ENDOWS[efst]
            if efst == WEAPONPROPERTY:
                v = x.c.status_val.get((aid, efst, s), -1)
                if 0 <= v < len(ELEMENTS):
                    return ELEMENTS[v]
    return None


def florescer_windows(x):
    """Trechos do clímax com Pólen (Florescer) no chefe e quanto de resistência a fogo ele perdia."""
    out = []
    for p in x.phases:
        for efst, s, e in x.st.get(p["aid"], ()):
            if efst == FLORESCER and e > max(s, x.climax):
                out.append((max(s, x.climax), e, x.c.status_val.get((p["aid"], efst, s), 0), p))
    return out


def _flor_phase(x, flor):
    if not x.multi:
        return _("Clímax")
    ns = sorted({w[3]["n"] for w in flor})
    return ", ".join(_("Fase %d") % n for n in ns) if ns else x.whole


def _elements(x, alerts, aids, party):
    c = x.c
    defense = boss_element(c, x.key)
    flor = florescer_windows(x)
    agg = collections.defaultdict(collections.Counter)
    endow_unknown = {a: x.unknown(a, ENDOW_IDS, ENDOW_UNSEEN_MS) for a in aids} if party else {}
    for h in x.hits:
        if h.src not in aids or h.t < x.climax:
            continue
        r = agg[h.src]
        in_flor = any(s <= h.t <= e for s, e, _v, _p in flor)
        el = hit_element(h.skill)
        weapon = el == "Weapon"
        state = "known"
        if weapon:
            el = weapon_element(x, h.src, h.t) if party and h.raw == h.src else None
            if el is None and (not party or h.raw != h.src or _active(endow_unknown.get(h.src, []), h.t)):
                state = "unknown"           # pode ter conversor de antes da gravação (ou não dá para ver)
            elif el is None:
                state = "native"            # nenhum conversor/encantamento: elemento da própria arma
        if in_flor:
            r["flor"] += h.dmg
            if el == "Fire":
                r["flor_fire"] += h.dmg
            elif state == "unknown":
                r["flor_unknown"] += h.dmg
            elif state == "native":
                r["flor_native"] += h.dmg
            elif weapon:
                r["flor_other"] += h.dmg
                r["flor_el_" + el] += h.dmg
            else:
                r["flor_fixed"] += h.dmg
        if el is not None and defense is not None:
            rate = attr_rate(el, defense)
            if rate is not None and rate < 100:
                r["bad"] += h.dmg
                r["bad_el_" + el] += h.dmg
        r["all"] += h.dmg
    rows = []
    for a, r in agg.items():
        if not r["all"]:
            continue
        f = r["flor"]
        row = dict(key="el|%d" % a, aid=a, name=c.name_of(a), job=meter.job_name(job_id(c, a)), me=a == c.me,
                   flor=f or None, fire=(r["flor_fire"] / f) if f else None,
                   native=(r["flor_native"] / f) if f else None, unknown=(r["flor_unknown"] / f) if f else None,
                   bad=(r["bad"] / r["all"]) if r["bad"] else None)
        verdict = []
        others = sorted(k[8:] for k in r if k.startswith("flor_el_"))
        names = "/".join(ELEMENT_PT.get(e, e) for e in others)
        dps = x.role.get(a) != "S" if party else r["all"] >= DPS_SHARE * (x.total or 1)
        if f and r["flor_other"] >= 0.3 * f:
            verdict.append(_("arma de %s no Florescer") % names)
            _alert(alerts, 2, _flor_phase(x, flor), _("Sem fogo no Florescer"), c.name_of(a),
                   _("%s do dano no Florescer saiu com arma de %s; o chefe estava sem resistência a fogo") % (
                       _pct(r["flor_other"] / f), names))
        elif f and dps and not r["flor_fire"] and r["flor_native"] >= 0.3 * f:
            verdict.append(_("sem fogo visível na arma"))
            _alert(alerts, 1, _flor_phase(x, flor), _("Sem fogo no Florescer?"), c.name_of(a),
                   _("nenhum conversor ou encantamento de fogo durante o Florescer (%s do dano dele ali usava o "
                   "elemento da arma). Se a arma já é de fogo, ignore") % _pct(r["flor_native"] / f))
        elif f and r["flor_fire"]:
            verdict.append(_("fogo em %s do dano no Florescer") % _pct(r["flor_fire"] / f))
        if f and r["flor_unknown"] >= 0.3 * f:
            verdict.append(_("elemento da arma não visível em %s") % _pct(r["flor_unknown"] / f))
        if f and r["flor_fixed"]:
            verdict.append(_("%s com skill de elemento fixo") % _pct(r["flor_fixed"] / f))
        bads = sorted(k[7:] for k in r if k.startswith("bad_el_"))
        if r["bad"] and r["bad"] >= 0.1 * r["all"]:
            rate = min(attr_rate(e, defense) for e in bads)
            verdict.append(_("desvantagem: %s") % "/".join(ELEMENT_PT.get(e, e) for e in bads))
            _alert(alerts, 1, x.whole, _("Atacou com desvantagem elemental"), c.name_of(a),
                   _("%s do dano com %s contra %s %d (%d%% do dano)") % (
                       _pct(r["bad"] / r["all"]), "/".join(ELEMENT_PT.get(e, e) for e in bads),
                       ELEMENT_PT.get(defense[0], defense[0]), defense[1], rate))
        row["verdict"] = " · ".join(verdict)
        row["tag"] = "bad" if (f and r["flor_other"] >= 0.3 * f) or (r["bad"] and r["bad"] >= 0.1 * r["all"]) else (
            "mid" if any(v == _("sem fogo visível na arma") for v in verdict) else "")
        rows.append(row)
    rows.sort(key=lambda r: -(r["flor"] or 0))
    return rows, flor, defense


def _poison(x, alerts):
    c = x.c
    venom_prov = [a for a in x.party if JOB_SKILLS.get(x.jobs[a], set()) & {2021}]
    venom_spans = x.boss_spans({VENOM_IMPRESS})
    venom_seen = bool(venom_spans)
    rows = []
    poisoned = []
    for a in x.party:
        if x.role[a] == "S":
            continue
        ids = POISON_WEAPON | {902}
        spans = x.spans(a, ids) + [(s, e) for efst, s, e in x.st.get(a, ())
                                   if efst == WEAPONPROPERTY and c.status_val.get((a, efst, s)) == 5]
        can = bool(JOB_SKILLS.get(x.jobs[a], set()) & POISON_SKILLS)
        if not spans and not can:
            continue
        wins = []
        for p in x.phases:
            wins += x.alive(a, p["win"])
        unk = x.unknown(a, ids)
        known = an._subtract(wins, unk) if unk else wins
        mine = _uptime(spans, known) if _total(known) >= MIN_WINDOW_MS else (UNKNOWN if wins else None)
        venom = _uptime(venom_spans, wins)
        both = _uptime(_intersect(_merge(spans), _merge(venom_spans)), wins)
        if isinstance(mine, float) and mine >= BAD:
            poisoned.append(a)
        verdict = ""
        if isinstance(mine, float) and mine >= BAD and venom_prov and (venom or 0) < BAD:
            verdict = _("arma com veneno, chefe sem Potencializar Veneno")
            if venom_seen:
                _alert(alerts, 1, x.whole, _("Veneno sem Potencializar Veneno"), c.name_of(a),
                       _("arma com veneno em %s do clímax, mas o chefe teve Potencializar Veneno só %s · quem aplica: "
                       "%s") % (_pct(mine), _pct(venom), _names(c, venom_prov)))
        elif (venom or 0) >= BAD and can and isinstance(mine, float) and mine < BAD:
            verdict = _("chefe com Potencializar Veneno, arma sem veneno")
            _alert(alerts, 1, x.whole, _("Arma sem veneno"), c.name_of(a),
                   _("o chefe estava com Potencializar Veneno em %s do clímax e a arma com veneno só %s") % (
                       _pct(venom), _pct(mine)))
        elif mine and venom:
            verdict = _("os dois juntos em %s do clímax") % _pct(both)
        rows.append(dict(key="pz|%d" % a, aid=a, name=c.name_of(a), job=meter.job_name(x.jobs[a]), me=a == c.me,
                         weapon=_pct(mine), venom=_pct(venom), both=_pct(both), verdict=verdict,
                         bad=bool(verdict) and "juntos" not in verdict))
    return rows, poisoned


def _magus(x, alerts, flor):
    """Florescer com Clímax nv 4 tira 100% da resistência a fogo."""
    for _s, _e, val, p in flor:
        if 0 < val < 100:
            _alert(alerts, 1, x.phase_name(p), _("Florescer fraco"), "Magus",
                   _("o chefe perdeu só %d%% de resistência a fogo (com Clímax nv 4 seriam 100%%)") % val)


# --- análise completa de uma luta --------------------------------------------------

def analyze(c, key, rng=None):
    if not any(h.out and h.dst == key and an._in(rng, h.t) for h in c.hits):
        return None
    x = Ctx(c, key, rng)
    alerts = []
    buffs = _buff_rows(x, GROUP_BUFFS, "grupo", alerts)
    buffs += _buff_rows(x, DEFENSE_BUFFS, "proteção", alerts)
    buffs += _class_buffs(x, alerts)
    buffs += _elo(x, alerts, x.party)
    refl = reflect_info(x)
    poison_rows, poisoned = _poison(x, alerts)
    claw, claw_execs = _claw(x, alerts, refl, x.party, True)
    _before_claw(x, alerts, refl, x.party)
    debuffs = _debuffs(x, alerts, refl, poisoned, claw)
    deaths = _deaths(x, x.party, alerts, True)
    element, flor, defense = _elements(x, alerts, set(x.party), True)
    _magus(x, alerts, flor)
    o_alerts = []
    o_deaths = _deaths(x, x.others, o_alerts, False)
    o_element, _f, _d = _elements(x, o_alerts, set(x.others), False)
    o_claw, o_claw_execs = _claw(x, o_alerts, refl, x.others, False)
    _before_claw(x, o_alerts, refl, x.others)
    _elo(x, o_alerts, x.others)
    total = x.total or 1
    party_rows = [dict(key=a, aid=a, name=c.name_of(a), job=meter.job_name(x.jobs[a]), me=a == c.me,
                       dmg=x.dmg.get(a, 0), share=x.dmg.get(a, 0) / total,
                       role={"W": _("físico"), "M": _("mágico"), "S": _("suporte")}[x.role[a]],
                       deaths=len(x.dead.get(a, ())) or None) for a in x.party]
    party_rows.sort(key=lambda r: -r["dmg"])
    others = []
    for a in x.others:
        ds = x.dead.get(a, ())
        others.append(dict(key=a, aid=a, name=c.name_of(a), job=meter.job_name(job_id(c, a)), me=False,
                           dmg=x.dmg.get(a, 0), share=x.dmg.get(a, 0) / total, deaths=len(ds) or None,
                           dead_ms=max(((b if b is not None else x.end) - t for t, b, _x in ds), default=None)))
    others.sort(key=lambda r: -r["dmg"])
    for lst in (alerts, o_alerts):
        lst.sort(key=lambda r: (-r["sev"], r["phase"] == x.whole, r["phase"], r["what"]))
        for i, r in enumerate(lst):
            r["key"] = i
    return dict(key=key, name=c.target_name(key), start=x.start, end=x.end, killed=x.killed, total=x.total,
                hp=x.hp, hp_label=x.hp_label, hp_how=x.hp_how, hp_table=x.hp_table,
                climax=x.climax, phases=x.phases, multi=x.multi, party=party_rows, others=others,
                alerts=alerts, buffs=buffs, debuffs=debuffs, deaths=deaths, element=element, poison=poison_rows,
                o_alerts=o_alerts, o_deaths=o_deaths, o_element=o_element, reflect=refl, florescer=flor,
                claw=claw, claw_execs=claw_execs, o_claw=o_claw, o_claw_execs=o_claw_execs,
                defense=defense, best=best_elements(defense), late_start=x.start < UNSEEN_MS)


def climax_text(r):
    if r.get("hp_table"):
        how = _("HP %s, %s — %s") % (num(r["hp"]), r["hp_label"], r["hp_how"])
    elif r["killed"]:
        how = _("o chefe morreu: HP = dano total")
    else:
        how = _("estimado: o chefe não morreu, conta o dano feito até agora")
    return _("Clímax a partir de %s, depois dos primeiros %d%% do HP (%s)") % (an._dur(r["climax"]),
                                                                          round(CLIMAX_HP * 100), how)


def report_text(c, r):
    """Texto para colar no Discord/WhatsApp."""
    def line(a):
        return "%s %s · %s · %s%s" % (a["sev_txt"].split()[0], a["phase"], a["what"], a["who"],
                                      (" — " + a["detail"]) if a["detail"] else "")
    lines = [_("Dedo Duro — %s · %s–%s%s") % (r["name"], an._dur(r["start"]), an._dur(r["end"]),
                                          _(" · morto") if r["killed"] else ""), climax_text(r)]
    lines.append(_("Grupo:") if r["alerts"] else _("Grupo: nada para apontar."))
    lines += [line(a) for a in r["alerts"] if a["sev"] > 0]
    if r["o_alerts"]:
        lines.append(_("Fora do grupo:"))
        lines += [line(a) for a in r["o_alerts"] if a["sev"] > 0]
    return "\n".join(lines)
