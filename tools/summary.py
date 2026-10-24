"""Resumo de um ou mais replays no terminal (para conferir o medidor).

Uso: python tools/summary.py arquivo.rrf [...] [--gap 10] [--chunk 4096]
  --chunk N  le o arquivo em pedacos de N bytes, como se estivesse sendo gravado
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import meter  # noqa: E402
from fmt import num, dur  # noqa: E402


def load(path, gap, chunk):
    rf = meter.ReplayFile(path, gap * 1000)
    if not chunk:
        rf.poll(max_bytes=1 << 30)
        rf.combat.finished = True
        return rf
    # simula a gravacao: entrega o arquivo aos poucos
    data = open(path, "rb").read()
    import rrf
    h = rrf.Header(data)
    s = rrf.Session(h, data)
    rf.header, rf.session = h, s
    rf.reader = rrf.StreamReader(h.keys, rrf.WANTED)
    rf.combat = meter.Combat(s, gap * 1000)
    for e in rrf.initial_entities(h, data):
        rf.combat.add_entity(e)
    for p in range(h.stream_offset, len(data), chunk):
        rf.combat.feed(rf.reader.feed(data[p:p + chunk]), rf.reader.last_time)
    rf.combat.finished = True
    return rf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--gap", type=float, default=10)
    ap.add_argument("--chunk", type=int, default=0)
    ap.add_argument("--all", action="store_true", help="mostra todos os encontros")
    a = ap.parse_args()
    for path in a.files:
        rf = load(path, a.gap, a.chunk)
        c = rf.combat
        s = rf.session
        print("== %s | %s (%s) | mapa %s | %d registros" % (
            os.path.basename(path), s.player, meter.job_name(s.job), c.map, rf.reader.records))
        encs = c.history + ([c.current] if c.current else [])
        shown = encs if a.all else sorted(encs, key=lambda e: -sum(x.total for x in e.by_source.values()))[:1]
        for enc in shown:
            snap = c.snapshot(enc)
            print("  encontro %s-%s (%s em combate) alvo %s | meu dano %s | meu DPS %s | maior hit %s" % (
                dur(enc.start), dur(enc.last), dur(snap["duration_ms"]),
                snap["target"], num(snap["my_total"]), num(snap["my_dps"]), num(snap["my_max"])))
            for i, p in enumerate(snap["players"][:8], 1):
                print("    %d. %-22s %9s  %8s/s  %5.1f%%%s" % (
                    i, p["name"][:22], num(p["total"]), num(p["dps"]), p["share"] * 100, "  <- você" if p["me"] else ""))
            for k in snap["skills"][:6]:
                print("       %-34s %9s  %5.1f%%  %d hits" % (k["name"][:34], num(k["total"]), k["share"] * 100, k["hits"]))
        print("  %d encontro(s)" % len(encs))


if __name__ == "__main__":
    main()
