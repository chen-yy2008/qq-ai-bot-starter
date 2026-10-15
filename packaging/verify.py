"""Verify clean release ZIP against manifest; inspect only distributed text files."""
import argparse
import hashlib
import json
import re
import zipfile

p=argparse.ArgumentParser()
p.add_argument("--archive",required=True)
args=p.parse_args()
with zipfile.ZipFile(args.archive) as z:
    names=z.namelist()
    roots={name.split("/")[0] for name in names}
    if len(roots)!=1: raise SystemExit("Expected one package root")
    prefix=next(iter(roots))+"/"
    manifest=json.loads(z.read(prefix+"MANIFEST.sha256.json"))
    files={name.removeprefix(prefix) for name in names if not name.endswith("/")}
    if files!=set(manifest)|{"MANIFEST.sha256.json"}: raise SystemExit("Unexpected or missing files")
    for relative,digest in manifest.items():
        content=z.read(prefix+relative)
        if hashlib.sha256(content).hexdigest()!=digest: raise SystemExit("Hash mismatch: "+relative)
        if relative.startswith("data/") and not relative.startswith("data/plugins/astrbot_plugin_qq_ai_lab/"):
            raise SystemExit("Private runtime data in archive")
        if relative.endswith((".db",".log",".key",".pyc")) or "/.git/" in relative:
            raise SystemExit("Disallowed runtime file: "+relative)
        if relative.startswith(("framework/","runtime/","tools/")): continue
        if relative.endswith((".py",".json",".md",".ps1",".txt",".lock",".yml",".yaml")):
            text=content.decode("utf-8-sig")
            if re.search(r"gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{20,}|[A-Z]:[\\/]Users[\\/]",text):
                raise SystemExit("Possible secret or development machine path: "+relative)
    required=("runtime/python.exe","framework/main.py","framework/LICENSE","framework/dashboard/dist/index.html","plugin/main.py","data/plugins/astrbot_plugin_qq_ai_lab/main.py","packaging/requirements-win.lock","启动机器人.bat","自检.bat","tools/licenses/LICENSE-MIT")
    for path in required:
        if path not in files: raise SystemExit("Missing required file: "+path)
    print("Verified",len(files),"files; manifest, required components, no runtime data or credential patterns.")
