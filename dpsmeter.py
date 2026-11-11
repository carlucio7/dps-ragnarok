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
import random
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

import analysis
import clientdata
import itemkind
import sprites
import meter
import quests
import testes
import xp
from analysis_ui import AnalysisWindow
from fmt import num, dur, dec
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
PIN_H = 22             # faixa das informações fixadas (abaixo das abas)
MAX_PINS = 2
FOOT_H = 28
MIN_SCALE, MAX_SCALE = 0.7, 2.5
FONT_PX = {"big": 30, "big_s": 23, "spaced": 13, "unit": 11, "title": 12, "text": 11, "small": 10, "num": 12, "icon": 11, "tab": 11}
MIN_FONT_PX = 8
ALERT_S = 7.0          # quanto tempo um aviso fica no rodapé
DROP_SCROLL_ROWS = 3   # itens que a roda do mouse rola na aba Drops
MIRACLE_FLASH_S = 9.0  # o widget brilha por esse tempo quando o Milagre ativa
MIRACLE_BANNER_S = 6.0
MIRACLE_COLORS = ("#fbbf24", "#fde68a", "#c084fc", "#f9a8d4", "#ffffff", "#a5b4fc")
POLL_MS = 150         # ler o pedaço novo do arquivo custa < 1 ms
DEATH_CARD_S = 10.0   # o resumo da morte fica no widget por esse tempo
BOSS_CARD_S = 5.0     # o aviso de chefe que mudou (propriedade, imunidade, tamanho) fica esse tempo
BOSS_MERGE_MS = 2000  # mudanças do mesmo chefe quase juntas viram um cartão só (ex.: volta a ser grande e vira Sombrio)
SUMMARY_CARD_S = 14.0     # o resumo do fim da luta (conclusões do Dedo Duro) fica esse tempo
SUMMARY_WAIT_MS = 2500    # depois da morte do chefe, espera os últimos pacotes da luta
SUMMARY_PHASE_MS = 14000  # chefe em fases que morreu antes da 3ª: espera para ver se vem outra fase
REC_OFF_S = 45.0          # jogo aberto e nada gravando há esse tempo: lembrete de gravação desligada
GAME_CHECK_S = 5.0        # de quanto em quanto tempo olha se o jogo está aberto
SIZE_NAMES = {"S": "pequeno", "M": "médio", "L": "grande"}
# Padrão único dos cartões (chefe mudou, mecânica, fim da luta), no formato do resumo da morte: moldura e título
# na cor da gravidade, desenho do chefe no alto e linhas centradas. Todos ocupam a mesma área do widget.
SEV_COLORS = {"grave": "#ef4444", "atencao": "#f59e0b", "bom": "#22c55e", "info": "#38bdf8"}
CARD_BG, CARD_DIM, CARD_WHITE = "#14161c", "#a3a8b5", "#ffffff"
# avisos de mecânica: (título, gravidade, [(linha, cor ou None)]); traduzidos na hora de desenhar
MECH_CARDS = {
    "maxpain_on": ("Dor Máxima ativa", "grave", [("Segure os golpes grandes", "#f87171"),
                                                 ("Ela devolve parte de cada golpe", None)]),
    "maxpain_off": ("Dor Máxima acabou", "bom", [("Pode soltar os golpes grandes", "#4ade80")]),
    "defense": ("modo defesa", "atencao", [("O dano quase não entra (99%)", None)]),
    "relief": ("Aliviar muito alto", "grave", []),        # as linhas (Almas ativas, redução) são montadas na hora
    "def_break": ("a defesa caiu", "bom", [("5 s de dano total: solte tudo", "#4ade80")]),
}
DEATH_RED = "#ef4444"
DEATH_CARD_BG = "#1f0606"   # cartão escuro no meio do widget
# título do resumo a cada morte no mesmo encontro (1ª, 2ª, ...); a última vale dali em diante, com o número
DEATH_TITLES = [_("VOCÊ MORREU"), _("MORREU DE NOVO"), _("DE NOVO?!"), _("MELHORE"), _("JÁ É HÁBITO"),
                _("O CHÃO TE CONHECE"), _("SALVOU NA KAFRA?"), _("MODO TAPETE ATIVADO"), _("%d MORTES. RESPEITO.")]
DEATH_DIM = 0.55            # o widget escurece (nas cores do tema) enquanto o resumo da morte aparece
# cor de cada propriedade de ataque no resumo da morte
ELEMENT_COLORS = {"Neutral": "#a1a1aa", "Water": "#38bdf8", "Earth": "#d9a05b", "Fire": "#f97316", "Wind": "#4ade80",
                  "Poison": "#a3e635", "Holy": "#fde047", "Dark": "#a78bfa", "Ghost": "#f0abfc", "Undead": "#94a3b8",
                  "Mixed": "#e5e7eb"}

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
    "shot": _("Copiar a imagem do widget (cole com Ctrl+V)"),
    "summary": _("Clique: abrir o Dedo Duro · botão direito: desligar o resumo da luta"),
    "more": _("Opções"), "min": _("Minimizar"), "close": _("Fechar o medidor"), "reset": _("Zerar: começa a contar de novo"),
    "view": _("Escolher o que mostrar: tudo ou uma luta"), "prev": _("Luta anterior"), "next": _("Próxima luta"),
    "group": _("Dano de cada jogador"), "skills": _("O seu dano por skill"), "targets": _("Em quem você bateu"),
    "drops": _("Itens que você pegou"), "xp": _("XP estimada dos seus abates e seu nível"),
    "grip": _("Arraste para mudar a largura e o número de linhas"),
    "where": _("Onde quem grava está (mapa e coordenadas). Clique para copiar o /navi"),
    "pinbar": _("Informação fixada · botão direito para desafixar"),
    "row": _("Botão direito: fixar no widget, ocultar..."),
    "death": _("Clique: fechar · botão direito: desligar o resumo da morte"),
    "bosscard": _("Clique: fechar · botão direito: desligar o aviso do chefe"),
}
# o que dá para fixar na faixa abaixo das abas (além dos itens da aba Drops)
PIN_STATS = [("xp_min", _("XP por minuto")), ("xp_hour", _("XP por hora")), ("xp_total", _("XP estimada")),
             ("xp_eta", _("Até o próximo nível")), ("kills", _("Abates")), ("level", _("Nível"))]
PIN_LABELS = {"xp_min": _("XP/min"), "xp_hour": _("XP/h"), "xp_total": _("XP"), "xp_eta": _("Próx. nível"),
              "kills": _("Abates"), "level": _("Nível")}
TABS = [("group", _("Grupo")), ("skills", _("Skills")), ("targets", _("Alvos")), ("drops", _("Drops")),
        ("xp", _("XP"))]

ICONS = {
    "pin_on": ("\uE840", "📌"), "pin_off": ("\uE718", "📌"), "more": ("\uE712", "⋯"),
    "min": ("\uE921", "–"), "close": ("\uE8BB", "✕"), "reset": ("\uE72C", "↻"),
    "prev": ("\uE76B", "‹"), "next": ("\uE76C", "›"), "file": ("\uE8E5", "📂"),
    "chart": ("\uE9D2", "📊"),
    "where": ("\uE707", "📍"),
    "shot": ("\uE722", "📷"),
}

