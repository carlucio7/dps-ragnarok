# -*- coding: utf-8 -*-
"""Relatório do que o Replay Master aprendeu sobre o jogo (XP e drops), para o jogador ler e, se quiser, mandar
para quem desenvolve o programa ou para outra pessoa. O programa não envia nada.

Sem nada pessoal: sem nomes de personagem, de conta, de grupo ou de guilda e sem nomes de arquivo. Os personagens
aparecem como A, B, C (classe e nível). Datas só do dia. Monstros, itens, mapas e efeitos são do jogo.
"""

import datetime
import hashlib
import json
import os

import meter
import xp
from fmt import dec, full
from i18n import _

FORMAT = 1                    # versão do bloco de dados (RM|...), lido por tools/ler_relatorios.py

BONUS_NAMES = {"server": "evento do servidor", "vip": "VIP", "scepter": "Cetro", "kafra": "Kafra Buff",
               "manual": "manual", "njord": "Njord", "gear": "itens", "miracle": "Milagre"}
MIN_DROP_KILLS = 3            # monstro com menos abates que isso fica fora dos drops (não diz nada)


def _letters(lrn):
    """{personagem: letra}, na ordem em que apareceram nas medidas e nos drops."""
    order = []
    for m in lrn.get("measures") or []:
        if m.get("char") not in order:
            order.append(m.get("char"))
    return {g: (chr(ord("A") + i) if i < 26 else "P%d" % (i + 1)) for i, g in enumerate(order)}


_SEEN = {}                    # nomes que o jogo mostrou na gravação (monstros que a base do programa não tem)


def _mob(mid):
    try:
        return meter.monster_name(int(mid)) or _SEEN.get(str(mid)) or _("Monstro %d") % int(mid)
    except (TypeError, ValueError):
        return str(mid)


DROP_ITEMS = {252: (12210, 12412)}   # efeito de drop -> itens que dão (o nome do efeito no jogo é o interno)
DROP_PCT = {252}                     # efeitos cujo valor é o % de drop (nos outros o valor do jogo vai como está)


def drop_status_name(ef):
    """Nome de um efeito de drop: o dos itens que dão ("Goma de Mascar/Super Chiclete") ou o do jogo."""
    items = DROP_ITEMS.get(ef)
    if items:
        return "/".join(meter.item_name(i) for i in items)
    return meter.status_name(ef) or str(ef)


def _ctx_text(ctx):
    """Os bônus de drop de um abate em palavras: "Goma de Mascar/Super Chiclete (252) 100% + Bônus de DROP (983)"."""
    if not ctx or ctx == "-":
        return _("nenhum bônus de drop visível")
    out = []
    for part in ctx.split("+"):
        ef, _sep, val = part.partition(":")
        out.append(drop_tag_text(ef, val))
    return " + ".join(out)


def drop_tag_text(ef, val=""):
    """Um efeito de drop com o valor: "Goma de Mascar/Super Chiclete (252) 100%", "Bônus de DROP (938) [30000]"."""
    try:
        name = "%s (%s)" % (drop_status_name(int(ef)), ef)        # nomes iguais no jogo: o número separa
        pct = int(ef) in DROP_PCT
    except ValueError:
        name, pct = ef, False
    if not val or val == "0":
        return name
    return "%s %s%%" % (name, val) if pct else "%s [%s]" % (name, val)


def _bonus_text(bon):
    """Os bônus de XP de uma medida: "evento do servidor +100%, VIP (100% do trecho), manual +50% (80% do trecho)"."""
    out = []
    for k, (cover, pct) in sorted((bon or {}).items()):
        name = _(BONUS_NAMES.get(k, k))
        txt = name + (" +%g%%" % pct if pct and k not in ("vip", "scepter", "kafra") else "")
        if cover < 100:
            txt += " (%s)" % (_("%d%% do trecho") % cover)
        out.append(txt)
    return ", ".join(out) or "—"


