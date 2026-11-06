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
    for i, aid in enumerate((52001, 52002, 52003)):
        ev += [(i * 1000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 1000 + 300, fr.skill_damage(ME, aid, 5000)),
               (i * 1000 + 400, fr.vanish(aid, 1))]
    ev += [(3500, fr.spawn(52004, "mob", 1124, "Goblin")), (3600, fr.skill_damage(OTHER, 52004, 5000)),
           (3700, fr.vanish(52004, 1))]                                    # morto por outro: sem XP
    for name, date, exp, events in (("a.rrf", (2026, 11, 5, 19, 35, 0), 1000, ev),
                                    ("b.rrf", (2026, 11, 5, 19, 35, 20), 1000 + 306, [])):
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
          and est["source"][0] == "medido",
          "XP: 3 Goblins a 10%% = 102, +306 na gravação seguinte = fator medido ×3 -> %s %s" % (f, est["source"]))
    check(xpmod.factor(rf.combat, {"xp_mode": "fixo", "xp_fixed": 200})[0] == 3.0, "XP: valor fixo +200% = ×3")
    est = xpmod.estimate(rf.combat, {"xp_bonuses": {"server": {"on": True, "pct": 100}}})
    check(round(est["xp"]) == 204 and est["source"][0] == "lista", "XP: pela lista, evento +100%% = ×2 -> %s" % est["xp"])

c0 = combat_of(fr.build(ME, [(0, fr.spawn(52100, "mob", 21539, "Rgan")), (300, fr.skill_damage(ME, 52100, 5000)),
                             (400, fr.vanish(52100, 1)), (500, fr.spawn(52101, "mob", 3445, "Esqueleto")),
                             (600, fr.skill_damage(ME, 52101, 5000)), (700, fr.vanish(52101, 1))])[0])
rows0, unknown0 = xpmod.kills(c0)
check(unknown0 == 0 and [r["xp"] for r in rows0] == [729743 * 125 // 100, 0],      # nível 240 x 253: 125%
      "XP: monstro do episódio 19 com XP do Divine Pride; o que não dá XP conta como 0, não como desconhecido -> %s"
      % [r["xp"] for r in rows0])
wins = {"vip": [(0, 100, 0)], "manual": [(0, 100, 0)], "njord": [(50, 100, 60)]}
sets = xpmod.settings({"xp_bonuses": {"server": {"on": True}, "manual": {"pct": 200}}})
check(xpmod.bonus_at(10, wins, sets) == 100 + 20 + 200 and xpmod.bonus_at(60, wins, sets) == 100 + 20 + 200 + 60,
      "XP: bônus somam; o manual vale só enquanto ativo; Njord com o % do status")
sets2 = xpmod.settings({"xp_bonuses": {"manual": {"pct": 50}}})
xpmod.BONUSES.append(dict(key="_teste", name="x", pct=100, status=1, on=True, group="consumível"))
sets2 = xpmod.settings({"xp_bonuses": {"manual": {"pct": 50}}})
check(xpmod.bonus_at(10, {"manual": [(0, 100, 0)], "_teste": [(0, 100, 0)], "vip": []}, sets2) == 100,
      "XP: dois consumíveis ativos não somam (vale o maior)")
xpmod.BONUSES.pop()

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
