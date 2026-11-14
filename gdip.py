# -*- coding: utf-8 -*-
"""Desenho de imagens com o GDI+ do Windows (gdiplus.dll, por ctypes).

O Tk só sabe ampliar repetindo pixels e reduzir jogando pixels fora: um monstro maior que a caixa, ou montado com
camadas em escala (Betelgeuse usa de 0,4 a 0,7), saía "pixelado". O GDI+ reduz, amplia e gira com suavização, em C,
em milésimos de segundo por quadro. Tudo aqui trabalha com bytes BGRA de cima para baixo (o formato do Windows).
Sem o GDI+ (outro sistema, ou algum erro), ready() diz False e quem chama usa o caminho do Tk.
"""

import ctypes
import os
import threading

_ARGB = 0x26200A                  # PixelFormat32bppARGB
_NEAREST, _SMOOTH = 5, 7          # InterpolationModeNearestNeighbor, HighQualityBicubic
_HALF = 4                         # PixelOffsetModeHalf: o centro do pixel no meio, sem deslocar meio pixel
_FLIP_XY = 3                      # WrapModeTileFlipXY: a borda da imagem não escurece nem some ao suavizar
_PIXEL = 2                        # UnitPixel
_S = {"tried": False, "lib": None, "matrix": None, "attr": None}
_LOCK = threading.RLock()          # a análise desenha na thread da tela e os cartões do widget numa outra


def _lib():
    """A gdiplus.dll iniciada (uma vez), ou None."""
    with _LOCK:
        if not _S["tried"]:
            _S["tried"] = True
            if os.name == "nt":
                try:
                    _S["lib"] = _start()
                except (OSError, AttributeError, ValueError):
                    _S["lib"] = None
        return _S["lib"]


def _start():
    g = ctypes.windll.gdiplus
    P, I, F = ctypes.c_void_p, ctypes.c_int, ctypes.c_float
    PP = ctypes.POINTER(P)
    for name, args in (
            ("GdiplusStartup", [ctypes.POINTER(ctypes.c_size_t), P, P]),
            ("GdipCreateBitmapFromScan0", [I, I, I, I, P, PP]),
            ("GdipDisposeImage", [P]),
            ("GdipGetImageGraphicsContext", [P, PP]),
            ("GdipDeleteGraphics", [P]),
            ("GdipSetInterpolationMode", [P, I]),
            ("GdipSetPixelOffsetMode", [P, I]),
            ("GdipCreateMatrix", [PP]),
            ("GdipSetMatrixElements", [P, F, F, F, F, F, F]),
            ("GdipSetWorldTransform", [P, P]),
            ("GdipCreateImageAttributes", [PP]),
            ("GdipSetImageAttributesWrapMode", [P, I, ctypes.c_uint32, I]),
            ("GdipDrawImageRectRect", [P, P, F, F, F, F, F, F, F, F, I, P, P, P]),
            ("GdipFlush", [P, I])):
        fn = getattr(g, name)
        fn.argtypes, fn.restype = args, I

    class StartupInput(ctypes.Structure):
        _fields_ = [("version", ctypes.c_uint32), ("callback", P), ("no_thread", I), ("no_codecs", I)]
    token = ctypes.c_size_t()
    if g.GdiplusStartup(ctypes.byref(token), ctypes.byref(StartupInput(1, None, 0, 0)), None) != 0:
        return None
    matrix, attr = P(), P()
    if g.GdipCreateMatrix(ctypes.byref(matrix)) != 0 or g.GdipCreateImageAttributes(ctypes.byref(attr)) != 0:
        return None
    g.GdipSetImageAttributesWrapMode(attr, _FLIP_XY, 0, 0)
    _S["matrix"], _S["attr"] = matrix, attr
    return g


def ready():
    return _lib() is not None


class Image:
    """Uma imagem BGRA pronta para ser desenhada. Guarda os próprios bytes: o GDI+ lê direto deles."""

    def __init__(self, w, h, bgra):
        g = _lib()
        if g is None or w <= 0 or h <= 0 or len(bgra) < w * h * 4:
            raise ValueError("imagem que o GDI+ não aceita")
        self.w, self.h = w, h
        self.buf = ctypes.create_string_buffer(bytes(bgra[:w * h * 4]), w * h * 4)
        self.handle = ctypes.c_void_p()
        if g.GdipCreateBitmapFromScan0(w, h, w * 4, _ARGB, self.buf, ctypes.byref(self.handle)) != 0:
            self.handle = None
            raise ValueError("o GDI+ recusou a imagem")

    def close(self):
        handle, self.handle = getattr(self, "handle", None), None
        if handle:
            try:
                _S["lib"].GdipDisposeImage(handle)
            except Exception:  # noqa: BLE001 - o programa está fechando: não há mais o que soltar
                pass

    __del__ = close


def render(w, h, draws):
    """Uma imagem transparente w x h com cada imagem de `draws` desenhada por cima, na ordem.
    draws: [(Image, m11, m12, m21, m22, dx, dy, suave)]: a imagem entra com o centro na origem e a matriz a leva
    para o lugar (x' = x·m11 + y·m21 + dx; y' = x·m12 + y·m22 + dy), o que cobre escala, espelho e giro. `suave`
    liga a suavização (reduções, escalas quebradas, giros); sem ela os pixels saem exatos (escala 1 ou inteira).
    Devolve os bytes BGRA de cima para baixo, ou None se o GDI+ não desenhar."""
    g = _lib()
    if g is None or w <= 0 or h <= 0:
        return None
    with _LOCK:
        return _render(g, w, h, draws)


def _render(g, w, h, draws):
    buf = ctypes.create_string_buffer(w * h * 4)
    bmp, gfx = ctypes.c_void_p(), ctypes.c_void_p()
    if g.GdipCreateBitmapFromScan0(w, h, w * 4, _ARGB, buf, ctypes.byref(bmp)) != 0:
        return None
    ok = False
    try:
        if g.GdipGetImageGraphicsContext(bmp, ctypes.byref(gfx)) != 0:
            return None
        try:
            g.GdipSetPixelOffsetMode(gfx, _HALF)
            mode = None
            ok = True
            for img, m11, m12, m21, m22, dx, dy, smooth in draws:
                want = _SMOOTH if smooth else _NEAREST
                if want != mode:
                    g.GdipSetInterpolationMode(gfx, want)
                    mode = want
                g.GdipSetMatrixElements(_S["matrix"], m11, m12, m21, m22, dx, dy)
                g.GdipSetWorldTransform(gfx, _S["matrix"])
                if g.GdipDrawImageRectRect(gfx, img.handle, -img.w / 2.0, -img.h / 2.0, img.w, img.h,
                                           0.0, 0.0, img.w, img.h, _PIXEL, _S["attr"], None, None) != 0:
                    ok = False
            g.GdipFlush(gfx, 1)
        finally:
            g.GdipDeleteGraphics(gfx)
    finally:
        g.GdipDisposeImage(bmp)
    return buf.raw if ok else None


def resize(w, h, bgra, tw, th):
    """A imagem BGRA w x h redimensionada com suavização para tw x th (bytes BGRA), ou None."""
    try:
        img = Image(w, h, bgra)
    except ValueError:
        return None
    try:
        return render(tw, th, [(img, tw / float(w), 0.0, 0.0, th / float(h), tw / 2.0, th / 2.0, True)])
    finally:
        img.close()


def swap_rb(data):
    """Troca o vermelho com o azul em cada pixel (BGRA <-> RGBA), canal inteiro de uma vez."""
    out = bytearray(data)
    out[0::4], out[2::4] = data[2::4], data[0::4]
    return bytes(out)
