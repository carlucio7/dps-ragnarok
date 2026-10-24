"""Testes de build guardados no PC (histórico local, nada é enviado para lugar nenhum).

Cada teste guarda: personagem, alvo, tempo em combate, dano e DPS, as skills, os
buffs (com % do tempo ativo) e o equipamento vestido no começo da luta.
"""

import json
import os
import time

import analysis as an
import meter
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
    return dict(
        id="%d-%s" % (int(time.time() * 1000), os.urandom(2).hex()),
        key="%s|%d" % (os.path.basename(rf.path), start),
        saved_at=time.time(), replay=os.path.basename(rf.path), recorded_at=list(s.recorded_at),
        char=s.player, job=meter.job_name(s.job), level=s.base_level, map=c.map or s.map,
        target=c.target_name(target) if target is not None else "", dummy=bool(target and is_dummy(c, target)),
        start=start, combat_ms=dur_ms, damage=sm["dealt"], dps=sm["dps"], eff_dps=sm["effective_dps"],
        hits=sm["hits"], max_hit=sm["best"]["dmg"] if sm["best"] else 0,
        skills=[dict(name=k["name"], total=k["total"], hits=k["hits"], share=k["share"])
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
