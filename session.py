# -*- coding: utf-8 -*-
"""Resumo da sessão: o cartão que o widget mostra quando a gravação para, com as informações que a pessoa escolheu
na aba Cartões. As contas são as mesmas do widget e da análise (a XP da aba XP, o seu dano do ranking, os itens da aba
Drops), então o cartão bate com o que a pessoa viu durante a sessão.

A gravação parou quando o jogo solta o arquivo dela (o widget pergunta ao Windows quem está com o arquivo aberto),
quando o jogo é fechado ou quando começa outra gravação. Visto ao vivo (2026-11-19): o jogo segura o arquivo do replay
o tempo todo enquanto grava e solta quando a gravação para; então, com o jogo segurando, o arquivo parado não é fim
(personagem parado: o arquivo só cresce com o relógio, que o jogo pede ao servidor a cada 12 s; jogo travado: em 227
gravações, duas ficaram mais de 15 s sem nada, 15,6 s e 11 min 51 s, e o que o servidor mandou entrou de uma vez
depois). Só quando não dá para saber quem está com o arquivo vale a espera de SESSION_END_S sem crescer.
"""

import collections

from i18n import _

# (chave, nome na lista da aba Cartões), na ordem em que aparecem no cartão
FIELDS = [
    ("duration", "Duração e mapa"),
    ("xp", "XP ganha"),
    ("xp_hour", "XP por hora"),
    ("levels", "Níveis que subiu"),
    ("level_now", "Nível agora"),
    ("eta", "Tempo até o próximo nível"),
    ("kills", "Abates"),
    ("quests", "Missões entregues"),
    ("damage", "Seu dano e DPS"),
    ("max_hit", "Maior golpe"),
    ("bosses", "Chefes derrotados"),
    ("deaths", "Mortes"),
    ("picked", "Itens pegos"),
    ("favs", "Favoritos que caíram"),
    ("marked", "Itens marcados que caíram"),
    ("miracle", "Milagre"),
    ("used", "Itens usados"),
]
KEYS = [k for k, _n in FIELDS]
DEFAULT = ["duration", "xp", "levels", "kills", "deaths", "favs", "bosses"]
MIN_MS = 60000                # gravação de menos de 1 min só tem resumo se teve um destes acontecimentos:
SHORT_OK = ("card", "one_shot", "levelup", "boss")
SESSION_END_S = 15.0          # o arquivo parado há isso: a gravação acabou (o mesmo tempo do "Gravando" do rodapé)
GREEN, RED, WHITE, DIM, GOLD = "#4ade80", "#f87171", "#ffffff", "#a3a8b5", "#fbbf24"
PURPLE, TEAL, BLUE, PINK = "#c084fc", "#2dd4bf", "#60a5fa", "#f472b6"

# Destaques: o que a sessão teve de especial. O primeiro vira o título do cartão, com o emblema e uma animação curta
# dele (confete, moedinhas, estrelas, brilho, chuva); os outros viram selos embaixo. Cada um pode ser desligado na aba
# Cartões. Os limites saíram de 78 gravações de 10 min ou mais daqui: destaque é o que não acontece toda vez.
# (chave, nome na aba Cartões, quando aparece)
HIGHLIGHTS = [
    ("card", "Sorte grande", "Caiu uma carta (ou um item favorito) e você pegou"),
    ("one_shot", "One shot", "Derrubou um chefe com um golpe só"),
    ("levelup", "Subiu de nível", "Subiu um ou mais níveis na gravação"),
    ("record", "Recorde pessoal", "Bateu um recorde seu: o maior golpe do personagem, ou a XP por hora ou os abates "
                                  "por minuto num mapa"),
    ("untouchable", "Intocável", "Levou %d%% da vida em 10 s sem morrer, ou %d vezes a vida numa gravação sem "
                                 "nenhuma morte"),
    ("top_damage", "Maior DPS do grupo", "O seu DPS foi o maior do seu grupo (o mesmo DPS do widget)"),
    ("miracle", "Escravo do Milagre", "O Milagre veio %d vezes ou mais"),
    ("boss", "Caçador de chefes", "Derrotou um ou mais chefes"),
    ("close", "Quase lá", "Passou de %d%% do nível: falta pouco para subir"),
    ("top_hit", "Maior golpe do grupo", "O maior golpe da gravação no seu grupo foi seu"),
    ("kills", "Máquina de abates", "%d abates ou mais"),
    ("picked", "Bolsa cheia", "Pegou %d itens ou mais"),
    ("used", "Gastou bonito", "Usou %d itens ou mais"),
    ("long", "Maratona", "Gravação de %d h ou mais"),
    ("tough", "Sessão difícil", "%d mortes ou mais: um incentivo para a próxima"),
]
HL_KEYS = [k for k, _n, _w in HIGHLIGHTS]
HL_MIRACLES = 2               # Milagres para "Escravo do Milagre" (2 das 78 gravações)
HL_CLOSE_PCT = 85             # "Quase lá": passou disto do nível
HL_KILLS = 1000               # abates para "Máquina de abates"
HL_PICKED = 500               # itens pegos para "Bolsa cheia" (~15% das gravações)
HL_USED = 200                 # itens usados para "Gastou bonito" (~10%)
HL_LONG_H = 2                 # "Maratona" (horas)
HL_TOUGH = 5                  # mortes para o incentivo da "Sessão difícil"
# "Intocável": dano sofrido sem morrer, só em momentos bem incomuns (113 gravações de 5 min ou mais daqui: o pico em
# 10 s passou de 487% da vida em 5% delas; numa gravação inteira sem morte, 120 vidas ou mais em 4 de 67)
HL_TANK_BURST = 500           # % da vida máxima levado em HL_TANK_WINDOW_S, sem morrer nem logo depois
HL_TANK_WINDOW_S = 10
HL_TANK_LIVES = 120           # vezes a vida máxima, numa gravação sem nenhuma morte
HL_ARGS = {"miracle": HL_MIRACLES, "close": HL_CLOSE_PCT, "kills": HL_KILLS, "picked": HL_PICKED, "used": HL_USED,
           "long": HL_LONG_H, "tough": HL_TOUGH, "untouchable": (HL_TANK_BURST, HL_TANK_LIVES)}
