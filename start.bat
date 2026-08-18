@echo off
chcp 65001 >nul
setlocal

REM Dasturni TRAY rejimida ishga tushiradi: konsol oynasi ochilmaydi, o'rniga
REM soat yonidagi (bildirishnomalar sohasi) kichik ikonka paydo bo'ladi.
REM O'sha ikonkani sichqonchaning O'NG tugmasi bilan bosib: ochish, to'xtatish,
REM qayta ishga tushirish, yuklamalar/loglar papkasi va chiqish mumkin.
REM
REM Kod ustida ishlayotgan bo'lsangiz start_dev.bat'ni ishlating — u konsolni
REM ochiq qoldiradi va fayl o'zgarganda serverni avtomatik qayta yuklaydi.

py -3.14 -c "import fastapi, pystray, PIL" >nul 2>&1
if errorlevel 1 (
    echo Kerakli kutubxonalar topilmadi yoki Python 3.14 o'rnatilmagan.
    echo Avval setup.bat faylini ishga tushiring.
    echo.
    pause
    exit /b 1
)

REM pythonw.exe — konsolsiz Python. `start ""` bilan chaqiramiz, shunda bu
REM oyna darhol yopiladi va dastur fonda, tray'da ishlashda davom etadi.
for /f "usebackq delims=" %%P in (`py -3.14 -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"`) do set "PYW=%%P"

if not exist "%PYW%" (
    echo XATO: pythonw.exe topilmadi: %PYW%
    pause
    exit /b 1
)

start "" "%PYW%" "%~dp0launcher\tray_app.py"
exit /b 0
