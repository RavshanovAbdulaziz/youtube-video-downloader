@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0backend"

echo ============================================
echo   YouTube Downloader - O'rnatish
echo ============================================
echo.

py -3.14 --version >nul 2>&1
if errorlevel 1 (
    echo XATO: Python 3.14 topilmadi.
    echo Avval Python 3.14 o'rnating: https://python.org
    pause
    exit /b 1
)

ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo OGOHLANTIRISH: ffmpeg PATH'da topilmadi.
    echo Video/audio birlashtirish va mp3'ga o'girish ishlamaydi.
    echo https://ffmpeg.org dan yuklab, PATH'ga qo'shing.
    echo.
)

echo [1/3] Asosiy kutubxonalar o'rnatilmoqda (fastapi, yt-dlp)...
echo Bu bir necha daqiqa vaqt olishi mumkin.
echo.
py -3.14 -m pip install -r requirements.txt
if errorlevel 1 (
    echo XATO: kutubxonalarni o'rnatishda muammo yuz berdi.
    pause
    exit /b 1
)

echo.
echo [2/3] Tray (soat yonidagi ikonka) uchun kutubxonalar...
echo.
py -3.14 -m pip install -r "%~dp0launcher\requirements.txt"
if errorlevel 1 (
    echo XATO: tray kutubxonalarini o'rnatishda muammo yuz berdi.
    echo start.bat ishlamasligi mumkin - start_dev.bat esa ishlayveradi.
    pause
)

echo.
echo ============================================
echo   [3/3] Ixtiyoriy: "Ovozni ajratish" (AI) funksiyasi
echo ============================================
echo Bu funksiya audioni odam gapi va fon tovushlariga ajratadi.
echo PyTorch + Demucs + audio-separator kerak (~3-5GB yuklab olish).
echo.
set /p AI_CHOICE="O'rnatilsinmi? (y/n): "
if /i "%AI_CHOICE%"=="y" (
    call "%~dp0install_ai.bat"
) else (
    echo O'tkazib yuborildi. Keyinroq kerak bo'lsa install_ai.bat ni ishga tushiring.
)

echo.
echo ============================================
echo   O'rnatish tugadi!
echo ============================================
echo.
echo   start.bat      - kundalik ishlatish uchun.
echo                    Soat yonida (tray) ikonka paydo bo'ladi, o'ng tugma
echo                    bilan bosib istalgan payt to'xtatish mumkin.
echo.
echo   start_dev.bat  - kod ustida ishlash uchun (konsol + auto-reload).
echo.
pause
