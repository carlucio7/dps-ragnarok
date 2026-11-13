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
import sys
import threading
import weakref

_DATA = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "data")

try:
    with open(os.path.join(_DATA, "mob_exp.json"), encoding="utf-8") as _f:
        MOB_EXP = {int(k): v for k, v in json.load(_f).items()}
except (OSError, ValueError):
    MOB_EXP = {}

# diferença (nível do monstro − nível do jogador) -> % da XP
PENALTY_UP = ((16, 40), (15, 115), (14, 120), (13, 125), (12, 130), (11, 135), (10, 140), (9, 135), (8, 130),
              (7, 125), (6, 120), (5, 115), (4, 110), (3, 105))
PENALTY_DOWN = ((-31, 10), (-26, 35), (-21, 60), (-16, 85), (-11, 90), (-6, 95))
CALIBRATE_GAP_S = 60          # a próxima gravação começou até 1 min depois do fim desta
CALIBRATE_MIN_KILLS = 3
CALIBRATE_MIN_MS = 10 * 60000  # trecho curto não calibra (30 s de gravação davam um fator 20% errado)...
CALIBRATE_MIN_FRAC = 0.01     # ...a não ser que já tenha rendido 1% do nível (o que vier primeiro)
CALIBRATE_KEEP = 12           # medidas guardadas por personagem (a média pesa cada uma pela XP que cobre)
PACE_MS = 10 * 60000          # o tempo até o nível usa o ritmo dos últimos 10 min de farm
WARMUP_MS, WARMUP_FRAC = 10 * 60000, 0.01   # a previsão só aparece depois de 10 min de farm ou 1% do nível
FARM_FRAC = 0.4               # o farm começa no 1º minuto que rende 40% do melhor minuto (antes: preparação)

# XP de cada nível nas classes 4 do LATAM: a do nível anterior × 1,22, arredondada para baixo. Conferido nos
# replays: a partir do 224 (1.868.364.511) sai exatamente o que o jogo mandou do 240 ao 248. 250 é o máximo.
FOURTH_JOBS = set(range(4252, 4265)) | set(range(4278, 4282)) | set(range(4302, 4309)) | {4316}
TABLE_4TH_FROM = (224, 1868364511)
MAX_LEVEL_4TH = 250


def table_need(job, level):
    """XP do nível `level` (para chegar ao seguinte) pela tabela conhecida, ou None."""
    lv, need = TABLE_4TH_FROM
    if job not in FOURTH_JOBS or not lv <= level < MAX_LEVEL_4TH:
        return None
    for _i in range(level - lv):
        need = need * 122 // 100
    return need


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
    hits = c.hits
    first = hits[0] if hits else None
    names = _names_version()
    if (st is None or st["c"]() is not c or st["n"] > len(hits) or (st["n"] and st["first"] is not first)
            or st["names"] != names):
        st = _CACHE["k"] = dict(c=weakref.ref(c), n=0, first=first, mine={}, total={}, sig=None, res=([], 0),
                                times=[], ordered=True, names=names)
    n = st["n"]
    if n < len(hits):
        mine, total, me = st["mine"], st["total"], c.me
        for i in range(n, len(hits)):
            h = hits[i]
            if h.dmg > 0:
                d = h.dst
                total[d] = total.get(d, 0) + h.dmg
                if h.src == me:
                    mine[d] = mine.get(d, 0) + h.dmg
        st["n"], st["first"] = len(hits), hits[0]
    sig = (c.version, len(c.death_log), len(hits))
    if st["sig"] != sig:
        st["sig"] = sig
        st["res"] = _all_kills(c, st["mine"], st["total"])
        times = st["times"] = [r["t"] for r in st["res"][0]]
        st["ordered"] = all(a <= b for a, b in zip(times, times[1:]))
    return st


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


