$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "未找到 uv，请先安装 uv 后再运行此脚本。"
}

$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path

& uv tool install --reinstall $projectDirectory
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& uv tool update-shell
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "PathCraft 已安装。重新打开终端后，输入 pathcraft 即可启动。"
