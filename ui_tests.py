# -*- coding: utf-8 -*-
"""Aba Testes da análise: dois testes lado a lado. De fora para dentro, de cada lado: a lista para escolher o
teste, o equipamento dele (com os ícones do jogo) e os números; os números dos dois se encontram no meio, com a
diferença. Numa janela estreita as duas listas sobem para cima da comparação.
"""

import tkinter as tk
from tkinter import ttk

import testes
import ui_parts
from analysis_ui import ScrollFrame, Table
from fmt import dur, full
from i18n import _

WIDE_PX = 1340                # largura (a 100%) a partir da qual as listas ficam dos lados
PICK_W = 250                  # largura da lista de cada lado, quando fica do lado
EQUIP_W = 235                 # largura do equipamento de cada lado
SIDE_GROUPS = [("Equipamento", ui_parts.GEAR), ("Sombrio", ui_parts.SHADOW)]   # visuais não mudam o dano


class TestsTab:
    def __init__(self, win, nb):
        self.win = win
        c = win.c
        tab = tk.Frame(nb, bg=c["panel"])
        nb.add(tab, text=_("Testes"))
        self.tab = tab
        bar = tk.Frame(tab, bg=c["panel"])
        bar.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(bar, text=_("Salvar luta como teste…"), style="An.TButton", command=win.save_test).pack(side="left")
        ttk.Button(bar, text=_("Renomear"), style="An.TButton", command=win.rename_test).pack(side="left", padx=6)
        ttk.Button(bar, text=_("Excluir"), style="An.TButton", command=win.delete_test).pack(side="left")
        self.hint = win.label(bar, "", "small", "muted", "panel", anchor="w", justify="left")
        self.hint.pack(side="left", padx=12, fill="x", expand=True)
        ui_parts.follow_wrap(bar, self.hint, int(430 * win.dpi), 200)
        self.body = tk.Frame(tab, bg=c["panel"])
        self.body.pack(fill="both", expand=True)
        self.ids = {"a": None, "b": None}
        self.last = "a"               # lado do último teste clicado (renomear e excluir valem para ele)
        self.pick = {}
        self.head = {}
        self.equip = {}
        self.sig = None
        self.wide = None
        for side in ("a", "b"):
            frame = tk.Frame(self.body, bg=c["panel"])
            title = win.label(frame, _("Teste A") if side == "a" else _("Teste B"), "head", "accent" if side == "a"
                              else "good", "panel", anchor="w")
            title.pack(fill="x", padx=8, pady=(6, 2))
            t = Table(frame, win, [("title", _("Teste"), 120, "w", "text"), ("when", _("Quando"), 78, "w", "text"),
                                   ("dps", "DPS", 58, "e", "num")], height=5,
                      on_select=lambda r, s=side: self.picked(s, r))
            t.pack(fill="both", expand=True, padx=(8, 4) if side == "a" else (4, 8), pady=(0, 6))
            self.pick[side] = (frame, t)
        self.mid_outer = tk.Frame(self.body, bg=c["panel"])
        mid = ScrollFrame(self.mid_outer, win).inner
        mid.columnconfigure(1, weight=1)
        z = win.dpi
        mid.columnconfigure(0, minsize=int(EQUIP_W * z))
        mid.columnconfigure(2, minsize=int(EQUIP_W * z))
        for col, side in ((0, "a"), (2, "b")):
            box = tk.Frame(mid, bg=c["panel"], width=int(EQUIP_W * z))
            box.grid(row=0, column=col, sticky="new", padx=4, pady=(4, 8))
            h1 = win.label(box, "", "head", "accent" if side == "a" else "good", "panel", anchor="w", justify="left",
                           wraplength=int((EQUIP_W - 12) * z))
            h1.pack(fill="x", padx=6)
            h2 = win.label(box, "", "small", "muted", "panel", anchor="w", justify="left",
                           wraplength=int((EQUIP_W - 12) * z))
            h2.pack(fill="x", padx=6, pady=(0, 4))
            panel = ui_parts.EquipPanel(box, win, groups=SIDE_GROUPS, cols=1)
            panel.configure(width=int(EQUIP_W * z))
            panel.pack(fill="x")
            self.head[side] = (h1, h2)
            self.equip[side] = panel
        self.fly = ui_parts.Butterfly(mid, win)
        self.fly.grid(row=0, column=1, sticky="new", pady=(4, 8))
        self.body.bind("<Configure>", lambda e: self.layout(e.width))

    # ------------------------------------------------------------ disposição

    def layout(self, width):
        wide = width >= WIDE_PX * self.win.dpi * self.win.zoom
        if wide == self.wide:
            return
        self.wide = wide
        b = self.body
        (fa, _ta), (fb, _tb) = self.pick["a"], self.pick["b"]
        for w in (fa, fb, self.mid_outer):
            w.grid_forget()
        z = self.win.dpi * self.win.zoom
        for col in range(3):
            b.columnconfigure(col, weight=0, minsize=0, uniform="")
        for row in range(2):
            b.rowconfigure(row, weight=0, minsize=0)
        if wide:                                   # lista | equipamento, números, equipamento | lista
            b.columnconfigure(0, minsize=int(PICK_W * z))
            b.columnconfigure(1, weight=1)
            b.columnconfigure(2, minsize=int(PICK_W * z))
            b.rowconfigure(0, weight=1)
            fa.grid(row=0, column=0, sticky="nsew")
            self.mid_outer.grid(row=0, column=1, sticky="nsew")
            fb.grid(row=0, column=2, sticky="nsew")
        else:                                      # as duas listas em cima, a comparação embaixo
            b.columnconfigure(0, weight=1, uniform="pick")
            b.columnconfigure(1, weight=1, uniform="pick")
            b.rowconfigure(1, weight=1)
            fa.grid(row=0, column=0, sticky="nsew")
            fb.grid(row=0, column=1, sticky="nsew")
            self.mid_outer.grid(row=1, column=0, columnspan=2, sticky="nsew")

    # ------------------------------------------------------------ dados

    def store(self):
        return self.win.app.tests

    def focused(self):
        """O teste do último lado clicado (para renomear e excluir)."""
        rid = self.ids.get(self.last)
        return self.store().get(rid) if rid else None

    def picked(self, side, row):
        if row is None or row["id"] == self.ids[side]:
            if row is not None:
                self.last = side
            return
        self.ids[side] = row["id"]
        self.last = side
        self.compare()

    def refresh(self):
        if self.wide is None:
            self.layout(self.body.winfo_width() if self.body.winfo_width() > 1 else self.win.top.winfo_width())
        st = self.store()
        rows = []
        for r in st.records:
            _y, mo, d, hh, mm, _ss = (r.get("recorded_at") or [0] * 6)[:6]
            rows.append(dict(id=r["id"], title=r.get("label") or r.get("target") or "?", dps=r.get("dps") or 0,
                             when="%02d/%02d %02d:%02d" % (d, mo, hh, mm)))
        known = {r["id"] for r in rows}
        if self.ids["a"] not in known:
            self.ids["a"] = rows[0]["id"] if rows else None
        if self.ids["b"] not in known:
            prev = st.previous(st.get(self.ids["a"])) if self.ids["a"] else None
            self.ids["b"] = prev["id"] if prev else next((r["id"] for r in rows if r["id"] != self.ids["a"]), None)
        for side in ("a", "b"):
            t = self.pick[side][1]
            t.set_rows(rows, lambda r: r["id"])
            if self.ids[side]:
                t.select(self.ids[side])
        self.hint.configure(text=_("%d teste(s). As lutas contra bonecos de treino são salvas sozinhas; qualquer outra "
                                   "(inclusive de replays de outras pessoas) dá para salvar no botão. Escolha um "
                                   "teste de cada lado para comparar.") % len(rows))
        self.compare()

    def compare(self):
        st = self.store()
        a = st.get(self.ids["a"]) if self.ids["a"] else None
        b = st.get(self.ids["b"]) if self.ids["b"] else None
        sig = (self.ids["a"], self.ids["b"], (a or {}).get("label"), (b or {}).get("label"), len(st.records),
               self.win.zoom)
        if sig == self.sig:
            return
        self.sig = sig
        diff = testes.equip_diff(a, b) if a and b else set()
        for side, rec in (("a", a), ("b", b)):
            h1, h2 = self.head[side]
            if rec is None:
                h1.configure(text=_("Nenhum teste escolhido"))
                h2.configure(text="")
                self.equip[side].set([])
                continue
            _y, mo, d, hh, mm, _ss = (rec.get("recorded_at") or [0] * 6)[:6]
            h1.configure(text=rec.get("label") or rec.get("target") or "?")
            bits = [rec.get("char") or "", rec.get("job") or "", (_("nível %d") % rec["level"]) if rec.get("level") else "",
                    rec.get("target") if rec.get("label") else "", "%02d/%02d %02d:%02d" % (d, mo, hh, mm),
                    dur(rec.get("combat_ms") or 0), "DPS %s" % full(round(rec.get("dps") or 0))]
            h2.configure(text=" · ".join(x for x in bits if x))
            self.equip[side].set(rec.get("equip") or [], diff=diff, show_empty=True)
        if a is None:
            self.fly.set([dict(kind="head", name=_("Salve ou escolha um teste para comparar"))])
        else:
            self.fly.set(testes.sides(a, b))
