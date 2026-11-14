"""Testes de build guardados no PC (histórico local, nada é enviado para lugar nenhum).

Cada teste guarda: personagem, alvo, tempo em combate, dano e DPS, as skills, os
buffs (com % do tempo ativo) e o equipamento vestido no começo da luta. Desde a 1.7 (v = 2) também os atributos de
quem gravou durante a luta (ASPD, ATQ, precisão...), conjuração e recarga por skill, a pós-conjuração e os itens
usados; os testes antigos continuam abrindo, com "—" no que não foi guardado.
"""

import json
import os
import time

import analysis as an
import meter
import stats
from fmt import dec, dur, full
from i18n import _

DUMMY_IDS = set(range(21060, 21100))      # bonecos de treino (Dummy - Dragão, Bruto, Amorfo...)
MIN_COMBAT_MS = 5000                      # testes mais curtos que isso não são salvos sozinhos
MAX_TESTS = 1000


def is_dummy(c, aid):
    e = c.entities.get(aid)
    return e is not None and (e.job in DUMMY_IDS or (e.name or "").lower().startswith("dummy"))


def main_target(enc):
    return max(enc.by_target.items(), key=lambda kv: kv[1])[0] if enc.by_target else None


def build(rf, enc, label=""):
    """Registro de um teste a partir de um encontro (ou da sessão, se enc for None)."""
    c, s = rf.combat, rf.session
    rng, dur_ms = an.scope_range(c, enc)
    sm = an.summary(c, rng, dur_ms)
    target = main_target(enc if enc is not None else c.total) if (enc or c.total) else None
    start = enc.start if enc is not None else (c.total.start if c.total else 0)
    buffs, _total = an.buff_uptime(c, c.me, rng)
    span = stats.span(c, rng) if enc is not None else (start, c.now)
    cast_rows = {r["skill"]: r for r in stats.casts(c, span)}
    return dict(
        v=2, adps=sm["active_dps"], active_ms=sm["active_ms"], crits=sm["crits"], misses=sm["misses"],
        taken=sm["taken"], deaths=sm["deaths"],
        stats={k: list(v) for k, v in stats.values(c, span).items()},
        casts=[dict(name=r["name"], n=r["n"], cast=r["cast"], cooldown=r["cooldown"])
               for r in list(cast_rows.values())[:14]],
        post=stats.post_delay(c, span), blocked=stats.blocked(c, span), stopped=stats.stopped(c, span),
        items=[dict(name=r["name"], item=r["item"], n=r["n"]) for r in stats.items_used(c, span)[:12]],
        id="%d-%s" % (int(time.time() * 1000), os.urandom(2).hex()),
        key="%s|%d" % (os.path.basename(rf.path), start),
        saved_at=time.time(), replay=os.path.basename(rf.path), recorded_at=list(s.recorded_at),
        char=s.player, job=meter.job_name(s.job), level=s.base_level, map=c.map or s.map,
        target=c.target_name(target) if target is not None else "", dummy=bool(target and is_dummy(c, target)),
        start=start, combat_ms=dur_ms, damage=sm["dealt"], dps=sm["dps"], eff_dps=sm["effective_dps"],
        hits=sm["hits"], max_hit=sm["best"]["dmg"] if sm["best"] else 0,
        skills=[dict(name=k["name"], total=k["total"], hits=k["hits"], share=k["share"], avg=k["avg"],
                     max_hit=k["max_hit"], cast=k["cast"],
                     cooldown=(cast_rows.get(k["skill"]) or {}).get("cooldown"))
                for k in an.player_skills(c, rng, c.me, dur_ms)],
        buffs=[dict(name=b["name"], kind=b["kind"], uptime=b["uptime"]) for b in buffs
               if b["kind"] != "Serviço" and (b["uptime"] or 0) > 0],
        equip=an.equipment(c, start), label=label,
    )


class Store:
    def __init__(self, path):
        self.path = path
        self.records = []
        self.mtime = None
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.records = [r for r in data if isinstance(r, dict) and r.get("id")] if isinstance(data, list) else []
            self.mtime = os.path.getmtime(self.path)
        except (OSError, ValueError):
            self.records = []

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.records[:MAX_TESTS], f, ensure_ascii=False)
            os.replace(tmp, self.path)
            self.mtime = os.path.getmtime(self.path)
        except OSError:
            pass

    def keys(self):
        return {r.get("key") for r in self.records}

    def add(self, rec):
        if rec.get("key") in self.keys():
            return False
        self.records.insert(0, rec)
        self.save()
        return True

    def delete(self, ids):
        ids = set(ids)
        self.records = [r for r in self.records if r["id"] not in ids]
        self.save()

    def rename(self, rid, label):
        for r in self.records:
            if r["id"] == rid:
                r["label"] = label
        self.save()

    def get(self, rid):
        return next((r for r in self.records if r["id"] == rid), None)

    def previous(self, rec):
        """O teste anterior do mesmo personagem (para comparar quando só um está escolhido)."""
        older = [r for r in self.records if r["char"] == rec["char"] and r["saved_at"] < rec["saved_at"]
                 and r["id"] != rec["id"]]
        return max(older, key=lambda r: (r.get("recorded_at"), r.get("start", 0)), default=None)


