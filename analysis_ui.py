# -*- coding: utf-8 -*-
"""Janela de análise completa (Resumo, Jogadores, Monstros, Análise de DPS, Buffs, Mortes, Testes e
Dedo Duro), atualizada ao vivo.

Ctrl + roda (ou Ctrl + / −) muda o tamanho de tudo; o layout se reorganiza com a largura.
"""

import collections
import re
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import simpledialog, ttk

import analysis as an
import dedoduro as dd
import testes
from fmt import num, full, dur, dec
from i18n import _

# cores bem diferentes entre si; cada jogador fica com a mesma cor em todas as tabelas e gráficos
PALETTE = ["#ff7a59", "#5b9cff", "#4ade80", "#c084fc", "#fbbf24", "#22d3ee", "#f472b6",
           "#a3e635", "#d6a38f", "#94a3b8", "#e11d48", "#2dd4bf"]
OTHERS = "#7c7f8a"
BUCKETS = [(1000, "1 s"), (2000, "2 s"), (5000, "5 s"), (10000, "10 s")]
SESSION, LATEST = _("Sessão inteira"), _("Último encontro (acompanha)")
ZOOMS = (0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6)
FONT_PT = dict(text=10, small=9, head=10, title=13, big=15, tile=17)


def _mix(a, b, t):
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * t)) for x, y in zip(pa, pb))


def _fmt(kind, v):
    if v is None or v == "":
        return "—"
    if kind == "big":
        return full(v)
    if kind == "int":
        return "%d" % v
    if kind == "pct":
        return dec("%.1f%%" % (v * 100))
    if kind == "ms":
        return "%d ms" % round(v) if v else "—"
    if kind == "dur":
        return dur(v)
    if kind == "f2":
        return dec("%.2f" % v)
    return str(v)


class Table:
    """ttk.Treeview com colunas formatadas, ordenação por clique, atualização sem piscar
    e (opcional) um quadradinho com a cor do jogador na primeira coluna."""

    def __init__(self, parent, win, columns, height=8, on_select=None, swatch=False, multi=False):
        self.win = win
        self.columns = columns               # (chave, título, largura, alinhamento, tipo)
        self.on_select = on_select
        self.swatch = swatch
        self.sort = None                     # (chave, decrescente)
        self.rows = {}
        self.key_fn = lambda r: id(r)
        self.tag_fn = self.color_fn = None
        frame = tk.Frame(parent, bg=win.c["panel"])
        self.frame = frame
        keys = [c[0] for c in columns]
        self.tree = ttk.Treeview(frame, columns=keys, show="tree headings" if swatch else "headings",
                                 height=height, style="An.Treeview", selectmode="extended" if multi else "browse")
        for key, title, _width, anchor, _kind in columns:
            self.tree.heading(key, text=title, anchor=anchor, command=lambda k=key: self.sort_by(k))
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview, style="An.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("me", foreground=win.c["accent"])
        self.tree.tag_configure("warn", foreground=win.c["live"])
        self.tree.tag_configure("good", foreground=win.c["good"])
        self.tree.tag_configure("bad", foreground=win.c["bad"])
        self.tree.tag_configure("mid", foreground=win.c["mid"])
        self.tree.tag_configure("muted", foreground=win.c["muted"])
        self.tree.tag_configure("odd", background=win.c["row_alt"])
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self._kinds = {c[0]: c[4] for c in columns}
        self.rescale()
        win.tables.append(self)

    def rescale(self):
        z = self.win.dpi * self.win.zoom
        if self.swatch:
            self.tree.column("#0", width=int(26 * z), minwidth=int(26 * z), stretch=False, anchor="center")
        for key, _title, width, anchor, kind in self.columns:
            self.tree.column(key, width=int(width * z), minwidth=int(36 * z), anchor=anchor,
                             stretch=key == self.columns[0][0] or kind == "text")

    def show(self, keys, titles=None):
        """Mostra só estas colunas (na ordem original) e troca títulos (ex.: Fase 1 / Clímax)."""
        if titles:
            self.columns = [(k, titles.get(k, t), w, a, kind) for k, t, w, a, kind in self.columns]
        keys = [c[0] for c in self.columns if c[0] in keys]
        if tuple(self.tree["displaycolumns"]) != tuple(keys):
            self.tree["displaycolumns"] = keys

    def pack(self, **kw):
        self.frame.pack(**kw)

    def grid(self, **kw):
        self.frame.grid(**kw)

    def sort_by(self, key):
        if self.sort and self.sort[0] == key:
            self.sort = (key, not self.sort[1])
        else:
            self.sort = (key, self._kinds[key] != "text")
        self._render(list(self.rows.values()))

    def set_rows(self, rows, key_fn, tag_fn=None, color_fn=None):
        self.tag_fn, self.key_fn, self.color_fn = tag_fn, key_fn, color_fn
        self.rows = {str(key_fn(r)): r for r in rows}
        self._render(rows)

    def _render(self, rows):
        if self.sort:
            k, desc = self.sort
            filled = sorted((r for r in rows if r.get(k) is not None), key=lambda r: r.get(k), reverse=desc)
            rows = filled + [r for r in rows if r.get(k) is None]         # vazios sempre por último
        for key, title, _w, _a, _kind in self.columns:
            arrow = ""
            if self.sort and self.sort[0] == key:
                arrow = " ▼" if self.sort[1] else " ▲"
            self.tree.heading(key, text=title + arrow)
        tree = self.tree
        want = [str(self.key_fn(r)) for r in rows]
        for iid in set(tree.get_children()) - set(want):
            tree.delete(iid)
        for i, (iid, r) in enumerate(zip(want, rows)):
            values = [_fmt(kind, r.get(key)) for key, _t, _w, _a, kind in self.columns]
            tags = ["odd"] if i % 2 else []
            if self.tag_fn:
                tags += self.tag_fn(r)
            kw = dict(values=values, tags=tags)
            if self.swatch and self.color_fn:
                kw["image"] = self.win.swatch(self.color_fn(r))
            if tree.exists(iid):
                tree.item(iid, **kw)
                if tree.index(iid) != i:
                    tree.move(iid, "", i)
            else:
                tree.insert("", i, iid=iid, **kw)

    def selected(self):
        sel = self.tree.selection()
        return self.rows.get(sel[0]) if sel else None

    def selected_all(self):
        return [self.rows[i] for i in self.tree.selection() if i in self.rows]

    def select(self, iid):
        """Seleciona sem rolar a lista (o ranking continua visível do topo)."""
        iid = str(iid)
        if self.tree.exists(iid) and self.tree.selection() != (iid,):
            self.tree.selection_set(iid)

    def _selected(self, _e):
        if self.on_select:
            self.on_select(self.selected())


