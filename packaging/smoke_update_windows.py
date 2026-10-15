"""Update a disposable GUI-smoke package with real stop/start and file hashes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import updater as u


def main():
    p=argparse.ArgumentParser();p.add_argument("--package",type=Path,required=True)
    p.add_argument("--manifest",type=Path);p.add_argument("--archive",type=Path)
    p.add_argument("--public",action="store_true")
    args=p.parse_args();root,app=u.layout(args.package)
    conf,_=u.read_config(root)
    if conf.get("platform") or conf.get("provider") or (root/"data/user-data-retention.fixture").read_bytes()!=b"keep existing private data fixture":
        raise RuntimeError("UPDATE_SMOKE_REQUIRES_DISPOSABLE_CREDENTIAL_FREE_GUI_FIXTURE")
    if args.public:
        manifest,url=u.get_release()
        content=u.download(url,manifest["package"]["size"],manifest["package"]["sha256"])
        print("ANONYMOUS_GITHUB_RELEASE_DOWNLOAD_OK",flush=True)
    else:
        manifest=json.loads(args.manifest.read_text(encoding="utf-8"));content=args.archive.read_bytes()
    files=u.unpack(content,manifest)
    protected=[root/"data/cmd_config.json",root/"data/panel-password.initialized.json",root/"data/user-data-retention.fixture"]
    protected+=list((root/"data/plugins/astrbot_plugin_qq_ai_lab/personas").glob("*.json"))
    protected+=list((root/"data/config").glob("*.json"))
    before={path:path.read_bytes() for path in protected}
    original_popen=subprocess.Popen
    children=[]
    output=(root.parent/"update-smoke.safe.log").open("wb")
    def hidden_popen(*args,**kwargs):
        kwargs["creationflags"]=getattr(subprocess,"CREATE_NO_WINDOW",0)
        kwargs["env"]=dict(kwargs.get("env",os.environ),QQ_AI_NO_BROWSER="1")
        kwargs["stdout"]=output;kwargs["stderr"]=output
        child=original_popen(*args,**kwargs);children.append(child);return child
    try:
        with patch.object(u.subprocess,"Popen",hidden_popen):
            u.start_robot(root,app)
            print("REAL_EXISTING_INSTANCE_RUNNING",flush=True)
            backup=u.apply_update(root,app,manifest,files)
            print("REAL_UPDATE_STOP_INSTALL_RESTART_WEBUI_OK",flush=True)
            u.stop_and_wait(root,app)
        for child in children:child.wait(timeout=25)
        for path,data in before.items():
            if path.read_bytes()!=data:raise RuntimeError("PRIVATE_FIXTURE_CHANGED_DURING_UPDATE")
        if json.loads((backup/"transaction.json").read_text(encoding="utf-8"))["state"]!="committed":raise RuntimeError("UPDATE_NOT_COMMITTED")
        for f in manifest["files"]:
            if u.digest(u.destination(root,app,f).read_bytes())!=f["sha256"]:raise RuntimeError("INSTALLED_HASH_MISMATCH")
        print("PROGRAM_HASHES_AND_CONFIG_PERSONAS_DATA_PRESERVED",flush=True)
        print("REAL_QQ_AND_DEEPSEEK_NOT_TESTED",flush=True)
    finally:
        try:
            if (root/"data/robot-process.json").exists():u.stop_and_wait(root,app)
        except Exception:pass
        output.close()


if __name__=="__main__":main()