RECORD_MIN = 10               # recordes de XP por hora e abates por minuto: com pelo menos isto de caça no mapa (min)
RECORD_KILLS = 50             # ...e pelo menos estes abates lá
MAIN_SHARE = 0.8              # o mapa da caça: com pelo menos isto dos abates (senão, só "e mais N mapas")
SALMON, ICE = "#ff8f7a", "#a5f3fc"   # golpes e dano; o "Intocável"
# o símbolo de cada destaque: no círculo à esquerda do título e no começo do selo
EMBLEMS = {"card": "✦", "one_shot": "✊", "levelup": "▲", "record": "✪", "untouchable": "◆", "top_damage": "♛",
           "miracle": "★", "boss": "♚", "close": "➚", "top_hit": "✸", "kills": "⚔", "picked": "⛁", "used": "⚗",
           "long": "⌛", "tough": "☁"}
# os títulos de cada destaque: um deles, sempre o mesmo para a mesma gravação
TITLES = {
    "card": ("Sorte grande!", "Que sorte!", "Olha a carta!"),
    "fav": ("Caiu um favorito!", "Sorte grande!"),
    "one_shot": ("ONE SHOT!", "Um golpe só!"),
    "levelup": ("Subiu de nível!", "Mais um nível!", "Level up!"),
    "levelups": ("Subiu %d níveis!", "%d níveis de uma vez!"),
    "record": ("Recorde pessoal!", "Novo recorde!"),
    "untouchable": ("Intocável!", "Inquebrável!", "Inabalável!"),
    "top_damage": ("Maior DPS do grupo!", "Carregou o grupo!", "Ninguém bateu mais!"),
    "miracle": ("Escravo do Milagre",),
    "boss": ("Chefe derrotado!", "Chefe no chão!"),
    "bosses": ("Caçador de chefes!", "Chefes no chão!"),
    "close": ("Quase lá!", "Falta pouco!", "Na reta final!"),
    "top_hit": ("Maior golpe do grupo!", "Golpe mais forte do grupo!"),
    "kills": ("Máquina de abates!", "Exterminador!"),
    "picked": ("Bolsa cheia!", "Chuva de itens!"),
    "used": ("Gastou bonito!", "Sem economia!"),
    "long": ("Maratona!", "Que fôlego!"),
    "tough": ("Sessão difícil", "Dia puxado"),
}
# a animação de cada um. Golpes e dano: a luva de boxe dando vários socos ("jabs") ou, num one shot, um soco só, muito
# forte ("one_punch"); "chase": Porings, Drops, Poporings e Marins fugindo de um jogador; "diamonds": o cartão
# translúcido do "Intocável"; moedinhas: ganhou (pegou muito) caem e se empilham, gastou (usou muito) caem do emblema
FX = {"card": "lucky", "one_shot": "asura", "levelup": "confetti", "record": "confetti", "untouchable": "diamonds",
      "top_damage": "combo", "miracle": "stars", "boss": "boss_down", "close": "glow", "top_hit": "heavy",
      "kills": "chase", "picked": "coins_stack", "used": "coins_down", "long": "glow", "tough": "rain"}
FX_KINDS = ("confetti", "coins_stack", "coins_down", "stars", "sparkle", "glow", "lucky", "flash", "rain", "jabs",
            "one_punch", "chase", "diamonds", "combo", "heavy", "asura", "boss_down")
# os cartões de dano são cenas de luta com os desenhos do jogo: "combo" (Maior DPS: uma sequência rápida de golpes, um
# monte de números), "heavy" (Maior golpe: um golpe carregado só, um número grande, o monstro cambaleia) e "asura" (one
# shot: carrega, avança, o monstro cai e a tela racha). "boss_down" (Chefe derrotado): a luta com o chefe da sessão,
# que cai no golpe final, e o confete. Quem luta é o personagem de quem grava se for de uma destas
# classes de punho (Monge, Mestre, Shura, Taekwon, Templário Estelar, Mestre Celestial e as versões baby e trans);
# senão, um Mestre (Champion) com soqueira.
FIST_JOBS = {15, 4016, 4030, 4070, 4077, 4102, 4046, 4047, 4048, 4239, 4241, 4243, 4244,
             4262, 4302, 4316}           # e as 4ªs: Inquisidor, Mestre Celestial (e a variante dele)


def chosen(cfg):
    """As informações escolhidas, na ordem do cartão."""
    want = cfg.get("session_fields")
    if not isinstance(want, list):
        want = DEFAULT
    return [k for k in KEYS if k in want]


def _names(rows, limit=3):
    """"Carta Stapo ×1, Jubileu ×13" (os primeiros `limit`; o resto vira "+N")."""
    parts = ["%s ×%d" % (name, n) for name, n in rows[:limit]]
    if len(rows) > limit:
        parts.append("+%d" % (len(rows) - limit))
    return ", ".join(parts)


