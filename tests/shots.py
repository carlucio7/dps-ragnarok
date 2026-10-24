# -*- coding: utf-8 -*-
"""Abre o medidor com config limpa e tira prints com PrintWindow.

A janela fica atrás das outras (sem "sempre no topo"); PrintWindow funciona
mesmo encoberta, então não atrapalha quem está jogando.
"""

import ctypes
import os
import struct
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
user32.GetWindowDC.restype = ctypes.c_void_p
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetWindowDC.argtypes = [ctypes.c_void_p]
user32.PrintWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]


def capture(hwnd, w, h, path):
    wdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(wdc)
    bmp = gdi32.CreateCompatibleBitmap(wdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)                 # PW_RENDERFULLCONTENT
    hdr = struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0) + b"\0" * 16
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.c_char_p(hdr), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, wdc)
    raw = bytearray()
    data = buf.raw
    for row in range(h):
        raw.append(0)
        line = data[row * w * 4:(row + 1) * w * 4]
        for i in range(0, len(line), 4):
            raw += bytes((line[i + 2], line[i + 1], line[i]))

    def chunk(k, d):
        return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


class Shooter:
    def __init__(self, out):
        self.out = out
        os.makedirs(out, exist_ok=True)
        os.environ["RODPS_CONFIG"] = os.path.join(out, "config.json")
        with open(os.environ["RODPS_CONFIG"], "w", encoding="utf-8") as f:
            f.write('{"pinned": false, "alpha": 1.0, "x": 200, "y": 200, "folder": "%s"}'
                    % out.replace("\\", "\\\\"))
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        import tkinter as tk
        import dpsmeter
        self.root = tk.Tk()
        self.app = dpsmeter.DpsApp(self.root)
        self.pump(0.6)

    def pump(self, secs):
        end = time.monotonic() + secs
        while time.monotonic() < end:
            self.root.update()
            self.root.lower()
            if self.app.analysis is not None:
                self.app.analysis.top.lower()
            time.sleep(0.01)

    def shot(self, name):
        app = self.app
        app.draw()
        self.pump(0.2)
        w, h = self.root.winfo_width(), self.root.winfo_height()
        path = os.path.join(self.out, name + ".png")
        capture(app.hwnd, w, h, path)
        print("print:", path, "(%dx%d, dpi %.2f)" % (w, h, app.dpi))

    def shot_window(self, top, name):
        self.pump(0.3)
        hwnd = int(top.wm_frame(), 16)
        r = (ctypes.c_long * 4)()
        user32.GetWindowRect(hwnd, r)
        path = os.path.join(self.out, name + ".png")
        capture(hwnd, r[2] - r[0], r[3] - r[1], path)
        print("print:", path)
