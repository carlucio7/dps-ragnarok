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
# aba Alvos: MVPs > monstros chefes > comuns, cada grupo pelo dano (o MVP com a aura vermelha toma 1% do dano e ficava
# no fim da lista; Laboratório Central, 2026-11-20)
rank_events = [(0, fr.spawn(70001, "mob", 1127, "Hode")), (0, fr.spawn(70002, "mob", 1791, "Galion", boss=1)),
               (0, fr.spawn(70003, "mob", 1785, "Atroce", boss=True)), (0, fr.spawn(70004, "mob", 1127, "Hode")),
               (1000, fr.skill_damage(ME, 70001, 1000)), (1200, fr.skill_damage(ME, 70002, 500)),
               (1400, fr.skill_damage(ME, 70003, 10)), (1600, fr.skill_damage(ME, 70004, 700))]
rank_snap = combat_of(fr.build(ME, rank_events)[0]).snapshot(session=True)
rank_order = [(g["rank"], g["total"]) for g in sorted(rank_snap["targets"], key=lambda g: (g["rank"], -g["total"]))]
check(rank_order == [(0, 10), (1, 500), (2, 1000), (2, 700)] and meter.rathena_boss(1791) is True
      and meter.rathena_boss(1127) is False and meter.rathena_boss(9999999) is None,
      "aba Alvos: MVP (10) > chefe (500) > comuns pelo dano (1000, 700) -> %s" % rank_order)
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
    # chave de 6 letras (monstros mais novos, como a Juncea): procurada no jogo quando aparece, e guardada à parte
    jpath = os.path.join(game, "Replay", "juncea.rrf")
    with open(jpath, "wb") as fh:
        fh.write(fr.build(ME, [(0, fr.spawn(687, "mob", 21533, "\x1ccbb7DQ\x1c")),
                               (0, fr.spawn(688, "mob", 21998, "\x1coIY2DA\x1c")),
                               (0, fr.spawn(689, "mob", 21997, "\x1cZZ99zz\x1c")),
                               (1000, fr.skill_damage(ME, 687, 5000)), (1500, fr.vanish(687, 1)),
                               (1600, __import__("struct").pack("<HIIHBHHBBHBH", rrf.P_ITEM_FALL, 1, 607, 3, 1,
                                                                10, 10, 6, 6, 1, 1, 0))])[0])
    csv2 = csv + "cbb7DQ,,%s,,,,,%s,,%s\n" % (b64("Simulation Juncea"), b64("Juncea de Simulação"),
                                             b64("Junca de simulación"))
    fr.build_grf(os.path.join(game, "data.grf"), {"data\\i18n\\sc\\abc.csv": csv2.encode("utf-8"),
                                                 "data\\sprite\\x.spr": b"nada"})
    clientdata.NAMES = clientdata.ClientNames()
    rj = meter.ReplayFile(jpath)
    rj.poll(max_bytes=1 << 30)
    clientdata.NAMES.wait(30)                            # as tabelas curtas
    first = [rj.combat.name_of(a) for a in (687, 688, 689)]
    clientdata.NAMES.wait(30)                            # a busca das chaves longas
    after = [rj.combat.name_of(a) for a in (687, 688, 689)]
    check(first == ["Monstro 21533", "Monstro 21998", "Monstro 21997"]
          and after == ["Juncea de Simulação", "Uma frase", "Monstro 21997"],
          "chave de 6 letras: o nome vem do jogo depois da busca; chave que não existe mostra o id: %s -> %s"
          % (first, after))
    fell = [d for d in rj.combat.drops if d["fell"]]
    check(len(fell) == 1 and rj.combat.drop_mob(fell[0]) == "Juncea de Simulação",
          "o nome de quem deixou o item cair é visto na hora de mostrar: %s (guardado: %s)"
          % (fell and rj.combat.drop_mob(fell[0]), fell and fell[0]["mob"]))
    saved_extra = json.load(open(clientdata.extra_path(), encoding="utf-8"))["extra"]
    again = clientdata.ClientNames()
    again.use_folder(os.path.join(game, "Replay"))
    again.load()
    check(saved_extra.get("cbb7DQ", [None, None])[1] == "Juncea de Simulação" and "ZZ99zz" in saved_extra
          and again.lookup("cbb7DQ") == "Juncea de Simulação" and again._extra_thread is None,
          "chaves longas ficam guardadas: ao reabrir o programa o nome sai na hora, sem procurar de novo")
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
# aviso de "dano em monstros comuns não é contado": só sem luta contada em andamento
check(c.off_notice() is None and cm.off_last == 1300 and cm.off_notice() is None,
      "aviso do filtro: nada com 'todos os monstros', nem com uma luta contada em andamento")


def only_mvp(events, now=None):
    data = fr.build(ME, events)[0]
    h = rrf.Header(data)
    x = meter.Combat(rrf.Session(h, data), 10000, "mvp")
    r = rrf.StreamReader(h.keys, rrf.WANTED)
    x.feed(r.feed(data[h.stream_offset:]), r.last_time if now is None else now)
    return x


poring = [(0, fr.spawn(MOB, "mob", 1002, "Poring")), (1200, fr.skill_damage(ME, MOB, 10))]
x = only_mvp(poring)
check(x.off_notice() == "nothing" and not x.encounters(), "aviso do filtro: só bateu em monstro comum = nada contado")
x = only_mvp([(0, fr.spawn(MOB, "mob", 1002, "Poring")), (1200, fr.skill_damage(OTHER, MOB, 10))])
check(x.off_notice() is None, "aviso do filtro: outro jogador batendo em monstro comum não avisa quem grava")
boss_then_poring = [(0, fr.spawn(60001, "mob", BETEL, "Betelgeuse", boss=2)), (0, fr.spawn(MOB, "mob", 1002, "Poring")),
                    (1000, fr.skill_damage(ME, 60001, 3000)), (30000, fr.skill_damage(ME, MOB, 10))]
x = only_mvp(boss_then_poring, now=31000)
check(x.off_notice() == "now", "aviso do filtro: a luta contada acabou e ele bate em monstro comum = avisa")
x = only_mvp(boss_then_poring, now=45000)
check(x.off_notice() is None, "aviso do filtro: parou de bater em monstro comum há mais de 10 s = some")
x = only_mvp(boss_then_poring, now=31000)
x.finished = True
check(x.off_notice() is None, "aviso do filtro: replay encerrado com luta contada não avisa")

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

    # a luta contra o boneco ainda em andamento quando o widget passa para outra gravação: antes se perdia
    def put(path, data):
        with open(path, "wb") as f:
            f.write(data)

    fight = dummy + [(1000 + i * 500, fr.skill_damage(ME, 4404, 2000)) for i in range(20)]
    day = (2026, 10, 23, 1, 5, 0)
    whole, part = fr.build(ME, fight, date=day)[0], fr.build(ME, fight[:15], date=day)[0]
    path = os.path.join(tmp, "seguida.rrf")
    put(path, part)
    rf = meter.ReplayFile(path, 15000)
    rf.poll()
    seen = set()
    check(testes.auto_save(store, rf, seen) == 0, "luta contra o boneco em andamento: ainda não é salva")
    check(testes.waiting(store, rf, seen) is not None, "e aparece como esperando para ser salva")
    left = testes.Left()
    left.add(rf, 100.0)
    put(path, whole)                                     # o jogo seguiu gravando depois de o widget sair dela
    check(left.step(store, seen, 105.0) == 0 and len(left.items) == 1, "gravação deixada para trás ainda crescendo: espera")
    check(left.step(store, seen, 105.0 + testes.QUIET_S + 1) == 1 and not left.items,
          "gravação deixada para trás parou de crescer: o teste é salvo")
    check(store.records[0]["damage"] == 20 * 2000, "e com a luta inteira (%s)" % store.records[0]["damage"])
    check(testes.waiting(store, rf, seen) is None, "depois de salva, não espera mais")
    # ao fechar o programa: salva a que já parou, larga a que ainda cresce (não guarda luta pela metade)
    day = (2026, 10, 23, 1, 6, 0)
    whole, part = fr.build(ME, fight, date=day)[0], fr.build(ME, fight[:15], date=day)[0]
    path = os.path.join(tmp, "fechando.rrf")
    put(path, part)
    rf = meter.ReplayFile(path, 15000)
    rf.poll()
    left.add(rf, 200.0)
    put(path, whole)
    n_before = len(store.records)
    check(left.step(store, seen, 200.5, closing=True) == 0 and not left.items and len(store.records) == n_before,
          "fechando com a gravação crescendo: não salva pela metade")
    rf = meter.ReplayFile(path, 15000)
    rf.poll()
    left.add(rf, 200.0)
    check(left.step(store, seen, 202.0, closing=True) == 1 and store.records[0]["damage"] == 20 * 2000,
          "fechando com a gravação já parada: o teste é salvo")
    # outro replay gravado por cima, com o mesmo nome: é outra gravação, lida do começo
    sub = os.path.join(tmp, "Replay")
    os.makedirs(sub)
    path = os.path.join(sub, "mesmo nome.rrf")
    put(path, fr.build(ME, fight, date=(2026, 10, 23, 1, 7, 0))[0])
    w3 = meter.Watcher(sub, 15000, auto=False)
    w3.poll(time.time())
    old = w3.file
    check(old is not None and old.ready and old.combat.snapshot()["my_total"] == 20 * 2000, "replay aberto e lido")
    again = dummy + [(1000 + i * 500, fr.skill_damage(ME, 4404, 7)) for i in range(40)]
    put(path, fr.build(ME, again, date=(2026, 10, 23, 1, 8, 0))[0])
    w3.poll(time.time())
    check(old.gone and w3.file is not old, "outro replay gravado por cima, com o mesmo nome: o medidor percebe")
    check(w3.file.ready and w3.file.combat.snapshot()["my_total"] == 40 * 7,
          "e lê o novo do começo (%s)" % (w3.file.ready and w3.file.combat.snapshot()["my_total"]))
    left.add(old, 300.0)
    check(left.step(store, seen, 300.1) == 1 and store.records[0]["replay"] == "mesmo nome.rrf",
          "a luta do replay que foi sobrescrito não se perde")
    put(path, fr.build(ME, fight[:8], date=(2026, 10, 23, 1, 9, 0))[0])     # e agora um menor por cima
    w3.poll(time.time())
    check(w3.file.ready and w3.file.combat.snapshot()["my_total"] == 7 * 2000, "replay menor gravado por cima: também")
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

# --- Dedo Duro: Animista (Chuva de Mariscos, Balaio de Gato -> Despertar, Bênção da Natureza, Aliança Animal) ---
ANI, SKE2, MAG3, BOSS3 = 2201, 2202, 2203, 60003
ani_ev = [(0, fr.spawn(ANI, "pc", 4308, "Bicho")), (0, fr.spawn(SKE2, "pc", 4302, "Ceu2")),
      (0, fr.spawn(MAG3, "pc", 4255, "Mago2")), (0, fr.spawn(BOSS3, "mob", BETEL, "Betelgeuse", boss=2))]
ani_ev += [(100, fr.party_hp(a, 50000, 50000)) for a in (ANI, SKE2, MAG3)]
ani_ev += [(500, fr.skill_use(ANI, ANI, 5040)), (900, fr.skill_use(ANI, ANI, 5447)), (1000, fr.skill_use(ANI, ANI, 5053))]
ani_ev += [(600, fr.status(a, 920, True, 180000, 180000, 10)) for a in (ANI, SKE2, MAG3)]       # Chuva de Mariscos
ani_ev += [(70000, fr.status(a, 920, False)) for a in (ANI, SKE2, MAG3)]
ani_ev += [(1000, fr.status(a, 953, True, 12000, 12000, 100)) for a in (ANI, SKE2, MAG3)]       # Despertar (Balaio)
ani_ev += [(13000, fr.status(a, 953, False)) for a in (ANI, SKE2, MAG3)]
ani_ev += [(900, fr.status(ANI, 1377, True, 150000, 150000, 15)), (70000, fr.status(ANI, 1377, False))]  # Aliança Animal
# Bênção da Natureza no Mestre Celestial: P.ATQ e S.ATQM +50 por 10 s; depois, 1 min sem poder receber de novo
bless_ev = [(20000, fr.skill_use(ANI, SKE2, 5448)), (20000, fr.status(SKE2, 1378, True, 10000, 10000, 5)),
            (30000, fr.status(SKE2, 1378, False)), (30000, fr.status(SKE2, 1379, True, 60000, 60000, 0)),
            (60000, fr.status(SKE2, 1379, False))]
ani_ev += bless_ev
ani_ev += [(2000 + i * 500, fr.skill_damage(a, BOSS3, 2000000, skill=sk, hits=1)) for i in range(120)
       for a, sk in ((SKE2, 5474), (MAG3, 2218), (ANI, 5437))]
c_ani = combat_of(fr.build(ME, sorted(ani_ev, key=lambda e: e[0]), player="Eu")[0], gap_ms=15000)
r_ani = dd.analyze(c_ani, BOSS3)
shrimp = {b["name"] for b in r_ani["buffs"] if b["buff"] == meter.status_name(920)}
awake = [b for b in r_ani["buffs"] if b["buff"] == meter.status_name(953)]
pact = [b for b in r_ani["buffs"] if b["buff"] == meter.status_name(1377)]
check(meter.job_name(4308) == "Animista" and {"Ceu2", "Mago2"} <= shrimp,
      "Animista: Chuva de Mariscos cobrada de quem bate físico e mágico (ATQ e ATQM +10%%): %s" % sorted(shrimp))
check(len(awake) == 1 and "rajada" in awake[0]["note"] and not any(meter.status_name(953) in a["what"]
                                                                  for a in r_ani["alerts"]),
      "Despertar do Balaio de Gato (12 s a cada 180 s): na tabela da classe, sem alerta de tempo ativo: %s"
      % [(b["name"], b["note"]) for b in awake])
check(len(pact) == 1 and pact[0]["name"] == "Bicho" and pact[0]["p1"] == "100%",
      "Aliança Animal: buff da própria classe do Animista -> %s" % [(b["name"], b["p1"]) for b in pact])
bless, aftermath = meter.status_name(1378), meter.status_name(1379)
bless_rows = {row["name"]: row for row in an.buff_uptime(c_ani, SKE2, None)[0]}
check(bless in bless_rows and not any(bless in a["what"] or aftermath in a["what"] for a in r_ani["alerts"] + r_ani["o_alerts"]),
      "Bênção da Natureza (alvo único, 10 s): na tabela de buffs de quem recebeu (%s), sem alerta" % bless)
# crédito: os buffs do Animista do grupo rendem para ele (estimativa da calculadora); fora do grupo, nada
import contrib  # noqa: E402
crows, _ctot = contrib.credit(c_ani, BOSS3)
ani_via = next((r_["via"] for r_ in crows if r_["aid"] == ANI), {})
frows = {r_["efst"]: r_ for r_ in contrib.fight(c_ani, BOSS3)[0]}
# Bênção: 20 golpes de 2M com Chuva (×1,006) e Bênção (×1,151): o ganho de cada um, dividido pelo log, ~261,6K
check(set(ani_via) == {920, 953, 1378} and abs(ani_via[1378] - 5232000) < 50000 and ani_via[953] > 0
      and ani_via[920] > 0 and frows.get(1378, {}).get("where") == "given" and frows[1378]["hits"] == 20,
      "crédito do Animista do grupo (Chuva, Despertar, Bênção) -> %s" % {k: round(v) for k, v in ani_via.items()})
solo = combat_of(fr.build(ME, sorted([e for e in ani_ev if e != (100, fr.party_hp(ANI, 50000, 50000))],
                                     key=lambda e: e[0]), player="Eu")[0], gap_ms=15000)
srows, _stot = contrib.credit(solo, BOSS3)
check(not any(r_["via"] for r_ in srows) and not {920, 953, 1378} & {r_["efst"] for r_ in contrib.fight(solo, BOSS3)[0]},
      "Animista fora do grupo: os buffs dele não entram no crédito")
# Dedo Duro: Animista do grupo que não usou a Bênção da Natureza em nenhum momento = grave
check(not any(meter.skill_name(5448) in a["what"] for a in r_ani["alerts"]), "usou a Bênção da Natureza: sem alerta")
lazy = combat_of(fr.build(ME, sorted([e for e in ani_ev if e not in bless_ev], key=lambda e: e[0]),
                          player="Eu")[0], gap_ms=15000)
nob = [a for a in dd.analyze(lazy, BOSS3)["alerts"] if a["what"] == "%s não foi usada" % meter.skill_name(5448)]
check(len(nob) == 1 and nob[0]["sev"] == 2 and nob[0]["who"] == "Bicho",
      "Animista sem a Bênção da Natureza na luta: grave -> %s" % [(a["sev"], a["who"]) for a in nob])

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
# golpe a golpe: só montados quando alguém liga a faixa (numa luta longa são mais de cem mil eventos)
hev = d2["hit_events"]()
_ph = [h for h in c2.hits if d2["t0"] <= h.t <= d2["t1"] and h.out and h.src in set(d2["players"])]
check({l["key"] for l in d2["lanes"]} >= {"hits"} and not any(e["kind"] in ("hit", "mobhit") for e in d2["events"])
      and d2["hit_events"]() is hev and [e["t"] for e in hev] == sorted(e["t"] for e in hev) and _ph
      and sorted((e["t"], e["aid"], e["value"]) for e in hev if e["kind"] == "hit")
      == sorted((h.t, h.src, h.dmg) for h in _ph)
      and all(e["who"] == c2.name_of(e["aid"]) and "target" in e for e in hev if e["kind"] == "hit"),
      "linha do tempo: golpes de cada jogador montados só quando a faixa liga, uma vez, em ordem -> %d de %d"
      % (sum(1 for e in hev if e["kind"] == "hit"), len(_ph)))
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

# --- atacou muito antes dos outros DPS ----------------------------------------
DA, DB, DC = 2201, 2202, 2203
ev = [(0, fr.spawn(61000, "mob", BETEL, "Betelgeuse", boss=2)), (0, fr.spawn(DA, "pc", 4302, "Sincronia")),
      (0, fr.spawn(DB, "pc", 4302, "Parceiro")), (0, fr.spawn(DC, "pc", 4302, "Quase"))]
ev += [(100, fr.party_hp(a, 50000, 50000)) for a in (DA, DB, DC)]
ev += [(1000 + i * 1000, fr.skill_damage(DA, 61000, 10000000, hits=1)) for i in range(20)]
ev += [(1100 + i * 1000, fr.skill_damage(DB, 61000, 10000000, hits=1)) for i in range(20)]
ev += [(26000, fr.skill_damage(DA, 61000, 10000000, hits=1)),     # 2,5 s antes da volta do parceiro
       (26300, fr.skill_damage(DA, 61000, 10000000, hits=1)),     # mesmo episódio
       (28500, fr.skill_damage(DB, 61000, 10000000, hits=1)), (28600, fr.skill_damage(DA, 61000, 10000000, hits=1)),
       (33200, fr.skill_damage(DC, 61000, 10000000, hits=1)),     # 0,8 s antes dos outros: só atenção
       (34000, fr.skill_damage(DB, 61000, 10000000, hits=1)), (34050, fr.skill_damage(DA, 61000, 10000000, hits=1)),
       (40000, fr.skill_damage(DB, 61000, 10000000, hits=1))]     # sozinho no fim: ninguém bate depois, não conta
c = combat_of(fr.build(ME, ev)[0])
r = dd.analyze(c, 61000)
alert = {a["sev"]: a for a in r["alerts"] if a["what"] == "Atacou muito antes dos outros DPS"}
check(sorted(alert) == [1, 2] and alert[2]["who"] == "Sincronia 2,5 s antes" and alert[1]["who"] == "Quase 0,8 s antes"
      and sorted((d["aid"], d["hits"]) for d in r["desync"]) == [(DA, 2), (DC, 1)],
      "atacou antes: 2,5 s antes é grave (2 golpes num episódio), 0,8 s é atenção, sozinho no fim não conta -> %s"
      % {k: v["who"] for k, v in alert.items()})

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
# corpo a corpo x de longe: alcance negativo é o da arma (Firmamento −9, Golpe Fulminante −1) e algumas skills fogem
# da regra (Impacto Brutal, Revoada Sombria e Avanço Sísmico chegam de longe mas contam como corpo a corpo)
near = [s for s in (5474, 5, 42, 271, 5287, 5294, 5296, 5315, 5473, 0) if contrib.melee(s)]
far = [s for s in (46, 2554, 5406, 5437, 2332, 57) if not contrib.melee(s)]
check(len(near) == 10 and len(far) == 6, "corpo a corpo: %s; de longe: %s" % (near, far))
ev = [(0, fr.spawn(61000, "mob", BETEL, "Betelgeuse", boss=2)),
      (500, fr.status(61000, 730, True, 20000, 20000, 150)),                    # Garra Sombria nv 5 (150%)
      (1000, fr.skill_damage(ME, 61000, 1750000, skill=5474, hits=1)),          # Firmamento: corpo a corpo
      (2000, fr.skill_damage(ME, 61000, 1000000, skill=46, hits=1))]            # Rajada Dupla: de longe
c = combat_of(fr.build(ME, ev)[0])
rows, total = contrib.fight(c, 61000)
got = {r["efst"]: round(r["contrib"]) for r in rows}
check(total == 2750000 and got.get(730) == 750000,
      "contribuição: a Garra Sombria vale no Firmamento (75/175) e não na Rajada Dupla -> %s" % got)
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
# Lex Aeterna na linha do tempo: um ponto por Lex posta, com o golpe que ela dobrou ou por que não dobrou nada
import timeline as _tl  # noqa: E402
ev += [(3000, fr.skill_use(OTHER, 61000, 78)), (3300, fr.skill_use(OTHER, 61000, 78)),     # a 1ª não acumula
       (3400, fr.skill_damage(ME, 61000, 4000, skill=5473, hits=1)), (3700, fr.skill_use(OTHER, 61000, 78))]
c = combat_of(fr.build(ME, ev)[0])
_lx = [e for e in _tl.build(c, 61000)["events"] if e["kind"] == "lex"]
_lanes = {l["key"]: l for l in _tl.build(c, 61000)["lanes"]}
check([(e["t"], e["aid"], e["used"], e.get("target")) for e in _lx]
      == [(1000, OTHER, True, ME), (1300, OTHER, True, ME), (1600, OTHER, True, ME), (2000, None, False, None),
          (3000, OTHER, False, None), (3300, OTHER, True, ME), (3700, OTHER, False, None)]
      and "1.000 (a Lex rendeu 500)" in _lx[0]["detail"] and _lx[3]["detail"] == _tl.LEX_END["off"]
      and _lx[4]["detail"] == _tl.LEX_END["replaced"] and _lx[6]["detail"] == _tl.LEX_END["left"]
      and _lanes["lex"]["kind"] == "point" and _lanes["lex"]["on"] and len(_lanes["lex"]["items"]) == 7,
      "linha do tempo: Lex Aeterna com o golpe dobrado, a que só o status mostrou (gasta fora da tela), a que não "
      "acumulou e a que sobrou -> %s" % [(e["t"], e["used"], e["detail"]) for e in _lx])
# força de cada golpe (cor na lista, bolinhas na curva de HP): faixa pelo % do HP do chefe; o % vai nos golpes fortes
# e no golpe a golpe no chefe, e a Lex que dobrou guarda o instante e o % do golpe dobrado
_big = ev + [(4000, fr.skill_use(OTHER, 61000, 78)), (4100, fr.skill_damage(ME, 61000, 48000000, skill=5473, hits=1)),
             (4500, fr.skill_damage(ME, 61000, 4000000, skill=5473, hits=1))]
_d = _tl.build(combat_of(fr.build(ME, _big)[0]), 61000)
_hp = float(_d["hp_max"])
_st = [(e["t"], _tl.strength(e["pct"])) for e in _d["events"] if e["kind"] == "strong"]
_lxu = [e for e in _d["events"] if e["kind"] == "lex" and e["used"]]
check([_tl.strength(p) for p in (0.0049, 0.005, 0.01, 0.0101, 0.05, 0.0501)] == [0, 1, 1, 2, 2, 3]
      and _st == [(4100, 3), (4500, 1)]
      and all(e.get("pct") == e["value"] / _hp for e in _d["hit_events"]() if e["kind"] == "hit")
      and (_lxu[-1]["hit_t"], _tl.strength(_lxu[-1]["hit_pct"])) == (4100, 3)
      and all(e["hit_t"] >= e["t"] and e["hit_pct"] == 2 * e["value"] / _hp for e in _lxu),
      "força do golpe: faixas < 0,5%% | 0,5–1%% | > 1%% | > 5%% do HP; o %% nos golpes e, na Lex, o do golpe dobrado "
      "-> %s, %s" % (_st, [(e["hit_t"], round(e["hit_pct"] * 100, 4)) for e in _lxu]))

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
# a cifra do .grf com tabelas dá o mesmo que a conta bit a bit (blocos ao acaso e casos de borda)
import random as _rnd  # noqa: E402
_rg = _rnd.Random(7)
_blocks = [bytes(8), b"\xff" * 8, bytes(range(8))] + [bytes(_rg.randrange(256) for _ in range(8)) for _ in range(400)]
_same = 0
for _b in _blocks:
    _x, _y = bytearray(_b), bytearray(_b)
    sprites._des_block(_x, 0)
    sprites._des_block_bits(_y, 0)
    _same += _x == _y
check(_same == len(_blocks), "grf: a cifra com tabelas é igual à bit a bit em %d de %d blocos" % (_same, len(_blocks)))
# imagem no lugar como o jogo (metade do tamanho em divisão inteira): com round() o .5 ia para o par e um quadro
# de tamanho ímpar pulava 1 pixel (o Olho do Necromante, 37 de altura, saltava a cada passo)
check([sprites.put_at(11, y, 53, 37)[1] - y for y in (-65, -64, -63, -62)] == [-18] * 4
      and sprites.put_at(0, 0, 4, 4) == (-2, -2) and sprites.put_at(-3, 5, 5, 3) == (-5, 4),
      "sprites: a imagem fica no mesmo lugar em relação à camada em todo quadro (sem o arredondamento para o par)")
_E, _A, _B = bytes(4), bytes([1, 2, 3, 255]), bytes([4, 5, 6, 9])
_im = _E + _A + _E + _E + _E + _E + _B + _E + _E * 4            # 4 x 3: um pixel em (1, 0), outro em (2, 1)
check(sprites.alpha_box(4, 3, _im) == (1, 0, 3, 2) and sprites.alpha_box(2, 2, bytes(16)) is None
      and sprites.crop_rgba(4, _im, (1, 0, 3, 2)) == _A + _E + _E + _B,
      "visuais: miniatura do chapéu recortada no que tem pixel")
# chapéus e capas animados (varredura de 2026-11-17: 371 chapéus e 16 capas): parado e sentado, os quadros vêm em 3
# grupos (cabeça de frente, esquerda, direita) que animam no ritmo da parte; andando, a parte com o mesmo número
# de quadros do corpo segue o passo dele, e a de outra quantidade anima no próprio ritmo


