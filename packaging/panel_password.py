"""Local-only panel ownership and atomic auth updates. Never import AstrBot."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import tempfile

AUTH_FIELDS={"password","pbkdf2_password","password_storage_upgraded","password_change_required","jwt_secret"}
REQUIREMENTS="至少 12 位，包含大写字母、小写字母和数字；两个密码框必须一致。"
BOOTSTRAP={"dashboard":{"enable":True,"username":"astrbot","host":"127.0.0.1","port":6185},"platform_settings":{"ignore_bot_self_message":True,"enable_id_white_list":False},"provider_ltm_settings":{"group_message_history_enable":False},"log_level":"WARNING","log_file_enable":False,"trace_enable":False,"trace_log_enable":False,"disable_metrics":True}


class PasswordError(Exception): pass
class Cancelled(PasswordError): pass


def sanitize_environment():
    # An inherited value must never initialize or reset this user's password.
    for key in ("ASTRBOT_DASHBOARD_INITIAL_PASSWORD","ASTRBOT_RESET_DASHBOARD_PASSWORD"):
        os.environ.pop(key,None)


def no_duplicates(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise PasswordError("配置存在重复字段，请先修复配置；原文件未修改。")
        result[key]=value
    return result


def read_config(root):
    path=Path(root)/"data/cmd_config.json"
    original=path.read_bytes() if path.exists() else None
    if original is None: return copy.deepcopy(BOOTSTRAP),None
    try:
        conf=json.loads(original.decode("utf-8-sig"),object_pairs_hook=no_duplicates)
    except (ValueError,UnicodeError): raise PasswordError("配置文件无法解析；原文件未修改。") from None
    if not isinstance(conf,dict) or not isinstance(conf.get("dashboard",{}),dict):
        raise PasswordError("管理后台配置格式异常；原文件未修改。")
    return conf,original


def panel_details(conf):
    panel=conf.get("dashboard",{})
    port=panel.get("port",6185)
    if not isinstance(port,int) or not 1<=port<=65535: raise PasswordError("后台端口配置无效；原文件未修改。")
    username=panel.get("username","astrbot")
    if not isinstance(username,str) or not username: raise PasswordError("后台用户名配置无效；原文件未修改。")
    scheme="https" if (panel.get("ssl") or {}).get("enable") else "http"
    return f"{scheme}://127.0.0.1:{port}",username


def check_stopped(conf):
    port=conf.get("dashboard",{}).get("port",6185)
    panel_details(conf)
    for candidate in {port,6185}:
        with socket.socket() as check:
            try:
                if hasattr(socket,"SO_EXCLUSIVEADDRUSE"):
                    check.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
                check.bind(("127.0.0.1",candidate))
            except OSError:
                raise PasswordError("请先关闭 AstrBot（或占用后台端口的程序），然后重试。原配置未修改。") from None


class BundleLock:
    """The launcher holds this lock for its entire lifetime, including startup."""
    def __init__(self,root): self.path=Path(root)/"data/panel-control.lock"; self.file=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file=self.path.open("a+b")
        try:
            if self.file.tell()==0: self.file.write(b"0"); self.file.flush()
            self.file.seek(0)
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.file.close(); self.file=None
            raise PasswordError("机器人正在运行或另一个设置窗口已打开；请先关闭后再操作。") from None
        return self
    def __exit__(self,*args):
        if self.file:
            self.file.seek(0)
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
            self.file.close()


def validate_password(password,confirmation):
    if not isinstance(password,str) or not 12<=len(password)<=128: raise PasswordError("密码长度应为 12–128 位。")
    if not all(re.search(pattern,password) for pattern in (r"[A-Z]",r"[a-z]",r"[0-9]")): raise PasswordError("密码需包含大写字母、小写字母和数字。")
    if password!=confirmation: raise PasswordError("两次输入的密码不一致。")


def fingerprint(conf):
    panel=conf.get("dashboard",{})
    value={key:panel.get(key) for key in ("username","password","pbkdf2_password")}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def initialized(root,conf):
    panel=conf.get("dashboard",{})
    try:
        scheme,iterations,salt,digest=panel.get("pbkdf2_password","").split("$")
        usable=scheme=="pbkdf2_sha256" and 0<int(iterations)<=5_000_000 and len(bytes.fromhex(salt))==16 and len(bytes.fromhex(digest))==32
    except (ValueError,TypeError,AttributeError): return False
    if not usable or panel.get("password_change_required",True): return False
    try:
        receipt=json.loads((Path(root)/"data/panel-password.initialized.json").read_text(encoding="utf-8"))
        # A prepared receipt is not proof of ownership until config replacement
        # succeeds. Later WebUI password changes remain valid and need no reset.
        return receipt.get("schema")==1 and receipt.get("source")=="local-password-dialog" and receipt.get("username")==panel.get("username","astrbot") and fingerprint(conf)!=receipt.get("previous_fingerprint")
    except (OSError,ValueError): return False


def atomic_write(path,content,*,before_commit=None):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    name=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix=".panel-",suffix=".tmp",delete=False) as f:
            name=f.name; f.write(content); f.flush(); os.fsync(f.fileno())
        if before_commit: before_commit()
        os.replace(name,path)
        name=None
    finally:
        if name:
            try: Path(name).unlink()
            except OSError: pass


def save_password(root,conf,original,password,confirmation,*,stopped=check_stopped):
    validate_password(password,confirmation)
    updated=copy.deepcopy(conf)
    panel=updated.setdefault("dashboard",{})
    panel.setdefault("username","astrbot")
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),600_000).hex()
    panel.update(pbkdf2_password=f"pbkdf2_sha256$600000${salt}${digest}",password=hashlib.md5(password.encode()).hexdigest(),password_storage_upgraded=True,password_change_required=False,jwt_secret=secrets.token_urlsafe(48))
    content=(json.dumps(updated,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8")
    path=Path(root)/"data/cmd_config.json"
    stopped(conf)
    if (path.read_bytes() if path.exists() else None)!=original:
        raise PasswordError("配置在设置期间发生了变化，请重新操作。原文件未覆盖。")
    receipt={"schema":1,"source":"local-password-dialog","username":panel["username"],"previous_fingerprint":fingerprint(conf)}
    # Prepare ownership proof first. os.replace of config is the final commit;
    # any preceding failure leaves the original config byte-for-byte untouched.
    atomic_write(Path(root)/"data/panel-password.initialized.json",json.dumps(receipt).encode("utf-8"))
    def verify_unchanged():
        stopped(conf)
        if (path.read_bytes() if path.exists() else None)!=original:
            raise PasswordError("配置在保存期间发生变化，原文件未覆盖。请重试。")
    atomic_write(path,content,before_commit=verify_unchanged)
    return updated


def dialog(app,mode,username,address):
    script=Path(app)/"password_dialog.ps1"
    command=["powershell.exe","-NoLogo","-NoProfile","-STA","-ExecutionPolicy","Bypass","-File",str(script),"-Mode",mode]
    # Only non-secret display information is passed on stdin; passwords return
    # through an anonymous pipe. No environment variable or CLI contains one.
    result=subprocess.run(command,input=json.dumps({"username":username,"address":address},ensure_ascii=False).encode(),capture_output=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    if result.returncode==2: raise Cancelled("已取消，原配置未修改。")
    if result.returncode: raise PasswordError("无法打开密码设置窗口；原配置未修改。")
    try:
        data=json.loads(result.stdout.decode("utf-8-sig"))
        password,confirmation=data["password"],data["confirmation"]
        validate_password(password,confirmation)
        return password,confirmation
    except (ValueError,KeyError,TypeError): raise PasswordError("密码窗口返回结果无效；原配置未修改。") from None


def notify(app,message,error=False):
    # Message is never a password or a raw exception.
    command=["powershell.exe","-NoLogo","-NoProfile","-STA","-ExecutionPolicy","Bypass","-File",str(Path(app)/"password_dialog.ps1"),"-Mode","notice"]
    try:
        subprocess.run(command,input=json.dumps({"message":message,"error":error},ensure_ascii=False).encode(),capture_output=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    except OSError: pass


def ensure_password(root,app,*,reset=False,ask=dialog,inform=notify):
    sanitize_environment()
    conf,original=read_config(root)
    if not reset and initialized(root,conf): return conf
    check_stopped(conf)
    address,username=panel_details(conf)
    password,confirmation=ask(app,"reset" if reset else "setup",username,address)
    updated=save_password(root,conf,original,password,confirmation)
    del password,confirmation
    inform(app,f"管理密码已保存。\n\n登录地址：{address}\n用户名：{username}\n\n启动机器人后，请使用刚设置的密码登录。请保存好密码，不要发送给其他人。")
    return updated