def auto_save(store, rf, already):
    """Salva os encontros encerrados contra bonecos de treino. `already` guarda o que já
    foi visto nesta sessão, para não refazer a conta a cada leitura."""
    c = rf.combat
    if c is None:
        return 0
    saved = 0
    keys = store.keys()
    for enc in c.encounters():
        if c.is_live(enc):
            continue
        key = "%s|%d" % (os.path.basename(rf.path), enc.start)
        if key in already or key in keys:
            continue
        already.add(key)
        target = main_target(enc)
        if target is None or not is_dummy(c, target) or enc.duration_ms() < MIN_COMBAT_MS:
            continue
        if store.add(build(rf, enc)):
            saved += 1
    return saved


SIDE_SKILLS = 8               # skills, buffs e itens mostrados na comparação lado a lado
SIDE_BUFFS = 14
SIDE_ITEMS = 8


def _ms(v):
    return "%d ms" % round(v) if v else _("instantânea")


def sides(a, b):
    """A comparação lado a lado de dois testes (b pode ser None): linhas para ui_parts.Butterfly, em seções.
    Cada linha diz qual lado é melhor quando mais alto ("high") ou mais baixo ("low")."""
    b = b or {}
    out = []

    def head(name):
        out.append(dict(kind="head", name=name))

    def row(name, va, vb, fmt, better="high", bar=True):
        out.append(dict(name=name, a=va, b=vb, a_txt=fmt(va) if va is not None else None,
                        b_txt=fmt(vb) if vb is not None else None, better=better, bar=bar))

    def get(rec, key):
        v = rec.get(key)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    whole = lambda v: full(round(v))
    pct = lambda v: dec("%.1f%%" % (v * 100))
    head(_("Dano"))
    row(_("DPS (em combate)"), get(a, "dps"), get(b, "dps"), whole)
    row(_("DPS ativo"), get(a, "adps"), get(b, "adps"), whole)
    row(_("DPS do 1º ao último golpe"), get(a, "eff_dps"), get(b, "eff_dps"), whole)
    row(_("Dano"), get(a, "damage"), get(b, "damage"), whole)
    row(_("Tempo em combate"), get(a, "combat_ms"), get(b, "combat_ms"), dur, better=None, bar=False)
    row(_("Acertos"), get(a, "hits"), get(b, "hits"), whole, better=None)

    def rate(rec):                              # golpes por segundo no tempo em que estava batendo
        ms = rec.get("active_ms") or rec.get("combat_ms")
        return (rec["hits"] * 1000.0 / ms) if ms and rec.get("hits") else None

    def per_hit(rec):
        return (rec["damage"] / float(rec["hits"])) if rec.get("hits") and rec.get("damage") else None

    def share(rec, key):
        return (rec[key] / float(rec["hits"])) if rec.get("hits") and rec.get(key) is not None else None
    row(_("Golpes por segundo"), rate(a), rate(b), lambda v: dec("%.2f" % v))
    row(_("Dano por golpe"), per_hit(a), per_hit(b), whole)
    row(_("Maior golpe"), get(a, "max_hit"), get(b, "max_hit"), whole)
    row(_("Críticos"), share(a, "crits"), share(b, "crits"), pct, bar=False)
    row(_("Erros"), share(a, "misses"), share(b, "misses"), pct, better="low", bar=False)
    sa, sb = a.get("stats") or {}, b.get("stats") or {}
    if sa or sb:
        head(_("Atributos (média na luta)"))
        for key, name, better in stats.SHOWN:
            va, vb = (sa.get(key) or [None])[0], (sb.get(key) or [None])[0]
            if va is None and vb is None:
                continue
            row(_(name), va, vb, lambda v, k=key: stats.stat_text(k, v), better=better, bar=False)
    # conjuração, recarga e pós-conjuração
    ca = {r["name"]: r for r in a.get("casts") or []}
    cb = {r["name"]: r for r in b.get("casts") or []}
    names = sorted(set(ca) | set(cb), key=lambda n: -max((ca.get(n) or {}).get("n", 0), (cb.get(n) or {}).get("n", 0)))
    timing = []
    for n in names[:SIDE_SKILLS]:
        ra, rb = ca.get(n) or {}, cb.get(n) or {}
        if ra.get("cast") or rb.get("cast"):
            timing.append((_("%s · conjuração") % n, ra.get("cast"), rb.get("cast")))
        if ra.get("cooldown") or rb.get("cooldown"):
            timing.append((_("%s · recarga") % n, ra.get("cooldown"), rb.get("cooldown")))
    pa, pb = a.get("post") or {}, b.get("post") or {}
    if timing or pa or pb or a.get("blocked") is not None or b.get("blocked") is not None:
        head(_("Conjuração e recarga"))
        for name, va, vb in timing:
            row(name, va, vb, _ms, better="low", bar=False)
        if pa or pb:
            row(_("Pós-conjuração"), pa.get("real"), pb.get("real"), _ms, better="low", bar=False)
            row(_("Redução da pós-conjuração"), pa.get("cut"), pb.get("cut"), lambda v: dec("%.0f%%" % (v * 100)),
                bar=False)
        if a.get("blocked") is not None or b.get("blocked") is not None:
            row(_("Tentativas com a skill em recarga"), get(a, "blocked"), get(b, "blocked"), whole, better=None,
                bar=False)
    # skills: o dano de cada uma (as que mais renderam nos dois)
    ka = {k["name"]: k for k in a.get("skills") or []}
    kb = {k["name"]: k for k in b.get("skills") or []}
    names = sorted(set(ka) | set(kb), key=lambda n: -max((ka.get(n) or {}).get("total", 0), (kb.get(n) or {}).get("total", 0)))
    if names:
        head(_("Skills (dano)"))
        for n in names[:SIDE_SKILLS]:
            ra, rb = ka.get(n) or {}, kb.get(n) or {}
            row(n, ra.get("total"), rb.get("total"), whole)
    ba = {x["name"]: x for x in a.get("buffs") or []}
    bb = {x["name"]: x for x in b.get("buffs") or []}
    names = sorted(set(ba) | set(bb), key=lambda n: (-max((ba.get(n) or {}).get("uptime") or 0,
                                                          (bb.get(n) or {}).get("uptime") or 0), n))
    if names:
        head(_("Buffs (tempo ativo)"))
        for n in names[:SIDE_BUFFS]:
            row(n, (ba.get(n) or {}).get("uptime"), (bb.get(n) or {}).get("uptime"), lambda v: dec("%.0f%%" % (v * 100)))
    ia = {x["name"]: x["n"] for x in a.get("items") or []}
    ib = {x["name"]: x["n"] for x in b.get("items") or []}
    names = sorted(set(ia) | set(ib), key=lambda n: -max(ia.get(n, 0), ib.get(n, 0)))
    if names:
        head(_("Itens usados"))
        for n in names[:SIDE_ITEMS]:
            row(n, ia.get(n), ib.get(n), whole, better=None)
    return out


