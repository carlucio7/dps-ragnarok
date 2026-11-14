# -*- coding: utf-8 -*-
"""Aba Cartões da análise (o gerenciador de cartões): à esquerda os cartões do programa, cada um com a sua caixa
para desligar, e a prévia de como o escolhido aparece no widget; à direita os efeitos que o widget acompanha com um
contador (busca em todos os buffs, debuffs e efeitos de chão). Funciona sem replay aberto.

A prévia é desenhada pelo próprio código do widget (as funções de dpsmeter.DpsApp) num widget de mentira: o cartão
da prévia é o cartão de verdade, com dados de exemplo.
"""

import sys
import time
import tkinter as tk
from tkinter import ttk

import cards
import clientdata
import meter
import sprites
import ui_parts
import xp
from analysis_ui import ScrollFrame, Table
from fmt import num
from i18n import _

ALL = "Todos os tipos"
BETEL, AQUILA, AQUILA_OVER, PORING = 20994, 21531, 21588, 1002
PREVIEW_ROWS = 6              # linhas do widget de mentira da prévia
PREVIEW_TRIES = 12            # redesenhos enquanto os desenhos do jogo carregam


class CardPreview(tk.Canvas):
    """Um widget de mentira (100%, 6 linhas, o tema escolhido) com o cartão pedido por cima, desenhado pelas
    funções do widget de verdade."""

    def __init__(self, parent, win):
        self.win = win
        app = win.app
        self.mod = sys.modules[type(app).__module__]          # o módulo do widget (constantes e cores)

        class Fake(type(app)):                                # o widget sem janela: só o que o desenho usa
            s = property(lambda self: self._s)
        p = self.p = object.__new__(Fake)
        p._s = app.dpi
        p.dpi = app.dpi
        p.root = win.top
        p.cfg = dict(app.cfg, scale=1.0, rows=PREVIEW_ROWS, width=self.mod.BASE_W, pins=[])
        p.make_fonts()
        p.W, p.H = p.size_px()
        super().__init__(parent, width=p.W, height=p.H, highlightthickness=1,
                         highlightbackground=win.c["grid"], bd=0)
        p.canvas = self
        p.hits, p.hover, p.phase, p.sprite_photos = [], None, 0, {}
        p.tracker_rows, p.tracker_n, p.pinned_fx = [], 0, {}
        p.fx_cards, p.fx_closed, p.fx_now = [], set(), []
        p.death_card = p.boss_card = p.ping_card = p.summary_card = None
        p.miracle_at = -1e9
        self.what = ("trackers", None)
        self.rows = []
        self.pinned = {}
        self.fx = []
        self._after = None
        self._tries = 0
        self.bind("<Destroy>", lambda e: self._cancel())

    def _cancel(self):
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def show(self, what, rows=None, pinned=None, fx=None):
        """what: ("system", chave do cartão) ou ("trackers", None) com as linhas dos contadores em `rows`.
        `pinned`: {chave: linha} dos efeitos fixados na faixa fixa; `fx`: os que aparecem como cartão."""
        self.what, self.rows, self.pinned, self.fx = what, rows or [], pinned or {}, fx or []
        self._tries = 0
        self.redraw()

    # ------------------------------------------------------------ dados de exemplo

    def mob_name(self, mob, fallback):
        return meter.monster_name(mob) or fallback

    def sample(self, key):
        """Os dados de exemplo de um cartão do programa."""
        betel, aquila = self.mob_name(BETEL, "Betelgeuse"), self.mob_name(AQUILA, "Aquila")
        if key == "boss_element":
            return "boss", dict(name=betel, element="Fire", mine="Water", sprite=("mob", BETEL))
        if key == "boss_size":
            return "boss", dict(name=aquila, size="S", prev_size="L", sprite=("mob", AQUILA))
        if key == "maxpain":
            return "boss", dict(name=betel, mech="maxpain_on", hp=120000, sprite=("mob", BETEL))
        if key == "defense":
            return "boss", dict(name=aquila, mech="defense", job=AQUILA, sprite=("mob", AQUILA))
        if key == "relief":
            return "boss", dict(name=betel, mech="relief", souls=6, pct=90, sprite=("mob", BETEL))
        if key == "def_break":
            return "boss", dict(name=aquila, mech="def_break", sprite=("mob", AQUILA_OVER))
        if key == "summary":
            return "summary", dict(key=0, sprite=("mob", BETEL), name=betel, killed=True, ms=154000, share=0.231,
                                   rank=2, players=7, grave=1, warn=2,
                                   alerts=[(2, _("Atacou antes da Garra Sombria"), "Fenrir"),
                                           (1, _("Atacou muito antes dos outros DPS"), "Bastion")])
        if key == "ping":
            item = 4001
            art = xp.GEAR.art.get(item)
            return "ping", dict(kind="drop", ref=None, item=item, name=meter.item_name(item), count=1,
                                map="prt_fild08", x=123, y=45, mob=self.mob_name(PORING, "Poring"), secs=12.0,
                                sprite=("item", item, art) if art else None)
        if key == "death":
            meteor, judge = meter.skill_name(83), meter.skill_name(0)
            src = [dict(source=betel, skill=meteor, element="Fire", dmg=121410, hits=2, killing=True, job=BETEL,
                        share=0.79, count=1),
                   dict(source=betel, skill=judge, element="Neutral", dmg=33059, hits=3, killing=False, job=BETEL,
                        share=0.21, count=1)]
            return "death", dict(sources=src, trap=False, trap_pct=None, fusion=False, hp_pct=None, special=None,
                                 killer=betel, overload_ms=0, unclear=False, no_hit=False, overkill=42000,
                                 window=5000, hits=5, total=154469, max_hp=119918, reflected=None,
                                 sprite=("mob", BETEL), nth=1)
        return "foot", None

    def foot_text(self, key):
        """(texto, cor) do aviso de rodapé de exemplo."""
        t = self.p.t
        if key == "buff_end":
            return _("%s acabou") % meter.status_name(20), "#f59e0b"
        if key == "fusion":
            return _(meter.FUSION_WARNINGS[0][1]) % 28, t["live"]
        if key == "rec":
            return _("Gravação desligada: ligue o replay no jogo"), t["live"]
        return (_("Você morreu") + ": %s · %s" % (meter.skill_name(83), self.mob_name(BETEL, "Betelgeuse"))
                + _(" · overkill %s") % num(42000)), t["live"]

    # ------------------------------------------------------------ desenho

    def backdrop(self, foot=None):
        """O widget de mentira por baixo do cartão: nome, DPS, abas, linhas e rodapé."""
        p, m = self.p, self.mod
        c, s, t, W, H, f = self, p.s, p.t, p.W, p.H, p.fonts
        tid = c.create_text(12 * s, m.TOP_Y * s, anchor="w", text="Aria", font=f["title"], fill=t["fg"])
        c.create_text(c.bbox(tid)[2] + 5 * s, m.TOP_Y * s + 1 * s, anchor="w", text="· " + (meter.job_name(4302) or ""),
                      font=f["small"], fill=t["muted"])
        bid = c.create_text(12 * s, m.BIG_Y * s, anchor="w", text="8,03M", font=f["big"], fill=t["fg"])
        c.create_text(c.bbox(bid)[2] + 4 * s, m.BIG_Y * s + 7 * s, anchor="w", text="DPS", font=f["unit"],
                      fill=t["muted"])
        side = p.side_pins(None)              # com um cartão aberto, o que está fixado fica à direita do DPS
        if side:
            p.draw_side_pins(side, W - 12 * s)
        else:
            for i, (text, col) in enumerate(((_("agora %s/s") % "9,25M", t["accent"]), (_("total %s") % "239M", t["fg"]),
                                             (_("%s %s") % (_("em combate"), "00:29"), t["muted"]))):
                c.create_text(W - 12 * s, m.BIG_Y * s - 14 * s + i * 14 * s, anchor="e", text=text, font=f["small"],
                              fill=col)
        x = 10 * s
        for i, (key, label) in enumerate(m.TABS):
            x = p.chip(("tab", key), x, label, i == 0) + 4 * s
        names = ["Aria", "Fenrir", "Bastion", "Corvina", "Lyra", "Dante"]
        vals = [239, 170, 82.5, 61.0, 33.4, 12.8]
        y = p.rows_y0() * s
        for i in range(PREVIEW_ROWS):
            x0, x1, y1 = 8 * s, W - 8 * s, y + (m.ROW_H - 3) * s
            c.create_polygon(m.round_rect_pts(x0, y, x1, y1, 4 * s), smooth=True, fill=t["track"], outline="")
            c.create_polygon(m.round_rect_pts(x0, y, x0 + (x1 - x0) * vals[i] / vals[0], y1, 4 * s), smooth=True,
                             fill=t["bar_me"] if i == 0 else t["bar"], outline="")
            c.create_text(x0 + 7 * s, (y + y1) / 2, anchor="w", text="%d. %s" % (i + 1, names[i]), font=f["text"],
                          fill=t["fg"])
            c.create_text(x1 - 7 * s, (y + y1) / 2, anchor="e", text=("%.1fM" % vals[i]).replace(".", ","),
                          font=f["num"], fill=t["fg"])
            y += m.ROW_H * s
        fy = H - m.FOOT_H * s / 2 - 2 * s
        text, dot = foot or (self.mob_name(BETEL, "Betelgeuse") + " · " + _("Gravando"), t["muted"])
        if foot:
            c.create_polygon(m.round_rect_pts(6 * s, fy - 10 * s, W - 10 * s, fy + 10 * s, 6 * s), smooth=True,
                             fill=m.mix(t["bg"], dot, 0.16), outline="")
        r = 3.2 * s
        c.create_oval(12 * s - r, fy - r, 12 * s + r, fy + r, outline="", fill=dot if foot else t["live"])
        sid = c.create_text(20 * s, fy, anchor="w", text=text, font=f["small"], fill=dot)
        p.clip_text(sid, text, W - 14 * s)

    def redraw(self):
        self._cancel()
        p = self.p
        now = time.time()
        p.cfg["theme"] = self.win.app.cfg.get("theme")
        for k in ("tracker_rows", "tracker_flash"):
            p.cfg[k] = self.win.app.cfg.get(k, p.cfg.get(k))
        p.death_card = p.boss_card = p.ping_card = p.summary_card = None
        p.miracle_at = -1e9
        kind, key = self.what
        p.tracker_n, p.hits = 0, []
        p.tracker_rows = list(self.rows) if kind == "trackers" else []
        p.fx_cards, p.fx_closed = (list(self.fx) if kind == "trackers" else []), set()
        p.fx_now = p.fx_card_rows()
        p.cfg["pins"] = ["fx:" + k for k in self.pinned]       # só os efeitos fixados (XP e drops pedem um replay)
        p.pinned_fx = dict(self.pinned)
        p.W, p.H = p.size_px()                                 # com algo fixado o widget é uma faixa mais alto
        self.configure(width=p.W, height=p.H)
        shape, data, foot, spec = None, None, None, None
        if p.fx_now and p.fx_now[0].get("mob"):
            spec = ("mob", p.fx_now[0]["mob"])
        if kind == "system":
            if key == "miracle":
                p.miracle_at = now - 1.0
            else:
                shape, data = self.sample(key)
                if shape == "death":
                    p.death_card = (data, now - 1.0)           # já escurecido, como fica depois do primeiro instante
                elif shape == "foot":
                    foot = True
                elif shape == "boss":
                    p.boss_card = (data, now - 0.01)
                elif shape == "summary":
                    p.summary_card = (data, now - 0.01)
                elif shape == "ping":
                    p.ping_card = (data, now - 0.01)
            spec = (data or {}).get("sprite")
        p.t = p.theme()
        self.delete("all")
        self.configure(bg=p.t["bg"])
        self.backdrop(self.foot_text(key) if foot else None)
        card_up = shape in ("death", "boss", "summary", "ping") or bool(p.fx_now)
        try:
            if not card_up:
                p.draw_pins(None)
            if kind == "trackers" and p.fx_now:
                p.draw_fx_card()
            elif kind == "trackers":
                p.draw_trackers()
            elif key == "miracle":
                p.draw_miracle()
            elif shape == "death":
                p.draw_death()
            elif shape == "boss":
                p.draw_boss_card()
            elif shape == "summary":
                p.draw_summary_card()
            elif shape == "ping":
                p.draw_ping_card()
            if shape == "death" and self.pinned:               # o resumo da morte cobre o DPS: a faixa fica acima dele
                p.draw_pins(None, top=self.mod.TOP_Y + 14)
        except Exception:  # noqa: BLE001 - a prévia é um extra: um erro nela não derruba a aba
            self.win.app.log_error(*sys.exc_info())
        # o desenho do chefe (ou do item) vem do data.grf em outra thread: redesenha até chegar
        if spec and self._tries < PREVIEW_TRIES:
            ui_parts.start_loaders()
            if sprites.MONSTERS.book is None or (sprites.MONSTERS.expected(spec) and sprites.MONSTERS.image(spec) is None):
                if clientdata.NAMES.grf and sprites.MONSTERS.error is None:
                    self._tries += 1
                    self._after = self.after(350, self.redraw)


