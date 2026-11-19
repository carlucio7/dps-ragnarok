# -*- coding: utf-8 -*-
"""Lê os relatórios de aprendizado que os jogadores mandaram (o texto copiado ou o arquivo salvo) e resume o que eles
ensinam, para melhorar o programa:

- XP por mapa e por dia, comparada com o normal de cada personagem: evento do servidor (vários mapas no mesmo dia)
  ou de um mapa só (spotlight);
- monstros que, sozinhos, rendem mais ou menos do que a lista do programa diz (spotlight ou XP errada na base);
- mortes (a regra dos 5% sem seguro);
- a recompensa de cada missão (o que os programas mediram e o que sobra nas medidas com uma missão só), qual regra
  de bônus de missão bate com o que o jogo pagou, e um arquivo com as recompensas para o tools/build_quest_exp.py
  (--missoes-json) levar para a próxima versão;
- monstros sem XP na base, XP de nível diferente da tabela, mudanças que os programas detectaram;
- drops por monstro e por bônus de drop ativo no abate, com intervalo de 95%, e o efeito de cada bônus em cada item
  juntando monstros e PCs (Mantel-Haenszel), para perguntas como "o bônus de drop afeta o Pó de Éter?".

Os relatórios são de outras pessoas: só dados. A ferramenta lê as linhas "RM|{json}" do fim de cada um e não roda
nada do que vier neles; o texto que vem neles é limpo antes de aparecer. O mesmo registro em relatórios seguidos do
mesmo PC conta uma vez (marca do registro + marca do PC).

Uso: python -I tools/ler_relatorios.py PASTA_OU_ARQUIVO [...] [--item ID|nome] [--monstro ID|nome]
         [--min-abates N] [--jogo PASTA_DO_JOGO] [-o resumo.txt] [--missoes-json recompensas.json]
"""

import argparse
import io
import json
import math
import os
import sys
import unicodedata

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import meter  # noqa: E402
import xp  # noqa: E402
import xpreport  # noqa: E402
from fmt import dec, full  # noqa: E402

FORMAT = 1                    # o formato do bloco de dados que esta ferramenta conhece (xpreport.FORMAT)
MAX_BYTES = 64 << 20          # arquivo maior que isso não é relatório
EXTS = (".txt", ".md", ".log")
WRAP_LINES = 40               # linha "RM|" quebrada no caminho (e-mail): junta até tantas linhas
DEV = 0.12                    # desvio que chama atenção (o mesmo que o programa usa para "o mapa mudou")
DOMINANT = 70                 # % da XP da medida para ela contar como "do monstro"
MIN_BASE = 3                  # medidas de um personagem para saber o normal dele
MIN_DROPS = 5                 # item com menos drops que isso fica fora da tabela dos bônus
MIN_EFFECT_KILLS = 30         # abates de cada lado (com e sem o bônus) para dar intervalo e veredito
QUEST_MIN_SHARE = 0.10        # a missão tem de pesar isso do trecho (abaixo, o erro dos abates engole a conta)
FLAG = "  <<"

_NAMES = {}                   # nomes que vieram nos relatórios (monstros que a base do programa não tem)


# ---------------------------------------------------------------------------------------------- texto e números

def clean(s, n=60):
    """Texto de outra pessoa, para mostrar: sem caracteres de controle (nada de sequências do terminal), curto."""
    s = s if isinstance(s, str) else "" if s is None else str(s)
    return "".join(ch for ch in s if ch.isprintable())[:n]


