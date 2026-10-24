"""Formatacao de numeros e tempos. Português e espanhol: 1,5M e 1.234.567; inglês: 1.5M e 1,234,567."""

import i18n


def dec(text):
    """Troca o ponto decimal pela vírgula (menos em inglês)."""
    return text if i18n.LANG == "en" else text.replace(".", ",")


def num(v):
    """1234 -> 1,2K   92508200 -> 92,5M   7993472848 -> 7,99B"""
    v = float(v)
    a = abs(v)
    for lim, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= lim:
            x = v / lim
            s = ("%.2f" if abs(x) < 10 else "%.1f" if abs(x) < 100 else "%.0f") % x
            return dec(s) + suf
    return "%d" % round(v)


def full(v):
    """1234567 -> 1.234.567"""
    s = "{:,}".format(int(v))
    return s if i18n.LANG == "en" else s.replace(",", ".")


def dur(ms):
    s = max(0, int(ms // 1000))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%02d:%02d" % (m, s)
