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
$staleOnlineDistDir = Join-Path $distRoot "TVCaptionerBackend-Online"
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

function Invoke-Pip([string[]]$Arguments, [int]$Retries = 1) {
    for ($attempt = 1; $attempt -le $Retries; $attempt++) {
        & .\.venv\Scripts\python.exe -m pip @Arguments
        if ($LASTEXITCODE -eq 0) {
            return
        }
        if ($attempt -lt $Retries) {
            Write-Host "pip command failed, retrying ($attempt/$Retries): $($Arguments -join ' ')" -ForegroundColor Yellow
            Start-Sleep -Seconds 2
        }
    }
    throw "pip command failed: $($Arguments -join ' ')"
}

function Remove-IfExists([string]$Path) {
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
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

function New-GgufCudaDlc {
    Write-Host "[3/5] Preparing optional GGUF CUDA DLC..." -ForegroundColor Yellow
    $dlcReadme = @"
TV Captioner Backend GGUF CUDA DLC

这个文件夹是可选的 GPU 加速包，里面包含转写 CUDA 加速和 GGUF 翻译 GPU offload 需要的运行库文件。

安装方法：
1. 先下载并解压普通版 TVCaptionerBackend。
2. 把本文件夹里的 gguf-cuda-dlc 目录复制到普通版 TVCaptionerBackend 目录下。
3. 以后更新普通版时，保留这个 gguf-cuda-dlc 目录即可，不需要每次重新下载 DLC。
4. 启动 TVCaptionerBackend.exe。转写 CUDA 会自动尝试使用 DLC 里的运行库；只有界面显示 GGUF GPU offload 可用时，才需要到“直播 > 高级设备参数”里设置 GGUF 翻译 GPU 层数。

不安装这个 DLC，普通版也可以正常运行；缺少 CUDA 运行库时，转写和 GGUF 翻译会使用 CPU。
"@

    $requiredDlcFiles = @(
        "_internal\llama_cpp\lib\ggml-cuda.dll",
        "_internal\cublas64_12.dll",
        "_internal\cublasLt64_12.dll"
    )
    $dlcReady = $true
    foreach ($relativePath in $requiredDlcFiles) {
        if (-not (Test-Path (Join-Path $gpuDlcPayloadDir $relativePath))) {
            $dlcReady = $false
            break
        }
    }
    if ($dlcReady) {
        Write-Host "Existing GGUF CUDA DLC is complete; reusing it without downloading again."
        $dlcReadme | Set-Content -LiteralPath (Join-Path $gpuDlcDir "README-GGUF-CUDA-DLC.txt") -Encoding UTF8
        return
    }

    Remove-IfExists $gpuDlcDir
    Remove-IfExists $cudaWheelDir
    New-Item -ItemType Directory -Force -Path $gpuDlcPayloadDir | Out-Null

    Invoke-Pip -Arguments @("install", "--isolated", "--no-deps", "--no-cache-dir", "--target", $cudaWheelDir, $llamaCudaWheel) -Retries 3

    $cudaLlamaPackage = Join-Path $cudaWheelDir "llama_cpp"
    $cudaLlamaDistInfo = Get-ChildItem -LiteralPath $cudaWheelDir -Directory -Filter "llama_cpp_python-*.dist-info" | Select-Object -First 1
    if (-not (Test-Path $cudaLlamaPackage)) {
        throw "GGUF CUDA wheel did not contain llama_cpp package."
    }

    $dlcInternal = Join-Path $gpuDlcPayloadDir "_internal"
    New-Item -ItemType Directory -Force -Path $dlcInternal | Out-Null
    Copy-Item -LiteralPath $cudaLlamaPackage -Destination (Join-Path $dlcInternal "llama_cpp") -Recurse -Force
    if ($cudaLlamaDistInfo) {
        Copy-Item -LiteralPath $cudaLlamaDistInfo.FullName -Destination (Join-Path $dlcInternal $cudaLlamaDistInfo.Name) -Recurse -Force
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

    $dlcReadme | Set-Content -LiteralPath (Join-Path $gpuDlcDir "README-GGUF-CUDA-DLC.txt") -Encoding UTF8
}

Write-Host "== TV Captioner portable build ==" -ForegroundColor Cyan
Write-Host "Project root: $PSScriptRoot"
Write-Host ""

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "[1/5] Creating runtime environment..." -ForegroundColor Yellow
    .\setup.ps1
}
else {
    Write-Host "[1/5] Ensuring runtime dependencies..." -ForegroundColor Yellow
    Invoke-Pip @("install", "--isolated", "-r", ".\requirements.txt")
}

Write-Host "[2/5] Installing build dependencies..." -ForegroundColor Yellow
Invoke-Pip @("install", "--isolated", "-r", ".\packaging\requirements-build.txt")

Remove-IfExists $distDir
Remove-IfExists $staleOnlineDistDir
Remove-IfExists $workDir
Remove-IfExists $specDir
New-GgufCudaDlc

Write-Host "Ensuring base package uses CPU GGUF runtime..." -ForegroundColor Yellow
Invoke-Pip @("install", "--isolated", "--force-reinstall", "--no-deps", "--no-cache-dir", $llamaCpuWheel)

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
Write-Host "Release dist\TVCaptionerBackend for regular CPU/default use."
Write-Host "Release dist\TVCaptionerBackend-GGUF-CUDA-DLC separately for users who want GGUF GPU translation."
