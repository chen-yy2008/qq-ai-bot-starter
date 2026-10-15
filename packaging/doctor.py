"""Report capability codes only: no credentials, message text or machine paths."""
import importlib.util
import json
from pathlib import Path
import socket
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from bundle_paths import locations

root,app=locations(__file__)
print("QQ AI Bot self-check; private local data will not be printed.")
print("PYTHON:",sys.version.split()[0],"X64:",sys.maxsize>2**32)
for module in ("aiohttp","openai","quart","botpy","sqlalchemy","PIL","faiss"):
    print("DEPENDENCY",module,"OK" if importlib.util.find_spec(module) else "MISSING")
print("DASHBOARD:","OK" if (app/"framework/dashboard/dist/index.html").exists() else "MISSING")
print("PLUGIN:","OK" if (root/"data/plugins/astrbot_plugin_qq_ai_lab/main.py").exists() else "MISSING")
conf=root/"data/cmd_config.json"
if conf.exists():
    try:
        c=json.loads(conf.read_text(encoding="utf-8-sig"))
        print("QQ_ADAPTER:","CONFIGURED_NOT_VERIFIED" if any(p.get("type")=="qq_official" and p.get("enable") for p in c.get("platform",[])) else "NOT_CONFIGURED")
        print("MODEL:","CONFIGURED_NOT_VERIFIED" if c.get("provider") else "NOT_CONFIGURED")
    except Exception: print("CONFIG: INVALID_JSON")
try:
    with socket.socket() as s: s.bind(("127.0.0.1",6185))
    print("PORT_6185: FREE")
except OSError: print("PORT_6185: IN_USE (possibly the running bot)")
print("REAL_QQ_AND_KEY: require user authorization and actual /自检 + group test.")
