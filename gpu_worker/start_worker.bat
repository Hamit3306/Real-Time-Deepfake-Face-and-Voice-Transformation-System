@echo off
echo ============================================
echo  DeepFake GPU Worker - Baslatiliyor
echo ============================================
echo.

REM gpu_worker dizininde calisiyoruz
cd /d "%~dp0"

REM Sanal ortami aktif et (lokal venv)
call venv\Scripts\activate.bat

echo [1/2] gpu_worker ortam kontrol ediliyor...
python -c "import torch; print('CUDA:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"

echo.
echo [2/2] GPU Worker baslatiyor (port 8001)...
uvicorn api:app --host 0.0.0.0 --port 8001 --reload

pause
