@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TV Captioner Portable Build
echo ==================================================
echo TV Captioner portable build
echo Project: %~dp0
echo ==================================================
echo.
echo The PowerShell window will stay open after the build finishes.
echo.
powershell -NoExit -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-portable.ps1"
