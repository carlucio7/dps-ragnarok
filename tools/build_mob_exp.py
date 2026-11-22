"""Gera data/mob_exp.json: XP de base e de classe de cada monstro (para estimar a XP dos abates).

  {id: [nível, XP base, XP classe]} do db/re/mob_db.yml do rAthena (https://github.com/rathena/rathena),
  mais data/mob_exp_extra.json (monstros que o rAthena ainda não tem, com a XP do Divine Pride).

  As cópias invocadas ("G_...": a escolta de um MVP, como as Quimeras mutantes da Quimera Única em Amicitia) não dão
  XP nem drop. Entram com XP 0 as que o rAthena tem e, com --grf, todas as que o cliente do jogo lista
  (npcidentity.lub do data.grf) e ainda não estão aqui, com o nível do monstro de que são cópia. Sem dado, o monstro
  fica "sem XP conhecida" no programa, e o trecho em que ele morre muitas vezes não mede a XP (xp._kill_band).

uso: python tools/build_mob_exp.py CAMINHO/mob_db.yml [--grf CAMINHO/data.grf]
"""

import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def client_ids(grf_path):
    """{nome interno (JT_...): id} de todos os monstros que o cliente do jogo lista (npcidentity.lub)."""
    sys.path.insert(0, ROOT)
    import lub
    import sprites
    grf = sprites.Grf(grf_path, prefixes=(sprites.LUA,))
    data = grf.read(sprites.LUA + "npcidentity.lub")
    if not data:
        raise SystemExit("npcidentity.lub não encontrado em %s" % grf_path)
    table = lub.run(data, "cp949").get("jobtbl") or {}
    return {k: v for k, v in table.items() if isinstance(k, str) and isinstance(v, int)}


def copy_level(name, ids, levels):
    """Nível de uma cópia invocada pelo monstro de que ela é cópia (JT_G_X -> JT_X; JT_G_X_ -> JT_X_ ou JT_X)."""
    rest = name[len("JT_G_"):]
    for cand in ("JT_" + rest, "JT_" + rest.rstrip("_")):
        lv = levels.get(ids.get(cand))
        if lv:
            return lv
    return None


def main(path, grf_path=None):
    text = open(path, encoding="utf-8", errors="replace").read()
    out, levels, copies = {}, {}, 0
    for block in re.split(r"\n  - Id: ", text)[1:]:
        mid = block.split("\n", 1)[0].strip()
        if not mid.isdigit():
            continue

        def num(key):
            m = re.search(r"\n    %s: (\d+)" % key, block)
            return int(m.group(1)) if m else 0
        aegis = re.search(r"\n    AegisName: (\S+)", block)
        levels[int(mid)] = num("Level") or 1
        if num("BaseExp") or num("JobExp"):
            out[mid] = [num("Level") or 1, num("BaseExp"), num("JobExp")]
        elif aegis and aegis.group(1).startswith("G_"):
            out[mid] = [num("Level") or 1, 0, 0]          # cópia invocada: não dá XP
            copies += 1
    with open(os.path.join(ROOT, "data", "mob_exp_extra.json"), encoding="utf-8") as f:
        extra = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    levels.update({int(k): v[0] for k, v in extra.items()})
    if grf_path:
        ids = client_ids(grf_path)
        for name, mid in sorted(ids.items(), key=lambda kv: kv[1]):
            if name.startswith("JT_G_") and str(mid) not in out and str(mid) not in extra:
                out[str(mid)] = [copy_level(name, ids, levels) or levels.get(mid) or 1, 0, 0]
                copies += 1
    out.update(extra)
    dest = os.path.join(ROOT, "data", "mob_exp.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(out.items(), key=lambda kv: int(kv[0]))), f, separators=(",", ":"))
    print("%d monstros (%d extras, %d cópias invocadas com XP 0) -> %s" % (len(out), len(extra), copies, dest))


if __name__ == "__main__":
    args = sys.argv[1:]
    grf = None
    if "--grf" in args:
        i = args.index("--grf")
        grf = args[i + 1]
        del args[i:i + 2]
    main(args[0], grf)
