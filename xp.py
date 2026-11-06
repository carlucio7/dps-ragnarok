# -*- coding: utf-8 -*-
"""Estimativa da XP de base dos abates de quem grava.

O replay não grava a XP ganha: só a XP total no início de cada gravação (sessão, chunk 1015). A estimativa é

    XP de um abate = XP do monstro × penalidade de nível ÷ 100 (arredondada para baixo) × parte do dano × fator

- XP do monstro: data/mob_exp.json (rAthena, mais os monstros novos com a XP do Divine Pride).
- Penalidade de nível: a mesma tabela do rAthena e do Divine Pride (nível do monstro − nível do jogador).
- Parte do dano: quanto do dano no monstro foi de quem grava (grupo dividindo XP não entra).
- Fator: os bônus somados (servidor, VIP, manuais, equipamentos...). O replay só mostra que um bônus de
  período está ativo, não quanto ele dá, então o fator é calibrado com duas gravações seguidas do mesmo
  personagem (a XP exata entre elas ÷ a XP estimada dos abates) ou vem do bônus que a pessoa informa.
"""

import datetime
import json
import os
import re
import sys
import threading

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


def penalty(diff):
    for d, rate in PENALTY_UP:
        if diff >= d:
            return rate
    for d, rate in PENALTY_DOWN:
        if diff <= d:
            return rate
    return 100


_CACHE = {}


