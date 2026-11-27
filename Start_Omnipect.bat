@echo off
title Omnipect Backend
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%deskbuddy_backend"

:: Ensure .env exists on fresh clones
if not exist ".env" (
    if exist ".env.example" (
        echo [Setup] Creating default .env from .env.example...
        copy /Y ".env.example" ".env" >nul
    )
)

:: Portable Python environment discovery (works on any laptop)
set "PYTHON_EXE="
if exist "%ROOT_DIR%.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%ROOT_DIR%deskbuddy_backend\.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT_DIR%deskbuddy_backend\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\.conda\envs\inspection\python.exe" set "PYTHON_EXE=%USERPROFILE%\.conda\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\envs\inspection\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\envs\inspection\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\miniconda3\envs\inspection\python.exe" set "PYTHON_EXE=C:\ProgramData\miniconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\anaconda3\envs\inspection\python.exe" set "PYTHON_EXE=C:\ProgramData\anaconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

echo Starting Omnipect Backend using: %PYTHON_EXE%
start "" cmd /c "timeout /t 4 /nobreak >nul & start http://127.0.0.1:8080/"
"%PYTHON_EXE%" -m app.main
pause
