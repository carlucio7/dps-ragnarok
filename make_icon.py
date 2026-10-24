# -*- coding: utf-8 -*-
"""Gera dpsmeter.ico (sem dependências): círculo escuro com três barras de dano."""

import math
import os
import struct
import zlib

BG = (30, 31, 36)
BAR = (120, 124, 138)
ACCENT = (91, 156, 255)
LIVE = (255, 92, 92)
SIZES = [16, 24, 32, 48, 64, 256]
BARS = [(0.27, 0.40, 0.66, BAR), (0.43, 0.56, 0.30, ACCENT), (0.59, 0.72, 0.48, BAR)]   # x0, x1, topo, cor


def pixel(u, v):
    """Cor RGBA de um ponto (u, v) em [0,1]²."""
    x, y = u - 0.5, v - 0.5
    if math.hypot(x, y) > 0.48:
        return (0, 0, 0, 0)
    if math.hypot(u - 0.72, v - 0.27) <= 0.07:
        return (*LIVE, 255)
    for x0, x1, top, col in BARS:
        if x0 <= u <= x1 and top <= v <= 0.76:
            return (*col, 255)
    return (*BG, 255)


def render(size, ss=4):
    rows = []
    for py in range(size):
        row = []
        for px in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    r, g, b, a = pixel((px + (sx + 0.5) / ss) / size, (py + (sy + 0.5) / ss) / size)
                    acc[0] += r * a
                    acc[1] += g * a
                    acc[2] += b * a
                    acc[3] += a
            n = ss * ss
            a = acc[3] / n
            if a <= 0:
                row.append((0, 0, 0, 0))
            else:
                row.append(tuple(int(round(acc[i] / acc[3])) for i in range(3)) + (int(round(a)),))
        rows.append(row)
    return rows


def png(rows):
    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in rows)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def dib(rows):
    h, w = len(rows), len(rows[0])
    pixels = b"".join(bytes((b, g, r, a)) for row in reversed(rows) for (r, g, b, a) in row)
    mask = b"\x00" * (((w + 31) // 32) * 4 * h)
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(pixels) + len(mask), 0, 0, 0, 0)
    return header + pixels + mask


def main():
    images = [(s, png(render(s)) if s >= 256 else dib(render(s))) for s in SIZES]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for s, data in images:
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out += b"".join(data for _, data in images)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dpsmeter.ico")
    with open(path, "wb") as f:
        f.write(out)
    print("ok", path, len(out), "bytes")


if __name__ == "__main__":
    main()
