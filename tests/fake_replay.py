"""Monta arquivos .rrf sinteticos (mesma cifra e layout do cliente) para os testes."""

import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rrf  # noqa: E402

DATE = (2026, 10, 22, 23, 16, 53)


def container(chunks, keys):
    body = b"".join(struct.pack("<hi", cid, len(d)) + d for cid, d in chunks)
    return rrf.decrypt(body, keys)          # XOR: cifrar = decifrar


def header(aid, player="Tester", map_name="prt_fild08", date=DATE, entities=(), option=0, look=None, sex=None,
           xp=None):
    """Cabecalho + containers. O fluxo (tipo 1) comeca logo depois.
    look: {"hair": 22, "top": 1677, ...} (visual de quem grava, como em rrf.LOOK_CHUNKS); sex: 1/0.
    xp: (id do personagem, XP de base no início, XP do nível) -> chunks 1011, 1015 e 1018."""
    keys = rrf.Keys(*date)
    # cada container abre com o marcador do cliente (id proprio, tamanho 0)
    replay_data = [(950, b""), (951, b""), (960, b""), (961, b""), (970, player.encode("utf-8") + b"\0"),
                   (971, map_name.encode() + b"\0")]
    session = [(1000, b""), (1010, struct.pack("<I", aid)), (1014, struct.pack("<I", 4302)),
               (1016, struct.pack("<I", 240)), (1070, struct.pack("<I", option))]
    chunk = dict(rrf.LOOK_CHUNKS)
    session += [(chunk[k], struct.pack("<i", v)) for k, v in (look or {}).items()]
    if sex is not None:
        replay_data.append((rrf.RD_SEX, struct.pack("<i", sex)))
    if xp is not None:
        session += [(1011, struct.pack("<I", xp[0])), (1015, struct.pack("<q", xp[1])), (1018, struct.pack("<q", xp[2]))]
    init = [(10000, b"")] + [(210, spawn0857(*e)) for e in entities] + [(10001, b"")]
    # mesma ordem do cliente: ReplayData por ultimo, logo antes do fluxo
    blobs = [(rrf.CT_SESSION, container(session, keys)),
             (rrf.CT_INITIAL_ENTITIES, container(init, keys)),
             (rrf.CT_REPLAY_DATA, container(replay_data, keys))]
    head = bytearray(b"<< Ragnarok Replay File Version 0.05 >>\r\n".ljust(0x64, b"\0"))
    head += bytes([5]) + b"GAR" + struct.pack("<hBBBBBB", date[0], date[1], date[2], 0, *date[3:])
    table_len = rrf.FIRST_CONTAINER - rrf.TABLE_OFFSET
    off = len(head) + table_len
    table = b""
    data = b""
    for ctype, blob in blobs:
        table += struct.pack("<Hii", ctype, len(blob), off + len(data))
        data += blob
    table += struct.pack("<Hii", rrf.CT_PACKET_STREAM, 0, off + len(data))
    table = table.ljust(table_len, b"\0")
    return bytes(head) + table + data, keys


def record(t, packet, keys):
    return struct.pack("<iiH", 0, t, len(packet)) + rrf.decrypt(packet, keys)


def skill_damage(src, dst, dmg, skill=5473, hits=3, action=8):
    return struct.pack("<HHIIIiiihhB", rrf.P_SKILL, skill, src, dst, 0, 0, 0, dmg, 5, hits, action)


def auto_attack(src, dst, dmg, action=0, left=0):
    return struct.pack("<HIIIiiiBhBi", rrf.P_ACT3_NEW, src, dst, 0, 0, 0, dmg, 0, 1, action, left)


def spawn(aid, kind, job, name, gid=0, boss=False, pos=None, stand=False):
    """0x09fe com os campos que o medidor le nas posicoes certas; com stand=True, o 0x09ff (aparecer parado), que
    tem 1 byte a mais antes do nivel. pos = (x, y) da unidade."""
    kinds = {v: k for k, v in rrf.OBJ_KIND.items()}
    extra = 1 if stand else 0
    p = bytearray(83 + extra)
    struct.pack_into("<HHBII", p, 0, rrf.P_SPAWN_STAND if stand else rrf.P_SPAWN_IDLE, 0, kinds[kind], aid, gid)
    struct.pack_into("<h", p, 23, job)
    if pos is not None:
        x, y = pos
        p[63:66] = bytes([x >> 2, ((x & 3) << 6) | (y >> 4), (y & 0x0F) << 4])
    level = (2 if boss else 0) if isinstance(boss, bool) else boss   # 0 normal, 1 chefe menor, 2 MVP
    struct.pack_into("<iiB", p, 72 + extra, -1, -1, level)           # a LATAM manda -1 no HP
    p += name.encode("utf-8")
    struct.pack_into("<H", p, 2, len(p))
    return bytes(p)


def spawn0857(aid, kind, job, name):
    kinds = {v: k for k, v in rrf.OBJ_KIND.items()}
    p = bytearray(69)
    struct.pack_into("<HHBI", p, 0, rrf.P_INITIAL_SPAWN, 0, kinds[kind], aid)
    struct.pack_into("<h", p, 19, job)
    p += name.encode("utf-8")
    struct.pack_into("<H", p, 2, len(p))
    return bytes(p)


def vanish(aid, kind=1):
    return struct.pack("<HIB", rrf.P_VANISH, aid, kind)


def ground_unit(unit, caster):
    return struct.pack("<HHIIhhBBB", rrf.P_GROUND_UNIT, 19, unit, caster, 10, 10, 0x7e, 1, 1)


