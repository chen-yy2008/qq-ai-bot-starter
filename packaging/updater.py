"""Explicit, verified program-file updates. No pip, framework reinstall or secrets."""
import argparse
from datetime import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from bundle_paths import locations
from panel_password import BundleLock,PasswordError,atomic_write,check_stopped,panel_details,read_config
from control import stop as stop_robot

REPO="chen-yy2008/qq-ai-bot-starter"
CHANNEL="v1.0.0"  # Fixed public stable release; never a draft/artifact URL.
API=f"https://api.github.com/repos/{REPO}/releases/tags/{CHANNEL}"
ASSET="QQ-AI-Bot-Update.zip"
METADATA="QQ-AI-Bot-Update.json"
MAX_ZIP=16_000_000
ALLOWED={
    "app":frozenset("launch.py doctor.py start.ps1 bundle_paths.py panel_password.py password_dialog.ps1 control.py safe_diagnostics.py diagnostic_control.py updater.py".split()),
    "plugin":frozenset("main.py core.py diagnostics.py images.py __init__.py catalog.json _conf_schema.json metadata.yaml requirements.txt".split()),
    "root":frozenset(("启动机器人.bat","打开管理面板.bat","停止机器人.bat","重置管理密码.bat","检查并更新.bat","安全诊断.bat","自检.bat","self-check.bat","首次使用.html")),
    "docs":frozenset(("新手安装指南.md","常见故障.md","更新与诊断.md","发布说明.md","开发和许可证说明.md","验收报告.md","真人验收清单.md","QQ官方机器人配置.md","password-window.png","windows-login.png","LICENSE","NOTICE-THIRD-PARTY.md")),
}


class UpdateError(Exception):
    def __init__(self,message,code=None):
        super().__init__(message)
        self.code=code


def digest(content):return hashlib.sha256(content).hexdigest()


def trusted_url(url):
    p=urllib.parse.urlsplit(url)
    return p.scheme=="https" and p.hostname in ("api.github.com","github.com","release-assets.githubusercontent.com","objects.githubusercontent.com") and not p.username and not p.password and p.port in (None,443)


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,url):
        if not trusted_url(url):raise UpdateError("下载重定向到未信任来源；已拒绝。")
        return super().redirect_request(request,fp,code,msg,headers,url)


def download(url,limit,expected=None):
    """Bounded, timeout-protected, TLS-verified anonymous HTTPS, no retries/install."""
    if not trusted_url(url):raise UpdateError("更新来源不受信任。")
    request=urllib.request.Request(url,headers={"User-Agent":"QQ-AI-Bot-Updater/1","Accept":"application/vnd.github+json" if "api.github.com/" in url else "application/octet-stream"})
    try:
        with urllib.request.build_opener(Redirect()).open(request,timeout=25) as response:
            if not trusted_url(response.geturl()):raise UpdateError("下载来源校验失败。")
            content=bytearray()
            while True:
                block=response.read(min(65536,limit+1-len(content)))
                if not block:break
                content.extend(block)
                if len(content)>limit:raise UpdateError("下载内容超过大小限制。")
    except urllib.error.HTTPError as e:raise UpdateError(f"GitHub 下载失败（HTTP {e.code}）；未修改程序。请稍后重试。",code=e.code) from None
    except (OSError,urllib.error.URLError,TimeoutError,http.client.HTTPException):raise UpdateError("网络连接失败、超时或下载中断；未修改程序。请检查网络后重试。",code="network") from None
    if expected and digest(content)!=expected:raise UpdateError("SHA256 完整性校验失败；未停止机器人或修改程序。")
    return bytes(content)


