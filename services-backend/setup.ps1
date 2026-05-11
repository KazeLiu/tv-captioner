$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location $PSScriptRoot

# Some Windows Python installs set PYTHONPATH globally. Clear it so this project
# uses its own virtual environment instead of mixing system packages.
$env:PYTHONPATH = ""
$env:PYTHONHOME = ""
$env:PYTHONNOUSERSITE = "1"
$env:PIP_CONFIG_FILE = "NUL"

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --isolated --upgrade pip
.\.venv\Scripts\python.exe -m pip install --isolated -r requirements.txt

Write-Host ""
Write-Host "后端依赖安装完成。下一步运行：" -ForegroundColor Green
Write-Host ".\start.ps1"
