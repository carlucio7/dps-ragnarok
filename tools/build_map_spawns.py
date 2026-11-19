# -*- coding: utf-8 -*-
"""Gera data/map_spawns.json: quantos monstros de cada tipo nascem em cada mapa. Serve ao simulador de XP ("e se eu
caçasse no mapa X?"): a XP média por abate de um mapa sai da mistura dos monstros dele.

Fonte principal: a lista do /navi do próprio cliente do LATAM (data.grf: navi_mob_br.lub e navi_map_br.lub), que tem
os mapas novos (Torre do Relógio, Niflheim, Amicitia, Biosfera, Jormungandr...) e as quantidades do servidor oficial.
Os nomes: o do /navi; as instâncias e os mapas sem nome nele, o do mapnametable.txt. E o nível de cada monstro
no /navi (o do LATAM): onde ele não bate com o da nossa tabela de XP, o LATAM tem outra versão do monstro.
Ficam só os monstros comuns (tipo 300; os chefes, 301, ficam de fora). Os mapas que o /navi não tem vêm dos scripts de
nascimento do rAthena (npc/re/mobs, sem os boss_monster, sem instâncias com "@" e sem linhas comentadas), se a pasta
for dada. Também guarda o nome de cada mapa no /navi (para achar o mapa digitando o nome).

uso: python tools/build_map_spawns.py --navi C:\\Gravity\\Ragnarok\\data.grf [PASTA_DO_RATHENA_NPC]
     (a pasta "npc" do rAthena, com re/mobs dentro)"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
OUT = os.path.join(ROOT, "data", "map_spawns.json")
LINE = re.compile(r"^([A-Za-z0-9_@\-]+),\d+,\d+(?:,\d+,\d+)?\t(monster|boss_monster)\t[^\t]*\t(\d+),(\d+)")
NAVI = "data\\luafiles514\\lua files\\navigation\\"
NAVI_MOB, NAVI_MAP = NAVI + "navi_mob_br.lub", NAVI + "navi_map_br.lub"
NAVI_COMMON = 300             # tipo do monstro no /navi: 300 comum, 301 chefe
MAPNAMES = "data\\mapnametable.txt"


def read_rathena(folder):
    """{mapa: {monstro: quantos}} de todos os .txt de re/mobs."""
    out = {}
    base = os.path.join(folder, "re", "mobs")
    for root, _dirs, files in os.walk(base):
        for name in sorted(files):
            if not name.endswith(".txt"):
                continue
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip("\r\n")
                    if line.lstrip().startswith("//"):
                        continue
                    m = LINE.match(line)
                    if not m:
                        continue
                    mapname, kind, mob, amount = m.group(1).lower(), m.group(2), int(m.group(3)), int(m.group(4))
                    if kind != "monster" or "@" in mapname or amount <= 0:
                        continue
                    spot = out.setdefault(mapname, {})
                    spot[mob] = spot.get(mob, 0) + amount
    return out


def read_navi(grf):
    """({mapa: {monstro: quantos}}, {mapa: nome}) do /navi do cliente. Cada linha do Navi_Mob: {mapa, id da linha,
    tipo, quantos << 16 | monstro, nome, sprite, nível, ...}; do Navi_Map: {mapa, nome, ...}."""
    sys.path.insert(0, ROOT)
    import clientdata
    import lub
    files = clientdata.grf_files(grf, [NAVI_MOB, NAVI_MAP])
    mobs = lub.run(files[NAVI_MOB.lower()])["Navi_Mob"]
    maps = lub.run(files[NAVI_MAP.lower()])["Navi_Map"]
    out, levels = {}, {}
    for row in mobs.values():
        mapname, kind, packed = str(row.get(1) or "").lower(), row.get(3), int(row.get(4) or 0)
        n, mob = packed >> 16, packed & 0xFFFF
        if mob and isinstance(row.get(7), int) and row.get(7) > 0:
            levels[mob] = row.get(7)                 # o nível do monstro no LATAM (o que o /navi mostra)
        if kind != NAVI_COMMON or not mapname or mapname == "null" or "@" in mapname or n <= 0 or not mob:
            continue
        spot = out.setdefault(mapname, {})
        spot[mob] = spot.get(mob, 0) + n
    names = {}
    for row in maps.values():
        mapname, name = str(row.get(1) or "").lower(), str(row.get(2) or "").strip()
        if mapname in out and name:
            names[mapname] = name
    # as instâncias ("1@ch_t" no cliente, "0q83@ch_t" na gravação) e os mapas sem nome no /navi: do mapnametable.txt,
    # pelo nome sem o prefixo da instância
    table = clientdata.grf_files(grf, [MAPNAMES]).get(MAPNAMES.lower(), b"").decode("cp1252", "replace")
    for line in table.splitlines():
        parts = line.split("#")
        if len(parts) < 2 or line.startswith("//"):
            continue
        mapname = parts[0].strip().lower().replace(".rsw", "")
        name = parts[1].strip()
        key = mapname.split("@")[-1]
        if name and key and key not in names and ("@" in mapname or key in out):
            names[key] = name
    return out, names, levels


def table(spawns):
    return {m: sorted(([mob, n] for mob, n in mobs.items()), key=lambda x: (-x[1], x[0]))
            for m, mobs in sorted(spawns.items())}


def main():
    args = sys.argv[1:]
    if "--navi" not in args or args.index("--navi") + 1 >= len(args):
        print(__doc__)
        return 1
    i = args.index("--navi")
    grf = args[i + 1]
    rest = args[:i] + args[i + 2:]
    navi, names, levels = read_navi(grf)
    rath = read_rathena(rest[0]) if rest else {}
    only_rath = {m: v for m, v in rath.items() if m not in navi}
    data = {"_fonte": "maps: a lista do /navi do cliente do Ragnarok LATAM (navi_mob_br.lub: monstros comuns e "
                      "quantos nascem de cada um em cada mapa; names: navi_map_br.lub). rathena: os mapas que o /navi "
                      "não tem, dos scripts do rAthena (npc/re/mobs, sem chefes nem instâncias). Gerado por "
                      "tools/build_map_spawns.py.",
            "maps": table(navi), "rathena": table(only_rath), "names": dict(sorted(names.items())),
            "levels": {str(k): v for k, v in sorted(levels.items())}}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print("%d mapas do /navi (%d com nome) + %d só do rAthena -> %s" % (len(navi), len(names), len(only_rath), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