def text(cfg, version=""):
    """O relatório inteiro, em texto."""
    lrn = (cfg or {}).get("xp_learn") or {}
    _SEEN.clear()
    _SEEN.update(lrn.get("names") or {})
    letters = _letters(lrn)
    measures = list(lrn.get("measures") or [])
    lines = [_("Replay Master %s · relatório de aprendizado") % version,
             _("Gerado em %s. O programa não enviou nada: este texto só sai do seu PC se você mandar.")
             % datetime.date.today().isoformat(),
             _("Sem nada pessoal: sem nomes de personagem, conta, grupo ou guilda e sem nomes de arquivo. Os "
               "personagens aparecem como A, B, C.")]
    fr = lrn.get("folder_read")
    if isinstance(fr, dict) and fr.get("files"):
        lines.append(_("Inclui as %d gravações que já estavam na pasta, lidas uma vez em %s.")
                     % (fr["files"], fr.get("date") or "?"))
    lines.append("")
    head = len(lines)

    # personagens: classe e níveis vistos
    chars = {}
    for m in measures:
        c = chars.setdefault(m.get("char"), dict(job=m.get("job"), levels=set()))
        c["levels"].add(m.get("level"))
    if chars:
        lines.append("== %s ==" % _("Personagens"))
        for g, c in chars.items():
            lv = sorted(v for v in c["levels"] if v)
            lines.append("%s: %s, %s" % (letters.get(g, "?"), meter.job_name(c["job"]) or c["job"],
                                         (_("nível %d") % lv[0]) if len(lv) == 1 else
                                         (_("níveis %d a %d") % (lv[0], lv[-1])) if lv else "?"))
        lines.append("")

    # XP por mapa
    by_map = {}
    for m in measures:
        if not m.get("quests"):
            by_map.setdefault(m.get("map") or "?", []).append(m)
    if by_map:
        lines.append("== %s ==" % _("XP por mapa (XP real ÷ XP estimada pela lista de bônus)"))
        for mp, ms in sorted(by_map.items(), key=lambda kv: -len(kv[1])):
            k = sum(x.get("kills") or 0 for x in ms) or 1
            ratio = sum(x["ratio"] * (x.get("kills") or 0) for x in ms) / k
            days = sorted({x["date"][:10] for x in ms})
            mobs = {}
            for x in ms:
                for mid, share in x.get("mobs") or []:
                    mobs[mid] = mobs.get(mid, 0) + share * (x.get("kills") or 0)
            top = sorted(mobs.items(), key=lambda kv: -kv[1])[:4]
            tot = sum(mobs.values()) or 1
            lines.append(_("%s · %s · %d medidas, %s min · ×%s (de ×%s a ×%s) · personagens %s · monstros: %s") % (
                mp, days[0] if len(days) == 1 else "%s a %s" % (days[0], days[-1]), len(ms),
                dec("%.0f" % sum(x.get("mins") or 0 for x in ms)), dec("%.3f" % ratio),
                dec("%.3f" % min(x["ratio"] for x in ms)), dec("%.3f" % max(x["ratio"] for x in ms)),
                ", ".join(sorted({letters.get(x.get("char"), "?") for x in ms})),
                ", ".join("%s %d%%" % (_mob(mid), round(100 * v / tot)) for mid, v in top)))
        lines.append("")

    # mudanças detectadas
    changes = [(c["date"], _("%s: ×%s → ×%s (o mapa mudou: evento começou ou acabou?)") % (
        c["map"], dec("%.2f" % c["old"]), dec("%.2f" % c["new"]))) for c in lrn.get("changes") or []]
    changes += [(s["date"], _("evento do servidor: +%d%% → +%d%% (deduzido pela XP exata)") % (s["old"], s["new"]))
                for s in lrn.get("server") or []]
    if changes:
        lines.append("== %s ==" % _("Mudanças detectadas"))
        lines += ["%s  %s" % (d, t) for d, t in sorted(changes)]
        lines.append("")

    # medidas uma a uma
    if measures:
        lines.append("== %s ==" % _("Medidas de XP exata (uma por linha)"))
        lines.append(_("data · mapa · minutos · abates (divididos) · real÷estimado · personagem e nível · mortes · "
                       "missões · bônus · monstros"))
        for m in sorted(measures, key=lambda x: x["date"]):
            deaths = []
            if m.get("deaths"):
                deaths.append(_("%d sem seguro") % m["deaths"])
            if m.get("insured"):
                deaths.append(_("%d com seguro") % m["insured"])
            lines.append(" · ".join([
                m["date"][:10], m.get("map") or "?", dec("%.1f" % (m.get("mins") or 0)),
                "%d (%d)" % (m.get("kills") or 0, m.get("shared") or 0), "×" + dec("%.3f" % m["ratio"]),
                "%s %s" % (letters.get(m.get("char"), "?"), m.get("level") or "?"),
                ", ".join(deaths) or _("sem mortes"),
                (_("missões %s") % ", ".join(str(q) for q in m["quests"])) if m.get("quests") else _("sem missões"),
                _bonus_text(m.get("bonus")),
                ", ".join("%s %d%%" % (_mob(mid), share) for mid, share in (m.get("mobs") or [])[:4])]))
        lines.append("")

    # monstros sem XP na base
    unknown = lrn.get("unknown") or {}
    if unknown:
        lines.append("== %s ==" % _("Monstros que o programa ainda não conhece a XP"))
        for mid, u in sorted(unknown.items(), key=lambda kv: -sum((kv[1].get("recs") or {}).values())):
            recs = u.get("recs") or {}
            name = u.get("name")
            if not name or str(mid) in str(name):             # "Monstro 21533": gravado sem os nomes do jogo
                name = _mob(mid)
            lines.append(_("%s (%s) · mapas %s · %d abates em %d gravações · visto por último em %s") % (
                name, mid, ", ".join(sorted(u.get("maps") or {})) or "?",
                sum(recs.values()), len(recs), u.get("last") or "?"))
        lines.append("")

    # recompensas de missão medidas (XP real − abates, ao fechar um nível ou entre duas gravações seguidas)
    obs = [q for q in lrn.get("quests") or [] if isinstance(q, dict) and q.get("quest") is not None]
    if obs:
        import quests
        lines.append("== %s ==" % _("Recompensas de missão medidas (sem bônus)"))
        for q in sorted(obs, key=lambda x: (str(x.get("quest")), str(x.get("date") or ""))):
            extra = []
            if q.get("known"):
                extra.append(_("o programa já esperava %s") % full(q["known"]))
            if q.get("with"):
                extra.append(_("entregue junto com %s: o total dividido entre elas") %
                             ", ".join(str(w) for w in q["with"]))
            lines.append(" · ".join([_("missão %s (%s)") % (q["quest"], quests.title(int(q["quest"]))),
                                     full(q.get("base") or 0) + (" (×%s %s)" % (dec("%.2f" % q["mult"]),
                                                                             _("na entrega")) if q.get("mult") else ""),
                                     _("nível %s") % (q.get("level") or "?"), q.get("date") or "?"] + extra))
        lines.append("")

    # XP de nível que o jogo mandou e a tabela do programa não tem (ou tem diferente)
    diff = []
    for job, levels in sorted(((cfg or {}).get("xp_levels") or {}).items()):
        for lv, val in sorted(levels.items(), key=lambda kv: int(kv[0])):
            table = xp.table_need(int(job), int(lv))
            if table != val:
                diff.append(_("%s nível %s: o jogo mandou %s, a tabela do programa diz %s") % (
                    meter.job_name(int(job)) or job, lv, full(val), full(table) if table else _("nada")))
    if diff:
        lines.append("== %s ==" % _("XP de nível diferente da tabela do programa"))
        lines += diff
        lines.append("")

    # drops: por monstro, separados pelos bônus de drop ativos no abate
    agg = {}
    days = set()
    for rec in (lrn.get("drops") or {}).values():
        days.add(rec.get("date") or "")
        for mid, ctxs in (rec.get("mobs") or {}).items():
            for ctx, (k, items) in ctxs.items():
                row = agg.setdefault(mid, {}).setdefault(ctx, [0, {}])
                row[0] += k
                for it, n in items.items():
                    row[1][it] = row[1].get(it, 0) + n
    agg = {mid: ctxs for mid, ctxs in agg.items() if sum(v[0] for v in ctxs.values()) >= MIN_DROP_KILLS}
    if agg:
        days = sorted(d for d in days if d)
        lines.append("== %s ==" % _("Drops (monstros que você matou dando a maior parte do dano)"))
        if days:
            lines.append(_("Gravações de %s a %s. Só abates isolados (nenhum outro monstro morreu até 0,35 s antes ou "
                           "depois), para saber de quem caiu cada item. Cada linha: os bônus de drop ativos no abate, "
                           "os abates e quantos de cada item caíram (por abate).") % (days[0], days[-1]))
        for mid, ctxs in sorted(agg.items(), key=lambda kv: -sum(v[0] for v in kv[1].values())):
            lines.append("%s (%s): %d %s" % (_mob(mid), mid, sum(v[0] for v in ctxs.values()), _("abates")))
            for ctx, (k, items) in sorted(ctxs.items(), key=lambda kv: -kv[1][0]):
                its = ", ".join("%s (%s) %d = %s" % (meter.item_name(int(it)), it, n, dec("%.1f%%" % (100.0 * n / k)))
                                for it, n in sorted(items.items(), key=lambda kv: -kv[1]))
                lines.append("   %s · %d %s · %s" % (_ctx_text(ctx), k, _("abates"), its or _("nada caiu")))
        lines.append("")
    if len(lines) <= head:
        lines.append(_("Ainda não há nada aprendido: grave o farm (com uma subida de nível ou duas gravações seguidas) "
                       "e volte aqui."))
    lines.append(_("Para ajudar a melhorar o Replay Master: copie este texto e mande para quem desenvolve o "
                   "programa (ou para quem você quiser)."))
    data = data_lines(cfg, version, letters)
    if len(data) > 1:
        lines += ["", "== %s ==" % _("Dados (o mesmo conteúdo acima, para a ferramenta de quem desenvolve)"),
                  _("Uma linha por registro. As marcas (id, pc, cid) são sorteadas neste PC: só servem para não contar "
                    "duas vezes o que vier repetido em relatórios seguidos e não revelam nomes de arquivo nem de "
                    "personagem.")] + data
    return "\n".join(lines)


