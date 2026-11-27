@echo off
title Omnipect Cloud PC Agent
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

set "PYTHON_EXE="
if exist "%PROJECT_DIR%.venv\Scripts\python.exe" set "PYTHON_EXE=%PROJECT_DIR%.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%PROJECT_DIR%deskbuddy_backend\.venv\Scripts\python.exe" set "PYTHON_EXE=%PROJECT_DIR%deskbuddy_backend\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\.conda\envs\inspection\python.exe" set "PYTHON_EXE=%USERPROFILE%\.conda\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\envs\inspection\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\envs\inspection\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\miniconda3\envs\inspection\python.exe" set "PYTHON_EXE=C:\ProgramData\miniconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\anaconda3\envs\inspection\python.exe" set "PYTHON_EXE=C:\ProgramData\anaconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

set "TARGET_URL=%~1"
if "%TARGET_URL%"=="" set "TARGET_URL=http://127.0.0.1:8080"

echo ========================================================
echo  Starting Omnipect PC Agent
echo  Project: %PROJECT_DIR%
echo  Backend URL: %TARGET_URL%
echo ========================================================

"%PYTHON_EXE%" "%PROJECT_DIR%pc_agent.py" --url "%TARGET_URL%"
pause
