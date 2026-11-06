"""Gera data/item_kind.json: categorias de itens que a descrição do jogo não diz (para colorir os drops).

  mvpcard: cartas que caem de MVPs (mob_db: MvpExp ou modo Mvp)
  refine:  materiais de refino, grau e reforma (refine.yml, enchantgrade.yml, item_reform.yml e minérios brutos)
  alch:    ingredientes de Preparar Poção, Farmacologia Avançada, Culinária Avançada e Manipular Poção
           (produce_db.txt; as mesmas receitas do browiki), mais o recipiente de cada uma
  episode: recompensas de quest e materiais especiais dos episódios 17 em diante (lista à mão, abaixo)

Equipamento e carta comum vêm da descrição do próprio jogo ("Tipo: ...", em itemkind.py), que cobre os itens
novos da LATAM.

uso: python tools/build_item_kinds.py PASTA
     (com db/re/item_db_etc.yml, mob_db.yml, refine.yml, enchantgrade.yml, item_reform.yml e produce_db.txt
      de https://github.com/rathena/rathena)
"""

import json
import os
import re
import sys

# (nível do item, skill) de produce_db.txt que entram no verde, como o usuário pediu:
# Preparar Poção (AM_PHARMACY 228), Culinária Avançada (GN_MIX_COOKING 2495), Farmacologia Avançada
# (GN_S_PHARMACY 2497) e Manipular Poção (BO_BIONIC_PHARMACY 5336). A culinária comum (livros) fica de fora.
PRODUCE_SKILLS = {(22, 228), (27, 2495), (29, 2497), (32, 5336)}
# recipientes gastos a cada uso que o produce_db não lista: Vasilha de Mistura (Preparar Poção)
EXTRA_ALCH = (7134,)
# episódios 17 em diante: recompensas das quests diárias, drops especiais e materiais das armas invernais.
# Fontes: irowiki (Cor Memorial, 17.2 Daily Quest, Episode 18 Daily Quest), wiki.muhro.eu (19 Isgard) e
# browiki (Equipamentos Invernais); nomes conferidos no iteminfo do jogo.
EPISODE_ITEMS = {
    # 17.1 Illusion: Núcleo COR, Chip Misterioso, Arma Danificada
    25723: "17.1", 25669: "17.1", 25668: "17.1",
    # 17.2 Legado do Sábio (mansão Varmunt): Vale Varmida
    1000103: "17.2",
    # 18 Direção da Prece (Cânion de Oz, Lobo Cinzento): Fragmento de Ametista
    1000405: "18",
    # 19 Issgard: Pétala de Flor Invernal, Minério Mágico da Flor de Neve, os três Globos de Flor Invernal,
    # Corpo Luminoso Misterioso (recompensas da instância) e os materiais das Armas Vis Invernais:
    # Pedras da Fonte Mágica, Cristais Mágicos, Magia Corrompida e os Extratos
    1000608: "19", 1000811: "19", 1000812: "19", 1000813: "19", 1000814: "19", 1000833: "19",
    1001029: "19", 1001030: "19", 1001031: "19", 1001032: "19", 1001033: "19",
    1001034: "19", 1001035: "19", 1001036: "19", 1001037: "19",
}
# minérios brutos, ajudas de refino e os minérios de equipamento sombrio, que não aparecem no refine.yml
EXTRA_REFINE = ("Oridecon_Stone", "Elunium_Stone", "Blacksmith_Blessing", "Bradium_Stone", "Carnium_Stone",
                "Etel_Dust", "Etel_Stone", "Shadowdecon_Ore", "Shadowdecon", "Zelunium_Ore", "Zelunium")


def items(path):
    """(AegisName -> id, ids de cartas) do item_db_etc.yml."""
    by_name, cards = {}, set()
    cur = None
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"\s*- Id: (\d+)", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.match(r"\s+AegisName: (\S+)", line)
        if m and cur is not None:
            by_name[m.group(1)] = cur
            continue
        if cur is not None and re.match(r"\s+Type: Card\s*$", line):
            cards.add(cur)
    return by_name, cards


def mvp_drops(path):
    """AegisNames dos itens que caem de MVPs."""
    out = set()
    mvp, drops = False, []

    def flush():
        if mvp:
            out.update(drops)
    for line in open(path, encoding="utf-8", errors="replace"):
        if re.match(r"  - Id: \d+", line):
            flush()
            mvp, drops = False, []
        elif re.match(r"\s+MvpExp: \d+", line) or re.match(r"\s+Mvp: true", line):
            mvp = True
        else:
            m = re.match(r"\s+- Item: (\S+)", line)
            if m:
                drops.append(m.group(1))
    flush()
    return out


def main(folder):
    j = lambda name: os.path.join(folder, name)
    by_name, cards = items(j("item_db_etc.yml"))
    mvpcard = sorted(by_name[n] for n in mvp_drops(j("mob_db.yml")) if n in by_name and by_name[n] in cards)
    refine = set()
    for name in re.findall(r"Material: (\S+)", open(j("refine.yml"), encoding="utf-8").read()):
        refine.add(name)
    refine.update(re.findall(r"Item: (\S+)", open(j("enchantgrade.yml"), encoding="utf-8").read()))
    refine.update(re.findall(r"(?m)^  - Item: (\S+)", open(j("item_reform.yml"), encoding="utf-8").read()))
    refine.update(EXTRA_REFINE)
    refine = sorted(by_name[n] for n in refine if n in by_name and not n.startswith("IDTest"))
    alch = set()
    for line in open(j("produce_db.txt"), encoding="utf-8", errors="replace"):
        if not line[:1].isdigit():
            continue
        p = [int(x) for x in line.split("//")[0].strip().split(",") if x.strip()]
        if (p[2], p[3]) not in PRODUCE_SKILLS:
            continue
        mats = p[5:]
        for item, amount in zip(mats[0::2], mats[1::2]):
            if amount > 0:              # quantidade 0 = livro de receitas (só precisa ter)
                alch.add(item)
    alch.update(EXTRA_ALCH)
    alch = sorted(alch - set(refine) - cards - set(EPISODE_ITEMS))
    out = dict(mvpcard=mvpcard, refine=refine, alch=alch, episode=sorted(EPISODE_ITEMS))
    dest = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "item_kind.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(dest, {k: len(v) for k, v in out.items()})


if __name__ == "__main__":
    main(sys.argv[1])
