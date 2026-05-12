@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 pause & exit /b %errorlevel%
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
pause