def lines(c, cfg, favs=(), marked=(), skip=()):
    """[(texto, cor)] do resumo da gravação `c`: uma linha por informação escolhida que tem o que dizer (sem chefe
    derrotado, sem favorito que caiu... a linha não aparece). `favs` e `marked`: os itens favoritos e os marcados;
    `skip`: informações que o cartão mostra em outro lugar (a duração vai no subtítulo)."""
    import analysis as an
    import stats
    import xp
    from fmt import dec, dur, num
    keys = [k for k in chosen(cfg) if k not in skip]
    est = xp.estimate(c, cfg) if any(k in keys for k in ("xp", "xp_hour", "kills", "quests")) else None
    me = extra = None
    if any(k in keys for k in ("damage", "max_hit", "deaths")):
        rng, dur_ms = an.scope_range(c, None)
        me = next((p for p in an.players(c, rng, dur_ms) if p["me"]), None)
        extra = an.players_extra(c, rng).get(c.me) or {}
    drops = c.drop_summary() if any(k in keys for k in ("picked", "favs", "marked")) else []
    out = []
    for k in keys:
        if k == "duration":
            where = c.map or c.session.map
            out.append(((_("Gravação de %s em %s") % (dur(c.now), where)) if where else
                        _("Gravação de %s") % dur(c.now), WHITE))
        elif k == "xp" and est and est["xp"]:
            out.append(((_("XP: +%s do nível (%s)") % (dec("%.2f%%" % est["pct"]), num(est["xp"])))
                        if est["pct"] is not None else _("XP: +%s") % num(est["xp"]), WHITE))
        elif k == "xp_hour" and est and est["per_hour"]:
            out.append(((_("XP por hora: %s (%s)") % (dec("%.1f%%" % est["per_hour_pct"]), num(est["per_hour"])))
                        if est["per_hour_pct"] is not None else _("XP por hora: %s") % num(est["per_hour"]), DIM))
        elif k == "levels" and getattr(c, "level_ups", None):
            first, last = c.session.base_level, c.level_ups[-1][1]
            n = len(c.level_ups)
            out.append(((_("Subiu %d níveis: %d → %d") % (n, first, last)) if n > 1 else
                        _("Subiu de nível: %d → %d") % (first, last), GREEN))
        elif k == "level_now":
            pr = xp.progress(c, cfg)
            if pr and pr["pct"] is not None:
                out.append((_("Nível %d · %s") % (pr["level"], dec("%.1f%%" % min(99.9, pr["pct"]))), DIM))
        elif k == "eta":
            eta, _left = xp.time_to_level(c, cfg)
            if eta:
                out.append((_("Próximo nível: %s no ritmo da sessão") % xp.span_text(eta), DIM))
        elif k == "kills" and est and est["kills"]:
            per = est["kills_per_min"]
            out.append(((_("Abates: %d (%s por minuto)") % (est["kills"], dec("%.1f" % per))) if per is not None
                        else _("Abates: %d") % est["kills"], WHITE))
        elif k == "quests" and est and est["quests"]:
            out.append((_("Missões entregues: %d") % len(est["quests"]), DIM))
        elif k == "damage" and me and me["total"]:
            out.append((_("Seu dano: %s · DPS %s") % (num(me["total"]), num(me["dps"])), WHITE))
        elif k == "max_hit" and me and me["max_hit"]:
            out.append((_("Maior golpe: %s") % num(me["max_hit"]), DIM))
        elif k == "bosses":
            ends = getattr(c, "fight_ends", None) or {}
            seen = collections.Counter(c.name_of(key) for key, _t in ends.values())
            if seen:
                out.append((_("Chefes: %s") % _names(seen.most_common()), GOLD))
        elif k == "deaths":
            n = (extra or {}).get("deaths", 0)
            out.append((_("Mortes: %d") % n if n else _("Mortes: nenhuma"), RED if n else GREEN))
        elif k == "picked":
            got = [(r["name"], r["mine"]) for r in drops if r["mine"]]
            total = sum(n for _i, n in got)
            if len(got) > 1:
                out.append((_("Itens pegos: %d (%d diferentes)") % (total, len(got)), DIM))
            elif got:
                out.append((_("Itens pegos: %s") % _names(got), DIM))
        elif k == "favs":
            fav = set(favs)
            got = [(r["name"], r["mine"]) for r in drops if r["item"] in fav and r["mine"]]
            if got:
                out.append((_("Favoritos: %s") % _names(got), GOLD))
        elif k == "marked":
            mark = set(marked)
            got = [(r["name"], r["fell"] + r["mvp"]) for r in drops if r["item"] in mark and (r["fell"] or r["mvp"])]
            if got:
                out.append((_("Marcados que caíram: %s") % _names(got), GOLD))
        elif k == "miracle":
            n = len(getattr(c, "miracles", ()) or ())
            if n:
                out.append(((_("Milagre: %d vezes") % n) if n > 1 else _("Milagre: 1 vez"), GOLD))
        elif k == "used":
            used = stats.items_used(c)
            if used:
                out.append((_("Itens usados: %d (%s ×%d)") % (sum(u["n"] for u in used), used[0]["name"],
                                                               used[0]["n"]), DIM))
    return out


def hunt_maps(c):
    """[(mapa, abates lá)] da gravação, do mapa com mais abates para o com menos."""
    import bisect
    import xp
    spans = sorted(c.map_spans())
    starts = [st for st, _e, _m in spans]
    per = collections.Counter()
    for r in xp.kills(c)[0]:
        i = bisect.bisect_right(starts, r["t"]) - 1
        m = xp.map_key(spans[i][2]) if i >= 0 else xp.map_key(c.session.map)
        if m:
            per[m] += 1
    return per.most_common()


