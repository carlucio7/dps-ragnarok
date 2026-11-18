# -*- coding: utf-8 -*-
"""Aba "Visuais" da análise: simulador de visuais montado com os sprites do jogo instalado.

Começa do personagem que gravou o replay (classe, sexo, cabelo, cores e o que ele vestia) e deixa trocar tudo
olhando: cada visual, cada cabelo e cada cor aparece como uma miniatura desenhada no próprio personagem. O catálogo
é lido do jogo (visuals.Catalog), então visual novo aparece sozinho. Os looks podem ser guardados e copiados como
imagem.
"""

import copy
import os
import time
import tkinter as tk
from tkinter import simpledialog, ttk

import clientdata
import gamecache
import gdip
import ground
import meter
import sprites
import streffect
import visuals
from i18n import _

SEXES = [(0, "Feminino"), (1, "Masculino")]
REPLAY = "Personagem do replay"
CW, CH = 220, 240             # tamanho da prévia, em pixels do jogo (alguns visuais são enormes)
SEARCH_MS = 180               # espera depois da última tecla para refazer a grade da busca
# o que dá para escolher na grade: (chave, nome, célula da miniatura (l, a), com o corpo?)
ICON_KEYS = ("top", "mid", "low")     # nestas a célula mostra o desenho do chapéu sozinho, o mesmo da animação (a
#                                       cabeça do personagem escondia visuais como as piscadelas; o ícone de 24 px
#                                       ampliado ficava pixelado); os minúsculos e os sem desenho mostram o ícone
CATEGORIES = [("top", "Topo", (76, 76), False), ("mid", "Meio", (76, 76), False), ("low", "Baixo", (76, 76), False),
              ("robe", "Capa", (76, 104), True), ("hair", "Cabelo", (76, 76), False),
              ("hair_color", "Cor do cabelo", (76, 76), False), ("cloth_color", "Cor da roupa", (76, 104), True),
              ("effects", "Pedras e efeitos", (178, 50), False)]
NO_GROUND, GRID = "Nenhum", "Grade de células"
SHADOW_AT = (14, -26)         # onde a cópia da pedra Sombra fica em relação ao personagem (pixels do jogo)
SLOT_KEYS = tuple(k for k, _n in visuals.SLOTS)
WORK_S = 0.012                # quanto tempo por vez o programa gasta desenhando miniaturas (a janela segue leve)
MAX_THUMBS = 1500             # miniaturas guardadas; passou disso, recomeça
# o chão, os efeitos e os ícones leem pastas que ficam quase todas dentro de data\texture\: um índice só do
# data.grf para os três (cada índice separado era uma passada a mais pela tabela do jogo, com a janela esperando)
VIS_PREFIXES = ground.PREFIXES + streffect.PREFIXES + (sprites.ITEM_ICON, sprites.ITEM_ART)


