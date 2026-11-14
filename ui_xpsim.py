# -*- coding: utf-8 -*-
"""Simulador de XP (sub-aba da aba XP): refaz a conta do recorte trocando um bônus de cada vez.

Cada bônus começa em "Como foi": vale exatamente como valeu na gravação (o Banquete de Njord só nos minutos em que
esteve ativo, o Milagre só enquanto durou...), então sem mexer em nada o simulado é igual ao que foi. A pessoa muda
só o que quer testar: "O tempo todo" (com o % que escolher) ou "Desligado". Os abates são os mesmos; só o fator de
cada um muda. A coluna "Como foi" sai da mesma conta do simulado, para a diferença ser só a do que foi trocado.
"""

import tkinter as tk
from tkinter import ttk

import ui_parts
import xp
from analysis_ui import Table
from fmt import dec, dur, full, num
from i18n import _

# (chave, nome, opções do % ou None = valor fixo do bônus)
ROWS = [
    ("server", "Evento do servidor", ("50", "100", "200")),
    ("vip", "VIP", None),
    ("scepter", "Cetro do Coração Lunar", None),
    ("kafra", "Kafra Buff / Manual Kafra", None),
    ("manual", "Manual de combate", ("50", "100", "200", "300")),
    ("njord", "Banquete de Njord", None),
    ("gear", "Itens de XP", ("5", "10", "15", "20", "30")),
    ("miracle", "Milagre", None),
]
REAL, ON, OFF = "Como foi", "O tempo todo", "Desligado"


