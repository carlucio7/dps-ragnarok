# -*- coding: utf-8 -*-
"""Medidor de DPS do Ragnarok: lê a gravação de replay (.rrf) enquanto ela é escrita.

No jogo, comece a gravar um replay; o medidor encontra o arquivo novo na pasta
Replay sozinho e mostra o dano em tempo real.

Tudo é feito com o mouse (sem teclas de atalho), e clicar no widget não tira o
foco do jogo: as teclas continuam indo para o Ragnarok. Passe o mouse sobre um
botão para ver o que ele faz no rodapé; o botão direito abre todas as opções.
"""

import ctypes
import json
import os
import subprocess
import sys
import time
import traceback
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

import clientdata
import meter
import testes
from analysis_ui import AnalysisWindow
from fmt import num, dur
import i18n
from i18n import _
from version import VERSION

IS_WIN = os.name == "nt"
WS_EX_NOACTIVATE = 0x08000000

CONFIG_PATH = os.environ.get("RODPS_CONFIG") or os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), "RODpsMeter", "config.json")
RES_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

# Medidas de base (escala 100%, 96 dpi)
BASE_W = 300            # largura padrão (o usuário pode mudar arrastando o canto)
MIN_W, MAX_W = 230, 640
MIN_ROWS, MAX_ROWS = 2, 20
TOP_Y = 15
BIG_Y = 50
TABS_Y0, TABS_Y1 = 76, 96
ROWS_Y0, ROW_H = 102, 21
FOOT_H = 28
MIN_SCALE, MAX_SCALE = 0.7, 2.5
FONT_PX = {"big": 30, "big_s": 23, "unit": 11, "title": 12, "text": 11, "small": 10, "num": 12, "icon": 11, "tab": 11}
MIN_FONT_PX = 8
ALERT_S = 7.0          # quanto tempo um aviso fica no rodapé
POLL_MS = 150         # ler o pedaço novo do arquivo custa < 1 ms

THEMES = {
    "Grafite":    dict(bg="#1e1f24", btn="#2d2f37", fg="#f2f3f5", muted="#8b8f99", accent="#5b9cff", live="#ff5c5c"),
    "Meia-noite": dict(bg="#0f1729", btn="#1c2742", fg="#e8eefc", muted="#7d8bb0", accent="#38bdf8", live="#7dd3fc"),
    "Roxo":       dict(bg="#1d1430", btn="#2e2249", fg="#f3ecff", muted="#9a8bbd", accent="#a78bfa", live="#e879f9"),
    "Floresta":   dict(bg="#0f1f17", btn="#1c3427", fg="#e9f7ee", muted="#7fa58e", accent="#34d399", live="#bef264"),
    "Oceano":     dict(bg="#0b2129", btn="#153641", fg="#e6f6f8", muted="#79a3ab", accent="#2dd4bf", live="#67e8f9"),
    "Vinho":      dict(bg="#2a0f1a", btn="#421b2c", fg="#fdeef3", muted="#b58799", accent="#f472b6", live="#fb7185"),
    "Âmbar":      dict(bg="#24180a", btn="#3b2911", fg="#fff4e3", muted="#b39a78", accent="#f59e0b", live="#fde047"),
    "Neon":       dict(bg="#07070b", btn="#17171f", fg="#f5f5ff", muted="#7a7a99", accent="#22ff88", live="#ff2bd6"),
    "Claro":      dict(bg="#f6f7f9", btn="#e3e6eb", fg="#1d2129", muted="#6b7280", accent="#2563eb", live="#ef4444"),
}

SIZES = [(0.8, _("Pequeno")), (1.0, _("Médio")), (1.3, _("Grande")), (1.7, _("Muito grande"))]
ALPHAS = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5]
ROW_CHOICES = [4, 6, 8, 10, 12]
WIDTHS = [(260, _("estreita")), (300, _("normal")), (380, _("larga")), (480, _("muito larga"))]
GAP_CHOICES = [(5, _("5 segundos sem dano")), (10, _("10 segundos sem dano")), (15, _("15 segundos sem dano")),
               (30, _("30 segundos sem dano")), (60, _("1 minuto sem dano"))]
TARGET_CHOICES = [("all", _("Todos os monstros")), ("mvp", _("Só MVPs e bonecos de treino"))]
HINTS = {
    "pin": _("Fixar sempre por cima das outras janelas"), "chart": _("Análise completa (abre outra janela)"),
    "more": _("Opções"), "min": _("Minimizar"), "close": _("Fechar o medidor"), "reset": _("Zerar: começa a contar de novo"),
    "view": _("Escolher o que mostrar: tudo ou uma luta"), "prev": _("Luta anterior"), "next": _("Próxima luta"),
    "group": _("Dano de cada jogador"), "skills": _("O seu dano por skill"), "targets": _("Em quem você bateu"),
    "grip": _("Arraste para mudar a largura e o número de linhas"),
}
TABS = [("group", _("Grupo")), ("skills", _("Skills")), ("targets", _("Alvos"))]

ICONS = {
    "pin_on": ("\uE840", "📌"), "pin_off": ("\uE718", "📌"), "more": ("\uE712", "⋯"),
    "min": ("\uE921", "–"), "close": ("\uE8BB", "✕"), "reset": ("\uE72C", "↻"),
    "prev": ("\uE76B", "‹"), "next": ("\uE76C", "›"), "file": ("\uE8E5", "📂"),
    "chart": ("\uE9D2", "📊"),
}

CONFIG_VERSION = 2
DEFAULTS = {
    "theme": "Grafite", "scale": 1.0, "alpha": 0.92, "pinned": True,
    "rows": 6, "gap_s": 15, "tab": "group", "session": True, "show_pct": False,
    "folder": None, "x": None, "y": None, "v": CONFIG_VERSION, "width": BASE_W,
    "an_geometry": None, "an_tab": 0, "an_zoom": 1.0,
    "auto_tests": True, "alert_buffs": True, "alert_death": True, "alert_fusion": True, "targets": "all",
    "lang": None,          # None = idioma do Windows
}


# ---------------------------------------------------------------- utilidades

def short_path(path, keep=2):
    """C:\Gravity\Ragnarok\Replay -> …\Ragnarok\Replay (cabe no widget)."""
    parts = os.path.normpath(path).split(os.sep)
    return path if len(parts) <= keep + 1 else "…" + os.sep + os.sep.join(parts[-keep:])


