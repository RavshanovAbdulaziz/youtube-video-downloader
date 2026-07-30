@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0backend"

echo ============================================
echo   "Ovozni ajratish" (AI) - o'rnatish
echo ============================================
echo.

set /p GPU_CHOICE="NVIDIA GPU (CUDA) bormi? (y/n): "
echo.

if /i "%GPU_CHOICE%"=="y" (
    echo [1/4] PyTorch CUDA/GPU versiyasi o'rnatilmoqda...
    py -3.14 -m pip install --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
) else (
    echo [1/4] PyTorch CPU versiyasi o'rnatilmoqda...
    py -3.14 -m pip install torch torchvision torchaudio
)
if errorlevel 1 goto :fail

echo.
echo [2/4] Demucs o'rnatilmoqda...
py -3.14 -m pip install demucs
if errorlevel 1 goto :fail

echo.
echo [3/4] audio-separator o'rnatilmoqda (Windows uchun maxsus usul bilan,
echo       chunki "diffq-fixed" bog'liqligi yangi Python versiyalarida
echo       qurilmaydi va uni chetlab o'tamiz)...
if /i "%GPU_CHOICE%"=="y" (
    py -3.14 -m pip install audio-separator[gpu] --no-deps
) else (
    py -3.14 -m pip install audio-separator --no-deps
)
py -3.14 -m pip install audioop-lts beartype einops julius librosa ml_collections numpy onnx-weekly onnx2torch-py313 onnxruntime-gpu pydub pyyaml requests resampy rotary-embedding-torch samplerate scipy six soundfile tqdm
if errorlevel 1 goto :fail

echo.
echo [4/4] Muvofiqlik tuzatishlari qo'llanilmoqda...
py -3.14 -m pip install --upgrade beartype
py -3.14 -m pip install "numpy<2.5"
if errorlevel 1 goto :fail

echo.
echo ============================================
echo   "Ovozni ajratish" muvaffaqiyatli o'rnatildi!
echo ============================================
exit /b 0

:fail
echo.
echo XATO: o'rnatish jarayonida muammo yuz berdi. Yuqoridagi xabarlarni tekshiring.
exit /b 1
