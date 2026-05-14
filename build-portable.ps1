$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location $PSScriptRoot

$env:PYTHONPATH = ""
$env:PYTHONHOME = ""
$env:PYTHONNOUSERSITE = "1"
$env:PIP_CONFIG_FILE = "NUL"
$distRoot = Join-Path $PSScriptRoot "dist"
$distDir = Join-Path $distRoot "TVCaptionerBackend"
$gpuDlcDir = Join-Path $distRoot "TVCaptionerBackend-GGUF-CUDA-DLC"
$workDir = Join-Path $PSScriptRoot "build\pyinstaller"
$specDir = Join-Path $PSScriptRoot "build\pyinstaller-spec"
$staticDir = Join-Path $PSScriptRoot "app\static"
$cudaWheelDir = Join-Path $PSScriptRoot "build\gguf-cuda-wheel"
$gpuDlcPayloadDir = Join-Path $gpuDlcDir "gguf-cuda-dlc"
$llamaCpuWheel = "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.23/llama_cpp_python-0.3.23-py3-none-win_amd64.whl"
$llamaCudaWheel = "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.23-cu124/llama_cpp_python-0.3.23-py3-none-win_amd64.whl"
$gpuDlcFiles = @(
    "_internal\cublas64_12.dll",
    "_internal\cublasLt64_12.dll"
)

Write-Host "== TV Captioner portable build ==" -ForegroundColor Cyan
Write-Host "Project root: $PSScriptRoot"
Write-Host ""

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "[1/5] Creating runtime environment..." -ForegroundColor Yellow
    .\setup.ps1
}
else {
    Write-Host "[1/5] Ensuring runtime dependencies..." -ForegroundColor Yellow
    .\.venv\Scripts\python.exe -m pip install --isolated -r .\requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install runtime dependencies."
    }
}

Write-Host "[2/5] Installing build dependencies..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe -u -m pip install --isolated -r .\packaging\requirements-build.txt
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install build dependencies."
}

if (Test-Path ".\dist\TVCaptionerBackend") {
    Write-Host "[3/5] Removing previous dist\\TVCaptionerBackend..." -ForegroundColor Yellow
    Remove-Item -LiteralPath $distDir -Recurse -Force
}
if (Test-Path $workDir) {
    Remove-Item -LiteralPath $workDir -Recurse -Force
}
if (Test-Path $specDir) {
    Remove-Item -LiteralPath $specDir -Recurse -Force
}
if (Test-Path $cudaWheelDir) {
    Remove-Item -LiteralPath $cudaWheelDir -Recurse -Force
}