def _rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return _hex([x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b))])


def luminance(h):
    r, g, b = (v / 255 for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def on_color(h):
    return "#16181d" if luminance(h) > 0.55 else "#ffffff"


def shade(h, amount):
    return mix(h, "#ffffff" if luminance(h) < 0.5 else "#000000", amount)


def round_rect_pts(x1, y1, x2, y2, r):
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
            x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            cfg.update({k: v for k, v in saved.items() if k in DEFAULTS})
            if saved.get("v", 1) < 2:
                # v2: Sessão virou o padrão e a pausa padrão subiu para 15 s
                cfg["session"] = True
                if cfg["gap_s"] in (0, 10):
                    cfg["gap_s"] = 15
                cfg["v"] = CONFIG_VERSION
    except (OSError, ValueError):
        pass
    if cfg["theme"] not in THEMES:
        cfg["theme"] = DEFAULTS["theme"]
    if cfg["tab"] not in dict(TABS):
        cfg["tab"] = "group"
    if cfg["targets"] not in dict(TARGET_CHOICES):
        cfg["targets"] = "all"
    if not cfg["gap_s"]:
        cfg["gap_s"] = 15
    return cfg


# ---------------------------------------------------------------- Windows

if IS_WIN:
    user32 = ctypes.windll.user32
    user32.GetParent.restype = ctypes.c_void_p
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.MonitorFromPoint.restype = ctypes.c_void_p
    user32.MonitorFromPoint.argtypes = [_POINT, ctypes.c_uint]


def dwm_set(hwnd, attr, value):
    if not IS_WIN or not hwnd:
        return False
    try:
        v = ctypes.c_uint(value)
        return ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), attr, ctypes.byref(v), ctypes.sizeof(v)) == 0
    except (OSError, AttributeError):
        return False


# ---------------------------------------------------------------- app

