"""Gera data/mob_size.json (id do monstro -> "S" pequeno, "M" médio, "L" grande) a partir do mob_db do rAthena,
mais os chefes que o rAthena não tem (tamanho do Divine Pride). Usado pelos avisos de troca de forma e pela
Oposição Solar, Lunar e Estelar (Solar = pequeno, Lunar = médio, Estelar = grande).

uso: python tools/build_mob_size.py db/re/mob_db.yml   (de https://github.com/rathena/rathena)
"""

import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SIZES = {"Small": "S", "Medium": "M", "Large": "L"}
# chefes da LATAM que o rAthena não tem ou trata diferente (conferidos no Divine Pride)
# Aquila em sobrecarga (sprite 21588) continua grande no servidor: uma Oposição Estelar lançada no meio da sobrecarga
# foi aceita para a classe 21531 (0x020e com resultado 10), e o dano dos golpes não muda dentro e fora dela na
# Executiva. O Divine Pride diz pequeno para a 21588, mas é só a aparência.
EXTRA = {20994: "L",              # Betelgeuse (Torre da Constelação)
         21531: "L", 21588: "L",  # Aquila (Destruição da Aeronave) e a forma de sobrecarga
         21533: "L",              # Juncea de Simulação
         20573: "L",              # Fantasma de Amdarais (Glast Heim Sombria, desafio)
         20572: "M",              # Fantasma de Himmelmez (a mesma instância, chance de 5% × o nível no lugar dele)
         # Edda do Biolaboratório (MD_ED_*): a Espadachim Anônima (MVP), os monstros das salas e o objeto escondido
         20536: "M", 20537: "M", 20538: "M", 20539: "M", 20540: "M", 20541: "M", 20542: "M", 20562: "M"}
EXTRA.update({j: "M" for j in range(20856, 20873)})   # arena noturna de Geffen (MD_N_ARENA_*, Fei, Alphonse, Fenrir)


def parse(path):
    out, cur = {}, None
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.rstrip("\r\n")
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^\s*- Id:\s*(\d+)", line)
        if m:
            cur = int(m.group(1))
            out[cur] = "S"                       # o padrão do rAthena é pequeno
            continue
        m = re.match(r"^\s+Size:\s*(\w+)", line)
        if m and cur is not None and m.group(1) in SIZES:
            out[cur] = SIZES[m.group(1)]
    return out


def main():
    sizes = parse(sys.argv[1])
    sizes.update(EXTRA)
    with open(os.path.join(ROOT, "data", "mob_size.json"), "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in sorted(sizes.items())}, f, separators=(",", ":"))
    print("%d monstros (%d pequenos, %d médios, %d grandes)" % (
        len(sizes), sum(v == "S" for v in sizes.values()), sum(v == "M" for v in sizes.values()),
        sum(v == "L" for v in sizes.values())))


if __name__ == "__main__":
    main()