def equip_diff(a, b):
    """Slots cujo item mudou entre os dois testes."""
    if not b:
        return set()
    ea = {e["slot"]: e["item"] for e in a.get("equip") or []}
    eb = {e["slot"]: e["item"] for e in b.get("equip") or []}
    return {s for s in set(ea) | set(eb) if ea.get(s) != eb.get(s)}


def compare(a, b):
    """Linhas de comparação entre dois testes (a = mais novo/escolhido, b = referência)."""
    def pct(x, y):
        return ((x - y) / y) if y else None

    summary = []
    for key, label in (("dps", _("DPS (em combate)")), ("eff_dps", _("DPS do 1º ao último golpe")), ("damage", _("Dano")),
                       ("combat_ms", _("Tempo em combate")), ("hits", _("Acertos")), ("max_hit", _("Maior golpe"))):
        va, vb = a.get(key) or 0, (b or {}).get(key) or 0
        summary.append(dict(name=label, key=key, a=va, b=vb if b else None, diff=pct(va, vb) if b else None))
    skills = {}
    for side, rec in (("a", a), ("b", b)):
        for k in (rec or {}).get("skills", []):
            row = skills.setdefault(k["name"], dict(name=k["name"], a=0, a_share=0, b=0, b_share=0))
            row[side] = k["total"]
            row[side + "_share"] = k["share"]
    for row in skills.values():
        row["diff"] = pct(row["a"], row["b"]) if b else None
    equip = {}
    order = []
    for side, rec in (("a", a), ("b", b)):
        for e in (rec or {}).get("equip", []):
            if e["slot"] not in equip:
                order.append(e["slot"])
            equip.setdefault(e["slot"], dict(slot=e["slot"], a="", b=""))[side] = e["item"]
    equip_rows = [dict(equip[s], changed=bool(b) and equip[s]["a"] != equip[s]["b"]) for s in order]
    buffs = {}
    for side, rec in (("a", a), ("b", b)):
        for x in (rec or {}).get("buffs", []):
            buffs.setdefault(x["name"], dict(name=x["name"], kind=x.get("kind", ""), a=None, b=None))[side] = x["uptime"]
    return dict(summary=summary, skills=sorted(skills.values(), key=lambda r: -(r["a"] or r["b"])),
                equip=equip_rows, buffs=sorted(buffs.values(), key=lambda r: (r["kind"], r["name"])))
