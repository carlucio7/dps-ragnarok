"""Prints de divulgação com um replay de demonstração (nomes fictícios), nos 3 idiomas.

uso: python tools/demo_shots.py PASTA_DE_SAIDA
Gera PASTA/demo.rrf (luta contra o Betelgeuse em 2 fases, grupo de 7) e, para pt, en e es:
widget, resumo, análise de DPS, Dedo Duro (alertas, Garra Sombria e elemento).
"""

import os
import random
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

ME = 1000
BASTION, CORVINA, DALIA, ELRIC, FENRIR, GAIA = 2001, 2002, 2003, 2004, 2005, 2006
P1, P2 = 60001, 60002
PARTY = [(BASTION, 4254, "Bastion"), (CORVINA, 4255, "Corvina"), (DALIA, 4256, "Dalia"),
         (ELRIC, 4253, "Elric"), (FENRIR, 4302, "Fenrir"), (GAIA, 4303, "Gaia")]


def build(path):
    import fake_replay as fr
    rnd = random.Random(7)
    ev = [(0, fr.spawn(a, "pc", job, name)) for a, job, name in PARTY]
    ev += [(0, fr.spawn(P1, "mob", 20994, "Betelgeuse", boss=2)), (31500, fr.spawn(P2, "mob", 20994, "Betelgeuse", boss=2))]
    ev += [(100, fr.party_hp(a, 400000, 400000)) for a, _j, _n in PARTY]
    # buffs
    for a in (ME, BASTION, CORVINA, FENRIR, ELRIC, GAIA):
        ev += [(500, fr.status(a, 10, True, 240000)), (500, fr.status(a, 12, True, 240000)),
               (500, fr.status(a, 30, True, 300000))]
    for a in (ME, BASTION, FENRIR):
        ev += [(600, fr.status(a, 24, True, 55000))]
    ev += [(20000, fr.status(FENRIR, 24, False))]                       # Manejo Perfeito acabou e não voltou
    ev += [(0, fr.status(ME, 90, True)), (500, fr.status(FENRIR, 92, True)),   # fogo / vento na arma
           (700, fr.status(ME, 1359, True, 300000)), (1000, fr.status(BASTION, 341, True, val1=5)),
           (7000, fr.status(CORVINA, 1152, True, 150000, val1=4))]
    # debuffs no chefe
    ev += [(2000, fr.skill_use(BASTION, P1, 5001)), (2000, fr.status(P1, 730, True)), (22000, fr.status(P1, 730, False)),
           (5000, fr.status(P1, 1402, True)), (15000, fr.status(P1, 1402, False)),
           (8000, fr.status(P1, 1183, True, val1=100)), (28000, fr.status(P1, 1183, False)),
           (34000, fr.skill_use(BASTION, P2, 5001)), (34000, fr.status(P2, 730, True)), (54000, fr.status(P2, 730, False)),
           (36000, fr.status(P2, 1183, True, val1=100)), (60000, fr.status(P2, 1183, False)),
           (54000, fr.status(P2, 713, True)), (60000, fr.status(P2, 713, False))]
    # dano dos jogadores (fase 1: 1–30 s; fase 2: 33–62 s)
    plan = [(ME, (5473, 5469, 5470), 700, 3.0, 6.0), (FENRIR, (5473, 5474, 5469), 800, 2.5, 5.0),
            (BASTION, (5289, 2036, 5291), 1000, 2.0, 4.0), (CORVINA, (2217, 5215, 5222), 1500, 3.0, 7.0),
            (ELRIC, (5296,), 2500, 1.0, 2.0), (GAIA, (5426, 5428), 2000, 1.0, 2.0)]
    for src, skills, every, lo, hi in plan:
        for start, end, boss in ((1000, 30000, P1), (33000, 62000, P2)):
            t = start + rnd.randint(0, every)
            while t < end:
                if not (src == BASTION and 45000 <= t <= 49500):
                    dmg = int(rnd.uniform(lo, hi) * 1e6)
                    ev.append((t, fr.skill_damage(src, boss, dmg, skill=rnd.choice(skills), hits=rnd.randint(1, 5))))
                t += every + rnd.randint(-150, 150)
    # o chefe batendo, Dor Máxima refletindo e as mortes
    for t in range(4000, 61000, 3500):
        ev.append((t, fr.skill_damage(P1 if t < 31000 else P2, rnd.choice([ME, FENRIR, BASTION]),
                                      rnd.randint(20000, 90000), skill=768, hits=1)))
    for t in range(55000, 60000, 1000):
        ev.append((t, fr.skill_damage(P2, rnd.choice([ME, FENRIR]), rnd.randint(30000, 60000), skill=717, hits=1)))
    ev += [(45000, fr.vanish(BASTION)), (49500, fr.resurrect(BASTION)),
           (50000, fr.vanish(FENRIR)), (50800, fr.resurrect(FENRIR)),
           (31000, fr.vanish(P1, kind=0)), (62000, fr.vanish(P2))]
    with open(path, "wb") as f:
        f.write(fr.build(ME, sorted(ev, key=lambda e: e[0]), player="Aria", map_name="1@ch_t.gat")[0])


def shots(out, lang, replay):
    from shots import Shooter
    s = Shooter(os.path.join(out, "tmp_" + lang))
    app = s.app
    app.watcher.open(replay)
    app.set_rows(7)
    app.dirty = True
    s.out = out
    s.shot("widget_" + lang)
    app.open_analysis()
    w = app.analysis
    w.top.geometry("1180x860+60+40")
    w.select_tab("resumo")
    w.refresh(force=True)
    s.shot_window(w.top, "resumo_" + lang)
    w.select_tab("dps")
    w.refresh(force=True)
    s.shot_window(w.top, "dps_" + lang)
    w.select_tab("linha")
    w.refresh(force=True)
    s.shot_window(w.top, "linha_" + lang)
    w.select_tab("dedo")
    w.refresh(force=True)
    s.shot_window(w.top, "dedoduro_" + lang)
    sub = w.dd_group["sub"]
    for key, name in (("claw", "garra"), ("element", "elemento"), ("deaths", "mortes")):
        sub.select(w.dd_group["tabs"][key])
        w.refresh(force=True)
        s.shot_window(w.top, "%s_%s" % (name, lang))
    w.close()
    s.root.destroy()


if __name__ == "__main__":
    out = os.path.abspath(sys.argv[1])
    if len(sys.argv) > 2:                       # processo filho: um idioma
        shots(out, sys.argv[2], os.path.join(out, "demo.rrf"))
    else:
        os.makedirs(out, exist_ok=True)
        build(os.path.join(out, "demo.rrf"))
        for lang in ("pt", "en", "es"):
            env = dict(os.environ, RODPS_LANG=lang)
            subprocess.check_call([sys.executable, "-X", "utf8", os.path.abspath(__file__), out, lang], env=env)
