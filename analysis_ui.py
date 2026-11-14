# -*- coding: utf-8 -*-
"""Janela de análise completa (Resumo, Jogadores, Equipamento, Monstros, Drops, XP, Linha do tempo, Buffs,
Mortes, Testes, Dedo Duro e Cartões), atualizada ao vivo.

Ctrl + roda (ou Ctrl + / −) muda o tamanho de tudo; o layout se reorganiza com a largura.
"""

import collections
import os
import re
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser, simpledialog, ttk

import analysis as an
import clientdata
import contrib
import dedoduro as dd
import itemkind
import itemping
import clipimg
import meter
import quests
import sprites
import testes
import ui_parts
import xp
from fmt import num, full, dur, dec
from i18n import _

# cor de cada efeito no gráfico "Por jogador" (o dano próprio usa a cor do jogador)
EFFECT_COLORS = {1142: "#22d3ee", 1183: "#4ade80", 730: "#a78bfa", 1402: "#f59e0b", 1403: "#fbbf24", 22: "#f472b6",
                 1182: "#a3e635", 608: "#ef4444", 1319: "#94a3b8",
                 -285: "#fb923c", -2468: "#d6a38f", -286: "#38bdf8", -287: "#bef264"}   # áreas no chão (−skill)
# cores bem diferentes entre si; cada jogador fica com a mesma cor em todas as tabelas e gráficos
PALETTE = ["#ff7a59", "#5b9cff", "#4ade80", "#c084fc", "#fbbf24", "#22d3ee", "#f472b6",
           "#a3e635", "#d6a38f", "#94a3b8", "#e11d48", "#2dd4bf"]
OTHERS = "#7c7f8a"
BUCKETS = [(1000, "1 s"), (2000, "2 s"), (5000, "5 s"), (10000, "10 s")]
SESSION, LATEST = _("Sessão inteira"), _("Último encontro (acompanha)")
ZOOMS = (0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6)
# abas pelo nome (a configuração antiga guardava a posição, na ordem de OLD_TABS)
TABS = ["resumo", "jogadores", "equip", "monstros", "drops", "xp", "linha", "buffs", "mortes", "testes", "dedo",
        "cartoes"]
KEEP_LABELS = [("all", "em todos os personagens"), ("char", "só neste personagem"),
               ("session", "só até fechar o programa")]      # para quem valem os itens marcados (aviso de item)
# ao vivo, a aba à vista é refeita com dados novos no máximo a cada LIVE_MIN_S, ou a cada LIVE_COST × o que levou
# para refazer (até LIVE_MAX_S): uma aba que leva 0,5 s numa sessão longa passa a ser refeita a cada 6 s
LIVE_MIN_S, LIVE_COST, LIVE_MAX_S = 1.0, 12, 30.0
TONE_LABELS = {"grave": "Grave", "medio": "Médio", "agudo": "Agudo", "bem agudo": "Bem agudo"}   # tom do aviso de item
OLD_TABS = ["resumo", "jogadores", "monstros", "dps", "buffs", "mortes", "testes", "dedo"]
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
    if kind == "num":
        return num(v)
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
        self._shown = {}                     # linha na tela -> (valores, marcas, imagem): só mexe no que mudou
        self._order = []                     # as linhas na ordem em que estão na tela
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
        try:
            self._fill(rows)
        except tk.TclError:                  # a tela não estava como o guardado: monta a tabela do zero
            self.tree.delete(*self.tree.get_children())
            self._shown, self._order = {}, []
            self._fill(rows)

    def _fill(self, rows):
        """Põe as linhas na tela mexendo só no que mudou. Uma tabela de milhares de linhas (os eventos de uma
        sessão longa) era regravada inteira a cada atualização, três chamadas ao Tk por linha: levava segundos."""
        tree, shown = self.tree, self._shown
        want = [str(self.key_fn(r)) for r in rows]
        keep = set(want)
        gone = [iid for iid in shown if iid not in keep]
        if gone:
            tree.delete(*gone)
            for iid in gone:
                del shown[iid]
        kept = [iid for iid in self._order if iid in shown]
        in_place = want[:len(kept)] == kept  # as que ficam seguem na mesma ordem: as novas entram no fim
        self._order = want
        for i, (iid, r) in enumerate(zip(want, rows)):
            values = tuple(_fmt(kind, r.get(key)) for key, _t, _w, _a, kind in self.columns)
            tags = ["odd"] if i % 2 else []
            if self.tag_fn:
                tags += self.tag_fn(r)
            kw = dict(values=values, tags=tags)
            image = None
            if self.swatch and self.color_fn:
                image = kw["image"] = self.win.swatch(self.color_fn(r))
            state = (values, tuple(tags), str(image) if image is not None else None)
            old = shown.get(iid)
            if old is None:
                tree.insert("", "end" if in_place else i, iid=iid, **kw)
            else:
                if old != state:
                    tree.item(iid, **kw)
                if not in_place and tree.index(iid) != i:
                    tree.move(iid, "", i)
            shown[iid] = state

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
        self.hist = []                # as últimas larguras aplicadas, para reconhecer um vai-e-vem
        self.swing = set()            # as duas larguras de um vai-e-vem reconhecido (ficam sem efeito)
        self.bind("<Configure>", lambda e: self.reflow())
        win.all_tiles.append(self)

    def reflow(self):
        w = self.winfo_width()
        if w <= 1:
            return                    # ainda sem tamanho (a janela não apareceu)
        if w != self.width and self.cols:
            # Quando ninguém impõe a largura (dentro de uma área de rolagem ainda sem tamanho, por exemplo), o
            # próprio conteúdo mexe nela: muda o número de colunas, o texto quebra de outro jeito, a largura
            # pedida muda e a conta recomeça. Largura A, B, A, B é isso: fica na disposição da menor e as duas
            # deixam de ter efeito, senão a janela ficava presa refazendo a conta para sempre.
            if w in self.swing:
                return
            h = self.hist
            if len(h) >= 3 and w == h[-2] and h[-1] == h[-3]:
                self.swing = {w, h[-1]}
                if w > h[-1]:
                    return
            else:
                self.swing = set()
            h.append(w)
            del h[:-4]
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
        self.left_pad = 74                   # margem esquerda (a aba de DPS usa uma maior, para os nomes das faixas)
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
        return self.left_pad * d, 14 * d, self.winfo_width() - 16 * d, self.winfo_height() - 26 * d - legend

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


class HpPicker:
    """Dificuldade do chefe (e com ela o HP), para os chefes com tabela de dificuldades: deduzida do dano
    ou escolhida aqui. Vale para o Dedo Duro, a Linha do tempo e a tabela de Monstros."""

    def __init__(self, parent, win):
        self.win = win
        self.c = self.key = None
        self.shown = False
        self.frame = tk.Frame(parent, bg=win.c["panel"])
        win.label(self.frame, _("Dificuldade:"), color="muted", bg="panel").pack(side="left")
        self.var = tk.StringVar(win.top, "")
        self.box = ttk.Combobox(self.frame, textvariable=self.var, state="readonly", width=20,
                                style="An.TCombobox", font=win.f["text"])
        self.box.pack(side="left", padx=6)
        self.box.bind("<<ComboboxSelected>>", lambda e: self.picked())

    def sync(self, c, key):
        self.c, self.key = c, key
        levels = an.hp_levels(c, key) if c is not None and key is not None else []
        if not levels:
            if self.shown:
                self.frame.pack_forget()
                self.shown = False
            return
        values = [_("deduzir pelo dano")] + ["%s — %s" % (name, num(hp)) for name, hp in levels]
        if list(self.box["values"]) != values:
            self.box["values"] = values
        i = an.hp_choice(c, key)
        self.var.set(values[0 if i is None else i + 1])
        if not self.shown:
            self.frame.pack(side="left", padx=(12, 0))
            self.shown = True

    def picked(self):
        values = list(self.box["values"])
        if self.var.get() in values and self.c is not None:
            i = values.index(self.var.get())
            an.choose_hp(self.c, self.key, None if i == 0 else i - 1)
            self.win.refresh(force=True)


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


def _nice_up(x):
    """O número "redondo" logo acima de x (funciona com frações: 0,37 -> 0,4; 1.234 -> 1.500)."""
    import math
    if x <= 0:
        return 1
    e = 10 ** math.floor(math.log10(x))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * e >= x * 0.999:
            return m * e
    return 10 * e


def _nice_time(ms):
    for s in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600):
        if s * 1000 >= ms:
            return s * 1000
    return 3600000


