# -*- coding: utf-8 -*-
"""Gerenciador de cartões: o que o widget mostra por cima das linhas.

Duas listas:
  * os cartões do programa (resumo da morte, avisos do chefe, resumo da luta, item marcado, Milagre e os avisos do
    rodapé): continuam ligados por padrão, e cada um tem a sua caixa para desligar;
  * os efeitos que a pessoa escolheu acompanhar (qualquer buff, debuff ou efeito de chão): enquanto um deles está
    ativo, o widget mostra um contador no pé das linhas, com o tempo que falta quando o jogo manda a duração (os
    debuffs no chefe vêm com ela: Garra Sombria 20 s, Cometa 20 s, Pólen 30 s...) ou há quanto tempo está ativo
    quando não manda. Quando acaba, o contador pisca "acabou" por alguns segundos.

Só acompanha o que foi escolhido: sem nada na lista, nada é olhado a cada leitura.
"""

import clientdata
import i18n
import itemping
import meter
import sounds as sndlib
from i18n import _

# cartões do programa: (chave, nome, o que é, chave da configuração que liga/desliga ou None = lista cards_off)
SYSTEM = [
    ("death", "Resumo da morte", "Quando você morre: o golpe que matou e o que veio antes, por 10 s", "death_card"),
    ("boss_element", "Chefe trocou de propriedade ou ficou imune", "Com o que bater e o que evitar, por 5 s", None),
    ("boss_size", "Chefe mudou de tamanho", "O tamanho novo e o de antes, por 5 s", None),
    ("maxpain", "Dor Máxima ligou ou acabou", "Segurar os golpes grandes enquanto ela devolve dano", None),
    ("defense", "Modo defesa (Aquila)", "O dano quase não entra até a defesa cair", None),
    ("relief", "Aliviar muito alto (Betelgeuse)", "Almas ativas e a redução de dano do chefe", None),
    ("def_break", "A defesa caiu (Aquila)", "5 s de dano total", None),
    ("summary", "Resumo da luta contra chefe", "No fim da luta: tempo, sua parte do dano e o Dedo Duro", "fight_summary"),
    ("ping", "Item marcado caiu", "O cartão com o mapa e as coordenadas (o som é à parte)", None),
    ("miracle", "Milagre Solar, Lunar e Estelar", "A faixa dourada quando o Milagre ativa", "alert_miracle"),
    ("buff_end", "Buff importante acabou", "Aviso no rodapé, no meio da luta", "alert_buffs"),
    ("death_foot", "Morte com overkill", "Aviso no rodapé", "alert_death"),
    ("fusion", "HP baixo com a União", "Aviso no rodapé (Mestre Taekwon)", "alert_fusion"),
    ("rec", "Jogo aberto sem gravar", "Lembrete no rodapé", "alert_rec"),
]
BOSS_KEYS = ("boss_element", "boss_size", "maxpain", "defense", "relief", "def_break")   # dependem de alert_boss
MECH_KEY = {"maxpain_on": "maxpain", "maxpain_off": "maxpain", "defense": "defense", "relief": "relief",
            "def_break": "def_break"}
GROUPS = ["Debuff no alvo", "Buff de grupo", "Buff de classe e outros", "Consumível", "Efeito de chão"]
KIND_GROUP = {"Grupo/suporte": "Buff de grupo", "Consumível": "Consumível"}
SUGGESTED = [730, 1142, 1183, 22, 1402]       # Garra Sombria, Cometa, Pólen, Lex Aeterna, Avanço Sísmico
NO_TIMER = (9999,)            # "falta 9999 ms": o jogo não diz quanto falta
OVERDUE_MS = 1500             # contador vencido há mais que isso sem o fim ter chegado (alvo fora da tela): some
FLASH_S = 3.0                 # o "acabou" fica esse tempo
ROW_CHOICES = (2, 3, 4, 5, 6)
# como um efeito acompanhado aparece no widget; "pin" (fixado na faixa fixa) fica guardado na lista de fixados
SHOWS = ("counter", "pin", "card")
SHOW_TEXT = {"counter": "contador", "pin": "faixa fixa", "card": "cartão"}
DEFAULT_ROWS = 4
MAX_TRACKED = 30
# som de cada efeito acompanhado: quando toca. None = o padrão da aba ("Som quando acabar")
SOUNDS = ("off", "start", "end", "before")
SOUND_TEXT = {"off": "sem som", "start": "ao começar", "end": "ao acabar", "before": "antes de acabar"}
BEFORE_CHOICES = (1, 2, 3, 5, 10, 15, 30)       # "antes de acabar": quantos segundos antes
DEFAULT_BEFORE = 3
DEFAULT_TONE = "agudo"                          # os tons são os do aviso de item (itemping.TONES)
# temporizador: a duração que a pessoa escolhe (s); 0 = a do jogo
TIMER_CHOICES = (5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 300, 600)
MAX_TIMER_S = 3600
SOUND_GAP_S = 0.6             # dois sons seguidos ficam pelo menos isso separados (vários efeitos ao mesmo tempo)


