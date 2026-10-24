# -*- coding: utf-8 -*-
"""Prints do widget em vários tamanhos, linhas e temas.

uso: python tests\\sizes_test.py PASTA_DE_SAIDA [replay.rrf]
"""

import sys

from shots import Shooter

s = Shooter(sys.argv[1])
app = s.app
if len(sys.argv) > 2:
    app.watcher.open(sys.argv[2])
for scale in (0.7, 0.85, 1.0, 1.3, 1.7, 2.5):
    app.set_scale(scale)
    for tab in ("group", "skills"):
        app.set_tab(tab)
        s.shot("tam_%03d_%s" % (round(scale * 100), tab))
app.set_scale(1.0)
for width in (230, 380, 520):
    app.set_width(width)
    s.shot("largura_%d" % width)
    app.set_tab("skills")
    s.shot("largura_%d_skills" % width)
    app.set_tab("group")
app.set_width(300)
for rows in (4, 12):
    app.set_rows(rows)
    s.shot("linhas_%02d" % rows)
app.set_theme("Claro")
app.set_tab("group")
s.shot("claro")
s.root.destroy()
