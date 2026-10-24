"""Leitor de replays do Ragnarok Online (.rrf, versao 0.05).

Formato (conferido com os replays do ROLatam e com o projeto rrfparser, MIT,
https://github.com/adsonpleal/rrfparser):

  0x00  texto "<< Ragnarok Replay File Version 0.05 >>" (100 bytes)
  0x64  versao u8 (=5), assinatura "GAR"
  0x68  data/hora da gravacao: ano i16, mes u8, dia u8, (pad) u8, hora u8, min u8, seg u8
  0x70  tabela de containers: tipo u16, tamanho i32, offset i32 (10 bytes cada)

Cada container generico e uma lista de chunks (id i16, tamanho i32, dados). O
container tipo 1 e o fluxo de pacotes: fica no fim do arquivo, tem tamanho 0
na tabela e cresce enquanto a gravacao acontece. Cada registro do fluxo:

  id i32, tempo i32 (ms desde o inicio), tamanho u16, dados (pacote servidor->cliente)

Tudo e ofuscado com XOR por palavra de 32 bits: chave(i) = (k1 + i + 1) * k2,
com k1/k2 derivados da data/hora do cabecalho. Bytes que sobram depois da
ultima palavra inteira ficam em claro.
"""

import struct

MAGIC = b"<< Ragnarok Replay File Version"
TABLE_OFFSET = 0x70
DESC_SIZE = 10
REC_HEADER = 10
M32 = 0xFFFFFFFF

CT_PACKET_STREAM = 1
CT_REPLAY_DATA = 2
CT_SESSION = 3
CT_INITIAL_ENTITIES = 15


def _s32(v):
    v &= M32
    return v - (1 << 32) if v & 0x80000000 else v


