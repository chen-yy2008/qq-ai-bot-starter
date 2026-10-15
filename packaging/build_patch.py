"""Create an in-place launcher-only patch. No framework, data or dependencies."""
import argparse
from pathlib import Path
import shutil
import zipfile
from build import APP_FILES,ROOT
from entrypoints import write_entries

p=argparse.ArgumentParser()
p.add_argument("--output",type=Path,required=True)
args=p.parse_args()
output=args.output.resolve()
if not output.is_relative_to((ROOT/"dist").resolve()): raise SystemExit("Output must stay within project dist")
output.mkdir(parents=True,exist_ok=False)
(output/"程序文件").mkdir()
for folder in (output,output/"程序文件"):
    for name in APP_FILES:
        source=ROOT/"packaging"/name
        if name.endswith(".ps1"):
            (folder/name).write_text(source.read_text(encoding="utf-8-sig"),encoding="utf-8-sig")
        else: shutil.copy2(source,folder/name)
write_entries(output)
shutil.copytree(ROOT/"docs",output/"使用说明")
for name in ("LICENSE","NOTICE-THIRD-PARTY.md"):
    shutil.copy2(ROOT/name,output/"使用说明"/name)
archive=output.parent/"QQ-AI-Bot-Windows-体验修复补丁.zip"
with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
    for f in sorted(output.rglob("*")):
        if f.is_file(): z.write(f,str(f.relative_to(output)))
print(archive.name)
