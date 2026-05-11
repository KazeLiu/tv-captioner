$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location $PSScriptRoot

$env:PYTHONPATH = ""
$env:PYTHONHOME = ""
$env:PYTHONNOUSERSITE = "1"
$env:PIP_CONFIG_FILE = "NUL"

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "还没有创建虚拟环境，请先运行 .\setup.ps1" -ForegroundColor Yellow
    exit 1
}

$hostAddress = if ($env:TV_CAPTIONER_HOST) { $env:TV_CAPTIONER_HOST } else { "0.0.0.0" }
$port = if ($env:TV_CAPTIONER_PORT) { [int]$env:TV_CAPTIONER_PORT } else { 8765 }
$url = "http://127.0.0.1:$port"
$lanAddress = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.InterfaceAlias -notmatch "vEthernet|Tailscale|Loopback" -and
        ($_.IPAddress -like "192.168.*" -or $_.IPAddress -like "10.*" -or $_.IPAddress -match "^172\.(1[6-9]|2[0-9]|3[0-1])\.")
    } |
    Select-Object -First 1 -ExpandProperty IPAddress
$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "后端已经在运行，正在打开网页控制台：" -ForegroundColor Green
    Write-Host $url
    if ($lanAddress) {
        Write-Host "手机/模拟器可尝试访问：http://$lanAddress`:$port"
    }
    Start-Process $url
    exit 0
}

Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile -Command `"Start-Sleep -Seconds 2; Start-Process '$url'`""

Write-Host "本机网页控制台：$url" -ForegroundColor Green
if ($lanAddress) {
    Write-Host "手机/模拟器访问地址：http://$lanAddress`:$port" -ForegroundColor Green
}
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host $hostAddress --port $port