def place(mapname):
    """O mapa para o resumo: o código, como no /navi (ve_fild07); numa instância ou num mapa sem monstros na lista do
    jogo, o nome dele (Constellation Tower), se o jogo tiver."""
    import xp
    key = xp.map_key(mapname)
    if "@" in (mapname or "") or key not in xp.spawn_table():
        return xp.map_title(key) or key or mapname
    return key


def subtitle(c, cfg):
    """"1:12:40 caçando em ve_fild07" (a duração e o mapa da caça, o com mais abates; sem abates, o último), ou "" se
    a pessoa não escolheu essa informação."""
    from fmt import dur
    if "duration" not in chosen(cfg):
        return ""
    maps = [(m, n) for m, n in hunt_maps(c) if n >= 10]
    if maps:
        text = _("%s caçando em %s") % (dur(c.now), place(maps[0][0]))
        if len(maps) > 1:
            text += _(" e mais %d mapas") % (len(maps) - 1) if len(maps) > 2 else _(" e mais 1 mapa")
        return text
    where = place(c.map or c.session.map)
    return "%s · %s" % (dur(c.now), where) if where else dur(c.now)


def card(c, cfg, favs=(), marked=(), records=None):
    """Tudo o que o cartão mostra: dict(lines, hl (os destaques), sub (a duração e o mapa)). `records`: os recordes
    batidos nesta gravação (update_records; só o widget, no fim da gravação, guarda recordes)."""
    return dict(lines=lines(c, cfg, favs, marked, skip=("duration",)), hl=highlights(c, cfg, favs, records),
                sub=subtitle(c, cfg))


def sample_card(cfg):
    """O cartão de mentira da prévia da aba Cartões (sem gravação aberta)."""
    keys = chosen(cfg)
    return dict(lines=[ln for k, ln in zip(keys, sample_lines(cfg)) if k != "duration"],
                hl=sample_highlights(cfg),
                sub=(_("%s caçando em %s") % ("1:12:40", "ve_fild07")) if "duration" in keys else "")


def _demo():
    """{informação: (texto, cor)} de mentira, para a prévia e para a coluna Exemplo da aba Cartões."""
    return {
        "duration": (_("Gravação de %s em %s") % ("1:12:40", "ve_fild07"), WHITE),
        "xp": (_("XP: +%s do nível (%s)") % ("63,12%", "2,9M"), WHITE),
        "xp_hour": (_("XP por hora: %s (%s)") % ("52,1%", "2,4M"), DIM),
        "levels": (_("Subiu de nível: %d → %d") % (96, 97), GREEN),
        "level_now": (_("Nível %d · %s") % (97, "18,4%"), DIM),
        "eta": (_("Próximo nível: %s no ritmo da sessão") % "1 h 34 min", DIM),
        "kills": (_("Abates: %d (%s por minuto)") % (1180, "16,2"), WHITE),
        "quests": (_("Missões entregues: %d") % 4, DIM),
        "damage": (_("Seu dano: %s · DPS %s") % ("38,2M", "9,4K"), WHITE),
        "max_hit": (_("Maior golpe: %s") % "21,3K", DIM),
        "bosses": (_("Chefes: %s") % "Pharaoh ×1", GOLD),
        "deaths": (_("Mortes: nenhuma"), GREEN),
        "picked": (_("Itens pegos: %d (%d diferentes)") % (412, 17), DIM),
        "favs": (_("Favoritos: %s") % "Carta Stapo ×1, Jubileu ×38", GOLD),
        "marked": (_("Marcados que caíram: %s") % "Carta Stapo ×1", GOLD),
        "miracle": (_("Milagre: %d vezes") % 2, GOLD),
        "used": (_("Itens usados: %d (%s ×%d)") % (803, "Asas de Mosquito", 760), DIM),
    }


def sample_lines(cfg):
    """O resumo de mentira para a prévia da aba Cartões (sem replay aberto), com as informações escolhidas."""
    demo = _demo()
    return [demo[k] for k in chosen(cfg)]


def sample_texts():
    """{informação: texto de exemplo} (a duração mostra como fica no subtítulo)."""
    out = {k: text for k, (text, _c) in _demo().items()}
    out["duration"] = _("%s caçando em %s") % ("1:12:40", "ve_fild07")
    return out


def hl_chosen(cfg):
    """Os destaques ligados (todos, se a pessoa não mexeu)."""
    off = cfg.get("session_hl_off")
    off = set(off) if isinstance(off, list) else set()
    return [k for k in HL_KEYS if k not in off]


def hl_text(key):
    """(nome, quando aparece) de um destaque, no idioma da pessoa e com o limite dele."""
    for k, name, when in HIGHLIGHTS:
        if k == key:
            when = _(when)
            return _(name), (when % HL_ARGS[k]) if k in HL_ARGS else when
    return key, ""


def _seed(c):
    """A mesma semente para a mesma gravação: o título sorteado não muda se o resumo aparecer de novo."""
    import os
    return "%s|%s|%s" % (os.path.basename(getattr(c, "path", None) or ""), c.session.gid,
                         getattr(c.session, "recorded_at", ""))


def _title(seed, key, n=None):
    import random
    text = _(random.Random("%s|%s" % (seed, key)).choice(TITLES[key]))
    return text % n if n is not None else text


def _hl(key, title, chip, color, sub=None, bar=None, fx=None, tag=None, fight=None):
    """Um destaque. tag: o número que flutua ao lado do emblema na animação ("+1.412" itens pegos, "−268" usados).
    glass: o cartão fica translúcido (o "Intocável"). fight: a cena de luta dos cartões de dano (fight_of)."""
    return dict(key=key, title=title, chip=EMBLEMS.get(key, "✦") + " " + chip, color=color, emblem=EMBLEMS.get(key),
                fx=FX.get(key) if fx is None else fx, sub=sub, bar=bar, tag=tag, glass=key == "untouchable",
                fight=fight)