Write-Host "[3/5] Preparing optional GGUF CUDA DLC..." -ForegroundColor Yellow
if (Test-Path $gpuDlcDir) {
    Remove-Item -LiteralPath $gpuDlcDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $gpuDlcPayloadDir | Out-Null
.\.venv\Scripts\python.exe -m pip install --isolated --no-deps --no-cache-dir --target $cudaWheelDir $llamaCudaWheel
if ($LASTEXITCODE -ne 0) {
    throw "Failed to download GGUF CUDA wheel for DLC."
}

$cudaLlamaPackage = Join-Path $cudaWheelDir "llama_cpp"
$cudaLlamaDistInfo = Get-ChildItem -LiteralPath $cudaWheelDir -Directory -Filter "llama_cpp_python-*.dist-info" | Select-Object -First 1
if (-not (Test-Path $cudaLlamaPackage)) {
    throw "GGUF CUDA wheel did not contain llama_cpp package."
}

$dlcInternal = Join-Path $gpuDlcPayloadDir "_internal"
$dlcLlamaPackage = Join-Path $dlcInternal "llama_cpp"
if (Test-Path $dlcLlamaPackage) {
    Remove-Item -LiteralPath $dlcLlamaPackage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $dlcInternal | Out-Null
Copy-Item -LiteralPath $cudaLlamaPackage -Destination $dlcLlamaPackage -Recurse -Force
if ($cudaLlamaDistInfo) {
    $dlcDistInfo = Join-Path $dlcInternal $cudaLlamaDistInfo.Name
    if (Test-Path $dlcDistInfo) {
        Remove-Item -LiteralPath $dlcDistInfo -Recurse -Force
    }
    Copy-Item -LiteralPath $cudaLlamaDistInfo.FullName -Destination $dlcDistInfo -Recurse -Force
}

function Find-CudaDll([string]$dllName) {
    $candidates = @()
    if ($env:CUDA_PATH) {
        $candidates += Join-Path $env:CUDA_PATH "bin\$dllName"
    }
    if ($env:CUDA_PATH_V12_6) {
        $candidates += Join-Path $env:CUDA_PATH_V12_6 "bin\$dllName"
    }
    if ($env:CUDA_PATH_V12_4) {
        $candidates += Join-Path $env:CUDA_PATH_V12_4 "bin\$dllName"
    }
    $whereResult = (& where.exe $dllName 2>$null)
    if ($whereResult) {
        $candidates += $whereResult
    }
    $candidates += Get-ChildItem "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA" -Recurse -File -Filter $dllName -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        ForEach-Object { $_.FullName }
    return $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

foreach ($relativePath in $gpuDlcFiles) {
    $dllName = Split-Path -Leaf $relativePath
    $sourcePath = Find-CudaDll $dllName
    if (-not $sourcePath) {
        Write-Host "Optional CUDA DLL not found on this machine: $dllName" -ForegroundColor Yellow
        continue
    }
    $targetPath = Join-Path $gpuDlcPayloadDir $relativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force
    Write-Host "Added to DLC: $relativePath"
}

$dlcReadme = @"
TV Captioner Backend GGUF CUDA DLC

This folder contains optional GGUF translation GPU runtime files.

How to install:
1. Download and extract the base TVCaptionerBackend package.
2. Copy this folder's gguf-cuda-dlc directory into the TVCaptionerBackend folder.
3. Keep gguf-cuda-dlc there when updating the base package.
4. Start TVCaptionerBackend.exe and set GGUF translation GPU layers in the Live tab.

Without this DLC, the base package still works and GGUF translation runs on CPU.
"@
$dlcReadme | Set-Content -LiteralPath (Join-Path $gpuDlcDir "README-GGUF-CUDA-DLC.txt") -Encoding UTF8

Write-Host "Ensuring base package uses CPU GGUF runtime..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe -m pip install --isolated --force-reinstall --no-deps --no-cache-dir $llamaCpuWheel
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install CPU GGUF runtime for the base package."
}

Write-Host "[4/5] Running PyInstaller..." -ForegroundColor Yellow
& .\.venv\Scripts\python.exe -u -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name TVCaptionerBackend `
    --distpath $distRoot `
    --workpath $workDir `
    --specpath $specDir `
    --add-data "${staticDir};app\static" `
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
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed. See the messages above."
}

Write-Host "[5/5] Preparing portable folder..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path (Join-Path $distDir "models\asr") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $distDir "models\translate") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $distDir "data\uploads") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $distDir "data\outputs") | Out-Null

$llamaDll = Get-ChildItem -Path $distDir -Recurse -Filter "llama.dll" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $llamaDll) {
    throw "Portable build is missing llama.dll under $distDir"
}
Write-Host ("Found GGUF runtime: " + $llamaDll.FullName)

Get-ChildItem -LiteralPath $PSScriptRoot -Filter "*.md" -File | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $distDir $_.Name) -Force
}

Write-Host ""
Write-Host "Portable build completed:" -ForegroundColor Green
Write-Host (Join-Path $distDir "TVCaptionerBackend.exe")
Write-Host ""
Write-Host "Optional GGUF CUDA DLC folder:" -ForegroundColor Green
Write-Host $gpuDlcDir
Write-Host ""
Write-Host "Release the base dist\TVCaptionerBackend folder for CPU/default use."
Write-Host "Release dist\TVCaptionerBackend-GGUF-CUDA-DLC separately for users who want GGUF GPU translation."