class XpSim:
    def __init__(self, win, parent):
        self.win = win
        c = win.c
        frame = tk.Frame(parent, bg=c["tile"])
        self.frame = frame
        top = tk.Frame(frame, bg=c["tile"])
        top.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Button(top, text=_("Resetar simulador"), style="An.TButton", command=self.reset).pack(side="right",
                                                                                               anchor="n")
        note = win.label(top, _("Como teria sido a XP deste recorte mudando algum bônus. Tudo começa em \"Como foi\": "
                                "cada bônus vale como valeu na gravação, e o simulado é igual ao que foi. Mude só o "
                                "que quiser testar; os abates são os mesmos."), "small", "muted", "tile",
                         anchor="w", justify="left")
        note.pack(side="left", fill="x", expand=True)
        ui_parts.follow_wrap(top, note, int(190 * win.dpi), 200)
        grid = tk.Frame(frame, bg=c["tile"])
        grid.pack(fill="x", padx=8, pady=(0, 6))
        for col, text in ((0, _("Bônus")), (1, _("Como foi neste recorte")), (2, _("No simulador")), (3, "%")):
            win.label(grid, text, "small", "muted", "tile", anchor="w").grid(row=0, column=col, sticky="w",
                                                                              padx=(0, 14))
        self.state, self.pct, self.real_lbl, self.name_lbl = {}, {}, {}, {}
        states = [_(REAL), _(ON), _(OFF)]
        for i, (key, name, choices) in enumerate(ROWS, start=1):
            lbl = win.label(grid, _(name), bg="tile", anchor="w")
            lbl.grid(row=i, column=0, sticky="w", padx=(0, 14), pady=1)
            real = win.label(grid, "", "small", "muted", "tile", anchor="w")
            real.grid(row=i, column=1, sticky="w", padx=(0, 14))
            sv = tk.StringVar(win.top, _(REAL))
            sb = ttk.Combobox(grid, textvariable=sv, values=states, width=14, state="readonly", style="An.TCombobox",
                              font=win.f["text"])
            sb.grid(row=i, column=2, sticky="w", padx=(0, 14))
            sb.bind("<<ComboboxSelected>>", lambda e: self.changed())
            pv = tk.StringVar(win.top, "")
            if choices:
                pb = ttk.Combobox(grid, textvariable=pv, values=choices, width=5, style="An.TCombobox",
                                  font=win.f["text"], justify="right")
                pb.bind("<<ComboboxSelected>>", lambda e, k=key: self.pct_changed(k))
                pb.bind("<Return>", lambda e, k=key: self.pct_changed(k))
                pb.bind("<FocusOut>", lambda e, k=key: self.pct_changed(k))
                pb.grid(row=i, column=3, sticky="w")
            else:
                tk.Label(grid, textvariable=pv, font=win.f["text"], fg=c["muted"], bg=c["tile"]).grid(
                    row=i, column=3, sticky="w")
            self.state[key], self.pct[key], self.real_lbl[key], self.name_lbl[key] = sv, pv, real, lbl
        grid.columnconfigure(1, weight=1)
        self.verdict = win.label(frame, "", "head", "fg", "tile", anchor="w", justify="left")
        self.verdict.pack(fill="x", padx=8, pady=(2, 6))
        ui_parts.follow_wrap(frame, self.verdict, 20, 200)
        self.table = Table(frame, win, [
            ("what", _("O quê"), 290, "w", "text"), ("real", _("Como foi"), 130, "e", "text"),
            ("sim", _("Simulado"), 130, "e", "text"), ("diff", _("Diferença"), 85, "e", "text")], height=5)
        self.table.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.replay = None            # a gravação para a qual a tela foi montada (outra gravação: tudo "Como foi")
        self.real = {}
        self.loading = False
        self.typed = {}               # o último % que valeu em cada caixa (para saber se a pessoa mexeu)

    # ------------------------------------------------------------ estado

    def reset(self):
        """Volta tudo para "Como foi"."""
        self.replay = None
        self.win.refresh(force=True)

    def changed(self):
        if not self.loading:
            self.win.refresh(force=True)

    def pct_changed(self, key):
        """Mexer no % de um bônus já é pedir para simular esse valor: ele passa para "O tempo todo"."""
        if self.loading:
            return
        now = self.pct[key].get().strip()
        if now != self.typed.get(key):
            self.typed[key] = now
            self.state[key].set(_(ON))
            self.win.refresh(force=True)

    def show_real(self, real, reset):
        """Escreve como cada bônus valeu de verdade no recorte. `reset`: põe todos de volta em "Como foi"."""
        self.loading = True
        self.real = real
        for key, _name, choices in ROWS:
            r = real[key]
            if reset:
                self.state[key].set(_(REAL))
            if not choices:
                self.pct[key].set("×2" if key == "miracle" else "+%g%%" % r["pct"])
            elif self.state[key].get() == _(REAL):         # em "Como foi" a caixa mostra o % que valeu
                self.pct[key].set("%g" % r["pct"])
                self.typed[key] = "%g" % r["pct"]
            if not r["counted"]:
                text, good = _("fora da conta (desmarcado na lista de bônus)"), False
            elif r["cover"] is None:
                text, good = _("marcado: +%g%%") % r["pct"], True
            elif r["cover"] <= 0:
                text, good = _("não esteve ativo"), False
            else:
                share = dec("%.0f%%" % (100 * r["cover"])) if r["cover"] < 0.995 else "100%"
                text = _("ativo por %s (%s do recorte)") % (dur(r["ms"]), share)
                if key != "miracle" and r["pct"]:
                    text += " · +%g%%" % r["pct"]
                good = True
            self.real_lbl[key].configure(text=text, fg=self.win.c["good" if good else "muted"])
        self.loading = False

    def read(self):
        """{chave: ("on", %) | ("off",)} só do que a pessoa tirou de "Como foi"."""
        over = {}
        for key, _name, choices in ROWS:
            state = self.state[key].get()
            self.name_lbl[key].configure(fg=self.win.c["accent" if state != _(REAL) else "fg"])
            if state == _(OFF):
                over[key] = ("off",)
            elif state == _(ON):
                pct = self.real[key]["pct"]
                if choices:
                    try:
                        pct = max(0.0, float(self.pct[key].get().replace(",", ".").replace("%", "").strip()))
                    except ValueError:
                        pass
                over[key] = ("on", pct)
        return over

    # ------------------------------------------------------------ conta

    def refresh(self, c, est):
        win = self.win
        cfg = win.app.cfg
        self.show_real(xp.sim_real(c, cfg, win.rng), reset=self.replay is not c)
        self.replay = c
        over = self.read()
        base = xp.simulate(c, cfg, win.rng, {})          # "como foi", pela mesma conta do simulado
        sim = xp.simulate(c, cfg, win.rng, over) if over else base
        nxt = c.session.next_exp

        def amount(v):
            if v is None:
                return "—"
            return ("%s · %s" % (dec("%.2f%%" % (100.0 * v / nxt)), num(v))) if nxt else full(round(v))

        def diff(a, b):
            if not a or b is None:
                return "—"
            return dec("%+.1f%%" % ((b - a) * 100.0 / a))

        recent = xp.recent_range(c, cfg)        # o mesmo trecho do "Até o próximo nível" lá de cima

        def eta(o):
            if recent is None:
                return "—"
            got = xp.simulate(c, cfg, recent, o)["xp"] or 0.0
            rate = got * 60000.0 / (recent[1] - recent[0])
            ms, _left = xp.time_to_level(c, cfg, rate) if rate > 0 else (None, None)
            return xp.span_text(ms) if ms else ("—" if ms is None else _("já subiu"))

        def whole_level(per_min):
            pr = xp.progress(c, cfg)
            need = pr["need"] if pr else None
            return xp.span_text(need / per_min * 60000.0) if need and per_min else "—"

        def times(v):
            return ("×" + dec("%.2f" % v)) if v else "—"
        rows = [
            dict(key="xp", what=_("XP no recorte"), real=amount(base["xp"]), sim=amount(sim["xp"]),
                 diff=diff(base["xp"], sim["xp"])),
            dict(key="hour", what=_("XP por hora"), real=amount(base["per_hour"]), sim=amount(sim["per_hour"]),
                 diff=diff(base["per_hour"], sim["per_hour"])),
            dict(key="factor", what=_("Fator de bônus"), real=times(base["factor"]), sim=times(sim["factor"]),
                 diff=diff(base["factor"], sim["factor"])),
            dict(key="eta", what=_("Até o próximo nível (ritmo dos últimos 10 min)"), real=eta({}), sim=eta(over),
                 diff=""),
            dict(key="level", what=_("Um nível inteiro no ritmo do recorte"), real=whole_level(base["per_min"]),
                 sim=whole_level(sim["per_min"]), diff=""),
        ]
        self.table.set_rows(rows, lambda r: r["key"])
        if not base["xp"] or sim["xp"] is None:
            self.verdict.configure(text=_("Sem abates com XP conhecida neste recorte."), fg=win.c["muted"])
        elif not over:
            self.verdict.configure(text=_("Tudo como foi. Mude algum bônus acima para simular."), fg=win.c["muted"])
        else:
            d = sim["xp"] / float(base["xp"]) - 1.0
            if abs(d) < 0.0005:
                text, color = _("Com estes bônus a XP seria a mesma."), win.c["muted"]
            elif d > 0:
                text = _("Com estes bônus: %s de XP (%s a mais no recorte).") % (
                    dec("%+.1f%%" % (d * 100)), num(sim["xp"] - base["xp"]))
                color = win.c["good"]
            else:
                text = _("Com estes bônus: %s de XP (%s a menos no recorte).") % (
                    dec("%+.1f%%" % (d * 100)), num(base["xp"] - sim["xp"]))
                color = win.c["bad"]
            self.verdict.configure(text=text, fg=color)