def one_shots(c):
    """Os abates de um golpe só de quem grava: [(dano, nome, chefe?, golpe)]. O monstro só levou aquele golpe, e o
    golpe foi do tamanho da vida dele na tabela (sem a vida na tabela, vale): assim o oponente do torneio, que some
    "morto" no fim do tempo com a vida de mentira de 2 bilhões, não conta."""
    import meter
    hits_on = collections.defaultdict(list)
    for h in c.hits:
        if h.out and h.dmg > 0:
            hits_on[h.dst_raw].append(h)
    alias = getattr(c, "alias", None) or {}
    bosses = {key for key, _t in (getattr(c, "fight_ends", None) or {}).values()}
    out = []
    for aid, t in c.deaths.items():
        hs = [h for h in hits_on.get(aid, ()) if h.t <= t]
        if len(hs) != 1 or hs[0].src != c.me:
            continue
        e = c.entities.get(aid)
        job = e.job if e is not None else None
        hp = (meter.MONSTERS.get(str(job)) or {}).get("hp") if job else None
        if hp and hs[0].dmg < hp:
            continue
        out.append((hs[0].dmg, c.name_of(aid), alias.get(aid, aid) in bosses, hs[0]))
    return out


def top_target(c):
    """O monstro (id) em que quem grava deu mais dano na gravação, ou None."""
    per = collections.Counter()
    for h in c.hits:
        if h.out and h.src == c.me and h.dmg > 0:
            e = c.entities.get(h.dst_raw)
            if e is not None and e.kind == "mob" and e.job:
                per[e.job] += h.dmg
    return per.most_common(1)[0][0] if per else None


def fight_of(c, hit=None, avg=None, mob=None):
    """O que a cena de luta de um cartão de dano mostra: dict(look (o visual de quem grava, se for de uma classe de
    punho; None = o Mestre), mob (o monstro: o dado, ou o em que quem grava mais bateu), hit (o maior golpe), avg (o
    golpe médio))."""
    sess = c.session
    look = dict(sess.look) if getattr(sess, "job", 0) in FIST_JOBS and getattr(sess, "look", None) else None
    return dict(look=look, mob=mob if mob is not None else top_target(c), hit=hit, avg=avg)


def _mob_of(c, h):
    e = c.entities.get(h.dst_raw) if h is not None else None
    return e.job if e is not None and e.kind == "mob" else None


def tank(c, window_s=HL_TANK_WINDOW_S):
    """O dano que quem grava levou: (o maior em `window_s` segundos sem morrer nem 5 s depois, em % da vida máxima;
    o total, em vidas; as mortes), ou None sem saber a vida máxima."""
    import statistics
    maxes = [m for _t, _h, m in (getattr(c, "hp_log", None) or {}).get(c.me, []) if m]
    life = statistics.median(maxes) if maxes else (getattr(c, "max_hp_seen", None) or {}).get(c.me)
    if not life:
        return None
    hits = sorted((h.t, h.dmg) for h in c.hits if not h.out and h.dst == c.me and h.dmg > 0)
    deaths = sorted(t for t, aid in c.death_log if aid == c.me)
    best = acc = 0
    j = 0
    win = window_s * 1000
    for t, d in hits:
        acc += d
        while hits[j][0] < t - win:
            acc -= hits[j][1]
            j += 1
        if not any(hits[j][0] <= dt <= t + 5000 for dt in deaths):
            best = max(best, acc)
    return 100.0 * best / life, sum(d for _t, d in hits) / float(life), len(deaths)


def _map_pace(c, cfg, mapname):
    """(XP por hora, abates por minuto) dos abates no mapa, pelo tempo de caça lá (as pausas longas ficam de fora),
    ou None com menos de RECORD_MIN de caça ou RECORD_KILLS abates."""
    import xp
    rows = xp.estimate(c, cfg)["rows"]
    total = active = 0.0
    n = 0
    spans = sorted(c.map_spans())
    for i, (st, en, m) in enumerate(spans):
        if xp.map_key(m) != mapname:
            continue
        en = min(en if en else c.now, spans[i + 1][0] if i + 1 < len(spans) else c.now, c.now)
        here = [r for r in rows if st <= r["t"] <= en]
        if not here or en - st < 60000:
            continue
        total += sum(r.get("total") or 0.0 for r in here)
        n += len(here)
        active += xp.active_ms(c, (st, en))
    if n < RECORD_KILLS or active < RECORD_MIN * 60000:
        return None
    return total * 3600000.0 / active, n * 60000.0 / active


def update_records(c, cfg):
    """Compara a gravação com os recordes do personagem e guarda os novos em cfg["session_records"]. Devolve os
    batidos: [(tipo "hit" | "xph" | "kpm", valor, o recorde de antes, mapa)]. A primeira gravação de um personagem (ou
    de um mapa) só marca o valor, sem festa. A mesma gravação contada de novo compara com o recorde de antes dela."""
    import analysis as an
    import os
    recs = cfg.setdefault("session_records", {})
    mine = recs.setdefault(str(c.session.gid or 0), {})
    me = os.path.basename(getattr(c, "path", None) or "") + "|%s" % (getattr(c.session, "recorded_at", ""),)
    found = []
    rng, dur_ms = an.scope_range(c, None)
    row = next((p for p in an.players(c, rng, dur_ms) if p["me"]), None)
    values = []
    if row and row["max_hit"]:
        values.append(("hit", "hit", float(row["max_hit"]), None))
    maps = hunt_maps(c)
    total = sum(n for _m, n in maps)
    if maps and total and maps[0][1] >= MAIN_SHARE * total:
        pace = _map_pace(c, cfg, maps[0][0])
        if pace:
            values += [("xph", "xph:" + maps[0][0], pace[0], maps[0][0]),
                       ("kpm", "kpm:" + maps[0][0], pace[1], maps[0][0])]
    for kind, key, value, where in values:
        old = mine.get(key)
        if not isinstance(old, dict):
            mine[key] = dict(v=value, by=me, prev=None)
            continue
        base = old.get("prev") if old.get("by") == me else old.get("v")
        if old.get("by") == me:
            old["v"] = max(value, old.get("v") or 0)
        elif value > (old.get("v") or 0):
            mine[key] = dict(v=value, by=me, prev=old.get("v"))
        if base is not None and value > base * 1.0001:
            found.append((kind, value, base, where))
    return found


