@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0backend"

py -3.14 -c "import aiogram" >nul 2>&1
if errorlevel 1 (
    echo Kerakli kutubxona topilmadi: aiogram
    echo O'rnatish uchun: py -3.14 -m pip install aiogram
    pause
    exit /b 1
)

if not exist ".env" (
    echo XATO: backend\.env fayli topilmadi.
    echo Ichida BOT_TOKEN=... qatori bo'lishi kerak.
    pause
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    set "%%A=%%B"
)

if "%BOT_TOKEN%"=="" (
    echo XATO: BOT_TOKEN topilmadi ^(backend\.env ichida^).
    pause
    exit /b 1
)

echo ============================================
echo   Telegram bot ishga tushirilmoqda...
echo   ^(to'xtatish uchun bu oynani yoping^)
echo ============================================
py -3.14 bot.py

echo.
echo Bot to'xtatildi.
pause
