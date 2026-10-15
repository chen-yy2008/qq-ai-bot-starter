"""One downloadable BAT for old packages without an updater. Verified own code only."""
import argparse
import json
from pathlib import Path
from updater import REPO,CHANNEL,ASSET

PREFIX='''@echo off
chcp 65001 >nul
set "QQBOT_BOOTSTRAP=%~f0"
powershell.exe -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $s=[IO.File]::ReadAllText($env:QQBOT_BOOTSTRAP,[Text.Encoding]::UTF8); & ([ScriptBlock]::Create(($s -split '(?m)^# POWERSHELL_PAYLOAD\\r?$',2)[1]))"
pause
exit /b
# POWERSHELL_PAYLOAD
'''

SCRIPT='''$ErrorActionPreference='Stop'
try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $dialog=New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description='选择现有机器人目录：应能看到 启动机器人.bat 和 data。不会重新安装框架。'
    $dialog.ShowNewFolderButton=$false
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { Write-Host '已取消。'; exit 0 }
    $installRoot=[IO.Path]::GetFullPath($dialog.SelectedPath)
    $appRoot=Join-Path $installRoot '程序文件'
    if (!(Test-Path -LiteralPath (Join-Path $appRoot 'runtime\\python.exe'))) { $appRoot=$installRoot }
    $python=Join-Path $appRoot 'runtime\\python.exe'
    if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath (Join-Path $appRoot 'framework\\main.py')) -or !(Test-Path -LiteralPath (Join-Path $installRoot 'data\\plugins\\astrbot_plugin_qq_ai_lab\\main.py'))) { throw 'INSTALL_NOT_FOUND' }
    Write-Host '从项目公开候选 Release 下载已固定校验值的更新器。无需 GitHub 登录。'
    $stage=Join-Path $installRoot 'data\\update-bootstrap\\@@SHORT@@'
    $probe=$stage
    while ($probe -and $probe -ne (Split-Path -Parent $installRoot)) {
        if (Test-Path -LiteralPath $probe) {
            if ((Get-Item -LiteralPath $probe -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'LINKED_DIRECTORY_REJECTED' }
        }
        $probe=Split-Path -Parent $probe
    }
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    $archive=Join-Path $stage 'verified-update.zip'
    [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
    $web=New-Object Net.WebClient
    try { $web.Headers['User-Agent']='QQ-AI-Bot-Update-Bootstrap/1'; $web.DownloadFile('@@URL@@',$archive) }
    finally { $web.Dispose() }
    $hasher=[Security.Cryptography.SHA256]::Create()
    try { $actual=[BitConverter]::ToString($hasher.ComputeHash([IO.File]::ReadAllBytes($archive))).Replace('-','').ToLowerInvariant() }
    finally { $hasher.Dispose() }
    if ($actual -ne '@@SHA@@' -or (Get-Item -LiteralPath $archive).Length -ne @@SIZE@@) { throw 'HASH_OR_SIZE_MISMATCH' }
    $zip=[IO.Compression.ZipFile]::OpenRead($archive)
    try {
        foreach ($name in @('updater.py','bundle_paths.py','panel_password.py','control.py')) {
            $entry=$zip.GetEntry('payload/app/'+$name)
            if (!$entry -or $entry.Length -gt 1000000) { throw 'UPDATER_ENTRY_INVALID' }
            $stream=$entry.Open()
            $output=[IO.File]::Create((Join-Path $stage $name))
            try { $stream.CopyTo($output) } finally { $output.Dispose(); $stream.Dispose() }
        }
    } finally { $zip.Dispose() }
    & $python -I -X utf8 (Join-Path $stage 'updater.py') --root $installRoot
    if ($LASTEXITCODE -ne 0) { Write-Host '更新未完成。请阅读上方安全提示；不要删除 data 或备份。' -ForegroundColor Yellow; exit 1 }
} catch {
    Write-Host '引导未完成：请确认安装目录、网络和磁盘权限。下载包必须通过固定 SHA256 和大小校验才会运行；程序配置没有被本引导器覆盖。' -ForegroundColor Red
    exit 1
}
'''


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--manifest",type=Path,required=True)
    args=p.parse_args();m=json.loads(args.manifest.read_text(encoding="utf-8"));pkg=m["package"]
    script=SCRIPT.replace("@@SHORT@@",pkg["sha256"][:16]).replace("@@URL@@",f"https://github.com/{REPO}/releases/download/{CHANNEL}/{ASSET}").replace("@@SHA@@",pkg["sha256"]).replace("@@SIZE@@",str(pkg["size"]))
    output=args.manifest.parent/"QQ-AI-Bot-Update-Start.bat"
    output.write_bytes((PREFIX+script).replace("\r\n","\n").replace("\n","\r\n").encode("utf-8"))
    print(output.name)