def highlights(c, cfg, favs=(), records=None):
    """Os destaques da gravação `c`, do mais importante para o menos: [dict(key, title, chip, color, emblem, fx, sub,
    bar)]. title: o título do cartão quando é o primeiro; chip: o texto curto do selo; fx: a animação; sub: a frase
    dele; bar: o % do nível (a barra do "Quase lá"). `records`: os recordes batidos (update_records). Só os ligados na
    aba Cartões."""
    import analysis as an
    import itemkind
    import stats
    import xp
    from fmt import dec, dur, full, num
    want = set(hl_chosen(cfg))
    seed = _seed(c)
    got = {}
    drops = c.drop_summary() if want & {"card", "picked"} else []
    if "card" in want:
        fav = set(favs)
        mine = [r for r in drops if r["mine"]]
        lucky = [r for r in mine if itemkind.kind(r["item"], r["name"]) in ("card", "mvpcard")]
        favs_got = [r for r in mine if r["item"] in fav and r not in lucky]
        if lucky or favs_got:
            rows = lucky + favs_got
            more = (" +%d" % (sum(r["mine"] for r in rows) - 1)) if sum(r["mine"] for r in rows) > 1 else ""
            got["card"] = _hl("card", _title(seed, "card" if lucky else "fav"), rows[0]["name"] + more, GOLD,
                              sub=_("Caiu e você pegou: %s") % _names([(r["name"], r["mine"]) for r in rows], 2))
    shots = one_shots(c) if want & {"one_shot", "top_hit", "record"} else []
    boss_shots = sorted((x for x in shots if x[2]), key=lambda x: -x[0])
    if "one_shot" in want and boss_shots:
        dmg, name, _b, h1 = boss_shots[0]
        got["one_shot"] = _hl("one_shot", _title(seed, "one_shot"), _("%s com um golpe") % name, SALMON,
                              sub=_("%s caiu com um golpe só: %s") % (name, num(dmg)),
                              fight=fight_of(c, hit=dmg, mob=_mob_of(c, h1)))
    ups = getattr(c, "level_ups", None) or []
    if "levelup" in want and ups:
        first, last = c.session.base_level, ups[-1][1]
        got["levelup"] = _hl("levelup", _title(seed, "levelup") if len(ups) == 1 else _title(seed, "levelups", len(ups)),
                             "%d → %d" % (first, last), GREEN,
                             sub=_("Do nível %d ao %d em %s") % (first, last, dur(c.now)))
    if "record" in want and records:
        kind, value, before, where = records[0]
        if kind == "hit":
            chip, sub = _("recorde de golpe"), _("Seu maior golpe com este personagem: %s (antes, %s)") % (
                num(value), num(before))
        elif kind == "xph":
            chip, sub = _("recorde de XP/h"), _("Sua melhor XP por hora em %s: %s (antes, %s)") % (
                where, num(value), num(before))
        else:
            chip, sub = _("recorde de abates/min"), _("Seus abates por minuto em %s: %s (antes, %s)") % (
                where, dec("%.1f" % value), dec("%.1f" % before))
        if len(records) > 1:
            chip += " +%d" % (len(records) - 1)
        if kind == "hit":                       # recorde de golpe: salmão e o golpe carregado (Asura se foi um one shot)
            one = next((x for x in shots if x[0] >= value), None)
            got["record"] = _hl("record", _title(seed, "record"), chip, SALMON, sub=sub,
                                fx="asura" if one else "heavy",
                                fight=fight_of(c, hit=value, mob=_mob_of(c, one[3]) if one else None))
        else:
            got["record"] = _hl("record", _title(seed, "record"), chip, GOLD, sub=sub)
    if "untouchable" in want:
        tk_ = tank(c)
        if tk_ and (tk_[0] >= HL_TANK_BURST or (tk_[2] == 0 and tk_[1] >= HL_TANK_LIVES)):
            burst, lives, _deaths = tk_
            if burst >= HL_TANK_BURST:
                sub = _("Levou %s da sua vida em %d s e não caiu") % (dec("%.0f%%" % burst), HL_TANK_WINDOW_S)
                chip = _("%s da vida em %d s") % (dec("%.0f%%" % burst), HL_TANK_WINDOW_S)
            else:
                sub = _("Levou %s vezes a sua vida nesta gravação e não morreu nenhuma vez") % dec("%.0f" % lives)
                chip = _("%s vidas sem morrer") % dec("%.0f" % lives)
            got["untouchable"] = _hl("untouchable", _title(seed, "untouchable"), chip, ICE, sub=sub)
    if want & {"top_damage", "top_hit"}:
        rng, dur_ms = an.scope_range(c, None)
        grp = [r for r in an.players(c, rng, dur_ms) if (r["me"] or r["party"]) and r["total"] > 0]
        me = next((r for r in grp if r["me"]), None)
        if me is not None and len(grp) >= 2:
            others = [r for r in grp if not r["me"]]
            rate = "adps" if cfg.get("rate") == "active" else "dps"     # o mesmo DPS que o widget mostra
            if "top_damage" in want and me[rate] > max(r[rate] for r in others):
                landed = max(1, (me["hits"] or 0) - (me["misses"] or 0))
                got["top_damage"] = _hl("top_damage", _title(seed, "top_damage"), _("1º no DPS entre %d") % len(grp),
                                        SALMON, sub=_("DPS %s · %s do dano do grupo de %d") % (
                                            num(me[rate]),
                                            dec("%.0f%%" % (100 * me["total"] / float(sum(r["total"] for r in grp)))),
                                            len(grp)),
                                        fight=fight_of(c, hit=me["max_hit"], avg=me["total"] / float(landed)))
            if "top_hit" in want and me["max_hit"] > max(r["max_hit"] for r in others):
                one = next((x for x in shots if x[0] >= me["max_hit"]), None)
                got["top_hit"] = _hl("top_hit", _title(seed, "top_hit"), _("maior golpe: %s") % num(me["max_hit"]),
                                     SALMON, fx="asura" if one else "heavy",
                                     fight=fight_of(c, hit=me["max_hit"], mob=_mob_of(c, one[3]) if one else None),
                                     sub=(_("%s de um golpe só: %s nem viu") % (num(me["max_hit"]), one[1])) if one
                                     else _("%s: ninguém do grupo bateu mais forte") % num(me["max_hit"]))
    n = len(getattr(c, "miracles", ()) or ())
    if "miracle" in want and n >= HL_MIRACLES:
        got["miracle"] = _hl("miracle", _title(seed, "miracle"), _("%d Milagres") % n, PURPLE,
                             sub=_("O Milagre veio %d vezes nesta gravação") % n)
    if "boss" in want:
        ends = getattr(c, "fight_ends", None) or {}
        seen = collections.Counter(c.name_of(key) for key, _t in ends.values())
        if seen:
            total = sum(seen.values())
            last = max(ends.values(), key=lambda kt: kt[1])[0]          # a cena usa o último chefe derrotado
            e = c.entities.get(last)
            # os números da cena: o maior golpe e o golpe médio de quem grava nesse chefe (sem golpe dele, os do grupo)
            on = [h for h in c.hits if h.out and h.dmg > 0 and last in (h.dst, h.dst_raw)]
            dmg = [h.dmg for h in on if h.src == c.me] or [h.dmg for h in on]
            got["boss"] = _hl("boss", _title(seed, "bosses" if total > 1 else "boss"),
                              (_("%d chefes") % total) if total > 1 else seen.most_common(1)[0][0], GOLD,
                              sub=_names(seen.most_common()) if total > 1 else None,
                              fight=fight_of(c, hit=max(dmg) if dmg else None,
                                             avg=sum(dmg) / float(len(dmg)) if dmg else None,
                                             mob=e.job if e is not None else None))
    if "close" in want:
        pr = xp.progress(c, cfg)
        if pr and pr["pct"] is not None and HL_CLOSE_PCT <= pr["pct"] < 100:
            left = 100.0 - pr["pct"]
            eta, _rest = xp.time_to_level(c, cfg)
            sub = (_("Faltam só %s para o nível %d: uns %s no ritmo de hoje") % (dec("%.1f%%" % left), pr["level"] + 1,
                                                                               xp.span_text(eta))) if eta else \
                _("Faltam só %s para o nível %d") % (dec("%.1f%%" % left), pr["level"] + 1)
            got["close"] = _hl("close", _title(seed, "close"), _("faltam %s") % dec("%.1f%%" % left), TEAL, sub=sub,
                               bar=pr["pct"])
    if "kills" in want:
        est = xp.estimate(c, cfg)
        if est["kills"] >= HL_KILLS:
            per = est["kills_per_min"]
            got["kills"] = _hl("kills", _title(seed, "kills"), _("%s abates") % full(est["kills"]), BLUE,
                               sub=(_("%s por minuto, em média") % dec("%.1f" % per)) if per else None)
    if "picked" in want:
        picked = [(r["name"], r["mine"]) for r in drops if r["mine"]]
        total = sum(k for _n, k in picked)
        if total >= HL_PICKED:
            picked.sort(key=lambda x: -x[1])
            got["picked"] = _hl("picked", _title(seed, "picked"), _("%s itens pegos") % full(total), GOLD,
                                sub=_("Mais pegos: %s") % _names(picked, 2), tag="+" + full(total))
    if "used" in want:
        used = stats.items_used(c)
        total = sum(u["n"] for u in used)
        if total >= HL_USED:
            got["used"] = _hl("used", _title(seed, "used"), _("%s itens usados") % full(total), GOLD,
                              sub=_("Mais usados: %s") % _names([(u["name"], u["n"]) for u in used], 2),
                              tag="−" + full(total))
    deaths = None
    if "tough" in want:
        rng, _d = an.scope_range(c, None)
        deaths = (an.players_extra(c, rng).get(c.me) or {}).get("deaths", 0)
    if "long" in want and c.now >= HL_LONG_H * 3600000:
        got["long"] = _hl("long", _title(seed, "long"), dur(c.now), BLUE, sub=_("%s gravando") % dur(c.now))
    if "tough" in want and deaths is not None and deaths >= HL_TOUGH:
        got["tough"] = _hl("tough", _title(seed, "tough"), _("%d mortes") % deaths, BLUE,
                           sub=_("%d mortes, mas você seguiu até o fim. Na próxima vai!") % deaths)
    return [got[k] for k in HL_KEYS if k in got]


