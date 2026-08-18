@echo off
chcp 65001 >nul
setlocal

REM Ish stoliga "YouTube Downloader" yorlig'ini yaratadi, shunda dasturni
REM ishga tushirish uchun har safar loyiha papkasini ochish shart emas.
REM Yorliq start.bat'ni chaqiradi (tray rejimi, konsolsiz).

echo ============================================
echo   Ish stoliga yorliq yaratish
echo ============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"

echo.
echo Endi ish stolidagi "YouTube Downloader" yorlig'ini bosib
echo dasturni ishga tushirishingiz mumkin.
echo.
pause
