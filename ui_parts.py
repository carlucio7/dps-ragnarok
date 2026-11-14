# -*- coding: utf-8 -*-
"""Peças da janela de análise usadas por mais de uma aba: ícones dos itens, dica flutuante, painel de equipamento
(ícone, nome e cartas de cada peça, com a ficha inteira ao passar o mouse), o desenho animado de um monstro e a
comparação lado a lado dos testes.

Os desenhos vêm do data.grf do próprio jogo (sprites.MONSTERS); sem o jogo instalado, tudo aparece só com texto.
"""

import base64
import struct
import tkinter as tk

import clientdata
import gdip
import meter
import sprites
import xp
from fmt import dec
from i18n import _

# grupos de slots do painel de equipamento (os rótulos são os de meter.EQUIP_SLOTS)
GEAR = ["Topo", "Meio", "Baixo", "Armadura", "Arma", "Escudo", "Capa", "Sapato", "Acessório esq.",
        "Acessório dir.", "Munição"]
SHADOW = ["Sombrio armadura", "Sombrio arma", "Sombrio escudo", "Sombrio sapato", "Sombrio acess. dir.",
          "Sombrio acess. esq."]
VISUAL = ["Visual topo", "Visual meio", "Visual baixo", "Visual capa"]
GROUPS = [("Equipamento", GEAR), ("Sombrio", SHADOW), ("Visual", VISUAL)]
GRADE_COLORS = {"D": "#94a3b8", "C": "#4ade80", "B": "#38bdf8", "A": "#c084fc"}
ICON_PX = 24                  # os ícones de item do jogo têm 24 × 24
WAIT_MS = 300                 # enquanto os desenhos carregam, o painel se redesenha a cada tanto...
WAIT_TRIES = 40               # ...até desistir (jogo não encontrado: fica só o texto)


def mix(a, b, t):
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * t)) for x, y in zip(pa, pb))


def fit(font, text, max_w):
    """O texto cortado com reticências para caber em max_w pontos."""
    if max_w <= 0:
        return ""
    if font.measure(text) <= max_w:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid] + "…") <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo].rstrip() + "…") if lo else ""


def follow_wrap(box, labels, margin, minimum=120):
    """A quebra de linha dos textos `labels` acompanha a largura de `box` (menos `margin`), com folga: só muda
    quando o texto deixaria de caber ou quando sobram mais de 24 px. Sem a folga, numa grade de colunas
    proporcionais a largura pedida pelo texto mexe na largura da coluna, que mexe na quebra, e as colunas ficam
    trocando 1 px uma com a outra para sempre (a janela trava refazendo a conta)."""
    labels = labels if isinstance(labels, (list, tuple)) else [labels]
    state = [0]

    def fit(e):
        if e.widget is not box:
            return
        room = max(minimum, e.width - margin)
        if room < state[0] or room - state[0] >= 24:
            state[0] = max(minimum, room - 12)
            for lbl in labels:
                lbl.configure(wraplength=state[0])
    box.bind("<Configure>", fit, add="+")


def photo(master, w, h, px, zoom=1):
    """PhotoImage dos pixels RGBA; None se o Tk recusar."""
    try:
        img = tk.PhotoImage(master=master, data=sprites.png_b64(w, h, px), format="png")
        return img.zoom(zoom) if zoom > 1 else img
    except (tk.TclError, ValueError, IndexError):
        return None


# reduções possíveis com as imagens do Tk (ampliar × e pegar 1 a cada ÷), da maior para a menor
FIT_RATIOS = [(1, 1), (3, 4), (2, 3), (1, 2), (2, 5), (1, 3), (1, 4), (1, 5), (1, 6), (1, 8)]
LAYER_RATIOS = [(z, q) for q in (1, 2, 3, 4) for z in (1, 2, 3, 4)]


def _fit_ratio(w, h, box_w, box_h):
    """(ampliar, reduzir) para o desenho caber na caixa; os pequenos dobram de tamanho quando cabem."""
    if w * 2 <= box_w and h * 2 <= box_h:
        return 2, 1
    k = min(1.0, box_w / float(w), box_h / float(h))
    return next(((z, q) for z, q in FIT_RATIOS if z / float(q) <= k + 1e-9), FIT_RATIOS[-1])