def get_release(fetch=download):
    source=f"https://github.com/{REPO}/releases/download/{CHANNEL}/"
    try:raw=fetch(API,1_000_000)
    except UpdateError as error:
        if error.code not in (403,429,500,502,503,504,"network"):raise
        # GitHub's shared anonymous API quota can be exhausted even for a
        # public release. Its stable asset URL remains anonymously accessible.
        # The manifest is authenticated by normal HTTPS to our exact repo;
        # ZIP SHA256, size, version and every file hash remain mandatory.
        print("GitHub 公共 API 暂不可用；改用同一公开 Release 的 HTTPS 清单，保留全部文件完整性校验。")
        try:manifest=json.loads(fetch(source+METADATA,1_000_000))
        except (ValueError,UnicodeError):raise UpdateError("公开更新清单无法解析；未修改程序。") from None
        validate_manifest(manifest)
        return manifest,source+ASSET
    try:
        release=json.loads(raw)
        if release.get("draft") or release.get("prerelease") or release.get("tag_name")!=CHANNEL:raise ValueError()
        assets={x["name"]:x for x in release["assets"]}
        meta=assets[METADATA]
        if meta["browser_download_url"]!=source+METADATA:raise ValueError()
        checksum=meta.get("digest","")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}",checksum):raise ValueError()
        manifest=json.loads(fetch(meta["browser_download_url"],1_000_000,checksum[7:]))
        validate_manifest(manifest)
        archive=assets[ASSET]
        if archive["browser_download_url"]!=source+ASSET or archive["size"]!=manifest["package"]["size"] or archive.get("digest")!="sha256:"+manifest["package"]["sha256"]:raise ValueError()
        return manifest,archive["browser_download_url"]
    except (KeyError,TypeError,ValueError,UnicodeError):raise UpdateError("公开更新元数据不完整或不匹配；未修改程序。") from None


def validate_manifest(m):
    try:
        if m["schema"]!=1 or m["framework"]!="4.29.0" or m["version"]!="1.0.0" or m["release_tag"]!=CHANNEL or type(m["sequence"]) is not int or m["sequence"]<1:raise ValueError()
        p=m["package"]
        if p["name"]!=ASSET or not re.fullmatch(r"[0-9a-f]{64}",p["sha256"]) or type(p["size"]) is not int or not 0<p["size"]<=MAX_ZIP:raise ValueError()
        found=set()
        for f in m["files"]:
            key=(f["target"],f["path"])
            if key in found or f["path"] not in ALLOWED.get(f["target"],()) or not re.fullmatch(r"[0-9a-f]{64}",f["sha256"]):raise ValueError()
            found.add(key)
        if not found or len(found)>100:raise ValueError()
        for key in (("app","updater.py"),("plugin","main.py"),("root","检查并更新.bat")):
            if key not in found:raise ValueError()
        # Release notes printed in a console are our constrained metadata, not
        # arbitrary release markdown containing links, escapes or user data.
        if not isinstance(m["changes"],list) or not 1<=len(m["changes"])<=12:raise ValueError()
        if any(not isinstance(s,str) or len(s)>200 or any(ord(c)<32 for c in s) for s in m["changes"]):raise ValueError()
    except (KeyError,TypeError,ValueError):raise UpdateError("更新清单不受支持或包含非允许文件；已拒绝。") from None


def layout(root):
    root=Path(root).resolve()
    app=root/"程序文件" if (root/"程序文件/runtime/python.exe").is_file() else root
    if not (app/"runtime/python.exe").is_file() or not (app/"framework/main.py").is_file() or not (root/"data/plugins/astrbot_plugin_qq_ai_lab/main.py").is_file():raise UpdateError("此目录不是支持的 Windows 整合包。请选择包含 启动机器人.bat 和 data 的安装目录。")
    version=app/"framework/astrbot/__init__.py"
    try:
        if not re.search(r'^__version__\s*=\s*[\'"]4\.29\.0[\'"]',version.read_text(encoding="utf-8"),re.M):raise ValueError()
    except (OSError,ValueError):raise UpdateError("仅支持锁定的 AstrBot 4.29.0；版本不匹配，未更新。") from None
    for relative in ("data/update-control.lock","data/panel-control.lock","data/qqbot-update.json","data/stop-request.json","data/robot-process.json","data/update-backups"):
        guard_path(root,root/relative)
    return root,app


def destination(root,app,f):
    base={"app":app,"plugin":root/"data/plugins/astrbot_plugin_qq_ai_lab","root":root,"docs":root/"使用说明"}[f["target"]]
    path=base/f["path"]
    return guard_path(root,path)


def guard_path(root,path):
    for parent in (path,*path.parents):
        if parent==root.parent:break
        if parent.is_symlink() or (parent.exists() and getattr(parent.stat(),"st_file_attributes",0)&0x400):raise UpdateError("更新目标包含链接或联接目录；为保护其他文件已停止。")
    if not path.resolve().is_relative_to(root):raise UpdateError("更新目标越出安装目录。")
    return path


