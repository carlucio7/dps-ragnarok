# -*- coding: utf-8 -*-
"""Aba "Linha do tempo" da análise: curvas e marcações da luta sobrepostas no mesmo eixo de tempo.

Em cima, as curvas (DPS do grupo e de cada jogador, HP estimado do chefe, dano recebido); embaixo, uma faixa
por marcação (Garra Sombria, Pólen, Avanço Sísmico e Dor Máxima no chefe, mortes, skills do chefe, dano
refletido...). Arrastar no gráfico ou girar a roda do mouse aproxima; duplo clique volta para a luta toda.
A lista embaixo mostra cada evento com décimo de segundo; clicar num evento marca o instante no gráfico.
"""

import bisect
import tkinter as tk
from tkinter import ttk

import analysis as an
import timeline as tl
from analysis_ui import HpPicker, ScrollFrame, Table, _lum, _mix, _nice
from fmt import dec, dur, full, num
from i18n import _

LANE_H = 20                   # altura de cada faixa (antes do zoom da janela); encolhe até LANE_MIN
LANE_MIN = 13
PLOT_MIN = 120                # as curvas ficam com pelo menos essa altura
SMOOTH = [(0, _("sem média")), (1000, _("média de 1 s")), (3000, _("média de 3 s")), (5000, _("média de 5 s"))]
TIME_STEPS = (100, 200, 500, 1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000, 300000)
CURVES = [("group", _("DPS do grupo")), ("hp", _("HP do chefe (estimado)")), ("taken", _("Dano recebido pelo grupo"))]
MIN_VIEW_MS = 1000


def ink(win, color):
    """Cor para texto: no tema claro, as cores vivas (verde, amarelo, ciano) escurecem para dar para ler."""
    return color if _lum(win.c["bg"]) < 0.5 else _mix(color, win.c["fg"], 0.45)