def _layer_ratio(scale):
    """A escala de uma camada do .act como (ampliar, reduzir) inteiros, a mais próxima."""
    if abs(scale - 1.0) < 0.06:
        return 1, 1
    return min(LAYER_RATIOS, key=lambda zq: abs(zq[0] / float(zq[1]) - scale))


def _smooth_frames(master, part, frames, box_w, box_h, layers):
    """Os quadros montados pelo GDI+ (sprites.smooth_frames), com suavização: [imagens do Tk], ou None se não
    der (aí vale o caminho do Tk). Se o desenho for maior que a caixa, o quadro inteiro é reduzido de uma vez,
    suavizado; os pequenos dobram de tamanho repetindo pixels, como sempre."""
    got = sprites.smooth_frames(part, frames, layers)
    if not got:
        return None
    w, h, shots = got
    double = w * 2 <= box_w and h * 2 <= box_h
    k = 1.0 if double else min(1.0, box_w / float(w), box_h / float(h))
    tw, th = max(1, int(round(w * k))), max(1, int(round(h * k)))
    photos = []
    for data in shots:
        if (tw, th) != (w, h):
            data = gdip.resize(w, h, data, tw, th)
            if data is None:
                return None
        img = tk.PhotoImage(master=master, data=base64.b64encode(sprites.png_rgba(tw, th, gdip.swap_rb(data))),
                            format="png")
        photos.append(img.zoom(2) if double else img)
    return photos