class Tiles(tk.Frame):
    """Cartões (título, valor, detalhe) que se reorganizam conforme a largura."""

    NUMERIC = re.compile(r"^[\d.,:\s–-]+(ms|s|%)?$")

    def __init__(self, parent, win, specs, min_w=170, bg="panel", compact=False, dense=False):
        super().__init__(parent, bg=win.c[bg])
        self.win = win
        self.min_w = min_w
        self.compact = compact
        self.cells = {}
        self.order = []
        self.labels = []
        for key, title in specs:
            tight = compact or dense
            cell = tk.Frame(self, bg=win.c["tile"], padx=10 if tight else 12, pady=4 if tight else 8)
            t = win.label(cell, title.upper(), "small", "muted", "tile", anchor="w", justify="left")
            t.pack(fill="x")
            v = win.label(cell, "—", "big" if tight else "tile", "fg", "tile", anchor="w", justify="left")
            v.pack(fill="x")
            s = None
            if not compact:
                s = win.label(cell, "", "small", "muted", "tile", anchor="w", justify="left")
                s.pack(fill="x")
            self.cells[key] = (v, s)
            self.order.append(cell)
            self.labels += [x for x in (t, v, s) if x is not None]
        self.big = "big" if (compact or dense) else "tile"
        self.values = {v for v, _s in self.cells.values()}
        self.last = {}
        self.wrap = 0
        self.cols = 0
        self.width = 0
        self.bind("<Configure>", lambda e: self.reflow())

    def reflow(self):
        w = self.winfo_width()
        cols = max(1, min(len(self.order), int(w // (self.min_w * self.win.dpi * self.win.zoom))))
        if cols != self.cols:
            self.cols = cols
            pad = 6 if self.compact else 8
            for i, cell in enumerate(self.order):
                cell.grid(row=i // cols, column=i % cols, sticky="nsew", padx=(0, 8), pady=(0, pad))
            for c in range(len(self.order)):
                self.columnconfigure(c, weight=1 if c < cols else 0, uniform="t" if c < cols else "")
        if w != self.width:
            # textos longos quebram linha em vez de serem cortados
            self.width = w
            self.wrap = max(60, int(w / self.cols - 32 * self.win.dpi))
            for lbl in self.labels:
                if lbl not in self.values:
                    lbl.configure(wraplength=self.wrap)
            for key, args in self.last.items():
                self.put(key, *args)

    def put(self, key, value, sub="", color=None, short=None):
        self.last[key] = (value, sub, color, short)
        v, s = self.cells[key]
        textual = not self.NUMERIC.match(value) and value != "—"     # nome de skill etc.: fonte menor
        font = self.win.f["head" if textual else self.big]
        if not textual and short and self.wrap and font.measure(value) > self.wrap:
            value = short                                           # 844.845.246 -> 845M
        v.configure(text=value, fg=color or self.win.c["fg"], font=font,
                    wraplength=self.wrap if textual else 0)
        if s is not None:
            s.configure(text=sub)


class ScrollFrame:
    """Área com barra de rolagem vertical (a roda do mouse rola, exceto sobre tabelas)."""

    def __init__(self, parent, win):
        self.canvas = tk.Canvas(parent, bg=win.c["panel"], highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=self.canvas.yview, style="An.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=win.c["panel"])
        self.item = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self._fit())
        self.canvas.bind("<Configure>", lambda e: self._fit())
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _fit(self):
        c = self.canvas
        need = self.inner.winfo_reqheight()
        c.itemconfigure(self.item, width=c.winfo_width(), height=max(need, c.winfo_height()))
        c.configure(scrollregion=(0, 0, c.winfo_width(), max(need, c.winfo_height())))

    def _wheel(self, e):
        if e.state & 0x4 or isinstance(e.widget, ttk.Treeview):
            return
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")


class Chart(tk.Canvas):
    """Gráfico no tempo: linhas (uma por jogador) ou barras (um jogador), com linhas extras
    (ex.: DPS móvel) e uma linha horizontal de referência (ex.: média). Passar o mouse
    mostra os valores; com `on_select`, arrastar escolhe um trecho."""

    def __init__(self, parent, win, height=230, on_select=None):
        super().__init__(parent, height=int(height * win.dpi), highlightthickness=0, bd=0, bg=win.c["panel"])
        self.win = win
        self.on_select = on_select
        self.data = None
        self.sel = None
        self.drag = None
        self.hover = None
        self.overlays = []
        self.hline = None
        self.unit = ""
        self.empty = ""
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        if on_select:
            self.bind("<ButtonPress-1>", self._press)
            self.bind("<B1-Motion>", self._drag)
            self.bind("<ButtonRelease-1>", self._release)
            self.configure(cursor="crosshair")

    def set(self, ts, bucket, series, kind="line", markers=(), sel=None, empty=_("Sem eventos de dano para exibir."),
            overlays=(), hline=None, unit=""):
        self.data = (ts, bucket, series, kind, list(markers))
        self.sel = sel
        self.empty = empty
        self.overlays = list(overlays)       # (nome, cor, valores)
        self.hline = hline                   # (valor, rótulo)
        self.unit = unit
        self.redraw()

    def _color(self, n, aid):
        return self.win.color_of(aid) if aid is not None else OTHERS

    def _z(self):
        return self.win.dpi * self.win.zoom

    def _box(self):
        d = self._z()
        legend = self._legend_rows() * 18 * d
        return 74 * d, 14 * d, self.winfo_width() - 16 * d, self.winfo_height() - 26 * d - legend

    def _legend_items(self):
        if not self.data:
            return []
        items = []
        if self.data[3] == "line":
            items += [(name, self._color(n, aid)) for n, (aid, name, _v) in enumerate(self.data[2])]
        items += [(name, col) for name, col, _v in self.overlays]
        if self.hline:
            items.append((self.hline[1], self.win.c["fg"]))
        return items

    def _legend_rows(self):
        items = self._legend_items()
        if not items:
            return 0
        f, d = self.win.f["small"], self._z()
        x, rows = 0, 1
        w = max(100, self.winfo_width() - 90 * d)
        for name, _c in items:
            item = f.measure(name) + 30 * d
            if x + item > w and x > 0:
                rows += 1
                x = 0
            x += item
        return rows

    def _span(self):
        ts, bucket = self.data[0], self.data[1]
        return ts[0], ts[-1] + bucket

    def x_of(self, t):
        x0, _y0, x1, _y1 = self._box()
        a, b = self._span()
        return x0 + (t - a) * (x1 - x0) / max(1, b - a)

    def t_of(self, x):
        x0, _y0, x1, _y1 = self._box()
        a, b = self._span()
        return a + (min(max(x, x0), x1) - x0) * (b - a) / max(1, x1 - x0)

    def redraw(self):
        self.delete("all")
        c, f, d = self.win.c, self.win.f, self._z()
        W, H = self.winfo_width(), self.winfo_height()
        if W < 60 or H < 60:
            return
        if not self.data or not self.data[0]:
            self.create_text(W / 2, H / 2, text=self.empty, fill=c["muted"], font=f["text"])
            return
        ts, bucket, series, kind, markers = self.data
        x0, y0, x1, y1 = self._box()
        top = max([max(v) for _a, _n, v in series if v] + [max(v) for _n, _c, v in self.overlays if v] +
                  ([self.hline[0]] if self.hline else []) + [1])
        step = _nice(top / 4)
        ymax = step * max(1, -(-top // step))

        def yv(v):
            return y1 - v * (y1 - y0) / ymax

        for i in range(int(ymax // step) + 1):
            y = yv(i * step)
            self.create_line(x0, y, x1, y, fill=c["grid"])
            self.create_text(x0 - 6 * d, y, text=num(i * step), anchor="e", fill=c["muted"], font=f["small"])
        a, b = self._span()
        tick = _nice_time((b - a) / max(2, (x1 - x0) / (70 * d)))
        t = a - a % tick + (tick if a % tick else 0)
        while t <= b:
            x = self.x_of(t)
            self.create_line(x, y1, x, y1 + 4 * d, fill=c["grid"])
            self.create_text(x, y1 + 6 * d, text=dur(t), anchor="n", fill=c["muted"], font=f["small"])
            t += tick
        if self.sel:
            sa, sb = self.x_of(self.sel[0]), self.x_of(self.sel[1])
            self.create_rectangle(sa, y0, sb, y1, fill=_mix(c["panel"], c["accent"], 0.16), outline=c["accent"])
        if kind == "bar":
            aid, _name, vals = series[0]
            base = self.win.color_of(aid)
            bw = max(1.0, (x1 - x0) / len(ts))
            for i, v in enumerate(vals):
                if v <= 0:
                    continue
                bx = x0 + i * bw
                inside = not self.sel or self.sel[0] <= ts[i] + bucket and ts[i] <= self.sel[1]
                color = base if inside else _mix(c["panel"], base, 0.35)
                self.create_rectangle(bx + bw * 0.12, yv(v), bx + bw * 0.88, y1, fill=color, outline="")
        else:
            for n, (aid, _name, vals) in enumerate(series):
                self._polyline(ts, bucket, vals, self._color(n, aid), yv, max(1, 2 * d))
        for _name, col, vals in self.overlays:
            self._polyline(ts, bucket, vals, col, yv, max(1, 2.2 * d))
        if self.hline:
            y = yv(self.hline[0])
            self.create_line(x0, y, x1, y, fill=c["fg"], dash=(6, 4))
        for t, label in markers:
            x = self.x_of(t)
            if x0 <= x <= x1:
                self.create_line(x, y0, x, y1, fill=c["fg"], dash=(4, 3))
                self.create_text(x + 4 * d, y0 + 2 * d, text=label, anchor="nw", fill=c["fg"], font=f["small"])
        items = self._legend_items()
        if items:
            lx, ly = x0, H - self._legend_rows() * 18 * d + 2 * d
            for name, col in items:
                item = f["small"].measure(name) + 30 * d
                if lx + item > x1 and lx > x0:
                    lx, ly = x0, ly + 18 * d
                self.create_rectangle(lx, ly + 3 * d, lx + 10 * d, ly + 13 * d, fill=col, outline="")
                self.create_text(lx + 15 * d, ly + 8 * d, text=name, anchor="w", fill=c["fg"], font=f["small"])
                lx += item
        self._draw_hover()

    def _polyline(self, ts, bucket, vals, color, yv, width):
        pts = []
        for i, v in enumerate(vals):
            pts += [self.x_of(ts[i] + bucket / 2), yv(v)]
        if len(pts) >= 4:
            self.create_line(*pts, fill=color, width=width)
        elif pts:
            r = 3 * self._z()
            self.create_oval(pts[0] - r, pts[1] - r, pts[0] + r, pts[1] + r, fill=color, outline="")

    def _bucket_at(self, x):
        if not self.data or not self.data[0]:
            return None
        x0, _y0, x1, _y1 = self._box()
        if not x0 <= x <= x1:
            return None
        ts, bucket = self.data[0], self.data[1]
        return max(0, min(len(ts) - 1, int((self.t_of(x) - ts[0]) // bucket)))

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.delete("hover")
            self._draw_hover()

    def _motion(self, e):
        self._set_hover(self._bucket_at(e.x))

    def _draw_hover(self):
        i = self.hover
        if i is None or not self.data or not self.data[0] or i >= len(self.data[0]):
            return
        c, f, d = self.win.c, self.win.f, self._z()
        ts, bucket, series, kind, _m = self.data
        x0, y0, x1, y1 = self._box()
        x = self.x_of(ts[i] + bucket / 2)
        self.create_line(x, y0, x, y1, fill=c["muted"], tags="hover")
        lines = [("%s – %s" % (dur(ts[i]), dur(ts[i] + bucket)), c["muted"])]
        vals = sorted(((v[i], n, aid, name) for n, (aid, name, v) in enumerate(series) if i < len(v)), reverse=True)
        lines += [("%s: %s%s" % (name, full(round(v)), self.unit), self._color(n, aid))
                  for v, n, aid, name in vals[:8] if v > 0 or kind == "bar"]
        lines += [("%s: %s%s" % (name, full(round(v[i])), self.unit), col) for name, col, v in self.overlays
                  if i < len(v)]
        w = max(f["small"].measure(s) for s, _c in lines) + 16 * d
        h = len(lines) * 16 * d + 8 * d
        bx = x + 10 * d if x + 10 * d + w < x1 else x - 10 * d - w
        self.create_rectangle(bx, y0 + 4 * d, bx + w, y0 + 4 * d + h, fill=c["tip"], outline=c["grid"], tags="hover")
        for k, (s, col) in enumerate(lines):
            self.create_text(bx + 8 * d, y0 + 8 * d + k * 16 * d, text=s, anchor="nw", font=f["small"],
                             fill=col if k else c["muted"], tags="hover")

    def _press(self, e):
        self.drag = e.x

    def _drag(self, e):
        if self.drag is None or not self.data or not self.data[0]:
            return
        a, b = sorted((self.t_of(self.drag), self.t_of(e.x)))
        self.sel = (a, b)
        self.redraw()

    def _release(self, e):
        if self.drag is None:
            return
        moved = abs(e.x - self.drag) > 4
        self.drag = None
        if not moved:
            self.sel = None
            self.redraw()
        if self.on_select:
            self.on_select(self.sel)


class HBars(tk.Canvas):
    """Barras horizontais: um jogador por linha (como "Dano total por jogador" do site)."""

    def __init__(self, parent, win):
        super().__init__(parent, highlightthickness=0, bd=0, bg=win.c["panel"])
        self.win = win
        self.rows = []
        self.bind("<Configure>", lambda e: self.redraw())

    def set(self, rows):
        self.rows = rows
        self.redraw()

    def redraw(self):
        self.delete("all")
        c, f, d = self.win.c, self.win.f, self.win.dpi * self.win.zoom
        W = self.winfo_width()
        if not self.rows:
            self.create_text(W / 2, 30 * d, text=_("Nenhum dano neste recorte."), fill=c["muted"], font=f["text"])
            return
        name_w = min(W * 0.32, max(f["text"].measure(r["name"]) for r in self.rows) + 20 * d)
        val_w = max(f["text"].measure("%s  %s" % (full(r["total"]), _fmt("pct", r["share"]))) for r in self.rows) + 16 * d
        top = self.rows[0]["total"] or 1
        y = 10 * d
        h = 18 * d
        for r in self.rows:
            self.create_text(12 * d, y + h / 2, text=r["name"], anchor="w", font=f["text"],
                             fill=c["accent"] if r.get("me") else c["fg"])
            bx0, bx1 = 12 * d + name_w, W - val_w - 8 * d
            self.create_rectangle(bx0, y + 2 * d, bx1, y + h - 2 * d, fill=c["track"], outline="")
            bw = (bx1 - bx0) * r["total"] / top
            if bw >= 1:
                self.create_rectangle(bx0, y + 2 * d, bx0 + bw, y + h - 2 * d, fill=self.win.color_of(r["aid"]),
                                      outline="")
            self.create_text(W - 8 * d, y + h / 2, text="%s  %s" % (full(r["total"]), _fmt("pct", r["share"])),
                             anchor="e", font=f["text"], fill=c["muted"])
            y += 26 * d


def _nice(x):
    if x <= 0:
        return 1
    p = 10 ** len(str(int(x))) / 10
    for m in (1, 2, 2.5, 5, 10):
        if m * p >= x:
            return m * p
    return 10 * p


def _nice_time(ms):
    for s in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600):
        if s * 1000 >= ms:
            return s * 1000
    return 3600000


class AnalysisWindow:
    def __init__(self, app):
        self.app = app
        self.top = tk.Toplevel(app.root)
        self.top.title(_("Análise — DPS Ragnarok   (Ctrl + roda do mouse: tamanho)"))
        self.dpi = app.dpi
        try:
            self.zoom = float(app.cfg.get("an_zoom") or 1.0)
        except (TypeError, ValueError):
            self.zoom = 1.0
        self.sig = None
        self.scope_items = []
        self.dps_sel = None
        self.mob_key = None
        self.player_aid = None
        self.dd_key = None
        self.dd_cache = (None, None)
        self.dd_result = None
        self.combat_id = None
        self.colors = {}
        self.tables = []
        self._swatches = {}
        self._last = 0.0
        t = app.theme()
        bg = t["bg"]
        dark = _lum(bg) < 0.5
        self.c = dict(bg=bg, panel=_mix(bg, t["fg"], 0.035), fg=t["fg"], muted=t["muted"], accent=t["accent"],
                      grid=_mix(bg, t["fg"], 0.12), track=_mix(bg, t["fg"], 0.08), row_alt=_mix(bg, t["fg"], 0.06),
                      tip=_mix(bg, t["fg"], 0.10), btn=t["btn"], live=t["live"],
                      tile=_mix(bg, t["fg"], 0.075 if dark else 0.05),
                      good="#4ade80" if dark else "#15803d", bad="#f87171" if dark else "#dc2626",
                      mid="#fbbf24" if dark else "#b45309")
        fams = set(tkfont.families(app.root))
        ui = "Segoe UI" if "Segoe UI" in fams else "Arial"
        semi = "Segoe UI Semibold" if "Segoe UI Semibold" in fams else ui
        nums = "Bahnschrift SemiBold" if "Bahnschrift SemiBold" in fams else semi
        self.f = dict(text=tkfont.Font(self.top, family=ui), small=tkfont.Font(self.top, family=ui),
                      head=tkfont.Font(self.top, family=semi), title=tkfont.Font(self.top, family=semi),
                      big=tkfont.Font(self.top, family=nums), tile=tkfont.Font(self.top, family=nums))
        self.size_fonts()
        self.top.configure(bg=bg)
        geo = app.cfg.get("an_geometry")
        self.top.geometry(geo if geo else "%dx%d" % (int(1120 * self.dpi), int(800 * self.dpi)))
        self.top.minsize(int(720 * self.dpi), int(500 * self.dpi))
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.top.bind("<Escape>", lambda e: self.close())
        self.top.bind("<Control-MouseWheel>", lambda e: self.set_zoom(1 if e.delta > 0 else -1))
        for seq, step in (("<Control-plus>", 1), ("<Control-equal>", 1), ("<Control-KP_Add>", 1),
                          ("<Control-minus>", -1), ("<Control-KP_Subtract>", -1)):
            self.top.bind(seq, lambda e, s=step: self.set_zoom(s))
        self.top.bind("<Control-0>", lambda e: self.set_zoom(0))
        self.style()
        self.build()
        self.refresh(force=True)

    # ------------------------------------------------------------ aparência

    def size_fonts(self):
        for key, pt in FONT_PT.items():
            self.f[key].configure(size=max(7, int(round(pt * self.zoom))))

    def set_zoom(self, step):
        if step == 0:
            z = 1.0
        else:
            i = min(range(len(ZOOMS)), key=lambda k: abs(ZOOMS[k] - self.zoom))
            z = ZOOMS[max(0, min(len(ZOOMS) - 1, i + step))]
        if z == self.zoom:
            return
        self.zoom = z
        self.app.cfg["an_zoom"] = z
        self.size_fonts()
        self.style()
        for t in self.tables:
            t.rescale()
        for tiles in (self.sum_tiles, self.dps_tiles, self.head_tiles):
            tiles.cols = 0
            tiles.reflow()
        self.refresh(force=True)

    def color_of(self, aid):
        if aid is None:
            return OTHERS
        col = self.colors.get(aid)
        if col is None:
            col = self.colors[aid] = PALETTE[len(self.colors) % len(PALETTE)]
        return col

    def swatch(self, color):
        img = self._swatches.get(color)
        if img is None:
            n = max(10, int(12 * self.dpi * self.zoom))
            img = tk.PhotoImage(master=self.top, width=n, height=n)
            img.put(color, to=(1, 1, n - 1, n - 1))
            self._swatches[color] = img
        return img

    def style(self):
        c, f = self.c, self.f
        s = ttk.Style(self.top)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        rh = int(23 * self.dpi * self.zoom)
        s.configure("An.Treeview", background=c["panel"], fieldbackground=c["panel"], foreground=c["fg"],
                    rowheight=rh, borderwidth=0, font=f["text"])
        s.map("An.Treeview", background=[("selected", _mix(c["panel"], c["accent"], 0.42))],
              foreground=[("selected", c["fg"])])
        s.configure("An.Treeview.Heading", background=c["btn"], foreground=c["fg"], relief="flat", font=f["head"],
                    borderwidth=0, padding=(6, 5))
        s.map("An.Treeview.Heading", background=[("active", _mix(c["btn"], c["fg"], 0.1))])
        s.configure("An.Vertical.TScrollbar", background=c["btn"], troughcolor=c["panel"], borderwidth=0,
                    arrowcolor=c["muted"], bordercolor=c["panel"], lightcolor=c["btn"], darkcolor=c["btn"])
        s.configure("An.TNotebook", background=c["bg"], borderwidth=0, tabmargins=(8, 6, 8, 0))
        s.configure("An.TNotebook.Tab", background=c["bg"], foreground=c["muted"], padding=(16, 7), font=f["head"],
                    borderwidth=0)
        s.map("An.TNotebook.Tab", background=[("selected", c["panel"])], foreground=[("selected", c["fg"])])
        s.configure("Sub.TNotebook", background=c["panel"], borderwidth=0, tabmargins=(6, 4, 6, 0))
        s.configure("Sub.TNotebook.Tab", background=c["panel"], foreground=c["muted"], padding=(12, 5),
                    font=f["head"], borderwidth=0)
        s.map("Sub.TNotebook.Tab", background=[("selected", c["tile"])], foreground=[("selected", c["fg"])])
        s.configure("An.TCombobox", fieldbackground=c["btn"], background=c["btn"], foreground=c["fg"],
                    arrowcolor=c["fg"], bordercolor=c["btn"], lightcolor=c["btn"], darkcolor=c["btn"],
                    selectbackground=c["btn"], selectforeground=c["fg"], padding=(6, 3))
        s.map("An.TCombobox", fieldbackground=[("readonly", c["btn"])], foreground=[("readonly", c["fg"])])
        self.top.option_add("*TCombobox*Listbox.background", c["btn"])
        self.top.option_add("*TCombobox*Listbox.foreground", c["fg"])
        self.top.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
        self.top.option_add("*TCombobox*Listbox.font", f["text"])
        s.configure("An.TCheckbutton", background=c["bg"], foreground=c["fg"], font=f["text"],
                    indicatorbackground=c["btn"], indicatorforeground=c["fg"])
        s.map("An.TCheckbutton", background=[("active", c["bg"])])
        s.configure("An.TButton", background=c["btn"], foreground=c["fg"], borderwidth=0, font=f["text"],
                    padding=(12, 5))
        s.map("An.TButton", background=[("active", _mix(c["btn"], c["fg"], 0.1))])
        s.configure("An.TPanedwindow", background=c["bg"])
        s.configure("Sash", sashthickness=int(6 * self.dpi), gripcount=0, background=c["bg"])

    def label(self, parent, text, font="text", color="fg", bg="bg", **kw):
        return tk.Label(parent, text=text, font=self.f[font], fg=self.c[color], bg=self.c[bg], **kw)

    # ------------------------------------------------------------ montagem

    def build(self):
        c = self.c
        head = tk.Frame(self.top, bg=c["bg"])
        head.pack(fill="x", padx=14, pady=(10, 2))
        self.title_lbl = self.label(head, _("Análise"), "title")
        self.title_lbl.pack(side="left")
        self.status_lbl = self.label(head, "", color="muted")
        self.status_lbl.pack(side="left", padx=(12, 0))
        self.copy_btn = ttk.Button(head, text=_("Copiar ranking"), style="An.TButton", command=self.copy_ranking)
        self.copy_btn.pack(side="right")
        bar = tk.Frame(self.top, bg=c["bg"])
        bar.pack(fill="x", padx=14, pady=(4, 6))
        self.label(bar, _("Recorte:"), color="muted").pack(side="left")
        self.scope_var = tk.StringVar(self.top, SESSION)
        self.scope_box = ttk.Combobox(bar, textvariable=self.scope_var, state="readonly", width=48,
                                      style="An.TCombobox", font=self.f["text"])
        self.scope_box.pack(side="left", padx=(6, 0))
        self.scope_box.bind("<<ComboboxSelected>>", lambda e: self.scope_changed())
        self.group_var = tk.BooleanVar(self.top, True)
        ttk.Checkbutton(bar, text=_("Agrupar fases dos MVPs"), variable=self.group_var, style="An.TCheckbutton",
                        command=lambda: self.refresh(force=True)).pack(side="left", padx=16)
        self.mvp_var = tk.BooleanVar(self.top, self.app.cfg.get("targets") == "mvp")
        ttk.Checkbutton(bar, text=_("Só MVPs e bonecos de treino"), variable=self.mvp_var, style="An.TCheckbutton",
                        command=lambda: self.app.set_targets("mvp" if self.mvp_var.get() else "all")
                        ).pack(side="left")

        self.head_tiles = Tiles(self.top, self, [
            ("group", _("Dano do grupo")), ("gdps", _("DPS do grupo")), ("combat", _("Em combate")),
            ("players", _("Jogadores")), ("events", _("Eventos de dano")), ("recorded", _("Gravação"))],
            min_w=112, bg="bg", compact=True)
        self.head_tiles.pack(fill="x", padx=14, pady=(2, 0))

        self.nb = ttk.Notebook(self.top, style="An.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.tab_changed())
        self.build_summary()
        self.build_players()
        self.build_monsters()
        self.build_dps()
        self.build_buffs()
        self.build_deaths()
        self.build_tests()
        self.build_dedo()
        try:
            self.nb.select(int(self.app.cfg.get("an_tab", 0)))
        except (tk.TclError, ValueError):
            pass

    def section(self, parent, text, bg="panel"):
        lbl = self.label(parent, text, "head", bg=bg, anchor="w")
        lbl.pack(fill="x", padx=10, pady=(10, 4))
        return lbl

    def build_summary(self):
        outer = tk.Frame(self.nb, bg=self.c["panel"])
        self.nb.add(outer, text=_("Resumo"))
        tab = ScrollFrame(outer, self).inner
        self.sum_title = self.section(tab, "")
        self.sum_tiles = Tiles(tab, self, [
            ("dealt", _("Seu dano")), ("dps", _("Seu DPS (em combate)")), ("eff", _("DPS do 1º ao último golpe")),
            ("hits", _("Acertos")), ("best", _("Maior golpe")), ("top", _("Skill mais usada")),
            ("kills", _("Abates (golpe fatal)")), ("taken", _("Dano recebido")), ("deaths", _("Mortes"))], min_w=165,
            dense=True)
        self.sum_tiles.pack(fill="x", padx=10)
        both = tk.Frame(tab, bg=self.c["panel"])
        both.pack(fill="both", expand=True, padx=4, pady=(4, 8))
        both.columnconfigure(0, weight=1, uniform="r")
        both.columnconfigure(1, weight=1, uniform="r")
        left = tk.Frame(both, bg=self.c["panel"])
        right = tk.Frame(both, bg=self.c["panel"])
        left.grid(row=0, column=0, sticky="nsew")
        right.grid(row=0, column=1, sticky="nsew")
        self.section(left, _("Seus maiores golpes"))
        self.t_tophits = Table(left, self, [
            ("t", _("Tempo"), 55, "e", "dur"), ("name", _("Habilidade"), 140, "w", "text"),
            ("target", _("Alvo"), 130, "w", "text"), ("dmg", _("Dano"), 105, "e", "big"), ("hits", _("Hits"), 40, "e", "int")],
            height=10)
        self.t_tophits.pack(fill="both", expand=True, padx=6)
        self.section(right, _("Dano recebido"))
        self.t_taken = Table(right, self, [
            ("source", _("Fonte"), 130, "w", "text"), ("name", _("Habilidade"), 130, "w", "text"),
            ("hits", _("Acertos"), 60, "e", "int"), ("total", _("Dano"), 100, "e", "big"), ("share", "%", 55, "e", "pct")],
            height=10)
        self.t_taken.pack(fill="both", expand=True, padx=6)

    def build_players(self):
        tab = tk.Frame(self.nb, bg=self.c["panel"])
        self.nb.add(tab, text=_("Jogadores"))
        pw = ttk.PanedWindow(tab, orient="vertical", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True)
        upper = tk.Frame(pw, bg=self.c["panel"])
        lower = tk.Frame(pw, bg=self.c["panel"])
        pw.add(upper, weight=3)
        pw.add(lower, weight=3)
        self.section(upper, _("Jogadores — dano de invocações e skills de chão conta para o dono"))
        self.t_players = Table(upper, self, [
            ("name", _("Jogador"), 170, "w", "text"), ("job", _("Classe"), 130, "w", "text"),
            ("total", _("Dano"), 120, "e", "big"), ("dps", "DPS", 105, "e", "big"), ("share", "%", 60, "e", "pct"),
            ("hits", _("Acertos"), 70, "e", "int"), ("misses", _("Erros"), 55, "e", "int"),
            ("max_hit", _("Maior golpe"), 110, "e", "big"), ("mobs", _("Monstros"), 75, "e", "int"),
            ("kills", _("Abates"), 60, "e", "int")], height=7, on_select=self.player_selected, swatch=True)
        self.t_players.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.player_title = self.section(lower, "")
        sub = ttk.Notebook(lower, style="Sub.TNotebook")
        sub.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.player_nb = sub
        sub.bind("<<NotebookTabChanged>>", lambda e: self.refresh(force=True))
        f1 = tk.Frame(sub, bg=self.c["panel"])
        sub.add(f1, text=_("Habilidades"))
        self.t_pskills = Table(f1, self, [
            ("name", _("Habilidade"), 220, "w", "text"), ("hits", _("Acertos"), 70, "e", "int"),
            ("total", _("Dano total"), 120, "e", "big"), ("share", "%", 60, "e", "pct"),
            ("dps", "DPS", 100, "e", "big"), ("avg", _("Dano médio"), 110, "e", "big"),
            ("max_hit", _("Maior golpe"), 110, "e", "big"), ("avg_multi", _("Hits médios"), 95, "e", "f2"),
            ("cast", _("Cast médio"), 85, "e", "ms")], height=6)
        self.t_pskills.pack(fill="both", expand=True, padx=4, pady=6)
        f2 = tk.Frame(sub, bg=self.c["panel"])
        sub.add(f2, text=_("Monstros atingidos"))
        self.t_ptargets = Table(f2, self, [
            ("name", _("Monstro"), 240, "w", "text"), ("hits", _("Acertos"), 70, "e", "int"),
            ("total", _("Dano"), 120, "e", "big"), ("share", "%", 60, "e", "pct"),
            ("max_hit", _("Maior golpe"), 110, "e", "big")], height=6)
        self.t_ptargets.pack(fill="both", expand=True, padx=4, pady=6)
        f3 = tk.Frame(sub, bg=self.c["panel"])
        sub.add(f3, text=_("Dano ao longo do tempo (todos)"))
        bar = tk.Frame(f3, bg=self.c["panel"])
        bar.pack(fill="x", padx=8, pady=(6, 0))
        self.label(bar, _("Dano a cada"), color="muted", bg="panel").pack(side="left")
        self.pl_bucket = tk.StringVar(self.top, "2 s")
        cb = ttk.Combobox(bar, textvariable=self.pl_bucket, values=[b[1] for b in BUCKETS], width=6,
                          state="readonly", style="An.TCombobox", font=self.f["text"])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh(force=True))
        self.pl_chart = Chart(f3, self, height=240)
        self.pl_chart.pack(fill="both", expand=True, padx=4, pady=4)

    def build_monsters(self):
        tab = tk.Frame(self.nb, bg=self.c["panel"])
        self.nb.add(tab, text=_("Monstros"))
        pw = ttk.PanedWindow(tab, orient="vertical", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True)
        upper = tk.Frame(pw, bg=self.c["panel"])
        lower = tk.Frame(pw, bg=self.c["panel"])
        pw.add(upper, weight=2)
        pw.add(lower, weight=5)
        self.section(upper, _("Monstros atacados — clique para ver o confronto"))
        self.t_mobs = Table(upper, self, [
            ("name", _("Monstro"), 220, "w", "text"), ("mob_id", _("ID do mob"), 80, "e", "int"),
            ("total", _("Dano"), 120, "e", "big"), ("hits", _("Acertos"), 70, "e", "int"),
            ("attackers", _("Atacantes"), 80, "e", "int"), ("max_hp", _("HP máx."), 120, "e", "big"),
            ("ttk", _("Tempo até abate"), 125, "e", "dur"), ("killer", _("Abatido por"), 140, "w", "text")],
            height=5, on_select=self.mob_selected)
        self.t_mobs.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.mob_title = self.section(lower, "")
        sub = ttk.Notebook(lower, style="Sub.TNotebook")
        sub.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.mob_nb = sub
        sub.bind("<<NotebookTabChanged>>", lambda e: self.refresh(force=True))

        f1 = tk.Frame(sub, bg=self.c["panel"])
        sub.add(f1, text=_("Dano por jogador"))
        self.mob_bars = HBars(f1, self)
        self.mob_bars.pack(fill="both", expand=True, pady=4)

        f2 = tk.Frame(sub, bg=self.c["panel"])
        sub.add(f2, text=_("Linha do tempo"))
        bar = tk.Frame(f2, bg=self.c["panel"])
        bar.pack(fill="x", padx=8, pady=(6, 0))
        self.label(bar, _("Dano a cada"), color="muted", bg="panel").pack(side="left")
        self.mob_bucket = tk.StringVar(self.top, "2 s")
        cb = ttk.Combobox(bar, textvariable=self.mob_bucket, values=[b[1] for b in BUCKETS], width=6,
                          state="readonly", style="An.TCombobox", font=self.f["text"])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh(force=True))
        self.label(bar, _("uma linha por jogador · tracejado = troca de fase"), color="muted", bg="panel").pack(side="left")
        self.mob_chart = Chart(f2, self, height=300)
        self.mob_chart.pack(fill="both", expand=True, padx=4, pady=4)

        f3 = tk.Frame(sub, bg=self.c["panel"])
        sub.add(f3, text=_("Habilidades usadas contra ele"))
        self.t_against = Table(f3, self, [
            ("name", _("Habilidade"), 200, "w", "text"), ("player", _("Jogador"), 150, "w", "text"),
            ("job", _("Classe"), 120, "w", "text"), ("hits", _("Acertos"), 70, "e", "int"),
            ("total", _("Dano total"), 120, "e", "big"), ("avg", _("Dano médio"), 110, "e", "big"),
            ("avg_multi", _("Hits médios"), 95, "e", "f2"), ("cast", _("Cast médio"), 85, "e", "ms")], height=10,
            swatch=True)
        self.t_against.pack(fill="both", expand=True, padx=4, pady=6)

        f4 = tk.Frame(sub, bg=self.c["panel"])
        sub.add(f4, text=_("Habilidades do monstro"))
        bar = tk.Frame(f4, bg=self.c["panel"])
        bar.pack(fill="x", padx=8, pady=(6, 0))
        self.label(bar, _("Com dano e de suporte/debuff.   Filtrar por alvo:"), color="muted",
                   bg="panel").pack(side="left")
        self.victim_var = tk.StringVar(self.top, _("Todos os alvos"))
        self.victim_box = ttk.Combobox(bar, textvariable=self.victim_var, width=24, state="readonly",
                                       style="An.TCombobox", font=self.f["text"])
        self.victim_box.pack(side="left", padx=6)
        self.victim_box.bind("<<ComboboxSelected>>", lambda e: self.refresh(force=True))
        self.victims = {}
        self.t_mskills = Table(f4, self, [
            ("name", _("Habilidade"), 220, "w", "text"), ("skill", _("ID"), 60, "e", "int"),
            ("hits", _("Acertos"), 70, "e", "int"), ("total", _("Dano total"), 120, "e", "big"),
            ("avg", _("Dano médio"), 110, "e", "big"), ("nodmg", _("Usos sem dano"), 115, "e", "int"),
            ("targets", _("Alvos"), 60, "e", "int"), ("cast", _("Cast médio"), 85, "e", "ms")], height=10)
        self.t_mskills.pack(fill="both", expand=True, padx=4, pady=6)

    def build_dps(self):
        tab = tk.Frame(self.nb, bg=self.c["panel"])
        self.nb.add(tab, text=_("Análise de DPS"))
        bar = tk.Frame(tab, bg=self.c["panel"])
        bar.pack(fill="x", padx=10, pady=(10, 0))
        self.label(bar, _("Jogador:"), color="muted", bg="panel").pack(side="left")
        self.dps_player = tk.StringVar(self.top, "")
        self.dps_player_box = ttk.Combobox(bar, textvariable=self.dps_player, width=26, state="readonly",
                                           style="An.TCombobox", font=self.f["text"])
        self.dps_player_box.pack(side="left", padx=6)
        self.dps_player_box.bind("<<ComboboxSelected>>", lambda e: self.refresh(force=True))
        self.dps_players = {}
        self.label(bar, _("  Barras a cada"), color="muted", bg="panel").pack(side="left")
        self.dps_bucket = tk.StringVar(self.top, "1 s")
        cb = ttk.Combobox(bar, textvariable=self.dps_bucket, values=[b[1] for b in BUCKETS], width=6,
                          state="readonly", style="An.TCombobox", font=self.f["text"])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh(force=True))
        ttk.Button(bar, text=_("Limpar seleção"), style="An.TButton", command=self.clear_dps_sel).pack(side="right")
        pw = ttk.PanedWindow(tab, orient="vertical", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True, pady=(6, 0))
        top = tk.Frame(pw, bg=self.c["panel"])
        bottom = tk.Frame(pw, bg=self.c["panel"])
        pw.add(top, weight=2)
        pw.add(bottom, weight=3)
        self.dps_chart = Chart(top, self, height=220, on_select=self.dps_selected)
        self.dps_chart.pack(fill="both", expand=True, padx=4)
        self.dps_window_lbl = self.section(bottom, _("Estatísticas da janela"))
        split = tk.Frame(bottom, bg=self.c["panel"])
        split.pack(fill="both", expand=True)
        split.columnconfigure(0, weight=3, uniform="d")
        split.columnconfigure(1, weight=2, uniform="d")
        split.rowconfigure(0, weight=1)
        left = tk.Frame(split, bg=self.c["panel"])
        right = tk.Frame(split, bg=self.c["panel"])
        left.grid(row=0, column=0, sticky="nsew")
        right.grid(row=0, column=1, sticky="nsew")
        self.dps_tiles = Tiles(left, self, [
            ("window", _("Janela")), ("events", _("Eventos de dano")), ("total", _("Dano total")),
            ("span", _("Em combate")), ("dps", _("DPS médio")), ("mean_gap", _("Intervalo médio")),
            ("max_hit", _("Maior golpe")), ("avg_hit", _("Dano por golpe")), ("longest", _("Maior intervalo")),
            ("distinct", _("Skills distintas")), ("top", _("Skill com mais dano"))], min_w=135, dense=True)
        self.dps_tiles.pack(fill="both", expand=True, padx=(10, 4))
        self.label(right, _("Habilidades no trecho"), "head", bg="panel", anchor="w").pack(fill="x", padx=6, pady=(0, 4))
        self.t_wskills = Table(right, self, [
            ("name", _("Habilidade"), 120, "w", "text"), ("hits", _("Acertos"), 64, "e", "int"),
            ("total", _("Dano"), 100, "e", "big"), ("share", "%", 52, "e", "pct"),
            ("dps", "DPS", 90, "e", "big")], height=5)
        self.t_wskills.pack(fill="both", expand=True, padx=(4, 8), pady=(0, 8))

    # ------------------------------------------------------------ dados

    def combat(self):
        return self.app.combat()

    def scope(self, c):
        """Encounter escolhido (None = sessão inteira)."""
        v = self.scope_var.get()
        if v == SESSION or c is None:
            return None
        encs = c.encounters()
        if not encs:
            return None
        if v == LATEST:
            return encs[-1]
        for label, enc in self.scope_items:
            if label == v and enc in encs:
                return enc
        return None

    def update_scope_list(self, c):
        encs = c.encounters() if c else []
        items = []
        for i, enc in enumerate(encs, 1):
            tgt = max(enc.by_target.items(), key=lambda kv: kv[1])[0] if enc.by_target else None
            name = c.target_name(tgt) if tgt is not None else ""
            items.append((_("Encontro %d · %s–%s · %s") % (i, dur(enc.start), dur(enc.last), name), enc))
        items.reverse()
        self.scope_items = items
        values = [SESSION, LATEST] + [lbl for lbl, _e in items]
        if list(self.scope_box["values"]) != values:
            cur = self.scope_var.get()
            self.scope_box["values"] = values
            if cur not in values:
                # mesmo encontro com o rótulo atualizado (o fim muda enquanto acontece)
                prefix = cur.split(" · ")[0]
                self.scope_var.set(next((v for v in values if v.split(" · ")[0] == prefix), SESSION))

    def scope_changed(self):
        self.dps_sel = None
        self.refresh(force=True)

    def tab_changed(self):
        try:
            self.app.cfg["an_tab"] = self.nb.index(self.nb.select())
        except tk.TclError:
            pass
        self.refresh(force=True)

    def tick(self):
        """Chamado pelo widget a cada leitura; redesenha no máximo 1x por segundo."""
        c = self.combat()
        live = c is not None and c.active()
        sig = (id(c), c.version if c else None, self.scope_var.get(), self.group_var.get(),
               len(self.app.tests.records))
        if sig != self.sig or (live and time.monotonic() - self._last >= 1.0):
            self.refresh()

    def refresh(self, force=False):
        self._last = time.monotonic()
        c = self.combat()
        if c is not None and id(c) != self.combat_id:
            self.combat_id = id(c)
            self.dps_sel = None
            self.player_aid = c.me
            self.mob_key = None
            self.colors = {}
        self.sig = (id(c), c.version if c else None, self.scope_var.get(), self.group_var.get(),
                    len(self.app.tests.records))
        if self.mvp_var.get() != (self.app.cfg.get("targets") == "mvp"):
            self.mvp_var.set(self.app.cfg.get("targets") == "mvp")       # mudou pelo menu do widget
        self.update_scope_list(c)
        tab = self.nb.index(self.nb.select())
        if tab == 6:
            self.refresh_tests()              # o histórico não depende do replay aberto
        if c is None:
            self.title_lbl.configure(text=_("Análise"))
            self.status_lbl.configure(text=_("sem replay aberto — comece a gravar no jogo ou abra um replay salvo"))
            return
        scope = self.scope(c)
        rng, dur_ms = an.scope_range(c, scope)
        self.rng, self.dur_ms = rng, dur_ms
        s = c.session
        self.title_lbl.configure(text="%s · %s" % (s.player, c.map or s.map))
        live = c.active() and (scope is None or c.is_live(scope))
        _y, mo, d, hh, mm, _ss = s.recorded_at
        state = _("● ao vivo") if live else (_("gravando") if not c.finished else _("replay encerrado"))
        self.status_lbl.configure(text=_("%s · gravado %02d/%02d às %02d:%02d") % (state, d, mo, hh, mm),
                                  fg=self.c["live"] if live else self.c["muted"])
        self.players_rows = an.players(c, rng, dur_ms)
        for p in self.players_rows:          # cor fixa por jogador, na ordem do ranking
            self.color_of(p["aid"])
        hs = an.out_hits(c, rng)
        total = sum(h.dmg for h in hs)
        ht = self.head_tiles
        gdps = total * 1000.0 / max(1, dur_ms)
        ht.put("group", full(total), short=num(total))
        ht.put("gdps", full(round(gdps)), short=num(gdps))
        ht.put("combat", dur(dur_ms))
        ht.put("players", "%d" % len(self.players_rows))
        ht.put("events", "%d" % len(hs))
        ht.put("recorded", dur(c.now))
        if tab == 0:
            self.refresh_summary(c)
        elif tab == 1:
            self.refresh_players(c)
        elif tab == 2:
            self.refresh_monsters(c)
        elif tab == 3:
            self.refresh_dps(c)
        elif tab == 4:
            self.refresh_buffs(c)
        elif tab == 5:
            self.refresh_deaths(c)
        elif tab == 7:
            self.refresh_dedo(c)

    def refresh_summary(self, c):
        sm = an.summary(c, self.rng, self.dur_ms)
        me = c.session
        self.sum_title.configure(text=_("%s · %s · nível %d") % (me.player, an.job_of(c, c.me), me.base_level))
        t = self.sum_tiles
        t.put("dealt", full(sm["dealt"]), _("%s do grupo") % _fmt("pct", sm["share"]), self.c["accent"])
        t.put("dps", full(round(sm["dps"])), _("tempo em combate %s") % dur(sm["combat_ms"]))
        t.put("eff", full(round(sm["effective_dps"])) if sm["effective_dps"] else "—", _("como no Ragna Recap"))
        t.put("hits", "%d" % sm["hits"], _("%d erros · %d críticos") % (sm["misses"], sm["crits"]))
        if sm["best"]:
            t.put("best", full(sm["best"]["dmg"]), "%s · %s" % (sm["best"]["skill"], sm["best"]["target"]))
        else:
            t.put("best", "—")
        t.put("top", sm["top_skill"] or "—", _("%d usos") % sm["top_count"] if sm["top_count"] else "")
        t.put("kills", "%d" % sm["kills"], _("%d chefes") % sm["boss_kills"] if sm["boss_kills"] else "")
        t.put("taken", full(sm["taken"]), _("%d acertos") % sm["taken_hits"])
        t.put("deaths", "%d" % sm["deaths"], "", self.c["live"] if sm["deaths"] else None)
        self.t_tophits.set_rows(an.top_hits(c, self.rng, c.me, 15), lambda r: "%d|%d" % (r["t"], r["dmg"]))
        self.t_taken.set_rows(an.damage_taken(c, self.rng, c.me), lambda r: "%s|%s" % (r["source"], r["name"]))

    def refresh_players(self, c):
        rows = self.players_rows
        self.t_players.set_rows(rows, lambda r: r["aid"], lambda r: ["me"] if r["me"] else [],
                                lambda r: self.color_of(r["aid"]))
        aids = [r["aid"] for r in rows]
        if self.player_aid not in aids and aids:
            self.player_aid = c.me if c.me in aids else aids[0]
        if self.player_aid is not None:
            self.t_players.select(self.player_aid)
        self.refresh_player_detail(c)

    def player_selected(self, row):
        if row is not None and row["aid"] != self.player_aid:
            self.player_aid = row["aid"]
            self.refresh_player_detail(self.combat())

    def refresh_player_detail(self, c):
        aid = self.player_aid
        if c is None or aid is None:
            self.player_title.configure(text="")
            self.t_pskills.set_rows([], lambda r: 0)
            return
        row = next((r for r in self.players_rows if r["aid"] == aid), None)
        bits = [c.name_of(aid)]
        if row:
            bits += [row["job"], _("dano %s") % full(row["total"]), "DPS %s" % full(round(row["dps"]))]
        self.player_title.configure(text="  ·  ".join(b for b in bits if b))
        sub = self.player_nb.index(self.player_nb.select())
        if sub == 0:
            self.t_pskills.set_rows(an.player_skills(c, self.rng, aid, self.dur_ms), lambda r: r["name"])
        elif sub == 1:
            self.t_ptargets.set_rows(an.player_targets(c, self.rng, aid, self.group_var.get()), lambda r: r["key"])
        else:
            bucket = dict((b[1], b[0]) for b in BUCKETS)[self.pl_bucket.get()]
            ts, series = an.timeline(c, self.rng, bucket, top=10)
            self.pl_chart.set(ts, bucket, series, "line", self.phase_markers(c))

    def phase_markers(self, c, key=None):
        if not self.group_var.get():
            return []
        out = []
        for root, starts in c.phase_starts.items():
            if key is None or root == key:
                out += [(t, _("Fase %d") % (i + 2)) for i, t in enumerate(starts)]
        return out

    def refresh_monsters(self, c):
        group = self.group_var.get()
        rows = an.monsters(c, self.rng, group)
        self.t_mobs.set_rows(rows, lambda r: r["key"])
        keys = [r["key"] for r in rows]
        if self.mob_key not in keys:
            self.mob_key = keys[0] if keys else None
        if self.mob_key is not None:
            self.t_mobs.select(self.mob_key)
        self.refresh_mob_detail(c, rows)

    def mob_selected(self, row):
        if row is not None and row["key"] != self.mob_key:
            self.mob_key = row["key"]
            self.victim_var.set(_("Todos os alvos"))
            self.refresh(force=True)

    def refresh_mob_detail(self, c, rows):
        key = self.mob_key
        group = self.group_var.get()
        row = next((r for r in rows if r["key"] == key), None)
        if row is None:
            self.mob_title.configure(text=_("Nenhum monstro atacado neste recorte."))
            self.mob_bars.set([])
            self.mob_chart.set([], 1000, [])
            self.t_against.set_rows([], lambda r: 0)
            self.t_mskills.set_rows([], lambda r: 0)
            return
        bits = [row["name"], _("dano %s") % full(row["total"]), _("%d acertos") % row["hits"]]
        if row["max_hp"]:
            bits.append(_("HP máx. %s") % full(row["max_hp"]))
        if row["ttk"] is not None:
            bits.append(_("abatido em %s por %s") % (dur(row["ttk"]), row["killer"]))
        self.mob_title.configure(text="  ·  ".join(bits))
        sub = self.mob_nb.index(self.mob_nb.select())
        if sub == 0:
            self.mob_bars.set(an.monster_players(c, self.rng, key, group)[:14])
        elif sub == 1:
            bucket = dict((b[1], b[0]) for b in BUCKETS)[self.mob_bucket.get()]
            ts, series = an.timeline(c, self.rng, bucket, key=key, group=group, top=10)
            self.mob_chart.set(ts, bucket, series, "line", self.phase_markers(c, key))
        elif sub == 2:
            self.t_against.set_rows(an.skills_against(c, self.rng, key, group),
                                    lambda r: "%s|%s" % (r["player"], r["name"]),
                                    color_fn=lambda r: self.color_of(r["src"]))
        else:
            victims = an.monster_victims(c, self.rng, key)
            self.victims = {"Todos os alvos": None}
            self.victims.update({name: aid for aid, name in victims})
            vals = list(self.victims)
            if list(self.victim_box["values"]) != vals:
                self.victim_box["values"] = vals
            target = self.victims.get(self.victim_var.get())
            self.t_mskills.set_rows(an.monster_skills(c, self.rng, key, target), lambda r: r["skill"])

    def dps_selected(self, sel):
        self.dps_sel = sel
        self.refresh(force=True)

    def clear_dps_sel(self):
        self.dps_sel = None
        self.refresh(force=True)

    def refresh_dps(self, c):
        players = self.players_rows
        self.dps_players = {(_("%s (você)") % p["name"]) if p["me"] else p["name"]: p["aid"] for p in players}
        vals = list(self.dps_players)
        if list(self.dps_player_box["values"]) != vals:
            self.dps_player_box["values"] = vals
        aid = self.dps_players.get(self.dps_player.get())
        if aid is None:
            aid = c.me if c.me in self.dps_players.values() else (players[0]["aid"] if players else c.me)
            self.dps_player.set(next((k for k, v in self.dps_players.items() if v == aid), ""))
        bucket = dict((b[1], b[0]) for b in BUCKETS)[self.dps_bucket.get()]
        ts, series = an.timeline(c, self.rng, bucket, src=aid)
        if self.dps_sel:
            t0, t1 = self.dps_sel
        elif self.rng:
            t0, t1 = self.rng
        else:
            t0, t1 = (ts[0], ts[-1] + bucket) if ts else (0, 0)
        w = an.window_stats(c, aid, t0, t1)
        overlays, hline, bars = [], None, series[:1]
        if bars:
            # barras em DPS (dano do intervalo / duração), com média móvel de 5 s e a média da janela
            a, name, v = bars[0]
            per_s = [x * 1000.0 / bucket for x in v]
            bars = [(a, name, per_s)]
            if len(v) > 2:
                overlays.append((_("DPS móvel (5 s)"), self.c["fg"], an.rolling_dps(v, bucket)))
            if w["dps"]:
                hline = (w["dps"], _("média da janela: %s") % full(round(w["dps"])))
        self.dps_chart.set(ts, bucket, bars, "bar", self.phase_markers(c), self.dps_sel,
                           empty=_("Nenhum dano deste jogador no recorte."), overlays=overlays, hline=hline, unit="/s")
        self.dps_window_lbl.configure(text=_("Estatísticas da janela — %s") % (
            "%s a %s" % (dur(t0), dur(t1)) if self.dps_sel else _("recorte inteiro (arraste no gráfico para escolher)")))
        put = self.dps_tiles.put
        put("window", dur(w["window_ms"]) if self.dps_sel else _("tudo"),
            "%s – %s" % (dur(t0), dur(t1)) if self.dps_sel else "")
        put("events", "%d" % w["events"])
        put("total", full(w["total"]))
        put("span", dec("%.1f s" % (w["span_ms"] / 1000.0)) if w["events"] else "—",
            _("do 1º ao último golpe"))
        put("dps", full(round(w["dps"])) if w["dps"] else "—", "", self.c["accent"])
        put("mean_gap", "%d ms" % round(w["mean_gap"]) if w["mean_gap"] is not None else "—")
        put("max_hit", full(w["max_hit"]) if w["events"] else "—")
        put("avg_hit", full(round(w["avg_hit"])) if w["events"] else "—")
        put("longest", "%d ms" % w["longest_gap"] if w["events"] > 1 else "—")
        put("distinct", "%d" % w["distinct"])
        put("top", w["top_skill"] or "—", full(w["top_skill_dmg"]) if w["top_skill"] else "")
        self.t_wskills.set_rows(w["skills"], lambda r: r["name"])

    # ------------------------------------------------------------ buffs

    def build_buffs(self):
        tab = tk.Frame(self.nb, bg=self.c["panel"])
        self.nb.add(tab, text=_("Buffs"))
        pw = ttk.PanedWindow(tab, orient="vertical", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True)
        upper = tk.Frame(pw, bg=self.c["panel"])
        lower = tk.Frame(pw, bg=self.c["panel"])
        pw.add(upper, weight=3)
        pw.add(lower, weight=2)
        self.buffs_title = self.section(upper, _("Seus buffs"))
        self.t_buffs = Table(upper, self, [
            ("name", _("Buff"), 220, "w", "text"), ("kind_txt", _("Tipo"), 120, "w", "text"),
            ("uptime", _("Tempo ativo em combate"), 170, "e", "pct"), ("count", _("Aplicações"), 90, "e", "int"),
            ("start_txt", _("Já estava no início"), 130, "center", "text"), ("now_txt", _("Agora"), 110, "e", "text")],
            height=9)
        self.t_buffs.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        bar = tk.Frame(lower, bg=self.c["panel"])
        bar.pack(fill="x", padx=10, pady=(10, 4))
        self.label(bar, _("Debuffs no monstro"), "head", bg="panel").pack(side="left")
        self.debuff_mob = tk.StringVar(self.top, "")
        self.debuff_box = ttk.Combobox(bar, textvariable=self.debuff_mob, width=34, state="readonly",
                                       style="An.TCombobox", font=self.f["text"])
        self.debuff_box.pack(side="left", padx=8)
        self.debuff_box.bind("<<ComboboxSelected>>", lambda e: self.refresh(force=True))
        self.debuff_info = self.label(bar, "", color="muted", bg="panel")
        self.debuff_info.pack(side="left")
        self.debuff_mobs = {}
        self.t_debuffs = Table(lower, self, [
            ("name", _("Debuff"), 240, "w", "text"), ("uptime", _("Tempo ativo enquanto apanhava"), 200, "e", "pct"),
            ("count", _("Aplicações"), 90, "e", "int"), ("imp", _("Importante"), 90, "center", "text")], height=6)
        self.t_debuffs.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def refresh_buffs(self, c):
        rows, total = an.buff_uptime(c, c.me, self.rng)
        for r in rows:
            r["start_txt"] = _("sim") if r["at_start"] else ""
            r["kind_txt"] = _(r["kind"])
            if r["active"]:
                r["now_txt"] = (_("ativo · %s") % dur(r["left"])) if r["left"] is not None else _("ativo")
            else:
                r["now_txt"] = ""
        self.buffs_title.configure(text=_("Seus buffs — %% do tempo em combate, vivo (%s). Em vermelho: buff de grupo "
                                        "ou consumível ativo em menos de 80%% desse tempo.") % dur(total))
        self.t_buffs.set_rows(rows, lambda r: r["name"],
                              lambda r: ["warn"] if r["kind"] in ("Grupo/suporte", "Consumível")
                              and r["uptime"] is not None and r["uptime"] < 0.8 else [])
        mobs = an.monsters(c, self.rng, self.group_var.get())
        self.debuff_mobs = {m["name"]: m["key"] for m in mobs}
        vals = list(self.debuff_mobs)
        if list(self.debuff_box["values"]) != vals:
            self.debuff_box["values"] = vals
        if self.debuff_mob.get() not in self.debuff_mobs:
            self.debuff_mob.set(vals[0] if vals else "")
        key = self.debuff_mobs.get(self.debuff_mob.get())
        if key is None:
            self.t_debuffs.set_rows([], lambda r: 0)
            self.debuff_info.configure(text="")
            return
        drows, span = an.mob_debuffs(c, self.rng, key, self.group_var.get())
        for r in drows:
            r["imp"] = "★" if r["important"] else ""
        self.debuff_info.configure(text=_("apanhou durante %s") % dur(span))
        self.t_debuffs.set_rows(drows, lambda r: r["efst"])

    # ------------------------------------------------------------ mortes

    def build_deaths(self):
        tab = tk.Frame(self.nb, bg=self.c["panel"])
        self.nb.add(tab, text=_("Mortes"))
        pw = ttk.PanedWindow(tab, orient="vertical", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True)
        upper = tk.Frame(pw, bg=self.c["panel"])
        lower = tk.Frame(pw, bg=self.c["panel"])
        pw.add(upper, weight=2)
        pw.add(lower, weight=3)
        self.section(upper, _("Mortes de jogadores — HP só é conhecido para você e para quem está no seu grupo"))
        self.t_deaths = Table(upper, self, [
            ("t", _("Tempo"), 60, "e", "dur"), ("name", _("Jogador"), 150, "w", "text"), ("job", _("Classe"), 120, "w", "text"),
            ("cause", _("Causa"), 260, "w", "text"), ("hit", _("Golpe"), 105, "e", "big"),
            ("hp_before", _("HP antes"), 95, "e", "big"), ("overkill", _("Overkill"), 105, "e", "big"),
            ("taken_5s", _("Dano em 5 s"), 110, "e", "big")], height=6, on_select=self.death_selected, swatch=True)
        self.t_deaths.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.death_title = self.label(lower, "", "head", bg="panel", anchor="w", justify="left")
        self.death_title.pack(fill="x", padx=10, pady=(10, 2))
        self.death_text = self.label(lower, "", "text", "muted", "panel", anchor="w", justify="left")
        self.death_text.pack(fill="x", padx=10, pady=(0, 6))
        self.t_recap = Table(lower, self, [
            ("rel_txt", _("Antes da morte"), 110, "e", "text"), ("source", _("Fonte"), 200, "w", "text"),
            ("name", _("Habilidade / evento"), 200, "w", "text"), ("dmg", _("Dano"), 110, "e", "big"),
            ("hp", _("HP"), 100, "e", "big")], height=8)
        self.t_recap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.death_key = None
        self.death_rows = []
        self.death_wrap = False
        lower.bind("<Configure>", lambda e: (self.death_title.configure(wraplength=e.width - 30),
                                             self.death_text.configure(wraplength=e.width - 30)))

    def refresh_deaths(self, c):
        rows = an.deaths(c, self.rng)
        for i, d in enumerate(rows):
            d["key"] = "%d|%d" % (d["t"], d["aid"])
            if d["trap"]:
                d["cause"] = _("Armadilha do mapa") + (_(" (~%d%% do HP máx.)") % round(d["trap_pct"] * 100)
                                                    if d["trap_pct"] else "")
            elif d["fusion"]:
                d["cause"] = _("União Solar, Lunar e Estelar (atacou com %s de HP)") % (
                    "%d%%" % round(d["hp_pct"] * 100) if d["hp_pct"] is not None else _("20% ou menos"))
            elif d["no_hit"]:
                d["cause"] = _("sem golpe visível (efeito, debuff ou algo fora da tela)")
            elif d["unclear"]:
                d["cause"] = _("último golpe: %s · %s (não bastava sozinho)") % (d["skill"], d["killer"])
            else:
                d["cause"] = "%s · %s" % (d["skill"], d["killer"])
            if d["unclear"] or d["fusion"] or not d["overkill"]:
                d["overkill"] = None
        self.death_rows = rows
        self.t_deaths.set_rows(rows, lambda r: r["key"], lambda r: ["me"] if r["me"] else [],
                               lambda r: self.color_of(r["aid"]))
        keys = [d["key"] for d in rows]
        if self.death_key not in keys:
            mine = [d["key"] for d in rows if d["me"]]
            self.death_key = (mine or keys or [None])[-1]
        if self.death_key:
            self.t_deaths.select(self.death_key)
        self.show_death()

    def death_selected(self, row):
        if row is not None:
            self.death_key = row["key"]
            self.show_death()

    def show_death(self):
        d = next((r for r in self.death_rows if r["key"] == self.death_key), None)
        if d is None:
            self.death_title.configure(text=_("Nenhuma morte de jogador neste recorte."))
            self.death_text.configure(text="")
            self.t_recap.set_rows([], lambda r: 0)
            return
        title = _("%s morreu em %s") % (d["name"], dur(d["t"]))
        if d["trap"]:
            title += _(" — armadilha do mapa")
            if d["hit"]:
                title += ": ~%s" % full(d["hit"])
            if d["trap_pct"]:
                title += _(" (%d%% do HP máx.)") % round(d["trap_pct"] * 100)
            if d["overkill"]:
                title += _(" · overkill ~%s") % full(d["overkill"])
        elif d["fusion"]:
            title += _(" — União Solar, Lunar e Estelar")
        elif not d["no_hit"] and not d["unclear"]:
            title += _(" — %s de %s: %s") % (d["skill"], d["killer"], full(d["hit"]))
            if d["overkill"]:
                title += _(" · overkill %s") % full(d["overkill"])
                if d["overkill_x"]:
                    title += dec(_(" (o golpe foi %.1f× o HP que restava)") % d["overkill_x"])
        self.death_title.configure(text=title)
        bits = []
        if d["trap"]:
            bits.append(_("as armadilhas da Torre da Constelação tiram uma %% fixa do HP máx. (irredutível), "
                        "que sobe com a dificuldade e conforme o chefe perde vida; a %% vem das armadilhas que "
                        "não mataram%s") % (_(" — HP antes: %s") % full(d["hp_before"]) if d["hp_before"] is not None else ""))
            if d["hp_before"] is not None and d["hit"] and d["hit"] < d["hp_before"]:
                bits.append(_("a armadilha estimada era menor que o último HP conhecido: o HP do grupo chega "
                            "com atraso, então algum golpe pode ter vindo antes"))
        if d["fusion"]:
            bits.append(_("com a União, cada ataque físico custa 2%% do HP máx. e atacar com 20%% de HP ou menos "
                        "mata na hora. HP no último registro: %s%s") % (
                            full(d["hp_last"]) if d["hp_last"] is not None else "?",
                            _(" (%d%% de %s)") % (round(d["hp_pct"] * 100), full(d["max_hp"])) if d["hp_pct"] else ""))
            if d["fusion_cost"]:
                bits.append(_("HP gasto pela União nos 10 s antes: %s") % full(d["fusion_cost"]))
        elif d["hp_before"] is not None:
            bits.append(_("HP antes do último golpe: %s%s") % (full(d["hp_before"]),
                        _(" de %s") % full(d["max_hp"]) if d["max_hp"] else ""))
        if d["no_hit"] and d["hp_loss"] and not d["fusion"]:
            bits.append(_("perdeu %s de HP sem golpe visível") % full(d["hp_loss"]))
        if d["unclear"] and not d["fusion"]:
            bits.append(_("o último golpe visível (%s) era menor que o HP: a causa real não apareceu no replay")
                        % full(d["hit"]))
        bits.append(_("dano recebido nos últimos 5 s: %s em %d golpes") % (full(d["taken_5s"]), d["hits_5s"]))
        if d["statuses"]:
            bits.append(_("efeitos ativos: ") + ", ".join(d["statuses"][:14]))
        self.death_text.configure(text="  ·  ".join(bits))
        rows = []
        for i, r in enumerate(d["rows"]):
            rows.append(dict(r, key=i, rel_txt=dec("%.1f s" % (r["rel"] / 1000.0))))
        self.t_recap.set_rows(rows, lambda r: r["key"], lambda r: ["warn"] if r["kind"] == "dano" and r["dmg"] else [])

    # ------------------------------------------------------------ dedo duro

    SEV_TAG = {2: "bad", 1: "mid", 0: "muted"}

    def build_dedo(self):
        c = self.c
        tab = tk.Frame(self.nb, bg=c["panel"])
        self.nb.add(tab, text=_("Dedo Duro"))
        bar = tk.Frame(tab, bg=c["panel"])
        bar.pack(fill="x", padx=10, pady=(10, 4))
        self.label(bar, _("Chefe:"), color="muted", bg="panel").pack(side="left")
        self.dd_var = tk.StringVar(self.top, "")
        self.dd_box = ttk.Combobox(bar, textvariable=self.dd_var, state="readonly", width=64,
                                   style="An.TCombobox", font=self.f["text"])
        self.dd_box.pack(side="left", padx=6)
        self.dd_box.bind("<<ComboboxSelected>>", lambda e: self.dd_pick())
        self.dd_copy = ttk.Button(bar, text=_("Copiar relatório"), style="An.TButton", command=self.copy_dedo)
        self.dd_copy.pack(side="right")
        self.dd_fights = {}
        # o chefe em destaque
        band = _mix(c["tile"], c["accent"], 0.16)
        self.dd_banner = tk.Frame(tab, bg=band, padx=14, pady=8)
        self.dd_banner.pack(fill="x", padx=10, pady=(4, 6))
        top = tk.Frame(self.dd_banner, bg=band)
        top.pack(fill="x")
        self.dd_title = tk.Label(top, text="", font=self.f["title"], fg=c["accent"], bg=band, anchor="w")
        self.dd_title.pack(side="left")
        self.dd_counts = tk.Label(top, text="", font=self.f["head"], fg=c["fg"], bg=band, anchor="e")
        self.dd_counts.pack(side="right")
        self.dd_sub = tk.Label(self.dd_banner, text="", font=self.f["small"], fg=c["muted"], bg=band, anchor="w",
                               justify="left")
        self.dd_sub.pack(fill="x")
        self.dd_banner.bind("<Configure>", lambda e: self.dd_sub.configure(wraplength=e.width - 30))
        # grupo e fora do grupo: listas separadas
        self.dd_nb = ttk.Notebook(tab, style="Sub.TNotebook")
        self.dd_nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.dd_group = self.dd_side(self.dd_nb, party=True)
        self.dd_other = self.dd_side(self.dd_nb, party=False)

    def dd_side(self, nb, party):
        """Uma das metades (grupo / fora do grupo): alertas em cima, detalhes embaixo."""
        c = self.c
        frame = tk.Frame(nb, bg=c["panel"])
        nb.add(frame, text=_("Grupo") if party else _("Fora do grupo"))
        side = dict(frame=frame)
        hint = self.label(frame, "", "small", "muted", "panel", anchor="w", justify="left")
        hint.pack(fill="x", padx=10, pady=(8, 0))
        frame.bind("<Configure>", lambda e: hint.configure(wraplength=e.width - 30))
        side["hint"] = hint
        pw = ttk.PanedWindow(frame, orient="vertical", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True)
        upper = tk.Frame(pw, bg=c["panel"])
        lower = tk.Frame(pw, bg=c["panel"])
        pw.add(upper, weight=1)
        pw.add(lower, weight=1)
        side["title"] = self.label(upper, "", "head", bg="panel", anchor="w")
        side["title"].pack(fill="x", padx=10, pady=(6, 2))
        # o texto inteiro do alerta escolhido (a coluna Detalhe corta os longos)
        side["detail"] = self.label(upper, "", "text", "fg", "panel", anchor="w", justify="left")
        side["detail"].pack(side="bottom", fill="x", padx=10, pady=(2, 4))
        upper.bind("<Configure>", lambda e, lbl=side["detail"]: lbl.configure(wraplength=e.width - 30))
        side["alerts"] = Table(upper, self, [
            ("sev_txt", _("Gravidade"), 95, "w", "text"), ("phase", _("Fase"), 95, "w", "text"),
            ("what", _("O quê"), 270, "w", "text"), ("who", _("Quem"), 250, "w", "text"),
            ("detail", _("Detalhe"), 420, "w", "text")], height=8,
            on_select=lambda r, sd=side: self.dd_detail(sd, r))
        side["alerts"].pack(fill="both", expand=True, padx=8, pady=(0, 2))
        sub = ttk.Notebook(lower, style="Sub.TNotebook")
        sub.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        side["sub"] = sub
        phases = [("p1", _("Fase 1"), 70, "e", "text"), ("p2", _("Fase 2"), 70, "e", "text"), ("p3", _("Fase 3"), 70, "e", "text")]
        specs = []
        if party:
            specs += [
                ("buffs", _("Buffs no clímax"), [("name", _("Jogador"), 140, "w", "text"), ("job", _("Classe"), 120, "w", "text"),
                                              ("buff", _("Buff"), 210, "w", "text"), ("kind_txt", _("Tipo"), 80, "w", "text")]
                 + phases + [("note", _("Recarga / AP"), 150, "w", "text")]),
                ("debuffs", _("Debuffs no chefe"), [("debuff", _("Debuff"), 260, "w", "text"),
                                                 ("who", _("Quem aplica"), 230, "w", "text")]
                 + phases + [("note", _("Observação"), 320, "w", "text")]),
            ]
        specs += [
            ("claw", _("Garra Sombria"), [("phase", _("Fase"), 80, "w", "text"), ("start", _("Início"), 70, "e", "dur"),
                                       ("dur_txt", _("Sem Garra"), 85, "e", "text"),
                                       ("pain_txt", "Dor Máxima", 90, "center", "text"),
                                       ("refl", _("Refletidos"), 85, "e", "int"), ("who", _("Executores"), 560, "w", "text")]),
            ("deaths", _("Mortes"), [("phase", _("Fase"), 80, "w", "text"), ("t", _("Morreu"), 70, "e", "dur"),
                                  ("name", _("Jogador"), 140, "w", "text"), ("job", _("Classe"), 120, "w", "text"),
                                  ("dead_txt", _("Tempo morto"), 95, "e", "text"), ("back", _("Volta"), 170, "w", "text")]
             + ([("lost", _("Buffs que não voltaram em 15 s"), 360, "w", "text")] if party else [])),
            ("element", _("Elemento"), [
                ("name", _("Jogador"), 140, "w", "text"), ("job", _("Classe"), 120, "w", "text"),
                ("flor", _("Dano no Florescer"), 130, "e", "big"), ("fire", _("Com fogo"), 80, "e", "pct"),
                ("native", _("Sem conversor"), 100, "e", "pct"), ("unknown", _("Não visível"), 90, "e", "pct"),
                ("verdict", _("Situação"), 360, "w", "text")]),
            ("players", _("Jogadores"), [("name", _("Jogador"), 150, "w", "text"), ("job", _("Classe"), 130, "w", "text")]
             + ([("role", _("Papel"), 80, "w", "text")] if party else [])
             + [("dmg", _("Dano no chefe"), 130, "e", "big"), ("share", _("% do dano"), 85, "e", "pct"),
                ("deaths", _("Mortes"), 70, "e", "int")]
             + ([] if party else [("dead_ms", _("Maior tempo morto"), 130, "e", "dur")])),
        ]
        if party:
            specs.insert(5, ("poison", _("Veneno"), [
                ("name", _("Jogador"), 140, "w", "text"), ("job", _("Classe"), 120, "w", "text"),
                ("weapon", _("Arma com veneno"), 120, "e", "text"),
                ("venom", _("Chefe c/ Potencializar Veneno"), 190, "e", "text"),
                ("both", _("Os dois juntos"), 110, "e", "text"), ("verdict", _("Situação"), 330, "w", "text")]))
        side["tables"] = {}
        for key, title, cols in specs:
            f = tk.Frame(sub, bg=c["panel"])
            sub.add(f, text=title)
            side["tabs"] = side.get("tabs", {})
            side["tabs"][key] = f
            if key == "buffs":
                bar = tk.Frame(f, bg=c["panel"])
                bar.pack(fill="x", padx=4, pady=(6, 0))
                self.dd_only = tk.BooleanVar(self.top, True)
                ttk.Checkbutton(bar, text=_("Só o que faltou (abaixo de 50% em alguma fase)"), variable=self.dd_only,
                                style="An.TCheckbutton", command=lambda: self.refresh(force=True)).pack(side="left")
            t = Table(f, self, cols, height=4, swatch=key in ("deaths", "players", "element", "buffs", "poison"))
            t.pack(fill="both", expand=True, padx=4, pady=6)
            side["tables"][key] = t
        return side

    def dd_pick(self):
        self.dd_key = self.dd_fights.get(self.dd_var.get())
        self.refresh(force=True)

    def dd_detail(self, side, row):
        if row is None:
            side["detail"].configure(text="")
            return
        side["detail"].configure(text="%s · %s · %s%s" % (row["phase"], row["what"], row["who"],
                                                         (" — " + row["detail"]) if row["detail"] else ""),
                                 fg=self.c[{2: "bad", 1: "mid"}.get(row["sev"], "fg")])

    def refresh_dedo(self, c):
        fights = dd.boss_fights(c, self.rng)
        self.dd_fights = collections.OrderedDict((dd.fight_label(c, f), f["key"]) for f in fights)
        labels = list(self.dd_fights)
        if list(self.dd_box["values"]) != labels:
            self.dd_box["values"] = labels
        keys = list(self.dd_fights.values())
        if self.dd_key not in keys:
            self.dd_key = keys[0] if keys else None
        label = next((lb for lb, k in self.dd_fights.items() if k == self.dd_key), "")
        if self.dd_var.get() != label:
            self.dd_var.set(label)
        if self.dd_key is None:
            self.dd_result = None
            self.dd_title.configure(text=_("Nenhuma luta contra chefe neste recorte"))
            self.dd_sub.configure(text=_("O Dedo Duro olha as lutas contra MVPs, chefes de instância e bonecos de treino."))
            self.dd_counts.configure(text="")
            for side in (self.dd_group, self.dd_other):
                side["alerts"].set_rows([], lambda r: 0)
                side["title"].configure(text="")
                side["hint"].configure(text="")
                side["detail"].configure(text="")
                for t in side["tables"].values():
                    t.set_rows([], lambda r: 0)
            return
        sig = (id(c), c.version, self.dd_key, self.rng)
        if self.dd_cache[0] != sig:
            self.dd_cache = (sig, dd.analyze(c, self.dd_key, self.rng))
        r = self.dd_result = self.dd_cache[1]
        if r is None:
            return
        f = next(f for f in fights if f["key"] == self.dd_key)
        kind = _("MVP") if f["mvp"] else (_("boneco de treino") if f["dummy"] else _("chefe"))
        self.dd_title.configure(text="%s%s — %s" % ("★ " if f["mvp"] else "", r["name"].replace(" ★", ""), kind),
                                fg=self.c["accent"] if f["mvp"] else self.c["fg"])
        bits = ["%s–%s" % (dur(r["start"]), dur(r["end"])),
                (_("morto em %s") % dur(f["ttk"])) if f["ttk"] is not None else _("não morreu"),
                (lambda t: t[:1].lower() + t[1:])(dd.climax_text(r))]
        if r["defense"]:
            el = dd.ELEMENT_PT.get(r["defense"][0], r["defense"][0])
            best = ", ".join(dd.ELEMENT_PT.get(e, e) for e, _r in r["best"])
            bits.append(_("elemento %s %d%s") % (el, r["defense"][1],
                                              (_(" (vantagem: %s)") % best) if best else
                                              _(" (nenhum elemento tem vantagem; só o Florescer muda isso)")))
        else:
            bits.append(_("elemento do chefe desconhecido: só a regra do Florescer vale"))
        if r["reflect"]["used"]:
            bits.append(_("usa Dor Máxima (reflete dano)"))
        self.dd_sub.configure(text=" · ".join(bits))
        counts = collections.Counter(a["sev"] for a in r["alerts"])
        self.dd_counts.configure(text=_("grupo: ● %d grave%s   ◐ %d atenção") % (
            counts[2], "s" if counts[2] != 1 else "", counts[1]))
        self.dd_fill(self.dd_group, r, party=True)
        self.dd_fill(self.dd_other, r, party=False)
        try:
            self.dd_nb.tab(0, text=_("Grupo (%d)") % len(r["party"]))
            self.dd_nb.tab(1, text=_("Fora do grupo (%d)") % len(r["others"]))
        except tk.TclError:
            pass

    def dd_fill(self, side, r, party):
        c = self.c
        alerts = r["alerts"] if party else r["o_alerts"]
        sev_tag = lambda a: [self.SEV_TAG.get(a["sev"], "")]
        side["alerts"].set_rows(alerts, lambda a: a["key"], sev_tag)
        counts = collections.Counter(a["sev"] for a in alerts)
        if party:
            side["title"].configure(text=_("O que faltou e o que deu errado — %d grave(s), %d de atenção, "
                                         "%d informativo(s)") % (counts[2], counts[1], counts[0]))
            hint = (_("Só no clímax, por fase e com quem está vivo; só é cobrado o que alguma classe do grupo dá. "
                    "De quem gravou, todos os buffs aparecem. Dos outros, buff dado antes de começar a gravar só "
                    "aparece quando acaba (? = não dá para saber; grave antes de buffar). Competentia, Benedictum, "
                    "Presens Acies, Argutus, Lauda, Reencarnação das Almas e Talismã do Guerreiro/Mago o jogo não "
                    "mostra nos outros jogadores: desses, só se cobra de quem gravou."))
        else:
            side["title"].configure(text=(_("Jogadores fora do grupo — %d grave(s), %d de atenção") % (counts[2], counts[1]))
                                    if r["others"] else _("Ninguém de fora do grupo bateu neste chefe"))
            hint = (_("Buffs e debuffs de quem está fora do grupo não chegam no replay: aqui só aparecem dano, mortes, "
                    "a Garra Sombria e o elemento das skills de elemento fixo."))
        side["hint"].configure(text=hint)
        keys = [a["key"] for a in alerts]
        if side["alerts"].selected() is None and keys:
            side["alerts"].select(keys[0])
        self.dd_detail(side, side["alerts"].selected())
        multi = r["multi"]
        n = len(r["phases"])
        titles = {"p1": _("Fase 1") if multi else _("Clímax"), "p2": _("Fase 2"), "p3": _("Fase 3")}
        phase_keys = ["p1", "p2", "p3"][:max(1, min(3, n))]
        color = lambda row: self.color_of(row.get("aid"))
        t = side["tables"]
        if party:
            rows = r["buffs"]
            if self.dd_only.get():
                rows = [b for b in rows if b["worst"] is not None and b["worst"] < dd.BAD]
            for b in rows:
                b["kind_txt"] = _(b["kind"])
            tb = t["buffs"]
            tb.show([k for k, *_x in tb.columns if not k.startswith("p") or k in phase_keys], titles)
            tb.set_rows(rows, lambda b: b["key"],
                        lambda b: ["bad"] if b["worst"] is not None and b["worst"] < dd.BAD and b["kind"] == "grupo"
                        else (["me"] if b["me"] else []), color)
            td = t["debuffs"]
            td.show([k for k, *_x in td.columns if not k.startswith("p") or k in phase_keys], titles)
            td.set_rows(r["debuffs"], lambda d: d["key"], lambda d: ["bad"] if d["bad"] else [])
            t["poison"].set_rows(r["poison"], lambda x: x["key"], lambda x: ["mid"] if x["bad"] else [], color)
        claw = r["claw"] if party else r["o_claw"]
        for g in claw:
            g["dur_txt"] = dd._secs(g["dur"])
        t["claw"].set_rows(claw, lambda g: g["key"], lambda g: ["bad"] if g["bad"] else [])
        execs = r["claw_execs"] if party else r["o_claw_execs"]
        side["sub"].tab(side["tabs"]["claw"], text=_("Garra Sombria") + ("" if execs else _(" (sem Executor)")))
        deaths = r["deaths"] if party else r["o_deaths"]
        t["deaths"].set_rows(deaths, lambda d: d["key"], lambda d: ["bad"] if d["late"] else [], color)
        side["sub"].tab(side["tabs"]["deaths"], text=_("Mortes (%d)") % len(deaths))
        element = r["element"] if party else r["o_element"]
        t["element"].set_rows(element, lambda e: e["key"],
                              lambda e: [e["tag"]] if e.get("tag") else [], color)
        t["players"].set_rows(r["party"] if party else r["others"], lambda p_: p_["key"],
                              lambda p_: ["me"] if p_["me"] else [], color)

    def copy_dedo(self):
        c = self.combat()
        if c is None or self.dd_result is None:
            return
        self.top.clipboard_clear()
        self.top.clipboard_append(dd.report_text(c, self.dd_result))
        self.dd_copy.configure(text=_("Copiado!"))
        self.top.after(1500, lambda: self.dd_copy.configure(text=_("Copiar relatório")))

    # ------------------------------------------------------------ testes

    def build_tests(self):
        tab = tk.Frame(self.nb, bg=self.c["panel"])
        self.nb.add(tab, text=_("Testes"))
        bar = tk.Frame(tab, bg=self.c["panel"])
        bar.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(bar, text=_("Salvar recorte atual"), style="An.TButton", command=self.save_test).pack(side="left")
        ttk.Button(bar, text=_("Renomear"), style="An.TButton", command=self.rename_test).pack(side="left", padx=6)
        ttk.Button(bar, text=_("Excluir"), style="An.TButton", command=self.delete_test).pack(side="left")
        self.tests_hint = self.label(bar, "", "small", "muted", "panel")
        self.tests_hint.pack(side="left", padx=12)
        pw = ttk.PanedWindow(tab, orient="vertical", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True)
        upper = tk.Frame(pw, bg=self.c["panel"])
        lower = tk.Frame(pw, bg=self.c["panel"])
        pw.add(upper, weight=2)
        pw.add(lower, weight=3)
        self.t_tests = Table(upper, self, [
            ("when", _("Gravado em"), 120, "w", "text"), ("char", _("Personagem"), 140, "w", "text"),
            ("target", _("Alvo"), 170, "w", "text"), ("combat_ms", _("Em combate"), 85, "e", "dur"),
            ("damage", _("Dano"), 125, "e", "big"), ("dps", "DPS", 115, "e", "big"), ("label", _("Rótulo"), 200, "w", "text")],
            height=7, on_select=lambda r: self.refresh_compare(), multi=True)
        self.t_tests.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.cmp_title = self.label(lower, "", "head", bg="panel", anchor="w", justify="left")
        self.cmp_title.pack(fill="x", padx=10, pady=(8, 4))
        sub = ttk.Notebook(lower, style="Sub.TNotebook")
        sub.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        specs = [
            (_("Resumo"), [("name", _("Métrica"), 220, "w", "text"), ("a_txt", "A", 150, "e", "text"),
                        ("b_txt", "B", 150, "e", "text"), ("diff", "A × B", 100, "e", "pct")]),
            (_("Skills"), [("name", _("Skill"), 200, "w", "text"), ("a", _("A dano"), 130, "e", "big"),
                        ("a_share", "A %", 65, "e", "pct"), ("b", _("B dano"), 130, "e", "big"),
                        ("b_share", "B %", 65, "e", "pct"), ("diff", "A × B", 90, "e", "pct")]),
            (_("Equipamento"), [("slot_txt", _("Slot"), 120, "w", "text"), ("a", "A", 380, "w", "text"),
                             ("b", "B", 380, "w", "text")]),
            (_("Buffs"), [("name", _("Buff"), 220, "w", "text"), ("kind_txt", _("Tipo"), 120, "w", "text"),
                       ("a", _("A tempo ativo"), 120, "e", "pct"), ("b", _("B tempo ativo"), 120, "e", "pct")]),
        ]
        self.cmp_tables = {}
        for title, cols in specs:
            f = tk.Frame(sub, bg=self.c["panel"])
            sub.add(f, text=title)
            t = Table(f, self, cols, height=8)
            t.pack(fill="both", expand=True, padx=4, pady=6)
            self.cmp_tables[title] = t

    def store(self):
        return self.app.tests

    def refresh_tests(self):
        st = self.store()
        rows = []
        for r in st.records:
            y, mo, d, hh, mm, _ss = (r.get("recorded_at") or [0] * 6)[:6]
            rows.append(dict(r, when="%02d/%02d %02d:%02d" % (d, mo, hh, mm)))
        self.t_tests.set_rows(rows, lambda r: r["id"])
        self.tests_hint.configure(text=_("%d teste(s). Os encontros contra bonecos de treino são salvos sozinhos. "
                                       "Ctrl + clique escolhe dois para comparar.") % len(rows))
        self.refresh_compare()

    def refresh_compare(self):
        sel = self.t_tests.selected_all()
        st = self.store()
        if not sel:
            self.cmp_title.configure(text=_("Escolha um teste (compara com o anterior do mesmo personagem) ou dois."))
            for t in self.cmp_tables.values():
                t.set_rows([], lambda r: 0)
            return
        a = sel[0]
        b = sel[1] if len(sel) > 1 else st.previous(a)
        if len(sel) > 1 and (a.get("recorded_at"), a.get("start", 0)) < (b.get("recorded_at"), b.get("start", 0)):
            a, b = b, a                       # A = o mais recente
        name = lambda r: "%s · %s · %s" % (r.get("label") or r["target"], r["char"], dur(r["combat_ms"]))
        self.cmp_title.configure(text=_("A: %s     B: %s") % (name(a), name(b) if b else "—"))
        cmp = testes.compare(a, b)
        for r in cmp["summary"]:
            fmtv = (lambda v: dur(v)) if r["key"] == "combat_ms" else (lambda v: full(round(v)))
            r["a_txt"] = fmtv(r["a"])
            r["b_txt"] = fmtv(r["b"]) if r["b"] is not None else "—"
        updown = lambda r: (["good"] if (r.get("diff") or 0) > 0.005 else ["warn"] if (r.get("diff") or 0) < -0.005
                            else [])
        for r in cmp["equip"]:
            r["slot_txt"] = _(r["slot"])
        for r in cmp["buffs"]:
            r["kind_txt"] = _(r.get("kind") or "")
        self.cmp_tables[_("Resumo")].set_rows(cmp["summary"], lambda r: r["key"], updown)
        self.cmp_tables[_("Skills")].set_rows(cmp["skills"], lambda r: r["name"], updown)
        self.cmp_tables[_("Equipamento")].set_rows(cmp["equip"], lambda r: r["slot"],
                                                   lambda r: ["warn"] if r["changed"] else [])
        self.cmp_tables[_("Buffs")].set_rows(cmp["buffs"], lambda r: r["name"])

    def save_test(self):
        rf = self.app.watcher.file
        if rf is None or not rf.ready:
            return
        c = rf.combat
        label = simpledialog.askstring(_("Salvar teste"), _("Rótulo (ex.: com Coroa +12, sem Impositio):"),
                                       parent=self.top)
        if label is None:
            return
        rec = testes.build(rf, self.scope(c), label.strip())
        rec["key"] += "|manual|%s" % rec["id"]
        self.store().add(rec)
        self.refresh(force=True)

    def rename_test(self):
        sel = self.t_tests.selected_all()
        if not sel:
            return
        label = simpledialog.askstring(_("Renomear teste"), _("Rótulo:"), initialvalue=sel[0].get("label", ""),
                                       parent=self.top)
        if label is not None:
            self.store().rename(sel[0]["id"], label.strip())
            self.refresh(force=True)

    def delete_test(self):
        sel = self.t_tests.selected_all()
        if sel:
            self.store().delete([r["id"] for r in sel])
            self.refresh(force=True)

    def copy_ranking(self):
        c = self.combat()
        if c is None:
            return
        scope = self.scope(c)
        if scope is None:
            title = "%s · %s" % (c.session.player, c.map or c.session.map)
        else:
            tgt = max(scope.by_target.items(), key=lambda kv: kv[1])[0] if scope.by_target else None
            title = c.target_name(tgt) if tgt is not None else _("Encontro")
        text = an.share_text(c, self.rng, self.dur_ms, title)
        self.top.clipboard_clear()
        self.top.clipboard_append(text)
        self.copy_btn.configure(text=_("Copiado!"))
        self.top.after(1500, lambda: self.copy_btn.configure(text=_("Copiar ranking")))

    def close(self):
        try:
            self.app.cfg["an_geometry"] = self.top.geometry()
            self.app.save()
        except tk.TclError:
            pass
        self.top.destroy()
        self.app.analysis = None


def _lum(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