def unpack(archive,m):
    import io
    if len(archive)!=m["package"]["size"] or digest(archive)!=m["package"]["sha256"]:raise UpdateError("更新包大小或 SHA256 不匹配；未修改程序。")
    expected={f"payload/{f['target']}/{f['path']}":f for f in m["files"]}
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            names=z.namelist()
            if len(names)!=len(set(names)) or set(names)!=set(expected):raise ValueError()
            if sum(x.file_size for x in z.infolist())>32_000_000:raise ValueError()
            result={}
            for name,f in expected.items():
                info=z.getinfo(name)
                if info.file_size>8_000_000 or (info.external_attr>>16)&0o170000==0o120000:raise ValueError()
                data=z.read(name)
                if digest(data)!=f["sha256"]:raise ValueError()
                result[(f["target"],f["path"])]=data
            return result
    except (ValueError,zipfile.BadZipFile,KeyError,RuntimeError):raise UpdateError("更新 ZIP 文件清单或逐文件校验失败；未修改程序。") from None


def running(root,app):
    conf,_=read_config(root)
    try:
        with BundleLock(root):check_stopped(conf)
        return False
    except PasswordError:
        if not (root/"data/robot-process.json").is_file():raise UpdateError("有旧版机器人或其他程序占用后台。请在原启动窗口按 Ctrl+C 关闭，再重新更新；不会强行终止未知进程。") from None
        return True


def start_robot(root,app):
    env=os.environ.copy()
    for name in ("ASTRBOT_DASHBOARD_INITIAL_PASSWORD","ASTRBOT_RESET_DASHBOARD_PASSWORD"):env.pop(name,None)
    process=subprocess.Popen([os.environ.get("COMSPEC","cmd.exe"),"/d","/c","call",str(root/"启动机器人.bat")],cwd=root,env=env,creationflags=getattr(subprocess,"CREATE_NEW_CONSOLE",0))
    address,_=panel_details(read_config(root)[0])
    for _ in range(90):
        if process.poll() is not None:raise UpdateError("更新后的启动程序提前退出。")
        try:
            with urllib.request.urlopen(address,timeout=1) as response:
                if response.status==200 and (root/"data/robot-process.json").is_file():return
        except (OSError,urllib.error.URLError):pass
        time.sleep(1)
    raise UpdateError("更新后后台未在等待时间内就绪。")


def stop_and_wait(root,app):
    stop_robot(root,app,quiet=True)
    # The stop receipt is removed just before the launcher's lifetime lock is
    # released. Wait for both so a normal shutdown cannot race the update.
    for _ in range(100):
        try:
            with BundleLock(root):check_stopped(read_config(root)[0])
            return
        except PasswordError:time.sleep(0.2)
    raise UpdateError("机器人尚未完全退出；未开始覆盖程序文件。")


