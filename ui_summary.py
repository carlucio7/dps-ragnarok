# -*- coding: utf-8 -*-
"""Aba Resumo da análise: o recorte inteiro de relance, para quem gravou. Em cima os números do dano; depois a
sobrevivência e o ritmo (ASPD, conjuração, itens usados), a XP e os drops; as lutas contra chefe do recorte; e,
embaixo, os maiores golpes, o dano recebido e os itens usados. Cada bloco resume uma aba: os detalhes estão nela.
"""

import bisect
import collections
import tkinter as tk

import analysis as an
import dedoduro as dd
import meter
import stats
import ui_parts
import xp
from analysis_ui import ScrollFrame, Table, Tiles, _fmt
from fmt import dec, dur, full, num
from i18n import _

BOSS_ROWS = 12                # lutas contra chefe mostradas (as de mais dano)


class SummaryTab:
    def __init__(self, win, nb):
        self.win = win
        c = win.c
        outer = tk.Frame(nb, bg=c["panel"])
        nb.add(outer, text=_("Resumo"))
        tab = ScrollFrame(outer, win).inner
        self.title = win.section(tab, "")
        self.sub = win.label(tab, "", "small", "muted", "panel", anchor="w", justify="left")
        self.sub.pack(fill="x", padx=10, pady=(0, 6))

        def head(text):
            win.label(tab, text.upper(), "small", "muted", "panel", anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        head(_("Seu dano"))
        self.dmg = Tiles(tab, win, [
            ("dealt", _("Seu dano")), ("dps", _("Seu DPS (em combate)")), ("adps", _("Seu DPS ativo")),
            ("eff", _("DPS do 1º ao último golpe")), ("hits", _("Acertos")), ("rate", _("Golpes por segundo")),
            ("best", _("Maior golpe")), ("top", _("Skill mais usada"))], min_w=165, dense=True)
        self.dmg.pack(fill="x", padx=10)
        head(_("Sobrevivência e ritmo"))
        self.life = Tiles(tab, win, [
            ("taken", _("Dano recebido")), ("deaths", _("Mortes")), ("kills", _("Abates (golpe fatal)")),
            ("items", _("Itens usados")), ("aspd", "ASPD"), ("cast", _("Conjuração")),
            ("post", _("Pós-conjuração")), ("blocked", _("Skill em recarga"))], min_w=165, dense=True)
        self.life.pack(fill="x", padx=10)
        head(_("XP e drops"))
        self.gain = Tiles(tab, win, [
            ("xp", _("XP estimada")), ("hour", _("XP por hora")), ("level", _("Nível")), ("mobs", _("Abates do grupo")),
            ("drops", _("Itens pegos")), ("mvp", _("Prêmios de MVP"))], min_w=165, dense=True)
        self.gain.pack(fill="x", padx=10)
        self.boss_lbl = win.section(tab, _("Chefes do recorte"))
        self.t_boss = Table(tab, win, [
            ("name", _("Chefe"), 200, "w", "text"), ("when", _("Quando"), 70, "e", "dur"),
            ("end_txt", _("Resultado"), 150, "w", "text"), ("total", _("Dano do grupo"), 125, "e", "big"),
            ("mine", _("Seu dano"), 120, "e", "big"), ("share", _("Sua parte"), 80, "e", "pct"),
            ("my_dps", _("Seu DPS"), 110, "e", "big"), ("deaths", _("Mortes do grupo"), 110, "e", "int")], height=4)
        self.t_boss.pack(fill="x", padx=6)
        both = tk.Frame(tab, bg=c["panel"])
        both.pack(fill="both", expand=True, padx=4, pady=(4, 8))
        for col in range(3):
            both.columnconfigure(col, weight=1, uniform="r")
        cols = [tk.Frame(both, bg=c["panel"]) for _i in range(3)]
        for i, f in enumerate(cols):
            f.grid(row=0, column=i, sticky="nsew")
        win.section(cols[0], _("Seus maiores golpes"))
        self.t_tophits = Table(cols[0], win, [
            ("t", _("Tempo"), 50, "e", "dur"), ("name", _("Habilidade"), 120, "w", "text"),
            ("target", _("Alvo"), 100, "w", "text"), ("dmg", _("Dano"), 95, "e", "big")], height=8)
        self.t_tophits.pack(fill="both", expand=True, padx=6)
        win.section(cols[1], _("Dano recebido"))
        self.t_taken = Table(cols[1], win, [
            ("source", _("Fonte"), 110, "w", "text"), ("name", _("Habilidade"), 110, "w", "text"),
            ("hits", _("Acertos"), 55, "e", "int"), ("total", _("Dano"), 90, "e", "big")], height=8)
        self.t_taken.pack(fill="both", expand=True, padx=6)
        win.section(cols[2], _("Itens usados"))
        self.t_items = Table(cols[2], win, [("name", _("Item"), 220, "w", "text"), ("n", _("Vezes"), 60, "e", "int")],
                             height=8)
        self.t_items.pack(fill="both", expand=True, padx=6)
        ui_parts.follow_wrap(tab, self.sub, 24, 200)
        self.cache = (None, None)
        self.sum_cache = (None, None, None, None)
        self.fight_cache = (None, [], 0, None)

    def fights(self, c, rng):
        """As lutas contra chefe do recorte (guardadas enquanto o replay não muda): os MVPs, ou, sem nenhum, os
        chefes menores; no máximo BOSS_ROWS, as de mais dano, na ordem em que aconteceram. Num mapa cheio de
        monstros com vida de chefe (Torre do Relógio) são centenas."""
        sig = (id(c), c.version, rng)
        if self.fight_cache[0] != sig:
            fights = [f for f in dd.boss_fights(c, rng) if not f["dummy"]]
            fights = [f for f in fights if f["mvp"]] or fights
            top = sorted(sorted(fights, key=lambda f: -f["total"])[:BOSS_ROWS], key=lambda f: f["first"])
            self.fight_cache = (sig, top, len(fights), None)
        return self.fight_cache[1]

    def boss_rows(self, c, rng, fights):
        """Uma linha por luta contra chefe. O dano de quem grava em cada uma sai de uma passada só pelos golpes
        (antes era uma passada inteira por chefe: 5 s num replay de 78 mil golpes e 313 chefes)."""
        sig, top, count, rows = self.fight_cache
        if rows is not None:
            return rows
        keys = {f["key"] for f in fights}
        mine = collections.Counter()
        for h in an.out_hits(c, rng):
            if h.src == c.me and h.dst in keys:
                mine[h.dst] += h.dmg
        dead = sorted(tt for tt, a in c.death_log
                      if a == c.me or (c.entities.get(a) is not None and c.entities[a].kind == "pc"))
        rows = []
        for f in fights:
            dmg = mine.get(f["key"], 0)
            span_ms = max(1, f["last"] - f["first"])
            rows.append(dict(key=f["key"], name=f["name"], when=f["first"],
                             end_txt=(_("morto em %s") % dur(f["ttk"])) if f["ttk"] is not None else _("não morreu"),
                             total=f["total"], mine=dmg, share=(dmg / float(f["total"])) if f["total"] else None,
                             my_dps=dmg * 1000.0 / span_ms if dmg else None,
                             deaths=bisect.bisect_right(dead, f["last"] + 1000) - bisect.bisect_left(dead, f["first"]),
                             dead=f["ttk"] is not None))
        self.fight_cache = (sig, top, count, rows)
        return rows

    def refresh(self, c):
        win = self.win
        rng, dur_ms = win.rng, win.dur_ms
        sig = (id(c), c.version, rng, dur_ms, meter.HIDE_NAMES)
        if self.sum_cache[0] != sig:
            self.sum_cache = (sig, an.summary(c, rng, dur_ms), an.top_hits(c, rng, c.me, 15),
                              an.damage_taken(c, rng, c.me))
        _sig, sm, top_hits, taken_rows = self.sum_cache
        me = c.session
        name = c.name_of(c.me) if meter.HIDE_NAMES else me.player
        self.title.configure(text=_("%s · %s · nível %d") % (name, an.job_of(c, c.me), me.base_level))
        fights = self.fights(c, rng)
        bits = [_("mapa %s") % (c.map or me.map), _("%s gravados") % dur(c.now), _("%s em combate") % dur(dur_ms),
                _("%d jogadores") % len(win.players_rows)]
        if fights:
            bits.append(_("%d luta(s) contra chefe") % self.fight_cache[2])
        self.sub.configure(text=" · ".join(bits))
        t = self.dmg
        t.put("dealt", full(sm["dealt"]), _("%s do grupo") % _fmt("pct", sm["share"]), win.c["accent"],
              short=num(sm["dealt"]))
        t.put("dps", full(round(sm["dps"])), _("tempo em combate %s") % dur(sm["combat_ms"]))
        t.put("adps", full(round(sm["active_dps"])) if sm["active_dps"] else "—",
              _("só o tempo batendo: %s") % dur(sm["active_ms"]) if sm["active_ms"] else "")
        t.put("eff", full(round(sm["effective_dps"])) if sm["effective_dps"] else "—", _("como no Ragna Recap"))
        crit = (_("%s críticos") % _fmt("pct", sm["crits"] / float(sm["hits"]))) if sm["hits"] else ""
        t.put("hits", "%d" % sm["hits"], " · ".join(x for x in ((_("%d erros") % sm["misses"]), crit) if x))
        t.put("rate", dec("%.2f" % (sm["hits"] * 1000.0 / sm["active_ms"])) if sm["active_ms"] and sm["hits"] else "—",
              _("no tempo batendo"))
        if sm["best"]:
            t.put("best", full(sm["best"]["dmg"]), "%s · %s" % (sm["best"]["skill"], sm["best"]["target"]),
                  short=num(sm["best"]["dmg"]))
        else:
            t.put("best", "—")
        t.put("top", sm["top_skill"] or "—", _("%d usos") % sm["top_count"] if sm["top_count"] else "")
        # sobrevivência e ritmo
        span = stats.span(c, rng)
        sig = (id(c), c.version, rng, win.app.cfg.get("xp_mode"))
        if self.cache[0] != sig:
            deaths = [d for d in an.deaths(c, rng) if d["me"]]
            self.cache = (sig, dict(deaths=deaths, used=stats.items_used(c, span), casts=stats.casts(c, span),
                                    post=stats.post_delay(c, span), blocked=stats.blocked(c, span),
                                    stopped=stats.stopped(c, span), vals=stats.values(c, span),
                                    drops=c.drop_summary(rng)))
        x = self.cache[1]
        life = self.life
        life.put("taken", full(sm["taken"]), _("%d acertos") % sm["taken_hits"], short=num(sm["taken"]))
        last = x["deaths"][-1] if x["deaths"] else None
        cause = ""
        if last is not None:
            cause = _("a última: %s") % (_("armadilha do mapa") if last["trap"] else (
                "%s · %s" % (last["skill"], last["killer"]) if last.get("killer") else _("sem golpe visível")))
        life.put("deaths", "%d" % sm["deaths"], cause, win.c["bad"] if sm["deaths"] else None)
        life.put("kills", "%d" % sm["kills"], _("%d chefes") % sm["boss_kills"] if sm["boss_kills"] else "")
        used = x["used"]
        life.put("items", "%d" % sum(r["n"] for r in used) if used else "—",
                 ("%s ×%d" % (used[0]["name"], used[0]["n"])) if used else _("nenhum à vista"))
        aspd = x["vals"].get("aspd")
        life.put("aspd", stats.stat_text("aspd", aspd[0]) if aspd else "—",
                 (_("de %s a %s no recorte") % (stats.stat_text("aspd", aspd[1]), stats.stat_text("aspd", aspd[2])))
                 if aspd and aspd[2] > aspd[1] else (_("média no recorte") if aspd else _("o replay não trouxe")))
        cast = next((r for r in x["casts"] if r["cast"]), None)
        life.put("cast", ("%d ms" % round(cast["cast"])) if cast else _("instantânea") if x["casts"] else "—",
                 (_("%s · %d usos") % (cast["name"], cast["n"])) if cast else
                 (_("%d interrompidas") % x["stopped"] if x["stopped"] else ""))
        post = x["post"]
        life.put("post", ("%d ms" % post["real"]) if post else "—",
                 (_("%d ms de base · -%d%%") % (post["base"], round(post["cut"] * 100))) if post
                 else _("nenhuma skill com pós-conjuração"))
        life.put("blocked", "%d" % x["blocked"] if x["blocked"] else "—",
                 _("tentativas antes de a skill voltar") if x["blocked"] else "")
        # XP e drops
        gain = self.gain
        est = xp.estimate(c, win.app.cfg, rng)
        if est["pct"] is not None:
            gain.put("xp", dec("%.2f%%" % est["pct"]), _("do nível · %s") % num(est["xp"]), win.c["accent"])
        else:
            gain.put("xp", num(est["xp"]) if est["xp"] else "—", "", win.c["accent"])
        if est["per_hour"] is not None:
            gain.put("hour", dec("%.2f%%" % est["per_hour_pct"]) if est["per_hour_pct"] is not None
                     else num(est["per_hour"]), (_("do nível · %s/h") % num(est["per_hour"]))
                     if est["per_hour_pct"] is not None else "")
        else:
            gain.put("hour", "—", _("recorte curto demais"))
        pr = xp.progress(c, win.app.cfg)
        if pr is not None and pr["pct"] is not None:
            gain.put("level", "%d" % pr["level"], _("%s agora (estimado)") % dec("%.2f%%" % min(100.0, pr["pct"])))
        else:
            gain.put("level", "%d" % me.base_level if me.base_level else "—")
        gain.put("mobs", "%d" % est["kills"], (_("%s por minuto") % dec("%.1f" % est["kills_per_min"]))
                 if est["kills_per_min"] is not None else "")
        drops = x["drops"]
        mine = [r for r in drops if r["mine"]]
        gain.put("drops", "%d" % sum(r["mine"] for r in mine) if mine else "—",
                 (_("%d itens diferentes · %s") % (len(mine), mine[0]["name"])) if mine else _("nenhum no recorte"))
        mvp = [r for r in drops if r["mvp"]]
        gain.put("mvp", "%d" % sum(r["mvp"] for r in mvp) if mvp else "—", ", ".join(r["name"] for r in mvp[:3]))
        # chefes do recorte
        rows = self.boss_rows(c, rng, fights)
        self.boss_lbl.configure(text=_("Chefes do recorte") if rows else _("Chefes do recorte: nenhuma luta contra chefe"))
        self.t_boss.set_rows(rows, lambda r: r["key"], lambda r: ["good"] if r["dead"] else ["mid"])
        self.t_tophits.set_rows(top_hits, lambda r: "%d|%d" % (r["t"], r["dmg"]))
        self.t_taken.set_rows(taken_rows, lambda r: "%s|%s" % (r["source"], r["name"]))
        self.t_items.set_rows(used, lambda r: r["item"])
