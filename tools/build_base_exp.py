"""Gera data/base_exp.json: a XP de base de cada nível, por grupo de classes, a partir do rAthena.

  {"groups": [{"jobs": [id da classe, ...], "max": nível máximo, "exp": {nível: XP para o seguinte}}]}

O jogo só manda a XP do nível no começo da gravação; depois de subir de nível o programa precisa da tabela para
continuar mostrando o % e o tempo até o próximo nível. Os valores do ROLatam conferem com os do rAthena nas
gravações vistas (classe 2 no 76, 3ª classe 134–190, 4ª classe 200–201), menos em dois trechos que o ROLatam ainda
não reduziu: a 4ª classe do 220 em diante (conta à parte em xp.table_need) e as classes 1 e 2 do 79 ao 98
(LATAM_79_98 abaixo, gravado por cima do rAthena).

uso: python tools/build_base_exp.py job_exp.yml
     (db/re/job_exp.yml de https://github.com/rathena/rathena; as classes vêm de data/rathena.json)
"""

import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# A XP para ir do nível 79 ao 99 nas classes 1 e 2 (normais e transcendentais) de antes da redução dos níveis 80–99
# (kRO; iRO Wiki: 8/7/2025; rAthena desde o #8103, jan/2024). O ROLatam continua nesta: um Ferreiro no 96 recebeu
# 2.098.423 do jogo (o rAthena diz 1.018.605), e o ritmo de XP do mesmo replay no 97 só fecha com 2.465.723.
# Valores do ragnarok-db.com (iguais em todas as classes 1 e 2 de cada tipo; do 1 ao 78 iguais ao rAthena).
# Chave: uma classe do grupo do rAthena que recebe a tabela.
LATAM_79_98 = {
    "Blacksmith": {79: 181403, 80: 204449, 81: 235195, 82: 273571, 83: 311715, 84: 372936, 85: 426040, 86: 463377,
                   87: 523585, 88: 575751, 89: 688829, 90: 763069, 91: 912936, 92: 1137747, 93: 1361200,
                   94: 1583303, 95: 1804061, 96: 2098423, 97: 2465723, 98: 2979788},
    "Whitesmith": {79: 272105, 80: 327119, 81: 376312, 82: 437714, 83: 498744, 84: 596697, 85: 681665, 86: 741403,
                   87: 837736, 88: 921202, 89: 1102126, 90: 1297218, 91: 1551992, 92: 1934170, 93: 2314041,
                   94: 2691615, 95: 3066904, 96: 3567320, 97: 4191729, 98: 5065641},
}


# classes que o data/rathena.json não traz (ele só lista as que têm árvore de habilidades própria)
EXTRA_IDS = {"super_novice": [23]}


def latam(groups_):
    """Grava a LATAM_79_98 por cima dos grupos do rAthena (só nos grupos que vão até o nível 99)."""
    done = set()
    for g in groups_:
        names = {n.lower() for n in g["jobs"]}
        for job, levels in LATAM_79_98.items():
            if job.lower() in names and (g["max"] or 0) <= 99:
                g["exp"].update(levels)
                done.add(job)
    missing = set(LATAM_79_98) - done
    if missing:
        sys.exit("grupo não achado para %s" % sorted(missing))
    return groups_


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
    by_name = {name: list(ids) for name, ids in EXTRA_IDS.items()}
    for jid, info in jobs.items():
        by_name.setdefault(info["name"].lower(), []).append(int(jid))
    out, missing = [], set()
    for g in latam(groups(sys.argv[1])):
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
