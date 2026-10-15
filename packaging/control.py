"""User entry points. Pure stdlib: password reset needs no framework installation."""
import json
import os
from pathlib import Path
import secrets
import sys
import time
import urllib.request
import webbrowser

sys.path.insert(0,str(Path(__file__).resolve().parent))
from bundle_paths import locations
from panel_password import BundleLock,Cancelled,PasswordError,atomic_write,ensure_password,notify,panel_details,read_config


def stop(root,app,quiet=False):
    record=Path(root)/"data/robot-process.json"
    try: instance=json.loads(record.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        raise PasswordError("未找到由本启动器管理的运行实例。旧版启动窗口请按 Ctrl+C 关闭。") from None
    atomic_write(Path(root)/"data/stop-request.json",json.dumps({"instance":instance["instance"]}).encode())
    address,_=panel_details(read_config(root)[0])
    for _ in range(100):
        if not record.exists():
            if not quiet:notify(app,"机器人已停止。现在可以重置管理密码或重新启动。")
            return
        try:
            with urllib.request.urlopen(address,timeout=0.4): pass
        except Exception: pass
        time.sleep(0.2)
    raise PasswordError("已发送停止请求，仍在等待退出。请查看启动窗口；如尚未退出，请在原窗口按 Ctrl+C。")


def main():
    root,app=locations(__file__)
    action=sys.argv[1] if len(sys.argv)>1 else "reset"
    try:
        if action in ("setup","reset"):
            with BundleLock(root):
                ensure_password(root,app,reset=action=="reset")
        elif action=="open":
            conf,_=read_config(root)
            webbrowser.open(panel_details(conf)[0])
        elif action=="stop": stop(root,app)
        else: raise PasswordError("未知操作。请使用安装目录中的快捷入口。")
        return 0
    except Cancelled:
        print("已取消，原配置未修改。")
        return 2
    except PasswordError as error:
        notify(app,str(error),error=True)
        print("操作未完成；请查看提示窗口。原有配置和数据会保留。")
        return 1
    except Exception:
        notify(app,"操作失败。请确认机器人已关闭、配置格式正确且安装目录可写。未提交的新密码不会覆盖原配置。",error=True)
        print("操作失败；错误细节已隐藏。")
        return 1


if __name__=="__main__": raise SystemExit(main())