# ------------------------------------------------------------------ cartões do programa

def enabled(cfg, key):
    """Este cartão do programa está ligado?"""
    spec = next((s for s in SYSTEM if s[0] == key), None)
    if spec is None:
        return True
    if spec[3]:
        return bool(cfg.get(spec[3], True))
    if key in BOSS_KEYS and not cfg.get("alert_boss", True):
        return False
    return key not in (cfg.get("cards_off") or [])


def set_enabled(cfg, key, on):
    """Liga ou desliga um cartão do programa."""
    spec = next((s for s in SYSTEM if s[0] == key), None)
    if spec is None:
        return
    if spec[3]:
        cfg[spec[3]] = bool(on)
        return
    off = [k for k in (cfg.get("cards_off") or []) if k != key]
    if key in BOSS_KEYS:
        if on and not cfg.get("alert_boss", True):
            # os avisos do chefe estavam todos desligados pelo menu: liga só este
            cfg["alert_boss"] = True
            off = [k for k in off if k not in BOSS_KEYS] + [k for k in BOSS_KEYS if k != key]
    if not on:
        off.append(key)
    cfg["cards_off"] = off
    if all(k in off for k in BOSS_KEYS):
        cfg["alert_boss"] = False
        cfg["cards_off"] = [k for k in off if k not in BOSS_KEYS]


def boss_card_key(info):
    """De que tipo é um aviso do chefe (para a caixa dele no gerenciador)."""
    if info.get("mech"):
        return MECH_KEY.get(info["mech"], "maxpain")
    if info.get("immune") or info.get("element"):
        return "boss_element"
    return "boss_size"


# ------------------------------------------------------------------ efeitos para acompanhar

_CAT = {}


def catalog():
    """Tudo que dá para acompanhar: [dict(kind "status" | "area", id, ids, name, group, norm)], sem os status de
    sistema e de serviço. Status diferentes com o mesmo nome (níveis, versões) viram uma entrada só."""
    key = (i18n.LANG, clientdata.NAMES.version)
    if _CAT.get("key") == key:
        return _CAT["rows"]
    merged = {}
    for k in meter.EFST:
        try:
            efst = int(k)
        except ValueError:
            continue
        kind = meter.status_kind(efst)
        if kind in ("Sistema", "Serviço"):
            continue
        name = meter.status_name(efst)
        if not name or name.startswith("Status ") or (kind == "Outro" and efst not in meter.MOB_DEBUFFS):
            continue
        if not _named(efst):
            continue                               # só o código interno ("Abyss 002"): ninguém procura por isso
        group = "Debuff no alvo" if efst in meter.MOB_DEBUFFS else KIND_GROUP.get(kind, "Buff de classe e outros")
        row = merged.get((name, group))
        if row is None:
            merged[(name, group)] = dict(kind="status", id=efst, ids=[efst], name=name, group=group,
                                         norm=itemping.norm(name))
        else:
            row["ids"].append(efst)
            if efst in SUGGESTED:
                row["id"] = efst
    rows = sorted(merged.values(), key=lambda r: (GROUPS.index(r["group"]), r["norm"]))
    for skill in sorted(set(meter.AREA_SKILLS.values())):
        name = meter.skill_name(skill)
        rows.append(dict(kind="area", id=skill, ids=[skill], name=name, group="Efeito de chão",
                         norm=itemping.norm(name)))
    _CAT.update(key=key, rows=rows, by={(r["kind"], i): r for r in rows for i in r["ids"]})
    return rows


