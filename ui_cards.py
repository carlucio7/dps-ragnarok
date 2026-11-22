# -*- coding: utf-8 -*-
"""Aba Cartões da análise (o gerenciador de cartões). Três páginas à esquerda, a prévia à direita:
  * Cartões do programa: cada um com a sua caixa para desligar (passe o mouse para ver a prévia);
  * Efeitos acompanhados: a busca em todos os buffs, debuffs e efeitos de chão, a lista do que o widget acompanha e
    as opções de cada um (como aparece, onde olhar, temporizador, som; os sons da pasta da pessoa também);
  * Resumo da sessão: o que o cartão do fim da gravação mostra.
Funciona sem replay aberto.

A prévia é desenhada pelo próprio código do widget (as funções de dpsmeter.DpsApp) num widget de mentira com a
largura, as linhas, o zoom, o tema e a faixa fixa do widget de verdade, e o tempo dos efeitos corre como no jogo
(conta, fica amarelo no fim, pisca "acabou" e recomeça). Os botões Contador / Faixa fixa / Cartão mostram, ao passar o
mouse, como o efeito escolhido apareceria em cada modo; o clique escolhe.
"""

import sys
import time
import tkinter as tk
from tkinter import ttk

import cards
import class_scenes
import clientdata
import itemping
import meter
import session
import sounds
import sprites
import ui_parts
import xp
from analysis_ui import ScrollFrame, Table
from fmt import num
from i18n import _

ALL = "Todos os tipos"
# o som de cada cartão do programa que tem um: (liga/desliga, volume, qual som)
SYS_SOUNDS = {"miracle": ("miracle_sound", "miracle_volume", "chime"), "fusion": ("fusion_sound", "fusion_volume", "beep"),
              "rec": ("rec_sound", "fusion_volume", "beep"), "ping": ("ping_sound", "ping_volume", "ping")}
BETEL, AQUILA, AQUILA_OVER, PORING = 20994, 21531, 21588, 1002
ATROCE = 1785                 # o "Curar" do monstro (dano que vira cura), como no Laboratório Central
PREVIEW_TRIES = 12            # redesenhos enquanto os desenhos do jogo carregam
TICK_MS = 150                 # a prévia anima a esse passo enquanto a aba está à vista
IDLE_MS = 700                 # ...e confere com essa calma quando não está
SESSION_REST_S = 3.0          # na prévia do resumo da sessão, o cartão fica parado isto entre uma animação e outra
MODE_TEXT = {
    "counter": "Contador: uma linha no pé do widget, embaixo das outras, só enquanto o efeito está ativo, com o tempo "
               "e a barra esvaziando. Quando acaba, pisca \"acabou\" e some.",
    "pin": "Faixa fixa: fica sempre à vista na faixa abaixo das abas (junto com o que mais estiver fixado, até 2), com "
           "o tempo quando está ativo e \"—\" quando não está. Com um cartão aberto, vai para o lado do DPS.",
    "card": "Cartão: cobre as linhas do widget enquanto o efeito dura, com o alvo, o tempo que falta e a barra; fica "
            "amarelo no fim e vermelho quando acaba. Outros cartões (morte, chefe, item) passam na frente.",
}


def clear_selection(table):
    """Tira a seleção de uma lista (Table); o aviso de seleção dela chega depois, com None."""
    try:
        sel = table.tree.selection()
        if sel:
            table.tree.selection_remove(*sel)
    except tk.TclError:
        pass


