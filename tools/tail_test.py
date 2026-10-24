"""Mede se o replay e escrito em tempo real: espera um .rrf novo na pasta Replay
e mostra, a cada leitura, o tamanho do arquivo, o ultimo registro decodificado e o
atraso entre o relogio e o tempo do registro.

Uso: python tools/tail_test.py [pasta_replay] [segundos]
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rrf  # noqa: E402

folder = sys.argv[1] if len(sys.argv) > 1 else r"C:\Gravity\Ragnarok\Replay"
limit = float(sys.argv[2]) if len(sys.argv) > 2 else 900


def log(msg):
    print(time.strftime("%H:%M:%S ") + msg, flush=True)


before = {f: os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder) if f.endswith(".rrf")}
log("aguardando replay novo em %s (%d existentes)" % (folder, len(before)))
start = time.time()
path = None
while time.time() - start < limit and path is None:
    for f in os.listdir(folder):
        if f.endswith(".rrf") and f not in before:
            path = os.path.join(folder, f)
    time.sleep(0.2)
if not path:
    log("nenhum replay novo")
    sys.exit(1)

seen_at = time.time()
log("novo arquivo: %s" % path)
header = session = reader = None
pos = 0
dmg_total = dmg_count = 0
last_size = -1
last_rec_t = None
first_rec_wall = None
idle_since = time.time()
while time.time() - start < limit:
    try:
        with open(path, "rb") as fh:
            size = os.fstat(fh.fileno()).st_size
            if header is None and size >= 0x200:
                buf = fh.read()
                try:
                    header = rrf.Header(buf)
                    if header.stream_offset and header.stream_offset <= size:
                        session = rrf.Session(header, buf)
                        reader = rrf.StreamReader(header.keys, rrf.WANTED)
                        pos = header.stream_offset
                        log("cabecalho ok: %s aid=%d mapa=%s stream@%#x (tamanho %d)" % (
                            session.player, session.aid, session.map, pos, size))
                    else:
                        log("cabecalho sem stream ainda (stream=%s, tamanho %d)" % (header.stream_offset, size))
                        header = None
                except ValueError as e:
                    log("cabecalho incompleto: %s" % e)
                    header = None
            if reader is not None and size > pos:
                fh.seek(pos)
                data = fh.read(size - pos)
                pos += len(data)
                for t, pid, d in reader.feed(data):
                    last_rec_t = t
                    if first_rec_wall is None:
                        first_rec_wall = time.time() - t / 1000.0
                    if pid in rrf.DAMAGE_PACKETS:
                        x = rrf.parse_damage(t, pid, d)
                        if x and x.src == session.aid:
                            dmg_total += x.damage
                            dmg_count += 1
    except OSError as e:
        log("erro de leitura: %s" % e)
        size = last_size
    if size != last_size:
        lag = ""
        if last_rec_t is not None and first_rec_wall is not None:
            lag = " atraso~%.1fs" % (time.time() - (first_rec_wall + last_rec_t / 1000.0))
        log("tamanho=%d (+%d) ultimo_reg=%sms meus_hits=%d dano=%d%s" % (
            size, size - max(last_size, 0), last_rec_t, dmg_count, dmg_total, lag))
        last_size = size
        idle_since = time.time()
    elif time.time() - idle_since > 120 and last_size > 0:
        log("arquivo parado ha 2 min, encerrando")
        break
    time.sleep(0.25)
log("fim")
