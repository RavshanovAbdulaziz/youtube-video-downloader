@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0backend"

REM DEVELOPMENT rejimi — start.bat'dan farqi:
REM   * konsol oynasi ochiq qoladi (loglar, xatolar darhol ko'rinadi)
REM   * `--reload`: .py fayl saqlanganda server O'ZI qayta yuklanadi, ya'ni
REM     har o'zgarishdan keyin qo'lda to'xtatib-yoqish shart emas
REM   * tray ikonkasi YO'Q (to'xtatish uchun shu oynada Ctrl+C)
REM
REM Kundalik ishlatish uchun start.bat'ni oching (tray ikonka bilan).

py -3.14 -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo Kerakli kutubxonalar topilmadi yoki Python 3.14 o'rnatilmagan.
    echo Avval setup.bat faylini ishga tushiring.
    echo.
    pause
    exit /b 1
)

echo ============================================
echo   YouTube Downloader - DEVELOPMENT rejimi
echo ============================================
echo.
echo   Manzil:     http://127.0.0.1:8000
echo   Auto-reload: yoqilgan (.py o'zgarsa qayta yuklanadi)
echo   To'xtatish:  shu oynada Ctrl+C
echo.
echo ============================================
echo.

start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"

py -3.14 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

echo.
echo Server to'xtatildi.
pause