# a prévia de cada destaque na aba Cartões: a cena (monstro, maior golpe, golpe médio) dos que têm luta
SAMPLE_SCENES = {"one_shot": (1087, 86341920, 0), "top_damage": (1583, 11500000, 1250000),
                 "boss": (1312, 10200000, 900000), "top_hit": (1039, 86341920, 0)}
COLORS = {"card": GOLD, "one_shot": SALMON, "levelup": GREEN, "record": GOLD, "untouchable": ICE, "top_damage": SALMON,
          "miracle": PURPLE, "boss": GOLD, "close": TEAL, "top_hit": SALMON, "kills": BLUE, "picked": GOLD,
          "used": GOLD, "long": BLUE, "tough": BLUE}


def _sample_texts(key):
    """(título, selo, frase) de exemplo de um destaque, com as mesmas frases (traduzidas) do cartão de verdade; os
    monstros com o nome do jogo no idioma da pessoa (o Herói Orc da cena do one shot, o General Tartaruga)."""
    import meter
    orc = meter.monster_name(SAMPLE_SCENES["one_shot"][0]) or "Orc Hero"
    turtle = meter.monster_name(SAMPLE_SCENES["boss"][0]) or "General Tartaruga"
    return {
        "card": (_("Sorte grande!"), "Carta Sieglouse", _("Caiu e você pegou: %s") % "Carta Sieglouse ×1"),
        "one_shot": (_("ONE SHOT!"), _("%s com um golpe") % orc,
                     _("%s caiu com um golpe só: %s") % (orc, "86,3M")),
        "levelup": (_("Subiu de nível!"), "96 → 97", _("Do nível %d ao %d em %s") % (96, 97, "1:12:40")),
        "record": (_("Recorde pessoal!"), _("recorde de XP/h"),
                   _("Sua melhor XP por hora em %s: %s (antes, %s)") % ("ve_fild07", "2,41M", "2,02M")),
        "untouchable": (_("Intocável!"), _("%s da vida em %d s") % ("540%", HL_TANK_WINDOW_S),
                        _("Levou %s da sua vida em %d s e não caiu") % ("540%", HL_TANK_WINDOW_S)),
        "top_damage": (_("Maior DPS do grupo!"), _("1º no DPS entre %d") % 5,
                       _("DPS %s · %s do dano do grupo de %d") % ("1,01M", "38%", 5)),
        "miracle": (_("Escravo do Milagre"), _("%d Milagres") % 3, _("O Milagre veio %d vezes nesta gravação") % 3),
        "boss": (_("Chefe derrotado!"), turtle, None),
        "close": (_("Quase lá!"), _("faltam %s") % "7,4%",
                  _("Faltam só %s para o nível %d: uns %s no ritmo de hoje") % ("7,4%", 98, "12 min")),
        "top_hit": (_("Maior golpe do grupo!"), _("maior golpe: %s") % "86,3M",
                    _("%s: ninguém do grupo bateu mais forte") % "86,3M"),
        "kills": (_("Máquina de abates!"), _("%s abates") % "2.647", _("%s por minuto, em média") % "43,7"),
        "picked": (_("Bolsa cheia!"), _("%s itens pegos") % "2.728", _("Mais pegos: %s") % "Jubileu ×412, Carvão ×120"),
        "used": (_("Gastou bonito!"), _("%s itens usados") % "268",
                 _("Mais usados: %s") % "Poção Branca ×200, Asas de Mosquito ×60"),
        "long": (_("Que fôlego!"), "2:36:27", _("%s gravando") % "2:36:27"),
        "tough": (_("Sessão difícil"), _("%d mortes") % 7,
                  _("%d mortes, mas você seguiu até o fim. Na próxima vai!") % 7),
    }[key]


