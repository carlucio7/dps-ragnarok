"""Gera data/quest_exp.json: a XP de base (sem bônus) que cada missão dá ao ser entregue, para a previsão de nível.

  {"exp": {id da missão: XP}, "zero": [ids das missões de espera, que não dão XP]}

O replay mostra a entrega (a missão sai da lista), mas não quanto ela rendeu. As fontes, da mais forte para a
mais fraca:
  1. o que foi medido no LATAM com a XP exata (LATAM_MEASURED abaixo);
  2. o RewardEXP do próprio jogo (System\\OngoingQuestInfoList_True.lub; "Lv110 5%" fica de fora);
  3. os scripts de NPC do rAthena (npc/): um "getexp N,M" com números fixos no mesmo bloco do "erasequest Q" ou
     "completequest Q" (bloco = as linhas entre case, rótulos e fim); missão com valores diferentes em lugares
     diferentes (depende do nível ou de uma escolha) fica de fora;
  4. a missão do LATAM igual a outra (mesmo título, descrição e resumo) leva a XP dela: o servidor do LATAM entrega a
     caçada da Agente Lauren pela 8663, o rAthena pela 8665, e as duas são a mesma missão no jogo.
Missões de espera (título "[Espera...", "Em espera..." ou CoolTimeQuest) dão 0: a entrega delas é só o fim da espera.
O bônus de missão é outra conta (xp.quest_mult); a recompensa aprendida em cada PC corrige o que a tabela e a regra
erram.

uso: python tools/build_quest_exp.py pasta_npc_do_rathena pasta_do_jogo [--relatorios recompensas.json]
     (npc/ de https://github.com/rathena/rathena; o jogo instalado, com a pasta System; --relatorios: o arquivo do
     tools/ler_relatorios.py --missoes-json, com o que os jogadores mediram no LATAM, que vale mais que o RewardEXP
     e o rAthena e menos que LATAM_MEASURED)
"""

import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import lub  # noqa: E402

# medido com a XP exata (capturas de 2026-11-11, nível 247, manual 100, Kafra, Njord e Milagre): o Jantar do Diabo
# fecha com o valor oficial do iRO Wiki × 8 (2,5 × 1,6 × Milagre); o Mímico pagou o oficial × 4 (sem o Milagre?)
LATAM_MEASURED = {5964: 698346800, 5970: 1745867}

GETEXP = re.compile(r"\bgetexp2?\s*\(?\s*(\d+)\s*,\s*(\d+)\s*\)?\s*;")
DONE = re.compile(r"\b(?:erasequest|completequest)\s*\(?\s*(\d+)\s*\)?\s*;")
CHANGE = re.compile(r"\bchangequest\s*\(?\s*(\d+)\s*,\s*(\d+)\s*\)?\s*;")
SET = re.compile(r"\bsetquest\s*\(?\s*(\d+)\s*\)?\s*;")
BREAK = re.compile(r"^\s*(case\s+[^:]+:|default\s*:|[A-Za-z_][A-Za-z0-9_]*:\s*$|\}|end\s*;|close\s*;|"
                   r"OnInit|function\b|-\s+script|\w+,\d+,\d+,\d+\s+script)")
WAIT = ("[espera", "em espera")


def rathena_rewards(npc):
    """{missão: XP de base} dos scripts do rAthena (só as que têm um valor fixo e único)."""
    found = {}
    for dirpath, _dirs, names in os.walk(npc):
        for name in sorted(names):
            if not name.endswith(".txt"):
                continue
            lines = [ln.split("//", 1)[0] for ln in open(os.path.join(dirpath, name), encoding="utf-8",
                                                         errors="replace")]
            blocks, cur = [], []
            for ln in lines:
                if BREAK.search(ln) and cur:
                    blocks.append(cur)
                    cur = []
                cur.append(ln)
            if cur:
                blocks.append(cur)
            for blk in blocks:
                text = "\n".join(blk)
                exps = GETEXP.findall(text)
                if not exps:
                    continue
                done = set(DONE.findall(text)) | {a for a, _b in CHANGE.findall(text)}
                done -= set(SET.findall(text))          # a missão de espera posta de novo no mesmo bloco
                if len(done) != 1 or len(set(exps)) != 1:
                    continue
                found.setdefault(int(done.pop()), set()).add(int(exps[0][0]))
    return {q: vals.pop() for q, vals in found.items() if len(vals) == 1 and min(vals) > 0}


def reward_exp(value):
    """RewardEXP do jogo como número ("1.120.000", "300000", 100000), ou None ("Lv110 5%")."""
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value).strip().replace(".", "").replace(",", "")
    return int(text) if text.isdigit() and int(text) > 0 else None


def reports_exp(path):
    """{missão: XP sem bônus} do arquivo do tools/ler_relatorios.py --missoes-json."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    out = {}
    for k, v in (d.get("exp") if isinstance(d, dict) and isinstance(d.get("exp"), dict) else {}).items():
        if str(k).isdigit() and isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            out[int(k)] = int(v)
    return out


def main():
    args = list(sys.argv[1:])
    reports = {}
    if "--relatorios" in args:
        i = args.index("--relatorios")
        if i + 1 >= len(args):
            sys.exit(__doc__)
        reports = reports_exp(args[i + 1])
        del args[i:i + 2]
    if len(args) < 2:
        sys.exit(__doc__)
    npc, game = args[0], args[1]
    tables = []
    for rel in ("System\\OngoingQuestInfoList_True.lub", "System\\english\\OngoingQuestInfoList_True.lub"):
        with open(os.path.join(game, rel), "rb") as f:
            tables.append({q: i for q, i in (lub.run(f.read()).get("QuestInfoList") or {}).items()
                           if isinstance(q, int) and isinstance(i, dict)})
    pt, en = tables
    exp = {q: v for q, v in rathena_rewards(npc).items() if q in pt}
    from_rathena = len(exp)
    for q, info in pt.items():
        v = reward_exp(info.get("RewardEXP")) if info.get("RewardEXP") is not None else None
        if v:
            exp[q] = v
    from_reports = {q: v for q, v in reports.items() if q in pt}
    exp.update(from_reports)
    exp.update({q: v for q, v in LATAM_MEASURED.items() if q in pt})
    # missões iguais (mesmo título, descrição e resumo) levam a XP uma da outra, quando todas as conhecidas concordam
    twins = {}
    for q, info in pt.items():
        twins.setdefault(repr((info.get("Title"), info.get("Description"), info.get("Summary"))), []).append(q)
    copied = 0
    for group in twins.values():
        vals = {exp[q] for q in group if q in exp}
        if len(group) > 1 and len(vals) == 1:
            v = vals.pop()
            for q in group:
                if q not in exp:
                    exp[q] = v
                    copied += 1
    zero = sorted(q for q, info in pt.items() if q not in exp and (
        str(info.get("Title", "")).strip().lower().startswith(WAIT) or info.get("CoolTimeQuest")
        or (en.get(q) or {}).get("CoolTimeQuest")))
    dest = os.path.join(ROOT, "data", "quest_exp.json")
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(exp={str(q): v for q, v in sorted(exp.items())}, zero=zero), f, separators=(",", ":"))
    print("%d missões com XP (%d do rAthena, %d dos relatórios, %d copiadas de missões iguais), %d de espera -> %s "
          "(%d bytes)" % (len(exp), from_rathena, len(from_reports), copied, len(zero), dest, os.path.getsize(dest)))


if __name__ == "__main__":
    main()
