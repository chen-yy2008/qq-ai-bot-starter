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
    manifest_name="程序文件/MANIFEST.sha256.json"
    manifest=json.loads(z.read(manifest_name))
    files={name for name in names if not name.endswith("/")}
    if files!=set(manifest)|{manifest_name}: raise SystemExit("Unexpected or missing files")
    for relative,digest in manifest.items():
        content=z.read(relative)
        if hashlib.sha256(content).hexdigest()!=digest: raise SystemExit("Hash mismatch: "+relative)
        if relative.startswith("data/") and not relative.startswith("data/plugins/astrbot_plugin_qq_ai_lab/"):
            raise SystemExit("Private runtime data in archive")
        if relative.endswith((".db",".log",".key",".pyc")) or "/.git/" in relative:
            raise SystemExit("Disallowed runtime file: "+relative)
        if relative.startswith(("程序文件/framework/","程序文件/runtime/","程序文件/tools/")): continue
        if relative.endswith((".py",".json",".md",".ps1",".txt",".lock",".yml",".yaml")):
            text=content.decode("utf-8-sig")
            if re.search(r"gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{20,}|[A-Z]:[\\/]Users[\\/]",text):
                raise SystemExit("Possible secret or development machine path: "+relative)
    required=("程序文件/runtime/python.exe","程序文件/framework/main.py","程序文件/framework/LICENSE","程序文件/framework/dashboard/dist/index.html","程序文件/panel_password.py","程序文件/password_dialog.ps1","data/plugins/astrbot_plugin_qq_ai_lab/main.py","程序文件/packaging/requirements-win.lock","启动机器人.bat","自检.bat","打开管理面板.bat","停止机器人.bat","重置管理密码.bat","首次使用.html","程序文件/tools/licenses/LICENSE-MIT")
    for path in required:
        if path not in files: raise SystemExit("Missing required file: "+path)
    for path in ("安全诊断.bat","程序文件/updater.py","程序文件/safe_diagnostics.py","data/plugins/astrbot_plugin_qq_ai_lab/diagnostics.py"):
        if path not in files:raise SystemExit("Missing required candidate component: "+path)
    print("Verified",len(files),"files; manifest, required components, no runtime data or credential patterns.")
