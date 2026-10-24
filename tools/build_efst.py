"""Gera data/efst.json a partir do rAthena (status.hpp, status.yml, skill_db.yml).

Para cada id de status (EFST) guarda o nome interno e as skills que aplicam aquele
status. Serve para dar nome aos status que o cliente não nomeia e para ligar
buffs/debuffs às skills (ex.: Pólen do simulador = AG_ALL_BLOOM = EFST_CLIMAX_BLOOM).

uso: python tools/build_efst.py PASTA_COM_OS_3_ARQUIVOS_DO_RATHENA
     (https://github.com/rathena/rathena: src/map/status.hpp, db/re/status.yml, db/re/skill_db.yml)
"""

import json
import os
import re
import sys

src = sys.argv[1]
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "efst.json")

enum = {}
txt = open(os.path.join(src, "status.hpp"), encoding="utf-8", errors="replace").read()
body = txt[txt.index("enum efst_type"):]
body = body[body.index("{") + 1:body.index("};")]
n = -1
for line in body.split("\n"):
    line = line.split("//")[0].strip().rstrip(",")
    m = re.match(r"^(EFST_\w+)\s*(?:=\s*(-?\d+))?$", line)
    if m:
        n = int(m.group(2)) if m.group(2) is not None else n + 1
        enum[m.group(1)] = n

icon = {}
cur = None
for line in open(os.path.join(src, "status.yml"), encoding="utf-8", errors="replace"):
    m = re.match(r"^\s*-\s*Status:\s*(\w+)", line)
    if m:
        cur = m.group(1).lower()
    m = re.match(r"^\s*Icon:\s*(EFST_\w+)", line)
    if m and cur:
        icon[cur] = m.group(1)

by_efst = {}
cur = None
for line in open(os.path.join(src, "skill_db.yml"), encoding="utf-8", errors="replace"):
    m = re.match(r"^  - Id:\s*(\d+)", line)
    if m:
        cur = int(m.group(1))
        continue
    m = re.match(r"^    Status:\s*(\w+)", line)
    if m and cur is not None:
        efst = enum.get(icon.get(m.group(1).lower(), ""))
        if efst is not None:
            by_efst.setdefault(efst, []).append(cur)

data = {str(v): {"c": k[5:], **({"s": by_efst[v]} if v in by_efst else {})} for k, v in enum.items() if v >= 0}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(data, f, separators=(",", ":"))
print("ok", len(data), "status,", sum(1 for d in data.values() if "s" in d), "com skill ->", out_path)
