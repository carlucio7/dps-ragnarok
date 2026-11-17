"""Gera data/base_exp.json: a XP de base de cada nível, por grupo de classes, a partir do rAthena.

  {"groups": [{"jobs": [id da classe, ...], "max": nível máximo, "exp": {nível: XP para o seguinte}}]}

O jogo só manda a XP do nível no começo da gravação; depois de subir de nível o programa precisa da tabela para
continuar mostrando o % e o tempo até o próximo nível. Os valores do ROLatam conferem com os do rAthena nas
gravações vistas (3ª classe 163–180, 4ª classe 224–248).

uso: python tools/build_base_exp.py job_exp.yml
     (db/re/job_exp.yml de https://github.com/rathena/rathena; as classes vêm de data/rathena.json)
"""

import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def groups(path):
    """[(nomes das classes, nível máximo, {nível: XP})] dos grupos que têm BaseExp."""
    out, cur, where = [], None, None
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        s = line.strip()
        if s == "- Jobs:":
            cur = dict(jobs=[], max=None, exp={})
            out.append(cur)
            where = "jobs"
        elif cur is None:
            continue
        elif s.startswith("MaxBaseLevel:"):
            cur["max"] = int(s.split(":")[1])
            where = None
        elif s == "BaseExp:":
            where = "base"
        elif s in ("JobExp:", "MaxJobLevel:") or s.startswith(("MaxJobLevel", "BaseExp", "JobExp")):
            where = None if s != "BaseExp:" else "base"
        elif where == "jobs" and s.endswith(": true"):
            cur["jobs"].append(s[:-len(": true")])
        elif where == "base":
            m = re.match(r"-?\s*Level:\s*(\d+)", s)
            if m:
                cur["_lv"] = int(m.group(1))
            m = re.match(r"Exp:\s*(\d+)", s)
            if m and "_lv" in cur:
                cur["exp"][cur.pop("_lv")] = int(m.group(1))
    return [g for g in out if g["exp"]]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    jobs = json.load(open(os.path.join(ROOT, "data", "rathena.json"), encoding="utf-8"))["jobs"]
    by_name = {}
    for jid, info in jobs.items():
        by_name.setdefault(info["name"].lower(), []).append(int(jid))
    out, missing = [], set()
    for g in groups(sys.argv[1]):
        ids = sorted({i for n in g["jobs"] for i in by_name.get(n.lower(), [])})
        missing |= {n for n in g["jobs"] if n.lower() not in by_name}
        if ids:
            out.append(dict(jobs=ids, max=g["max"] or max(g["exp"]) + 1,
                            exp={str(k): v for k, v in sorted(g["exp"].items())}))
    dest = os.path.join(ROOT, "data", "base_exp.json")
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(groups=out), f, separators=(",", ":"))
    print("%d grupos, %d classes -> %s (%d bytes); sem id: %s" % (
        len(out), sum(len(g["jobs"]) for g in out), dest, os.path.getsize(dest), sorted(missing)[:12]))


if __name__ == "__main__":
    main()
