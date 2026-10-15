"""Run the pinned framework locally with content-free default logging."""
import json
import logging
import os
from pathlib import Path
import runpy
import socket
import sys
import threading
import time
import webbrowser
import warnings
import _thread

sys.path.insert(0,str(Path(__file__).resolve().parent))
from bundle_paths import locations
from panel_password import BundleLock,Cancelled,PasswordError,atomic_write,check_stopped,ensure_password,notify,panel_details,sanitize_environment
import safe_diagnostics
sys.modules["qqbot_safe_diagnostics"]=safe_diagnostics

ROOT,APP=locations(__file__)


def install_private_logging():
    safe_diagnostics.install_private_logging()


def main():
    sanitize_environment()
    with BundleLock(ROOT):
        return run_locked()


def run_locked():
    warnings.filterwarnings("ignore",category=SyntaxWarning)
    # This MUST run before even importing astrbot.core.config.default, whose
    # parent package creates AstrBotConfig() as an import side effect.
    conf=ensure_password(ROOT,APP)
    check_stopped(conf)
    address,username=panel_details(conf)
    os.chdir(ROOT)
    os.environ["ASTRBOT_ROOT"]=str(ROOT)
    os.environ["PYTHONUTF8"]="1"
    os.environ["TMP"]=os.environ["TEMP"]=str(ROOT/"data"/"temp")
    (ROOT/"data"/"temp").mkdir(parents=True,exist_ok=True)
    framework=APP/"framework"
    sys.path.insert(0,str(framework))
    install_private_logging()
    safe_diagnostics.install(ROOT)
    def open_browser():
        for _ in range(90):
            try:
                with socket.create_connection(("127.0.0.1",conf["dashboard"].get("port",6185)),timeout=1): pass
                webbrowser.open(address)
                return
            except OSError: time.sleep(1)
    if not os.environ.get("QQ_AI_NO_BROWSER"):
        threading.Thread(target=open_browser,daemon=True).start()
    import secrets
    instance=secrets.token_hex(16)
    record=ROOT/"data/robot-process.json"
    atomic_write(record,json.dumps({"pid":os.getpid(),"instance":instance}).encode())
    stopping=threading.Event()
    def watch_stop():
        while not stopping.wait(0.2):
            try:
                request=json.loads((ROOT/"data/stop-request.json").read_text(encoding="utf-8"))
                if request.get("instance")==instance:
                    _thread.interrupt_main()
                    return
            except (OSError,ValueError): pass
    threading.Thread(target=watch_stop,daemon=True).start()
    print(f"正在启动 AstrBot。面板地址：{address}\n登录用户名：{username}；请使用你刚设置的管理密码，并保存好密码。\n日志仅显示安全阶段和错误类别；排查请双击 安全诊断.bat。停止：双击 停止机器人.bat 或在此窗口按 Ctrl+C。请勿分享 data 文件夹。")
    sys.argv=[str(framework/"main.py"),"--webui-dir",str(framework/"dashboard"/"dist")]
    try: runpy.run_path(str(framework/"main.py"),run_name="__main__")
    except KeyboardInterrupt: print("机器人已停止。")
    except Exception as error:
        # No traceback, exception text, user paths or provider payloads in logs.
        print("启动失败，异常类型："+type(error).__name__+"。请双击 自检.bat，并参阅 docs/常见故障.md。")
        return 1
    finally:
        stopping.set()
        for path in (record,ROOT/"data/stop-request.json"):
            try: path.unlink(missing_ok=True)
            except OSError: pass
    return 0


if __name__=="__main__":
    try: code=main()
    except Cancelled:
        print("已取消密码设置；机器人没有启动，原配置未修改。")
        code=2
    except PasswordError as error:
        notify(APP,str(error),error=True)
        code=1
    except KeyboardInterrupt: code=0
    except Exception as error:
        print("启动失败，异常类型："+type(error).__name__+"。请运行自检；敏感错误细节已隐藏。")
        code=1
    raise SystemExit(code)
