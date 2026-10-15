"""Assemble an allowlisted, credential-free online bootstrap Windows package."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

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
    for name in ("README.md","LICENSE","NOTICE-THIRD-PARTY.md","docs","personas","config","plugin","tests","packaging"):
        src=ROOT/name
        if src.is_dir(): shutil.copytree(src,stage/name,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
        else: shutil.copy2(src,stage/name)
    (stage/"tools").mkdir()
    with zipfile.ZipFile(deps/"uv.zip") as z:
        (stage/"tools/uv.exe").write_bytes(z.read("uv.exe"))
    shutil.copytree(deps/"uv-licenses",stage/"tools/licenses")
    extract(deps/"python-3.12.10-embed-amd64.zip",stage/"runtime")
    (stage/"runtime/python312._pth").write_text("python312.zip\n.\nLib/site-packages\nimport site\n",encoding="ascii")
    extract(deps/"astrbot-v4.29.0.zip",stage/"upstream-source")
    (stage/"upstream-source/AstrBot-4.29.0").rename(stage/"framework")
    (stage/"upstream-source").rmdir()
    extract(deps/"AstrBot-v4.29.0-dashboard.zip",stage/"framework/dashboard")
    plugin=stage/"data/plugins/astrbot_plugin_qq_ai_lab"
    shutil.copytree(ROOT/"plugin",plugin,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    shutil.copytree(ROOT/"personas",plugin/"personas")
    for name in ("launch.py","doctor.py","start.ps1"):
        shutil.copy2(ROOT/"packaging"/name,stage/name)
    for name,body in {
        "启动机器人.bat":'@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\npowershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"\r\npause\r\n',
        "自检.bat":'@echo off\r\ncd /d "%~dp0"\r\nruntime\\python.exe -I -X utf8 doctor.py\r\npause\r\n',
        "self-check.bat":'@echo off\r\ncd /d "%~dp0"\r\nruntime\\python.exe -I -X utf8 doctor.py\r\npause\r\n',
        "首次使用.html":'<!doctype html><meta charset="utf-8"><title>QQ 毒舌群友首次使用</title><body style="font:18px sans-serif;max-width:850px;margin:48px auto;line-height:1.8"><h1>QQ 毒舌群友 · 离线候选包</h1><p>尚未完成真实 QQ 验收。首次启动需要联网安装固定依赖。</p><ol><li>解压全部文件到可写目录，不要直接在压缩包里运行。</li><li>双击 启动机器人.bat，等待依赖安装并打开 AstrBot 面板。</li><li>在原生面板配置自己的 DeepSeek Key 和 QQ 官方 WebSocket 机器人。</li><li>配置管理员、插件模型 ID 和允许群，群中发送 /帮助。</li></ol><p><a href="docs/新手安装指南.md">完整安装说明</a> · <a href="http://127.0.0.1:6185">打开本机面板</a></p><p>停止：在机器人窗口按 Ctrl+C，然后关闭窗口。日志：本地面板；默认内容已隐藏。不要分享 data 文件夹。</p></body>'
    }.items(): (stage/name).write_bytes(body.encode("utf-8"))
    # Verify neither development machine paths nor generated credentials enter assets.
    manifest={str(f.relative_to(stage)).replace("\\","/"):sha(f) for f in sorted(stage.rglob("*")) if f.is_file()}
    (stage/"MANIFEST.sha256.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    archive=output/(stage.name+".zip")
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in sorted(stage.rglob("*")):
            if f.is_file(): z.write(f,str(f.relative_to(output)))
    (output/"SHA256SUMS.txt").write_text(sha(archive)+"  "+archive.name+"\n",encoding="ascii")
    print(archive.name,archive.stat().st_size,"bytes",sha(archive))


if __name__=="__main__": main()
