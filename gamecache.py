# -*- coding: utf-8 -*-
"""Tabelas do jogo já digeridas, guardadas em disco ao lado da configuração.

Ler a lista de itens do jogo (iteminfo, 18 mil itens rodados numa mini-VM de Lua) leva mais de 1 s de
processamento, e as tabelas de nomes dos sprites mais uns décimos. Essas leituras rodam em segundo plano, mas em
Python uma thread ocupada segura a janela: abrir uma aba com ícones ou desenhos ficava lento por segundos. Aqui o
resultado é guardado num arquivo e só é refeito quando o arquivo do jogo muda (tamanho ou data); nas outras vezes
abre em centésimos de segundo.
"""

import json
import os
import threading

import i18n

VERSION = 1
ITEMS_FILE = "itens_do_jogo.json"
_LOCK = threading.Lock()
_ITEMS = {}                   # caminho do iteminfo -> o resumo dele já pronto (nesta execução)


def _path(name):
    return os.path.join(os.path.dirname(i18n.config_path()), name)


def stamp(file):
    """O que identifica a versão de um arquivo do jogo: caminho, tamanho e data."""
    st = os.stat(file)
    return [os.path.normcase(os.path.abspath(file)), st.st_size, int(st.st_mtime)]


def load(name, mark):
    """O que foi guardado em `name` para a versão `mark` do arquivo do jogo, ou None."""
    try:
        with open(_path(name), encoding="utf-8") as f:
            d = json.load(f)
        return d["data"] if d.get("v") == VERSION and d.get("stamp") == mark else None
    except (OSError, ValueError, KeyError, AttributeError):
        return None


def save(name, mark, data):
    try:
        path = _path(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = "%s.%d.tmp" % (path, threading.get_ident())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"v": VERSION, "stamp": mark, "data": data}, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass


def items(info_path):
    """O resumo da lista de itens do jogo (System\\iteminfo_new.lub): dict(names, display, art, table, kinds,
    classnum), tudo por id do item. Lido uma vez só por execução (quem pedir ao mesmo tempo espera), e do disco
    enquanto o arquivo do jogo não mudar. Levanta OSError / ValueError se o arquivo não der para ler."""
    with _LOCK:
        got = _ITEMS.get(info_path)
        if got is not None:
            return got
        mark = stamp(info_path)
        raw = load(ITEMS_FILE, mark)
        if raw is None:
            import itemkind
            import lub
            import xp
            with open(info_path, "rb") as f:
                tbl = lub.run(f.read()).get("tbl") or {}
            rows = [(i, v) for i, v in tbl.items() if isinstance(i, int) and isinstance(v, dict)]
            raw = dict(
                names={str(i): xp._norm(v.get("identifiedDisplayName")) for i, v in rows},
                display={str(i): " ".join(v["identifiedDisplayName"].split()) for i, v in rows
                         if isinstance(v.get("identifiedDisplayName"), str) and v["identifiedDisplayName"].strip()},
                art={str(i): v["identifiedResourceName"] for i, v in rows
                     if isinstance(v.get("identifiedResourceName"), str) and v["identifiedResourceName"]},
                table={str(i): [[pct, list(group) if group else None, bool(event)] for pct, group, event in entries]
                       for i, entries in xp.parse_gear(tbl).items()},
                kinds={str(i): k for i, k in itemkind.parse_kinds(tbl).items()},
                classnum={str(i): v["ClassNum"] for i, v in rows
                          if isinstance(v.get("ClassNum"), int) and v["ClassNum"] > 0})
            save(ITEMS_FILE, mark, raw)
        got = _ITEMS[info_path] = dict(
            names={int(i): v for i, v in raw["names"].items()},
            display={int(i): v for i, v in raw["display"].items()},
            art={int(i): v for i, v in raw["art"].items()},
            table={int(i): [(pct, tuple(group) if group else None, bool(event)) for pct, group, event in entries]
                   for i, entries in raw["table"].items()},
            kinds={int(i): k for i, k in raw["kinds"].items()},
            classnum={int(i): v for i, v in raw["classnum"].items()})
        return got
