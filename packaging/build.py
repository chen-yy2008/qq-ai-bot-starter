"""Assemble an allowlisted, credential-free online bootstrap Windows package."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from entrypoints import write_entries

APP_FILES=("launch.py","doctor.py","start.ps1","bundle_paths.py","panel_password.py","password_dialog.ps1","control.py")

ROOT=Path(__file__).resolve().parents[1]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def extract(source,target):
    with zipfile.ZipFile(source) as z:
        for entry in z.infolist():
            path=(target/entry.filename).resolve()
            if not path.is_relative_to(target.resolve()): raise ValueError("Unsafe archive entry")
        z.extractall(target)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--deps",type=Path,required=True)
    p.add_argument("--output",type=Path,default=ROOT/"dist")
    args=p.parse_args()
    deps=args.deps.resolve()
    lock=json.loads((ROOT/"packaging/artifacts.lock.json").read_text())
    for entry in lock["artifacts"]:
        if sha(deps/entry["file"])!=entry["sha256"]: raise ValueError("Artifact hash mismatch: "+entry["file"])
    output=args.output.resolve()
    if not output.is_relative_to((ROOT/"dist").resolve()): raise ValueError("Output must stay within project dist")
    output.mkdir(exist_ok=True,parents=True)
    stage=output/"QQ-AI-Bot-v1.0.0-Windows-x64"
    if stage.exists(): raise SystemExit("Build directory exists; use a fresh output directory after reviewing its contents.")
    stage.mkdir()
    app=stage/"程序文件"
    app.mkdir()
    shutil.copytree(ROOT/"docs",stage/"使用说明",ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    for name in ("README.md","LICENSE","NOTICE-THIRD-PARTY.md"):
        shutil.copy2(ROOT/name,stage/"使用说明"/name)
    for name in ("personas","config","plugin","tests","packaging"):
        src=ROOT/name
        shutil.copytree(src,app/name,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    (app/"tools").mkdir()
    with zipfile.ZipFile(deps/"uv.zip") as z:
        (app/"tools/uv.exe").write_bytes(z.read("uv.exe"))
    shutil.copytree(deps/"uv-licenses",app/"tools/licenses")
    extract(deps/"python-3.12.10-embed-amd64.zip",app/"runtime")
    (app/"runtime/python312._pth").write_text("python312.zip\n.\nLib/site-packages\nimport site\n",encoding="ascii")
    extract(deps/"astrbot-v4.29.0.zip",stage/"upstream-source")
    (stage/"upstream-source/AstrBot-4.29.0").rename(app/"framework")
    (stage/"upstream-source").rmdir()
    extract(deps/"AstrBot-v4.29.0-dashboard.zip",app/"framework/dashboard")
    plugin=stage/"data/plugins/astrbot_plugin_qq_ai_lab"
    shutil.copytree(ROOT/"plugin",plugin,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    shutil.copytree(ROOT/"personas",plugin/"personas")
    for name in APP_FILES:
        source=ROOT/"packaging"/name
        if name.endswith(".ps1"):
            (app/name).write_text(source.read_text(encoding="utf-8-sig"),encoding="utf-8-sig")
        else: shutil.copy2(source,app/name)
    write_entries(stage)
    # Verify neither development machine paths nor generated credentials enter assets.
    manifest={str(f.relative_to(stage)).replace("\\","/"):sha(f) for f in sorted(stage.rglob("*")) if f.is_file()}
    (app/"MANIFEST.sha256.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    archive=output/(stage.name+".zip")
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in sorted(stage.rglob("*")):
            if f.is_file(): z.write(f,str(f.relative_to(stage)))
    (output/"SHA256SUMS.txt").write_text(sha(archive)+"  "+archive.name+"\n",encoding="ascii")
    print(archive.name,archive.stat().st_size,"bytes",sha(archive))


if __name__=="__main__": main()