class _FakeAct:
    def __init__(self, counts, delay=100.0):
        self.counts, self.delays = counts, [delay] * 104

    def frames(self, act_i):
        return [([], [(0, 0)])] * self.counts.get(act_i // 8, 1)


hat24 = sprites.Part("top", None, _FakeAct({0: 24, 1: 8, 2: 24}))
hat3 = sprites.Part("top", None, _FakeAct({0: 3, 1: 8}))
hat16 = sprites.Part("top", None, _FakeAct({0: 24, 1: 16}, 200.0))
pf = sprites.part_frame
check(pf(hat24, 0, sprites.IDLE, 0, 0, 3, 250) == 2 and pf(hat24, 0, sprites.IDLE, 1, 0, 3, 250) == 10
      and pf(hat24, 0, sprites.IDLE, 2, 0, 3, 820) == 16 and pf(hat3, 0, sprites.IDLE, 1, 0, 3, 999) == 1
      and pf(hat24, 8, sprites.WALK, 0, 5, 8, 999) == 5 and pf(hat16, 8, sprites.WALK, 0, 5, 8, 650) == 3
      and pf(hat24, 16, sprites.SIT, 2, 0, 3, 100) == 17
      and sprites.own_clock(24, sprites.IDLE, 3) and not sprites.own_clock(3, sprites.IDLE, 3)
      and not sprites.own_clock(8, sprites.WALK, 8) and sprites.own_clock(16, sprites.WALK, 8)
      and sprites.own_clock(8, sprites.IDLE, 3),
      "visuais animados: parado, o chapéu de 24 quadros anima dentro do grupo da direção da cabeça (frente 0-7, "
      "esquerda 8-15, direita 16-23); o comum mostra o quadro da direção; andando, segue o passo do corpo, e o de "
      "outra quantidade de quadros anima no próprio ritmo")
check(sprites.extent([body, head], body, sprites.IDLE, 0) == (-ox, -oy, w_ - ox, h_ - oy),
      "visuais: o retângulo de todos os quadros (pés fixos na prévia) bate com o do quadro montado -> %s" % (
          sprites.extent([body, head], body, sprites.IDLE, 0),))
# o personagem montado pelo GDI+: igual ao pixel a pixel no que é opaco; no translúcido sobre o vazio a cor fica
# inteira (o pixel a pixel escurecia: o brilho do Olho do Necromante saía sujo)
import gdip as _gd  # noqa: E402
if _gd.ready():
    fast = sprites.compose_gdi([body, head], body, sprites.IDLE, 0, 0)
    ghost = sprites.Part("fantasma", body.spr, sprites.Act(act_bytes((0, -1), (0, -10))), anchored=False)
    ghost.act.frames(0)[0][0][0].color = (255, 255, 255, 128)
    slow_g = sprites.compose([ghost], ghost, sprites.IDLE, 0, 0)[2][0]
    fast_g = sprites.compose_gdi([ghost], ghost, sprites.IDLE, 0, 0)[2][:4]
    check(fast is not None and fast[:2] == (w_, h_) and fast[3:] == (ox, oy)
          and fast[2] == b"".join(bytes(p) for p in px)
          and slow_g[:3] == (128, 0, 0) and tuple(fast_g) == (255, 0, 0, 128)
          and sprites.shade(bytes([200, 100, 50, 255])) == bytes([40, 20, 10, 141])
          and sprites.whiten(bytes([0, 100, 255, 7])) == bytes([153, 193, 255, 7]),
          "visuais: o quadro do personagem pelo GDI+ é igual ao pixel a pixel no opaco e mantém a cor no translúcido "
          "-> %s %s" % (slow_g, tuple(fast_g)))
# desenho suavizado (GDI+ do Windows): os monstros maiores que a caixa ou montados com peças em escala
import gdip  # noqa: E402
if gdip.ready():
    RD, GN, BL, NO = bytes([0, 0, 255, 255]), bytes([0, 255, 0, 255]), bytes([255, 0, 0, 255]), bytes(4)   # BGRA
    im = gdip.Image(2, 2, RD + GN + BL + NO)
    check(gdip.render(2, 2, [(im, 1.0, 0.0, 0.0, 1.0, 1.0, 1.0, False)]) == RD + GN + BL + NO
          and gdip.render(2, 2, [(im, -1.0, 0.0, 0.0, 1.0, 1.0, 1.0, False)]) == GN + RD + NO + BL
          and gdip.render(2, 2, [(im, 0.0, 1.0, -1.0, 0.0, 1.0, 1.0, False)]) == BL + RD + NO + GN
          and gdip.render(4, 4, [(im, 2.0, 0.0, 0.0, 2.0, 2.0, 2.0, False)])[:16] == RD + RD + GN + GN,
          "GDI+: escala 1 copia pixel a pixel, o espelho troca as colunas, 90 graus gira no sentido do relógio e "
          "o dobro repete os pixels")
    WH, BK = bytes([255] * 4), bytes([0, 0, 0, 255])
    half = gdip.resize(4, 4, ((WH + BK) * 2 + (BK + WH) * 2) * 2, 2, 2)
    check(half is not None and all(60 < half[i] < 200 for i in (0, 4, 8, 12)) and half[3] == 255,
          "GDI+: reduzir à metade mistura os pixels em vez de jogar fora (o xadrez vira cinza) -> %s" % list(half[:8]))
    got = sprites.smooth_frames(body, body.act.frames(sprites.IDLE)[:1])
    want = sprites.compose([body], body, sprites.IDLE, 0, 0)
    check(got is not None and got[:2] == want[:2]
          and list(struct.iter_unpack("4B", gdip.swap_rb(got[2][0]))) == [tuple(p) for p in want[2]],
          "sprite: sem escala nem giro, o quadro montado pelo GDI+ é igual ao montado pixel a pixel -> %s" % (got and got[:2],))
    big = sprites.Part("grande", sprites.Sprite(spr_bytes(4, 4, [1, 0] * 8, {1: RED})), body.act, anchored=False)
    big.act.frames(0)[0][0][0].sx = big.act.frames(0)[0][0][0].sy = 0.5
    got = sprites.smooth_frames(big, big.act.frames(0)[:1])
    big.act.frames(0)[0][0][0].sx = big.act.frames(0)[0][0][0].sy = 1.0
    check(got is not None and got[:2] == (2, 2) and all(40 < got[2][0][i + 3] < 215 for i in (0, 4, 8, 12)),
          "sprite: a peça em escala 0,5 sai do tamanho certo e suavizada (colunas cheias e vazias viram meio "
          "transparentes) -> %s" % ((got and (got[:2], list(got[2][0]))),))
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
    only_mvp = meter.ReplayFile(os.path.join(tmp, "a.rrf"), 15000, "mvp")
    only_mvp.poll(max_bytes=1 << 30)
    rows_mvp, _unk = xpmod.kills(only_mvp.combat)
    check(not only_mvp.combat.encounters() and not [h for h in only_mvp.combat.hits if h.out]
          and [(r["aid"], r["xp"], r["share"]) for r in rows_mvp] == [(r["aid"], r["xp"], r["share"]) for r in rows],
          "XP: com 'Contar dano em: só MVPs e bonecos' o abate de monstro comum vale XP do mesmo jeito -> %d abates"
          % len(rows_mvp))
    rows, unknown = xpmod.kills(rf.combat)
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

    # Zerar no meio da gravação apaga os abates de antes: a XP exata do trecho ficava comparada só com os abates
    # depois do Zerar (numa gravação real, fator 3,31 em vez de 1,55, guardado como medida do mapa)
    def zerado(n_events):
        """a.rrf lido como o widget ao vivo (o arquivo crescendo), com um Zerar depois dos n primeiros eventos."""
        zp = os.path.join(tempfile.mkdtemp(dir=tmp), "a.rrf")
        full, _o = fr.build(ME, ev, date=(2026, 11, 5, 19, 35, 0), xp=(7100, 1000, 10 ** 9))
        part, _o = fr.build(ME, ev[:n_events], date=(2026, 11, 5, 19, 35, 0), xp=(7100, 1000, 10 ** 9))
        with open(zp, "wb") as fh:
            fh.write(part)
        rz = meter.ReplayFile(zp)
        rz.poll(max_bytes=1 << 30)
        xpmod.keep_level(rz.combat, {})
        rz.combat.reset()
        with open(zp, "ab") as fh:
            fh.write(full[len(part):])
        rz.poll(max_bytes=1 << 30)
        rz.combat.path = os.path.join(tmp, "a.rrf")         # a gravação seguinte (b.rrf) está na pasta do teste
        return rz.combat, full.startswith(part)
    zc, prefix = zerado(3)                                  # Zerar depois do 1º abate
    cz = {}
    p_zero, p_full = xpmod.progress(zc, {}), xpmod.progress(rf.combat, {})
    check(prefix and len(xpmod.kills(zc)[0]) == 2 and xpmod.exact_segments(zc, cz, meter.xp_after) == []
          and xpmod.calibrate(zc, cz, meter.xp_after) is None and not cz.get("xp_corr")
          and round(p_zero["xp"]) == round(p_full["xp"]) == 1102,
          "XP: Zerar no meio apaga abates: o trecho não calibra e a posição no nível não volta para trás -> %s / %s"
          % (round(p_zero["xp"]), round(p_full["xp"])))
    z0, prefix = zerado(1)                                  # Zerar antes do 1º abate: nada apagado
    check(prefix and z0.reset_t is None and xpmod.calibrate(z0, {}, meter.xp_after) == 3.0,
          "XP: Zerar sem abate apagado não atrapalha a medida")
    rb = rrf.read_session(os.path.join(tmp, "b.rrf"))
    scan_first = meter.xp_scan(tmp)
    meter._XP_SCANS[os.path.normcase(tmp)].join(10)
    check(meter.xp_scan(tmp) is True and meter.xp_scan("") is True and scan_first in (True, False)
          and meter.xp_after_soon(a, s_a) == meter.xp_after(a, s_a),
          "XP: as outras gravações da pasta são lidas num fio à parte; pronto, a consulta rápida dá o mesmo")
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
m = an.BOSS_MODEL[21531]
# 500M - 100M = 80%; 10 s de sobrecarga, os 2 primeiros sem curar: +8 s × 0,54% = 84,32%; quebra -4,4%; -1M
check(xa.hp == 500000000 and xa.hp_label == "Executiva" and wins == [(2000, 12000)] and hid == [13000]
      and an.regen_windows(ca, xa.boss_aids, m, xa.start, xa.end) == [(4000, 12000)]
      and abs(end - (0.8 + 0.0432 - 0.044 - 0.002)) < 1e-6,
      "Aquila: Executiva pela redução de 50%%; regenera 0,54%%/s em sobrecarga depois de 2 s e a quebra de defesa "
      "tira 4,4%% -> %.4f" % end)
check([an.boss_regen(m, 21531, hp) for hp in (300000000, 500000000, 600000000, 123)] == [0.0054, 0.0054, 0.0105, 0.0054],
      "Aquila: regeneração por dificuldade (Econômica e Executiva 0,54%/s, Primeira Classe 1,05%/s)")
# o chefe fora da tela: nem a troca de sprite nem o Tetra Vortex chegam, mas os anúncios da sala sim
ev_room = [(0, fr.spawn(AQ, "mob", 21531, "Aquila", boss=True)), (50, fr.status(AQ, 1166, True, 0, 0, 50)),
           (1000, fr.skill_damage(ME, AQ, 100000000)),
           (2000, fr.broadcast("ni0XDg")), (12000, fr.broadcast("nS0XDg")),         # sobrecarga liga e desliga
           (13000, fr.broadcast("my0XDg")), (13400, fr.broadcast("my0XDg")),        # quebra de defesa (repetido)
           (14000, fr.skill_damage(ME, AQ, 1000000))]
cr = combat_of(fr.build(ME, ev_room)[0])
xr = dd.Ctx(cr, AQ, None)
end_r = tl.build(cr, AQ)["hp"][-1][1]
check(cr.overloads == [[2000, 12000]] and cr.def_breaks == [13000]
      and an.regen_windows(cr, xr.boss_aids, m, xr.start, xr.end) == [(4000, 12000)]
      and an.hidden_losses(cr, xr.boss_aids, m, xr.start, xr.end) == [13000] and abs(end_r - end) < 1e-9,
      "Aquila: sobrecarga e quebra de defesa pelos anúncios da sala, com o chefe fora da tela -> %.4f" % end_r)
cm = combat_of(fr.build(ME, [(0, fr.spawn(AQ, "mob", 21531, "Aquila", boss=True)), (500, fr.skill_damage(ME, AQ, 1000)),
                             (3000, fr.broadcast("nS0XDg"))])[0])
check(cm.overloads == [[0, 3000]], "Aquila: gravação que começa com a sobrecarga ligada conta desde o começo -> %s"
      % cm.overloads)
# luta em que ele morreu: com 0,54%/s a curva zerava aos 34 s (40% + 15,1% - 40% - 16%), 6 s antes da morte. A
# regeneração da luta é ajustada para a curva fechar no golpe que matou, e ela não encosta no zero antes
ev_kill = [(0, fr.spawn(AQ, "mob", 21531, "Aquila", boss=True)), (50, fr.status(AQ, 1166, True, 0, 0, 50)),
           (1000, fr.skill_damage(ME, AQ, 300000000)), (2000, fr.broadcast("ni0XDg")), (32000, fr.broadcast("nS0XDg")),
           (33000, fr.skill_damage(ME, AQ, 200000000)), (34000, fr.skill_damage(ME, AQ, 80000000)),
           (40000, fr.skill_damage(ME, AQ, 30000000)), (40000, fr.vanish(AQ, 1))]
dk = tl.build(combat_of(fr.build(ME, ev_kill)[0]), AQ)
before = [f for t, f in dk["hp"] if t < 40000]
check(dk["killed"] and dk["hp"][-1] == (40000, 0.0) and min(before) >= tl.HP_FLOOR
      and 0.0054 < dk["regen_fit"] < 0.0054 * tl.HP_FIT[1] and abs(before[-1] - 0.03) < 0.002,
      "Aquila morto: a curva de HP fecha na morte (regeneração da luta %.3f%%/s) e fica acima de zero antes -> "
      "%.1f%% antes do último golpe" % (dk["regen_fit"] * 100, before[-1] * 100))
alive = tl.build(combat_of(fr.build(ME, ev_kill[:-2])[0]), AQ)
check(not alive["killed"] and alive["regen_fit"] is None and min(f for _t, f in alive["hp"]) == tl.HP_FLOOR,
      "Aquila vivo: sem ajuste (a regeneração do modelo), e a curva para no piso em vez de zerar")
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


def change_lanes(events, boss):
    d = tl.build(combat_of(fr.build(ME, events)[0]), boss)
    return {l["key"]: [(s, e, lab) for s, e, lab in l["items"]] for l in d["lanes"] if l["key"] in ("bossel", "bosssize")}


# simulador de visuais: catálogo pelo texto do jogo, busca sem acento e looks guardados
import visuals as vis  # noqa: E402
vtbl = {5035: {"ClassNum": 120, "identifiedDescriptionName": {1: "Um chapéu.", 2: "^777777Equipa em:^000000 Topo"}},
        2201: {"ClassNum": 12, "identifiedDescriptionName": {1: "Equipa em: Meio e baixo"}},
        20504: {"ClassNum": 14, "identifiedDescriptionName": {1: "Tipo: Visual", 2: "Equipa em: Capa"}},
        1201: {"ClassNum": 1, "identifiedDescriptionName": {1: "Equipa em: Arma"}},
        607: {"identifiedDescriptionName": {1: "Equipa em: Topo"}},
        9001: {"ClassNum": 999, "identifiedDescriptionName": {1: "Posição: Superior Peso: 0"}}}
vslots = vis.slots_of(vtbl)
vnames = {5035: "Chapéu de Poring", 2201: "Óculos Escuros", 20504: "[Visual] Asas de Cupido", 9001: "Sem Sprite"}
vcat = vis.Catalog(vslots, {i: v["ClassNum"] for i, v in vtbl.items() if "ClassNum" in v}, {120: "a", 12: "b"},
                   {14: "c"}, vnames.get)
check(vslots == {5035: "t", 2201: "ml", 20504: "r", 9001: "t"}
      and vcat.search("top", "chapeu PORING") == [("Chapéu de Poring", 5035, 120)]
      and vcat.search("mid") == vcat.search("low") == [("Óculos Escuros", 2201, 12)]
      and vcat.search("robe", "cupido") == [("[Visual] Asas de Cupido", 20504, 14)] and vcat.count("top") == 1
      and vcat.name_of_view("top", 120) == "Chapéu de Poring" and vcat.name_of_view("top", 7) is None,
      "visuais: posição pelo texto do item, só o que tem sprite no jogo, busca sem acento e sem maiúsculas -> %s"
      % vslots)
vlook = vis.clean({"job": 4302, "sex": 0, "hair": 0, "top": 120.0, "low": "x", "lixo": 5, "mid": True})
check(vlook["job"] == 4302 and vlook["sex"] == 0 and vlook["hair"] == 1 and vlook["top"] == 120 and vlook["low"] == 0
      and vlook["mid"] == 0 and "lixo" not in vlook
      and vis.saved_looks({"looks": {"meu": {"job": 7}, "ruim": 5}}) == {"meu": dict(vis.DEFAULT_LOOK, job=7)},
      "visuais: look guardado só com o que o programa conhece -> %s" % vlook)
# efeitos de chapéu (.str): quadro-chave de base mais o de movimento vezes os quadros, texturas e cores
import streffect as sfx  # noqa: E402
key0 = dict(frame=0, type=0, pos=(320.0, 240.0), xy=(-8.0, 8.0, 8.0, -8.0, -8.0, -8.0, 8.0, 8.0), aniframe=0.0,
            anitype=0, delay=0.0, angle=0.0, color=(255.0, 255.0, 255.0, 200.0), src=5, dst=7)
key1 = dict(key0, type=1, pos=(1.0, -2.0), xy=(0.0,) * 8, angle=4.0, color=(0.0, 0.0, 0.0, -10.0), anitype=3,
            delay=0.5)
lay = dict(tex=["a.bmp", "b.bmp", "c.bmp"], keys=[key0, key1, dict(key0, frame=20)])
st5 = sfx.state(lay, 5)
check(st5["pos"] == (325.0, 230.0) and st5["angle"] == 20.0 and st5["color"][3] == 150.0 and st5["tex"] == 2
      and sfx.state(lay, 19)["pos"] == (339.0, 202.0) and sfx.state(lay, 20) is None      # a última chave encerra
      and sfx.state(dict(tex=[], keys=[]), 3) is None
      and sfx._tex(float("nan"), 3) == 0 and sfx._tex(9.0, 3) == 2,
      "efeitos: o estado da camada num quadro (posição, giro, cor e textura andam um tanto por quadro) -> %s"
      % (st5["pos"], ))
tga = bytes([0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 1, 0, 24, 0x20]) + bytes([10, 20, 30, 40, 50, 60])
rle = bytes([0, 0, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 1, 0, 32, 0x20]) + bytes([0x81, 1, 2, 3, 4])
check(sfx.tga_bgra(tga) == (2, 1, bytes([10, 20, 30, 255, 40, 50, 60, 255]))
      and sfx.tga_bgra(rle) == (2, 1, bytes([1, 2, 3, 4, 1, 2, 3, 4]))
      and sfx.glow(bytes([0, 0, 0, 255, 100, 200, 50, 255])) == bytes([0, 0, 0, 0, 127, 255, 63, 197])
      and sfx.tint(bytes([200, 100, 50, 255]), (128, 255, 255, 64)) == bytes([200, 100, 25, 64]),
      "efeitos: texturas .tga (cruas e comprimidas), o preto das de luz vira transparente e a cor do quadro entra")
wl, wi, wh = dict(vis.DEFAULT_LOOK), {}, {}
ch1 = vis.wear(wl, wi, wh, "mid", ("Andarilho", 900, 77), "tm")
two = (wl["top"], wl["mid"], wi["top"], sorted(wh), wh["mid"])
ch2 = vis.wear(wl, wi, wh, "mid", ("Óculos", 901, 5), "m")          # outro no meio: o de duas posições sai inteiro
after = (wl["top"], wl["mid"], dict(wh))
vis.wear(wl, wi, wh, "low", ("Triplo", 902, 9), "tml")
three = (wl["top"], wl["mid"], wl["low"], sorted(wh))
vis.wear(wl, wi, wh, "top", None)                                    # tirar de uma posição tira de todas
vis.wear(wl, wi, wh, "robe", ("Capa", 903, 4), "r")
check(two == (77, 0, 900, ["mid", "top"], (900, 77, "Andarilho")) and ch1 == {"top", "mid"}
      and after == (0, 5, {}) and "top" in ch2 and three == (9, 0, 0, ["low", "mid", "top"])
      and (wl["top"], wl["mid"], wl["low"], wl["robe"], wh) == (0, 0, 0, 4, {}) and vcat.letters == vslots,
      "visuais: o visual de duas ou três posições ocupa todas e sai de todas junto -> %s %s %s" % (two, after, three))
ON, OFF = (1, 2, 3, 255), (0, 0, 0, 0)
check(vis.tiny_icon(24, 24, [OFF] * 576) and vis.tiny_icon(24, 24, [OFF] * 240 + [ON] * 13 + [OFF] * 323)
      and not vis.tiny_icon(24, 24, [ON] * 576) and not vis.tiny_icon(10, 10, [ON] * 100)
      and vis.tiny_icon(10, 10, [ON] * 80 + [OFF] * 20),
      "visuais: ícone com a parte desenhada de até %d px num dos lados conta como minúsculo" % vis.TINY_ICON)
# Desfazer da aba Visuais: o estado de antes de cada passo vai para a pilha; passo que não muda nada não conta;
# a troca de replay recomeça sem nada para desfazer; no máximo UNDO_MAX passos
hist = vis.History()
hist.reset("a")
hist.record("b")
hist.record("b")                          # nada mudou: não conta
hist.record("c")
u1, u2, u3 = hist.undo(), hist.undo(), hist.undo()
hist.record("d")
after_undo = (hist.now, hist.past)
hist.reset("x")
for k in range(vis.UNDO_MAX + 7):
    hist.record(k)
check((u1, u2, u3) == ("b", "a", None) and after_undo == ("d", ["a"]) and len(hist.past) == vis.UNDO_MAX
      and hist.past[0] == 6 and hist.can_undo() and not vis.History().can_undo(),
      "visuais: Desfazer volta passo a passo, passo sem mudança não conta, guarda até %d -> %s %s"
      % (vis.UNDO_MAX, (u1, u2, u3), after_undo))
vfx = vis.clean({"job": 1, "effects": ["a", 5, "b", "c", "d"]})
check(vfx["effects"] == ["a", "b", "c"] and vis.clean({"effects": "x"})["effects"] == []
      and vis.STONES[25058] == "ljosalfar" and vis.STONES[25138] == vis.SHRINK
      and vis.STONES[25059] == "rl_banishing_buster" and sfx.NUDGE["ljosalfar"] == (5.5, -4.0),
      "visuais: os efeitos do look são nomes (até %d) e as pedras conhecidas apontam para o efeito" % vis.MAX_EFFECTS)
check(vis.fx_key("C_Snow_Powder") == vis.fx_key("HAT_EF_SNOW_POWDER") == "snowpowder"
      and vis.fx_key("C_Romance_Rose_TW") == vis.fx_key("c_romance_rose_tw") and vis.fx_key(None) == ""
      and vis.STONES[25225] == "red_wave" and vis.STONES[25136] == "blue_wave"
      and vis.RESOURCE_FX["C홍염의폭렬파동"] == "red_wave" and set(sfx.EXTRA) == {"red_wave", "blue_wave"},
      "visuais: o nome interno de um visual só de efeito casa com o do efeito; Raios Vermelhos e a Fúria dos Shuras "
      "usam a onda vermelha, Raios Azuis a azul")
check(vis.STONES[1002585] == "digital_space" and sfx.SPRITES["digital_space"][0] == "digital_space\\digital_space"
      and sfx.SPRITES["digital_space"][2] is True and vis.fx_key("C_Digital_Space") == vis.fx_key("digital_space"),
      "visuais: Espaço Digital (a pedra e o Holograma Futurista) é um sprite de efeito, atrás do personagem")
if gdip.ready():
    class _FakeGrf:
        def __init__(self, files):
            self.files = files

        def read(self, name):
            return self.files.get(name)

    hfx = sfx.HatEffects.__new__(sfx.HatEffects)
    hfx.grf = _FakeGrf({"x.spr": spr_bytes(2, 2, [1] * 4, {1: RED}), "x.act": act_bytes((0, -1), (0, -10))})
    built = hfx._build(dict(name="x", sprite="x", ms=120.0, behind=True))
    org = sprites.smooth_frames(body, body.act.frames(sprites.IDLE)[:1], with_origin=True)
    check(built is not None and (built["w"], built["h"], built["cx"], built["cy"]) == (2, 2, 1, 2)
          and len(built["frames"]) == 1 and built["ms"] == 120.0 and built["behind"] is True
          and org is not None and org[3:] == (1, 2)
          and hfx._build(dict(name="y", sprite="y", ms=1.0, behind=False)) is None,
          "efeitos: o efeito de sprite sai com a origem do sprite nos pés do personagem -> %s"
          % (built and (built["w"], built["h"], built["cx"], built["cy"]),))
# chão da prévia: o .gnd do jogo (texturas, superfícies e a de cima de cada quadrado)
import ground as gnd  # noqa: E402
raw_gnd = (b"GRGN" + bytes([1, 7]) + struct.pack("<iifii", 2, 1, 10.0, 2, 8) + b"a.bmp\0\0\0" + b"b.bmp\0\0\0"
           + struct.pack("<iiii", 1, 2, 2, 1) + bytes(16)
           + struct.pack("<i", 1) + struct.pack("<8fhH4B", 0, .5, 0, .5, 0, 0, .5, .5, 1, 0, 255, 255, 255, 255)
           + struct.pack("<4fiii", 0, 0, 0, 0, 0, -1, -1) + struct.pack("<4fiii", 0, 0, 0, 0, -1, -1, -1))
pg = gnd.parse(raw_gnd)
check(pg["w"] == 2 and pg["h"] == 1 and pg["textures"] == ["a.bmp", "b.bmp"] and pg["top"] == [0, -1]
      and pg["tiles"] == [((0.0, 0.5, 0.0, 0.5), (0.0, 0.0, 0.5, 0.5), 1)]
      and vis.STONES[25224] == vis.PALE and vis.STONES[25177] == vis.SHADOW,
      "chão: o terreno do mapa (.gnd) é lido com as texturas, o recorte de cada quadrado e o que fica por cima")
try:
    gnd.parse(raw_gnd[:-5])
    _cut = "leu"
except ValueError:
    _cut = "recusou"
check(_cut == "recusou", "chão: .gnd cortado no meio é recusado (o chão fica de fora em vez de sair torto)")
# índice do .grf: os nomes das pastas pedidas sem diferença de maiúsculas, a pasta que está dentro de outra pedida
# não conta duas vezes, e read() desempacota a entrada guardada em bytes crus
with tempfile.TemporaryDirectory() as tmp:
    gp = os.path.join(tmp, "data.grf")
    fr.build_grf(gp, {"Data\\Texture\\Effect\\Brilho.BMP": b"luz", "data\\texture\\chao.bmp": b"terra",
                      "data\\sprite\\x.spr": b"sprite", "data\\prontera.gnd": b"mapa"})
    _g = sprites.Grf(gp, prefixes=("data\\texture\\effect\\", "data\\texture\\", "data\\prontera.gnd"))
    _gv = sprites.Grf(gp, prefixes=gnd.PREFIXES + sfx.PREFIXES)
    check(sorted(_g.index) == [b"data\\prontera.gnd", b"data\\texture\\chao.bmp", b"data\\texture\\effect\\brilho.bmp"]
          and _g.read("DATA\\texture\\effect\\brilho.bmp") == b"luz" and _g.read("data\\prontera.gnd") == b"mapa"
          and _g.read("data\\sprite\\x.spr") is None and _g.folders == [b"data\\texture\\", b"data\\prontera.gnd"]
          and _g.covers((sfx.EFF, sprites.ITEM_ICON)) and not _g.covers((sprites.HUMAN,))
          and gnd.Ground(gp, _gv).grf is _gv and gnd.Ground(gp, _g).grf is not _g
          and gnd.Ground(gp, _gv).places() == [gnd.PLACES[0]],
          "grf: índice das pastas pedidas (maiúsculas não importam, pasta dentro de outra é coberta); o chão usa um "
          "índice já aberto só se ele cobre todas as pastas dele -> %s" % sorted(_g.index))


def bmp_bytes(w, h, bpp, pixels, palette=(), top_down=False):
    """.bmp de 8 bits (pixels = índices na paleta [(r, g, b)]) ou de 24 bits (pixels = (r, g, b)), listados de cima
    para baixo; o arquivo guarda as linhas de baixo para cima (a não ser top_down), cada uma em múltiplo de 4 bytes."""
    stride = ((w * bpp + 31) // 32) * 4
    rows = []
    for y in range(h):
        row = pixels[y * w:(y + 1) * w]
        line = bytes(row) if bpp == 8 else b"".join(bytes((b, g, r)) for r, g, b in row)
        rows.append(line.ljust(stride, b"\0"))
    if not top_down:
        rows.reverse()
    pal = b"".join(bytes((b, g, r, 0)) for r, g, b in palette)
    off = 54 + len(pal)
    return (b"BM" + struct.pack("<IHHI", off + stride * h, 0, 0, off)
            + struct.pack("<IiiHHIIiiII", 40, w, -h if top_down else h, 1, bpp, 0, stride * h, 0, 0, len(palette), 0)
            + pal + b"".join(rows))


def bmp_reference(data):
    """O BGRA pela leitura pixel a pixel (sprites.bmp_rgba), a conta que a textura do chão usava antes."""
    w, h, px = sprites.bmp_rgba(data)
    return w, h, b"".join(bytes((p[2], p[1], p[0], p[3])) for p in px)


# magenta é transparente: vermelho e azul acima de 240 e verde abaixo de 16 (240 e 16 já não contam)
_pal = [(255, 0, 255), (10, 20, 30), (241, 15, 241), (240, 0, 255), (255, 16, 255)]
_rg2 = _rnd.Random(11)
_bmps = [bmp_bytes(3, 2, 8, [0, 1, 2, 3, 4, 1], _pal), bmp_bytes(3, 2, 8, [4, 3, 2, 1, 0, 0], _pal, top_down=True),
         bmp_bytes(3, 2, 24, _pal + [(1, 2, 3)]), bmp_bytes(5, 3, 24, [tuple(_rg2.choice((0, 15, 16, 240, 241, 255))
                                                                       for _ in range(3)) for _ in range(15)]),
         bmp_bytes(2, 2, 24, _pal[:4], top_down=True)]
_got = [sfx.bmp_bgra(b) for b in _bmps]
check(all(g == bmp_reference(b) for g, b in zip(_got, _bmps)) and _got[0][2][:8] == bytes((255, 0, 255, 0, 30, 20, 10, 255))
      and [_got[2][2][i * 4 + 3] for i in range(6)] == [0, 255, 0, 255, 255, 255],
      "efeitos/chão: textura .bmp de 8 e 24 bits lida em bloco igual à leitura pixel a pixel (magenta transparente, "
      "linhas de baixo para cima ou de cima para baixo, largura ímpar)")
# Betelgeuse: a pontuação da dificuldade anunciada na sala; 925 = HP selado
bet = [(0, fr.broadcast("gQdADQ", 925)), (4000, fr.spawn(60001, "mob", BETEL, "Betelgeuse", boss=2)),
       (5000, fr.skill_damage(ME, 60001, 3000))]
cbp = combat_of(fr.build(ME, bet)[0])
hp925 = an.boss_hp(cbp, 60001, 3000, False)
cb4 = combat_of(fr.build(ME, [(0, fr.broadcast("gQdADQ", 400))] + bet[1:])[0])
check(cbp.boss_points == [(0, 925)] and an.boss_points(cbp, 60001) == 925 and hp925[0] == 500000000
      and hp925[1] == "Selado" and an.boss_points(cb4, 60001) == 400 and an.boss_hp(cb4, 60001, 3000, False)[0] == 800000000,
      "Betelgeuse: 925 pontos anunciados = HP selado (500M); 400 pontos não diz o HP (segue o nível de costume) -> %s"
      % (hp925[:2],))
# linha do tempo: faixas "Propriedade" e "Tamanho" do chefe só nas lutas em que ele troca
ev5 = [(0, fr.spawn(AQ, "mob", 21531, "Aquila", boss=True)), (500, fr.skill_damage(ME, AQ, 1000)),
       (2000, struct.pack("<HIBI", rrf.P_SPRITE, AQ, 0, 21588)),                           # sobrecarga
       (6000, fr.skill_use(AQ, AQ, 168)), (6010, struct.pack("<HIBI", rrf.P_SPRITE, AQ, 0, 21531)),
       (9000, fr.skill_damage(ME, AQ, 1000))]
got = change_lanes(ev5, AQ)
check(list(got) == ["bossel"] and [(s, lab) for s, _e, lab in got["bossel"]][1:] == [(2000, "Neutro 1"), (6010, "Sombrio")]
      and got["bossel"][0][2] == "Neutro 3" and got["bossel"][0][1] == 2000,
      "linha do tempo: propriedade do chefe por trecho; a troca junto com a volta da forma vale na forma nova -> %s"
      % got)
got = change_lanes(ev4 + [(4000, fr.skill_damage(ME, BAPHO, 1000))], BAPHO)
check(list(got) == ["bosssize"] and [(s, lab) for s, _e, lab in got["bosssize"]][1:] == [(2000, "médio")]
      and got["bosssize"][0][2] == "grande",
      "linha do tempo: tamanho do chefe por trecho quando a forma nova tem outro tamanho -> %s" % got)
check(change_lanes([(0, fr.spawn(AQ, "mob", 21531, "Aquila", boss=True)), (500, fr.skill_damage(ME, AQ, 1000)),
                    (3000, fr.skill_damage(ME, AQ, 1000))], AQ) == {},
      "linha do tempo: sem troca de propriedade nem de tamanho, nenhuma das duas faixas aparece")

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
# XP do nível: a que o jogo mandou (no começo desta gravação ou de outra da mesma classe) vale mais que a tabela
seen = {"xp_levels": {"4302": {"240": 777, "241": 12345}}}
got = (xpmod.need(cl, seen, 240), xpmod.need(cl, seen, 241), xpmod.need(cl, {}, 241),
       xpmod.need(cl, {"xp_levels": {"4302": {"241": 999999999}}}, 241))
check(got == (1000, 12345, xpmod.table_need(4302, 241), xpmod.table_need(4302, 241)),
      "XP: a XP do nível que o jogo mandou em outra gravação vale mais que a tabela; a desta gravação vale mais que "
      "todas; o 999999999 do nível máximo não conta -> %s" % (got,))
# penalidade do rAthena: monstro 16+ níveis acima rende 40% (Petite: 1.086 × 40% = 434, como nos bancos de dados)
check(xpmod.penalty(16) == 40 and xpmod.penalty(28) == 40 and xpmod.penalty(15) == 115 and xpmod.penalty(10) == 140,
      "XP: monstro 16 ou mais níveis acima rende 40%")
# o jogo reaproveita o AID (depois de trocar de mapa, outro monstro qualquer): o abate é do monstro que tinha o
# número na hora da morte, e o dano conta só naquela vida
er = [(0, fr.spawn(OTHER, "pc", 4252, "Outro")), (0, fr.spawn(52601, "mob", 1127, "Hode")),
      (300, fr.skill_damage(OTHER, 52601, 5000)), (400, fr.skill_damage(ME, 52601, 5000)), (500, fr.vanish(52601, 1)),
      (5000, fr.spawn(52601, "mob", 1155, "Petite")), (5300, fr.skill_damage(ME, 52601, 5000)),
      (5400, fr.vanish(52601, 1))]
cr = combat_of(fr.build(ME, er, xp=(7204, 0, 10 ** 12))[0])
rr = [(r["mob"], round(r["share"], 2), r["name"]) for r in xpmod.kills(cr)[0]]
check(rr == [(1127, 0.5, meter.monster_name(1127) or "Monstro 1127"), (1155, 1.0, cr.name_of(52601))],
      "XP: AID reaproveitado — o 1º abate é do Hode (com a parte dele: 50%%), o 2º do Petite (100%%, só a vida dele) "
      "-> %s" % rr)
# a entrega que sobe o nível (mesmo instante da subida) é do nível que fechou: não conta de novo no nível novo
eu = []
for i, aid in enumerate((52211, 52212, 52213)):
    eu += [(i * 60000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 60000 + 300, fr.skill_damage(ME, aid, 5000)),
           (i * 60000 + 400, fr.vanish(aid, 1))]
eu += [(150000, fr.quest_done(3477)), (150000, fr.hp(241, rrf.SP_BASELEVEL)), (170000, fr.quest_done(4244))]
cu = combat_of(fr.build(ME, eu, xp=(7201, 0, 10 ** 6))[0])
pu = xpmod.progress(cu, {})
cfg_u = {"xp_mode": "lista"}
xpmod.learn_quests(cu, cfg_u, [(0, 150000, 10 ** 6, "0")])
cu2 = combat_of(fr.build(ME, eu[:9] + [(150000, fr.quest_done(4245)), (150000, fr.hp(241, rrf.SP_BASELEVEL))],
                         xp=(7201, 0, 10 ** 6))[0])
check(pu["level"] == 241 and pu["xp"] == 0 and xpmod.quests_uncounted(cu, {}) == 1
      and xpmod.quests_uncounted(cu2, {}) == 0 and xpmod.quest_in(cu, 0, 150000) and xpmod.quest_in(cu, 150000, 160000)
      and "xp_quests" not in cfg_u,
      "missões: a entrega que subiu o nível conta no nível que fechou e não no novo (nem avisa nele); os dois trechos "
      "em volta saem da calibração e do aprendizado (a sobra não aparece) -> %s" % (pu and round(pu["xp"]),))
# nível em que um abate vale 10%+ do nível (a sobra do abate que subiu passa sem aparecer): fora da medição, ele e
# o seguinte
el2 = []
for i, aid in enumerate((52221, 52222, 52223, 52224)):
    el2 += [(i * 60000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 60000 + 300, fr.skill_damage(ME, aid, 5000)),
            (i * 60000 + 400, fr.vanish(aid, 1))]
el2 += [(100000, fr.hp(241, rrf.SP_BASELEVEL)), (200000, fr.hp(242, rrf.SP_BASELEVEL))]
ce = combat_of(fr.build(ME, el2, xp=(7202, 0, 200))[0])         # nível 240 de 200 de XP: um Goblin (34) vale 17%
check(xpmod.level_segments(ce, {}) == [] and len(xpmod.level_segments(cl, {})) == 1,
      "XP: nível em que um abate vale 10% ou mais dele fica fora da medição, e o seguinte também")
# aprender missões entregues juntas (o total dividido, valendo só quando vêm juntas) e num trecho sem abates
eb = [(1000, fr.quest_done(4246)), (2000, fr.quest_done(4247)), (5000, fr.quest_done(4246))]
cb2 = combat_of(fr.build(ME, eb, xp=(7203, 0, 10 ** 12))[0])
cfg_b = {"xp_mode": "lista"}
xpmod.learn_quests(cb2, cfg_b, [(0, 3000, 1000, "0")])
both = json.loads(json.dumps(cfg_b["xp_quests"]))
alone = xpmod.quest_rows(cb2, cfg_b, (4000, 6000))
together = [r["xp"] for r in xpmod.quest_rows(cb2, cfg_b, (0, 3000))]
xpmod.learn_quests(cb2, cfg_b, [(4000, 6000, 640, "fim")])
obs_b = [(o["quest"], o["base"], o.get("with")) for o in cfg_b["xp_learn"]["quests"]]
check(both == {"4246": {"base": 500, "level": 240, "mult": 1.0, "with": [4247]},
               "4247": {"base": 500, "level": 240, "mult": 1.0, "with": [4246]}}
      and alone[0]["xp"] is None and together == [500, 500]
      and cfg_b["xp_quests"]["4246"] == {"base": 640, "level": 240, "mult": 1.0}
      and cfg_b["xp_quests"]["4247"]["with"] == [4246]
      and obs_b == [(4246, 500, [4247]), (4247, 500, [4246]), (4246, 640, None)]
      and all(o["date"] == "2026-10-22" and o["src"].startswith("#") for o in cfg_b["xp_learn"]["quests"]),
      "missões: duas entregues juntas dividem o total e só valem juntas; sozinha num trecho sem abates (gravar, "
      "entregar e gravar de novo) a recompensa sai exata; cada medida fica anotada no registro de aprendizado -> "
      "%s %s" % (both, obs_b))
# a mesma missão entregue mais de uma vez no trecho (a Água Mineral renova a espera): cada entrega rende inteira
ea = [(1000, fr.quest_done(3477)), (2000, fr.quest_done(3477)), (5000, fr.quest_done(4248)),
      (6000, fr.quest_done(4248))]
ca = combat_of(fr.build(ME, ea, xp=(7205, 0, 10 ** 12))[0])
cfg_a = {"xp_mode": "lista"}
xpmod.learn_quests(ca, cfg_a, [(0, 3000, 2 * 148560 * 1.5, "0"), (4000, 7000, 2 * 1000, "1")])
got = {k: (v["base"], v.get("with")) for k, v in cfg_a["xp_quests"].items()}
check(got == {"3477": (222840, None), "4248": (1000, None)} and len(xpmod.quest_rows(ca, cfg_a, (0, 3000))) == 2,
      "missões: a mesma missão entregue duas vezes no trecho conta nas duas (renovada com Água Mineral) -> %s" % got)
# Zerar depois de um nível que fechou com missão entregue: os abates de antes somem e a missão "aprendia" o nível
# inteiro (1.10.0: um jogador via "já subiu" logo depois de cada entrega dela nas gravações seguintes)
ez = []
for i, aid in enumerate(range(52241, 52243)):                    # 2 Goblins: 68 dos 400 do nível
    ez += [(i * 20000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 20000 + 300, fr.skill_damage(ME, aid, 5000)),
           (i * 20000 + 400, fr.vanish(aid, 1))]
ez += [(100000, fr.quest_done(4249)), (150000, fr.hp(241, rrf.SP_BASELEVEL))]
ez += [(200000 + i * 5000 + d, p) for i, aid in enumerate((52249, 52250)) for d, p in (
    (0, fr.spawn(aid, "mob", 1124, "Goblin")), (300, fr.skill_damage(ME, aid, 5000)), (400, fr.vanish(aid, 1)))]
with tempfile.TemporaryDirectory() as tmpz:
    zp = os.path.join(tmpz, "z.rrf")
    full_z, _o = fr.build(ME, ez, xp=(7206, 0, 400))
    part_z, _o = fr.build(ME, [e for e in ez if e[0] < 180000], xp=(7206, 0, 400))
    with open(zp, "wb") as fh:
        fh.write(part_z)
    rz = meter.ReplayFile(zp)
    rz.poll(max_bytes=1 << 30)
    cfg_z = {"xp_mode": "auto"}
    xpmod.keep_level(rz.combat, cfg_z)
    rz.combat.reset()                                             # Zerar já no nível 241
    with open(zp, "ab") as fh:
        fh.write(full_z[len(part_z):])
    rz.poll(max_bytes=1 << 30)
    xpmod.calibrate(rz.combat, cfg_z, meter.xp_after)
    cn = combat_of(full_z)                                        # a mesma gravação sem o Zerar
    cn.path = zp
    cfg_n = {"xp_mode": "auto"}
    xpmod.calibrate(cn, cfg_n, meter.xp_after)
    learned_n = ((cfg_n.get("xp_quests") or {}).get("4249") or {}).get("base")
check(full_z.startswith(part_z) and "xp_quests" not in cfg_z and learned_n == 332,
      "missões: Zerar depois de um nível fechado com missão não ensina a missão (os abates dele sumiram e ela ficava "
      "valendo o nível inteiro: 'já subiu' a cada entrega) -> sem o Zerar ela vale %s" % learned_n)
# a recompensa que é a XP do nível inteiro (o que a 1.10.0 aprendia depois do Zerar) não vale nem é aprendida
need_240 = xpmod.table_need(4302, 240)
cw2 = combat_of(fr.build(ME, [(100000, fr.quest_done(4249)), (150000, fr.hp(241, rrf.SP_BASELEVEL))],
                         xp=(7207, 0, need_240))[0])
cfg_w = {"xp_mode": "lista"}
xpmod.learn_quests(cw2, cfg_w, [(0, 150000, need_240, "0")])
bad = {"xp_quests": {"3477": {"base": 672904, "level": 94, "mult": 2.0}}}      # Mestre Ferreiro 94, duas entregas
good = {"xp_quests": {"3477": {"base": 253420, "level": 92, "mult": 2.0}}}
# ao vivo, na subida de nível, a missão do nível que fechou já é aprendida (sem esperar a gravação seguinte); cada
# nível uma vez, e a calibração depois troca a anotação em vez de repetir
eq = []
for i, aid in enumerate(range(52251, 52253)):                    # 2 Goblins: 68 dos 400 do nível
    eq += [(i * 20000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 20000 + 300, fr.skill_damage(ME, aid, 5000)),
           (i * 20000 + 400, fr.vanish(aid, 1))]
eq += [(100000, fr.quest_done(4250)), (150000, fr.hp(241, rrf.SP_BASELEVEL))]
cq = combat_of(fr.build(ME, eq, xp=(7208, 0, 400))[0])
cq.path = os.path.join("x", "q.rrf")
cfg_l = {"xp_mode": "auto"}
first_l, again_l = xpmod.learn_levels(cq, cfg_l), xpmod.learn_levels(cq, cfg_l)
learned_l = dict(cfg_l.get("xp_quests") or {})
xpmod.calibrate(cq, cfg_l, None)
check(first_l and not again_l and learned_l.get("4250", {}).get("base") == 332 and cq.quests_learned_upto == 150000
      and cfg_l["xp_quests"]["4250"]["base"] == 332 and [o["src"] for o in cfg_l["xp_learn"]["quests"]] == ["q.rrf#0"],
      "missões: na subida de nível a missão do nível que fechou já é aprendida, uma vez só; a calibração da gravação "
      "depois confere e troca a anotação -> %s" % learned_l)
eb2 = []
for i, aid in enumerate(range(52261, 52269)):                    # nível 240: 8 Goblins (272) e uma missão (128)
    eb2 += [(i * 20000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 20000 + 300, fr.skill_damage(ME, aid, 5000)),
            (i * 20000 + 400, fr.vanish(aid, 1))]
eb2 += [(100000, fr.quest_done(4251)), (150000, fr.hp(241, rrf.SP_BASELEVEL))]
cblind = combat_of(fr.build(ME, eb2, xp=(7212, 0, 400))[0])
cblind.path = os.path.join("x", "cego.rrf")
cfg_blind = {"xp_mode": "auto"}
xpmod.learn_levels(cblind, cfg_blind)
ec = []
for i, aid in enumerate(range(52271, 52283)):                    # nível 240 sem missão: 12 Goblins = 408, a medida
    ec += [(i * 10000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 10000 + 300, fr.skill_damage(ME, aid, 5000)),
           (i * 10000 + 400, fr.vanish(aid, 1))]
ec += [(150000, fr.hp(241, rrf.SP_BASELEVEL))]
for i, aid in enumerate(range(52291, 52303)):                    # nível 241: 12 Goblins (408) e uma missão (192)
    ec += [(200000 + i * 10000, fr.spawn(aid, "mob", 1124, "Goblin")),
           (200000 + i * 10000 + 300, fr.skill_damage(ME, aid, 5000)), (200000 + i * 10000 + 400, fr.vanish(aid, 1))]
ec += [(330000, fr.quest_done(4252)), (350000, fr.hp(242, rrf.SP_BASELEVEL))]
cmeas = combat_of(fr.build(ME, ec, xp=(7213, 0, 408))[0])
cmeas.path = os.path.join("x", "medido.rrf")
cfg_meas = {"xp_mode": "auto", "xp_levels": {"4302": {"241": 600}}}
xpmod.learn_levels(cmeas, cfg_meas)
check("xp_quests" not in cfg_blind and (cfg_meas.get("xp_quests") or {}).get("4252", {}).get("base") == 192,
      "missões: sem medida exata dos abates (evento desmarcado, todo nível com missão) a missão que pesa 32%% do nível "
      "não é aprendida (o erro da lista iria para ela); com um nível sem missão medido antes, é -> %s / %s"
      % (cfg_blind.get("xp_quests"), cfg_meas.get("xp_quests")))
check("xp_quests" not in cfg_w and xpmod.quest_base(3477, bad) == 148560 and xpmod.quest_base(3477, good) == 253420,
      "missões: recompensa aprendida que é a XP do nível inteiro (ou metade, com duas entregas) não vale e não é "
      "aprendida: a tabela volta a valer até a próxima medida -> %s / %s" % (xpmod.quest_base(3477, bad),
                                                                         cfg_w.get("xp_quests")))

# o ritmo do "Até o próximo nível" conta só o tempo caçando: uma pausa de 5 min no meio da janela sai da conta; numa
# caça lenta (um abate por minuto), o intervalo normal entre abates não é pausa
ep = []
for i in list(range(0, 25)) + list(range(54, 67)):                        # um abate a cada 10 s, pausa de 5 min
    aid = 53000 + i
    ep += [(i * 10000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 10000 + 300, fr.skill_damage(ME, aid, 5000)),
           (i * 10000 + 400, fr.vanish(aid, 1))]
cp = combat_of(fr.build(ME, ep, xp=(7209, 0, 10 ** 9))[0])
rp = xpmod.recent_range(cp, {})
pace_p = xpmod.recent_pace(cp, {})
es = []
for i in range(13):                                                       # um abate por minuto, 12 min
    aid = 53100 + i
    es += [(i * 60000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 60000 + 300, fr.skill_damage(ME, aid, 5000)),
           (i * 60000 + 400, fr.vanish(aid, 1))]
cs = combat_of(fr.build(ME, es, xp=(7210, 0, 10 ** 9))[0])
rs = xpmod.recent_range(cs, {})
check(rp == (60400, 660400) and xpmod.active_ms(cp, rp) == 330000 and abs(pace_p - 32 * 34 * 60000 / 330000.0) < 1e-6
      and rs is not None and xpmod.active_ms(cs, rs) == rs[1] - rs[0],
      "XP: o ritmo até o próximo nível conta só o tempo caçando (pausa de 5 min fora); numa caça lenta nada sai -> "
      "%s/min" % (pace_p and round(pace_p, 1)))
# resumo da sessão: as linhas escolhidas, com as contas do widget (subida de nível, abates, mortes, duração)
import cards  # noqa: E402
import session  # noqa: E402
cs_ = combat_of(fr.build(ME, ep + [(670000, fr.hp(241, rrf.SP_BASELEVEL))], xp=(7211, 0, 10 ** 9))[0])
lines_s = [t for t, _col in session.lines(cs_, {"session_fields": ["duration", "levels", "kills", "deaths", "bosses",
                                                                    "favs"]})]
check(lines_s[0].startswith("Gravação de 11:10") and "Subiu de nível: 240 → 241" in lines_s
      and any(t.startswith("Abates: 38") for t in lines_s) and "Mortes: nenhuma" in lines_s
      and not any(t.startswith(("Chefes", "Favoritos")) for t in lines_s)
      and set(session.chosen({})) == set(session.DEFAULT) and len(session.sample_lines({})) == len(session.DEFAULT),
      "resumo da sessão: só as informações escolhidas que têm o que dizer (sem chefe nem favorito, a linha some) -> %s"
      % lines_s)
check(cards.parse_secs("45") == 45 and cards.parse_secs("1:30") == 90 and cards.parse_secs("90 s") == 90
      and cards.parse_secs("2,5") == 2 and cards.parse_secs("x") is None and cards.parse_secs("9999", 1, 600) == 600,
      "cartões: segundos digitados (45, 1:30, 90 s) para o temporizador e o \"segundos antes\"")
# destaques do resumo: o primeiro vira o título (Subiu de nível, com confete); o subtítulo diz onde caçou; os
# desligados na aba Cartões não aparecem; instância pelo nome que o jogo dá a ela
hl_s = session.highlights(cs_, {})
sub_s = session.subtitle(cs_, {"session_fields": ["duration"]})
hl_off = [h["key"] for h in session.highlights(cs_, {"session_hl_off": ["levelup"]})]
check([h["key"] for h in hl_s][:1] == ["levelup"] and hl_s[0]["fx"] == "confetti" and hl_s[0]["chip"].endswith("240 → 241")
      and " caçando em " in sub_s and "levelup" not in hl_off and session.place("0q83@ch_t") == "Constellation Tower"
      and session.place("ve_fild07") == "ve_fild07" and session.subtitle(cs_, {"session_fields": ["xp"]}) == "",
      "resumo da sessão: o destaque vira o título (Subiu de nível, com confete); o subtítulo diz onde caçou; a "
      "instância aparece pelo nome do jogo -> %s / %s" % ([h["key"] for h in hl_s], sub_s))
# nível máximo: chegar ao 250 numa 4ª classe (a gravação de teste é de um Mestre Celestial) vira o "Nível máximo", na
# frente de tudo e sem o "Subiu de nível"; desligado na aba Cartões, volta o "Subiu de nível"
cs_max = combat_of(fr.build(ME, ep + [(670000, fr.hp(250, rrf.SP_BASELEVEL))], xp=(7212, 0, 10 ** 9))[0])
hl_max = session.highlights(cs_max, {})
hl_max_off = [h["key"] for h in session.highlights(cs_max, {"session_hl_off": ["maxlevel"]})]
check([h["key"] for h in hl_max][:1] == ["maxlevel"] and "levelup" not in [h["key"] for h in hl_max]
      and hl_max[0]["rise"]["level"] == 250 and hl_max[0]["rise"]["prev"] == 249 and hl_max[0]["fx"] == "maxlevel"
      and hl_max_off[:1] == ["levelup"] and [h["key"] for h in hl_s][:1] == ["levelup"]
      and xpmod.max_level(4302) == 250 and xpmod.max_level(4054) == 200 and xpmod.max_level(1) == 99
      and xpmod.max_level(99999) is None and "maxlevel" in session.SHORT_OK and session.HL_KEYS[0] == "maxlevel",
      "resumo da sessão: chegar ao nível máximo da classe (250 na 4ª classe) vira o \"Nível máximo\", na frente e sem "
      "o \"Subiu de nível\"; desligado, volta o \"Subiu de nível\" -> %s" % [h["key"] for h in hl_max])
# o nível máximo de cada tipo de classe (conferido nas 257 gravações em 2026-11-20: quem grava e os outros jogadores
# têm sempre o código da classe; montado, só as opções mudam, então os códigos de montaria do cliente não aparecem)
MAX_BY_KIND = {99: [0, 1, 7, 10, 13, 23, 24, 25, 4001, 4008, 4011, 4014, 4023, 4030, 4045, 4046, 4047, 4048, 4049,
                    4222, 4225, 4228],
               200: [4054, 4060, 4064, 4080, 4096, 4190, 4191, 4211, 4212, 4215, 4218, 4220, 4223, 4229, 4239, 4240,
                     4241, 4243],
               250: [4252, 4253, 4258, 4262, 4278, 4302, 4303, 4304, 4305, 4306, 4307, 4308, 4316]}
wrong_max = {j: xpmod.max_level(j) for top, jobs in MAX_BY_KIND.items() for j in jobs if xpmod.max_level(j) != top}
check(not wrong_max, "nível máximo por tipo de classe: 99 (1ª, 2ª, trans, bebê, Super Aprendiz, Justiceiro, Ninja, "
      "Taekwon, Mestre Taekwon, Espiritualista), 200 (3ª, 3ª trans e bebê, expandidas, Doram), 250 (4ª e 4ª expandida)"
      " -> erradas: %s" % wrong_max)
# o exemplo do "Nível máximo" na prévia da aba Cartões: sobe do 249 para o 250 com a XP desse nível, sem "Nível agora"
# e "Próximo nível" (o exemplo comum dizia "Subiu de nível: 96 → 97" e 2,9M embaixo de "Nível 250")
ex_max = [t for t, _c in session.sample_card_for({"session_fields": ["xp", "levels", "level_now", "eta", "kills"]},
                                                  "maxlevel")["lines"]]
ex_up = [t for t, _c in session.sample_card_for({"session_fields": ["levels", "level_now"]}, "levelup")["lines"]]
check(len(ex_max) == 3 and "249 → 250" in ex_max[1] and "170B" in ex_max[0] and ex_max[2].startswith("Abates")
      and len(ex_up) == 2 and "96 → 97" in ex_up[0],
      "prévia do \"Nível máximo\": o exemplo sobe do 249 para o 250 com a XP desse nível, sem o nível agora e o "
      "próximo nível; os outros destaques seguem com o exemplo comum -> %s / %s" % (ex_max, ex_up))
# a prévia de uma informação: o cartão de exemplo com a linha dela acesa (a marcada no lugar dela; a desmarcada entra
# na ordem do cartão, para ver como ficaria); a duração vai no subtítulo
cfg_inf = {"session_fields": ["duration", "xp", "kills", "deaths"]}
in_on, in_off = session.sample_card_info(cfg_inf, "kills"), session.sample_card_info(cfg_inf, "xp_hour")
in_dur = session.sample_card_info({"session_fields": ["xp"]}, "duration")
check(in_on["focus"] == 1 and in_on["lines"][1][0].startswith("Abates") and not in_on["focus_off"]
      and len(in_on["lines"]) == 3 and in_off["focus"] == 1 and in_off["lines"][1][0].startswith("XP por hora")
      and in_off["focus_off"] and len(in_off["lines"]) == 4 and in_dur["focus"] == "sub" and in_dur["focus_off"]
      and "ve_fild07" in in_dur["sub"] and in_on["hl"],
      "prévia de uma informação: o exemplo com a linha dela acesa, marcada ou não (a duração no subtítulo) -> %s / %s"
      % ([t for t, _c in in_on["lines"]], [t for t, _c in in_off["lines"]]))
# recordes: a primeira gravação só marca; outra com um golpe maior bate o recorde; contada de novo, continua batendo
# (compara com o de antes dela)
ep_hit = []
for i in range(0, 25):
    aid = 53400 + i
    ep_hit += [(i * 10000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 10000 + 300, fr.skill_damage(ME, aid, 9000)),
               (i * 10000 + 400, fr.vanish(aid, 1))]
cfg_rec = {}
c_r1 = combat_of(fr.build(ME, ep, xp=(7212, 0, 10 ** 9))[0])
c_r1.path = os.path.join("x", "r1.rrf")
c_r2 = combat_of(fr.build(ME, ep_hit, xp=(7212, 0, 10 ** 9))[0])
c_r2.path = os.path.join("x", "r2.rrf")
rec1 = session.update_records(c_r1, cfg_rec)
rec2 = session.update_records(c_r2, cfg_rec)
rec2b = session.update_records(c_r2, cfg_rec)
hl_r = session.highlights(c_r2, {}, records=rec2)
check(rec1 == [] and [r[:3] for r in rec2] == [("hit", 9000.0, 5000.0)] and [r[:3] for r in rec2b] == [("hit", 9000.0, 5000.0)]
      and hl_r and hl_r[0]["key"] == "record" and num(9000) in (hl_r[0]["sub"] or "")
      and session.update_records(c_r1, cfg_rec) == [],
      "resumo da sessão: recorde pessoal (maior golpe do personagem): a primeira gravação só marca; a seguinte com "
      "golpe maior bate; a mesma de novo continua contando -> %s / %s" % (rec2, hl_r and hl_r[0]["sub"]))
# "Chefe derrotado": a cena luta com os golpes de quem grava NO chefe (o Osíris do usuário: o maior 371.759, enquanto
# o maior golpe da sessão, 36M, foi numa Ísis); antes vinham números de mentira (99999)
ev_b = [(0, fr.spawn(53601, "mob", 1029, "Ísis")), (500, fr.skill_damage(ME, 53601, 36000000)),
        (600, fr.vanish(53601, 1)), (1000, fr.spawn(53602, "mob", 1038, "Osíris", boss=True))]
ev_b += [(2000 + i * 3000, fr.skill_damage(ME, 53602, d)) for i, d in enumerate((100000, 150000, 371759, 200000))]
ev_b += [(14000, fr.vanish(53602, 1))]
c_b = combat_of(fr.build(ME, ev_b, xp=(7213, 0, 10 ** 9))[0])
hl_b = [h for h in session.highlights(c_b, {}) if h["key"] == "boss"]
fb = hl_b[0]["fight"] if hl_b else {}
check(hl_b and fb.get("mob") == 1038 and fb.get("hit") == 371759 and abs(fb.get("avg") - 821759 / 4.0) < 1e-6
      and "boss" in session.SHORT_OK and "mvp_card" in session.SHORT_OK and "top_hit" not in session.SHORT_OK,
      "resumo da sessão: \"Chefe derrotado\" luta com os golpes de quem grava no chefe (não com o maior da sessão, "
      "numa Ísis); gravação de menos de 1 min só tem resumo com um acontecimento -> %s" % fb)
# o fim da gravação na hora: o Windows diz quem está com o arquivo aberto (um processo segurando o arquivo aparece;
# depois de fechado, ninguém), sem o programa abrir o arquivo
with tempfile.TemporaryDirectory() as th_:
    fp_ = os.path.join(th_, "g.rrf")
    with open(fp_, "wb") as fh_:
        fh_.write(b"x")
    holder_ = subprocess.Popen([sys.executable, "-c", "import sys, time; f = open(sys.argv[1], 'ab'); "
                                "print('ok', flush=True); time.sleep(30)", fp_], stdout=subprocess.PIPE)
    holder_.stdout.readline()
    held_ = meter.file_holders(fp_)
    holder_.kill()
    holder_.wait()
    time.sleep(0.3)
    free_ = meter.file_holders(fp_)
check(bool(held_) and free_ == set(),
      "fim da gravação: o Restart Manager vê o processo com o arquivo aberto e, fechado, ninguém -> %s / %s"
      % (held_, free_))
# sons da pasta da pessoa: WAV de 8 e 16 bits e de ponto flutuante viram 16 bits, cortados em 10 s; nada de fora da pasta
import sounds as sndmod  # noqa: E402


def _wav(path, tag, ch, rate, bits, frames):
    if tag == 3:
        body = struct.pack("<%df" % (frames * ch), *([0.25] * (frames * ch)))
    elif bits == 8:
        body = bytes([160] * (frames * ch))
    else:
        body = struct.pack("<%dh" % (frames * ch), *([8000] * (frames * ch)))
    fmt_ = struct.pack("<HHIIHH", tag, ch, rate, rate * ch * bits // 8, ch * bits // 8, bits)
    data = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt_)) + fmt_ + b"data" + struct.pack("<I", len(body)) + body
    with open(path, "wb") as fh:
        fh.write(b"RIFF" + struct.pack("<I", len(data)) + data)


with tempfile.TemporaryDirectory() as tsnd:
    _wav(os.path.join(tsnd, "longo.wav"), 1, 2, 8000, 16, 8000 * 12)
    _wav(os.path.join(tsnd, "oito.wav"), 1, 1, 8000, 8, 800)
    _wav(os.path.join(tsnd, "float.wav"), 3, 1, 8000, 32, 800)
    with open(os.path.join(tsnd, "texto.txt"), "w") as fh:
        fh.write("x")
    found_s = sndmod.custom_sounds(tsnd)
    secs_s = {}
    for k, _n in found_s:
        w_ = sndmod.custom_wav(sndmod.custom_path(tsnd, k), 100)
        chn, rate_ = struct.unpack_from("<HI", w_, 22)
        secs_s[k] = round((len(w_) - 44) / float(2 * chn * rate_), 2)
    check([k for k, _n in found_s] == ["file:float.wav", "file:longo.wav", "file:oito.wav"]
          and secs_s == {"file:float.wav": 0.1, "file:longo.wav": 10.0, "file:oito.wav": 0.1}
          and sndmod.custom_path(tsnd, "file:../longo.wav") is None and sndmod.valid("file:x.mp3")
          and not sndmod.valid("nada") and sndmod.label("file:Meu Som.mp3") == "♪ Meu Som"
          and cards.tracked({"trackers": [dict(kind="status", id=730, snd="file:oito.wav")]})[0]["snd"] == "file:oito.wav",
          "sons da pasta: .wav e .mp3 da pasta (não das subpastas), WAV de 8/16/32 bits em 16 bits, cortado em 10 s; "
          "o efeito acompanhado guarda o som da pasta -> %s" % secs_s)
# simulador: "e se fosse no mapa X" — os abates da pessoa no mapa dão a mistura; no próprio mapa, a XP é a do recorte
cfg_m = {"xp_mode": "lista"}
lrn_m = xpmod._learn(cfg_m)
cp.path = os.path.join("x", "m.rrf")
xpmod.log_map_mix(lrn_m, cp, "m.rrf", "2026-11-19 01:00")
here = xpmod.map_key(cp.session.map)
sm_here = xpmod.sim_map(cp, cfg_m, None, here)
mix_r, src_r = xpmod.map_mix(cfg_m, "gef_fild08")
sm_far = xpmod.sim_map(cp, cfg_m, None, "gef_fild08")
check(lrn_m["maps"][here]["recs"]["m.rrf"] == {"1124": 38} and sm_here["source"] == "seus"
      and abs(sm_here["xp"] - sm_here["base_xp"]) < 1e-6 and src_r == "jogo" and 1156 in mix_r
      and sm_far is not None and sm_far["kills"] == 38 and xpmod.sim_map(cp, cfg_m, None, "mapa_que_nao_existe") is None,
      "simulador por mapa: no mapa em que caçou dá a mesma XP; outro mapa usa quantos nascem (/navi do jogo); mapa "
      "desconhecido não simula -> %s / %s" % (sm_here and round(sm_here["xp"]), sm_far and round(sm_far["xp"])))
# a lista do simulador: os mapas novos do LATAM (do /navi) e, no topo, os de nível mais perto do de quem gravou
new_maps = {m: xpmod.map_mix({}, m)[1] for m in ("clock_01", "nif_dun01", "nif_dun02", "amicitia1", "amicitia2",
                                                  "niflheim", "jor_ab02", "bl_ice", "abyss_04")}
top250 = xpmod.sim_maps({}, 250)[:5]
top99 = xpmod.sim_maps({}, 99)[:5]
lv_g = xpmod.map_levels(mix_r)
check(set(new_maps.values()) == {"jogo"} and xpmod.map_title("clock_01") == "Clock Tower Unknown Basement"
      and all(abs(r[3][0] - 250) <= 6 for r in top250) and all(abs(r[3][0] - 99) <= 3 for r in top99)
      and lv_g is not None and (lv_g[1], lv_g[2]) == (59, 79) and len(xpmod.sim_maps({})) > 400
      and xpmod.map_mix({}, "lhz_dun_n")[1] == "rathena",
      "simulador por mapa: Torre do Relógio, Niflheim, Amicitia, Biosfera, Jormungandr vêm do /navi do jogo; a lista "
      "põe no topo os mapas de nível mais perto -> %s / %s" % ([r[0] for r in top250], [r[0] for r in top99]))
# a Biosfera no LATAM é outra versão (nível diferente no /navi do jogo): o simulador avisa; num mapa comum, não
sm_bl = xpmod.sim_map(cp, cfg_m, None, "bl_grass")
sm_ok = xpmod.sim_map(cp, cfg_m, None, "jor_ab02")
check(sm_bl is not None and len(sm_bl["latam_other"]) >= 5 and sm_bl["latam_share"] > 0.5 and not sm_bl["measured"]
      and sm_ok is not None and sm_ok["latam_other"] == [] and xpmod.latam_level(21549) == 251,
      "simulador por mapa: os monstros com outro nível no LATAM (Biosfera) são marcados; jor_ab02 não -> %s"
      % (sm_bl and [(m, a, b) for m, a, b in sm_bl["latam_other"]][:3]))
# a medida num mapa de outra versão (a Biosfera rende uns 15% da lista) vale só para ele: não vira o "normal" do
# personagem (senão todo mapa sem medida sairia com a XP da Biosfera) nem entra na média geral
cfg_f = {"xp_corr": {"777": {"samples": [[1.02, 9e9, "2026-11-18 20:00", "a.rrf#0", "jor_ab02", 1500],
                                         [0.15, 4e9, "2026-11-18 22:00", "b.rrf#0", "bl_lava", 900]]}}}
p_new = xpmod.predict(cfg_f, 777, "abyss_04")
p_bio = xpmod.predict(cfg_f, 777, "bl_lava")
p_other = xpmod.predict(cfg_f, 888, "bl_lava")          # outro personagem sem medida: a do mapa, pelos dele
check([xpmod.foreign_map(m) for m in ("bl_grass", "bl_lava", "bl_ice", "bl_death", "clock_01", "jor_ab02", "")]
      == [True, True, True, True, False, False, False]
      and p_new is not None and p_new[1] == "personagem" and abs(p_new[0] - 1.02) < 1e-9
      and p_bio is not None and p_bio[1] == "mapa" and abs(p_bio[0] - 0.15) < 1e-9
      and p_other is not None and p_other[1] == "personagens" and abs(p_other[0] - 0.15 / 1.02) < 1e-6
      and sm_bl["bio_share"] > 0.9 and sm_ok["bio_share"] == 0,
      "XP: a medida na Biosfera (outra versão no LATAM) vale só para ela, não para o normal do personagem -> %s / %s / %s"
      % (p_new, p_bio, p_other))
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
# as quatro Insígnias no chão ao mesmo tempo, debaixo do chefe: cada uma rende +50% só no elemento que vence o dela
# (Fogo → água, Água → vento, Vento → terra, Terra → fogo) e o crédito das quatro vai para quem as pôs
INSIGNIAS = [(2465, 0xF1), (2466, 0xF2), (2467, 0xF3), (2468, 0xF4)]


def insignia_fight(on=True, skills=(2218, 2219, 2220, 2221)):
    """Quem grava e mais três (2402-2404) batem 1 vez por segundo de 1 a 20 s, cada um com um Tetra Vortex de
    `skills` (fogo, água, vento, terra). Com `on`, as quatro Insígnias do Mestre Elemental ficam sob o chefe de 4,5 a
    15,5 s (11 golpes de cada um), e os golpes desse trecho saem +50%."""
    who = [ME, 2402, 2403, 2404]
    ev = [(0, at(fr.spawn(ABOSS, "mob", 1038, "Chefe", boss=2), 100, 100)), (0, fr.spawn(EM, "pc", 4261, "Elementa")),
          (0, fr.stop(ME, 100, 95))] + [(0, fr.spawn(a, "pc", 4255, "Magus %d" % a)) for a in who[1:]]
    ev += [(100, fr.party_hp(a, 50000, 50000)) for a in [EM] + who]
    if on:
        for i, (skill, kind) in enumerate(INSIGNIAS):
            ev += [(4500, fr.ground_skill(EM, skill, 3, 100, 100)), (15500, fr.ground_gone(8200 + i)),
                   (4500, fr.ground_area(8200 + i, EM, 100, 100, kind, 3, 1))]
    for k in range(20):
        t = 1000 + k * 1000
        ev += [(t, fr.skill_damage(a, ABOSS, AHIT * 3 // 2 if on and 4500 <= t <= 15500 else AHIT, skill=s, hits=1))
               for a, s in zip(who, skills)]
    ev += [(20500, fr.vanish(ABOSS, 1))]
    return combat_of(fr.build(ME, sorted(ev, key=lambda e: e[0]))[0])


c4 = insignia_fight()
rows4, total4 = contrib.fight(c4, ABOSS)
by4 = {r["key"]: r for r in rows4}
crows4, _t4 = contrib.credit(c4, ABOSS)
cb4 = {r["aid"]: r for r in crows4}
check(sorted(a["skill"] for a in c4.areas) == [2465, 2466, 2467, 2468]
      and all(c4.area_spans(a) == [(4500, 15500)] and c4.in_area(a, (100, 100), 10000) for a in c4.areas)
      and all(round(by4[-sk]["contrib"]) == 11 * AHIT // 2 and by4[-sk]["hits"] == 11 and by4[-sk]["where"] == "boss"
              and "+50%% no dano de %s" % dd.ELEMENT_PT[contrib.AREAS[-sk][1]].lower() in by4[-sk]["rule"]
              for sk, _k in INSIGNIAS)
      and [contrib.AREAS[-sk][1] for sk, _k in INSIGNIAS] == ["Water", "Wind", "Earth", "Fire"]
      and round(cb4[EM]["total"]) == 4 * 11 * AHIT // 2 and sorted(cb4[EM]["via"]) == [-2468, -2467, -2466, -2465]
      and all(round(cb4[a]["own"]) == 20 * AHIT and not cb4[a]["via"] for a in (ME, 2402, 2403, 2404))
      and abs(sum(r["total"] for r in crows4) - total4) < 1,
      "as quatro Insígnias ao mesmo tempo: +50%% só no elemento que vence cada uma; crédito das quatro para quem pôs "
      "-> %s" % {contrib.effect_name(k): round(v) for k, v in cb4[EM]["via"].items()})
r4 = dd.analyze(c4, ABOSS)
dd4 = {d["key"]: d for d in r4["debuffs"] if d["key"].startswith("area|")}
l4 = {l["key"]: l for l in tl.build(c4, ABOSS)["lanes"] if l.get("area")}
check(sorted(dd4) == ["area|2465", "area|2466", "area|2467", "area|2468"] and len({d["p1"] for d in dd4.values()}) == 1
      and all(d["who"] == "Elementa" for d in dd4.values())
      and sorted(l4) == ["ar2465", "ar2466", "ar2467", "ar2468"] and all(l["items"] == [(4500, 15500)] for l in l4.values())
      and len({l["color"] for l in l4.values()}) == 4,
      "as quatro Insígnias no Dedo Duro e na linha do tempo, cada uma com a sua cor -> %s" % {
          k: d["p1"] for k, d in dd4.items()})
wal = {a["what"]: a for a in dd.analyze(insignia_fight(on=False, skills=(2219,) * 4), ABOSS)["alerts"]}
check(wal.get("Insígnia do Fogo faltou", {}).get("sev") == 1 and "água" in wal["Insígnia do Fogo faltou"]["detail"]
      and "Insígnia da Terra faltou" not in wal and "Insígnia da Água faltou" not in wal,
      "Dedo Duro: grupo batendo com água sem a Insígnia do Fogo é alerta amarelo (as outras não são cobradas) -> %s" % (
          sorted(k for k in wal if "faltou" in k)))

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

# o "Curar" do monstro (NPC_DAMAGE_HEAL 753, nele mesmo): por 30 s o dano físico (1), mágico (2) ou especial (3) vira
# cura. O uso chega em dois pacotes iguais (um aviso só); outro monstro que não é chefe, ou o uso em outro, não avisa
ev = [(0, fr.spawn(ABOSS, "mob", 1785, "Atroce", boss=2)), (0, fr.spawn(MOB, "mob", 1002, "Poring")),
      (1000, fr.skill_use(ABOSS, ABOSS, 753, level=1)), (1000, fr.skill_use(ABOSS, ABOSS, 753, level=1)),
      (40000, fr.skill_use(ABOSS, ABOSS, 753, level=2)), (80000, fr.skill_use(ABOSS, ABOSS, 753, level=3)),
      (90000, fr.skill_use(MOB, MOB, 753, level=1)), (95000, fr.skill_use(ABOSS, ME, 753, level=1)),
      (99000, fr.skill_damage(ME, ABOSS, 1000, hits=1))]
chl = combat_of(fr.build(ME, ev)[0])
heal = [(b["t"], b["mech"], cards.boss_card_key(b)) for b in sorted(chl.boss_alerts.values(), key=lambda b: b["t"])
        if b.get("mech")]
check(heal == [(1000, "heal_phys", "damage_heal"), (40000, "heal_magic", "damage_heal"),
               (80000, "heal_misc", "damage_heal")]
      and any("dano físico vira cura por 30 s" in a[3] for a in chl.alerts),
      "Curar do chefe: dano físico, mágico e especial viram aviso (o pacote repetido, uma vez só) -> %s" % heal)
check(cards.enabled({}, "damage_heal") and not cards.enabled({"cards_off": ["damage_heal"]}, "damage_heal")
      and not cards.enabled({"alert_boss": False}, "damage_heal"),
      "Curar do chefe: o cartão liga e desliga na aba Cartões e com os outros avisos do chefe")
_p114 = r"C:\Gravity\Ragnarok\Replay\RagnarokReplay_0114.rrf"
if os.path.isfile(_p114):
    _rf = meter.ReplayFile(_p114)
    while _rf.poll():
        pass
    _h = [(round(b["t"] / 1000.0, 1), b["mech"]) for b in _rf.combat.boss_alerts.values()
          if (b.get("mech") or "").startswith("heal")]
    check(_h == [(544.5, "heal_phys"), (587.1, "heal_phys"), (621.8, "heal_phys")],
          "RagnarokReplay_0114: o Atroce do Laboratório converteu o dano físico em cura 3 vezes -> %s" % _h)
else:
    print("pula  RagnarokReplay_0114.rrf (nao encontrado)")

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
qr = xpmod.quest_rows(cq, {})
eq = xpmod.estimate(cq, {})
check([(h["quest"], h["parts"]) for h in hq] == [(7777, [(3, 10)])] and 5964 not in cq.quest_hunts,
      "missões: o progresso da caça aparece e some quando a missão é entregue -> %s" % hq)
check([q["quest"] for q in qr] == [5964, 4242] and qr[0]["mult"] == 2.5 and qr[0]["xp"] == 698346800 * 2.5
      and qr[1]["xp"] is None and eq["quest_xp"] == 1745867000 and eq["xp"] == 1745867000 and eq["kill_xp"] == 0
      and eq["quests_unknown"] == 1 and eq["per_min"] == 0 and xpmod.quests_uncounted(cq, {}) == 1,
      "missões: a XP do Jantar do Diabo (tabela) entra na estimativa com manual 100%% e Kafra (×2,5), fora do ritmo "
      "dos abates; a de recompensa desconhecida fica de fora e a tela avisa -> %s"
      % [(q["quest"], q["mult"], q["xp"]) for q in qr])
check(xpmod.quest_base(4242, {"xp_quests": {"4242": {"base": 1000}}}) == 1000 and xpmod.quest_base(4242, {}) is None
      and xpmod.quest_base(5964, {"xp_quests": {"5964": {"base": 7}}}) == 7,
      "missões: a recompensa aprendida vale no lugar da tabela")
# bônus da missão: (1 + manual + Kafra) × Njord × Milagre; evento, VIP, Cetro, itens e spotlight não entram
# (Jantar do Diabo capturado: 698.346.800 do iRO Wiki -> 5.586.774.400 com manual 100, Kafra, Njord e Milagre = ×8;
# três diárias de Hugel com manual 50 e Kafra pagaram ×1,94 sobre o iRO Wiki)
on = [(0, 10 ** 9, 0)]
qw = {"vip": on, "scepter": on, "kafra": on, "manual": [(0, 10 ** 9, 100)], "njord": [(0, 10 ** 9, 60)],
      "gear": [(0, 10 ** 9, 65)], "miracle": on, "spot": [(0, 10 ** 9, 20)]}
qs4 = xpmod.settings({"xp_bonuses": {"server": {"on": True, "pct": 100}}})
qw_h = {"vip": on, "scepter": on, "kafra": on, "manual": [(0, 10 ** 9, 50)], "gear": [(0, 10 ** 9, 15)]}
got = (xpmod.quest_mult(1000, qw, qs4), xpmod.quest_mult(1000, qw_h, qs4),
       xpmod.quest_base(3477, {}), xpmod.quest_base(8663, {}), xpmod.quest_base(8665, {}), xpmod.quest_base(5964, {}))
check(got == (8.0, 2.0, 148560.0, 165480.0, 165480.0, 698346800.0) and round(698346800 * got[0]) == 5586774400,
      "missões: bônus de missão = (1 + manual + Kafra) × Njord × Milagre, sem evento, VIP, Cetro, itens nem "
      "spotlight; Sociedade de Monstros pela tabela (a 8663 do LATAM é a 8665 do rAthena) -> %s" % (got,))
# missão de espera ("[Espera] Refeição do Diabo"): sai da lista sem dar XP, não é entrega nem tira o trecho da calibração
ew = [(0, fr.spawn(52401, "mob", 1124, "Goblin")), (300, fr.skill_damage(ME, 52401, 5000)), (400, fr.vanish(52401, 1)),
      (1000, fr.quest_done(5961))]
cw2 = combat_of(fr.build(ME, ew, xp=(7101, 0, 10 ** 12))[0])
check(xpmod.quest_wait(5961) and xpmod.quest_rows(cw2, {}) == [] and xpmod.quests_uncounted(cw2, {}) == 0
      and not xpmod.quest_in(cw2, 0, 2000) and xpmod.quest_in(cq, 0, 70000),
      "missões: o fim de uma espera não é entrega (não avisa nem tira o trecho da calibração)")
# aprender: real − abates − outras missões; a desconhecida aprende, a conhecida só muda se errar mais de 15%
el = [(0, fr.spawn(52411, "mob", 1124, "Goblin")), (300, fr.skill_damage(ME, 52411, 5000)), (400, fr.vanish(52411, 1)),
      (1000, fr.quest_done(4242)),
      (2000, fr.spawn(52412, "mob", 1124, "Goblin")), (2300, fr.skill_damage(ME, 52412, 5000)), (2400, fr.vanish(52412, 1)),
      (2500, fr.quest_done(3477))]
cl2 = combat_of(fr.build(ME, el, xp=(7102, 0, 10 ** 12))[0])
k1, k2 = xpmod._list_xp(cl2, {}, (0, 1500)), xpmod._list_xp(cl2, {}, (1900, 3000))
cfg_q = {"xp_mode": "lista"}
xpmod.learn_quests(cl2, cfg_q, [(0, 1500, k1 + 900, "0"), (1900, 3000, k2 + 148560 * 1.1, "1")])
learned1 = dict(cfg_q["xp_quests"])
xpmod.learn_quests(cl2, cfg_q, [(1900, 3000, k2 + 148560 * 1.5, "1")])
check(k1 and k2 and learned1 == {"4242": {"base": 900, "level": 240, "mult": 1.0}}
      and cfg_q["xp_quests"]["3477"]["base"] == round(148560 * 1.5),
      "missões: aprende a recompensa desconhecida (900); a da tabela fica se o medido conferir (+10%%) e é trocada "
      "se errar mais (+50%%) -> %s %s" % (learned1, cfg_q.get("xp_quests")))
mq = xpmod._measure_log(cq, {}, 0, 70000, 1000, 1.0, "m", "x#0", "2026-11-17 10:00")
check(mq["quests"] == [5964, 4242] and mq["quest_at"] == [[5964, {"manual": 100, "kafra": 50}],
                                                          [4242, {"manual": 100, "kafra": 50}]],
      "registro de aprendizado: cada entrega de missão leva os bônus ativos no instante (manual 100%% e Kafra) -> %s"
      % mq.get("quest_at"))
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
    check(xpmod.settings(cfga, rfa.combat)["server"] == {"on": True, "pct": 200.0}
          and cfga["xp_server_band"] == {"200+": {"on": True, "pct": 200, "auto": True}} and corr == 1.0
          and round(esta["xp"]) == 333 and esta["source"][0] == "medido",
          "XP automática: o evento do servidor (+200%%) sai da XP exata e a lista fecha sozinha -> %s %s" % (
              cfga.get("xp_server_band"), corr))
    cfgl = {"xp_mode": "lista"}
    xpmod.calibrate(rfa.combat, cfgl, meter.xp_after)
    check("xp_bonuses" not in cfgl, "XP: no modo \"pela lista\" o programa não mexe no evento do servidor")
# mapa que rende mais (spotlight): a mesma gravação (111 pela lista), mas a seguinte mostra +133 = lista × 1,20
for tag, gain in (("spot", 133), ("plain", 111)):
    with tempfile.TemporaryDirectory() as tmp3:
        for name, date, exp, events in (("a.rrf", (2026, 11, 5, 19, 35, 0), 1000, ev),
                                        ("b.rrf", (2026, 11, 5, 19, 45, 40), 1000 + gain, [])):
            with open(os.path.join(tmp3, name), "wb") as f:
                f.write(fr.build(ME, events, date=date, xp=(7100, exp, 10 ** 9))[0])
        rfs = meter.ReplayFile(os.path.join(tmp3, "a.rrf"))
        rfs.poll(max_bytes=1 << 30)
        here = xpmod.map_key(rfs.combat.map)
        if tag == "spot":
            cfgs = {}
            corr = xpmod.calibrate(rfs.combat, cfgs, meter.xp_after)
            ests = xpmod.estimate(rfs.combat, cfgs)
            check(not cfgs.get("xp_spot") and "xp_bonuses" not in cfgs and abs(corr - 133 / 111.0) < 0.01
                  and round(ests["xp"]) == 133 and cfgs["xp_corr"]["7100"]["samples"][0][4] == here
                  and xpmod.own_samples(rfs.combat, cfgs) == 1,
                  "XP automática: XP exata = lista × 1,20 vira a correção deste mapa (nenhuma marca de mapa, e o "
                  "evento do servidor fica como está) -> %s %s" % (cfgs.get("xp_spot"), corr))
            lst = xpmod.estimate(rfs.combat, {"xp_mode": "lista", "xp_spot": {here.upper(): {"pct": 20}}})["xp"]
            off = xpmod.estimate(rfs.combat, {"xp_mode": "lista", "xp_spot": {here: {"pct": 20}},
                                              "xp_bonuses": {"spot": {"on": False, "pct": 20}}})["xp"]
            other = xpmod.estimate(rfs.combat, {"xp_mode": "lista", "xp_spot": {"outro_mapa": {"pct": 20}}})["xp"]
            check(abs(lst - 111 * 1.2) < 1e-6 and round(off) == 111 and round(other) == 111,
                  "XP: o spotlight multiplica tudo, só no mapa marcado e só com o bônus ligado -> %s %s %s"
                  % (lst, off, other))
        else:
            cfgu = {"xp_spot": {here: {"pct": 20, "when": "2026-11-01", "auto": True}}}
            xpmod.calibrate(rfs.combat, cfgu, meter.xp_after)
            cfgk = {"xp_spot": {here: {"pct": 20, "when": "2026-11-01", "auto": False}}}
            xpmod.calibrate(rfs.combat, cfgk, meter.xp_after)
            check(not cfgu.get("xp_spot") and here in cfgk["xp_spot"],
                  "XP automática: a marca de spotlight posta pelo programa (versões anteriores) sai; a feita à mão "
                  "fica -> %s %s" % (cfgu.get("xp_spot"), cfgk.get("xp_spot")))
# spotlight de +50% (mapas de nível mais baixo): com o evento do servidor em 50% a lista dá 166,5; +250 = x1,5
with tempfile.TemporaryDirectory() as tmp5:
    for name, date, exp, events in (("a.rrf", (2026, 11, 5, 19, 35, 0), 1000, ev),
                                    ("b.rrf", (2026, 11, 5, 19, 45, 40), 1000 + 250, [])):
        with open(os.path.join(tmp5, name), "wb") as f:
            f.write(fr.build(ME, events, date=date, xp=(7100, exp, 10 ** 9))[0])
    rf5 = meter.ReplayFile(os.path.join(tmp5, "a.rrf"))
    rf5.poll(max_bytes=1 << 30)
    here5 = xpmod.map_key(rf5.combat.map)
    cfg5 = {"xp_bonuses": {"server": {"on": True, "pct": 50}}}
    xpmod.calibrate(rf5.combat, cfg5, meter.xp_after)
    cfg6 = {"xp_bonuses": {"server": {"on": True, "pct": 50}},
            "xp_spot": {here5: {"pct": 20, "when": "2026-11-01", "auto": True}}}
    xpmod.calibrate(rf5.combat, cfg6, meter.xp_after)
    cfg7 = {"xp_bonuses": {"server": {"on": True, "pct": 50}},
            "xp_spot": {here5: {"pct": 20, "when": "2026-11-01", "auto": False}}}
    xpmod.calibrate(rf5.combat, cfg7, meter.xp_after)
    custom = xpmod.estimate(rf5.combat, {"xp_mode": "lista", "xp_spot": {here5: {"pct": 75}}})["xp"]
    c5 = xpmod.stored_correction(rf5.combat, cfg5, here5)
    c6 = xpmod.stored_correction(rf5.combat, cfg6, here5)
    c7 = xpmod.stored_correction(rf5.combat, cfg7, here5)
    check(not cfg5.get("xp_spot") and xpmod.settings(cfg5, rf5.combat)["server"]["pct"] == 50
          and abs(c5[0] - 250 / 166.5) < 1e-3
          and not cfg6.get("xp_spot") and abs(c6[0] - 250 / 166.5) < 1e-3
          and cfg7["xp_spot"][here5]["pct"] == 20 and abs(c7[0] - 250 / (166.5 * 1.2)) < 1e-3
          and abs(custom - 111 * 1.75) < 1e-6 and 20.0 in xpmod.SPOT_CHOICES and 50.0 in xpmod.SPOT_CHOICES,
          "XP automática: mapa que rende +50%% aprende ×1,5 (o evento do servidor fica); a marca automática antiga "
          "sai, a feita à mão fica e a correção é sobre ela; qualquer %% digitado vale -> %s %s %s" % (c5, c6, c7))
# cada abate usa a correção do mapa em que aconteceu; mapa sem medida usa o normal do personagem (o grupo de mapas
# que rendem menos: o spotlight só aumenta a XP)
cfgm = {"xp_mode": "medido", "xp_corr": {"7300": {"samples": [
    [2.0, 100, "2026-11-05 10:00", "x#0", "prt_fild08"], [1.0, 100, "2026-11-05 10:00", "y#0", "outro_mapa"]]}}}
evm2 = []
for i, aid in enumerate((53101, 53102)):
    evm2 += [(i * 60000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 60000 + 300, fr.skill_damage(ME, aid, 5000)),
             (i * 60000 + 400, fr.vanish(aid, 1))]
evm2.insert(3, (30000, fr.map_move("pay_fild01", 100, 100)))
cmm = combat_of(fr.build(ME, evm2, xp=(7300, 0, 10 ** 9))[0])
rows_m = [r["total"] for r in xpmod.estimate(cmm, cfgm)["rows"]]               # as linhas são as mesmas a cada
lst_m = [r["total"] for r in xpmod.estimate(cmm, dict(cfgm, xp_mode="lista"))["rows"]]   # conta: copiar o total
ratios_m = [round(a / b, 3) for a, b in zip(rows_m, lst_m)]
check(ratios_m == [2.0, 1.0] and xpmod.correction(cmm, cfgm) == (1.0, 2) and xpmod.own_samples(cmm, cfgm) == 0
      and xpmod.map_corrections(cmm, cfgm) == {"prt_fild08": 2.0, "outro_mapa": 1.0}
      and xpmod.correction_kind(cmm, cfgm) == "personagem",
      "XP: cada abate usa a correção do mapa em que aconteceu (prt_fild08 ×2); mapa sem medida usa o normal do "
      "personagem (×1, o mapa que rende menos) -> %s %s" % (ratios_m, xpmod.correction(cmm, cfgm)))
# o mapa medido por outro personagem vale para este: quanto ele rende a mais sobre o normal de quem mediu
cfg_x = {"xp_corr": {
    "1": {"samples": [[1.5, 100, "2026-11-05 10:00", "a#0", "mapa_x", 300], [1.0, 100, "2026-11-05 11:00", "b#0",
                                                                             "mapa_y", 300]]},
    "2": {"samples": [[1.1, 100, "2026-11-05 12:00", "c#0", "mapa_y", 300]]}}}
p_b = xpmod.predict(cfg_x, 2, "mapa_x")
p_c = xpmod.predict(cfg_x, 3, "mapa_x")
p_a = xpmod.predict(cfg_x, 1, "mapa_z")
check(p_b[1] == "personagens" and abs(p_b[0] - 1.65) < 1e-9 and p_c[1] == "personagens" and abs(p_c[0] - 1.5) < 1e-9
      and p_a == (1.0, "personagem", 2) and xpmod.predict(cfg_x, 3, "mapa_z") is None,
      "XP: mapa medido por outro personagem vale para este (o outro rende ×1,5 nele sobre o normal; este, normal "
      "×1,1, fica ×1,65; sem medida nenhuma, ×1,5) -> %s %s %s" % (p_b, p_c, p_a))
# memória longa (30 dias) e mudança no mapa: medida nova que discorda das antigas do mapa apaga as antigas
cfg_k = {"xp_corr": {"1": {"samples": [[1.0, 100, "2026-11-01 10:00", "a#0", "mapa_x", 300],
                                       [1.0, 100, "2026-11-02 10:00", "b#0", "mapa_y", 300]]},
                     "2": {"samples": [[1.02, 100, "2026-11-03 10:00", "c#0", "mapa_x", 300]]}}}
same = xpmod._check_change(cfg_k, 1, [1.05, 100, "2026-11-20 10:00", "d#0", "mapa_x", 300])
moved = xpmod._check_change(cfg_k, 1, [1.25, 100, "2026-11-21 10:00", "e#0", "mapa_x", 300])
left = sorted((g, x[3]) for g, e in cfg_k["xp_corr"].items() for x in e["samples"])
old40 = {"xp_corr": {"1": {"samples": [[2.0, 100, "2026-10-01 10:00", "x#0", "m"],
                                       [1.0, 100, "2026-11-05 10:00", "y#0", "m"]]}}}
check(not same and moved and left == [("1", "b#0")] and cfg_k["xp_learn"]["changes"][-1]["map"] == "mapa_x"
      and xpmod.predict(old40, 1, "m") == (1.0, "mapa", 1),
      "XP: memória de 30 dias; medida nova 25%% acima das antigas do mapa = o mapa mudou: as antigas dele saem (de "
      "todos os personagens) e a mudança vai para o registro -> %s" % left)
# proteções da calibração (estudo de 2026-11-21): a medida que discorda das do mapa sem provar a mudança entra junto
cfg_f = {"xp_corr": {"1": {"samples": [[1.0, 100, "2026-11-01 10:00", "a#0", "mapa_x", 300]]},
                     "2": {"samples": [[1.02, 100, "2026-11-03 10:00", "c#0", "mapa_x", 300]]}}}
kept = xpmod._check_change(cfg_f, 1, [1.25, 100, "2026-11-21 10:00", "e#0", "mapa_x", 300], keep=lambda: True)
left_f = sorted(x[3] for e in cfg_f["xp_corr"].values() for x in e["samples"])
check(not kept and left_f == ["a#0", "c#0"],
      "XP: medida que discorda do mapa sem provar a mudança (frágil, replay aberto à mão) não apaga as dele -> %s"
      % left_f)
with tempfile.TemporaryDirectory() as tmp:
    def guard_rec(name, date, exp, events, gid=7300):
        data, _off = fr.build(ME, events, date=date, xp=(gid, exp, 50000))
        with open(os.path.join(tmp, name), "wb") as f:
            f.write(data)
        rf_ = meter.ReplayFile(os.path.join(tmp, name))
        rf_.poll(max_bytes=1 << 30)
        return rf_.combat

    def goblins(base):
        ev = []
        for i in range(6):                     # um abate por minuto, de 0:30 a 5:30
            t, aid = 30000 + i * 60000, base + i
            ev += [(t - 400, fr.spawn(aid, "mob", 1124, "Goblin")), (t - 100, fr.skill_damage(ME, aid, 5000)),
                   (t, fr.vanish(aid, 1))]
        return ev
    late = guard_rec("tarde.rrf", (2026, 11, 6, 10, 0, 0), 1000,
                     goblins(53001) + [(60000, fr.status(ME, 250, True, 1800000, 1800000, val1=100))])
    early = guard_rec("cedo.rrf", (2026, 11, 6, 12, 0, 0), 1000,
                      goblins(53101) + [(0, fr.status(ME, 250, True, 1800000, 1800000, val1=100))])
    s_late, s_early = xpmod.timing_sensitivity(late, {}, (0, late.now)), xpmod.timing_sensitivity(early, {}, (0, early.now))
    check(abs(s_late + 2 / 11.0) < 1e-9 and s_early == 0.0,
          "XP: manual de +100%% ligando no 1º minuto: com os bônus 2 min depois a lista do trecho cai 2/11 (medida "
          "frágil); manual já ativo no começo: nada muda -> %.4f %.4f" % (s_late, s_early))
    xk, mk = xpmod.kills(late)[0][0]["xp"], xpmod._kill_map(late, 0, late.now)
    guard_rec("tarde2.rrf", (2026, 11, 6, 10, 6, 0), int(1000 + 22 * xk), [])     # 30 s depois: razão 2,0 e 1,83
    guard_rec("cedo2.rrf", (2026, 11, 6, 12, 6, 0), int(1000 + 22 * xk), [])

    def old_samples(mode="medido"):            # medidas antigas do mapa a ×1,0: deste personagem e de outro
        return {"xp_mode": mode, "xp_corr": {"7300": {"samples": [[1.0, 500, "2026-11-05 09:00", "velha#0", mk, 300]]},
                                             "7301": {"samples": [[1.0, 500, "2026-11-05 09:30", "outro#0", mk, 300]]}}}

    def names(cfg):
        return sorted(x[3] for e in cfg["xp_corr"].values() for x in e["samples"])
    cf_late, cf_early = old_samples(), old_samples()
    xpmod._CACHE.clear()
    xpmod.calibrate(late, cf_late, meter.xp_after)
    xpmod._CACHE.clear()
    xpmod.calibrate(early, cf_early, meter.xp_after)
    check(names(cf_late) == ["outro#0", "tarde.rrf#fim", "velha#0"] and names(cf_early) == ["cedo.rrf#fim"],
          "XP: medida frágil (manual ligando no meio) que discorda do mapa entra sem apagar as outras; a firme que "
          "discorda apaga as do mapa (o mapa mudou) -> %s %s" % (names(cf_late), names(cf_early)))
    calls, real_ds = [], xpmod.detect_server
    xpmod.detect_server = lambda *a, **k: calls.append(1)
    try:
        cf_hand, cf_live = old_samples("auto"), old_samples("auto")
        xpmod._CACHE.clear()
        xpmod.calibrate(early, cf_hand, meter.xp_after, live=False)
        n_hand = len(calls)
        xpmod._CACHE.clear()
        xpmod.calibrate(early, cf_live, meter.xp_after)
    finally:
        xpmod.detect_server = real_ds
    check(n_hand == 0 and len(calls) == 1 and names(cf_hand) == ["cedo.rrf#fim", "outro#0", "velha#0"]
          and names(cf_live) == ["cedo.rrf#fim"],
          "XP: replay aberto à mão mede, mas não confere o evento do servidor nem apaga as medidas do mapa (de nenhum "
          "personagem) -> %s" % names(cf_hand))
# abates de monstros sem XP conhecida (a escolta do MVP de Amicitia, 2026-11-21): poucos não tiram a medida do trecho
# (cada um entra pela metade do maior abate do trecho); muitos, ou um chefe sem XP conhecida, deixam o trecho sem
# medida; e um trecho assim não impede mais os outros trechos da gravação de dizerem o evento do servidor
with tempfile.TemporaryDirectory() as tmp:
    def kill_ev(t, aid, job, name="", boss=False):
        return [(t - 400, fr.spawn(aid, "mob", job, name, boss=boss)), (t - 100, fr.skill_damage(ME, aid, 5000)),
                (t, fr.vanish(aid, 1))]

    def unk_rec(name, n_unk, boss=False):
        ev = []
        for i in range(100):                              # 100 Goblins (34 de XP pela lista no 240), um a cada 6 s
            ev += kill_ev(1000 + i * 6000, 56000 + i, 1124, "Goblin")
        for j in range(n_unk):                            # cópia invocada que o programa não conhece
            ev += kill_ev(4000 + j * 6000, 56500 + j, 21999, boss=boss)
        with open(os.path.join(tmp, name), "wb") as f:
            f.write(fr.build(ME, sorted(ev, key=lambda e: e[0]), xp=(7310, 1000, 10 ** 9))[0])
        rf_ = meter.ReplayFile(os.path.join(tmp, name))
        rf_.poll(max_bytes=1 << 30)
        return rf_.combat
    u_recs = [unk_rec("u0.rrf", 0), unk_rec("u1.rrf", 1), unk_rec("u4.rrf", 4), unk_rec("ub.rrf", 1, boss=True)]
    xpmod._CACHE.clear()
    lu0, lu1, lu4, lub = [xpmod._list_xp(c_, {}, (0, c_.now)) for c_ in u_recs]
    check(lu0 and lu1 and abs(lu1 / lu0 - 1.005) < 1e-9 and lu4 is None and lub is None,
          "XP: 1 abate sem XP conhecida entre 100 não tira a medida (entra pela metade do maior abate: lista ×1,005); "
          "4 (4%% da lista) ou um chefe sem XP conhecida deixam o trecho sem medida -> %s %s %s %s"
          % (lu0, lu1, lu4, lub))
    ev_u = []
    for i in range(3):                                    # nível 240: 3 Goblins e 2 sem XP conhecida
        ev_u += kill_ev(1000 + i * 20000, 56600 + i, 1124, "Goblin")
    for j in range(2):
        ev_u += kill_ev(11000 + j * 20000, 56650 + j, 21999)
    ev_u.append((60000, fr.hp(241, rrf.SP_BASELEVEL)))    # subiu (faltavam 204)
    for i in range(30):                                   # nível 241: 30 Goblins = 1020 pela lista, sem evento
        ev_u += kill_ev(61000 + i * 20000, 56700 + i, 1124, "Goblin")
    ev_u.append((661000, fr.hp(242, rrf.SP_BASELEVEL)))   # subiu de novo: o 241 inteiro (3060) = ×3, evento +200%
    with open(os.path.join(tmp, "dois.rrf"), "wb") as f:
        f.write(fr.build(ME, sorted(ev_u, key=lambda e: e[0]), date=(2026, 11, 8, 10, 0, 0),
                         xp=(7320, 1000 - 204, 1000))[0])
    rf_u = meter.ReplayFile(os.path.join(tmp, "dois.rrf"))
    rf_u.poll(max_bytes=1 << 30)
    cfg_u = {"xp_mode": "auto", "xp_levels": {"4302": {"241": 3060}}}
    xpmod._CACHE.clear()
    segs_u = xpmod.exact_segments(rf_u.combat, cfg_u)
    corr_u = xpmod.calibrate(rf_u.combat, cfg_u, meter.xp_after)
    got_u = [x[3] for x in cfg_u.get("xp_corr", {}).get("7320", {}).get("samples", [])]
    check(len(segs_u) == 2 and xpmod.settings(cfg_u, rf_u.combat)["server"] == {"on": True, "pct": 200.0}
          and got_u == ["dois.rrf#1"] and corr_u is not None and abs(corr_u - 1.0) < 1e-9,
          "XP: o nível com abates sem XP conhecida demais fica sem medida, mas o nível seguinte ainda diz o evento "
          "(+200%%) e mede ×1,0 -> %s %s %s" % (cfg_u.get("xp_bonuses"), got_u, corr_u))
check(all(xpmod.MOB_EXP.get(m) and not xpmod.MOB_EXP[m][1] for m in (21048, 21049, 21050, 21051, 20516, 21379, 21589))
      and xpmod.MOB_EXP.get(21533) == [215, 7798710, 5430080],
      "XP: as cópias invocadas (escolta de MVP: Quimeras mutantes, Ferus Esqueleto, Sapo de Lava...) entram como sem "
      "XP, e os monstros do arquivo extra chegam aos dados (Juncea)")
# medida frágil (bônus ligando no meio do trecho) só vale quando o mapa não tem medida firme (2026-11-22, Amicitia)
fr_firm = [0.85, 2.7e9, "2026-11-19 23:25", "up.rrf#fim", "amicitia2", 455, 0]
fr_frag = [0.65, 1.4e9, "2026-11-21 18:26", "aga.rrf#fim", "amicitia2", 344, 1]
p_both = xpmod.predict({"xp_corr": {"1": {"samples": [fr_firm, fr_frag]}}}, 1, "amicitia2")
p_only = xpmod.predict({"xp_corr": {"1": {"samples": [fr_frag]}}}, 1, "amicitia2")
p_old = xpmod.predict({"xp_corr": {"1": {"samples": [fr_firm[:6], fr_frag[:6]]}}}, 1, "amicitia2")
flags = {x[3]: x[6] for e in list(cf_late["xp_corr"].values()) + list(cf_early["xp_corr"].values())
         for x in e["samples"] if len(x) >= 7}
check(p_both == (0.85, "mapa", 1) and p_only == (0.65, "mapa", 1)
      and abs(p_old[0] - (0.85 * 2.7 + 0.65 * 1.4) / 4.1) < 1e-9
      and flags.get("tarde.rrf#fim") == 1 and flags.get("cedo.rrf#fim") == 0,
      "XP: medida frágil fica fora da média do mapa quando há medida firme; sozinha, vale; as guardadas antes (sem a "
      "marca) contam como firmes; a calibração marca a frágil -> %s %s %s %s" % (p_both, p_only, p_old, flags))
# no automático os bônus vistos na gravação contam sempre (o amigo tinha desmarcado o Njord e o Cetro, 2026-11-22);
# a caixa só vale em "Pela lista abaixo"; as medidas são sempre sobre a lista travada
off_b = {"manual": {"on": False, "pct": 50}, "njord": {"on": False, "pct": 60}, "vip": {"on": True, "pct": 25}}
cfg_auto_off, cfg_list_off = {"xp_mode": "auto", "xp_bonuses": off_b}, {"xp_mode": "lista", "xp_bonuses": off_b}
s_auto, s_list = xpmod.settings(cfg_auto_off), xpmod.settings(cfg_list_off)
xpmod._CACHE.clear()
la, l_def = xpmod._list_xp(late, cfg_auto_off, (0, late.now)), xpmod._list_xp(late, {}, (0, late.now))
l_ui = xpmod.estimate(late, dict(cfg_list_off, xp_locked=xpmod.locked(cfg_list_off)), (0, late.now))["kill_xp"]
l_cal = xpmod._list_xp(late, cfg_list_off, (0, late.now))
check(s_auto["manual"]["on"] and s_auto["njord"]["on"] and s_auto["vip"]["pct"] == 20 and not s_list["manual"]["on"]
      and not s_list["njord"]["on"] and s_list["vip"]["pct"] == 25 and la == l_def and l_cal == l_def and l_ui < l_def
      and xpmod.locked({}) and xpmod.locked({"xp_mode": "medido"}) and not xpmod.locked(cfg_list_off)
      and xpmod.overridden(cfg_auto_off) and not xpmod.overridden({"xp_mode": "auto"})
      and not xpmod.overridden(cfg_list_off),
      "XP: no automático os bônus vistos na gravação contam mesmo desmarcados (e com o %% do jogo); em 'Pela lista "
      "abaixo' a caixa vale na tela, mas a medida é sempre sobre a lista travada -> %s %s %s %s" % (la, l_def, l_cal,
                                                                                                   l_ui))
# faixas de nível (2026-11-22): um Ferreiro abaixo do 100 não mexe no evento, nas medidas nem nos mapas de um
# Mestre Celestial 230 (e vice-versa); o evento marcado à mão vale para todas as faixas
import types  # noqa: E402
lo_c = types.SimpleNamespace(session=types.SimpleNamespace(base_level=90, gid=1))
hi_c = types.SimpleNamespace(session=types.SimpleNamespace(base_level=247, gid=2))
cfg_bd = {"xp_bonuses": {"server": {"on": True, "pct": 100}},
          "xp_server_band": {"<200": {"on": True, "pct": 200, "auto": True}},
          "xp_corr": {"1": {"band": "<200", "samples": [[1.5, 100, "2026-11-05 10:00", "a#0", "mapa_x", 300],
                                                         [1.0, 100, "2026-11-05 10:30", "a#1", "mapa_y", 300]]},
                      "2": {"band": "200+", "samples": [[1.0, 100, "2026-11-05 11:00", "b#0", "mapa_y", 300]]},
                      "3": {"band": "200+", "samples": [[1.2, 100, "2026-11-05 11:00", "c#0", "mapa_z", 300],
                                                         [1.0, 100, "2026-11-05 11:30", "c#1", "mapa_y", 300]]}}}
p_lo = xpmod.predict(cfg_bd, 2, "mapa_x")            # só um personagem de outra faixa mediu: não empresta
p_hi = xpmod.predict(cfg_bd, 2, "mapa_z")            # outro da mesma faixa mediu: empresta
moved = xpmod._check_change(cfg_bd, 2, [1.6, 100, "2026-11-06 10:00", "b#9", "mapa_y", 300])
left_bd = sorted(x[3] for e in cfg_bd["xp_corr"].values() for x in e["samples"])
check(xpmod.band_of(199) == "<200" and xpmod.band_of(200) == "200+"
      and xpmod.settings(cfg_bd, lo_c)["server"]["pct"] == 200 and xpmod.settings(cfg_bd, hi_c)["server"]["pct"] == 100
      and xpmod.settings(cfg_bd)["server"]["pct"] == 100 and p_lo == (1.0, "personagem", 1)
      and p_hi[1] == "personagens" and abs(p_hi[0] - 1.2) < 1e-9 and moved and left_bd == ["a#0", "a#1", "c#0"],
      "XP: faixas de nível: o evento deduzido para os abaixo de 200 não vale para o 247; o 247 não usa a medida do "
      "mapa feita só pelo de nível 90, mas usa a de outro 200+; 'o mapa mudou' apaga só as medidas da faixa -> "
      "%s %s %s" % (p_lo, p_hi, left_bd))
with tempfile.TemporaryDirectory() as tmp_b:
    ev_b = []                                         # 3 Goblins (37 cada pela lista sem evento) e +333 na seguinte
    for i, aid in enumerate((57001, 57002, 57003)):
        ev_b += [(i * 300000, fr.spawn(aid, "mob", 1122, "Goblin")), (i * 300000 + 200, fr.skill_damage(ME, aid, 5000)),
                 (i * 300000 + 400, fr.vanish(aid, 1))]
    for name, date, exp, events in (("a.rrf", (2026, 11, 5, 19, 35, 0), 1000, ev_b),
                                    ("b.rrf", (2026, 11, 5, 19, 45, 40), 1000 + 333, [])):
        with open(os.path.join(tmp_b, name), "wb") as f:
            f.write(fr.build(ME, events, date=date, xp=(7110, exp, 10 ** 9))[0])
    rf_b = meter.ReplayFile(os.path.join(tmp_b, "a.rrf"))
    rf_b.poll(max_bytes=1 << 30)
    cfg_ev = {"xp_mode": "auto", "xp_bonuses": {"server": {"on": True, "pct": 100}}}
    xpmod._CACHE.clear()
    xpmod.calibrate(rf_b.combat, cfg_ev, meter.xp_after)   # nível 240: a XP exata pede +200% (faixa 200+)
s_lo, s_hi = xpmod.settings(cfg_ev, lo_c)["server"]["pct"], xpmod.settings(cfg_ev, rf_b.combat)["server"]["pct"]
check(s_hi == 200 and s_lo == 100 and cfg_ev["xp_bonuses"]["server"]["pct"] == 100
      and cfg_ev["xp_corr"]["7110"]["band"] == "200+"
      and (cfg_ev.get("xp_learn") or {}).get("server", [{}])[-1].get("band") == "200+",
      "XP: o evento que a XP exata de um personagem 200+ revela vale para a faixa dele; os abaixo de 200 e o geral "
      "ficam como estavam -> %s %s %s" % (s_hi, s_lo, cfg_ev.get("xp_server_band")))
# a conta guardada (estimate) refaz quando o evento da faixa muda: antes a calibração usava a lista com o evento velho
# logo depois da troca e guardava uma medida errada (×1,55 num jogador)
xpmod._CACHE.clear()
cfg_cache = {"xp_mode": "lista", "xp_bonuses": {"server": {"on": True, "pct": 100}}}
e_100 = xpmod.estimate(rf_b.combat, cfg_cache)["xp"]
cfg_cache["xp_server_band"] = {"200+": {"on": True, "pct": 200}}
e_200 = xpmod.estimate(rf_b.combat, cfg_cache)["xp"]
check(e_100 and abs(e_200 / e_100 - 1.5) < 1e-9,
      "XP: a XP guardada pela lista é refeita quando o evento da faixa muda (+100%% -> +200%%: ×1,5) -> %s %s"
      % (e_100, e_200))
# fora do automático, o aviso quando ele daria um valor muito diferente (AUTO_GAP, 15%)
mk_late = xpmod._kill_map(late, 0, late.now)
corr_cfg = {"xp_corr": {"7300": {"samples": [[1.3, 500, "2026-11-06 09:00", "v#0", mk_late, 300]]}}}
corr_low = {"xp_corr": {"7300": {"samples": [[1.05, 500, "2026-11-06 09:00", "v#0", mk_late, 300]]}}}
xpmod._CACHE.clear()
g_auto = xpmod.auto_gap(late, dict(corr_cfg, xp_mode="auto"))
g_list = xpmod.auto_gap(late, dict(corr_cfg, xp_mode="lista"))
g_low = xpmod.auto_gap(late, dict(corr_low, xp_mode="lista"))
g_off = xpmod.auto_gap(late, cfg_list_off)
g_fix = xpmod.auto_gap(late, {"xp_mode": "fixo", "xp_fixed": 0.0})
check(g_auto is None and g_list and abs(g_list[0] - 0.30) < 1e-6 and g_low is None and g_off and g_off[0] > 0.15
      and g_fix and g_fix[0] > 0.15,
      "XP: fora do automático, aviso quando ele daria 15%% ou mais de diferença (medida ×1,3 do mapa: +30%%; ×1,05: "
      "nada; manual desmarcado na lista: o automático conta) -> %s %s %s %s"
      % (g_list and round(g_list[0], 3), g_low, g_off and round(g_off[0], 3), g_fix and round(g_fix[0], 3)))
# drops no registro: só abates isolados, cada item com a morte dele (o aid volta quando o monstro renasce), separados
# pelos bônus de drop ativos (Chiclete 252 com o %)


def _fall(map_id, item, x=100, y=100, count=1):
    p = bytearray(22)
    struct.pack_into("<HII", p, 0, rrf.P_ITEM_FALL, map_id, item)
    struct.pack_into("<HH", p, 13, x, y)
    struct.pack_into("<H", p, 19, count)
    return bytes(p)


evg = [(0, fr.spawn(54001, "mob", 1124, "Goblin")), (900, fr.skill_damage(ME, 54001, 5000)),
       (1000, fr.vanish(54001, 1)), (1001, _fall(1, 501)),
       (3000, fr.spawn(54001, "mob", 1124, "Goblin")), (4900, fr.skill_damage(ME, 54001, 5000)),
       (5000, fr.vanish(54001, 1)), (5001, _fall(2, 501)),
       (7000, fr.status(ME, 252, True, 1800000, 1800000, 100)),
       (8000, fr.spawn(54002, "mob", 1124, "Goblin")), (8900, fr.skill_damage(ME, 54002, 5000)),
       (9000, fr.vanish(54002, 1)),
       (19000, fr.spawn(54003, "mob", 1124, "Goblin")), (19001, fr.spawn(54004, "mob", 1124, "Goblin")),
       (19900, fr.skill_damage(ME, 54003, 5000)), (19901, fr.skill_damage(ME, 54004, 5000)),
       (20000, fr.vanish(54003, 1)), (20010, fr.vanish(54004, 1)), (20011, _fall(3, 502)),
       (30000, fr.skill_damage(ME, 77, 1))]
cg = combat_of(fr.build(ME, evg)[0])
dl = xpmod.drop_log(cg)
check(dl == {"1124": {"-": [2, {"501": 2}], "252:100": [1, {}]}},
      "registro de drops: cada item conta na morte dele (o monstro que renasce com o mesmo número não soma os itens "
      "das outras vidas), rajada de mortes fica de fora, bônus de drop ativo (Chiclete 100%%) separa -> %s" % dl)
# aviso de calibrar: mapa sem medida depois de 10 min de farm, gravação em andamento, sem subida de nível
evh = []
for i, aid in enumerate(range(54101, 54113)):
    evh += [(i * 60000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 60000 + 300, fr.skill_damage(ME, aid, 5000)),
            (i * 60000 + 400, fr.vanish(aid, 1))]
ch = combat_of(fr.build(ME, evh, xp=(7400, 100, 10 ** 9))[0])
ch.finished = False
h_new = xpmod.calibration_hint(ch, {})
h_own = xpmod.calibration_hint(ch, {"xp_corr": {"7400": {"samples": [[1.0, 100, "2026-10-22 10:00", "x#0",
                                                                      "prt_fild08", 300]]}}})
h_list = xpmod.calibration_hint(ch, {"xp_mode": "lista"})
ch.finished = True
h_done = xpmod.calibration_hint(ch, {})
ch2 = combat_of(fr.build(ME, evh[:9], xp=(7400, 100, 10 ** 9))[0])
ch2.finished = False
check(h_new == "prt_fild08" and h_own is None and h_list is None and h_done is None
      and xpmod.calibration_hint(ch2, {}) is None,
      "XP: aviso de calibrar só em mapa sem medida, depois de 10 min de farm, com a gravação em andamento e no modo "
      "automático -> %s %s %s %s" % (h_new, h_own, h_list, h_done))
# aviso de medida antiga: nenhuma medida exata na faixa de nível há 2 dias (o evento do servidor pode ter acabado);
# o personagem do replay de teste é nível 240 (faixa 200+)
ch.finished = False


def _stale_cfg(date, band=None, log=None):
    e = {"samples": [[1.0, 100, date, "x#0", "prt_fild08", 300]]}
    if band:
        e["band"] = band
    out = {"xp_corr": {"7400": e}}
    if log:
        out["xp_learn"] = {"measures": log}
    return out


s_fresh = xpmod.stale_hint(ch, _stale_cfg("2026-10-22 10:00"))          # 13 h antes da gravação
s_old = xpmod.stale_hint(ch, _stale_cfg("2026-10-19 10:00"))            # 3,5 dias
s_log = xpmod.stale_hint(ch, _stale_cfg("2026-10-19 10:00", log=[dict(char="7401", level=230, date="2026-10-22 09:00",
                                                                         ratio=1.0, map="pay_fild01", gain=5)]))
s_other = xpmod.stale_hint(ch, dict(_stale_cfg("2026-10-19 10:00"), xp_learn={"measures": [
    dict(char="7401", level=150, date="2026-10-22 09:00", ratio=1.0, map="pay_fild01", gain=5)]}))
s_list = xpmod.stale_hint(ch, dict(_stale_cfg("2026-10-19 10:00"), xp_mode="lista"))
s_none = xpmod.stale_hint(ch, {})
ch.finished = True
s_done = xpmod.stale_hint(ch, _stale_cfg("2026-10-19 10:00"))
ch.finished = False
s_short = xpmod.stale_hint(ch2, _stale_cfg("2026-10-19 10:00"))
check(s_fresh is None and s_old == 3 and s_log is None and s_other == 3 and s_list is None and s_none is None
      and s_done is None and s_short is None,
      "XP: aviso de medida antiga (2 dias sem medida exata na faixa de nível, gravando, 10 min de farm, automático); "
      "uma medida do registro de outro personagem da mesma faixa conta, a de outra faixa não -> %s"
      % [s_fresh, s_old, s_log, s_other, s_list, s_none, s_done, s_short])
# relatório: legível e sem nada pessoal (sem o número do personagem, sem nomes de arquivo)
import xpreport  # noqa: E402
cfg_r = {"xp_levels": {"4302": {"200": 653047446}}, "xp_learn": {
    "measures": [dict(src="gravacao secreta de Fulano.rrf#0", date="2026-11-17 03:26", map="abyss_04", mins=28.9,
                      kills=396, ratio=0.99, char="123456", job=4302, level=200, deaths=1, insured=0, quests=[],
                      bonus={"vip": [100, 20], "manual": [70, 50]}, mobs=[[20617, 24]], shared=33, party=3,
                      spot_list=True)],
    "unknown": {"21533": dict(name="Juncea de Simulação", recs={"gravacao secreta de Fulano.rrf": 1},
                              maps={"jorlab": 1}, last="2026-11-17")},
    "drops": {"gravacao secreta de Fulano.rrf": dict(date="2026-11-17", mobs={"20617": {"983": [10, {"1000322": 1}]}})},
    "changes": [dict(date="2026-11-17", map="abyss_04", old=1.0, new=1.23)], "server": [], "names": {}}}
rep = xpreport.text(cfg_r, "9.9.9")
check("123456" not in rep and "Fulano" not in rep and ".rrf" not in rep and "secreta" not in rep
      and "A: " in rep and "abyss_04" in rep and "1000322" in rep and "21533" in rep and "1,23" in rep,
      "relatório de aprendizado: personagens como A, B, C, sem o número do personagem e sem nomes de arquivo; com os "
      "mapas, as mudanças, os monstros sem XP e os drops")
# bloco de dados do relatório (uma linha "RM|{json}" por registro) e a ferramenta que lê os relatórios mandados
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("ler_relatorios", os.path.join(HERE, "..", "tools", "ler_relatorios.py"))
ler = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ler)
rows_r = [json.loads(ln[3:]) for ln in rep.splitlines() if ln.startswith("RM|")]
check(rows_r and rows_r[0]["t"] == "report" and {"m", "d", "u", "c"} <= {r["t"] for r in rows_r}
      and rows_r[1]["char"] == "A" and len(rows_r[1]["date"]) == 10 and "hour" not in rows_r[1]
      and cfg_r["xp_learn"].get("secret"),
      "relatório: bloco de dados no fim, uma linha por registro (medidas, drops, monstros sem XP, mudanças), só o dia "
      "(sem hora), com o sorteio do PC criado se faltava -> %s" % [r["t"] for r in rows_r])
cfg_ru = {"xp_learn": {"measures": [dict(cfg_r["xp_learn"]["measures"][0], unknown=2)], "unknown": {}, "drops": {},
                       "changes": [], "server": [], "names": {}}}
rep_u = xpreport.text(cfg_ru, "9.9.9")
check("396 (33), 2 sem XP conhecida" in rep_u
      and any(json.loads(ln[3:]).get("unknown") == 2 for ln in rep_u.splitlines() if ln.startswith("RM|{\"bonus\"")),
      "relatório: a medida com abates sem XP conhecida diz quantos foram -> %s"
      % [ln for ln in rep_u.splitlines() if "396" in ln][:1])


def _lrn(secret, measures, drops, unknown):
    return {"xp_learn": {"secret": secret, "measures": measures, "drops": drops, "unknown": unknown, "changes": [],
                         "server": [], "names": {}}}


def _meas(src, date, mp, ratio):
    return dict(src=src, date=date, map=mp, mins=30.0, kills=300, ratio=ratio, gain=10 ** 8, char="111", job=4302,
                level=230, deaths=0, insured=0, quests=[], bonus={}, mobs=[[20617, 90]], shared=0, party=1,
                spot_list=False)


m_1 = _meas("x.rrf#0", "2026-11-15 10:00", "abyss_04", 1.0)
m_2 = _meas("y.rrf#0", "2026-11-15 11:00", "prt_fild08", 1.02)
m_3 = _meas("z.rrf#0", "2026-11-16 12:00", "abyss_04", 1.5)
d_1 = {"x.rrf": dict(date="2026-11-15", mobs={"20617": {"-": [100, {"6608": 2}], "252:100": [100, {"6608": 4}]}})}
d_2 = dict(d_1, **{"z.rrf": dict(date="2026-11-16", mobs={"20617": {"-": [50, {"6608": 1}]}})})
u_1 = {"21533": dict(name="Juncea de Simulação", recs={"x.rrf": 3}, maps={"jorlab": 3}, last="2026-11-15")}
with tempfile.TemporaryDirectory() as tmpr:
    rep_1 = xpreport.text(_lrn("s1", [m_1, m_2], d_1, u_1), "9.9.9")
    rep_2 = xpreport.text(_lrn("s1", [m_1, m_2, m_3], d_2, u_1), "9.9.9")       # o mesmo PC, mais tarde
    rep_3 = xpreport.text(_lrn("s2", [m_1], {}, u_1), "9.9.9")                 # outro PC, o mesmo nome de gravação
    cut = next(ln for ln in rep_2.splitlines() if '"t":"m"' in ln)
    rep_2 = rep_2.replace(cut, cut[:70] + "\n" + cut[70:])                      # linha quebrada no e-mail
    for nm, txt in (("a.txt", rep_1), ("b.txt", rep_2), ("c.txt", rep_3)):
        with open(os.path.join(tmpr, nm), "w", encoding="utf-8") as f:
            f.write(txt)
    lr = ler.load([tmpr])
    lr_text = ler.summary(lr)
    lr_item = ler.summary(lr, item="6608", min_kills=10)
check(len(lr.measures) == 4 and lr.repeated == {"m": 2, "d": 1, "q": 0} and len(lr.drops) == 2 and lr.bad == 0
      and len({r["pc"] for r in lr.reports}) == 2
      and "Juncea de Simulação (21533) · 6 abates em 2 gravações, 2 PCs" in lr_text
      and "×1,471" in lr_text and "fora do normal" in lr_text and "x.rrf" not in lr_text,
      "ferramenta dos relatórios: o repetido em relatórios seguidos do mesmo PC conta uma vez, o mesmo nome de "
      "gravação em outro PC é outro registro, linha quebrada no caminho ainda é lida, XP comparada com o normal do "
      "personagem (dia fora do normal marcado) -> %d medidas, repetidos %s, %d drops, %d linhas ruins"
      % (len(lr.measures), lr.repeated, len(lr.drops), lr.bad))
w_lo, w_hi = ler.wilson(5, 100)
mh = ler.mantel_haenszel([(10, 100, 5, 100), (20, 100, 10, 100)])
check(abs(w_lo - 0.0215) < 5e-4 and abs(w_hi - 0.1118) < 5e-4 and ler.fisher(5, 100, 5, 100) > 0.999
      and ler.fisher(10, 100, 1, 100) < 0.05 and abs(mh[0] - 2.0) < 1e-9 and mh[1][0] < 2.0 < mh[1][1]
      and "Efeito de cada bônus de drop" in lr_item and "×2,00" in lr_item and ler.clean("a\x1b[2Jb") == "a[2Jb",
      "ferramenta dos relatórios: intervalo de Wilson, teste de Fisher, bônus de drop juntando monstros e PCs "
      "(Mantel-Haenszel) e texto de outra pessoa sem caracteres de controle -> %.4f %.4f %s" % (w_lo, w_hi, mh))
# o efeito de um bônus é medido com os outros bônus iguais (Goma 100% + 983 contra só 983); duas gravações pequenas
# iguais em tudo no mesmo relatório são duas gravações
be = ler.bonus_effect({"20178": {"983": {"pc": [1000, {"1000322": 15}]},
                                 "252:100+983": {"pc": [500, {"1000322": 15}]}}})
same_d = {"p.rrf": dict(date="2026-11-15", mobs={"21853": {"-": [1, {}]}}),
          "q.rrf": dict(date="2026-11-15", mobs={"21853": {"-": [1, {}]}})}
with tempfile.TemporaryDirectory() as tmpr2:
    with open(os.path.join(tmpr2, "r.txt"), "w", encoding="utf-8") as f:
        f.write(xpreport.text(_lrn("s3", [m_1], same_d, {}), "9.9.9"))
    lr2 = ler.load([tmpr2])
qm = [_meas("a.rrf#0", "2026-11-15 10:00", "abyss_04", 1.0), _meas("b.rrf#0", "2026-11-15 11:00", "prt_fild08", 1.0),
      _meas("c.rrf#0", "2026-11-15 12:00", "abyss_04", 1.0),
      dict(_meas("d.rrf#0", "2026-11-15 13:00", "abyss_04", 1.5), gain=3 * 10 ** 6, quests=[8721],
           quest_at=[[8721, {"server": 100, "manual": 50}]])]
with tempfile.TemporaryDirectory() as tmpr3:
    with open(os.path.join(tmpr3, "q.txt"), "w", encoding="utf-8") as f:
        f.write(xpreport.text(_lrn("s4", qm, {}, {}), "9.9.9"))
    lq = ler.summary(ler.load([tmpr3]))
check("missão 8721" in lq and "1 medida" in lq and "XP ≈ 1.000.000 (33% do trecho)" in lq
      and "bônus na entrega: evento do servidor +100%, manual +50%" in lq and "sem bônus ≈ 666.667" in lq,
      "ferramenta dos relatórios: XP de cada missão (XP real − abates × o normal do personagem) com os bônus ativos "
      "na entrega e a recompensa sem bônus pela regra do programa (×1,5: só o manual conta)")
# recompensas que o programa mediu vão no relatório (linhas "q"); a ferramenta junta as dos PCs, compara o que o jogo
# pagou com as duas regras de bônus de missão e grava o arquivo para o tools/build_quest_exp.py
full_on = {"server": 100, "vip": 20, "scepter": 30, "kafra": 50, "manual": 50}
qm2 = qm[:3] + [dict(_meas("e.rrf#0", "2026-11-16 10:00", "abyss_04", 1.5), gain=3 * 148560 * 3.5,
                     quests=[3477], quest_at=[[3477, full_on]]),
                dict(_meas("f.rrf#0", "2026-11-16 11:00", "abyss_04", 1.5), gain=3 * 165480 * 3.5,
                     quests=[8663], quest_at=[[8663, full_on]], edge=[8663])]
lrn_q = _lrn("s5", qm2, {}, {})
lrn_q["xp_learn"]["quests"] = [
    dict(src="g.rrf#0", quest=7893, base=15823920, level=190, mult=2.0, date="2026-11-17"),
    dict(src="h.rrf#1", quest=7895, base=4000000, level=190, mult=2.0, date="2026-11-17", **{"with": [7897]})]
rep_q = xpreport.text(lrn_q, "9.9.9")
rows_q = [json.loads(ln[3:]) for ln in rep_q.splitlines() if ln.startswith("RM|")]
with tempfile.TemporaryDirectory() as tmpr4:
    with open(os.path.join(tmpr4, "q.txt"), "w", encoding="utf-8") as f:
        f.write(rep_q)
    dq = ler.load([tmpr4])
    lq2 = ler.summary(dq)
    build_q = ler.quests_for_build(ler.quest_obs(ler.xp_rows(dq), dq))
check([r["quest"] for r in rows_q if r["t"] == "q"] == [7893, 7895] and all(r.get("mid") for r in rows_q if r["t"] == "q")
      and "Recompensas de missão medidas (sem bônus)" in rep_q
      and "pagou ×3,50 · regra do programa ×2,00 (+75%) · regra alternativa ×3,50 (+0%)" in lq2
      and "Erro mediano da regra do programa: 75% em 1 medida" in lq2
      and "Erro mediano da regra alternativa: 0% em 1 medida" in lq2
      and "junto com 7897: o total dividido" in lq2 and "missão 8663" not in lq2.split("Regra do bônus")[0]
      and build_q == {"7893": 15823920},
      "relatório e ferramenta: recompensas medidas pelo programa no relatório; a ferramenta compara o que o jogo pagou "
      "com as duas regras, deixa de fora a entrega no instante de uma subida e grava só o que é confiável -> %s"
      % build_q)
# medida da 1.10.0 depois de um Zerar: a missão "pagou" o nível inteiro (Mestre Ferreiro 92 = 1.934.170; 94 com duas
# entregas, a recompensa arredondada) -> descartada; uma medida de verdade da mesma missão passa
check(ler.whole_level(92, 967085 * 2.0, 2.0) and ler.whole_level(94, 672904 * 2.0, 2.0)
      and ler.whole_level(93, 1157020 * 2.0, 2.0) and not ler.whole_level(92, 253420 * 2.0, 2.0)
      and not ler.whole_level(None, 5.0, 1.0),
      "ferramenta dos relatórios: a medida que é a XP do nível inteiro (abates apagados pelo Zerar da 1.10.0) fica de "
      "fora da recompensa e do arquivo para o build")
# a leitura da pasta junta as recompensas medidas (sem repetir) e as aprendidas valem para a previsão
import learnfolder  # noqa: E402
lm = xpmod._learn({})
lm["quests"] = [dict(src="a.rrf#0", quest=3477, base=1, date="2026-11-01")]
learnfolder.merge(lm, {"quests": [dict(src="a.rrf#0", quest=3477, base=2, date="2026-11-01"),
                                  dict(src="b.rrf#0", quest=3477, base=3, date="2026-11-02")]})
_spec_b = importlib.util.spec_from_file_location("build_quest_exp", os.path.join(HERE, "..", "tools",
                                                                                 "build_quest_exp.py"))
build_quest_exp = importlib.util.module_from_spec(_spec_b)
_spec_b.loader.exec_module(build_quest_exp)
with tempfile.TemporaryDirectory() as tmpq:
    pq = os.path.join(tmpq, "r.json")
    with open(pq, "w", encoding="utf-8") as f:
        json.dump({"exp": {"3477": 150000, "x": 5, "8663": -1, "7893": True}}, f)
    rq = build_quest_exp.reports_exp(pq)
check([(x["src"], x["base"]) for x in lm["quests"]] == [("a.rrf#0", 1), ("b.rrf#0", 3)] and rq == {3477: 150000},
      "missões: a leitura da pasta junta as recompensas medidas sem repetir a mesma gravação; o build lê o arquivo da "
      "ferramenta dos relatórios (só números válidos) -> %s %s" % (lm["quests"], rq))
check(len(be) == 1 and be[0][:2] == ("1000322", "252:100") and abs(be[0][2][0] - 2.0) < 1e-9
      and len(lr2.drops) == 2 and lr2.repeated["d"] == 0,
      "ferramenta dos relatórios: efeito de cada bônus de drop com os outros bônus iguais; gravações pequenas iguais "
      "não são tomadas por repetidas -> %s, %d gravações" % ([(r[0], r[1], round(r[2][0], 3)) for r in be],
                                                             len(lr2.drops)))
# leitura única das gravações que já estavam na pasta (processo à parte): em ordem de data, num rascunho, grava só
# o aprendizado; o widget junta (o que ele já tinha fica), marca a pasta como lida e não começa de novo
import learnfolder  # noqa: E402
evf = []
for i, aid in enumerate((52701, 52702, 52703)):
    evf += [(i * 300000, fr.spawn(aid, "mob", 1122, "Goblin")), (i * 300000 + 200, fr.skill_damage(ME, aid, 5000)),
            (i * 300000 + 400, fr.vanish(aid, 1))]
age_before = xpmod.MAX_AGE_S
with tempfile.TemporaryDirectory() as tmpf, tempfile.TemporaryDirectory() as tmpc:
    os.environ["RODPS_CONFIG"] = os.path.join(tmpc, "config.json")      # caches de nomes fora do seu PC
    for name, date, exp, events in (("b.rrf", (2026, 11, 5, 19, 45, 40), 1000 + 111, []),
                                    ("a.rrf", (2026, 11, 5, 19, 35, 0), 1000, evf)):
        with open(os.path.join(tmpf, name), "wb") as f:
            f.write(fr.build(ME, events, date=date, xp=(7100, exp, 10 ** 9))[0])
    with open(os.path.join(tmpc, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"xp_bonuses": {"server": {"on": False, "pct": 100}}, "xp_mode": "lista"}, f)
    recs_f = [os.path.basename(p) for _w, p in learnfolder.recordings([tmpf], busy_s=0)]
    busy_f = learnfolder.recordings([tmpf])                     # acabaram de ser escritas: ficam para o widget
    with open(os.path.join(tmpc, learnfolder.PROGRESS), "w", encoding="utf-8") as f:
        json.dump({"done": 3, "total": 10}, f)
    prog_f = (learnfolder.progress(tmpc), learnfolder.should_start({}, tmpc))   # outro processo lendo: não começa
    res_f = learnfolder.run([tmpf], tmpc, busy_s=0)
    cfg_f = {"xp_learn": {"measures": [dict(src="a.rrf#fim", date="2026-11-05 19:35", map="x", ratio=9.0)]}}
    took = learnfolder.take(cfg_f, tmpc)
    left_f = [n for n in os.listdir(tmpc) if n.startswith("aprendizado_pasta") or n == "erros.log"]
    lf = cfg_f["xp_learn"]
    start_f = (learnfolder.should_start(lf, tmpc), learnfolder.should_start({}, tmpc),
               learnfolder.should_start({"folder_tries": 3}, tmpc))
    os.environ.pop("RODPS_CONFIG", None)
mf = res_f["learn"]["measures"]
check(recs_f == ["a.rrf", "b.rrf"] and busy_f == [] and res_f["files"] == 2 and res_f["errors"] == 0
      and [m["src"] for m in mf] == ["a.rrf#fim"] and abs(mf[0]["ratio"] - 1.0) < 0.01
      and took and left_f == [] and lf["folder_read"]["files"] == 2 and [m["ratio"] for m in lf["measures"]] == [9.0]
      and start_f == (False, True, False) and xpmod.MAX_AGE_S == age_before and prog_f == ((3, 10), False),
      "leitura da pasta: gravações em ordem de data (as que ainda podem estar gravando ficam para o widget), o "
      "rascunho aprende no automático, o widget junta sem trocar o que já tinha, marca a pasta como lida e não "
      "começa de novo -> %s %s %s %s" % (recs_f, [(m["src"], m["ratio"]) for m in mf], left_f, start_f))
# o evento do servidor não muda por causa de um mapa só: XP 50% acima da lista aqui, e os outros mapas fecham
with tempfile.TemporaryDirectory() as tmp9:
    for name, date, exp, events in (("a.rrf", (2026, 11, 5, 19, 35, 0), 1000, ev),
                                    ("b.rrf", (2026, 11, 5, 19, 45, 40), 1000 + 333, [])):
        with open(os.path.join(tmp9, name), "wb") as f:
            f.write(fr.build(ME, events, date=date, xp=(7100, exp, 10 ** 9))[0])
    rf9 = meter.ReplayFile(os.path.join(tmp9, "a.rrf"))
    rf9.poll(max_bytes=1 << 30)
    here9 = xpmod.map_key(rf9.combat.map)
    cfg_o = {"xp_bonuses": {"server": {"on": True, "pct": 100}},
             "xp_corr": {"7100": {"samples": [[1.0, 1000, "2026-11-05 10:00", "z#0", "outro_mapa"]]}}}
    xpmod.calibrate(rf9.combat, cfg_o, meter.xp_after)
    cfg_n = {"xp_bonuses": {"server": {"on": True, "pct": 100}}}
    xpmod.calibrate(rf9.combat, cfg_n, meter.xp_after)
    c_o = xpmod.stored_correction(rf9.combat, cfg_o, here9)
    check(xpmod.settings(cfg_o, rf9.combat)["server"]["pct"] == 100 and abs(c_o[0] - 1.5) < 1e-3
          and xpmod.settings(cfg_n, rf9.combat)["server"]["pct"] == 200,
          "XP automática: XP acima da lista num mapa com os outros mapas fechando é coisa do mapa (a correção dele "
          "aprende ×1,5; o evento do servidor fica em 100%%); sem outros mapas medidos, o evento ainda é deduzido "
          "-> %s %s %s" % (xpmod.settings(cfg_o, rf9.combat)["server"], c_o, xpmod.settings(cfg_n, rf9.combat)["server"]))
# Monster Spotlight por monstro (lista do evento de 10/11 a 07/12/2026): no Lago do Abismo 4 só Ferus Esqueleto
# (20616) e Acidus Esqueleto (20617) rendem +50%; Ferus Roxo (20612) não. O mapa marcado vale só para quem está
# fora da lista, e desligar o bônus desliga os dois
evs = []
for i, (aid, mob, nm) in enumerate(((73001, 20616, "Ferus Esqueleto"), (73002, 20612, "Ferus Roxo"),
                                    (73003, 20617, "Acidus Esqueleto"))):
    evs += [(i * 1000, fr.spawn(aid, "mob", mob, nm)), (i * 1000 + 300, fr.skill_damage(ME, aid, 5000)),
            (i * 1000 + 400, fr.vanish(aid, 1))]
csp = combat_of(fr.build(ME, evs, date=(2026, 11, 17, 3, 26, 41), map_name="abyss_04")[0])
cso = combat_of(fr.build(ME, evs, date=(2026, 12, 8, 3, 26, 41), map_name="abyss_04")[0])


def _spot_ratio(cmb, cfg):
    on = {r["mob"]: r["total"] for r in xpmod.estimate(cmb, dict(cfg, xp_mode="lista"))["rows"]}
    off = {r["mob"]: r["total"] for r in xpmod.estimate(cmb, dict(cfg, xp_mode="lista", xp_bonuses={
        "spot": {"on": False, "pct": 20}}))["rows"]}
    return [round(on[m] / off[m], 3) for m in (20616, 20612, 20617)]


# estimativa guardada: A, depois B (outros bônus), depois A de novo (vem guardada) deixa nas linhas os totais de A
_cfg_a, _cfg_b = {"xp_mode": "lista"}, {"xp_mode": "lista", "xp_bonuses": {"spot": {"on": False, "pct": 20}}}
_ea = xpmod.estimate(csp, _cfg_a)
_ta = [r["total"] for r in _ea["rows"]]
_eb = xpmod.estimate(csp, _cfg_b)
_tb = [r["total"] for r in _eb["rows"]]
_ea2 = xpmod.estimate(csp, _cfg_a)
check(_ta != _tb and [r["total"] for r in _ea2["rows"]] == _ta and _ea2["xp"] == _ea["xp"] and _ea2 is not _ea,
      "XP: a estimativa guardada devolve o mesmo resultado e regrava nas linhas os totais dela -> %s %s" % (_ta, _tb))
sp_plain = _spot_ratio(csp, {})
sp_mark = _spot_ratio(csp, {"xp_spot": {"abyss_04": {"pct": 20}}})
sp_late = _spot_ratio(cso, {})
check(sp_plain == [1.5, 1.0, 1.5] and sp_mark == [1.5, 1.2, 1.5] and sp_late == [1.0, 1.0, 1.0]
      and xpmod.event_spots(csp).get(21542) == 20
      and xpmod.spot_kills(csp) == {50.0: {"Ferus Esqueleto": 1, "Acidus Esqueleto": 1}},
      "XP: Monster Spotlight vale por monstro da lista do evento (+50%% só nos Esqueletos do Lago do Abismo), o mapa "
      "marcado só para os de fora da lista, e só no período do evento -> %s %s %s" % (sp_plain, sp_mark, sp_late))
# manual que vence depois de uma morte: a morte encerra os status no medidor, mas o manual segue; quando o jogo
# avisa que ele acabou (o "desligou" chega depois da morte), a XP para de contar o bônus ali (fdgsrb: 5,8 min,
# e o programa contava até o fim da gravação)
evm = [(1000, fr.status(ME, 250, True, 1800000, 1800000, 50)), (5000, fr.vanish(ME, 1)),
       (20000, fr.status(ME, 250, False, 0, 0, 0)), (30000, fr.skill_damage(ME, 77, 1))]
cm = combat_of(fr.build(ME, evm)[0])
cm2 = combat_of(fr.build(ME, evm[:2] + evm[3:])[0])
man = xpmod.windows(cm, {})["manual"]
man2 = xpmod.windows(cm2, {})["manual"]
check(man == [(1000, 20000, 50)] and man2 == [(1000, 30000, 50)] and cm.lasting(250) == [(1000, 20000)],
      "XP: manual que vence depois de uma morte para de contar quando o jogo avisa (sem o aviso, segue pela duração) "
      "-> %s %s" % (man, man2))
# trecho com morte de quem grava não calibra (a morte tira XP e o replay não diz quanto)
evd2 = []
for i, aid in enumerate((52601, 52602, 52603, 52604)):
    evd2 += [(i * 60000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 60000 + 300, fr.skill_damage(ME, aid, 5000)),
             (i * 60000 + 400, fr.vanish(aid, 1))]
    if i == 2:
        evd2.append((i * 60000 + 500, fr.hp(241, rrf.SP_BASELEVEL)))
cl_ok = combat_of(fr.build(ME, evd2, xp=(7200, 1000 - 204, 1000))[0])
cl_dead = combat_of(fr.build(ME, sorted(evd2 + [(70000, fr.vanish(ME, 1))], key=lambda x: x[0]),
                             xp=(7200, 1000 - 204, 1000))[0])
cl_ins = combat_of(fr.build(ME, sorted(evd2 + [(70000, fr.vanish(ME, 1)), (70010, struct.pack(
    "<HHIIHB", rrf.P_ITEM_USE, 20, 6413, ME, 43, 1))], key=lambda x: x[0]), xp=(7200, 1000 - 204, 1000))[0])
sc_ok = xpmod.session_correction(cl_ok, {"xp_mode": "medido"})
sc_dead = xpmod.session_correction(cl_dead, {"xp_mode": "medido"})
sc_ins = xpmod.session_correction(cl_ins, {"xp_mode": "medido"})
check(sc_ok and abs(sc_ok[0] - 2.0) < 1e-9 and sc_dead and abs(sc_dead[0] - 254 / 102.0) < 1e-9
      and sc_ins and abs(sc_ins[0] - 2.0) < 1e-9 and xpmod.died_in(cl_dead, 0, 130000)
      and not xpmod.died_in(cl_ok, 0, 130000) and not xpmod.died_in(cl_ins, 0, 130000)
      and xpmod.lost_deaths(cl_dead) == [70000] and xpmod.lost_deaths(cl_ins) == [],
      "XP: morte sem seguro tira 5%% do nível, e a medida da subida de nível soma isso de volta (204 + 50 = 254 em "
      "102 pela lista); com o Seguro Estendido gasto na morte nada muda -> %s %s %s" % (sc_ok, sc_dead, sc_ins))
# a previsão desconta a morte sem seguro (5% do nível, nunca abaixo de 0) e avisa
evd3 = []
for i, aid in enumerate((52701, 52702, 52703)):
    evd3 += [(i * 60000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 60000 + 300, fr.skill_damage(ME, aid, 5000)),
             (i * 60000 + 400, fr.vanish(aid, 1))]
evd3.append((200000, fr.skill_damage(ME, 77, 1)))
p_ok = xpmod.progress(combat_of(fr.build(ME, evd3, xp=(7200, 500, 1000))[0]), {})
c_dead3 = combat_of(fr.build(ME, sorted(evd3 + [(90000, fr.vanish(ME, 1))], key=lambda x: x[0]),
                             xp=(7200, 500, 1000))[0])
p_dead = xpmod.progress(c_dead3, {})
p_ins = xpmod.progress(combat_of(fr.build(ME, sorted(evd3 + [(90000, fr.vanish(ME, 1)), (90005, struct.pack(
    "<HHIIHB", rrf.P_ITEM_USE, 20, 6413, ME, 9, 1))], key=lambda x: x[0]), xp=(7200, 500, 1000))[0]), {})
p_cap = xpmod.progress(combat_of(fr.build(ME, sorted(evd3 + [(100, fr.vanish(ME, 1))], key=lambda x: x[0]),
                                          xp=(7200, 10, 1000))[0]), {})
check(abs(p_ok["xp"] - p_dead["xp"] - 50) < 1e-6 and abs(p_ins["xp"] - p_ok["xp"]) < 1e-6 and p_dead["deaths"] == 1
      and abs(p_cap["lost"] - 10) < 1e-6 and xpmod.death_note(c_dead3, {}) == (1, 5.0)
      and xpmod.death_text(1, 5.0) == "morte sem seguro −5%",
      "XP: a previsão desconta 5%% do nível por morte sem seguro (nada com o Seguro Estendido; nunca mais do que "
      "havia) e avisa -> %s %s %s %s" % (round(p_ok["xp"]), round(p_dead["xp"]), round(p_ins["xp"]), p_cap["lost"]))
# no período de um Monster Spotlight conhecido o automático não adivinha mapa: a marca automática antiga sai, a
# feita à mão fica
with tempfile.TemporaryDirectory() as tmp8:
    for name, date, exp, events in (("a.rrf", (2026, 11, 17, 19, 35, 0), 1000, ev),
                                    ("b.rrf", (2026, 11, 17, 19, 45, 40), 1000 + 133, [])):
        with open(os.path.join(tmp8, name), "wb") as f:
            f.write(fr.build(ME, events, date=date, xp=(7100, exp, 10 ** 9))[0])
    rf8 = meter.ReplayFile(os.path.join(tmp8, "a.rrf"))
    rf8.poll(max_bytes=1 << 30)
    here8 = xpmod.map_key(rf8.combat.map)
    cfg8 = {"xp_spot": {here8: {"pct": 20, "when": "2026-11-12", "auto": True},
                        "outro": {"pct": 50, "when": "2026-11-12", "auto": False}}}
    xpmod.calibrate(rf8.combat, cfg8, meter.xp_after)
    cfg9 = {}
    xpmod.calibrate(rf8.combat, cfg9, meter.xp_after)
    check(cfg8["xp_spot"] == {"outro": {"pct": 50, "when": "2026-11-12", "auto": False}} and not cfg9.get("xp_spot"),
          "XP automática: no período do Monster Spotlight (lista oficial na conta) nenhum mapa é marcado por palpite e "
          "a marca automática antiga sai; a feita à mão fica -> %s %s" % (cfg8.get("xp_spot"), cfg9.get("xp_spot")))
# nome de disfarce na instância: os MVPs do Laboratório Central chegam todos como "Criatura não identificada"
evd = [(0, fr.spawn(71001, "mob", 1087, "\x1c52Z2Bw\x1c", boss=2)), (0, fr.spawn(71002, "mob", 1980, "Rótulo")),
       (0, fr.spawn(71003, "mob", 2087, "Rótulo")), (0, fr.spawn(71004, "mob", 20641, "Broken Robovac#3")),
       (0, fr.spawn(71005, "mob", 1002, "Nome do jogo")), (0, fr.spawn(71006, "mob", 20581, "#grn_1")),
       (0, fr.spawn(71007, "mob", 20639, "2 Zone Patrol#1")), (0, fr.spawn(71008, "mob", 20641, "2 Zone Patrol#1"))]
cd = combat_of(fr.build(ME, evd)[0])
got = [cd.name_of(a) for a in (71001, 71002, 71003, 71004, 71005, 71006, 71007, 71008)]
check(got[:3] == [meter.monster_name(1087), meter.monster_name(1980), meter.monster_name(2087)] and all(got[:3])
      and got[3] == "Broken Robovac" and got[4] == "Nome do jogo" and got[5] == meter.monster_name(20581) and got[5]
      and got[6] == got[7] == "2 Zone Patrol",
      "nomes: disfarce da instância (chave conhecida ou mesmo nome em monstros diferentes) vira o nome de verdade; "
      "rótulo \"nome#n\" aparece como no jogo, sem o #, mesmo repetido em monstros diferentes; o nome normal "
      "continua -> %s" % got)
# monstros do Lago do Abismo 4 (abyss_04) com XP; sem nenhum monstro de XP conhecida a previsão diz isso
check(all(xpmod.MOB_EXP.get(m) for m in range(20612, 20618)) and xpmod.MOB_EXP[20617][:2] == [207, 249407]
      and xpmod.MOB_EXP[20773][1] == 252562 and xpmod.MOB_EXP[20604][1] == 179251 and xpmod.MOB_EXP[1085][1:] == [0, 0],
      "XP: os monstros do Lago do Abismo 4 têm XP (não ficam em \"calculando\" para sempre)")
# XP de cada nível da 3ª classe (Mestre Estelar 4239), a mesma que o jogo mandou no começo das gravações
check(xpmod.table_need(4239, 163) == 132704283 and xpmod.table_need(4239, 180) == 371309911
      and xpmod.table_need(4239, 200) is None and xpmod.table_need(4302, 240) == 45000661693
      and xpmod.table_need(4302, 248) == 220850071960 and xpmod.table_need(999999, 100) is None,
      "XP: a XP do nível vem da tabela também fora da 4ª classe (o %% e o tempo até o nível seguem depois de upar)")
# 4ª classe do 200 ao 223: o que o jogo mandou no 200 e no 201 (Lago do Abismo) e no 224; do 220 em diante × 1,22
check(xpmod.table_need(4302, 200) == 653047446 and xpmod.table_need(4302, 201) == 655006588
      and xpmod.table_need(4253, 219) == 691293473 and xpmod.table_need(4302, 220) == 691293473 * 122 // 100
      and xpmod.table_need(4302, 224) == 1868364511 and xpmod.table_need(4262, 246) == 148380859958
      and xpmod.table_need(4302, 249) == 269437087791,
      "XP: a XP dos níveis 200 a 223 da 4ª classe é conhecida (o %% e o tempo até o nível seguem ao subir do 200 "
      "para o 201) -> %s" % [xpmod.table_need(4302, lv) for lv in (200, 201, 219, 220, 224)])
# classes 1 e 2 do 79 ao 98: o LATAM não reduziu a XP como o rAthena (um Ferreiro no 96 recebeu 2.098.423 do jogo;
# no 76 as duas tabelas conferem); transcendentais pela mesma tabela antiga; o Superaprendiz (23) tem tabela;
# Doram e 3ª classe continuam a do rAthena
got = [xpmod.table_need(j, lv) for j, lv in ((10, 76), (10, 78), (10, 79), (10, 96), (10, 97), (10, 98), (10, 99),
                                              (4011, 96), (23, 96), (4218, 96), (4239, 175))]
check(got == [149620, 158216, 181403, 2098423, 2465723, 2979788, None, 3567320, 2098423, 890438, 320295193],
      "XP: classes 1 e 2 do 79 ao 98 pela XP do LATAM (o \"já subiu\" antes da hora num Ferreiro 96→97) -> %s" % got)
old_s = {"xp_corr": {"7100": {"samples": [[2.0, 100, "2026-10-01 10:00", "x#0"], [1.0, 100, "2026-11-05 10:00", "y#0"]]}}}
new_s = {"xp_corr": {"7100": {"samples": [[2.0, 100, "2026-10-20 10:00", "x#0"], [1.0, 100, "2026-11-05 10:00", "y#0"]]}}}
check(xpmod.stored_correction(cq, old_s) == (1.0, 1) and xpmod.stored_correction(cq, new_s) == (1.5, 2),
      "XP: a correção guardada usa as medidas de até 30 dias antes da mais nova -> %s %s"
      % (xpmod.stored_correction(cq, old_s), xpmod.stored_correction(cq, new_s)))
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


# reiniciou a gravação com o Milagre ligado: o que falta de verdade vem logo depois do efeito no registro do início;
# o restante do fim do registro é o do último aviso do servidor (no Milagre, sempre a hora cheia do proc)
def combat_start(data):
    h = rrf.Header(data)
    c = meter.Combat(rrf.Session(h, data), 10000)
    c.start_statuses(rrf.statuses_at_start(h, data))     # como o ReplayFile, antes do fluxo
    r = rrf.StreamReader(h.keys, rrf.WANTED)
    c.feed(r.feed(data[h.stream_offset:]), r.last_time)
    c.finished = True
    return c


data = fr.build(ME, [(5000, fr.skill_damage(ME, 77, 1))],
                buffs=[(meter.MIRACLE_EFST, 611387, 3600000, 3600000), (39, 1395727, 1800000, 1414082),
                       (802, 999999, 9999, 9999), (895, -18355, 0, 0)])[0]
got = rrf.statuses_at_start(rrf.Header(data), data)
c = combat_start(data)
check(got == [(meter.MIRACLE_EFST, 3600000, 611387), (39, 1800000, 1395727), (802, 9999, 9999), (895, 0, 0)]
      and c.status_on[(ME, 39)][2] == 1395727,
      "buffs do início: vale o que faltava quando a gravação começou (o sem tempo fica como estava) -> %s" % got)
check(c.miracle_left() == 611387 - 5000 and c.miracle_windows() == [(0, 5000)]
      and not any(a[2] == "miracle" for a in c.alerts),
      "Milagre já ligado no início: conta o que falta de verdade, não 1 hora (e sem aviso de novo) -> %s"
      % c.miracle_left())
c = combat_start(fr.build(ME, [(700000, fr.skill_damage(ME, 77, 1))],
                          buffs=[(meter.MIRACLE_EFST, 611387, 3600000, 3600000)])[0])
check(c.miracle_left() is None and c.miracle_windows() == [(0, 611387)],
      "Milagre já ligado no início: acaba na hora certa -> %s" % c.miracle_windows())
# buff que passou do tempo que o jogo mandou sem o "acabou" chegar (31 em ~32.600 nas gravações do usuário, como um
# Magnificat): acaba na hora; o aviso do jogo continua valendo quando chega (antes do tempo: perdeu o buff)
c = combat_of(fr.build(ME, [(1000, fr.status(ME, 20, True, 90000, 90000, 1)),           # Magnificat de 90 s
                            (2000, fr.status(ME, 10, True, 240000, 240000, 10)),          # Bênção de 240 s...
                            (30000, fr.status(ME, 10, False)),                             # ...perdida aos 30 s
                            (93000, fr.skill_damage(ME, 77, 1))])[0])
mag_93 = [s for s in c.statuses(ME) if s[1] == 20]
active_93 = c.status_active((ME, 20))
c = combat_of(fr.build(ME, [(1000, fr.status(ME, 20, True, 90000, 90000, 1)), (2000, fr.status(ME, 10, True, 240000, 240000, 10)),
                            (30000, fr.status(ME, 10, False)), (200000, fr.status(ME, 20, True, 90000, 90000, 1)),
                            (250000, fr.skill_damage(ME, 77, 1))])[0])
mag = sorted(s[2:] for s in c.statuses(ME) if s[1] == 20)
bless = [s[2:] for s in c.statuses(ME) if s[1] == 10]
check(mag_93 == [(ME, 20, 1000, 93000)] and active_93 and mag == [(1000, 91000), (200000, 250000)]
      and bless == [(2000, 30000)] and c.status_active((ME, 20)),
      "buffs: o aviso do jogo encerra antes da hora; sem o aviso, passado o tempo (+5 s) acaba na hora certa, e ligar "
      "de novo abre outro trecho -> %s %s" % (mag, bless))

# reiniciou para calibrar: a gravação nova (até 3 min depois, mesmo personagem) segue o ritmo do fim da anterior,
# sem outros 10 min de "calculando…" no "Até o próximo nível"
ea = []
for i in range(73):                                                     # um abate a cada 10 s por 12 min
    aid = 54000 + i
    ea += [(i * 10000, fr.spawn(aid, "mob", 1124, "Goblin")), (i * 10000 + 300, fr.skill_damage(ME, aid, 5000)),
           (i * 10000 + 400, fr.vanish(aid, 1))]
c_a = combat_of(fr.build(ME, ea, date=(2026, 11, 19, 20, 0, 0), xp=(7311, 1000, 10 ** 9))[0])


def restarted(date, gid=7311, n=1):
    ev = []
    for i in range(n):                                                  # o 1º abate 1 min depois de começar
        aid = 54100 + i
        ev += [(60000 + i * 10000, fr.spawn(aid, "mob", 1124, "Goblin")),
               (60300 + i * 10000, fr.skill_damage(ME, aid, 5000)), (60400 + i * 10000, fr.vanish(aid, 1))]
    return combat_of(fr.build(ME, ev, date=date, xp=(gid, 1000 + 73 * 34, 10 ** 9))[0])


c_b = restarted((2026, 11, 19, 20, 12, 30))                              # 30 s depois do fim da anterior
before = (xpmod.warming_up(c_b, {}), xpmod.time_to_level(c_b, {}))
linked = xpmod.carry_from(c_b, c_a, {})
pace_a, pace_b = xpmod.recent_pace(c_a, {}), xpmod.recent_pace(c_b, {})
check(before == (True, (None, None)) and linked and not xpmod.warming_up(c_b, {})
      and xpmod.time_to_level(c_b, {})[0] and pace_a and abs(pace_b - pace_a) < 1e-6,
      "XP: reiniciar a gravação não volta ao \"calculando…\": a nova segue o ritmo do fim da anterior -> %s %s/min"
      % (before, pace_b and round(pace_b, 1)))
far, other, old = (restarted((2026, 11, 19, 20, 16, 0)), restarted((2026, 11, 19, 20, 12, 30), gid=7312),
                   restarted((2026, 11, 19, 19, 0, 0)))
check(not xpmod.carry_from(far, c_a, {}) and not xpmod.carry_from(other, c_a, {})
      and not xpmod.carry_from(old, c_a, {}) and xpmod.warming_up(far, {}) and xpmod.carry(other) is None,
      "XP: só continua a gravação do mesmo personagem que acabou até 3 min antes (nem outra, nem uma velha aberta)")
c_c = restarted((2026, 11, 19, 20, 14, 0))                              # reiniciou de novo, 30 s depois da 2ª
pace_c = xpmod.recent_pace(c_c, {}) if xpmod.carry_from(c_c, c_b, {}) else None
c_d = restarted((2026, 11, 19, 20, 12, 30), n=61)                       # 10 min de farm só dela: não usa a anterior
xpmod.carry_from(c_d, c_a, {})
check(pace_c and abs(pace_c - pace_a) / pace_a < 0.1 and xpmod.recent_parts(c_d, {})[1:] == (0.0, 0.0),
      "XP: reiniciar duas vezes seguidas mantém o ritmo; com 10 min de farm na nova, a anterior sai da conta -> %s"
      % (pace_c and round(pace_c, 1)))

# o Milagre dobra a XP quando liga e quando acaba: o ritmo dos últimos 10 min vê a mudança na hora, não 10 min depois
# (um jogador subiu para o 250 uns 8 min depois do previsto: o Milagre acabou 14 min antes da subida, 2026-11-19)
def farm_miracle(extra=(), date=(2026, 11, 19, 21, 0, 0), first=0):
    ev = list(extra)
    for i in range(73):                                                 # um abate a cada 10 s por 12 min
        aid = 56000 + first + i
        ev += [(i * 10000 + 2000, fr.spawn(aid, "mob", 1124, "Goblin")),
               (i * 10000 + 2300, fr.skill_damage(ME, aid, 5000)), (i * 10000 + 2400, fr.vanish(aid, 1))]
    return combat_of(fr.build(ME, sorted(ev, key=lambda e: e[0]), date=date, xp=(7320, 1000, 10 ** 9))[0])


MIR_ON = fr.status(ME, meter.MIRACLE_EFST, True, 3600000, 3600000, 1)
m_plain = farm_miracle()
m_ended = farm_miracle([(1000, MIR_ON), (480000, fr.status(ME, meter.MIRACLE_EFST, False))])    # acabou aos 8 min
m_began = farm_miracle([(480000, MIR_ON)])                                                    # ligou aos 8 min
p_plain, p_ended, p_began = (xpmod.recent_pace(m_plain, {}), xpmod.recent_pace(m_ended, {}),
                             xpmod.recent_pace(m_began, {}))
check(p_plain and abs(p_ended / p_plain - 1.0) < 1e-6 and abs(p_began / p_plain - 2.0) < 1e-6
      and abs(xpmod.time_to_level(m_ended, {})[0] / xpmod.time_to_level(m_plain, {})[0] - 1.0) < 0.02,
      "XP: o Milagre que acabou (ou ligou) no meio dos últimos 10 min muda o ritmo do \"Até o próximo nível\" na hora "
      "-> %.2f e %.2f do ritmo sem Milagre" % (p_ended / p_plain, p_began / p_plain))
m_a = farm_miracle([(1000, MIR_ON)])                                    # com Milagre até o fim...
m_b = combat_of(fr.build(ME, [(60000, fr.spawn(56900, "mob", 1124, "Goblin")),
                              (60300, fr.skill_damage(ME, 56900, 5000)), (60400, fr.vanish(56900, 1))],
                         date=(2026, 11, 19, 21, 12, 32), xp=(7320, 1000 + 73 * 68, 10 ** 9))[0])   # ...e a nova sem
xpmod.carry_from(m_b, m_a, {})
check(abs(xpmod.recent_pace(m_b, {}) * 2.0 / xpmod.recent_pace(m_a, {}) - 1.0) < 0.05,
      "XP: reiniciou e o Milagre não veio junto: o ritmo que veio da gravação anterior cai para a metade -> %.2f"
      % (xpmod.recent_pace(m_b, {}) / xpmod.recent_pace(m_a, {})))

# o aviso de calibrar voltava depois de reiniciar (relato de um jogador no clock_01, 2026-11-19): a gravação começava
# na cidade e a medida ficava sem mapa; o jogo leva 1,5 a 3 min para parar e começar outra (o limite era 1 min); e o
# aviso aparecia quando gravar de novo nem mediria (missão entregue, monstro sem XP no trecho)
def farm_clock(extra=()):
    ev = [(1000, fr.spawn(55000, "mob", 1124, "Goblin")), (1300, fr.skill_damage(ME, 55000, 5000)),
          (1400, fr.vanish(55000, 1)), (60000, fr.map_move("clock_01", 100, 100))]     # 1 abate na cidade, 33 na torre
    for i in range(33):
        aid = 55001 + i
        ev += [(70000 + i * 20000, fr.spawn(aid, "mob", 1124, "Goblin")),
               (70300 + i * 20000, fr.skill_damage(ME, aid, 5000)), (70400 + i * 20000, fr.vanish(aid, 1))]
    return sorted(ev + list(extra), key=lambda e: e[0])


ck = combat_of(fr.build(ME, farm_clock(), map_name="aldebaran", xp=(7500, 100, 10 ** 9))[0])
ck.finished = False
cq_ = combat_of(fr.build(ME, farm_clock([(500000, fr.quest_done(3477))]), map_name="aldebaran",
                         xp=(7500, 100, 10 ** 9))[0])
cu_ = combat_of(fr.build(ME, farm_clock([(500000, fr.spawn(55100, "mob", 21999, "")),
                                         (500300, fr.skill_damage(ME, 55100, 5000)), (500400, fr.vanish(55100, 1)),
                                         (520000, fr.spawn(55101, "mob", 21999, "")),     # 2 entre 33: 6% da lista
                                         (520300, fr.skill_damage(ME, 55101, 5000)), (520400, fr.vanish(55101, 1))]),
                         map_name="aldebaran", xp=(7500, 100, 10 ** 9))[0])
cq_.finished = cu_.finished = False
log = {"xp_learn": {"measures": [
    dict(src="x.rrf#0", date="2026-10-20 10:00", map="clock_01", mins=12, kills=300, ratio=1.1, gain=5000, char="9999",
         quests=[]),
    dict(src="y.rrf#0", date="2026-10-20 11:00", map="pay_fild01", mins=12, kills=300, ratio=1.0, gain=5000,
         char="9999", quests=[]),
    dict(src="z.rrf#fim", date="2026-10-20 12:00", map="gef_fild06", mins=12, kills=300, ratio=0.5, gain=5000,
         char="9999", quests=[3477])]}}
p_log = xpmod.predict(log, 7500, "clock_01")
check(xpmod._one_map(ck, 0, ck.now) is None and xpmod._kill_map(ck, 0, ck.now) == "clock_01"
      and xpmod.calibration_hint(ck, {}) == "clock_01" and xpmod.calibration_hint(cq_, {}) is None
      and xpmod.calibration_hint(cu_, {}) is None and xpmod.calibration_hint(ck, log) is None
      and p_log is not None and p_log[1] == "registro" and abs(p_log[0] - 1.1) < 1e-9
      and xpmod.predict(log, 7500, "gef_fild06") is None,
      "XP: começou na cidade e farmou no clock_01: a medida é do clock_01; sem aviso quando gravar de novo não mede "
      "(missão, monstro sem XP) ou quando o mapa já foi medido antes (registro, sem as com missão) -> %s" % (p_log,))
with tempfile.TemporaryDirectory() as tmp:
    def pair(gap_s, name, gid):
        data, _off = fr.build(ME, farm_clock(), date=(2026, 11, 19, 10, 0, 0), map_name="aldebaran",
                              xp=(gid, 1000, 10 ** 9))
        pa = os.path.join(tmp, name + "_a.rrf")
        with open(pa, "wb") as f:
            f.write(data)
        end = 10 * 3600 + 70400 // 1000 + 32 * 20 + gap_s           # o último abate fecha a gravação
        when = (2026, 11, 19, end // 3600, end // 60 % 60, end % 60)
        data, _off = fr.build(ME, [], date=when, xp=(gid, 1000 + 34 * 34 * 3, 10 ** 9))
        with open(os.path.join(tmp, name + "_b.rrf"), "wb") as f:
            f.write(data)
        rf = meter.ReplayFile(pa)
        rf.poll(max_bytes=1 << 30)
        cfg_p = {}
        xpmod.calibrate(rf.combat, cfg_p, meter.xp_after)
        return [(x[3].split("#")[1], x[4]) for x in (cfg_p.get("xp_corr") or {}).get(str(gid), {}).get("samples", [])]
    got2, got4 = pair(150, "dois", 7501), pair(240, "quatro", 7502)
check(got2 == [("fim", "clock_01")] and got4 == [],
      "XP: a gravação seguinte 2,5 min depois ainda mede (o jogo demora para parar e começar outra), 4 min não; a "
      "medida é do mapa dos abates -> %s / %s" % (got2, got4))


# resumo da sessão (o usuário, 2026-11-19): o antigo "Sorte grande" (qualquer carta ou favorito) era fácil demais;
# agora a carta de MVP, a mão de 6 cartas ou mais e o item marcado são destaques separados
def loot(items, mob=1039):
    """O Bafomé morre e deixa cair cada item de `items`; quem grava pega todos."""
    ev = [(0, fr.spawn(58000, "mob", mob, "Bafomé", boss=mob == 1039)), (500, fr.skill_damage(ME, 58000, 100)),
          (900, fr.vanish(58000, 1))]
    for i, item in enumerate(items):
        mid = 950000 + i
        ev += [(1000, item_fall(mid, item, 100 + i, 100)), (2000 + i * 300, pick_action(ME, mid)),
               (2010 + i * 300, struct.pack("<HI", rrf.P_ITEM_GONE, mid)), (2050 + i * 300, pickup_ack(item))]
    return combat_of(fr.build(ME, ev)[0])


hl_mvp = session.highlights(loot([4147, 4001]), {})
hl_six = session.highlights(loot([4001, 4001, 4001, 4002, 4004, 4006]), {})
hl_five = session.highlights(loot([4001, 4001, 4002, 4004, 4006]), {})
hl_fav = session.highlights(loot([607], 1002), {}, favs=[607])
hl_ping = session.highlights(loot([607], 1002), {}, marked=[607])
first = hl_mvp[0] if hl_mvp else {}
six = next((h for h in hl_six if h["key"] == "cards"), {})
check(first.get("key") == "mvp_card" and first["deal"]["cards"] == [4147] and first["deal"]["mob"] == 1039
      and first["deal"]["name"] and not any(h["key"] == "cards" for h in hl_mvp)
      and six.get("deal", {}).get("n") == 6 and len(six["deal"]["cards"]) == 6
      and not any(h["key"] == "cards" for h in hl_five)
      and [h["key"] for h in hl_fav] == ["marked"] and [h["key"] for h in hl_ping] == ["marked"]
      and not session.highlights(loot([607], 1002), {})
      and not {"cards", "marked"} & set(session.hl_chosen({"session_hl_off": ["card"]}))
      and "mvp_card" in session.hl_chosen({"session_hl_off": ["card"]}),
      "resumo da sessão: carta de MVP (com quem deixou cair) na frente; mão de cartas só com 6 ou mais; item favorito "
      "ou marcado nos avisos à parte; quem desligou o antigo \"Sorte grande\" fica sem os dois novos -> %s / %s"
      % ([h["key"] for h in hl_mvp], six.get("chip")))
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

# --- aviso de item: busca na lista do jogo, som e os itens marcados que caíram -------------
import itemping  # noqa: E402

cat = [(i, n, itemping.norm(n)) for i, n in ((501, "Poção Vermelha"), (502, "Poção Laranja"), (4001, "Carta Poring"),
                                             (545, "Poção Vermelha Compacta"), (12184, "Kit de Poção Vermelha"))]
check(itemping.search("pocao verm", rows=cat) == [(501, "Poção Vermelha"), (545, "Poção Vermelha Compacta"),
                                                 (12184, "Kit de Poção Vermelha")]
      and itemping.search("4001", rows=cat) == [(4001, "Carta Poring")]
      and itemping.search("PORING carta", rows=cat) == [(4001, "Carta Poring")]
      and itemping.search("  ", rows=cat) == [] and itemping.search("xyz", rows=cat) == [],
      "aviso de item: busca sem acento e sem maiúsculas, por palavras ou pelo número; os que começam com o texto "
      "vêm primeiro -> %s" % itemping.search("pocao verm", rows=cat))
w1, w2 = itemping.wav(40, "grave"), itemping.wav(40, "bem agudo")
check(w1[:4] == b"RIFF" and len(w1) == len(w2) and w1 != w2 and itemping.wav(40, "tom que não existe")
      == itemping.wav(40, itemping.DEFAULT_TONE) and len(w1) < 20000,
      "aviso de item: um toque curto (%d bytes), diferente em cada tom" % len(w1))


def live_combat(events):
    """Combat alimentado aos poucos, como numa gravação em curso: devolve (c, até(t))."""
    data = fr.build(ME, sorted(events, key=lambda e: e[0]))[0]
    h = rrf.Header(data)
    c = meter.Combat(rrf.Session(h, data))
    for e in rrf.initial_entities(h, data):
        c.add_entity(e)
    recs = list(rrf.StreamReader(h.keys, rrf.WANTED).feed(data[h.stream_offset:]))
    at = [0]

    def upto(t):
        batch = []
        while at[0] < len(recs) and recs[at[0]][0] <= t:
            batch.append(recs[at[0]])
            at[0] += 1
        c.feed(batch, t)
    return c, upto


gone = lambda map_id: struct.pack("<HI", rrf.P_ITEM_GONE, map_id)                       # noqa: E731
ev = [(0, fr.spawn(50101, "mob", 1002, "Poring")), (0, fr.spawn(OTHER, "pc", 4252, "Outro")),
      (500, fr.skill_damage(ME, 50101, 100)), (900, fr.vanish(50101, 1)),
      (1200, item_fall(900001, 607, 100, 100)), (1200, item_fall(900002, 909, 100, 101, 3)),
      (1200, item_fall(900003, 4001, 102, 100)), (1250, struct.pack("<HI", rrf.P_MVP_ITEM, 607)),
      (3000, pick_action(ME, 900001)), (3010, gone(900001)), (3050, pickup_ack(607)),
      (4000, pick_action(OTHER, 900003)), (4010, gone(900003)),
      (5000, gone(900002)),                                   # saiu da vista sem ninguém pegar
      (70000, fr.skill_damage(ME, OTHER, 1))]
c, upto = live_combat(ev)
tr = itemping.Tracker()
upto(600)
first = tr.poll(c, {607, 909, 4001})
upto(1300)
fell = tr.poll(c, {607, 909, 4001})
upto(3100)
got = tr.poll(c, {607, 909, 4001})
upto(4100)
taken = tr.poll(c, {607, 909, 4001})
upto(5200)
soon = tr.poll(c, {607, 909, 4001})
upto(6600)
left = tr.poll(c, {607, 909, 4001})
upto(70000)
late = tr.poll(c, {607, 909, 4001})
info = fell[0][1] if fell else {}
check(first == [] and [(k, d["item"]) for k, d in fell] == [("drop", 607), ("drop", 909), ("drop", 4001), ("mvp", 607)]
      and (info.get("map"), info.get("x"), info.get("y"), info.get("mob")) == ("prt_fild08", 100, 100, "Poring")
      and itemping.navi(info) == "/navi prt_fild08 100/100" and itemping.navi(fell[3][1]) is None
      and [(k, d["item"]) for k, d in got] == [("got", 607)] and [(k, d["item"]) for k, d in taken] == [("taken", 4001)]
      and soon == [] and [(k, d["item"], d["count"]) for k, d in left] == [("left", 909, 3)]
      and [(k, d["item"]) for k, d in late] == [("expired", 909)] and tr.watch == [],
      "aviso de item: caiu (com o lugar e o /navi), prêmio de MVP, pego por você, pego por outro, ficou para trás "
      "1,5 s depois de sair da vista e sumiu do chão depois de 1 min -> %s" % [
          [(k, d["item"]) for k, d in x] for x in (fell, got, taken, soon, left, late)])
# telou para outro mapa sem pegar: avisa na hora; item não marcado e replay já encerrado não avisam nada
c, upto = live_combat([(1200, item_fall(900001, 607, 100, 100)), (1200, item_fall(900002, 909, 100, 101)),
                       (2000, fr.map_move("prontera", 150, 150)), (2500, fr.stop(ME, 150, 150))])
tr = itemping.Tracker()
upto(1300)
a = tr.poll(c, {607})
upto(2600)
b = tr.poll(c, {607})
tr2 = itemping.Tracker()
check([(k, d["item"]) for k, d in a] == [("drop", 607)] and [(k, d["item"], d["map"]) for k, d in b]
      == [("left", 607, "prt_fild08")] and tr2.poll(c, {607}, live=False) == [] and tr2.poll(c, set()) == []
      and tr2.n_drops == 2,
      "aviso de item: trocar de mapa sem pegar avisa que ficou para trás (com o mapa de onde caiu); só itens "
      "marcados e só ao vivo -> %s %s" % (a, b))
# abrir o programa com a gravação em curso: o que caiu há mais de 5 s não avisa
c, upto = live_combat([(1200, item_fall(900001, 607, 100, 100)), (19000, item_fall(900002, 607, 110, 100)),
                       (20000, fr.skill_damage(ME, OTHER, 1))])
upto(20000)
tr = itemping.Tracker()
old = tr.poll(c, {607})
check([(k, d["x"]) for k, d in old] == [("drop", 110)],
      "aviso de item: ao pegar uma gravação em curso, só avisa do que caiu nos últimos segundos -> %s" % old)

# --- sessões longas: a XP guardada entre desenhos dá o mesmo que a conta feita do zero -------------
import xp as xpl  # noqa: E402

kills_ev = []
for i in range(60):
    aid = 53000 + i % 7                                       # o jogo reaproveita o id do monstro que renasce
    t = 1000 + i * 2000
    kills_ev += [(t, fr.spawn(aid, "mob", 1002 if i % 3 else 1113, "Poring")), (t + 300, fr.skill_damage(ME, aid, 500 + i)),
                 (t + 400, fr.skill_damage(OTHER, aid, 100)), (t + 600, fr.vanish(aid, 1))]
kills_ev += [(30000, fr.status(ME, 984, True, 600000, 600000)), (50000, fr.status(ME, 250, True, 1800000, 1800000, 100)),
             (90000, fr.status(ME, 250, False))]
c, upto = live_combat([(0, fr.spawn(OTHER, "pc", 4252, "Outro"))] + kills_ev)
same = True
for t in range(5000, 125001, 5000):
    upto(t)
    for cfg in ({}, {"xp_mode": "lista", "xp_bonuses": {"server": {"on": True, "pct": 100}}}):
        rows, unknown = xpl.kills(c)
        ref_rows, ref_unknown = xpl._all_kills(c)
        strip = lambda rs: [{k: v for k, v in r.items() if k != "total"} for r in rs]      # noqa: E731
        est = xpl.estimate(c, cfg, None)
        wins, sets, marks = xpl.windows(c, cfg), xpl.settings(cfg, c), xpl.marks_of(c)
        slow = sum(r["xp"] * xpl.factor_at(r["t"], wins, sets, r["mob"], marks) for r in ref_rows if r["xp"] is not None)
        part = xpl.kills(c, (t - 20000, t - 3000))[0]
        same = same and strip(rows) == strip(ref_rows) and unknown == ref_unknown and abs(est["kill_xp"] - slow) < 1e-6 \
            and [r["t"] for r in part] == [r["t"] for r in ref_rows if t - 20000 <= r["t"] <= t - 3000]
check(same and len(xpl.kills(c)[0]) == 60 and xpl.estimate(c, {}, None)["kill_xp"] > 0,
      "sessão longa: os abates somados aos poucos, as janelas guardadas e o fator por trecho dão a mesma XP que a "
      "conta inteira, a cada leitura (%d abates)" % len(xpl.kills(c)[0]))
c.reset()
upto(130000)
check(xpl.kills(c) == ([], 0), "sessão longa: zerar esvazia os abates guardados")

# --- duas gravações ao mesmo tempo (dois clientes): o medidor não pula de uma para a outra ---------
tmp = tempfile.mkdtemp()
try:
    w = meter.Watcher(tmp, auto=False)
    a_path, b_path = os.path.join(tmp, "a.rrf"), os.path.join(tmp, "b.rrf")
    now = time.time()
    with open(a_path, "wb") as fh:
        fh.write(b"x")
    first = w.scan(now)
    w.file = meter.ReplayFile(a_path)
    with open(b_path, "wb") as fh:                            # outra gravação começa: passa a seguir a nova
        fh.write(b"x")
    second = w.scan(now + 0.2)
    w.file = meter.ReplayFile(b_path)
    picks = []
    for i in range(6):                                        # as duas continuam sendo escritas, uma de cada vez
        path = a_path if i % 2 == 0 else b_path
        with open(path, "ab") as fh:
            fh.write(b"y")
        os.utime(path, (now + 1 + i, now + 1 + i))
        picks.append(os.path.basename(w.scan(now + 1 + i)))
    os.utime(b_path, (now - 60, now - 60))                    # a nova parou: volta para a que continua
    os.utime(a_path, (now + 8, now + 8))
    back = w.scan(now + 8.5)
    check(first == a_path and second == b_path and picks == ["b.rrf"] * 6 and back == a_path,
          "duas gravações em curso: segue a que começou por último sem pular entre elas, e volta para a outra "
          "quando ela para -> %s" % picks)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# --- cartão "Gravação nova": com um replay aberto à mão, o jogo começou a gravar outro ------------
tmp = tempfile.mkdtemp()
try:
    old_p, live_p, new_p, new2_p = (os.path.join(tmp, n) for n in ("velho.rrf", "aovivo.rrf", "nova.rrf", "nova2.rrf"))
    now = time.time()
    with open(old_p, "wb") as fh:
        fh.write(b"x")
    os.utime(old_p, (now - 3600, now - 3600))                 # um replay antigo, parado
    with open(live_p, "wb") as fh:                            # uma gravação em curso
        fh.write(b"x")
    w = meter.Watcher(tmp, auto=False)
    w.scan(now)
    w.open(old_p)                                             # a pessoa abre o antigo à mão
    first = w.offer(now + 0.2)                                # a que já gravava não é novidade: ela saiu de lá
    with open(new_p, "wb") as fh:                             # o jogo começa outra gravação
        fh.write(b"x")
    w.poll(now + 0.5)
    offered = w.offered
    w.skip(new_p)                                             # "Ficar neste"
    after_skip = w.offer(now + 0.7)
    with open(new2_p, "wb") as fh:                            # e mais outra: pergunta de novo
        fh.write(b"x")
    again = w.offer(now + 1.0)
    w.follow(again)                                           # "Seguir a nova"
    followed = (w.pinned, w.file.path if w.file else None)
    w.poll(now + 1.2)
    still = w.file.path if w.file else None
    check(first is None and offered == new_p and after_skip is None and again == new2_p
          and followed == (False, new2_p) and still == new2_p and w.offered is None and not w.pin_skip,
          "Gravação nova: com um replay aberto à mão, a gravação que começou depois é oferecida (a que já gravava "
          "não), 'Ficar neste' não pergunta de novo por ela, a próxima pergunta, e 'Seguir a nova' segue esta -> "
          "%s" % [first, offered, after_skip, again, followed, still])
    import cards as cardmod0  # noqa: E402
    check(cardmod0.enabled({}, "follow") and not cardmod0.enabled({"cards_off": ["follow"]}, "follow"),
          "Gravação nova: ligado por padrão e desligável na aba Cartões")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# --- 1.7: atributos, conjuração, recarga, pós-conjuração e itens de quem grava -------------------
import stats as stmod  # noqa: E402
import cards as cardmod  # noqa: E402
SUP = 2401
ev = [(0, fr.spawn(61000, "mob", BETEL, "Betelgeuse", boss=2)), (0, fr.spawn(SUP, "pc", 4256, "Cura"))]
ev += [(100, fr.party_hp(SUP, 50000, 50000))]
# 1 M por golpe até os 11 s; com a Garra Sombria no chefe (dos 11 s em diante), 2 M
ev += [(1000 + i * 500, fr.skill_damage(ME, 61000, 1000000 if 1000 + i * 500 < 11000 else 2000000, skill=5470, hits=1))
       for i in range(40)]
ev += [(500, fr.hp(120, 53)), (10000, fr.hp(100, 53)),                       # ASPD 188 -> 190
       (2000, struct.pack("<HHI", rrf.P_COOLDOWN, 5470, 300)),
       (2500, fr.cast(ME, 61000, 5470, 200)),
       (3000, fr.status(ME, meter.POSTDELAY_EFST, True, 500, 425)),
       (4000, struct.pack("<HHIIHB", rrf.P_ITEM_USE, 3, 501, ME, 9, 1)),
       (4100, struct.pack("<HHIIHB", rrf.P_ITEM_USE, 3, 501, SUP, 9, 1)),
       (5000, struct.pack("<HHiIBB", rrf.P_SKILL_FAIL, 5470, 0, 0, 0, rrf.FAIL_DELAY)),
       (6000, fr.skill_use(SUP, ME, 34)), (6500, fr.skill_use(SUP, ME, 34)),
       (11000, fr.status(61000, 730, True, 0, 20000, 150)),
       (15000, fr.skill_damage(61000, SUP, 30000, skill=83, hits=1))]
ev.sort(key=lambda e: e[0])
c17 = combat_of(fr.build(ME, ev)[0])
vals = stmod.values(c17)
row = next(r for r in stmod.casts(c17) if r["skill"] == 5470)
post = stmod.post_delay(c17)
check(vals["aspd"][1:] == (188.0, 190.0) and 188.0 < vals["aspd"][0] < 190.0 and stmod.stat_text("aspd", 188.04) == "188,0",
      "atributos: a ASPD de quem grava como o jogo mostra, com média, menor e maior -> %s" % (vals.get("aspd"),))
check(row["cooldown"] == 300 and row["cast"] == 200 and (post["base"], post["real"], post["n"]) == (500, 425, 1)
      and abs(post["cut"] - 0.15) < 1e-9,
      "conjuração de cada uso, recarga da skill e pós-conjuração (base e com as reduções) -> %s %s" % (row, post))
check([(r["item"], r["n"]) for r in stmod.items_used(c17)] == [(501, 1)] and stmod.blocked(c17) == 1
      and [(r["item"], r["n"]) for r in stmod.items_used(c17, None, SUP)] == [(501, 1)],
      "itens usados (de cada jogador à vista) e tentativas com a skill em recarga")
# jogadores: quem é do grupo e não deu dano também aparece, com o que usou e o que recebeu
prow = {r["aid"]: r for r in an.players(c17, None, 20000)}
check(SUP in prow and prow[SUP]["total"] == 0 and prow[SUP]["uses"] == 2 and prow[SUP]["items"] == 1
      and prow[SUP]["taken"] == 30000 and prow[ME]["party"] and "Cura" not in an.share_text(c17, None, 20000, "x")
      and [(r["skill"], r["uses"], r["targets"]) for r in an.support_uses(c17, None, SUP)] == [(34, 2, 1)],
      "jogadores: o suporte do grupo sem dano entra na lista (fora do ranking copiado) -> %s" % prow.get(SUP))
rep = an.monster_report(c17, None, 61000)
check(rep["total"] == 30000 and rep["hits"] == 1 and rep["victims"] == 1 and rep["best"]["victim"] == "Cura"
      and rep["top"]["name"] == "Cura" and rep["kills"] == [] and rep["skill_max"] == {83: 30000},
      "monstro: dano causado, maior golpe e quem mais apanhou -> %s" % rep)
# cartões: o contador da Garra Sombria no chefe com o tempo que falta, e as chaves dos cartões do programa
cfg17 = {}
check(cardmod.track(cfg17, "status", 730) and cardmod.is_tracked(cfg17, "status", 730)
      and cardmod.tracked(cfg17) == [dict(kind="status", id=730, where="target", show="counter", sound=None,
                                          before=cardmod.DEFAULT_BEFORE, snd="sino", tone=cardmod.DEFAULT_TONE,
                                          secs=0)]
      and any(r["id"] == 730 and r["group"] == "Debuff no alvo" for r in cardmod.search("garra")),
      "cartões: a busca acha a Garra Sombria e ela entra na lista olhando o alvo -> %s" % cfg17)
live = cardmod.live(c17, cardmod.tracked(cfg17))
check(len(live) == 1 and live[0]["target"] == "Betelgeuse" and live[0]["left"] == 20000 - (c17.now - 11000)
      and cardmod.time_text(dict(left=4200)) == "4,2 s" and cardmod.time_text(dict(left=75000)) == "1:15"
      and cardmod.time_text(dict(left=None, since=42000)) == "há 42 s",
      "cartões: contador com o tempo que falta (o jogo manda a duração do debuff no chefe) -> %s" % live)
cardmod.track(cfg17, "status", 1142)
check(cardmod.track(cfg17, "status", 730, show="card") and [t["id"] for t in cardmod.tracked(cfg17)] == [730, 1142]
      and cardmod.tracked(cfg17)[0]["show"] == "card" and not cardmod.track(cfg17, "status", 730, show="card")
      and live[0]["mob"] == BETEL,
      "cartões: o efeito pode aparecer como cartão (a escolha fica guardada, sem mudar a ordem da lista) e a linha "
      "leva o monstro em que ele está, para o desenho -> %s" % cfg17)
watch = cardmod.Watch()
watch.update(live, 100.0)
shown, ended = watch.update([], 101.0)
check(len(ended) == 1 and shown[0]["ended"] == 0.0 and cardmod.time_text(shown[0]) == "acabou"
      and watch.update([], 105.0) == ([], []), "cartões: quando o efeito acaba o contador pisca e some")
# som de cada efeito e temporizador escolhido
cfg18 = {}
cardmod.track(cfg18, "status", 730, sound="before", before=5, tone="grave", secs=30, snd="sonar")
cardmod.track(cfg18, "status", 1142, sound="start")
cardmod.track(cfg18, "status", 730, show="card")                       # mudar outra coisa não perde o som
t18 = cardmod.tracked(cfg18)
live18 = cardmod.live(c17, t18)
garra = next(r for r in live18 if r["key"] == "status:730")
check(t18[0]["sound"] == "before" and t18[0]["before"] == 5 and t18[0]["tone"] == "grave" and t18[0]["secs"] == 30
      and t18[0]["show"] == "card" and garra["total"] == 30000 and garra["left"] == 30000 - (c17.now - 11000)
      and cardmod.sound_text(cfg18, t18[0]) == "5 s antes de acabar" and cardmod.timer_text(t18[0]) == "30 s"
      and cardmod.timer_text(dict(secs=90)) == "1:30" and cardmod.timer_text(dict(secs=0)) == "do jogo"
      and cardmod.sound_of({"tracker_sound": True}, dict(sound=None)) == "end"
      and cardmod.sound_of({}, dict(sound=None)) == "off",
      "cartões: cada efeito guarda o som e o temporizador; o temporizador vale no lugar da duração do jogo -> %s"
      % t18)
w18, prev18 = cardmod.Watch(), {}
row = lambda left: [dict(key="status:730", left=left)]                 # noqa: E731
w18.update(row(9000), 0.0)
first = cardmod.sounds(cfg18, t18, w18, [], prev18)                     # já estava ativo ao abrir: nada
w18.update(row(6000), 1.0)
above = cardmod.sounds(cfg18, t18, w18, [], prev18)
w18.update(row(4000), 2.0)
cross = cardmod.sounds(cfg18, t18, w18, [], prev18)
w18.update(row(3000), 3.0)
again = cardmod.sounds(cfg18, t18, w18, [], prev18)
_shown, gone = w18.update([dict(key="status:1142", left=None)], 4.0)
start = cardmod.sounds(cfg18, t18, w18, gone, prev18)
import sounds as sndmod  # noqa: E402
waves = [sndmod.wav(k, "agudo", 40) for k in sndmod.KEYS]
check(first == [] and above == [] and cross == [("sonar", "grave")] and again == []
      and start == [("sino", cardmod.DEFAULT_TONE)] and len(sndmod.KEYS) >= 16
      and all(w[:4] == b"RIFF" and len(w) > 2000 for w in waves) and sndmod.wav("nada")[:4] == b"RIFF",
      "cartões: o som toca uma vez ao cruzar \"5 s antes de acabar\", e ao começar no efeito que pediu -> %s"
      % [first, above, cross, again, start])
cfg17 = {"alert_boss": True}
cardmod.set_enabled(cfg17, "maxpain", False)
one = cardmod.enabled(cfg17, "maxpain"), cardmod.enabled(cfg17, "boss_size")
for k in cardmod.BOSS_KEYS:
    cardmod.set_enabled(cfg17, k, False)
off = cfg17["alert_boss"]
cardmod.set_enabled(cfg17, "defense", True)
check(one == (False, True) and off is False and cfg17["alert_boss"] is True and cardmod.enabled(cfg17, "defense")
      and not cardmod.enabled(cfg17, "relief") and cardmod.boss_card_key(dict(mech="maxpain_off")) == "maxpain"
      and cardmod.boss_card_key(dict(size="L")) == "boss_size",
      "cartões: cada aviso do chefe tem a sua chave; todos desligados = avisos do chefe desligados -> %s" % cfg17)
# testes lado a lado: seções, o lado melhor e o que os testes antigos não guardaram
ta = dict(dps=200.0, damage=2000, hits=10, combat_ms=10000, active_ms=5000, crits=5, misses=0,
          stats={"aspd": [190.0, 188.0, 190.0]}, casts=[dict(name="Alvorada", n=5, cast=200, cooldown=300)],
          skills=[dict(name="Alvorada", total=2000, hits=10, share=1.0)], equip=[dict(slot="Arma", item="+12 A")])
tb = dict(dps=100.0, damage=1000, hits=10, combat_ms=10000, skills=[dict(name="Alvorada", total=1000, hits=10, share=1.0)],
          equip=[dict(slot="Arma", item="+11 B")])
side = testes.sides(ta, tb)
named = {r["name"]: r for r in side if r.get("kind") != "head"}
check([r["name"] for r in side if r.get("kind") == "head"][:3] == ["Dano", "Atributos (média na luta)", "Conjuração e recarga"]
      and named["DPS (em combate)"]["better"] == "high" and named["ASPD"]["a_txt"] == "190,0" and named["ASPD"]["b_txt"] is None
      and named["Alvorada · recarga"]["a_txt"] == "300 ms" and named["Erros"]["better"] == "low"
      and testes.equip_diff(ta, tb) == {"Arma"} and testes.sides(ta, None)[1]["b"] is None,
      "testes lado a lado: seções, atributos e recarga, e teste antigo sem esses dados -> %s" % sorted(named))

# --- 1.7: simulador de XP ------------------------------------------------------------------------
ev = []
for i in range(2):
    ev += [(1000 + i * 40000, fr.spawn(53001 + i, "mob", 1124, "Goblin")), (1100 + i * 40000, fr.skill_damage(ME, 53001 + i, 5000)),
           (1200 + i * 40000, fr.vanish(53001 + i, 1))]
ev += [(90000, fr.stop(ME, 1, 1))]
cs = combat_of(fr.build(ME, ev, xp=(7100, 1000, 10 ** 9))[0])
base = sum(r["xp"] for r in xpmod.kills(cs)[0])
none17 = {k: ("off",) for k in xpmod.SIM_KEYS}                    # tudo desligado: só a XP crua dos monstros
sim = lambda **kw: xpmod.simulate(cs, {}, None, dict(none17, **{k: ("on", v) for k, v in kw.items()}))  # noqa: E731
check(base > 0 and sim()["xp"] == base and sim(server=100)["xp"] == 2 * base
      and abs(sim(vip=20, njord=60, manual=100)["xp"] - base * (1.2 * 1.6 + 1.0)) < 1e-6
      and abs(sim(server=100, miracle=100)["factor"] - 4.0) < 1e-9 and sim(server=100)["per_hour"] == 2 * base * 40,
      "simulador de XP: [(1 + evento e conta) × (1 + itens e Njord) + manual] × Milagre, com os mesmos abates -> %s"
      % sim(vip=20, njord=60, manual=100))
# "como foi": sem trocar nada o simulado é a própria estimativa; trocar só o evento muda só o evento
ev = [(0, fr.status(ME, 78, True, 60000, 60000, 60))]                # Njord nos primeiros 60 s (só o 1º abate)
for i in range(2):
    ev += [(1000 + i * 80000, fr.spawn(54001 + i, "mob", 1124, "Goblin")), (1100 + i * 80000, fr.skill_damage(ME, 54001 + i, 5000)),
           (1200 + i * 80000, fr.vanish(54001 + i, 1))]
ev += [(60000, fr.status(ME, 78, False)), (120000, fr.stop(ME, 1, 1))]
cs = combat_of(fr.build(ME, ev, xp=(7100, 1000, 10 ** 9))[0])
cfg17 = {"xp_mode": "lista", "xp_bonuses": {"server": {"on": True, "pct": 100}}}
est17 = xpmod.estimate(cs, cfg17)
real17 = xpmod.sim_real(cs, cfg17)
same = xpmod.simulate(cs, cfg17, None, {})
ev200 = xpmod.simulate(cs, cfg17, None, {"server": ("on", 200)})
each = est17["base"] / 2.0
check(abs(same["xp"] - est17["kill_xp"]) < 1e-6 and abs(est17["kill_xp"] - each * (2 * 1.6 + 2)) < 1e-6
      and abs(ev200["xp"] - each * (3 * 1.6 + 3)) < 1e-6 and real17["server"] == dict(counted=True, cover=None, ms=None, pct=100.0)
      and abs(real17["njord"]["cover"] - 0.5) < 0.01 and real17["njord"]["ms"] == 60000 and real17["njord"]["pct"] == 60.0 and real17["miracle"]["cover"] == 0.0
      and abs(xpmod.simulate(cs, cfg17, None, {"njord": ("off",)})["xp"] - each * 4) < 1e-6
      and abs(xpmod.simulate(cs, cfg17, None, {"njord": ("on", 60)})["xp"] - each * 6.4) < 1e-6,
      "simulador de XP: sem trocar nada é a própria estimativa (Njord só no trecho em que valeu); o evento de 100%% "
      "para 200%% rende +50%% -> %s contra %s" % (ev200["xp"], est17["kill_xp"]))

# --- XP: o Lanche do Diabo (entrega que só abre a espera 5967), a Refeição especial e a 1ª etapa do Mímico ------
import quests  # noqa: E402
ev = [(0, fr.status(ME, 250, True, 1800000, 1800000, 100)),
      (1000, fr.pickup(70, 25509, 100)),                       # 100 Cascas Arredondadas Brilhantes no slot 70
      (5000, fr.item_del(70, 100)), (5000, fr.quest_add(5967)),  # entrega o lanche: sai da bolsa e nasce a espera
      (5200, fr.item_del(71, 1)), (6000, fr.quest_add(5967)),    # outra entrega sem saber o item (slot vazio)
      (9000, fr.quest_done(5967)), (9500, fr.stop(ME, 1, 1))]  # o fim da espera não é entrega
cs = combat_of(fr.build(ME, ev, xp=(7110, 0, 10 ** 12))[0])
rs = xpmod.quest_rows(cs, {})
check([(r["quest"], r.get("handin"), r["item"], r["base"], r["mult"]) for r in rs]
      == [(5967, True, 25509, 347798000.0, 2.0), (5967, True, None, 279337600.0, 2.0)]
      and xpmod.quest_in(cs, 4000, 5500) and not xpmod.quest_in(cs, 6500, 9500)
      and xpmod.estimate(cs, {})["quest_xp"] == (347798000 + 279337600) * 2.0,
      "lanche do Diabo: a espera que nasce na entrega conta como entrega, pelo item que saiu da bolsa (sem o item, "
      "o valor mais comum), com o bônus de missão; o fim da espera não -> %s"
      % [(r["quest"], r["item"], r["base"], r["mult"]) for r in rs])
_titles = quests.NAMES.titles
quests.NAMES.titles = {5967: "[Espera] Lanche do Diabo"}
_t1, _t2 = quests.row_title(rs[0]), quests.row_title(rs[1])
quests.NAMES.titles = _titles
check(_t1.startswith("Lanche do Diabo (") and _t2 == "Lanche do Diabo",
      "lanche do Diabo: o nome na lista é o da espera sem a etiqueta, com o item entregue -> %r, %r" % (_t1, _t2))
check(xpmod.quest_base(5966, {}) == 5455834375.0 and xpmod.quest_wait(5969) and not xpmod.quest_wait(5970),
      "Torre do Relógio: Refeição especial pelo valor medido no LATAM; a 1ª etapa do Mímico não dá XP")

# --- Amdarais: vida por dificuldade, pela fala do Oscar ou pela cura do chefe ------------------------------------
AMD = 61500


def _amd_fight(dead, said=None):
    """11 golpes de 200M a cada 2 s no Amdarais (cada golpe volta 65% 1 s depois, antes do próximo)."""
    ev = [(0, fr.spawn(AMD, "mob", 20573, "Phantom of Amdarais", boss=True))]
    ev += [(1000 + 2000 * i, fr.skill_damage(ME, AMD, 200000000)) for i in range(11)]
    if dead:
        ev.append((21100, fr.vanish(AMD, 1)))
    if said is not None:
        ev.append((60000, fr.npc_say(43520, meter.LEVEL_SAY_KEY, said, "Miragem")))
    ev.append((61000, fr.stop(ME, 1, 1)))
    return combat_of(fr.build(ME, ev)[0])


_ca, _cb, _cc = _amd_fight(True), _amd_fight(False), _amd_fight(True, said=4)
_ha = an.boss_hp(_ca, AMD, 2200000000, True, 20000)
_hb = an.boss_hp(_cb, AMD, 2200000000, False, 20000)
_hc = an.boss_hp(_cc, AMD, 2200000000, True, 20000)
_lost = [round(v / 1e6) for _t, v in an.heal_lost(_ca, AMD, an.BOSS_HEAL[20573])]
check(_lost[:3] == [200, 270, 340] and _lost[-1] == 900 and _ha[:2] == (900000000, "Nível 3")
      and _hb[:2] == (600000000, "Nível 1") and "no mínimo" in _hb[2]
      and _hc[:2] == (1050000000, "Nível 4") and "fala do NPC" in _hc[2] and _cc.said_level == [(60000, 4)],
      "Amdarais: vida pela fala do Oscar no fim; sem ela, pela cura (abate: o nível em que morre no último golpe; "
      "vivo: no mínimo, com a cura alta) -> %s %s %s %s" % (_lost, _ha, _hb, _hc))
_ta = tl.build(_ca, AMD)
_hp_pts = [v for _t, v in _ta["hp"]]
check(_ta["hp_max"] == 900000000 and _hp_pts[-1] == 0.0 and any(b > a for a, b in zip(_hp_pts, _hp_pts[1:]))
      and min(_hp_pts[:-1]) > 0.0,
      "Amdarais: a curva de HP da Linha do tempo sobe com a cura e só zera no abate -> %s"
      % [round(v, 3) for v in _hp_pts])

# --- marca de chefe: o servidor manda; sem marca, o mesmo monstro, o rAthena ou vida de chefe -----------------
GUARD, GUARD0, SWORD, ATRIA, HIDE, ORC0, AMD0, ERZ0 = 70001, 70002, 70003, 70004, 70005, 70006, 70007, 70008
_ev = [(0, fr.spawn(GUARD, "mob", 20542, "Guarda da Rekenber", boss=0)),      # comum de 1,47 mi de vida
       (0, fr.spawn(SWORD, "mob", 20536, "Espadachim Anônima", boss=2)),
       (0, fr.spawn(ATRIA, "mob", 2562, "Atria", boss=1)),
       (0, fr.spawn(HIDE, "mob", 20562, "#bb5m1_1", boss=1)),
       (1000, fr.skill_damage(ME, GUARD, 2000000)), (1100, fr.vanish(GUARD, 1)),
       (2000, fr.skill_damage(ME, SWORD, 435241860)), (2100, fr.vanish(SWORD, 1)),
       (3000, fr.stop(ME, 1, 1))]
# já na tela no começo (sem marca): um Guarda (o outro Guarda tem marca 0), o Orc Herói (MVP no rAthena, 362 mil de
# vida), o Amdarais (fora do rAthena, 2 bi) e a Erzsebet da Torre do Relógio (fora do rAthena, 37,7 mi)
_cm = combat_of(fr.build(ME, _ev, entities=[(GUARD0, "mob", 20542, "Guarda da Rekenber"),
                                            (ORC0, "mob", 1087, "Orc Herói"), (AMD0, "mob", 20573, "Amdarais"),
                                            (ERZ0, "mob", 20176, "Erzsebet")])[0])
_fights = [f["key"] for f in dd.boss_fights(_cm)]
check(not _cm.is_mvp(GUARD) and _cm.is_mvp(SWORD) and not _cm.is_mvp(ATRIA) and not _cm.is_mvp(GUARD0)
      and _cm.is_mvp(ORC0) and _cm.is_mvp(AMD0) and not _cm.is_mvp(ERZ0)
      and _cm.entities[GUARD0].boss is None and _cm.job_marks[20542] == 0
      and SWORD in _fights and GUARD not in _fights and not _cm.boss_like(GUARD),
      "MVP pela marca do servidor: comum de muita vida (Edda, Torre do Relógio) não vira MVP; sem marca, vale a do "
      "mesmo monstro, o rAthena e 50 mi de vida -> lutas %s" % _fights)
_hs = an.boss_hp(_cm, SWORD, 435241860, True, 100)
check(_hs[0] == 75500000 and "golpe que matou" in _hs[2] and _cm.name_of(HIDE) == "Objeto escondido",
      "abate de um golpe só: a vida é a da base (confere com o golpe que matou), não o golpe inteiro; rótulo de "
      "script sem nome no jogo vira objeto escondido -> %s %r" % (_hs, _cm.name_of(HIDE)))
_ev2 = [(0, fr.spawn(SWORD, "mob", 20536, "Espadachim Anônima", boss=2)),
        (1000, fr.skill_damage(ME, SWORD, 80000000)), (1500, fr.skill_damage(ME, SWORD, 10000000)),
        (1600, fr.vanish(SWORD, 1)), (3000, fr.stop(ME, 1, 1))]
_c2 = combat_of(fr.build(ME, _ev2)[0])
_h2 = an.boss_hp(_c2, SWORD, 90000000, True, 600)
check(_h2[:3] == (90000000, "", an._("dano até morrer")),
      "a base que não confere com o abate (já tinha passado da vida antes do último golpe) não vale -> %s" % (_h2,))
check(xpmod.MOB_EXP.get(20536) == [180, 5885540, 4780000] and xpmod.MOB_EXP.get(20562) == [170, 0, 0]
      and all(meter.MOB_SIZE.get(j) == "M" for j in range(20536, 20544)) and dd.boss_element(_cm, SWORD) == ("Fire", 2)
      and dd.boss_element(_cm, GUARD) == ("Neutral", 2),
      "Edda do Biolaboratório: XP, tamanho e propriedade da Espadachim Anônima e dos monstros das salas (Divine Pride)")

# --- arena noturna de Geffen: vida anunciada, saiu vivo no fim do tempo, curva com a vida do servidor ------------
BRUTO, RECH, AJR = 71001, 71002, 71003
_ev = [(0, fr.broadcast_list(meter.ARENA_HP_KEY, 124100000, 5)),
       (8000, fr.spawn(RECH, "mob", 20866, "Rechenier", boss=0)),
       (9000, fr.skill_damage(ME, RECH, 62734656)),
       (9100, fr.spawn(RECH, "mob", 20866, "Rechenier", boss=0, hp=(2000000000, 61365344))),
       (9200, fr.skill_damage(ME, RECH, 62734656)), (9300, fr.vanish(RECH, 1)),
       (20000, fr.broadcast_list(meter.ARENA_HP_KEY, 800000000, 9)),
       (28000, fr.spawn(BRUTO, "mob", 20859, "Bruto", boss=0)),
       (29000, fr.skill_damage(ME, BRUTO, 300000000)),
       (30000, fr.spawn(BRUTO, "mob", 20859, "Bruto", boss=0, hp=(2000000000, 500000000))),
       (31000, fr.spawn(BRUTO, "mob", 20859, "Bruto", boss=0, hp=(2000000000, 700000000))),      # curou 200 mi
       (32000, fr.skill_damage(ME, BRUTO, 100000000)),
       (33000, fr.spawn(AJR, "mob", 2566, "", boss=0, raw_name="알퐁스 쥬니어#0".encode("cp949"))),
       # fora da arena (sem anúncio) a vida mandada não muda nada: morre de dano que a gravação não mostra
       (40000, fr.spawn(ERZ0, "mob", 20176, "Erzsebet", boss=0, hp=(37709580, 22163868))),
       (41000, fr.skill_damage(ME, ERZ0, 1000000)), (42000, fr.vanish(ERZ0, 1)),
       (88000, fr.vanish(BRUTO, 1)),                                                             # o tempo acabou
       (90000, fr.stop(ME, 1, 1))]
_car = combat_of(fr.build(ME, _ev)[0])
_hb = an.boss_hp(_car, BRUTO, 400000000, False, 4000)
_fk = [f["key"] for f in dd.boss_fights(_car)]
check(RECH in _car.deaths and BRUTO not in _car.deaths and _car.left_alive.get(BRUTO) == (88000, 600000000)
      and ERZ0 in _car.deaths and ERZ0 not in _car.left_alive
      and _car.announced_hp == {RECH: (124100000, 5), BRUTO: (800000000, 9)}
      and _hb[0] == 800000000 and "arena" in _hb[2] and RECH in _fk and BRUTO in _fk,
      "arena noturna: a vida vem do anúncio da rodada, o adversário é luta de chefe e quem sumiu 'morto' com vida "
      "sobrando (o tempo acabou) saiu vivo -> %s %s %s" % (_car.left_alive, _car.announced_hp, _hb))
_tlb = tl.build(_car, BRUTO)["hp"]
check(abs(_tlb[-1][1] - 0.75) < 1e-9 and min(v for _t, v in _tlb) > 0 and any(b > a for (_x, a), (_y, b) in
                                                                               zip(_tlb, _tlb[1:])),
      "arena noturna: a curva de HP segue a vida que o servidor manda (sobe com a cura e termina viva) -> %s"
      % [(t, round(v, 3)) for t, v in _tlb])
_arg2 = rrf.broadcast_arglist(fr.broadcast_list("", raw=b"\x1clWJyDQ\x1d\x1cH2JyDQ\x1c\x1dFei\x1c"))
check(_car.name_of(AJR) == "Alfonso Jr." and rrf.decode_name("알퐁스".encode("cp949")) == "알퐁스"
      and rrf.decode_name("AÇÃO".encode("cp1252")) == "AÇÃO" and _arg2 == [("lWJyDQ", ["", "Fei"])]
      and rrf.broadcast_arglist(fr.broadcast_list("lGJyDQ", 4300000, 2)) == [("lGJyDQ", ["4300000", "2"])],
      "nome em coreano (sem tradução) vira o da base; português em cp1252 continua; anúncio com vários argumentos "
      "-> %r %r" % (_car.name_of(AJR), _arg2))

# --- cartões de classe e de papel (roles.py) -----------------------------------
import roles  # noqa: E402
import contrib as contrib_mod  # noqa: E402
ALLY1, ALLY2, ALLY3, ALLY4 = 3001, 3002, 3003, 3004
RBOSS = 60001


def role_combat(extra, job=4258):
    """Uma gravação com quem grava (da classe `job`), três aliados no grupo e o Bafomé (chefe), mais `extra`."""
    ev = [(0, fr.spawn(ALLY1, "pc", 4302, "Aliado1")), (0, fr.spawn(ALLY2, "pc", 4255, "Aliado2")),
          (0, fr.spawn(ALLY3, "pc", 4254, "Aliado3")), (0, fr.spawn(RBOSS, "mob", 1039, "Bafomé", boss=True)),
          (0, fr.party_hp(ALLY1, 100, 100)), (0, fr.party_hp(ALLY2, 100, 100)), (0, fr.party_hp(ALLY3, 100, 100)),
          (0, fr.hp(200000, rrf.SP_MAXHP)), (0, fr.hp(200000))]
    data, _ = fr.build(ME, sorted(ev + extra, key=lambda e: e[0]))
    cc = combat_of(data)
    cc.session.job = job          # o cabeçalho de mentira é sempre de Mestre Celestial
    return cc


# Redenção: o dano dos aliados protegidos chega como um golpe de quem usou nele mesmo (skill 0)
ev = [(3000, fr.skill_use(ME, ALLY1, 255)), (3010, fr.skill_use(ME, ALLY2, 255))]
for i in range(25):
    ev.append((4000 + 300 * i, fr.auto_attack(RBOSS, ALLY1, 90000 + i)))
    ev.append((4001 + 300 * i, fr.auto_attack(ME, ME, 90000 + i)))
ev.append((1200, fr.auto_attack(ME, ME, 50000)))                         # antes da Redenção: não conta
rc = role_combat(ev)
ab = roles.absorbed(rc)
check(ab is not None and ab["hits"] == 25 and ab["total"] == sum(90000 + i for i in range(25)) and ab["allies"] == 2
      and ab["life"] == 200000, "Redenção: 25 golpes que passaram para quem usou, 2 aliados protegidos, a vida dele "
      "-> %r" % (ab and {k: ab[k] for k in ("hits", "total", "allies", "life")}))
f_red = roles.found(rc, {"redeemer"})
check("redeemer" in f_red, "Redentor: %s absorvido = %.1f vidas (limite %d) -> o cartão" % (
    ab and ab["total"], (ab["total"] / 200000.0) if ab else 0, roles.HL_REDEEM_LIVES))
check(roles.absorbed(role_combat([(1000, fr.auto_attack(ME, ME, 9000))])) is None,
      "sem usar a Redenção: nada (o golpe nele mesmo não é dela)")
ev2 = [(500, fr.skill_use(ME, ALLY1, 255))] + [(1000 + 300 * i, fr.auto_attack(ME, ME, 40000)) for i in range(25)]
check("redeemer" not in roles.found(role_combat(ev2), {"redeemer"}), "Redentor: 5 vidas não bastam (limite 10)")

# Lex Aeterna: o pico de 10 s numa luta de chefe
ev = [(1000 + 400 * i, fr.skill_damage(ALLY1, RBOSS, 500000, skill=5473, hits=1)) for i in range(60)]
ev += [(1100 + 330 * i, fr.skill_use(ME, RBOSS, 78)) for i in range(70)]
rc = role_combat(ev, job=4256)
lx = roles.lex_fights(rc)
check(len(lx) == 1 and lx[0]["n"] == 70 and abs(lx[0]["peak"] - 3.1) < 0.11,
      "Lex: 70 usos no chefe, pico de ~3 por segundo -> %r" % ([(x["n"], x["peak"]) for x in lx],))
check("lex" in roles.found(rc, {"lex"}), "Chuva de Lex: pico acima de %s por segundo -> o cartão" % roles.HL_LEX_PER_S)
ev3 = [(1000 + 400 * i, fr.skill_damage(ALLY1, RBOSS, 500000, skill=5473, hits=1)) for i in range(60)]
ev3 += [(1100 + 900 * i, fr.skill_use(ME, RBOSS, 78)) for i in range(25)]
check("lex" not in roles.found(role_combat(ev3, job=4256), {"lex"}), "Chuva de Lex: ~1 por segundo não basta")

# Varredura: 21 monstros derrubados pela mesma skill no mesmo instante
ev = []
for i in range(21):
    aid = 70000 + i
    ev += [(0, fr.spawn(aid, "mob", 1002, "Poring")), (2000, fr.skill_damage(ME, aid, 9999, skill=5473, hits=1)),
           (2100, fr.vanish(aid))]
ev += [(0, fr.spawn(71000, "mob", 1002, "Poring")), (2000, fr.skill_damage(ME, 71000, 50, skill=5473, hits=1)),
       (2050, fr.skill_damage(ALLY1, 71000, 9999, skill=5473, hits=1)), (2100, fr.vanish(71000))]   # este, outro matou
rc = role_combat(ev, job=4302)
mk = roles.multi_kill(rc)
check(mk is not None and mk["n"] == 21 and mk["skill"] == 5473 and mk["mob"] == 1002,
      "Varredura: 21 abates da mesma skill em 1 s (o monstro que outro terminou não conta) -> %r" % (mk,))
check("aoe" in roles.found(rc, {"aoe"}), "Oi, tchau: %d ou mais -> o cartão" % roles.HL_MULTI)

# Anjo da guarda: Ressuscitar seguido da volta do aliado
ev = []
for i, (ally, t) in enumerate(((ALLY1, 2000), (ALLY2, 5000), (ALLY3, 8000), (ALLY1, 11000))):
    ev += [(t - 500, fr.vanish(ally)), (t, fr.skill_use(ME, ally, 54)), (t + 400, fr.resurrect(ally))]
ev += [(14000, fr.skill_use(ME, ALLY2, 54))]                              # sem a volta: não conta
rc = role_combat(ev, job=4256)
check(roles.revived(rc) == (4, 3), "Ressuscitar: 4 voltas confirmadas, 3 aliados -> %r" % (roles.revived(rc),))
check("revive" in roles.found(rc, {"revive"}), "Quero um aumento: %d ou mais -> o cartão" % roles.HL_REVIVE)

# o destaque no resumo: o Redentor (o Escudo do Guardião), com o total na cena e no selo; desligado, some
rc = role_combat([(500, fr.skill_use(ME, ALLY1, 255))] + [(1000 + 300 * i, fr.auto_attack(ME, ME, 90000))
                                                           for i in range(25)])
hl_all = session.highlights(rc, {})
hl_none = session.highlights(rc, {"session_hl_off": ["redeemer"]})
red = [h for h in hl_all if h["key"] == "redeemer"]
check(len(red) == 1 and red[0]["fx"] == "bulwark" and red[0]["scene"]["total"] == 25 * 90000
      and "2,25M" in red[0]["chip"],
      "resumo: o Redentor com o Escudo do Guardião, o total na cena e no selo -> %r" % (
          [(h["key"], h["fx"], h["chip"]) for h in red],))
check(not [h for h in hl_none if h["key"] == "redeemer"], "resumo: desligado na aba Cartões, o Redentor não aparece")
check([session.hl_text(k)[0] for k in ("buffed", "credit", "aoe", "revive", "served", "no_elixir")]
      == ["Podem ir", "Sem mim era Wipe", "Oi, tchau", "Quero um aumento", "Bem servido", "Tá fácil pra ninguém"],
      "os nomes que o usuário deu (2026-11-22) -> %r" % ([session.hl_text(k)[0] for k in session.ROLE_KEYS],))
_name, _when = session.hl_text("buffed")
check("40" in _when and "caçada" in _when and "%" in _when,
      "aba Cartões: o Podem ir diz as duas condições (luta de chefe e caçada) -> %r" % (_when,))
check(all(k in session.HL_KEYS for k in session.ROLE_KEYS)
      and session.HL_KEYS.index("no_elixir") < session.HL_KEYS.index("marked"),
      "os cartões de classe estão na lista de destaques, acima do Item marcado")
check(all(session.FX[k] in session.FX_KINDS for k in session.ROLE_KEYS)
      and [session.FX[k] for k in ("redeemer", "lex", "buffed", "credit", "aoe")]
      == ["bulwark", "lex_double", "buff_wings", "credit_boss", "aoe_blast"],
      "as versões aprovadas: Redentor B, Chuva de Lex B, Podem ir B, Sem mim era Wipe A, Oi tchau A")
for key in session.ROLE_KEYS:
    smp = session.sample_card_for({}, key)
    check(smp["hl"][0]["key"] == key and smp["hl"][0]["scene"] and smp["hl"][0]["fx"] in session.FX_KINDS,
          "prévia de %s: o exemplo com a cena (%s)" % (key, smp["hl"][0]["fx"]))

# Podem ir na caçada: as rodadas de buff lançadas por quem grava (o pacote de conjuração dele logo antes do uso); o
# buff que outro Cardeal pôs no grupo chega como um uso de quem grava nele mesmo, sem a conjuração dele, e não conta
_BUFFS6 = (2041, 2042, 2045, 74, 75, 5281)
ev, ev_other = [], []
for r in range(45):
    _t0 = 1000 + r * 40000
    for j, sk in enumerate(_BUFFS6):
        ev += [(_t0 + j * 300, fr.cast(ME, ME, sk, 0)), (_t0 + j * 300 + 10, fr.skill_use(ME, ME, sk))]
        ev_other += [(_t0 + j * 300, fr.cast(ALLY4, ALLY4, sk, 0)), (_t0 + j * 300 + 10, fr.skill_use(ME, ME, sk))]
rc = role_combat(ev, job=4256)
rr = roles.buff_rounds(rc)
check(rr is not None and rr["n"] == 45 and rr["skills"][0] in _BUFFS6,
      "rodadas de buff: 45 rodadas de 6 buffs lançados por quem grava -> %r" % (rr and rr["n"],))
_got = roles.found(rc, {"buffed"}).get("buffed") or {}
check(_got.get("farm") and _got.get("n") == 45 and _got.get("members") == 3,
      "Podem ir na caçada: %d rodadas ou mais, num grupo -> o cartão -> %r" % (roles.HL_ROUNDS, _got))
_hl_farm = [h for h in session.highlights(rc, {}) if h["key"] == "buffed"]
check(_hl_farm and "45" in _hl_farm[0]["chip"] and _hl_farm[0]["scene"].get("rounds") == 45,
      "resumo: o Podem ir da caçada com as rodadas no selo e na cena -> %r" % ([h["chip"] for h in _hl_farm],))
rc2 = role_combat(ev_other, job=4256)
check(roles.buff_rounds(rc2) is None and "buffed" not in roles.found(rc2, {"buffed"}),
      "os buffs que outro Cardeal pôs no grupo (sem a conjuração de quem grava) não contam")
check(roles.own_cast(rc, ME, 1010, 2041) and not roles.own_cast(rc2, ME, 1010, 2041),
      "own_cast: o uso logo depois da conjuração de quem grava é dele; o de outro, não")

# Bem servido (KS): monstros que um jogador de fora do grupo começou (1 s antes) e em que bateu, e que quem grava matou
_STRANGER = 3100
ev = [(0, fr.spawn(_STRANGER, "pc", 4252, "Outro"))]
ev2 = []
for i in range(22):
    _aid, _t0 = 72000 + i, 2000 + i * 5000
    ev += [(0, fr.spawn(_aid, "mob", 1002, "Poring")),
           (_t0, fr.skill_damage(_STRANGER, _aid, 30000, skill=5473, hits=1)),
           (_t0 + 1500, fr.skill_damage(ME, _aid, 9999, skill=5473, hits=1)), (_t0 + 1600, fr.vanish(_aid))]
    ev2 += [(0, fr.spawn(_aid, "mob", 1002, "Poring")),
            (_t0, fr.skill_damage(ALLY1, _aid, 30000, skill=5473, hits=1)),
            (_t0 + 1500, fr.skill_damage(ME, _aid, 9999, skill=5473, hits=1)), (_t0 + 1600, fr.vanish(_aid))]
rc = role_combat(ev, job=4302)
ks = roles.kill_steals(rc)
check(ks is not None and ks["n"] == 22 and ks["victims"] == [4252] and ks["mob"] == 1002,
      "KS: 22 monstros que outro jogador começou e quem grava matou -> %r" % (ks,))
_got = roles.found(rc, {"served"}).get("served") or {}
check(_got.get("kind") == "ks" and _got.get("n") == 22, "Bem servido: %d KS ou mais -> o cartão" % roles.HL_KS)
_hl_ks = [h for h in session.highlights(rc, {}) if h["key"] == "served"]
check(_hl_ks and _hl_ks[0]["fx"] == "served_ks" and "22 KS" in _hl_ks[0]["chip"]
      and _hl_ks[0]["scene"]["others"] == [4252],
      "resumo: o Bem servido dos KS, com quem foi roubado na cena -> %r" % ([(h["fx"], h["chip"]) for h in _hl_ks],))
check(roles.kill_steals(role_combat(ev2, job=4302)) is None, "o monstro que alguém do grupo começou não é KS")

# Bem servido (MVP): o aviso de MVP com quem grava, num chefe em que os outros já tinham dado 20% do dano antes dele
ev = [(0, fr.spawn(_STRANGER, "pc", 4252, "Outro"))]
ev += [(1000 + 500 * i, fr.skill_damage(_STRANGER, RBOSS, 1000000, skill=5473, hits=1)) for i in range(10)]
ev += [(7000 + 300 * i, fr.skill_damage(ME, RBOSS, 2000000, skill=5473, hits=1)) for i in range(10)]
ev += [(10000, fr.vanish(RBOSS))] + [(10050, fr.mvp(ME))] * 5         # o aviso chega repetido no mesmo instante
rc = role_combat(ev, job=4302)
lm = roles.late_mvp(rc)
check(lm is not None and abs(lm["before"] - 1 / 3.0) < 0.01 and lm["others"] == [4252] and lm["late"] == 6000
      and len(rc.mvp_log) == 1,
      "MVP chegando depois: os outros deram 1/3 do dano antes, 6 s antes dele (o aviso repetido conta uma vez) -> %r" % (
          lm,))
_got = roles.found(rc, {"served"}).get("served") or {}
check(_got.get("kind") == "mvp", "Bem servido: o MVP chegando depois -> o cartão")
_hl_mvp = [h for h in session.highlights(rc, {}) if h["key"] == "served"]
check(_hl_mvp and _hl_mvp[0]["fx"] == "served_mvp" and "33%" in _hl_mvp[0]["sub"],
      "resumo: o Bem servido do MVP, com a parte dos outros na frase -> %r" % ([h["sub"] for h in _hl_mvp],))
ev[-5:] = [(10050, fr.mvp(_STRANGER))]
check(roles.late_mvp(role_combat(ev, job=4302)) is None, "o MVP que ficou com o outro não conta")

# Tá fácil pra ninguém: o item de cura acabou (o uso deixou 0) apanhando, depois de usar com sobra
_hurt = [(1000 + 400 * i, fr.auto_attack(RBOSS, ME, 50000)) for i in range(20)]
ev = _hurt + [(1200 + 1000 * i, fr.item_use(ME, 1100005, 4 - i)) for i in range(5)]      # 4, 3, 2, 1, 0
rc = role_combat(ev, job=4302)
ro = roles.ran_out(rc)
check(ro is not None and ro["item"] == 1100005 and ro["uses"] == 5 and ro["mob"] == 1039 and ro["t"] == 5200,
      "Tá fácil pra ninguém: o Elixir Dourado acabou apanhando do Bafomé -> %r" % (ro,))
_hl_el = [h for h in session.highlights(rc, {}) if h["key"] == "no_elixir"]
check(_hl_el and _hl_el[0]["fx"] == "no_elixir" and _hl_el[0]["scene"]["item"] == 1100005,
      "resumo: o Tá fácil pra ninguém com o item na cena -> %r" % ([h["chip"] for h in _hl_el],))
ev = _hurt + [(1200 + 1000 * i, fr.item_use(ME, 12333, 0)) for i in range(5)]
check(roles.ran_out(role_combat(ev, job=4256)) is None, "a Ancilla (feita e bebida na hora) não conta")
ev = [(1200 + 1000 * i, fr.item_use(ME, 1100005, 4 - i)) for i in range(5)]
check(roles.ran_out(role_combat(ev)) is None, "acabou fora da luta (sem apanhar): não conta")
ev = _hurt + [(1200 + 1000 * i, fr.item_use(3001, 1100005, 4 - i)) for i in range(5)]
check(roles.ran_out(role_combat(ev)) is None, "o item de outro jogador que acabou não conta")

# as cenas de dano com a classe de quem grava, no estilo dela
_GRF = r"C:\\Gravity\\Ragnarok\\data.grf"
if os.path.isfile(_GRF):
    import class_scenes as cs_mod  # noqa: E402
    import sprites as spr_mod  # noqa: E402
    _w = spr_mod.Wardrobe(_GRF)
    _acts = {j: cs_mod.attack_act(_w, cs_mod.look_for(j)) for j in (4252, 4257, 4254, 4260, 4306, 4302, 4256)}
    check(_acts == {4252: 10, 4257: 11, 4254: 11, 4260: 10, 4306: 10, 4302: spr_mod.ATTACK,
                    4256: spr_mod.CAST},
          "cenas: as classes físicas golpeiam com a arma (a ação em que ela aparece), o Mestre Celestial soca e "
          "o Cardeal conjura -> %s" % _acts)
    _parts = {j: [p.name for p in _w.parts(cs_mod.look_for(j), 6)[0]] for j in (4258, 4066)}
    check(all("shield" in v and "weapon" in v for v in _parts.values()),
          "os Guardiões (Imperial e Real) com lança e escudo; o Real não vira Aprendiz -> %s" % _parts)
    _real = dict(job=4258, sex=1, hair=2, weapon=530015, shield=460157)
    check("shield" in [p.name for p in _w.parts(_real, 6)[0]],
          "o escudo comum de um visual de verdade (o Broquel do Guardião Imperial) é achado")
else:
    print("pula  armas e escudos das cenas (sem o data.grf)")
check([session.fight_style(j) for j in (4302, 4256, 4257, 4252, 4038, 4030, 4306, 4255)]
      == ["fist", "magic", "ranged", "melee", "fist", "melee", "ranged", "magic"],
      "o estilo de luta de cada classe nas cenas de dano (o Mini Monge soca, o Mini Cavaleiro não)")
rc.session.look = dict(job=4256, sex=0, hair=17, hair_color=2, weapon=15)
_fo = session.fight_of(rc, hit=1000)
check(_fo["look"] and _fo["look"]["job"] == 4256, "cena de dano: o visual de quem grava, de qualquer classe (o Cardeal)")

# o dano creditado de um efeito sem o uso à vista vai para o único do grupo que tem a skill (o Pólen do Magus)
_c_ev = [(0, fr.spawn(ALLY2, "pc", 4255, "Magus")), (0, fr.party_hp(ALLY2, 100, 100))]
_c_ev += [(1000, fr.status(RBOSS, 1183, True, total=60000, left=60000))]
_c_ev += [(1500 + 300 * i, fr.skill_damage(ALLY1, RBOSS, 1000000, skill=5473, hits=1)) for i in range(40)]
rc = role_combat(_c_ev, job=4302)
_x = dd.Ctx(rc, RBOSS, None)
_ap = contrib_mod.appliers(rc, _x, 1183)
check(_ap and all(w == ALLY2 for _s, _e, w, _v in _ap),
      "Pólen sem o Florescer à vista: vai para o Magus do grupo -> %r" % ([w for _s, _e, w, _v in _ap],))

# replays de verdade do usuário (se existirem): a Lex do Cardeal e os buffs dele, os KS do Mestre Celestial e o
# Elixir Dourado que acabou
for _path, _want in ((r"C:\Gravity\Ragnarok\Replay\RagnarokReplay_0067.rrf", {"lex", "credit"}),
                     (r"C:\Gravity\Ragnarok\Replay\fdfdsf.rrf", {"lex", "buffed"}),
                     (r"C:\Gravity\Ragnarok\Replay\RagnarokReplay_0029.rrf", {"served"}),
                     (r"C:\Gravity\Ragnarok\Replay\afafads.rrf", {"no_elixir"})):
    if not os.path.isfile(_path):
        print("pula  %s (nao encontrado)" % _path)
        continue
    _rf = meter.ReplayFile(_path)
    while _rf.poll():
        pass
    _got = roles.found(_rf.combat, set(session.ROLE_KEYS))
    check(_want <= set(_got), "%s: cartões de classe %s -> %s" % (os.path.basename(_path), sorted(_want),
                                                                   sorted(_got)))

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