def ground_area(unit, caster, x, y, kind, level, radius=0):
    """0x09ca no formato atual (23 bytes): uma célula de área no chão (kind 0x9a = Vulcão, 0xf4 = Insígnia da Terra)."""
    return struct.pack("<HHIIhhIbBB", rrf.P_GROUND_UNIT, 23, unit, caster, x, y, kind, radius, 1, level)


def ground_gone(unit):
    """0x0120: a célula saiu do chão."""
    return struct.pack("<HI", rrf.P_GROUND_GONE, unit)


def ground_skill(src, skill, level, x, y):
    """0x0117: skill usada numa célula (monstros mandam nível 65535)."""
    return struct.pack("<HHIHhhI", rrf.P_GROUND_SKILL, skill, src, level, x, y, 0)


def stop(aid, x, y):
    """0x0088: a unidade parou em (x, y)."""
    return struct.pack("<HIhh", rrf.P_STOP, aid, x, y)


def map_move(name, x, y):
    """0x0091: quem grava trocou de mapa ou teleportou."""
    return struct.pack("<H16shh", rrf.P_MAPMOVE, name.encode() + b".gat", x, y)


def build(aid, events, **kw):
    """events: lista de (t_ms, pacote). Devolve (bytes do arquivo, offset do fluxo)."""
    head, keys = header(aid, **kw)
    return head + b"".join(record(t, p, keys) for t, p in events), len(head)


def without_table(data):
    """Como o arquivo fica nos primeiros ~9 s da gravacao: tabela do cabecalho vazia."""
    z = bytearray(data)
    z[rrf.TABLE_OFFSET:rrf.FIRST_CONTAINER] = bytes(rrf.FIRST_CONTAINER - rrf.TABLE_OFFSET)
    return bytes(z)


def skill_use(src, dst, skill, level=1):
    return struct.pack("<HHiIIB", rrf.P_SKILL_NODMG, skill, level, dst, src, 1)


def quest_hunt(entries):
    """0x0afe: progresso de caça; entries = [(missão, id da caça, meta, contagem)]."""
    body = b"".join(struct.pack("<IIIHH", quest, ident, 1, goal, count) for quest, ident, goal, count in entries)
    return struct.pack("<HHH", rrf.P_QUEST_HUNT, 6 + len(body), len(entries)) + body


def quest_done(quest):
    """0x02b4: a missão saiu da lista (concluída ou entregue)."""
    return struct.pack("<HI", rrf.P_QUEST_DONE, quest)


def cast(src, dst, skill, ms):
    return struct.pack("<HIIhhHIIB", rrf.P_CAST2, src, dst, 0, 0, skill, 0, ms, 0)


def rekey(data, date):
    """O mesmo replay cifrado como se tivesse sido gravado em `date` (ex.: 0 h, chave fraca)."""
    h = rrf.Header(data)
    new = rrf.Keys(*date)
    out = bytearray(data)
    struct.pack_into("<hBBBBBB", out, 0x68, date[0], date[1], date[2], 0, *date[3:])
    for t, ln, off in h.containers:
        if t != rrf.CT_PACKET_STREAM and ln > 0:
            plain = rrf.decrypt(data[off:off + ln], h.keys)
            out[off:off + ln] = rrf.decrypt(plain, new)
    p = h.stream_offset
    while p + rrf.REC_HEADER <= len(data):
        ln = struct.unpack_from("<H", data, p + 8)[0]
        a, b = p + rrf.REC_HEADER, p + rrf.REC_HEADER + ln
        if b > len(data):
            break
        out[a:b] = rrf.decrypt(rrf.decrypt(data[a:b], h.keys), new)
        p = b
    return bytes(out)


def status(aid, efst, on, total=0, left=0, val1=0):
    """0x0983: buff/debuff ligou ou desligou (val1 = nível ou força do efeito)."""
    return struct.pack("<HHIBIIiii", rrf.P_STATUS3, efst, aid, 1 if on else 0, total, left, val1, 0, 0)


def party_hp(aid, value, max_hp):
    """0x080e: HP de um membro do grupo (só quem está no grupo recebe)."""
    return struct.pack("<HIii", rrf.P_PARTY_HP, aid, value, max_hp)


def resurrect(aid):
    """0x0148: o jogador ressuscitou."""
    return struct.pack("<HIH", rrf.P_RESURRECT, aid, 0)


def hp(value, var=rrf.SP_HP):
    """0x00b0: HP (ou HP máx.) do próprio jogador."""
    return struct.pack("<HHi", rrf.P_PARAM, var, value)


def build_grf(path, files):
    """data.grf mínimo no formato 0x300 ("Event Horizon"), com os arquivos {nome: bytes} compactados."""
    import zlib
    body = b""
    table = b""
    for name, data in files.items():
        packed = zlib.compress(data)
        table += name.encode("cp949") + b"\0" + struct.pack("<IIIBQ", len(packed), len(packed), len(data), 1, len(body))
        body += packed
    ztable = zlib.compress(table)
    head = b"Event Horizon\x00c\x00" + bytes(14) + struct.pack("<QII", len(body), len(files), 0x300)
    with open(path, "wb") as f:
        f.write(head + body + struct.pack("<III", 0, len(ztable), len(table)) + ztable)


def broadcast(key):
    """0x01c3: anúncio do mapa com o texto como chave entre bytes 0x1c, como nas instâncias."""
    body = bytes([0x1C]) + key.encode("ascii") + bytes([0x1C, 0])
    return struct.pack("<HH", rrf.P_BROADCAST, 16 + len(body)) + bytes.fromhex("ffff000090010c0000000000") + body


def effect(aid, effect_id):
    """0x01f3: efeito especial numa unidade (ex.: 537 = armadilha da Torre da Constelação)."""
    return struct.pack("<HIi", rrf.P_EFFECT, aid, effect_id)