def _mark(secret, key):
    """Marca anônima de um registro: igual em relatórios seguidos do mesmo PC (para não contar duas vezes), mas não
    deixa descobrir o nome da gravação (o sorteio do PC entra na conta)."""
    return hashlib.sha1(("%s|%s" % (secret, key)).encode("utf-8")).hexdigest()[:12]


def data_lines(cfg, version, letters=None):
    """O bloco de dados: uma linha "RM|{json}" por registro, com o mesmo conteúdo das seções acima (personagens como
    letras, marcas anônimas no lugar dos nomes de gravação)."""
    lrn = (cfg or {}).get("xp_learn") or {}
    secret = lrn.get("secret")
    if not isinstance(secret, str) or not secret:
        # sem o sorteio, a marca de um nome de arquivo fácil de adivinhar (data e hora) daria para conferir
        secret = xp._learn(cfg)["secret"] if isinstance(cfg, dict) and cfg.get("xp_learn") else os.urandom(8).hex()
    letters = letters or _letters(lrn)

    def row(obj):
        return "RM|" + json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    out = [row(dict(t="report", v=version, fmt=FORMAT, date=datetime.date.today().isoformat(),
                    pc=_mark(secret, "pc"), folder=lrn.get("folder_read") or None))]
    for m in lrn.get("measures") or []:
        out.append(row(dict(t="m", id=_mark(secret, m.get("src")), date=(m.get("date") or "")[:10],
                            map=m.get("map"), mins=m.get("mins"), kills=m.get("kills"), ratio=m.get("ratio"),
                            gain=m.get("gain"),
                            char=letters.get(m.get("char"), "?"), cid=_mark(secret, "char|%s" % m.get("char"))[:8],
                            job=m.get("job"), level=m.get("level"), deaths=m.get("deaths"), insured=m.get("insured"),
                            quests=m.get("quests") or [], quest_at=m.get("quest_at") or [], edge=m.get("edge") or [],
                            bonus=m.get("bonus") or {}, mobs=m.get("mobs") or [],
                            shared=m.get("shared"), party=m.get("party"), spot_list=m.get("spot_list"))))
    for q in lrn.get("quests") or []:
        # mid: a marca da medida do mesmo trecho (a ferramenta não conta duas vezes)
        out.append(row(dict(t="q", id=_mark(secret, "%s|%s" % (q.get("src"), q.get("quest"))), quest=q.get("quest"),
                            mid=_mark(secret, q.get("src")), base=q.get("base"), level=q.get("level"),
                            mult=q.get("mult"), date=q.get("date"), known=q.get("known"),
                            partners=q.get("with") or [])))
    for rec, d in (lrn.get("drops") or {}).items():
        out.append(row(dict(t="d", id=_mark(secret, rec), date=d.get("date"), mobs=d.get("mobs") or {})))
    for mid, u in (lrn.get("unknown") or {}).items():
        out.append(row(dict(t="u", mob=mid, name=u.get("name"), maps=u.get("maps") or {}, last=u.get("last"),
                            recs={_mark(secret, r): n for r, n in (u.get("recs") or {}).items()})))
    for c in lrn.get("changes") or []:
        out.append(row(dict(t="c", **c)))
    for s in lrn.get("server") or []:
        out.append(row(dict(t="s", **s)))
    for job, levels in sorted(((cfg or {}).get("xp_levels") or {}).items()):
        for lv, val in levels.items():
            table = xp.table_need(int(job), int(lv))
            if table != val:
                out.append(row(dict(t="l", job=int(job), level=int(lv), game=val, table=table)))
    if lrn.get("names"):
        out.append(row(dict(t="n", names=lrn["names"])))
    return out