class Keys:
    __slots__ = ("k1", "k2", "_cache")

    def __init__(self, year, month, day, hour, minute, second):
        self.k1 = _s32((year & 0xFFFF) | (month << 16) | (day << 24)) >> 5
        self.k2 = _s32((hour << 8) | (minute << 16) | (second << 24)) >> 3
        self._cache = b""

    def stream(self, nwords):
        """Bytes da chave para as primeiras `nwords` palavras (com cache)."""
        need = nwords * 4
        if len(self._cache) < need:
            n = max(nwords, 64, len(self._cache) // 2)
            k1, k2 = self.k1, self.k2
            self._cache = struct.pack("<%dI" % n, *[((k1 + i + 1) * k2) & M32 for i in range(n)])
        return self._cache[:need]


def decrypt(data, keys):
    n = len(data) // 4
    if not n:
        return bytes(data)
    body = int.from_bytes(data[:n * 4], "little") ^ int.from_bytes(keys.stream(n), "little")
    return body.to_bytes(n * 4, "little") + bytes(data[n * 4:])


def decrypt_head(data, keys):
    """So os 2 primeiros bytes (id do pacote), sem decifrar o resto."""
    if len(data) < 4:
        return data[0] | (data[1] << 8) if len(data) >= 2 else -1
    w = int.from_bytes(data[:4], "little") ^ int.from_bytes(keys.stream(1), "little")
    return w & 0xFFFF


FIRST_CONTAINER = 0x174
# Todo container abre com um chunk marcador de tamanho 0 e id proprio; esses ids
# nunca aparecem no meio de um container (conferido em 19 replays).
CONTAINER_MARKERS = {8000: 24, 1000: 3, 2000: 4, 3500: 6, 4000: 7, 4500: 8, 5000: 9, 5500: 10,
                     6500: 12, 7000: 13, 13000: 22, 19000: 18, 10000: 15, 15000: 16, 17000: 17,
                     14000: 23, 25000: 20, 20000: 19, 26000: 21, 950: 2}


def _stream_start_ok(buf, pos):
    """O fluxo sempre comeca com um registro id=0, tempo=0 (cabecalho em claro)."""
    if pos + REC_HEADER + 2 > len(buf):
        return False
    rid, t, ln = struct.unpack_from("<iiH", buf, pos)
    return rid == 0 and t == 0 and 2 <= ln < 4096


def _marker_at(buf, pos, keys):
    """Tipo do container que comeca em `pos`, ou None.

    O marcador e decifrado com a chave recomecando em `pos`. Testa tambem o caso
    de o container acabar dentro dele (bytes depois da 1a palavra em claro).
    """
    raw = buf[pos:pos + 8]
    if len(raw) < 6:
        return None
    dec = decrypt(raw, keys)
    for hdr in (dec[:6], dec[:4] + raw[4:6]):
        cid, clen = struct.unpack_from("<hi", hdr)
        if clen == 0 and cid in CONTAINER_MARKERS:
            return CONTAINER_MARKERS[cid]
    return None


def _boundary(buf, pos, keys):
    return _stream_start_ok(buf, pos) or _marker_at(buf, pos, keys) is not None


def _container_size(buf, start, keys):
    """Tamanho do container que comeca em `start` (None se ainda nao der para saber).

    A cifra recomeca em cada container, e os 1-3 bytes depois da ultima palavra
    inteira ficam em claro. O fim e onde comeca o proximo marcador (ou o fluxo).
    Nao da para confiar so em "o cabecalho parece valido": com a gravacao
    comecando a 0 h a chave fica fraca (metade de cada palavra sem cifra).
    """
    dec = decrypt(buf[start:], keys)
    room = len(buf) - start
    q = 6                                       # pula o marcador (tamanho 0)
    while q + 6 <= room:
        if _boundary(buf, start + q, keys):
            return q
        # o fim (em claro) caiu dentro deste cabecalho?
        for b in range(((q + 3) // 4) * 4, q + 7, 4):
            if b <= q:
                continue
            hdr = bytearray(buf[start + q:start + q + 6])
            hdr[:b - q] = dec[q:b]
            _cid, clen = struct.unpack_from("<hi", bytes(hdr))
            end = q + 6 + clen
            if 0 <= clen <= room - q - 6 and end % 4 and end - end % 4 == b and _boundary(buf, start + end, keys):
                return end
        _cid, clen = struct.unpack_from("<hi", dec, q)
        if not 0 <= clen <= room - q - 6:
            return None
        q += 6 + clen
    return None


def scan_containers(buf, keys, max_containers=40):
    """Acha os containers e o inicio do fluxo sem a tabela do cabecalho.
    Devolve ([(tipo, tamanho, offset)...], offset_do_fluxo) ou None."""
    found = []
    pos = FIRST_CONTAINER
    while not (found and _stream_start_ok(buf, pos)):
        ctype = _marker_at(buf, pos, keys)
        size = _container_size(buf, pos, keys) if ctype is not None else None
        if not size or len(found) >= max_containers:
            return None
        found.append((ctype, size, pos))
        pos += size
    if not any(t == CT_SESSION for t, _l, _o in found):
        return None
    return found + [(CT_PACKET_STREAM, 0, pos)], pos


def _chunks(body, ln):
    out, p = [], 0
    while p + 6 <= ln:
        cid, clen = struct.unpack_from("<hi", body, p)
        if clen < 0 or p + 6 + clen > len(body):
            break
        out.append((cid, body[p + 6:p + 6 + clen]))
        p += 6 + clen
    return out


class Header:
    def __init__(self, buf):
        if len(buf) < TABLE_OFFSET or not buf.startswith(MAGIC):
            raise ValueError("nao e um replay do Ragnarok")
        self.version = buf[0x64]
        if self.version != 5:
            raise ValueError("versao de replay nao suportada: %d" % self.version)
        year, month, day, _pad, hour, minute, second = struct.unpack_from("<hBBBBBB", buf, 0x68)
        self.recorded_at = (year, month, day, hour, minute, second)
        self.keys = Keys(year, month, day, hour, minute, second)
        self.containers = []          # (tipo, tamanho_declarado, offset)
        for pos in range(TABLE_OFFSET, FIRST_CONTAINER - DESC_SIZE + 1, DESC_SIZE):
            ctype, ln, off = struct.unpack_from("<Hii", buf, pos)
            if ctype and ln >= 0 and FIRST_CONTAINER <= off <= len(buf):
                self.containers.append((ctype, ln, off))
        stream = [c for c in self.containers if c[0] == CT_PACKET_STREAM]
        self.stream_offset = stream[0][2] if stream else None
        self.scanned = False
        if self.stream_offset is None:
            # O cliente so preenche esta tabela ~9 s depois de comecar a gravar.
            # Ate la os containers ja estao no arquivo, um atras do outro.
            found = scan_containers(buf, self.keys)
            if found is not None:
                self.containers, self.stream_offset = found
                self.scanned = True

    def container_chunks(self, buf, ctype):
        """Chunks (id, dados) do primeiro container generico do tipo pedido."""
        for t, ln, off in self.containers:
            if t != ctype or ln <= 0 or off + ln > len(buf):
                continue
            return _chunks(decrypt(buf[off:off + ln], self.keys), ln)
        return []


def decode_name(raw):
    raw = raw.split(b"\0", 1)[0]
    for enc in ("utf-8", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1")


def entity_name(raw):
    i = 0
    while i < len(raw) and raw[i] in (0, 0xFF):
        i += 1
    # "\x1cpY4B\x1c" = chave das tabelas de nomes do cliente (monstros novos); clientdata traduz
    return decode_name(raw[i:])


class Session:
    """Quem esta gravando: AID e nome do personagem, mapa inicial."""

    def __init__(self, header, buf):
        self.aid = 0
        self.job = 0
        self.base_level = 0
        self.player = ""
        self.map = ""
        self.option = 0
        self.recorded_at = header.recorded_at
        sess = dict(header.container_chunks(buf, CT_SESSION))
        if len(sess.get(1010, b"")) >= 4:
            self.aid = struct.unpack_from("<I", sess[1010])[0]
        if len(sess.get(1014, b"")) >= 4:
            self.job = struct.unpack_from("<I", sess[1014])[0]
        if len(sess.get(1016, b"")) >= 4:
            self.base_level = struct.unpack_from("<I", sess[1016])[0]
        if len(sess.get(1070, b"")) >= 4:
            self.option = struct.unpack_from("<I", sess[1070])[0]
        rd = header.container_chunks(buf, CT_REPLAY_DATA)
        if len(rd) > 5:
            self.player = decode_name(rd[4][1])
            self.map = decode_name(rd[5][1])


class StreamReader:
    """Le o fluxo de pacotes de forma incremental (o arquivo pode estar crescendo).

    `feed(bytes)` recebe o que foi lido a partir de `stream_offset`; registros
    incompletos ficam guardados ate o resto chegar.
    """

    def __init__(self, keys, wanted=None):
        self.keys = keys
        self.wanted = wanted          # set de ids de pacote a decifrar (None = todos)
        self._pending = b""
        self.consumed = 0             # bytes do fluxo ja processados
        self.last_time = 0            # tempo (ms) do ultimo registro, de qualquer tipo
        self.records = 0

    def feed(self, data):
        buf = self._pending + data if self._pending else data
        out = []
        p, n = 0, len(buf)
        wanted, keys = self.wanted, self.keys
        t = self.last_time
        while p + REC_HEADER <= n:
            _rid, t, ln = struct.unpack_from("<iiH", buf, p)
            end = p + REC_HEADER + ln
            if end > n:
                break
            raw = buf[p + REC_HEADER:end]
            pid = decrypt_head(raw, keys)
            if wanted is None or pid in wanted:
                out.append((t, pid, decrypt(raw, keys)))
            self.records += 1
            p = end
        if p:
            self.last_time = t
        self._pending = buf[p:]
        self.consumed += p
        return out


# --- pacotes --------------------------------------------------------------

P_ACT_LEGACY = 0x008A    # ZC_NOTIFY_ACT
P_ACT3 = 0x02E1          # ZC_NOTIFY_ACT3
P_ACT3_NEW = 0x08C8      # ZC_NOTIFY_ACT3 (com isSPDamage)
P_SKILL = 0x01DE         # ZC_NOTIFY_SKILL
P_VANISH = 0x0080        # ZC_NOTIFY_VANISH (tipo 1 = morreu)
P_MAPMOVE = 0x0091       # ZC_NPCACK_MAPMOVE
P_GROUND_UNIT = 0x09CA   # ZC_SKILL_ENTRY5 (unidade de skill no chao)
P_HP_INFO = 0x0977       # ZC_HP_INFO
P_SPAWN_IDLE = 0x09FE
P_SPAWN_STAND = 0x09FF
P_SPAWN_WALK = 0x0915
P_SPAWN_NEW = 0x09FD

P_SKILL_NODMG_OLD = 0x011A  # skill sem dano (cura, buff, debuff)
P_SKILL_NODMG = 0x09CB
P_CAST = 0x013E            # comecou a conjurar
P_CAST2 = 0x07FB

DAMAGE_PACKETS = {P_ACT_LEGACY, P_ACT3, P_ACT3_NEW, P_SKILL}
SPAWN_PACKETS = {P_SPAWN_IDLE, P_SPAWN_STAND, P_SPAWN_WALK, P_SPAWN_NEW}
SKILL_USE_PACKETS = {P_SKILL_NODMG_OLD, P_SKILL_NODMG}
CAST_PACKETS = {P_CAST, P_CAST2}
P_STATUS = 0x0196          # buff/debuff ligou/desligou (sem tempo)
P_STATUS2 = 0x043F         # ... com tempo restante
P_STATUS3 = 0x0983         # ... com duração total e tempo restante
P_PARAM = 0x00B0           # atributo do próprio jogador (5 = HP, 6 = HP máx.)
P_PARTY_HP = 0x080E        # HP de um membro do grupo
P_WEAR = 0x0999            # equipou
P_TAKEOFF = 0x099A         # desequipou
P_ITEM_ADD = 0x0A37        # item entrou na bolsa
P_OPTION = 0x0229          # opções visuais de uma unidade (montaria, falcão, "voando" da União...)
P_EFFECT = 0x01F3          # efeito especial numa unidade
P_RESURRECT = 0x0148       # jogador ressuscitou
# Efeitos de mapa que tiram HP sem pacote de dano (o replay só traz o efeito e a queda de HP).
# Outros encontros têm os seus: efeitos desconhecidos que coincidem com queda de HP sem golpe
# aparecem no recap como "efeito N" até ganharem nome aqui.
MAP_DAMAGE_EFFECTS = {537: "Armadilha da Torre da Constelação"}
EF_TRAP = 537
OPTION_FLYING = 0x8000     # Mestre Taekwon com a União Solar, Lunar e Estelar ativa

STATUS_PACKETS = {P_STATUS, P_STATUS2, P_STATUS3}
WANTED = DAMAGE_PACKETS | SPAWN_PACKETS | SKILL_USE_PACKETS | CAST_PACKETS | STATUS_PACKETS | {
    P_VANISH, P_MAPMOVE, P_GROUND_UNIT, P_HP_INFO, 0x010F, P_PARAM, P_PARTY_HP, P_WEAR, P_TAKEOFF, P_ITEM_ADD,
    P_OPTION, P_EFFECT, P_RESURRECT}
SP_HP, SP_MAXHP = 5, 6

OBJ_KIND = {0: "pc", 5: "mob", 6: "npc", 7: "pet", 8: "homun", 9: "merc", 10: "elem",
            0xD: "abr", 0xE: "bionic"}

# acao (e_damage_type do rAthena)
DMG_SPLASH, DMG_SINGLE, DMG_REPEAT = 5, 6, 7
DMG_MULTI_HIT, DMG_MULTI_HIT_ENDURE = 8, 9
DMG_CRITICAL, DMG_LUCY_DODGE, DMG_MULTI_HIT_CRITICAL = 10, 11, 13
NON_DAMAGE_ACTIONS = {1, 2, 3}   # pegar item, sentar, levantar (mesmo pacote do ataque)


class Damage:
    __slots__ = ("time", "src", "dst", "skill", "level", "damage", "hits", "action", "crit", "miss")

    def __init__(self, time, src, dst, skill, level, damage, hits, action):
        self.time = time
        self.src = src
        self.dst = dst
        self.skill = skill
        self.level = level
        self.action = action
        self.hits = max(1, hits)
        self.crit = action in (DMG_CRITICAL, DMG_MULTI_HIT_CRITICAL)
        self.miss = action == DMG_LUCY_DODGE or (
            damage <= 0 and action in (0, DMG_SPLASH, DMG_SINGLE, DMG_REPEAT))
        self.damage = 0 if self.miss else max(0, damage)

    def __repr__(self):
        return "Damage(t=%d %d->%d skill=%d dmg=%d x%d act=%d)" % (
            self.time, self.src, self.dst, self.skill, self.damage, self.hits, self.action)


def parse_damage(t, pid, d):
    try:
        if pid == P_SKILL:
            skill, src, dst = struct.unpack_from("<HII", d, 2)
            dmg, lvl, hits, act = struct.unpack_from("<ihhB", d, 24)
            if dmg == 0 and act == DMG_SINGLE:
                return None   # marcador de animacao antes do dano em area
            return Damage(t, src, dst, skill, lvl, dmg, hits, act)
        src, dst = struct.unpack_from("<II", d, 2)
        # dano da mao esquerda (dual wield) vem separado no fim do pacote
        if pid == P_ACT3_NEW:
            dmg, _sp, hits, act, left = struct.unpack_from("<iBhBi", d, 22)
        elif pid == P_ACT3:
            dmg, hits, act, left = struct.unpack_from("<ihBi", d, 22)
        else:
            dmg, hits, act, left = struct.unpack_from("<hhBh", d, 22)
        if act in NON_DAMAGE_ACTIONS:
            return None
        if dmg > 0 and left > 0:
            dmg += left
        return Damage(t, src, dst, 0, 0, dmg, hits, act)
    except struct.error:
        return None


class Entity:
    __slots__ = ("aid", "gid", "kind", "job", "name", "max_hp", "hp", "boss", "option")

    def __init__(self, aid, gid, kind, job, name, max_hp=0, hp=0, boss=False, option=0):
        self.aid, self.gid, self.kind, self.job = aid, gid, kind, job
        self.name, self.max_hp, self.hp, self.boss = name, max_hp, hp, boss
        self.option = option


P_INITIAL_SPAWN = 0x0857


def initial_entities(header, buf):
    """Entidades ja visiveis quando a gravacao comecou (pacotes 0x0857, sem GID)."""
    out = []
    for _cid, d in header.container_chunks(buf, CT_INITIAL_ENTITIES):
        if len(d) < 69 or struct.unpack_from("<H", d)[0] != P_INITIAL_SPAWN:
            continue
        plen = struct.unpack_from("<H", d, 2)[0]
        aid = struct.unpack_from("<I", d, 5)[0]
        job = struct.unpack_from("<h", d, 19)[0]
        out.append(Entity(aid, 0, OBJ_KIND.get(d[4], "unknown"), job, entity_name(d[69:plen])))
    return out


def parse_skill_use(pid, d):
    """0x011a / 0x09cb: (fonte, alvo, skill) de uma skill que nao causou dano."""
    try:
        if pid == P_SKILL_NODMG:
            skill, _lvl, dst, src = struct.unpack_from("<HiII", d, 2)
        else:
            skill, _lvl, dst, src = struct.unpack_from("<HHII", d, 2)
        return src, dst, skill
    except struct.error:
        return None


def parse_cast(d):
    """0x013e / 0x07fb: (fonte, alvo, skill, tempo de conjuracao em ms)."""
    try:
        src, dst = struct.unpack_from("<II", d, 2)
        skill, _elem, cast_ms = struct.unpack_from("<HII", d, 14)
        return src, dst, skill, cast_ms
    except struct.error:
        return None


def parse_status(pid, d):
    """(aid, efst, ligou, duração total ms, restante ms, val1). val1 é o nível ou a força do
    efeito (ex.: Clímax 4, Florescer 100 = -100% de resistência a fogo, conversor = elemento)."""
    try:
        efst, aid, on = struct.unpack_from("<HIB", d, 2)
        total = left = val1 = 0
        if pid == P_STATUS3:
            total, left, val1 = struct.unpack_from("<IIi", d, 9)
        elif pid == P_STATUS2:
            left, val1 = struct.unpack_from("<Ii", d, 9)
        return aid, efst, on != 0, total, left, val1
    except struct.error:
        return None


def parse_param(d):
    """0x00b0: (variável, valor)."""
    try:
        return struct.unpack_from("<Hi", d, 2)
    except struct.error:
        return None


def parse_party_hp(d):
    """0x080e: (aid, hp, hp máx.)."""
    try:
        return struct.unpack_from("<Iii", d, 2)
    except struct.error:
        return None


CT_EFST_LIST = 18


def statuses_at_start(header, buf):
    """Buffs que já estavam no personagem quando a gravação começou:
    [(efst, duração total ms, restante ms)]. Registros de 28 bytes no container 18."""
    out = []
    for _cid, d in header.container_chunks(buf, CT_EFST_LIST):
        if len(d) >= 28:
            efst = struct.unpack_from("<I", d)[0]
            total, left = struct.unpack_from("<ii", d, 20)
            out.append((efst, max(0, total), max(0, left)))
    return out


# --- equipamento ----------------------------------------------------------

CT_ITEMS = 8
ITEM_CHUNKS = {4510: "bag", 4601: "worn", 4603: "worn"}   # bolsa, equipado, visual/sombrio
_ITEM_RECORD_SIZES = (221, 172)
_TAG_POS, _TAG_WEAR, _TAG_QTY, _TAG_CARDS, _TAG_ID, _TAG_REFINE, _TAG_GRADE, _TAG_OPTIONS = (
    285, 286, 287, 290, 291, 295, 299, 301)


class Item:
    __slots__ = ("slot", "item_id", "refine", "grade", "cards", "options", "location")

    def __init__(self, slot, item_id, refine=0, grade=0, cards=(), options=(), location=0):
        self.slot, self.item_id, self.refine, self.grade = slot, item_id, refine, grade
        self.cards = [c for c in cards if c]
        self.options = list(options)       # (id, valor, param)
        self.location = location


def _record_size(d):
    for size in _ITEM_RECORD_SIZES:
        if len(d) < size or len(d) % size:
            continue
        ids = [struct.unpack_from("<i", d, r * size + 104)[0] for r in range(len(d) // size)]
        if any(i > 0 for i in ids) and all(0 <= i < 5000000 for i in ids):
            return size
    return 0


def _read_item(d, base, size):
    """Um registro de item: cadeia tag u16 | tamanho u32 | valor (como no rrfparser)."""
    fields = {}
    o = 0
    while o + 6 <= size:
        tag, ln = struct.unpack_from("<HI", d, base + o)
        if o + 6 + ln > size:
            fields = None
            break
        fields[tag] = (base + o + 6, ln)
        o += 6 + ln
    if fields is None or o != size:
        # layout desconhecido: posições fixas
        pos = struct.unpack_from("<h", d, base + 22)[0]
        cards = struct.unpack_from("<4i", d, base + 82)
        return (pos, struct.unpack_from("<i", d, base + 104)[0], struct.unpack_from("<h", d, base + 52)[0],
                struct.unpack_from("<i", d, base + 42)[0], d[base + 134], 0, cards, [])

    def num(tag):
        f = fields.get(tag)
        if not f:
            return 0
        off, ln = f
        return {1: lambda: d[off], 2: lambda: struct.unpack_from("<H", d, off)[0],
                4: lambda: struct.unpack_from("<i", d, off)[0]}.get(ln, lambda: 0)()

    cards = (0, 0, 0, 0)
    f = fields.get(_TAG_CARDS)
    if f and f[1] == 16:
        cards = struct.unpack_from("<4i", d, f[0])
    options = []
    f = fields.get(_TAG_OPTIONS)
    if f and f[1] == 25:
        for i in range(5):
            oid, val, param = struct.unpack_from("<HhB", d, f[0] + i * 5)
            if oid:
                options.append((oid, val, param))
    return (num(_TAG_POS), num(_TAG_ID), num(_TAG_QTY), num(_TAG_WEAR), num(_TAG_REFINE), num(_TAG_GRADE),
            cards, options)


def items_at_start(header, buf):
    """(bolsa {slot: Item}, equipado [Item]) no início da gravação."""
    bag, worn = {}, []
    for cid, d in header.container_chunks(buf, CT_ITEMS):
        kind = ITEM_CHUNKS.get(cid)
        size = _record_size(d) if kind else 0
        if not size:
            continue
        seen = set()
        for base in range(0, len(d) - size + 1, size):
            try:
                pos, item_id, qty, wear, refine, grade, cards, options = _read_item(d, base, size)
            except struct.error:
                continue
            slot = pos - 2
            if item_id <= 0 or qty <= 0 or slot < 0 or slot in seen:
                continue
            seen.add(slot)
            it = Item(slot, item_id, refine, grade, cards, options, wear)
            if kind == "worn" and wear:
                worn.append(it)
            bag.setdefault(slot, it)
    return bag, worn


def parse_wear(pid, d):
    """0x0999/0x099a: (slot, máscara de posição, equipou?, sucesso?)."""
    try:
        slot, loc = struct.unpack_from("<HI", d, 2)
        result = d[10] if pid == P_WEAR else d[8]
        return slot - 2, loc, pid == P_WEAR, result == 0
    except (struct.error, IndexError):
        return None


def parse_item_add(d):
    """0x0a37: Item que entrou na bolsa (slot, id, refino, cartas)."""
    try:
        slot, amount, item_id = struct.unpack_from("<HHI", d, 2)
        refine = d[12]
        cards = struct.unpack_from("<4i", d, 13)
        loc = struct.unpack_from("<I", d, 29)[0]
        return Item(slot - 2, item_id, refine, 0, cards, (), loc) if amount > 0 else None
    except (struct.error, IndexError):
        return None


def parse_effect(d):
    """0x01f3: (aid, id do efeito)."""
    try:
        return struct.unpack_from("<Ii", d, 2)
    except struct.error:
        return None


def parse_resurrect(d):
    try:
        return struct.unpack_from("<I", d, 2)[0]
    except struct.error:
        return None


def parse_option(d):
    """0x0229: (aid, opções)."""
    try:
        aid = struct.unpack_from("<I", d, 2)[0]
        return aid, struct.unpack_from("<I", d, 10)[0]
    except struct.error:
        return None


def parse_ground_unit(d):
    """0x09ca: unidade de skill no chao -> quem lancou."""
    try:
        unit, caster = struct.unpack_from("<II", d, 4)
        return unit, caster
    except struct.error:
        return None


def parse_spawn(pid, d):
    try:
        plen = struct.unpack_from("<H", d, 2)[0]
        objtype = d[4]
        aid, gid = struct.unpack_from("<II", d, 5)
        job = struct.unpack_from("<h", d, 23)[0]
        tail = 68                                 # level (0x09fe)
        if pid == P_SPAWN_STAND:
            tail = 69
        elif pid in (P_SPAWN_WALK, P_SPAWN_NEW):
            tail = 75
        max_hp, hp, boss = struct.unpack_from("<iiB", d, tail + 4)
        name = entity_name(d[tail + 15:plen])
        option = struct.unpack_from("<I", d, 19)[0]
        # boss: 0 = normal, 1 = chefe menor/minion (e bonecos de treino), 2 = MVP
        return Entity(aid, gid, OBJ_KIND.get(objtype, "unknown"), job, name, max_hp, hp, boss, option)
    except (struct.error, IndexError):
        return None
