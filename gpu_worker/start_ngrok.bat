@echo off
echo ============================================
echo  Ngrok Tunnel - GPU Worker (port 8001)
echo ============================================
echo.
echo Ngrok baslatiliyor...
echo Acilan URL'yi kopyalayip AWS env dosyasindaki GPU_WORKER_URL'yi guncelle!
echo.
ngrok http 8001
pause