class ThumbGrid:
    """Grade de miniaturas com rolagem: só desenha as células à vista e faz as miniaturas aos poucos."""

    def __init__(self, parent, win, make, on_pick, on_hover):
        self.win, self.make, self.on_pick, self.on_hover = win, make, on_pick, on_hover
        c = win.c
        self.canvas = tk.Canvas(parent, bg=c["btn"], highlightthickness=0, bd=0, cursor="hand2")
        self.bar = ttk.Scrollbar(parent, orient="vertical", command=self.scroll, style="An.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.items, self.cell, self.selected = [], (76, 76), None
        self.images = {}              # chave da miniatura -> PhotoImage (None = não há o que desenhar)
        self.queue, self.after, self.cols, self.hover = [], None, 1, None
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<Motion>", self.motion)
        self.canvas.bind("<Leave>", lambda e: self.set_hover(None))

    def set(self, items, cell, selected=None, keep_scroll=False):
        """items: [dict(key=chave da miniatura, name=..., value=...)]. `selected`: o `value` marcado."""
        self.items, self.cell, self.selected = items, cell, selected
        self.queue = []
        if not keep_scroll:
            self.canvas.yview_moveto(0)
        self.redraw()

    def scroll(self, *args):
        self.canvas.yview(*args)
        self.redraw()

    def wheel(self, e):
        self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        self.redraw()
        return "break"

    def index_at(self, e):
        cw, ch = self.cell
        x, y = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        col, row = int(x // cw), int(y // ch)
        i = row * self.cols + col
        return i if 0 <= col < self.cols and 0 <= i < len(self.items) else None

    def click(self, e):
        i = self.index_at(e)
        if i is not None:
            self.on_pick(self.items[i])

    def motion(self, e):
        self.set_hover(self.index_at(e))

    def set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.on_hover(self.items[i] if i is not None and i < len(self.items) else None)

    def redraw(self):
        cv, c = self.canvas, self.win.c
        cw, ch = self.cell
        width, height = max(1, cv.winfo_width()), max(1, cv.winfo_height())
        self.cols = max(1, width // cw)
        rows = (len(self.items) + self.cols - 1) // self.cols
        cv.configure(scrollregion=(0, 0, width, max(height, rows * ch)), yscrollincrement=ch // 2)
        cv.delete("all")
        top = cv.canvasy(0)
        first, last = max(0, int(top // ch)), int((top + height) // ch) + 1
        want = []
        for row in range(first, min(rows, last)):
            for col in range(self.cols):
                i = row * self.cols + col
                if i >= len(self.items):
                    break
                it = self.items[i]
                x, y = col * cw, row * ch
                chosen = (it["value"] in self.selected if isinstance(self.selected, (list, tuple, set))
                          else it["value"] == self.selected)
                cv.create_rectangle(x + 2, y + 2, x + cw - 2, y + ch - 2, fill=c["tile"],
                                    outline=c["accent"] if chosen else c["tile"], width=2 if chosen else 1)
                if it.get("text"):                # célula só de texto (efeitos: desenhar todos custaria caro)
                    cv.create_text(x + 8, y + ch / 2, text=it["text"], anchor="w", width=cw - 14,
                                   fill=c["fg"], font=self.win.f["small"])
                elif it["key"] in self.images:
                    img = self.images[it["key"]]
                    if img is not None:
                        cv.create_image(x + cw / 2, y + ch / 2, image=img)
                    else:
                        cv.create_text(x + cw / 2, y + ch / 2, text="—", fill=c["muted"], font=self.win.f["small"])
                else:
                    cv.create_text(x + cw / 2, y + ch / 2, text="…", fill=c["muted"], font=self.win.f["small"])
                    want.append(it["key"])
                if it.get("label"):
                    cv.create_text(x + 6, y + 5, text=it["label"], anchor="nw", fill=c["muted"],
                                   font=self.win.f["small"])
        self.queue = want
        if want and self.after is None:
            self.schedule()

    def schedule(self):
        """A próxima leva de miniaturas só depois que o Tk redesenhar a tela. Ele desenha nas tarefas ociosas, que não
        rodam enquanto houver um after vencido: com after(1) direto as levas emendavam e a aba só aparecia (e a
        janela só se redesenhava) com todas as miniaturas prontas."""
        def soon():
            try:
                self.after = self.win.top.after(1, self.work)
            except tk.TclError:                   # janela fechada nesse meio-tempo
                self.after = None
        self.after = self.win.top.after_idle(soon)

    def work(self):
        """Faz as miniaturas que faltam das células à vista, um pouco por vez."""
        self.after = None
        end = time.monotonic() + WORK_S
        done = False
        while self.queue and time.monotonic() < end:
            key = self.queue.pop(0)
            if key not in self.images:
                if len(self.images) > MAX_THUMBS:
                    self.images = {}
                self.images[key] = self.make(key, self.cell)
                done = True
        if done:
            self.redraw()                 # redesenha e põe na fila o que ainda falta
        elif self.queue:
            self.schedule()


class VisualsTab:
    def __init__(self, win, nb):
        self.win = win
        c = win.c
        tab = tk.Frame(nb, bg=c["panel"])
        nb.add(tab, text=_("Visuais"))
        self.tab = tab
        self.look = dict(visuals.DEFAULT_LOOK)
        self.history = visuals.History()   # o Desfazer: o estado depois de cada passo
        self.items = {}               # posição -> item escolhido (para mostrar o nome certo)
        self.held = {}                # posição -> (item, desenho, nome) do visual de várias posições que a ocupa
        self.icons = None             # os ícones dos itens no data.grf (aberto na primeira vez)
        self.icon_art = {}            # item -> nome do desenho dele (iteminfo do jogo)
        self.vis = None               # o índice do data.grf do chão, dos efeitos e dos ícones (vis_grf)
        self.base_id = None          # o replay de onde veio o look de partida
        self.touched = False          # a pessoa já mexeu no look? (replay novo só troca o look se não mexeu)
        self.catalog = None
        self.jobs = {}                # nome da classe -> id
        self.images, self.frame, self.n, self.dir, self.after = {}, 0, 1, 0, None
        self.search_after = None
        self.scale = max(2, int(round(2 * win.dpi)))
        self.fx = None                # streffect.HatEffects, aberto quando alguém usa um efeito
        self.fx_names = {}            # efeito -> nome para mostrar
        self.t0 = time.monotonic()    # começo da animação (o quadro do personagem e o dos efeitos saem do relógio)
        self.delay = 100.0
        self.speed = None             # velocidade de andar do personagem do replay (a da pose "Andando (rápido)")
        self.extents = {}             # (look, pose, direção, cabeça) -> retângulo de todos os quadros (pés fixos)
        self.fx_photos = []           # as imagens dos efeitos à vista (o Tk precisa que alguém as segure)
        self.ground = None            # ground.Ground, aberto quando a prévia pede um terreno
        self.ground_img = (None, None)   # (o que foi pedido, a imagem do chão)

        bar = tk.Frame(tab, bg=c["panel"])
        bar.pack(fill="x", padx=10, pady=(8, 2))
        win.label(bar, _("Look:"), color="muted", bg="panel").pack(side="left")
        self.saved = tk.StringVar(win.top, _(REPLAY))
        self.saved_box = ttk.Combobox(bar, textvariable=self.saved, width=30, state="readonly", style="An.TCombobox",
                                      font=win.f["text"])
        self.saved_box.pack(side="left", padx=6)
        self.saved_box.bind("<<ComboboxSelected>>", lambda e: self.pick_saved())
        self.undo_btn = ttk.Button(bar, text=_("↶ Desfazer"), style="An.TButton", command=self.undo)
        self.undo_btn.pack(side="left")
        ttk.Button(bar, text=_("Original do replay"), style="An.TButton",
                   command=self.reset_look).pack(side="left", padx=(6, 12))
        ttk.Button(bar, text=_("Salvar look…"), style="An.TButton", command=self.save_look).pack(side="left")
        ttk.Button(bar, text=_("Excluir"), style="An.TButton", command=self.delete_look).pack(side="left", padx=6)
        ttk.Button(bar, text=_("Copiar imagem"), style="An.TButton",
                   command=lambda: win.copy_image(self.canvas)).pack(side="left")
        # cabelo, cores, direção e o que faltou no jogo: numa linha própria (na barra, com Desfazer e Original do
        # replay, era cortado na largura padrão da janela)
        self.info = win.label(tab, "", "small", "muted", "panel", anchor="w")
        self.info.pack(fill="x", padx=12, pady=(0, 2))

        body = tk.Frame(tab, bg=c["panel"])
        body.pack(fill="both", expand=True, padx=6, pady=(2, 8))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        # prévia à esquerda, com pose e direção em cima (embaixo ficariam fora da janela no tamanho padrão)
        left = tk.Frame(body, bg=c["tile"])
        left.grid(row=0, column=0, sticky="n", padx=(4, 8), pady=4)
        sc = self.scale
        ctr = tk.Frame(left, bg=c["tile"])
        ctr.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Button(ctr, text="⟲", width=3, style="An.TButton", command=lambda: self.turn(1)).pack(side="left")
        ttk.Button(ctr, text="⟳", width=3, style="An.TButton",
                   command=lambda: self.turn(-1)).pack(side="left", padx=(4, 0))
        self.action = tk.StringVar(win.top, _("Parado"))
        box = ttk.Combobox(ctr, textvariable=self.action, values=[_(n) for _a, n in sprites.ACTIONS], width=17,
                           state="readonly", style="An.TCombobox", font=win.f["text"])
        box.pack(side="left", padx=(8, 0))
        box.bind("<<ComboboxSelected>>", lambda e: self.restart())
        win.label(ctr, _("Cabeça:"), color="muted", bg="tile").pack(side="left", padx=(10, 0))
        self.head = tk.StringVar(win.top, _("Frente"))
        box = ttk.Combobox(ctr, textvariable=self.head, values=[_(n) for _h, n in sprites.HEAD_DIRS], width=9,
                           state="readonly", style="An.TCombobox", font=win.f["text"])
        box.pack(side="left", padx=(6, 0))
        box.bind("<<ComboboxSelected>>", lambda e: self.restart())
        row2 = tk.Frame(left, bg=c["tile"])
        row2.pack(fill="x", padx=10, pady=(2, 0))
        win.label(row2, _("Chão:"), color="muted", bg="tile").pack(side="left")
        self.floor = tk.StringVar(win.top, win.app.cfg.get("vis_ground") or "")
        self.floor_box = ttk.Combobox(row2, textvariable=self.floor, width=22, state="readonly",
                                      style="An.TCombobox", font=win.f["text"], values=[_(NO_GROUND), _(GRID)])
        self.floor_box.pack(side="left", padx=(6, 0))
        self.floor_box.bind("<<ComboboxSelected>>", lambda e: self.floor_changed())
        self.canvas = tk.Canvas(left, width=CW * sc, height=CH * sc, bg=c["tile"], highlightthickness=0, bd=0,
                                cursor="hand2")
        self.canvas.pack(padx=10, pady=(4, 8))
        self.canvas.bind("<Button-1>", lambda e: self.turn(1 if e.x < self.canvas.winfo_width() / 2 else -1))

        # à direita: quem é o personagem, o que ele veste e a grade de miniaturas do que dá para trocar
        right = tk.Frame(body, bg=c["panel"])
        right.grid(row=0, column=1, sticky="nsew", pady=4)
        who = tk.Frame(right, bg=c["tile"])
        who.pack(fill="x", padx=(0, 4))
        row = tk.Frame(who, bg=c["tile"])
        row.pack(fill="x", padx=10, pady=(8, 4))
        win.label(row, _("Classe:"), color="muted", bg="tile").pack(side="left")
        self.job = tk.StringVar(win.top, "")
        self.job_box = ttk.Combobox(row, textvariable=self.job, width=26, state="readonly", style="An.TCombobox",
                                    font=win.f["text"])
        self.job_box.pack(side="left", padx=(6, 14))
        self.job_box.bind("<<ComboboxSelected>>", lambda e: self.changed())
        win.label(row, _("Sexo:"), color="muted", bg="tile").pack(side="left")
        self.sex = tk.StringVar(win.top, _("Masculino"))
        box = ttk.Combobox(row, textvariable=self.sex, values=[_(n) for _s, n in SEXES], width=11, state="readonly",
                           style="An.TCombobox", font=win.f["text"])
        box.pack(side="left", padx=(6, 0))
        box.bind("<<ComboboxSelected>>", lambda e: self.changed())
        # o que está em cada posição, com o botão de tirar
        worn = tk.Frame(who, bg=c["tile"])
        worn.pack(fill="x", padx=10, pady=(0, 8))
        self.slot = {}
        for i, (key, name) in enumerate(visuals.SLOTS):
            cell = tk.Frame(worn, bg=c["tile"])
            cell.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 12), pady=1)
            worn.columnconfigure(i % 2, weight=1, uniform="worn")
            win.label(cell, _(name) + ":", color="muted", bg="tile").pack(side="left")
            ttk.Button(cell, text="✕", style="An.TButton", width=2,
                       command=lambda k=key: self.pick(k, None)).pack(side="right")
            cur = win.label(cell, "", "text", "accent", "tile", anchor="w", cursor="hand2")
            cur.pack(side="left", padx=(6, 4), fill="x", expand=True)
            cur.bind("<Button-1>", lambda e, k=key: self.set_category(k))
            self.slot[key] = dict(cur=cur)
        cell = tk.Frame(worn, bg=c["tile"])
        cell.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(0, 12), pady=1)
        win.label(cell, _("Efeitos:"), color="muted", bg="tile").pack(side="left")
        ttk.Button(cell, text="✕", style="An.TButton", width=2, command=self.clear_effects).pack(side="right")
        self.fx_lbl = win.label(cell, _("nada"), "text", "accent", "tile", anchor="w", cursor="hand2")
        self.fx_lbl.pack(side="left", padx=(6, 4), fill="x", expand=True)
        self.fx_lbl.bind("<Button-1>", lambda e: self.set_category("effects"))
        # categorias da grade
        cats = tk.Frame(right, bg=c["panel"])
        cats.pack(fill="x", pady=(8, 2))
        self.category = tk.StringVar(win.top, "top")
        for key, name, _cell, _body in CATEGORIES:
            tk.Radiobutton(cats, text=_(name), value=key, variable=self.category, indicatoron=0,
                           command=self.show_category, font=win.f["text"], bg=c["btn"], fg=c["fg"],
                           selectcolor=c["accent"], activebackground=c["btn"], activeforeground=c["fg"],
                           relief="flat", bd=0, padx=9, pady=3, highlightthickness=0).pack(side="left", padx=(0, 4))
        find = tk.Frame(right, bg=c["panel"])
        find.pack(fill="x", pady=(4, 4))
        self.find_lbl = win.label(find, _("Buscar:"), "small", "muted", "panel")
        self.find_lbl.pack(side="left")
        self.query = tk.StringVar(win.top, "")
        self.find_ent = tk.Entry(find, textvariable=self.query, font=win.f["text"], bg=c["btn"], fg=c["fg"], width=28,
                                 insertbackground=c["fg"], relief="flat", highlightthickness=1,
                                 highlightbackground=c["track"], highlightcolor=c["accent"],
                                 disabledbackground=c["panel"], disabledforeground=c["muted"])
        self.find_ent.pack(side="left", padx=(6, 10), ipady=2)
        self.win.trace(self.query, lambda *_a: self.search_soon())
        self.count = win.label(find, "", "small", "muted", "panel", anchor="w")
        self.count.pack(side="left", fill="x", expand=True)
        self.count_text = ""
        holder = tk.Frame(right, bg=c["panel"])
        holder.pack(fill="both", expand=True, padx=(0, 4))
        self.grid = ThumbGrid(holder, win, self.thumb, self.chosen, self.hovered)
        self.history.reset(self.snapshot())
        self.show_undo()

    # ------------------------------------------------------------ dados

    def replay_look(self, c):
        """O visual de quem gravou, no começo da gravação (com o que ele vestia, se o replay trouxe)."""
        if c is None:
            return dict(visuals.DEFAULT_LOOK)
        w = sprites.LOADER.wardrobe
        worn = c.worn_at(0)
        look = sprites.look_at(c.session.look, worn, w.classnum) if (w and worn) else dict(c.session.look)
        return visuals.clean(look)

    def ensure_catalog(self, w):
        if self.catalog is not None or w is None:
            return
        try:
            info = gamecache.items(os.path.join(os.path.dirname(w.grf.path), "System", "iteminfo_new.lub"))
            slots = info.get("slots") or {}
        except (OSError, ValueError, KeyError, IndexError, AttributeError):
            slots = {}
        self.catalog = visuals.Catalog(slots, w.classnum, w.acc, w.robe, meter.item_name)
        names = {}
        for job in sorted(sprites.JOB_SPRITE):
            name = meter.job_name(job)
            if name and name not in names:
                names[name] = job
        self.jobs = names
        self.job_box["values"] = sorted(names)
        self.show_category()

    def refresh(self, c):
        """Chamado quando a aba fica à vista ou o replay muda."""
        grf = clientdata.NAMES.grf
        sprites.LOADER.start(grf)
        # "Andando (rápido)" anda na velocidade do personagem do replay quando ele tinha acréscimo
        self.speed = c.session.stats.get("speed") if c is not None else None
        ident = id(c) if c is not None else 0
        ready = sprites.LOADER.wardrobe is not None
        if (ident, ready) != self.base_id and not self.touched:
            # replay novo (ou as tabelas do jogo ficaram prontas): parte de novo do personagem do replay
            self.base_id = (ident, ready)
            self.set_look(self.replay_look(c), mark=False)
            self.history.reset(self.snapshot())        # nada para desfazer: o look mudou sozinho
            self.show_undo()
        names = [_(REPLAY)] + sorted(visuals.saved_looks(self.win.app.cfg))
        if list(self.saved_box["values"]) != names:
            self.saved_box["values"] = names
        self.draw()

    def set_look(self, look, mark=True):
        self.look = visuals.clean(look)
        self.items = {}
        self.held = {}
        self.touched = mark
        self.images, self.frame, self.extents = {}, 0, {}
        self.show_look()
        self.show_category(keep_scroll=True)

    def show_look(self):
        """Põe o look atual nos controles (classe, sexo e o nome do que está em cada posição)."""
        look = self.look
        self.job.set(meter.job_name(look["job"]) or str(look["job"]))
        self.sex.set(_(dict(SEXES).get(look["sex"], "Masculino")))
        for key in SLOT_KEYS:
            self.show_slot(key)
        self.show_effects()

    def vis_grf(self, path):
        """O índice do data.grf que o chão, os efeitos e os ícones dividem (aberto na primeira vez que um deles pede).
        None se o arquivo não abrir: aí cada um tenta o seu (e cai no que já fazia quando falha)."""
        if self.vis is None:
            try:
                self.vis = sprites.Grf(path, prefixes=VIS_PREFIXES)
            except Exception:  # noqa: BLE001 - .grf estranho ou que sumiu
                self.vis = False
        return self.vis or None

    def grounds(self):
        """Os terrenos do jogo (aberto na primeira vez); a caixa "Chão" ganha os nomes deles."""
        w = sprites.LOADER.wardrobe
        if self.ground is None and w is not None:
            try:
                self.ground = ground.Ground(w.grf.path, self.vis_grf(w.grf.path))
            except (OSError, ValueError, KeyError, IndexError):
                self.ground = False
            names = [n for n, _m, _c in self.ground.places()] if self.ground else []
            self.floor_box["values"] = [_(NO_GROUND), _(GRID)] + names
            if self.floor.get() not in self.floor_box["values"]:
                self.floor.set(names[0] if names else _(GRID))
        return self.ground or None

    def floor_changed(self):
        self.win.app.cfg["vis_ground"] = self.floor.get()
        self.win.app.save()
        self.draw()

    def draw_floor(self, W, H, fx, fy):
        """O chão debaixo do personagem: a grade de células ou o terreno do mapa escolhido, em perspectiva."""
        cv, col, sc = self.canvas, self.win.c, self.scale
        choice = self.floor.get()
        if choice == _(NO_GROUND):
            return
        g = self.grounds()
        place = next((pl for pl in (g.places() if g else []) if pl[0] == choice), None)
        if place is not None:
            want = (place[1], W, H, int(fx), int(fy), sc)
            if self.ground_img[0] != want:
                photo = None
                data = g.render(place[1], place[2], W, H, (fx, fy), sc)
                if data:
                    try:
                        photo = tk.PhotoImage(master=self.win.top, format="png", data=streffect.base64.b64encode(
                            sprites.png_rgba(W, H, gdip.swap_rb(data))).decode("ascii"))
                    except tk.TclError:
                        photo = None
                self.ground_img = (want, photo)
            if self.ground_img[1] is not None:
                cv.create_image(0, 0, image=self.ground_img[1], anchor="nw")
                return
        # grade: uma célula do jogo tem 35 px de largura e fica achatada como o chão
        cw, ch = ground.CELL * sc, ground.CELL * ground.SQUASH * sc
        line = _shade(col["tile"])
        x = fx - cw / 2.0
        while x > 0:
            x -= cw
        while x < W:
            cv.create_line(x, 0, x, H, fill=line)
            x += cw
        y = fy - ch / 2.0
        while y > 0:
            y -= ch
        while y < H:
            cv.create_line(0, y, W, y, fill=line)
            y += ch

    def effects(self):
        """A tabela de efeitos de chapéu do jogo (aberta na primeira vez) e os nomes para mostrar."""
        w = sprites.LOADER.wardrobe
        if self.fx is None and w is not None:
            try:
                self.fx = streffect.HatEffects(w.grf.path, self.vis_grf(w.grf.path))
            except (OSError, ValueError, KeyError, IndexError):
                self.fx = False
            names = {visuals.SHRINK: _("Miniatura (personagem pela metade)")}
            for item, key in visuals.STONES.items():
                if key in (visuals.PALE, visuals.SHADOW):
                    names[key] = meter.item_name(item)
            if self.fx:
                for item, key in visuals.STONES.items():
                    name = self.fx.find(key) if key not in visuals.SPECIAL else None
                    if name:
                        names[name] = meter.item_name(item)
                # os visuais "só de efeito" do jogo dão nome ao efeito que usam, quando o nome interno casa
                try:
                    info = gamecache.items(os.path.join(os.path.dirname(w.grf.path), "System", "iteminfo_new.lub"))
                    art, shown = info.get("art") or {}, info.get("display") or {}
                except (OSError, ValueError, KeyError, IndexError):
                    art, shown = {}, {}
                keys = {visuals.fx_key(n): n for n in self.fx.table}
                keys.update({visuals.fx_key(e["file"].rsplit("\\", 1)[-1].rsplit(".", 1)[0]): n
                             for n, e in self.fx.table.items()})
                for item in self.fx.effect_items():
                    res = art.get(item)
                    name = visuals.RESOURCE_FX.get(res) or keys.get(visuals.fx_key(res))
                    if name in self.fx.table and shown.get(item):
                        label = meter.item_name(item)
                        if label not in names.get(name, ""):
                            names[name] = (names[name] + " · " + label) if name in names else label
                for name, entry in self.fx.table.items():
                    names.setdefault(name, entry["name"].replace("_", " "))
            self.fx_names = names
        return self.fx or None

    def show_effects(self):
        on = self.look.get("effects") or []
        if on:
            self.effects()
        self.fx_lbl.configure(text=", ".join(self.fx_names.get(e, e) for e in on) if on else _("nada"))

    def clear_effects(self):
        if self.look.get("effects"):
            self.look["effects"] = []
            self.modified()
            self.show_effects()
            if self.category.get() == "effects":
                self.grid.selected = []
                self.grid.redraw()
            self.draw()

    def show_slot(self, key):
        view = self.look.get(key) or 0
        if key in self.held:                       # preso a um visual de várias posições: o nome dele
            text = self.held[key][2]
        elif not view:
            text = _("nada")
        else:
            name = self.catalog.name_of_view(key, view, self.items.get(key)) if self.catalog else None
            text = name or _("visual %d") % view
        self.slot[key]["cur"].configure(text=text)

    def modified(self):
        self.touched = True
        self.saved.set("")
        self.frame = 0
        self.t0 = time.monotonic()
        self.remember()

    # ------------------------------------------------------------ desfazer e voltar ao do replay

    def snapshot(self):
        """O estado do look para o Desfazer (cópias: o look é mexido no lugar)."""
        return (copy.deepcopy(self.look), dict(self.items), dict(self.held), self.saved.get())

    def remember(self):
        """Depois de um passo (vestir, tirar, classe, cabelo, cores, efeitos, look guardado): o de antes vai
        para o Desfazer."""
        self.history.record(self.snapshot())
        self.show_undo()

    def show_undo(self):
        try:
            self.undo_btn.state(["!disabled"] if self.history.can_undo() else ["disabled"])
        except (tk.TclError, AttributeError):
            pass

    def undo(self):
        """Desfaz o último passo."""
        state = self.history.undo()
        if state is None:
            return
        look, items, held, saved = state
        self.look, self.items, self.held = copy.deepcopy(look), dict(items), dict(held)
        self.touched = True
        self.saved.set(saved)
        self.frame, self.t0 = 0, time.monotonic()
        self.show_look()
        self.show_category(keep_scroll=True)
        self.show_undo()
        self.draw()

    def reset_look(self):
        """Volta ao visual do personagem do replay (o Desfazer traz de volta o que estava)."""
        c = self.win.combat()
        self.set_look(self.replay_look(c), mark=False)
        self.base_id = (id(c) if c is not None else 0, sprites.LOADER.wardrobe is not None)
        self.saved.set(_(REPLAY))
        self.remember()
        self.draw()

    def changed(self):
        """Classe ou sexo mudou."""
        look = dict(self.look)
        job = self.jobs.get(self.job.get())
        if job is not None:
            look["job"] = job
            look["option"] = 0
        look["sex"] = next((s for s, n in SEXES if _(n) == self.sex.get()), 1)
        if look != self.look:
            w = sprites.LOADER.wardrobe
            if w is not None:                      # cabelo e cores que a classe e o sexo novos não têm voltam ao padrão
                if look["hair"] not in w.hairs(look["job"], look["sex"]):
                    look["hair"] = 1
                if look["hair_color"] not in w.hair_colors(look["hair"], look["sex"]):
                    look["hair_color"] = 0
                if look["cloth_color"] not in w.cloth_colors(look["job"], look["sex"]):
                    look["cloth_color"] = 0
            self.look = visuals.clean(look)
            self.modified()
            self.show_look()
            self.show_category(keep_scroll=True)
            self.draw()

    def pick(self, key, row):
        """Escolhe o item de uma posição (None = tira). row = (nome, item, desenho)."""
        letters = self.catalog.letters.get(row[1], "") if (row and self.catalog) else ""
        changed = visuals.wear(self.look, self.items, self.held, key, row, letters) | {key} | set(self.held)
        self.modified()
        for k in changed:
            self.show_slot(k)
        if self.category.get() in SLOT_KEYS:
            self.grid.selected = self.worn(self.category.get())
            self.grid.redraw()
        self.draw()

    def worn(self, key):
        """O desenho que ocupa a posição (o do visual de várias posições, se ela estiver presa a um)."""
        return self.held[key][1] if key in self.held else self.look.get(key)

    # ------------------------------------------------------------ grade de miniaturas

    def set_category(self, key):
        self.category.set(key)
        self.show_category()

    def search_soon(self):
        top = self.win.top
        if self.search_after is not None:
            try:
                top.after_cancel(self.search_after)
            except tk.TclError:
                pass
        self.search_after = top.after(SEARCH_MS, self.show_category)

    def context(self):
        """O que do look muda o desenho das miniaturas (classe, sexo, cabelo e cores)."""
        k = self.look
        return (k["job"], k["sex"], k["hair"], k["hair_color"], k["cloth_color"])

    def show_category(self, keep_scroll=False):
        """Refaz a grade com a categoria escolhida e o que foi digitado na busca."""
        self.search_after = None
        w = sprites.LOADER.wardrobe
        if self.catalog is None or w is None:
            return
        key = self.category.get()
        name, cell, _body = next((n, cl, b) for k, n, cl, b in CATEGORIES if k == key)
        ctx, look = self.context(), self.look
        searchable = key in SLOT_KEYS or key == "effects"
        self.find_ent.configure(state="normal" if searchable else "disabled")
        if key == "effects":
            table = self.effects()
            words = visuals.fold(self.query.get()).split()
            stones = [n for n in ((table.find(k) if table else None) if k not in visuals.SPECIAL else k
                                  for k in visuals.STONES.values()) if n]
            rest = [n for n in (table.table if table else {}) if n not in stones]
            # depois das pedras, os efeitos que têm nome de visual, e por fim os que só têm o nome interno
            named = sorted((n for n in rest if self.fx_names.get(n) != table.table[n]["name"].replace("_", " ")),
                           key=lambda n: visuals.fold(self.fx_names.get(n, n)))
            order = list(dict.fromkeys(stones)) + named + sorted(n for n in rest if n not in named)
            items = []
            for n in order:
                label = self.fx_names.get(n, n)
                if not words or all(wd in visuals.fold(label) for wd in words):
                    items.append(dict(key=("fx", n), name=label, value=n, text=label))
            self.count_text = _("%d efeitos (as pedras primeiro; até %d ligados)") % (len(items), visuals.MAX_EFFECTS)
            self.count.configure(text=self.count_text)
            self.grid.set(items, tuple(int(v * self.win.dpi) for v in cell), list(look.get("effects") or []),
                          keep_scroll)
            return
        if searchable:
            text = self.query.get()
            rows = self.catalog.search(key, text, limit=100000)
            seen, items = set(), []
            for nm, item, view in rows:              # um desenho só aparece uma vez (vários itens usam o mesmo)
                if view in seen:
                    continue
                seen.add(view)
                # o desenho do chapéu muda com o sexo e com a raça (doram)
                cell_key = (("icon", item, view, look["sex"], look["job"] in sprites.DORAM_JOBS) if key in ICON_KEYS
                            else (key, view) + ctx)
                items.append(dict(key=cell_key, name=nm, value=view, row=(nm, item, view)))
            self.count_text = _("%d visuais") % len(items)
        elif key == "hair":
            items = [dict(key=("hair", n) + ctx, name=_("Cabelo %d") % n, value=n, label=str(n))
                     for n in w.hairs(look["job"], look["sex"])]
            self.count_text = _("%d cabelos") % len(items)
        elif key == "hair_color":
            items = [dict(key=("hair_color", n) + ctx, name=_("Cor %d") % n, value=n, label=str(n))
                     for n in w.hair_colors(look["hair"], look["sex"])]
            self.count_text = _("%d cores") % len(items)
        else:
            items = [dict(key=("cloth_color", n) + ctx, name=_("Cor %d") % n, value=n, label=str(n))
                     for n in w.cloth_colors(look["job"], look["sex"], look.get("option", 0))]
            self.count_text = _("%d cores") % len(items)
        self.count.configure(text=self.count_text)
        self.grid.set(items, tuple(int(v * self.win.dpi) for v in cell),
                      self.worn(key) if key in SLOT_KEYS else look.get(key), keep_scroll)

    def thumb(self, key, cell):
        """A miniatura de uma célula: o personagem atual só com aquilo (chapéu na cabeça, capa no corpo...)."""
        w = sprites.LOADER.wardrobe
        if w is None:
            return None
        kind, value = key[0], key[1]
        if kind == "icon":                         # topo, meio e baixo: o desenho do chapéu (senão o ícone do item)
            photo = self.sprite_thumb(key[2], cell) or self.icon(value, cell)
            if photo is not None:
                return photo
            kind, value = "top", key[2]            # item sem desenho nem ícone: a cabeça com ele, como antes
        base = dict(self.look, top=0, mid=0, low=0, robe=0, weapon=0, shield=0)
        base[kind] = value
        with_body = next(b for k, _n, _c, b in CATEGORIES if k == kind)
        try:
            res = w.thumb(base, with_body)
        except (ValueError, IndexError, KeyError):
            res = None
        if res is None:
            return None
        iw, ih, px = res
        cw, ch = cell[0] - 8, cell[1] - 8
        zoom = 1
        if iw * 2 <= cw and ih * 2 <= ch:
            zoom = 2
        elif iw > cw or ih > ch:                   # visual grande: encolhe até caber
            k = min(cw / float(iw), ch / float(ih))
            tw, th = max(1, int(iw * k)), max(1, int(ih * k))
            px, iw, ih = sprites.resize(iw, ih, px, tw, th), tw, th
        try:
            photo = tk.PhotoImage(master=self.win.top, data=sprites.png_b64(iw, ih, px), format="png")
        except (tk.TclError, ValueError, IndexError, ZeroDivisionError):
            return None
        return photo.zoom(zoom) if zoom > 1 else photo

    def sprite_thumb(self, view, cell):
        """O desenho do chapéu sozinho (o mesmo da animação) no maior tamanho que cabe na célula, ou None (sem
        desenho, ou minúsculo como uma piscadela: aí vale o ícone)."""
        w = sprites.LOADER.wardrobe
        if w is None:
            return None
        try:
            got = w.item_thumb(view, self.look, cell[0] - 8, cell[1] - 8)
            if got is None:
                return None
            _tw, _th, data, zoom = got
            photo = tk.PhotoImage(master=self.win.top, data=data, format="png")
        except Exception:  # noqa: BLE001 - desenho estranho: vale o ícone
            return None
        return photo.zoom(zoom) if zoom > 1 else photo

    def icon(self, item, cell):
        """O ícone do item (24 x 24 no jogo) como imagem do Tk, no maior tamanho inteiro que cabe na célula."""
        w = sprites.LOADER.wardrobe
        if w is None:
            return None
        try:
            if self.icons is None:
                self.icon_art = gamecache.items(os.path.join(os.path.dirname(w.grf.path), "System",
                                                             "iteminfo_new.lub")).get("art") or {}
                self.icons = self.vis_grf(w.grf.path) or sprites.Grf(w.grf.path, prefixes=(sprites.ITEM_ICON,
                                                                                            sprites.ITEM_ART))
            if not self.icons:
                return None
            art = self.icon_art.get(item)
            data = self.icons.read(sprites.ITEM_ICON + art + ".bmp") if art else None
            if not data:
                return None
            iw, ih, px = sprites.bmp_rgba(data)
            if visuals.tiny_icon(iw, ih, px):      # piscadelas, óculos...: vale a ilustração grande, reduzida
                big = self.icons.read(sprites.ITEM_ART + art + ".bmp")
                if big:
                    bw, bh, bpx = sprites.crop(*sprites.clear_background(*sprites.bmp_rgba(big)))
                    k = min(1.0, (cell[0] - 8) / float(bw), (cell[1] - 8) / float(bh))
                    tw, th = max(1, int(bw * k)), max(1, int(bh * k))
                    if (tw, th) != (bw, bh):
                        bpx = sprites.resize(bw, bh, bpx, tw, th)
                    return tk.PhotoImage(master=self.win.top, data=sprites.png_b64(tw, th, bpx), format="png")
            photo = tk.PhotoImage(master=self.win.top, data=sprites.png_b64(iw, ih, px), format="png")
        except Exception:  # noqa: BLE001 - ícone estranho ou jogo sem a lista de itens: vale a miniatura antiga
            self.icons = self.icons or False
            return None
        zoom = max(1, min((cell[0] - 8) // max(1, iw), (cell[1] - 8) // max(1, ih)))
        return photo.zoom(zoom) if zoom > 1 else photo

    def chosen(self, it):
        key = self.category.get()
        if key in SLOT_KEYS:
            self.pick(key, it["row"])
            return
        if key == "effects":                       # liga e desliga; passou do limite, sai o mais antigo
            on = list(self.look.get("effects") or [])
            if it["value"] in on:
                on.remove(it["value"])
            else:
                on = (on + [it["value"]])[-visuals.MAX_EFFECTS:]
            self.look["effects"] = on
            self.modified()
            self.show_effects()
            self.grid.selected = list(on)
            self.grid.redraw()
            self.draw()
            return
        if self.look.get(key) == it["value"]:
            return
        self.look[key] = it["value"]
        if key == "hair" and self.look["hair_color"] not in sprites.LOADER.wardrobe.hair_colors(
                self.look["hair"], self.look["sex"]):
            self.look["hair_color"] = 0
        self.modified()
        self.grid.selected = it["value"]
        self.grid.redraw()
        self.draw()

    def hovered(self, it):
        self.count.configure(text=it["name"] if it else self.count_text,
                             fg=self.win.c["fg"] if it else self.win.c["muted"])

    # ------------------------------------------------------------ looks guardados

    def pick_saved(self):
        name = self.saved.get()
        if name == _(REPLAY):
            self.reset_look()
            return
        look = visuals.saved_looks(self.win.app.cfg).get(name)
        if look:
            self.set_look(look)
            self.saved.set(name)
            self.remember()
            self.draw()

    def save_look(self):
        cur = self.saved.get()
        name = simpledialog.askstring(_("Salvar look"), _("Nome do look:"), parent=self.win.top,
                                      initialvalue="" if cur in ("", _(REPLAY)) else cur)
        name = " ".join((name or "").split())
        if not name or name == _(REPLAY):
            return
        cfg = self.win.app.cfg
        looks = dict(cfg.get("looks") or {})
        looks[name] = visuals.clean(self.look)
        cfg["looks"] = looks
        self.win.app.save()
        self.saved_box["values"] = [_(REPLAY)] + sorted(looks)
        self.saved.set(name)

    def delete_look(self):
        name = self.saved.get()
        cfg = self.win.app.cfg
        looks = dict(cfg.get("looks") or {})
        if name in looks:
            del looks[name]
            cfg["looks"] = looks
            self.win.app.save()
            self.saved_box["values"] = [_(REPLAY)] + sorted(looks)
            self.saved.set("")

    # ------------------------------------------------------------ prévia

    def turn(self, step):
        self.dir = (self.dir + step) % 8
        self.draw()

    def restart(self):
        self.frame = 0
        self.t0 = time.monotonic()
        self.draw()

    def choice(self):
        action = next((a for a, n in sprites.ACTIONS if _(n) == self.action.get()), sprites.IDLE)
        head = next((h for h, n in sprites.HEAD_DIRS if _(n) == self.head.get()), 0)
        return action, head

    def stop(self):
        if self.after is not None:
            try:
                self.win.top.after_cancel(self.after)
            except tk.TclError:
                pass
            self.after = None

    def visible(self):
        return self.win.tab_name() == "visuais"

    def draw(self):
        """Desenha o quadro atual e agenda o próximo (anima enquanto a aba estiver à vista)."""
        self.stop()
        win, cv, col, sc = self.win, self.canvas, self.win.c, self.scale
        cv.delete("all")
        W, H = int(cv["width"]), int(cv["height"])
        loader = sprites.LOADER
        w = loader.wardrobe
        if w is None:
            if loader.loading or (clientdata.NAMES.grf and loader.error is None):
                msg = _("Carregando os sprites do jogo…")
                if self.visible():
                    self.after = win.top.after(250, lambda: self.refresh(win.combat()))
            elif loader.error:
                msg = _("Não deu para ler o data.grf do jogo (%s).") % loader.error
            else:
                msg = _("Jogo não encontrado: o visual é montado com os sprites do data.grf da instalação.")
            cv.create_text(W / 2, H / 2, text=msg, fill=col["muted"], font=win.f["text"], width=W - 20)
            self.info.configure(text="")
            return
        if self.catalog is None:
            self.ensure_catalog(w)
            self.show_look()
        action, head = self.choice()
        look = self.look
        elapsed = (time.monotonic() - self.t0) * 1000.0
        lk = tuple(sorted((k, v) for k, v in look.items() if k != "effects"))
        # cada parte no quadro dela neste instante (chapéus e capas animados no próprio ritmo, o passo do corpo na
        # velocidade do personagem) e quanto falta para o próximo quadro mudar
        fast = self.action.get() == _(sprites.FAST_WALK)
        st = w.clock(look, action, self.dir, head, elapsed, sprites.walk_speed(fast, self.speed))
        step, idx, wait = st if st else (0, (), None)
        self.frame = step
        on = list(look.get("effects") or [])
        table = self.effects() if on else None
        zoom = max(1, sc // 2) if visuals.SHRINK in on else sc
        pale, shadow = visuals.PALE in on, visuals.SHADOW in on
        key = (lk, action, self.dir, head, idx, zoom, pale, shadow)
        img = self.images.get(key)
        if img is None:
            # montado pelo GDI+ (a Sombra e a Palidez já vêm prontas)
            r = w.render_png(look, action, self.dir, step, head, elapsed, pale, shadow)
            if r is None:
                cv.create_text(W / 2, H / 2, text=_("Sem sprite para esta classe."), fill=col["muted"],
                               font=win.f["text"], width=W - 20)
                self.info.configure(text="")
                return
            iw, ih, data, ox, oy, delay, nframes, missing, dark_data = r
            dark = None
            if dark_data:                          # Sombra: a mesma figura, escura e meio transparente
                dark = tk.PhotoImage(master=win.top, format="png", data=dark_data)
                dark = dark.zoom(zoom) if zoom > 1 else dark
            photo = tk.PhotoImage(master=win.top, data=data, format="png")
            if zoom > 1:
                photo = photo.zoom(zoom)
            if len(self.images) > 160:
                self.images = {}
            img = self.images[key] = (photo, ox * zoom, oy * zoom, delay, nframes, missing, dark)
        photo, ox, oy, delay, nframes, missing, dark = img
        self.n, self.delay = max(1, nframes), float(delay or 100)
        # os pés ficam perto de baixo; um visual muito alto (um dragão em volta do personagem) desce o que der
        # para caber inteiro, e um que sobra para baixo dos pés sobe. A conta usa o retângulo de TODOS os quadros
        # da animação: com o de cada quadro, o personagem subia e descia quando o visual mudava de tamanho (e o chão
        # era redesenhado a cada quadro)
        ek = (lk, action, self.dir, head)
        ext = self.extents.get(ek)
        if ext is None:
            if len(self.extents) > 200:
                self.extents = {}
            ext = self.extents[ek] = w.extent(look, action, self.dir, head) or (
                -ox / zoom, -oy / zoom, (photo.width() - ox) / zoom, (photo.height() - oy) / zoom)
        above, below = -ext[1] * zoom, ext[3] * zoom
        fx, fy = W / 2, H - (70 if on else 30) * sc     # com efeito ligado sobra chão para o que fica nos pés
        fy = min(fy, H - 2 - below) if below > 30 * sc - 2 else fy
        if fy - above < 2:
            fy = min(H - 2 - below, above + 2) if above + below <= H - 4 else (H - (above + below)) / 2 + above
        fx, fy = int(fx), int(fy)
        self.draw_floor(W, H, fx, fy)
        cv.create_oval(fx - 14 * zoom, fy - 4 * zoom, fx + 14 * zoom, fy + 4 * zoom, outline="",
                       fill=_shade(col["tile"]), stipple="gray50")
        # efeitos: os de trás do personagem primeiro, os outros por cima (cada um no próprio ritmo)
        photos, front = [], []
        waits = [wait] if wait is not None else []
        for name in on:
            anim = table.frames(name) if (table and name not in visuals.SPECIAL) else None
            if not anim:
                continue
            waits.append(anim["ms"] - elapsed % anim["ms"])
            data, dx, dy = anim["frames"][int(elapsed / anim["ms"]) % len(anim["frames"])]
            try:
                ph = tk.PhotoImage(master=win.top, data=data, format="png")
                ph = ph.zoom(sc) if sc > 1 else ph
            except tk.TclError:
                continue
            photos.append(ph)
            # cada quadro guarda só o pedaço desenhado: (dx, dy) é onde ele fica no quadrado do efeito
            spot = (fx + (dx - anim["cx"]) * sc, fy + (dy - anim["cy"]) * sc, ph)
            if anim["behind"]:
                cv.create_image(spot[0], spot[1], image=ph, anchor="nw")
            else:
                front.append(spot)
        if dark is not None:
            cv.create_image(fx - ox + SHADOW_AT[0] * zoom, fy - oy + SHADOW_AT[1] * zoom, image=dark, anchor="nw")
        cv.create_image(fx - ox, fy - oy, image=photo, anchor="nw")
        for x, y, ph in front:
            cv.create_image(x, y, image=ph, anchor="nw")
        self.fx_photos = photos
        info = [_("cabelo %d, cor %d · roupa cor %d") % (look["hair"], look["hair_color"], look["cloth_color"]),
                _("direção %s") % sprites.DIRECTIONS[self.dir]]
        if missing:
            names = {"corpo": _("corpo"), "cabeça": _("cabeça"), "low": _("chapéu de baixo"),
                     "mid": _("chapéu do meio"), "top": _("chapéu de cima"), "robe": _("capa")}
            info.append(_("sem sprite no jogo: %s") % ", ".join(names.get(m, m) for m in missing))
        self.info.configure(text=" · ".join(info))
        if self.visible() and waits:
            # o próximo desenho na hora em que algum quadro muda (antes: o delay do corpo DEPOIS de desenhar, o que
            # somava o tempo do desenho e pulava quadros)
            self.after = win.top.after(max(10, int(min(waits)) + 1), self.tick)

    def tick(self):
        self.after = None
        if self.visible():
            self.draw()


def _shade(color):
    """A cor do painel um pouco mais escura (a sombra no chão)."""
    try:
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return color
    return "#%02x%02x%02x" % (int(r * 0.65), int(g * 0.65), int(b * 0.65))
