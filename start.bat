@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0backend"

py -3.14 -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo Kerakli kutubxonalar topilmadi yoki Python 3.14 o'rnatilmagan.
    echo Avval setup.bat faylini ishga tushiring.
    echo.
    pause
    exit /b 1
)

echo ============================================
echo   YouTube Downloader ishga tushirilmoqda...
echo ============================================
echo.
echo Brauzer avtomatik ochiladi. To'xtatish uchun stop.bat'ni ishga tushiring
echo (yoki shunchaki bu oynani yoping).
echo.

start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"

py -3.14 -m uvicorn main:app --host 127.0.0.1 --port 8000

echo.
echo Server to'xtatildi.
pause
