# -*- coding: utf-8 -*-
"""Aprender com as gravações que já estavam na pasta: uma vez só, num processo à parte e com prioridade mínima (o
jogo e o widget não sentem), logo que esta versão abre. Os replays costumam ser apagados, então quanto antes, melhor;
o que for aprendido fica no registro de aprendizado mesmo depois que o replay some.

O processo filho (`ReplayMaster.exe --aprender-pasta PASTA_DA_CONFIG PASTA_REPLAY...`) lê as gravações em ordem de
data numa configuração de rascunho, como se o programa tivesse acompanhado cada uma no automático, e grava só o
registro de aprendizado num arquivo; o widget junta com o dele e apaga o arquivo. A previsão de XP de hoje (medidas
de cada personagem, evento do servidor, mapas marcados) não muda.
"""

import datetime
import json
import os
import sys
import threading
import time

ARG = "--aprender-pasta"
RESULT = "aprendizado_pasta.json"     # o que o processo filho aprendeu (o widget junta e apaga)
PROGRESS = "aprendizado_pasta.prog"   # andamento: {"done", "total"}
TRIES = 3                             # tentativas (processo fechado no meio: o PC desligou...)
ALIVE_S = 180                         # andamento mexido há menos que isso: o processo ainda está lendo
BUSY_S = 120                          # gravação mexida há menos que isso fica para o widget (pode estar gravando)
DELAY_MS = int(os.environ.get("RODPS_LEARN_DELAY_MS") or 90000)   # depois de abrir, para não pesar na abertura
GEAR_WAIT_S = 120                     # espera pela lista de itens do jogo (o bônus dos itens entra na conta)
# da configuração do jogador, o que a conta da XP pela lista usa (o resto do rascunho começa vazio)
SETTINGS = ("xp_bonuses", "xp_manual_last", "xp_spot", "xp_levels", "xp_event_off", "xp_fixed", "lang")


def enabled():
    """A leitura automática roda no programa empacotado; no código-fonte (testes, desenvolvimento) só com
    RODPS_LEARN_FOLDER=1."""
    flag = os.environ.get("RODPS_LEARN_FOLDER")
    if flag is not None:
        return flag == "1"
    return bool(getattr(sys, "frozen", False))


def _path(cfg_dir, name):
    return os.path.join(cfg_dir, name)


def alive(cfg_dir, now=None):
    """Um processo de leitura está rodando (o andamento foi mexido há pouco)?"""
    try:
        return (now or time.time()) - os.path.getmtime(_path(cfg_dir, PROGRESS)) < ALIVE_S
    except OSError:
        return False