def sample_card_for(cfg, key, look=None):
    """O cartão de exemplo com o destaque `key` como título, para ver a animação dele na prévia da aba Cartões.
    look: o visual de quem grava (a gravação aberta), para a cena de luta usar o personagem dele."""
    title, chip, sub = _sample_texts(key)
    scene = SAMPLE_SCENES.get(key)
    tag = {"picked": "+2.728", "used": "−268"}.get(key)
    fight = dict(look=look, mob=scene[0], hit=scene[1], avg=scene[2] or None) if scene else None
    main = _hl(key, title, chip, COLORS[key], sub=sub, tag=tag, fight=fight, bar=92.6 if key == "close" else None)
    card = sample_card(cfg)
    card["hl"] = [main] + [h for h in card["hl"] if h["key"] != key][:2]
    return card


def sample_highlights(cfg):
    """Os destaques de mentira da prévia: Subiu de nível, Milagre, Recorde e Bolsa cheia (só os ligados)."""
    demo = {
        "levelup": _hl("levelup", _("Subiu de nível!"), "96 → 97", GREEN, sub=_("Do nível %d ao %d em %s") % (
            96, 97, "1:12:40")),
        "miracle": _hl("miracle", _("Escravo do Milagre"), _("%d Milagres") % 3, PURPLE,
                       sub=_("O Milagre veio %d vezes nesta gravação") % 3),
        "record": _hl("record", _("Recorde pessoal!"), _("recorde de XP/h"), GOLD),
        "picked": _hl("picked", _("Bolsa cheia!"), _("%s itens pegos") % "1.412", GOLD, tag="+1.412"),
        "untouchable": _hl("untouchable", _("Intocável!"), _("%s da vida em %d s") % ("540%", HL_TANK_WINDOW_S), ICE),
    }
    return [demo[k] for k in hl_chosen(cfg) if k in demo]
