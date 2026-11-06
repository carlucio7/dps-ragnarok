"""Gera data/mob_exp.json: XP de base e de classe de cada monstro (para estimar a XP dos abates).

  {id: [nível, XP base, XP classe]} do db/re/mob_db.yml do rAthena (https://github.com/rathena/rathena),
  mais data/mob_exp_extra.json (monstros que o rAthena ainda não tem, com a XP do Divine Pride).

uso: python tools/build_mob_exp.py CAMINHO/mob_db.yml
"""

import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def main(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    out = {}
    for block in re.split(r"\n  - Id: ", text)[1:]:
        mid = block.split("\n", 1)[0].strip()
        if not mid.isdigit():
            continue

        def num(key):
            m = re.search(r"\n    %s: (\d+)" % key, block)
            return int(m.group(1)) if m else 0
        if num("BaseExp") or num("JobExp"):
            out[mid] = [num("Level") or 1, num("BaseExp"), num("JobExp")]
    with open(os.path.join(ROOT, "data", "mob_exp_extra.json"), encoding="utf-8") as f:
        extra = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    out.update(extra)
    dest = os.path.join(ROOT, "data", "mob_exp.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(out.items(), key=lambda kv: int(kv[0]))), f, separators=(",", ":"))
    print("%d monstros (%d extras) -> %s" % (len(out), len(extra), dest))


if __name__ == "__main__":
    main(sys.argv[1])
