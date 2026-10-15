"""Exercise real root BATs, native password GUI, login, stop, reset and restart."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request

p=argparse.ArgumentParser()
p.add_argument("--package",type=Path,required=True)
p.add_argument("--port",type=int,default=6185)
args=p.parse_args()
root=args.package.resolve()
app=root/"程序文件"
if (root/"data/cmd_config.json").exists(): raise SystemExit("Smoke test requires fresh extracted package data")
if args.port!=6185:
    from panel_password import BOOTSTRAP
    fixture=json.loads(json.dumps(BOOTSTRAP))
    fixture["dashboard"]["port"]=args.port
    (root/"data").mkdir(exist_ok=True)
    (root/"data/cmd_config.json").write_text(json.dumps(fixture),encoding="utf-8")
driver=Path(__file__).resolve().parents[1]/"tests/windows_gui_driver.ps1"
password="GuiOwnerA1"+secrets.token_urlsafe(20)
new_password="ResetOwnerB2"+secrets.token_urlsafe(20)
env=dict(os.environ,ASTRBOT_DASHBOARD_INITIAL_PASSWORD="UnwantedFixtureA12345",ASTRBOT_RESET_DASHBOARD_PASSWORD="1",QQ_AI_NO_BROWSER="1",PYTHONUTF8="1")
logs=[]
processes=[]

def entry(name):
    output=(root.parent/(name+".test.out.log")).open("wb")
    error=(root.parent/(name+".test.err.log")).open("wb")
    logs.extend([output,error])
    process=subprocess.Popen([os.environ.get("COMSPEC","cmd.exe"),"/d","/c","call",str(root/name)],cwd=root,env=env,stdout=output,stderr=error,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    processes.append(process)
    return process


def gui(process,password_value="",notice=False):
    command=["powershell.exe","-NoLogo","-NoProfile","-STA","-ExecutionPolicy","Bypass","-File",str(driver),"-RootPid",str(process.pid)]
    if notice: command.append("-NoticeOnly")
    result=subprocess.run(command,input=json.dumps({"password":password_value}).encode(),capture_output=True,timeout=320)
    if result.returncode: raise RuntimeError("REAL_GUI_AUTOMATION_FAILED")


def request(path,body=None,token=None):
    headers={"Content-Type":"application/json"}
    if token: headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(f"http://127.0.0.1:{args.port}"+path,data=json.dumps(body).encode() if body else None,headers=headers)
    with urllib.request.urlopen(req,timeout=10) as response: return response.status,response.read()


def wait_ready(process):
    for i in range(360):
        if process.poll() is not None: raise RuntimeError("STARTUP_EXITED")
        try:
            status,body=request("/")
            if status==200 and b"<html" in body.lower(): return
        except Exception: pass
        if i%30==0: print("Installing/starting:",i,"seconds",flush=True)
        time.sleep(1)
    raise RuntimeError("WEBUI_TIMEOUT")


def login(value):
    status,body=request("/api/auth/login",{"username":"astrbot","password":value})
    auth=json.loads(body); data=auth.get("data") or {}
    token=data.get("token") or data.get("access_token")
    if not token or data.get("password_change_required"): raise RuntimeError("LOCAL_LOGIN_FAILED")
    return token


def stopped(process):
    control=entry("停止机器人.bat")
    gui(control,notice=True)
    control.wait(timeout=20)
    process.wait(timeout=20)
    if (root/"data/robot-process.json").exists(): raise RuntimeError("STOP_RECORD_NOT_REMOVED")


try:
    for name in ("启动机器人.bat","打开管理面板.bat","停止机器人.bat","重置管理密码.bat","首次使用.html"):
        if not (root/name).exists(): raise RuntimeError("ROOT_ENTRY_MISSING")
    print("FLAT_ZIP_ROOT_ENTRIES_OK",flush=True)
    process=entry("启动机器人.bat")
    gui(process,password)
    print("REAL_FIRST_PASSWORD_GUI_OK (inherited password/reset env ignored)",flush=True)
    wait_ready(process)
    print("WEBUI_HTTP_200",flush=True)
    old_token=login(password)
    print("NATIVE_LOGIN_WITH_GUI_PASSWORD_OK",flush=True)
    status,body=request("/api/plugin/get",token=old_token)
    if "qq_ai_lab" not in body.decode(): raise RuntimeError("PLUGIN_NOT_LOADED")
    print("PINNED_PLUGIN_LOADED",flush=True)
    status,body=request("/api/v1/plugins/config/schema?plugin_id=qq_ai_lab",token=old_token)
    metadata=json.loads(body)["data"]["metadata"]["qq_ai_lab"]["items"]["provider_id"]
    if metadata.get("_special")!="select_provider" or "deepseek/deepseek-flash" not in metadata.get("hint",""):
        raise RuntimeError("MODEL_INSTANCE_SELECTOR_SCHEMA_NOT_EXPOSED")
    if not any(b'select_provider' in f.read_bytes() for f in (app/"framework/dashboard/dist/assets").glob("*.js")):
        raise RuntimeError("PINNED_DASHBOARD_MODEL_SELECTOR_NOT_PRESENT")
    print("NATIVE_MODEL_INSTANCE_SELECTOR_SCHEMA_AND_DASHBOARD_OK",flush=True)
    checks=subprocess.run([str(app/"runtime/python.exe"),"-I","-X","utf8",str(app/"doctor.py")],capture_output=True,text=True,encoding="utf-8")
    if "MISSING" in checks.stdout: raise RuntimeError("MISSING_COMPONENT")
    print("ALL_COMPONENTS_PRESENT",flush=True)
    stopped(process)
    print("ROOT_STOP_ENTRY_OK",flush=True)
    conf_path=root/"data/cmd_config.json"
    before=json.loads(conf_path.read_text(encoding="utf-8-sig"))
    sentinel=root/"data/user-data-retention.fixture"
    sentinel.write_bytes(b"keep existing private data fixture")
    reset=entry("重置管理密码.bat")
    gui(reset,new_password)
    if reset.wait(timeout=20)!=0: raise RuntimeError("RESET_EXIT_FAILED")
    after=json.loads(conf_path.read_text(encoding="utf-8-sig"))
    for field in ("password","pbkdf2_password","password_storage_upgraded","password_change_required","jwt_secret"):
        before["dashboard"].pop(field,None); after["dashboard"].pop(field,None)
    if before!=after or sentinel.read_bytes()!=b"keep existing private data fixture": raise RuntimeError("RESET_CHANGED_NON_AUTH_DATA")
    print("REAL_RESET_GUI_PRESERVES_CONFIG_AND_DATA",flush=True)
    process=entry("启动机器人.bat")
    wait_ready(process)
    login(new_password)
    try: login(password)
    except urllib.error.HTTPError as error:
        if error.code!=401: raise
    else: raise RuntimeError("OLD_PASSWORD_STILL_WORKS")
    try: request("/api/plugin/get",token=old_token)
    except urllib.error.HTTPError as error:
        if error.code!=401: raise
    else: raise RuntimeError("OLD_TOKEN_STILL_WORKS")
    print("RESTART_NEW_PASSWORD_OK_OLD_PASSWORD_AND_TOKEN_REJECTED",flush=True)
    stopped(process)
    print("REAL_QQ_AND_DEEPSEEK_NOT_TESTED",flush=True)
finally:
    for process in processes:
        if process.poll() is None:
            subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for log in logs: log.close()