def progress(cfg_dir):
    """(lidas, total) da leitura em andamento, ou None."""
    if not alive(cfg_dir):
        return None
    try:
        with open(_path(cfg_dir, PROGRESS), encoding="utf-8") as f:
            p = json.load(f)
        return int(p["done"]), int(p["total"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def should_start(lrn, cfg_dir):
    """Falta ler a pasta, ainda há tentativa e nenhum processo está lendo?"""
    return (not lrn.get("folder_read") and int(lrn.get("folder_tries") or 0) < TRIES and not alive(cfg_dir)
            and not os.path.exists(_path(cfg_dir, RESULT)))


def start(cfg_dir, folders):
    """Abre o processo filho (sem janela, com prioridade mínima). True se abriu."""
    import subprocess
    if getattr(sys, "frozen", False):
        args = [sys.executable]
    else:
        args = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "dpsmeter.py")]
    args += [ARG, cfg_dir] + [f for f in folders if f and os.path.isdir(f)]
    flags = 0
    if os.name == "nt":
        flags = 0x00000040 | 0x08000000          # IDLE_PRIORITY_CLASS | CREATE_NO_WINDOW
    try:
        subprocess.Popen(args, close_fds=True, creationflags=flags, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True


def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _background():
    """Prioridade mínima de CPU e de disco para este processo (Windows: modo de segundo plano)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetPriorityClass(k.GetCurrentProcess(), 0x00100000)     # PROCESS_MODE_BACKGROUND_BEGIN
    except (OSError, AttributeError):
        pass


def recordings(folders, busy_s=BUSY_S, now=None):
    """[(quando gravou, caminho)] das gravações das pastas, da mais velha para a mais nova, sem as que ainda podem
    estar sendo gravadas."""
    import rrf
    now = now or time.time()
    out, seen = [], set()
    for folder in folders:
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            p = os.path.join(folder, name)
            key = os.path.normcase(os.path.abspath(p))
            if not name.lower().endswith(".rrf") or key in seen:
                continue
            seen.add(key)
            try:
                if busy_s > 0 and now - os.path.getmtime(p) < busy_s:
                    continue
                s = rrf.read_session(p)
            except Exception:  # noqa: BLE001 - arquivo estranho ou cortado: fica de fora
                continue
            if s is not None and s.gid and s.recorded_at:
                out.append((tuple(s.recorded_at[:6]), p))
    return sorted(out)


def run(folders, cfg_dir, busy_s=BUSY_S):
    """Lê as gravações e grava o que aprendeu em RESULT (o andamento em PROGRESS). Devolve o resultado."""
    import clientdata
    import meter
    import xp
    from version import VERSION
    prog, out = _path(cfg_dir, PROGRESS), _path(cfg_dir, RESULT)
    cfg = {"xp_mode": "auto"}
    try:
        with open(_path(cfg_dir, "config.json"), encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            cfg.update({k: saved[k] for k in SETTINGS if k in saved})
    except (OSError, ValueError):
        pass
    cfg["xp_mode"] = "auto"                       # o rascunho aprende como o automático (o evento é deduzido)
    files = recordings(folders, busy_s)
    _write(prog, dict(done=0, total=len(files)))
    for d in list(folders) + meter.find_replay_dirs():     # os nomes do jogo (monstros novos) vêm da instalação
        clientdata.NAMES.use_folder(d)
    clientdata.NAMES.load()
    t0 = time.time()
    while not xp.gear_ready() and time.time() - t0 < GEAR_WAIT_S:
        time.sleep(0.5)
    age, xp.MAX_AGE_S = xp.MAX_AGE_S, None        # gravações antigas também (o rascunho não é a configuração de hoje)
    errors = []
    last = time.time()
    stop = threading.Event()

    def beat():                                   # gravação enorme demora: o andamento segue "vivo" (ALIVE_S)
        while not stop.wait(30.0):
            try:
                os.utime(prog, None)
            except OSError:
                pass
    threading.Thread(target=beat, daemon=True).start()
    try:
        for k, (_when, path) in enumerate(files):
            try:
                rf = meter.ReplayFile(path)
                while rf.poll():
                    pass
                c = rf.combat
                if c is not None:
                    c.path = path
                    c.finished = True
                    xp._CACHE.clear()
                    xp.calibrate(c, cfg, meter.xp_after)
            except Exception as exc:  # noqa: BLE001 - uma gravação estranha não para a leitura das outras
                errors.append("%s: %s" % (type(exc).__name__, exc))
            rf = c = None
            if time.time() - last > 2.0 or k + 1 == len(files):
                last = time.time()
                _write(prog, dict(done=k + 1, total=len(files)))
    finally:
        stop.set()
        xp.MAX_AGE_S = age
        xp._CACHE.clear()
    lrn = dict(cfg.get("xp_learn") or {})
    for key in ("secret", "rev", "folder_read", "folder_tries"):
        lrn.pop(key, None)
    result = dict(v=VERSION, date=datetime.date.today().isoformat(), files=len(files), errors=len(errors),
                  learn=lrn, quests=cfg.get("xp_quests") or {})
    _write(out, result)
    try:
        os.remove(prog)
    except OSError:
        pass
    if errors:
        try:
            with open(_path(cfg_dir, "erros.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "leitura da pasta (%s): %d gravações com erro, "
                        "a primeira: %s\n" % (VERSION, len(errors), errors[0]))
        except OSError:
            pass
    return result


def child(argv):
    """Entrada do processo filho: `--aprender-pasta PASTA_DA_CONFIG PASTA_REPLAY...`."""
    i = argv.index(ARG)
    if i + 1 >= len(argv):
        return
    _background()
    try:
        run(argv[i + 2:], argv[i + 1])
    except Exception:  # noqa: BLE001 - sem resultado: o widget tenta de novo na próxima abertura (até TRIES)
        import traceback
        try:
            with open(_path(argv[i + 1], "erros.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "leitura da pasta:\n" + traceback.format_exc() + "\n")
        except OSError:
            pass


def take(cfg, cfg_dir):
    """Junta o resultado de uma leitura que terminou (se houver) com o registro de aprendizado e apaga o arquivo.
    True se juntou."""
    path = _path(cfg_dir, RESULT)
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
    except (OSError, ValueError):
        got = None
    import xp
    lrn = xp._learn(cfg)
    if isinstance(got, dict) and isinstance(got.get("learn"), dict):
        merge(lrn, got["learn"])
        lrn["folder_read"] = dict(date=str(got.get("date") or datetime.date.today().isoformat())[:10],
                                  files=int(got.get("files") or 0))
        xp.touch_learn(lrn)
        # recompensas de missão que as gravações antigas ensinaram valem para a previsão (a que o widget já
        # aprendeu fica: é de uma gravação mais nova)
        mine = cfg.setdefault("xp_quests", {})
        for qid, e in (got.get("quests") if isinstance(got.get("quests"), dict) else {}).items():
            if isinstance(e, dict) and isinstance(e.get("base"), (int, float)) and e["base"] > 0:
                mine.setdefault(str(qid), e)
    try:
        os.remove(path)
    except OSError:
        pass
    return True


def merge(lrn, got):
    """Junta o que o processo filho aprendeu com o registro do widget. O que o widget já tinha fica (é o mesmo, ou de
    uma leitura mais nova da mesma gravação)."""
    import xp
    have = {m.get("src") for m in lrn["measures"]}
    add = [m for m in got.get("measures") or [] if isinstance(m, dict) and m.get("src") not in have]
    lrn["measures"] = sorted(lrn["measures"] + add, key=lambda m: str(m.get("date") or ""))[-xp.LEARN_KEEP:]
    drops = {k: v for k, v in (got.get("drops") or {}).items() if isinstance(v, dict)}
    drops.update(lrn["drops"])
    lrn["drops"] = dict(sorted(drops.items(), key=lambda kv: str(kv[1].get("date") or ""))[-xp.LEARN_DROP_RECS:])
    for mid, u in (got.get("unknown") or {}).items():
        if not isinstance(u, dict):
            continue
        e = lrn["unknown"].setdefault(mid, dict(name=u.get("name"), recs={}, maps={}))
        for r, n in (u.get("recs") or {}).items():
            e["recs"].setdefault(r, n)
        for m, n in (u.get("maps") or {}).items():
            e["maps"][m] = max(e["maps"].get(m, 0), n)
        e["last"] = max(str(e.get("last") or ""), str(u.get("last") or ""))
        if not e.get("name") or (str(mid) in str(e["name"]) and u.get("name") and str(mid) not in str(u["name"])):
            e["name"] = u.get("name")             # o nome do jogo no lugar do "Monstro 21533" (sem os nomes carregados)
    if len(lrn["unknown"]) > xp.LEARN_UNKNOWN:
        keep = sorted(lrn["unknown"].items(), key=lambda kv: str(kv[1].get("last") or ""))[-xp.LEARN_UNKNOWN:]
        lrn["unknown"] = dict(keep)
    for k, v in (got.get("names") or {}).items():
        lrn["names"].setdefault(k, v)
    for key, keep in (("changes", 100), ("server", 50)):
        seen = {json.dumps(x, sort_keys=True) for x in lrn[key]}
        new = [x for x in got.get(key) or [] if isinstance(x, dict) and json.dumps(x, sort_keys=True) not in seen]
        lrn[key] = sorted(lrn[key] + new, key=lambda x: str(x.get("date") or ""))[-keep:]
    # recompensas de missão medidas: a mesma gravação e missão que o widget já tem fica a dele
    have = {(x.get("src"), x.get("quest")) for x in lrn["quests"]}
    new = [x for x in got.get("quests") or [] if isinstance(x, dict) and (x.get("src"), x.get("quest")) not in have]
    lrn["quests"] = sorted(lrn["quests"] + new, key=lambda x: str(x.get("date") or ""))[-xp.LEARN_QUESTS:]