def _all_kills(c, mine=None, total=None):
    """As linhas dos abates. `mine` e `total`: dano de quem grava e de todos em cada monstro, se já somados."""
    if mine is None:
        dead = {aid for t, aid in c.death_log}
        mine, total = {}, {}
        for h in c.hits:
            if h.dst in dead and h.dmg > 0:
                total[h.dst] = total.get(h.dst, 0) + h.dmg
                if h.src == c.me:
                    mine[h.dst] = mine.get(h.dst, 0) + h.dmg
    rows, unknown = [], 0
    for t, aid in c.death_log:
        e = c.entities.get(aid)
        if e is None or e.kind != "mob" or c.is_friendly(aid) or not mine.get(aid):
            continue
        share = mine[aid] / float(total[aid])
        data = MOB_EXP.get(e.job)
        if not data:                     # sem dado; XP 0 = o monstro não dá XP (instância, desafio...)
            unknown += 1
            rows.append(dict(t=t, aid=aid, mob=e.job, name=c.name_of(aid), lv=data[0] if data else None,
                             share=share, pen=None, xp=None))
            continue
        pen = penalty(data[0] - level_at(c, t))
        rows.append(dict(t=t, aid=aid, mob=e.job, name=c.name_of(aid), lv=data[0], share=share, pen=pen,
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
    """XP do nível `level` para quem grava: a que o jogo mandou no começo da gravação, a da tabela conhecida ou a
    que já apareceu em outra gravação dessa classe (cfg["xp_levels"]). None se não se sabe."""
    ses = c.session
    if level == ses.base_level and ses.next_exp:
        return ses.next_exp
    n = table_need(ses.job, level)
    if n:
        return n
    return ((cfg or {}).get("xp_levels") or {}).get(str(ses.job), {}).get(str(level))


def anchors(c):
    """Pontos em que a XP de quem grava é exata: [(t, nível, XP no nível)] — o começo da gravação e cada subida
    de nível (XP 0 no nível novo; a sobra do abate que subiu fica de fora, é pouca)."""
    ses = c.session
    if ses.base_exp is None or not ses.base_level:
        return []
    return [(0, ses.base_level, ses.base_exp)] + [(t, lv, 0) for t, lv in getattr(c, "level_ups", ())]


def level_segments(c, cfg):
    """Trechos da gravação com a XP real exata: de um ponto exato até a subida de nível seguinte.
    [(início, fim, XP real)]."""
    out = []
    an = anchors(c)
    for (t0, lv, x0), (t1, lv1, _x) in zip(an, an[1:]):
        nd = need(c, cfg, lv)
        if lv1 == lv + 1 and nd:
            out.append((t0, t1, nd - x0))
    return out


def quest_in(c, t0, t1):
    """True se quem grava concluiu ou entregou alguma missão no trecho: a XP da recompensa não vem de abate, então
    o trecho não serve para medir a XP dos abates (uma entrega de diária no Porão rendeu 3% do nível de uma vez)."""
    return any(t0 <= t <= t1 for t, _q in getattr(c, "quests_done", ()))


def _list_xp(c, cfg, rng):
    """XP dos abates do trecho pela lista de bônus (sem correção e sem missões), ou None se não dá para medir."""
    est = estimate(c, dict(cfg or {}, xp_mode="lista"), rng)
    return None if est["unknown"] or not est["kill_xp"] else est["kill_xp"]


def session_correction(c, cfg):
    """(real ÷ lista, XP real coberta) das subidas de nível desta gravação, ou None."""
    # os trechos já fecharam (terminam numa subida de nível): não mudam com o que chega depois
    sig = (id(c), len(getattr(c, "level_ups", ())), len(getattr(c, "quests_done", ())),
           repr(sorted((cfg or {}).get("xp_bonuses", {}).items())))
    hit = _CACHE.get("sc")
    if hit and hit[0] == sig:
        return hit[1]
    real = est = 0.0
    for t0, t1, gain in level_segments(c, cfg):
        if quest_in(c, t0, t1):
            continue
        e = _list_xp(c, cfg, (t0, t1))
        if e:
            real += gain
            est += e
    res = (real / est, real) if est else None
    _CACHE["sc"] = (sig, res)
    return res


def stored_correction(c, cfg):
    """(correção média das gravações longas deste personagem, nº de medidas) ou None."""
    entry = ((cfg or {}).get("xp_corr") or {}).get(str(c.session.gid))
    samples = (entry or {}).get("samples") or []
    w = sum(x[1] for x in samples)
    if not w:
        return None
    return sum(x[0] * x[1] for x in samples) / w, len(samples)


def correction(c, cfg):
    """A correção que vale agora: a das subidas de nível desta gravação, senão a média guardada.
    (correção, origem) ou (None, None)."""
    sc = session_correction(c, cfg)
    if sc:
        return sc[0], "nivel"
    st = stored_correction(c, cfg)
    if st:
        return st[0], st[1]
    return None, None


def calibrate(c, cfg, xp_after):
    """Guarda em cfg["xp_corr"][personagem] as medidas de "XP real ÷ XP pela lista" desta gravação: cada trecho
    até uma subida de nível e o trecho até a gravação seguinte (se ela começou logo depois). Trecho com menos de
    10 min não conta. Também anota a XP do nível que o jogo mandou (cfg["xp_levels"]). Devolve a correção média
    nova ou None."""
    s = c.session
    if not getattr(c, "path", None) or not s.gid:
        return None
    if s.base_level and s.next_exp and s.next_exp != 999999999:
        cfg.setdefault("xp_levels", {}).setdefault(str(s.job), {})[str(s.base_level)] = s.next_exp
    remember_manual(c, cfg)
    segs = exact_segments(c, cfg, xp_after)
    detect_server(c, cfg, segs)                  # antes de medir: a correção é sobre a lista já acertada
    when = "%04d-%02d-%02d %02d:%02d" % tuple(s.recorded_at[:5])
    name = os.path.basename(c.path)
    new = []
    for t0, t1, gain, tag in segs:
        if quest_in(c, t0, t1) or not _big(c, cfg, t0, t1, gain):
            continue
        est = _list_xp(c, cfg, (t0, t1))
        if est:
            new.append([round(gain / est, 4), gain, when, "%s#%s" % (name, tag)])
    learn_quests(c, cfg, segs)
    if not new:
        return None
    entry = cfg.setdefault("xp_corr", {}).setdefault(str(s.gid), {})
    keep = [x for x in entry.get("samples", []) if not x[3].startswith(name + "#")] + new
    entry["samples"] = keep[-CALIBRATE_KEEP:]
    return stored_correction(c, cfg)[0]


def exact_segments(c, cfg, xp_after=None):
    """Trechos da gravação com a XP real exata: [(início, fim, XP real, rótulo)]. Cada subida de nível fecha um; com
    `xp_after`, o último vai até o começo da gravação seguinte do personagem, se ela começou logo depois."""
    s = c.session
    segs = [(t0, t1, gain, "%d" % i) for i, (t0, t1, gain) in enumerate(level_segments(c, cfg))]
    an = anchors(c)
    nxt = xp_after(c.path, s) if xp_after is not None and getattr(c, "path", None) else None
    if an and nxt and nxt.get("exp") is not None:
        start, other = _seconds(s.recorded_at), _seconds(nxt["when"])
        if start is not None and other is not None and other - (start + c.now / 1000.0) <= CALIBRATE_GAP_S:
            t0, lv, x0 = an[-1]                 # do último ponto exato até o começo da gravação seguinte
            gain = None
            if nxt["level"] == lv:
                gain = nxt["exp"] - x0
            elif nxt["level"] == lv + 1 and need(c, cfg, lv):
                gain = need(c, cfg, lv) - x0 + nxt["exp"]
            if gain and gain > 0:
                segs.append((t0, c.now, gain, "fim"))
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


def detect_server(c, cfg, segs=None, xp_after=None):
    """Deduz o evento do servidor da XP exata (só no modo automático). Em cada trecho exato que serve (sem entrega
    de missão, sem manual de valor desconhecido), a lista é refeita com o evento em 0, 50, 100 e 200%; se um deles
    fecha a 6% do real e o que está marcado erra mais de 12%, o programa marca esse (e esquece as medidas antigas,
    que eram sobre a lista errada). Devolve o % novo (0 = sem evento) ou None se nada mudou."""
    if (cfg.get("xp_mode") if cfg.get("xp_mode") in MODES else "auto") != "auto" or not _fresh(c):
        return None
    segs = exact_segments(c, cfg, xp_after) if segs is None else segs
    known = (cfg.get("xp_manual_last") or {}).get(str(c.session.gid))
    use = [(t0, t1, gain) for t0, t1, gain, _tag in segs
           if not quest_in(c, t0, t1) and _big(c, cfg, t0, t1, gain) and (known or not _manual_blind(c, t0, t1))]
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
    cfg.setdefault("xp_bonuses", {})["server"] = dict(on=best > 0, pct=best or 100, auto=True)
    cfg.get("xp_corr", {}).pop(str(c.session.gid), None)
    _CACHE.pop("sc", None)
    return best


def learn_quests(c, cfg, segs):
    """Aprende a XP de uma missão num trecho com XP exata: real − abates − missões já conhecidas. Só quando há uma
    única missão desconhecida no trecho e ela pesa pelo menos um quarto dele (abaixo disso o erro dos abates
    engole a conta). Guarda a recompensa sem bônus em cfg["xp_quests"]. True se aprendeu alguma."""
    if not QUEST_XP_ON:
        return False
    corr = correction(c, cfg)[0] or 1.0
    learned = False
    for t0, t1, gain, _tag in segs:
        qs = quest_rows(c, cfg, (t0, t1))
        unknown = [q for q in qs if q["xp"] is None]
        if len(unknown) != 1 or len({q["quest"] for q in unknown}) != 1:
            continue
        est = _list_xp(c, cfg, (t0, t1))
        if not est:
            continue
        rest = gain - est * corr - sum(q["xp"] for q in qs if q["xp"])
        if rest < QUEST_LEARN_MIN * gain:
            continue
        q = unknown[0]
        cfg.setdefault("xp_quests", {})[str(q["quest"])] = dict(base=int(round(rest / q["mult"])),
                                                              level=level_at(c, q["t"]))
        learned = True
    return learned


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
# pontos em quem foi medido, então qual dos dois fica em g é o mais provável (o Kafra é da família dos manuais,
# e a XP das missões fecha com manual + Kafra), não medido.
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
        m = _CACHE["m"] = dict(c=weakref.ref(c), sig=sig, wins={}, fac={}, farm=())
    return m


def windows(c, cfg=None):
    """Quando cada bônus detectável esteve ativo em quem grava: {chave: [(início, fim, valor)]}.
    cfg: para saber se os bônus "[Durante o Evento]" dos itens estão marcados."""
    event_on = settings(cfg or {})["gear_event"]["on"]
    off = event_off(cfg or {})
    store = _moment(c)["wins"]
    out = store.get((event_on, off))
    if out is None:
        out = store[(event_on, off)] = _windows(c, event_on, off)
    return dict(out)


def _windows(c, event_on, off):
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
            ln = c.status_len.get((a, ef, st))
            out.append((st, min(c.now, max(e, st + ln)) if ln else c.now, c.status_val.get((a, ef, st)) or 0))
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
    out, group = {"g": 0.0, "k": 0.0, "p": 0.0, "first": 0.0}, {}
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


def factor_at(t, wins, sets, mob=None, marks=None, parts=None):
    """Fator de XP de um abate: [(1 + g) × (1 + k) + p] × (1 + primeiro passo). `mob` e `marks` (marks_of) entram
    só para o alvo da Oposição, quando não há Milagre. `parts`: os bônus do instante, se já calculados."""
    a = parts_at(t, wins, sets) if parts is None else parts
    first = a["first"] or mark_pct(marks, t, mob)
    return ((1.0 + a["g"] / 100.0) * (1.0 + a["k"] / 100.0) + a["p"] / 100.0) * (1.0 + first / 100.0)


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
    key = (settings(cfg or {})["gear_event"]["on"], event_off(cfg or {}), repr(sorted(sets.items())))
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


# XP das missões: o replay mostra a entrega (a missão sai da lista), não quanto ela rende, e o jogo instalado só
# traz a recompensa de 50 das 10 mil missões. DESLIGADO por enquanto (QUEST_XP_ON): só duas entregas foram medidas
# com a XP exata (capturas de 2026-11-11, nível 247, com evento, VIP, Cetro, Kafra, manual 100%, Njord e Milagre
# ativos), e a regra dos bônus ainda não fecha. Sobre os valores oficiais (iRO Wiki, "Clock Tower: Unknown
# Basement": Jantar 698.346.800, Mímico 1.745.867), o Jantar rendeu ×8 e o Mímico ×4 na mesma entrega; o Mímico
# fecha ao ponto com ×2,5 (manual + Kafra) e ×1,6 (Njord), o Jantar tem um ×2 a mais ainda sem explicação.
# Enquanto estiver desligado, as entregas aparecem listadas mas a XP delas não entra na estimativa; os trechos
# com entrega continuam fora da calibração (quest_in).
QUEST_XP_ON = False
QUEST_XP = {5964: 2234709760,        # [Diário] Jantar do Diabo: o medido ÷ 2,5 (hipótese manual + Kafra)
            5970: 2793387}           # [Diário] Mímico de Estimação: idem
QUEST_KEYS = ("manual", "kafra")     # os bônus que valeriam na XP de missão (hipótese)
QUEST_LEARN_MIN = 0.25               # só aprende a XP de uma missão que pese pelo menos isso do trecho exato


def quest_base(qid, cfg):
    """Recompensa da missão sem bônus (a aprendida, senão a da tabela) ou None. Sempre None com QUEST_XP_ON
    desligado."""
    if not QUEST_XP_ON:
        return None
    learned = ((cfg or {}).get("xp_quests") or {}).get(str(qid))
    if isinstance(learned, dict) and isinstance(learned.get("base"), (int, float)) and learned["base"] > 0:
        return float(learned["base"])
    return QUEST_XP.get(qid)


def quest_mult(t, wins, sets):
    """Multiplicador da XP de missão num instante: 1 + manual + Kafra Buff."""
    extra, best = 0.0, 0.0
    for b in BONUSES:
        if b["key"] in QUEST_KEYS:
            pct = _pct_at(b, t, wins, sets)
            if pct is not None:
                if b.get("group"):
                    best = max(best, pct)
                else:
                    extra += pct
    return 1.0 + (extra + best) / 100.0


def quest_rows(c, cfg, rng=None, wins=None, sets=None):
    """Missões entregues por quem grava no recorte: [dict(t, quest, base, mult, xp)] (xp None = recompensa que o
    programa ainda não conhece)."""
    done = [(t, q) for t, q in getattr(c, "quests_done", ()) if rng is None or rng[0] <= t <= rng[1]]
    if not done:
        return []
    wins = windows(c, cfg) if wins is None else wins
    sets = settings(cfg, c) if sets is None else sets
    out = []
    for t, q in done:
        base = quest_base(q, cfg)
        mult = quest_mult(t, wins, sets)
        out.append(dict(t=t, quest=q, base=base, mult=mult, xp=base * mult if base else None))
    return out


def quests_uncounted(c, cfg=None):
    """Quantas missões foram entregues desde o último ponto exato (começo da gravação ou subida de nível) sem a
    XP entrar na conta. Enquanto houver alguma, o nível mostrado está abaixo do real e o tempo até o próximo nível,
    acima: a tela avisa."""
    an = anchors(c)
    since = an[-1][0] if an else 0
    return sum(1 for q in quest_rows(c, cfg or {}, (since, c.now)) if q["xp"] is None)


def estimate(c, cfg, rng=None):
    """XP de base estimada no recorte: dict(xp (abates + missões), kill_xp, quest_xp, quests (quest_rows),
    quests_unknown, base, kills, unknown, factor (médio dos abates), source, per_hour, per_min, per_min_pct (% do
    nível por minuto; ritmo só dos abates), rows (com "total" de cada abate))."""
    rows, unknown = kills(c, rng)
    f, source, corr = factor(c, cfg)
    wins = sets = None
    if f is None:
        wins, sets, marks = windows(c, cfg), settings(cfg, c), marks_of(c)
        parts = _parts(c, cfg, wins, sets)
    total = base = 0.0
    for r in rows:
        if r["xp"] is None:
            r["total"] = None
            continue
        k = f if f is not None else factor_at(r["t"], wins, sets, r["mob"], marks, parts.at(r["t"])) * corr
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
                import lub
                with open(path, "rb") as f:
                    items = lub.run(f.read()).get("tbl") or {}
                self.names = {i: _norm(v.get("identifiedDisplayName")) for i, v in items.items()
                              if isinstance(i, int) and isinstance(v, dict)}
                self.display = {i: " ".join(v["identifiedDisplayName"].split()) for i, v in items.items()
                                if isinstance(i, int) and isinstance(v, dict)
                                and isinstance(v.get("identifiedDisplayName"), str) and v["identifiedDisplayName"].strip()}
                self.art = {i: v["identifiedResourceName"] for i, v in items.items()
                            if isinstance(i, int) and isinstance(v, dict)
                            and isinstance(v.get("identifiedResourceName"), str) and v["identifiedResourceName"]}
                self.table = parse_gear(items)
                import itemkind                  # categorias dos itens (cores dos drops), do mesmo arquivo
                self.kinds = itemkind.parse_kinds(items)
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
    """{item: %} dos itens com bônus "[Durante o Evento]" vestidos em algum momento da gravação."""
    GEAR.start(_iteminfo_path())
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
    if not an:
        return None
    ta, lv, x0 = an[-1]
    nd = need(c, cfg, lv)
    xpv = x0 + (estimate(c, cfg, (ta, t))["xp"] if t > ta else 0.0)
    return dict(level=lv, xp=xpv, need=nd, pct=(100.0 * xpv / nd) if nd else None, since=ta)


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


def warming_up(c, cfg):
    """True enquanto a previsão ainda não vale: menos de 10 min de farm e menos de 1% do nível ganho."""
    start = farm_start(c)
    if start is None:
        return True
    if c.now - start >= WARMUP_MS:
        return False
    nd = need(c, cfg, c.session.base_level) if c.session.base_level else None
    return not (nd and estimate(c, cfg, (0, c.now))["kill_xp"] >= WARMUP_FRAC * nd)


def recent_pace(c, cfg):
    """XP por minuto nos últimos 10 min de farm (contando do começo do farm, não da gravação), ou None enquanto
    aquece (warming_up)."""
    start = farm_start(c)
    if start is None or warming_up(c, cfg):
        return None
    span = min(PACE_MS, c.now - start)
    if span <= 0:
        return None
    rate = estimate(c, cfg, (c.now - span, c.now))["kill_xp"] * 60000.0 / span     # ritmo só dos abates
    return rate if rate > 0 else None


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
