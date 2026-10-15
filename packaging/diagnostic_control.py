"""Console menu, safe diagnostics toggle/report; never reads bot configuration."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from bundle_paths import locations
from panel_password import atomic_write
import safe_diagnostics


def main():
    root,_=locations(__file__)
    flag=root/"data/safe-diagnostics.enabled.json"
    print("安全诊断（不记录消息原文、身份、Key 或 QQ Secret）")
    print("1. 开启一次诊断（最长一小时；启用后重启机器人）\n2. 查看诊断结果\n3. 关闭诊断（立即生效，正常隐私模式）\n其他输入退出")
    action=input("选择：").strip()
    if action=="1":
        # Start a fresh observation interval; no prior conversation content exists.
        atomic_write(root/"data/safe-diagnostics.jsonl",b"")
        atomic_write(flag,json.dumps({"expires":time.time()+3600}).encode())
        print("已开启。请重启机器人，在 QQ 群复现一次，然后选 2 查看。完成后选 3 关闭。")
    elif action=="2":safe_diagnostics.report(root)
    elif action=="3":
        flag.unlink(missing_ok=True)
        print("已关闭；仍保留安全阶段日志，不记录正文和凭据。")
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except (OSError,ValueError,EOFError):print("诊断操作未完成：请确认本机目录可写。敏感错误细节已隐藏。");raise SystemExit(1)
