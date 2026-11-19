# -*- coding: utf-8 -*-
"""Sons curtos gerados na hora (WAV 16 bits mono), para os avisos dos efeitos acompanhados.

Cada som tem um desenho próprio (um toque, dois, três, subindo, descendo, varrendo...), para dar para reconhecer
de ouvido qual efeito avisou mesmo com vários na lista; o tom (grave, médio, agudo, bem agudo) muda a altura de
qualquer um deles. Nada é lido do disco: o som sai das contas abaixo e fica guardado depois da primeira vez.
"""

import math
import os
import random
import struct
import threading
import time

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


# ------------------------------------------------------------------ sons da pasta da pessoa
#
# A pessoa escolhe uma pasta; os .wav e .mp3 que estão nela (não nas subpastas) viram sons para os efeitos
# acompanhados e para os itens marcados. Limites: até CUSTOM_MAX_BYTES por arquivo e no máximo CUSTOM_MAX_S tocando
# (um aviso comprido atropela o próximo); o volume do programa vale para eles, o tom não (é o som da pessoa). O WAV é
# lido aqui (PCM de 8, 16, 24 ou 32 bits, ou ponto flutuante de 32) e tocado da memória como os sons gerados; o MP3
# toca pelo MCI do Windows. Arquivo que sumiu ou não dá para ler: toca o som padrão no lugar.

CUSTOM_EXT = (".wav", ".mp3")
CUSTOM_MAX_BYTES = 10 * 1024 * 1024
CUSTOM_MAX_S = 10.0
CUSTOM_MAX_FILES = 200
CUSTOM_PREFIX = "file:"
_FILES = {}                   # pasta -> (marca da pasta, [(chave, nome)])
_CUSTOM_WAV = {}              # (caminho, tamanho, data, volume) -> WAV pronto


def is_custom(key):
    """A chave é de um som da pasta da pessoa ("file:nome.wav")?"""
    return isinstance(key, str) and key.startswith(CUSTOM_PREFIX) and len(key) > len(CUSTOM_PREFIX)


def valid(key):
    """Chave de som aceitável na configuração: um dos sons do programa ou um da pasta."""
    return key in _NOTES or is_custom(key)


def label(key):
    """O nome do som para a tela: o do programa, ou o nome do arquivo (sem a extensão) com ♪ na frente."""
    if is_custom(key):
        return "♪ " + os.path.splitext(key[len(CUSTOM_PREFIX):])[0]
    return NAMES.get(key, NAMES[DEFAULT])


def custom_sounds(folder):
    """[(chave, nome)] dos sons da pasta, em ordem alfabética (no máximo CUSTOM_MAX_FILES). Arquivos grandes demais
    ficam de fora. A lista é refeita só quando a pasta muda."""
    if not folder:
        return []
    try:
        mark = os.stat(folder).st_mtime_ns
    except OSError:
        return []
    hit = _FILES.get(folder)
    if hit and hit[0] == mark:
        return hit[1]
    out = []
    try:
        names = sorted(os.listdir(folder), key=lambda n: n.lower())
    except OSError:
        names = []
    for name in names:
        if not name.lower().endswith(CUSTOM_EXT):
            continue
        path = os.path.join(folder, name)
        try:
            if not os.path.isfile(path) or os.path.getsize(path) > CUSTOM_MAX_BYTES:
                continue
        except OSError:
            continue
        key = CUSTOM_PREFIX + name
        out.append((key, label(key)))
        if len(out) >= CUSTOM_MAX_FILES:
            break
    _FILES[folder] = (mark, out)
    return out


def custom_path(folder, key):
    """O caminho do arquivo de um som da pasta, ou None se ele não está mais lá (ou é grande demais)."""
    if not folder or not is_custom(key):
        return None
    name = key[len(CUSTOM_PREFIX):]
    if os.path.basename(name) != name:           # só arquivos de dentro da pasta escolhida
        return None
    path = os.path.join(folder, name)
    try:
        if os.path.isfile(path) and os.path.getsize(path) <= CUSTOM_MAX_BYTES:
            return path
    except OSError:
        pass
    return None