def kills(c, rng=None):
    """Abates em que quem grava bateu: (linhas, abates sem XP conhecida).
    linha: t, aid, mob, name, lv, share (parte do dano), pen (%), xp (sem o fator)."""
    sig = (id(c), c.version, rng)
    hit = _CACHE.get("k")
    if hit and hit[0] == sig:
        return hit[1]
    dead = {aid for t, aid in c.death_log if rng is None or rng[0] <= t <= rng[1]}
    mine, total = {}, {}
    for h in c.hits:
        if h.dst in dead and h.dmg > 0:
            total[h.dst] = total.get(h.dst, 0) + h.dmg
            if h.src == c.me:
                mine[h.dst] = mine.get(h.dst, 0) + h.dmg
    level = c.session.base_level or 1
    rows, unknown = [], 0
    for t, aid in c.death_log:
        if rng is not None and not rng[0] <= t <= rng[1]:
            continue
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
        pen = penalty(data[0] - level)
        rows.append(dict(t=t, aid=aid, mob=e.job, name=c.name_of(aid), lv=data[0], share=share, pen=pen,
                         xp=(data[1] * pen // 100) * share))
    res = (rows, unknown)
    _CACHE["k"] = (sig, res)
    return res


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


def calibrate(c, cfg, xp_after):
    """Se a próxima gravação do personagem começou logo depois desta, guarda o fator real ÷ estimado
    em cfg["xp_factor"][personagem] = [fator, quando, arquivo]. Devolve o fator novo ou None."""
    s = c.session
    if not getattr(c, "path", None) or not s.gid:
        return None
    nxt = xp_after(c.path, s)
    if not nxt or not nxt["gain"] or nxt["gain"] <= 0:
        return None
    start, other = _seconds(s.recorded_at), _seconds(nxt["when"])
    if start is None or other is None or other - (start + c.now / 1000.0) > CALIBRATE_GAP_S:
        return None
    rows, unknown = kills(c)
    est = sum(r["xp"] for r in rows if r["xp"] is not None)
    if unknown or len(rows) < CALIBRATE_MIN_KILLS or est <= 0:
        return None
    f = round(nxt["gain"] / est, 4)
    table = cfg.setdefault("xp_factor", {})
    table[str(s.gid)] = [f, "%04d-%02d-%02d %02d:%02d" % tuple(s.recorded_at[:5]), os.path.basename(c.path)]
    return f


# Bônus de XP (todos somam). Os detectáveis valem só enquanto o status está ativo em quem grava; os
# consumíveis (manuais) competem entre si: vale só o maior. O Milagre aparece como o status 160 de 1 hora
# (sem ícone no jogo). Evento do servidor e outros não aparecem no replay: a pessoa marca.
BONUSES = [
    dict(key="server", name="Evento do servidor", pct=100, status=None, on=False),
    dict(key="vip", name="VIP (Bônus de EXP II, 30 dias)", pct=20, status=984, on=True, lasting=True),
    dict(key="scepter", name="Cetro do Coração Lunar (Bônus de EXP, 24 h)", pct=30, status=939, on=True, lasting=True),
    dict(key="kafra", name="Kafra Buff / Manual Kafra (7 dias)", pct=50, status=1085, on=True, lasting=True),
    dict(key="manual", name="Manual de combate (consumível)", pct=50, status=250, on=True, group="consumível",
         lasting=True),
    dict(key="njord", name="Banquete de Njord", pct=60, status=78, on=True, val=True),
    dict(key="miracle", name="Milagre Solar, Lunar e Estelar (alvos estelares)", pct=100, status="milagre", on=True),
    dict(key="gear", name="Equipamentos, visuais e cartas (texto dos itens)", pct=0, status="equipamento", on=True,
         val=True),
    # bônus "[Durante o Evento]" do texto dos itens (ex.: Carta Baby Shark): o evento do item costuma acabar antes
    # do item sair do jogo, então fica desligado até a pessoa marcar
    dict(key="gear_event", name="Bônus de evento dos itens ([Durante o Evento])", pct=0, status=None, on=False),
    dict(key="other", name="Outros (equipamentos, cartas, alvos do ódio...)", pct=0, status=None, on=False),
]
# manuais de XP (consumíveis; não acumulam entre si), com o bônus do texto do item na LATAM (Divine Pride)
MANUALS = [("Manual de Combate", 50), ("Manual de Combate com Chiclete", 50), ("Manual de Campo Avançado", 100),
           ("Enciclopédia de Combate", 200), ("Manual de Combate HE", 200), ("Manual de Combate x3", 300)]
MODES = ("lista", "medido", "fixo")


def settings(cfg):
    """{chave: {"on", "pct"}} dos bônus, com os padrões para o que a pessoa ainda não mexeu."""
    saved = cfg.get("xp_bonuses") or {}
    out = {}
    for b in BONUSES:
        st = saved.get(b["key"]) or {}
        pct = st.get("pct")
        out[b["key"]] = dict(on=bool(st.get("on", b["on"])), pct=float(pct) if isinstance(pct, (int, float)) else b["pct"])
    return out


def windows(c, cfg=None):
    """Quando cada bônus detectável esteve ativo em quem grava: {chave: [(início, fim, valor)]}.
    cfg: para saber se os bônus "[Durante o Evento]" dos itens estão marcados."""
    event_on = settings(cfg or {})["gear_event"]["on"]
    out = {}
    for b in BONUSES:
        if b["status"] is None:
            continue
        if b["status"] == "milagre":
            out[b["key"]] = [(s, e, 0) for s, e in c.miracle_windows()]
            continue
        if b["status"] == "equipamento":
            out[b["key"]] = gear_windows(c, event_on)
            continue
        if b.get("lasting"):          # bônus de conta/período e manuais não acabam com a morte
            out[b["key"]] = [(s, e, 0) for s, e in c.lasting(b["status"])]
            continue
        out[b["key"]] = sorted((s, e, c.status_val.get((a, ef, s)) or 0)
                               for a, ef, s, e in c.statuses(c.me) if ef == b["status"])
    return out


def bonus_at(t, wins, sets):
    """Bônus somado (%) num instante, com a regra dos consumíveis (vale o maior)."""
    total, group = 0.0, {}
    for b in BONUSES:
        st = sets[b["key"]]
        if not st["on"]:
            continue
        pct = st["pct"]
        if b["status"] is not None:
            hit = next((v for s, e, v in wins.get(b["key"], ()) if s <= t <= e), None)
            if hit is None:
                continue
            if b.get("val") and hit > 0:
                pct = hit                       # o Banquete de Njord traz o % no próprio status
        if b.get("group"):
            group[b["group"]] = max(group.get(b["group"], 0.0), pct)
        else:
            total += pct
    return total + sum(group.values())


def detected(c, cfg=None):
    """{chave: fração da gravação em que o bônus esteve ativo} dos detectáveis (0 = não apareceu)."""
    span = max(1, c.now)
    out = {}
    for key, ws in windows(c, cfg).items():
        out[key] = min(1.0, sum(max(0, min(e, c.now) - max(0, s)) for s, e, _v in ws) / float(span))
    return out


def factor(c, cfg):
    """(fator fixo ou None, origem). None = pela lista de bônus, golpe a golpe.
    origem: ("lista", None) | ("medido", "AAAA-MM-DD HH:MM") | ("fixo", bônus %)."""
    mode = cfg.get("xp_mode") if cfg.get("xp_mode") in MODES else "lista"
    if mode == "medido":
        cal = (cfg.get("xp_factor") or {}).get(str(c.session.gid))
        if cal:
            return float(cal[0]), ("medido", cal[1])
    if mode == "fixo" and isinstance(cfg.get("xp_fixed"), (int, float)):
        return (100.0 + cfg["xp_fixed"]) / 100.0, ("fixo", cfg["xp_fixed"])
    return None, ("lista", None)


def estimate(c, cfg, rng=None):
    """XP de base estimada no recorte: dict(xp, base, kills, unknown, factor (médio), source, per_hour,
    per_min, per_min_pct (% do nível por minuto), rows (com "total" de cada abate))."""
    rows, unknown = kills(c, rng)
    f, source = factor(c, cfg)
    if f is None:
        wins, sets = windows(c, cfg), settings(cfg)
    total = base = 0.0
    for r in rows:
        if r["xp"] is None:
            r["total"] = None
            continue
        k = f if f is not None else 1.0 + bonus_at(r["t"], wins, sets) / 100.0
        r["total"] = r["xp"] * k
        base += r["xp"]
        total += r["total"]
    span = (rng[1] - rng[0]) if rng else c.now
    per_min = total * 60000.0 / span if span and span > 60000 else None
    nxt = c.session.next_exp
    return dict(xp=total, base=base, kills=len(rows), unknown=unknown, factor=(total / base) if base else (f or 1.0),
                source=source, per_hour=per_min * 60 if per_min is not None else None, per_min=per_min,
                per_min_pct=(100.0 * per_min / nxt) if per_min is not None and nxt else None, rows=rows)


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
        self.table, self.names, self._thread = None, {}, None

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
                self.table = parse_gear(items)
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


def gear_bonus(worn, event_on, table=None, names=None):
    """(% de XP dos itens vestidos, [itens que deram bônus]) para {bit do slot: Item}."""
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
            if event and not event_on:
                continue
            if group and not all(_norm(n) in worn_names for n in group):
                continue
            got += pct
        if got:
            total += got
            who.append(i)
    return total, who


def gear_windows(c, event_on):
    """[(início, fim, %)] do bônus dos itens vestidos, a cada troca de equipamento."""
    GEAR.start(_iteminfo_path())
    if GEAR.table is None:
        return []
    out = []
    log = getattr(c, "equip_log", None) or [(0, {})]
    for i, (t, state) in enumerate(log):
        end = log[i + 1][0] if i + 1 < len(log) else max(c.now, t)
        pct, _who = gear_bonus(state, event_on)
        if pct:
            out.append((t, end, pct))
    return out
