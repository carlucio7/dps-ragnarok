# -*- coding: utf-8 -*-
"""Velocidade das prévias da aba Cartões: cada destaque do resumo da sessão (as cenas com uma volta inteira da
animação) e cada cartão do programa, com os desenhos do jogo se o data.grf estiver lá. Mede o tempo de cada quadro e o
maior tempo que o laço do Tk ficou parado (o programa inteiro travado). Depois passa por todas de novo, rápido: o que
cresceu entre a primeira e a segunda volta (imagens do Tk, objetos GDI, memória) é vazamento. Rode na área de trabalho
oculta, para nada aparecer na tela (uns 4 min):

    python C:\\Users\\carlu\\Claude\\icue-macro-tool\\tests\\hidden.py --timeout 400 tests\\preview_speed.py [zoom] [linhas]

Nasceu da 1.12.0-teste1: a prévia do "Nível máximo" remontava a cena inteira a cada quadro (~0,6 s por quadro, o
programa todo travava). O primeiro segundo de cada prévia (quando a cena monta os desenhos do jogo) conta à parte."""
import ctypes
import ctypes.wintypes as wt
import gc
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
ZOOM = float(sys.argv[1]) if len(sys.argv) > 1 else 1.24
ROWS = int(sys.argv[2]) if len(sys.argv) > 2 else 11
FRAME_MS = 40          # mediana de um quadro depois do primeiro segundo
STALL_MS = 250         # o laço do Tk parado depois do primeiro segundo
BUILD_MS = 600         # o laço parado no primeiro segundo (montando os desenhos da cena)
GROW = dict(imagens=30, gdi=30, mb=12.0)     # o que pode crescer da primeira para a segunda volta
TMP = tempfile.mkdtemp(prefix="rmprevia_")
os.environ["RODPS_CONFIG"] = os.path.join(TMP, "config.json")
os.environ["RODPS_LANG"] = "pt"
json.dump(dict(pinned=False, x=200, y=200, folder=os.path.join(TMP, "Replay"), rows=ROWS, alert_rec=False, lang="pt",
               scale=ZOOM, width=301, theme="Grafite", pins=["xp_eta"]), open(os.environ["RODPS_CONFIG"], "w"))
os.makedirs(os.path.join(TMP, "Replay"))
ctypes.windll.shcore.SetProcessDpiAwareness(1)
import tkinter as tk  # noqa: E402
import meter  # noqa: E402
meter.find_replay_dirs = lambda: []
import dpsmeter  # noqa: E402
import clientdata  # noqa: E402
import sprites  # noqa: E402
import session as S  # noqa: E402
import cards  # noqa: E402


class Mem(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [(n, ctypes.c_size_t) for n in (
        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
        "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


k32, u32, psapi = ctypes.windll.kernel32, ctypes.windll.user32, ctypes.windll.psapi
k32.GetCurrentProcess.restype = wt.HANDLE
u32.GetGuiResources.argtypes = [wt.HANDLE, wt.DWORD]
psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD]


def counts():
    gc.collect()
    h = k32.GetCurrentProcess()
    m = Mem()
    m.cb = ctypes.sizeof(m)
    psapi.GetProcessMemoryInfo(h, ctypes.byref(m), m.cb)
    return dict(imagens=len(root.tk.splitlist(root.tk.call("image", "names"))), gdi=u32.GetGuiResources(h, 0),
                mb=m.PrivateUsage / 1048576.0)


root = tk.Tk()
app = dpsmeter.DpsApp(root)
app.save = lambda *a, **k: None
game = r"C:\Gravity\Ragnarok\Replay"
if os.path.isdir(game):
    clientdata.NAMES.use_folder(game)
if clientdata.NAMES.grf:
    sprites.MONSTERS.start(clientdata.NAMES.grf)
    sprites.LOADER.start(clientdata.NAMES.grf)
    t0 = time.time()
    while (sprites.MONSTERS.book is None or sprites.LOADER.wardrobe is None) and time.time() - t0 < 60:
        root.update()
        time.sleep(0.2)
print("zoom %.2f · s %.2f · %d linhas · desenhos do jogo: %s" % (ZOOM, app.s, ROWS,
                                                               "sim" if sprites.MONSTERS.book is not None else "não"))
app.open_analysis()
an = app.analysis
an.top.geometry("1180x860+60+40")
an.select_tab("cartoes")
an.refresh(force=True)
tab = an.cards_tab
pv = tab.preview
frames, beats = [], []
orig = pv.redraw


def timed():
    t = time.perf_counter()
    orig()
    frames.append((t, time.perf_counter() - t))


pv.redraw = timed


def beat():
    beats.append(time.perf_counter())
    root.after(20, beat)


root.after(20, beat)


def run(sec):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.005)


fails = []


def measure(label, sec, select, quiet):
    del frames[:]
    t0 = time.perf_counter()
    select()
    del beats[:]
    beats.append(t0)
    run(sec)
    if quiet:
        return
    late = [b for b in frames if b[0] >= t0 + 1.0]
    ts = sorted(d for _t, d in late)
    gaps = [(b - a, b) for a, b in zip(beats, beats[1:])]
    build = max([g for g, b in gaps if b < t0 + 1.0] or [0.0])
    stall = max([g for g, b in gaps if b >= t0 + 1.0] or [0.0])
    med = ts[len(ts) // 2] if ts else 0.0
    bad = [name for name, over in (("quadro", med * 1000 > FRAME_MS), ("parado", stall * 1000 > STALL_MS),
                                   ("montagem", build * 1000 > BUILD_MS)) if over]
    print("%-24s %3d quadros · mediana %3.0f ms · pior %4.0f ms · parado %4.0f ms · 1º segundo %4.0f ms%s"
          % (label, len(frames), med * 1000, (ts[-1] if ts else 0.0) * 1000, stall * 1000, build * 1000,
             "  <-- " + ", ".join(bad) if bad else ""))
    if bad:
        fails.append(label)


def cycle(quiet):
    tab.pages.select(tab.page_ses)
    run(0.5)
    for key in S.HL_KEYS:
        scene = S.FX.get(key) in dpsmeter.SCENE_FX
        sec = 1.5 if quiet else (dpsmeter.SESSION_FX_S + 3.5 if scene else 3.0)
        measure("destaque %s" % key, sec, lambda key=key: tab.hl_selected({"key": key}), quiet)
    tab.pages.select(tab.page_sys)
    run(0.5)
    for key, _n, _t, _c in cards.SYSTEM:
        measure("cartão %s" % key, 1.0 if quiet else 3.0, lambda key=key: tab.show_preview(("system", key)), quiet)
    run(1.0)
    return counts()


run(1.0)
start = counts()
first = cycle(False)
second = cycle(True)
print("imagens do Tk %d -> %d -> %d · objetos GDI %d -> %d -> %d · memória %.0f -> %.0f -> %.0f MB (começo -> "
      "1ª volta -> 2ª volta)" % (start["imagens"], first["imagens"], second["imagens"], start["gdi"], first["gdi"],
                                second["gdi"], start["mb"], first["mb"], second["mb"]))
grew = [k for k, lim in GROW.items() if second[k] - first[k] > lim]
if grew:
    fails.append("cresceu na 2ª volta: " + ", ".join(grew))
log = os.path.join(TMP, "erros.log")
if os.path.exists(log):
    print("erros.log:", open(log, encoding="utf-8", errors="replace").read()[-2000:])
    fails.append("erros.log")
print("\n%d falha(s): %s" % (len(fails), "; ".join(fails)) if fails else "\nTUDO OK")
app.quit()
sys.exit(1 if fails else 0)
