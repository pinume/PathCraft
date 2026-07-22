$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "未找到 uv，无法构建 PathCraft.exe。"
}

$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$output = Join-Path $projectDirectory "dist\PathCraft.exe"
$icon = Join-Path $projectDirectory "assets\pathcraft.ico"
$iconData = "$icon;assets"
$ui = Join-Path $projectDirectory "assets\ui"
$uiData = "$ui;assets\ui"

Push-Location $projectDirectory
try {
    & uv run --group build pyinstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name PathCraft `
        --icon $icon `
        --add-data $iconData `
        --add-data $uiData `
        --hidden-import webview `
        --paths src `
        --exclude-module numpy `
        --exclude-module pandas `
        --exclude-module PIL `
        --exclude-module lxml `
        --exclude-module defusedxml `
        --exclude-module fontTools `
        --exclude-module matplotlib `
        --exclude-module IPython `
        --exclude-module pytest `
        --exclude-module cppyy `
        --exclude-module pymupdf_fonts `
        --distpath dist `
        --workpath build\pyinstaller `
        --specpath build `
        packaging\pathcraft_portable.pyw
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $output)) {
    throw "构建完成但未找到输出文件：$output"
}

$artifact = Get-Item -LiteralPath $output
Write-Host "便携版构建完成：$($artifact.FullName) ($([math]::Round($artifact.Length / 1MB, 1)) MB)"
