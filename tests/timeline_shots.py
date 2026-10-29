# -*- coding: utf-8 -*-
"""Prints só da aba Linha do tempo: a luta toda, um trecho aproximado com o mouse em cima e tudo ligado.

uso: python tests\\timeline_shots.py PASTA_DE_SAIDA replay.rrf [TEMA]
(o widget sai com o DPS ativo, para conferir essa opção também)
"""

import sys

from shots import Shooter

OUT, REPLAY = sys.argv[1], sys.argv[2]
s = Shooter(OUT)
app = s.app
if len(sys.argv) > 3:
    app.set_theme(sys.argv[3])
app.set_rate("active")
app.watcher.open(REPLAY)
app.dirty = True
s.shot("01_widget")
app.open_analysis()
win = app.analysis
win.top.geometry("1180x860+60+40")
win.select_tab("linha")
win.refresh(force=True)
s.shot_window(win.top, "02_linha_do_tempo")
tab = win.timeline
d = tab.data
if d:
    first = next((e["t"] for e in d["events"] if e["kind"] in ("reflect", "death")), d["start"])
    tab.chart.view = (first - 2500, first + 2500)
    tab.chart.redraw()
    tab.chart._set_hover(tab.chart.x_of(first + 100))
    s.shot_window(win.top, "03_trecho_com_mouse")
    for lane in d["lanes"]:
        tab.on[lane["key"]] = True
    tab.on["taken"] = True
    tab.players_on.update(d["players"][:4])
    tab.panel_sig = None
    win.refresh(force=True)
    tab.chart.reset_view()
    s.shot_window(win.top, "04_tudo_ligado")
    rows = list(tab.table.rows.values())
    pick = next((r for r in rows if r["kind"] == "death"), rows[0] if rows else None)
    if pick is not None:
        tab.table.select(pick["row"])
        tab.event_picked(pick)
        s.shot_window(win.top, "05_evento_escolhido")
# a dificuldade (HP) do chefe aparece no Dedo Duro e na tabela de Monstros
win.select_tab("dedo")
win.refresh(force=True)
s.shot_window(win.top, "06_dedo_duro")
win.select_tab("monstros")
win.refresh(force=True)
s.shot_window(win.top, "07_monstros")
win.close()
s.root.destroy()