def _named(efst):
    """O status tem nome de verdade (na base em português ou no jogo instalado), não só o código interno?"""
    if efst in meter.MOB_DEBUFFS or meter._pt_has_name(efst):
        return True
    name = clientdata.NAMES.game_name("status", efst)
    return bool(name) and "%" not in name and not name.isupper()


def short_name(name):
    """"Cometa (Vício Mágico)" -> "Cometa" (para os botões de sugestão)."""
    return name.split(" (")[0]


def entry(kind, ident):
    """A entrada do catálogo de um efeito (por qualquer um dos ids dela), ou None."""
    catalog()
    return _CAT["by"].get((kind, ident))


def search(query, group=None, limit=200):
    """Efeitos cujo nome contém todas as palavras digitadas (sem acento, maiúsculas ou ordem)."""
    words = itemping.norm(query).split()
    out = []
    for r in catalog():
        if group and r["group"] != group:
            continue
        if all(w in r["norm"] for w in words):
            out.append(r)
            if len(out) >= limit:
                break
    return out


def default_where(kind, ident):
    """Onde olhar um efeito por padrão: os debuffs, no alvo; o resto, em quem grava."""
    return "target" if kind == "status" and ident in meter.MOB_DEBUFFS else ("any" if kind == "area" else "me")


def _int(v, lo, hi, default):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return v if lo <= v <= hi else default


