# -*- coding: utf-8 -*-
"""Copia a imagem de uma janela do programa (ou de um pedaço dela) para a área de transferência, pronta para
colar no Discord ou no WhatsApp. Usa PrintWindow, que funciona mesmo com a janela encoberta, e só olha as janelas
do próprio programa."""

import ctypes
import os
import struct

IS_WIN = os.name == "nt"
CF_DIB = 8
GMEM_MOVEABLE = 0x0002

if IS_WIN:
    user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
    user32.GetWindowDC.restype = ctypes.c_void_p
    user32.GetWindowDC.argtypes = [ctypes.c_void_p]
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.PrintWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
    gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_uint]
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]


def window_rect(hwnd):
    """(esquerda, topo, direita, base) da janela na tela."""
    r = (ctypes.c_long * 4)()
    user32.GetWindowRect(hwnd, r)
    return r[0], r[1], r[2], r[3]


def grab(hwnd):
    """(largura, altura, pixels BGRA de cima para baixo) da janela inteira (com a moldura)."""
    left, top, right, bottom = window_rect(hwnd)
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        return 0, 0, b""
    wdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(wdc)
    bmp = gdi32.CreateCompatibleBitmap(wdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)                 # PW_RENDERFULLCONTENT
    hdr = struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0) + b"\0" * 16
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.SelectObject(mdc, old)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.c_char_p(hdr), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, wdc)
    return w, h, buf.raw


def crop(w, h, pixels, box):
    """Recorta (x0, y0, x1, y1) de uma imagem BGRA de cima para baixo."""
    x0, y0, x1, y1 = (int(v) for v in box)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return 0, 0, b""
    rows = [pixels[(y * w + x0) * 4:(y * w + x1) * 4] for y in range(y0, y1)]
    return x1 - x0, y1 - y0, b"".join(rows)


def dib(w, h, pixels):
    """A imagem no formato da área de transferência (CF_DIB): cabeçalho + linhas de baixo para cima, opaca.
    (O 4º byte de cada pixel vai em 255: alguns programas leem como transparência e colariam uma imagem vazia.)"""
    data = bytearray(pixels)
    data[3::4] = b"\xff" * (w * h)
    stride = w * 4
    flipped = b"".join(bytes(data[y * stride:(y + 1) * stride]) for y in range(h - 1, -1, -1))
    return struct.pack("<IiiHHIIiiII", 40, w, h, 1, 32, 0, len(flipped), 2835, 2835, 0, 0) + flipped


def to_clipboard(w, h, pixels, owner=None):
    """Põe a imagem na área de transferência. True se deu certo."""
    if not IS_WIN or not w or not h:
        return False
    blob = dib(w, h, pixels)
    if not user32.OpenClipboard(owner):
        return False
    try:
        user32.EmptyClipboard()
        mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(blob))
        if not mem:
            return False
        ptr = kernel32.GlobalLock(mem)
        if not ptr:
            kernel32.GlobalFree(mem)
            return False
        ctypes.memmove(ptr, blob, len(blob))
        kernel32.GlobalUnlock(mem)
        if not user32.SetClipboardData(CF_DIB, mem):
            kernel32.GlobalFree(mem)
            return False
        return True
    finally:
        user32.CloseClipboard()


def copy_window(hwnd, box=None):
    """Copia a janela `hwnd` (ou só o retângulo `box`, em pixels dentro dela) para a área de transferência."""
    if not IS_WIN or not hwnd:
        return False
    w, h, pixels = grab(hwnd)
    if box is not None:
        w, h, pixels = crop(w, h, pixels, box)
    return to_clipboard(w, h, pixels)


def copy_widget(top, widget=None):
    """Copia um widget do Tk (por exemplo um gráfico) ou, sem `widget`, o conteúdo da janela `top` sem a barra de
    título."""
    if not IS_WIN:
        return False
    hwnd = int(top.wm_frame(), 16)
    left, upper, _r, _b = window_rect(hwnd)
    target = widget if widget is not None else top
    x0, y0 = target.winfo_rootx() - left, target.winfo_rooty() - upper
    return copy_window(hwnd, (x0, y0, x0 + target.winfo_width(), y0 + target.winfo_height()))
