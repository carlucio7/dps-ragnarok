"""Testes do decodificador e do agregador (sem janela, sem mexer no jogo).

uso: python tests\\logic_test.py
"""

import collections
import json
import os
os.environ.setdefault("RODPS_LANG", "pt")      # os testes conferem os textos em português
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import rrf  # noqa: E402
import meter  # noqa: E402
import fake_replay as fr  # noqa: E402
from fmt import num, full, dur  # noqa: E402

ME, OTHER, MOB, MOB2 = 1000, 2000, 50001, 50002
BETEL = 20994
failures = 0


def check(cond, msg):
    global failures
    print(("ok   " if cond else "FALHA") + " " + msg)
    if not cond:
        failures += 1


def combat_of(data, gap_ms=10000):
    h = rrf.Header(data)
    s = rrf.Session(h, data)
    c = meter.Combat(s, gap_ms)
    for e in rrf.initial_entities(h, data):
        c.add_entity(e)
    r = rrf.StreamReader(h.keys, rrf.WANTED)
    c.feed(r.feed(data[h.stream_offset:]), r.last_time)
    c.finished = True             # replay terminado: nada "ao vivo"
    return c


# --- chave: valores tirados de um replay real (22/10/2026 23:16:53) -----------
k = rrf.Keys(2026, 10, 22, 23, 16, 53)
check(k.k2 & 0xFFFFFFFF == 0x06A202E0, "k2 derivado da hora")
check(((k.k1 + 1) * k.k2) & 0xFFFFFFFF == 0x4366B800, "primeira palavra da chave")
blob = bytes(range(37))
check(rrf.decrypt(rrf.decrypt(blob, k), k) == blob, "cifra XOR e simetrica (com bytes de sobra)")

# --- formatacao ---------------------------------------------------------------
check(num(92508200) == "92,5M" and num(7993472848) == "7,99B" and num(950) == "950", "num()")
check(full(212804388) == "212.804.388", "full()")
check(dur(61000) == "01:01" and dur(3725000) == "1:02:05", "dur()")

# --- cabecalho, sessao e dano basico -----------------------------------------
events = [
    (0, fr.spawn(OTHER, "pc", 4252, "Outro")),
    (0, fr.spawn(MOB, "mob", 1002, "Poring")),
    (1000, fr.skill_damage(ME, MOB, 1000)),
    (1500, fr.auto_attack(ME, MOB, 300, left=200)),                 # dual wield: 500
    (2000, fr.skill_damage(OTHER, MOB, 4000)),
    (2500, fr.skill_damage(MOB, ME, 999)),                          # monstro batendo: ignora
    (3000, fr.auto_attack(ME, MOB, 0, action=11)),                  # errou
    (3100, fr.auto_attack(ME, MOB, 0, action=2)),                   # sentou: nao e ataque
    (4000, fr.skill_damage(ME, MOB, 0, action=6)),                  # marcador de animacao
]
data, _ = fr.build(ME, events, player="Aria", map_name="tra_fild",
                   entities=[(4404, "mob", 21068, "Dummy - Dragão")])
c = combat_of(data)
check(c.session.player == "Aria" and c.session.aid == ME, "sessao: nome e AID")
check(c.name_of(4404) == "Dummy - Dragão", "entidade inicial (container 15)")
snap = c.snapshot()
check(snap["my_total"] == 1500, "meu dano = 1000 + 300 + 200 (mao esquerda) -> %d" % snap["my_total"])
check([p["name"] for p in snap["players"]] == ["Outro", "Aria"], "ranking do grupo")
check(snap["my_hits"] == 3, "acertos contam o erro, nao sentar nem marcador -> %d" % snap["my_hits"])
check(snap["skills"][0]["name"] == "Explosão Galática", "nome da skill em portugues")
check(snap["target"] == "Poring", "alvo principal")
check(snap["duration_ms"] == 2000, "duracao do encontro 1000..3000 ms -> %d" % snap["duration_ms"])

# --- invocacao e unidade no chao contam para o dono ----------------------------
events = [
    (0, fr.spawn(MOB, "mob", 1002, "Poring")),
    (0, fr.spawn(7001, "bionic", 20848, "Bionico", gid=ME)),
    (0, fr.ground_unit(7002, ME)),
    (0, fr.spawn(7003, "homun", 6001, "Vanilmirth", gid=OTHER)),     # dono aparece depois
    (0, fr.spawn(OTHER, "pc", 4252, "Outro")),
    (1000, fr.skill_damage(7001, MOB, 100)),
    (1100, fr.skill_damage(7002, MOB, 10)),
    (1200, fr.skill_damage(7003, MOB, 7)),
]
c = combat_of(fr.build(ME, events)[0])
snap = c.snapshot()
check(snap["my_total"] == 110, "dano da invocacao + unidade no chao = 110 -> %d" % snap["my_total"])
check(any(k["name"].startswith("Bionico:") for k in snap["skills"]), "skill da invocacao rotulada")
check(any(p["name"] == "Outro" and p["total"] == 7 for p in snap["players"]), "homunculo do outro jogador")

# --- encontros: pausa separa; fases do Betelgeuse nao -------------------------
events = [
    (0, fr.spawn(MOB, "mob", 1002, "Poring")),
    (1000, fr.skill_damage(ME, MOB, 100)),
    (2000, fr.vanish(MOB)),
    (30000, fr.spawn(MOB2, "mob", 1002, "Poring")),
    (31000, fr.skill_damage(ME, MOB2, 50)),                         # 29 s depois: outro encontro
    (50000, fr.spawn(60001, "mob", BETEL, "Betelgeuse", boss=True)),
    (51000, fr.skill_damage(ME, 60001, 1000)),
    (55000, fr.skill_damage(ME, 60001, 1000)),
    (55500, fr.vanish(60001, 0)),                                   # some sem morrer (troca de fase)
    (66000, fr.spawn(60002, "mob", BETEL, "Betelgeuse", boss=True)),
    (67000, fr.skill_damage(ME, 60002, 2000)),                      # 12 s depois: mesma luta
    (71000, fr.skill_damage(ME, 60002, 2000)),
    (71500, fr.vanish(60002, 1)),                                   # morreu
    (90000, fr.spawn(60003, "mob", BETEL, "Betelgeuse", boss=True)),
    (91000, fr.skill_damage(ME, 60003, 5)),                         # outro Betelgeuse: luta nova
]
betel_events = events
c = combat_of(fr.build(ME, events)[0])
encs = c.history + [c.current]
check(len(encs) == 4, "4 encontros (poring, poring, betel com 2 fases, betel novo) -> %d" % len(encs))
betel = c.snapshot(encs[2])
check(betel["my_total"] == 6000 and betel["target"] == "Betelgeuse ★ (2 fases)",
      "fases somadas: %s / %s" % (betel["my_total"], betel["target"]))
