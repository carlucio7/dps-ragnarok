"""Prepara o ambiente de build (.venv-build) com um PyInstaller cujo lançador é compilado aqui.

Por quê: o lançador de janela do PyInstaller (runw.exe) importa LoadIconMetric da comctl32
(ordinal 380), que só existe quando o Windows aplica o manifesto do .exe. Em alguns PCs isso não
acontece (antivírus que roda o programa isolado, por exemplo) e o programa nem abre: "Não foi
possível localizar o número ordinal 380". Compilado aqui, o lançador usa LoadIconW (só serve para o
ícone do diálogo de erro) e não depende da comctl32. Lançador próprio também costuma ser menos
marcado por antivírus que o padrão, que é o mesmo em milhares de programas.

Precisa de internet (código do PyInstaller no GitHub e as dependências dele no pip) e de um gcc
MinGW com a mesma arquitetura do Python (ex.: o do Strawberry Perl, 32 bits).

uso: python tools/build_bootloader.py
     depois o tools/build_release.py usa o .venv-build sozinho.
"""

import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
VENV = os.path.join(ROOT, ".venv-build")
PYINSTALLER = "6.22.3"
URL = "https://github.com/pyinstaller/pyinstaller/archive/refs/tags/v%s.tar.gz" % PYINSTALLER
DIALOG = os.path.join("bootloader", "src", "pyi_exception_dialog.c")
OLD = "#if 0\n    dialog->hErrorIcon = LoadIconW(NULL, IDI_ERROR);"
NEW = ("#if 1  /* RODpsMeter: sem LoadIconMetric (comctl32 v6, ordinal 380) */\n"
       "    dialog->hErrorIcon = LoadIconW(NULL, IDI_ERROR);")


def ordinal_imports(path):
    """{dll: [ordinais]} que o .exe importa por número (o caso que quebra sem o manifesto)."""
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    out = {e.dll.decode().lower(): [i.ordinal for i in e.imports if i.import_by_ordinal]
           for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])}
    pe.close()
    return out


def main():
    bits = struct.calcsize("P") * 8
    tmp = tempfile.mkdtemp(prefix="pyi_bootloader_")
    try:
        archive = os.path.join(tmp, "pyinstaller.tar.gz")
        print("baixando", URL)
        urllib.request.urlretrieve(URL, archive)
        with tarfile.open(archive) as tar:
            tar.extractall(tmp, filter="data")
        src = os.path.join(tmp, "pyinstaller-%s" % PYINSTALLER)
        path = os.path.join(src, DIALOG)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if text.count(OLD) != 1:
            sys.exit("o trecho do ícone mudou em %s: confira %s" % (PYINSTALLER, DIALOG))
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace(OLD, NEW))
        subprocess.check_call([sys.executable, "waf", "distclean", "all", "--gcc", "--target-arch=%dbit" % bits],
                              cwd=os.path.join(src, "bootloader"))
        runw = os.path.join(src, "PyInstaller", "bootloader", "Windows-%dbit-intel" % bits, "runw.exe")
        imports = ordinal_imports(runw)
        if "comctl32.dll" in imports:
            sys.exit("o lançador novo ainda importa a comctl32: %s" % imports)
        if os.path.isdir(VENV):
            shutil.rmtree(VENV)
        subprocess.check_call([sys.executable, "-m", "venv", VENV])
        py = os.path.join(VENV, "Scripts", "python.exe")
        subprocess.check_call([py, "-m", "pip", "install", "--quiet", src])
        print("\npronto: %s (PyInstaller %s, lançador sem comctl32)" % (VENV, PYINSTALLER))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
