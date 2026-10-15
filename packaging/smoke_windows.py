"""Fresh bootstrap + authenticated native API checks. No QQ/model credentials."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request

p=argparse.ArgumentParser()
p.add_argument("--package",type=Path,required=True)
args=p.parse_args()
root=args.package.resolve()
if (root/"data/cmd_config.json").exists(): raise SystemExit("Smoke test requires fresh package data")
password="QqLab1"+secrets.token_urlsafe(24)
env=dict(os.environ,ASTRBOT_DASHBOARD_INITIAL_PASSWORD=password,QQ_AI_NO_BROWSER="1",PYTHONUTF8="1")
out=(root.parent/"smoke-private.out.log").open("wb")
err=(root.parent/"smoke-private.err.log").open("wb")
process=subprocess.Popen(["powershell.exe","-NoLogo","-NoProfile","-ExecutionPolicy","Bypass","-File",str(root/"start.ps1")],cwd=root,env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
def request(path,body=None,token=None):
    headers={"Content-Type":"application/json"}
    if token: headers["Authorization"]="Bearer "+token
    req=urllib.request.Request("http://127.0.0.1:6185"+path,data=json.dumps(body).encode() if body else None,headers=headers)
    with urllib.request.urlopen(req,timeout=10) as response:
        return response.status,response.read()
try:
    for i in range(360):
        if process.poll() is not None: raise RuntimeError("STARTUP_EXITED")
        try:
            status,body=request("/")
            if status==200 and b"<html" in body.lower(): break
        except Exception: pass
        if i%30==0: print("Installing/starting:",i,"seconds",flush=True)
        time.sleep(1)
    else: raise RuntimeError("WEBUI_TIMEOUT")
    print("WEBUI_HTTP_200",flush=True)
    status,body=request("/api/auth/login",{"username":"astrbot","password":password})
    auth=json.loads(body)
    data=auth.get("data") or {}
    token=data.get("token") or data.get("access_token")
    if not token: raise RuntimeError("LOCAL_LOGIN_FAILED")
    print("NATIVE_LOGIN_OK",flush=True)
    status,body=request("/api/plugin/get",token=token)
    plugins=json.loads(body)
    if "qq_ai_lab" not in json.dumps(plugins): raise RuntimeError("PLUGIN_NOT_LOADED")
    print("PINNED_PLUGIN_LOADED",flush=True)
    status,body=request("/api/plugin/source/get-failed-plugins",token=token)
    failed=json.loads(body)
    if "qq_ai_lab" in json.dumps(failed): raise RuntimeError("PLUGIN_LOAD_ERROR")
    print("NO_QQ_PLUGIN_LOAD_FAILURE",flush=True)
    checks=subprocess.run([str(root/"runtime/python.exe"),"-I","-X","utf8",str(root/"doctor.py")],capture_output=True,text=True,encoding="utf-8")
    if "MISSING" in checks.stdout: raise RuntimeError("MISSING_COMPONENT")
    print("ALL_COMPONENTS_PRESENT",flush=True)
    print("REAL_QQ_AND_DEEPSEEK_NOT_TESTED",flush=True)
finally:
    # Only terminate the process tree started by this smoke test.
    subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    out.close(); err.close()