check(betel["duration_ms"] == 20000 - 12000, "troca de fase fora do tempo: %d ms" % betel["duration_ms"])
sess = c.snapshot(session=True)
check(sess["my_total"] == 6155, "sessao soma tudo -> %d" % sess["my_total"])
check(sess["duration_ms"] == 1000 + 1000 + 8000 + 1000, "sessao usa so tempo em combate -> %d" % sess["duration_ms"])
c.reset()
check(c.snapshot() is None and c.snapshot(session=True) is None, "zerar limpa tudo")
for gap in (15000,):
    # pausa configurada maior que a troca de fase (12 s): ela continua fora do tempo em combate
    cg = combat_of(fr.build(ME, betel_events)[0], gap)
    bg = next(e for e in cg.encounters() if 60001 in e.by_target)
    check(bg.duration_ms() == 8000, "pausa de %d s: troca de fase fora do tempo (%d ms)" % (gap // 1000, bg.duration_ms()))

# --- arquivo crescendo aos pedacos (como o jogo grava) -------------------------
tmp = tempfile.mkdtemp()
try:
    events = [(0, fr.spawn(MOB, "mob", 1002, "Poring"))] + \
             [(1000 + i * 250, fr.skill_damage(ME, MOB, 1000 + i)) for i in range(200)]
    data, stream_at = fr.build(ME, events)
    path = os.path.join(tmp, "teste.rrf")
    w = meter.Watcher(tmp, auto=False)
    seen = []
    with open(path, "wb") as fh:
        fh.write(data[:stream_at - 37])                             # cabecalho incompleto
        fh.flush()
        check(not w.poll(time.time()), "cabecalho pela metade: espera")
        pos = stream_at - 37
        step = 97                                                   # corta registros no meio
        while pos < len(data):
            fh.write(data[pos:pos + step])
            fh.flush()
            pos += step
            w.poll(time.time())
            if w.file and w.file.ready and w.file.combat.current:
                seen.append(w.file.combat.snapshot()["my_total"])
    total = sum(1000 + i for i in range(200))
    final = w.file.combat.snapshot()["my_total"]
    check(final == total, "leitura incremental = total (%d == %d)" % (final, total))
    check(len(set(seen)) > 10 and seen == sorted(seen), "o total cresce enquanto o arquivo cresce")
    check(w.recording(time.time()), "arquivo recente = gravando")
    check(not w.recording(time.time() + 60), "parado ha 60 s = encerrado")

    # inicio da gravacao: o cliente ainda nao preencheu a tabela do cabecalho
    path2 = os.path.join(tmp, "sem_tabela.rrf")
    blank = fr.without_table(data)
    w2 = meter.Watcher(tmp, auto=False)
    with open(path2, "wb") as fh:
        fh.write(blank[:stream_at + 5])                             # containers prontos, 1o registro pela metade
        fh.flush()
        w2.poll(time.time() + 1)
        check(not (w2.file and w2.file.ready), "sem tabela e sem 1o registro: espera")
        fh.write(blank[stream_at + 5:stream_at + 300])
        fh.flush()
        w2.poll(time.time() + 1)
        ok = w2.file is not None and w2.file.ready and w2.file.header.scanned
        check(ok, "sem tabela: acha containers e fluxo sozinho")
        fh.write(blank[stream_at + 300:])
        fh.flush()
        w2.poll(time.time() + 1)
    snap2 = w2.file.combat.snapshot()
    check(snap2["my_total"] == total and w2.file.session.player == "Tester",
          "sem tabela: mesmo jogador e total (%d)" % snap2["my_total"])

    # gravacao comecando a 0 h: chave fraca (metade de cada palavra sem cifra)
    for date in [(2026, 10, 23, 0, 24, 14), (2026, 10, 23, 0, 0, 7), (2026, 1, 1, 0, 0, 0)]:
        weak = fr.without_table(fr.rekey(data, date))
        hw = rrf.Header(weak)
        cw = combat_of(weak)
        check(hw.scanned and hw.stream_offset == stream_at and cw.snapshot()["my_total"] == total,
              "sem tabela e chave fraca (%02d:%02d:%02d)" % date[3:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# --- monstros novos (nome em código) e várias instalações do jogo ----------------
import base64  # noqa: E402
import clientdata  # noqa: E402

tmp = tempfile.mkdtemp()
try:
    os.environ["RODPS_CONFIG"] = os.path.join(tmp, "cfg", "config.json")      # o cache não vai para o seu PC
    game = os.path.join(tmp, "Jogo")
    os.makedirs(os.path.join(game, "Replay"))
    b64 = lambda t: base64.b64encode(t.encode("utf-8")).decode()
    csv = "VpIB,,%s,,,,,%s,,%s\noIY2DA,,%s,,,,,%s,,%s\n" % (
        b64("[Bio] Lava Golem"), b64("[Eco] Golem de Lava"), b64("[Eco] Gólem de Lava"),
        b64("A long sentence"), b64("Uma frase"), b64("Una frase"))
    fr.build_grf(os.path.join(game, "data.grf"), {"data\\i18n\\sc\\abc.csv": csv.encode("utf-8"),
                                                 "data\\sprite\\x.spr": b"nada"})
    check(meter.replay_dir_for(game) == os.path.join(game, "Replay"), "escolher a pasta do jogo usa a pasta Replay dela")
    clientdata.NAMES = clientdata.ClientNames()
    rpath = os.path.join(game, "Replay", "bio.rrf")
    with open(rpath, "wb") as fh:
        fh.write(fr.build(ME, [(0, fr.spawn(685, "mob", 21559, "\x1cVpIB\x1c")), (0, fr.spawn(686, "mob", 21999, "")),
                               (1000, fr.skill_damage(ME, 685, 5000)), (1500, fr.skill_damage(ME, 686, 3000))])[0])
    rf = meter.ReplayFile(rpath)
    rf.poll(max_bytes=1 << 30)
    rf.combat.name_of(685)
    clientdata.NAMES.wait(30)
    names = {t["name"] for t in rf.combat.snapshot(session=True)["targets"]}
    check(names == {"[Eco] Golem de Lava", "Monstro 21999"},
          "nome de monstro novo vem das tabelas do jogo; sem nome, mostra o id do monstro: %s" % names)
    check(os.path.isfile(clientdata.cache_path()) and "oIY2DA" not in (clientdata.NAMES.names or {}),
          "cache dos nomes gravado (só chaves curtas)")
    # várias instalações: segue a gravação mais nova de qualquer pasta Replay
    other = os.path.join(tmp, "Outro", "Replay")
    os.makedirs(other)
    old, new = os.path.join(game, "Replay", "a.rrf"), os.path.join(other, "b.rrf")
    for path in (old, new):
        with open(path, "wb") as fh:
            fh.write(b"x")
    os.utime(old, (time.time() - 5, time.time() - 5))
    saved = meter.find_replay_dirs
    meter.find_replay_dirs = lambda: [os.path.join(game, "Replay"), other]
    try:
        w = meter.Watcher(None)
        check(w.folders == [os.path.join(game, "Replay"), other] and w.scan(time.time()) == new,
              "várias pastas Replay: segue a gravação mais nova")
    finally:
        meter.find_replay_dirs = saved
finally:
    os.environ.pop("RODPS_CONFIG", None)
    clientdata.NAMES = clientdata.ClientNames()
    shutil.rmtree(tmp, ignore_errors=True)

# inglês e espanhol sem o jogo instalado: nomes da cópia do pacote (data/names.json), descrições do
# rAthena e catálogo para skills de monstro, as classes que o cliente grafa diferente (JT_ARC_MAGE)
# e nomes sem o espaço que o cliente deixa sobrando
probe = ("import meter; print('|'.join([meter.job_name(4255), meter.job_name(4309), meter.skill_name(172), "
         "meter.skill_name(717), meter.skill_name(783), meter.status_name(1339), meter.skill_name(5001), "
         "meter.skill_name(444)]))")
for lang, expected in (("en", "Arch Mage|Sky Emperor|Guided Attack|Max Pain (attack)|Killing Aura|Killing Aura|Dark Claw|"
                              "Solar, Lunar and Stellar Union"),
                       ("es", "Archimago|Emperador Celestial|Ataque Guiado|Dolor Máxima (ataque)|Aura Asesina|"
                              "Aura Asesina|Garra Tenebrosa|Unión Solar, Lunar y Estelar")):
    out = subprocess.run([sys.executable, "-X", "utf8", "-c", probe], cwd=os.path.join(HERE, ".."),
                         env=dict(os.environ, RODPS_LANG=lang), capture_output=True, text=True,
                         encoding="utf-8").stdout.strip()
    check(out == expected, "nomes em %s sem o jogo: %s" % (lang, out))

# --- replays reais (opcional) ------------------------------------------------
# tests/local_replays.json (fica só no seu PC, fora do repositório):
#   {"scan": ["C:/.../a.rrf", ...], "totals": [["C:/.../b.rrf", "Personagem", 123456], ...]}
# "scan": replays reais lidos sem a tabela e com chave fraca; "totals": dano conferido no Ragna Recap.
try:
    with open(os.path.join(HERE, "local_replays.json"), encoding="utf-8") as _f:
        LOCAL = json.load(_f)
except (OSError, ValueError):
    LOCAL = {}
for path in LOCAL.get("scan", []):
    if not os.path.isfile(path):
        print("pula  %s (nao encontrado)" % path)
        continue
    real = open(path, "rb").read()
    ref = rrf.Header(real)
    for date in [None, (2026, 10, 23, 0, 0, 7)]:
        b = fr.without_table(real if date is None else fr.rekey(real, date))
        hb = rrf.Header(b)
        check(hb.scanned and sorted(hb.containers) == sorted(ref.containers),
              "%s sem tabela%s: containers iguais" % (os.path.basename(path), "" if date is None else " (00:00:07)"))

# --- analise (abas da janela completa) ----------------------------------------
import analysis as an  # noqa: E402

events = [
    (0, fr.spawn(OTHER, "pc", 4252, "Outro")),
    (0, fr.spawn(60001, "mob", BETEL, "Betelgeuse", boss=True)),
    (1000, fr.cast(60001, OTHER, 2217, 1000)),
    (1050, fr.cast(60001, OTHER, 2217, 1000)),                      # repetido em 50 ms: ignora
    (2000, fr.skill_damage(60001, OTHER, 5000, skill=2217, hits=1, action=5)),
    (2100, fr.skill_damage(60001, ME, 3000, skill=2217, hits=1, action=5)),
    (2500, fr.skill_use(60001, 60001, 685)),                        # invencibilidade (sem dano)
    (3000, fr.skill_damage(ME, 60001, 0, skill=5469, hits=2, action=8)),   # acerto de dano 0
    (3500, fr.skill_damage(ME, 60001, 1000, skill=5469, hits=2, action=8)),
    (4000, fr.skill_damage(ME, 60001, 4000, skill=5473)),
    (9000, fr.skill_damage(OTHER, 60001, 9000, skill=5470)),
    (9500, fr.vanish(60001, 1)),
]
c = combat_of(fr.build(ME, events)[0])
rng, dur_ms = an.scope_range(c, None)
pl = an.players(c, rng, dur_ms)
check([(p["name"], p["total"], p["hits"], p["kills"]) for p in pl] == [("Outro", 9000, 1, 1), ("Tester", 5000, 3, 0)],
      "jogadores: dano, acertos (com o de dano 0) e golpe fatal")
mob = an.monsters(c, rng)[0]
check(mob["killer"] == "Outro" and mob["ttk"] == 9500 - 3000 and mob["max_hp"] == 500000000,
      "monstro: abatido por, tempo até abate, HP pela dificuldade (morreu com pouco dano: Selado)")
sk = {s["skill"]: s for s in an.monster_skills(c, rng, mob["key"])}
check(sk[2217]["hits"] == 2 and sk[2217]["total"] == 8000 and sk[2217]["targets"] == 2 and sk[2217]["cast"] == 1000,
      "habilidades do monstro: acertos, alvos e conjuracao (sem repetida)")
check(sk[685]["nodmg"] == 1 and sk[685]["hits"] == 0, "habilidade do monstro sem dano")
mine = {s["skill"]: s for s in an.player_skills(c, rng, ME, dur_ms)}
check(mine[5469]["hits"] == 2 and mine[5469]["total"] == 1000 and mine[5469]["avg_multi"] == 2,
      "skills do jogador: acertos e hits medios")
ws = an.window_stats(c, ME, 0, 10000)
check(ws["events"] == 3 and ws["span_ms"] == 1000 and ws["dps"] == 5000 and ws["top_skill"] == "Explosão Galática"
      and ws["longest_gap"] == 500, "janela de DPS: eventos, janela de combate, DPS, maior intervalo")
ts, series = an.timeline(c, rng, 1000)
check(len(ts) == 7 and sum(series[0][2]) == 9000 and series[0][1] == "Outro", "linha do tempo por jogador")

# --- buffs, debuffs, avisos e morte -------------------------------------------
BLESS, DARKCLAW = 10, 730
events = [
    (0, fr.spawn(MOB, "mob", 1002, "Poring")),
    (500, fr.status(ME, BLESS, True, 60000, 60000)),
    (1000, fr.skill_damage(ME, MOB, 100)),
    (2000, fr.status(MOB, DARKCLAW, True, 4000, 4000)),
    (5000, fr.status(ME, BLESS, False)),                            # Bênção acabou no meio da luta
    (6000, fr.status(MOB, DARKCLAW, False)),
    (9000, fr.skill_damage(ME, MOB, 100)),
    (9500, fr.hp(30000)),
    (10000, fr.skill_damage(MOB, ME, 50000, skill=0, action=0)),
    (10100, fr.vanish(ME, 1)),
]
c = combat_of(fr.build(ME, events)[0])
rows, total = an.buff_uptime(c, ME, None)
bless = next(r for r in rows if r["efst"] == BLESS)
check(total == 8000 and abs(bless["uptime"] - 0.5) < 1e-9 and bless["kind"] == "Grupo/suporte",
      "uptime de buff: Bênção 50%% de 8 s (%s)" % bless["uptime"])
drows, span = an.mob_debuffs(c, None, MOB)
claw = next(r for r in drows if r["efst"] == DARKCLAW)
check(span == 8000 and abs(claw["uptime"] - 0.5) < 1e-9 and claw["important"], "debuff no monstro: Garra Sombria 50%")
texts = [a[3] for a in c.alerts]
check("Bênção acabou" in texts, "aviso de buff que acabou na luta: %s" % texts)
dr = an.deaths(c)
check(len(dr) == 1 and dr[0]["hit"] == 50000 and dr[0]["hp_before"] == 30000 and dr[0]["overkill"] == 20000,
      "recap de morte: golpe 50.000 com 30.000 de HP = overkill 20.000")
check(any(t.startswith("Você morreu") and "overkill 20,0K" in t for t in texts), "aviso de morte com overkill")

# --- resumo da morte no widget: 5 s antes, cortados na última cura até 95% da vida ---------------------
COMET, TETRA = 2213, 2217


def death_events(heal, to=98000):
    ev = [(0, fr.spawn(MOB, "mob", 1002, "Poring")),
          (100, fr.hp(100000, rrf.SP_MAXHP)), (110, fr.hp(100000)),
          (500, fr.skill_damage(MOB, ME, 5000, skill=COMET, hits=1)),     # mais de 5 s antes da morte
          (550, fr.hp(95000)),
          (2000, fr.skill_damage(MOB, ME, 60000, skill=COMET, hits=1)),
          (2050, fr.hp(35000))]
    if heal:
        ev.append((3000, fr.hp(to)))                                      # curou até 98% (ou só 90%)
    ev += [(6000, fr.skill_damage(MOB, ME, 120000, skill=TETRA, hits=1)), (6100, fr.vanish(ME, 1))]
    return ev


for heal in (True, False):
    cd = combat_of(fr.build(ME, death_events(heal))[0])
    dt = next(t for t, a in cd.death_log if a == ME)
    card = an.death_card(cd, ME, dt)
    skills = sorted(g["skill"] for g in card["sources"])
    if heal:
        check(skills == ["Tetra Vortex"] and card["healed"] and card["window"] == dt - 3000 and cd.death_alerts,
              "resumo da morte: curou até 98%% depois do Cometa, só o Tetra Vortex conta (%s, %d ms)" % (
                  skills, card["window"]))
    else:
        check(skills == ["Cometa", "Tetra Vortex"] and not card["healed"] and card["window"] == 5000
              and card["sources"][0]["skill"] == "Tetra Vortex" and card["sources"][1]["dmg"] == 60000,
              "resumo da morte: sem cura, os 5 s antes (o Cometa de 5,6 s antes fica de fora): %s" % skills)
cd = combat_of(fr.build(ME, death_events(True, to=90000))[0])
dt = next(t for t, a in cd.death_log if a == ME)
card = an.death_card(cd, ME, dt)
check(sorted(g["skill"] for g in card["sources"]) == ["Cometa", "Tetra Vortex"] and not card["healed"],
      "resumo da morte: curou só até 90% (menos de 95%), o Cometa continua contando")
again = death_events(False) + [(7000, fr.resurrect(ME)), (7100, fr.hp(50000)),
                               (8000, fr.skill_damage(MOB, ME, 90000, skill=TETRA, hits=1)), (8100, fr.vanish(ME, 1))]
cd = combat_of(fr.build(ME, again)[0])
nths = [an.death_card(cd, ME, t)["nth"] for t, a in cd.death_log if a == ME]
check(nths == [1, 2], "resumo da morte: a 2ª morte no mesmo encontro é contada (muda o título): %s" % nths)

# --- União Solar, Lunar e Estelar (Mestre Taekwon) -----------------------------
MAXHP = 100000
events = [(0, fr.spawn(MOB, "mob", 21068, "Dummy - Dragão")), (100, fr.hp(MAXHP, rrf.SP_MAXHP)), (100, fr.hp(MAXHP))]
hpv = MAXHP
for i in range(42):                                                 # cada ataque custa 2% do HP máx.
    t = 1000 + i * 300
    events.append((t, fr.skill_damage(ME, MOB, 1000)))
    hpv -= MAXHP * 2 // 100
    events.append((t + 50, fr.hp(hpv)))
    if hpv <= MAXHP * 20 // 100:
        events.append((t + 100, fr.vanish(ME, 1)))                 # atacou com 20% ou menos: morreu
        break
data = fr.build(ME, events, option=rrf.OPTION_FLYING)[0]
c = combat_of(data)
texts = [a[3] for a in c.alerts]
check(any(x.startswith("HP 28% com a União") for x in texts), "aviso de HP baixo com a União (28%%): %s" % texts[:2])
check(any("pode matar" in x for x in texts), "segundo aviso (22% ou menos)")
d = an.deaths(c)[0]
check(d["fusion"] and d["hp_pct"] == 0.2 and d["no_hit"], "morte atribuída à União (atacou com 20%% de HP): %s" % d["hp_pct"])
check(any(x.startswith("Você morreu: União Solar (atacou com 20% de HP)") for x in texts), "aviso de morte pela União")
c2 = combat_of(fr.build(ME, events)[0])                             # sem a União: não atribui
check(not an.deaths(c2)[0]["fusion"] and not any(a[2] == "fusion" for a in c2.alerts),
      "sem a opção 'voando' nada é atribuído à União")

# --- invocações de jogadores, filtro de MVP e armadilhas do mapa --------------
SPHERE, SOUL, DUMMY = 70001, 70002, 4404
events = [
    (0, fr.spawn(OTHER, "pc", 4259, "Coral")),
    (0, fr.spawn(SPHERE, "mob", 1142, "Coral", gid=OTHER)),           # Esfera Marinha do Coral
    (0, fr.spawn(MOB, "mob", 1002, "Poring")),
    (0, fr.spawn(SOUL, "mob", 20995, "Alma Morta", boss=1)),
    (0, fr.spawn(60001, "mob", BETEL, "Betelgeuse", boss=2)),
    (0, fr.spawn(DUMMY, "mob", 21068, "Dummy - Dragão", boss=1)),
    (1000, fr.skill_damage(ME, SPHERE, 100000)),                     # bater na esfera não é dano em monstro
    (1100, fr.skill_damage(SPHERE, 60001, 777)),                     # a explosão conta para o dono
    (1200, fr.skill_damage(ME, MOB, 10)),
    (1300, fr.skill_damage(ME, SOUL, 20)),
    (1400, fr.skill_damage(ME, 60001, 3000)),
    (1500, fr.skill_damage(ME, DUMMY, 400)),
]
data = fr.build(ME, events)[0]
c = combat_of(data)
pl = {p["name"]: p["total"] for p in an.players(c, None, 1000)}
check(pl == {"Tester": 3430, "Coral": 777}, "invocação de jogador não é alvo; explosão conta para o dono: %s" % pl)
h = rrf.Header(data)
cm = meter.Combat(rrf.Session(h, data), 10000, "mvp")
r = rrf.StreamReader(h.keys, rrf.WANTED)
cm.feed(r.feed(data[h.stream_offset:]), r.last_time)
pl = {p["name"]: p["total"] for p in an.players(cm, None, 1000)}
check(pl == {"Tester": 3400, "Coral": 777}, "só MVPs e bonecos: ignora monstro normal e minion: %s" % pl)

MAXHP = 100000
events = [(0, fr.spawn(60001, "mob", BETEL, "Betelgeuse", boss=2)), (100, fr.hp(MAXHP, rrf.SP_MAXHP)), (100, fr.hp(MAXHP)),
          (500, fr.skill_damage(ME, 60001, 1000)),
          (2000, fr.effect(ME, rrf.EF_TRAP)), (2000, fr.hp(40000)),      # armadilha: 60% do HP máx.
          (2500, fr.skill_damage(ME, 60001, 1000)),
          (4000, fr.effect(ME, rrf.EF_TRAP)), (4000, fr.hp(0)), (4000, fr.vanish(ME, 1))]
c = combat_of(fr.build(ME, events)[0])
d = an.deaths(c)[0]
check(d["trap"] and abs(d["trap_pct"] - 0.6) < 1e-9 and d["hit"] == 60000 and d["hp_before"] == 40000
      and d["overkill"] == 20000, "armadilha do mapa: 60%% do HP máx. com 40.000 de HP = overkill 20.000 (%s)"
      % {k: d[k] for k in ("trap", "trap_pct", "hit", "hp_before", "overkill")})
taken = {r["source"]: r["total"] for r in an.damage_taken(c, None, ME)}
check(taken.get("Armadilha do mapa") == 120000, "armadilhas no dano recebido (a letal pela estimativa): %s" % taken)
check(any(a[3].startswith("Você morreu: armadilha do mapa (~60% do HP máx.) · overkill 20,0K") for a in c.alerts),
      "aviso de morte pela armadilha")

# --- testes de build (histórico local) -----------------------------------------
import testes  # noqa: E402

tmp = tempfile.mkdtemp()
try:
    store = testes.Store(os.path.join(tmp, "testes.json"))
    dummy = [(0, fr.spawn(4404, "mob", 21068, "Dummy - Dragão"))]
    run1 = dummy + [(1000 + i * 500, fr.skill_damage(ME, 4404, 1000)) for i in range(20)]
    run2 = dummy + [(1000 + i * 500, fr.skill_damage(ME, 4404, 1500)) for i in range(20)]
    for i, ev in enumerate((run1, run2)):
        path = os.path.join(tmp, "teste%d.rrf" % i)
        with open(path, "wb") as f:
            f.write(fr.build(ME, ev, date=(2026, 10, 23, 1, i, 0))[0])
        rf = meter.ReplayFile(path, 15000)
        rf.poll()
        rf.combat.finished = True
        check(testes.auto_save(store, rf, set()) == 1, "teste %d no boneco salvo sozinho" % (i + 1))
        check(testes.auto_save(store, rf, set()) == 0, "teste %d não é salvo duas vezes" % (i + 1))
    store2 = testes.Store(store.path)
    check(len(store2.records) == 2, "histórico gravado no arquivo")
    cmp = testes.compare(store2.records[0], store2.records[1])
    dps = cmp["summary"][0]
    check(abs(dps["diff"] - 0.5) < 1e-9, "comparação: +50%% de DPS (%s)" % dps["diff"])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# --- Dedo Duro ----------------------------------------------------------------
import dedoduro as dd  # noqa: E402

EXE, CARD, MAG, FORA, BOSS = 2001, 2002, 2003, 3001, 60001
ev = [(0, fr.spawn(EXE, "pc", 4254, "Exec")), (0, fr.spawn(CARD, "pc", 4256, "Card")),
      (0, fr.spawn(MAG, "pc", 4255, "Mago")), (0, fr.spawn(FORA, "pc", 4302, "Fora")),
      (0, fr.spawn(BOSS, "mob", BETEL, "Betelgeuse", boss=2))]
ev += [(100, fr.party_hp(a, 50000, 50000)) for a in (EXE, CARD, MAG)]       # só quem está no grupo
ev += [(500, fr.status(ME, 10, True)), (500, fr.status(EXE, 10, True)), (20000, fr.status(EXE, 10, False)),
       (500, fr.status(ME, 12, True)), (500, fr.status(EXE, 12, True)),   # Agilidade: some na morte do Exec
       (0, fr.status(ME, 90, True)),                                       # arma de fogo (Chamas)
       (9000, fr.status(EXE, 91, True)),                                   # arma de água
       (1000, fr.status(EXE, 341, True, val1=5)),                          # Aplicar Toxina
       (9000, fr.status(MAG, 1152, True, val1=4)),                         # Clímax nv 4
       (2000, fr.skill_use(EXE, BOSS, 5001)), (2000, fr.status(BOSS, 730, True)),
       (22000, fr.status(BOSS, 730, False)),                               # Garra: 20 s, recarga 60 s
       (10000, fr.status(BOSS, 1183, True, val1=100)), (40000, fr.status(BOSS, 1183, False)),
       (30000, fr.status(BOSS, 713, True)), (40000, fr.status(BOSS, 713, False)),   # Dor Máxima
       (30000, fr.status(CARD, 15, False)), (30001, fr.status(CARD, 15, False))]    # Impositio de antes da gravação
ev += [(32000 + i * 1000, fr.skill_damage(BOSS, ME, 500, skill=717, hits=1)) for i in range(2)]   # dano refletido
ev += [(1000 + i * 500, fr.auto_attack(ME, BOSS, 3000000)) for i in range(121)]
ev += [(1000 + i * 1000, fr.auto_attack(EXE, BOSS, 3000000)) for i in range(61) if not 45 <= i <= 47]
ev += [(1000 + i * 1000, fr.auto_attack(FORA, BOSS, 3000000)) for i in range(50)]
ev += [(45000, fr.vanish(EXE)), (48500, fr.resurrect(EXE)), (50500, fr.vanish(FORA)), (54500, fr.resurrect(FORA)),
       (52000, fr.vanish(CARD)), (60000, fr.resurrect(CARD))]                # 8 s morto: provável wipe
c = combat_of(fr.build(ME, sorted(ev, key=lambda e: e[0]), player="Eu")[0], gap_ms=15000)
check(c.party == {EXE, CARD, MAG} and (48500, EXE) in c.res_log and len(c.res_log) == 3, "grupo pelo HP do grupo; ressurreição")
check([s for s in c.statuses(CARD) if s[1] == 15] == [(CARD, 15, 0, 30000)],
      "buff de antes da gravação aparece quando acaba (e o aviso repetido não duplica)")
fights = dd.boss_fights(c)
check(fights and fights[0]["key"] == BOSS and fights[0]["mvp"], "Dedo Duro: chefe MVP primeiro")
r = dd.analyze(c, BOSS)
al = {a["what"]: a for a in r["alerts"]}
o_al = {a["what"]: a for a in r["o_alerts"]}
check(sorted(p["name"] for p in r["party"]) == ["Card", "Eu", "Exec", "Mago"] and
      [p["name"] for p in r["others"]] == ["Fora"], "grupo e fora do grupo separados")
check(all("Fora" not in a["who"] + a["detail"] for a in r["alerts"]) and "Demorou para ressuscitar" in o_al,
      "quem está fora do grupo só aparece na lista de fora: %s" % list(o_al))
check(5000 < r["climax"] < 8000 and r["hp"] == 800000000 and r["hp_table"],
      "clímax depois de 10%% do HP (Nível 1, deduzido do dano): %d ms" % r["climax"])
check("Faltou Bênção" in al and "Exec" in al["Faltou Bênção"]["who"] and "Card" in al["Faltou Bênção"]["detail"],
      "faltou Bênção no Exec (o Cardeal está no grupo)")
check("Demorou para ressuscitar" in al and "3,5 s" in al["Demorou para ressuscitar"]["detail"],
      "mais de 2 s morto até ressuscitar")
check(al.get("Faltou Bênção", {}).get("sev") == 2 and al.get("Sem Aumentar Agilidade depois de morrer", {}).get("sev") == 1,
      "Bênção faltando antes da 1ª morte é grave; Agilidade não renovada depois de morrer é atenção")
rules = {min(r_.ids): r_ for r_ in dd.GROUP_BUFFS}
check(rules[1359].miss_sev() == 1 and rules[1359].absent_sev() == 1 and rules[1227].absent_sev() == 0
      and rules[24].miss_sev() == 2, "alvo único nunca é grave; Manejo Perfeito sim")
check(all(a["phase"] != "Luta" for a in r["alerts"]) and any(a["phase"] == "Luta inteira" for a in r["alerts"]),
      "alertas da luta toda dizem 'Luta inteira' (ou 'Todas as fases'), não 'Luta'")
card_death = next(d for d in r["deaths"] if d["name"] == "Card")
check("Card" not in al["Demorou para ressuscitar"]["who"] and "wipe" in card_death["back"] and not card_death["late"],
      "mais de 7 s morto = provável wipe, fora do relatório")
gap = r["claw"][0] if r["claw"] else {}
check(gap.get("start") == 22000 and gap.get("pain") and "Exec estava em recarga (40 s)" in gap.get("who", ""),
      "Garra Sombria: buraco com Dor Máxima e a recarga do Executor: %s" % gap.get("who"))
check(any(w.startswith("Garra Sombria") and a["sev"] == 2 for w, a in al.items())
      and "Dor Máxima refletiu sem Garra Sombria" in al,
      "Garra Sombria grave contra Dor Máxima")
check("Sem fogo no Florescer" in al and "Água" in al["Sem fogo no Florescer"]["detail"],
      "arma de água durante o Florescer")
mine = next(e for e in r["element"] if e["name"] == "Eu")
check(mine["fire"] == 1.0, "arma de fogo no Florescer: 100%")
check("Potencializar Veneno nunca apareceu no chefe" in al, "veneno na arma sem Potencializar Veneno no chefe")
pol = next((a for w, a in al.items() if w.startswith("Pólen")), {})
check("Mago estava com Clímax" in pol.get("detail", ""), "Pólen curto com o Clímax ativo: %s" % pol.get("detail"))
txt = dd.report_text(c, r)
head, _sep, tail = txt.partition("Fora do grupo:")
check("· Fora —" in tail and "· Fora —" not in head, "relatório separa quem está fora")

# --- Dedo Duro: bater antes da Garra Sombria e Elo Celestial -------------------------
SKY, SKY2, SKY3, EXE2, BOSS2 = 2101, 2102, 2103, 2104, 60002
ev = [(0, fr.spawn(SKY, "pc", 4302, "Ceu")), (0, fr.spawn(SKY2, "pc", 4302, "Nuvem")),
      (0, fr.spawn(SKY3, "pc", 4302, "Estrela")), (0, fr.spawn(EXE2, "pc", 4254, "Garra")),
      (0, fr.spawn(BOSS2, "mob", BETEL, "Betelgeuse", boss=2))]
ev += [(100, fr.party_hp(a, 50000, 50000)) for a in (SKY, SKY2, SKY3, EXE2)]
ev += [(500, fr.skill_use(SKY, SKY, dd.ELO_SKILL)),                       # Elo Celestial: some ao morrer
       (5000, fr.status(SKY3, dd.ELO, False)),                            # o Elo de antes da gravação acabou
       (1000, fr.status(BOSS2, dd.MAX_PAIN, True)), (3000, fr.status(BOSS2, dd.MAX_PAIN, False)),
       (3000, fr.skill_use(EXE2, BOSS2, 5001)), (3000, fr.status(BOSS2, dd.DARK_CLAW, True)),
       (60000, fr.status(BOSS2, dd.DARK_CLAW, False)),
       (1500, fr.skill_damage(SKY, BOSS2, 6000000)), (2500, fr.skill_damage(SKY, BOSS2, 6000000)),
       (2000, fr.skill_damage(SKY2, BOSS2, 1000000)), (10000, fr.skill_damage(SKY2, BOSS2, 15000000)),
       (30000, fr.vanish(SKY)), (40000, fr.resurrect(SKY))]
ev += [(3500 + i * 500, fr.skill_damage(a, BOSS2, 2000000)) for i in range(100) for a in (SKY, SKY2, SKY3)
       if not (a == SKY and 30000 <= 3500 + i * 500 < 40000)]
c2 = combat_of(fr.build(ME, sorted(ev, key=lambda e: e[0]), player="Eu")[0], gap_ms=15000)
r2 = dd.analyze(c2, BOSS2)
al2 = {a["what"]: a for a in r2["alerts"]}
early = al2.get("Atacou antes da Garra Sombria", {})
check(early.get("sev") == 2 and "Ceu 12,0M" in early.get("who", "") and "Nuvem" not in early.get("who", "")
      and "Dor Máxima no chefe desde 00:01,0" in early.get("detail", ""),
      "bateu forte antes da Garra Sombria (contra Dor Máxima): grave: %s · %s" % (early.get("who"), early.get("detail")))
elo = meter.skill_name(dd.ELO_SKILL)
forgot = al2.get("Faltou %s" % elo, {})
check(forgot.get("sev") == 2 and forgot.get("who", "").startswith("Estrela"),
      "%s acabou e não foi renovado: grave (%s)" % (elo, forgot.get("who")))
elo_rows = {b["name"]: b for b in r2["buffs"] if b["buff"] == elo}
check(not any("Ceu" in a["who"] for a in r2["alerts"] + r2["o_alerts"] if elo in a["what"])
      and elo_rows.get("Ceu", {}).get("p1") == "100%" and "1ª morte" in elo_rows.get("Ceu", {}).get("note", ""),
      "%s depois de morrer não é cobrado (sem AP): só conta até a 1ª morte" % elo)
check(not any("Nuvem" in a["who"] for a in r2["alerts"] if elo in a["what"]),
      "sem nenhum sinal do %s: desconhecido, não acusa" % elo)
check(len(elo_rows) == 3, "%s na tabela de buffs da classe" % elo)

# --- HP do chefe pela dificuldade (o replay não diz a dificuldade) ----------------
hp_of = lambda total, killed: an.boss_hp(c2, BOSS2, total, killed)[:2]
check(hp_of(844e6, True) == (800000000, "Nível 1") and hp_of(480e6, True) == (500000000, "Selado")
      and hp_of(300e6, False) == (800000000, "Nível 1") and hp_of(1041e6, False) == (1100000000, "Nível 2")
      and hp_of(805e6, False) == (800000000, "Nível 1"),
      "HP do Betelgeuse: morto, o nível do dano; vivo, o nível de costume ou o mínimo que comporta o dano")
regen = lambda total, killed, secs: an.boss_hp(c2, BOSS2, total, killed, secs * 1000)[1]
check(regen(1058e6, True, 300) == "Nível 1" and regen(924e6, False, 486) == "Nível 1"
      and regen(1041e6, False, 58) == "Nível 2",
      "dedução conta a regeneração do chefe: luta longa pede mais dano para o mesmo nível")
seen = c2.spawned.pop(BOSS2)              # como se a gravação começasse com o chefe já na tela
check(hp_of(580e6, True) == (800000000, "Nível 1") and an.caught_midway(c2, BOSS2),
      "gravação que pegou a luta no meio: o abate só diz o mínimo do HP")
c2.spawned[BOSS2] = seen
an.choose_hp(c2, BOSS2, 3)
check(hp_of(300e6, False) == (1400000000, "Nível 3") and dd.analyze(c2, BOSS2)["hp"] == 1400000000,
      "dificuldade escolhida na análise vale para o Dedo Duro")
an.choose_hp(c2, BOSS2, None)

# --- DPS ativo -------------------------------------------------------------------
check(meter.active_ms([0, 1000, 2000, 10000]) == 4000 and meter.active_ms([]) == 1000,
      "tempo batendo: pausas de mais de 5 s não contam, cada sequência ganha 1 s")
st = meter.Stat()
for t in (0, 1000, 2000, 10000):
    st.add(100, t)
check(st.active_ms() == 4000, "tempo batendo calculado na hora da leitura (%d)" % st.active_ms())
snap2 = c2.snapshot(session=True)
ceu = next(p for p in snap2["players"] if p["name"] == "Ceu")
check(ceu["adps"] > ceu["dps"] and ceu["active_ms"] < snap2["duration_ms"],
      "DPS ativo: sem o tempo morto, maior que o DPS em combate")

# --- linha do tempo ----------------------------------------------------------------
import timeline as tl  # noqa: E402
d2 = tl.build(c2, BOSS2)
lanes = {l["key"]: l for l in d2["lanes"]}
check(lanes["st%d" % dd.MAX_PAIN]["items"] == [(1000, 3000)] and lanes["st%d" % dd.DARK_CLAW]["on"],
      "linha do tempo: Dor Máxima e Garra Sombria como faixas no chefe")
check(d2["starts"] == [(0, None)] and "3,0 s depois do começo da fase" in early.get("detail", ""),
      "a luta começa quando o chefe aparece (não no 1º golpe): %s" % d2["starts"])
kinds = collections.Counter(e["kind"] for e in d2["events"])
check(kinds["death"] == 1 and kinds["res"] == 1 and kinds["claw"] == 1 and kinds["strong"] == 3 and kinds["elo"] == 1,
      "linha do tempo: morte, ressurreição, Garra, golpes fortes e Elo Celestial: %s" % dict(kinds))
status_ev = [e for e in d2["lane_events"] if e["lane"] == "st%d" % dd.DARK_CLAW]
check(status_ev and all(e["who"] == "" and e["what"].startswith("No chefe:") for e in status_ev),
      "linha do tempo: Garra Sombria é status no chefe, não skill do chefe -> %s" % [e["what"] for e in status_ev])
c3 = combat_of(fr.build(ME, sorted(ev + [(1500, fr.skill_use(0, ME, 28)),
                                         (1400, fr.status(ME, 1197, True, 30000, 30000, 1))],
                                   key=lambda e: e[0]), player="Eu")[0], gap_ms=15000)
d3 = tl.build(c3, BOSS2)
heal = [e for e in d3["events"] if e["t"] == 1500 and e["lane"] == "pskills"]
check(len(heal) == 1 and heal[0]["aid"] == ME and heal[0]["what"] == "recebeu cura de um efeito"
      and meter.skill_name(5269) in heal[0]["detail"] and not any(e.get("who") == "#0" for e in d3["events"]),
      "linha do tempo: cura sem autor vira 'recebeu cura' de quem tem o Mediale Votum -> %s" % heal)
marked = [e for e in d3["events"] + d3["lane_events"] if e["aid"] == ME or e.get("target") == ME]
check(not any(e["kind"] in ("boss", "status", "reflect") for e in marked),
      "linha do tempo: 'Jogadores marcados' não traz skills nem status do chefe")
ts2, vals = tl.series([(1000, 500), (1500, 500), (9000, 1000)], 0, 10000, 1000, 1000)
check(vals[1] == 1000.0 and vals[9] == 1000.0 and sum(vals) == 2000.0, "curva: dano por segundo por balde")

# --- fase de verdade: as armadilhas da fase 3 dizem que a fase 2 foi pulada ----
TRAP = 70001


def betel_phases(n_bosses, marker_before):
    """n_bosses fases do Betelgeuse (cada uma um monstro novo, ~11 s depois da anterior); a armadilha da fase 3
    (tipo 20351) reaparece 0,9 s antes do monstro de índice marker_before (None = nenhuma)."""
    ev = [(0, fr.spawn(TRAP, "npc", 20112, "#trap_1_0aa"))]
    for i in range(n_bosses):
        t0, aid = i * 16000, 61000 + i
        if marker_before == i:
            ev.append((t0 - 900, fr.spawn(TRAP, "npc", 20351, "#trap_1_0aa")))
            ev += [(t0 - 900 + k * 150, fr.spawn(TRAP, "npc", 20351, "#trap_1_0aa")) for k in range(1, 5)]
        ev += [(t0, fr.spawn(aid, "mob", BETEL, "Betelgeuse", boss=2)), (t0 + 500, fr.skill_damage(ME, aid, 1000)),
               (t0 + 4000, fr.skill_damage(ME, aid, 1000)), (t0 + 4500, fr.vanish(aid, 0))]
    c = combat_of(fr.build(ME, ev)[0])
    f = next(f for f in dd.boss_fights(c) if c.entities[f["key"]].job == BETEL)
    x = dd.Ctx(c, f["key"], None)
    return [x.phase_name(p) for p in x.phases], c


names, c = betel_phases(2, 1)
check(names == ["Fase 1", "Fase 3"], "fase 2 pulada: o 2º monstro é a fase 3 -> %s" % names)
check(len(c.phase_marks) == 1, "a armadilha andando repete o pacote, mas marca uma vez só -> %d" % len(c.phase_marks))
names, _c = betel_phases(3, 2)
check(names == ["Fase 1", "Fase 2", "Fase 3"], "três fases continuam 1, 2, 3 -> %s" % names)
names, _c = betel_phases(2, None)
check(names == ["Fase 1", "Fase 2"], "sem armadilha da fase 3, a ordem de sempre -> %s" % names)
names, _c = betel_phases(1, 0)
check(names == ["Fase 3"], "gravação que começa na fase 3 -> %s" % names)


def at(packet, x, y):
    """Põe a posição (PosDir) num 0x09fe do fake_replay."""
    p = bytearray(packet)
    p[63:66] = bytes([x >> 2, ((x & 3) << 6) | (y >> 4), (y & 0xF) << 4])
    return bytes(p)


# --- zona de risco: só na fase 3 do Betelgeuse --------------------------------
SAFE, RISKY, CORNER = 2101, 2102, 2103
ev = [(0, fr.spawn(TRAP, "npc", 20112, "#trap_1_0aa")), (0, at(fr.spawn(61000, "mob", BETEL, "Betelgeuse", boss=2), 156, 80)),
      (500, fr.skill_damage(ME, 61000, 1000)), (4500, fr.vanish(61000, 0)),
      (15100, fr.spawn(TRAP, "npc", 20351, "#trap_1_0aa")),
      (16000, at(fr.spawn(61001, "mob", BETEL, "Betelgeuse", boss=2), 156, 80)),
      (15000, at(fr.spawn(SAFE, "pc", 4302, "Segura"), 154, 79)), (15000, at(fr.spawn(RISKY, "pc", 4302, "Colada"), 156, 79)),
      (15000, at(fr.spawn(CORNER, "pc", 4256, "Canto"), 133, 70))]
ev += [(15000, fr.party_hp(a, 50000, 50000)) for a in (SAFE, RISKY, CORNER)]
ev += [(16500 + i * 500, fr.skill_damage(a, 61001, 1000)) for i in range(30) for a in (SAFE, RISKY)]
ev += [(18000, fr.effect(RISKY, rrf.EF_TRAP)), (19000, fr.effect(RISKY, rrf.EF_TRAP)), (18000, fr.effect(SAFE, rrf.EF_TRAP))]
c = combat_of(fr.build(ME, ev)[0])
f = next(f for f in dd.boss_fights(c) if c.entities[f["key"]].job == BETEL)
r = dd.analyze(c, f["key"])
rows = {x["name"]: x for x in r["risk"]}
check(r["risk_phase"] and rows["Colada"]["bad"] and rows["Colada"]["risk_hits"] == 2,
      "zona de risco: colada no Betel dá alerta e conta os 2 golpes -> %s" % rows.get("Colada"))
check(not rows["Segura"]["bad"] and rows["Segura"]["risk_ms"] == 0 and not rows["Canto"]["bad"],
      "zona de risco: 2 ← 1 ↓ e o canto esquerdo são seguros")
alert = [a for a in r["alerts"] if a["what"] == "Ficou na zona de risco das armadilhas"]
check(len(alert) == 1 and alert[0]["sev"] == 1 and alert[0]["phase"] == "Fase 3" and "Colada" in alert[0]["who"]
      and "Segura" not in alert[0]["who"], "zona de risco: alerta amarelo na fase 3 -> %s" % alert)
r1 = dd.analyze(*(lambda cc: (cc, next(f["key"] for f in dd.boss_fights(cc) if cc.entities[f["key"]].job == BETEL)))(
    betel_phases(2, None)[1]))
check(not r1["risk_phase"] and not r1["risk"], "zona de risco: sem a fase 3 não olha nada")

# --- golpes fortes fora da rajada dos outros DPS ------------------------------
DA, DB = 2201, 2202
ev = [(0, fr.spawn(61000, "mob", BETEL, "Betelgeuse", boss=2)), (0, fr.spawn(DA, "pc", 4302, "Sincronia")),
      (0, fr.spawn(DB, "pc", 4302, "Parceiro"))]
ev += [(100, fr.party_hp(a, 50000, 50000)) for a in (DA, DB)]
ev += [(1000 + i * 1000, fr.skill_damage(DA, 61000, 10000000, hits=1)) for i in range(20)]
ev += [(1100 + i * 1000, fr.skill_damage(DB, 61000, 10000000, hits=1)) for i in range(20)]
ev += [(22600, fr.skill_damage(DA, 61000, 10000000, hits=1)),     # 2,5 s depois do último golpe do parceiro
       (22900, fr.skill_damage(DA, 61000, 10000000, hits=1))]     # mesmo episódio
c = combat_of(fr.build(ME, ev)[0])
r = dd.analyze(c, 61000)
alert = [a for a in r["alerts"] if a["what"] == "Golpes fortes fora da rajada dos outros DPS"]
check(len(alert) == 1 and alert[0]["sev"] == 2 and alert[0]["who"] == "Sincronia 1×" and len(r["desync"]) == 1
      and r["desync"][0]["hits"] == 2, "assincronia: golpe forte sozinho, 2 golpes num episódio -> %s" % alert)

# --- Cinzas Vulcânicas: usadas, mas o status não aparece no chefe -------------
GEN, DIETER = 2301, 7301
ev = [(0, fr.spawn(61000, "mob", BETEL, "Betelgeuse", boss=2)), (0, fr.spawn(GEN, "pc", 4257, "Bioquimica")),
      (0, fr.spawn(DIETER, "homun", 6051, "Dieter", gid=GEN)), (100, fr.party_hp(GEN, 50000, 50000))]
ev += [(1000 + i * 1000, fr.skill_damage(ME, 61000, 10000000, hits=1)) for i in range(15)]
ev += [(3000, fr.cast(DIETER, 61000, 8043, 2000)), (9000, fr.cast(DIETER, 61000, 8043, 2000))]
c = combat_of(fr.build(ME, ev)[0])
r = dd.analyze(c, 61000)
row = next((d for d in r["debuffs"] if d["key"] == "deb|608"), None)
alert = [a for a in r["alerts"] if a["what"] == "Cinzas Vulcânicas não pegaram no chefe"]
check(row is not None and row["who"] == "Dieter (de Bioquimica)" and "2 uso(s)" in row["note"] and len(alert) == 1
      and alert[0]["sev"] == 0, "Cinzas Vulcânicas: linha nos debuffs e aviso de que não pegaram -> %s" % row)

# --- drops: caiu do monstro, quem pegou, entrou na bolsa ----------------------
import struct  # noqa: E402


def item_fall(map_id, item, x, y, count=1):
    return struct.pack("<HIIHBHHBBHBH", rrf.P_ITEM_FALL, map_id, item, 3, 1, x, y, 6, 6, count, 1, 0)


def pick_action(src, map_id):
    p = bytearray(29)
    struct.pack_into("<HII", p, 0, rrf.P_ACT_LEGACY, src, map_id)
    p[26] = 1                                            # ação 1: pegar item
    return bytes(p)


def pickup_ack(item, count=1):
    p = bytearray(70)
    struct.pack_into("<HHHI", p, 0, rrf.P_PICKUP, 10, count, item)
    return bytes(p)


ev = [(0, fr.spawn(50101, "mob", 1002, "Poring")), (500, fr.skill_damage(ME, 50101, 100)), (900, fr.vanish(50101, 1)),
      (1200, item_fall(900001, 607, 100, 100)), (1200, item_fall(900002, 909, 100, 101, 3)),
      (3000, pick_action(ME, 900001)), (3010, struct.pack("<HI", rrf.P_ITEM_GONE, 900001)), (3050, pickup_ack(607)),
      (4000, pick_action(OTHER, 900002)), (4010, struct.pack("<HI", rrf.P_ITEM_GONE, 900002)),
      (0, fr.spawn(OTHER, "pc", 4252, "Outro"))]
c = combat_of(fr.build(ME, ev)[0])
d1, d2 = c.drops
check(d1["mob"] == "Poring" and d1["mine"] and d1["by"] == ME and d2["by"] == OTHER and not d2["mine"],
      "drops: monstro, pego por você e pego por outro -> %s" % [(d["mob"], d["by"], d["mine"]) for d in c.drops])
summ = {r["item"]: r for r in c.drop_summary()}
check(summ[607]["fell"] == 1 and summ[607]["mine"] == 1 and summ[909]["fell"] == 3 and summ[909]["mine"] == 0,
      "drops: resumo por item -> %s" % list(summ.values()))

# --- quanto cada debuff rendeu (estimativa pela fórmula) ----------------------
import contrib  # noqa: E402
ev = [(0, fr.spawn(61000, "mob", BETEL, "Betelgeuse", boss=2)),
      (100, fr.status(61000, 1142, True, 30000, 30000, 1)), (100, fr.status(61000, 1183, True, 30000, 30000, 100)),
      (1000, fr.skill_damage(ME, 61000, 2500000, skill=2218, hits=1)),          # Tetra Vortex de fogo (mágico)
      (2000, fr.status(61000, 1142, False)), (2000, fr.status(61000, 1183, False)),
      (2500, fr.status(61000, 730, True, 20000, 20000, 150)),                   # Garra Sombria nv 5 (150%)
      (3000, fr.skill_damage(ME, 61000, 1750000, skill=5473, hits=1)),          # corpo a corpo físico
      (4000, fr.skill_damage(ME, 61000, 1000000, skill=2218, hits=1))]          # mágico: a Garra não vale
c = combat_of(fr.build(ME, ev)[0])
rows, total = contrib.fight(c, 61000)
got = {r["efst"]: round(r["contrib"]) for r in rows}
check(total == 5250000 and got.get(1183) == 1000000 and got.get(1142) == 500000 and got.get(730) == 750000,
      "contribuição: Pólen 100/250, Vício 50/250 do golpe de fogo; Garra 75/175 só no corpo a corpo -> %s" % got)
# Lex Aeterna em sequência: o jogo liga o status uma vez e só desliga no fim, mas cada uso dobra o próximo golpe
ev = [(0, fr.spawn(61000, "mob", BETEL, "Betelgeuse", boss=2)),
      (1000, fr.skill_use(OTHER, 61000, 78)), (1000, fr.status(61000, 22, True, 600000, 600000, 1)),
      (1100, fr.skill_damage(ME, 61000, 1000, skill=5473, hits=1)),
      (1300, fr.skill_use(OTHER, 61000, 78)), (1350, fr.skill_damage(ME, 61000, 3000, skill=5473, hits=1)),
      (1400, fr.skill_damage(ME, 61000, 5000, skill=5473, hits=1)),               # sem Lex: não dobra
      (1600, fr.skill_use(OTHER, 61000, 78)), (1650, fr.skill_damage(ME, 61000, 2000, skill=5473, hits=1)),
      (1650, fr.status(61000, 22, False)),
      (2000, fr.status(61000, 22, True, 600000, 600000, 1)), (2100, fr.status(61000, 22, False)),   # gasta fora da tela
      (2500, fr.skill_damage(ME, 61000, 7000, skill=5473, hits=1))]
c = combat_of(fr.build(ME, ev)[0])
rows, total = contrib.fight(c, 61000)
lex = next(r for r in rows if r["efst"] == contrib.LEX)
check(lex["hits"] == 3 and round(lex["contrib"]) == 3000 and lex["uptime"] is None,
      "Lex Aeterna: 3 usos seguidos dobram 3 golpes (metade de 1000+3000+2000); a que sumiu sem golpe visto não "
      "dobra o seguinte -> %d golpes, %s" % (lex["hits"], round(lex["contrib"])))
crows, ctotal = contrib.credit(c, 61000)
cred = {r["aid"]: r for r in crows}
check(ctotal == 18000 and round(cred[OTHER]["total"]) == 3000 and round(cred[OTHER]["via"][contrib.LEX]) == 3000
      and round(cred[ME]["own"]) == 15000 and round(sum(r["total"] for r in crows)) == 18000,
      "dano creditado: quem pôs a Lex fica com o ganho dela (3000), quem bateu com o resto; soma 100%% -> %s"
      % {k: round(v["total"]) for k, v in cred.items()})

# --- visual de quem gravou (sprites do jogo) ------------------------------------
import sprites  # noqa: E402
import types  # noqa: E402


def spr_bytes(w, h, idx, colors):
    """.spr 0x200 (sem compressão) com uma imagem indexada e a paleta {índice: (r, g, b)}."""
    pal = bytearray(1024)
    for k, rgb in colors.items():
        pal[k * 4:k * 4 + 3] = bytes(rgb)
    return b"SP" + bytes((0, 2)) + struct.pack("<HHHH", 1, 0, w, h) + bytes(idx) + bytes(pal)


def act_bytes(layer_xy, anchor, delay=4.0):
    """.act 0x203 com uma ação de um quadro: uma camada (imagem 0) e uma âncora."""
    d = b"AC" + bytes((3, 2)) + struct.pack("<H", 1) + bytes(10)
    d += struct.pack("<I", 1) + bytes(32) + struct.pack("<I", 1)
    d += struct.pack("<iiii", layer_xy[0], layer_xy[1], 0, 0) + bytes((255, 255, 255, 255))
    d += struct.pack("<f", 1.0) + struct.pack("<ii", 0, 0) + struct.pack("<i", -1)
    d += struct.pack("<i", 1) + struct.pack("<iiii", 0, anchor[0], anchor[1], 0)
    return d + struct.pack("<i", 0) + struct.pack("<f", delay)


RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)
body = sprites.Part("corpo", sprites.Sprite(spr_bytes(2, 2, [1] * 4, {1: RED})),
                    sprites.Act(act_bytes((0, -1), (0, -10))), anchored=False)
head = sprites.Part("cabeça", sprites.Sprite(spr_bytes(2, 2, [1] * 4, {1: GREEN})), sprites.Act(act_bytes((0, 0), (0, 2))))
w_, h_, px, ox, oy = sprites.compose([body, head], body, sprites.IDLE, 0, 0)
check((w_, h_, ox, oy) == (2, 13, 1, 13) and px[0][:3] == GREEN and px[12 * 2][:3] == RED and px[5 * 2][3] == 0,
      "sprite: cabeça presa na âncora do corpo (12 px acima), corpo no pé -> %s" % ((w_, h_, ox, oy),))
check(body.act.delays == [100.0] and body.act.actions[0][0][1] == [(0, -10)], "sprite: .act com âncora e tempo do quadro")
blue_pal = bytes(4) + bytes(BLUE) + bytes(1020 - 3)
body2 = sprites.Part("corpo", body.spr, body.act, blue_pal, anchored=False)
px2 = sprites.compose([body2], body2, sprites.IDLE, 0, 0)[2]
check(px2[0][:3] == BLUE, "sprite: paleta de cor de roupa troca a do arquivo")
with tempfile.TemporaryDirectory() as tmp:
    gp = os.path.join(tmp, "data.grf")
    base = sprites.HUMAN + "몸통\\남\\sky_emperor_남"
    fr.build_grf(gp, {base + ".spr": spr_bytes(2, 2, [1] * 4, {1: RED}), base + ".act": act_bytes((0, -1), (0, -10)),
                      sprites.HUMAN + "머리통\\남\\22_남.spr": spr_bytes(2, 2, [1] * 4, {1: GREEN}),
                      sprites.HUMAN + "머리통\\남\\22_남.act": act_bytes((0, 0), (0, 2))})
    wd = sprites.Wardrobe(gp)
    r = wd.render(dict(job=4302, sex=1, hair=22, top=1677), sprites.WALK, 3)
    check(r is not None and r[:2] == (2, 13) and r[7] == ["top"],
          "sprite: guarda-roupa lê corpo e cabeça do .grf; chapéu sem tabela fica como faltando -> %s" % (r and r[7]))
it = rrf.Item
worn = {1024: it(1, 31368), 256: it(2, 400242), 512: it(2, 400242), 2: it(3, 540045), 4: it(4, 480926)}
look = sprites.look_at(dict(job=4302, top=5, mid=7, low=9, robe=260), worn, {31368: 1677, 400242: 2220, 540045: 15})
check((look["top"], look["mid"], look["low"], look["robe"], look["weapon"]) == (1677, 2220, 0, 0, 540045),
      "visual no momento: visual vale mais que o normal, item sem ClassNum some -> %s" % look)
a, b, sh = it(3, 1), it(4, 2), it(5, 3)
fake = types.SimpleNamespace(equip_log=[(0, {2: a}), (5000, {2: b}), (6000, {2: b, 32: sh}), (20000, {2: b, 32: sh})])
check(an.equip_moments(fake) == [(0, []), (6000, ["Arma", "Escudo"])],
      "equipamento: trocas em sequência viram um momento só -> %s" % an.equip_moments(fake))
data, _off = fr.build(ME, [], look=dict(hair=22, top=1677, mid=1792, low=2154, robe=260, cloth_color=3), sex=0)
s_ = rrf.Session(rrf.Header(data), data)
check(s_.look.get("hair") == 22 and s_.look.get("top") == 1677 and s_.look.get("sex") == 0 and s_.look.get("job") == 4302
      and s_.player == "Tester", "sessão: visual e sexo de quem grava -> %s" % s_.look)

# --- XP exata entre gravações (o jogo guarda a XP total no início de cada uma) ---
with tempfile.TemporaryDirectory() as tmp:
    def rec(name, date, exp, gid=7001):
        data, _off = fr.build(ME, [], date=date, xp=(gid, exp, 1000000))
        with open(os.path.join(tmp, name), "wb") as f:
            f.write(data)
        return os.path.join(tmp, name)
    a = rec("a.rrf", (2026, 11, 5, 15, 24, 22), 500000)
    rec("b.rrf", (2026, 11, 5, 15, 24, 49), 500379)
    rec("c.rrf", (2026, 11, 5, 16, 0, 0), 900000)
    rec("outro.rrf", (2026, 11, 5, 15, 24, 30), 1, gid=7002)
    s_a = rrf.read_session(a)
    nxt = meter.xp_after(a, s_a)
    check(nxt and nxt["gain"] == 379 and os.path.basename(nxt["path"]) == "b.rrf" and meter.level_progress(s_a) == 0.5,
          "XP: +379 até a próxima gravação do mesmo personagem; 50%% do nível -> %s" % nxt)

# --- XP estimada dos abates e fator calibrado com a gravação seguinte --------------
import xp as xpmod  # noqa: E402
check(xpmod.penalty(255 - 246) == 135 and xpmod.penalty(44 - 240) == 10 and xpmod.penalty(0) == 100,
      "XP: penalidade de nível (rAthena / Divine Pride)")
with tempfile.TemporaryDirectory() as tmp:
    ev = []
    for i, aid in enumerate((52001, 52002, 52003)):                       # 3 abates em 10 min (trecho que calibra)
        ev += [(i * 300000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 300000 + 300, fr.skill_damage(ME, aid, 5000)),
               (i * 300000 + 400, fr.vanish(aid, 1))]
    ev += [(620000, fr.spawn(52004, "mob", 1124, "Goblin")), (620100, fr.skill_damage(OTHER, 52004, 5000)),
           (620200, fr.vanish(52004, 1))]                                  # morto por outro: sem XP
    for name, date, exp, events in (("a.rrf", (2026, 11, 5, 19, 35, 0), 1000, ev),
                                    ("b.rrf", (2026, 11, 5, 19, 45, 40), 1000 + 306, [])):
        data, _off = fr.build(ME, events, date=date, xp=(7100, exp, 10 ** 9))
        with open(os.path.join(tmp, name), "wb") as f:
            f.write(data)
    rf = meter.ReplayFile(os.path.join(tmp, "a.rrf"))
    rf.poll(max_bytes=1 << 30)
    cfg = {}
    rows, unknown = xpmod.kills(rf.combat)
    f = xpmod.calibrate(rf.combat, cfg, meter.xp_after)
    est = xpmod.estimate(rf.combat, dict(cfg, xp_mode="medido"))
    check(len(rows) == 3 and unknown == 0 and rows[0]["xp"] == 34 and f == 3.0 and round(est["xp"]) == 306
          and est["source"][0] == "medido" and est["correction"] == 3.0,
          "XP: 3 Goblins a 10%% = 102, +306 na gravação seguinte = lista ×3 medida -> %s %s" % (f, est["source"]))
    check(xpmod.factor(rf.combat, {"xp_mode": "fixo", "xp_fixed": 200})[0] == 3.0, "XP: valor fixo +200% = ×3")
    eta, left = xpmod.time_to_level(rf.combat, {"xp_mode": "fixo", "xp_fixed": 200}, 1000.0)
    check(left == 10 ** 9 - 1000 - 306 and abs(eta - left / 1000.0 * 60000) < 1,
          "XP: tempo até o próximo nível = XP que falta ÷ XP por minuto -> %s" % xpmod.span_text(eta))
    est = xpmod.estimate(rf.combat, {"xp_bonuses": {"server": {"on": True, "pct": 100}}})
    check(round(est["xp"]) == 204 and est["source"][0] == "auto", "XP: pela lista, evento +100%% = ×2 -> %s" % est["xp"])
    check(abs(est["pct"] - 100.0 * est["xp"] / 10 ** 9) < 1e-9
          and xpmod.estimate(rf.combat, {}, (0, 30000))["kills_per_min"] is None,
          "XP: % do nível ao lado da XP; abates por minuto só com mais de 1 min")
    est = xpmod.estimate(rf.combat, {}, (0, 1200000))
    check(abs(est["kills_per_min"] - 0.15) < 1e-12 and abs(est["per_hour_pct"] - est["per_min_pct"] * 60) < 1e-12,
          "XP: 3 abates em 20 min = 0,15 por minuto; %% por hora = %% por minuto × 60 -> %s" % est["kills_per_min"])
    # gravação curta (30 s) não calibra: 30 s davam um fator 20% errado na sessão real
    short = [(i * 10000 + d, p) for i, aid in enumerate((52011, 52012, 52013)) for d, p in (
        (0, fr.spawn(aid, "mob", 1124, "Goblin")), (300, fr.skill_damage(ME, aid, 5000)), (400, fr.vanish(aid, 1)))]
    for name, date, exp, events in (("c.rrf", (2026, 11, 5, 20, 0, 0), 1000, short),
                                    ("d.rrf", (2026, 11, 5, 20, 0, 40), 1500, [])):
        data, _off = fr.build(ME, events, date=date, xp=(7100, exp, 10 ** 9))
        with open(os.path.join(tmp, name), "wb") as f:
            f.write(data)
    rc = meter.ReplayFile(os.path.join(tmp, "c.rrf"))
    rc.poll(max_bytes=1 << 30)
    check(xpmod.calibrate(rc.combat, cfg, meter.xp_after) is None and len(cfg["xp_corr"]["7100"]["samples"]) == 1,
          "XP: gravação de 30 s não entra na calibração")
    rb = rrf.read_session(os.path.join(tmp, "b.rrf"))
    before = xpmod.recordings_before(os.path.join(tmp, "b.rrf"), rb)
    check([os.path.basename(r["path"]) for r in before] == ["a.rrf"],
          "XP: comparar com a gravação anterior do mesmo personagem -> %s" % before)

# --- Aquila: dificuldade pela redução de dano, regeneração só em sobrecarga e a quebra de defesa ------------
AQ = 52400
ev = [(0, fr.spawn(AQ, "mob", 21531, "Aquila", boss=True)), (50, fr.status(AQ, 1166, True, 0, 0, 50)),
      (1000, fr.skill_damage(ME, AQ, 100000000)),
      (2000, struct.pack("<HIBI", rrf.P_SPRITE, AQ, 0, 21588)),                  # entrou em sobrecarga
      (12000, struct.pack("<HIBI", rrf.P_SPRITE, AQ, 0, 21531)),                 # saiu: 10 s regenerando
      (13000, fr.skill_use(AQ, AQ, 2218)), (13200, fr.skill_use(AQ, AQ, 2220)),  # quebra de defesa
      (14000, fr.skill_damage(ME, AQ, 1000000))]
ca = combat_of(fr.build(ME, ev)[0])
xa = dd.Ctx(ca, AQ, None)
wins = an.form_windows(ca, xa.boss_aids, 21588, xa.start, xa.end)
hid = an.hidden_hits(ca, xa.boss_aids, (2218, 2219, 2220, 2221), xa.start, xa.end)
curve = tl.build(ca, AQ)["hp"]
end = curve[-1][1]
# 500M - 100M = 80%; +10 s × 0,55% = 85,5%; quebra -4,5% = 81%; -1M = 80,8%
check(xa.hp == 500000000 and xa.hp_label == "Executiva" and wins == [(2000, 12000)] and hid == [13000]
      and abs(end - (0.8 + 0.055 - 0.045 - 0.002)) < 1e-6,
      "Aquila: Executiva pela redução de 50%%; regenera 0,55%%/s só em sobrecarga e a quebra de defesa tira 4,5%% -> %.4f" % end)
m = an.BOSS_MODEL[21531]
check([an.boss_regen(m, 21531, hp) for hp in (300000000, 500000000, 600000000, 123)] == [0.0055, 0.0055, 0.011, 0.0055],
      "Aquila: regeneração por dificuldade (Econômica e Executiva 0,55%/s, Primeira Classe 1,1%/s)")
ba = sorted(ca.boss_alerts.values(), key=lambda b: b["t"])
BAPHO = 52403
ev4 = [(0, fr.spawn(BAPHO, "mob", 1039, "Baphomet", boss=True)), (500, fr.skill_damage(ME, BAPHO, 1000)),
       (2000, struct.pack("<HIBI", rrf.P_SPRITE, BAPHO, 0, 1038))]
bb = sorted(combat_of(fr.build(ME, ev4)[0]).boss_alerts.values(), key=lambda b: b["t"])
check(not [b for b in ba if b["size"]] and [(b["t"], b["size"], b["prev_size"]) for b in bb] == [(2000, "M", "L")],
      "aviso de chefe: Aquila continua grande na sobrecarga (sem aviso); chefe que vira forma média avisa -> %s %s" % (
          ba, bb))
ev2 = [(0, fr.spawn(AQ, "mob", 21531, "Aquila", boss=True)), (500, fr.skill_damage(ME, AQ, 1000)),
       (1000, fr.skill_use(AQ, AQ, 167)), (3000, fr.status(AQ, 1022, True, 30000, 30000)),
       (3500, fr.status(AQ, 1022, True, 30000, 29500))]                     # o mesmo status de novo: um aviso só
cb = combat_of(fr.build(ME, ev2)[0])
ba = sorted(cb.boss_alerts.values(), key=lambda b: b["t"])
best, avoid = an.element_advice("Holy")
check([(b["element"], b["immune"]) for b in ba] == [("Holy", None), (None, "Holy")]
      and [a for a, p in best] == ["Dark", "Undead"] and avoid == [("Holy", 0)]
      and any(a[3] == "Aquila virou Sagrado" for a in cb.alerts),
      "aviso de chefe: virou Sagrado (bata com Sombrio/Maldito 125%%, evite Sagrado 0%%) e ficou imune -> %s %s" % (
          [(b["element"], b["immune"]) for b in ba], best))
PAT, MINI = 52401, 52402
ev3 = [(0, fr.spawn(PAT, "mob", 20639, "2 Zone Patrol#1")), (0, fr.spawn(MINI, "mob", 1002, "Poring", boss=1)),
       (500, fr.skill_damage(ME, PAT, 1000)), (1000, fr.skill_use(PAT, PAT, 168)), (1500, fr.skill_use(MINI, MINI, 167)),
       (2000, fr.status(PAT, 1023, True, 30000, 30000))]
cp = combat_of(fr.build(ME, ev3)[0])
check(not cp.boss_alerts and not any(a[2] == "boss" for a in cp.alerts),
      "aviso de chefe: patrulha da Aeronave (1,9M de HP) e chefe menor trocando de propriedade não avisam -> %s" % (
          cp.boss_alerts,))

# --- subida de nível no meio da gravação: ponto exato, correção na hora e a XP do nível novo pela tabela ---
check(xpmod.table_need(4302, 244) == 99691521069 and xpmod.table_need(4302, 248) == 220850071960
      and xpmod.table_need(4302, 250) is None and xpmod.table_need(4060, 244) is None,
      "XP: tabela das classes 4 do LATAM (×1,22 por nível; conferida com os replays)")
ev = []
for i, aid in enumerate((52201, 52202, 52203, 52204, 52205)):
    ev += [(i * 60000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 60000 + 300, fr.skill_damage(ME, aid, 5000)),
           (i * 60000 + 400, fr.vanish(aid, 1))]
    if i == 2:
        ev.append((i * 60000 + 500, fr.hp(241, rrf.SP_BASELEVEL)))      # subiu do 240 para o 241
data, _off = fr.build(ME, ev, xp=(7200, 1000 - 204, 1000))               # faltavam 204 de XP no nível 240
cl = combat_of(data)
cfg_l = {"xp_mode": "medido"}
sc = xpmod.session_correction(cl, cfg_l)
pr = xpmod.progress(cl, cfg_l)
check(cl.level_ups and cl.level_ups[0][1] == 241 and sc and abs(sc[0] - 2.0) < 1e-9 and pr["level"] == 241
      and pr["need"] == xpmod.table_need(4302, 241) and abs(pr["xp"] - 2 * 68) < 1e-6,
      "XP: subida de nível = ponto exato (3 Goblins = 102 pela lista, faltavam 204 -> ×2); depois dela conta do zero "
      "no 241 -> %s %s" % (sc, pr and (pr["level"], round(pr["xp"]))))

ev = []
for i, aid in enumerate((52301, 52302, 52303)):                           # 3 abates no 1º minuto de farm
    ev += [(60000 + i * 20000, fr.spawn(aid, "mob", 1124, "Goblin")), (60000 + i * 20000 + 300, fr.skill_damage(ME, aid, 5000)),
           (60000 + i * 20000 + 400, fr.vanish(aid, 1))]
cw = combat_of(fr.build(ME, ev, xp=(7300, 1000, 10 ** 9))[0])
check(xpmod.warming_up(cw, {}) and xpmod.time_to_level(cw, {}) == (None, None) and xpmod.farm_start(cw) == 60400,
      "XP: sem previsão antes de 10 min de farm ou 1% do nível (o começo costuma ser preparação)")

c0 = combat_of(fr.build(ME, [(0, fr.spawn(52100, "mob", 21539, "Rgan")), (300, fr.skill_damage(ME, 52100, 5000)),
                             (400, fr.vanish(52100, 1)), (500, fr.spawn(52101, "mob", 3445, "Esqueleto")),
                             (600, fr.skill_damage(ME, 52101, 5000)), (700, fr.vanish(52101, 1))])[0])
rows0, unknown0 = xpmod.kills(c0)
check(unknown0 == 0 and [r["xp"] for r in rows0] == [729743 * 125 // 100, 0],      # nível 240 x 253: 125%
      "XP: monstro do episódio 19 com XP do Divine Pride; o que não dá XP conta como 0, não como desconhecido -> %s"
      % [r["xp"] for r in rows0])
check([xpmod.span_text(m * 60000) for m in (45, 200, 6000)] == ["45 min", "3 h 20 min", "4 dias 4 h"],
      "XP: tempo em palavras (min, h, dias)")
wins = {"vip": [(0, 100, 0)], "manual": [(0, 100, 0)], "njord": [(50, 100, 60)]}
sets = xpmod.settings({"xp_bonuses": {"server": {"on": True}, "manual": {"pct": 200}}})
check(xpmod.bonus_at(10, wins, sets) == 100 + 20 + 200 and xpmod.bonus_at(60, wins, sets) == 100 + 20 + 200 + 60
      and abs(xpmod.factor_at(10, wins, sets) - (2.2 + 2.0)) < 1e-9
      and abs(xpmod.factor_at(60, wins, sets) - (2.2 * 1.6 + 2.0)) < 1e-9,
      "XP: o manual vale só enquanto ativo e soma por fora; o Njord (% do status) multiplica o grupo do evento")
# fatores medidos abate a abate com a XP exata do jogo (evento 100, VIP 20, Cetro 30, Kafra 50; itens 15, Njord 60,
# Milagre, manual de 100%)
xp_all = {"vip": [(0, 999, 0)], "scepter": [(0, 999, 0)], "kafra": [(0, 999, 0)], "gear": [(100, 999, 15)],
        "njord": [(200, 999, 60)], "miracle": [(300, 999, 0)], "manual": [(400, 999, 100)]}
setm = xpmod.settings({"xp_bonuses": {"server": {"on": True, "pct": 100}}})
xp_got = [round(xpmod.factor_at(t, xp_all, setm), 4) for t in (50, 150, 250, 350, 450)]
xp_got2 = [round(xpmod.factor_at(t, dict(xp_all, njord=[]), setm), 4) for t in (350, 450)]
check(xp_got == [3.0, 3.375, 4.875, 9.75, 11.75] and xp_got2 == [6.75, 8.75],
      "XP: fatores medidos com a XP exata (3,000 · itens 3,375 · Njord 4,875 · Milagre 9,75 · manual 11,75; sem "
      "Njord 6,75 e 8,75) -> %s %s" % (xp_got, xp_got2))


# alvo da Oposição: Solar nos dias pares, Lunar nos ímpares, Estelar nos múltiplos de 5; com Milagre não soma
class _Ses:
    recorded_at = (2026, 11, 11, 0, 31, 56)


class _Marked:
    session = _Ses()
    hate_marks = [(1000, 0, 20179, False), (2000, 1, 20177, False), (3000, 2, 20175, True)]


def _mark_gain(mob, t=5000, w=None):
    w = w or {"vip": [(0, 10 ** 9, 0)]}
    return round(xpmod.factor_at(t, w, setm, mob, xpmod.marks_of(_Marked())) / xpmod.factor_at(t, w, setm), 3)


xp_day11 = [_mark_gain(20179), _mark_gain(20177), _mark_gain(20175), _mark_gain(20177, 1500)]
xp_mir = _mark_gain(20177, 5000, {"vip": [(0, 10 ** 9, 0)], "miracle": [(0, 10 ** 9, 0)]})
_Ses.recorded_at = (2026, 11, 10, 12, 0, 0)
xp_day10 = [_mark_gain(20179), _mark_gain(20177), _mark_gain(20175), _mark_gain(20175, 500)]
_Ses.recorded_at = (2026, 11, 10, 23, 59, 30)
xp_midnight = _mark_gain(20177, 60000)
check(xp_day11 == [1.0, 1.5, 1.0, 1.0] and xp_mir == 1.0 and xp_day10 == [1.5, 1.0, 2.0, 2.0] and xp_midnight == 1.5,
      "XP: alvo da Oposição rende pelo dia do mês (dia 11: só o Lunar ×1,5; dia 10: Solar ×1,5 e Estelar ×2, que já "
      "estava marcado; virou meia-noite: Lunar) e não soma com o Milagre -> %s %s %s %s" % (xp_day11, xp_mir, xp_day10, xp_midnight))
xp_evq = [(0, fr.spawn(52500, "mob", 20177, "Jeniffer")), (1000, fr.skill_damage(ME, 52500, 1000)),
       (2000, struct.pack("<H24sIBB", rrf.P_STARSKILL, b"x", 20177, 1, 10)),
       (2500, struct.pack("<H24sIBB", rrf.P_STARSKILL, b"", 0, 0, 0)),             # Sensação: não é marca
       (3000, struct.pack("<HI", rrf.P_QUEST_DONE, 5964))]
xp_cq = combat_of(fr.build(ME, xp_evq)[0])
check(xp_cq.hate_marks == [(2000, 1, 20177, False)] and xp_cq.quests_done == [(3000, 5964)]
      and xpmod.quest_in(xp_cq, 0, 5000) and not xpmod.quest_in(xp_cq, 3500, 9000),
      "XP: a gravação guarda o alvo da Oposição e a missão entregue; trecho com entrega não calibra -> %s %s" % (
          xp_cq.hate_marks, xp_cq.quests_done))
sets2 = xpmod.settings({"xp_bonuses": {"manual": {"pct": 50}}})
xpmod.BONUSES.append(dict(key="_teste", name="x", pct=100, status=1, on=True, group="consumível"))
sets2 = xpmod.settings({"xp_bonuses": {"manual": {"pct": 50}}})
check(xpmod.bonus_at(10, {"manual": [(0, 100, 0)], "_teste": [(0, 100, 0)], "vip": []}, sets2) == 100,
      "XP: dois consumíveis ativos não somam (vale o maior)")
xpmod.BONUSES.pop()
# Milagre multiplica o total dos outros bônus (replay de 89 min: 14,48% estimado x 14,49% real)
wins = {"vip": [(0, 100, 0)], "kafra": [(0, 100, 0)], "manual": [(0, 100, 0)], "miracle": [(50, 100, 0)]}
sets = xpmod.settings({"xp_bonuses": {"server": {"on": True, "pct": 100}}})
check(abs(xpmod.factor_at(10, wins, sets) - 3.2) < 1e-9 and abs(xpmod.factor_at(60, wins, sets) - 6.4) < 1e-9
      and xpmod.bonus_at(60, wins, sets) == 220,
      "XP: Milagre +100%% dobra o total dos outros (1 + 2,2 = ×3,2 -> ×6,4) -> %s" % xpmod.factor_at(60, wins, sets))
# o manual traz o % no status; sem o valor (já ativo no início da gravação) vale o digitado
wins = {"manual": [(0, 100, 0), (40, 100, 100)]}
sets = xpmod.settings({"xp_bonuses": {"manual": {"pct": 50}}})
check(xpmod.bonus_at(10, wins, sets) == 50 and xpmod.bonus_at(60, wins, sets) == 100,
      "XP: manual com o %% do status do jogo; sem valor, o digitado")

# --- áreas no chão do Mestre Elemental: Vulcão, Insígnia da Terra, Ganbantein, Prisão de Teia ---------
EM, ABOSS, AHIT = 2401, 61000, 1020000


def area_fight(areas=True, em_job=4261):
    """Quem grava bate com fogo (20 golpes, 1 por segundo) num chefe parado em (100, 100), de (100, 95). Com
    `areas`: Vulcão nv 5 (3×3 células) sob quem grava de 0,5 a 9 s, apagado pelo Ganbantein do chefe; Insígnia da
    Terra nv 3 (1 célula, raio 1) sob o chefe de 5,5 a 14,5 s; e uma Prisão de Teia que não pega."""
    ev = [(0, at(fr.spawn(ABOSS, "mob", 1038, "Chefe", boss=2), 100, 100)),      # sem tabela de HP: HP = dano total
          (0, fr.spawn(EM, "pc", em_job, "Elementa")), (100, fr.party_hp(EM, 50000, 50000)), (0, fr.stop(ME, 100, 95))]
    ev += [(1000 + i * 1000, fr.skill_damage(ME, ABOSS, AHIT, skill=2218, hits=1)) for i in range(20)]
    if areas:
        ev += [(500, fr.ground_skill(EM, 285, 5, 100, 95)), (550, fr.ground_skill(EM, 285, 5, 100, 95))]   # repetido
        ev += [(500, fr.ground_area(8000 + i, EM, 99 + i % 3, 94 + i // 3, 0x9A, 5)) for i in range(9)]
        ev += [(600, fr.ground_area(8000, EM, 99, 94, 0x9A, 5))]                                           # repetido
        ev += [(3000, fr.ground_skill(EM, 405, 5, 100, 100))]
        ev += [(5500, fr.ground_skill(EM, 2468, 3, 100, 101)), (5500, fr.ground_area(8100, EM, 100, 101, 0xF4, 3, 1)),
               (14500, fr.ground_gone(8100))]
        ev += [(9000, fr.ground_skill(ABOSS, 483, 65535, 100, 95))] + [(9000, fr.ground_gone(8000 + i)) for i in range(9)]
    ev += [(20500, fr.vanish(ABOSS, 1))]
    return combat_of(fr.build(ME, sorted(ev, key=lambda e: e[0]))[0])


ca = area_fight()
vul, ins = [a for a in ca.areas if a["skill"] == 285], [a for a in ca.areas if a["skill"] == 2468]
check(len(ca.areas) == 2 and len(vul[0]["units"]) == 9 and vul[0]["level"] == 5 and vul[0]["src"] == EM
      and ca.area_spans(vul[0]) == [(500, 9000)] and ca.area_spans(ins[0]) == [(5500, 14500)],
      "áreas no chão: um Vulcão de 9 células e uma Insígnia, com começo e fim -> %s" % [
          (a["skill"], len(a["units"]), ca.area_spans(a)) for a in ca.areas])
check(ca.in_area(vul[0], (101, 96), 8999) and not ca.in_area(vul[0], (101, 96), 9000)
      and not ca.in_area(vul[0], (102, 96), 5000) and ca.in_area(ins[0], (100, 100), 6000)
      and not ca.in_area(ins[0], (100, 99), 6000) and not ca.in_area(ins[0], None, 6000),
      "áreas no chão: dentro só nas células (e no raio) enquanto estão no chão")
check(len([u for u in ca.uses if u[4] == 285]) == 1 and [u[3] for u in ca.uses if u[4] in (285, 2468, 483)] == [0, 0, 0],
      "skill usada numa célula vira uso (sem alvo), sem contar a repetição -> %s" % [u for u in ca.uses if u[3] == 0])
rows, total = contrib.fight(ca, ABOSS)
by = {r["key"]: r for r in rows}
# Vulcão só (golpes 1-5): 20/120; os dois (6-8): 20/170 e 50/170; Insígnia só (9-14): 50/150
check(total == 20 * AHIT and round(by[-285]["contrib"]) == 1210000 and round(by[-2468]["contrib"]) == 2940000
      and by[-285]["where"] == "me" and by[-2468]["where"] == "boss" and by[-285]["hits"] == 8 and by[-2468]["hits"] == 9
      and by[-285]["name"] == "Vulcão" and "+20%" in by[-285]["rule"] and "+50%" in by[-2468]["rule"],
      "áreas no chão: Vulcão +20%% para quem bate de dentro e Insígnia +50%% no chefe em cima dela -> %s" % {
          k: (round(r["contrib"]), r["hits"]) for k, r in by.items() if r["contrib"]})
check(by[contrib.WEB]["contrib"] == 0 and "não apareceu no chefe" in by[contrib.WEB]["rule"] and 129 in meter.MOB_DEBUFFS,
      "Prisão de Teia: usada e sem status no chefe aparece na lista -> %s" % by.get(contrib.WEB))
crows, ctotal = contrib.credit(ca, ABOSS)
cby = {r["aid"]: r for r in crows}
check(ctotal == total and abs(sum(r["total"] for r in crows) - total) < 1 and round(cby[EM]["total"]) == 4150000
      and round(cby[EM]["via"][-285]) == 1210000 and round(cby[EM]["via"][-2468]) == 2940000
      and round(cby[ME]["own"]) == total - 4150000,
      "dano creditado: Vulcão e Insígnia vão para quem pôs a área -> %s" % {a: round(r["total"]) for a, r in cby.items()})
ra = dd.analyze(ca, ABOSS)
arows = {d["key"]: d for d in ra["debuffs"] if d["key"].startswith("area|")}
aal = {a["what"]: a for a in ra["alerts"]}
check(arows["area|285"]["p1"] == "37%" and arows["area|2468"]["p1"] == "47%" and arows["area|285"]["bad"]
      and arows["area|285"]["who"] == "Elementa" and "recarga 60 s" in arows["area|2468"]["note"],
      "Dedo Duro: Vulcão e Insígnia com o %% do dano de fogo coberto -> %s" % {k: v["p1"] for k, v in arows.items()})
check(aal.get("Vulcão durou pouco", {}).get("sev") == 1 and aal["Vulcão durou pouco"]["who"] == "Elementa"
      and "apagada por Ganbantein (Chefe)" in aal["Vulcão durou pouco"]["detail"]
      and aal.get("Insígnia da Terra durou pouco", {}).get("sev") == 1,
      "Dedo Duro: alerta amarelo de Vulcão e Insígnia, com o Ganbantein que apagou -> %s" % aal.get("Vulcão durou pouco"))
da = tl.build(ca, ABOSS)
alanes = {l["key"]: l for l in da["lanes"] if l.get("area")}
aev = [e for e in da["lane_events"] if e["kind"] == "area"]
check(alanes["ar285"]["items"] == [(500, 9000)] and alanes["ar2468"]["items"] == [(5500, 14500)] and alanes["ar285"]["on"]
      and any(e["what"] == "No chão: Vulcão acabou" and "apagada por Ganbantein" in e["detail"] and e["aid"] == EM
              for e in aev) and any(e["kind"] == "boss" and e["what"] == "Ganbantein" for e in da["events"]),
      "linha do tempo: faixas das áreas, quem pôs, o que apagou e o Ganbantein nas skills do chefe -> %s" % [
          (e["t"], e["what"], e["detail"]) for e in aev])
rb = dd.analyze(area_fight(areas=False), ABOSS)
bal = {a["what"]: a for a in rb["alerts"]}
check(bal.get("Vulcão faltou", {}).get("sev") == 1 and bal.get("Insígnia da Terra faltou", {}).get("sev") == 1
      and bal["Vulcão faltou"]["phase"] == "Luta inteira" and bal["Vulcão faltou"]["who"] == "Elementa",
      "Dedo Duro: com Mestre Elemental no grupo e dano de fogo, faltar Vulcão ou Insígnia é alerta amarelo -> %s" % (
          sorted(k for k in bal if "faltou" in k)))
rc = dd.analyze(area_fight(areas=False, em_job=4252), ABOSS)
check(not any(d["key"].startswith("area|") for d in rc["debuffs"])
      and not any("Vulcão" in a["what"] or "Insígnia" in a["what"] for a in rc["alerts"]),
      "Dedo Duro: sem quem ponha a área no grupo, nada é cobrado")
# em cima de quem o Ganbantein caiu (quem grava estava na célula) e o resumo no Dedo Duro
gan = next(e for e in da["events"] if e["kind"] == "boss" and e["what"] == "Ganbantein")
check(gan["detail"] == "em cima de Tester" and gan["target"] == ME
      and any("que caiu em Tester" in e["detail"] for e in aev if e["what"] == "No chão: Vulcão acabou")
      and "que caiu em Tester" in aal["Vulcão durou pouco"]["detail"],
      "Ganbantein: a linha do tempo e o alerta dizem em cima de quem caiu -> %s" % gan["detail"])
gal = aal.get("Ganbantein apagou áreas do grupo", {})
check(gal.get("sev") == 0 and gal.get("who") == "Tester 1×" and "1 vez(es)" in gal.get("detail", "")
      and "Vulcão 1×" in gal["detail"] and "Ganbantein apagou áreas do grupo" not in bal,
      "Dedo Duro: resumo do Ganbantein que apagou áreas, com em cima de quem caiu -> %s" % gal)
# rajada do chefe: células diferentes em menos de 200 ms são usos diferentes; a mesma célula repetida, não
ev = [(0, fr.spawn(ABOSS, "mob", 1038, "Chefe", boss=2)), (100, fr.ground_skill(ABOSS, 483, 65535, 10, 10)),
      (150, fr.ground_skill(ABOSS, 483, 65535, 10, 15)), (160, fr.ground_skill(ABOSS, 483, 65535, 10, 15))]
cg = combat_of(fr.build(ME, ev)[0])
check(len(cg.uses) == 2 and sorted(cg.ground_cells.values()) == [(10, 10), (10, 15)],
      "skill numa célula: rajada em células diferentes não é repetição -> %s" % cg.ground_cells)
# teleporte: a célula que volta logo depois nunca saiu do chão; a que não volta acabou ali
ev = [(1000, fr.ground_area(1, EM, 10, 10, 0x9A, 5)), (1000, fr.ground_area(2, EM, 11, 10, 0x9A, 5)),
      (2000, fr.map_move("prt_fild08", 10, 10)), (3000, fr.ground_area(1, EM, 10, 10, 0x9A, 5)), (9000, fr.stop(ME, 10, 10))]
cm = combat_of(fr.build(ME, ev)[0])
check(len(cm.areas) == 1 and cm.area_spans(cm.areas[0]) == [(1000, 9000)] and cm.in_area(cm.areas[0], (10, 10), 5000)
      and not cm.in_area(cm.areas[0], (11, 10), 5000),
      "áreas no chão: teleporte fecha as células, e a que reaparece segue no chão -> %s" % [a["units"] for a in cm.areas])

# --- Oposição no Dedo Duro: casa certa pelo tamanho do chefe (quem grava é Mestre Celestial) ----------
def hate_fight(level=None, start=70000):
    """Chefe médio (a casa certa é a Lunar, nível 2) apanhando de quem grava a partir de `start`."""
    ev = [(0, fr.spawn(ABOSS, "mob", 1038, "Chefe", boss=2))]
    if level:
        ev.append((start - 2000, fr.skill_use(ME, ABOSS, meter.HATE_SKILL, level)))
    ev += [(start + i * 1000, fr.skill_damage(ME, ABOSS, 1000000, hits=1)) for i in range(10)]
    ev += [(start + 10500, fr.vanish(ABOSS, 1))]
    cc = combat_of(fr.build(ME, sorted(ev, key=lambda e: e[0]))[0])
    return cc, {a["what"]: a for a in dd.analyze(cc, ABOSS)["alerts"]}


ch, hal = hate_fight()
check(hal.get("Oposição esquecida", {}).get("sev") == 2 and "Oposição Lunar" in hal["Oposição esquecida"]["detail"]
      and "médio" in hal["Oposição esquecida"]["detail"],
      "Oposição: bater no chefe sem marcar é grave -> %s" % hal.get("Oposição esquecida"))
ch, hal = hate_fight(level=3)
check(hal.get("Oposição errada", {}).get("sev") == 2 and "Oposição Estelar" in hal["Oposição errada"]["detail"]
      and "Oposição esquecida" not in hal and ch.hate_uses == [(68000, ME, ABOSS, 3)],
      "Oposição: casa errada para o tamanho é grave, e o uso guarda o nível -> %s" % hal.get("Oposição errada"))
ch, hal = hate_fight(level=2)
check("Oposição errada" not in hal and "Oposição esquecida" not in hal
      and any(e["what"] == "usou Oposição Lunar" for e in tl.build(ch, ABOSS)["events"]),
      "Oposição: a casa certa não dá alerta e a linha do tempo diz qual foi usada")
ch, hal = hate_fight(start=5000)
check(hal.get("Oposição esquecida", {}).get("sev") == 1 and "antes" in hal["Oposição esquecida"]["detail"],
      "Oposição: luta que começa junto com a gravação é só atenção (a marca pode ser de antes)")

# --- avisos de mecânica do chefe e fim da luta ---------------------------------------------------
AQ = 62000
ev = [(0, fr.spawn(ABOSS, "mob", 1038, "Chefe", boss=2)), (0, fr.spawn(AQ, "mob", 21531, "Aquila", boss=2)),
      (1000, fr.status(ABOSS, meter.MAX_PAIN_EFST, True, 10000, 10000, 1)),
      (1500, fr.status(ABOSS, meter.MAX_PAIN_EFST, True, 10000, 10000, 1)),     # renovou: não repete
      (6000, fr.status(ABOSS, meter.MAX_PAIN_EFST, False)),
      (7000, fr.status(AQ, meter.RELIEVE_EFST, True, 0, 0, 50)), (8000, fr.status(AQ, meter.RELIEVE_EFST, False)),
      (8000, fr.status(AQ, meter.RELIEVE_EFST, True, 0, 0, 99)),
      (12000, fr.skill_use(AQ, AQ, 2218)), (12100, fr.skill_use(AQ, AQ, 2220)),     # as duas juntas: um aviso só
      (13000, fr.skill_use(ABOSS, ABOSS, 2218)),                                    # outro chefe: não é quebra
      (14000, fr.skill_damage(ME, AQ, 5000000, hits=1)), (15000, fr.vanish(AQ, 1))]
cmx = combat_of(fr.build(ME, ev)[0])
mech = [(b["t"], b["aid"], b["mech"]) for b in sorted(cmx.boss_alerts.values(), key=lambda b: b["t"]) if b.get("mech")]
check(mech == [(1000, ABOSS, "maxpain_on"), (6000, ABOSS, "maxpain_off"), (8000, AQ, "defense"), (12000, AQ, "def_break")],
      "mecânicas: Dor Máxima liga e acaba, modo defesa (99%%) e defesa caída viram aviso -> %s" % mech)
check(list(cmx.fight_ends.values()) == [(AQ, 15000)] and any(a[2] == "bossdead" for a in cmx.alerts),
      "fim da luta: a morte do chefe fica anotada para o resumo -> %s" % cmx.fight_ends)

# Aliviar do chefe subindo com as Almas (30% sem nenhuma, +10% por Alma): avisa a partir de 90%, uma vez
ev = [(0, fr.spawn(ABOSS, "mob", 1038, "Chefe", boss=2))]
for i, val in enumerate((30, 40, 80, 90, 99, 90, 99, 80, 90)):
    ev += [(1000 + i * 1000, fr.status(ABOSS, meter.RELIEVE_EFST, False)),
           (1000 + i * 1000, fr.status(ABOSS, meter.RELIEVE_EFST, True, 0, 0, val))]
crl = combat_of(fr.build(ME, ev)[0])
rel = [(b["t"], b["mech"], b.get("pct"), b.get("souls"), b.get("more")) for b in sorted(crl.boss_alerts.values(),
                                                                                        key=lambda b: b["t"])]
check(rel == [(4000, "relief", 90, 6, False)] and any("Aliviar muito alto, 6 almas ativas" in a[3] for a in crl.alerts),
      "Aliviar muito alto: avisa ao passar de 90%% com o número de Almas, sem repetir a cada oscilação -> %s" % rel)

# --- mortes do Aquila: o golpe que matou, a explosão do Robovac e o golpe de fora da tela -----------
check(rrf.spawn_move(rrf.P_SPAWN_STAND, fr.spawn(MOB, "mob", 1002, "Poring", pos=(153, 155), stand=True))[1] == (153, 155)
      and rrf.spawn_move(rrf.P_SPAWN_IDLE, fr.spawn(MOB, "mob", 1002, "Poring", pos=(146, 161)))[1] == (146, 161)
      and rrf.parse_spawn(rrf.P_SPAWN_STAND, fr.spawn(MOB, "mob", 1002, "Poring", stand=True, boss=2)).boss == 2,
      "posição de quem aparece parado (0x09ff) e de quem nasce (0x09fe)")
REFLECT, CART, ROBO = meter.MAXPAIN_ATK, 153, 63000
base = [(0, fr.spawn(AQ, "mob", 21531, "Aquila", boss=2)), (100, fr.hp(100000, rrf.SP_MAXHP)), (110, fr.hp(100000))]
ev = base + [(5000, fr.skill_damage(ME, AQ, 1350000, hits=1)),
             (5000, fr.skill_damage(AQ, ME, 150000, skill=REFLECT, hits=1)),      # este mata (a vida cai ~1 s depois)
             (5400, fr.skill_damage(AQ, ME, 30000, skill=REFLECT, hits=1)),
             (5700, fr.skill_damage(AQ, ME, 2000, skill=CART, hits=1)),           # o último golpe, pequeno
             (6000, fr.vanish(ME, 1)), (9000, fr.status(AQ, meter.MAX_PAIN_EFST, False))]
ck = combat_of(fr.build(ME, ev)[0])
d = an.deaths(ck)[0]
card = an.death_card(ck, ME, 6000)
killg = next((g for g in card["sources"] if g["killing"]), {})
check(d["hit"] == 150000 and d["skill"] == meter.skill_name(REFLECT) and not d["unclear"] and d["overkill"] == 50000
      and killg.get("skill") == meter.skill_name(REFLECT) and (card["reflected"] or {}).get("dmg") == 1350000,
      "morte: vale o golpe que matou (reflexo de 150.000), não o último pequeno -> %s %s" % (d["skill"], d["hit"]))
mech = [(b["t"], b["mech"]) for b in sorted(ck.boss_alerts.values(), key=lambda b: b["t"]) if b.get("mech")]
check(mech == [(5000, "maxpain_on"), (9000, "maxpain_off")],
      "Dor Máxima usada fora da tela: o aviso sai no primeiro reflexo, uma vez, e fecha no fim -> %s" % mech)
ev = base + [(4990, fr.status(AQ, meter.MAX_PAIN_EFST, True, 10000, 10000, 1)),
             (5000, fr.skill_damage(AQ, ME, 500, skill=REFLECT, hits=1)),
             (5500, fr.skill_damage(AQ, ME, 500, skill=REFLECT, hits=1))]
ck = combat_of(fr.build(ME, ev)[0])
mech = [(b["t"], b["mech"]) for b in ck.boss_alerts.values() if b.get("mech")]
check(mech == [(4990, "maxpain_on")], "Dor Máxima vista pelo status: os reflexos não repetem o aviso -> %s" % mech)
ev = base + [(4500, fr.skill_damage(AQ, ME, 150000, skill=CART, hits=1)), (5800, fr.hp(90000)),   # viva 1,3 s depois
             (5900, fr.skill_damage(AQ, ME, 120000, skill=0, action=0)), (6000, fr.vanish(ME, 1))]
d = an.deaths(combat_of(fr.build(ME, ev)[0]))[0]
check(d["hit"] == 120000 and d["hp_before"] == 90000,
      "morte: golpe grande que não matou (a vítima aparece viva depois) não leva a culpa -> %s" % d["hit"])

robo = [(0, fr.spawn(ROBO, "mob", 20641, "Broken Robovac", pos=(150, 150))),
        (100, fr.hp(118000, rrf.SP_MAXHP)), (110, fr.hp(84646))]
ev = robo + [(0, fr.stop(ME, 153, 152)), (4000, fr.auto_attack(ROBO, ME, 3054)),
             (5000, fr.skill_use(ROBO, ROBO, meter.SELF_DESTRUCT)), (5000, fr.vanish(ROBO, 1)), (5000, fr.vanish(ME, 1))]
cb = combat_of(fr.build(ME, ev)[0])
d = an.deaths(cb)[0]
card = an.death_card(cb, ME, 5000)
killg = next((g for g in card["sources"] if g["killing"]), {})
boom = meter.skill_name(meter.SELF_DESTRUCT)
check(d["special"] == "boom" and d["skill"] == boom and "Broken Robovac" in d["killer"] and not d["no_hit"]
      and not d["unclear"] and d["hp_before"] == 84646 and cb.booms == [(5000, ROBO, (150, 150))]
      and killg.get("skill") == boom and card["sprite_mob"] == 20641
      and any(a[3].startswith("Você morreu: %s" % boom) for a in cb.alerts)
      and "sem número na tela" in tl.death_cause(d),
      "morte: a Autodestruição do Robovac colado vira a causa (não tem pacote de dano) -> %s" % tl.death_cause(d))
ev = robo + [(0, fr.stop(ME, 170, 170)), (5000, fr.skill_use(ROBO, ROBO, meter.SELF_DESTRUCT)), (5000, fr.vanish(ME, 1))]
d = an.deaths(combat_of(fr.build(ME, ev)[0]))[0]
check(d["special"] is None and d["no_hit"], "morte: explosão longe (20 células) não leva a culpa")

aq = [(0, fr.spawn(AQ, "mob", 21531, "Aquila", boss=2)), (100, fr.hp(118000, rrf.SP_MAXHP)), (110, fr.hp(111679)),
      (2000, fr.broadcast("ni0XDg"))]                                   # o éter amarelo acabou: sobrecarga
co = combat_of(fr.build(ME, aq + [(1000, fr.vanish(AQ, 0)), (32600, fr.vanish(ME, 1))])[0])
d = an.deaths(co)[0]
check(d["special"] == "offscreen" and d["overload_ms"] == 29600 and d["killer"].startswith("Aquila") and not d["no_hit"]
      and d["hp_before"] == 111679 and co.overloads == [[2000, None]] and co.in_sight(AQ, 31600) is False
      and "sobrecarga há 30 s" in tl.death_cause(d)
      and any("provável golpe de Aquila fora da tela" in a[3] for a in co.alerts),
      "morte: Aquila em sobrecarga e fora da tela vira a causa provável -> %s" % tl.death_cause(d))
d = an.deaths(combat_of(fr.build(ME, aq + [(32600, fr.vanish(ME, 1))])[0]))[0]
check(d["special"] is None and d["no_hit"], "morte: com o Aquila na tela, a morte sem golpe continua sem causa")
co = combat_of(fr.build(ME, aq + [(1000, fr.vanish(AQ, 0)), (20000, fr.broadcast("nS0XDg")), (32600, fr.vanish(ME, 1))])[0])
check(an.deaths(co)[0]["special"] is None and co.overloads == [[2000, 20000]] and co.overload_at(10000) == 8000
      and co.overload_at(25000) is None,
      "sobrecarga: os anúncios da sala abrem e fecham o período; fora dele o golpe de fora da tela não é palpite")

# --- nomes escondidos na imagem copiada e a imagem no formato da área de transferência ---------------
ev = [(0, fr.spawn(2501, "pc", 4252, "Fulano")), (0, fr.spawn(2502, "pc", 4252, "Beltrano")),
      (0, fr.spawn(2503, "pc", 4256, "Sicrano")), (0, fr.spawn(MOB, "mob", 1002, "Poring"))]
cn = combat_of(fr.build(ME, ev, player="Aria")[0])
meter.HIDE_NAMES = True
masked = [cn.name_of(a) for a in (2501, 2502, 2503, ME, MOB)]
meter.HIDE_NAMES = False
check(masked[0] != masked[1] and masked[0].endswith(" 1") and masked[1].endswith(" 2") and "Fulano" not in masked[0]
      and masked[2] == meter.job_name(4256) and masked[3] == meter.job_name(4302) and masked[4] == "Poring"
      and cn.name_of(2501) == "Fulano" and cn.name_of(ME) == "Aria",
      "copiar imagem sem nomes: cada jogador vira a classe (numerada se repete) -> %s" % masked)
import clipimg  # noqa: E402
px = bytes([1, 2, 3, 0, 4, 5, 6, 0, 7, 8, 9, 0, 10, 11, 12, 0])          # 2×2, de cima para baixo
blob = clipimg.dib(2, 2, px)
check(len(blob) == 40 + 16 and struct.unpack_from("<Iii", blob) == (40, 2, 2)
      and blob[40:] == bytes([7, 8, 9, 255, 10, 11, 12, 255, 1, 2, 3, 255, 4, 5, 6, 255])
      and clipimg.crop(2, 2, px, (1, 0, 2, 2)) == (1, 2, bytes([4, 5, 6, 0, 10, 11, 12, 0])),
      "copiar imagem: recorte e formato da área de transferência (de baixo para cima, opaco)")

# --- XP: missões (progresso da caça, entrega com manual e Kafra) e modo automático ------------------
ev = [(0, fr.status(ME, 250, True, 1800000, 1800000, 100)), (0, fr.status(ME, 1085, True, 600000000, 600000000, 0)),
      (1000, fr.quest_hunt([(5964, 59640, 1000, 640)])), (2000, fr.quest_hunt([(5964, 59640, 1000, 641), (7777, 1, 10, 3)])),
      (65000, fr.quest_done(5964)), (66000, fr.quest_done(4242)), (70000, fr.stop(ME, 1, 1))]
cq = combat_of(fr.build(ME, ev, xp=(7100, 0, 10 ** 12))[0])
hq = xpmod.hunts(cq)
eq0 = xpmod.estimate(cq, {})
check(eq0["quest_xp"] == 0 and eq0["xp"] == 0 and len(eq0["quests"]) == 2 and eq0["quests_unknown"] == 2
      and xpmod.quests_uncounted(cq, {}) == 2,
      "missões: a XP das entregas fica fora da conta (recurso desligado), mas as entregas são listadas e a tela avisa")
xpmod.QUEST_XP_ON = True                     # o mecanismo continua testado para quando a regra fechar
qr = xpmod.quest_rows(cq, {})
eq = xpmod.estimate(cq, {})
check([(h["quest"], h["parts"]) for h in hq] == [(7777, [(3, 10)])] and 5964 not in cq.quest_hunts,
      "missões: o progresso da caça aparece e some quando a missão é entregue -> %s" % hq)
check(qr[0]["mult"] == 2.5 and qr[0]["xp"] == 5586774400 and qr[1]["xp"] is None and eq["quest_xp"] == 5586774400
      and eq["xp"] == 5586774400 and eq["kill_xp"] == 0 and eq["quests_unknown"] == 1 and eq["per_min"] == 0,
      "missões: Jantar do Diabo com manual 100%% e Kafra rende ×2,5 (5.586.774.400), fora do ritmo dos abates -> %s"
      % [(q["quest"], q["mult"], q["xp"]) for q in qr])
check(xpmod.quest_base(4242, {"xp_quests": {"4242": {"base": 1000}}}) == 1000 and xpmod.quest_base(4242, {}) is None,
      "missões: a recompensa aprendida vale no lugar da tabela")
xpmod.QUEST_XP_ON = False
check(xpmod.factor(cq, {})[1][0] == "auto" and xpmod.factor(cq, {"xp_mode": "lista"})[1][0] == "lista",
      "XP: sem nada escolhido o modo é o automático (aproximado até haver medida)")
xpmod.MAX_AGE_S = None                       # nos testes as gravações são antigas
cfgm = {}
check(xpmod.remember_manual(cq, cfgm) and cfgm["xp_manual_last"] == {"7100": 100}
      and xpmod.settings(cfgm, cq)["manual"]["last"] == 100 and not xpmod.remember_manual(cq, cfgm),
      "XP: o %% do último manual visto fica guardado para o personagem -> %s" % cfgm)
wm = {"manual": [(0, 100, 0)]}
check(xpmod.bonus_at(10, wm, xpmod.settings(cfgm, cq)) == 100 and xpmod.bonus_at(10, wm, xpmod.settings({})) == 50,
      "XP: manual já ativo no começo usa o último %% visto, senão o digitado")
with tempfile.TemporaryDirectory() as tmp2:
    # 3 abates de 37 de XP pela lista sem evento (111); a gravação seguinte mostra +333 = ×3: evento de +200%
    ev = []
    for i, aid in enumerate((52001, 52002, 52003)):
        ev += [(i * 300000, fr.spawn(aid, "mob", 1122, "Goblin")), (i * 300000 + 200, fr.skill_damage(ME, aid, 5000)),
               (i * 300000 + 400, fr.vanish(aid, 1))]
    for name, date, exp, events in (("a.rrf", (2026, 11, 5, 19, 35, 0), 1000, ev),
                                    ("b.rrf", (2026, 11, 5, 19, 45, 40), 1000 + 333, [])):
        with open(os.path.join(tmp2, name), "wb") as f:
            f.write(fr.build(ME, events, date=date, xp=(7100, exp, 10 ** 9))[0])
    rfa = meter.ReplayFile(os.path.join(tmp2, "a.rrf"))
    rfa.poll(max_bytes=1 << 30)
    cfga = {}
    corr = xpmod.calibrate(rfa.combat, cfga, meter.xp_after)
    esta = xpmod.estimate(rfa.combat, cfga)
    check(cfga["xp_bonuses"]["server"] == {"on": True, "pct": 200, "auto": True} and corr == 1.0
          and round(esta["xp"]) == 333 and esta["source"][0] == "medido",
          "XP automática: o evento do servidor (+200%%) sai da XP exata e a lista fecha sozinha -> %s %s" % (
              cfga.get("xp_bonuses"), corr))
    cfgl = {"xp_mode": "lista"}
    xpmod.calibrate(rfa.combat, cfgl, meter.xp_after)
    check("xp_bonuses" not in cfgl, "XP: no modo \"pela lista\" o programa não mexe no evento do servidor")
xpmod.MAX_AGE_S = 24 * 3600

# --- Milagre Solar, Lunar e Estelar (status 160 de 1 hora, sem ícone) e bônus dos itens ----------------
ev = [(1000, fr.status(ME, 984, True, 2592000, 2592000, 0)),          # VIP
      (5000, fr.status(ME, meter.MIRACLE_EFST, True, 3600000, 3600000, 1)),
      (8000, fr.vanish(ME, 1)),                                            # morreu: VIP e Milagre continuam
      (20000, fr.skill_damage(ME, 77, 1))]
c = combat_of(fr.build(ME, ev)[0])
check(c.miracle_windows() == [(5000, c.now)] and any(a[2] == "miracle" for a in c.alerts)
      and c.lasting(984) == [(1000, c.now)],
      "Milagre: status 160 de 1 h vira o Milagre (com aviso); ele e o VIP não acabam com a morte -> %s" % c.miracle_windows())
def mapmove(name, x=100, y=100):
    return struct.pack("<H16sHH", rrf.P_MAPMOVE, name.encode() + b".gat", x, y)


ev = [(5000, fr.status(ME, meter.MIRACLE_EFST, True, 3600000, 3600000, 1)),
      (20000, fr.status(ME, meter.MIRACLE_EFST, True, 3600000, 3600000, 1)),     # proc de novo: mais 1 hora
      (20300, fr.status(ME, meter.MIRACLE_EFST, True, 3600000, 3600000, 1)),     # o mesmo proc repetido
      (30000, mapmove("prt_fild08")),                                            # teleporte no mesmo mapa
      (40000, mapmove("aldebaran")),                                             # outro mapa: segue, a confirmar
      (50000, fr.skill_damage(ME, 77, 1))]
c = combat_of(fr.build(ME, ev)[0])
check(c.miracle_windows() == [(5000, 50000)] and sum(a[2] == "miracle" for a in c.alerts) == 2
      and c.miracle_left() is not None and c.miracle_uncertain() == 40000,
      "Milagre: proc de novo renova (com aviso); outro mapa não tira, só deixa a confirmar -> %s %s"
      % (c.miracle_windows(), c.miracle_uncertain()))
c = combat_of(fr.build(ME, ev[:5] + [(45000, fr.status(ME, meter.MIRACLE_EFST, False)),
                                     (50000, fr.skill_damage(ME, 77, 1))])[0])
check(c.miracle_windows() == [(5000, 45000)] and c.miracle_left() is None,
      "Milagre: quando o jogo avisa que acabou, acaba -> %s" % c.miracle_windows())
c = combat_of(fr.build(ME, [(5000, fr.status(ME, meter.MIRACLE_EFST, True, 3600000, 3600000, 1)),
                            (8000, fr.vanish(ME, 1)), (9000, fr.status(ME, meter.MIRACLE_EFST, True, 3600000,
                                                                       3600000, 1)),
                            (12000, fr.skill_damage(ME, 77, 1))])[0])
check(c.miracle_uncertain() is None and c.miracle_windows() == [(5000, 12000)],
      "Milagre: depois de morrer fica a confirmar até um novo proc confirmar")
# 1.2.2: o rodapé travava em "1 min" quando a hora acabava (o jogo nunca manda o "acabou")
c = combat_of(fr.build(ME, [(5000, fr.status(ME, meter.MIRACLE_EFST, True, 3600000, 3600000, 1)),
                            (3606000, fr.skill_damage(ME, 77, 1))])[0])
check(c.miracle_left() is None and c.miracle_windows() == [(5000, 3605000)],
      "Milagre: 1 hora depois do último proc ele acaba e sai do rodapé -> %s" % c.miracle_windows())
c = combat_of(fr.build(ME, [(5000, fr.status(ME, meter.MIRACLE_EFST, True, 3600000, 3600000, 1)),
                            (3000000, fr.status(ME, meter.MIRACLE_EFST, True, 3600000, 3600000, 1)),
                            (3700000, fr.skill_damage(ME, 77, 1))])[0])
check(c.miracle_left() == 3000000 + 3600000 - 3700000,
      "Milagre: proc aos 50 min renova a hora (não trava no fim da primeira) -> %s" % c.miracle_left())
items = {31975: {"identifiedDisplayName": "Visual Batata-doce na Boca", "identifiedDescriptionName": {
            1: "[Durante o Evento]", 2: "EXP obtida por monstros +5%.", 3: "-", 4: "Conjunto",
            5: "[Visual] Chapéu do Festival da Colheita", 6: "Dano físico +10%.",
            7: "EXP obtida por monstros +5% adicional.", 8: "-", 9: "Conjunto", 10: "[Visual] Espetinhos",
            11: "EXP obtida por monstros +5% adicional.", 12: "--------------------------", 13: "Tipo: Visual"}},
         31368: {"identifiedDisplayName": "[Visual] Chapéu do Festival da Colheita"},
         300834: {"identifiedDisplayName": "Carta Baby Shark", "identifiedDescriptionName": {
             1: "EXP adquirida ao derrotar a raça Planta +10%.", 2: "EXP adquirida ao derrotar monstros +15%."}}}
table = xpmod.parse_gear(items)
names = {i: xpmod._norm(v["identifiedDisplayName"]) for i, v in items.items()}
worn = {4096: rrf.Item(1, 31975), 1024: rrf.Item(2, 31368), 4: rrf.Item(3, 480146, cards=(300834,))}
check(xpmod.gear_bonus(worn, True, table, names)[0] == 5 + 5 + 15 and xpmod.gear_bonus(worn, False, table, names)[0] == 15,
      "XP dos itens: +5% da Batata, +5% do conjunto com o chapéu (sem o Espetinhos), +15% da carta; sem evento só a carta")
check(xpmod.gear_bonus(worn, True, table, names, event_off=frozenset({31975}))[0] == 15
      and xpmod.event_off({"xp_event_off": [31975, "x"]}) == frozenset({31975}),
      "XP dos itens: evento desmarcado só na Batata -> fica só a carta")

# --- categorias dos itens (cores dos drops) --------------------------------------
import itemkind  # noqa: E402
kinds = itemkind.parse_kinds({
    4001: {"identifiedDescriptionName": {1: "SOR +2.", 2: "^777777Tipo:^000000 Carta"}},
    1201: {"identifiedDescriptionName": {1: "Uma faca.", 2: "Tipo: Adaga"}},
    5912: {"identifiedDescriptionName": {1: "Tipo: Visual"}},
    984: {"identifiedDescriptionName": {1: "Oridecon refinado.", 2: "Refinarias:"}},
    9001: {"identifiedDescriptionName": {1: "Tipo: Ovo de Mascote"}}})
check(kinds == {4001: "card", 1201: "equip", 984: "refine"},
      "drops: carta, arma e refino pela descrição do jogo (visual e ovo não contam) -> %s" % kinds)
saved_kinds, xpmod.GEAR.kinds = xpmod.GEAR.kinds, kinds
check(itemkind.kind(4147) == "mvpcard" and itemkind.kind(4001) == "card" and itemkind.kind(507) == "alch"
      and itemkind.kind(1000813) == "episode" and itemkind.kind(1001037) == "episode" and itemkind.kind(25723) == "episode"
      and itemkind.kind(940) is None and itemkind.kind(7134) == "alch" and itemkind.kind(1000275) == "alch"
      and itemkind.kind(984) == "refine" and itemkind.kind(1) is None and itemkind.kind(9, "Carta Nova") == "card",
      "drops: carta de MVP, carta, alquimia (só as 4 skills), episódios 17+, refino e sem categoria")
xpmod.GEAR.kinds = saved_kinds
rows = [dict(item=i, n=n) for i, n in ((1, 50), (2, 10), (3, 99), (4, 5))]
got = [r["item"] for r in itemkind.favorites_first(rows, [4, 2], lambda r: -r["n"])]
check(got == [4, 2, 3, 1], "drops: favoritos na ordem em que foram marcados, o resto pela quantidade -> %s" % got)
cols = itemkind.colors({"drop_colors": {"card": "#123456", "equip": "", "alch": "azul"}})
check(cols["card"] == "#123456" and cols["equip"] is None and cols["alch"] == itemkind.DEFAULT_COLORS["alch"],
      "drops: cor escolhida, sem cor e cor inválida volta à padrão -> %s" % cols)

# --- todo texto da interface tem tradução -------------------------------------
import ast  # noqa: E402
import i18n  # noqa: E402
untranslated = []
for name in sorted(os.listdir(os.path.join(HERE, ".."))):
    if name.endswith(".py"):
        tree = ast.parse(open(os.path.join(HERE, "..", name), encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_" and node.args:
                a = node.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value not in i18n.CATALOG:
                    untranslated.append("%s: %s" % (name, a.value[:60]))
untranslated += ["sprites.py: %s" % n for _a, n in sprites.ACTIONS + sprites.HEAD_DIRS if n not in i18n.CATALOG]
untranslated += ["xp.py: %s" % n for n in [b["name"] for b in xpmod.BONUSES] + [m for m, _p in xpmod.MANUALS]
                 if n not in i18n.CATALOG]
check(not untranslated, "textos sem tradução para EN/ES: %s" % (untranslated or "nenhum"))

# --- replays reais do usuario (se existirem) ----------------------------------
for path, who, expected in LOCAL.get("totals", []):
    if not os.path.isfile(path):
        print("pula  %s (nao encontrado)" % path)
        continue
    rf = meter.ReplayFile(path)
    rf.poll(max_bytes=1 << 30)
    snap = rf.combat.snapshot(session=True)
    got = next((p["total"] for p in snap["players"] if p["name"] == who), None)
    check(got == expected, "%s: %s = %s" % (os.path.basename(path), who, full(got or 0)))

print("\n%s" % ("TUDO OK" if not failures else "%d FALHA(S)" % failures))
sys.exit(1 if failures else 0)