class AnalysisWindow:
    def __init__(self, app):
        self.app = app
        self.top = tk.Toplevel(app.root)
        self.top.withdraw()                  # só aparece depois de montada e preenchida (veja o fim do __init__)
        self.top.title(_("Análise — Replay Master   (Ctrl + roda do mouse: tamanho)"))
        self.dpi = app.dpi
        try:
            self.zoom = float(app.cfg.get("an_zoom") or 1.0)
        except (TypeError, ValueError):
            self.zoom = 1.0
        self.sig = None
        self.scope_items = []
        self.mob_key = None
        self.player_aid = None
        self.dd_key = None
        self.dd_cache = (None, None)
        self.dd_result = None
        self.combat_id = None
        self.colors = {}
        self.tables = []
        self.all_tiles = []                  # todos os grupos de cartões (refeitos quando o tamanho muda)
        self._swatches = {}
        self.icons = ui_parts.Icons(self)    # ícones dos itens (do data.grf do jogo)
        self._common = (None, [], 0, 0)      # (chave, jogadores, dano do grupo, eventos) do recorte à vista
        self._last = 0.0
        self._next = 0.0                     # ao vivo, a próxima atualização automática só depois disto
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
        self.start_geo = self.fit_geometry(app.cfg.get("an_geometry"))
        self.top.geometry(self.start_geo)
        self.top.minsize(int(900 * self.dpi), int(500 * self.dpi))   # abaixo disso as abas não cabem
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
        # sem update_idletasks aqui: com a janela escondida nada tem largura imposta, e forçar o layout nessa hora
        # deixava os quadros do Resumo trocando de largura sem parar (a janela nunca abria)
        self.normal_geo = None if self.open_zoomed else self.start_geo
        self.top.bind("<Configure>", self.note_geometry, add="+")
        if self.open_zoomed:
            try:
                self.top.state("zoomed")
            except tk.TclError:
                pass
        self.bring_to_front()

    def note_geometry(self, e):
        """Lembra o tamanho e a posição da janela enquanto ela não está maximizada (é o que fica guardado)."""
        if e.widget is self.top:
            try:
                if self.top.state() == "normal":
                    self.normal_geo = self.top.geometry()
            except tk.TclError:
                pass

    def work_area(self, x=None, y=None):
        """(esquerda, topo, direita, base) da área útil (sem a barra de tarefas) do monitor do ponto dado, ou do
        monitor onde o widget está."""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            if x is None:
                x = self.app.root.winfo_rootx() + self.app.root.winfo_width() // 2
                y = self.app.root.winfo_rooty() + self.app.root.winfo_height() // 2
            user32.MonitorFromPoint.restype = ctypes.c_void_p
            user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            mon = user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)      # 2 = o monitor mais próximo
            info = (ctypes.c_long * 10)()
            info[0] = ctypes.sizeof(info)
            if mon and user32.GetMonitorInfoW(mon, info):
                return info[5], info[6], info[7], info[8]
        except Exception:  # noqa: BLE001 - sem a área do monitor, vale a tela inteira
            pass
        return 0, 0, self.top.winfo_screenwidth(), self.top.winfo_screenheight() - int(48 * self.dpi)

    def fit_geometry(self, geo):
        """A posição e o tamanho guardados, ajustados para a janela caber inteira na área útil do monitor (ela
        abria cortada quando tinha sido guardada num monitor maior ou com outra escala). Sem nada guardado, o
        tamanho padrão no monitor onde o widget está."""
        # "LxA+X+Y"; num monitor à esquerda ou acima do principal o Tk escreve a posição negativa como "+-X"
        m = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", geo or "")
        frame = int(40 * self.dpi)             # a barra de título e as bordas ficam fora do tamanho pedido
        self.open_zoomed = bool(self.app.cfg.get("an_zoomed"))
        area = None
        if m:
            w, h, x, y = (int(v) for v in m.groups())
            area = self.work_area(x + w // 2, y + h // 2)
            if w >= area[2] - area[0] - frame and h >= area[3] - area[1] - 2 * frame:
                # o tamanho da tela inteira: foi guardada maximizada (as versões anteriores guardavam assim, com a
                # posição de antes de maximizar, e a janela abria cortada). Abre maximizada nesse monitor.
                self.open_zoomed, m = True, None
        if m:
            left, top, right, bottom = area
        else:
            left, top, right, bottom = area or self.work_area()
            w, h = int(1120 * self.dpi), int(800 * self.dpi)
            x, y = left + (right - left - w) // 2, top + (bottom - top - h - frame) // 2
        w = max(int(600 * self.dpi), min(w, right - left - int(16 * self.dpi)))
        h = max(int(400 * self.dpi), min(h, bottom - top - frame - int(8 * self.dpi)))
        x = max(left, min(x, right - w - int(16 * self.dpi)))
        y = max(top, min(y, bottom - h - frame))
        return "%dx%d+%d+%d" % (w, h, x, y)

    def bring_to_front(self):
        """Mostra a janela na frente das outras. O widget não toma o foco do jogo, então para o Windows este
        programa não é o que está em uso e uma janela nova abriria por trás: passar um instante por "sempre no
        topo" traz a janela para cima de qualquer jeito; o foco é pedido em seguida."""
        try:
            if self.top.state() in ("withdrawn", "iconic"):
                self.top.deiconify()
            self.top.lift()
            self.top.attributes("-topmost", True)
            self.top.after(250, lambda: self.top.winfo_exists() and self.top.attributes("-topmost", False))
            self.top.focus_force()
        except tk.TclError:
            pass

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
        for tiles in self.all_tiles:
            tiles.cols = 0
            tiles.reflow()
        self.tab_pad, self.tab_font = 16, "head"     # a letra mudou: recalcula o que cabe
        self.fit_tabs()
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
        s.configure("An.TNotebook.Tab", background=c["bg"], foreground=c["muted"],
                    padding=(getattr(self, "tab_pad", 16), 7), font=f[getattr(self, "tab_font", "head")], borderwidth=0)
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
        # imagem da aba para colar no Discord; Ctrl+Shift+C copia só o gráfico que está sob o mouse (com a dica aberta)
        self.copy_img_btn = ttk.Button(head, text=_("Copiar imagem"), style="An.TButton", command=self.copy_image)
        self.copy_img_btn.pack(side="right", padx=(0, 6))
        self.hide_names_var = tk.BooleanVar(self.top, bool(self.app.cfg.get("copy_hide_names")))
        ttk.Checkbutton(head, text=_("sem nomes"), variable=self.hide_names_var, style="An.TCheckbutton",
                        command=self.hide_names_changed).pack(side="right", padx=(0, 6))
        self.label(head, _("Ctrl+Shift+C: só o gráfico sob o mouse"), "small", "muted").pack(side="right", padx=(0, 10))
        for seq in ("<Control-Shift-C>", "<Control-Shift-c>"):
            self.top.bind(seq, self.copy_hovered)
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
        self.nb.bind("<Configure>", lambda e: self.fit_tabs())
        self.build_summary()
        self.build_players()
        self.build_equip()
        self.build_monsters()
        self.build_drops()
        self.build_xp()
        import timeline_ui
        self.timeline = timeline_ui.TimelineTab(self, self.nb)
        self.build_buffs()
        self.build_deaths()
        self.build_tests()
        self.build_dedo()
        import ui_cards
        self.cards_tab = ui_cards.CardsTab(self, self.nb)
        saved = self.app.cfg.get("an_tab", 0)
        if isinstance(saved, int) and 0 <= saved < len(OLD_TABS):
            saved = OLD_TABS[saved]
        if saved in TABS:
            self.select_tab(saved)

    def tab_name(self):
        try:
            return TABS[self.nb.index(self.nb.select())]
        except (tk.TclError, IndexError):
            return TABS[0]

    def select_tab(self, name):
        self.nb.select(TABS.index(name))

    def section(self, parent, text, bg="panel"):
        lbl = self.label(parent, text, "head", bg=bg, anchor="w")
        lbl.pack(fill="x", padx=10, pady=(10, 4))
        return lbl

    def build_summary(self):
        import ui_summary
        self.summary_tab = ui_summary.SummaryTab(self, self.nb)

    def build_players(self):
        tab = tk.Frame(self.nb, bg=self.c["panel"])
        self.nb.add(tab, text=_("Jogadores"))
        pw = ttk.PanedWindow(tab, orient="vertical", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True)
        upper = tk.Frame(pw, bg=self.c["panel"])
        lower = tk.Frame(pw, bg=self.c["panel"])
        pw.add(upper, weight=3)
        pw.add(lower, weight=3)
        self.section(upper, _("Jogadores — o grupo inteiro (quem não deu dano também); dano de invocações e skills "
                              "de chão conta para o dono"))
        self.t_players = Table(upper, self, [
            ("name", _("Jogador"), 150, "w", "text"), ("job", _("Classe"), 115, "w", "text"),
            ("total", _("Dano"), 112, "e", "big"), ("dps", "DPS", 95, "e", "big"),
            ("adps", _("DPS ativo"), 95, "e", "big"), ("share", "%", 55, "e", "pct"),
            ("crit_pct", _("Crít."), 55, "e", "pct"), ("max_hit", _("Maior golpe"), 100, "e", "big"),
            ("taken", _("Recebido"), 95, "e", "big"), ("deaths", _("Mortes"), 55, "e", "int"),
            ("uses", _("Suporte"), 65, "e", "int"), ("items", _("Itens"), 50, "e", "int"),
            ("kills", _("Abates"), 55, "e", "int")], height=7, on_select=self.player_selected, swatch=True)
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
        # o que mais se sabe de cada um: suporte e itens, dano recebido e buffs
        fs = tk.Frame(sub, bg=self.c["panel"])
        sub.add(fs, text=_("Suporte e itens"))
        fs.columnconfigure(0, weight=3, uniform="s")
        fs.columnconfigure(1, weight=2, uniform="s")
        fs.rowconfigure(0, weight=1)
        self.t_psupport = Table(fs, self, [
            ("name", _("Skill sem dano (buff, cura, debuff)"), 240, "w", "text"), ("uses", _("Usos"), 60, "e", "int"),
            ("targets", _("Alvos"), 60, "e", "int")], height=6)
        self.t_psupport.grid(row=0, column=0, sticky="nsew", padx=(4, 2), pady=6)
        self.t_pitems = Table(fs, self, [("name", _("Item usado"), 220, "w", "text"), ("n", _("Vezes"), 60, "e", "int")],
                              height=6)
        self.t_pitems.grid(row=0, column=1, sticky="nsew", padx=(2, 4), pady=6)
        ft = tk.Frame(sub, bg=self.c["panel"])
        sub.add(ft, text=_("Dano recebido"))
        self.t_ptaken = Table(ft, self, [
            ("source", _("Fonte"), 200, "w", "text"), ("name", _("Habilidade"), 200, "w", "text"),
            ("hits", _("Acertos"), 70, "e", "int"), ("total", _("Dano"), 120, "e", "big"),
            ("max_hit", _("Maior golpe"), 110, "e", "big"), ("share", "%", 60, "e", "pct")], height=6)
        self.t_ptaken.pack(fill="both", expand=True, padx=4, pady=6)
        fb = tk.Frame(sub, bg=self.c["panel"])
        sub.add(fb, text=_("Buffs"))
        self.t_pbuffs = Table(fb, self, [
            ("name", _("Buff"), 240, "w", "text"), ("kind_txt", _("Tipo"), 130, "w", "text"),
            ("uptime", _("Ativo"), 70, "e", "pct")], height=6)
        self.t_pbuffs.pack(fill="both", expand=True, padx=4, pady=6)
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

    # ------------------------------------------------------------ equipamento

    def build_equip(self):
        c = self.c
        tab = tk.Frame(self.nb, bg=c["panel"])
        self.nb.add(tab, text=_("Equipamento"))
        bar = tk.Frame(tab, bg=c["panel"])
        bar.pack(fill="x", padx=10, pady=(10, 2))
        self.label(bar, _("Momento:"), color="muted", bg="panel").pack(side="left")
        self.eq_when = tk.StringVar(self.top, "")
        self.eq_when_box = ttk.Combobox(bar, textvariable=self.eq_when, width=56, state="readonly",
                                        style="An.TCombobox", font=self.f["text"])
        self.eq_when_box.pack(side="left", padx=6)
        self.eq_when_box.bind("<<ComboboxSelected>>", lambda e: self.refresh(force=True))
        self.eq_moments = {}
        self.eq_title = self.label(bar, "", "head", bg="panel", anchor="w")
        self.eq_title.pack(side="left", padx=(14, 0))
        body = ScrollFrame(tab, self).inner
        body.columnconfigure(0, weight=1, uniform="eq")
        body.columnconfigure(2, weight=1, uniform="eq")
        # o equipamento de verdade à esquerda, o personagem no meio, sombrios e visuais à direita
        self.eq_gear = ui_parts.EquipPanel(body, self, groups=ui_parts.GROUPS[:1])
        self.eq_gear.grid(row=0, column=0, sticky="new", padx=(4, 0), pady=(6, 10))
        self.eq_special = ui_parts.EquipPanel(body, self, groups=ui_parts.GROUPS[1:])
        self.eq_special.grid(row=0, column=2, sticky="new", padx=(0, 4), pady=(6, 10))
        left = tk.Frame(body, bg=c["tile"])
        left.grid(row=0, column=1, sticky="n", padx=6, pady=(10, 10))
        self.eq_scale = max(2, int(round(2 * self.dpi)))
        sc = self.eq_scale
        self.eq_canvas = tk.Canvas(left, width=150 * sc, height=150 * sc, bg=c["tile"], highlightthickness=0, bd=0,
                                   cursor="hand2")
        self.eq_canvas.pack(padx=10, pady=(10, 0))
        # clique: metade esquerda gira para um lado, metade direita para o outro (como girar o boneco)
        self.eq_canvas.bind("<Button-1>", lambda e: self.eq_turn(1 if e.x < self.eq_canvas.winfo_width() / 2 else -1))
        ctr = tk.Frame(left, bg=c["tile"])
        ctr.pack(fill="x", padx=10, pady=(6, 2))
        ttk.Button(ctr, text="\u27f2", width=3, style="An.TButton", command=lambda: self.eq_turn(1)).pack(side="left")
        ttk.Button(ctr, text="\u27f3", width=3, style="An.TButton",
                   command=lambda: self.eq_turn(-1)).pack(side="left", padx=(4, 0))
        self.eq_action = tk.StringVar(self.top, _("Andando"))      # anda por padrão, como no jogo
        box = ttk.Combobox(ctr, textvariable=self.eq_action, values=[_(n) for _a, n in sprites.ACTIONS], width=13,
                           state="readonly", style="An.TCombobox", font=self.f["text"])
        box.pack(side="left", padx=(8, 0))
        box.bind("<<ComboboxSelected>>", lambda e: self.eq_restart())
        ctr2 = tk.Frame(left, bg=c["tile"])
        ctr2.pack(fill="x", padx=10, pady=(4, 2))
        self.label(ctr2, _("Cabeça:"), color="muted", bg="tile").pack(side="left")
        self.eq_head = tk.StringVar(self.top, _("Frente"))
        box = ttk.Combobox(ctr2, textvariable=self.eq_head, values=[_(n) for _h, n in sprites.HEAD_DIRS], width=10,
                           state="readonly", style="An.TCombobox", font=self.f["text"])
        box.pack(side="left", padx=(6, 0))
        box.bind("<<ComboboxSelected>>", lambda e: self.eq_restart())
        self.eq_info = self.label(left, "", "small", "muted", "tile", anchor="w", justify="left",
                                  wraplength=150 * sc)
        self.eq_info.pack(fill="x", padx=10, pady=(6, 10))
        self.eq_dir, self.eq_frame, self.eq_after = 0, 0, None
        self.eq_look, self.eq_images, self.eq_loader_v = None, {}, -1

    def refresh_equip(self, c):
        moments = an.equip_moments(c)
        labels = collections.OrderedDict()
        for t, changed in moments:
            if t == 0:
                labels[_("Início da gravação")] = 0
            else:
                names = ", ".join(_(x) for x in changed[:4]) + ("…" if len(changed) > 4 else "")
                labels[_("%s · trocou %s") % ("%d:%02d" % divmod(t // 1000, 60), names)] = t
        self.eq_moments = labels
        if list(self.eq_when_box["values"]) != list(labels):
            self.eq_when_box["values"] = list(labels)
        if self.eq_when.get() not in labels:
            self.eq_when.set(next(iter(labels)))
        t = labels[self.eq_when.get()]
        rows = an.equipment(c, t)
        sig = (id(c), t, len(rows), self.zoom, xp.GEAR.table is None)
        if sig != getattr(self, "eq_sig", None):
            self.eq_sig = sig
            self.eq_gear.set(rows)
            self.eq_special.set(rows)
        self.eq_title.configure(text=_("Equipamento de %s") % (
            (c.name_of(c.me) if meter.HIDE_NAMES else c.session.player) or _("quem gravou")) if rows
                                else _("O replay não trouxe a lista de itens de quem gravou"))
        # visual: o do início da gravação, com chapéus/capa/arma/escudo dos itens vestidos no momento escolhido
        grf = clientdata.NAMES.grf
        sprites.LOADER.start(grf)
        w = sprites.LOADER.wardrobe
        worn = c.worn_at(t)
        look = sprites.look_at(c.session.look, worn, w.classnum) if (w and worn) else dict(c.session.look)
        if look != self.eq_look:
            self.eq_look = look
            self.eq_frame = 0
            if len(self.eq_images) > 300:
                self.eq_images = {}
        self.eq_draw()

    def eq_turn(self, step):
        self.eq_dir = (self.eq_dir + step) % 8
        self.eq_draw()

    def eq_restart(self):
        self.eq_frame = 0
        self.eq_draw()

    def eq_choice(self):
        action = next((a for a, n in sprites.ACTIONS if _(n) == self.eq_action.get()), sprites.IDLE)
        head = next((h for h, n in sprites.HEAD_DIRS if _(n) == self.eq_head.get()), 0)
        return action, head

    def eq_draw(self):
        """Desenha o quadro atual e agenda o próximo (anima enquanto a aba estiver aberta)."""
        if self.eq_after is not None:
            try:
                self.top.after_cancel(self.eq_after)
            except tk.TclError:
                pass
            self.eq_after = None
        cv, col, sc = self.eq_canvas, self.c, self.eq_scale
        cv.delete("all")
        W, H = int(cv["width"]), int(cv["height"])
        loader = sprites.LOADER
        w = loader.wardrobe
        if w is None or self.eq_look is None:
            if loader.loading or (self.eq_look is not None and clientdata.NAMES.grf and loader.error is None):
                msg = _("Carregando os sprites do jogo…")
                self.eq_after = self.top.after(250, self.eq_wait_loader)
            elif loader.error:
                msg = _("Não deu para ler o data.grf do jogo (%s).") % loader.error
            else:
                msg = _("Jogo não encontrado: o visual é montado com os sprites do data.grf da instalação.")
            cv.create_text(W / 2, H / 2, text=msg, fill=col["muted"], font=self.f["text"], width=W - 20)
            self.eq_info.configure(text="")
            return
        action, head = self.eq_choice()
        look = self.eq_look
        key = (tuple(sorted(look.items())), action, self.eq_dir, head, self.eq_frame)
        img = self.eq_images.get(key)
        if img is None:
            r = w.render(look, action, self.eq_dir, self.eq_frame, head)
            if r is None:
                cv.create_text(W / 2, H / 2, text=_("Sem sprite para esta classe."), fill=col["muted"],
                               font=self.f["text"], width=W - 20)
                return
            iw, ih, px, ox, oy, delay, nframes, missing = r
            photo = tk.PhotoImage(master=self.top, data=sprites.png_b64(iw, ih, px), format="png")
            if sc > 1:
                photo = photo.zoom(sc)
            img = self.eq_images[key] = (photo, ox * sc, oy * sc, delay, nframes, missing)
        photo, ox, oy, delay, nframes, missing = img
        fx, fy = W / 2, H - 22 * sc
        cv.create_oval(fx - 14 * sc, fy - 4 * sc, fx + 14 * sc, fy + 4 * sc, fill=_mix(col["tile"], "#000000", 0.35),
                       outline="")
        cv.create_image(fx - ox, fy - oy, image=photo, anchor="nw")
        info = [meter.job_name(look.get("job", 0)),
                _("cabelo %d, cor %d · roupa cor %d") % (look.get("hair") or 1, look.get("hair_color", 0),
                                                         look.get("cloth_color", 0)),
                _("direção %s") % sprites.DIRECTIONS[self.eq_dir]]
        if missing:
            names = {"corpo": _("corpo"), "cabeça": _("cabeça"), "low": _("chapéu de baixo"),
                     "mid": _("chapéu do meio"), "top": _("chapéu de cima"), "robe": _("capa")}
            info.append(_("sem sprite no jogo: %s") % ", ".join(names.get(m, m) for m in missing))
        self.eq_info.configure(text="\n".join(x for x in info if x))
        if action not in (sprites.IDLE, sprites.SIT) and nframes > 1 and self.tab_name() == "equip":
            self.eq_after = self.top.after(int(delay), self.eq_tick)

    def eq_tick(self):
        self.eq_after = None
        if self.tab_name() != "equip":
            return
        self.eq_frame += 1
        self.eq_draw()

    def eq_wait_loader(self):
        """Espera o guarda-roupa carregar e redesenha com o visual do momento escolhido."""
        self.eq_after = None
        if sprites.LOADER.loading:
            self.eq_after = self.top.after(250, self.eq_wait_loader)
            return
        if self.tab_name() == "equip":
            self.refresh(force=True)

    def build_monsters(self):
        import ui_mobs
        self.mobs_tab = ui_mobs.MobsTab(self, self.nb)

    def build_drops(self):
        c = self.c
        tab = tk.Frame(self.nb, bg=c["panel"])
        self.nb.add(tab, text=_("Drops"))
        self.drop_tiles = Tiles(tab, self, [
            ("fell", _("Itens que caíram")), ("mine", _("Pegos por você")), ("others", _("Pegos por outros")),
            ("ground", _("Ficaram no chão")), ("mvp", _("Prêmios de MVP")), ("kinds", _("Itens diferentes"))],
            min_w=150, dense=True)
        self.drop_tiles.pack(fill="x", padx=10, pady=(10, 0))
        self.label(tab, _("Itens que caíram de monstros no recorte. \"Pego por\" vem da ação de pegar do jogo; quando "
                          "ela não aparece, vale o item que entrou na bolsa de quem grava logo depois de sumir do "
                          "chão. Botão direito num item: favoritar, fixar no widget, ocultar ou avisar quando cair "
                          "(um som curto e o lugar do item no widget)."), "small", "muted",
                   "panel", anchor="w", justify="left", wraplength=1100).pack(fill="x", padx=12, pady=(6, 2))
        legend = tk.Frame(tab, bg=c["panel"])
        legend.pack(fill="x", padx=12, pady=(2, 2))
        self.label(legend, _("Cores (clique para trocar):"), "small", "muted", "panel").pack(side="left")
        self.drop_chips = {}
        for kind in ("equip", "card", "mvpcard", "refine", "alch", "episode"):
            chip = tk.Label(legend, text="", font=self.f["small"], bg=c["panel"], cursor="hand2", padx=6,
                            compound="left")
            chip.pack(side="left", padx=(6, 0))
            chip.bind("<Button-1>", lambda e, k=kind: self.pick_drop_color(k))
            chip.bind("<Button-3>", lambda e, k=kind: self.drop_color_menu(e, k))
            self.drop_chips[kind] = chip
        ttk.Button(legend, text=_("Cores padrão"), style="An.TButton",
                   command=self.reset_drop_colors).pack(side="left", padx=(10, 0))
        self.drop_hidden_btn = ttk.Button(legend, text="", style="An.TButton", command=self.hidden_drops_menu)
        self.drop_hidden_btn.pack(side="right")
        grid = tk.Frame(tab, bg=c["panel"])
        grid.pack(fill="both", expand=True, pady=(2, 4))
        for i in (0, 1):
            grid.columnconfigure(i, weight=1, uniform="drops")
            grid.rowconfigure(i, weight=1, uniform="drops")

        def box(row, col, title):
            f = tk.Frame(grid, bg=c["tile"])
            f.grid(row=row, column=col, sticky="nsew", padx=6, pady=4)
            lbl = self.section(f, title, bg="tile")
            return f, lbl
        f, self.drop_mine_title = box(0, 0, _("Você pegou"))
        self.t_drop_mine = Table(f, self, [
            ("time", _("Tempo"), 64, "e", "text"), ("name", _("Item"), 190, "w", "text"),
            ("count", _("Qtd."), 46, "e", "int"), ("mob", _("De onde"), 150, "w", "text")], height=6)
        self.t_drop_mine.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        f, self.drop_others_title = box(0, 1, _("Pegos por outros jogadores"))
        self.t_drop_others = Table(f, self, [
            ("time", _("Tempo"), 64, "e", "text"), ("name", _("Item"), 190, "w", "text"),
            ("count", _("Qtd."), 46, "e", "int"), ("who", _("Quem pegou"), 130, "w", "text"),
            ("mob", _("Monstro"), 130, "w", "text")], height=6)
        self.t_drop_others.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        f, self.drop_ground_title = box(1, 0, _("Ficaram no chão"))
        self.t_drop_ground = Table(f, self, [
            ("time", _("Tempo"), 64, "e", "text"), ("name", _("Item"), 190, "w", "text"),
            ("count", _("Qtd."), 46, "e", "int"), ("mob", _("Monstro"), 130, "w", "text"),
            ("where", _("Onde"), 70, "w", "text"), ("fate", _("Destino"), 140, "w", "text")], height=6)
        self.t_drop_ground.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        f, _lbl = box(1, 1, _("Por item"))
        # avisos de item: a coluna ♪ marca os que já caíram; o botão abre a busca na lista de itens do jogo
        self.drop_ping_btn = ttk.Button(f, text=_("Avisos de item…"), style="An.TButton", command=self.open_pings)
        self.drop_ping_btn.place(relx=1.0, x=-6, y=2, anchor="ne")
        self.t_drop_items = Table(f, self, [
            ("star", "★", 34, "center", "text"), ("ping", "♪", 30, "center", "text"),
            ("name", _("Item"), 200, "w", "text"),
            ("fell", _("Caíram"), 70, "e", "int"), ("mine", _("Você pegou"), 90, "e", "int"),
            ("mvp", _("MVP"), 50, "e", "int")], height=6)
        self.t_drop_items.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.t_drop_items.tree.bind("<Button-1>", self.drop_star_click, add="+")
        for table in (self.t_drop_mine, self.t_drop_others, self.t_drop_ground, self.t_drop_items):
            table.tree.bind("<Button-3>", lambda e, t=table: self.drop_row_menu(e, t), add="+")
        self.color_drop_tags()

    def drop_colors(self):
        """{categoria: cor legível neste tema ou None}."""
        out = {}
        for kind, color in itemkind.colors(self.app.cfg).items():
            if color and _lum(self.c["panel"]) > 0.5:
                color = _mix(color, "#000000", 0.45)
            out[kind] = color
        return out

    def color_drop_tags(self):
        """Cores das categorias nas 4 tabelas e na legenda."""
        cols = self.drop_colors()
        for table in (self.t_drop_mine, self.t_drop_others, self.t_drop_ground, self.t_drop_items):
            for kind, color in cols.items():
                table.tree.tag_configure("k_" + kind, foreground=color or self.c["fg"])
        for kind, chip in self.drop_chips.items():
            color = cols.get(kind)
            chip.configure(text=" " + _(itemkind.NAMES[kind]), fg=color or self.c["muted"],
                           image=self.swatch(color) if color else "")

    def drop_tags(self, r):
        """Etiquetas de uma linha de drop: a categoria (cor) e "me" para o que quem grava pegou."""
        kind = itemkind.kind(r["item"], meter.ITEMS.get(str(r["item"]), {}).get("name"))
        tags = ["k_" + kind] if kind and itemkind.colors(self.app.cfg).get(kind) else []
        return tags

    def pick_drop_color(self, kind):
        now = itemkind.colors(self.app.cfg).get(kind) or itemkind.DEFAULT_COLORS[kind]
        got = colorchooser.askcolor(color=now, parent=self.top, title=_(itemkind.NAMES[kind]))
        if got and got[1]:
            self.set_drop_color(kind, got[1])

    def set_drop_color(self, kind, color):
        cols = dict(self.app.cfg.get("drop_colors") or {})
        if color is None:
            cols.pop(kind, None)               # volta à cor padrão
        else:
            cols[kind] = color                 # "" = sem cor
        self.app.cfg["drop_colors"] = cols
        self.app.save()
        self.color_drop_tags()
        self.app.drops_changed()

    def reset_drop_colors(self):
        self.app.cfg["drop_colors"] = {}
        self.app.save()
        self.color_drop_tags()
        self.app.drops_changed()

    def drop_color_menu(self, e, kind):
        m = tk.Menu(self.top, tearoff=0)
        m.add_command(label=_("Escolher cor…"), command=lambda: self.pick_drop_color(kind))
        m.add_command(label=_("Sem cor"), command=lambda: self.set_drop_color(kind, ""))
        m.add_command(label=_("Cor padrão"), command=lambda: self.set_drop_color(kind, None))
        self._menu = m
        m.tk_popup(e.x_root, e.y_root)

    def drop_row_menu(self, e, table):
        """Botão direito num item das tabelas de drops: favoritar, fixar no widget, ocultar."""
        iid = table.tree.identify_row(e.y)
        r = table.rows.get(iid) if iid else None
        if not r or r.get("item") is None:
            return None
        item = r["item"]
        app = self.app
        app.menu_refs = []
        m = tk.Menu(self.top, tearoff=0)
        fav = item in (app.cfg.get("drop_favs") or [])
        m.add_command(label=meter.item_name(item), state="disabled")
        m.add_separator()
        m.add_command(label=_("Tirar dos favoritos") if fav else _("Favoritar (fica no topo)"),
                      command=lambda: app.toggle_fav(item))
        m.add_command(label=_("Parar de avisar quando cair") if item in app.ping_items()
                      else _("Avisar quando cair (som e lugar)"), command=lambda: app.toggle_ping(item))
        pin = "item:%d" % item
        m.add_command(label=_("Desafixar do widget") if pin in (app.cfg.get("pins") or []) else _("Fixar no widget"),
                      command=lambda: app.toggle_pin_stat(pin))
        m.add_separator()
        m.add_command(label=_("Ocultar até fechar o programa"), command=lambda: app.hide_item(item, False))
        m.add_command(label=_("Ocultar sempre"), command=lambda: app.hide_item(item, True))
        hm = app.hidden_menu(m)
        if hm is not None:
            m.add_cascade(label=_("Itens ocultos"), menu=hm)
        self._menu = m
        m.tk_popup(e.x_root, e.y_root)
        return "break"

    def hidden_drops_menu(self):
        app = self.app
        app.menu_refs = []
        hm = app.hidden_menu(self.top)
        if hm is None:
            return
        self._menu = hm
        b = self.drop_hidden_btn
        hm.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def refresh_drops(self, c):
        rng = self.rng
        inside = lambda t: rng is None or rng[0] <= t <= rng[1]
        hidden = self.app.hidden_items()            # ocultos (botão direito) somem de toda a aba
        itemkind.start()
        drops = [d for d in c.drops if d["fell"] and inside(d["t"]) and d["item"] not in hidden]
        mvp = [(t, i) for t, i in c.mvp_items if inside(t) and i not in hidden]
        items = [r for r in c.drop_summary(rng) if r["item"] not in hidden]
        self.drop_hidden_btn.configure(text=_("Itens ocultos (%d) ▾") % len(hidden) if hidden else _("Nenhum item oculto"),
                                       state="normal" if hidden else "disabled")
        if itemkind.loading():                      # cores dos equipamentos e cartas: o jogo ainda está sendo lido
            self.top.after(800, lambda: self.refresh(force=True) if self.tab_name() == "drops" else None)
        mine_rows, other_rows, ground_rows = [], [], []
        for i, d in enumerate(drops):
            row = dict(key=i, t=d["t"], time=dur(d["t"]), name=meter.item_name(d["item"]), count=d["count"],
                       mob=d["mob"] or "", where="%d, %d" % (d["x"], d["y"]), item=d["item"])
            if d["mine"]:
                mine_rows.append(row)
            elif d["by"] is not None:
                row["who"] = c.name_of(d["by"])
                other_rows.append(row)
            else:
                row["fate"] = (_("sumiu %s depois") % dur(d["gone"] - d["t"])) if d["gone"] is not None \
                    else _("ainda no chão")
                ground_rows.append(row)
        for t, item in mvp:
            mine_rows.append(dict(key="mvp%d" % t, t=t, time=dur(t), name=meter.item_name(item), count=1,
                                  mob=_("prêmio de MVP"), item=item))
        for rows in (mine_rows, other_rows, ground_rows):
            rows.sort(key=lambda r: r["t"])
        count = lambda rows: sum(r["count"] for r in rows)
        put = self.drop_tiles.put
        put("fell", "%d" % sum(d["count"] for d in drops))
        put("mine", "%d" % count(mine_rows), "", self.c["accent"])
        put("others", "%d" % count(other_rows))
        put("ground", "%d" % count(ground_rows))
        put("mvp", "%d" % len(mvp), ", ".join(meter.item_name(i) for _t, i in mvp[:2]))
        put("kinds", "%d" % len(items))
        self.drop_mine_title.configure(text=_("Você pegou — %d") % count(mine_rows))
        self.drop_others_title.configure(text=_("Pegos por outros jogadores — %d") % count(other_rows))
        self.drop_ground_title.configure(text=_("Ficaram no chão — %d") % count(ground_rows))
        self.t_drop_mine.set_rows(mine_rows, lambda r: r["key"], self.drop_tags)
        self.t_drop_others.set_rows(other_rows, lambda r: r["key"], self.drop_tags)
        self.t_drop_ground.set_rows(ground_rows, lambda r: r["key"], self.drop_tags)
        marked = self.app.cfg.get("drop_favs") or []
        favs = set(marked)
        pings = self.app.ping_items()
        self.drop_ping_btn.configure(text=(_("Avisos de item (%d)…") % len(pings)) if pings else _("Avisos de item…"))
        dlg = getattr(self, "ping_dlg", None)
        if dlg is not None and dlg.winfo_exists():        # a janela dos avisos aberta mostra a lista de agora
            self.ping_fill()
        for r in items:
            r["star"] = "★" if r["item"] in favs else "☆"
            r["ping"] = "♪" if r["item"] in pings else "·"
        items = itemkind.favorites_first(items, marked)       # favoritos no topo, na ordem em que foram marcados
        self.t_drop_items.set_rows(items, lambda r: r["item"],
                                   lambda r: self.drop_tags(r) or (["me"] if r["mine"] else []))

    def drop_star_click(self, e):
        """Clique na estrela de "Por item": marca/desmarca o favorito (o widget usa a mesma lista). Na coluna ♪:
        marca/desmarca o aviso de quando o item cair."""
        tree = self.t_drop_items.tree
        col = tree.identify_column(e.x)
        if col not in ("#1", "#2"):
            return None
        row = tree.identify_row(e.y)
        if not row:
            return None
        try:
            item = int(row)
        except ValueError:
            return None
        if col == "#1":
            self.app.toggle_fav(item)
        else:
            self.app.toggle_ping(item)
        return "break"

    def open_pings(self):
        """Janela "Avisos de item": busca na lista de itens do jogo, os itens marcados e as opções do som."""
        old = getattr(self, "ping_dlg", None)
        if old is not None and old.winfo_exists():
            old.lift()
            return
        app, c = self.app, self.c
        dlg = self.ping_dlg = tk.Toplevel(self.top)
        dlg.title(_("Avisos de item"))
        dlg.configure(bg=c["panel"])
        dlg.transient(self.top)
        box = tk.Frame(dlg, bg=c["panel"], padx=14, pady=12)
        box.pack(fill="both", expand=True)
        self.label(box, _("Quando um item marcado cair, o widget toca um som curto e mostra onde ele caiu: um clique "
                          "no cartão copia o /navi para colar no jogo. Se você sair de perto sem pegar, o cartão volta "
                          "até o item sumir do chão."), "small", "muted", "panel", anchor="w", justify="left",
                   wraplength=560).pack(fill="x")
        row = tk.Frame(box, bg=c["panel"])
        row.pack(fill="x", pady=(10, 2))
        self.label(row, _("Buscar item do jogo:"), bg="panel").pack(side="left")
        query = tk.StringVar(dlg, "")
        entry = tk.Entry(row, textvariable=query, font=self.f["text"], bg=c["btn"], fg=c["fg"],
                         insertbackground=c["fg"], relief="flat")
        entry.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=3)
        hint = self.label(box, "", "small", "muted", "panel", anchor="w")
        hint.pack(fill="x")

        def listbox(height):
            frame = tk.Frame(box, bg=c["panel"])
            lb = tk.Listbox(frame, height=height, font=self.f["text"], bg=c["btn"], fg=c["fg"], relief="flat",
                            selectbackground=c["accent"], selectforeground=c["bg"], highlightthickness=0,
                            activestyle="none", exportselection=False)
            sb = ttk.Scrollbar(frame, orient="vertical", command=lb.yview, style="An.Vertical.TScrollbar")
            lb.configure(yscrollcommand=sb.set)
            lb.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            return frame, lb
        frame, found = listbox(9)
        frame.pack(fill="both", expand=True, pady=(2, 4))
        add_btn = ttk.Button(box, text=_("Avisar quando este item cair"), style="An.TButton")
        add_btn.pack(anchor="e")
        marked_lbl = self.label(box, "", bg="panel", anchor="w")
        marked_lbl.pack(fill="x", pady=(10, 2))
        frame, marked = listbox(6)
        frame.pack(fill="both", expand=True, pady=(0, 4))
        del_btn = ttk.Button(box, text=_("Parar de avisar"), style="An.TButton")
        del_btn.pack(anchor="e")
        state = dict(found=[], marked=[], job=None)

        def fill_marked():
            ids = [i for i in app.ping_list() if isinstance(i, int)]
            state["marked"] = ids
            marked.delete(0, "end")
            for i in ids:
                marked.insert("end", "%s  (%d)" % (meter.item_name(i), i))
            who = app.ping_char() if app.cfg.get("ping_keep") == "char" else None
            if ids:
                marked_lbl.configure(text=(_("Itens com aviso de %s (%d):") % (who, len(ids))) if who
                                     else _("Itens com aviso (%d):") % len(ids))
            else:
                marked_lbl.configure(text=(_("Nenhum item com aviso para %s ainda.") % who) if who
                                     else _("Nenhum item com aviso ainda."))

        def run_search():
            state["job"] = None
            if not dlg.winfo_exists():
                return
            text = query.get().strip()
            rows = itemping.search(text, 300) if text else []
            if itemping.loading():                       # a lista do jogo ainda está sendo lida
                hint.configure(text=_("lendo os itens do jogo…"))
                state["job"] = dlg.after(500, run_search)
            elif not text:
                hint.configure(text=_("Digite parte do nome (sem precisar de acentos) ou o número do item."))
            else:
                hint.configure(text=(_("%d itens") % len(rows)) if len(rows) < 300 else _("os primeiros 300: digite mais"))
            state["found"] = rows
            found.delete(0, "end")
            for i, name in rows:
                found.insert("end", "%s  (%d)" % (name, i))

        def search_soon(*_a):
            if state["job"] is not None:
                dlg.after_cancel(state["job"])
            state["job"] = dlg.after(180, run_search)

        def add(_e=None):
            sel = found.curselection()
            if not sel:
                return
            item = state["found"][sel[0]][0]
            if item not in app.ping_items():
                app.toggle_ping(item)
            fill_marked()

        def remove(_e=None):
            sel = marked.curselection()
            if not sel:
                return
            item = state["marked"][sel[0]]
            if item in app.ping_items():
                app.toggle_ping(item)
            fill_marked()
        query.trace_add("write", search_soon)
        add_btn.configure(command=add)
        del_btn.configure(command=remove)
        found.bind("<Double-Button-1>", add)
        found.bind("<Return>", add)
        marked.bind("<Double-Button-1>", remove)
        marked.bind("<Delete>", remove)
        # para quem valem os itens marcados
        keep_row = tk.Frame(box, bg=c["panel"])
        keep_row.pack(fill="x", pady=(10, 0))
        self.label(keep_row, _("Os itens marcados valem:"), bg="panel").pack(side="left")
        keeps = [(_(lbl), k) for k, lbl in KEEP_LABELS]
        keep = tk.StringVar(dlg, next((lbl for lbl, k in keeps if k == (app.cfg.get("ping_keep") or "all")), keeps[0][0]))
        kb = ttk.Combobox(keep_row, textvariable=keep, values=[lbl for lbl, _k in keeps], state="readonly", width=28,
                          style="An.TCombobox", font=self.f["text"])
        kb.pack(side="left", padx=(8, 0))

        def save_keep(_e=None):
            app.set_ping_keep(dict(keeps).get(keep.get(), "all"))
            fill_marked()
        kb.bind("<<ComboboxSelected>>", save_keep)
        # som: liga/desliga, volume e tom, com um botão para ouvir
        snd = tk.Frame(box, bg=c["panel"])
        snd.pack(fill="x", pady=(12, 0))
        on = tk.BooleanVar(dlg, bool(app.cfg.get("ping_sound", True)))
        tones = [(_(TONE_LABELS[t]), t) for t, _hz in itemping.TONES]
        tone = tk.StringVar(dlg, next((lbl for lbl, t in tones if t == app.cfg.get("ping_tone")), tones[1][0]))
        vol = tk.StringVar(dlg, "%d%%" % app.cfg.get("ping_volume", 40))

        def save_sound(play=False):
            app.cfg["ping_sound"] = bool(on.get())
            app.cfg["ping_tone"] = dict(tones).get(tone.get(), itemping.DEFAULT_TONE)
            try:
                app.cfg["ping_volume"] = max(0, min(100, int(vol.get().strip("% "))))
            except ValueError:
                pass
            app.save()
            if play:
                self.play_ping()
        tk.Checkbutton(snd, text=_("Tocar som"), variable=on, command=save_sound, bg=c["panel"], fg=c["fg"],
                       selectcolor=c["btn"], activebackground=c["panel"], activeforeground=c["fg"],
                       font=self.f["text"], highlightthickness=0).pack(side="left")
        self.label(snd, _("Volume:"), bg="panel").pack(side="left", padx=(14, 4))
        vb = ttk.Combobox(snd, textvariable=vol, values=["%d%%" % v for v in itemping.VOLUMES], state="readonly",
                          width=6, style="An.TCombobox", font=self.f["text"])
        vb.pack(side="left")
        self.label(snd, _("Tom:"), bg="panel").pack(side="left", padx=(14, 4))
        tb = ttk.Combobox(snd, textvariable=tone, values=[lbl for lbl, _t in tones], state="readonly", width=11,
                          style="An.TCombobox", font=self.f["text"])
        tb.pack(side="left")
        vb.bind("<<ComboboxSelected>>", lambda e: save_sound(True))
        tb.bind("<<ComboboxSelected>>", lambda e: save_sound(True))
        ttk.Button(snd, text=_("Ouvir"), style="An.TButton", command=lambda: save_sound(True)).pack(side="left", padx=(10, 0))
        ttk.Button(snd, text=_("Fechar"), style="An.TButton", command=dlg.destroy).pack(side="right")
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        fill_marked()
        run_search()
        self.ping_fill = fill_marked
        entry.focus_set()

    def play_ping(self):
        """Toca o aviso de item com o volume e o tom escolhidos (o som é o do widget)."""
        import dpsmeter
        dpsmeter.play_ping(self.app.cfg.get("ping_volume", 40), self.app.cfg.get("ping_tone"))

    # ------------------------------------------------------------ XP

    def build_xp(self):
        c = self.c
        tab = tk.Frame(self.nb, bg=c["panel"])
        self.nb.add(tab, text=_("XP"))
        self.xp_tiles = Tiles(tab, self, [
            ("est", _("XP estimada no recorte")), ("min", _("XP por minuto")), ("hour", _("XP por hora")),
            ("kills", _("Abates")), ("factor", _("Fator de bônus")), ("level", _("Nível")),
            ("eta", _("Até o próximo nível")), ("real", _("XP real até a próxima gravação"))], min_w=140, dense=True)
        self.xp_tiles.pack(fill="x", padx=10, pady=(10, 0))
        self.label(tab, _("O replay não grava a XP ganha: só a XP total no início de cada gravação. A estimativa soma "
                          "a XP de cada monstro que você ajudou a matar (rAthena e Divine Pride), com a penalidade de "
                          "nível e a sua parte do dano, vezes os bônus. Evento do servidor, VIP e Cetro somam entre "
                          "si; os bônus dos itens e o Banquete de Njord multiplicam esse grupo; manual e Kafra Buff "
                          "somam por fora; e o Milagre dobra tudo (conta medida com a XP exata do jogo). Os manuais "
                          "competem entre si (vale o maior). O replay mostra quando VIP, Cetro, Kafra Buff, manual, "
                          "Banquete de Njord e "
                          "Milagre estão ativos, mas não o evento do servidor: marque-o. \"Medido\" corrige a lista "
                          "com a XP exata: cada subida de nível (a XP de cada nível é conhecida) e duas gravações "
                          "seguidas do mesmo personagem; trechos com menos de 10 min não contam."),
                   "small", "muted", "panel", anchor="w", justify="left", wraplength=1150).pack(fill="x", padx=12,
                                                                                               pady=(6, 2))
        pw = ttk.PanedWindow(tab, orient="horizontal", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True, pady=(4, 0))
        left = tk.Frame(pw, bg=c["tile"])
        right = tk.Frame(pw, bg=c["panel"])
        pw.add(left, weight=2)
        pw.add(right, weight=3)
        self.section(left, _("Bônus de XP"), bg="tile")
        self.xp_mode = tk.StringVar(self.top, "auto")
        modes = tk.Frame(left, bg=c["tile"])
        modes.pack(fill="x", padx=10)
        self.xp_mode_btns = {}
        for key, text in (("auto", _("Automático (recomendado)")), ("lista", _("Pela lista abaixo")),
                          ("medido", _("Medido nas gravações")), ("fixo", _("Valor fixo (%):"))):
            row = tk.Frame(modes, bg=c["tile"])
            row.pack(fill="x", pady=1)
            rb = tk.Radiobutton(row, text=text, variable=self.xp_mode, value=key, command=self.xp_save,
                                bg=c["tile"], fg=c["fg"], selectcolor=c["btn"], activebackground=c["tile"],
                                activeforeground=c["fg"], font=self.f["text"], anchor="w", highlightthickness=0)
            rb.pack(side="left")
            self.xp_mode_btns[key] = rb
            if key == "fixo":
                self.xp_fixed = tk.StringVar(self.top, "")
                self.xp_fixed.trace_add("write", lambda *_a: self.xp_save_soon())
                ent = tk.Entry(row, textvariable=self.xp_fixed, width=6, font=self.f["text"], bg=c["btn"],
                               fg=c["fg"], insertbackground=c["fg"], relief="flat")
                ent.pack(side="left", padx=6, ipady=2)
                ent.bind("<Return>", lambda e: self.xp_save())
                ent.bind("<FocusOut>", lambda e: self.xp_save())
            if key == "auto":
                self.label(row, _("a lista, corrigida pela XP exata; confere o evento do servidor sozinho"), "small",
                           "muted", "tile").pack(side="left", padx=6)
            if key == "medido":
                self.xp_measured = self.label(row, "", "small", "muted", "tile")
                self.xp_measured.pack(side="left", padx=6)
                ttk.Button(row, text=_("Esquecer"), style="An.TButton", command=self.xp_forget).pack(side="right")
        lst = tk.Frame(left, bg=c["tile"])
        lst.pack(fill="x", padx=10, pady=(8, 4))
        self.xp_on, self.xp_pct, self.xp_seen, self.xp_checks = {}, {}, {}, {}
        # a caixa diz se o bônus entra na conta; se ele estava ativo nesta gravação, diz a última coluna
        for col, text in ((0, _("Contar · Bônus")), (1, "%"), (3, _("Nesta gravação"))):
            self.label(lst, text, "small", "muted", "tile").grid(row=0, column=col, columnspan=2 if col == 1 else 1,
                                                                 sticky="w", padx=(10, 0) if col == 3 else 0)
        for i, bdef in enumerate(xp.BONUSES, start=1):
            var = tk.BooleanVar(self.top, bdef["on"])
            cb = tk.Checkbutton(lst, text=_(bdef["name"]), variable=var, command=self.xp_save, bg=c["tile"],
                                fg=c["fg"], selectcolor=c["btn"], activebackground=c["tile"], activeforeground=c["fg"],
                                font=self.f["text"], anchor="w", highlightthickness=0)
            cb.grid(row=i, column=0, sticky="w")
            self.xp_checks[bdef["key"]] = cb
            pv = tk.StringVar(self.top, "%g" % bdef["pct"])
            if bdef["key"] == "server":          # o evento costuma ser +50%, +100% e às vezes +200%
                ent = ttk.Combobox(lst, textvariable=pv, values=("50", "100", "200"), width=4, style="An.TCombobox",
                                   font=self.f["text"], justify="right")
                ent.bind("<<ComboboxSelected>>", lambda e: self.xp_save())
            else:
                ent = tk.Entry(lst, textvariable=pv, width=5, font=self.f["text"], bg=c["btn"], fg=c["fg"],
                               insertbackground=c["fg"], relief="flat", justify="right")
            ent.grid(row=i, column=1, padx=(8, 2), ipady=1)
            ent.bind("<Return>", lambda e: self.xp_save())
            ent.bind("<FocusOut>", lambda e: self.xp_save())
            self.label(lst, "%", color="muted", bg="tile").grid(row=i, column=2, sticky="w")
            seen = self.label(lst, "", "small", "muted", "tile", anchor="w")
            seen.grid(row=i, column=3, sticky="w", padx=(10, 0))
            self.xp_on[bdef["key"]], self.xp_pct[bdef["key"]], self.xp_seen[bdef["key"]] = var, pv, seen
            pv.trace_add("write", lambda *_a: self.xp_save_soon())     # o % digitado vale sem precisar de Enter
            if bdef["key"] in ("gear", "gear_event"):  # o % vem do texto dos itens vestidos
                pv.set(_("auto"))
                ent.configure(state="disabled", disabledbackground=c["tile"], disabledforeground=c["muted"])
            if bdef["key"] == "gear_event":            # cada item de evento pode estar valendo ou não
                ent.grid_remove()
                self.xp_event_btn = ttk.Button(lst, text=_("Itens ▾"), style="An.TButton", width=7,
                                               command=self.xp_event_menu)
                self.xp_event_btn.grid(row=i, column=1, columnspan=2, padx=(8, 2), sticky="w")
        lst.columnconfigure(3, weight=1)
        row = tk.Frame(left, bg=c["tile"])
        row.pack(fill="x", padx=10, pady=(4, 2))
        self.label(row, _("Manual usado:"), color="muted", bg="tile").pack(side="left")
        self.xp_manual = tk.StringVar(self.top, "")
        box = ttk.Combobox(row, textvariable=self.xp_manual, state="readonly", width=30, style="An.TCombobox",
                           font=self.f["text"], values=["%s (+%d%%)" % (_(n), p) for n, p in xp.MANUALS])
        box.pack(side="left", padx=6)
        box.bind("<<ComboboxSelected>>", lambda e: self.xp_pick_manual())
        self.xp_compare = self.label(left, "", "small", "muted", "tile", anchor="w", justify="left", wraplength=440)
        self.xp_compare.pack(fill="x", padx=10, pady=(6, 10))
        self.xp_chart_title = self.section(right, _("XP ao longo do tempo"))
        self.xp_chart = tk.Canvas(right, height=int(210 * self.dpi * self.zoom), bg=c["panel"], highlightthickness=0,
                                  bd=0)
        self.xp_chart.pack(fill="x", padx=10)
        self.xp_chart.bind("<Configure>", lambda e: self.draw_xp_chart())
        self.xp_chart.bind("<Motion>", self.xp_chart_hover)
        self.xp_chart.bind("<Leave>", lambda e: self.xp_chart.delete("hover"))
        self.xp_series = ([], None)
        sub = ttk.Notebook(right, style="Sub.TNotebook")
        sub.pack(fill="both", expand=True, padx=6, pady=(4, 8))
        mobs = tk.Frame(sub, bg=c["tile"])
        sub.add(mobs, text=_("Por monstro"))
        self.t_xp = Table(mobs, self, [
            ("name", _("Monstro"), 160, "w", "text"), ("lv", _("Nível"), 50, "e", "int"),
            ("kills", _("Abates"), 65, "e", "int"), ("pen_txt", _("Penalidade"), 85, "e", "text"),
            ("xp_txt", _("XP estimada"), 120, "e", "text"), ("each_txt", _("Por abate"), 105, "e", "text")], height=6)
        self.t_xp.pack(fill="both", expand=True, padx=6, pady=6)
        qtab = tk.Frame(sub, bg=c["tile"])
        sub.add(qtab, text=_("Missões"))
        self.t_xp_quests = Table(qtab, self, [
            ("when", _("Quando"), 90, "w", "text"), ("name", _("Missão"), 250, "w", "text"),
            ("xp_txt", _("XP"), 120, "e", "text"), ("how", _("Como conta"), 260, "w", "text")], height=6)
        self.t_xp_quests.pack(fill="both", expand=True, padx=6, pady=(6, 2))
        self.label(qtab, _("O replay mostra a entrega e o progresso das caças, mas não quanto cada missão rende. Por "
                           "enquanto a XP das missões fica fora da estimativa: depois de uma entrega, o nível mostrado "
                           "fica abaixo do real até a próxima subida de nível ou a próxima gravação."), "small",
                   "muted", "tile", anchor="w", justify="left", wraplength=640).pack(fill="x", padx=8, pady=(0, 6))
        cmp_tab = tk.Frame(sub, bg=c["tile"])
        sub.add(cmp_tab, text=_("Comparar com outra gravação"))
        bar = tk.Frame(cmp_tab, bg=c["tile"])
        bar.pack(fill="x", padx=8, pady=(8, 4))
        self.label(bar, _("Gravação:"), color="muted", bg="tile").pack(side="left")
        self.xp_cmp_var = tk.StringVar(self.top, "")
        self.xp_cmp_box = ttk.Combobox(bar, textvariable=self.xp_cmp_var, state="readonly", width=44,
                                       style="An.TCombobox", font=self.f["text"])
        self.xp_cmp_box.pack(side="left", padx=6)
        self.xp_cmp_box.bind("<<ComboboxSelected>>", lambda e: self.refresh(force=True))
        self.xp_cmp_status = self.label(bar, "", "small", "muted", "tile")
        self.xp_cmp_status.pack(side="left", padx=6)
        self.t_xp_cmp = Table(cmp_tab, self, [
            ("what", _("O quê"), 170, "w", "text"), ("this", _("Esta gravação"), 150, "e", "text"),
            ("other", _("A outra"), 150, "e", "text"), ("diff", _("Diferença"), 100, "e", "text")], height=8)
        self.t_xp_cmp.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.label(cmp_tab, _("As duas usam a mesma lista de bônus. A outra gravação é sempre inteira."), "small",
                   "muted", "tile", anchor="w").pack(fill="x", padx=8, pady=(0, 6))
        import ui_xpsim
        self.xp_sim = ui_xpsim.XpSim(self, sub)
        sub.add(self.xp_sim.frame, text=_("Simulador"))
        self.xp_sub = sub
        self.xp_sim_open = False
        sub.bind("<<NotebookTabChanged>>", lambda e: self.xp_sub_changed())
        self.xp_cmp_files = []             # [{"path", "when"}] das gravações anteriores do personagem
        self.xp_cmp_cache = {}             # caminho -> "lendo" | "erro" | Combat
        self.xp_cmp_for = None
        self.xp_calibrated = set()
        self.xp_loaded = False

    def xp_sub_changed(self):
        """Com o Simulador aberto, o gráfico da XP sai da frente (o simulador precisa da altura toda)."""
        try:
            sim = self.xp_sub.index(self.xp_sub.select()) == self.xp_sub.index("end") - 1
        except tk.TclError:
            return
        if sim != self.xp_sim_open:
            self.xp_sim_open = sim
            if sim:
                self.xp_chart_title.pack_forget()
                self.xp_chart.pack_forget()
            else:
                self.xp_chart_title.pack(fill="x", padx=10, pady=(10, 4), before=self.xp_sub)
                self.xp_chart.pack(fill="x", padx=10, before=self.xp_sub)
        self.refresh(force=True)

    def xp_load(self):
        """Põe na tela o que está salvo (uma vez)."""
        cfg = self.app.cfg
        sets = xp.settings(cfg)
        for key, st in sets.items():
            self.xp_on[key].set(st["on"])
            if key not in ("gear", "gear_event"):
                self.xp_pct[key].set("%g" % st["pct"])
        self.xp_mode.set(cfg.get("xp_mode") if cfg.get("xp_mode") in xp.MODES else "auto")
        if isinstance(cfg.get("xp_fixed"), (int, float)):
            self.xp_fixed.set("%g" % cfg["xp_fixed"])
        pct = sets["manual"]["pct"]
        self.xp_manual.set(next(("%s (+%d%%)" % (_(n), p) for n, p in xp.MANUALS if p == pct), ""))
        self.xp_loaded = True

    def xp_save_soon(self):
        """Salva o que foi digitado meio segundo depois da última tecla (o widget acompanha)."""
        if not getattr(self, "xp_loaded", False):
            return
        if getattr(self, "_xp_after", None):
            try:
                self.top.after_cancel(self._xp_after)
            except tk.TclError:
                pass
        self._xp_after = self.top.after(600, self.xp_save)

    def xp_save(self):
        def number(text):
            try:
                return float(text.strip().replace("%", "").replace(",", "."))
            except ValueError:
                return None
        cfg = self.app.cfg
        saved = {}
        for b in xp.BONUSES:
            pct = number(self.xp_pct[b["key"]].get())
            saved[b["key"]] = dict(on=bool(self.xp_on[b["key"]].get()), pct=pct if pct is not None else b["pct"])
        old = xp.settings(cfg)
        if any((old[k]["on"], old[k]["pct"]) != (v["on"], v["pct"]) for k, v in saved.items()):
            cfg["xp_corr"] = {}                  # as medidas guardadas eram sobre a lista antiga
            if old["manual"]["pct"] != saved["manual"]["pct"]:
                cfg["xp_manual_last"] = {}       # a pessoa escolheu o manual: vale o que ela disse
        cfg["xp_bonuses"] = saved
        cfg["xp_mode"] = self.xp_mode.get()
        cfg["xp_fixed"] = number(self.xp_fixed.get())
        self.app.save()
        self.app.dirty = True
        self.refresh(force=True)

    def xp_pick_manual(self):
        label = self.xp_manual.get()
        pct = next((p for n, p in xp.MANUALS if label.startswith(_(n))), None)
        if pct is not None:
            self.xp_pct["manual"].set("%g" % pct)
            self.xp_save()

    def xp_forget(self):
        c = self.combat()
        if c is not None:
            (self.app.cfg.get("xp_corr") or {}).pop(str(c.session.gid), None)
            self.app.save()
            self.refresh(force=True)

    def refresh_xp(self, c):
        if not self.xp_loaded:
            self.xp_load()
        f = self.app.watcher.file
        if (f is not None and f.ready and f.combat is c and f.pos >= f.size and c.finished
                and id(c) not in self.xp_calibrated):
            self.xp_calibrated.add(id(c))
            self.app.xp_calibrate(c)
        cfg = self.app.cfg
        series, est = xp.timeline(c, cfg, self.rng)
        put = self.xp_tiles.put
        put("est", full(round(est["xp"])), short=num(est["xp"]), color=self.c["accent"])
        if est["pct"] is not None:              # % do nível primeiro, número depois (como no jogo)
            sub = _("do nível · %s XP") % full(round(est["xp"]))
            if est["quests"]:
                sub += " · " + (_("com %d missão(ões)") % len(est["quests"]) if not est["quests_unknown"] else
                                _("sem a XP de %d missão(ões)") % est["quests_unknown"])
            put("est", dec("%.2f%%" % est["pct"]), sub, color=self.c["accent"])
        if est["per_min"] is not None:
            put("min", dec("%.3f%%" % est["per_min_pct"]) if est["per_min_pct"] is not None else num(est["per_min"]),
                _("do nível · %s/min") % num(est["per_min"]) if est["per_min_pct"] is not None else "")
            put("hour", dec("%.2f%%" % est["per_hour_pct"]) if est["per_hour_pct"] is not None else num(est["per_hour"]),
                _("do nível · %s/h") % num(est["per_hour"]) if est["per_hour_pct"] is not None else "")
        else:
            put("min", "—", _("recorte curto demais"))
            put("hour", "—", _("recorte curto demais"))
        eta, left = xp.time_to_level(c, cfg)          # pelo ritmo dos últimos minutos
        if eta is None and xp.warming_up(c, cfg):
            put("eta", _("calculando…"), _("depois de 10 min de farm ou 1% do nível"))
        elif eta is None:
            put("eta", "—", _("sem ritmo de XP no recorte"))
        elif eta and xp.quests_uncounted(c, cfg):
            put("eta", xp.span_text(eta), _("pode ser menos: a XP das missões entregues não entra na conta"))
        else:
            put("eta", xp.span_text(eta) if eta else _("já subiu"),
                (_("faltam %s XP") % full(round(left))) if left else _("pela XP estimada"))
        per = (_("%s por minuto") % dec("%.1f" % est["kills_per_min"])) if est["kills_per_min"] is not None else ""
        if est["unknown"]:
            per = (per + " · " if per else "") + _("%d sem XP conhecida") % est["unknown"]
        put("kills", "%d" % est["kills"], per)
        kind, info = est["source"]
        if kind == "medido":
            how = _("lista × %s, da subida de nível desta gravação") % dec("%.3f" % est["correction"]) \
                if info == "nivel" else _("lista × %s, de %d medidas") % (dec("%.3f" % est["correction"]), info)
        elif kind == "fixo":
            how = _("valor fixo: +%g%%") % info
        elif kind == "auto":
            how = _("pela lista, aproximado: ainda sem XP exata para conferir")
        else:
            how = _("pela lista de bônus")
        put("factor", "×" + dec("%.2f" % est["factor"]), how)
        ses = c.session
        prog = meter.level_progress(ses)
        pr = xp.progress(c, cfg)
        if pr is not None and pr["pct"] is not None:   # agora: o último ponto exato + a XP estimada desde ele
            put("level", "%d" % pr["level"], (_("%s agora (sem a XP das missões)") if xp.quests_uncounted(c, cfg)
                                             else _("%s agora (estimado)")) % dec("%.2f%%" % min(100.0, pr["pct"])))
        else:
            put("level", "%d" % ses.base_level if ses.base_level else "—",
                dec("%.2f%%" % (100 * prog)) if prog is not None else "")
        nxt = meter.xp_after(c.path, ses)
        if nxt is None:
            put("real", "—", _("sem gravação depois desta"))
        else:
            _y, mo, d, hh, mm, _ss = nxt["when"]
            when = _("até %02d/%02d %02d:%02d") % (d, mo, hh, mm)
            put("real", (_("+%d níveis") % nxt["levels"]) if nxt["gain"] is None
                else ("+" if nxt["gain"] >= 0 else "") + full(nxt["gain"]), when)
        # bônus detectados nesta gravação
        seen = xp.detected(c, cfg)
        wins = xp.windows(c, cfg)
        event_on = xp.settings(cfg)["gear_event"]["on"]
        off = xp.event_off(cfg)
        worn = c.worn_at(self.rng[1] if self.rng else c.now)
        self.xp_event_items = xp.event_items(c)
        for b in xp.BONUSES:
            if b["key"] == "gear_event":
                ev = self.xp_event_items
                counted = [i for i in sorted(ev) if i not in off]
                if not ev:
                    text = _("nenhum item vestido tem bônus de evento")
                elif not counted:
                    text = _("nenhum item de evento marcado (botão Itens)")
                else:
                    text = _("+%d%% se o evento ainda vale: %s") % (sum(ev[i] for i in counted), ", ".join(
                        meter.item_name(i) for i in counted))
                    if len(counted) < len(ev):
                        text += " " + _("(%d de %d itens)") % (len(counted), len(ev))
                self.xp_event_btn.configure(state="normal" if ev else "disabled")
            elif b["status"] is None:
                text = _("marque se valia")
            elif b["key"] == "gear":
                pct, who = xp.gear_bonus(c.worn_at(self.rng[1] if self.rng else c.now), event_on, event_off=off)
                if xp.GEAR.loading or xp.GEAR.table is None:
                    text = _("lendo os itens do jogo…")
                    self.top.after(800, lambda: self.refresh(force=True) if self.tab_name() == "xp" else None)
                elif pct:
                    text = _("+%d%%: %s") % (pct, ", ".join(meter.item_name(i) for i in who))
                else:
                    text = _("nenhum item vestido dá XP")
            elif b["key"] == "miracle" and seen.get(b["key"]) and any(m[3] is not None for m in c.miracles):
                text = _("detectado (%s); a confirmar depois de morte ou troca de mapa") % dec(
                    "%.0f%%" % (100 * seen[b["key"]]))
            elif seen.get(b["key"]):
                text = _("ativo em %s da gravação") % dec("%.0f%%" % (100 * seen[b["key"]]))
                vals = sorted({v for _s, _e, v in wins.get(b["key"], ()) if v > 0}) if b.get("val") else []
                if vals:                       # o % que o jogo mandou no status vale no lugar do digitado
                    text += " · " + _("%s no replay") % ", ".join("+%g%%" % v for v in vals)
            else:
                text = _("não estava ativo")
            self.xp_seen[b["key"]].configure(text=text, fg=self.c["good"] if seen.get(b["key"]) else self.c["muted"])
            # bônus que o replay mostra e que não apareceu: nome em cinza (a caixa marcada só quer dizer "contar")
            absent = b["status"] is not None and b["key"] != "gear" and not seen.get(b["key"])
            self.xp_checks[b["key"]].configure(fg=self.c["muted"] if absent else self.c["fg"])
        corr, how = xp.correction(c, cfg)
        if corr and how == "nivel":
            text = _("lista × %s (subida de nível nesta gravação)") % dec("%.3f" % corr)
        elif corr:
            text = _("lista × %s (%d medidas de 10 min ou mais)") % (dec("%.3f" % corr), how)
        else:
            text = _("ainda sem subida de nível ou duas gravações seguidas de 10 min ou mais")
        self.xp_measured.configure(text=text)
        self.xp_mode_btns["medido"].configure(state="normal" if corr else "disabled")
        lst = xp.estimate(c, dict(cfg, xp_mode="lista"), self.rng)
        parts = [_("Pela lista: ×%s") % dec("%.2f" % lst["factor"])]
        if corr:
            parts.append(_("medido: ×%s (%s%% da lista)") % (dec("%.2f" % (lst["factor"] * corr)),
                                                             dec("%+.1f" % ((corr - 1) * 100))))
        self.xp_compare.configure(text=" · ".join(parts))
        self.xp_series = (series, ses.next_exp)
        self.draw_xp_chart()
        rows = []
        for r in xp.by_monster(est["rows"]):
            total = sum(k["total"] for k in est["rows"] if k["mob"] == r["key"] and k.get("total") is not None) \
                if r["xp"] is not None else None
            rows.append(dict(key=r["key"], name=r["name"], lv=r["lv"], kills=r["kills"],
                             pen_txt=("%d%%" % r["pen"]) if r["pen"] is not None else "—",
                             xp_txt=full(round(total)) if total is not None else _("desconhecida"),
                             each_txt=full(round(total / r["kills"])) if total is not None else "—", xp=total))
        rows.sort(key=lambda r: -(r["xp"] or 0))
        self.t_xp.set_rows(rows, lambda r: r["key"], lambda r: [] if r["xp"] is not None else ["warn"])
        # missões: as entregues no recorte (com a XP, quando se sabe) e as caças em andamento
        qrows = []
        for i, q in enumerate(est["quests"]):
            extra = round((q["mult"] - 1.0) * 100)
            qrows.append(dict(key="d%d" % i, when=dur(q["t"]), name=quests.title(q["quest"]), known=q["xp"] is not None,
                              xp_txt=full(round(q["xp"])) if q["xp"] is not None else _("fora da conta"),
                              how=(_("recompensa %s, sem bônus") % full(round(q["base"])) if not extra else
                                   _("recompensa %s +%d%% (manual e Kafra)") % (full(round(q["base"])), extra))
                              if q["base"] else _("entregue: a XP desta missão ainda não entra na estimativa")))
        for h in xp.hunts(c):
            qrows.append(dict(key="h%d" % h["quest"], when=_("em andamento"), name=quests.title(h["quest"]), known=True,
                              xp_txt=" · ".join("%d/%d" % p for p in h["parts"]),
                              how=_("caça: %s feito") % dec("%.0f%%" % (100.0 * h["count"] / h["goal"]))
                              if h["goal"] else ""))
        self.t_xp_quests.set_rows(qrows, lambda r: r["key"], lambda r: [] if r["known"] else ["warn"])
        self.refresh_xp_compare(c)
        self.xp_sim.refresh(c, est)

    def xp_event_menu(self):
        """Menu com cada item de bônus "[Durante o Evento]": marcado = o evento daquele item ainda vale."""
        items = getattr(self, "xp_event_items", None) or {}
        if not items:
            return
        off = xp.event_off(self.app.cfg)
        m = tk.Menu(self.top, tearoff=0)
        self._event_vars = []
        for item in sorted(items, key=meter.item_name):
            var = tk.BooleanVar(self.top, item not in off)
            self._event_vars.append(var)
            m.add_checkbutton(label="%s (+%d%%)" % (meter.item_name(item), items[item]), variable=var,
                              command=lambda i=item: self.xp_toggle_event(i))
        m.add_separator()
        m.add_command(label=_("Marque os itens cujo evento ainda está valendo."), state="disabled")
        self._menu = m
        b = self.xp_event_btn
        m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def xp_toggle_event(self, item):
        off = set(self.app.cfg.get("xp_event_off") or [])
        if item in off:
            off.discard(item)
        else:
            off.add(item)
        self.app.cfg["xp_event_off"] = sorted(off)
        if item not in off:                        # marcou um item: os bônus de evento passam a contar
            self.xp_on["gear_event"].set(True)
        self.xp_save()

    def refresh_xp_compare(self, c):
        """Aba "Comparar": esta gravação (ou recorte) contra outra do mesmo personagem."""
        if self.xp_cmp_for != (getattr(c, "path", None), c.session.gid):
            self.xp_cmp_for = (getattr(c, "path", None), c.session.gid)
            self.xp_cmp_files = xp.recordings_before(getattr(c, "path", None), c.session)
            labels = []
            for r in self.xp_cmp_files:
                _y, mo, d, hh, mm, _ss = r["when"]
                labels.append("%02d/%02d %02d:%02d · %s" % (d, mo, hh, mm, os.path.basename(r["path"])))
            self.xp_cmp_box.configure(values=labels)
            self.xp_cmp_var.set(labels[0] if labels else "")
        if not self.xp_cmp_files:
            self.xp_cmp_status.configure(text=_("nenhuma gravação anterior deste personagem na pasta"))
            self.t_xp_cmp.set_rows([], lambda r: r["key"])
            return
        values = list(self.xp_cmp_box.cget("values"))
        pick = values.index(self.xp_cmp_var.get()) if self.xp_cmp_var.get() in values else 0
        path = self.xp_cmp_files[pick]["path"]
        other = self.xp_cmp_cache.get(path)
        if other is None:
            self.xp_cmp_cache[path] = "lendo"
            gap, targets = self.app.gap_ms(), self.app.cfg["targets"]

            def run():
                try:
                    rf = meter.ReplayFile(path, gap, targets)
                    rf.poll(max_bytes=1 << 30)
                    rf.combat.finished = True
                    rf.combat.path = path
                    self.xp_cmp_cache[path] = rf.combat
                except Exception:  # noqa: BLE001 - replay estragado: só avisa
                    self.xp_cmp_cache[path] = "erro"
            for k in [k for k, v in self.xp_cmp_cache.items() if k != path and not isinstance(v, str)]:
                del self.xp_cmp_cache[k]          # guarda só uma gravação lida (memória)
            threading.Thread(target=run, daemon=True).start()
            other = "lendo"
        if other == "lendo":
            self.xp_cmp_status.configure(text=_("lendo a gravação…"))
            self.top.after(400, lambda: self.refresh(force=True) if self.tab_name() == "xp" else None)
            return
        if other == "erro":
            self.xp_cmp_status.configure(text=_("não consegui ler essa gravação"))
            self.t_xp_cmp.set_rows([], lambda r: r["key"])
            return
        cfg = self.app.cfg
        a, b = xp.summary(c, cfg, self.rng), xp.summary(other, cfg)
        self.xp_cmp_status.configure(text=_("nível %s · %s") % (b["level"] or "?", xp.span_text(b["span"])))

        def pct_or_num(v, p, fmt):
            if p is not None:
                return dec(fmt % p) + " · " + num(v)
            return num(v) if v is not None else "—"

        def diff(x, y):
            if x is None or y is None or not y:
                return "—", []
            d = (x / float(y) - 1) * 100
            return dec("%+.0f%%" % d), (["good"] if d > 0.5 else ["bad"] if d < -0.5 else [])
        rows = []
        for key, what, va, vb, cmp_a, cmp_b in (
                ("span", _("Duração"), xp.span_text(a["span"]), xp.span_text(b["span"]), None, None),
                ("xp", _("XP estimada"), pct_or_num(a["xp"], a["pct"], "%.2f%%"),
                 pct_or_num(b["xp"], b["pct"], "%.2f%%"), a["xp"], b["xp"]),
                ("min", _("XP por minuto"), pct_or_num(a["per_min"], a["per_min_pct"], "%.3f%%"),
                 pct_or_num(b["per_min"], b["per_min_pct"], "%.3f%%"), a["per_min"], b["per_min"]),
                ("hour", _("XP por hora"), pct_or_num(a["per_hour"], a["per_hour_pct"], "%.2f%%"),
                 pct_or_num(b["per_hour"], b["per_hour_pct"], "%.2f%%"), a["per_hour"], b["per_hour"]),
                ("kills", _("Abates"), "%d" % a["kills"], "%d" % b["kills"], a["kills"], b["kills"]),
                ("kpm", _("Abates por minuto"),
                 dec("%.1f" % a["kills_per_min"]) if a["kills_per_min"] is not None else "—",
                 dec("%.1f" % b["kills_per_min"]) if b["kills_per_min"] is not None else "—",
                 a["kills_per_min"], b["kills_per_min"]),
                ("factor", _("Fator de bônus"), "×" + dec("%.2f" % a["factor"]), "×" + dec("%.2f" % b["factor"]),
                 a["factor"], b["factor"])):
            d, tags = diff(cmp_a, cmp_b) if cmp_a is not None else ("", [])
            rows.append(dict(key=key, what=what, this=va, other=vb, diff=d, tags=tags))
        self.t_xp_cmp.set_rows(rows, lambda r: r["key"], lambda r: r["tags"])

    def draw_xp_chart(self):
        """Barras: XP de cada minuto (escala da esquerda); linha: XP acumulada (escala da direita).
        Em % do nível quando o jogo mandou quanto falta; passe o mouse para ver cada minuto."""
        cv, col, f = self.xp_chart, self.c, self.f
        cv.delete("all")
        self.xp_geo = None
        series, next_exp = self.xp_series
        W, H = cv.winfo_width(), cv.winfo_height()
        d = self.dpi * self.zoom
        if not series or not any(v for _t, v, _a in series) or W < 50:
            cv.create_text(10 * d, H / 2, anchor="w", fill=col["muted"], font=f["text"],
                           text=_("Nenhum abate com XP conhecida no recorte."))
            return
        pct = (lambda x: 100.0 * x / next_exp) if next_exp else None
        fmt_min = (lambda x: dec("%.3f%%" % pct(x))) if pct else num
        fmt_tot = (lambda x: dec("%.2f%%" % pct(x))) if pct else num
        n = len(series)
        peak = max(v for _t, v, _a in series) or 1
        scale = _nice_up(pct(peak) if pct else peak)       # topo da escala, num número redondo
        top_v = scale * next_exp / 100.0 if pct else scale
        total = series[-1][2] or 1
        sm = f["small"]
        left = max(sm.measure(fmt_min(top_v)), sm.measure("0")) + 12 * d
        right = W - (sm.measure(fmt_tot(total)) + 14 * d)
        top, bottom = 24 * d, H - 22 * d
        bar_col = _mix(col["panel"], col["accent"], 0.6)
        # legenda
        cv.create_rectangle(left, 6 * d, left + 10 * d, 14 * d, fill=bar_col, outline="")
        cv.create_text(left + 14 * d, 10 * d, anchor="w", fill=col["muted"], font=sm, text=_("XP por minuto"))
        cv.create_line(right - 14 * d, 10 * d, right - 2 * d, 10 * d, fill=col["good"], width=max(2, int(2 * d)))
        cv.create_text(right - 18 * d, 10 * d, anchor="e", fill=col["muted"], font=sm, text=_("XP acumulada"))
        # grade
        for k in (0.0, 0.5, 1.0):
            y = bottom - (bottom - top) * k
            cv.create_line(left, y, right, y, fill=col["grid"], dash=() if k == 0 else (2, 4))
            cv.create_text(left - 6 * d, y, anchor="e", fill=col["muted"], font=sm,
                           text="0" if k == 0 else fmt_min(top_v * k))
        bw = (right - left) / n
        gap = min(3 * d, bw * 0.25)
        for i, (t0, v, acc) in enumerate(series):
            x0 = left + i * bw
            h = (bottom - top) * min(1.0, v / top_v)
            if h > 0:
                cv.create_rectangle(x0 + gap / 2, bottom - h, x0 + bw - gap / 2, bottom, fill=bar_col, outline="")
        pts = [left, bottom]
        for i, (t0, v, acc) in enumerate(series):
            pts += [left + (i + 1) * bw, bottom - (bottom - top) * acc / total]
        cv.create_line(*pts, fill=col["good"], width=max(2, int(2 * d)))
        ex, ey = pts[-2], pts[-1]
        r = 3 * d
        cv.create_oval(ex - r, ey - r, ex + r, ey + r, fill=col["good"], outline="")
        cv.create_text(right + 6 * d, ey, anchor="w", fill=col["good"], font=sm, text=fmt_tot(total))
        # eixo do tempo: o passo cresce até os rótulos não encostarem uns nos outros
        def lab(m):
            if n <= 90:
                return _("%d min") % m
            return ("%dh" % (m // 60)) if m % 60 == 0 else ("%dh%02d" % (m // 60, m % 60))
        widest = sm.measure(lab(n)) + 14 * d
        step = next((st for st in (1, 2, 5, 10, 15, 20, 30, 60, 120, 180, 240, 360) if st * bw >= widest), 480)
        for m in range(0, n + 1, step):
            x = left + m * bw
            if x + sm.measure(lab(m)) / 2 > W:
                break
            cv.create_line(x, bottom, x, bottom + 3 * d, fill=col["grid"])
            cv.create_text(x, bottom + 5 * d, anchor="n", fill=col["muted"], font=sm, text=lab(m))
        self.xp_geo = (left, right, top, bottom, bw, series, fmt_min, fmt_tot)

    def xp_chart_hover(self, e):
        cv = self.xp_chart
        cv.delete("hover")
        geo = getattr(self, "xp_geo", None)
        if not geo:
            return
        left, right, top, bottom, bw, series, fmt_min, fmt_tot = geo
        if not left <= e.x <= right or not top - 10 <= e.y <= bottom:
            return
        i = min(len(series) - 1, int((e.x - left) // bw))
        _t0, v, acc = series[i]
        d = self.dpi * self.zoom
        x0 = left + i * bw
        cv.create_rectangle(x0, top, x0 + bw, bottom, outline=self.c["fg"], width=1, tags="hover")
        text = _("minuto %d: %s · total %s") % (i + 1, fmt_min(v), fmt_tot(acc))
        tw = self.f["small"].measure(text) + 14 * d
        bx = min(max(left, x0 + bw / 2 - tw / 2), right - tw)
        cv.create_rectangle(bx, top - 2 * d, bx + tw, top + 16 * d, fill=self.c["tip"], outline=self.c["grid"],
                            tags="hover")
        cv.create_text(bx + 7 * d, top + 7 * d, anchor="w", text=text, font=self.f["small"], fill=self.c["fg"],
                       tags="hover")

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
        self.refresh(force=True)

    def fit_tabs(self):
        """Com muitas abas, a janela no tamanho padrão cortava os nomes ("Dedo Durc"): diminui o espaço em volta
        de cada nome e, se ainda não couber, a letra, até todas caberem na largura da janela."""
        try:
            n = self.nb.index("end")
            texts = [self.nb.tab(i, "text") for i in range(n)]
        except tk.TclError:
            return
        width = self.nb.winfo_width()
        if width <= 1 or not n:
            return
        choice = None
        for key in ("head", "small"):
            text_w = sum(self.f[key].measure(t) for t in texts)
            for pad in (16, 12, 9, 6, 4):
                if text_w + n * (2 * pad + 8) + 24 <= width:
                    choice = (pad, key)
                    break
            if choice:
                break
        pad, key = choice or (4, "small")
        if (pad, key) != (getattr(self, "tab_pad", 16), getattr(self, "tab_font", "head")):
            self.tab_pad, self.tab_font = pad, key
            ttk.Style(self.top).configure("An.TNotebook.Tab", padding=(pad, 7), font=self.f[key])

    def tab_changed(self):
        try:
            self.app.cfg["an_tab"] = self.tab_name()
        except tk.TclError:
            pass
        self.refresh(force=True)

    def tick(self):
        """Chamado pelo widget a cada leitura do replay. Com dados novos, refaz a aba no máximo 1 vez por segundo,
        e mais devagar quando refazer custa caro (numa sessão de horas, algumas abas levam mais de 1 s): o widget e
        a própria janela continuam respondendo. Minimizada, não refaz nada; atualiza quando voltar. O que a pessoa
        muda (aba, luta, grupo) continua valendo na hora."""
        c = self.combat()
        live = c is not None and c.active()
        sig = (id(c), c.version if c else None, self.scope_var.get(), self.group_var.get(),
               len(self.app.tests.records))
        now = time.monotonic()
        if sig == self.sig and not (live and now - self._last >= 1.0):
            return
        only_data = self.sig is not None and sig[0] == self.sig[0] and sig[2:] == self.sig[2:]
        if only_data and now < self._next:
            return
        try:
            if self.top.state() in ("iconic", "withdrawn"):
                return
        except tk.TclError:
            return
        self.refresh()

    def refresh(self, force=False):
        """Refaz a aba à vista e anota quanto levou, para o tick dosar a próxima atualização ao vivo."""
        t0 = time.monotonic()
        try:
            return self._refresh(force)
        finally:
            end = time.monotonic()
            self._next = end + min(LIVE_MAX_S, max(LIVE_MIN_S, LIVE_COST * (end - t0)))

    def _refresh(self, force=False):
        self._last = time.monotonic()
        c = self.combat()
        if c is not None and id(c) != self.combat_id:
            self.combat_id = id(c)
            self.player_aid = c.me
            self.mob_key = None
            self.colors = {}
        self.sig = (id(c), c.version if c else None, self.scope_var.get(), self.group_var.get(),
                    len(self.app.tests.records))
        if self.mvp_var.get() != (self.app.cfg.get("targets") == "mvp"):
            self.mvp_var.set(self.app.cfg.get("targets") == "mvp")       # mudou pelo menu do widget
        self.update_scope_list(c)
        tab = self.tab_name()
        if tab == "testes":
            self.refresh_tests()              # o histórico não depende do replay aberto
        elif tab == "cartoes":
            self.cards_tab.refresh()          # nem o gerenciador de cartões
        if c is None:
            self.title_lbl.configure(text=_("Análise"))
            self.status_lbl.configure(text=_("sem replay aberto — comece a gravar no jogo ou abra um replay salvo"))
            return
        scope = self.scope(c)
        rng, dur_ms = an.scope_range(c, scope)
        self.rng, self.dur_ms = rng, dur_ms
        s = c.session
        self.title_lbl.configure(text="%s · %s" % (c.name_of(c.me) if meter.HIDE_NAMES else s.player, c.map or s.map))
        live = c.active() and (scope is None or c.is_live(scope))
        _y, mo, d, hh, mm, _ss = s.recorded_at
        state = _("● ao vivo") if live else (_("gravando") if not c.finished else _("replay encerrado"))
        self.status_lbl.configure(text=_("%s · gravado %02d/%02d às %02d:%02d") % (state, d, mo, hh, mm),
                                  fg=self.c["live"] if live else self.c["muted"])
        # jogadores e totais do recorte: toda aba usa, e num replay grande cada conta varre dezenas de milhares
        # de golpes; ficam guardados enquanto o replay e o recorte não mudam (mudar de aba não refaz nada disso)
        key = (id(c), c.version, rng, dur_ms, meter.HIDE_NAMES)
        if self._common[0] != key:
            hs = an.out_hits(c, rng)
            self._common = (key, an.players(c, rng, dur_ms), sum(h.dmg for h in hs), len(hs))
        _key, self.players_rows, total, events = self._common
        for p in self.players_rows:          # cor fixa por jogador, na ordem do ranking
            self.color_of(p["aid"])
        ht = self.head_tiles
        gdps = total * 1000.0 / max(1, dur_ms)
        ht.put("group", full(total), short=num(total))
        ht.put("gdps", full(round(gdps)), short=num(gdps))
        ht.put("combat", dur(dur_ms))
        ht.put("players", "%d" % len(self.players_rows))
        ht.put("events", "%d" % events)
        ht.put("recorded", dur(c.now))
        if tab == "resumo":
            self.refresh_summary(c)
        elif tab == "jogadores":
            self.refresh_players(c)
        elif tab == "equip":
            self.refresh_equip(c)
        elif tab == "monstros":
            self.refresh_monsters(c)
        elif tab == "drops":
            self.refresh_drops(c)
        elif tab == "xp":
            self.refresh_xp(c)
        elif tab == "linha":
            self.timeline.refresh(c)
        elif tab == "buffs":
            self.refresh_buffs(c)
        elif tab == "mortes":
            self.refresh_deaths(c)
        elif tab == "dedo":
            self.refresh_dedo(c)

    def refresh_summary(self, c):
        self.summary_tab.refresh(c)

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
            bits += [row["job"], _("do grupo") if row["party"] else _("fora do grupo"),
                     _("dano %s") % full(row["total"]), "DPS %s" % full(round(row["dps"]))]
            if row["deaths"]:
                bits.append(_("%d morte(s)") % row["deaths"])
        self.player_title.configure(text="  ·  ".join(b for b in bits if b))
        sub = self.player_nb.index(self.player_nb.select())
        if sub == 0:
            self.t_pskills.set_rows(an.player_skills(c, self.rng, aid, self.dur_ms), lambda r: r["name"])
        elif sub == 1:
            self.t_ptargets.set_rows(an.player_targets(c, self.rng, aid, self.group_var.get()), lambda r: r["key"])
        elif sub == 2:
            import stats
            self.t_psupport.set_rows(an.support_uses(c, self.rng, aid), lambda r: r["skill"])
            self.t_pitems.set_rows(stats.items_used(c, self.rng, aid), lambda r: r["item"])
        elif sub == 3:
            self.t_ptaken.set_rows(an.damage_taken(c, self.rng, aid), lambda r: "%s|%s" % (r["source"], r["name"]))
        elif sub == 4:
            brows, _total = an.buff_uptime(c, aid, self.rng)
            for r in brows:
                r["kind_txt"] = _(r["kind"])
            self.t_pbuffs.set_rows([r for r in brows if r["kind"] != "Serviço"], lambda r: r["name"])
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
                first = c.spawned.get(root, starts[0] if starts else 0)
                nums = c.phase_numbers([first] + list(starts))[1:]      # fase 2 pulada: "Fase 3"
                out += [(t, _("Fase %d") % n) for t, n in zip(starts, nums)]
        return out

    def refresh_monsters(self, c):
        self.mobs_tab.refresh(c)

    # ------------------------------------------------------------ buffs

    def build_buffs(self):
        c = self.c
        tab = tk.Frame(self.nb, bg=c["panel"])
        self.nb.add(tab, text=_("Buffs e Debuffs"))
        bar = tk.Frame(tab, bg=c["panel"])
        bar.pack(fill="x", padx=10, pady=(10, 2))
        self.label(bar, _("Luta:"), color="muted", bg="panel").pack(side="left")
        self.bf_fight = tk.StringVar(self.top, "")
        self.bf_fight_box = ttk.Combobox(bar, textvariable=self.bf_fight, width=54, state="readonly",
                                         style="An.TCombobox", font=self.f["text"])
        self.bf_fight_box.pack(side="left", padx=6)
        self.bf_fight_box.bind("<<ComboboxSelected>>", lambda e: self.refresh(force=True))
        self.label(bar, _("Fase:"), color="muted", bg="panel").pack(side="left", padx=(12, 0))
        self.bf_phase = tk.StringVar(self.top, "")
        self.bf_phase_box = ttk.Combobox(bar, textvariable=self.bf_phase, width=16, state="readonly",
                                         style="An.TCombobox", font=self.f["text"])
        self.bf_phase_box.pack(side="left", padx=6)
        self.bf_phase_box.bind("<<ComboboxSelected>>", lambda e: self.refresh(force=True))
        self.bf_phases, self.bf_ctx = {}, (None, None)
        self.label(bar, _("Jogador:"), color="muted", bg="panel").pack(side="left", padx=(12, 0))
        self.bf_player = tk.StringVar(self.top, "")
        self.bf_player_box = ttk.Combobox(bar, textvariable=self.bf_player, width=26, state="readonly",
                                          style="An.TCombobox", font=self.f["text"])
        self.bf_player_box.pack(side="left", padx=6)
        self.bf_player_box.bind("<<ComboboxSelected>>", lambda e: self.refresh(force=True))
        self.bf_fights, self.bf_players, self.bf_cache = {}, {}, (None, None)
        # ranking: quanto do dano cada efeito rendeu, ou o dano creditado a cada jogador
        modes = tk.Frame(tab, bg=c["panel"])
        modes.pack(fill="x", padx=10, pady=(6, 0))
        self.label(modes, _("Gráfico:"), color="muted", bg="panel").pack(side="left")
        self.bf_mode = tk.StringVar(self.top, "jogador")
        for value, text in (("jogador", _("Dano creditado a cada jogador")), ("efeito", _("Quanto cada efeito rendeu"))):
            tk.Radiobutton(modes, text=text, variable=self.bf_mode, value=value, command=self.bf_mode_changed,
                           bg=c["panel"], fg=c["fg"], selectcolor=c["btn"], activebackground=c["panel"],
                           activeforeground=c["fg"], font=self.f["text"], highlightthickness=0).pack(side="left", padx=(8, 0))
        self.bf_credit = ([], 0)
        self.bf_chart = tk.Canvas(tab, height=int(150 * self.dpi * self.zoom), bg=c["panel"], highlightthickness=0, bd=0)
        self.bf_chart.pack(fill="x", padx=12, pady=(6, 0))
        self.bf_chart.bind("<Configure>", lambda e: self.draw_contrib())
        self.bf_rows = []
        self.bf_note = self.label(tab, "", "small", "muted", "panel", anchor="w", justify="left", wraplength=1150)
        self.bf_note.pack(fill="x", padx=12, pady=(4, 2))
        self.bf_mode_changed(redraw=False)
        pw = ttk.PanedWindow(tab, orient="horizontal", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True, pady=(4, 0))
        left = tk.Frame(pw, bg=c["panel"])
        right = tk.Frame(pw, bg=c["panel"])
        pw.add(left, weight=1)
        pw.add(right, weight=1)
        self.debuffs_title = self.section(left, _("Debuffs no chefe"))
        self.t_debuffs = Table(left, self, [
            ("rank", "#", 34, "e", "int"), ("name", _("Debuff"), 180, "w", "text"), ("contrib", _("Rendeu"), 100, "e", "big"),
            ("share", _("% do dano"), 90, "e", "pct"), ("uptime", _("Ativo"), 65, "e", "pct"),
            ("rule", _("Como conta"), 300, "w", "text")], height=8)
        self.t_debuffs.pack(fill="both", expand=True, padx=(8, 4), pady=(0, 8))
        self.buffs_title = self.section(right, _("Buffs"))
        self.t_buffs = Table(right, self, [
            ("rank", "#", 34, "e", "int"), ("name", _("Buff"), 180, "w", "text"), ("contrib", _("Rendeu"), 100, "e", "big"),
            ("share", _("% do dano"), 90, "e", "pct"), ("uptime", _("Ativo"), 65, "e", "pct"),
            ("kind_txt", _("Tipo"), 105, "w", "text"), ("desc", _("Efeito"), 340, "w", "text"),
            ("now_txt", _("Agora"), 90, "e", "text")], height=8)
        self.t_buffs.pack(fill="both", expand=True, padx=(4, 8), pady=(0, 8))

    def refresh_buffs(self, c):
        fights = dd.boss_fights(c, self.rng)
        self.bf_fights = collections.OrderedDict((dd.fight_label(c, f), f["key"]) for f in fights)
        labels = list(self.bf_fights)
        if list(self.bf_fight_box["values"]) != labels:
            self.bf_fight_box["values"] = labels
        if self.bf_fight.get() not in self.bf_fights:
            self.bf_fight.set(labels[0] if labels else "")
        key = self.bf_fights.get(self.bf_fight.get())
        # fases da luta escolhida: o recorte vira só a fase escolhida
        phases = collections.OrderedDict([(_("Todas as fases"), None)])
        if key is not None:
            sig = (id(c), c.version, key, self.rng)
            if self.bf_ctx[0] != sig:
                self.bf_ctx = (sig, dd.Ctx(c, key, self.rng))
            x = self.bf_ctx[1]
            if len(x.phases) > 1:
                for p in x.phases:
                    phases[x.phase_name(p)] = (p["start"], p["end"])
        self.bf_phases = phases
        if list(self.bf_phase_box["values"]) != list(phases):
            self.bf_phase_box["values"] = list(phases)
        if self.bf_phase.get() not in phases:
            self.bf_phase.set(_("Todas as fases"))
        self.bf_phase_box.configure(state="readonly" if len(phases) > 1 else "disabled")
        rng = phases.get(self.bf_phase.get()) or self.rng
        if self.rng and phases.get(self.bf_phase.get()):
            rng = (max(rng[0], self.rng[0]), min(rng[1], self.rng[1]))
        players = self.players_rows
        self.bf_players = collections.OrderedDict([(_("Todos"), None)] + [
            ((_("%s (você)") % p["name"]) if p["me"] else p["name"], p["aid"]) for p in players])
        if list(self.bf_player_box["values"]) != list(self.bf_players):
            self.bf_player_box["values"] = list(self.bf_players)
        if self.bf_player.get() not in self.bf_players:
            self.bf_player.set(_("Todos"))
        aid = self.bf_players.get(self.bf_player.get())
        sig = (id(c), c.version, key, aid, rng)
        if self.bf_cache[0] != sig:
            self.bf_cache = (sig, contrib.fight(c, key, rng, aid) if key is not None else ([], 0))
        rows, total = self.bf_cache[1]
        self.bf_rows = rows
        csig = (id(c), c.version, key, rng)
        if self.bf_mode.get() == "jogador" and getattr(self, "bf_credit_sig", None) != csig:
            self.bf_credit_sig = csig
            self.bf_credit = contrib.credit(c, key, rng) if key is not None else ([], 0)
        self.draw_contrib()
        # debuffs no chefe: os estimados primeiro, depois os outros que apareceram nele
        deb = [dict(r) for r in rows if r["where"] == "boss"]
        if key is not None:
            seen = {r["efst"] for r in deb}
            drows, _span = an.mob_debuffs(c, rng, key, self.group_var.get())
            for r in drows:
                if r["efst"] not in seen:
                    deb.append(dict(key=r["efst"], efst=r["efst"], name=r["name"], contrib=None, share=None,
                                    uptime=r["uptime"], rule=meter.status_desc(r["efst"]) or _("sem estimativa de dano")))
        for i, r in enumerate(deb):           # já vêm do que mais rendeu para o que menos rendeu
            r["rank"] = i + 1
        self.debuffs_title.configure(text=(_("Debuffs no chefe — %s de dano olhado") % full(total)) if key is not None
                                     else _("Debuffs no chefe — escolha uma luta contra chefe"))
        self.t_debuffs.set_rows(deb, lambda r: r["key"], lambda r: ["good"] if r["contrib"] else [])
        # buffs do jogador escolhido (ou de quem gravou): tempo ativo, e quanto rendeu quando dá para estimar
        who = aid if aid is not None else c.me
        # mesmo recorte do gráfico e dos debuffs: a luta escolhida (ou a fase), não a sessão inteira; senão o
        # combate de antes (outro mapa, outro grupo) entra na conta e derruba o tempo ativo dos buffs da luta
        buff_rng = rng
        if key is not None and not phases.get(self.bf_phase.get()):
            x = self.bf_ctx[1]
            buff_rng = (x.start, x.end)
            if self.rng:
                buff_rng = (max(buff_rng[0], self.rng[0]), min(buff_rng[1], self.rng[1]))
        brows, btotal = an.buff_uptime(c, who, buff_rng)
        est = {r["efst"]: r for r in rows if r["where"] == "me"}
        out = []
        for r in brows:
            e = est.pop(r.get("efst"), None)
            now = ""
            if r["active"]:
                now = (_("ativo · %s") % dur(r["left"])) if r["left"] is not None else _("ativo")
            out.append(dict(key=r["name"], name=r["name"], contrib=e["contrib"] if e else None,
                            share=e["share"] if e else None, uptime=r["uptime"], kind_txt=_(r["kind"]), now_txt=now,
                            kind=r["kind"], desc=e["rule"] if e else meter.status_desc(r.get("efst"))))
        for e in est.values():
            out.append(dict(key=e["name"], name=e["name"], contrib=e["contrib"], share=e["share"], uptime=e["uptime"],
                            kind_txt=e.get("kind_txt", ""), now_txt="", kind="", desc=e["rule"]))
        # hierarquia: o que rendeu dano estimado; depois suporte do grupo, buffs de classe, consumíveis e serviços
        tier = {"Grupo/suporte": 0, "Classe/outros": 1, "Consumível": 2, "Outro": 3, "Serviço": 4}
        out.sort(key=lambda r: (-(r["contrib"] or 0), tier.get(r["kind"], 1), -(r["uptime"] or 0), r["name"]))
        for i, r in enumerate(out):
            r["rank"] = i + 1
        title = _("Buffs de %s na luta — %% do tempo em combate, vivo (%s)") if buff_rng is not rng else             _("Buffs de %s — %% do tempo em combate, vivo (%s)")
        self.buffs_title.configure(text=title % (c.name_of(who), dur(btotal)))
        self.t_buffs.set_rows(out, lambda r: r["key"],
                              lambda r: ["good"] if r["contrib"] else (
                                  ["warn"] if r["kind"] in ("Grupo/suporte", "Consumível") and r["uptime"] is not None
                                  and r["uptime"] < 0.8 else []))

    def bf_mode_changed(self, redraw=True):
        if self.bf_mode.get() == "jogador":
            text = _("Creditado = a parte do dano que é do próprio jogador (os golpes dele sem os efeitos dos outros) "
                     "mais o que os efeitos que ele pôs renderam nos golpes de todos: Cometa, Pólen, Garra Sombria, "
                     "Avanço Sísmico, Lex Aeterna... Quando vários efeitos valem no mesmo golpe, o ganho é dividido "
                     "entre eles, então tudo soma 100%. Ficam de fora os buffs cujo ganho depende de atributos que o "
                     "replay não mostra (Competentia, Benedictum, Bênção, Agilidade...). É estimativa, e só conta o que "
                     "aparece no replay.")
        else:
            text = _("Rendeu = quanto o dano cairia sem o efeito, pela fórmula de cada um (rAthena e textos do "
                     "jogo), golpe a golpe e só onde ele vale (fogo, físico, corpo a corpo...). É estimativa: os "
                     "buffs cujo ganho depende de atributos que o replay não mostra (Competentia, Benedictum, Bênção, "
                     "Agilidade...) aparecem só com o tempo ativo.")
        self.bf_note.configure(text=text)
        if redraw:
            self.refresh(force=True)

    def draw_credit(self):
        """Barras empilhadas: o dano creditado a cada jogador (próprio + cada efeito que ele pôs)."""
        cv, col, f = self.bf_chart, self.c, self.f
        cv.delete("all")
        W = cv.winfo_width()
        d = self.dpi * self.zoom
        rows, total = self.bf_credit
        rows = [r for r in rows if r["total"] >= total * 0.0005][:12] if total else []
        if not rows:
            cv.configure(height=int(40 * d))
            cv.create_text(8, 20 * d, anchor="w", fill=col["muted"], font=f["text"],
                           text=_("Nenhuma luta contra chefe no recorte."))
            return
        c = self.combat()
        name = lambda aid: c.name_of(aid) if aid is not None else _("(quem pôs não aparece)")
        rh = 24 * d
        legend_h = 22 * d
        cv.configure(height=int(rh * len(rows) + legend_h + 10 * d))
        label_w = max(f["text"].measure(name(r["aid"])) for r in rows) + 16 * d
        top = max(r["total"] for r in rows) or 1

        def text_of(r):
            bits = [dec("%.1f%%" % (100.0 * r["total"] / total)), full(round(r["total"]))]
            bits += ["%s %s" % (contrib.effect_name(ef), dec("%.1f%%" % (100.0 * v / total)))
                     for ef, v in sorted(r["via"].items(), key=lambda kv: -kv[1]) if v >= total * 0.0005]
            if r["via"] and r["own"] >= total * 0.0005:
                bits.append(_("próprio %s") % dec("%.1f%%" % (100.0 * r["own"] / total)))
            return " · ".join(bits)
        texts = [text_of(r) for r in rows]
        # a barra mais comprida de cada linha + o texto dela cabem na largura
        bar_w = min([W - label_w - 14 * d - f["small"].measure(t) for t in texts[:1]] +
                    [(W - label_w - 14 * d - f["small"].measure(t)) * top / (r["total"] or 1)
                     for r, t in zip(rows, texts)])
        bar_w = max(60, bar_w)
        used = []
        for i, r in enumerate(rows):
            y = 4 * d + i * rh
            cv.create_text(label_w - 8 * d, y + rh / 2, anchor="e", text=name(r["aid"]), fill=col["fg"], font=f["text"])
            x = label_w
            parts = [(None, r["own"])] + sorted(r["via"].items(), key=lambda kv: -kv[1])
            for ef, v in parts:
                w = bar_w * v / top
                if w < 0.5:
                    continue
                color = self.color_of(r["aid"]) if ef is None else EFFECT_COLORS.get(ef, col["accent"])
                cv.create_rectangle(x, y + 4 * d, x + w, y + rh - 4 * d, fill=color, outline="")
                x += w
                if ef is not None and ef not in used:
                    used.append(ef)
            cv.create_text(x + 8 * d, y + rh / 2, anchor="w", fill=col["fg"], font=f["small"], text=texts[i])
        # legenda das cores dos efeitos
        y = 6 * d + len(rows) * rh + legend_h / 2
        x = label_w
        cv.create_text(x, y, anchor="w", fill=col["muted"], font=f["small"], text=_("cor do jogador = dano próprio"))
        x += f["small"].measure(_("cor do jogador = dano próprio")) + 16 * d
        for ef in used:
            cv.create_rectangle(x, y - 5 * d, x + 10 * d, y + 5 * d, fill=EFFECT_COLORS.get(ef, col["accent"]), outline="")
            label = contrib.effect_name(ef)
            cv.create_text(x + 14 * d, y, anchor="w", fill=col["muted"], font=f["small"], text=label)
            x += 14 * d + f["small"].measure(label) + 14 * d

    def draw_contrib(self):
        """Barras: quanto do dano cada efeito rendeu (do maior para o menor)."""
        if self.bf_mode.get() == "jogador":
            self.draw_credit()
            return
        cv, col, f = self.bf_chart, self.c, self.f
        cv.delete("all")
        W = cv.winfo_width()
        rows = [r for r in self.bf_rows if r["contrib"] > 0][:6]
        d = self.dpi * self.zoom
        if not rows:
            cv.configure(height=int(40 * d))
            cv.create_text(8, 20 * d, anchor="w", fill=col["muted"], font=f["text"],
                           text=_("Nenhum efeito com dano estimado nesta luta (ou nenhuma luta contra chefe no recorte)."))
            return
        rh = 24 * d
        cv.configure(height=int(rh * len(rows) + 8 * d))
        label_w = max(f["text"].measure(r["name"]) for r in rows) + 16 * d
        top = max(r["share"] for r in rows) or 1
        bar_w = max(60, W - label_w - 260 * d)
        for i, r in enumerate(rows):
            y = 4 * d + i * rh
            cv.create_text(label_w - 8 * d, y + rh / 2, anchor="e", text=r["name"], fill=col["fg"], font=f["text"])
            w = bar_w * r["share"] / top
            color = col["accent"] if r["where"] == "boss" else col["good"]
            cv.create_rectangle(label_w, y + 4 * d, label_w + max(2, w), y + rh - 4 * d, fill=color, outline="")
            cv.create_text(label_w + w + 8 * d, y + rh / 2, anchor="w", fill=col["fg"], font=f["small"],
                           text=_("%s do dano · %s · %s") % (
                               dec("%.1f%%" % (100 * r["share"])), full(round(r["contrib"])),
                               (_("ativo %s") % dec("%.0f%%" % (100 * r["uptime"]))) if r["uptime"] is not None
                               else _("%d golpes dobrados") % r["hits"]))

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
            ("cause", _("Causa"), 250, "w", "text"), ("el_txt", _("Propriedade"), 85, "w", "text"),
            ("hit", _("Golpe"), 105, "e", "big"),
            ("hp_before", _("HP antes"), 95, "e", "big"), ("overkill", _("Overkill"), 105, "e", "big"),
            ("taken_5s", _("Dano em 5 s"), 110, "e", "big")], height=6, on_select=self.death_selected, swatch=True)
        self.t_deaths.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        # a morte escolhida: o desenho de quem matou, o golpe com a propriedade dele e o que aconteceu
        info = tk.Frame(lower, bg=self.c["panel"])
        info.pack(fill="x", padx=10, pady=(8, 4))
        art = tk.Frame(info, bg=self.c["tile"])
        art.pack(side="left", anchor="n", padx=(0, 12))
        self.death_sprite = ui_parts.SpriteView(art, self, w=124, h=108)
        self.death_sprite.pack(padx=3, pady=3)
        txt = tk.Frame(info, bg=self.c["panel"])
        txt.pack(side="left", fill="both", expand=True)
        self.death_title = self.label(txt, "", "head", bg="panel", anchor="w", justify="left")
        self.death_title.pack(fill="x")
        chips = tk.Frame(txt, bg=self.c["panel"])
        chips.pack(fill="x", pady=(3, 3))
        self.death_skill = self.label(chips, "", "text", bg="panel", anchor="w")
        self.death_skill.pack(side="left")
        self.death_el = tk.Label(chips, text="", font=self.f["small"], bg=self.c["panel"], fg="#111318", padx=6)
        self.death_el.pack(side="left", padx=(8, 0))
        self.death_text = self.label(txt, "", "text", "muted", "panel", anchor="w", justify="left")
        self.death_text.pack(fill="x")
        self.t_recap = Table(lower, self, [
            ("rel_txt", _("Antes da morte"), 110, "e", "text"), ("source", _("Fonte"), 200, "w", "text"),
            ("name", _("Habilidade / evento"), 200, "w", "text"), ("el_txt", _("Propriedade"), 95, "w", "text"),
            ("dmg", _("Dano"), 110, "e", "big"), ("hp", _("HP"), 100, "e", "big")], height=8)
        self.t_recap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.death_key = None
        self.death_rows = []
        self.death_wrap = False
        ui_parts.follow_wrap(txt, [self.death_title, self.death_text], 16)

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
            elif d["special"] == "boom":
                d["cause"] = _("%s · %s (dano fixo, sem número na tela)") % (d["skill"], d["killer"])
            elif d["special"] == "offscreen":
                d["cause"] = _("provável golpe de %s fora da tela (sobrecarga há %d s)") % (
                    d["killer"], round(d["overload_ms"] / 1000.0))
            elif d["unclear"]:
                d["cause"] = _("último golpe: %s · %s (não bastava sozinho)") % (d["skill"], d["killer"])
            else:
                d["cause"] = "%s · %s" % (d["skill"], d["killer"])
            d["el_txt"] = an.element_name(d.get("kill_element"))
            if d["unclear"] or d["fusion"] or not d["overkill"]:
                d["overkill"] = None
            if d["special"]:
                d["hit"] = None                # explosão sem pacote de dano / golpe de fora da tela: não há número
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
            self.death_skill.configure(text="")
            self.death_el.configure(text="", bg=self.c["panel"])
            self.death_sprite.set(None)
            self.t_recap.set_rows([], lambda r: 0)
            return
        self.death_sprite.set(d.get("killer_job"), d.get("killer") or "", sprites.MOB_ATTACK)
        el = d.get("kill_element")
        named = bool(d.get("skill")) and not d["no_hit"]
        self.death_skill.configure(text=("%s · %s" % (d["skill"], d["killer"])) if named and d.get("killer")
                                   else (d["skill"] if named else ""))
        self.death_el.configure(text=an.element_name(el) if el else "",
                                bg=an.ELEMENT_COLORS.get(el, self.c["panel"]) if el else self.c["panel"])
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
        elif d["special"] == "boom":
            title += _(" — %s de %s (dano fixo, sem número na tela)") % (d["skill"], d["killer"])
        elif d["special"] == "offscreen":
            title += _(" — provável golpe de %s fora da tela") % d["killer"]
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
        if d["special"] == "boom":
            bits.append(_("a explosão não manda pacote de dano: tira um valor fixo de HP de quem está perto "
                        "(no Aquila, 120.000 na %s e 300.000 na %s)") % (_("Executiva"), _("Primeira Classe")))
        elif d["special"] == "offscreen":
            bits.append(_("o chefe estava fora da tela e em sobrecarga há %d s: o golpe dele cresce a cada segundo "
                        "de sobrecarga e, de fora da tela, não chega ao replay nem aparece no jogo")
                        % round(d["overload_ms"] / 1000.0))
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
            rows.append(dict(r, key=i, rel_txt=dec("%.1f s" % (r["rel"] / 1000.0)),
                             el_txt=an.element_name(r.get("element"))))
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
        self.dd_hp = HpPicker(bar, self)
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
        ui_parts.follow_wrap(self.dd_banner, self.dd_sub, 30)
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
        side = dict(frame=frame, hint_text="")
        pw = ttk.PanedWindow(frame, orient="vertical", style="An.TPanedwindow")
        pw.pack(fill="both", expand=True)
        upper = tk.Frame(pw, bg=c["panel"])
        lower = tk.Frame(pw, bg=c["panel"])
        pw.add(upper, weight=3)
        pw.add(lower, weight=2)
        row = tk.Frame(upper, bg=c["panel"])
        row.pack(fill="x", padx=10, pady=(8, 4))
        side["title"] = self.label(row, "", "head", bg="panel", anchor="w")
        side["title"].pack(side="left")
        # como o Dedo Duro avalia: numa dica, para a lista de alertas ficar com o espaço
        how = self.label(row, _("ⓘ como é avaliado"), "small", "muted", "panel", cursor="question_arrow")
        how.pack(side="right")
        tip = ui_parts.Tip(self)

        def show_how(e, sd=side):
            tip.show(id(sd), e.x_root, e.y_root, lambda fr: tk.Label(
                fr, text=sd["hint_text"], font=self.f["small"], fg=self.c["fg"], bg=self.c["tip"], justify="left",
                wraplength=int(520 * self.dpi)).pack())
        how.bind("<Enter>", show_how)
        how.bind("<Leave>", lambda e: tip.hide())
        # cada alerta num cartão, com o detalhe inteiro
        side["alerts"] = ui_parts.AlertList(upper, self)
        side["alerts"].pack(fill="both", expand=True, padx=6, pady=(0, 2))
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
                                       ("dur_txt", _("Sem Garra"), 130, "e", "text"),
                                       ("pain_txt", _("Dor Máxima"), 90, "center", "text"),
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
        specs.append(("risk", _("Zona de risco"), [
            ("name", _("Jogador"), 140, "w", "text"), ("job", _("Classe"), 120, "w", "text"),
            ("seen", _("Tempo olhado"), 95, "e", "dur"), ("risk_ms", _("Na zona de risco"), 115, "e", "dur"),
            ("share", _("% em risco"), 85, "e", "pct"), ("hits", _("Golpes de armadilha"), 150, "e", "int"),
            ("risk_hits", _("Golpes na zona de risco"), 155, "e", "int"), ("where", _("Onde mais ficou"), 150, "w", "text")]))
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
            if key == "risk":
                note = self.label(f, _("Só na fase 3 do Betelgeuse, de 1 s antes a 16 s depois de ele aparecer. "
                                       "Zona segura: a coluna 2 ← abaixo do Betel (de 2 ← 1 ↓ a 2 ← 6 ↓), 1 → 1 ↓ "
                                       "de 7,5 a 14,5 s e tudo fora do alcance das armadilhas (o canto esquerdo da "
                                       "arena). Atenção para quem passou 40% do tempo ou mais (e 2 s ou mais) fora "
                                       "dela."), "small", "muted", "panel", anchor="w", justify="left")
                note.pack(fill="x", padx=6, pady=(6, 0))
                ui_parts.follow_wrap(f, note, 20)
            t = Table(f, self, cols, height=4, swatch=key in ("deaths", "players", "element", "buffs", "poison"))
            t.pack(fill="both", expand=True, padx=4, pady=6)
            side["tables"][key] = t
        return side

    def dd_pick(self):
        self.dd_key = self.dd_fights.get(self.dd_var.get())
        self.refresh(force=True)

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
            self.dd_hp.sync(c, None)
            self.dd_title.configure(text=_("Nenhuma luta contra chefe neste recorte"))
            self.dd_sub.configure(text=_("O Dedo Duro olha as lutas contra MVPs, chefes de instância e bonecos de treino."))
            self.dd_counts.configure(text="")
            for side in (self.dd_group, self.dd_other):
                side["alerts"].set([])
                side["title"].configure(text="")
                side["hint_text"] = ""
                for t in side["tables"].values():
                    t.set_rows([], lambda r: 0)
            return
        self.dd_hp.sync(c, self.dd_key)
        sig = (id(c), c.version, self.dd_key, self.rng, an.hp_choice(c, self.dd_key))
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
        side["alerts"].set(alerts)
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
        side["hint_text"] = hint
        multi = r["multi"]
        n = len(r["phases"])
        titles = {"p1": _("Fase 1") if multi else _("Clímax"), "p2": _("Fase 2"), "p3": _("Fase 3")}
        for i, p in enumerate(r["phases"][:3]):      # número de verdade (fase 2 pulada: 1 e 3)
            if multi or p.get("marked"):
                titles["p%d" % (i + 1)] = _("Fase %d") % p["n"]
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
        risk = r.get("risk" if party else "o_risk") or []
        t["risk"].set_rows(risk, lambda x_: x_["key"], lambda x_: ["mid"] if x_["bad"] else (["me"] if x_["me"] else []),
                           color)
        side["sub"].tab(side["tabs"]["risk"], text=_("Zona de risco") if r.get("risk_phase")
                        else _("Zona de risco (sem fase 3)"))

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
        import ui_tests
        self.tests_tab = ui_tests.TestsTab(self, self.nb)

    def store(self):
        return self.app.tests

    def refresh_tests(self):
        self.tests_tab.refresh()

    def save_test(self):
        """Salva como teste qualquer luta do replay aberto (de chefe, boneco ou a sessão inteira), inclusive de
        replays gravados por outra pessoa: o equipamento salvo é o de quem gravou."""
        rf = self.app.watcher.file
        if rf is None or not rf.ready or rf.combat is None:
            return
        c = rf.combat
        self.update_scope_list(c)
        choices = [(_("Sessão inteira"), None)] + [(lbl, enc) for lbl, enc in self.scope_items]
        current = self.scope(c)
        dlg = tk.Toplevel(self.top)
        dlg.title(_("Salvar luta como teste"))
        dlg.configure(bg=self.c["panel"])
        dlg.transient(self.top)
        dlg.resizable(False, False)
        box = tk.Frame(dlg, bg=self.c["panel"], padx=14, pady=12)
        box.pack(fill="both", expand=True)
        self.label(box, _("Gravado por %s · o equipamento salvo é o dessa pessoa") % (rf.session.player or "?"),
                   "small", "muted", "panel", anchor="w").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.label(box, _("Luta:"), bg="panel").grid(row=1, column=0, sticky="w")
        fight_var = tk.StringVar(dlg, next((lbl for lbl, enc in choices if enc is current), choices[0][0]))
        cb = ttk.Combobox(box, textvariable=fight_var, values=[lbl for lbl, _e in choices], state="readonly", width=56,
                          style="An.TCombobox", font=self.f["text"])
        cb.grid(row=1, column=1, sticky="we", padx=(8, 0), pady=2)
        self.label(box, _("Rótulo:"), bg="panel").grid(row=2, column=0, sticky="w")
        label_var = tk.StringVar(dlg, "")
        entry = tk.Entry(box, textvariable=label_var, width=58, font=self.f["text"], bg=self.c["btn"], fg=self.c["fg"],
                         insertbackground=self.c["fg"], relief="flat")
        entry.grid(row=2, column=1, sticky="we", padx=(8, 0), pady=6, ipady=3)
        self.label(box, _("ex.: com Coroa +12, sem Impositio"), "small", "muted", "panel", anchor="w").grid(
            row=3, column=1, sticky="w", padx=(8, 0))
        buttons = tk.Frame(box, bg=self.c["panel"])
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))

        def save():
            enc = dict(choices).get(fight_var.get())
            rec = testes.build(rf, enc, label_var.get().strip())
            rec["key"] += "|manual|%s" % rec["id"]
            self.store().add(rec)
            dlg.destroy()
            self.refresh(force=True)
        ttk.Button(buttons, text=_("Cancelar"), style="An.TButton", command=dlg.destroy).pack(side="right")
        ttk.Button(buttons, text=_("Salvar"), style="An.TButton", command=save).pack(side="right", padx=6)
        dlg.bind("<Return>", lambda e: save())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        entry.focus_set()

    def rename_test(self):
        rec = self.tests_tab.focused()
        if rec is None:
            return
        label = simpledialog.askstring(_("Renomear teste"), _("Rótulo:"), initialvalue=rec.get("label", ""),
                                       parent=self.top)
        if label is not None:
            self.store().rename(rec["id"], label.strip())
            self.refresh(force=True)

    def delete_test(self):
        rec = self.tests_tab.focused()
        if rec is not None:
            self.store().delete([rec["id"]])
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

    def hide_names_changed(self):
        self.app.cfg["copy_hide_names"] = bool(self.hide_names_var.get())
        self.app.save()

    def copy_hovered(self, _event=None):
        """Ctrl+Shift+C: copia só o gráfico (Canvas) que está sob o mouse; fora de um gráfico, a aba inteira."""
        try:
            x, y = self.top.winfo_pointerxy()
            w = self.top.winfo_containing(x, y)
        except (tk.TclError, KeyError):
            w = None
        self.copy_image(w if isinstance(w, tk.Canvas) else None)
        return "break"

    def copy_image(self, widget=None):
        """Copia a janela (ou um gráfico) como imagem. Com "sem nomes", redesenha antes com cada jogador como a
        classe e volta ao normal depois."""
        c = self.combat()
        hide = bool(self.app.cfg.get("copy_hide_names")) and c is not None
        ok = False
        try:
            if hide:
                meter.HIDE_NAMES = True
                c.version += 1                    # o que está guardado com os nomes de verdade é refeito
                self.refresh(force=True)
            self.top.update_idletasks()
            if hide:
                self.top.update()
            ok = clipimg.copy_widget(self.top, widget)
        except Exception:  # noqa: BLE001
            self.app.log_error(*__import__("sys").exc_info())
        finally:
            if hide:
                meter.HIDE_NAMES = False
                c.version += 1
                self.refresh(force=True)
        self.copy_img_btn.configure(text=_("Imagem copiada!") if ok else _("Não deu para copiar"))
        self.top.after(1500, lambda: self.copy_img_btn.configure(text=_("Copiar imagem")))

    def close(self):
        try:
            zoomed = self.top.state() == "zoomed"
            self.app.cfg["an_zoomed"] = zoomed
            if not zoomed:
                self.app.cfg["an_geometry"] = self.top.geometry()
            elif self.normal_geo:
                self.app.cfg["an_geometry"] = self.normal_geo      # o tamanho de antes de maximizar
            self.app.save()
        except tk.TclError:
            pass
        self.top.destroy()
        self.app.analysis = None


def _lum(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
