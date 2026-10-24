# -*- coding: utf-8 -*-
"""Nomes do jogo tirados da instalação do jogador: os que o servidor manda como código e os
nomes de skills, buffs, classes, monstros, itens e opções em inglês, português e espanhol.

Monstros novos (Biosfera de Varmundt e, daqui para frente, os do episódio 19) não vêm com o
nome no replay: vem uma chave entre dois caracteres 0x1C, como "\\x1cVpIB\\x1c". A tradução fica
nas tabelas data/i18n/sc/*.csv dentro do data.grf do jogo (chave, coreano, inglês, ..., português,
..., espanhol; textos em base64). Ex.: VpIB = "[Eco] Golem de Lava" / "[Bio] Lava Golem".

O cliente da LATAM traz também, por idioma (_enus, _eses, _ptbr), as tabelas de nomes em Lua
compilado: skillinfolist, stateiconinfo, pcjobnamegender, addrandomoptionnametable (no data.grf)
e System\\<idioma>\\iteminfo_new.lub. Os monstros saem das tabelas data/i18n/sc pelo nome em
português. O lub.py lê essas tabelas sem executar nada do jogo.

Tudo é lido só para leitura e vai para um cache em %APPDATA%\\RODpsMeter, refeito quando o
data.grf muda (atualização do jogo).
"""

import base64
import difflib
import json
import os
import re
import struct
import threading
import zlib

import i18n
import lub

CODE = re.compile(r"\x1c([A-Za-z0-9+/]{2,8})\x1c")
COLUMNS = {"en": 2, "pt": 7, "es": 9}          # colunas das tabelas do jogo
MAX_KEY = 4                                    # chaves de monstros têm 4 letras
MAX_NAME = 48                                  # textos maiores que isso são frases, não nomes
I18N_PREFIX = b"data\\i18n\\sc\\"
CACHE_VERSION = 5
SUFFIX = {"en": "enus", "es": "eses", "pt": "ptbr"}
LUA = "data\\luafiles514\\lua files\\"
ID_FILES = {"skill": LUA + "skillinfoz\\skillid.lub", "status": LUA + "stateicon\\efstids.lub",
            "job": LUA + "datainfo\\jobidentity.lub", "option": LUA + "datainfo\\enumvar.lub"}
NAME_FILES = {"skill": LUA + "skillinfoz\\skillinfolist_%s.lub", "status": LUA + "stateicon\\stateiconinfo_%s.lub",
              "job": LUA + "datainfo\\pcjobnamegender_%s.lub",
              "option": LUA + "datainfo\\addrandomoptionnametable_%s.lub"}
ITEM_FILES = {"en": "System\\english\\iteminfo_new.lub", "es": "System\\spanish\\iteminfo_new.lub",
              "pt": "System\\iteminfo_new.lub"}


def cache_path():
    return os.path.join(os.path.dirname(i18n.config_path()), "nomes_do_jogo.json")


def grf_entries(path, prefix=I18N_PREFIX):
    """Arquivos de um .grf (versões 0x200 e 0x300) cujo nome começa com `prefix`."""
    with open(path, "rb") as f:
        head = f.read(46)
        version = struct.unpack_from("<I", head, 42)[0]
        if version == 0x300:
            table = struct.unpack_from("<Q", head, 30)[0] + 46 + 4
            entry = "<IIIBQ"
        elif version == 0x200:
            table = struct.unpack_from("<I", head, 30)[0] + 46
            entry = "<IIIBI"
        else:
            return []
        f.seek(table)
        packed, _size = struct.unpack("<II", f.read(8))
        data = zlib.decompress(f.read(packed))
    size = struct.calcsize(entry)
    out = []
    pos = 0
    while pos < len(data):
        end = data.index(b"\0", pos)
        name = data[pos:end]
        packed, aligned, real, flags, offset = struct.unpack_from(entry, data, end + 1)
        pos = end + 1 + size
        # flag 1 = arquivo; 2 e 4 = cifrado (as tabelas de texto não são)
        if flags & 1 and not flags & 6 and name.lower().startswith(prefix):
            out.append((name, max(packed, aligned), real, offset))
    return out


def grf_files(path, wanted):
    """{nome em minúsculas: bytes} dos arquivos pedidos (nomes como no .grf, com \\)."""
    want = {w.lower().encode("cp949") for w in wanted}
    out = {}
    with open(path, "rb") as f:
        for name, packed, real, offset in grf_entries(path, b"data\\"):
            if name.lower() in want:
                f.seek(offset + 46)
                try:
                    out[name.lower().decode("cp949")] = zlib.decompressobj().decompress(f.read(packed))[:real]
                except zlib.error:
                    pass
    return out


