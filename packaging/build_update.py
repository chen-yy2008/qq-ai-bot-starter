"""Build code-only updates, plus metadata readable by the existing RC updater."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile
from build import APP_FILES,ROOT
from entrypoints import write_entries
from updater import ALLOWED,ASSET,CHANNEL,METADATA


def build(output):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/"dist").resolve()):raise ValueError("Output must stay within project dist")
    output.mkdir(parents=True,exist_ok=True)
    stage=output/"update-root-entries"
    stage.mkdir(exist_ok=False)
    write_entries(stage)
    payload={}
    for target,names in ALLOWED.items():
        for name in names:
            if target=="app":path=ROOT/"packaging"/name
            elif target=="plugin":path=ROOT/"plugin"/name
            elif target=="root":path=stage/name
            else:path=ROOT/name if name in ("LICENSE","NOTICE-THIRD-PARTY.md") else ROOT/"docs"/name
            if path.exists():
                content=path.read_bytes()
                if name.endswith(".ps1"):content=path.read_text(encoding="utf-8-sig").encode("utf-8-sig")
                payload[(target,name)]=content
    memory=io.BytesIO()
    with zipfile.ZipFile(memory,"w",zipfile.ZIP_DEFLATED) as z:
        for (target,name),content in sorted(payload.items()):z.writestr(f"payload/{target}/{name}",content)
    archive=memory.getvalue()
    manifest={"schema":1,"framework":"4.29.0","version":"1.0.0","release_tag":CHANNEL,"sequence":4,"package":{"name":ASSET,"size":len(archive),"sha256":hashlib.sha256(archive).hexdigest()},"changes":["v1.0.0 收尾：保留已真人验证的群聊身份、授权和 AI 文字回复路径及原生命令兼容修复","模型提供者可选择实例；明确区分源 ID、实例 ID 和服务端临时故障","补充初始化、上下文与主动模式的可复制操作提示；微调中文短句提示词","保留安全诊断、校验备份、失败回滚；只更新列出的自有文件","保留凭据、管理员、允许群、人格与数据库；高级功能验收范围见报告"],"files":[{"target":t,"path":n,"sha256":hashlib.sha256(c).hexdigest()} for (t,n),c in sorted(payload.items())]}
    (output/ASSET).write_bytes(archive)
    (output/METADATA).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    # Publish these two assets on the existing RC channel only AFTER the
    # stable release is approved and its anonymous downloads are verified.
    # Old updaters require their original tag/version, but receive the exact
    # same allowlisted stable payload; the installed updater then uses stable.
    bridge=dict(manifest,version="1.0.0-rc.1",release_tag="v1.0.0-rc.1")
    legacy=output/"rc-bridge";legacy.mkdir()
    (legacy/ASSET).write_bytes(archive)
    (legacy/METADATA).write_text(json.dumps(bridge,ensure_ascii=False,indent=2),encoding="utf-8")
    print(ASSET,len(archive),"bytes",manifest["package"]["sha256"])


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True)
    build(p.parse_args().output)
