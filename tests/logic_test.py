"""Testes do decodificador e do agregador (sem janela, sem mexer no jogo).

uso: python tests\\logic_test.py
"""

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
check(mob["killer"] == "Outro" and mob["ttk"] == 9500 - 3000 and mob["max_hp"] == 2000000000,
      "monstro: abatido por, tempo ate abate, HP da tabela")
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
ev += [(1000 + i * 500, fr.auto_attack(ME, BOSS, 1000)) for i in range(121)]
ev += [(1000 + i * 1000, fr.auto_attack(EXE, BOSS, 1000)) for i in range(61) if not 45 <= i <= 47]
ev += [(1000 + i * 1000, fr.auto_attack(FORA, BOSS, 1000)) for i in range(50)]
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
check(5000 < r["climax"] < 8000, "clímax depois de 10%% do HP (dano): %d ms" % r["climax"])
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