def _table(data, name):
    try:
        return lub.run(data).get(name) or {}
    except (ValueError, struct.error, IndexError, KeyError):
        return {}


def read_game_names(grf, lang, pt_names=None, pt_monsters=None):
    """{tipo: {id: nome}} no idioma `lang`: skill, status, job, option, item e monster.
    pt_names: {texto em português: [en, pt, es]} das tabelas de texto (para os monstros);
    pt_monsters: {id: nome em português} da base do medidor."""
    files = grf_files(grf, list(ID_FILES.values()) + [v % SUFFIX[lang] for v in NAME_FILES.values()])

    def get(path, table):
        return _table(files.get(path.lower(), b""), table) if path.lower() in files else {}

    out = {}
    ids = get(ID_FILES["skill"], "SKID")
    names = get(NAME_FILES["skill"] % SUFFIX[lang], "SkillInfoList_string")
    out["skill"] = {ids[k[1]]: v["SkillName"] for k, v in names.items()
                    if isinstance(k, lub.Symbol) and len(k) > 1 and k[1] in ids and isinstance(v, dict)
                    and isinstance(v.get("SkillName"), str)}
    ids = get(ID_FILES["status"], "EFST_IDs")
    names = get(NAME_FILES["status"] % SUFFIX[lang], "StateIconList_string")
    out["status"] = {}
    for k, v in names.items():
        try:
            if isinstance(k, lub.Symbol) and k[1] in ids:
                out["status"][ids[k[1]]] = v["descript"][1][1]
        except (KeyError, TypeError, IndexError):
            pass
    ids = get(ID_FILES["job"], "JTtbl")
    names = {k[1]: v for k, v in get(NAME_FILES["job"] % SUFFIX[lang], "PCJobNameTableMan").items()
             if isinstance(k, lub.Symbol) and len(k) > 1 and isinstance(v, str)}
    for key in [k for k in names if k not in ids]:     # grafia diferente em jobidentity ("JT_ARC_MAGE")
        near = difflib.get_close_matches(key, [k for k in ids if k not in names], 1, 0.9)
        if near:
            names[near[0]] = names[key]
    out["job"] = {}
    for key, ident in ids.items():
        name = names.get(key) or names.get(re.sub(r"(_RIDING|2)$", "", key))      # montado, segunda forma
        if name and isinstance(ident, int):
            out["job"][ident] = name
    ids = get(ID_FILES["option"], "EnumVAR")
    names = get(NAME_FILES["option"] % SUFFIX[lang], "NameTable_VAR")
    out["option"] = {ids[k][1]: v for k, v in names.items()
                     if k in ids and isinstance(ids[k], dict) and 1 in ids[k] and isinstance(v, str)}
    out["item"] = {}
    item_file = os.path.join(os.path.dirname(grf), ITEM_FILES[lang])
    try:
        with open(item_file, "rb") as f:
            items = _table(f.read(), "tbl")
        out["item"] = {i: v["identifiedDisplayName"] for i, v in items.items()
                       if isinstance(i, int) and isinstance(v, dict) and v.get("identifiedDisplayName")}
    except OSError:
        pass
    col = {"en": 0, "pt": 1, "es": 2}[lang]
    out["monster"] = {}
    for mid, pt in (pt_monsters or {}).items():
        row = (pt_names or {}).get(pt.strip().lower())
        if row and row[col]:
            out["monster"][mid] = row[col]
    # o cliente tem nomes com espaço sobrando ("Solar, Lunar and Stellar Union ")
    return {kind: {str(k): " ".join(v.split()) for k, v in table.items() if isinstance(v, str) and v.strip()}
            for kind, table in out.items()}