def mob_frames(master, part, action, direction, box_w, box_h, layers):
    """Os quadros de uma ação do monstro como imagens do Tk, todos na mesma moldura (a animação não treme) e do
    tamanho que cabe na caixa: ([imagens], ms por quadro), ou None se a ação não tiver nada.

    Quem monta é o GDI+ do Windows (_smooth_frames), que reduz, amplia e gira com suavização. Sem ele, o próprio
    Tk: cada imagem do .spr vira uma PhotoImage a partir do PNG que sprites.Sprite.png monta direto dos bytes, e
    cada quadro é a cópia dessas imagens na posição de cada camada (espelhada, ampliada ou tingida quando o .act
    pede); esse caminho só repete ou descarta pixels, então os desenhos reduzidos saem serrilhados.
    `layers` guarda as imagens do .spr já convertidas deste monstro."""
    act_i = action * 8 + direction
    frames = part.act.frames(act_i)
    if not frames:
        return None
    step = max(1, -(-len(frames) // sprites.ANIM_FRAMES))
    delays = part.act.delays
    delay = max(40.0, (delays[act_i] if act_i < len(delays) else 100.0) * step)
    if gdip.ready():
        try:
            smooth = _smooth_frames(master, part, frames[::step], box_w, box_h, layers)
        except (tk.TclError, ValueError, TypeError, OSError):
            smooth = None
        if smooth:
            return smooth, delay
    picked = []
    for frame_layers, _anchors in frames[::step]:
        items = []
        for ly in frame_layers:
            size = part.spr.size(ly.kind, ly.index) if ly.index >= 0 else None
            if size is None:
                continue
            zx, qx = _layer_ratio(abs(ly.sx) or 1.0)
            zy, qy = _layer_ratio(abs(ly.sy) or 1.0)
            dw, dh = max(1, -(-size[0] * zx // qx)), max(1, -(-size[1] * zy // qy))
            items.append((int(round(ly.x - dw / 2.0)), int(round(ly.y - dh / 2.0)), dw, dh, ly, (zx, qx, zy, qy)))
        picked.append(items)
    boxes = [it for items in picked for it in items]
    if not boxes:
        return None
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    w, h = max(b[0] + b[2] for b in boxes) - x0, max(b[1] + b[3] for b in boxes) - y0
    z, q = _fit_ratio(w, h, box_w, box_h)
    call = master.tk.call
    photos = []
    for items in picked:
        img = tk.PhotoImage(master=master, width=w, height=h)
        for left, top, _dw, _dh, ly, (zx, qx, zy, qy) in items:
            tint = tuple(ly.color) if tuple(ly.color) != (255, 255, 255, 255) else None
            key = (ly.kind, ly.index, tint)
            src = layers.get(key)
            if src is None:
                data = part.spr.png(ly.kind, ly.index, part.palette if ly.kind == 0 else None, tint)
                src = layers[key] = tk.PhotoImage(master=master, data=base64.b64encode(data), format="png")
            args = [img, "copy", src, "-to", left - x0, top - y0, "-compositingrule", "overlay"]
            if (zx, zy) != (1, 1):
                args += ["-zoom", zx, zy]
            if ly.mirror or (qx, qy) != (1, 1):
                args += ["-subsample", -qx if ly.mirror else qx, qy]
            call(*args)
        if (z, q) != (1, 1):
            out = tk.PhotoImage(master=master)
            args = [out, "copy", img]
            if z != 1:
                args += ["-zoom", z]
            if q != 1:
                args += ["-subsample", q]
            call(*args)
            img = out
        photos.append(img)
    return photos, delay


def start_loaders():
    """Põe para carregar (em threads) o que os desenhos precisam: o data.grf e a tabela de itens do jogo."""
    grf = clientdata.NAMES.grf
    if grf:
        sprites.MONSTERS.start(grf)
    if xp.GEAR.table is None:
        xp.GEAR.start(xp._iteminfo_path())


class Icons:
    """Os ícones dos itens como imagens do Tk, guardados por janela. `waiting` fica ligado quando algum pedido
    ainda não pôde ser atendido (o jogo ainda está sendo lido): quem desenha tenta de novo em seguida."""

    def __init__(self, win):
        self.win = win
        self.cache = {}
        self.waiting = False

    def factor(self):
        z = self.win.dpi * self.win.zoom
        return 1 if z < 1.7 else (2 if z < 2.7 else 3)

    def size(self):
        return ICON_PX * self.factor()

    def get(self, item_id):
        key = (item_id, self.factor())
        if key in self.cache:
            return self.cache[key]
        art = xp.GEAR.art.get(item_id)
        book = sprites.MONSTERS.book
        if not art or book is None:
            if (xp.GEAR.table is None or book is None) and clientdata.NAMES.grf and sprites.MONSTERS.error is None:
                start_loaders()
                self.waiting = True                # ainda carregando: tenta de novo depois
                return None
            if not art:
                self.cache[key] = None
            return None
        img = book.icon(art)
        self.cache[key] = photo(self.win.top, img[0], img[1], img[2], self.factor()) if img else None
        return self.cache[key]


class Tip:
    """Dica flutuante (uma janelinha sem moldura) que segue o que está sob o mouse."""

    def __init__(self, win):
        self.win = win
        self.top = None
        self.key = None

    def show(self, key, x, y, fill):
        """Mostra a dica de `key` perto de (x, y) da tela; `fill(frame)` põe o conteúdo."""
        if key != self.key or self.top is None:
            self.hide()
            c = self.win.c
            self.top = tk.Toplevel(self.win.top)
            self.top.overrideredirect(True)
            try:
                self.top.attributes("-topmost", True)
            except tk.TclError:
                pass
            self.top.configure(bg=c["grid"])
            frame = tk.Frame(self.top, bg=c["tip"], padx=10, pady=8)
            frame.pack(padx=1, pady=1)
            fill(frame)
            self.key = key
        self.top.update_idletasks()
        w, h = self.top.winfo_reqwidth(), self.top.winfo_reqheight()
        sw, sh = self.top.winfo_screenwidth(), self.top.winfo_screenheight()
        px = x + 16 if x + 16 + w <= sw else max(0, x - 12 - w)
        py = y + 18 if y + 18 + h <= sh else max(0, y - 10 - h)
        self.top.geometry("+%d+%d" % (px, py))

    def hide(self):
        if self.top is not None:
            try:
                self.top.destroy()
            except tk.TclError:
                pass
        self.top, self.key = None, None


def item_title(r):
    """"+12 Coroa de Belzebu [1]" a partir da linha do equipamento (testes antigos só têm o texto pronto)."""
    if r.get("name"):
        return ("+%d " % r["refine"] if r.get("refine") else "") + r["name"]
    return r.get("item") or ""


def item_extras(r):
    """Nomes das cartas e encantamentos da peça."""
    return [meter.item_name(cid) for cid in r.get("cards") or []]


class EquipPanel(tk.Canvas):
    """Peças de equipamento em cartões: ícone do jogo, nome com o refino, grau, e embaixo o slot e as cartas.
    Passando o mouse, a ficha inteira (cartas e encantamentos com os ícones, opções aleatórias).

    `groups`: [(título, [slots])]; `cols`: nº de colunas fixo (None = quantas couberem); `diff`: slots a destacar
    (na comparação de testes, os que mudaram)."""

    def __init__(self, parent, win, groups=None, cols=None, min_w=235, bg="panel", titles=True):
        super().__init__(parent, bg=win.c[bg], highlightthickness=0, bd=0, height=10)
        self.win = win
        self.groups = groups or GROUPS
        self.cols, self.min_w, self.bg, self.titles = cols, min_w, bg, titles
        self.rows = {}
        self.diff = set()
        self.show_empty = False
        self.icons = win.icons
        self.tip = Tip(win)
        self.boxes = []               # (x0, y0, x1, y1, linha) dos cartões, para a dica
        self._tries = 0
        self._after = None
        self._width = 0
        self.bind("<Configure>", self._resized)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self.tip.hide())
        self.bind("<Destroy>", lambda e: self.tip.hide())

    def set(self, rows, diff=(), show_empty=False):
        """rows: as linhas de analysis.equipment (ou as guardadas num teste)."""
        self.rows = {r["slot"]: r for r in rows or []}
        self.diff = set(diff)
        self.show_empty = show_empty
        self._tries = 0
        self.redraw()

    def _resized(self, e):
        if e.width != self._width:
            self._width = e.width
            self.redraw()

    def redraw(self):
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        win, c, f = self.win, self.win.c, self.win.f
        z = win.dpi * win.zoom
        self.delete("all")
        self.boxes = []
        self.icons.waiting = False
        W = max(self.winfo_width(), int(120 * z))
        pad, gap = int(6 * z), int(6 * z)
        icon = self.icons.size()
        tile_h = max(icon + int(12 * z), f["text"].metrics("linespace") + f["small"].metrics("linespace") + int(10 * z))
        cols = self.cols or max(1, int((W - pad) // (self.min_w * z)))
        tile_w = (W - pad * 2 - gap * (cols - 1)) / float(cols)
        y = int(2 * z)
        for title, slots in self.groups:
            shown = [s for s in slots if s in self.rows or (self.show_empty and s in self.diff)]
            if not shown:
                continue
            if self.titles:
                self.create_text(pad, y + int(8 * z), anchor="w", text=_(title).upper(), font=f["small"],
                                 fill=c["muted"])
                y += int(20 * z)
            for i, slot in enumerate(shown):
                col, row = i % cols, i // cols
                x0 = pad + col * (tile_w + gap)
                y0 = y + row * (tile_h + gap)
                self._tile(slot, self.rows.get(slot), x0, y0, x0 + tile_w, y0 + tile_h, z, icon)
            y += -(-len(shown) // cols) * (tile_h + gap) + int(6 * z)
        if not self.boxes:
            self.create_text(pad, y + int(10 * z), anchor="w", fill=c["muted"], font=f["text"], width=W - 2 * pad,
                             text=_("Sem itens neste grupo."))
            y += int(26 * z)
        self.configure(height=max(10, y))
        if self.icons.waiting and self._tries < WAIT_TRIES:
            self._tries += 1
            self._after = self.after(WAIT_MS, self.redraw)

    def _tile(self, slot, r, x0, y0, x1, y1, z, icon):
        c, f = self.win.c, self.win.f
        changed = slot in self.diff
        self.create_rectangle(x0, y0, x1, y1, fill=c["tile"], outline=c["accent"] if changed else c["grid"],
                              width=2 if changed else 1)
        ix, iy = x0 + int(7 * z), (y0 + y1) / 2
        tx = ix + icon + int(8 * z)
        right = x1 - int(8 * z)
        line1 = y0 + (y1 - y0) * 0.32
        line2 = y0 + (y1 - y0) * 0.72
        if r is None:
            self.create_rectangle(ix, iy - icon / 2, ix + icon, iy + icon / 2, outline=c["grid"], dash=(2, 2))
            self.create_text(tx, line1, anchor="w", text="—", font=f["text"], fill=c["muted"])
            self.create_text(tx, line2, anchor="w", text=_(slot), font=f["small"], fill=c["muted"])
            self.boxes.append((x0, y0, x1, y1, dict(slot=slot)))
            return
        img = self.icons.get(r.get("item_id"))
        if img is not None:
            self.create_image(ix, iy, anchor="w", image=img)
        else:
            self.create_rectangle(ix, iy - icon / 2, ix + icon, iy + icon / 2, fill=mix(c["tile"], c["fg"], 0.06),
                                  outline="")
        grade = r.get("grade")
        if grade:
            gw = f["small"].measure("A") + int(8 * z)
            col = GRADE_COLORS.get(grade, c["muted"])
            self.create_rectangle(right - gw, line1 - int(8 * z), right, line1 + int(8 * z), outline=col, width=1)
            self.create_text(right - gw / 2, line1, text=grade, font=f["small"], fill=col)
            right -= gw + int(6 * z)
        x = tx
        if r.get("name") and r.get("refine"):
            ref = "+%d " % r["refine"]
            self.create_text(x, line1, anchor="w", text=ref, font=f["head"], fill=c["accent"])
            x += f["head"].measure(ref)
            name = r["name"]
        else:
            name = item_title(r)
        self.create_text(x, line1, anchor="w", text=fit(f["text"], name, right - x), font=f["text"], fill=c["fg"])
        extras = item_extras(r)
        sub = _(slot) + ((" · " + ", ".join(extras)) if extras else "")
        if r.get("opts"):
            sub += " · " + (_("%d opções") % len(r["opts"]) if len(r["opts"]) > 1 else r["opts"][0])
        self.create_text(tx, line2, anchor="w", text=fit(f["small"], sub, x1 - int(8 * z) - tx), font=f["small"],
                         fill=c["muted"])
        self.boxes.append((x0, y0, x1, y1, r))

    def _motion(self, e):
        for x0, y0, x1, y1, r in self.boxes:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                if r.get("item_id") or r.get("item"):
                    self.tip.show(id(r), e.x_root, e.y_root, lambda fr, r=r: self._fill_tip(fr, r))
                    return
        self.tip.hide()

    def _fill_tip(self, frame, r):
        win, c = self.win, self.win.c

        def lbl(text, font="text", color="fg", **kw):
            w = tk.Label(frame, text=text, font=win.f[font], fg=c[color] if color in c else color, bg=c["tip"],
                         anchor="w", justify="left", **kw)
            w.pack(fill="x", anchor="w")
            return w
        lbl(_(r["slot"]).upper(), "small", "muted")
        title = item_title(r)
        lbl(title + ((_(" · grau %s") % r["grade"]) if r.get("grade") else ""), "head", wraplength=int(420 * win.dpi))
        cards = r.get("cards") or []
        if cards:
            lbl(_("Cartas e encantamentos").upper(), "small", "muted", pady=3)
            for cid in cards:
                row = tk.Frame(frame, bg=c["tip"])
                row.pack(fill="x", anchor="w")
                img = self.icons.get(cid)
                if img is not None:
                    tk.Label(row, image=img, bg=c["tip"]).pack(side="left")
                tk.Label(row, text=meter.item_name(cid), font=win.f["text"], fg=c["fg"], bg=c["tip"],
                         anchor="w").pack(side="left", padx=(4, 0))
        if r.get("opts"):
            lbl(_("Opções").upper(), "small", "muted", pady=3)
            for o in r["opts"]:
                lbl(o)
        if not r.get("name") and r.get("item") and (" (" in r["item"] or " · " in r["item"]):
            lbl(r["item"], "small", "muted", wraplength=int(420 * win.dpi))   # teste antigo: o texto que foi salvo


class SpriteView(tk.Canvas):
    """O desenho de um monstro, animado (parado, andando ou atacando), dentro de uma caixa. Enquanto o jogo é
    lido mostra "carregando"; sem o sprite, só o nome."""

    def __init__(self, parent, win, w=170, h=150, bg="tile"):
        z = win.dpi * win.zoom
        super().__init__(parent, width=int(w * z), height=int(h * z), bg=win.c[bg], highlightthickness=0, bd=0)
        self.win = win
        self.bg = bg
        self.mob = None
        self.action = sprites.MOB_IDLE
        self.label = ""
        self.frame = 0
        self.photos = {}              # (monstro, ação, largura, altura) -> ([imagens], ms por quadro)
        self.layers, self.layers_of = {}, None   # as imagens do .spr do monstro à vista, já convertidas
        self._after = None
        self._tries = 0
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Destroy>", lambda e: self._cancel())

    def set(self, mob, label="", action=None):
        """Mostra o monstro `mob` (id da classe); None limpa."""
        if action is None:
            action = self.action
        if (mob, action, label) == (self.mob, self.action, self.label):
            return
        self.mob, self.action, self.label = mob, action, label
        self.frame = 0
        self._tries = 0
        self.draw()

    def _cancel(self):
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _frames(self, W, H):
        """([imagens], ms por quadro) da ação do monstro para este tamanho de caixa. O bestiário já está aberto:
        ler o sprite do data.grf e montar os quadros leva alguns centésimos de segundo, na hora."""
        box = (max(8, W - 12), max(8, H - 16))
        key = (self.mob, self.action) + box
        if key in self.photos:
            return self.photos[key]
        got = ([], 100.0)
        part = sprites.MONSTERS.book.part(self.mob)
        if part is not None:
            if len(self.photos) > 12 or self.layers_of != self.mob:
                self.photos, self.layers, self.layers_of = {}, {}, self.mob
            try:
                made = mob_frames(self.win.top, part, self.action, 0, box[0], box[1], self.layers)
                if made is None and self.action != sprites.MOB_IDLE:      # monstro sem essa ação: fica parado
                    made = mob_frames(self.win.top, part, sprites.MOB_IDLE, 0, box[0], box[1], self.layers)
                got = made or got
            except (tk.TclError, ValueError, IndexError, KeyError, struct.error):
                got = ([], 100.0)                  # sprite estranho: fica só o nome
        self.photos[key] = got
        return got

    def draw(self):
        self._cancel()
        c, f = self.win.c, self.win.f
        self.delete("all")
        W, H = self.winfo_width(), self.winfo_height()
        if W <= 2 or H <= 2:
            W, H = int(self["width"]), int(self["height"])
        if self.mob is None:
            return

        def name_only():
            self.create_text(W / 2, H / 2, text=self.label or _("sem desenho"), fill=c["muted"], font=f["small"],
                             width=W - 10, justify="center")
        book = sprites.MONSTERS.book
        if book is None:                           # o índice do data.grf ainda está sendo lido (em outra thread)
            start_loaders()
            if sprites.MONSTERS.error is not None or not clientdata.NAMES.grf or self._tries > 120:
                name_only()
                return
            self._tries += 1
            self.create_text(W / 2, H / 2, text=_("carregando…"), fill=c["muted"], font=f["small"])
            self._after = self.after(200, self.draw)
            return
        if not book.has(self.mob):
            name_only()
            return
        shots, delay = self._frames(W, H)
        if not shots:
            name_only()
            return
        foot = H - 8
        self.create_oval(W / 2 - W * 0.28, foot - 7, W / 2 + W * 0.28, foot + 3,
                         fill=mix(self.win.c[self.bg], "#000000", 0.30), outline="")
        self.create_image(W / 2, foot, anchor="s", image=shots[self.frame % len(shots)])
        if len(shots) > 1:
            self._after = self.after(int(delay), self._tick)

    def _tick(self):
        self._after = None
        try:
            if not self.winfo_viewable():
                self._after = self.after(500, self._tick)     # aba escondida: espera sem desenhar
                return
        except tk.TclError:
            return
        self.frame += 1
        self.draw()


class Butterfly(tk.Canvas):
    """Comparação lado a lado: o nome de cada medida no meio, o valor de A à esquerda e o de B à direita, com uma
    barra de cada lado crescendo a partir do centro. O lado melhor fica em verde, com a diferença em %.

    Linhas: dict(kind="head", name=título) ou dict(name, a, b, a_txt, b_txt, better="high" | "low" | None)."""

    def __init__(self, parent, win, bg="panel"):
        super().__init__(parent, bg=win.c[bg], highlightthickness=0, bd=0, height=10)
        self.win = win
        self.rows = []
        self._width = 0
        self.bind("<Configure>", self._resized)

    def set(self, rows):
        self.rows = rows
        self.redraw()

    def _resized(self, e):
        if e.width != self._width:
            self._width = e.width
            self.redraw()

    def redraw(self):
        win, c, f = self.win, self.win.c, self.win.f
        z = win.dpi * win.zoom
        self.delete("all")
        W = max(self.winfo_width(), int(200 * z))
        rh = int(26 * z)
        names = [r["name"] for r in self.rows if r.get("kind") != "head"]
        mid_w = min(int(W * 0.34), max([f["small"].measure(n) for n in names] + [int(90 * z)]) + int(18 * z))
        cx = W / 2
        lx, rx = cx - mid_w / 2, cx + mid_w / 2          # onde as barras começam, de cada lado
        side_w = lx - int(8 * z)
        y = int(4 * z)
        for r in self.rows:
            if r.get("kind") == "head":
                y += int(6 * z)
                self.create_line(int(8 * z), y + rh / 2, W - int(8 * z), y + rh / 2, fill=c["grid"])
                tw = f["head"].measure(r["name"]) + int(16 * z)
                self.create_rectangle(cx - tw / 2, y + 2, cx + tw / 2, y + rh - 2, fill=c["panel"], outline="")
                self.create_text(cx, y + rh / 2, text=r["name"], font=f["head"], fill=c["fg"])
                y += rh
                continue
            a, b = r.get("a"), r.get("b")
            better = r.get("better")
            win_a = win_b = False
            if (better and isinstance(a, (int, float)) and isinstance(b, (int, float)) and a != b
                    and r.get("a_txt") != r.get("b_txt")):
                win_a = (a > b) if better == "high" else (a < b)
                win_b = not win_a
            top = max(abs(a) if isinstance(a, (int, float)) else 0, abs(b) if isinstance(b, (int, float)) else 0)
            self.create_text(cx, y + rh / 2, text=fit(f["small"], r["name"], mid_w - int(6 * z)), font=f["small"],
                             fill=c["muted"])
            for side, val, txt, won in ((-1, a, r.get("a_txt"), win_a), (1, b, r.get("b_txt"), win_b)):
                x0 = lx if side < 0 else rx
                if top and isinstance(val, (int, float)) and r.get("bar", True):
                    bw = (side_w - int(4 * z)) * abs(val) / top
                    col = mix(c["panel"], c["good"] if won else c["accent"], 0.30 if won else 0.16)
                    self.create_rectangle(x0, y + int(4 * z), x0 + side * bw, y + rh - int(4 * z), fill=col, outline="")
                text = txt if txt is not None else "—"
                if won and isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    other = b if side < 0 else a
                    if other:
                        text += "  " + dec("%+.1f%%" % ((val - other) * 100.0 / abs(other)))
                self.create_text(x0 + side * int(8 * z), y + rh / 2, anchor="e" if side < 0 else "w",
                                 text=fit(f["text"], text, side_w - int(12 * z)),
                                 font=f["head"] if won else f["text"], fill=c["good"] if won else c["fg"])
            y += rh
        self.configure(height=max(10, y + int(6 * z)))


class AlertList(tk.Frame):
    """Lista de alertas em cartões (Dedo Duro): faixa na cor da gravidade, o quê em destaque, quem e o detalhe
    inteiro, quebrado em linhas (numa tabela o detalhe ficava cortado). Rola com a roda do mouse."""

    SEV = {2: ("bad", "GRAVE"), 1: ("mid", "ATENÇÃO"), 0: ("muted", "INFO")}

    def __init__(self, parent, win, bg="panel"):
        super().__init__(parent, bg=win.c[bg])
        self.win = win
        self.rows = []
        self.cv = tk.Canvas(self, bg=win.c[bg], highlightthickness=0, bd=0, height=int(250 * win.dpi))
        from tkinter import ttk
        sb = ttk.Scrollbar(self, orient="vertical", command=self.cv.yview, style="An.Vertical.TScrollbar")
        self.cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.cv.pack(side="left", fill="both", expand=True)
        self._width = 0
        self.cv.bind("<Configure>", self._resized)
        self.cv.bind("<Enter>", lambda e: self.cv.bind_all("<MouseWheel>", self._wheel))
        self.cv.bind("<Leave>", lambda e: self.cv.unbind_all("<MouseWheel>"))

    def set(self, rows):
        sig = [(r.get("key"), r.get("sev"), r.get("who"), r.get("detail")) for r in rows]
        if sig == getattr(self, "_sig", None) and self._width == self.cv.winfo_width():
            return
        self._sig = sig
        self.rows = rows
        self.redraw()

    def _resized(self, e):
        if e.width != self._width:
            self._width = e.width
            self.redraw()

    def _wheel(self, e):
        if e.state & 0x4:
            return
        self.cv.yview_scroll(-2 if e.delta > 0 else 2, "units")

    def redraw(self):
        win, c, f, cv = self.win, self.win.c, self.win.f, self.cv
        z = win.dpi * win.zoom
        cv.delete("all")
        W = max(cv.winfo_width(), int(200 * z))
        self._width = cv.winfo_width()
        pad = int(8 * z)
        y = int(2 * z)
        if not self.rows:
            cv.create_text(pad, y + int(14 * z), anchor="w", fill=c["muted"], font=f["text"],
                           text=_("Nada a apontar aqui."))
            y += int(30 * z)
        for r in self.rows:
            color_key, tag = self.SEV.get(r.get("sev"), self.SEV[0])
            col = c[color_key]
            x = int(4 * z) + int(5 * z) + pad
            top = y
            ty = y + int(7 * z)
            badge = _(tag)
            cv.create_text(x, ty, anchor="nw", text=badge, font=f["small"], fill=col)
            bx = x + f["small"].measure(badge) + int(10 * z)
            if r.get("phase"):
                cv.create_text(bx, ty, anchor="nw", text=r["phase"], font=f["small"], fill=c["muted"])
                bx += f["small"].measure(r["phase"]) + int(12 * z)
            cv.create_text(bx, ty - int(1 * z), anchor="nw", text=fit(f["head"], r.get("what") or "", W - bx - pad),
                           font=f["head"], fill=c["fg"])
            ty += f["head"].metrics("linespace") + int(3 * z)
            for text, font, fill in ((r.get("who"), f["text"], c["fg"]), (r.get("detail"), f["small"], c["muted"])):
                if not text:
                    continue
                item = cv.create_text(x, ty, anchor="nw", text=text, font=font, fill=fill, width=W - x - pad)
                ty = cv.bbox(item)[3] + int(2 * z)
            bottom = ty + int(5 * z)
            back = cv.create_rectangle(int(4 * z), top, W - int(2 * z), bottom, fill=c["tile"], outline="")
            cv.tag_lower(back)
            cv.create_rectangle(int(4 * z), top, int(4 * z) + int(5 * z), bottom, fill=col, outline="")
            y = bottom + int(5 * z)
        cv.configure(scrollregion=(0, 0, W, y + 2))
        cv.yview_moveto(0)
