@echo off
chcp 65001 >nul
echo ============================================
echo   YouTube Downloader serverini to'xtatish
echo ============================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
echo.
pause