class CardPreview(tk.Canvas):
    """Um widget de mentira do tamanho do de verdade (largura, linhas, zoom e tema escolhidos), com o cartão ou os
    contadores pedidos por cima, desenhados pelas funções do widget de verdade."""

    def __init__(self, parent, win):
        self.win = win
        app = win.app
        self.mod = sys.modules[type(app).__module__]          # o módulo do widget (constantes e cores)

        class Fake(type(app)):                                # o widget sem janela: só o que o desenho usa
            s = property(lambda self: self._s)
        p = self.p = object.__new__(Fake)
        p.dpi = app.dpi
        p._s = app.cfg["scale"] * app.dpi
        p.root = win.top
        p.cfg = dict(app.cfg)
        p.make_fonts()
        p.W, p.H = p.size_px()
        super().__init__(parent, width=p.W, height=p.H, highlightthickness=1, highlightbackground=win.c["grid"], bd=0)
        p.canvas = self
        p.hits, p.hover, p.phase, p.sprite_photos = [], None, 0, {}
        p.tracker_rows, p.tracker_n, p.pinned_fx = [], 0, {}
        p.fx_cards, p.fx_closed, p.fx_now = [], set(), []
        p.death_card = p.boss_card = p.ping_card = p.summary_card = p.session_card = p.follow_offer = None
        p.miracle_at = -1e9
        self.what = ("trackers", None)
        self.rows, self.pinned, self.fx, self.extra_pin = [], {}, [], None
        self.session_data = None      # o cartão do resumo da sessão da gravação aberta (None: o de exemplo)
        # os desenhos da cena do resumo (o d["chase"]) de um quadro para o outro: (a cena, {desenhos}). O cartão é
        # refeito a cada quadro, e sem isso a cena era montada de novo em todo quadro (o "Nível máximo" levava uns
        # 0,6 s por quadro e o programa inteiro travava; a carta de MVP refazia o monstro caindo)
        self.scene = (None, {})
        self.started = time.time()
        self._after = self._anim = None
        self._tries = 0
        self._scale = None
        self.bind("<Destroy>", lambda e: self._cancel())

    def _cancel(self):
        for name in ("_after", "_anim"):
            job = getattr(self, name)
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, name, None)

    def show(self, what, rows=None, pinned=None, fx=None, extra_pin=None, session_data=None):
        """what: ("system", chave do cartão) ou ("trackers", None) com os contadores em `rows`. `pinned`: {chave:
        linha} dos efeitos na faixa fixa; `fx`: os que aparecem como cartão; `extra_pin`: um efeito a mostrar na faixa
        fixa só na prévia (o botão Faixa fixa sob o mouse); `session_data`: o resumo da sessão de exemplo a mostrar
        (de um destaque ou de uma informação; None = o de exemplo das escolhas)."""
        self.what, self.rows, self.pinned, self.fx = what, rows or [], pinned or {}, fx or []
        self.extra_pin, self.session_data = extra_pin, session_data
        self.scene = (None, {})
        self.started = time.time()
        self._tries = 0
        self.redraw()
        self.animate()

    # ------------------------------------------------------------ o tempo correndo

    def visible(self):
        """A aba Cartões está à vista (a animação só gasta tempo nela)."""
        try:
            return self.winfo_ismapped() and self.win.top.state() != "iconic"
        except tk.TclError:
            return False

    def animate(self):
        if self._anim is not None:
            return

        def step():
            self._anim = None
            if not self.winfo_exists():
                return
            ses = self.what == ("system", "session")         # o resumo da sessão repete a animação do destaque
            moving = ses or (self.what[0] == "trackers" and (self.rows or self.pinned or self.fx))
            if moving and self.visible():
                self.p.phase = (self.p.phase + 1) % 8
                self.redraw()
            fast = ses and self.session_k() < self.mod.SESSION_FX_S
            self._anim = self.after((self.mod.SESSION_FX_MS if fast else TICK_MS) if moving and self.visible()
                                    else IDLE_MS, step)
        self._anim = self.after(TICK_MS, step)

    def session_k(self):
        """O tempo do resumo da sessão na prévia: a animação do destaque e uns segundos parado, de novo e de novo."""
        return (time.time() - self.started) % (self.mod.SESSION_FX_S + SESSION_REST_S)

    def tick(self, r, el):
        """A linha `r` no instante `el` (ms desde o começo da prévia): conta do total até zero, pisca "acabou" e
        some um instante antes de recomeçar. Sem duração conhecida: "há N s" subindo. None = inativo agora."""
        total = r.get("total")
        off = r.get("off", 0)
        if not total or r.get("left") is None:
            return dict(r, since=(el + off) % 120000 + 4000)
        cycle = total + (cards.FLASH_S + 1.5) * 1000
        ph = (el + off) % cycle
        if ph < total:
            return dict(r, left=total - ph)
        gone = (ph - total) / 1000.0
        if gone < cards.FLASH_S and self.win.app.cfg.get("tracker_flash", True):
            return dict(r, left=0, ended=gone)
        return None

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
        if key == "damage_heal":
            return "boss", dict(name=self.mob_name(ATROCE, "Atroce"), mech="heal_phys", sprite=("mob", ATROCE))
        if key == "summary":
            return "summary", dict(key=0, sprite=("mob", BETEL), name=betel, killed=True, ms=154000, share=0.231,
                                   rank=2, players=7, grave=1, warn=2,
                                   alerts=[(2, _("Atacou antes da Garra Sombria"), "Fenrir"),
                                           (1, _("Atacou muito antes dos outros DPS"), "Bastion")])
        if key == "session":
            return "session", dict(self.session_data or session.sample_card(self.p.cfg), c=None, cur=None, n0=0)
        if key == "ping":
            item = 4001
            art = xp.GEAR.art.get(item)
            return "ping", dict(kind="drop", ref=None, item=item, name=meter.item_name(item), count=1,
                                map="prt_fild08", x=123, y=45, mob=self.mob_name(PORING, "Poring"), secs=12.0,
                                sprite=("item", item, art) if art else None)
        if key == "follow":
            return "follow", dict(path="RagnarokReplay_0121.rrf", name="RagnarokReplay_0121.rrf",
                                  current="RagnarokReplay_0098.rrf")
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
        names = ["Aria", "Fenrir", "Bastion", "Corvina", "Lyra", "Dante", "Selene", "Orion", "Kael", "Nyx"]
        vals = [239, 170, 82.5, 61.0, 33.4, 12.8, 9.1, 6.0, 3.2, 1.4]
        y = p.rows_y0() * s
        for i in range(p.cfg["rows"]):
            x0, x1, y1 = 8 * s, W - 8 * s, y + (m.ROW_H - 3) * s
            v = vals[i % len(vals)]
            c.create_polygon(m.round_rect_pts(x0, y, x1, y1, 4 * s), smooth=True, fill=t["track"], outline="")
            c.create_polygon(m.round_rect_pts(x0, y, x0 + (x1 - x0) * v / vals[0], y1, 4 * s), smooth=True,
                             fill=t["bar_me"] if i == 0 else t["bar"], outline="")
            c.create_text(x0 + 7 * s, (y + y1) / 2, anchor="w", text="%d. %s" % (i + 1, names[i % len(names)]),
                          font=f["text"], fill=t["fg"])
            c.create_text(x1 - 7 * s, (y + y1) / 2, anchor="e", text=("%.1fM" % v).replace(".", ","),
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

    def sync(self):
        """O widget de mentira segue o de verdade: largura, linhas, zoom, tema, faixa fixa e opções dos contadores."""
        app, p = self.win.app, self.p
        for k in ("width", "rows", "scale", "theme", "tracker_rows", "tracker_flash", "pins", "session_fields",
                  "session_hl_off", "session_anim"):
            if k in app.cfg:                       # o que a pessoa nunca mexeu fica de fora: vale o padrão de quem lê
                p.cfg[k] = app.cfg[k]              # (antes virava None, e o "Animar o destaque" saía desligado)
            else:
                p.cfg.pop(k, None)
        scale = app.cfg["scale"] * app.dpi
        if scale != self._scale:                   # zoom diferente: as fontes do widget de mentira acompanham
            self._scale = p._s = scale
            p.make_fonts()
            self.scene = (None, {})                # e os desenhos da cena saem de novo, no tamanho novo

    def redraw(self):
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        p = self.p
        now = time.time()
        self.sync()
        p.death_card = p.boss_card = p.ping_card = p.summary_card = p.session_card = p.follow_offer = None
        p.miracle_at = -1e9
        kind, key = self.what
        el = (now - self.started) * 1000.0
        p.tracker_n, p.hits = 0, []
        if kind == "trackers":
            p.tracker_rows = [x for x in (self.tick(r, el) for r in self.rows) if x]
            p.fx_cards = [x for x in (self.tick(r, el) for r in self.fx) if x]
            p.pinned_fx = {k: x for k, x in ((k, self.tick(r, el)) for k, r in self.pinned.items()) if x}
        else:
            p.tracker_rows, p.fx_cards, p.pinned_fx = [], [], {}
        p.fx_closed = set()
        p.fx_now = p.fx_card_rows()
        pins = list(p.cfg.get("pins") or [])
        if self.extra_pin and "fx:" + self.extra_pin not in pins:
            pins = (pins + ["fx:" + self.extra_pin])[-self.mod.MAX_PINS:]
        p.cfg["pins"] = pins
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
                elif shape == "session":
                    hl = data.get("hl") or []
                    fx = hl[0].get("fx") if hl else None
                    if fx in self.mod.SCENE_FX:                       # cenas com os desenhos do jogo
                        if self.scene[0] != fx:                       # (entram quando ficam prontos e ficam)
                            self.scene = (fx, {})
                        data["chase"] = data.get("chase") or self.scene[1]
                        if clientdata.NAMES.grf:
                            sprites.MONSTERS.start(clientdata.NAMES.grf)
                            sprites.LOADER.start(clientdata.NAMES.grf)
                            class_scenes.KIT.start(clientdata.NAMES.grf)
                    p.session_card = (data, now - self.session_k())
                elif shape == "ping":
                    p.ping_card = (data, now - 0.01)
                elif shape == "follow":
                    p.follow_offer = data
            spec = (data or {}).get("sprite")
        p.t = p.theme()
        self.delete("all")
        self.configure(bg=p.t["bg"])
        self.backdrop(self.foot_text(key) if foot else None)
        card_up = shape in ("death", "boss", "summary", "session", "ping", "follow") or bool(p.fx_now)
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
            elif shape == "session":
                p.draw_session_card()
            elif shape == "ping":
                p.draw_ping_card()
            elif shape == "follow":
                p.draw_follow_card()
            if shape == "death" and p.cfg.get("pins"):          # o resumo da morte cobre o DPS: a faixa fica acima
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
        tab = self.tab = tk.Frame(nb, bg=c["panel"])
        nb.add(tab, text=_("Cartões"))
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.pages = ttk.Notebook(tab, style="Sub.TNotebook")
        self.pages.grid(row=0, column=0, sticky="nsew", padx=(6, 4), pady=6)
        self.page_sys = tk.Frame(self.pages, bg=c["tile"])
        self.page_fx = tk.Frame(self.pages, bg=c["tile"])
        self.page_ses = tk.Frame(self.pages, bg=c["tile"])
        self.pages.add(self.page_sys, text=_("Cartões do programa"))
        self.pages.add(self.page_fx, text=_("Efeitos acompanhados"))
        self.pages.add(self.page_ses, text=_("Resumo da sessão"))
        self.pages.bind("<<NotebookTabChanged>>", lambda e: self.page_changed())
        self.build_preview(tab)
        self.build_system(self.page_sys)
        self.build_effects(self.page_fx)
        self.build_session(self.page_ses)
        self.pv_what = ("trackers", None)
        self.mode_hover = None
        self.sig = None

    # ------------------------------------------------------------ montagem

    def build_preview(self, tab):
        win, c = self.win, self.win.c
        right = tk.Frame(tab, bg=c["panel"])
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=6)
        self.pv_title = win.label(right, "", "head", bg="panel", anchor="w")
        self.pv_title.pack(fill="x")
        self.pv_note = win.label(right, _("Do tamanho do seu widget agora (largura, linhas, zoom e tema); o tempo "
                                          "corre como no jogo."), "small", "muted", "panel", anchor="w",
                                 justify="left")
        self.pv_note.pack(fill="x", pady=(0, 4))
        self.mode_bar = tk.Frame(right, bg=c["panel"])
        self.mode_btns = {}
        for mode in cards.SHOWS:
            b = tk.Label(self.mode_bar, text=_(cards.SHOW_TEXT[mode]).capitalize(), font=win.f["text"], bg=c["btn"],
                         fg=c["fg"], padx=10, pady=4, cursor="hand2")
            b.pack(side="left", padx=(0, 6))
            b.bind("<Enter>", lambda e, m=mode: self.hover_mode(m))
            b.bind("<Leave>", lambda e: self.hover_mode(None))
            b.bind("<Button-1>", lambda e, m=mode: self.pick_mode(m))
            self.mode_btns[mode] = b
        self.mode_text = win.label(right, "", "small", "fg", "panel", anchor="w", justify="left")
        holder = tk.Frame(right, bg=c["panel"])
        holder.pack(side="bottom", fill="both", expand=True)
        self.pv_scroll = ScrollFrame(holder, win)
        self.preview = CardPreview(self.pv_scroll.inner, win)
        self.preview.pack(anchor="nw")
        width = self.preview.p.W + int(30 * win.dpi)
        self.pv_note.configure(wraplength=width)
        self.mode_text.configure(wraplength=width)
        right.configure(width=width)

    def build_system(self, page):
        win, c = self.win, self.win.c
        note = win.label(page, _("O que o widget já mostra sozinho. Tudo vem ligado: clique no ✓ (ou dê dois cliques) "
                                 "para desligar ou ligar. Escolha um cartão para ver a prévia ao lado e as opções "
                                 "dele embaixo."), "small", "muted", "tile", anchor="w", justify="left")
        note.pack(fill="x", padx=10, pady=(8, 6))
        ui_parts.follow_wrap(page, note, 24, 200)
        chips = tk.Frame(page, bg=c["tile"])
        chips.pack(fill="x", padx=10, pady=(0, 6))
        win.label(chips, _("Todos:"), color="muted", bg="tile").pack(side="left")
        for text, on in ((_("Ligar todos"), True), (_("Desligar todos"), False)):
            self.chip(chips, text, lambda v=on: self.set_all_system(v))
        # o cartão escolhido fica embaixo (pack na ordem inversa): com a janela baixa a tabela encolhe, isto fica
        each = tk.Frame(page, bg=c["panel"], padx=10, pady=6)
        each.pack(side="bottom", fill="x", padx=10, pady=(4, 8))
        top = tk.Frame(each, bg=c["panel"])
        top.pack(fill="x")
        self.sys_title = win.label(top, "", "text", "fg", "panel", anchor="w")
        self.sys_title.pack(side="left")
        self.sys_on = tk.BooleanVar(win.top, True)
        self.sys_on_cb = self.check(top, _("Ligado"), self.sys_on, self.sys_on_changed, "panel")
        self.sys_on_cb.pack(side="right")
        self.sys_desc = win.label(each, "", "small", "muted", "panel", anchor="w", justify="left")
        self.sys_desc.pack(fill="x", pady=(2, 0))
        ui_parts.follow_wrap(each, self.sys_desc, 24, 200)
        snd = self.sys_snd = tk.Frame(each, bg=c["panel"])
        self.sys_snd_on = tk.BooleanVar(win.top, False)
        self.check(snd, _("Tocar um som"), self.sys_snd_on, self.sys_sound_changed, "panel").pack(side="left")
        win.label(snd, _("Volume:"), color="muted", bg="panel").pack(side="left", padx=(14, 4))
        self.sys_vol = tk.StringVar(win.top, "")
        self.sys_vol_box = ttk.Combobox(snd, textvariable=self.sys_vol, width=6, state="readonly",
                                        style="An.TCombobox", font=win.f["text"])
        self.sys_vol_box.pack(side="left")
        self.sys_vol_box.bind("<<ComboboxSelected>>", lambda e: self.sys_sound_changed(play=True))
        self.sys_tone_lbl = win.label(snd, _("Tom:"), color="muted", bg="panel")
        self.sys_tone = tk.StringVar(win.top, "")
        self.sys_tone_box = ttk.Combobox(snd, textvariable=self.sys_tone, width=10, state="readonly",
                                         values=[_(self.tone_name(t)) for t, _hz in itemping.TONES],
                                         style="An.TCombobox", font=win.f["text"])
        self.sys_tone_box.bind("<<ComboboxSelected>>", lambda e: self.sys_sound_changed(play=True))
        self.sys_play = ttk.Button(snd, text="▶ " + _("Ouvir"), style="An.TButton", command=self.sys_play_sound)
        self.sys_play.pack(side="right")
        self.sys_link = win.label(each, _("Escolher o que ele mostra ›"), "small", "accent", "panel", anchor="w",
                                  cursor="hand2")
        self.sys_link.bind("<Button-1>", lambda e: self.show_page("session"))
        holder = tk.Frame(page, bg=c["tile"])
        holder.pack(fill="both", expand=True, padx=8, pady=(0, 2))
        self.t_sys = Table(holder, win, [("mark", "", 26, "center", "text"), ("name", _("Cartão"), 230, "w", "text"),
                                         ("when", _("Quando aparece"), 300, "w", "text"),
                                         ("stay", _("Quanto fica"), 120, "w", "text")], height=8,
                           on_select=self.sys_selected)
        self.t_sys.pack(fill="both", expand=True)
        self.marks(self.t_sys, lambda key: self.toggle_system(key, not cards.enabled(self.cfg(), key)))

    def chip(self, parent, text, command):
        """Um botão rápido no estilo das sugestões da página dos efeitos."""
        c = self.win.c
        b = tk.Label(parent, text=text, font=self.win.f["small"], bg=c["btn"], fg=c["fg"], padx=8, pady=3,
                     cursor="hand2")
        b.pack(side="left", padx=(6, 0))
        b.bind("<Button-1>", lambda e: command())
        return b

    def check(self, parent, text, var, command, bg="tile", font="text"):
        c = self.win.c
        return tk.Checkbutton(parent, text=text, variable=var, command=command, bg=c[bg], fg=c["fg"],
                              selectcolor=c["btn"], activebackground=c[bg], activeforeground=c["fg"],
                              font=self.win.f[font], anchor="w", highlightthickness=0)

    def marks(self, table, toggle):
        """Clicar na coluna do ✓ (ou dois cliques na linha) liga e desliga a linha."""
        tree = table.tree

        def click(e):
            if tree.identify_region(e.x, e.y) == "cell" and tree.identify_column(e.x) == "#1":
                iid = tree.identify_row(e.y)
                if iid:
                    toggle(iid)
        tree.bind("<ButtonRelease-1>", click, add="+")
        tree.bind("<Double-1>", lambda e: (lambda iid: toggle(iid) if iid else None)(tree.identify_row(e.y)))

    def build_effects(self, page):
        win, c = self.win, self.win.c
        note2 = win.label(page, _("Enquanto um efeito da lista está ativo, o widget mostra o tempo que falta (ou há "
                                  "quanto tempo está ativo), só durante a gravação. Escolha um efeito em "
                                  "Acompanhando para mudar como ele aparece, o temporizador e o som."),
                          "small", "muted", "tile", anchor="w", justify="left")
        note2.pack(fill="x", padx=10, pady=(8, 6))
        ui_parts.follow_wrap(page, note2, 24, 200)
        sug = tk.Frame(page, bg=c["tile"])
        sug.pack(fill="x", padx=10, pady=(0, 6))
        win.label(sug, _("Sugestões:"), color="muted", bg="tile").pack(side="left")
        self.sug_btns = {}
        for efst in cards.SUGGESTED:
            b = tk.Label(sug, text="", font=win.f["small"], bg=c["btn"], fg=c["fg"], padx=8, pady=3, cursor="hand2")
            b.pack(side="left", padx=(6, 0))
            b.bind("<Button-1>", lambda e, i=efst: self.toggle("status", i))
            self.sug_btns[efst] = b
        bar = tk.Frame(page, bg=c["tile"])
        bar.pack(fill="x", padx=10)
        win.label(bar, _("Buscar:"), color="muted", bg="tile").pack(side="left")
        self.query = tk.StringVar(win.top, "")
        ent = tk.Entry(bar, textvariable=self.query, width=22, font=win.f["text"], bg=c["btn"], fg=c["fg"],
                       insertbackground=c["fg"], relief="flat")
        ent.pack(side="left", padx=6, ipady=3)
        win.trace(self.query, lambda *_a: self.fill_results())
        self.group = tk.StringVar(win.top, _(ALL))
        gb = ttk.Combobox(bar, textvariable=self.group, values=[_(ALL)] + [_(g) for g in cards.GROUPS], width=20,
                          state="readonly", style="An.TCombobox", font=win.f["text"])
        gb.pack(side="left", padx=6)
        gb.bind("<<ComboboxSelected>>", lambda e: self.fill_results())
        ttk.Button(bar, text=_("Acompanhar"), style="An.TButton", command=self.add_selected).pack(side="right")
        # embaixo primeiro (pack na ordem inversa): com a janela baixa, as duas listas encolhem e as opções ficam
        opts = tk.Frame(page, bg=c["tile"])
        opts.pack(side="bottom", fill="x", padx=10, pady=(2, 8))
        win.label(opts, _("Mostrar até"), color="muted", bg="tile").pack(side="left")
        self.rows_var = tk.StringVar(win.top, "%d" % cards.DEFAULT_ROWS)
        rb = ttk.Combobox(opts, textvariable=self.rows_var, values=["%d" % n for n in cards.ROW_CHOICES], width=3,
                          state="readonly", style="An.TCombobox", font=win.f["text"])
        rb.pack(side="left", padx=6)
        rb.bind("<<ComboboxSelected>>", lambda e: self.save_options())
        win.label(opts, _("contadores"), color="muted", bg="tile").pack(side="left")
        self.flash_var = tk.BooleanVar(win.top, True)
        self.sound_var = tk.BooleanVar(win.top, False)
        for var, text in ((self.flash_var, _('Piscar "acabou"')), (self.sound_var, _("Som quando acabar (padrão)"))):
            tk.Checkbutton(opts, text=text, variable=var, command=self.save_options, bg=c["tile"], fg=c["fg"],
                           selectcolor=c["btn"], activebackground=c["tile"], activeforeground=c["fg"],
                           font=win.f["text"], highlightthickness=0).pack(side="left", padx=(16, 0))
        folder = tk.Frame(page, bg=c["tile"])
        folder.pack(side="bottom", fill="x", padx=10, pady=(2, 0))
        ttk.Button(folder, text=_("Pasta com os seus sons…"), style="An.TButton",
                   command=self.pick_folder).pack(side="left")
        self.folder_lbl = win.label(folder, "", "small", "muted", "tile", anchor="w", justify="left")
        self.folder_lbl.pack(side="left", fill="x", expand=True, padx=8)
        ui_parts.follow_wrap(folder, self.folder_lbl, 220, 160)
        # tudo do efeito escolhido na lista, junto: como aparece, onde olhar, temporizador e som
        each = self.each = tk.Frame(page, bg=c["panel"], padx=10, pady=5)
        each.pack(side="bottom", fill="x", padx=10, pady=(4, 2))
        top = tk.Frame(each, bg=c["panel"])
        top.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 2))
        each.columnconfigure(4, weight=1)
        self.each_title = win.label(top, "", "text", "muted", "panel", anchor="w")
        self.each_title.pack(side="left")
        self.remove_btn = ttk.Button(top, text=_("Remover"), style="An.TButton", command=self.remove_selected,
                                     state="disabled")
        self.remove_btn.pack(side="right")

        def box(row, col, label, var, values, width, on_pick, editable=False):
            win.label(each, label, color="muted", bg="panel").grid(row=row, column=col, sticky="w", padx=(0, 6), pady=1)
            b = ttk.Combobox(each, textvariable=var, state="disabled", width=width, values=values,
                             style="An.TCombobox", font=win.f["text"])
            b.grid(row=row, column=col + 1, sticky="w", padx=(0, 14), pady=1)
            b.bind("<<ComboboxSelected>>", lambda e: on_pick())
            if editable:
                b.bind("<Return>", lambda e: on_pick())
                b.bind("<FocusOut>", lambda e: on_pick())
            return b
        self.show_var = tk.StringVar(win.top, "")
        self.show_box = box(1, 0, _("Aparece como:"), self.show_var, [_(cards.SHOW_TEXT[m]) for m in cards.SHOWS],
                            12, self.show_selected)
        self.where_var = tk.StringVar(win.top, "")
        self.where_box = box(1, 2, _("Onde olhar:"), self.where_var, [], 14, self.where_selected)
        self.timer_var = tk.StringVar(win.top, "")
        self.timer_box = box(2, 0, _("Temporizador:"), self.timer_var,
                             [_("do jogo")] + [cards.timer_text(dict(secs=s)) for s in cards.TIMER_CHOICES], 8,
                             self.timer_selected, editable=True)
        self.snd_var = tk.StringVar(win.top, "")
        self.snd_box = box(3, 0, _("Tocar som:"), self.snd_var,
                           [_("padrão da aba")] + [_(cards.SOUND_TEXT[m]) for m in cards.SOUNDS], 15, self.sound_selected)
        self.before_var = tk.StringVar(win.top, "")
        self.before_box = box(3, 2, _("Segundos antes:"), self.before_var, ["%d s" % s for s in cards.BEFORE_CHOICES],
                              7, self.sound_selected, editable=True)
        self.kind_var = tk.StringVar(win.top, "")
        self.kind_box = box(4, 0, _("Som:"), self.kind_var, self.sound_names(), 15, lambda: self.sound_selected(play=True))
        self.tone_var = tk.StringVar(win.top, "")
        self.tone_box = box(4, 2, _("Tom:"), self.tone_var, [_(self.tone_name(t)) for t, _hz in itemping.TONES], 10,
                            lambda: self.sound_selected(play=True))
        self.play_btn = ttk.Button(each, text="▶ " + _("Ouvir"), style="An.TButton", state="disabled",
                                   command=self.play_selected)
        self.play_btn.grid(row=4, column=4, sticky="w", pady=1)
        # as duas listas dividem o espaço que sobra (a divisão dá para arrastar): com a janela baixa as duas
        # encolhem juntas, nenhuma some
        split = ttk.PanedWindow(page, orient="vertical", style="An.TPanedwindow")
        split.pack(fill="both", expand=True, padx=(8, 8), pady=(6, 2))
        found = tk.Frame(split, bg=c["tile"])
        mine = tk.Frame(split, bg=c["tile"])
        split.add(found, weight=1)
        split.add(mine, weight=1)
        self.t_found = Table(found, win, [("mark", "", 26, "center", "text"), ("name", _("Efeito"), 250, "w", "text"),
                                          ("group_txt", _("Tipo"), 170, "w", "text")], height=3,
                             on_select=lambda r: self.show_preview(("trackers", (r["kind"], r["id"])) if r else None))
        self.t_found.pack(fill="both", expand=True, pady=(0, 2))
        self.t_found.tree.bind("<Double-1>", lambda e: self.add_selected())
        head = tk.Frame(mine, bg=c["tile"])
        head.pack(fill="x", padx=2, pady=(4, 0))
        self.following = win.label(head, "", "head", bg="tile", anchor="w")
        self.following.pack(side="left")
        self.t_mine = Table(mine, win, [("name", _("Efeito"), 180, "w", "text"),
                                        ("where_txt", _("Onde olhar"), 95, "w", "text"),
                                        ("shows_txt", _("Onde aparece"), 95, "w", "text"),
                                        ("timer_txt", _("Temporizador"), 90, "w", "text"),
                                        ("sound_txt", _("Som"), 130, "w", "text")], height=3,
                            on_select=self.mine_selected)
        self.t_mine.pack(fill="both", expand=True, pady=(2, 0))

    def build_session(self, page):
        win, c = self.win, self.win.c
        self.ses_on = tk.BooleanVar(win.top, True)
        self.check(page, _("Mostrar o resumo quando a gravação parar"), self.ses_on,
                   lambda: self.toggle_system("session", self.ses_on.get()), font="head").pack(fill="x", padx=10,
                                                                                            pady=(10, 2))
        note = win.label(page, _("O cartão aparece assim que a gravação para: quando o jogo solta o arquivo do "
                                 "replay, é fechado ou começa outra gravação (ou, de reserva, com o replay 15 s sem "
                                 "crescer). O título é o destaque da sessão, com uma animação curta; embaixo vêm os "
                                 "outros destaques e as informações marcadas. Clique nele para abrir a análise; ele "
                                 "some quando você volta a lutar. Para ver de novo: menu do widget › Resumo da "
                                 "última sessão."), "small", "muted", "tile", anchor="w", justify="left")
        note.pack(fill="x", padx=10, pady=(0, 6))
        ui_parts.follow_wrap(page, note, 24, 200)
        opts = tk.Frame(page, bg=c["tile"])
        opts.pack(side="bottom", fill="x", padx=10, pady=(2, 8))
        self.ses_anim = tk.BooleanVar(win.top, True)
        self.check(opts, _("Animar o destaque (confete, moedinhas, estrelas, chuva...)"), self.ses_anim,
                   self.save_session_anim).pack(side="left")
        self.ses_fit = win.label(page, "", "small", "muted", "tile", anchor="w", justify="left")
        self.ses_fit.pack(side="bottom", fill="x", padx=10, pady=(2, 0))
        ui_parts.follow_wrap(page, self.ses_fit, 24, 200)
        split = ttk.PanedWindow(page, orient="vertical", style="An.TPanedwindow")
        split.pack(fill="both", expand=True, padx=8, pady=(4, 2))
        part_a = tk.Frame(split, bg=c["tile"])
        part_b = tk.Frame(split, bg=c["tile"])
        split.add(part_a, weight=1)
        split.add(part_b, weight=1)
        head = tk.Frame(part_a, bg=c["tile"])
        head.pack(fill="x", padx=2, pady=(2, 4))
        self.info_head = win.label(head, _("Informações"), "head", bg="tile")
        self.info_head.pack(side="left")
        for text, keys in ((_("Padrão"), session.DEFAULT), (_("Tudo"), session.KEYS), (_("Nada"), [])):
            self.chip(head, text, lambda k=keys: self.set_session(k))
        self.t_info = Table(part_a, win, [("mark", "", 26, "center", "text"), ("name", _("Informação"), 190, "w", "text"),
                                          ("example", _("Exemplo"), 330, "w", "text")], height=5,
                            on_select=self.info_selected)
        self.t_info.pack(fill="both", expand=True)
        self.marks(self.t_info, self.toggle_field)
        head = tk.Frame(part_b, bg=c["tile"])
        head.pack(fill="x", padx=2, pady=(6, 4))
        self.hl_head = win.label(head, _("Destaques"), "head", bg="tile")
        self.hl_head.pack(side="left")
        for text, keys in ((_("Todos"), session.HL_KEYS), (_("Nenhum"), [])):
            self.chip(head, text, lambda k=keys: self.set_highlights(k))
        self.t_hl = Table(part_b, win, [("mark", "", 26, "center", "text"), ("name", _("Destaque"), 190, "w", "text"),
                                        ("when", _("Quando aparece"), 330, "w", "text")], height=5,
                          on_select=self.hl_selected)
        self.t_hl.pack(fill="both", expand=True)
        self.marks(self.t_hl, self.toggle_highlight)

    # ------------------------------------------------------------ páginas e prévia

    def show_page(self, name):
        """Vai para uma das páginas: "system", "effects" ou "session"."""
        page = {"system": self.page_sys, "effects": self.page_fx, "session": self.page_ses}.get(name)
        if page is not None:
            self.pages.select(page)

    def page(self):
        try:
            cur = self.pages.select()
        except tk.TclError:
            return "system"
        return {str(self.page_sys): "system", str(self.page_fx): "effects", str(self.page_ses): "session"}.get(cur)

    def page_changed(self):
        name = self.page()
        if name == "session":
            self.show_preview(("system", "session"))
        elif name == "effects":
            row = self.t_mine.selected()
            self.show_preview(("trackers", (row["kind"], row["id"]) if row else None))
        else:
            row = self.t_sys.selected()
            self.show_preview(("system", row["key"] if row else "death"))

    def tracker_rows(self, pick=None, mode=None):
        """Linhas de exemplo dos contadores: os efeitos da lista (o escolhido primeiro), com tempos de mentira que
        correm na prévia. Sem nada na lista, o efeito escolhido na busca ou as duas primeiras sugestões. `mode`: como
        o efeito escolhido apareceria (o botão sob o mouse), sem mudar nada de verdade."""
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
            total = None if area else (t.get("secs") or 0) * 1000 or 20000 + 10000 * (i % 3)
            lft = None if area else min(total, left[i % len(left)])
            rows.append(dict(key="%s:%d" % (t["kind"], t["id"]), name=cards.name_of(t), where=t["where"],
                             target="Betelgeuse" if t["where"] == "target" else None,
                             left=lft, total=total, off=(total - lft) if total else i * 7000,
                             since=42000, boss=False, mob=BETEL if t["where"] == "target" else None,
                             show=t.get("show", "counter")))
        if pick is not None:
            rows = rows[:1]                        # um efeito escolhido: a prévia mostra só ele, no modo dele
        fixed = self.fixed()
        first = rows[0]["key"] if rows and pick is not None else None
        extra = None
        if mode and first:                         # o botão sob o mouse: o escolhido nesse modo, só na prévia
            fixed.discard(first)
            rows[0]["show"] = "counter" if mode == "pin" else mode
            if mode == "pin":
                fixed.add(first)
                extra = first
        pinned = {r["key"]: r for r in rows if r["key"] in fixed}
        rest = [r for r in rows if r["key"] not in fixed]
        fx = [r for r in rest if r["show"] == "card"]
        rows = [r for r in rest if r["show"] != "card"]
        if pick is not None:                       # na faixa fixa, só o escolhido (os outros fixados ficam de fora)
            extra = extra or (first if first in fixed else None)
        return rows, pinned, fx, example, extra

    def fixed(self):
        """As chaves ("status:730") dos efeitos fixados na faixa fixa."""
        return {p[3:] for p in (self.cfg().get("pins") or []) if p.startswith("fx:")}

    def show_preview(self, what):
        if what is None:
            return
        self.pv_what = what
        if what[0] == "system":
            _rows, pinned, _fx, _example, _extra = self.tracker_rows(None)
            name = next((_(n) for k, n, _t, _c in cards.SYSTEM if k == what[1]), "")
            self.pv_title.configure(text=_("Prévia: %s") % name)
            self.mode_bar.pack_forget()
            self.mode_text.pack_forget()
            data = None
            if what[1] == "session":
                # sempre o exemplo (a aba é para ver como cada cartão fica e escolher se quer; o usuário, 2026-11-20:
                # "Não precisa conter dados dos replays gravados"): o do destaque escolhido, o da informação escolhida
                # (com a linha dela acesa, mesmo desmarcada) ou, sem nada escolhido, o das escolhas de agora
                key, info = getattr(self, "pv_hl", None), getattr(self, "pv_info", None)
                if key:
                    data = self.sample_for(key)
                    name = next((n for k, n, _w in session.HIGHLIGHTS if k == key), None)
                    if name:
                        self.pv_title.configure(text=_("Prévia: %s") % _(name))
                        # quando aparece (e, nas versões dos cartões de classe, a animação): na lista ele fica cortado
                        self.mode_text.configure(text=session.hl_text(key)[1])
                        self.mode_text.pack(fill="x", pady=(0, 6), before=self.pv_scroll.canvas.master)
                elif info:
                    data = session.sample_card_info(self.cfg(), info)
                    name = _(dict(session.FIELDS).get(info, info))
                    self.pv_title.configure(text=(_("Prévia: %s (desmarcada)") if data.get("focus_off") else
                                                  _("Prévia: %s")) % name)
            self.preview.show(what, [], pinned, session_data=data)
            return
        pick = what[1]
        rows, pinned, fx, example, extra = self.tracker_rows(pick, self.mode_hover if pick else None)
        if pick is None:
            self.pv_title.configure(text=_("Prévia: contadores (exemplo)") if example else
                                    _("Prévia: os efeitos acompanhados"))
        else:
            e = cards.entry(*pick)
            self.pv_title.configure(text=_("Prévia: %s") % (cards.short_name(e["name"]) if e else pick[1]))
        self.show_modes(pick)
        self.preview.show(("trackers", None), rows, pinned, fx, extra_pin=extra)

    def show_modes(self, pick):
        """Os botões dos três modos, com o atual do efeito escolhido em destaque e o texto do modo sob o mouse."""
        c = self.win.c
        self.mode_bar.pack(fill="x", pady=(0, 2), before=self.pv_scroll.canvas.master)
        self.mode_text.pack(fill="x", pady=(0, 6), before=self.pv_scroll.canvas.master)
        cur = self.current_mode(pick)
        for mode, b in self.mode_btns.items():
            on = mode == cur
            b.configure(bg=c["accent"] if on else c["btn"], fg="#ffffff" if on else c["fg"],
                        cursor="hand2" if pick else "arrow")
        shown = self.mode_hover or cur or "counter"
        text = _(MODE_TEXT[shown])
        if not pick:
            text += " " + _("Escolha um efeito para trocar o modo dele.")
        self.mode_text.configure(text=text)

    def current_mode(self, pick):
        if pick is None:
            return None
        e = cards.entry(*pick)
        ids = set(e["ids"]) if e else {pick[1]}
        key = next(("%s:%d" % (t["kind"], t["id"]) for t in cards.tracked(self.cfg())
                    if t["kind"] == pick[0] and t["id"] in ids), None)
        if key is None:
            return None
        if key in self.fixed():
            return "pin"
        return next((t["show"] for t in cards.tracked(self.cfg()) if t["kind"] == pick[0] and t["id"] in ids),
                    "counter")

    def hover_mode(self, mode):
        """Mouse num dos botões de modo: a prévia mostra o efeito escolhido nesse modo (sem mudar nada)."""
        self.mode_hover = mode
        if self.pv_what[0] == "trackers":
            self.show_preview(self.pv_what)

    def pick_mode(self, mode):
        """Clique num dos botões: o efeito escolhido passa a aparecer nesse modo (entra na lista se não estava)."""
        what = self.pv_what
        if what[0] != "trackers" or what[1] is None:
            return
        kind, ident = what[1]
        self.mode_hover = None
        self.sig = None
        self.win.app.set_fx_show(kind, ident, mode)

    def sample_for(self, key):
        """O cartão de exemplo com o destaque `key` no título; o personagem da cena é o da gravação aberta (como no
        cartão de verdade, que mostra quem grava de qualquer classe); nos cartões de classe, só quando a classe dele
        serve para o cartão."""
        c = self.win.combat() if hasattr(self.win, "combat") else None
        look = None
        if c is not None and getattr(c.session, "look", None):
            job = getattr(c.session, "job", 0)
            look = dict(c.session.look)
            if not look.get("job"):
                look["job"] = job
            if key in session.ROLE_KEYS:      # os cartões de classe: quem grava, se a classe dele serve para o cartão
                jobs = session.ROLE_JOBS[key][1]
                if jobs is not None and job not in jobs:
                    look = None
        try:
            return session.sample_card_for(self.cfg(), key, look)
        except (KeyError, ValueError):
            return None

    # ------------------------------------------------------------ ações

    def cfg(self):
        return self.win.app.cfg

    def saved(self):
        app = self.win.app
        app.save()
        app.dirty = True
        self.sig = None
        self.refresh()

    def toggle_system(self, key, on):
        cards.set_enabled(self.cfg(), key, bool(on))
        self.pv_what = ("system", key)
        self.saved()

    def set_all_system(self, on):
        """Ligar todos / Desligar todos os cartões do programa."""
        cfg = self.cfg()
        for key, _n, _t, _c in cards.SYSTEM:
            cards.set_enabled(cfg, key, on)
        self.saved()

    def sys_selected(self, row):
        """Escolheu um cartão do programa: a prévia dele e, embaixo, ligado/desligado e o som (os que têm)."""
        if row is None:
            self.sys_title.configure(text=_("Escolha um cartão na lista acima para ver as opções dele."))
            self.sys_desc.configure(text="")
            self.sys_on_cb.configure(state="disabled")
            self.sys_snd.pack_forget()
            self.sys_link.pack_forget()
            return
        key = row["key"]
        cfg = self.cfg()
        self.show_preview(("system", key))
        self.sys_title.configure(text=row["name"])
        self.sys_desc.configure(text=row["when"] + " · " + row["stay"])
        self.sys_on_cb.configure(state="normal")
        self.sys_on.set(cards.enabled(cfg, key))
        spec = SYS_SOUNDS.get(key)
        if spec:
            on_key, vol_key, kind = spec
            self.sys_snd_on.set(bool(cfg.get(on_key)))
            vols = itemping.VOLUMES if kind == "ping" else self.mod().CHIME_VOLUMES
            self.sys_vol_box.configure(values=["%d%%" % v for v in vols])
            self.sys_vol.set("%d%%" % int(cfg.get(vol_key) or 40))
            if kind == "ping":
                self.sys_tone_lbl.pack(side="left", padx=(14, 4))
                self.sys_tone_box.pack(side="left")
                self.sys_tone.set(_(self.tone_name(cfg.get("ping_tone") or itemping.DEFAULT_TONE)))
            else:
                self.sys_tone_lbl.pack_forget()
                self.sys_tone_box.pack_forget()
            self.sys_snd.pack(fill="x", pady=(4, 0))
        else:
            self.sys_snd.pack_forget()
        if key == "session":
            self.sys_link.pack(fill="x", pady=(4, 0))
        else:
            self.sys_link.pack_forget()

    def sys_on_changed(self):
        row = self.t_sys.selected()
        if row is not None:
            self.toggle_system(row["key"], self.sys_on.get())

    def mod(self):
        return sys.modules[type(self.win.app).__module__]

    def sys_sound_changed(self, play=False):
        """O som do cartão escolhido: liga/desliga, volume e (no item marcado) o tom."""
        row = self.t_sys.selected()
        spec = SYS_SOUNDS.get(row["key"]) if row else None
        if not spec:
            return
        on_key, vol_key, kind = spec
        cfg = self.cfg()
        cfg[on_key] = bool(self.sys_snd_on.get())
        try:
            cfg[vol_key] = int(self.sys_vol.get().rstrip("%"))
        except ValueError:
            pass
        if kind == "ping":
            tone = next((t for t, _hz in itemping.TONES if _(self.tone_name(t)) == self.sys_tone.get()), None)
            if tone:
                cfg["ping_tone"] = tone
        self.saved()
        if play:
            self.sys_play_sound()

    def sys_play_sound(self):
        row = self.t_sys.selected()
        spec = SYS_SOUNDS.get(row["key"]) if row else None
        if not spec:
            return
        _on, vol_key, kind = spec
        mod, cfg = self.mod(), self.cfg()
        vol = int(cfg.get(vol_key) or 40)
        if kind == "chime":
            mod.play_chime(vol)
        elif kind == "ping":
            mod.play_ping(vol, cfg.get("ping_tone"))
        else:
            mod.play_beep(vol)

    def toggle_field(self, key):
        """Liga/desliga uma informação do resumo da sessão (a ordem do cartão é sempre a da lista)."""
        want = set(session.chosen(self.cfg()))
        want ^= {key}
        self.set_session([k for k in session.KEYS if k in want])

    def toggle_highlight(self, key):
        off = {k for k in session.HL_KEYS if k not in session.hl_chosen(self.cfg())}   # o antigo "card" já convertido
        off ^= {key}
        self.set_highlights([k for k in session.HL_KEYS if k not in off])

    def hl_selected(self, row):
        """Escolheu um destaque: a prévia mostra o cartão com ele no título, com a animação dele (a cena de luta usa o
        personagem da gravação aberta, se for de uma classe de punho). A lista de informações perde a seleção: a
        prévia segue esta lista."""
        if row is None:               # a seleção saiu (escolheram uma informação): a prévia fica com a de lá
            return
        self.pv_hl, self.pv_info = row["key"], None
        clear_selection(self.t_info)
        self.show_preview(("system", "session"))

    def info_selected(self, row):
        """Escolheu uma informação: a prévia mostra o cartão de exemplo com a linha dela acesa (mesmo desmarcada, para
        ver como ficaria), animando como nos destaques. Antes mostrava o cartão da gravação aberta, igual em todo
        clique (com a do 250 de um amigo, sempre o "Nível máximo"; o usuário, 2026-11-20). A lista de destaques perde
        a seleção."""
        if row is None:               # a seleção saiu (escolheram um destaque): a prévia fica com o de lá
            return
        self.pv_hl, self.pv_info = None, row["key"]
        clear_selection(self.t_hl)
        self.show_preview(("system", "session"))

    def set_highlights(self, keys):
        self.cfg()["session_hl_off"] = [k for k in session.HL_KEYS if k not in keys]
        self.pv_what = ("system", "session")
        self.saved()

    def save_session_anim(self):
        self.cfg()["session_anim"] = bool(self.ses_anim.get())
        self.pv_what = ("system", "session")
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

    def pick_folder(self):
        self.win.app.pick_sound_folder()
        self.sig = None
        self.refresh()

    def sound_names(self):
        """Os nomes da caixa "Som": os do programa e os da pasta da pessoa."""
        return ([_(sounds.NAMES[k]) for k in sounds.KEYS]
                + [name for _k, name in sounds.custom_sounds(self.cfg().get("sound_folder"))])

    def sound_key(self, name):
        """A chave do som pelo nome mostrado na caixa "Som"."""
        k = next((k for k in sounds.KEYS if _(sounds.NAMES[k]) == name), None)
        return k or next((k for k, n in sounds.custom_sounds(self.cfg().get("sound_folder")) if n == name), None)

    def mine_selected(self, row):
        """Escolheu um efeito acompanhado: as caixas "Aparece como", "Temporizador" e "Som" passam a valer
        para ele."""
        boxes = (self.show_box, self.where_box, self.timer_box, self.snd_box, self.kind_box, self.tone_box)
        if row is None:
            for b in boxes + (self.before_box,):
                b.configure(state="disabled")
            for b in (self.play_btn, self.remove_btn):
                b.configure(state="disabled")
            self.each_title.configure(text=_("Escolha um efeito na lista acima para mudar as opções dele."))
            return
        for b in boxes:
            b.configure(state="readonly")
        self.timer_box.configure(state="normal")           # dá para digitar outro número de segundos
        for b in (self.play_btn, self.remove_btn):
            b.configure(state="normal")
        t = row["t"]
        self.each_title.configure(text=_("Opções de %s") % row["name"])
        self.show_var.set(_(cards.SHOW_TEXT[row["show"]]))
        order = self.where_order(row)
        self.where_box.configure(values=[cards.where_text(dict(t, where=w)) for w in order])
        self.where_var.set(cards.where_text(t))
        self.timer_var.set(cards.timer_text(t))
        self.snd_var.set(_(cards.SOUND_TEXT[t["sound"]]) if t["sound"] else _("padrão da aba"))
        self.before_var.set("%d s" % t["before"])
        self.before_box.configure(state="normal" if t["sound"] == "before" else "disabled")
        self.kind_box.configure(values=self.sound_names())
        self.kind_var.set(_(sounds.NAMES[t["snd"]]) if t["snd"] in sounds.NAMES else sounds.label(t["snd"]))
        self.tone_var.set(_(self.tone_name(t["tone"])))
        self.tone_box.configure(state="disabled" if sounds.is_custom(t["snd"]) else "readonly")   # o som é o do arquivo
        if self.page() == "effects":
            self.show_preview(("trackers", (row["kind"], row["id"])))

    @staticmethod
    def where_order(row):
        return ("any", "me") if row["kind"] == "area" else ("me", "target")

    def where_selected(self):
        row = self.t_mine.selected()
        if row is None:
            return
        pick = next((w for w in self.where_order(row) if cards.where_text(dict(row["t"], where=w))
                     == self.where_var.get()), None)
        if pick and pick != row["where"]:
            cards.track(self.cfg(), row["kind"], row["id"], on=True, where=pick)
            self.pv_what = ("trackers", (row["kind"], row["id"]))
            self.saved()

    @staticmethod
    def tone_name(tone):
        return {"grave": "Grave", "medio": "Médio", "agudo": "Agudo", "bem agudo": "Bem agudo"}.get(tone, tone)

    def timer_selected(self):
        """Temporizador do efeito escolhido: "do jogo", uma das opções ou um número de segundos digitado."""
        row = self.t_mine.selected()
        if row is None:
            return
        text = self.timer_var.get().strip()
        secs = 0
        if text and text != _("do jogo"):
            secs = cards.parse_secs(text, 1, cards.MAX_TIMER_S)
            if secs is None:
                self.timer_var.set(cards.timer_text(row["t"]))
                return
        self.pv_what = ("trackers", (row["kind"], row["id"]))
        self.sig = None
        self.win.app.set_fx_option(row["kind"], row["id"], secs=secs)

    def sound_selected(self, play=False):
        """Som do efeito escolhido: quando toca, quantos segundos antes (qualquer número de 1 s a 10 min), qual som e
        o tom."""
        row = self.t_mine.selected()
        if row is None:
            return
        mode = next((m for m in cards.SOUNDS if _(cards.SOUND_TEXT[m]) == self.snd_var.get()), None)
        tone = next((t for t, _hz in itemping.TONES if _(self.tone_name(t)) == self.tone_var.get()), None)
        snd = self.sound_key(self.kind_var.get())
        before = cards.parse_secs(self.before_var.get(), 1, cards.MAX_BEFORE_S)
        if before is None:
            self.before_var.set("%d s" % row["t"]["before"])
        self.pv_what = ("trackers", (row["kind"], row["id"]))
        self.sig = None
        if mode is None and play:                         # escolheu o som com o padrão da aba: passa a tocar
            mode = "end"                                  # ao acabar, que era o que o padrão faria
        self.win.app.set_fx_option(row["kind"], row["id"], play=play or (mode not in (None, "off")
                                                                          and mode != row["t"]["sound"]),
                                   sound=mode, before=before, tone=tone, snd=snd)

    def play_selected(self):
        row = self.t_mine.selected()
        if row is not None:
            import dpsmeter
            dpsmeter.play_sound(cards.voice(row["t"]), self.cfg().get("tracker_volume", 40))

    def show_selected(self):
        row = self.t_mine.selected()
        mode = next((m for m in cards.SHOWS if _(cards.SHOW_TEXT[m]) == self.show_var.get()), None)
        if row is not None and mode and mode != row["show"]:
            self.pv_what = ("trackers", (row["kind"], row["id"]))
            self.sig = None
            self.win.app.set_fx_show(row["kind"], row["id"], mode)

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

    def set_session(self, keys):
        self.cfg()["session_fields"] = [k for k in session.KEYS if k in keys]
        self.pv_what = ("system", "session")
        self.saved()

    # ------------------------------------------------------------ telas

    def fill_system(self):
        """A tabela dos cartões do programa (✓ ligado), e as opções do escolhido."""
        cfg = self.cfg()
        rows = []
        for key, name, text, _c in cards.SYSTEM:
            on = cards.enabled(cfg, key)
            stay = self.stay_text(key)
            spec = SYS_SOUNDS.get(key)
            if spec and cfg.get(spec[0]):
                stay += " · " + _("com som")
            rows.append(dict(key=key, mark="✓" if on else " ", name=_(name), when=_(text), stay=stay))
        self.t_sys.set_rows(rows, lambda r: r["key"], lambda r: [] if r["mark"].strip() else ["muted"])
        self.sys_selected(self.t_sys.selected())

    def stay_text(self, key):
        """Quanto tempo o cartão fica no widget."""
        m = self.mod()
        secs = {"death": m.DEATH_CARD_S, "summary": m.SUMMARY_CARD_S, "ping": m.PING_CARD_S,
                "miracle": m.MIRACLE_BANNER_S, "buff_end": m.ALERT_S, "death_foot": m.ALERT_S}
        if key == "damage_heal":
            return _("%d s (o efeito todo)") % m.MECH_SECS["heal_phys"]
        if key in cards.BOSS_KEYS:
            return "%d s" % m.BOSS_CARD_S
        if key in secs:
            return "%d s" % secs[key]
        return {"session": _("até fechar (10 min no máximo)"), "fusion": _("enquanto o HP estiver baixo"),
                "rec": _("até voltar a gravar"), "follow": _("até você escolher")}.get(key, "")

    def fill_results(self):
        group = next((g for g in cards.GROUPS if _(g) == self.group.get()), None)
        cfg = self.cfg()
        rows = [dict(key="%s:%d" % (r["kind"], r["id"]), kind=r["kind"], id=r["id"], name=r["name"],
                     group_txt=_(r["group"]), mark="✓" if cards.is_tracked(cfg, r["kind"], r["id"]) else " ")
                for r in cards.search(self.query.get(), group)]
        self.t_found.set_rows(rows, lambda r: r["key"], lambda r: ["good"] if r["mark"].strip() else [])

    def refresh(self, c=None):
        cfg = self.cfg()
        folder = cfg.get("sound_folder") or ""
        sig = (repr(cfg.get("trackers")), repr(cfg.get("cards_off")), tuple(cfg.get(s[3]) for s in cards.SYSTEM if s[3]),
               cfg.get("alert_boss"), cfg.get("tracker_rows"), cfg.get("tracker_flash"), cfg.get("tracker_sound"),
               len(cards.catalog()), cfg.get("theme"), repr(cfg.get("pins")), repr(cfg.get("session_fields")),
               cfg.get("width"), cfg.get("rows"), cfg.get("scale"), folder, len(sounds.custom_sounds(folder)),
               repr(cfg.get("session_hl_off")), cfg.get("session_anim"),
               tuple(cfg.get(k) for spec in SYS_SOUNDS.values() for k in spec[:2]), cfg.get("ping_tone"))
        if sig == self.sig:
            return
        self.sig = sig
        self.fill_system()
        self.ses_on.set(cards.enabled(cfg, "session"))
        self.ses_anim.set(bool(cfg.get("session_anim", True)))
        want = session.chosen(cfg)
        demo = session.sample_texts()
        self.t_info.set_rows([dict(key=k, mark="✓" if k in want else " ", name=_(n), example=demo.get(k, ""))
                              for k, n in session.FIELDS], lambda r: r["key"],
                             lambda r: [] if r["mark"].strip() else ["muted"])
        self.info_head.configure(text=_("Informações (%d de %d)") % (len(want), len(session.FIELDS)))
        hl_on = set(session.hl_chosen(cfg))
        rows = []
        for k in session.HL_KEYS:
            name, when = session.hl_text(k)
            rows.append(dict(key=k, mark="✓" if k in hl_on else " ", name="%s  %s" % (session.EMBLEMS.get(k, ""), name),
                             when=when))
        self.t_hl.set_rows(rows, lambda r: r["key"], lambda r: [] if r["mark"].strip() else ["muted"])
        self.hl_head.configure(text=_("Destaques (%d de %d)") % (len(hl_on), len(session.HL_KEYS)))
        data = self.preview.session_data or session.sample_card(cfg)
        fit = self.preview.p.session_fit(data)
        self.ses_fit.configure(text=_("No seu widget agora cabem %d linhas de informações no cartão (com %d linhas no "
                                      "widget); o que passar disso vira \"mais N\". Para caber mais, aumente o widget "
                                      "pelo canto.") % (fit, cfg["rows"]) if len(want) > fit else
                               _("No seu widget agora cabem %d linhas de informações no cartão: tudo o que está "
                                 "marcado aparece.") % fit)
        tr = cards.tracked(cfg)
        fixed = self.fixed()
        rows = []
        for t in tr:
            e = cards.entry(t["kind"], t["id"])
            key = "%s:%d" % (t["kind"], t["id"])
            show = "pin" if key in fixed else t["show"]
            snd = cards.sound_text(cfg, t)
            if cards.sound_of(cfg, t) != "off" and t.get("sound"):
                snd += " · " + (_(sounds.NAMES[t["snd"]]) if t["snd"] in sounds.NAMES else sounds.label(t["snd"]))
            rows.append(dict(key=key, kind=t["kind"], id=t["id"], where=t["where"], t=t,
                             name=cards.name_of(t), group_txt=_(e["group"]) if e else "",
                             where_txt=cards.where_text(t), show=show, shows_txt=_(cards.SHOW_TEXT[show]),
                             timer_txt=cards.timer_text(t), sound_txt=snd))
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
        mine = sounds.custom_sounds(folder)
        self.folder_lbl.configure(text=(_("%s: %d som(ns). WAV ou MP3, até 10 MB cada; toca no máximo 10 s; o volume "
                                          "vale, o tom não.") % (folder, len(mine))) if folder else
                                  _("Sons seus: escolha uma pasta com .wav ou .mp3 (até 10 MB cada; toca no máximo "
                                    "10 s). Eles aparecem em \"Som\" e no botão direito dos itens."))
        self.fill_results()
        width = self.preview.p.W + int(30 * self.win.dpi)
        self.pv_note.configure(wraplength=width)
        self.mode_text.configure(wraplength=width)
        self.show_preview(self.pv_what)
