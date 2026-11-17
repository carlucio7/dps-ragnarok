# -*- coding: utf-8 -*-
"""Sons curtos gerados na hora (WAV 16 bits mono), para os avisos dos efeitos acompanhados.

Cada som tem um desenho próprio (um toque, dois, três, subindo, descendo, varrendo...), para dar para reconhecer
de ouvido qual efeito avisou mesmo com vários na lista; o tom (grave, médio, agudo, bem agudo) muda a altura de
qualquer um deles. Nada é lido do disco: o som sai das contas abaixo e fica guardado depois da primeira vez.
"""

import math
import random
import struct

RATE = 22050
BASE_HZ = 990.0               # o tom "médio"; os outros tons multiplicam isto (os mesmos do aviso de item)
TONE_MULT = {"grave": 660.0 / BASE_HZ, "medio": 1.0, "agudo": 1480.0 / BASE_HZ, "bem agudo": 2090.0 / BASE_HZ}
DEFAULT = "sino"

# (chave, nome, notas). Nota: (fator da frequência, início s, duração s, timbre[, fator final]); o timbre "sino"
# soa e some aos poucos, "bipe" é reto, "varre" desliza até o fator final, "tambor" é grave com um pouco de ruído,
# "estalo" é um clique curto.
SOUNDS = [
    ("sino", "Sino", [(1.0, 0.0, 0.34, "sino")]),
    ("bipe", "Bipe", [(1.0, 0.0, 0.13, "bipe")]),
    ("bipe2", "Bipe duplo", [(1.0, 0.0, 0.09, "bipe"), (1.0, 0.14, 0.09, "bipe")]),
    ("bipe3", "Bipe triplo", [(1.0, 0.0, 0.07, "bipe"), (1.0, 0.11, 0.07, "bipe"), (1.0, 0.22, 0.07, "bipe")]),
    ("dingdong", "Ding-dong", [(1.26, 0.0, 0.32, "sino"), (1.0, 0.22, 0.42, "sino")]),
    ("sobe", "Subindo", [(1.0, 0.0, 0.12, "bipe"), (1.26, 0.11, 0.12, "bipe"), (1.5, 0.22, 0.18, "bipe")]),
    ("desce", "Descendo", [(1.5, 0.0, 0.12, "bipe"), (1.26, 0.11, 0.12, "bipe"), (1.0, 0.22, 0.18, "bipe")]),
    ("moeda", "Moeda", [(1.0, 0.0, 0.07, "bipe"), (1.335, 0.07, 0.3, "sino")]),
    ("harpa", "Harpa", [(1.0, 0.0, 0.3, "sino"), (1.26, 0.05, 0.3, "sino"), (1.5, 0.10, 0.3, "sino"),
                        (2.0, 0.15, 0.4, "sino")]),
    ("gota", "Gota", [(1.6, 0.0, 0.16, "varre", 0.7)]),
    ("pulo", "Pulo", [(0.7, 0.0, 0.16, "varre", 1.7)]),
    ("sirene", "Sirene", [(0.8, 0.0, 0.25, "varre", 1.3), (1.3, 0.25, 0.25, "varre", 0.8)]),
    ("alarme", "Alarme", [(1.0, 0.0, 0.11, "bipe"), (0.75, 0.12, 0.11, "bipe"), (1.0, 0.24, 0.11, "bipe"),
                          (0.75, 0.36, 0.11, "bipe")]),
    ("trinado", "Trinado", [(1.0 if i % 2 == 0 else 1.12, i * 0.045, 0.045, "bipe") for i in range(9)]),
    ("sonar", "Sonar", [(1.0, 0.0, 0.6, "sino"), (1.0, 0.32, 0.4, "eco")]),
    ("tambor", "Tambor", [(0.16, 0.0, 0.22, "tambor"), (0.16, 0.16, 0.22, "tambor")]),
    ("estalo", "Estalo", [(2.0, 0.0, 0.03, "estalo"), (2.0, 0.09, 0.03, "estalo")]),
]
KEYS = [k for k, _n, _s in SOUNDS]
NAMES = {k: n for k, n, _s in SOUNDS}
_NOTES = {k: s for k, _n, s in SOUNDS}
_WAV = {}


def _note(buf, freq, start, length, kind, end=None):
    i0 = int(start * RATE)
    i1 = min(len(buf), i0 + int(length * RATE))
    fade = max(1, int(RATE * 0.012))
    noise = random.Random(int(freq * 100 + start * 1000))
    phase = 0.0
    for i in range(i0, i1):
        x = (i - i0) / float(RATE)
        k = (i - i0) / float(max(1, i1 - i0))
        f = freq + (freq * end - freq) * k if end else freq                   # "varre": desliza até o fim
        phase += 2 * math.pi * f / RATE
        edge = min(1.0, (i - i0) / float(fade), (i1 - i) / float(fade))      # sem estalo no começo e no fim
        if kind == "sino":
            v = (math.exp(-x * 8.0) * math.sin(phase) + 0.35 * math.exp(-x * 12.0) * math.sin(2 * phase)
                 + 0.12 * math.exp(-x * 17.0) * math.sin(3 * phase))
        elif kind == "eco":
            v = 0.35 * math.exp(-x * 7.0) * math.sin(phase)
        elif kind == "tambor":
            v = math.exp(-x * 18.0) * (math.sin(phase) + 0.25 * (noise.random() * 2 - 1) * math.exp(-x * 60.0))
        elif kind == "estalo":
            v = math.exp(-x * 120.0) * (noise.random() * 2 - 1 + 0.5 * math.sin(phase))
        else:                                                                 # bipe e varre: reto
            v = 0.8 * (math.sin(phase) + 0.25 * math.sin(2 * phase))
        buf[i] += edge * v


def wav(key=DEFAULT, tone="medio", volume=40):
    """O som `key` no tom escolhido, como WAV pronto para tocar. volume: 0–100."""
    key = key if key in _NOTES else DEFAULT
    mult = TONE_MULT.get(tone, 1.0)
    volume = max(0, min(100, int(volume)))
    ck = (key, mult, volume)
    if ck in _WAV:
        return _WAV[ck]
    notes = _NOTES[key]
    length = max(s + d for _f, s, d, *_r in notes) + 0.02
    buf = [0.0] * int(RATE * length)
    for f, start, dur, kind, *rest in notes:
        _note(buf, BASE_HZ * mult * f, start, dur, kind, rest[0] if rest else None)
    peak = max(abs(v) for v in buf) or 1.0
    data = b"".join(struct.pack("<h", int(32767 * 0.5 * volume / 100.0 * v / peak)) for v in buf)
    head = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, RATE,
                                                                                         RATE * 2, 2, 16)
            + b"data" + struct.pack("<I", len(data)))
    _WAV[ck] = head + data
    return _WAV[ck]