class CardsTab:
    def __init__(self, win, nb):
        self.win = win
        c = win.c
        tab = tk.Frame(nb, bg=c["panel"])
        nb.add(tab, text=_("Cartões"))
        tab.columnconfigure(0, weight=2, uniform="k")
        tab.columnconfigure(1, weight=3, uniform="k")
        tab.rowconfigure(0, weight=1)
        # ---------------- cartões do programa e a prévia
        left = tk.Frame(tab, bg=c["panel"])
        left.grid(row=0, column=0, sticky="nsew")
        win.section(left, _("Cartões do programa"))
        note = win.label(left, _("O que o widget já mostra sozinho. Tudo vem ligado; desmarque o que não quiser ver. "
                                 "Passe o mouse num cartão para ver a prévia."),
                         "small", "muted", "panel", anchor="w", justify="left")
        note.pack(fill="x", padx=10, pady=(0, 4))
        ui_parts.follow_wrap(left, note, 24, 160)
        pv = tk.Frame(left, bg=c["panel"])
        pv.pack(side="bottom", fill="x", padx=10, pady=(4, 10))
        self.pv_title = win.label(pv, "", "head", bg="panel", anchor="w")
        self.pv_title.pack(fill="x", pady=(0, 4))
        self.preview = CardPreview(pv, win)
        self.preview.pack(anchor="w")
        self.pv_what = ("trackers", None)
        holder = tk.Frame(left, bg=c["panel"])
        holder.pack(fill="both", expand=True)
        box = ScrollFrame(holder, win).inner
        self.sys_vars = {}
        for key, name, text, _cfg in cards.SYSTEM:
            var = tk.BooleanVar(win.top, True)
            row = tk.Frame(box, bg=c["panel"])
            row.pack(fill="x", padx=8, pady=(3, 0))
            cb = tk.Checkbutton(row, text=_(name), variable=var, command=lambda k=key: self.toggle_system(k),
                                bg=c["panel"], fg=c["fg"], selectcolor=c["btn"], activebackground=c["panel"],
                                activeforeground=c["fg"], font=win.f["text"], anchor="w", highlightthickness=0)
            cb.pack(fill="x")
            desc = win.label(row, _(text), "small", "muted", "panel", anchor="w")
            desc.pack(fill="x", padx=(24, 0))
            for w in (row, cb, desc):
                w.bind("<Enter>", lambda e, k=key: self.show_preview(("system", k)))
            self.sys_vars[key] = var
        # ---------------- efeitos acompanhados
        right = tk.Frame(tab, bg=c["panel"])
        right.grid(row=0, column=1, sticky="nsew")
        win.section(right, _("Efeitos acompanhados no widget"))
        note2 = win.label(right, _("Enquanto um efeito da lista está ativo, o widget mostra um contador no pé das "
                                   "linhas: o tempo que falta quando o jogo manda a duração (os debuffs no chefe "
                                   "vêm com ela) ou há quanto tempo está ativo. Só durante a gravação. Cada "
                                   "efeito aparece como você escolher em \"Aparece como\": contador (um cartão o "
                                   "cobre enquanto aparece), faixa fixa (até 2; com um cartão aberto vai para a "
                                   "direita do DPS) ou cartão (fica enquanto o efeito durar)."),
                          "small", "muted", "panel", anchor="w", justify="left")
        note2.pack(fill="x", padx=10, pady=(0, 6))
        ui_parts.follow_wrap(right, note2, 24, 200)
        sug = tk.Frame(right, bg=c["panel"])
        sug.pack(fill="x", padx=10, pady=(0, 6))
        win.label(sug, _("Sugestões:"), color="muted", bg="panel").pack(side="left")
        self.sug_btns = {}
        for efst in cards.SUGGESTED:
            b = tk.Label(sug, text="", font=win.f["small"], bg=c["btn"], fg=c["fg"], padx=8, pady=3, cursor="hand2")
            b.pack(side="left", padx=(6, 0))
            b.bind("<Button-1>", lambda e, i=efst: self.toggle("status", i))
            self.sug_btns[efst] = b
        bar = tk.Frame(right, bg=c["panel"])
        bar.pack(fill="x", padx=10)
        win.label(bar, _("Buscar:"), color="muted", bg="panel").pack(side="left")
        self.query = tk.StringVar(win.top, "")
        ent = tk.Entry(bar, textvariable=self.query, width=26, font=win.f["text"], bg=c["btn"], fg=c["fg"],
                       insertbackground=c["fg"], relief="flat")
        ent.pack(side="left", padx=6, ipady=3)
        self.query.trace_add("write", lambda *_a: self.fill_results())
        self.group = tk.StringVar(win.top, _(ALL))
        gb = ttk.Combobox(bar, textvariable=self.group, values=[_(ALL)] + [_(g) for g in cards.GROUPS], width=24,
                          state="readonly", style="An.TCombobox", font=win.f["text"])
        gb.pack(side="left", padx=6)
        gb.bind("<<ComboboxSelected>>", lambda e: self.fill_results())
        ttk.Button(bar, text=_("Acompanhar"), style="An.TButton", command=self.add_selected).pack(side="right")
        self.t_found = Table(right, win, [("mark", "", 26, "center", "text"), ("name", _("Efeito"), 250, "w", "text"),
                                          ("group_txt", _("Tipo"), 170, "w", "text")], height=7,
                             on_select=lambda r: self.show_preview(("trackers", (r["kind"], r["id"])) if r else None))
        self.t_found.pack(fill="both", expand=True, padx=(8, 8), pady=(6, 4))
        self.t_found.tree.bind("<Double-1>", lambda e: self.add_selected())
        head = tk.Frame(right, bg=c["panel"])
        head.pack(fill="x", padx=10, pady=(4, 0))
        self.following = win.label(head, "", "head", bg="panel", anchor="w")
        self.following.pack(side="left")
        ttk.Button(head, text=_("Remover"), style="An.TButton", command=self.remove_selected).pack(side="right")
        ttk.Button(head, text=_("Trocar onde olhar"), style="An.TButton", command=self.cycle_where).pack(
            side="right", padx=6)
        # como o efeito escolhido aparece: contador no pé das linhas, fixado na faixa fixa ou cartão enquanto durar
        self.show_var = tk.StringVar(win.top, "")
        self.show_box = ttk.Combobox(head, textvariable=self.show_var, state="disabled", width=11,
                                     values=[_(cards.SHOW_TEXT[m]) for m in cards.SHOWS], style="An.TCombobox",
                                     font=win.f["text"])
        self.show_box.pack(side="right")
        self.show_box.bind("<<ComboboxSelected>>", lambda e: self.show_selected())
        win.label(head, _("Aparece como:"), color="muted", bg="panel").pack(side="right", padx=(0, 6))
        self.t_mine = Table(right, win, [("name", _("Efeito"), 210, "w", "text"), ("group_txt", _("Tipo"), 135, "w", "text"),
                                         ("where_txt", _("Onde olhar"), 105, "w", "text"),
                                         ("shows_txt", _("Onde aparece"), 110, "w", "text")], height=5,
                            on_select=self.mine_selected)
        self.t_mine.pack(fill="both", expand=True, padx=(8, 8), pady=(4, 4))
        opts = tk.Frame(right, bg=c["panel"])
        opts.pack(fill="x", padx=10, pady=(2, 10))
        win.label(opts, _("Mostrar até"), color="muted", bg="panel").pack(side="left")
        self.rows_var = tk.StringVar(win.top, "%d" % cards.DEFAULT_ROWS)
        rb = ttk.Combobox(opts, textvariable=self.rows_var, values=["%d" % n for n in cards.ROW_CHOICES], width=3,
                          state="readonly", style="An.TCombobox", font=win.f["text"])
        rb.pack(side="left", padx=6)
        rb.bind("<<ComboboxSelected>>", lambda e: self.save_options())
        win.label(opts, _("contadores"), color="muted", bg="panel").pack(side="left")
        self.flash_var = tk.BooleanVar(win.top, True)
        self.sound_var = tk.BooleanVar(win.top, False)
        for var, text in ((self.flash_var, _('Piscar "acabou"')), (self.sound_var, _("Som quando acabar"))):
            ttk.Checkbutton(opts, text=text, variable=var, style="An.TCheckbutton",
                            command=self.save_options).pack(side="left", padx=(16, 0))
        self.sig = None

    # ------------------------------------------------------------ prévia

    def tracker_rows(self, pick=None):
        """Linhas de exemplo dos contadores: os efeitos da lista (o escolhido primeiro), com tempos de mentira.
        Sem nada na lista, o efeito escolhido na busca ou as duas primeiras sugestões."""
        cfg = self.cfg()
        tr = list(cards.tracked(cfg))
        example = not tr
        if pick is not None and not cards.is_tracked(cfg, *pick):
            tr.insert(0, dict(kind=pick[0], id=pick[1], where=cards.default_where(*pick)))
        elif pick is not None:
            e = cards.entry(*pick)
            ids = set(e["ids"]) if e else {pick[1]}
            tr.sort(key=lambda t: not (t["kind"] == pick[0] and t["id"] in ids))
        if not tr:
            tr = [dict(kind="status", id=i, where="target") for i in cards.SUGGESTED[:2]]
        left = [12300, 2400, 36000, 18000, 7500, 44000]
        rows = []
        for i, t in enumerate(tr):
            area = t["kind"] == "area"
            rows.append(dict(key="%s:%d" % (t["kind"], t["id"]), name=cards.name_of(t), where=t["where"],
                             target="Betelgeuse" if t["where"] == "target" else None,
                             left=None if area else left[i % len(left)], total=None if area else 20000 + 10000 * (i % 3),
                             since=42000, boss=False, mob=BETEL if t["where"] == "target" else None,
                             show=t.get("show", "counter")))
        fixed = self.fixed()
        pinned = {r["key"]: r for r in rows if r["key"] in fixed}
        rest = [r for r in rows if r["key"] not in fixed]
        fx = [r for r in rest if r["show"] == "card"]
        rows = [r for r in rest if r["show"] != "card"][:int(cfg.get("tracker_rows") or cards.DEFAULT_ROWS)]
        return rows, pinned, fx, example

    def fixed(self):
        """As chaves ("status:730") dos efeitos fixados na faixa fixa."""
        return {p[3:] for p in (self.cfg().get("pins") or []) if p.startswith("fx:")}

    def show_preview(self, what):
        if what is None:
            return
        self.pv_what = what
        if what[0] == "system":
            _rows, pinned, _fx, _example = self.tracker_rows(None)
            name = next((_(n) for k, n, _t, _c in cards.SYSTEM if k == what[1]), "")
            self.pv_title.configure(text=_("Prévia: %s") % name)
            self.preview.show(what, [], pinned)
        else:
            rows, pinned, fx, example = self.tracker_rows(what[1])
            self.pv_title.configure(text=_("Prévia: contadores (exemplo)") if example and what[1] is None
                                    else _("Prévia: os efeitos acompanhados"))
            self.preview.show(("trackers", None), rows, pinned, fx)

    # ------------------------------------------------------------ ações

    def cfg(self):
        return self.win.app.cfg

    def saved(self):
        app = self.win.app
        app.save()
        app.dirty = True
        self.sig = None
        self.refresh()

    def toggle_system(self, key):
        cards.set_enabled(self.cfg(), key, bool(self.sys_vars[key].get()))
        self.pv_what = ("system", key)
        self.saved()

    def toggle(self, kind, ident):
        cards.track(self.cfg(), kind, ident, on=not cards.is_tracked(self.cfg(), kind, ident))
        self.pv_what = ("trackers", (kind, ident) if cards.is_tracked(self.cfg(), kind, ident) else None)
        self.saved()

    def add_selected(self):
        row = self.t_found.selected()
        if row is not None and cards.track(self.cfg(), row["kind"], row["id"], on=True):
            self.pv_what = ("trackers", (row["kind"], row["id"]))
            self.saved()

    def remove_selected(self):
        row = self.t_mine.selected()
        if row is not None:
            self.pv_what = ("trackers", None)
            self.sig = None
            self.win.app.untrack(row["kind"], row["id"])      # sai da lista e, se estava fixado, da faixa fixa

    def mine_selected(self, row):
        """Escolheu um efeito acompanhado: a caixa "Aparece como" passa a valer para ele."""
        if row is None:
            self.show_box.configure(state="disabled")
            return
        self.show_box.configure(state="readonly")
        self.show_var.set(_(cards.SHOW_TEXT[row["show"]]))
        self.show_preview(("trackers", (row["kind"], row["id"])))

    def show_selected(self):
        row = self.t_mine.selected()
        mode = next((m for m in cards.SHOWS if _(cards.SHOW_TEXT[m]) == self.show_var.get()), None)
        if row is not None and mode and mode != row["show"]:
            self.pv_what = ("trackers", (row["kind"], row["id"]))
            self.sig = None
            self.win.app.set_fx_show(row["kind"], row["id"], mode)

    def cycle_where(self):
        row = self.t_mine.selected()
        if row is None:
            return
        order = ("any", "me") if row["kind"] == "area" else ("me", "target")
        nxt = order[(order.index(row["where"]) + 1) % len(order)] if row["where"] in order else order[0]
        cards.track(self.cfg(), row["kind"], row["id"], on=True, where=nxt)
        self.pv_what = ("trackers", (row["kind"], row["id"]))
        self.saved()

    def save_options(self):
        cfg = self.cfg()
        try:
            cfg["tracker_rows"] = int(self.rows_var.get())
        except ValueError:
            cfg["tracker_rows"] = cards.DEFAULT_ROWS
        cfg["tracker_flash"] = bool(self.flash_var.get())
        cfg["tracker_sound"] = bool(self.sound_var.get())
        self.pv_what = ("trackers", None)
        self.saved()

    # ------------------------------------------------------------ telas

    def fill_results(self):
        group = next((g for g in cards.GROUPS if _(g) == self.group.get()), None)
        cfg = self.cfg()
        rows = [dict(key="%s:%d" % (r["kind"], r["id"]), kind=r["kind"], id=r["id"], name=r["name"],
                     group_txt=_(r["group"]), mark="✓" if cards.is_tracked(cfg, r["kind"], r["id"]) else " ")
                for r in cards.search(self.query.get(), group)]
        self.t_found.set_rows(rows, lambda r: r["key"], lambda r: ["good"] if r["mark"].strip() else [])

    def refresh(self, c=None):
        cfg = self.cfg()
        sig = (repr(cfg.get("trackers")), repr(cfg.get("cards_off")), tuple(cfg.get(s[3]) for s in cards.SYSTEM if s[3]),
               cfg.get("alert_boss"), cfg.get("tracker_rows"), cfg.get("tracker_flash"), cfg.get("tracker_sound"),
               len(cards.catalog()), cfg.get("theme"), repr(cfg.get("pins")))
        if sig == self.sig:
            return
        self.sig = sig
        for key, var in self.sys_vars.items():
            on = cards.enabled(cfg, key)
            if bool(var.get()) != on:
                var.set(on)
        tr = cards.tracked(cfg)
        fixed = self.fixed()
        rows = []
        for t in tr:
            e = cards.entry(t["kind"], t["id"])
            key = "%s:%d" % (t["kind"], t["id"])
            show = "pin" if key in fixed else t["show"]
            rows.append(dict(key=key, kind=t["kind"], id=t["id"], where=t["where"],
                             name=cards.name_of(t), group_txt=_(e["group"]) if e else "",
                             where_txt=cards.where_text(t), show=show, shows_txt=_(cards.SHOW_TEXT[show])))
        self.t_mine.set_rows(rows, lambda r: r["key"], lambda r: ["me"] if r["show"] != "counter" else [])
        self.mine_selected(self.t_mine.selected())
        self.following.configure(text=(_("Acompanhando (%d)") % len(rows)) if rows
                                 else _("Acompanhando: nada ainda (escolha acima)"))
        for efst, b in self.sug_btns.items():
            e = cards.entry("status", efst)
            on = cards.is_tracked(cfg, "status", efst)
            b.configure(text=("✓ " if on else "+ ") + (cards.short_name(e["name"]) if e else "%d" % efst),
                        bg=self.win.c["accent"] if on else self.win.c["btn"],
                        fg="#ffffff" if on else self.win.c["fg"])
        self.rows_var.set("%d" % int(cfg.get("tracker_rows") or cards.DEFAULT_ROWS))
        self.flash_var.set(bool(cfg.get("tracker_flash", True)))
        self.sound_var.set(bool(cfg.get("tracker_sound")))
        self.fill_results()
        self.show_preview(self.pv_what)
