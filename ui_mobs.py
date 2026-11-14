# -*- coding: utf-8 -*-
"""Aba Monstros da análise: a lista dos monstros atacados à esquerda e, à direita, o escolhido com o desenho dele
animado e, de relance, o que o grupo fez nele e o que ele fez (dano causado, quem matou, o maior golpe, quem mais
apanhou e as habilidades que usou). Os detalhes continuam em abas embaixo.
"""

import tkinter as tk
from tkinter import ttk

import analysis as an
import dedoduro as dd
import meter
import sprites
import ui_parts
from analysis_ui import BUCKETS, Chart, HBars, Table, Tiles
from fmt import dur, full, num
from i18n import _

ACTIONS = [(sprites.MOB_WALK, "Andando"), (sprites.MOB_IDLE, "Parado"), (sprites.MOB_ATTACK, "Atacando")]


class MobsTab:
    def __init__(self, win, nb):
        self.win = win
        c = win.c
        tab = tk.Frame(nb, bg=c["panel"])
        nb.add(tab, text=_("Monstros"))
        pw = ttk.PanedWindow(tab, orient="horizontal", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True)
        left = tk.Frame(pw, bg=c["panel"])
        right = tk.Frame(pw, bg=c["panel"])
        pw.add(left, weight=0)
        pw.add(right, weight=1)
        win.section(left, _("Monstros atacados"))
        self.t_mobs = Table(left, win, [
            ("name", _("Monstro"), 168, "w", "text"), ("total", _("Dano"), 64, "e", "num"),
            ("ttk", _("Abate"), 58, "e", "dur")], height=12, on_select=self.selected)
        self.t_mobs.pack(fill="both", expand=True, padx=(8, 2), pady=(0, 8))
        self.key = None
        self.rows = []
        self.victims = {}
        # --- o monstro escolhido
        head = tk.Frame(right, bg=c["panel"])
        head.pack(fill="x", padx=(4, 10), pady=(10, 0))
        art = tk.Frame(head, bg=c["tile"])
        art.pack(side="left", anchor="n")
        self.sprite = ui_parts.SpriteView(art, win, w=176, h=150)
        self.sprite.pack(padx=4, pady=(4, 0))
        self.action = tk.StringVar(win.top, _(ACTIONS[0][1]))
        box = ttk.Combobox(art, textvariable=self.action, values=[_(n) for _a, n in ACTIONS], width=11,
                           state="readonly", style="An.TCombobox", font=win.f["small"])
        box.pack(pady=(2, 6))
        box.bind("<<ComboboxSelected>>", lambda e: self.show_sprite())
        info = tk.Frame(head, bg=c["panel"])
        info.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.title = win.label(info, "", "title", bg="panel", anchor="w")
        self.title.pack(fill="x")
        self.sub = win.label(info, "", "small", "muted", "panel", anchor="w", justify="left")
        self.sub.pack(fill="x", pady=(0, 6))
        ui_parts.follow_wrap(info, self.sub, 10)
        win.label(info, _("O que o grupo fez nele").upper(), "small", "muted", "panel", anchor="w").pack(fill="x")
        self.got = Tiles(info, win, [("total", _("Dano recebido")), ("ttk", _("Tempo até o abate")),
                                     ("killer", _("Abatido por")), ("attackers", _("Atacantes"))],
                         min_w=128, dense=True)
        self.got.pack(fill="x", pady=(2, 2))
        win.label(info, _("O que ele fez").upper(), "small", "muted", "panel", anchor="w").pack(fill="x")
        self.did = Tiles(info, win, [("dealt", _("Dano causado")), ("kills", _("Jogadores mortos")),
                                     ("best", _("Maior golpe")), ("victim", _("Quem mais apanhou"))],
                         min_w=128, dense=True)
        self.did.pack(fill="x", pady=(2, 0))
        # --- detalhes
        sub = ttk.Notebook(right, style="Sub.TNotebook")
        sub.pack(fill="both", expand=True, padx=(4, 8), pady=(6, 8))
        self.nb = sub
        sub.bind("<<NotebookTabChanged>>", lambda e: win.refresh(force=True))
        f0 = tk.Frame(sub, bg=c["panel"])
        sub.add(f0, text=_("Habilidades que ele usou"))
        bar = tk.Frame(f0, bg=c["panel"])
        bar.pack(fill="x", padx=8, pady=(6, 0))
        win.label(bar, _("Com dano e de suporte/debuff.   Em quem:"), color="muted", bg="panel").pack(side="left")
        self.victim_var = tk.StringVar(win.top, _("Todos os alvos"))
        self.victim_box = ttk.Combobox(bar, textvariable=self.victim_var, width=24, state="readonly",
                                       style="An.TCombobox", font=win.f["text"])
        self.victim_box.pack(side="left", padx=6)
        self.victim_box.bind("<<ComboboxSelected>>", lambda e: win.refresh(force=True))
        self.t_mskills = Table(f0, win, [
            ("name", _("Habilidade"), 190, "w", "text"), ("el_txt", _("Propriedade"), 90, "w", "text"),
            ("uses", _("Usos"), 55, "e", "int"), ("total", _("Dano total"), 115, "e", "big"),
            ("max_hit", _("Maior golpe"), 105, "e", "big"), ("avg", _("Dano médio"), 100, "e", "big"),
            ("targets", _("Alvos"), 55, "e", "int"), ("cast", _("Cast médio"), 80, "e", "ms")], height=8)
        self.t_mskills.pack(fill="both", expand=True, padx=4, pady=6)
        f1 = tk.Frame(sub, bg=c["panel"])
        sub.add(f1, text=_("Dano por jogador"))
        self.bars = HBars(f1, win)
        self.bars.pack(fill="both", expand=True, pady=4)
        f2 = tk.Frame(sub, bg=c["panel"])
        sub.add(f2, text=_("Linha do tempo"))
        bar = tk.Frame(f2, bg=c["panel"])
        bar.pack(fill="x", padx=8, pady=(6, 0))
        win.label(bar, _("Dano a cada"), color="muted", bg="panel").pack(side="left")
        self.bucket = tk.StringVar(win.top, "2 s")
        cb = ttk.Combobox(bar, textvariable=self.bucket, values=[b[1] for b in BUCKETS], width=6, state="readonly",
                          style="An.TCombobox", font=win.f["text"])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: win.refresh(force=True))
        win.label(bar, _("uma linha por jogador · tracejado = troca de fase"), color="muted", bg="panel").pack(side="left")
        self.chart = Chart(f2, win, height=260)
        self.chart.pack(fill="both", expand=True, padx=4, pady=4)
        f3 = tk.Frame(sub, bg=c["panel"])
        sub.add(f3, text=_("Habilidades usadas contra ele"))
        self.t_against = Table(f3, win, [
            ("name", _("Habilidade"), 200, "w", "text"), ("player", _("Jogador"), 150, "w", "text"),
            ("job", _("Classe"), 120, "w", "text"), ("hits", _("Acertos"), 70, "e", "int"),
            ("total", _("Dano total"), 120, "e", "big"), ("avg", _("Dano médio"), 110, "e", "big"),
            ("avg_multi", _("Hits médios"), 95, "e", "f2"), ("cast", _("Cast médio"), 85, "e", "ms")], height=8,
            swatch=True)
        self.t_against.pack(fill="both", expand=True, padx=4, pady=6)

    # ------------------------------------------------------------ dados

    def selected(self, row):
        if row is not None and row["key"] != self.key:
            self.key = row["key"]
            self.victim_var.set(_("Todos os alvos"))
            self.win.mob_key = self.key
            self.win.refresh(force=True)

    def show_sprite(self):
        row = next((r for r in self.rows if r["key"] == self.key), None)
        action = next((a for a, n in ACTIONS if _(n) == self.action.get()), sprites.MOB_WALK)
        self.sprite.set(row["mob_id"] if row else None, row["name"] if row else "", action)

    def refresh(self, c):
        win = self.win
        group = win.group_var.get()
        rows = self.rows = an.monsters(c, win.rng, group)
        self.t_mobs.set_rows(rows, lambda r: r["key"], lambda r: ["me"] if r["boss"] else [])
        keys = [r["key"] for r in rows]
        if win.mob_key in keys:
            self.key = win.mob_key
        if self.key not in keys:
            self.key = keys[0] if keys else None
        win.mob_key = self.key
        if self.key is not None:
            self.t_mobs.select(self.key)
        row = next((r for r in rows if r["key"] == self.key), None)
        self.show_sprite()
        if row is None:
            self.title.configure(text=_("Nenhum monstro atacado neste recorte."))
            self.sub.configure(text="")
            for tiles, keys_ in ((self.got, ("total", "ttk", "killer", "attackers")),
                                 (self.did, ("dealt", "kills", "best", "victim"))):
                for k in keys_:
                    tiles.put(k, "—")
            self.t_mskills.set_rows([], lambda r: 0)
            self.bars.set([])
            self.chart.set([], 1000, [])
            self.t_against.set_rows([], lambda r: 0)
            return
        key = self.key
        self.title.configure(text=row["name"], fg=win.c["accent"] if row["boss"] else win.c["fg"])
        bits = []
        m = meter.MONSTERS.get(str(row["mob_id"])) or {}
        if m.get("level"):
            bits.append(_("nível %d") % m["level"])
        el = dd.boss_element(c, key)
        if el:
            bits.append("%s %d" % (an.element_name(el[0]), el[1]))
        size = meter.MOB_SIZE.get(row["mob_id"])
        if size:
            bits.append(_({"S": "pequeno", "M": "médio", "L": "grande"}[size]))
        if row["max_hp"]:
            bits.append(_("HP máx. %s") % full(row["max_hp"]))
        bits.append("ID %d" % row["mob_id"])
        self.sub.configure(text="  ·  ".join(bits))
        rep = an.monster_report(c, win.rng, key)
        g = self.got
        g.put("total", full(row["total"]), _("%d acertos") % row["hits"], short=num(row["total"]))
        g.put("ttk", dur(row["ttk"]) if row["ttk"] is not None else "—",
              "" if row["ttk"] is not None else _("não morreu no recorte"))
        g.put("killer", row["killer"] or "—", _("golpe final") if row["killer"] else "")
        g.put("attackers", "%d" % row["attackers"])
        d = self.did
        d.put("dealt", full(rep["total"]) if rep["total"] else "—",
              (_("%d golpes em %d jogadores") % (rep["hits"], rep["victims"])) if rep["hits"] else _("não acertou ninguém"),
              short=num(rep["total"]))
        d.put("kills", "%d" % len(rep["kills"]), ", ".join(rep["kills"][:6]) + (" …" if len(rep["kills"]) > 6 else ""),
              win.c["bad"] if rep["kills"] else None)
        if rep["best"]:
            b = rep["best"]
            d.put("best", full(b["dmg"]), _("%s em %s") % (b["skill"], b["victim"]), short=num(b["dmg"]))
        else:
            d.put("best", "—")
        if rep["top"]:
            t = rep["top"]
            d.put("victim", t["name"], _("%s · mais de %s") % (full(t["dmg"]), t["skill"]))
        else:
            d.put("victim", "—")
        sub = self.nb.index(self.nb.select())
        if sub == 0:
            victims = an.monster_victims(c, win.rng, key)
            self.victims = {_("Todos os alvos"): None}
            self.victims.update({name: aid for aid, name in victims})
            vals = list(self.victims)
            if list(self.victim_box["values"]) != vals:
                self.victim_box["values"] = vals
            target = self.victims.get(self.victim_var.get())
            rows2 = an.monster_skills(c, win.rng, key, target)
            for r in rows2:
                r["uses"] = r["hits"] + r["nodmg"]
                r["el_txt"] = an.element_name(an.attack_element(c, key, r["skill"])) if r["hits"] else ""
                r["max_hit"] = rep["skill_max"].get(r["skill"]) if target is None else None
            self.t_mskills.set_rows(rows2, lambda r: r["skill"])
        elif sub == 1:
            self.bars.set(an.monster_players(c, win.rng, key, group)[:14])
        elif sub == 2:
            bucket = dict((b[1], b[0]) for b in BUCKETS)[self.bucket.get()]
            ts, series = an.timeline(c, win.rng, bucket, key=key, group=group, top=10)
            self.chart.set(ts, bucket, series, "line", win.phase_markers(c, key))
        else:
            self.t_against.set_rows(an.skills_against(c, win.rng, key, group),
                                    lambda r: "%s|%s" % (r["player"], r["name"]),
                                    color_fn=lambda r: win.color_of(r["src"]))
