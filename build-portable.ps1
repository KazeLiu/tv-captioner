$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location $PSScriptRoot

$env:PYTHONPATH = ""
$env:PYTHONHOME = ""
$env:PYTHONNOUSERSITE = "1"
$env:PIP_CONFIG_FILE = "NUL"

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    .\setup.ps1
}

.\.venv\Scripts\python.exe -m pip install --isolated -r .\packaging\requirements-build.txt

if (Test-Path ".\dist\TVCaptionerBackend") {
    Remove-Item -LiteralPath ".\dist\TVCaptionerBackend" -Recurse -Force
}

.\.venv\Scripts\pyinstaller.exe `
    --noconfirm `
    --clean `
    --onedir `
    --name TVCaptionerBackend `
    --add-data "app\static;app\static" `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all llama_cpp `
    --collect-all tokenizers `
    --collect-all av `
    --hidden-import uvicorn.logging `
    --hidden-import uvicorn.loops `
    --hidden-import uvicorn.loops.auto `
    --hidden-import uvicorn.protocols `
    --hidden-import uvicorn.protocols.http `
    --hidden-import uvicorn.protocols.http.auto `
    --hidden-import uvicorn.protocols.websockets `
    --hidden-import uvicorn.protocols.websockets.auto `
    --hidden-import uvicorn.lifespan `
    --hidden-import uvicorn.lifespan.on `
    .\run_server.py

New-Item -ItemType Directory -Force -Path ".\dist\TVCaptionerBackend\models\asr" | Out-Null
New-Item -ItemType Directory -Force -Path ".\dist\TVCaptionerBackend\models\translate" | Out-Null
New-Item -ItemType Directory -Force -Path ".\dist\TVCaptionerBackend\data\uploads" | Out-Null
New-Item -ItemType Directory -Force -Path ".\dist\TVCaptionerBackend\data\outputs" | Out-Null

$llamaDll = ".\dist\TVCaptionerBackend\_internal\llama_cpp\lib\llama.dll"
if (-not (Test-Path $llamaDll)) {
    throw "打包结果缺少 GGUF 运行库：$llamaDll"
}

Copy-Item ".\README.md" ".\dist\TVCaptionerBackend\README.md" -Force
Copy-Item ".\怎么使用.md" ".\dist\TVCaptionerBackend\怎么使用.md" -Force

Write-Host ""
Write-Host "便携版已经生成：" -ForegroundColor Green
Write-Host (Join-Path $PSScriptRoot "dist\TVCaptionerBackend\TVCaptionerBackend.exe")
Write-Host ""
Write-Host "把 dist\TVCaptionerBackend 整个文件夹拷贝到其他 Windows 机器，双击 TVCaptionerBackend.exe 即可启动。"
