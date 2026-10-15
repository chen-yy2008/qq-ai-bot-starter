"""Download only pinned official artifacts and verify before any extraction."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

p=argparse.ArgumentParser()
p.add_argument("--deps",type=Path,required=True)
args=p.parse_args()
args.deps.mkdir(parents=True,exist_ok=True)
lock=json.loads((Path(__file__).parent/"artifacts.lock.json").read_text())
for entry in lock["artifacts"]:
    target=args.deps/entry["file"]
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=entry["sha256"]:
        print("Downloading",entry["file"],flush=True)
        request=urllib.request.Request(entry["url"],headers={"User-Agent":"qq-ai-bot-starter-build/1.0"})
        with urllib.request.urlopen(request,timeout=90) as r:
            target.write_bytes(r.read())
    if hashlib.sha256(target.read_bytes()).hexdigest()!=entry["sha256"]:
        raise SystemExit("Hash mismatch: "+entry["file"])
    print("Verified",entry["file"],flush=True)