class DpsApp:
    def __init__(self, root, open_path=None):
        self.root = root
        self.cfg = load_config()
        self.watcher = meter.Watcher(self.cfg["folder"], self.gap_ms(), self.cfg["targets"])
        # nomes do jogo no idioma escolhido (da instalação; com o cache leva ~0,1 s, na 1ª vez alguns segundos)
        clientdata.NAMES.load()
        self.names_v = clientdata.NAMES.version
        self.press_xy = None
        self.enc_back = 0                   # 0 = encontro atual, 1 = anterior...
        self.hover = self.pressed = self.drag = self.resize = None
        self.hwnd = None
        self.menu = None
        self.menu_refs = []
        self.last_draw = 0.0
        self.dirty = True
        self.phase = 0
        self.analysis = None
        self.tests = testes.Store(os.path.join(os.path.dirname(CONFIG_PATH), "testes.json"))
        self.tests_seen = set()       # encontros já avaliados para o salvamento automático
        self.last_autosave = 0.0
        self.alert = None             # (texto, tipo, quando apareceu)
        self.alert_seen = 0

        root.title(_("DPS Ragnarok"))
        root.report_callback_exception = self.log_error
        root.overrideredirect(True)
        self.dpi = root.winfo_fpixels("1i") / 96.0
        self.make_fonts()
        ico = os.path.join(RES_DIR, "dpsmeter.ico")
        if IS_WIN and os.path.isfile(ico):
            try:
                root.iconbitmap(default=ico)
            except tk.TclError:
                pass

        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        c = self.canvas
        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<Motion>", self.on_motion)
        c.bind("<Leave>", lambda e: self.set_hover(None))
        c.bind("<Button-3>", self.on_right_click)
        c.bind("<MouseWheel>", self.on_wheel)
        root.protocol("WM_DELETE_WINDOW", self.quit)

        w, h = self.size_px()
        x, y = self.initial_pos(w, h)
        root.geometry("%dx%d+%d+%d" % (w, h, x, y))
        root.attributes("-topmost", bool(self.cfg["pinned"]))
        root.attributes("-alpha", float(self.cfg["alpha"]))
        if open_path:
            self.watcher.open(open_path)
        self.draw()
        root.after(10, self.setup_native)
        root.after(50, self.tick)

    # ------------------------------------------------------------ base

    @property
    def s(self):
        return self.cfg["scale"] * self.dpi

    def gap_ms(self):
        g = self.cfg["gap_s"]
        return int(g * 1000) if g else 10 ** 12

    def base_w(self):
        try:
            return max(MIN_W, min(MAX_W, int(self.cfg.get("width") or BASE_W)))
        except (TypeError, ValueError):
            return BASE_W

    def size_px(self):
        h = ROWS_Y0 + self.cfg["rows"] * ROW_H + 6 + FOOT_H
        return int(round(self.base_w() * self.s)), int(round(h * self.s))

    def icon(self, name):
        glyph, fallback = ICONS[name]
        return glyph if self.has_icons else fallback

    def make_fonts(self):
        fams = set(tkfont.families(self.root))

        def pick(*names):
            return next((n for n in names if n in fams), names[-1])

        icon_fam = pick("Segoe Fluent Icons", "Segoe MDL2 Assets")
        self.has_icons = icon_fam in fams
        semi = pick("Segoe UI Semibold", "Segoe UI", "Arial")
        ui = pick("Segoe UI", "Arial")
        nums = pick("Bahnschrift SemiBold", "Bahnschrift", "Segoe UI Semibold", "Arial")
        self.fonts = {
            "big": tkfont.Font(self.root, family=nums),
            "big_s": tkfont.Font(self.root, family=nums),
            "unit": tkfont.Font(self.root, family=semi),
            "title": tkfont.Font(self.root, family=semi),
            "text": tkfont.Font(self.root, family=ui),
            "small": tkfont.Font(self.root, family=ui),
            "num": tkfont.Font(self.root, family=nums),
            "icon": tkfont.Font(self.root, family=icon_fam),
            "tab": tkfont.Font(self.root, family=semi),
        }
        self.size_fonts()

    def size_fonts(self):
        for key, px in FONT_PX.items():
            self.fonts[key].configure(size=-max(MIN_FONT_PX, int(round(px * self.s))))

    def theme(self):
        t = dict(THEMES.get(self.cfg["theme"], THEMES["Grafite"]))
        t["edge"] = mix(t["bg"], t["fg"], 0.10)
        t["track"] = mix(t["bg"], t["fg"], 0.07)
        t["bar"] = mix(t["bg"], t["muted"], 0.38)
        t["bar_me"] = mix(t["bg"], t["accent"], 0.62)
        return t

    def initial_pos(self, w, h):
        x, y = self.cfg.get("x"), self.cfg.get("y")
        ok = isinstance(x, int) and isinstance(y, int)
        if ok and IS_WIN:
            ok = bool(user32.MonitorFromPoint(_POINT(x + w // 2, y + h // 2), 0))
        if not ok:
            x = self.root.winfo_screenwidth() - w - int(40 * self.dpi)
            y = int(140 * self.dpi)
        return x, y

    def setup_native(self):
        if not IS_WIN:
            return
        try:
            self.hwnd = int(self.root.wm_frame(), 16)
        except (tk.TclError, ValueError):
            self.hwnd = user32.GetParent(self.root.winfo_id())
        # janela sem moldura, com botão na barra de tarefas, e que não fica ativa ao ser
        # clicada (WS_EX_NOACTIVATE): o teclado continua no jogo
        style = user32.GetWindowLongW(self.hwnd, -20)        # GWL_EXSTYLE
        user32.SetWindowLongW(self.hwnd, -20, (style & ~0x80) | 0x40000 | WS_EX_NOACTIVATE)
        self.root.withdraw()
        self.root.after(10, self.root.deiconify)
        dwm_set(self.hwnd, 33, 2)                            # cantos arredondados (Win 11)
        self.apply_border()

    def apply_border(self):
        if self.hwnd:
            r, g, b = _rgb(self.theme()["edge"])
            dwm_set(self.hwnd, 34, r | (g << 8) | (b << 16))  # DWMWA_BORDER_COLOR

    def save(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)
        except OSError:
            pass

    def save_position(self):
        self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
        self.save()

    def log_error(self, exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(os.path.join(os.path.dirname(CONFIG_PATH), "erros.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
        except OSError:
            pass
        if sys.stderr:
            sys.stderr.write(text)

    # ------------------------------------------------------------ dados

    def tick(self):
        now = time.time()
        try:
            if self.watcher.poll(now):
                self.dirty = True
        except Exception:  # noqa: BLE001 - um replay estranho nao pode derrubar o widget
            self.log_error(*sys.exc_info())
        if clientdata.NAMES.version != self.names_v:
            # os nomes dos monstros novos (lidos do próprio jogo) ficaram prontos
            self.names_v = clientdata.NAMES.version
            self.dirty = True
            if self.analysis is not None:
                self.analysis.refresh(force=True)
        f = self.watcher.file
        if f is not None and f.ready:
            f.combat.finished = not self.watcher.recording(now)
            self.check_alerts(f, now)
            if self.cfg["auto_tests"] and now - self.last_autosave >= 2.0:
                self.last_autosave = now
                try:
                    testes.auto_save(self.tests, f, self.tests_seen)
                except Exception:  # noqa: BLE001
                    self.log_error(*sys.exc_info())
        self.phase = (self.phase + 1) % 8
        if self.dirty or now - self.last_draw >= 1.0:
            self.draw()
        if self.analysis is not None:
            try:
                self.analysis.tick()
            except Exception:  # noqa: BLE001
                self.log_error(*sys.exc_info())
        self.root.after(POLL_MS, self.tick)

    def check_alerts(self, f, now):
        """Mostra no rodapé o aviso mais novo (buff que acabou, morte) por alguns segundos."""
        c = f.combat
        floor = max(f.alert_floor, self.alert_seen)
        for seq, _t, kind, text in c.alerts:
            if seq <= floor:
                continue
            self.alert_seen = seq
            if ((kind == "buff" and self.cfg["alert_buffs"]) or (kind == "death" and self.cfg["alert_death"])
                    or (kind == "fusion" and self.cfg["alert_fusion"])):
                self.alert = (text, kind, now)
                self.dirty = True
        if self.alert and now - self.alert[2] > ALERT_S:
            self.alert = None
            self.dirty = True

    def combat(self):
        f = self.watcher.file
        return f.combat if f is not None and f.ready else None

    def status(self):
        """(texto, cor_da_bolinha) do rodapé."""
        t = self.t
        now = time.time()
        w = self.watcher
        if not w.folders:
            return _("Pasta Replay não encontrada"), t["live"], False
        f = w.file
        if f is None:
            return _("Aguardando gravação de replay…"), t["muted"], False
        if not f.ready:
            if w.pinned:
                return _("Abrindo %s…") % os.path.basename(f.path), t["muted"], False
            # o jogo só preenche a tabela do cabeçalho uns 10 s depois de começar a gravar;
            # nada se perde, a leitura começa do início quando ela aparece
            return _("Gravação começou · aguardando o jogo (~10 s)"), t["live"], True
        if w.pinned:
            return os.path.basename(f.path), t["muted"], False
        if w.recording(now):
            return _("Gravando · %s") % os.path.basename(f.path), t["live"], True
        return _("Gravação encerrada · %s") % os.path.basename(f.path), t["muted"], False

    # ------------------------------------------------------------ desenho

    def draw(self):
        self.dirty = False
        self.last_draw = time.time()
        c = self.canvas
        c.delete("all")
        t = self.t = self.theme()
        s = self.s
        self.W, self.H = W, H = self.size_px()
        self.hits = []
        self.root.configure(bg=t["bg"])
        c.configure(bg=t["bg"])

        cb = self.combat()
        session = self.cfg["session"]
        enc = None
        if cb is not None and not session:
            enc = cb.encounter(self.enc_back)
            if enc is None and self.enc_back:
                self.enc_back = 0
                enc = cb.encounter(0)
        snap = cb.snapshot(enc, session=session) if cb is not None else None

        # barra de cima: nome do personagem e botões
        x = W - 16 * s
        for key, glyph, color in (("close", self.icon("close"), t["muted"]),
                                  ("min", self.icon("min"), t["muted"]),
                                  ("more", self.icon("more"), t["muted"]),
                                  ("chart", self.icon("chart"), t["muted"]),
                                  ("pin", self.icon("pin_on" if self.cfg["pinned"] else "pin_off"),
                                   t["accent"] if self.cfg["pinned"] else t["muted"])):
            self.icon_button(key, x, TOP_Y * s, glyph, color)
            x -= 23 * s
        title_right = x + 8 * s
        if cb is not None:
            sess = cb.session
            name = sess.player or _("Personagem")
            job = meter.job_name(sess.job)
        else:
            name, job = _("Medidor de DPS"), "Ragnarok"
        tx = 12 * s
        tid = c.create_text(tx, TOP_Y * s, anchor="w", text=name, font=self.fonts["title"], fill=t["fg"])
        x1 = c.bbox(tid)[2]
        if job and x1 + 30 * s < title_right:
            jid = c.create_text(x1 + 5 * s, TOP_Y * s + 1 * s, anchor="w", text="· " + job,
                                font=self.fonts["small"], fill=t["muted"])
            if c.bbox(jid)[2] > title_right:
                c.delete(jid)

        # número grande; as linhas da direita têm prioridade, o número encolhe se precisar
        rx = W - 12 * s
        lines = []
        if snap:
            if snap["live"]:
                lines.append((_("agora %s/s") % num(snap["dps_now"]), t["accent"]))
            lines.append((_("total %s") % num(snap["my_total"]), t["fg"]))
            label = _("em combate") if session else (_("ao vivo") if snap["live"] else _("duração"))
            lines.append((_("%s %s") % (label, dur(snap["duration_ms"])), t["muted"]))
        lines_w = max([self.fonts["small"].measure(txt) for txt, _c in lines] + [0])
        big_text = num(snap["my_dps"]) if snap else "—"
        room = rx - lines_w - 10 * s - 12 * s
        unit_w = self.fonts["unit"].measure("DPS") + 4 * s
        big_font, show_unit = self.fonts["big"], True
        for font, unit in ((self.fonts["big"], True), (self.fonts["big_s"], True), (self.fonts["big_s"], False)):
            big_font, show_unit = font, unit
            if font.measure(big_text) + (unit_w if unit else 0) <= room:
                break
        bid = c.create_text(12 * s, BIG_Y * s, anchor="w", text=big_text, font=big_font, fill=t["fg"])
        if show_unit:
            c.create_text(c.bbox(bid)[2] + 4 * s, BIG_Y * s + 7 * s, anchor="w", text="DPS",
                          font=self.fonts["unit"], fill=t["muted"])
        y0 = BIG_Y * s - (len(lines) - 1) * 7 * s
        for i, (txt, col) in enumerate(lines):
            c.create_text(rx, y0 + i * 14 * s, anchor="e", text=txt, font=self.fonts["small"], fill=col)

        # abas
        x = 10 * s
        for key, label in TABS:
            x = self.chip(("tab", key), x, label, self.cfg["tab"] == key) + 4 * s
        mode = self.view_label(cb) + " ▾"
        mw = self.fonts["tab"].measure(mode) + 16 * s
        self.chip(("btn", "view"), max(x + 4 * s, W - 10 * s - mw), mode, False, outline=True)

        # linhas
        self.draw_rows(snap)

        # rodapé
        fy = H - FOOT_H * s / 2 - 2 * s
        text, dot, live = self.status()
        bx = W - 10 * s
        bx = self.text_button("reset", bx, fy, self.icon("reset"), _("Zerar"))
        if not session and cb is not None:
            encs = len(cb.history) + (1 if cb.current else 0)
            if encs > 1:
                bx = self.icon_button("next", bx - 12 * s, fy, self.icon("next"),
                                      t["fg"] if self.enc_back > 0 else mix(t["bg"], t["muted"], 0.4)) - 12 * s
                bx = self.icon_button("prev", bx - 2 * s, fy, self.icon("prev"),
                                      t["fg"] if self.enc_back < encs - 1 else mix(t["bg"], t["muted"], 0.4)) - 12 * s
                text = _("Luta %d/%d · %s") % (encs - self.enc_back, encs, (snap or {}).get("target") or text)
            elif snap and snap["target"]:
                text = "%s · %s" % (snap["target"], text)
        elif snap and snap["target"]:
            text = "%s · %s" % (snap["target"], text)
        r = 3.2 * s
        pulse = live and self.phase < 4
        color = t["muted"]
        hint = HINTS.get(self.hover[1] if self.hover and self.hover[0] in ("btn", "tab") else
                         (self.hover[0] if self.hover else None))
        if hint and not self.alert:
            text, color = hint, t["fg"]
        if self.alert:
            # aviso (buff que acabou, morte) no lugar do status, piscando
            text, kind = self.alert[0], self.alert[1]
            dot = t["live"] if kind in ("death", "fusion") else "#f59e0b"
            color = dot
            live = True
            c.create_polygon(round_rect_pts(6 * s, fy - 10 * s, bx - 4 * s, fy + 10 * s, 6 * s), smooth=True,
                             fill=mix(t["bg"], dot, 0.16 if self.phase < 4 else 0.08), outline="")
        c.create_oval(12 * s - r, fy - r, 12 * s + r, fy + r, outline="",
                      fill=dot if not live or pulse else mix(dot, t["bg"], 0.55))
        sid = c.create_text(20 * s, fy, anchor="w", text=text, font=self.fonts["small"], fill=color)
        self.clip_text(sid, text, bx - 6 * s)

        # alça de redimensionar
        self.hits.append((("grip", None), (W - 11 * s, H - 11 * s, W, H)))
        for dx, dy in ((0, 0), (4, 0), (0, 4)):
            gx, gy, rr = W - (4 + dx) * s, H - (4 + dy) * s, max(0.8, 1.0 * s)
            c.create_oval(gx - rr, gy - rr, gx + rr, gy + rr, fill=mix(t["bg"], t["muted"], 0.6), outline="")
        self.paint_hover()

    def clip_text(self, item, text, max_x):
        c = self.canvas
        if c.bbox(item)[2] <= max_x:
            return
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            c.itemconfigure(item, text=text[:mid] + "…")
            if c.bbox(item)[2] <= max_x:
                lo = mid
            else:
                hi = mid - 1
        c.itemconfigure(item, text=(text[:lo] + "…") if lo < len(text) else text)

    def draw_rows(self, snap):
        c, s, t = self.canvas, self.s, self.t
        W = self.W
        n = self.cfg["rows"]
        tab = self.cfg["tab"]
        y = ROWS_Y0 * s
        msg = None
        rows = []
        if snap is None:
            f = self.watcher.file
            if f is not None and f.ready and f.combat.was_reset:
                msg = (_("Zerado."), _("O próximo dano começa um encontro novo."))
            elif f is not None and f.ready:
                msg = (_("Nenhum dano ainda."), _("Ataque algo enquanto grava o replay."))
            elif not self.watcher.folders:
                # sem pasta Replay: um clique no meio abre a escolha da pasta do jogo
                msg = (_("Não achei a pasta Replay do jogo."), _("Clique aqui e escolha a pasta do Ragnarok."))
            else:
                folders = self.watcher.folders
                where = short_path(folders[0]) if len(folders) == 1 else _("%d pastas Replay") % len(folders)
                msg = (_("No jogo, comece a gravar um replay."), _("Olhando em %s") % where)
        elif tab == "group":
            players = snap["players"]
            shown = players[:n]
            me = next((p for p in players if p["me"]), None)
            if me is not None and me not in shown and n > 1:
                shown = shown[:n - 1] + [me]
            top = players[0]["total"] if players else 1
            for p in shown:
                rank = players.index(p) + 1
                pct = "%.0f%%" % (p["share"] * 100)
                if self.cfg["show_pct"]:
                    right = pct
                elif self.base_w() >= 340:
                    right = "%s/s · %s" % (num(p["dps"]), pct)
                else:
                    right = "%s/s" % num(p["dps"])
                rows.append(dict(label="%d. %s" % (rank, p["name"]), value=num(p["total"]), right=right,
                                 frac=p["total"] / (top or 1), me=p["me"]))
            if not players:
                msg = (_("Nenhum dano neste encontro."), "")
        elif tab == "skills":
            sk = snap["skills"]
            top = sk[0]["total"] if sk else 1
            for k in sk[:n]:
                rows.append(dict(label=k["name"], value=num(k["total"]),
                                 right=(_("%.0f%% · %d acertos") if self.base_w() >= 340 else "%.0f%% · %d×")
                                 % (k["share"] * 100, k["hits"]),
                                 frac=k["total"] / (top or 1), me=True))
            if not sk:
                msg = (_("Você não causou dano aqui."), "")
        else:
            tg = snap["targets"]
            top = tg[0]["total"] if tg else 1
            total = snap["my_total"] or 1
            for g in tg[:n]:
                rows.append(dict(label=g["name"], value=num(g["total"]),
                                 right="%.0f%%" % (g["total"] * 100.0 / total),
                                 frac=g["total"] / (top or 1), me=True))
            if not tg:
                msg = (_("Você não causou dano aqui."), "")
        if msg:
            cy = y + n * ROW_H * s / 2
            c.create_text(W / 2, cy - 8 * s, text=msg[0], font=self.fonts["text"], fill=t["fg"])
            if msg[1]:
                c.create_text(W / 2, cy + 9 * s, text=msg[1], font=self.fonts["small"], fill=t["muted"])
            return
        x0, x1 = 10 * s, W - 10 * s
        # coluna da direita do tamanho do maior texto, para nada se sobrepor em nenhum tamanho
        right_w = max([self.fonts["small"].measure(r["right"]) for r in rows] + [40 * s]) + 6 * s
        value_x = x1 - right_w - 6 * s
        for r in rows:
            y1 = y + (ROW_H - 3) * s
            c.create_polygon(round_rect_pts(x0, y, x1, y1, 4 * s), smooth=True, fill=t["track"], outline="")
            bw = max(0.0, min(1.0, r["frac"])) * (x1 - x0)
            if bw >= 2 * s:
                c.create_polygon(round_rect_pts(x0, y, x0 + bw, y1, 4 * s), smooth=True,
                                 fill=t["bar_me"] if r["me"] and tab == "group" else t["bar"], outline="")
            cy = (y + y1) / 2
            fg = on_color(t["bar"]) if luminance(t["bg"]) < 0.5 else t["fg"]
            c.create_text(x1 - 6 * s, cy, anchor="e", text=r["right"], font=self.fonts["small"],
                          fill=mix(fg, t["muted"], 0.35))
            vid = c.create_text(value_x, cy, anchor="e", text=r["value"], font=self.fonts["num"], fill=fg)
            lid = c.create_text(x0 + 7 * s, cy, anchor="w", text=r["label"], font=self.fonts["text"], fill=fg)
            self.clip_text(lid, r["label"], c.bbox(vid)[0] - 8 * s)
            y += ROW_H * s

    def chip(self, target, x, label, active, outline=False):
        c, s, t = self.canvas, self.s, self.t
        w = self.fonts["tab"].measure(label) + 16 * s
        box = (x, TABS_Y0 * s, x + w, TABS_Y1 * s)
        hov = self.hover == target
        if active:
            fill, fg = t["accent"], on_color(t["accent"])
        else:
            fill = shade(t["btn"], 0.10) if hov else (t["bg"] if outline else t["btn"])
            fg = t["fg"] if hov or outline else t["muted"]
        c.create_polygon(round_rect_pts(*box, 9 * s), smooth=True, fill=fill,
                         outline=t["btn"] if outline else "", width=max(1, s))
        c.create_text((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, text=label, font=self.fonts["tab"], fill=fg)
        self.hits.append((target, box))
        return box[2]

    def icon_button(self, key, cx, cy, glyph, color):
        c, s = self.canvas, self.s
        half = 10 * s
        box = (cx - half, cy - half, cx + half, cy + half)
        tag = "hover_" + key
        c.create_polygon(round_rect_pts(*box, 5 * s), smooth=True, fill="", outline="", tags=(tag, tag + "_bg"))
        c.create_text(cx, cy, text=glyph, font=self.fonts["icon"], fill=color, tags=(tag, tag + "_fg"))
        self.hits.append((("btn", key), box))
        return box[0]

    def text_button(self, key, right, cy, glyph, label):
        c, s, t = self.canvas, self.s, self.t
        wi = self.fonts["icon"].measure(glyph)
        wl = self.fonts["small"].measure(label)
        w = wi + wl + 5 * s + 16 * s
        box = (right - w, cy - 10 * s, right, cy + 10 * s)
        tag = "hover_" + key
        c.create_polygon(round_rect_pts(*box, 6 * s), smooth=True, fill=t["btn"], outline="",
                         tags=(tag, tag + "_bg"))
        c.create_text(box[0] + 8 * s, cy, anchor="w", text=glyph, font=self.fonts["icon"], fill=t["fg"])
        c.create_text(box[0] + 8 * s + wi + 5 * s, cy, anchor="w", text=label, font=self.fonts["small"], fill=t["fg"])
        self.hits.append((("btn", key), box))
        return box[0]

    def paint_hover(self):
        tgt = self.hover
        c = self.canvas
        if tgt and tgt[0] == "btn":
            key = tgt[1]
            if key == "close":
                c.itemconfigure("hover_close_bg", fill="#e81123")
                c.itemconfigure("hover_close_fg", fill="#ffffff")
            elif c.find_withtag("hover_%s_bg" % key):
                base = self.t["btn"] if key == "reset" else self.t["bg"]
                c.itemconfigure("hover_%s_bg" % key, fill=shade(base, 0.12))
        cursor = ""
        if tgt:
            cursor = {"btn": "hand2", "tab": "hand2", "grip": "size_nw_se"}[tgt[0]]
        c.configure(cursor=cursor)

    # ------------------------------------------------------------ ações

    def reload(self):
        """Lê o arquivo atual de novo do início (ex.: mudou o intervalo de encontro)."""
        f = self.watcher.file
        self.watcher.gap_ms = self.gap_ms()
        if f is not None:
            pinned = self.watcher.pinned
            nf = meter.ReplayFile(f.path, self.gap_ms(), self.cfg["targets"])
            nf.poll(max_bytes=64 << 20)
            self.watcher.file = nf
            self.watcher.pinned = pinned
        self.dirty = True

    def reset(self):
        cb = self.combat()
        if cb is not None:
            cb.reset()
        self.enc_back = 0
        self.dirty = True

    def toggle_session(self):
        self.set_view(not self.cfg["session"])

    def set_view(self, session, back=0):
        """Tudo (desde o início ou desde Zerar) ou uma luta (0 = a atual, 1 = a anterior...)."""
        self.cfg["session"] = session
        self.enc_back = back
        self.save()
        self.dirty = True

    def set_targets(self, mode):
        self.cfg["targets"] = mode
        self.watcher.targets = mode
        self.save()
        self.enc_back = 0
        self.reload()

    def set_tab(self, key):
        self.cfg["tab"] = key
        self.save()
        self.dirty = True

    def view_label(self, cb):
        if self.cfg["session"]:
            return _("Tudo")
        if not self.enc_back:
            return _("Luta atual")
        encs = len(cb.encounters()) if cb else 0
        return _("Luta %d de %d") % (encs - self.enc_back, encs)

    def view_menu(self, parent=None):
        m = self.new_menu(parent)
        cb = self.combat()
        var = self.keep(tk.StringVar(self.root, "all" if self.cfg["session"] else "enc%d" % self.enc_back))
        m.add_radiobutton(label=_("Tudo (desde o início ou desde Zerar)"), variable=var, value="all",
                          command=lambda: self.set_view(True))
        m.add_radiobutton(label=_("Luta atual (a mais recente)"), variable=var, value="enc0",
                          command=lambda: self.set_view(False, 0))
        encs = cb.encounters() if cb else []
        if len(encs) > 1:
            m.add_separator()
            m.add_command(label=_("Lutas anteriores:"), state="disabled")
            for back in range(1, min(len(encs), 15)):
                enc = encs[-1 - back]
                tgt = max(enc.by_target.items(), key=lambda kv: kv[1])[0] if enc.by_target else None
                mine = enc.by_source.get(cb.me)
                label = _("Luta %d · %s · %s") % (len(encs) - back, cb.target_name(tgt) if tgt is not None else "?",
                                               dur(enc.duration_ms()))
                if mine:
                    label += " · %s/s" % num(mine.total * 1000.0 / enc.duration_ms())
                m.add_radiobutton(label="    " + label, variable=var, value="enc%d" % back,
                                  command=lambda b=back: self.set_view(False, b))
        m.add_separator()
        m.add_cascade(label=_("Uma luta termina após"), menu=self.gap_menu(m))
        m.add_cascade(label=_("Contar dano em"), menu=self.targets_menu(m))
        return m

    def gap_menu(self, parent):
        gap = self.new_menu(parent)
        gap_var = self.keep(tk.IntVar(self.root, self.cfg["gap_s"]))
        for value, label in GAP_CHOICES:
            gap.add_radiobutton(label=label, variable=gap_var, value=value, command=lambda v=value: self.set_gap(v))
        gap.add_separator()
        gap.add_command(label=_("As fases de um MVP contam como uma luta só"), state="disabled")
        return gap

    def targets_menu(self, parent):
        tm = self.new_menu(parent)
        var = self.keep(tk.StringVar(self.root, self.cfg["targets"]))
        for value, label in TARGET_CHOICES:
            tm.add_radiobutton(label=label, variable=var, value=value, command=lambda v=value: self.set_targets(v))
        tm.add_separator()
        tm.add_command(label=_("Invocações de jogadores (ex.: Esfera Marinha) nunca contam"), state="disabled")
        return tm

    def browse(self, step):
        cb = self.combat()
        if cb is None or self.cfg["session"]:
            return
        encs = len(cb.history) + (1 if cb.current else 0)
        self.enc_back = max(0, min(encs - 1, self.enc_back + step))
        self.dirty = True

    def toggle_pin(self):
        self.cfg["pinned"] = not self.cfg["pinned"]
        self.root.attributes("-topmost", self.cfg["pinned"])
        self.save()
        self.dirty = True

    def set_theme(self, name):
        self.cfg["theme"] = name
        self.save()
        self.apply_border()
        self.dirty = True

    def set_scale(self, scale, save=True):
        scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        if abs(scale - self.cfg["scale"]) < 0.005:
            return
        self.cfg["scale"] = scale
        self.resize_window()
        if save:
            self.save()

    def resize_window(self):
        self.size_fonts()
        w, h = self.size_px()
        self.root.geometry("%dx%d" % (w, h))
        self.draw()

    def set_alpha(self, alpha):
        self.cfg["alpha"] = alpha
        self.root.attributes("-alpha", alpha)
        self.save()

    def set_rows(self, n):
        self.cfg["rows"] = n
        self.save()
        self.resize_window()

    def set_width(self, w):
        self.cfg["width"] = w
        self.save()
        self.resize_window()

    def set_gap(self, secs):
        self.cfg["gap_s"] = secs
        self.save()
        self.enc_back = 0
        self.reload()

    def toggle_pct(self):
        self.cfg["show_pct"] = not self.cfg["show_pct"]
        self.save()
        self.dirty = True

    def toggle_cfg(self, key):
        self.cfg[key] = not self.cfg[key]
        if key.startswith("alert_") and not self.cfg[key]:
            self.alert = None
        self.save()
        self.dirty = True

    def open_file(self):
        start = self.watcher.folder or os.path.expanduser("~")
        path = filedialog.askopenfilename(parent=self.root, title=_("Abrir replay"), initialdir=start,
                                          filetypes=[(_("Replay do Ragnarok"), "*.rrf"), (_("Todos"), "*.*")])
        if path:
            self.watcher.gap_ms = self.gap_ms()
            self.watcher.open(path)
            self.enc_back = 0
            self.dirty = True

    def follow(self):
        self.watcher.follow()
        self.enc_back = 0
        self.dirty = True

    def pick_folder(self):
        path = filedialog.askdirectory(parent=self.root,
                                       title=_("Escolha a pasta do Ragnarok (ou a pasta Replay dentro dela)"),
                                       initialdir=self.watcher.folder or "C:\\")
        if path:
            self.cfg["folder"] = meter.replay_dir_for(path)       # aceita a pasta do jogo ou a Replay
            self.save()
            self.watcher.set_folder(self.cfg["folder"])
            self.dirty = True

    def minimize(self):
        if IS_WIN and self.hwnd:
            user32.ShowWindow(self.hwnd, 6)           # SW_MINIMIZE
        else:
            self.root.iconify()

    def open_analysis(self):
        if self.analysis is not None:
            self.analysis.top.deiconify()
            self.analysis.top.lift()
            self.analysis.top.focus_force()
            return
        self.analysis = AnalysisWindow(self)

    def set_lang(self, code):
        """Troca o idioma: grava e reabre o medidor (os textos são montados ao abrir)."""
        if code == i18n.LANG:
            return
        self.cfg["lang"] = code
        self.save()
        args = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
        f = self.watcher.file
        if self.watcher.pinned and f is not None:
            args.append(f.path)
        try:
            subprocess.Popen(args, close_fds=True)
        except OSError:
            return
        self.quit()

    def about(self):
        messagebox.showinfo(_("Sobre"), "DPS Ragnarok %s\n\n%s\n\n%s" % (
            VERSION, _("Medidor de DPS para Ragnarok Online (ROLatam) · versão %s") % VERSION,
            _("Só lê o arquivo de replay que o jogo grava. Não lê a memória do jogo, não mexe na rede e não "
              "manda nada para a internet.")), parent=self.root)

    def quit(self):
        if self.analysis is not None:
            self.analysis.close()
        self.save_position()
        self.root.destroy()

    def activate(self, target):
        kind, key = target
        if kind == "tab":
            self.set_tab(key)
            return
        actions = {
            "pin": self.toggle_pin, "min": self.minimize, "close": self.quit,
            "more": lambda: self.popup_at(target, self.main_menu),
            "view": lambda: self.popup_at(target, self.view_menu), "reset": self.reset, "chart": self.open_analysis,
            "prev": lambda: self.browse(1), "next": lambda: self.browse(-1),
        }
        actions[key]()

    # ------------------------------------------------------------ menus

    def new_menu(self, parent=None):
        return tk.Menu(parent or self.root, tearoff=0)

    def keep(self, obj):
        self.menu_refs.append(obj)
        return obj

    def swatch(self, theme):
        h = max(12, int(round(14 * self.dpi)))
        img = self.keep(tk.PhotoImage(master=self.root, width=h * 2, height=h))
        img.put(theme["bg"], to=(0, 0, h * 2, h))
        b = max(2, h // 5)
        img.put(theme["accent"], to=(b, b, h, h - b))
        img.put(theme["live"], to=(h + 1, b, h * 2 - b, h - b))
        return img

    def main_menu(self, parent=None):
        m = self.new_menu(parent)
        cfg = self.cfg
        pinned = self.keep(tk.BooleanVar(self.root, cfg["pinned"]))
        m.add_checkbutton(label=_("Fixar sempre no topo"), variable=pinned, command=self.toggle_pin)
        m.add_cascade(label=_("Mostrar"), menu=self.view_menu(m))
        m.add_cascade(label=_("Contar dano em"), menu=self.targets_menu(m))
        pct = self.keep(tk.BooleanVar(self.root, cfg["show_pct"]))
        m.add_checkbutton(label=_("Grupo: mostrar % em vez de DPS"), variable=pct, command=self.toggle_pct)
        m.add_command(label=_("Zerar"), command=self.reset)
        m.add_separator()
        m.add_command(label=_("Análise completa…"), command=self.open_analysis)
        for key, label in (("alert_buffs", _("Avisar quando um buff acabar na luta")),
                           ("alert_death", _("Avisar quando eu morrer (com overkill)")),
                           ("alert_fusion", _("Avisar HP baixo com a União Solar (Mestre Taekwon)")),
                           ("auto_tests", _("Salvar testes no boneco sozinho"))):
            var = self.keep(tk.BooleanVar(self.root, cfg[key]))
            m.add_checkbutton(label=label, variable=var, command=lambda k=key: self.toggle_cfg(k))

        m.add_command(label=_("Abrir replay salvo…"), command=self.open_file)
        if self.watcher.pinned:
            m.add_command(label=_("Voltar a seguir a gravação"), command=self.follow)
        m.add_command(label=_("Pasta dos replays…"), command=self.pick_folder)
        for folder in self.watcher.folders[:5] or [_("(não encontrada)")]:
            m.add_command(label="  " + folder, state="disabled")
        m.add_separator()

        color = self.new_menu(m)
        var = self.keep(tk.StringVar(self.root, cfg["theme"]))
        for name, theme in THEMES.items():
            color.add_radiobutton(label="  " + _(name), image=self.swatch(theme), compound="left",
                                  variable=var, value=name, command=lambda n=name: self.set_theme(n))
        m.add_cascade(label=_("Cor"), menu=color)
        size = self.new_menu(m)
        scale_var = self.keep(tk.DoubleVar(self.root, cfg["scale"]))
        for value, label in SIZES:
            size.add_radiobutton(label="%s (%d%%)" % (label, value * 100), variable=scale_var, value=value,
                                 command=lambda v=value: self.set_scale(v))
        size.add_separator()
        width_var = self.keep(tk.IntVar(self.root, self.base_w()))
        for value, label in WIDTHS:
            size.add_radiobutton(label=_("Largura: %s") % label, variable=width_var, value=value,
                                 command=lambda v=value: self.set_width(v))
        size.add_separator()
        size.add_command(label=_("Arraste o canto: largura e linhas"), state="disabled")
        size.add_command(label=_("Ctrl + roda (ou Shift + arrastar): zoom"), state="disabled")
        m.add_cascade(label=_("Tamanho"), menu=size)
        rows = self.new_menu(m)
        rows_var = self.keep(tk.IntVar(self.root, cfg["rows"]))
        for value in sorted(set(ROW_CHOICES + [cfg["rows"]])):
            rows.add_radiobutton(label=_("%d linhas") % value, variable=rows_var, value=value,
                                 command=lambda v=value: self.set_rows(v))
        m.add_cascade(label=_("Linhas"), menu=rows)
        alpha = self.new_menu(m)
        alpha_var = self.keep(tk.DoubleVar(self.root, cfg["alpha"]))
        for value in ALPHAS:
            alpha.add_radiobutton(label="%d%%" % round(value * 100), variable=alpha_var, value=value,
                                  command=lambda v=value: self.set_alpha(v))
        m.add_cascade(label=_("Opacidade"), menu=alpha)
        lang = self.new_menu(m)
        lang_var = self.keep(tk.StringVar(self.root, i18n.LANG))
        for code, label in i18n.LANGS:
            lang.add_radiobutton(label=label, variable=lang_var, value=code, command=lambda c=code: self.set_lang(c))
        m.add_cascade(label="%s / Language" % _("Idioma") if i18n.LANG != "en" else "Language", menu=lang)
        m.add_command(label=_("Sobre"), command=self.about)
        m.add_separator()
        m.add_command(label=_("Minimizar"), command=self.minimize)
        m.add_command(label=_("Fechar"), command=self.quit)
        return m

    def popup(self, factory, x, y):
        if self.menu is not None:
            self.menu.destroy()
        self.menu_refs = []
        self.menu = factory()
        prev = None
        if IS_WIN and self.hwnd:
            # o menu precisa da janela ativa para fechar direito; depois o foco volta para o jogo
            prev = user32.GetForegroundWindow()
            user32.SetForegroundWindow(self.hwnd)
        try:
            self.menu.tk_popup(int(x), int(y))
        finally:
            self.menu.grab_release()
        if prev and prev != self.hwnd:
            self.root.after(250, lambda: self.give_back_focus(prev))

    def give_back_focus(self, prev):
        # só devolve se nada novo abriu (diálogo de arquivo, janela de análise...)
        if IS_WIN and user32.GetForegroundWindow() == self.hwnd:
            user32.SetForegroundWindow(prev)

    def popup_at(self, target, factory):
        box = next((b for tg, b in self.hits if tg == target), None)
        x0, y1 = (box[0], box[3]) if box else (0, 0)
        self.popup(factory, self.root.winfo_rootx() + x0, self.root.winfo_rooty() + y1 + 2)

    # ------------------------------------------------------------ eventos

    def target_at(self, x, y):
        for target, (x0, y0, x1, y1) in reversed(self.hits):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return target
        return None

    def set_hover(self, target):
        if target != self.hover:
            self.hover = target
            self.draw()

    def on_motion(self, e):
        if not (self.drag or self.resize):
            self.set_hover(self.target_at(e.x, e.y))

    def on_press(self, e):
        self.pressed = self.drag = self.resize = None
        tgt = self.target_at(e.x, e.y)
        if tgt and tgt[0] in ("btn", "tab"):
            self.pressed = tgt
        elif tgt and tgt[0] == "grip":
            # arrastar o canto muda largura e número de linhas; com Shift, o zoom
            self.resize = (e.x_root, e.y_root, self.W, self.H, self.cfg["scale"], bool(e.state & 0x1))
        else:
            self.drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
            self.press_xy = (e.x_root, e.y_root)

    def on_drag(self, e):
        if self.drag:
            dx, dy = self.drag
            self.root.geometry("+%d+%d" % (e.x_root - dx, e.y_root - dy))
        elif self.resize:
            x0, y0, w0, h0, sc0, zoom = self.resize
            if zoom:
                ratio = max((w0 + e.x_root - x0) / w0, (h0 + e.y_root - y0) / h0)
                self.set_scale(sc0 * ratio, save=False)
                return
            s = self.s
            width = int(round((w0 + e.x_root - x0) / s))
            rows = int(round(((h0 + e.y_root - y0) / s - ROWS_Y0 - 6 - FOOT_H) / ROW_H))
            width = max(MIN_W, min(MAX_W, width))
            rows = max(MIN_ROWS, min(MAX_ROWS, rows))
            if width != self.base_w() or rows != self.cfg["rows"]:
                self.cfg["width"], self.cfg["rows"] = width, rows
                self.resize_window()

    def on_release(self, e):
        if self.pressed:
            tgt, self.pressed = self.pressed, None
            if self.target_at(e.x, e.y) == tgt:
                self.activate(tgt)
        elif self.drag:
            self.drag = None
            moved = self.press_xy and abs(e.x_root - self.press_xy[0]) + abs(e.y_root - self.press_xy[1]) > 4
            if not moved and not self.watcher.folders:
                self.pick_folder()
            else:
                self.save_position()
        elif self.resize:
            self.resize = None
            self.save()

    def on_right_click(self, e):
        self.popup(self.main_menu, e.x_root, e.y_root)

    def on_wheel(self, e):
        if e.state & 0x4:                                   # Ctrl
            self.set_scale(self.cfg["scale"] * (1.08 if e.delta > 0 else 1 / 1.08))


def main():
    if IS_WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (OSError, AttributeError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (OSError, AttributeError):
                pass
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RODpsMeter.DpsRagnarok")
        except (OSError, AttributeError):
            pass
    root = tk.Tk()
    path = sys.argv[1] if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]) else None
    DpsApp(root, path)
    root.mainloop()


if __name__ == "__main__":
    main()
