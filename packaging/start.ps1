$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8='1'
$env:UV_CACHE_DIR=Join-Path $PSScriptRoot 'data\install-cache'
$env:UV_NO_PROGRESS='1'
try {
    New-Item -ItemType Directory -Force -Path 'data\temp' | Out-Null
    $env:TEMP=Join-Path $PSScriptRoot 'data\temp'
    $env:TMP=$env:TEMP
    if (!(Test-Path -LiteralPath 'runtime\python.exe')) { throw 'RuntimeMissing' }
    $hasher=[System.Security.Cryptography.SHA256]::Create()
    try { $expected=[System.BitConverter]::ToString($hasher.ComputeHash([System.IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'packaging\requirements-win.lock')))).Replace('-','') }
    finally { $hasher.Dispose() }
    $ready=Test-Path -LiteralPath 'data\dependencies.ready'
    if ($ready) { $ready=((Get-Content -LiteralPath 'data\dependencies.ready' -Raw).Trim() -eq $expected) }
    if (!$ready) {
        Write-Host 'First start: installing pinned dependencies. Internet required; this may take several minutes.'
        New-Item -ItemType Directory -Force -Path 'data' | Out-Null
        $savedPreference=$ErrorActionPreference
        $ErrorActionPreference='Continue'
        $installOutput=(& '.\tools\uv.exe' pip sync 'packaging\requirements-win.lock' --build-constraints 'packaging\build-constraints.txt' --python 'runtime\python.exe' --target 'runtime\Lib\site-packages' --require-hashes --index-url 'https://pypi.org/simple' --quiet 2>&1 | Out-String)
        $installExit=$LASTEXITCODE
        $ErrorActionPreference=$savedPreference
        if ($installExit -ne 0) {
            $category='DEPENDENCY_INSTALL_FAILED'
            if ($installOutput -match 'timed out|dns|connect|request|network') { $category='NETWORK_FAILED' }
            if ($installOutput -match 'hash mismatch|Hash mismatch') { $category='HASH_MISMATCH' }
            if ($installOutput -match 'Access is denied|Permission denied|os error 5|No space') { $category='DISK_OR_PERMISSION_FAILED' }
            $category | Set-Content -LiteralPath 'data\install-status.txt' -Encoding ascii
            $installOutput=$null
            throw $category
        }
        $installOutput=$null
        'DEPENDENCIES_OK' | Set-Content -LiteralPath 'data\install-status.txt' -Encoding ascii
        $expected | Set-Content -LiteralPath 'data\dependencies.ready' -Encoding ascii
    }
    & '.\runtime\python.exe' -I -X utf8 'launch.py'
    if ($LASTEXITCODE -ne 0) { throw 'StartupFailed' }
} catch {
    'START_FAILED' | Set-Content -LiteralPath 'data\start-status.txt' -Encoding ascii
    Write-Host 'Setup/start failed. Check network, disk space and docs. Run self-check.bat.' -ForegroundColor Red
    Write-Host 'Safe result codes: data\install-status.txt and data\start-status.txt. See docs.'
    exit 1
}
