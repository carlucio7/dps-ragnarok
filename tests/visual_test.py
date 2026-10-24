# -*- coding: utf-8 -*-
"""Abre o medidor com um replay, passa pelas telas e salva prints (PNG).

uso: python tests\\visual_test.py PASTA_DE_SAIDA [replay.rrf]
"""

import os
import sys
import tempfile

from shots import Shooter
import fake_replay as fr

OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
REPLAY = sys.argv[2] if len(sys.argv) > 2 else None

s = Shooter(OUT)
app = s.app
print("fontes", {k: f.actual("family") for k, f in app.fonts.items()})
s.shot("01_aguardando")

if REPLAY:
    app.watcher.open(REPLAY)
else:
    ME = 1000
    ev = [(0, fr.spawn(2000 + i, "pc", 4252, n)) for i, n in enumerate(["Fenrir", "Bastion", "Corvina"])]
    ev += [(0, fr.spawn(60001, "mob", 20994, "Betelgeuse", boss=True))]
    for i in range(40):
        ev.append((1000 + i * 300, fr.skill_damage(ME, 60001, 2000000 + i * 7919, skill=5470 if i % 3 else 5469)))
        ev.append((1100 + i * 300, fr.skill_damage(2000 + i % 3, 60001, 5000000 // (i % 3 + 1))))
    path = os.path.join(OUT, "sintetico.rrf")
    with open(path, "wb") as f:
        f.write(fr.build(ME, ev, player="Aria")[0])
    app.watcher.open(path)
app.dirty = True
s.shot("02_grupo")
app.set_tab("skills")
s.shot("03_skills")
app.set_tab("targets")
s.shot("04_alvos")
app.set_tab("group")
app.toggle_session()
s.shot("05_encontro")
app.toggle_session()
app.set_hover(("btn", "reset"))
s.shot("06_hover_zerar")
app.set_hover(None)
app.set_rows(10)
app.set_theme("Claro")
s.shot("07_claro_10_linhas")
app.set_theme("Grafite")
app.set_rows(6)
app.set_scale(0.8)
s.shot("08_pequeno")
app.set_scale(1.3)
s.shot("09_grande")
app.set_scale(1.0)

# janela de análise completa
app.open_analysis()
an_win = app.analysis
an_win.top.geometry("1120x820+60+40")
an_win.nb.select(0)
an_win.refresh(force=True)
s.shot_window(an_win.top, "11_analise_resumo")
an_win.nb.select(1)
for i, name in enumerate(["habilidades", "monstros", "linha_do_tempo"]):
    an_win.player_nb.select(i)
    an_win.refresh(force=True)
    s.shot_window(an_win.top, "12_analise_jogadores_%d_%s" % (i, name))
an_win.nb.select(2)
for i, name in enumerate(["dano_por_jogador", "linha_do_tempo", "skills_contra", "skills_do_monstro"]):
    an_win.mob_nb.select(i)
    an_win.refresh(force=True)
    s.shot_window(an_win.top, "13_analise_monstro_%d_%s" % (i, name))
an_win.nb.select(3)
an_win.refresh(force=True)
s.shot_window(an_win.top, "14_analise_dps")
ts = an_win.dps_chart.data[0]
if ts:
    an_win.dps_selected((ts[len(ts) // 3], ts[len(ts) // 2]))
s.shot_window(an_win.top, "15_analise_dps_trecho")
an_win.top.geometry("760x560+60+40")
an_win.refresh(force=True)
s.shot_window(an_win.top, "16_analise_pequena")
an_win.nb.select(0)
an_win.refresh(force=True)
s.shot_window(an_win.top, "17_analise_pequena_resumo")
an_win.top.geometry("1400x900+60+40")
an_win.set_zoom(2)
an_win.nb.select(3)
an_win.refresh(force=True)
s.shot_window(an_win.top, "18_analise_zoom")
an_win.set_zoom(0)
# Dedo Duro: grupo (alertas e cada detalhe) e fora do grupo
an_win.top.geometry("1180x860+60+40")
an_win.nb.select(7)
an_win.refresh(force=True)
s.shot_window(an_win.top, "19_dedo_duro")
sub = an_win.dd_group["sub"]
for i in range(len(sub.tabs())):
    sub.select(i)
    an_win.refresh(force=True)
    s.shot_window(an_win.top, "20_dedo_duro_grupo_%d" % i)
an_win.dd_nb.select(1)
an_win.refresh(force=True)
s.shot_window(an_win.top, "21_dedo_duro_fora_do_grupo")
an_win.dd_nb.select(0)
an_win.close()
app.reset()
s.shot("10_zerado")
s.root.destroy()