def when(t, tenths=True):
    """00:22,1"""
    return dur(t) + (dec(".%d" % (int(t) % 1000 // 100)) if tenths else "")


def _secs(ms):
    return dec("%.1f s" % (ms / 1000.0))


def since(starts, t, short=False):
    """Quanto tempo depois do começo da fase (e da luta) `t` aconteceu. starts: [(quando, "Fase N" ou None)]."""
    if not starts:
        return ""
    fight = starts[0][0]
    if t < fight:
        return ("-" + _secs(fight - t)) if short else _("%s antes do começo da luta") % _secs(fight - t)
    at, label = [s for s in starts if s[0] <= t][-1]
    if short:
        return "%s +%s" % (label, _secs(t - at)) if label else "+" + _secs(t - fight)
    if label and at != fight:
        return _("%s depois do começo da %s (%s de luta)") % (_secs(t - at), label, _secs(t - fight))
    if label:
        return _("%s depois do começo da %s") % (_secs(t - at), label)
    return _("%s de luta") % _secs(t - fight)


class TimelineChart(tk.Canvas):
    def __init__(self, parent, win, on_click=None):
        super().__init__(parent, highlightthickness=0, bd=0, bg=win.c["panel"], cursor="crosshair")
        self.win = win
        self.on_click = on_click      # clique sem arrastar: instante escolhido
        self.full = None              # (início, fim) da luta
        self.view = None              # trecho visível
        self.curves = []              # dict(name, color, points, axis="dps"|"pct", kind="rate"|"step", width)
        self.lanes = []               # faixas ligadas (ver timeline.build)
        self.marks = []               # (t, rótulo): fases e clímax
        self.starts = []              # (t, "Fase N" ou None): começo de cada fase, para "x s depois do começo"
        self.smooth = 3000
        self.focus = None             # instante destacado (evento clicado na lista)
        self.hover = None
        self.drag = None
        self.layout = None
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Double-Button-1>", lambda e: self.reset_view())
        self.bind("<MouseWheel>", self._wheel)

    # ------------------------------------------------------------ dados

    def set(self, full, curves, lanes, marks, smooth, keep_view=False, starts=()):
        if not keep_view or self.full != full or self.view is None:
            self.view = full
        self.full = full
        self.curves, self.lanes, self.marks, self.smooth = curves, lanes, marks, smooth
        self.starts = list(starts)
        self.redraw()

    def reset_view(self):
        if self.full:
            self.view = self.full
            self.redraw()

    def show_time(self, t):
        """Marca o instante e, se ele estiver fora do trecho visível, centraliza nele."""
        self.focus = t
        if self.view and not self.view[0] <= t <= self.view[1]:
            span = self.view[1] - self.view[0]
            a = max(self.full[0], min(t - span / 2, self.full[1] - span))
            self.view = (a, a + span)
        self.redraw()

    # ------------------------------------------------------------ geometria

    def _z(self):
        return self.win.dpi * self.win.zoom

    def _layout(self):
        d, f = self._z(), self.win.f["small"]
        W, H = self.winfo_width(), self.winfo_height()
        label_w = max([f.measure(l["name"]) for l in self.lanes] + [f.measure("000,0M")]) + 14 * d
        pct = any(cv["axis"] == "pct" for cv in self.curves)
        legend = 20 * d if self.curves else 0
        x0, x1 = label_w, W - (44 * d if pct else 14 * d)
        y0 = 8 * d + legend
        axis = 24 * d
        n = len(self.lanes)
        room = H - axis - y0 - PLOT_MIN * d - 8 * d
        lane_h = max(LANE_MIN * d, min(LANE_H * d, room / n)) if n else 0
        y1 = H - axis - n * lane_h - (8 * d if n else 0)
        y1 = max(y0 + 40 * d, y1)
        return dict(x0=x0, x1=x1, y0=y0, y1=y1, lanes_y=y1 + 8 * d, lane_h=lane_h, H=H, W=W, d=d, pct=pct,
                    legend=legend)

    def x_of(self, t):
        L = self.layout
        a, b = self.view
        return L["x0"] + (t - a) * (L["x1"] - L["x0"]) / max(1, b - a)

    def t_of(self, x):
        L = self.layout
        a, b = self.view
        x = min(max(x, L["x0"]), L["x1"])
        return a + (x - L["x0"]) * (b - a) / max(1, L["x1"] - L["x0"])

    # ------------------------------------------------------------ desenho

    def _bucket(self):
        a, b = self.view
        width = max(50, self.layout["x1"] - self.layout["x0"])
        want = (b - a) / (width / 3.0)
        return next((s for s in TIME_STEPS if s >= want), TIME_STEPS[-1])

    def _values(self, cv, ts, bucket):
        if cv["kind"] == "step":
            times = [p[0] for p in cv["points"]]
            out = []
            for t in ts:
                i = bisect.bisect_right(times, t + bucket) - 1
                out.append(cv["points"][i][1] if i >= 0 else cv["points"][0][1])
            return out
        # perto, a média encolhe junto: com 3 s de média não daria para ver o que aconteceu em 0,5 s
        window = max(bucket, min(self.smooth, (self.view[1] - self.view[0]) / 12.0))
        return tl.series(cv["points"], ts[0], ts[-1], bucket, window)[1]

    def redraw(self):
        self.delete("all")
        c, f = self.win.c, self.win.f
        W, H = self.winfo_width(), self.winfo_height()
        if W < 80 or H < 80:
            return
        if not self.full:
            self.create_text(W / 2, H / 2, text=_("Escolha uma luta contra chefe."), fill=c["muted"], font=f["text"])
            return
        L = self.layout = self._layout()
        d, x0, x1, y0, y1 = L["d"], L["x0"], L["x1"], L["y0"], L["y1"]
        a, b = self.view
        bucket = self._bucket()
        ts = list(range(int(a), int(b) + 1, bucket)) or [int(a)]
        series = [(cv, self._values(cv, ts, bucket)) for cv in self.curves]
        top = max([max(v) for cv, v in series if cv["axis"] == "dps" and v] + [1])
        step = _nice(top / 4)
        ymax = step * max(1, -(-top // step))

        def yv(v, axis):
            frac = v if axis == "pct" else v / ymax
            return y1 - frac * (y1 - y0)

        # grade, eixo do DPS (esquerda) e do HP (direita)
        for i in range(int(ymax // step) + 1):
            y = yv(i * step, "dps")
            self.create_line(x0, y, x1, y, fill=c["grid"])
            self.create_text(x0 - 6 * d, y, text=num(i * step), anchor="e", fill=c["muted"], font=f["small"])
        if L["pct"]:
            for p in (0, 25, 50, 75, 100):
                self.create_text(x1 + 6 * d, yv(p / 100.0, "pct"), text="%d%%" % p, anchor="w", fill=c["muted"],
                                 font=f["small"])
        # eixo do tempo (com décimos quando o trecho é curto)
        bottom = L["lanes_y"] + len(self.lanes) * L["lane_h"]
        tick = next((s for s in TIME_STEPS if s >= (b - a) / max(2, (x1 - x0) / (78 * d))), TIME_STEPS[-1])
        t = a - a % tick + (tick if a % tick else 0)
        while t <= b:
            x = self.x_of(t)
            self.create_line(x, y0, x, bottom, fill=_mix(c["panel"], c["grid"], 0.45))
            self.create_text(x, bottom + 5 * d, text=when(t, tick < 1000), anchor="n", fill=c["muted"],
                             font=f["small"])
            t += tick
        # faixas
        lh = L["lane_h"]
        for i, lane in enumerate(self.lanes):
            ly = L["lanes_y"] + i * lh
            color = lane["color"] or c["fg"]
            self.create_rectangle(x0, ly + 1.5 * d, x1, ly + lh - 1.5 * d, fill=c["track"], outline="")
            self.create_text(x0 - 6 * d, ly + lh / 2, text=lane["name"], anchor="e", fill=ink(self.win, color),
                             font=f["small"])
            if lane["kind"] == "span":
                for item in lane["items"]:
                    s, e = item[0], item[1]
                    if e < a or s > b:
                        continue
                    sx, ex = max(x0, self.x_of(s)), min(x1, self.x_of(e))
                    self.create_rectangle(sx, ly + 3.5 * d, max(sx + 2, ex), ly + lh - 3.5 * d,
                                          fill=_mix(c["panel"], color, 0.8), outline=c["panel"])
                    # valor do trecho (redução do Alívio), quando cabe
                    if len(item) > 2 and ex - sx > f["small"].measure(item[2]) + 6 * d:
                        self.create_text((sx + ex) / 2, ly + lh / 2, text=item[2], fill=c["bg"], font=f["small"])
            else:
                self._points(lane, ly, lh, a, b)
        # marcas de fase e clímax (rótulos que se encostariam descem uma linha)
        ends = []
        for t, label in self.marks:
            if a <= t <= b:
                x = self.x_of(t)
                self.create_line(x, y0, x, bottom, fill=c["fg"], dash=(4, 3))
                row = next((k for k, e in enumerate(ends) if e < x), len(ends))
                w = f["small"].measure(label) + 10 * d
                if row == len(ends):
                    ends.append(x + w)
                else:
                    ends[row] = x + w
                self.create_text(x + 4 * d, y0 + 2 * d + row * 14 * d, text=label, anchor="nw", fill=c["fg"],
                                 font=f["small"])
        # curvas
        for cv, vals in series:
            pts = []
            for t, v in zip(ts, vals):
                pts += [self.x_of(t + bucket / 2), yv(v, cv["axis"])]
            if len(pts) >= 4:
                self.create_line(*pts, fill=cv["color"], width=max(1, cv.get("width", 2) * d))
        # legenda das curvas
        lx = x0
        for cv in self.curves:
            w = f["small"].measure(cv["name"]) + 30 * d
            if lx + w > x1:
                break
            self.create_rectangle(lx, 6 * d, lx + 10 * d, 16 * d, fill=cv["color"], outline="")
            self.create_text(lx + 15 * d, 11 * d, text=cv["name"], anchor="w", fill=c["fg"], font=f["small"])
            lx += w
        if self.focus is not None and a <= self.focus <= b:
            x = self.x_of(self.focus)
            self.create_line(x, y0, x, bottom, fill=c["accent"], width=max(1, 2 * d))
        if self.drag is not None and self.drag[1] is not None:
            sa, sb = sorted((self.drag[0], self.drag[1]))
            self.create_rectangle(sa, y0, sb, bottom, outline=c["accent"], fill="", width=max(1, d))
        self.hover = None
        self._ts, self._series, self._bucket_ms = ts, series, bucket

    def _points(self, lane, ly, lh, a, b):
        c, f, d = self.win.c, self.win.f, self._z()
        mid = ly + lh / 2
        r = min(3.5 * d, lh / 3.5)
        color = lane["color"] or c["fg"]
        items = [e for e in lane["items"] if a <= e["t"] <= b]
        biggest = max([e["value"] or 0 for e in items] + [1])
        xs = [self.x_of(e["t"]) for e in items]
        for k, e in enumerate(items):
            x = xs[k]
            if e["kind"] == "death":
                col = self.win.color_of(e["aid"])
                self.create_polygon(x, mid - r * 1.3, x + r, mid, x, mid + r * 1.3, x - r, mid, fill=col,
                                    outline=c["live"], width=max(1, d))
            elif e["kind"] == "res":
                col = self.win.color_of(e["aid"])
                self.create_oval(x - r * 0.8, mid - r * 0.8, x + r * 0.8, mid + r * 0.8, outline=col, width=max(1, d))
            elif e["kind"] == "reflect":
                h = (lh / 2 - 3 * d) * max(0.35, (e["value"] or 0) / biggest)
                self.create_rectangle(x - 2 * d, mid - h, x + 2 * d, mid + h, fill=color, outline="")
            elif e["kind"] in ("strong", "claw", "elo"):
                col = self.win.color_of(e["aid"]) if e["aid"] is not None else color
                self.create_oval(x - r, mid - r, x + r, mid + r, fill=col, outline=color, width=max(1, d))
            else:
                self.create_line(x, ly + 3.5 * d, x, ly + lh - 3.5 * d, fill=color, width=max(1, 2 * d))
                # o nome da skill do chefe, só quando cabe antes da próxima
                nxt = xs[k + 1] if k + 1 < len(xs) else self.layout["x1"]
                if nxt - x > f["small"].measure(e["what"]) + 10 * d:
                    self.create_text(x + 3 * d, mid, text=e["what"], anchor="w", fill=c["muted"], font=f["small"])

    # ------------------------------------------------------------ mouse

    def _set_hover(self, x):
        self.hover = x
        self.delete("hover")
        if x is None or not self.full or not self.layout:
            return
        c, f, d = self.win.c, self.win.f, self._z()
        L = self.layout
        if not L["x0"] <= x <= L["x1"]:
            return
        t = self.t_of(x)
        bottom = L["lanes_y"] + len(self.lanes) * L["lane_h"]
        self.create_line(x, L["y0"], x, bottom, fill=c["muted"], tags="hover")
        lines = [(when(t), c["muted"])]
        rel = since(self.starts, t)
        if rel:
            lines.append((rel, c["muted"]))
        i = max(0, min(len(self._ts) - 1, int((t - self._ts[0]) // self._bucket_ms)))
        for cv, vals in self._series:
            if i < len(vals):
                v = vals[i]
                txt = "%d%%" % round(v * 100) if cv["axis"] == "pct" else full(round(v)) + "/s"
                lines.append(("%s: %s" % (cv["name"], txt), ink(self.win, cv["color"])))
        tol = max(100, (self.view[1] - self.view[0]) * 10 * d / max(1, L["x1"] - L["x0"]))
        for lane in self.lanes:
            if lane["kind"] == "span":
                hit = next((item for item in lane["items"] if item[0] <= t <= item[1]), None)
                if hit is not None:
                    text = "● " + lane["name"] + ((" " + hit[2]) if len(hit) > 2 else "")
                    lines.append((text, ink(self.win, lane["color"] or c["fg"])))
        near = [e for lane in self.lanes if lane["kind"] == "point" for e in lane["items"] if abs(e["t"] - t) <= tol]
        for e in sorted(near, key=lambda e: e["t"])[:10]:
            col = ink(self.win, self.win.color_of(e["aid"])) if e["aid"] is not None else c["fg"]
            who = (e["who"] + " ") if e["who"] else ""
            lines.append(("%s  %s%s%s" % (when(e["t"]), who, e["what"], (" — " + e["detail"]) if e["detail"] else ""),
                          col))
        w = max(f["small"].measure(s) for s, _c in lines) + 16 * d
        h = len(lines) * 16 * d + 8 * d
        bx = x + 12 * d if x + 12 * d + w < L["W"] - 4 * d else max(2, x - 12 * d - w)
        by = L["y0"] + 4 * d
        self.create_rectangle(bx, by, bx + w, by + h, fill=c["tip"], outline=c["grid"], tags="hover")
        for k, (s, col) in enumerate(lines):
            self.create_text(bx + 8 * d, by + 4 * d + k * 16 * d, text=s, anchor="nw", font=f["small"], fill=col,
                             tags="hover")

    def _motion(self, e):
        if self.drag is not None:
            return
        self._set_hover(e.x)

    def _press(self, e):
        if self.layout and self.layout["x0"] <= e.x <= self.layout["x1"]:
            self.drag = [e.x, None]

    def _drag(self, e):
        if self.drag is not None:
            self.drag[1] = min(max(e.x, self.layout["x0"]), self.layout["x1"])
            self.redraw()

    def _release(self, e):
        if self.drag is None:
            return
        start, end = self.drag
        self.drag = None
        if end is not None and abs(end - start) > 6:
            ta, tb = sorted((self.t_of(start), self.t_of(end)))
            if tb - ta < MIN_VIEW_MS:
                mid = (ta + tb) / 2
                ta, tb = mid - MIN_VIEW_MS / 2, mid + MIN_VIEW_MS / 2
            self.view = (ta, tb)
        elif self.on_click:
            self.focus = self.t_of(start)
            self.on_click(self.focus)
        self.redraw()

    def _wheel(self, e):
        if e.state & 0x4 or not self.full or not self.layout:
            return None                           # Ctrl + roda: tamanho da janela
        a, b = self.view
        t = self.t_of(e.x)
        k = 0.8 if e.delta > 0 else 1.25
        span = min(self.full[1] - self.full[0], max(MIN_VIEW_MS, (b - a) * k))
        frac = (t - a) / max(1, b - a)
        na = max(self.full[0], min(t - frac * span, self.full[1] - span))
        self.view = (na, na + span)
        self.redraw()
        return "break"


class TimelineTab:
    """Monta a aba e liga os controles: luta, média, curvas, jogadores, faixas e a lista de eventos."""

    def __init__(self, win, nb):
        self.win = win
        c = win.c
        self.key = None
        self.data = None
        self.cache = (None, None)
        self.on = {}                  # faixa/curva -> ligada (fica igual de uma luta para outra)
        self.players_on = None        # jogadores com curva própria (None = só quem gravou)
        self.panel_sig = None
        tab = tk.Frame(nb, bg=c["panel"])
        nb.add(tab, text=_("Linha do tempo"))
        self.frame = tab
        bar = tk.Frame(tab, bg=c["panel"])
        bar.pack(fill="x", padx=10, pady=(10, 4))
        win.label(bar, _("Luta:"), color="muted", bg="panel").pack(side="left")
        self.fight_var = tk.StringVar(win.top, "")
        self.fight_box = ttk.Combobox(bar, textvariable=self.fight_var, state="readonly", width=56,
                                      style="An.TCombobox", font=win.f["text"])
        self.fight_box.pack(side="left", padx=6)
        self.fight_box.bind("<<ComboboxSelected>>", lambda e: self.pick())
        self.fights = {}
        self.smooth_var = tk.StringVar(win.top, SMOOTH[2][1])
        sm = ttk.Combobox(bar, textvariable=self.smooth_var, values=[s[1] for s in SMOOTH], width=13,
                          state="readonly", style="An.TCombobox", font=win.f["text"])
        sm.pack(side="left", padx=(10, 0))
        sm.bind("<<ComboboxSelected>>", lambda e: self.draw())
        self.hp = HpPicker(bar, win)
        ttk.Button(bar, text=_("Ver a luta toda"), style="An.TButton",
                   command=lambda: self.chart.reset_view()).pack(side="right")
        win.label(tab, _("Arraste no gráfico ou gire a roda do mouse para aproximar; duplo clique volta. Passe o "
                         "mouse para ver o que acontecia em cada instante."), "small", "muted", "panel",
                  anchor="w").pack(fill="x", padx=12)
        pw = ttk.PanedWindow(tab, orient="vertical", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True, pady=(4, 0))
        top = tk.Frame(pw, bg=c["panel"])
        bottom = tk.Frame(pw, bg=c["panel"])
        pw.add(top, weight=3)
        pw.add(bottom, weight=2)
        side_box = tk.Frame(top, bg=c["panel"], width=int(230 * win.dpi))
        side_box.pack(side="right", fill="y", padx=(0, 6))
        side_box.pack_propagate(False)
        self.side = ScrollFrame(side_box, win).inner
        self.chart = TimelineChart(top, win, on_click=self.time_picked)
        self.chart.pack(side="left", fill="both", expand=True, padx=(4, 6), pady=(2, 4))
        win.section(bottom, _("Eventos (só os das marcações ligadas)"))
        self.table = Table(bottom, win, [
            ("time", _("Tempo"), 70, "e", "text"), ("since", _("Desde o começo"), 110, "w", "text"),
            ("what", _("O quê"), 230, "w", "text"),
            ("who", _("Quem"), 140, "w", "text"), ("detail", _("Detalhe"), 330, "w", "text")],
            height=6, on_select=self.event_picked, swatch=True)
        self.table.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ------------------------------------------------------------ escolha da luta

    def pick(self):
        self.key = self.fights.get(self.fight_var.get())
        self.win.refresh(force=True)

    def refresh(self, c):
        rng = self.win.rng
        items = tl.fights(c, rng)
        self.fights = dict(items)
        labels = [lb for lb, _k in items]
        if list(self.fight_box["values"]) != labels:
            self.fight_box["values"] = labels
        keys = [k for _lb, k in items]
        if self.key not in keys:
            self.key = keys[0] if keys else None
        label = next((lb for lb, k in items if k == self.key), "")
        if self.fight_var.get() != label:
            self.fight_var.set(label)
        if self.key is None:
            self.data = None
            self.hp.sync(c, None)
            self.chart.set(None, [], [], [], 0)
            self.table.set_rows([], lambda r: 0)
            return
        self.hp.sync(c, self.key)
        sig = (id(c), c.version, self.key, rng, an.hp_choice(c, self.key))
        if self.cache[0] != sig:
            self.cache = (sig, tl.build(c, self.key, rng))
        keep = self.data is not None and self.data["key"] == self.key
        self.data = self.cache[1]
        if self.data is None:
            return
        for aid in self.data["players"]:
            self.win.color_of(aid)
        if self.players_on is None:
            self.players_on = {c.me} if c.me in self.data["players"] else set(self.data["players"][:1])
        self.build_side(c)
        self.draw(keep_view=keep)

    # ------------------------------------------------------------ controles do lado

    def build_side(self, c):
        d = self.data
        sig = (d["key"], tuple(l["key"] for l in d["lanes"]), tuple(d["players"]))
        if sig == self.panel_sig:
            return
        self.panel_sig = sig
        for w in self.side.winfo_children():
            w.destroy()
        win, col = self.win, self.win.c

        def head(text):
            win.label(self.side, text, "head", bg="panel", anchor="w").pack(fill="x", padx=6, pady=(8, 2))

        def check(key, text, color, default, store):
            var = tk.BooleanVar(win.top, store.get(key, default) if isinstance(store, dict) else key in store)
            color = ink(win, color)
            cb = tk.Checkbutton(self.side, text=text, variable=var, anchor="w", font=win.f["text"], fg=color,
                                bg=col["panel"], activebackground=col["panel"], activeforeground=color,
                                selectcolor=col["btn"], bd=0, highlightthickness=0,
                                command=lambda: self.toggle(key, var.get(), store))
            cb.pack(fill="x", padx=8)

        head(_("Curvas"))
        for key, name in CURVES:
            if key == "hp" and not d["hp_known"]:
                continue
            check(key, name, col["fg"] if key == "group" else (col["accent"] if key == "hp" else col["live"]),
                  key in ("group", "hp"), self.on)
        head(_("DPS de cada jogador"))
        for aid in d["players"]:
            mark = "" if aid in d["party"] or aid == c.me else _(" (fora do grupo)")
            check(aid, c.name_of(aid) + mark, win.color_of(aid), False, self.players_on)
        spans = [l for l in d["lanes"] if l["kind"] == "span"]
        if spans:
            head(_("No chefe"))
            for lane in spans:
                check(lane["key"], lane["name"], lane["color"], lane["on"], self.on)
        points = [l for l in d["lanes"] if l["kind"] == "point"]
        if points:
            head(_("Eventos"))
            for lane in points:
                check(lane["key"], lane["name"], lane["color"] or col["fg"], lane["on"], self.on)
        head(_("Marcações de fase"))
        check("marks", _("Fases e clímax"), col["fg"], True, self.on)

    def toggle(self, key, value, store):
        if isinstance(store, dict):
            store[key] = value
        elif value:
            store.add(key)
        else:
            store.discard(key)
        self.draw(keep_view=True)

    # ------------------------------------------------------------ desenho

    def lane_on(self, lane):
        return self.on.get(lane["key"], lane["on"])

    def draw(self, keep_view=True):
        d = self.data
        if d is None:
            return
        c = self.win.c
        curves = []
        if self.on.get("group", True):
            curves.append(dict(name=_("DPS do grupo"), color=c["fg"], points=[(t, v) for t, _a, v in d["out"]],
                               axis="dps", kind="rate", width=2.4))
        for aid in d["players"]:
            if aid in self.players_on:
                curves.append(dict(name=d["names"].get(aid, "?"), color=self.win.color_of(aid),
                                   points=[(t, v) for t, a, v in d["out"] if a == aid], axis="dps", kind="rate",
                                   width=1.6))
        if self.on.get("taken", False):
            curves.append(dict(name=_("Dano recebido pelo grupo"), color=c["live"],
                               points=[(t, v) for t, _a, v in d["taken"]], axis="dps", kind="rate", width=1.6))
        if self.on.get("hp", True) and d["hp_known"]:
            level = " · ".join(filter(None, (d["hp_label"], num(d["hp_max"]))))      # "Nível 1 · 800M"
            curves.append(dict(name=_("HP do chefe (%s)") % level, color=c["accent"], points=d["hp"], axis="pct",
                               kind="step", width=1.8))
        lanes = [l for l in d["lanes"] if self.lane_on(l)]
        marks = d["marks"] if self.on.get("marks", True) else []
        smooth = next((ms for ms, lb in SMOOTH if lb == self.smooth_var.get()), 3000)
        self.chart.set((d["t0"], d["t1"]), curves, lanes, marks, smooth, keep_view=keep_view, starts=d["starts"])
        # lista de eventos das marcações ligadas
        on = {l["key"] for l in lanes}
        rows = [e for e in d["events"] + d["lane_events"] if e["lane"] in on]
        rows.sort(key=lambda e: e["t"])
        colors = {l["key"]: l["color"] or c["fg"] for l in d["lanes"]}
        for i, e in enumerate(rows):
            e["time"] = when(e["t"])
            e["since"] = since(d["starts"], e["t"], short=True)
            e["row"] = "%d|%s|%s" % (e["t"], e["lane"], i)
        self.table.set_rows(rows, lambda e: e["row"], None,
                            lambda e: self.win.color_of(e["aid"]) if e["aid"] is not None else colors.get(e["lane"], c["fg"]))

    def event_picked(self, row):
        if row is not None:
            self.chart.show_time(row["t"])

    def time_picked(self, t):
        """Clique no gráfico: a lista pula para o primeiro evento daquele instante em diante."""
        rows = sorted(self.table.rows.values(), key=lambda r: r["t"])
        row = next((r for r in rows if r["t"] >= t - 150), rows[-1] if rows else None)
        if row is not None:
            tree = self.table.tree
            tree.selection_set(row["row"])
            tree.see(row["row"])