def apply_update(root,app,m,files,*,is_running=running,stop=None,start=start_robot,replace=atomic_write):
    """Backup only listed program bytes. On any failure restore exactly those bytes."""
    stop=stop or stop_and_wait
    validate_manifest(m)
    plans=[(f,destination(root,app,f),files[(f["target"],f["path"])]) for f in m["files"]]
    if any(digest(data)!=f["sha256"] for f,_,data in plans):raise UpdateError("安装前逐文件校验失败。")
    for unfinished in (root/"data/update-backups").glob("*/transaction.json"):
        try:state=json.loads(unfinished.read_text(encoding="utf-8"))["state"]
        except (OSError,ValueError,KeyError):raise UpdateError("旧备份状态无法读取，请先检查本机 data/update-backups；没有继续更新。") from None
        if state in ("installing","restarting","manual_recovery_required"):
            raise UpdateError("上次更新中断，需要先恢复 data/update-backups 内原程序文件；没有继续覆盖。请保留备份并联系项目维护者。")
    was_running=is_running(root,app)
    backup=root/"data/update-backups"/(datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+secrets.token_hex(4))
    guard_path(root,backup)
    backup.mkdir(parents=True,exist_ok=False)
    transaction={"schema":1,"version":m["version"],"state":"prepared","files":[]}
    for n,(f,path,data) in enumerate(plans):
        old=path.read_bytes() if path.exists() else None
        if old is not None:atomic_write(backup/f"{n:03}.original",old)
        transaction["files"].append({"target":f["target"],"path":f["path"],"existed":old is not None,"sha256_before":digest(old) if old is not None else None,"backup":f"{n:03}.original"})
    def state(value):
        transaction["state"]=value
        atomic_write(backup/"transaction.json",json.dumps(transaction,ensure_ascii=False,indent=2).encode())
    state("prepared")
    changed=[]
    receipt=root/"data/qqbot-update.json"
    guard_path(root,receipt)
    receipt_before=receipt.read_bytes() if receipt.exists() else None
    try:
        if was_running:stop(root,app)
        with BundleLock(root):
            check_stopped(read_config(root)[0])
            state("installing")
            for n,(f,path,data) in enumerate(plans):
                changed.append(n)
                replace(path,data)
                if digest(path.read_bytes())!=f["sha256"]:raise UpdateError("安装后文件校验失败。")
            atomic_write(receipt,json.dumps({"schema":1,"version":m["version"],"sequence":m["sequence"],"sha256":m["package"]["sha256"]}).encode())
            state("restarting")
        start(root,app)
        state("committed")
        return backup
    except (Exception,KeyboardInterrupt):
        if not changed:
            state("cancelled")
            raise UpdateError("停止或安装准备失败；程序文件未更改。请检查运行状态后重试。") from None
        try:
            if is_running(root,app):stop(root,app)
            with BundleLock(root):
                check_stopped(read_config(root)[0])
                for n in reversed(changed):
                    old=transaction["files"][n]
                    target=plans[n][1]
                    if old["existed"]:
                        content=(backup/old["backup"]).read_bytes()
                        if digest(content)!=old["sha256_before"]:raise UpdateError("备份校验失败。")
                        atomic_write(target,content)
                    else:target.unlink(missing_ok=True)
                if receipt_before is None:receipt.unlink(missing_ok=True)
                else:atomic_write(receipt,receipt_before)
                state("rolled_back")
            if was_running:start(root,app)
        except Exception:
            try:state("manual_recovery_required")
            except OSError:pass
            raise UpdateError("更新失败且无法自动完整恢复。已停止后续操作；请关闭机器人，保留 data/update-backups 下本次备份并联系项目维护者。不能视为更新成功。") from None
        raise UpdateError("更新失败；已校验并恢复本次改动的原程序文件。配置、人格和数据库未覆盖。备份在 data/update-backups。") from None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path)
    parser.add_argument("--check-only",action="store_true")
    args=parser.parse_args()
    root,app=layout(args.root or locations(__file__)[0])
    lock=BundleLock(root);lock.path=root/"data/update-control.lock"
    with lock:
        manifest,url=get_release()
        print("可信来源：https://github.com/"+REPO+"\n可用更新："+manifest["version"])
        for change in manifest["changes"]:print("- "+change)
        try:current=json.loads((root/"data/qqbot-update.json").read_text(encoding="utf-8"))
        except (OSError,ValueError):current={}
        if current.get("sequence",0)>=manifest["sequence"]:
            print("当前已安装此更新。各项真人验证范围见使用说明中的验收报告。")
            return 0
        print("安装目录："+str(root)+"\n本次仅修改以下程序文件（不会覆盖配置、人格、记忆数据库或其他插件）：")
        for f in manifest["files"]:print("  "+str(destination(root,app,f).relative_to(root)))
        if args.check_only:
            content=download(url,manifest["package"]["size"],manifest["package"]["sha256"])
            unpack(content,manifest)
            print("PUBLIC_DOWNLOAD_AND_FILE_HASHES_OK；仅检查，未安装、未停止机器人。")
            return 0
        print("将下载校验、备份、停止本目录机器人、安装并重新启动。")
        if input("输入 Y 确认更新，其他输入取消：").strip().lower()!="y":
            print("已取消，没有修改程序。")
            return 0
        content=download(url,manifest["package"]["size"],manifest["package"]["sha256"])
        files=unpack(content,manifest)
        backup=apply_update(root,app,manifest,files)
        print("更新成功，后台已就绪。备份："+str(backup)+"\n配置、人格和数据库已保留；此结果不代表所有 QQ 功能均已真人验证。")
        return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except (UpdateError,PasswordError) as error:print("更新未完成："+str(error));raise SystemExit(1)
    except (KeyboardInterrupt,EOFError):print("已取消。若安装阶段发生中断，请保留 data/update-backups 并先检查恢复状态。");raise SystemExit(2)
    except Exception:print("更新未完成：本地文件、配置或安装状态异常。请保留备份；敏感错误细节已隐藏。");raise SystemExit(1)
