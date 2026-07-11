@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0backend"

echo ============================================
echo   YouTube Downloader - O'rnatish
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo XATO: Python topilmadi.
    echo Avval Python 3.10+ o'rnating: https://python.org
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

echo [1/2] Asosiy kutubxonalar o'rnatilmoqda (fastapi, yt-dlp, demucs)...
echo Bu bir necha daqiqa vaqt olishi mumkin.
echo.
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo XATO: kutubxonalarni o'rnatishda muammo yuz berdi.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Ixtiyoriy: "Ovozni ajratish" (AI) funksiyasi
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
echo Ishga tushirish uchun start.bat faylini oching.
pause
