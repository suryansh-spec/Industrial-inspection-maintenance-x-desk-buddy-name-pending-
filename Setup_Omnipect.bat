@echo off
title Omnipect - One-Click Setup (Clone Ready)
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo ============================================================
echo   Omnipect - Automated First-Time Setup
echo ============================================================

:: 1. Ensure deskbuddy_backend/.env exists
if not exist "%ROOT_DIR%deskbuddy_backend\.env" (
    echo [1/4] Creating deskbuddy_backend\.env from .env.example...
    copy /Y "%ROOT_DIR%deskbuddy_backend\.env.example" "%ROOT_DIR%deskbuddy_backend\.env" >nul
    echo       IMPORTANT: Edit deskbuddy_backend\.env and add your NVIDIA_API_KEY
) else (
    echo [1/4] deskbuddy_backend\.env already exists.
)

:: 2. Ensure firmware voice_config.h exists
if not exist "%ROOT_DIR%firmware\arduino\DeskBuddy_Companion\voice_config.h" (
    if exist "%ROOT_DIR%firmware\arduino\DeskBuddy_Companion\voice_config.example.h" (
        echo [2/4] Creating firmware voice_config.h from voice_config.example.h...
        copy /Y "%ROOT_DIR%firmware\arduino\DeskBuddy_Companion\voice_config.example.h" "%ROOT_DIR%firmware\arduino\DeskBuddy_Companion\voice_config.h" >nul
    )
) else (
    echo [2/4] firmware voice_config.h already exists.
)

:: 3. Discover or create Python environment
set "PYTHON_EXE="
if exist "%ROOT_DIR%.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\.conda\envs\inspection\python.exe" set "PYTHON_EXE=%USERPROFILE%\.conda\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\envs\inspection\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\envs\inspection\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\miniconda3\envs\inspection\python.exe" set "PYTHON_EXE=C:\ProgramData\miniconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\anaconda3\envs\inspection\python.exe" set "PYTHON_EXE=C:\ProgramData\anaconda3\envs\inspection\python.exe"

if not defined PYTHON_EXE (
    echo [3/4] Creating local virtual environment (.venv)...
    python -m venv "%ROOT_DIR%.venv"
    if exist "%ROOT_DIR%.venv\Scripts\python.exe" (
        set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
    ) else (
        set "PYTHON_EXE=python"
    )
) else (
    echo [3/4] Found existing Python environment: %PYTHON_EXE%
)

:: 4. Install dependencies
echo [4/4] Installing Omnipect backend and voice agent dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r "%ROOT_DIR%deskbuddy_backend\requirements.txt"

echo.
echo ============================================================
echo   Setup Complete!
echo   1. Add your NVIDIA_API_KEY in deskbuddy_backend\.env
echo   2. Double-click Start_Omnipect.bat to launch the server!
echo ============================================================
pause
