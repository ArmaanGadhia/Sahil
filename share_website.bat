@echo off
title Sahil Communication & Mobile Repairs - Live Server & Public Link
echo ========================================================
echo Starting Sahil Communication Web Server & Public Link...
echo ========================================================
start /b python app.py
timeout /t 3 >nul
echo.
echo Launching public secure tunnel...
cloudflared.exe tunnel --url http://127.0.0.1:5000
pause
