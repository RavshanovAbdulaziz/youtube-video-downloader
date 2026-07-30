@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   YouTube Downloader — .exe qurish
echo ============================================
echo.

python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo PyInstaller topilmadi. O'rnatilmoqda...
    python -m pip install pyinstaller
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\build_exe.ps1"
if errorlevel 1 (
    echo.
    echo Qurishda xatolik yuz berdi.
    pause
    exit /b 1
)

echo.
pause
