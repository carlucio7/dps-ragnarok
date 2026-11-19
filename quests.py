# -*- coding: utf-8 -*-
"""Nomes das missões, lidos do jogo instalado (System\\OngoingQuestInfoList_True.lub, ~0,3 s numa thread)."""

import os
import re
import threading

import i18n
from i18n import _

QUEST_FILES = {"pt": "System\\OngoingQuestInfoList_True.lub", "en": "System\\english\\OngoingQuestInfoList_True.lub",
               "es": "System\\spanish\\OngoingQuestInfoList_True.lub"}


def parse_titles(table):
    """{id da missão: título} da tabela QuestInfoList do jogo."""
    out = {}
    for qid, info in (table or {}).items():
        if isinstance(qid, int) and isinstance(info, dict) and isinstance(info.get("Title"), str):
            out[qid] = " ".join(info["Title"].split())
    return out


class _Quests:
    def __init__(self):
        self.titles, self._thread, self.version = None, None, 0

    def start(self, grf):
        """Começa a ler os títulos (uma vez). `grf` é o data.grf do jogo: a pasta System fica ao lado dele."""
        if self.titles is not None or self._thread is not None or not grf:
            return
        folder = os.path.dirname(grf)
        paths = [os.path.join(folder, QUEST_FILES.get(i18n.LANG, QUEST_FILES["pt"])), os.path.join(folder, QUEST_FILES["pt"])]

        def run():
            titles = {}
            try:
                import lub
                for path in paths:
                    if os.path.isfile(path):
                        with open(path, "rb") as f:
                            titles = parse_titles(lub.run(f.read()).get("QuestInfoList"))
                        if titles:
                            break
            except (OSError, ValueError, IndexError, KeyError, AttributeError):
                titles = {}
            finally:
                self.titles = titles
                self.version += 1
                self._thread = None
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()


NAMES = _Quests()


def title(qid):
    """Nome da missão no jogo (sem o "[Diário] " da frente) ou "Missão N" enquanto não se sabe."""
    try:
        import clientdata
        NAMES.start(clientdata.NAMES.grf)
    except ImportError:
        pass
    name = (NAMES.titles or {}).get(qid)
    return name if name else _("Missão %d") % qid


def row_title(row):
    """Nome de uma linha de xp.quest_rows: o título da missão; numa entrega que só abre uma espera (o Lanche do
    Diabo), o título da espera sem a etiqueta da frente ("[Espera] ") e o item entregue."""
    if not row.get("handin"):
        return title(row["quest"])
    name = re.sub(r"^\s*\[[^\]]*\]\s*", "", title(row["quest"]))
    if row.get("item"):
        import meter
        name = "%s (%s)" % (name, meter.item_name(row["item"]))
    return name
