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
from analysis_ui import ScrollFrame, Table
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


def _span(levels):
    """"245–251" (ou "252" se for um nível só)."""
    return ("%d" % levels[0]) if levels[0] == levels[-1] else "%d–%d" % (levels[0], levels[-1])


class XpSim:
    def __init__(self, win, parent):
        self.win = win
        c = win.c
        self.frame = tk.Frame(parent, bg=c["tile"])
        frame = ScrollFrame(self.frame, win, bg="tile").inner     # com a janela baixa, rola em vez de cortar
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
        # e se fosse em outro mapa: os mesmos abates por minuto, cada um num monstro do mapa escolhido (no alto: é a
        # pergunta que mais se faz; a tabela dos monstros do mapa fica no fim)
        # numa caixa com borda na cor de destaque: a caixa de mapa e o resultado dela não se perdem no resto da aba
        box = tk.Frame(frame, bg=c["panel"], highlightthickness=1, highlightbackground=c["accent"], padx=10, pady=7)
        box.pack(fill="x", padx=8, pady=(4, 8))
        mp = tk.Frame(box, bg=c["panel"])
        mp.pack(fill="x")
        win.label(mp, _("E se fosse em outro mapa?"), "head", "fg", "panel").pack(side="left")
        self.map_var = tk.StringVar(win.top, "")
        self.map_box = ttk.Combobox(mp, textvariable=self.map_var, width=50, height=16, style="Map.TCombobox",
                                    font=win.f["text"], postcommand=self.map_open)   # a lista se refaz ao abrir
        self.map_box.pack(side="left", padx=10)
        self.map_box.bind("<<ComboboxSelected>>", lambda e: self.map_picked())
        self.map_box.bind("<Return>", lambda e: self.map_picked())
        self.map_box.bind("<KeyRelease>", self.map_filter)
        # clicar na caixa seleciona o texto: o que se digitar troca o mapa escolhido em vez de se juntar a ele
        self.map_box.bind("<FocusIn>", lambda e: self.map_box.select_range(0, "end"))
        self.map_result = win.label(box, "", "text", "fg", "panel", anchor="w", justify="left")
        self.map_result.pack(fill="x", pady=(6, 0))
        ui_parts.follow_wrap(box, self.map_result, 20, 200)
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
        self.map_title = win.label(frame, "", "head", "fg", "tile", anchor="w")
        self.map_title.pack(fill="x", padx=8, pady=(4, 0))
        self.map_table = Table(frame, win, [
            ("name", _("Monstro"), 170, "w", "text"), ("lv", _("Nível"), 55, "e", "int"),
            ("share_txt", _("Da mistura"), 90, "e", "text"), ("pen_txt", _("Penalidade"), 90, "e", "text"),
            ("each_txt", _("XP por abate"), 120, "e", "text")], height=4)
        self.map_table.pack(fill="both", expand=True, padx=8, pady=(2, 2))
        self.map_note = win.label(frame, "", "small", "muted", "tile", anchor="w", justify="left")
        self.map_note.pack(fill="x", padx=8, pady=(0, 8))
        ui_parts.follow_wrap(frame, self.map_note, 20, 200)
        self.maps = []                # [(texto da lista, mapa)]
        self.maps_level = None        # o nível pelo qual a lista está ordenada
        self.level = None             # o nível de quem gravou (no fim do recorte)
        self.map_chosen = ""          # o texto do último mapa escolhido (aberta com ele, a lista mostra todos)
        self.map_cache = (None, None)
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

    def map_list(self):
        """Os mapas da caixa, primeiro os de monstros de nível mais perto do de quem gravou: "mapa · nv 65–86 · nome
        no /navi" (e quantos você matou lá, se caçou nele com o programa aberto). Digitar filtra pelo texto todo:
        acha pelo código ou pelo nome."""
        out = []
        for m, source, n, lv in xp.sim_maps(self.win.app.cfg, self.level):
            text = m
            if lv:
                text += " · " + ((_("nv %d") % lv[1]) if lv[1] == lv[2] else (_("nv %d–%d") % (lv[1], lv[2])))
            if source == "seus":
                text += " · " + _("seus abates lá: %d") % n
            title = xp.map_title(m)
            if title:
                text += " · " + title
            out.append((text, m))
        self.maps, self.maps_level = out, self.level
        return [text for text, _m in out]

    def map_filter(self, e=None):
        """Digitar na caixa filtra a lista (parte do nome do mapa). Vazia ou com o mapa escolhido, a lista é toda."""
        if e is not None and e.keysym in ("Return", "Up", "Down", "Escape", "Tab"):
            return
        if not self.maps:
            self.map_list()
        values = [text for text, _m in self.maps]
        typed = self.map_var.get().strip()
        if typed and typed != self.map_chosen:
            low = typed.lower()
            values = [v for v in values if low in v.lower()]
        self.map_box.configure(values=values)

    def map_open(self):
        """Ao abrir a lista: refeita (os seus abates em cada mapa mudam) e filtrada só se a pessoa digitou um pedaço."""
        self.map_list()
        self.map_filter()

    def map_picked(self):
        self.map_chosen = self.map_var.get().strip()
        self.map_changed()

    def map_code(self):
        """O mapa escolhido (o código, como no /navi), ou "" sem escolha."""
        text = self.map_var.get().strip()
        if not text:
            return ""
        hit = next((m for t, m in self.maps if t == text), None)
        return hit or text.split()[0].lower()

    def map_changed(self):
        self.map_cache = (None, None)
        if not self.loading:
            self.win.refresh(force=True)

    def refresh_map(self, c, amount, over=None):
        """A linha "e se fosse em outro mapa" e a tabela dos monstros dele (com os bônus trocados no simulador)."""
        win, cfg = self.win, self.win.app.cfg
        self.level = xp.level_at(c, win.rng[1] if win.rng else c.now)
        if not self.maps or self.maps_level != self.level:
            self.map_list()
            self.map_filter()
        m = self.map_code()

        def empty(text):
            self.map_result.configure(text=text, fg=win.c["muted"])
            self.map_title.configure(text="")
            self.map_table.set_rows([], lambda r: 0)
            self.map_note.configure(text="")
        if not m:
            empty(_("Escolha um mapa (ou digite parte do nome): o simulador mantém os seus abates por minuto e troca "
                    "cada um por um monstro do mapa."))
            return
        key = (id(c), c.version, len(c.death_log), win.rng, m, repr(over), repr([cfg.get(k) for k in xp.EST_KEYS]))
        if self.map_cache[0] == key:
            r = self.map_cache[1]
        else:
            r = xp.sim_map(c, cfg, win.rng, m, over)
            self.map_cache = (key, r)
        if r is None:
            empty(_("Ainda não sei os monstros de %s: o /navi do jogo não tem esse mapa e você ainda não caçou nele "
                    "com o programa aberto.") % m)
            return
        title = xp.map_title(r["map"])
        self.map_title.configure(text=(_("Monstros de %s (%s)") % (r["map"], title)) if title
                                 else (_("Monstros de %s") % r["map"]))
        span = (win.rng[1] - win.rng[0]) if win.rng else c.now
        kpm = r["kills"] * 60000.0 / span if span > 0 else 0.0
        d = (r["xp"] / r["base_xp"] - 1.0) if r["base_xp"] else None
        text = _("Mantidas as mesmas quantidades de abates por minuto (%s por minuto), em %s a XP do recorte teria "
                 "sido %s") % (dec("%.1f" % kpm), r["map"], amount(r["xp"]))
        if d is not None:
            text += _(" (%s do que foi)") % dec("%+.0f%%" % (100 * d))
        if over:
            text += _(", com os bônus trocados acima")
        if r["per_hour"]:
            text += ". " + _("Por hora: %s.") % amount(r["per_hour"])
        color = win.c["fg"] if d is None or abs(d) < 0.005 else win.c["good" if d > 0 else "bad"]
        bio = r.get("bio_share", 0) >= xp.FOREIGN_SHARE
        lo, hi = xp.BIO_LATAM
        if r.get("latam_share", 0) >= xp.FOREIGN_SHARE and not r.get("measured"):
            # a XP da tabela é a de outra versão destes monstros: o número pode estar longe do LATAM
            if bio:                                 # a Biosfera: medido no LATAM, uns 11 a 17% da tabela
                text += " " + _("Atenção: esta conta usa a XP da Biosfera coreana, que não é a do LATAM. Numa gravação "
                                "real no bl_lava, a XP foi só uns %s a %s disso") % (
                    dec("%.0f%%" % (100 * lo)), dec("%.0f%%" % (100 * hi)))
                text += (_(": por hora, algo entre %s e %s.") % (amount(r["per_hour"] * lo), amount(r["per_hour"] * hi))
                         if r["per_hour"] else ".")
            else:
                text += " " + _("Atenção: no LATAM estes monstros são de outra versão, e a XP deles aqui pode estar bem "
                                "longe da real.")
            color = win.c["mid"]
        self.map_result.configure(text=text, fg=color)
        rows = [dict(key=x["mob"], name=x["name"], lv=x["lv"], share_txt=dec("%.0f%%" % (100 * x["share"])),
                     pen_txt="%d%%" % x["pen"], each_txt=num(x["per_kill"])) for x in r["mobs"]]
        self.map_table.set_rows(rows, lambda row: row["key"])
        note = {"seus": _("Mistura do mapa: os seus abates lá."),
                "rathena": _("Mistura do mapa: quantos nascem de cada monstro (rAthena).")}.get(
            r["source"], _("Mistura do mapa: quantos nascem de cada monstro (a lista do /navi do jogo)."))
        if r["unknown"] > 0.05:
            note += " " + _("%s dos monstros dele não têm XP no programa (ficaram de fora).") % dec(
                "%.0f%%" % (100 * r["unknown"]))
        if bio and r.get("measured"):
            note += " " + _("Biosfera: esta conta usa a XP medida no LATAM nas suas caçadas (a nossa tabela é a coreana, "
                            "de outra versão, que rende bem mais).")
        elif bio and r.get("latam_other"):
            ours = sorted({a for _m, a, _b in r["latam_other"]})
            theirs = sorted({b for _m, _a, b in r["latam_other"]})
            note += " " + _("Por que a Biosfera é diferente: no LATAM ela é a versão de antes da reforma coreana de agosto "
                            "de 2022 (%d monstros deste mapa têm outro nível lá: %s no jogo, %s na nossa tabela; e uns 3 "
                            "milhões de HP, contra 21 a 31 milhões na coreana). A nossa tabela de XP é a de depois da "
                            "reforma, que aumentou muito a XP. A faixa de %s a %s vem de uma gravação de 1 minuto no "
                            "bl_lava (17 abates) e varia com o evento do servidor daquele dia, que o replay não mostra. "
                            "Para medir de verdade: cace 10 minutos ou mais num mapa da Biosfera com o programa aberto e, "
                            "ao parar, comece outra gravação logo em seguida (as duas juntas dão a XP exata). Daí em "
                            "diante o simulador usa a sua medida, que vale só para aquele mapa: a previsão dos outros "
                            "mapas não muda.") % (len(r["latam_other"]), _span(theirs), _span(ours),
                                                  dec("%.0f%%" % (100 * lo)), dec("%.0f%%" % (100 * hi)))
        elif r.get("latam_other"):
            ours = sorted({a for _m, a, _b in r["latam_other"]})
            theirs = sorted({b for _m, _a, b in r["latam_other"]})
            note += " " + _("No LATAM, %d monstros deste mapa têm outro nível (%s no jogo, %s na nossa tabela de XP, que "
                            "vem da versão coreana): lá eles são de outra versão, e a XP deles pode não bater. Uma caçada "
                            "sua lá, com o programa aberto, faz o simulador usar a sua medida.") % (
                len(r["latam_other"]), _span(theirs), _span(ours))
        note += " " + _("Num mapa de monstros mais fortes os abates por minuto costumam cair: o simulador mantém os "
                        "seus. A penalidade de nível e o spotlight são os de cada monstro; a correção, a medida no "
                        "mapa (se houver).")
        self.map_note.configure(text=note)

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

        parts = xp.recent_parts(c, cfg)        # o mesmo trecho do "Até o próximo nível" lá de cima
        # a parte que vem do fim da gravação anterior (reiniciou para calibrar) muda na mesma proporção do recorte
        scale = (sim["xp"] / base["xp"]) if over and base["xp"] and sim["xp"] is not None else 1.0

        def eta(o):
            if parts is None:
                return "—"
            recent, more, more_ms = parts
            got = (xp.simulate(c, cfg, recent, o)["xp"] or 0.0) if recent else 0.0
            ms = (xp.active_ms(c, recent) if recent else 0.0) + more_ms
            rate = (got + more * (scale if o else 1.0)) * 60000.0 / ms if ms > 0 else 0.0   # o mesmo ritmo de caça
            ms, _left = xp.time_to_level(c, cfg, rate) if rate > 0 else (None, None)
            return xp.span_text(ms) if ms else ("—" if ms is None else _("a qualquer momento"))

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
        self.refresh_map(c, amount, over)
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
