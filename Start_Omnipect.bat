@echo off
title Omnipect Backend
cd /d "%~dp0deskbuddy_backend"

set "PYTHON_EXE=C:\Users\Suryansh3584\.conda\envs\inspection\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo Starting Omnipect Backend...
start "" cmd /c "timeout /t 4 /nobreak >nul & start http://127.0.0.1:8080/"
"%PYTHON_EXE%" -m app.main
pause
