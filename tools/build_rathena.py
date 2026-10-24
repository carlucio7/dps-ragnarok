"""Gera data/rathena.json a partir do rAthena (para o Dedo Duro).

  jobs:   id da classe -> nome e skills que ela pode ter (com herança: a 4ª classe tem as da 3ª...)
  skills: id -> nome interno, descrição em inglês, tipo (W físico, M mágico, X outro), elemento,
          recarga (ms) e custo de AP
  mobs:   id -> elemento, nível do elemento, classe (Normal/Boss...) e se é MVP
  attr:   tabela de vantagem elemental: nível -> elemento do ataque -> elemento do alvo -> %

uso: python tools/build_rathena.py PASTA
     (com src/common/mmo.hpp, db/re/skill_tree.yml, db/re/skill_db.yml, db/re/mob_db.yml,
      db/re/attr_fix.yml de https://github.com/rathena/rathena)
"""

import json
import os
import re
import sys


def _tokens(path):
    out = []
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if " #" in line and '"' not in line:
            line = line[:line.index(" #")]
        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()
        dash = text == "-" or text.startswith("- ")
        if dash:
            text = text[2:] if text != "-" else ""
        out.append([indent, dash, text])
    return out


def _parse(tok, pos, indent):
    if pos < len(tok) and tok[pos][1] and tok[pos][0] == indent:
        items = []
        while pos < len(tok) and tok[pos][0] == indent and tok[pos][1]:
            tok[pos] = [indent + 2, False, tok[pos][2]]     # o item vira um mapa na coluna seguinte
            item, pos = _parse_map(tok, pos, indent + 2)
            items.append(item)
        return items, pos
    return _parse_map(tok, pos, indent)


def _parse_map(tok, pos, indent):
    d = {}
    while pos < len(tok):
        ind, dash, text = tok[pos]
        if ind < indent or (ind == indent and dash):
            break
        if ind > indent:
            pos += 1
            continue
        key, _sep, val = text.partition(":")
        key, val = key.strip().strip('"'), val.strip()
        pos += 1
        if val == "":
            if pos < len(tok) and (tok[pos][0] > ind or (tok[pos][1] and tok[pos][0] >= ind)):
                d[key], pos = _parse(tok, pos, tok[pos][0])
            else:
                d[key] = None
        else:
            d[key] = val.strip('"')
    return d, pos


def parse_yaml(path):
    """Leitor mínimo para o YAML do rAthena: mapas, listas de mapas e valores simples."""
    return _parse(_tokens(path), 0, 0)[0]


def body(path):
    b = parse_yaml(path).get("Body") or []
    return b if isinstance(b, list) else []


def as_max(v, field):
    """Valor simples ou lista por nível (pega o maior)."""
    if isinstance(v, list):
        nums = [int(x.get(field, 0)) for x in v if isinstance(x, dict) and str(x.get(field, "0")).lstrip("-").isdigit()]
        return max(nums) if nums else 0
    if isinstance(v, str) and v.lstrip("-").isdigit():
        return int(v)
    return 0


def main():
    src = sys.argv[1]
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "rathena.json")

    # classes: JOB_X = número
    enum = {}
    txt = open(os.path.join(src, "mmo.hpp"), encoding="utf-8", errors="replace").read()
    block = txt[txt.index("enum e_job"):]
    block = block[block.index("{") + 1:block.index("};")]
    n = -1
    for line in block.split("\n"):
        line = line.split("//")[0].strip().rstrip(",")
        m = re.match(r"^(JOB_\w+)\s*(?:=\s*(-?\d+))?$", line)
        if m:
            n = int(m.group(2)) if m.group(2) is not None else n + 1
            enum[m.group(1)] = n

    skill_ids = {}
    skills = {}
    for e in body(os.path.join(src, "skill_db.yml")):
        if not isinstance(e, dict) or not str(e.get("Id", "")).isdigit():
            continue
        sid = int(e["Id"])
        skill_ids[e.get("Name")] = sid
        req = e.get("Requires") if isinstance(e.get("Requires"), dict) else {}
        skills[sid] = {"n": e.get("Name"), "d": e.get("Description") or "", "t": {"Weapon": "W", "Magic": "M"}.get(e.get("Type"), "X"),
                       "e": e.get("Element") if isinstance(e.get("Element"), str) else "",
                       "cd": as_max(e.get("Cooldown"), "Time"), "ap": as_max(req.get("ApCost"), "Amount")}

    trees = {}
    inherit = {}
    for e in body(os.path.join(src, "skill_tree.yml")):
        if not isinstance(e, dict) or "Job" not in e:
            continue
        job = e["Job"]
        tree = e.get("Tree") or []
        trees[job] = {skill_ids[t["Name"]] for t in tree if isinstance(t, dict) and t.get("Name") in skill_ids}
        inh = e.get("Inherit") or {}
        inherit[job] = [k for k, v in inh.items() if str(v).lower() == "true"] if isinstance(inh, dict) else []

    def all_skills(job, seen=()):
        out = set(trees.get(job, ()))
        for parent in inherit.get(job, []):
            if parent not in seen:
                out |= all_skills(parent, seen + (job,))
        return out

    jobs = {}
    for job in trees:
        jid = enum.get("JOB_" + job.upper())
        if jid is not None:
            jobs[jid] = {"name": job, "skills": sorted(all_skills(job))}

    mobs = {}
    for e in body(os.path.join(src, "mob_db.yml")):
        if not isinstance(e, dict) or not str(e.get("Id", "")).isdigit():
            continue
        modes = e.get("Modes") if isinstance(e.get("Modes"), dict) else {}
        mobs[int(e["Id"])] = {"e": e.get("Element", "Neutral"), "l": int(e.get("ElementLevel", 1) or 1),
                              "c": e.get("Class", "Normal"), "mvp": str(modes.get("Mvp", "")).lower() == "true"}

    attr = {}
    for e in body(os.path.join(src, "attr_fix.yml")):
        if isinstance(e, dict) and "Level" in e:
            lvl = e["Level"]
            attr[lvl] = {a: {d: int(v) for d, v in defs.items() if str(v).lstrip("-").isdigit()}
                         for a, defs in e.items() if isinstance(defs, dict)}

    data = {"jobs": jobs, "skills": skills, "mobs": mobs, "attr": attr}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    print("ok: %d classes, %d skills, %d monstros, %d níveis de elemento -> %s" % (
        len(jobs), len(skills), len(mobs), len(attr), out_path))


if __name__ == "__main__":
    main()
