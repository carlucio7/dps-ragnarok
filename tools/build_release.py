"""Monta o pacote para compartilhar: .exe com versão, instruções (pt/en/es), créditos, SHA-256 e .zip.

uso: python tools/build_release.py
saída: release/DpsRagnarok-VERSÃO/ e release/DpsRagnarok-VERSÃO-win.zip

O UPX fica desligado (compactar o .exe faz antivírus desconfiar à toa). O código SHA-256 do .exe
vai no SHA256.txt do pacote; o do .zip aparece no fim, para pôr na página de download.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from version import VERSION  # noqa: E402

DOCS = ["LEIA-ME.txt", "README.txt", "LEAME.txt", "CREDITOS.txt"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def version_file(path):
    nums = tuple(int(x) for x in VERSION.split(".")) + (0,)
    with open(path, "w", encoding="utf-8") as f:
        f.write("""VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(n)s, prodvers=%(n)s, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('FileDescription', 'DPS Ragnarok - DPS meter for Ragnarok Online (reads replay files)'),
      StringStruct('FileVersion', '%(v)s'),
      StringStruct('InternalName', 'DpsRagnarok'),
      StringStruct('OriginalFilename', 'DpsRagnarok.exe'),
      StringStruct('ProductName', 'DPS Ragnarok'),
      StringStruct('ProductVersion', '%(v)s')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""" % dict(n=repr(nums[:4]), v=VERSION))


def main():
    os.chdir(ROOT)
    os.makedirs("build", exist_ok=True)
    vfile = os.path.join("build", "version_info.txt")
    version_file(vfile)
    subprocess.check_call([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed", "--noupx",
                           "--name", "DpsRagnarok", "--icon", "dpsmeter.ico", "--version-file", vfile,
                           "--add-data", "dpsmeter.ico;.", "--add-data", "data;data", "dpsmeter.py"])
    name = "DpsRagnarok-%s" % VERSION
    out = os.path.join("release", name)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    exe = os.path.join(out, "DpsRagnarok.exe")
    shutil.copy2(os.path.join("dist", "DpsRagnarok.exe"), exe)
    for doc in DOCS:
        with open(os.path.join("docs", doc), encoding="utf-8") as f:
            text = f.read().replace("{VERSION}", VERSION)
        with open(os.path.join(out, doc), "w", encoding="utf-8-sig", newline="\r\n") as f:
            f.write(text)
    with open("CHANGELOG.md", encoding="utf-8") as f:                 # novidades, para abrir no Bloco de Notas
        text = f.read()
    with open(os.path.join(out, "CHANGELOG.txt"), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(text)
    exe_hash = sha256(exe)
    with open(os.path.join(out, "SHA256.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write("%s  DpsRagnarok.exe\n" % exe_hash)
    zpath = os.path.join("release", name + "-win.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(out)):
            z.write(os.path.join(out, fn), "%s/%s" % (name, fn))
    print("\nversão  %s" % VERSION)
    print("exe     %s  %s" % (exe_hash, exe))
    print("zip     %s  %s (%.1f MB)" % (sha256(zpath), zpath, os.path.getsize(zpath) / 1e6))


if __name__ == "__main__":
    main()
