"""Gera data/names.json: nomes do jogo em inglês e espanhol, tirados do cliente da LATAM instalado.

O medidor usa os nomes da instalação de quem joga (clientdata, sempre atualizados); este arquivo
vai no pacote para quando o jogo não está no PC (ex.: abrir um replay recebido de outra pessoa).

uso: python tools/build_names.py [PASTA_DO_JOGO]     (padrão: C:\\Gravity\\Ragnarok)
"""

import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import clientdata  # noqa: E402


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else r"C:\Gravity\Ragnarok"
    grf = os.path.join(game, "data.grf")
    with open(os.path.join(ROOT, "data", "monster.json"), encoding="utf-8") as f:
        pt_monsters = {int(k): v["name"] for k, v in json.load(f).items() if v.get("name")}
    by_pt = {}
    clientdata.read_names(grf, by_pt)
    out = {lang: clientdata.read_game_names(grf, lang, by_pt, pt_monsters) for lang in ("en", "es")}
    path = os.path.join(ROOT, "data", "names.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("ok:", {lang: {k: len(v) for k, v in t.items()} for lang, t in out.items()},
          "%.1f MB" % (os.path.getsize(path) / 1e6))


if __name__ == "__main__":
    main()
