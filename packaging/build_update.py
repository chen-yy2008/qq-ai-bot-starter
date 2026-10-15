"""Build a small public candidate repair asset from explicit code/doc lists."""
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
    manifest={"schema":1,"framework":"4.29.0","version":"1.0.0-rc.1","release_tag":CHANNEL,"sequence":2,"package":{"name":ASSET,"size":len(archive),"sha256":hashlib.sha256(archive).hexdigest()},"changes":["修复群消息处理器对 AstrBot 原生和其他插件命令的全局拦截","初始化身份无需模型；插件使用普通文本回复，避免依赖 QQ 原生 Markdown 权限","保留群白名单、授权、预算、冷却、退出记忆和默认关闭的主动模式","新增本机安全诊断，以及下载校验、程序备份、失败恢复的一键更新","GitHub 匿名 API 限流时改走同一公开 Release HTTPS 清单，仍强制 ZIP 和逐文件校验","仅更新列出的自有程序和说明，保留凭据、群设置、人格和数据库"],"files":[{"target":t,"path":n,"sha256":hashlib.sha256(c).hexdigest()} for (t,n),c in sorted(payload.items())]}
    (output/ASSET).write_bytes(archive)
    (output/METADATA).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(ASSET,len(archive),"bytes",manifest["package"]["sha256"])


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True)
    build(p.parse_args().output)