def number(x):
    """Número que veio no relatório, ou None (texto, booleano, infinito...)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return x if math.isfinite(x) else None


def count(x):
    v = number(x)
    return int(v) if v is not None and v >= 0 else 0


def fold(s):
    """Sem acento e em minúsculas, para procurar por nome."""
    return "".join(ch for ch in unicodedata.normalize("NFD", s or "") if unicodedata.category(ch) != "Mn").lower()


def x3(v):
    return "×" + dec("%.3f" % v) if v is not None else "×?"


def x2(v):
    return "×" + dec("%.2f" % v) if v is not None else "×?"


def pct(v):
    return dec(("%.2f%%" if v < 0.1 else "%.1f%%") % (100.0 * v))


def pval(p):
    if p is None:
        return "p ?"
    return "p < 0,001" if p < 0.001 else "p = " + dec("%.3f" % p if p < 0.1 else "%.2f" % p)


def plural(n, one, many):
    return "%s %s" % (full(n), one if n == 1 else many)


def mob_name(mid):
    try:
        n = meter.monster_name(int(mid))
    except (TypeError, ValueError):
        n = None
    return clean(n or _NAMES.get(str(mid)) or "Monstro %s" % mid)


def item_name(iid):
    try:
        return clean(meter.item_name(int(iid)))
    except (TypeError, ValueError):
        return clean("Item %s" % iid)


def job_name(jid):
    try:
        return clean(meter.job_name(int(jid))) or str(jid)
    except (TypeError, ValueError):
        return clean(jid)


def ctx_name(ctx):
    """Os bônus de drop de um abate em palavras ("-" = nenhum visível)."""
    if not ctx or ctx == "-":
        return "nenhum bônus de drop visível"
    out = []
    for part in str(ctx).split("+"):
        ef, _s, val = part.partition(":")
        out.append(clean(xpreport.drop_tag_text(ef, val), 80))
    return " + ".join(out)


def _tags(ctx):
    """Os bônus de um contexto ("252:100+983" -> {"252:100", "983"})."""
    return frozenset(t for t in str(ctx).split("+") if t and t != "-")


def _ctx_of(tags):
    return "+".join(sorted(tags)) or "-"          # como o programa escreve (xp.drop_context)


# ----------------------------------------------------------------------------------------------------- estatística

def wilson(k, n, z=1.96):
    """Intervalo de 95% da chance de drop com k drops em n abates (Wilson)."""
    if n <= 0:
        return 0.0, 1.0
    p = min(1.0, k / float(n))
    d = 1 + z * z / n
    c = (p + z * z / (2.0 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4.0 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def _lc(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def fisher(k1, n1, k2, n2):
    """Teste exato de Fisher, bilateral: a chance de drop é a mesma nos dois grupos? (p)."""
    if n1 <= 0 or n2 <= 0:
        return None
    k1, k2 = min(k1, n1), min(k2, n2)
    tot, n = k1 + k2, n1 + n2

    def lp(x):
        return _lc(n1, x) + _lc(n2, tot - x) - _lc(n, tot)
    obs = lp(k1)
    p = sum(math.exp(lp(x)) for x in range(max(0, tot - n2), min(n1, tot) + 1) if lp(x) <= obs + 1e-7)
    return min(1.0, p)


def mantel_haenszel(strata):
    """Juntando grupos (monstro e PC) com chances diferentes: [(drops com, abates com, drops sem, abates sem)] ->
    (razão das chances com ÷ sem, intervalo de 95%, p do teste de Cochran-Mantel-Haenszel) ou None."""
    num = den = var_num = 0.0
    obs = exp = var = 0.0
    used = 0
    for a, n1, b, n0 in strata:
        a, b = min(a, n1), min(b, n0)
        t = n1 + n0
        if n1 <= 0 or n0 <= 0 or t < 2:
            continue
        used += 1
        m1 = a + b
        num += a * n0 / float(t)
        den += b * n1 / float(t)
        var_num += (m1 * n1 * n0 - a * b * t) / float(t * t)
        obs += a
        exp += n1 * m1 / float(t)
        var += n1 * n0 * m1 * (t - m1) / float(t * t * (t - 1))
    if not used:
        return None
    if var > 0:
        chi = max(0.0, abs(obs - exp) - 0.5) ** 2 / var
        p = math.erfc(math.sqrt(chi / 2.0))
    else:
        p = 1.0
    if num <= 0 or den <= 0:
        return (math.inf if num > 0 else 0.0 if den > 0 else None), None, p
    rr = num / den
    se = math.sqrt(max(0.0, var_num) / (num * den))
    return rr, (rr * math.exp(-1.96 * se), rr * math.exp(1.96 * se)), p


# ------------------------------------------------------------------------------------------------------ leitura

def files(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                out += [os.path.join(root, n) for n in sorted(names) if n.lower().endswith(EXTS)]
        elif os.path.isfile(p):
            out.append(p)
    return out


def parse(text, src=""):
    """Os relatórios de um texto: ([dict(src, head, rows)], linhas "RM|" que não deram para ler)."""
    reports, bad, cur = [], 0, None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        k = lines[i].find("RM|")
        if k < 0:
            i += 1
            continue
        raw, j, obj = lines[i][k + 3:], i, None
        while True:
            try:
                obj = json.loads(raw)
                break
            except ValueError:
                if j + 1 >= len(lines) or j - i >= WRAP_LINES or "RM|" in lines[j + 1]:
                    break
                j += 1
                raw += lines[j]
        i = j + 1
        if not isinstance(obj, dict) or not isinstance(obj.get("t"), str):
            bad += 1
            continue
        if obj["t"] == "report":
            cur = dict(src=src, head=obj, rows=[])
            reports.append(cur)
            continue
        if cur is None:                          # sem o começo (texto cortado): vale como relatório à parte
            cur = dict(src=src, head={}, rows=[])
            reports.append(cur)
        cur["rows"].append(obj)
    return reports, bad


class Data:
    def __init__(self):
        self.files = 0
        self.reports = []
        self.bad = 0
        self.skipped = []           # (arquivo, motivo)
        self.measures = {}          # (pc, marca) -> medida
        self.drops = {}             # (pc, marca) -> gravação com drops
        self.unknown = {}           # monstro -> dict(names, maps, recs, last, pcs)
        self.changes = {}           # (data, mapa, antes, depois) -> {PCs}
        self.server = {}            # (data, antes, depois) -> {PCs}
        self.levels = {}            # (classe, nível) -> dict(table, game={valor: {PCs}})
        self.quests = {}            # (pc, marca) -> recompensa de missão medida pelo programa
        self.repeated = dict(m=0, d=0, q=0)
        self._same = {}             # conteúdo -> chave (o mesmo registro com outra marca, de versão diferente)


def _version(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


def _keep(data, store, kind, key, row, rep, same=None):
    """Guarda um registro; o que já veio (mesma marca do mesmo PC) fica com a versão do relatório mais novo. Uma
    medida igual em tudo com outra marca, vinda de outro relatório do mesmo PC, também é a mesma (versão do programa
    que marcava diferente)."""
    if key in store:
        data.repeated[kind] += 1
    elif same is not None and same in data._same and data._same[same][1] != rep:
        data.repeated[kind] += 1
        store.pop(data._same[same][0], None)
    store[key] = row
    if same is not None:
        data._same[same] = (key, rep)


def _add(data, pc, row, rep=0):
    t = row.get("t")
    if t == "m":
        ratio = number(row.get("ratio"))
        if ratio is None or ratio <= 0:
            return
        cid = clean(row.get("cid") or row.get("char"), 16)
        same = ("m", pc, cid, clean(row.get("date"), 10), clean(row.get("map"), 40), count(row.get("kills")),
                number(row.get("mins")), ratio)
        _keep(data, data.measures, "m", (pc, clean(row.get("id"), 16)), dict(row, pc=pc, cid=cid), rep, same)
    elif t == "d":
        # gravações pequenas iguais em tudo (um abate, nada caiu) são comuns: aqui só a marca diz que é a mesma
        if isinstance(row.get("mobs"), dict):
            _keep(data, data.drops, "d", (pc, clean(row.get("id"), 16)), dict(row, pc=pc), rep)
    elif t == "u":
        mid = clean(row.get("mob"), 12)
        if not mid:
            return
        u = data.unknown.setdefault(mid, dict(names={}, maps=set(), recs={}, last="", pcs=set()))
        nm = clean(row.get("name"))
        if nm:
            u["names"][nm] = u["names"].get(nm, 0) + 1
        if isinstance(row.get("maps"), dict):
            u["maps"].update(clean(m, 40) for m in row["maps"])
        if isinstance(row.get("recs"), dict):
            for r, n in row["recs"].items():
                k = (pc, clean(r, 16))
                u["recs"][k] = max(u["recs"].get(k, 0), count(n))
        u["last"] = max(u["last"], clean(row.get("last"), 10))
        u["pcs"].add(pc)
    elif t == "c":
        k = (clean(row.get("date"), 10), clean(row.get("map"), 40), number(row.get("old")), number(row.get("new")))
        data.changes.setdefault(k, set()).add(pc)
    elif t == "s":
        k = (clean(row.get("date"), 10), number(row.get("old")), number(row.get("new")))
        data.server.setdefault(k, set()).add(pc)
    elif t == "l":
        e = data.levels.setdefault((count(row.get("job")), count(row.get("level"))),
                                   dict(table=number(row.get("table")), game={}))
        g = number(row.get("game"))
        if g is not None:
            e["game"].setdefault(int(g), set()).add(pc)
    elif t == "n" and isinstance(row.get("names"), dict):
        for mid, nm in row["names"].items():
            _NAMES.setdefault(clean(mid, 12), clean(nm))
    elif t == "q":
        quest, base = count(row.get("quest")), number(row.get("base"))
        if not quest or base is None or base <= 0:
            return
        partners = sorted({count(p) for p in row.get("partners") or [] if count(p)}) \
            if isinstance(row.get("partners"), list) else []
        _keep(data, data.quests, "q", (pc, clean(row.get("id"), 16)),
              dict(pc=pc, quest=quest, base=base, level=count(row.get("level")), mult=number(row.get("mult")),
                   date=clean(row.get("date"), 10), known=number(row.get("known")), partners=partners,
                   mid=clean(row.get("mid"), 16)), rep)


def load(paths):
    """Lê os relatórios (pastas e arquivos) e junta tudo, sem contar duas vezes o que vier repetido."""
    data = Data()
    found = []
    for n, path in enumerate(files(paths)):
        data.files += 1
        try:
            if os.path.getsize(path) > MAX_BYTES:
                data.skipped.append((path, "grande demais"))
                continue
            with io.open(path, encoding="utf-8-sig", errors="replace") as f:
                text = f.read()
        except OSError as exc:
            data.skipped.append((path, clean(str(exc), 120)))
            continue
        reps, bad = parse(text, path)
        data.bad += bad
        found += [(r, n) for r in reps]
    # o mais novo por último: o mesmo registro em relatórios seguidos fica com o que veio no mais recente
    found.sort(key=lambda rn: (clean(rn[0]["head"].get("date"), 10), _version(rn[0]["head"].get("v")), rn[1]))
    for k, (rep, _n) in enumerate(found):
        pc = clean(rep["head"].get("pc"), 16) or "?%d" % k
        rep["pc"] = pc
        data.reports.append(rep)
        for row in rep["rows"]:
            _add(data, pc, row, k)
    return data


# --------------------------------------------------------------------------------------------------------- XP

def xp_rows(data):
    """As medidas, com o normal do personagem (rel. = razão ÷ normal) quando ele tem medidas suficientes. O normal é
    o do programa: os mapas que rendem até 8% acima do que rende menos (o spotlight só aumenta a XP)."""
    rows = []
    for (pc, mid), m in data.measures.items():
        rows.append(dict(pc=pc, mid=mid, char=(pc, m.get("cid") or "?"), date=clean(m.get("date"), 10) or "?",
                         map=clean(m.get("map"), 40) or "?", kills=max(1, count(m.get("kills"))),
                         mins=number(m.get("mins")) or 0.0, ratio=number(m.get("ratio")),
                         gain=number(m.get("gain")), level=count(m.get("level")), job=count(m.get("job")),
                         quests=[clean(q, 12) for q in m.get("quests")] if isinstance(m.get("quests"), list) else [],
                         quest_at=_quest_at(m.get("quest_at")),
                         edge=[clean(q, 12) for q in m.get("edge")] if isinstance(m.get("edge"), list) else [],
                         deaths=count(m.get("deaths")), insured=count(m.get("insured")),
                         mobs=m.get("mobs") if isinstance(m.get("mobs"), list) else [],
                         bonus=m.get("bonus") if isinstance(m.get("bonus"), dict) else {},
                         spot=bool(m.get("spot_list")), rel=None))
    by_char = {}
    for r in rows:
        if not r["quests"]:
            by_char.setdefault(r["char"], []).append([r["ratio"], r["kills"], r["date"], "", r["map"], r["kills"]])
    base = {ch: xp._baseline(s) for ch, s in by_char.items() if len(s) >= MIN_BASE}
    for r in rows:
        b = base.get(r["char"])
        if b:
            r["base"] = b
            r["rel"] = r["ratio"] / b
    return rows


def _wmean(pairs):
    w = sum(k for _v, k in pairs)
    return sum(v * k for v, k in pairs) / w if w else None


def _server(rows):
    """O evento do servidor que entrou na conta das medidas: "+100% em 8 de 8"."""
    seen = {}
    for r in rows:
        b = r["bonus"].get("server")
        key = "+%g%%" % b[1] if isinstance(b, list) and len(b) == 2 and number(b[1]) and (number(b[0]) or 0) >= 50 \
            else "nenhum"
        seen[key] = seen.get(key, 0) + 1
    return ", ".join("%s em %d de %d" % (k, n, len(rows)) for k, n in sorted(seen.items(), key=lambda kv: -kv[1]))


def section_xp(rows):
    out = []
    plain = [r for r in rows if not r["quests"]]
    if not plain:
        return out
    with_rel = [r for r in plain if r["rel"] is not None]
    # por dia, todos os mapas
    days = {}
    for r in with_rel:
        days.setdefault(r["date"], []).append(r)
    day_rel = {d: _wmean([(r["rel"], r["kills"]) for r in rs]) for d, rs in days.items()}
    out.append("== XP por dia, todos os mapas (rel. = comparada com o normal do mesmo personagem) ==")
    out.append("Só personagens com %d medidas ou mais. Evento do servidor no dia: vários mapas e PCs acima do normal."
               % MIN_BASE)
    for d in sorted(days):
        rs = days[d]
        maps, pcs = {r["map"] for r in rs}, {r["pc"] for r in rs}
        flag = ""
        if abs(day_rel[d] - 1) > DEV and (len(maps) >= 2 or len(pcs) >= 2):
            flag = FLAG + (" acima do normal em vários mapas: evento do servidor?" if day_rel[d] > 1 else
                           " abaixo do normal em vários mapas: evento acabou e o programa não viu?")
        out.append("%s · rel. %s · %s, %s, %s · evento do servidor na conta: %s%s" % (
            d, x3(day_rel[d]), plural(len(rs), "medida", "medidas"), plural(len(maps), "mapa", "mapas"),
            plural(len(pcs), "PC", "PCs"), _server(rs), flag))
    out.append("")
    # por mapa e por dia
    out.append("== XP por mapa (×: XP real ÷ estimada pela lista; rel.: comparada com o normal do personagem) ==")
    by_map = {}
    for r in plain:
        by_map.setdefault(r["map"], []).append(r)
    for mp, rs in sorted(by_map.items(), key=lambda kv: -sum(r["kills"] for r in kv[1])):
        rel = [r for r in rs if r["rel"] is not None]
        out.append("%s · %s, %s, %s · %s min, %s · %s (%s a %s)%s" % (
            mp, plural(len(rs), "medida", "medidas"), plural(len({r["pc"] for r in rs}), "PC", "PCs"),
            plural(len({r["char"] for r in rs}), "personagem", "personagens"),
            full(round(sum(r["mins"] for r in rs))), plural(sum(r["kills"] for r in rs), "abate", "abates"),
            x3(_wmean([(r["ratio"], r["kills"]) for r in rs])), x3(min(r["ratio"] for r in rs)),
            x3(max(r["ratio"] for r in rs)),
            " · rel. %s" % x3(_wmean([(r["rel"], r["kills"]) for r in rel])) if rel else ""))
        per_day = {}
        for r in rs:
            per_day.setdefault(r["date"], []).append(r)
        if len(per_day) < 2 and not any(r["rel"] is not None and abs(r["rel"] - 1) > DEV for r in rs):
            continue
        for d, ds in sorted(per_day.items()):
            dr = [r for r in ds if r["rel"] is not None]
            here = _wmean([(r["rel"], r["kills"]) for r in dr]) if dr else None
            flag = ""
            if here is not None and abs(here - 1) > DEV:
                others = [r for r in days.get(d, []) if r["map"] != mp]
                o = _wmean([(r["rel"], r["kills"]) for r in others]) if others else None
                if o is None:
                    flag = FLAG + " fora do normal (sem outros mapas no dia para comparar)"
                elif abs(o - 1) <= DEV:
                    flag = FLAG + (" só neste mapa: spotlight ou evento do mapa?" if here > 1 else
                                   " só neste mapa, abaixo: evento do mapa acabou?")
            out.append("   %s  %s%s · %s, %s%s" % (
                d, x3(_wmean([(r["ratio"], r["kills"]) for r in ds])), " rel. %s" % x3(here) if here else "",
                plural(len(ds), "medida", "medidas"), plural(len({r["pc"] for r in ds}), "PC", "PCs"), flag))
    out.append("")
    return out


def section_monsters(rows):
    """Medidas em que um monstro deu quase toda a XP: a razão dele diz se a lista acerta a XP desse monstro."""
    agg = {}
    for r in rows:
        if r["quests"] or not r["mobs"]:
            continue
        top = r["mobs"][0]
        if not isinstance(top, list) or len(top) != 2 or (number(top[1]) or 0) < DOMINANT:
            continue
        a = agg.setdefault(clean(top[0], 12), [])
        a.append(r)
    if not agg:
        return []
    out = ["== Monstros que deram %d%% ou mais da XP da medida ==" % DOMINANT,
           "Acima do normal: spotlight fora da lista ou XP da base baixa; abaixo: XP da base alta (ou evento acabou)."]
    for mid, rs in sorted(agg.items(), key=lambda kv: -sum(r["kills"] for r in kv[1])):
        rel = [r for r in rs if r["rel"] is not None]
        rv = _wmean([(r["rel"], r["kills"]) for r in rel]) if rel else None
        flag = ""
        if rv is not None and abs(rv - 1) > DEV:
            flag = FLAG + (" acima do normal" if rv > 1 else " abaixo do normal")
        out.append("%s (%s) · %s, %s, %s · %s%s · lista do evento na conta em %d de %d · %s a %s%s" % (
            mob_name(mid), mid, plural(len(rs), "medida", "medidas"), plural(len({r["pc"] for r in rs}), "PC", "PCs"),
            plural(sum(r["kills"] for r in rs), "abate", "abates"), x3(_wmean([(r["ratio"], r["kills"]) for r in rs])),
            " rel. %s" % x3(rv) if rv is not None else "", sum(1 for r in rs if r["spot"]), len(rs),
            min(r["date"] for r in rs), max(r["date"] for r in rs), flag))
    out.append("")
    return out


def section_deaths(rows):
    """Se a regra das mortes (−5% do nível sem seguro) está certa, as medidas com morte ficam no normal."""
    groups = (("com morte sem seguro (o programa desconta 5%)", lambda r: r["deaths"] > 0),
              ("só mortes com seguro", lambda r: not r["deaths"] and r["insured"] > 0),
              ("sem mortes", lambda r: not r["deaths"] and not r["insured"]))
    rel = [r for r in rows if r["rel"] is not None and not r["quests"]]
    parts = []
    for label, test in groups:
        rs = [r for r in rel if test(r)]
        if rs:
            parts.append("%s: %s, rel. %s" % (label, plural(len(rs), "medida", "medidas"),
                                              x3(_wmean([(r["rel"], r["kills"]) for r in rs]))))
    if not parts or not any(r["deaths"] or r["insured"] for r in rel):
        return []
    return ["== Mortes ==", "Com a regra certa, as medidas com morte ficam perto de ×1 como as outras.",
            *parts, ""]


def _quest_at(v):
    """[[missão, {bônus: %}]] de uma medida, só o que for válido."""
    out = []
    for x in v if isinstance(v, list) else []:
        if isinstance(x, list) and len(x) == 2 and isinstance(x[1], dict):
            out.append([clean(x[0], 12), {clean(k, 12): number(p) for k, p in x[1].items() if number(p) is not None}])
    return out


def _bonus_names(on):
    """Os bônus ativos numa entrega, em palavras: "evento do servidor +100%, VIP +20%, manual +50%"."""
    if on is None:
        return "não anotados (relatório de versão anterior)"
    if not on:
        return "nenhum"
    order = {k: i for i, k in enumerate(xp.QUEST_LOG_KEYS)}             # a ordem da lista de bônus do programa
    return ", ".join("%s +%g%%" % (xpreport.BONUS_NAMES.get(k, k), p)
                     for k, p in sorted(on.items(), key=lambda kv: (order.get(kv[0], 99), kv[0])))


QUEST_KEEP_SPREAD = 1.3       # recompensa vai para o arquivo se as medidas dela não variam mais que isso (maior÷menor)


def whole_level(level, pay, mult):
    """True se o que a medida diz que a missão pagou é a XP inteira do nível (ou a metade, um terço...): o programa
    que mediu não contou os abates do trecho (a 1.10.0, depois de um Zerar). O relatório não diz a classe: vale a XP
    do nível de qualquer tabela (xp.whole_level, a mesma conta que o programa usa para não aprender isso)."""
    try:
        level = int(level)
    except (TypeError, ValueError):
        return False
    return xp.whole_level(level, pay, mult)


def quest_mults(on):
    """(regra do programa, regra alternativa) do multiplicador de missão pelos bônus ativos na entrega, ou None sem eles
    anotados: (1 + manual + Kafra) × (1 + Njord) × (1 + Milagre), e (1 + evento + VIP + Cetro) + manual + Kafra."""
    if on is None:
        return None
    pct = {"p": 0.0, "k": 0.0, "first": 0.0}
    for k, v in on.items():
        role = xp.QUEST_ROLES.get(k)
        if role:
            pct[role] += v
    roles = {b["key"]: b.get("role", "p") for b in xp.BONUSES}
    g = sum(v for k, v in on.items() if roles.get(k) == "g")
    p = sum(v for k, v in on.items() if roles.get(k) == "p")
    return ((1 + pct["p"] / 100.0) * (1 + pct["k"] / 100.0) * (1 + pct["first"] / 100.0),
            1 + (g + p) / 100.0)


def _quest_id(q):
    try:
        return int(q)
    except (TypeError, ValueError):
        return None


def quest_obs(rows, data):
    """As recompensas medidas, uma por trecho: [dict(quest, base (sem bônus, pela regra do programa), pay (o que o
    jogo pagou), mult, rules ((programa, antiga) ou None), level, job, pc, date, src, partners, share, on)]. As do
    programa (linhas "q": XP real − abates ao fechar um nível ou entre gravações seguidas) e, nos trechos que ele não
    mediu, as medidas com uma missão só: XP real − abates × o normal do personagem, se ela pesa QUEST_MIN_SHARE do
    trecho. A entrega no instante de uma subida de nível fica de fora (a sobra dela não aparece)."""
    out, taken = [], set()
    for (pc, _id), q in data.quests.items():
        taken.add((pc, q["mid"]))
        pay = q["base"] * q["mult"] if q["mult"] else None
        out.append(dict(quest=q["quest"], base=q["base"], pay=pay,
                        mult=q["mult"], rules=None, level=q["level"], job=None, pc=pc, date=q["date"],
                        src="programa", partners=q["partners"], share=None, on=None,
                        whole=whole_level(q["level"], pay, q["mult"])))
    for r in rows:
        qs = [q for q in (_quest_id(x) for x in r["quests"]) if q and not xp.quest_wait(q)]
        # uma missão só, entregue uma vez ou mais (a Água Mineral renova a espera: cada entrega rende inteira)
        if (r["pc"], r["mid"]) in taken or not qs or len(set(qs)) != 1 or str(qs[0]) in r["edge"] \
                or not r["gain"] or not r.get("base"):
            continue
        share = 1 - r["base"] / r["ratio"]
        if share < QUEST_MIN_SHARE:
            continue
        on = next((o for q, o in r["quest_at"] if _quest_id(q) == qs[0]), None)
        rules = quest_mults(on)
        pay = r["gain"] * share / len(qs)
        out.append(dict(quest=qs[0], base=pay / rules[0] if rules else None, pay=pay, mult=rules[0] if rules else None,
                        rules=rules, level=r["level"], job=r["job"], pc=r["pc"], date=r["date"], src="medida",
                        partners=[], share=share, on=on, times=len(qs)))
    return out


def quest_rewards(obs):
    """{missão: (recompensa sem bônus, nº de medidas, maior÷menor)} das medidas de uma missão sozinha (as divididas
    em grupo só valem juntas e ficam de fora)."""
    by = {}
    for o in obs:
        if o["base"] and not o["partners"] and not o.get("whole"):
            by.setdefault(o["quest"], []).append(o["base"])
    out = {}
    for q, vals in by.items():
        vals.sort()
        mid = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2.0
        out[q] = (mid, len(vals), vals[-1] / vals[0])
    return out


def quests_for_build(obs):
    """{missão: recompensa} para o tools/build_quest_exp.py: as que têm duas medidas ou mais que não variam mais que
    QUEST_KEEP_SPREAD, ou uma medida do próprio programa."""
    progs = {o["quest"] for o in obs if o["src"] == "programa" and not o["partners"] and not o.get("whole")}
    return {str(q): int(round(v)) for q, (v, n, spread) in quest_rewards(obs).items()
            if (n >= 2 and spread <= QUEST_KEEP_SPREAD) or (n == 1 and q in progs)}


def _quest_title(q):
    try:
        import quests
        return clean(quests.title(int(q)))
    except Exception:  # noqa: BLE001 - sem o jogo: só o número
        return ""


def section_quests(rows, data):
    """A recompensa de cada missão e a regra do bônus de missão que bate com o que o jogo pagou."""
    obs = quest_obs(rows, data)
    turned = {}
    for r in rows:
        for q in (_quest_id(x) for x in r["quests"]):
            if q and not xp.quest_wait(q):
                turned[q] = turned.get(q, 0) + 1
    if not obs and not turned:
        return []
    out = ["== Missões: recompensa medida (sem bônus) ==",
           "Cada linha é um trecho com a XP exata: o que o jogo pagou pela missão (XP real − XP dos abates) e a "
           "recompensa sem bônus pela regra do programa ((1 + manual + Kafra) × Njord × Milagre). \"programa\": "
           "medida pelo próprio programa ao fechar um nível ou entre duas gravações seguidas; \"medida\": a sobra "
           "numa medida com essa missão só (abates × o normal do personagem; erro de uns 3% do trecho). A entrega "
           "no instante de uma subida de nível fica de fora."]
    rewards = quest_rewards(obs)
    table = xp._quest_data()[0]
    by_q = {}
    for o in obs:
        by_q.setdefault(o["quest"], []).append(o)
    for q, os_ in sorted(by_q.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        title = _quest_title(q)
        head = "missão %s%s · %s" % (q, " (%s)" % title if title and title != "Missão %s" % q else "",
                                     plural(len(os_), "medida", "medidas"))
        if q in rewards:
            v, n, spread = rewards[q]
            head += " · recompensa ≈ %s%s" % (full(round(v)), " (de %d, maior ÷ menor %s)" % (n, x2(spread))
                                               if n > 1 else "")
        if q in table:
            head += " · tabela do programa: %s" % full(table[q])
        out.append(head)
        for o in sorted(os_, key=lambda o: (o["level"], o["date"])):
            parts = ["   nível %d%s" % (o["level"], " " + job_name(o["job"]) if o["job"] else ""), o["date"] or "?"]
            if o["src"] == "medida":
                parts.append("XP ≈ %s (%d%% do trecho%s)" % (
                    full(round(o["pay"])), round(100 * o["share"]),
                    ", %d entregas" % o["times"] if o.get("times", 1) > 1 else ""))
                parts.append("bônus na entrega: %s" % _bonus_names(o["on"]))
            elif o["pay"]:
                parts.append("pagou %s (×%s na entrega)" % (full(round(o["pay"])), dec("%.2f" % o["mult"])))
            if o["base"]:
                parts.append("sem bônus ≈ %s" % full(round(o["base"])))
            if o["partners"]:
                parts.append("junto com %s: o total dividido (só vale junto)" % ", ".join(map(str, o["partners"])))
            parts.append(o["src"])
            if o.get("whole"):
                parts.append("DESCARTADA: é a XP do nível inteiro (os abates do trecho não entraram na conta; a 1.10.0 "
                             "fazia isso depois de um Zerar)")
            out.append(" · ".join(parts))
    rest = sorted(q for q in turned if q not in by_q)
    if rest:
        out.append("Entregues sem dar para medir (junto com outras, no instante de uma subida, ou pesando menos de "
                   "%d%% do trecho): %s" % (round(100 * QUEST_MIN_SHARE),
                                           ", ".join("%s (%d)" % (q, turned[q]) if turned[q] > 1 else str(q)
                                                     for q in rest)))
    out.append("")
    out += section_quest_rule(obs, table)
    return out


def section_quest_rule(obs, table):
    """O que o jogo pagou ÷ a recompensa da tabela do programa, contra as duas regras de bônus de missão."""
    lines, err = [], {"programa": [], "alternativa": []}
    for o in sorted(obs, key=lambda o: (o["quest"], o["level"])):
        t = table.get(o["quest"])
        if not t or not o["pay"] or o["partners"] or o.get("whole"):
            continue
        paid = o["pay"] / t
        txt = "missão %s nível %d (%s): pagou %s" % (o["quest"], o["level"], o["src"], x2(paid))
        if o["rules"]:
            a, b = o["rules"]
            err["programa"].append(abs(paid / a - 1))
            err["alternativa"].append(abs(paid / b - 1))
            txt += " · regra do programa %s (%+d%%) · regra alternativa %s (%+d%%) · bônus na entrega: %s" % (
                x2(a), round(100 * (paid / a - 1)), x2(b), round(100 * (paid / b - 1)), _bonus_names(o["on"]))
        elif o["mult"]:
            err["programa"].append(abs(paid / o["mult"] - 1))
            txt += " · regra do programa %s (%+d%%)" % (x2(o["mult"]), round(100 * (paid / o["mult"] - 1)))
        lines.append(txt)
    if not lines:
        return []
    out = ["== Regra do bônus de missão (o que o jogo pagou ÷ a recompensa da tabela) ==",
           "Regra do programa: (1 + manual + Kafra) × Njord × Milagre. Regra alternativa: (1 + evento + VIP + Cetro) "
           "+ manual + Kafra. A que erra menos é a do jogo (com o mesmo personagem e bônus, o erro dos abates fica em "
           "uns 3% do trecho). Eventos que aumentam a XP de certas missões (episódios, quadro do Éden) aparecem como "
           "\"pagou mais\" nas missões deles."]
    out += ["   " + ln for ln in lines]
    for k, label in (("programa", "regra do programa"), ("alternativa", "regra alternativa")):
        if err[k]:
            e = sorted(err[k])
            out.append("Erro mediano da %s: %d%% em %s" % (label, round(100 * e[len(e) // 2]),
                                                          plural(len(e), "medida", "medidas")))
    out.append("")
    return out


# ------------------------------------------------------------------------------------------- o resto do registro

def section_unknown(data):
    if not data.unknown:
        return []
    out = ["== Monstros sem XP na base (para data/mob_exp_extra.json) =="]
    for mid, u in sorted(data.unknown.items(), key=lambda kv: -sum(kv[1]["recs"].values())):
        name = max(u["names"].items(), key=lambda kv: kv[1])[0] if u["names"] else mob_name(mid)
        out.append("%s (%s) · %s em %s, %s · mapas: %s · visto por último em %s" % (
            name, mid, plural(sum(u["recs"].values()), "abate", "abates"),
            plural(len(u["recs"]), "gravação", "gravações"), plural(len(u["pcs"]), "PC", "PCs"),
            ", ".join(sorted(u["maps"])) or "?", u["last"] or "?"))
    out.append("")
    return out


def section_levels(data):
    if not data.levels:
        return []
    out = ["== XP de nível diferente da tabela do programa =="]
    for (job, lv), e in sorted(data.levels.items()):
        game = ", ".join("%s (%s)" % (full(v), plural(len(p), "PC", "PCs"))
                         for v, p in sorted(e["game"].items(), key=lambda kv: -len(kv[1])))
        out.append("%s (%d) nível %d: o jogo mandou %s; a tabela diz %s" % (
            job_name(job), job, lv, game or "?", full(e["table"]) if e["table"] else "nada"))
    out.append("")
    return out


def section_changes(data):
    rows = [(d, "%s: %s → %s" % (m, x2(o), x2(n)), p) for (d, m, o, n), p in data.changes.items()]
    rows += [(d, "evento do servidor: +%s%% → +%s%%" % (o, n), p) for (d, o, n), p in data.server.items()]
    if not rows:
        return []
    out = ["== Mudanças que os programas detectaram =="]
    out += ["%s  %s (%s)" % (d, t, plural(len(p), "PC", "PCs")) for d, t, p in sorted(rows)]
    out.append("")
    return out


# ------------------------------------------------------------------------------------------------------- drops

def drop_table(data):
    """{monstro: {bônus: {(pc, dia): [abates, {item: quantos}]}}}, de todas as gravações (sem repetidas). O dia separa
    os eventos de drop (item de evento, drop em dobro no fim de semana) do efeito dos bônus."""
    tab = {}
    for (pc, _id), rec in data.drops.items():
        day = clean(rec.get("date"), 10)
        for mid, ctxs in rec["mobs"].items():
            if not isinstance(ctxs, dict):
                continue
            for ctx, val in ctxs.items():
                if not isinstance(val, list) or len(val) != 2 or not isinstance(val[1], dict):
                    continue
                cell = tab.setdefault(clean(mid, 12), {}).setdefault(clean(ctx, 80), {}).setdefault((pc, day), [0, {}])
                cell[0] += count(val[0])
                for it, n in val[1].items():
                    it = clean(it, 12)
                    cell[1][it] = cell[1].get(it, 0) + count(n)
    return tab


def _sum_pcs(by_pc):
    k, items = 0, {}
    for n, its in by_pc.values():
        k += n
        for it, c in its.items():
            items[it] = items.get(it, 0) + c
    return k, items


def _match(query, ident, name):
    if query is None:
        return True
    q = fold(str(query)).strip()
    return q == str(ident) or (not q.isdigit() and q in fold(name))


def section_drops(data, item=None, mob=None, min_kills=30):
    tab = drop_table(data)
    if not tab:
        return []
    out = ["== Drops (abates isolados de quem deu a maior parte do dano) ==",
           "Cada bloco: os bônus de drop ativos no abate · abates · item: quantos caíram = por abate (intervalo de "
           "95%). O efeito de cada bônus, com os outros iguais, vem na seção seguinte."]
    shown = 0
    for mid, ctxs in sorted(tab.items(), key=lambda kv: -sum(_sum_pcs(v)[0] for v in kv[1].values())):
        if not _match(mob, mid, mob_name(mid)):
            continue
        tot = sum(_sum_pcs(v)[0] for v in ctxs.values())
        if tot < min_kills:
            continue
        flat = {ctx: _sum_pcs(by_pc) for ctx, by_pc in ctxs.items()}
        items = {it for _k, its in flat.values() for it in its}
        if item is not None:
            items = {it for it in items if _match(item, it, item_name(it))}
            if not items:
                continue
        out.append("%s (%s) · %s · %s" % (mob_name(mid), mid, plural(tot, "abate", "abates"),
                                          plural(len({s[0] for v in ctxs.values() for s in v}), "PC", "PCs")))
        for ctx, (k, its) in sorted(flat.items(), key=lambda kv: (kv[0] != "-", -kv[1][0])):   # sem bônus primeiro
            out.append("   %s · %s" % (ctx_name(ctx), plural(k, "abate", "abates")))
            for it in sorted(items, key=lambda i: (-(its.get(i, 0)), i)):
                n = its.get(it, 0)
                txt = "      %s (%s): %s = %s" % (item_name(it), it, full(n), pct(n / float(k)) if k else "?")
                if k and n <= k:
                    lo, hi = wilson(n, k)
                    txt += " (%s a %s)" % (pct(lo), pct(hi))
                elif k:
                    txt += " (vários por abate)"
                out.append(txt)
        shown += 1
    if not shown:
        out.append("(nenhum monstro com %d abates ou mais%s)" % (min_kills, " e esse item/monstro" if item or mob else ""))
    out.append("")
    out += section_bonus_effect(tab, item, mob)
    return out


def bonus_effect(tab, item=None, mob=None):
    """O efeito de cada bônus de drop em cada item: os abates com o bônus contra os abates com os mesmos outros bônus
    e sem ele, do mesmo monstro, no mesmo PC e no mesmo dia (os bônus escondidos de cada jogador, como os do
    equipamento, e os eventos do dia ficam iguais dos dois lados). [(item, bônus, (×, intervalo, p), [monstros,
    drops com, abates com, drops sem, abates sem])]."""
    pairs, totals = {}, {}
    for mid, ctxs in tab.items():
        if not _match(mob, mid, mob_name(mid)):
            continue
        items = {it for by_pc in ctxs.values() for _k, its in by_pc.values() for it in its}
        if item is not None:
            items = {it for it in items if _match(item, it, item_name(it))}
        for ctx, by_pc in ctxs.items():
            tags = _tags(ctx)
            for tag in tags:
                base = ctxs.get(_ctx_of(tags - {tag}))
                if not base:
                    continue
                for pc, (k, its) in by_pc.items():
                    if pc not in base:
                        continue
                    k0, its0 = base[pc]
                    for it in items:
                        a, b = its.get(it, 0), its0.get(it, 0)
                        pairs.setdefault((it, tag), []).append((a, k, b, k0))
                        t = totals.setdefault((it, tag), [set(), 0, 0, 0, 0])
                        t[0].add(mid)
                        t[1] += a
                        t[2] += k
                        t[3] += b
                        t[4] += k0
    rows = []
    for key, strata in pairs.items():
        t = totals[key]
        if t[1] + t[3] < MIN_DROPS:
            continue
        res = mantel_haenszel(strata)
        if res is not None and res[0] is not None:
            rows.append((key[0], key[1], res, t))
    return rows


def verdict(rr, ci, p, kills_with, kills_without):
    """Leitura curta do efeito: aumenta / diminui / não muda / falta abate."""
    if min(kills_with, kills_without) < MIN_EFFECT_KILLS:
        return "falta abate para saber"
    if p is not None and p < 0.05:
        return "aumenta" if rr > 1 else "diminui"
    if ci and ci[0] >= 1 / 1.3 and ci[1] <= 1.3:
        return "não muda (no máximo ±30%)"
    return "falta abate para saber"


def section_bonus_effect(tab, item=None, mob=None):
    rows = bonus_effect(tab, item, mob)
    if not rows:
        return []
    out = ["== Efeito de cada bônus de drop em cada item (Mantel-Haenszel) ==",
           "Chance com o bônus ÷ sem ele, com os outros bônus iguais, no mesmo monstro, PC e dia, juntando tudo. ×1 com "
           "intervalo estreito: o bônus não muda esse item. Com menos de %d abates de um lado, só o número."
           % MIN_EFFECT_KILLS]
    for it, tag, (rr, ci, p), t in sorted(rows, key=lambda r: (item_name(r[0]), -r[3][2])):
        few = min(t[2], t[4]) < MIN_EFFECT_KILLS
        rr_txt = "só caiu com o bônus" if rr == math.inf else x2(rr)
        ci_txt = " (95%%: %s a %s)" % (x2(ci[0]), x2(ci[1])) if ci and not few else ""
        out.append("%s (%s) · + %s: %s%s, %s · %s · com: %s em %s; sem: %s em %s · %s" % (
            item_name(it), it, ctx_name(tag), rr_txt, ci_txt, pval(p), verdict(rr, ci, p, t[2], t[4]), full(t[1]),
            plural(t[2], "abate", "abates"), full(t[3]), plural(t[4], "abate", "abates"),
            plural(len(t[0]), "monstro", "monstros")))
    out.append("")
    return out


# --------------------------------------------------------------------------------------------------------- tudo

def summary(data, item=None, mob=None, min_kills=30):
    """O resumo inteiro, em texto."""
    heads = [r["head"] for r in data.reports]
    versions = sorted({clean(h.get("v"), 16) for h in heads if h.get("v")}, key=_version)
    dates = sorted(clean(h.get("date"), 10) for h in heads if h.get("date"))
    newer = [h for h in heads if count(h.get("fmt")) > FORMAT]
    rows = xp_rows(data)
    out = ["Relatórios de aprendizado do Replay Master",
           "%s, %s de %s%s%s" % (
               plural(data.files, "arquivo", "arquivos"), plural(len(data.reports), "relatório", "relatórios"),
               plural(len({r["pc"] for r in data.reports}), "PC", "PCs"),
               " (%s %s)" % ("versão" if len(versions) == 1 else "versões", ", ".join(versions)) if versions else "",
               "" if not dates else ", gerados em %s" % dates[0] if dates[0] == dates[-1] else
               ", gerados de %s a %s" % (dates[0], dates[-1])),
           "%s (%s), %s, %s sem XP na base, %s com XP de nível diferente" % (
               plural(len(data.measures), "medida de XP", "medidas de XP"),
               plural(len({r["char"] for r in rows}), "personagem", "personagens"),
               plural(len(data.drops), "gravação com drops", "gravações com drops"),
               plural(len(data.unknown), "monstro", "monstros"), plural(len(data.levels), "nível", "níveis"))]
    if data.repeated["m"] or data.repeated["d"]:
        out.append("Repetidos (já vinham em relatório anterior do mesmo PC), contados uma vez: %s, %s" % (
            plural(data.repeated["m"], "medida", "medidas"),
            plural(data.repeated["d"], "gravação com drops", "gravações com drops")))
    if data.bad:
        out.append("Linhas de dados que não deram para ler (cortadas ou mexidas): %d" % data.bad)
    for path, why in data.skipped:
        out.append("Arquivo pulado: %s (%s)" % (clean(os.path.basename(path), 80), why))
    if newer:
        out.append("Atenção: %s de um formato mais novo que esta ferramenta (pode faltar coisa)."
                   % plural(len(newer), "relatório", "relatórios"))
    out.append("")
    if item is None and mob is None:
        out += section_xp(rows)
        out += section_monsters(rows)
        out += section_deaths(rows)
        out += section_quests(rows, data)
        out += section_unknown(data)
        out += section_levels(data)
        out += section_changes(data)
    out += section_drops(data, item, mob, min_kills)
    return "\n".join(out).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Resume os relatórios de aprendizado do Replay Master.")
    ap.add_argument("paths", nargs="+", help="pastas ou arquivos com os relatórios (.txt, .md, .log)")
    ap.add_argument("--item", help="só este item nos drops (número ou parte do nome)")
    ap.add_argument("--monstro", help="só este monstro nos drops (número ou parte do nome)")
    ap.add_argument("--min-abates", type=int, default=30, help="monstro com menos abates fica fora dos drops")
    ap.add_argument("--jogo", help="pasta do jogo, para os nomes de itens e monstros como o jogo mostra")
    ap.add_argument("-o", "--saida", help="grava o resumo neste arquivo (UTF-8) em vez de mostrar")
    ap.add_argument("--missoes-json", help="grava as recompensas de missão medidas neste arquivo, para o "
                                           "tools/build_quest_exp.py --relatorios")
    a = ap.parse_args(argv)
    if a.jogo:
        import clientdata
        clientdata.NAMES.use_folder(a.jogo)
        clientdata.NAMES.load()
    data = load(a.paths)
    text = summary(data, a.item, a.monstro, a.min_abates)
    if a.missoes_json:
        import datetime
        rewards = quests_for_build(quest_obs(xp_rows(data), data))
        with io.open(a.missoes_json, "w", encoding="utf-8") as f:
            json.dump(dict(exp=rewards, date=datetime.date.today().isoformat(),
                           reports=len(data.reports)), f, ensure_ascii=False, indent=1, sort_keys=True)
        print("recompensas de %d missões gravadas em %s" % (len(rewards), a.missoes_json))
    if a.saida:
        with io.open(a.saida, "w", encoding="utf-8") as f:
            f.write(text)
        print("resumo gravado em %s (%d linhas)" % (a.saida, text.count("\n")))
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