def _wav_chunks(data):
    """{id: bytes} dos pedaços de um arquivo RIFF/WAVE, ou None se não for um."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    out, pos = {}, 12
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        out.setdefault(cid, data[pos + 8:pos + 8 + size])
        pos += 8 + size + (size & 1)
    return out


def wav_pcm16(data):
    """(canais, taxa, amostras de 16 bits como bytes) de um WAV de PCM (8, 16, 24 ou 32 bits) ou de ponto flutuante
    de 32 bits, ou None se o formato não é um desses."""
    ch = _wav_chunks(data)
    if not ch or b"fmt " not in ch or b"data" not in ch:
        return None
    fmt = ch[b"fmt "]
    if len(fmt) < 16:
        return None
    tag, chans, rate, _bps, _align, bits = struct.unpack_from("<HHIIHH", fmt, 0)
    if tag == 0xFFFE and len(fmt) >= 26:              # WAVE_FORMAT_EXTENSIBLE: o formato de verdade vem no GUID
        tag = struct.unpack_from("<H", fmt, 24)[0]
    raw = ch[b"data"]
    if not chans or not rate:
        return None
    if tag == 1 and bits == 16:
        pcm = raw[:len(raw) // 2 * 2]
    elif tag == 1 and bits == 8:
        pcm = struct.pack("<%dh" % len(raw), *((b - 128) << 8 for b in raw))
    elif tag == 1 and bits in (24, 32):
        w = bits // 8
        pcm = b"".join(raw[i * w + w - 2:i * w + w] for i in range(len(raw) // w))   # os 2 bytes mais altos
    elif tag == 3 and bits == 32:
        n = len(raw) // 4
        vals = struct.unpack("<%df" % n, raw[:n * 4])
        pcm = struct.pack("<%dh" % n, *(max(-32768, min(32767, int(v * 32767))) for v in vals))
    else:
        return None
    return chans, rate, pcm


def custom_wav(path, volume=40):
    """O WAV da pessoa pronto para tocar da memória: em 16 bits, cortado em CUSTOM_MAX_S (com um fim suave) e no
    volume pedido (0–100). None se não deu para ler."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    volume = max(0, min(100, int(volume)))
    ck = (path, st.st_size, st.st_mtime_ns, volume)
    if ck in _CUSTOM_WAV:
        return _CUSTOM_WAV[ck]
    try:
        with open(path, "rb") as f:
            data = f.read(CUSTOM_MAX_BYTES + 1)
    except OSError:
        return None
    got = wav_pcm16(data) if len(data) <= CUSTOM_MAX_BYTES else None
    if got is None:
        return None
    chans, rate, pcm = got
    frames = len(pcm) // (2 * chans)
    keep = min(frames, int(rate * CUSTOM_MAX_S))
    n = keep * chans
    gain = volume / 100.0
    out = [int(v * gain) for v in struct.unpack("<%dh" % n, pcm[:n * 2])]
    fade = int(rate * 0.012) * chans if keep < frames else 0        # cortado: some aos poucos, sem estalo
    for i in range(max(0, n - fade), n):
        out[i] = int(out[i] * (n - i) / float(fade))
    body = struct.pack("<%dh" % n, *out)
    head = (b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, chans, rate, rate * 2 * chans, 2 * chans, 16)
            + b"data" + struct.pack("<I", len(body)))
    if len(_CUSTOM_WAV) > 24:
        _CUSTOM_WAV.clear()
    _CUSTOM_WAV[ck] = head + body
    return _CUSTOM_WAV[ck]


_MCI_LOCK = threading.Lock()
_MCI_N = [0]


def play_mp3(path, volume=40):
    """Toca um MP3 pelo MCI do Windows. Bloqueia até acabar ou até CUSTOM_MAX_S (chame numa thread). False se o
    Windows não conseguiu abrir o arquivo."""
    try:
        import ctypes
        mci = ctypes.windll.winmm.mciSendStringW
    except (ImportError, AttributeError, OSError):
        return False
    buf = ctypes.create_unicode_buffer(64)
    with _MCI_LOCK:
        _MCI_N[0] += 1
        alias = "rmsom%d" % _MCI_N[0]
    if mci('open "%s" type mpegvideo alias %s' % (path, alias), None, 0, None) != 0:
        return False
    try:
        mci("setaudio %s volume to %d" % (alias, max(0, min(1000, int(volume) * 10))), None, 0, None)
        if mci("play %s" % alias, None, 0, None) != 0:
            return False
        end = time.monotonic() + CUSTOM_MAX_S
        time.sleep(0.15)
        while time.monotonic() < end:
            if mci("status %s mode" % alias, buf, 64, None) != 0 or buf.value != "playing":
                break
            time.sleep(0.1)
        return True
    finally:
        mci("stop %s" % alias, None, 0, None)
        mci("close %s" % alias, None, 0, None)