CONFIG_VERSION = 3
DEFAULTS = {
    "theme": "Grafite", "scale": 1.0, "alpha": 0.92, "pinned": True,
    "rows": 6, "gap_s": 15, "tab": "group", "session": True, "show_pct": False,
    "rate": "combat",      # DPS: "combat" = dano / tempo da luta; "active" = dano / tempo em que cada um bateu
    "folder": None, "x": None, "y": None, "v": CONFIG_VERSION, "width": BASE_W,
    "an_geometry": None, "an_tab": 0, "an_zoom": 1.0,
    "auto_tests": True, "alert_buffs": True, "alert_death": True, "alert_fusion": True, "alert_miracle": True, "miracle_sound": True,
    "miracle_volume": 40,  # volume do som do Milagre (%)
    "targets": "all",
    "lang": None,          # None = idioma do Windows
    "xp_corr": {},         # {personagem: {"samples": [[XP real ÷ lista, XP real, quando, arquivo#trecho]]}}
    "xp_levels": {},       # {classe: {nível: XP do nível}} visto no começo das gravações
    "xp_bonuses": {},      # {bônus: {"on", "pct"}} da lista de bônus de XP (xp.BONUSES)
    "xp_mode": "auto",     # "auto" (lista + correção medida + evento deduzido), "lista", "medido" ou "fixo"
    "xp_fixed": None,      # bônus fixo (%) do modo "fixo"
    "xp_manual_last": {},  # {personagem: % do último manual que o jogo mandou} (para o manual já ativo no começo)
    "xp_quests": {},       # {missão: {"base": XP sem bônus, "level"}} aprendido de trechos com XP exata
    "xp_event_off": [],    # itens de evento cujo bônus "[Durante o Evento]" não vale mais
    "drop_favs": [],       # itens favoritos (ficam no topo da aba Drops)
    "drop_hidden": [],     # itens que a pessoa ocultou para sempre (somem das listas de drops)
    "drop_colors": {},     # {categoria: "#rrggbb" ou ""} cores dos drops por categoria (itemkind)
    "pins": [],            # informações fixadas na faixa abaixo das abas (até 2): "xp_min", "item:984"...
    "fusion_sound": False,  # som curto quando o HP fica baixo com a União
    "fusion_volume": 40,
    "death_card": True,     # quando você morre, o widget mostra por 10 s o que te matou
    "alert_boss": True,     # cartão de 5 s: o chefe trocou de propriedade/tamanho, ou mecânica (Dor Máxima, defesa)
    "fight_summary": True,  # no fim da luta contra chefe, as principais conclusões do Dedo Duro por alguns segundos
    "alert_rec": True,      # lembrar quando o jogo está aberto e nenhum replay está sendo gravado
    "rec_sound": False,     # ...com um som curto (uma vez)
    "copy_hide_names": False,   # "copiar imagem" troca os nomes dos jogadores pela classe
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


_CHIME = {}
CHIME_VOLUMES = (10, 25, 40, 60, 80, 100)


def chime_wav(volume=40):
    """Arpejo curto e brilhante (dó-mi-sol-dó e um brilho no fim), WAV 16 bits mono gerado na hora.
    volume: 0–100 (100 = o volume da 1.2.0, que ficou alto demais)."""
    volume = max(0, min(100, int(volume)))
    if volume in _CHIME:
        return _CHIME[volume]
    import math
    import struct as st
    rate, length = 22050, 1.25
    n = int(rate * length)
    buf = [0.0] * n
    notes = [(1046.5, 0.00, 0.30), (1318.5, 0.08, 0.28), (1568.0, 0.16, 0.26), (2093.0, 0.24, 0.30),
             (2637.0, 0.40, 0.10), (3136.0, 0.46, 0.08), (4186.0, 0.52, 0.06)]
    for freq, start, vol in notes:
        i0 = int(start * rate)
        for i in range(i0, n):
            x = (i - i0) / float(rate)
            env = math.exp(-x * 5.0) * min(1.0, x * 200)       # ataque rápido, cauda que some
            w = 2 * math.pi * freq * x
            buf[i] += vol * env * (math.sin(w) + 0.25 * math.sin(2 * w) + 0.1 * math.sin(3 * w))
    peak = max(abs(v) for v in buf) or 1.0
    data = b"".join(st.pack("<h", int(32767 * 0.55 * volume / 100.0 * v / peak)) for v in buf)
    head = (b"RIFF" + st.pack("<I", 36 + len(data)) + b"WAVEfmt " + st.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + st.pack("<I", len(data)))
    _CHIME[volume] = head + data
    return _CHIME[volume]


def beep_wav(volume=40):
    """Aviso curto (dois toques descendo, ~0,35 s) para HP baixo com a União. WAV 16 bits mono."""
    volume = max(0, min(100, int(volume)))
    key = ("beep", volume)
    if key in _CHIME:
        return _CHIME[key]
    import math
    import struct as st
    rate = 22050
    n = int(rate * 0.36)
    buf = [0.0] * n
    for freq, start, length in ((1318.5, 0.00, 0.14), (987.8, 0.17, 0.17)):
        i0, i1 = int(start * rate), min(n, int((start + length) * rate))
        for i in range(i0, i1):
            x = (i - i0) / float(rate)
            env = min(1.0, x * 400) * min(1.0, (i1 - i) / (rate * 0.03))     # sem estalo no começo e no fim
            w = 2 * math.pi * freq * x
            buf[i] += env * (math.sin(w) + 0.3 * math.sin(2 * w))
    peak = max(abs(v) for v in buf) or 1.0
    data = b"".join(st.pack("<h", int(32767 * 0.5 * volume / 100.0 * v / peak)) for v in buf)
    head = (b"RIFF" + st.pack("<I", 36 + len(data)) + b"WAVEfmt " + st.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + st.pack("<I", len(data)))
    _CHIME[key] = head + data
    return _CHIME[key]


def play_wav(make, volume=40):
    """Toca um som gerado (make(volume) -> WAV) sem travar o widget (Windows)."""
    if not IS_WIN or volume <= 0:
        return

    def run():
        try:
            import winsound
            winsound.PlaySound(make(volume), winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except (ImportError, RuntimeError, OSError):
            pass
    threading.Thread(target=run, daemon=True).start()


def play_chime(volume=40):
    """Toca o som do Milagre."""
    play_wav(chime_wav, volume)


def play_beep(volume=40):
    """Toca o aviso da União."""
    play_wav(beep_wav, volume)


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
            if saved.get("v", 1) < 3 and cfg.get("xp_mode") == "lista":
                # v3: a XP sai de "pela lista" (o padrão antigo, que quase ninguém escolheu) para o automático
                cfg["xp_mode"] = "auto"
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
        self.xp_seen = None
        self.xp_auto_at = 0.0                  # última conferência automática da XP (manual lembrado, evento)
        self.xp_lvl_seen = None                # (gravação, nº de subidas de nível) já conferido
        self.miracle_at = -1e9                 # quando o Milagre ativou (o widget brilha por uns segundos)
        self.press_xy = None
        self.enc_back = 0                   # 0 = encontro atual, 1 = anterior...
        self.drop_scroll = 0                # primeira linha mostrada na aba Drops (roda do mouse)
        self.drop_view = (0, 0, 0)          # (primeira, linhas, total) para a barra de rolagem
        self.session_hidden = set()         # drops ocultos só até fechar o programa
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
        self.death_card = None        # (resumo da morte, quando apareceu)
        self.boss_card = None         # (o que mudou no chefe, quando apareceu)
        self.summary_card = None      # (resumo do fim da luta, quando apareceu)
        self.summary_due = None       # (gravação, nº do aviso da morte do chefe) esperando os últimos pacotes
        self.game_on = False          # o jogo está aberto? (olhado a cada 5 s, para o lembrete de gravação)
        self.game_check_at = 0.0
        self.rec_seen_at = time.time()   # última vez em que havia gravação (ou em que o jogo não estava aberto)
        self.rec_warned = False       # o som do lembrete já tocou neste episódio
        self.sprite_photos = {}       # (monstro, largura, altura) -> PhotoImage do sprite
        self.press_target = None
        self.alert_seen = 0

        root.title(_("Replay Master"))
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

    def rows_y0(self):
        """Onde as linhas começam (sem escala): logo abaixo das abas, ou da faixa fixa quando há algo fixado."""
        return ROWS_Y0 + (PIN_H if self.cfg.get("pins") else 0)

    def size_px(self):
        h = self.rows_y0() + self.cfg["rows"] * ROW_H + 6 + FOOT_H
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
            "spaced": tkfont.Font(self.root, family=semi),
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
        dc = getattr(self, "death_card", None)
        k = time.time() - dc[1] if dc else -1.0
        if 0 <= k < DEATH_CARD_S:
            # resumo da morte: o widget escurece nas cores do tema (entra rápido, sai nos últimos instantes)
            a = min(1.0, k / 0.25) * min(1.0, (DEATH_CARD_S - k) / 0.6)
            t = {key: val if key == "fg" else mix(val, "#000000", DEATH_DIM * a) for key, val in t.items()}
        t["edge"] = mix(t["bg"], t["fg"], 0.10)
        t["track"] = mix(t["bg"], t["fg"], 0.07)
        t["bar"] = mix(t["bg"], t["muted"], 0.38)
        t["bar_me"] = mix(t["bg"], t["accent"], 0.62)
        k = time.time() - getattr(self, "miracle_at", -1e9)
        if 0 <= k < MIRACLE_FLASH_S:
            # Milagre: o widget brilha em dourado, lilás e branco, apagando aos poucos
            fade = 1.0 - k / MIRACLE_FLASH_S
            star = MIRACLE_COLORS[int(k * 6) % len(MIRACLE_COLORS)]
            t["accent"] = mix(t["accent"], star, 0.35 + 0.65 * fade)
            t["bar_me"] = mix(t["bar_me"], star, 0.75 * fade)
            t["bar"] = mix(t["bar"], "#7c3aed", 0.35 * fade)
            dark = sum(int(t["bg"][i:i + 2], 16) for i in (1, 3, 5)) < 384
            t["bg"] = mix(t["bg"], "#2e1065" if dark else "#fef3c7", 0.55 * fade)
            t["edge"] = mix(t["edge"], "#fbbf24", 0.8 * fade)
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
        """Laço do widget: lê o replay, desenha e se reagenda. Um erro em qualquer parte vai para o erros.log, mas
        nunca para o laço (antes, um erro ao desenhar congelava o DPS e os drops)."""
        try:
            self.step()
        except Exception:  # noqa: BLE001
            self.log_error(*sys.exc_info())
        finally:
            self.root.after(POLL_MS, self.tick)

    def step(self):
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
        cur = f.combat if f is not None and f.ready else None
        if cur is not self.xp_seen:
            prev, self.xp_seen = self.xp_seen, cur
            if prev is not None:
                self.xp_calibrate(prev)
        if f is not None and f.ready:
            f.combat.finished = not self.watcher.recording(now)
            self.check_alerts(f, now)
            if now - self.xp_auto_at >= 3.0:
                self.xp_auto_at = now
                self.xp_auto(f.combat)
            if self.cfg["auto_tests"] and now - self.last_autosave >= 2.0:
                self.last_autosave = now
                try:
                    testes.auto_save(self.tests, f, self.tests_seen)
                except Exception:  # noqa: BLE001
                    self.log_error(*sys.exc_info())
        self.phase = (self.phase + 1) % 8
        self.check_recording(now)
        if (now - self.miracle_at < MIRACLE_FLASH_S + 0.3 or self.death_card or self.boss_card
                or self.summary_card):
            self.dirty = True
        if self.dirty or now - self.last_draw >= 1.0:
            try:
                self.draw()
            except Exception:  # noqa: BLE001 - um erro ao desenhar não pode parar a leitura do replay
                self.log_error(*sys.exc_info())
        if self.analysis is not None:
            try:
                self.analysis.tick()
            except Exception:  # noqa: BLE001
                self.log_error(*sys.exc_info())

    def xp_calibrate(self, c):
        """Fator de XP do personagem: XP exata até a próxima gravação ÷ XP estimada dos abates desta. No modo
        automático a mesma medida confere o evento do servidor e aprende a XP das missões."""
        try:
            before = json.dumps([self.cfg.get(k) for k in ("xp_bonuses", "xp_quests", "xp_manual_last")], sort_keys=True)
            server = xp.settings(self.cfg)["server"]
            done = xp.calibrate(c, self.cfg, meter.xp_after)
            now = xp.settings(self.cfg)["server"]
            if (server["on"], server["pct"]) != (now["on"], now["pct"]):
                self.xp_server_found(now["pct"] if now["on"] else 0)
            after = json.dumps([self.cfg.get(k) for k in ("xp_bonuses", "xp_quests", "xp_manual_last")], sort_keys=True)
            if done or before != after:
                self.save()
                self.dirty = True
        except Exception:  # noqa: BLE001
            self.log_error(*sys.exc_info())

    def xp_auto(self, c):
        """Automático da XP durante a gravação: guarda o % do manual que o jogo mandou e, a cada subida de nível
        (XP exata), confere o evento do servidor."""
        try:
            changed = xp.remember_manual(c, self.cfg)
            sig = (id(c), len(c.level_ups))
            if sig != self.xp_lvl_seen:
                self.xp_lvl_seen = sig
                if c.level_ups:
                    changed = self.xp_server_found(xp.detect_server(c, self.cfg)) or changed
            if changed:
                self.save()
                self.dirty = True
        except Exception:  # noqa: BLE001
            self.log_error(*sys.exc_info())

    def xp_server_found(self, pct):
        """Avisa no rodapé que o evento do servidor foi deduzido da XP exata (pct None = nada mudou)."""
        if pct is None:
            return False
        text = (_("XP: evento do servidor de +%d%% detectado e marcado") % pct) if pct else _(
            "XP: sem evento do servidor agora (desmarcado pela XP exata)")
        self.alert = (text, "info", time.time())
        if self.analysis is not None:
            self.analysis.xp_loaded = False       # a lista de bônus da análise relê o que mudou
        return True

    def check_alerts(self, f, now):
        """Mostra no rodapé o aviso mais novo (buff que acabou, morte) por alguns segundos."""
        c = f.combat
        floor = max(f.alert_floor, self.alert_seen)
        for seq, _t, kind, text in c.alerts:
            if seq <= floor:
                continue
            self.alert_seen = seq
            if kind == "death" and self.cfg["death_card"]:
                self.show_death_card(c, seq, now)
            if kind == "boss" and self.cfg.get("alert_boss", True):
                self.show_boss_card(c, seq, now)
            if kind == "bossdead" and self.cfg.get("fight_summary", True):
                self.summary_due = (c, seq)
            if ((kind == "buff" and self.cfg["alert_buffs"]) or (kind == "death" and self.cfg["alert_death"])
                    or (kind == "fusion" and self.cfg["alert_fusion"])
                    or (kind == "boss" and self.cfg.get("alert_boss", True))
                    or (kind == "miracle" and self.cfg["alert_miracle"])):
                self.alert = (text, kind, now)
                self.dirty = True
                if kind == "miracle":
                    self.miracle_at = now
                    if self.cfg["miracle_sound"]:
                        play_chime(self.cfg["miracle_volume"])
                elif kind == "fusion" and self.cfg["fusion_sound"]:
                    play_beep(self.cfg["fusion_volume"])
        if self.alert and now - self.alert[2] > (MIRACLE_FLASH_S if self.alert[1] == "miracle" else ALERT_S):
            self.alert = None
            self.dirty = True
        if self.death_card and now - self.death_card[1] > DEATH_CARD_S:
            self.death_card = None
            self.dirty = True
        if self.boss_card and now - self.boss_card[1] > BOSS_CARD_S:
            self.boss_card = None
            self.dirty = True
        if self.summary_card and now - self.summary_card[1] > SUMMARY_CARD_S:
            self.summary_card = None
            self.dirty = True
        self.check_summary(c, now)

    def check_summary(self, c, now):
        """O chefe morreu: depois dos últimos pacotes (ou de ver que não vem outra fase), mostra o resumo da luta."""
        due = self.summary_due
        if due is None:
            return
        if due[0] is not c or due[1] not in c.fight_ends:
            self.summary_due = None
            return
        key, t = c.fight_ends[due[1]]
        e = c.entities.get(key)
        phased = e is not None and e.job in meter.PHASED_BOSSES and c.phases.get(key, 1) < 3
        if c.now < t + (SUMMARY_PHASE_MS if phased else SUMMARY_WAIT_MS) and not c.finished:
            return
        self.summary_due = None
        if any(h.out and h.dst == key and h.t > t + 1000 for h in c.hits[-300:]):
            return                                # veio outra fase: a luta continua
        self.show_summary(c, key, now)

    def show_summary(self, c, key, now):
        """Monta o cartão do fim da luta: tempo, a sua parte do dano e as principais conclusões do Dedo Duro."""
        try:
            import dedoduro
            r = dedoduro.analyze(c, key)
            if not r:
                return
            rows = sorted(r["party"] + r["others"], key=lambda p: -p["dmg"])
            mine = next((i for i, p in enumerate(rows) if p.get("me")), None)
            bad = [a for a in r["alerts"] if a["sev"] >= 1]
            e = c.entities.get(key)
            form = c.sprite_log[key][-1][1] if c.sprite_log.get(key) else (e.job if e is not None else 0)
            spec = ("mob", form) if form else None
            sprites.MONSTERS.start(clientdata.NAMES.grf)
            sprites.MONSTERS.image(spec)
            self.summary_card = (dict(
                key=key, sprite=spec, name=c.name_of(key), killed=r["killed"], ms=r["end"] - r["start"],
                share=rows[mine]["share"] if mine is not None else None,
                rank=mine + 1 if mine is not None else None, players=len(rows),
                alerts=[(a["sev"], a["what"], a["who"]) for a in bad[:3]],
                grave=sum(1 for a in bad if a["sev"] == 2), warn=sum(1 for a in bad if a["sev"] == 1)), now)
        except Exception:  # noqa: BLE001 - o resumo é um extra
            self.log_error(*sys.exc_info())
        self.dirty = True

    def open_summary(self):
        """Clique no resumo: abre a análise no Dedo Duro, na luta do cartão."""
        card, self.summary_card = self.summary_card, None
        self.dirty = True
        self.open_analysis()
        if self.analysis is not None and card:
            try:
                self.analysis.dd_key = card[0]["key"]
                self.analysis.select_tab("dedo")
                self.analysis.refresh(force=True)
            except Exception:  # noqa: BLE001
                self.log_error(*sys.exc_info())

    def summary_menu(self):
        m = self.new_menu()
        m.add_command(label=_("Abrir o Dedo Duro desta luta…"), command=self.open_summary)
        m.add_command(label=_("Fechar este resumo"), command=lambda: (setattr(self, "summary_card", None),
                                                                     setattr(self, "dirty", True)))
        m.add_command(label=_("Não mostrar mais o resumo da luta"), command=lambda: self.toggle_cfg("fight_summary"))
        return m

    def draw_summary_card(self):
        """Cartão do fim da luta: verde quando o chefe morreu (azul se não), a sua parte do dano e até 3 conclusões
        do Dedo Duro, cada uma com a bolinha da gravidade dela."""
        if not self.summary_card:
            return
        d, shown = self.summary_card
        title = (_("%s: derrotado em %s") % (d["name"], dur(d["ms"]))) if d["killed"] else _("%s: não morreu") % d["name"]
        lines = []
        if d["share"] is not None:
            lines.append((_("Você: %s do dano · %dº de %d") % (dec("%.1f%%" % (100 * d["share"])), d["rank"],
                                                               d["players"]), CARD_WHITE))
        for sev, what, who in d["alerts"]:
            lines.append(("%s %s · %s" % ("●" if sev == 2 else "◐", what, who), "#fca5a5" if sev == 2 else "#fcd34d"))
        more = d["grave"] + d["warn"] - len(d["alerts"])
        if not d["alerts"]:
            lines.append((_("Nada grave nem de atenção no Dedo Duro"), "#4ade80"))
        elif more > 0:
            lines.append((_("mais %d no Dedo Duro (clique para abrir)") % more, CARD_DIM))
        self.draw_card("summary", shown, SUMMARY_CARD_S, "bom" if d["killed"] else "info", title, lines, d.get("sprite"))

    def show_boss_card(self, c, seq, now):
        """Cartão do chefe que mudou; o que chega do mesmo chefe logo depois entra no mesmo cartão."""
        info = getattr(c, "boss_alerts", {}).get(seq)
        if info is None:
            return
        try:
            info = dict(info)
            cur = self.boss_card[0] if self.boss_card else None
            if (cur and cur["aid"] == info["aid"] and 0 <= info["t"] - cur["t"] <= BOSS_MERGE_MS
                    and not info.get("mech") and not cur.get("mech")):
                info = dict(cur, **{k: v for k, v in info.items() if v is not None})
            if info.get("mech"):                  # mecânica: o HP de quem grava dá o tamanho do golpe que mata
                log = c.hp_log.get(c.me) or ()
                info["hp"] = next((hp for _t, hp, _m in reversed(log) if hp), None)
            e = c.entities.get(info["aid"])
            form = info.get("form") or (c.sprite_log[info["aid"]][-1][1] if c.sprite_log.get(info["aid"])
                                        else (e.job if e is not None else 0))
            info["name"] = c.name_of(info["aid"])
            info["job"] = e.job if e is not None else None
            info["sprite"] = ("mob", form) if form else None
            info["mine"] = analysis.my_attack_element(c, info["t"])
            if not info.get("element") and form:          # forma nova: a propriedade dela, se conhecida
                import dedoduro
                known = dedoduro.BOSS_ELEMENTS.get(form) or (
                    (dedoduro.MOB_DB.get(str(form)) or {}).get("e"), (dedoduro.MOB_DB.get(str(form)) or {}).get("l"))
                if known and known[0]:
                    info["form_element"] = known
            sprites.MONSTERS.start(clientdata.NAMES.grf)
            sprites.MONSTERS.image(info["sprite"])
            self.boss_card = (info, now)
        except Exception:  # noqa: BLE001 - o aviso no rodapé continua
            self.log_error(*sys.exc_info())
        self.dirty = True

    def show_death_card(self, c, seq, now):
        """Monta o resumo da morte (fontes de dano nos 5 s antes) para mostrar por cima das linhas."""
        info = getattr(c, "death_alerts", {}).get(seq)
        if info is None:
            return
        try:
            d = analysis.death_card(c, *info)
            # o desenho do topo, lido do data.grf do jogo: a armadilha, o próprio personagem caído (União, vida
            # que caiu sem golpe) ou o monstro do golpe final
            if d["trap"]:
                d["sprite"] = ("trap",)
            elif d["fusion"] or d["no_hit"]:
                d["sprite"] = ("char", tuple(sorted(c.session.look.items())), tuple(sorted(c.worn_at(info[1]).items())))
            elif d.get("sprite_mob"):
                d["sprite"] = ("mob", d["sprite_mob"])
            grf = clientdata.NAMES.grf
            sprites.MONSTERS.start(grf)
            if d.get("sprite") and d["sprite"][0] == "char":
                sprites.LOADER.start(grf)
            sprites.MONSTERS.image(d.get("sprite"))
            self.death_card = (d, now)
        except Exception:  # noqa: BLE001 - o resumo é um extra; o aviso no rodapé continua
            self.log_error(*sys.exc_info())
        self.dirty = True

    def combat(self):
        f = self.watcher.file
        return f.combat if f is not None and f.ready else None

    def check_recording(self, now):
        """Lembrete de gravação desligada: o jogo está aberto e nenhum replay está sendo escrito há algum tempo."""
        if not self.cfg.get("alert_rec", True):
            self.rec_seen_at = now
            return
        if now - self.game_check_at >= GAME_CHECK_S:
            self.game_check_at = now
            self.game_on = meter.game_running()
        w = self.watcher
        writing = w.file is not None and not w.pinned and now - w.last_change <= w.ACTIVE_S
        if not self.game_on or writing or w.pinned:
            self.rec_seen_at = now
            self.rec_warned = False
        elif self.rec_off(now) and not self.rec_warned:
            self.rec_warned = True                # uma vez por episódio: o rodapé segue avisando
            self.dirty = True
            if self.cfg.get("rec_sound"):
                play_beep(self.cfg["fusion_volume"])

    def rec_off(self, now):
        return bool(self.cfg.get("alert_rec", True)) and self.game_on and now - self.rec_seen_at > REC_OFF_S

    def status(self):
        """(texto, cor_da_bolinha) do rodapé."""
        t = self.t
        now = time.time()
        w = self.watcher
        if not w.folders:
            return _("Pasta Replay não encontrada"), t["live"], False
        f = w.file
        if self.rec_off(now):
            return _("Gravação desligada: ligue o replay no jogo"), t["live"], True
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
                                  ("shot", self.icon("shot"), t["muted"]),
                                  ("pin", self.icon("pin_on" if self.cfg["pinned"] else "pin_off"),
                                   t["accent"] if self.cfg["pinned"] else t["muted"])):
            self.icon_button(key, x, TOP_Y * s, glyph, color)
            x -= 23 * s
        title_right = x + 8 * s
        if cb is not None:
            sess = cb.session
            name = (cb.name_of(cb.me) if meter.HIDE_NAMES else sess.player) or _("Personagem")
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
        active = self.cfg["rate"] == "active"
        lines = []
        if snap:
            if snap["live"]:
                lines.append((_("agora %s/s") % num(snap["dps_now"]), t["accent"]))
            lines.append((_("total %s") % num(snap["my_total"]), t["fg"]))
            if active:
                lines.append((_("batendo %s") % dur(snap["my_active_ms"]), t["muted"]))
            else:
                label = _("em combate") if session else (_("ao vivo") if snap["live"] else _("duração"))
                lines.append((_("%s %s") % (label, dur(snap["duration_ms"])), t["muted"]))
        lines_w = max([self.fonts["small"].measure(txt) for txt, _c in lines] + [0])
        big_text = num(snap["my_adps"] if active else snap["my_dps"]) if snap else "—"
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

        # faixa das informações fixadas (sempre visível, em qualquer aba)
        self.draw_pins(cb)

        # linhas (o resumo da morte fica por cima delas por alguns segundos)
        self.draw_rows(snap)
        if not self.death_card:
            self.draw_boss_card()
            if not self.boss_card:
                self.draw_summary_card()
        self.draw_death()

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
        # /where: mapa e coordenadas de quem grava; o clique copia o /navi
        where = cb.where() if cb is not None else None
        if where and where[1] is not None:
            label = "%s %d/%d" % (where[0], where[1], where[2])
            if self.fonts["small"].measure(label) > (bx - 20 * s) * 0.55:
                label = "%d/%d" % (where[1], where[2])
            bx = self.text_button("where", bx - 6 * s, fy, self.icon("where"), label)
        r = 3.2 * s
        pulse = live and self.phase < 4
        color = t["muted"]
        hint = HINTS.get(self.hover[1] if self.hover and self.hover[0] in ("btn", "tab") else
                         (self.hover[0] if self.hover else None))
        if self.hover and self.hover[0] == "fav":
            hint = _("Clique: favorito · botão direito: fixar ou ocultar")
        if hint and not self.alert:
            text, color = hint, t["fg"]
        elif not self.alert and cb is not None and cb.miracle_left() is not None:
            left = cb.miracle_left()
            doubt = cb.miracle_uncertain() is not None        # depois de morrer ou trocar de mapa
            text = (_("★ Milagre? · %d min (a confirmar)") if doubt else _("★ Milagre · %d min")) % max(
                1, round(left / 60000.0))
            color = self.readable("#fbbf24")
            live = True
        if self.alert:
            # aviso (buff que acabou, morte) no lugar do status, piscando
            text, kind = self.alert[0], self.alert[1]
            dot = t["live"] if kind in ("death", "fusion") else (
                t["accent"] if kind in ("info", "miracle") else "#f59e0b")
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
        self.draw_miracle()

    def draw_miracle(self):
        """Faixa dourada com estrelas quando o Milagre ativa (alguns segundos)."""
        k = time.time() - self.miracle_at
        if not 0 <= k < MIRACLE_BANNER_S:
            return
        c, t, s, W, H = self.canvas, self.t, self.s, self.W, self.H
        grow = min(1.0, k / 0.35)                              # abre rápido
        fade = 1.0 if k < MIRACLE_BANNER_S - 1.2 else max(0.0, (MIRACLE_BANNER_S - k) / 1.2)
        cy = H * 0.42
        hh = 34 * s * grow
        gold = MIRACLE_COLORS[int(k * 8) % 3]
        fill = mix(t["bg"], "#4c1d95", 0.85 * fade)
        c.create_polygon(round_rect_pts(8 * s, cy - hh, W - 8 * s, cy + hh, 10 * s), smooth=True, fill=fill,
                         outline=mix(t["bg"], gold, fade), width=max(2, int(2 * s)))
        if grow < 1:
            return
        rnd = random.Random(int(k * 12))                       # estrelas que piscam
        for _i in range(28):
            x, y = rnd.uniform(14 * s, W - 14 * s), rnd.uniform(cy - hh + 4 * s, cy + hh - 4 * s)
            size = rnd.uniform(7, 15) * s
            col = mix(t["bg"], rnd.choice(MIRACLE_COLORS), fade * rnd.uniform(0.45, 1.0))
            c.create_text(x, y, text=rnd.choice("★✦✧⋆"), fill=col, font=("Segoe UI Symbol", -int(size)))
        c.create_text(W / 2, cy - 8 * s, text=_("★ MILAGRE ★"), fill=mix(t["bg"], "#fde68a", fade),
                      font=self.fonts["big_s"])
        c.create_text(W / 2, cy + 18 * s, text=_("todos os monstros são alvos estelares por 1 hora"),
                      fill=mix(t["bg"], "#f5f3ff", fade), font=self.fonts["small"])

    # ------------------------------------------------------------ resumo da morte

    def death_texts(self, d):
        """(causa, overkill, resumo) do resumo da morte, já no idioma da pessoa."""
        kill = next((g for g in d["sources"] if g["killing"]), None)
        if d["trap"]:
            cause = _("Armadilha do mapa") + (_(" (~%d%% do HP máx.)") % round(d["trap_pct"] * 100)
                                              if d["trap_pct"] else "")
        elif d["fusion"]:
            cause = _("União Solar: atacou com %s de HP") % (
                "%d%%" % round(d["hp_pct"] * 100) if d["hp_pct"] is not None else _("pouco"))
        elif d["special"] == "offscreen":
            cause = _("Provável golpe de %s fora da tela · sobrecarga há %d s") % (
                d["killer"], round(d["overload_ms"] / 1000.0))
        elif kill is not None and not d["unclear"]:
            cause = _("Golpe final: %s") % self.source_label(dict(kill, count=1))
            el = analysis.element_name(kill["element"])
            if el:
                cause += " · " + el
        elif d["no_hit"]:
            cause = _("Sem golpe visível: a vida caiu sem um ataque no replay")
        elif kill is not None:
            # o golpe visível sozinho não bastava (ex.: reflexo da Dor Máxima): fica com quem bateu por último
            cause = _("Último golpe visível: %s") % self.source_label(dict(kill, count=1))
        elif d["unclear"]:
            cause = _("Causa incerta: o último golpe visível não bastava")
        else:
            cause = ""
        over = (_("overkill %s") % num(d["overkill"])) if d["overkill"] and not d["fusion"] else ""
        secs = d["window"] / 1000.0          # 5 s, ou menos se a vida voltou a 95% no meio do caminho
        span = ("%d s" % round(secs)) if secs >= 4.95 else dec("%.1f s" % secs)
        summary = (_("%s em %d golpe nos últimos %s") if d["hits"] == 1 else _("%s em %d golpes nos últimos %s")) % (
            num(d["total"]), d["hits"], span)
        if d["max_hp"]:
            summary += " · " + _("HP máx. %s") % num(d["max_hp"])
        return cause, over, summary

    def source_label(self, g):
        """'Monstro ×N · skill' (armadilha e HP sem golpe só com o nome)."""
        who = g["source"] + (" ×%d" % g["count"] if g["count"] > 1 else "")
        return "%s · %s" % (who, g["skill"]) if g["element"] is not None or g["count"] else who

    def shown_sources(self, d, n):
        """As n maiores fontes, sempre com a do golpe final (no lugar da última, se ela não couber)."""
        out = d["sources"][:max(0, n)]
        kill = next((g for g in d["sources"] if g["killing"]), None)
        if out and kill is not None and kill not in out:
            out[-1] = kill
        return out

    def draw_death(self):
        """Resumo da morte (10 s, clique fecha): o widget escurece com uma moldura vermelha e um cartão no meio
        mostra o monstro que deu o golpe final, a causa e quem mais bateu nos 5 s antes, com a propriedade do ataque."""
        if not self.death_card:
            return
        d, shown = self.death_card
        k = time.time() - shown
        if not 0 <= k < DEATH_CARD_S:
            return
        c, s, W, H = self.canvas, self.s, self.W, self.H
        left = 1.0 - k / DEATH_CARD_S
        x0, x1 = 8 * s, W - 8 * s
        y0, y1 = (TOP_Y + 14) * s, H - (FOOT_H + 2) * s
        pad = 10 * s
        white, dim = "#ffffff", "#d79a9a"
        fw = max(2, int(3 * s))                # moldura vermelha em volta do widget
        c.create_rectangle(fw / 2, fw / 2, W - fw / 2, H - fw / 2, outline=DEATH_RED, width=fw)
        c.create_polygon(round_rect_pts(x0, y0, x1, y1, 10 * s), smooth=True, fill=DEATH_CARD_BG,
                         outline=DEATH_RED, width=max(1, int(1.5 * s)))
        self.hits.append((("death", None), (x0, y0, x1, y1)))
        cause, over, summary = self.death_texts(d)

        refl = d.get("reflected")             # Dor Máxima: o golpe que foi refletido ganha uma linha

        def text_h(n):                     # título + causa (+ reflexo) + fontes + resumo
            return (26 + 16 + (14 if refl else 0) + 17 * n + 16 + 8) * s
        # o sprite do monstro fica com o espaço que sobra; sem monstro (União, sem golpe visível...), uma caveira
        spec = d.get("sprite")
        want = sprites.MONSTERS.expected(spec)
        n = min(4, len(d["sources"]))
        # uma 4ª fonte só entra se o sprite continuar grande; senão, menos fontes antes de encolher o sprite
        while n > 1 and (y1 - y0) - pad - text_h(n) < (80 if n > 3 else 44) * s:
            n -= 1
        sprite_h = min((80 if want else 56) * s, (y1 - y0) - pad - text_h(n))
        if sprite_h < 30 * s:
            sprite_h = 0
        y = y0 + pad
        cid = c.create_text(x1 - pad, y + 5 * s, anchor="e", text="%d s  ✕" % max(1, round(left * DEATH_CARD_S)),
                            font=self.fonts["small"], fill=dim)
        if sprite_h:
            cx, foot = (x0 + x1) / 2, y + sprite_h
            c.create_oval(cx - 34 * s, foot - 5 * s, cx + 34 * s, foot + 3 * s, fill="#3a0f0f", outline="")
            room_w = (x1 - x0) - 2 * pad - 2 * (c.bbox(cid)[2] - c.bbox(cid)[0])
            if want:
                photo = self.sprite_photo(spec, int(sprite_h), int(room_w))
                if photo is not None:
                    c.create_image(cx, foot, anchor="s", image=photo)
            else:
                r = sprite_h * 0.40
                self.draw_skull(cx, foot - r * 1.15, r)
            y = foot + 4 * s
        nth = d.get("nth", 1)
        title = DEATH_TITLES[min(nth, len(DEATH_TITLES)) - 1]
        if "%d" in title:
            title = title % nth
        self.draw_death_title((x0 + x1) / 2, y + 13 * s, x0 + pad, x1 - pad, icon=want or not sprite_h, title=title)
        if nth > 1:                            # contador no canto: caveira ×N
            self.draw_skull(x0 + pad + 5 * s, y0 + pad + 5 * s, 5 * s)
            c.create_text(x0 + pad + 13 * s, y0 + pad + 5 * s, anchor="w", text="×%d" % nth,
                          font=self.fonts["small"], fill="#fca5a5")
        y += 26 * s
        line = cause + ("  ·  " + over if over else "")
        lid = c.create_text((x0 + x1) / 2, y + 7 * s, text=line, font=self.fonts["small"], fill=white)
        if c.bbox(lid)[2] - c.bbox(lid)[0] > x1 - x0 - 2 * pad:
            c.itemconfigure(lid, anchor="w")
            c.coords(lid, x0 + pad, y + 7 * s)
            self.clip_text(lid, line, x1 - pad)
        y += 16 * s
        if refl:
            rtext = _("↩ refletiu %s · %s · %s") % (refl["skill"], _("você") if refl["mine"] else refl["who"],
                                                     num(refl["dmg"]))
            rid = c.create_text((x0 + x1) / 2, y + 5 * s, text=rtext, font=self.fonts["small"], fill="#fca5a5")
            if c.bbox(rid)[2] - c.bbox(rid)[0] > x1 - x0 - 2 * pad:
                c.itemconfigure(rid, anchor="w")
                c.coords(rid, x0 + pad, y + 5 * s)
                self.clip_text(rid, rtext, x1 - pad)
            y += 14 * s
        top = d["sources"][0]["dmg"] if d["sources"] else 1
        row_h = 17 * s
        heat = ("#dc2626", "#ea580c", "#d97706", "#a16207")     # do vermelho ao âmbar, pela posição
        for i, g in enumerate(self.shown_sources(d, n)):
            ry0, ry1 = y + 1 * s, y + row_h - 2 * s
            col = ELEMENT_COLORS.get(g["element"] or "", "#9ca3af")
            frac = g["dmg"] / float(top or 1)
            bx0, bx1 = x0 + pad - 3 * s, x1 - pad + 3 * s
            bw = (bx1 - bx0) * frac
            # barra: a maior fonte em vermelho, as seguintes em laranja e âmbar
            c.create_polygon(round_rect_pts(bx0, ry0, bx1, ry1, 4 * s), smooth=True, fill="#2a0b0b", outline="")
            if bw > 2 * s:
                c.create_polygon(round_rect_pts(bx0, ry0, bx0 + bw, ry1, 4 * s), smooth=True,
                                 fill=mix(DEATH_CARD_BG, heat[min(i, len(heat) - 1)], 0.55), outline="")
            cy = (ry0 + ry1) / 2
            r = 3.2 * s
            c.create_oval(x0 + pad + 2 * s - r, cy - r, x0 + pad + 2 * s + r, cy + r, fill=col, outline="")
            rid = c.create_text(x1 - pad, cy, anchor="e", text="%d%%" % round(g["share"] * 100),
                                font=self.fonts["small"], fill=dim)
            vid = c.create_text(c.bbox(rid)[0] - 6 * s, cy, anchor="e", text=num(g["dmg"]), font=self.fonts["small"],
                                fill=white)
            el = analysis.element_name(g["element"])
            label = ("✝ " if g["killing"] else "") + self.source_label(g) + ("  (%s)" % el if el else "")
            lid = c.create_text(x0 + pad + 9 * s, cy, anchor="w", text=label, font=self.fonts["small"], fill=white)
            self.clip_text(lid, label, c.bbox(vid)[0] - 6 * s)
            y += row_h
        sid = c.create_text((x0 + x1) / 2, y1 - 13 * s, text=summary, font=self.fonts["small"], fill=dim)
        if c.bbox(sid)[2] - c.bbox(sid)[0] > x1 - x0 - 2 * pad:
            c.itemconfigure(sid, anchor="w")
            c.coords(sid, x0 + pad, y1 - 13 * s)
            self.clip_text(sid, summary, x1 - pad)
        # contagem regressiva: linha que encolhe na borda de baixo
        c.create_line(x0 + 10 * s, y1 - 3 * s, x0 + 10 * s + (x1 - x0 - 20 * s) * left, y1 - 3 * s,
                      fill=DEATH_RED, width=max(2, int(2 * s)))

    def draw_death_title(self, cx, cy, xl, xr, icon=True, title=None):
        """O título ('V O C Ê  M O R R E U') com as letras espaçadas entre duas linhas finas, e a caveira à
        esquerda; um título comprido demais para espaçar sai com as letras juntas."""
        c, s = self.canvas, self.s
        title = title or _("VOCÊ MORREU")
        f = self.fonts["spaced"]
        room = xr - xl - (26 * s if icon else 0) - 2 * 18 * s
        spaced = " ".join(title).replace("   ", "  ")
        if f.measure(spaced) > room:
            spaced = title
        tw = f.measure(spaced)
        c.create_text(cx, cy, text=spaced, font=f, fill="#fca5a5")
        gap = 10 * s
        line = mix(DEATH_CARD_BG, DEATH_RED, 0.8)
        c.create_line(xl + (26 * s if icon else 0), cy, cx - tw / 2 - gap, cy, fill=line, width=1)
        c.create_line(cx + tw / 2 + gap, cy, xr, cy, fill=line, width=1)
        if icon:                               # sem a caveira grande no topo, uma pequena ao lado do título
            self.draw_skull(xl + 10 * s, cy, 9 * s)

    def draw_skull(self, cx, cy, r):
        """Caveira desenhada (crânio, olhos, nariz e dentes), branca com contorno vermelho."""
        c, s = self.canvas, self.s
        bone, line, hole = "#f5f5f4", "#b91c1c", DEATH_CARD_BG
        c.create_oval(cx - r, cy - r * 1.05, cx + r, cy + r * 0.7, fill=bone, outline=line, width=max(1, int(s)))
        c.create_polygon(round_rect_pts(cx - r * 0.55, cy + r * 0.25, cx + r * 0.55, cy + r * 1.05, r * 0.25),
                         smooth=True, fill=bone, outline=line, width=max(1, int(s)))
        for side in (-1, 1):
            ex = cx + side * r * 0.42
            c.create_oval(ex - r * 0.27, cy - r * 0.2, ex + r * 0.27, cy + r * 0.3, fill=hole, outline="")
        c.create_polygon(cx, cy + r * 0.32, cx - r * 0.13, cy + r * 0.55, cx + r * 0.13, cy + r * 0.55, fill=hole)
        for tx in (-0.2, 0.0, 0.2):
            c.create_line(cx + tx * r, cy + r * 0.72, cx + tx * r, cy + r * 1.0, fill=hole, width=1)

    def sprite_photo(self, spec, max_h, max_w):
        """O desenho do resumo (monstro, armadilha ou personagem caído, do data.grf do jogo) do tamanho pedido;
        None enquanto carrega ou se não houver."""
        img = sprites.MONSTERS.image(spec)
        if img is None or max_h < 8 or max_w < 8:
            return None
        w, h, px = img
        f = min(max_h / float(h), max_w / float(w), 2.0)
        tw, th = max(1, int(round(w * f))), max(1, int(round(h * f)))
        key = (repr(spec), tw, th)
        if key in self.sprite_photos:
            return self.sprite_photos[key]
        if len(self.sprite_photos) > 40:
            self.sprite_photos = {}
        try:
            px2 = px if (tw, th) == (w, h) else sprites.resize(w, h, px, tw, th)
            photo = tk.PhotoImage(master=self.root, data=sprites.png_b64(tw, th, px2), format="png")
        except (tk.TclError, ValueError, IndexError, ZeroDivisionError):
            photo = None                       # desenho estranho: o cartão aparece sem o sprite
        self.sprite_photos[key] = photo
        return photo

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
        y = self.rows_y0() * s
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
                rate = p["adps"] if self.cfg["rate"] == "active" else p["dps"]
                if self.cfg["show_pct"]:
                    right = pct
                elif self.base_w() >= 340:
                    right = "%s/s · %s" % (num(rate), pct)
                else:
                    right = "%s/s" % num(rate)
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
        elif tab == "drops":
            cb = self.combat()
            items, favs = self.drop_items(cb)
            top = max([r["mine"] + r["mvp"] for r in items] + [1])
            first = max(0, min(self.drop_scroll, len(items) - n))
            self.drop_scroll, self.drop_view = first, (first, n, len(items))
            for r in items[first:first + n]:
                rows.append(dict(label=r["name"], value="×%d" % (r["mine"] + r["mvp"]),
                                 right=_("prêmio de MVP") if r["mvp"] else "", frac=(r["mine"] + r["mvp"]) / float(top),
                                 me=True, item=r["item"], fav=r["item"] in favs, pin="item:%d" % r["item"],
                                 color=self.item_color(r["item"])))
            if not items:
                hidden = self.hidden_items()
                msg = (_("Você não pegou nenhum item aqui."),
                       _("%d itens ocultos: botão direito › Itens ocultos") % len(hidden) if hidden else
                       _("O que caiu no chão e o que outros pegaram fica na análise (aba Drops)."))
        elif tab == "xp":
            rows = self.xp_rows(self.combat())[:n]
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
            lx = x0 + 7 * s
            if "item" in r:                    # estrela de favorito (clique marca/desmarca)
                star = c.create_text(lx, cy, anchor="w", text="★" if r["fav"] else "☆", font=self.fonts["text"],
                                     fill="#fbbf24" if r["fav"] else mix(fg, t["muted"], 0.4))
                bx = c.bbox(star)
                # área de clique generosa: do começo da linha até depois da estrela, na altura toda da linha
                self.hits.append((("fav", r["item"]), (x0, y, bx[2] + 6 * s, y1)))
                lx = bx[2] + 5 * s
            lid = c.create_text(lx, cy, anchor="w", text=r["label"], font=self.fonts["text"],
                                fill=self.readable(r.get("color")) or fg)
            self.clip_text(lid, r["label"], c.bbox(vid)[0] - 8 * s)
            if r.get("pin"):                   # botão direito na linha: fixar, ocultar...
                self.hits.insert(0, (("row", r["pin"]), (x0, y, x1, y1)))
            y += ROW_H * s
        first, shown, total = self.drop_view if tab == "drops" else (0, 0, 0)
        if total > shown > 0:                  # barrinha de rolagem: tem mais itens (roda do mouse)
            top_y, h = self.rows_y0() * s, shown * ROW_H * s - 3 * s
            c.create_line(W - 4 * s, top_y, W - 4 * s, top_y + h, fill=t["track"], width=max(2, int(2 * s)))
            a = top_y + h * first / total
            c.create_line(W - 4 * s, a, W - 4 * s, a + max(8 * s, h * shown / total), fill=t["muted"],
                          width=max(2, int(2 * s)))

    # ------------------------------------------------------------ drops, XP e faixa fixa

    def view_rng(self, cb, pad=False):
        """Recorte da visão escolhida: None = tudo; senão a luta (pad: com a folga dos drops que caem depois)."""
        if cb is None or self.cfg["session"]:
            return None
        enc = cb.encounter(self.enc_back)
        if enc is None:
            return None
        return (enc.start - 2000, enc.last + 30000) if pad else (enc.start, enc.last)

    def drop_items(self, cb):
        """Itens que quem grava pegou na visão atual, sem os ocultos, com os favoritos no topo."""
        marked = self.cfg.get("drop_favs") or []
        hidden = self.hidden_items()
        items = [r for r in cb.drop_summary(self.view_rng(cb, pad=True))
                 if (r["mine"] or r["mvp"]) and r["item"] not in hidden]
        items = itemkind.favorites_first(items, marked, lambda r: (-(r["mine"] + r["mvp"]), r["name"]))
        return items, set(marked)

    def item_color(self, item):
        itemkind.start()
        return itemkind.color_of(item, self.cfg, meter.ITEMS.get(str(item), {}).get("name"))

    def readable(self, color):
        """A cor escolhida, escurecida no tema claro para dar para ler."""
        if not color:
            return None
        return mix(color, "#000000", 0.45) if luminance(self.t["bg"]) > 0.5 else color

    def xp_rows(self, cb):
        """Linhas da aba XP (cada uma com a chave para fixar na faixa)."""
        if cb is None:
            return []
        rng = self.view_rng(cb)
        est = xp.estimate(cb, self.cfg, rng)
        kind, _info = est["source"]
        how = {"medido": _("×%s medido"), "fixo": _("×%s fixo"), "auto": _("×%s aproximado")}.get(
            kind, _("×%s pela lista")) % dec("%.2f" % est["factor"])
        rows = []
        # porcentagem do nível primeiro, número absoluto depois (quando o jogo mandou quanto falta para o nível)
        pct = est["pct"] is not None
        rows.append(dict(label=_("XP estimada") if rng is None else _("XP nesta luta"),
                         value=dec("%.2f%%" % est["pct"]) if pct else num(est["xp"]),
                         right=("%s · %s" % (num(est["xp"]), how)) if pct else how, frac=1.0, me=True, pin="xp_total"))
        if est["per_min"] is not None:
            rows.append(dict(label=_("XP por minuto"),
                             value=dec("%.3f%%" % est["per_min_pct"]) if pct else num(est["per_min"]),
                             right=(_("%s/min") % num(est["per_min"])) if pct else "", frac=1.0, me=True, pin="xp_min"))
            rows.append(dict(label=_("XP por hora"),
                             value=dec("%.2f%%" % est["per_hour_pct"]) if pct else num(est["per_hour"]),
                             right=(_("%s/h") % num(est["per_hour"])) if pct else "", frac=1.0, me=True, pin="xp_hour"))
            eta, left = xp.time_to_level(cb, self.cfg)      # pelo ritmo dos últimos minutos de farm
            missing = xp.quests_uncounted(cb, self.cfg)     # missões entregues cuja XP não entra na conta
            if eta is not None:
                right = (_("faltam %s") % num(left)) if left else ""
                if missing and eta:
                    right = _("pode ser menos: missões fora da conta")
                rows.append(dict(label=_("Até o próximo nível"), value=xp.span_text(eta) if eta else _("já subiu"),
                                 right=right, frac=1.0, me=True, pin="xp_eta"))
            elif xp.warming_up(cb, self.cfg):
                rows.append(dict(label=_("Até o próximo nível"), value=_("calculando…"),
                                 right=_("10 min de farm ou 1%"), frac=1.0, me=True, pin="xp_eta"))
        per = (_("%s/min") % dec("%.1f" % est["kills_per_min"])) if est["kills_per_min"] is not None else ""
        if est["unknown"]:
            per = (per + " · " if per else "") + _("%d sem XP") % est["unknown"]
        rows.append(dict(label=_("Abates"), value="%d" % est["kills"], right=per, frac=0.0, me=False, pin="kills"))
        # missões: o que já foi entregue no recorte e o progresso das caças em andamento (dá para fixar na faixa)
        if est["quests"] and not est["quest_xp"]:
            # o jogo não grava quanto a missão rende: por enquanto só avisa que essa XP ficou de fora
            rows.append(dict(label=_("Missões entregues"), value="%d" % len(est["quests"]),
                             right=_("XP fora da conta: estimativa abaixo do real"), frac=0.0, me=False))
        elif est["quests"]:
            nxt_exp = cb.session.next_exp
            known = est["quest_xp"]
            right = _("%d entregue(s)") % len(est["quests"])
            if est["quests_unknown"]:
                right += " · " + _("%d sem XP conhecida") % est["quests_unknown"]
            rows.append(dict(label=_("XP de missões"),
                             value=dec("%.2f%%" % (100.0 * known / nxt_exp)) if nxt_exp else num(known),
                             right=right, frac=1.0, me=True))
        for h in xp.hunts(cb)[:3]:
            rows.append(dict(label=quests.title(h["quest"]), value=" · ".join("%d/%d" % p for p in h["parts"]),
                             right=dec("%.0f%%" % (100.0 * h["count"] / h["goal"])) if h["goal"] else "",
                             frac=min(1.0, h["count"] / float(h["goal"])) if h["goal"] else 0.0, me=False,
                             pin="quest:%d" % h["quest"]))
        pr = xp.progress(cb, self.cfg)
        prog = meter.level_progress(cb.session)
        if pr is not None and pr["pct"] is not None:   # onde está agora: o último ponto exato + a XP estimada
            rows.append(dict(label=_("Nível %d") % pr["level"], value=dec("%.1f%%" % min(100.0, pr["pct"])),
                             right=_("agora (sem as missões)") if xp.quests_uncounted(cb, self.cfg)
                             else _("agora (estimado)"), frac=min(1.0, pr["pct"] / 100.0), me=False, pin="level"))
        elif prog is not None:
            rows.append(dict(label=_("Nível %d") % cb.session.base_level, value=dec("%.1f%%" % (100 * prog)),
                             right=_("no início da gravação"), frac=prog, me=False, pin="level"))
        nxt = meter.xp_after(getattr(cb, "path", None), cb.session)
        if nxt and nxt["gain"] is not None:
            rows.append(dict(label=_("XP real até a próxima gravação"), value="+" + num(nxt["gain"]), right="",
                             frac=1.0, me=False))
        return rows

    def pin_texts(self, cb):
        """[(chave, rótulo, valor, detalhe, cor)] das informações fixadas, na ordem em que foram fixadas."""
        pins = self.cfg.get("pins") or []
        stats = {}
        if any(not p.startswith("item:") for p in pins):
            stats = {r["pin"]: r for r in self.xp_rows(cb) if r.get("pin")}
        items = None
        out = []
        for key in pins:
            if key.startswith("item:"):
                item = int(key[5:])
                if items is None:
                    items = {r["item"]: r for r in cb.drop_summary(self.view_rng(cb, pad=True))} if cb else {}
                r = items.get(item)
                out.append((key, meter.item_name(item), "×%d" % ((r["mine"] + r["mvp"]) if r else 0), "",
                            self.item_color(item)))
            elif key.startswith("quest:"):       # caça de missão: some da aba quando é entregue, a faixa avisa
                r = stats.get(key)
                out.append((key, quests.title(int(key[6:])), r["value"] if r else _("entregue ou sem progresso"),
                            r["right"] if r else "", None))
            else:
                r = stats.get(key)
                out.append((key, PIN_LABELS.get(key, key), r["value"] if r else "—", r["right"] if r else "", None))
        return out

    def draw_pins(self, cb):
        """Faixa abaixo das abas com até 2 informações fixadas (botão direito numa linha › Fixar no widget)."""
        if not self.cfg.get("pins"):
            return
        c, s, t, W = self.canvas, self.s, self.t, self.W
        y0, y1 = ROWS_Y0 * s, (ROWS_Y0 + PIN_H - 4) * s
        x0, x1 = 10 * s, W - 10 * s
        c.create_polygon(round_rect_pts(x0, y0, x1, y1, 5 * s), smooth=True, fill=mix(t["bg"], t["accent"], 0.16),
                         outline="")
        cy = (y0 + y1) / 2
        icon = c.create_text(x0 + 7 * s, cy, anchor="w", text=self.icon("pin_on"), font=self.fonts["icon"],
                             fill=t["accent"])
        x = c.bbox(icon)[2] + 6 * s
        parts = self.pin_texts(cb)
        part = (x1 - 6 * s - x) / max(1, len(parts))
        for i, (key, label, value, right, color) in enumerate(parts):
            px0 = x + i * part
            px1 = px0 + part - 10 * s
            if i:
                c.create_line(px0 - 6 * s, y0 + 4 * s, px0 - 6 * s, y1 - 4 * s, fill=mix(t["bg"], t["muted"], 0.5))
            lid = c.create_text(px0, cy, anchor="w", text=label, font=self.fonts["small"],
                                fill=self.readable(color) or t["muted"])
            self.clip_text(lid, label, px1 - 30 * s)
            text = value + (" · " + right if right else "")
            vid = c.create_text(c.bbox(lid)[2] + 5 * s, cy, anchor="w", text=text, font=self.fonts["text"],
                                fill=t["fg"])
            if c.bbox(vid)[2] > px1 and right:      # sem espaço: fica só o valor
                c.itemconfigure(vid, text=value)
            self.clip_text(vid, c.itemcget(vid, "text"), px1)
            self.hits.append((("pinbar", key), (px0 - 4 * s, y0, px1 + 4 * s, y1)))

    def toggle_pin_stat(self, key):
        pins = list(self.cfg.get("pins") or [])
        if key in pins:
            pins.remove(key)
        else:
            pins = (pins + [key])[-MAX_PINS:]          # com 2 fixadas, a mais antiga sai
        self.cfg["pins"] = pins
        self.save()
        self.resize_window()

    def clear_pins(self):
        self.cfg["pins"] = []
        self.save()
        self.resize_window()

    def toggle_fav(self, item):
        favs = list(self.cfg.get("drop_favs") or [])
        if item in favs:
            favs.remove(item)
        else:
            favs.append(item)
        self.cfg["drop_favs"] = favs
        self.save()
        self.drops_changed()

    def hidden_items(self):
        """Itens ocultos: os de sempre (config) e os de agora (até fechar o programa)."""
        return set(self.cfg.get("drop_hidden") or []) | self.session_hidden

    def hide_item(self, item, always):
        if always:
            hidden = list(self.cfg.get("drop_hidden") or [])
            if item not in hidden:
                hidden.append(item)
            self.cfg["drop_hidden"] = hidden
            self.save()
        else:
            self.session_hidden.add(item)
        self.drops_changed()

    def unhide_item(self, item):
        self.session_hidden.discard(item)
        hidden = [i for i in (self.cfg.get("drop_hidden") or []) if i != item]
        if hidden != (self.cfg.get("drop_hidden") or []):
            self.cfg["drop_hidden"] = hidden
            self.save()
        self.drops_changed()

    def unhide_all(self):
        self.session_hidden.clear()
        self.cfg["drop_hidden"] = []
        self.save()
        self.drops_changed()

    def drops_changed(self):
        """Favorito, oculto ou cor mudou: redesenha o widget e a análise."""
        self.dirty = True
        if self.analysis is not None:
            self.analysis.refresh(force=True)

    def hidden_menu(self, parent):
        """Submenu com cada item oculto (clique mostra de novo) e "Mostrar todos"; None se não há."""
        always = list(self.cfg.get("drop_hidden") or [])
        items = always + sorted(i for i in self.session_hidden if i not in always)
        if not items:
            return None
        hm = self.new_menu(parent)
        for item in items:
            when = _("sempre") if item in always else _("até fechar o programa")
            hm.add_command(label=_("Mostrar de novo: %s (%s)") % (meter.item_name(item), when),
                           command=lambda i=item: self.unhide_item(i))
        hm.add_separator()
        hm.add_command(label=_("Mostrar todos os itens ocultos"), command=self.unhide_all)
        return hm

    def pins_menu(self, parent):
        """Submenu "Faixa fixa": as informações que dá para fixar e as fixadas agora."""
        pm = self.new_menu(parent)
        pins = self.cfg.get("pins") or []
        for key, label in PIN_STATS:
            var = self.keep(tk.BooleanVar(self.root, key in pins))
            pm.add_checkbutton(label=label, variable=var, command=lambda k=key: self.toggle_pin_stat(k))
        for key in pins:
            if key.startswith("item:"):
                var = self.keep(tk.BooleanVar(self.root, True))
                pm.add_checkbutton(label=_("Drop: %s") % meter.item_name(int(key[5:])), variable=var,
                                   command=lambda k=key: self.toggle_pin_stat(k))
            elif key.startswith("quest:"):
                var = self.keep(tk.BooleanVar(self.root, True))
                pm.add_checkbutton(label=_("Missão: %s") % quests.title(int(key[6:])), variable=var,
                                   command=lambda k=key: self.toggle_pin_stat(k))
        pm.add_separator()
        pm.add_command(label=_("Até %d. Também dá para fixar com o botão direito numa linha das abas XP e Drops.")
                       % MAX_PINS, state="disabled")
        if pins:
            pm.add_command(label=_("Desafixar tudo"), command=self.clear_pins)
        return pm

    def sound_menu(self, parent):
        """Sons do Milagre e da União (liga/desliga e volume, com teste)."""
        sm = self.new_menu(parent)
        for key, vol_key, label, vol_label, play in (
                ("miracle_sound", "miracle_volume", _("Tocar um som no Milagre"), _("Volume do Milagre"), play_chime),
                ("fusion_sound", "fusion_volume", _("Tocar um som com HP baixo na União"), _("Volume da União"),
                 play_beep)):
            var = self.keep(tk.BooleanVar(self.root, self.cfg[key]))
            sm.add_checkbutton(label=label, variable=var, command=lambda k=key: self.toggle_cfg(k))
            vm = self.new_menu(sm)
            vvar = self.keep(tk.IntVar(self.root, self.cfg[vol_key]))
            for v in CHIME_VOLUMES:
                vm.add_radiobutton(label="%d%%" % v, variable=vvar, value=v,
                                   command=lambda v=v, k=vol_key, p=play: self.set_volume(k, v, p))
            vm.add_separator()
            vm.add_command(label=_("Tocar o som agora"), command=lambda k=vol_key, p=play: p(self.cfg[k]))
            sm.add_cascade(label=vol_label, menu=vm)
            sm.add_separator()
        var = self.keep(tk.BooleanVar(self.root, self.cfg["rec_sound"]))
        sm.add_checkbutton(label=_("Tocar um som quando a gravação estiver desligada"), variable=var,
                           command=lambda: self.toggle_cfg("rec_sound"))
        sm.add_separator()
        sm.add_command(label=_("Os sons só tocam com o aviso do Milagre ou da União ligado."), state="disabled")
        return sm

    def row_menu(self, target):
        """Botão direito numa linha das abas XP e Drops (ou na faixa fixa)."""
        m = self.new_menu()
        kind, key = target
        pins = self.cfg.get("pins") or []
        if kind == "pinbar":
            m.add_command(label=_("Desafixar"), command=lambda: self.toggle_pin_stat(key))
            if len(pins) > 1:
                m.add_command(label=_("Desafixar tudo"), command=self.clear_pins)
        else:
            pin = key if kind == "row" else "item:%d" % key
            m.add_command(label=_("Desafixar do widget") if pin in pins else _("Fixar no widget"),
                          command=lambda: self.toggle_pin_stat(pin))
            if pin.startswith("item:"):
                item = int(pin[5:])
                fav = item in (self.cfg.get("drop_favs") or [])
                m.add_command(label=_("Tirar dos favoritos") if fav else _("Favoritar (fica no topo)"),
                              command=lambda: self.toggle_fav(item))
                m.add_separator()
                m.add_command(label=_("Ocultar até fechar o programa"), command=lambda: self.hide_item(item, False))
                m.add_command(label=_("Ocultar sempre"), command=lambda: self.hide_item(item, True))
        hm = self.hidden_menu(m)
        if hm is not None:
            m.add_cascade(label=_("Itens ocultos"), menu=hm)
        m.add_separator()
        m.add_cascade(label=_("Todas as opções"), menu=self.main_menu(m))
        return m

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
            cursor = {"btn": "hand2", "tab": "hand2", "fav": "hand2", "grip": "size_nw_se"}.get(tgt[0], "")
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

    def rate_menu(self, parent):
        rm = self.new_menu(parent)
        var = self.keep(tk.StringVar(self.root, self.cfg["rate"]))
        for value, label in (("combat", _("Em combate (dano ÷ tempo da luta)")),
                             ("active", _("Ativo (dano ÷ tempo em que cada um estava batendo)"))):
            rm.add_radiobutton(label=label, variable=var, value=value, command=lambda v=value: self.set_rate(v))
        rm.add_separator()
        rm.add_command(label=_("Ativo: pausas de mais de 5 s sem bater não contam (morto, esperando, correndo)"),
                       state="disabled")
        return rm

    def set_volume(self, key, value, play):
        self.cfg[key] = value
        self.save()
        play(value)

    def set_rate(self, value):
        self.cfg["rate"] = value
        self.save()
        self.dirty = True

    def toggle_pct(self):
        self.cfg["show_pct"] = not self.cfg["show_pct"]
        self.save()
        self.dirty = True

    def close_death_card(self):
        self.death_card = None
        self.dirty = True

    def boss_menu(self):
        m = self.new_menu()
        m.add_command(label=_("Fechar este aviso"), command=lambda: (setattr(self, "boss_card", None),
                                                                     setattr(self, "dirty", True)))
        m.add_command(label=_("Não mostrar mais o aviso do chefe"), command=lambda: self.toggle_cfg("alert_boss"))
        return m

    def draw_card(self, hit, shown, secs, sev, title, lines, spec=None):
        """Cartão no padrão único: moldura e título na cor da gravidade, desenho do chefe no alto, linhas centradas e
        a contagem regressiva embaixo. Ocupa sempre a mesma área (das abas até o fim das linhas), então todos têm o
        mesmo tamanho; num widget com poucas linhas o desenho encolhe ou some, e sobram as linhas que couberem."""
        k = time.time() - shown
        if not 0 <= k < secs:
            return
        c, s, W = self.canvas, self.s, self.W
        col = SEV_COLORS[sev]
        x0, x1 = 8 * s, W - 8 * s
        y0 = (TABS_Y0 - 2) * s
        y1 = (self.rows_y0() + self.cfg["rows"] * ROW_H - 3) * s
        pad = 9 * s
        c.create_polygon(round_rect_pts(x0, y0, x1, y1, 10 * s), smooth=True, fill=CARD_BG, outline=col,
                         width=max(1, int(2 * s)))
        self.hits.append(((hit, None), (x0, y0, x1, y1)))
        cx = (x0 + x1) / 2
        cid = c.create_text(x1 - pad, y0 + pad + 4 * s, anchor="e", text="%d s  ✕" % max(1, round(secs - k)),
                            font=self.fonts["small"], fill=CARD_DIM)
        count_w = c.bbox(cid)[2] - c.bbox(cid)[0]
        room = (y1 - y0) - 2 * pad

        def text_h(n):                         # título + n linhas
            return (22 + 14 * n) * s
        n = len(lines)
        while n > 1 and room < text_h(n):
            n -= 1
        sprite_h = 0
        if spec and sprites.MONSTERS.expected(spec):
            sprite_h = min(56 * s, room - text_h(n))
            if sprite_h < 26 * s:
                sprite_h = 0
        if sprite_h:
            foot = y0 + pad + sprite_h
            c.create_oval(cx - 30 * s, foot - 4 * s, cx + 30 * s, foot + 3 * s, fill="#23262f", outline="")
            photo = self.sprite_photo(spec, int(sprite_h), int((x1 - x0) - 2 * pad - 2 * count_w))
            if photo is not None:
                c.create_image(cx, foot, anchor="s", image=photo)
            y = foot + 6 * s
            xr = x1 - pad
        else:                                  # sem desenho: o texto fica no meio da altura
            y = y0 + max(pad, ((y1 - y0) - text_h(n)) / 2)
            xr = x1 - pad - (count_w + 6 * s if y < y0 + pad + 14 * s else 0)
        self.center_text(cx, y + 8 * s, title.upper(), self.fonts["title"], col, x0 + pad, xr)
        y += 22 * s
        for text, fill in lines[:n]:
            self.center_text(cx, y + 5 * s, text, self.fonts["small"], fill or CARD_DIM, x0 + pad, x1 - pad)
            y += 14 * s
        left = 1.0 - k / secs
        c.create_line(x0 + 10 * s, y1 - 3 * s, x0 + 10 * s + (x1 - x0 - 20 * s) * left, y1 - 3 * s, fill=col,
                      width=max(2, int(2 * s)))

    def center_text(self, cx, cy, text, font, fill, xl, xr):
        """Texto centrado em cx; se não couber entre xl e xr, encosta na esquerda e corta com reticências."""
        c = self.canvas
        tid = c.create_text(cx, cy, text=text, font=font, fill=fill)
        b = c.bbox(tid)
        if b[2] - b[0] > xr - xl or b[2] > xr:
            c.itemconfigure(tid, anchor="w")
            c.coords(tid, xl, cy)
            self.clip_text(tid, text, xr)
        return tid

    def draw_boss_card(self):
        """Cartão de 5 s do chefe: o que mudou (propriedade, imunidade, tamanho) com o que bater e o que evitar, ou a
        mecânica que começou (Dor Máxima, Aliviar muito alto, defesa do Aquila)."""
        if not self.boss_card:
            return
        d, shown = self.boss_card
        dim = CARD_DIM
        el = d.get("immune") or d.get("element") or (d.get("form_element") or (None, 1))[0]
        level = 1 if d.get("element") or d.get("immune") else (d.get("form_element") or (None, 1))[1] or 1
        mine = d.get("mine")
        mech = MECH_CARDS.get(d.get("mech"))
        lines = []
        if mech:
            sev = mech[1]
            title = "%s: %s" % (d["name"], _(mech[0]))
            lines = [(_(text), fill) for text, fill in mech[2]]
            if d["mech"] == "maxpain_on" and d.get("hp"):
                # o reflexo é ~11% do golpe: acima de HP ÷ 0,11 o próprio golpe mata quem bateu
                lines.append((_("Golpe acima de %s te mata agora") % num(d["hp"] / analysis.MAXPAIN_RATIO[2]),
                              "#fbbf24"))
            elif d["mech"] == "defense" and d.get("job") in meter.DEF_BREAK_BOSSES:
                lines.append((_("Falta éter verde para a defesa cair"), "#4ade80"))
            elif d["mech"] == "relief":
                lines.append(((_("%d almas ativas ou mais") if d.get("more") else _("%d almas ativas"))
                              % d.get("souls", 0), "#fbbf24"))
                lines.append((_("O chefe está levando %d%% a menos de dano") % d.get("pct", 0), dim))
            el = None
        elif d.get("immune"):
            sev = "grave" if mine == d["immune"] else "atencao"      # grave quando é a propriedade do seu ataque
            title = _("%s: imune a %s") % (d["name"], analysis.element_name(d["immune"]))
        elif d.get("element"):
            sev = "atencao"
            title = _("%s virou %s") % (d["name"], analysis.element_name(d["element"]))
        else:
            sev = "atencao"
            title = (_("%s ficou pequeno") if d.get("size") == "S" else _("%s ficou grande") if d.get("size") == "L"
                     else _("%s ficou médio")) % d["name"]
        if d.get("size") and d.get("prev_size"):
            lines.append((_("Tamanho: %s (era %s)") % (_(SIZE_NAMES.get(d["size"], "?")),
                                                       _(SIZE_NAMES.get(d["prev_size"], "?"))), dim))
        if d.get("immune"):
            lines.append((_("Golpes de %s não tiram dano") % analysis.element_name(d["immune"]), "#f87171"))
        elif el:
            if not d.get("element"):
                lines.append((_("Propriedade: %s %d") % (analysis.element_name(el), level), dim))
            best, avoid = analysis.element_advice(el, level)
            if best:
                lines.append((_("Bata com: %s") % " · ".join("%s %d%%" % (analysis.element_name(a), p)
                                                             for a, p in best), "#4ade80"))
            if avoid:
                lines.append((_("Evite: %s") % " · ".join("%s %d%%" % (analysis.element_name(a), p)
                                                         for a, p in avoid), "#f87171"))
        if mine and (el or d.get("immune")):
            if d.get("immune"):
                pct = 0 if mine == d["immune"] else 100
            else:
                import dedoduro
                pct = ((dedoduro.RATHENA.get("attr") or {}).get(str(level)) or {}).get(mine, {}).get(el)
            if pct is not None:
                lines.append((_("Seu ataque: %s → %d%%") % (analysis.element_name(mine), pct),
                              "#f87171" if pct < 100 else ("#4ade80" if pct > 100 else dim)))
        self.draw_card("bosscard", shown, BOSS_CARD_S, sev, title, lines, d.get("sprite"))

    def death_menu(self):
        """Botão direito no resumo da morte: fechar ou desligar de vez (volta pelo menu de opções)."""
        m = self.new_menu()
        m.add_command(label=_("Fechar este resumo"), command=self.close_death_card)
        m.add_command(label=_("Não mostrar mais o resumo da morte"), command=lambda: self.toggle_cfg("death_card"))
        m.add_command(label=_("Ver todas as mortes na análise…"), command=self.open_deaths)
        return m

    def open_deaths(self):
        self.close_death_card()
        self.open_analysis()
        if self.analysis is not None:
            try:
                self.analysis.select_tab("mortes")
            except Exception:  # noqa: BLE001
                self.log_error(*sys.exc_info())

    def toggle_cfg(self, key):
        self.cfg[key] = not self.cfg[key]
        if key == "death_card" and not self.cfg[key]:
            self.death_card = None
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
        messagebox.showinfo(_("Sobre"), "Replay Master %s\n\n%s\n\n%s" % (
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
        if kind == "fav":                      # estrela na aba Drops: favorito fica sempre no topo
            self.toggle_fav(key)
            return
        actions = {
            "pin": self.toggle_pin, "min": self.minimize, "close": self.quit,
            "more": lambda: self.popup_at(target, self.main_menu),
            "view": lambda: self.popup_at(target, self.view_menu), "reset": self.reset, "chart": self.open_analysis,
            "prev": lambda: self.browse(1), "next": lambda: self.browse(-1), "where": self.copy_where,
            "shot": self.copy_image,
        }
        actions[key]()

    def copy_image(self):
        """Copia o widget como imagem (para colar no Discord). Com "sem nomes", cada jogador aparece como a classe."""
        import clipimg
        cb = self.combat()
        hide = bool(self.cfg.get("copy_hide_names")) and cb is not None
        ok = False
        try:
            if hide:
                meter.HIDE_NAMES = True
                cb.version += 1
            self.hover = None                     # sem o realce do botão que acabou de ser clicado
            self.draw()
            self.root.update_idletasks()
            ok = clipimg.copy_window(self.hwnd)
        except Exception:  # noqa: BLE001
            self.log_error(*sys.exc_info())
        finally:
            if hide:
                meter.HIDE_NAMES = False
                cb.version += 1
        self.alert = (_("Imagem copiada: cole com Ctrl+V") if ok else _("Não deu para copiar a imagem"), "info",
                      time.time())
        self.dirty = True

    def copy_where(self):
        """Copia o /navi de onde quem grava está (no formato do jogo: /navi mapa x/y)."""
        cb = self.combat()
        w = cb.where() if cb is not None else None
        if not w or w[1] is None:
            return
        cmd = "/navi %s %d/%d" % (w[0], w[1], w[2])
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd)
        except tk.TclError:
            return
        self.alert = (_("Copiado: %s") % cmd, "info", time.time())
        self.dirty = True

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
        m.add_cascade(label=_("DPS"), menu=self.rate_menu(m))
        m.add_command(label=_("Zerar"), command=self.reset)
        m.add_separator()
        m.add_command(label=_("Análise completa…"), command=self.open_analysis)
        m.add_command(label=_("Copiar a imagem do widget"), command=self.copy_image)
        hide = self.keep(tk.BooleanVar(self.root, cfg["copy_hide_names"]))
        m.add_checkbutton(label=_("Copiar imagem sem os nomes dos jogadores"), variable=hide,
                          command=lambda: self.toggle_cfg("copy_hide_names"))
        for key, label in (("alert_buffs", _("Avisar quando um buff acabar na luta")),
                           ("alert_death", _("Avisar quando eu morrer (com overkill)")),
                           ("death_card", _("Mostrar o que me matou por 10 s (resumo da morte)")),
                           ("alert_boss", _("Avisos do chefe: propriedade, tamanho e mecânicas (5 s)")),
                           ("fight_summary", _("Resumo no fim da luta contra chefe (Dedo Duro)")),
                           ("alert_rec", _("Lembrar quando o jogo está aberto sem gravar")),
                           ("alert_fusion", _("Avisar HP baixo com a União Solar (Mestre Taekwon)")),
                           ("alert_miracle", _("Festejar o Milagre Solar, Lunar e Estelar (Mestre Taekwon)")),
                           ("auto_tests", _("Salvar testes no boneco sozinho"))):
            var = self.keep(tk.BooleanVar(self.root, cfg[key]))
            m.add_checkbutton(label=label, variable=var, command=lambda k=key: self.toggle_cfg(k))
        m.add_cascade(label=_("Sons"), menu=self.sound_menu(m))
        m.add_cascade(label=_("Faixa fixa"), menu=self.pins_menu(m))
        hm = self.hidden_menu(m)
        if hm is not None:
            m.add_cascade(label=_("Drops ocultos"), menu=hm)

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
        tgt = self.press_target = self.target_at(e.x, e.y)
        if tgt and tgt[0] in ("btn", "tab", "fav"):
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
            rows = int(round(((h0 + e.y_root - y0) / s - self.rows_y0() - 6 - FOOT_H) / ROW_H))
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
            if not moved and self.press_target and self.press_target[0] == "death":
                self.close_death_card()
            elif not moved and self.press_target and self.press_target[0] == "bosscard":
                self.boss_card = None
                self.dirty = True
            elif not moved and self.press_target and self.press_target[0] == "summary":
                self.open_summary()
            elif not moved and not self.watcher.folders:
                self.pick_folder()
            else:
                self.save_position()
        elif self.resize:
            self.resize = None
            self.save()

    def on_right_click(self, e):
        tgt = self.target_at(e.x, e.y)
        if tgt and tgt[0] in ("row", "fav", "pinbar"):
            self.popup(lambda: self.row_menu(tgt), e.x_root, e.y_root)
        elif tgt and tgt[0] == "death":
            self.popup(self.death_menu, e.x_root, e.y_root)
        elif tgt and tgt[0] == "bosscard":
            self.popup(self.boss_menu, e.x_root, e.y_root)
        elif tgt and tgt[0] == "summary":
            self.popup(self.summary_menu, e.x_root, e.y_root)
        else:
            self.popup(self.main_menu, e.x_root, e.y_root)

    def on_wheel(self, e):
        if e.state & 0x4:                                   # Ctrl
            self.set_scale(self.cfg["scale"] * (1.08 if e.delta > 0 else 1 / 1.08))
        elif self.cfg["tab"] == "drops":                    # rola a lista de itens (3 por "clique" da roda)
            first, shown, total = self.drop_view
            step = DROP_SCROLL_ROWS * max(1, abs(e.delta) // 120)
            new = max(0, min(total - shown, first + (-step if e.delta > 0 else step)))
            if new != first:
                self.drop_scroll = new
                self.dirty = True


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
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RODpsMeter.ReplayMaster")
        except (OSError, AttributeError):
            pass
    root = tk.Tk()
    path = sys.argv[1] if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]) else None
    DpsApp(root, path)
    root.mainloop()


if __name__ == "__main__":
    main()