def read_names(path, by_pt=None):
    """{chave: [inglês, português, espanhol]} das tabelas de texto do jogo (só chaves curtas).
    by_pt, se for um dict, recebe {texto em português (minúsculas): [en, pt, es]}."""
    names = {}

    def text(v):
        try:
            return " ".join(base64.b64decode(v).decode("utf-8").split()) if v else ""
        except (ValueError, UnicodeDecodeError):
            return ""

    with open(path, "rb") as f:
        for _name, packed, real, offset in grf_entries(path):
            f.seek(offset + 46)
            try:
                raw = zlib.decompressobj().decompress(f.read(packed))[:real]
            except zlib.error:
                continue
            for line in raw.decode("utf-8", "replace").splitlines():
                cols = line.split(",")
                key = cols[0]
                if len(cols) <= COLUMNS["es"] or len(key) > 8:
                    continue
                pt = cols[COLUMNS["pt"]]
                if not 2 <= len(key) <= MAX_KEY and (by_pt is None or not pt or len(pt) > 2 * MAX_NAME):
                    continue
                row = [text(cols[COLUMNS["en"]]), text(pt), text(cols[COLUMNS["es"]])]
                if max(len(x) for x in row) > MAX_NAME:                # nomes, não descrições
                    continue
                if 2 <= len(key) <= MAX_KEY:
                    names[key] = row
                if by_pt is not None and row[1]:
                    by_pt.setdefault(row[1].strip().lower(), row)
    return names


class ClientNames:
    """Tradução das chaves do servidor com as tabelas do jogo instalado (carrega em segundo plano)."""

    def __init__(self):
        self.candidates = []          # data.grf de cada instalação encontrada
        self.loaded_from = None
        self.names = None
        self.game = None              # {tipo: {id: nome}} no idioma escolhido
        self.pt_monsters = {}         # {id: nome em português} (o meter preenche)
        self.version = 0              # muda quando os nomes ficam prontos (a tela redesenha)
        self._thread = None

    def use_folder(self, folder):
        """Anota o data.grf da instalação dona da pasta Replay, de um replay ou da pasta do jogo."""
        if not folder:
            return
        d = os.path.abspath(folder)
        for _ in range(3):
            grf = os.path.join(d, "data.grf")
            if os.path.isfile(grf):
                if grf.lower() not in (x.lower() for x in self.candidates):
                    self.candidates.append(grf)
                return
            d = os.path.dirname(d)

    @property
    def grf(self):
        """Com várias instalações, a mais atualizada (o data.grf mais novo)."""
        if self.loaded_from:
            return self.loaded_from

        def mtime(p):
            try:
                return os.path.getmtime(p)
            except OSError:
                return -1
        return max(self.candidates, key=mtime) if self.candidates else None

    def _load(self):
        lang = i18n.LANG
        try:
            self.loaded_from = self.grf
            st = os.stat(self.grf)
            stamp = [self.grf, st.st_size, int(st.st_mtime)]
            path = cache_path()
            cached = {}
            try:
                with open(path, encoding="utf-8") as f:
                    cached = json.load(f)
                if cached.get("v") != CACHE_VERSION or cached.get("grf") != stamp:
                    cached = {}
            except (OSError, ValueError):
                cached = {}
            if cached.get("names") is not None and lang in cached.get("game", {}):
                self.names, self.game = cached["names"], cached["game"][lang]
                return
            by_pt = {}
            names = read_names(self.grf, by_pt)
            game = read_game_names(self.grf, lang, by_pt, self.pt_monsters)
            self.names, self.game = names, game
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                games = dict(cached.get("game", {}), **{lang: game})
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"v": CACHE_VERSION, "grf": stamp, "names": names, "game": games}, f,
                              ensure_ascii=False)
                os.replace(tmp, path)
            except OSError:
                pass
        except (OSError, ValueError, struct.error, zlib.error):
            self.names = self.names or {}
            self.game = self.game or {}
        finally:
            self.version += 1

    def load(self):
        """Carrega agora (o medidor chama ao abrir: com o cache leva ~0,1 s; na 1ª vez, uns segundos)."""
        if self.names is None and self.grf and self._thread is None:
            self._load()
        else:
            self.wait()

    def game_name(self, kind, ident):
        if not self.game:
            return None
        return self.game.get(kind, {}).get(str(ident))

    def start(self):
        if self._thread is None and self.grf:
            self._thread = threading.Thread(target=self._load, daemon=True)
            self._thread.start()

    def wait(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)

    def lookup(self, key):
        if self.names is None:
            self.start()
            return None
        row = self.names.get(key)
        if not row:
            return None
        order = {"en": (0, 1, 2), "es": (2, 1, 0)}.get(i18n.LANG, (1, 2, 0))
        return next((row[i] for i in order if row[i]), None)

    def resolve(self, text):
        """Troca cada chave pelo nome; None se alguma ainda não deu para traduzir."""
        if "\x1c" not in text:
            return text
        missing = []

        def sub(m):
            name = self.lookup(m.group(1))
            if name is None:
                missing.append(m.group(1))
                return ""
            return name

        out = CODE.sub(sub, text).replace("\x1c", "").strip()
        return None if missing or not out else out


NAMES = ClientNames()