def tracked(cfg):
    """Os efeitos acompanhados: [dict(kind, id, where, show, sound, before, snd, tone, secs)], só os válidos.
    `show`: "counter" (contador no pé das linhas) ou "card" (cartão enquanto durar); o fixado na faixa fixa é outra
    lista (os fixados do widget). `sound`: quando tocar (SOUNDS) ou None = o padrão da aba; `before`: segundos antes
    de acabar; `snd`: qual som (sounds.KEYS); `tone`: o tom; `secs`: o temporizador escolhido (0 = a do jogo)."""
    out, seen = [], set()
    tones = {name for name, _hz in itemping.TONES}
    for t in cfg.get("trackers") or []:
        try:
            kind, ident = t["kind"], int(t["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if kind not in ("status", "area") or (kind, ident) in seen:
            continue
        seen.add((kind, ident))
        where = t.get("where") if t.get("where") in ("me", "target", "any") else default_where(kind, ident)
        out.append(dict(kind=kind, id=ident, where=where, show="card" if t.get("show") == "card" else "counter",
                        sound=t.get("sound") if t.get("sound") in SOUNDS else None,
                        before=_int(t.get("before"), 1, 600, DEFAULT_BEFORE),
                        snd=t.get("snd") if t.get("snd") in sndlib.KEYS else sndlib.DEFAULT,
                        tone=t.get("tone") if t.get("tone") in tones else DEFAULT_TONE,
                        secs=_int(t.get("secs"), 0, MAX_TIMER_S, 0)))
    return out[:MAX_TRACKED]


def sound_of(cfg, t):
    """Quando o efeito toca som: o escolhido nele ou, sem escolha, o padrão da aba ("Som quando acabar")."""
    if t.get("sound"):
        return t["sound"]
    return "end" if cfg.get("tracker_sound") else "off"


def sound_text(cfg, t):
    """O som do efeito em palavras: "ao acabar", "3 s antes de acabar", "sem som"."""
    mode = sound_of(cfg, t)
    if mode == "before":
        return _("%d s antes de acabar") % t["before"]
    return _(SOUND_TEXT[mode])


def timer_text(t):
    """O temporizador em palavras: "do jogo", "20 s", "1:30"."""
    s = t.get("secs") or 0
    if not s:
        return _("do jogo")
    return "%d s" % s if s < 60 else ("%d:%02d" % divmod(s, 60))


def is_tracked(cfg, kind, ident):
    e = entry(kind, ident)
    ids = set(e["ids"]) if e else {ident}
    return any(t["kind"] == kind and t["id"] in ids for t in tracked(cfg))


_KEEP = object()


def track(cfg, kind, ident, on=True, where=None, show=None, sound=_KEEP, before=None, tone=None, secs=None,
          snd=None):
    """Põe ou tira um efeito da lista (ou troca onde olhar / como aparece / o som / o temporizador de um que já
    está, sem tirá-lo do lugar). `sound` None volta ao padrão da aba. Devolve True se mudou."""
    e = entry(kind, ident)
    ids = set(e["ids"]) if e else {ident}
    cur = tracked(cfg)
    same = lambda t: t["kind"] == kind and t["id"] in ids          # noqa: E731
    old = next((t for t in cur if same(t)), None) or {}
    if not on:
        new = [t for t in cur if not same(t)]
    else:
        item = dict(kind=kind, id=(e["id"] if e else ident),
                    where=where or old.get("where") or default_where(kind, ident),
                    show=show if show in ("counter", "card") else old.get("show", "counter"),
                    sound=(sound if sound in SOUNDS else None) if sound is not _KEEP else old.get("sound"),
                    before=_int(before, 1, 600, DEFAULT_BEFORE) if before is not None else old.get("before",
                                                                                                  DEFAULT_BEFORE),
                    snd=snd if snd in sndlib.KEYS else old.get("snd", sndlib.DEFAULT),
                    tone=tone if tone in {n for n, _h in itemping.TONES} else old.get("tone", DEFAULT_TONE),
                    secs=_int(secs, 0, MAX_TIMER_S, 0) if secs is not None else old.get("secs", 0))
        new = [item if same(t) else t for t in cur] if old else cur + [item]
    if new == cur:
        return False
    cfg["trackers"] = new[:MAX_TRACKED]
    return True


def name_of(t):
    e = entry(t["kind"], t["id"])
    if e:
        return e["name"]
    return meter.skill_name(t["id"]) if t["kind"] == "area" else meter.status_name(t["id"])


def where_text(t):
    return {"me": _("em mim"), "target": _("no alvo"), "any": _("de qualquer um")}[t["where"]]


# ------------------------------------------------------------------ o que está ativo agora

def live(c, trackers):
    """Os efeitos acompanhados que estão ativos agora: [dict(key, name, where, target (nome ou None), left (ms que
    faltam ou None), total (ms ou None), since (ms ativo))], o que acaba antes primeiro. Um por efeito: no alvo
    vale o chefe (ou, sem chefe, o que tem mais tempo pela frente)."""
    if not trackers:
        return []
    want = {}
    areas = {}
    for t in trackers:
        e = entry(t["kind"], t["id"])
        ids = e["ids"] if e else [t["id"]]
        for i in ids:
            (areas if t["kind"] == "area" else want)[i] = t
    best = {}
    if want:
        seen_at = getattr(c, "status_seen", {})
        for (aid, efst), (start, total, left) in c.status_on.items():
            t = want.get(efst)
            if t is None:
                continue
            mine = aid == c.me
            if t["where"] == "me" and not mine:
                continue
            if t["where"] == "target" and (mine or c.is_friendly(aid)):
                continue
            rem = None
            if t.get("secs"):                      # o temporizador escolhido vale no lugar da duração do jogo
                total = left = t["secs"] * 1000
                rem = max(0, left - (c.now - start))
            elif left and left not in NO_TIMER:
                rem = left - (c.now - seen_at.get((aid, efst), start))
                if rem < -OVERDUE_MS:
                    continue                       # o fim não chegou (o alvo saiu da tela): não fica vencido na tela
                rem = max(0, rem)
            boss = (not mine) and c.is_mvp(aid)
            e = None if mine else c.entities.get(aid)
            mob = None                                 # o monstro em que o efeito está (o desenho do cartão)
            if e is not None and e.kind == "mob":
                log = c.sprite_log.get(aid)
                mob = log[-1][1] if log else e.job
            row = dict(key="status:%d" % t["id"], name=name_of(t), where=t["where"],
                       target=None if mine else c.name_of(aid), left=rem, total=(total or left) if rem is not None else None,
                       since=c.now - start, boss=boss, mob=mob)
            old = best.get(row["key"])
            if old is None or (boss, rem if rem is not None else 0) > (old["boss"], old["left"] if old["left"] is not None else 0):
                best[row["key"]] = row
    if areas:
        for a in reversed(getattr(c, "areas", ())):
            t = areas.get(a["skill"])
            if t is None or not any(u[1] is None for u in a["units"]):
                continue
            if t["where"] == "me" and a["src"] != c.me:
                continue
            key = "area:%d" % t["id"]
            if key not in best:
                secs = t.get("secs") or 0
                best[key] = dict(key=key, name=name_of(t), where=t["where"],
                                 target=None if a["src"] == c.me else c.name_of(a["src"]),
                                 left=max(0, secs * 1000 - (c.now - a["t"])) if secs else None,
                                 total=secs * 1000 if secs else None,
                                 since=c.now - a["t"], boss=False, mob=None)
    return sorted(best.values(), key=lambda r: (r["left"] is None, r["left"] if r["left"] is not None else -r["since"]))


class Watch:
    """Lembra o que estava ativo na leitura anterior, para o "acabou" piscar por FLASH_S."""

    def __init__(self):
        self.prev = {}
        self.gone = {}                # chave -> (linha, quando acabou)
        self.started = []             # as que começaram na última leitura (a primeira leitura não conta)
        self.fresh = True

    def reset(self):
        self.prev, self.gone, self.started, self.fresh = {}, {}, [], True

    def update(self, rows, now, flash=True):
        """(linhas para desenhar, as que acabaram agora). As que acabaram entram no fim, com `ended` = há quantos
        segundos."""
        cur = {r["key"]: r for r in rows}
        ended = [r for k, r in self.prev.items() if k not in cur]
        # as que começaram agora; na primeira leitura (replay aberto no meio) o que já estava ativo não conta
        self.started = [] if self.fresh else [r for k, r in cur.items() if k not in self.prev]
        self.crossed = [r for k, r in cur.items() if k in self.prev]      # para o "antes de acabar"
        self.fresh = False
        for r in ended:
            self.gone[r["key"]] = (r, now)
        for k in cur:
            self.gone.pop(k, None)
        self.prev = cur
        self.gone = {k: v for k, v in self.gone.items() if now - v[1] < FLASH_S}
        out = list(rows)
        if flash:
            out += [dict(r, ended=now - when) for r, when in self.gone.values()]
        return out, ended


def voice(t):
    """(som, tom) de um efeito acompanhado."""
    return t.get("snd") or sndlib.DEFAULT, t.get("tone") or DEFAULT_TONE


def sounds(cfg, trackers, watch, ended, prev_left):
    """Os sons a tocar nesta leitura: [(som, tom)], um por efeito que pediu som e passou do ponto agora (começou,
    acabou, ou cruzou "N s antes de acabar"); None = o bipe de sempre (efeito sem som próprio, padrão da aba).
    `prev_left`: {chave: ms que faltavam na leitura anterior}, que esta função atualiza."""
    by_key = {"%s:%d" % (t["kind"], t["id"]): t for t in trackers}
    out = []
    for r in watch.started:
        t = by_key.get(r["key"])
        if t and sound_of(cfg, t) == "start":
            out.append(voice(t))
    for r in ended:
        t = by_key.get(r["key"])
        if t and sound_of(cfg, t) == "end":
            out.append(voice(t) if t.get("sound") else None)      # o padrão da aba toca o bipe de sempre
    for r in getattr(watch, "crossed", ()) + watch.started:
        t = by_key.get(r["key"])
        left = r.get("left")
        if t is None or left is None or sound_of(cfg, t) != "before":
            continue
        mark = t["before"] * 1000
        before = prev_left.get(r["key"])
        if left <= mark and (before is None and r in watch.started and left > 0 or before is not None and before > mark):
            out.append(voice(t))
    for k in [k for k in prev_left if k not in {r["key"] for r in watch.crossed + watch.started}]:
        del prev_left[k]
    for r in watch.crossed + watch.started:
        prev_left[r["key"]] = r.get("left")
    return out


def time_text(row):
    """O texto do contador: "12 s", "4,2 s" nos últimos segundos, "1:05"; sem duração, há quanto tempo está ativo."""
    from fmt import dec
    if row.get("ended") is not None:
        return _("acabou")
    left = row.get("left")
    if left is None:
        s = int(row["since"] // 1000)
        return _("há %d s") % s if s < 60 else _("há %d:%02d") % divmod(s, 60)
    if left < 10000:
        return dec("%.1f s" % (left / 1000.0))
    s = int(round(left / 1000.0))
    return "%d s" % s if s < 60 else "%d:%02d" % divmod(s, 60)
