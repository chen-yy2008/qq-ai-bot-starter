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

ROOT=Path(__file__).resolve().parent


def install_private_logging():
    factory=logging.getLogRecordFactory()
    def private_factory(*args,**kwargs):
        record=factory(*args,**kwargs)
        record.msg="框架事件（隐私模式已隐藏内容）"
        record.args=()
        record.exc_info=record.exc_text=record.stack_info=None
        record.pathname=record.filename="framework"
        return record
    logging.setLogRecordFactory(private_factory)
    from loguru import logger
    def patch(record):
        record["message"]="框架事件（隐私模式已隐藏内容）"
        record["exception"]=None
    logger.configure(patcher=patch)


def main():
    warnings.filterwarnings("ignore",category=SyntaxWarning)
    os.chdir(ROOT)
    os.environ["ASTRBOT_ROOT"]=str(ROOT)
    os.environ["PYTHONUTF8"]="1"
    os.environ["TMP"]=os.environ["TEMP"]=str(ROOT/"data"/"temp")
    (ROOT/"data"/"temp").mkdir(parents=True,exist_ok=True)
    with socket.socket() as check:
        try: check.bind(("127.0.0.1",6185))
        except OSError:
            print("端口 6185 已被占用。请关闭旧实例，或检查占用程序后重试。")
            return 2
    sys.path.insert(0,str(ROOT/"framework"))
    install_private_logging()
    from astrbot.core.config.default import DEFAULT_CONFIG
    path=ROOT/"data"/"cmd_config.json"
    if not path.exists():
        import copy
        import getpass
        from astrbot.core.utils.auth_password import hash_dashboard_password,hash_md5_dashboard_password,validate_dashboard_password
        conf=copy.deepcopy(DEFAULT_CONFIG)
        conf["dashboard"].update(host="127.0.0.1",port=6185)
        password=os.environ.pop("ASTRBOT_DASHBOARD_INITIAL_PASSWORD","")
        while not password:
            password=getpass.getpass("首次启动：设置本机面板密码（至少 12 位，不显示输入）：")
            try:
                if len(password)<12: raise ValueError("short")
                validate_dashboard_password(password)
            except ValueError:
                password=""
                print("请设置至少 12 位，包含大写字母、小写字母和数字的密码。")
                continue
            if password!=getpass.getpass("再次输入面板密码："):
                password=""
                print("两次输入不一致，请重试。")
        validate_dashboard_password(password)
        conf["dashboard"].update(pbkdf2_password=hash_dashboard_password(password),password=hash_md5_dashboard_password(password),password_storage_upgraded=True,password_change_required=False)
        del password
        conf.update(log_level="WARNING",log_file_enable=False,trace_enable=False,trace_log_enable=False,disable_metrics=True)
        conf["provider_ltm_settings"]["group_message_history_enable"]=False
        conf["platform_settings"]["ignore_bot_self_message"]=True
        conf["platform_settings"]["enable_id_white_list"]=False
        path.write_text(json.dumps(conf,ensure_ascii=False,indent=2),encoding="utf-8")
    else:
        conf=json.loads(path.read_text(encoding="utf-8-sig"))
        conf["dashboard"].update(host="127.0.0.1",port=6185)
        conf.update(log_file_enable=False,trace_enable=False,trace_log_enable=False)
        conf.setdefault("provider_ltm_settings",{})["group_message_history_enable"]=False
        path.write_text(json.dumps(conf,ensure_ascii=False,indent=2),encoding="utf-8")
    def open_browser():
        for _ in range(90):
            try:
                with socket.create_connection(("127.0.0.1",6185),timeout=1): pass
                webbrowser.open("http://127.0.0.1:6185")
                return
            except OSError: time.sleep(1)
    if not os.environ.get("QQ_AI_NO_BROWSER"):
        threading.Thread(target=open_browser,daemon=True).start()
    print("正在启动 AstrBot。面板地址：http://127.0.0.1:6185\n登录用户名：astrbot；密码为首次启动时你设置的本机面板密码。\n默认日志隐藏消息和异常内容。停止：在此窗口按 Ctrl+C。请勿分享 data 文件夹。")
    sys.argv=[str(ROOT/"framework"/"main.py"),"--webui-dir",str(ROOT/"framework"/"dashboard"/"dist")]
    try: runpy.run_path(str(ROOT/"framework"/"main.py"),run_name="__main__")
    except KeyboardInterrupt: print("机器人已停止。")
    except Exception as error:
        # No traceback, exception text, user paths or provider payloads in logs.
        print("启动失败，异常类型："+type(error).__name__+"。请双击 自检.bat，并参阅 docs/常见故障.md。")
        return 1
    return 0


if __name__=="__main__":
    try: code=main()
    except KeyboardInterrupt: code=0
    except Exception as error:
        print("启动失败，异常类型："+type(error).__name__+"。请运行自检；敏感错误细节已隐藏。")
        code=1
    raise SystemExit(code)
