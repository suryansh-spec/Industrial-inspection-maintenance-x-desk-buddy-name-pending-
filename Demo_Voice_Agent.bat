@echo off
title Omnipect Voice Agent Demonstration
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

set "PYTHON_EXE="
if exist "%ROOT_DIR%.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%ROOT_DIR%deskbuddy_backend\.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT_DIR%deskbuddy_backend\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\.conda\envs\inspection\python.exe" set "PYTHON_EXE=%USERPROFILE%\.conda\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\envs\inspection\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\envs\inspection\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\miniconda3\envs\inspection\python.exe" set "PYTHON_EXE=C:\ProgramData\miniconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\anaconda3\envs\inspection\python.exe" set "PYTHON_EXE=C:\ProgramData\anaconda3\envs\inspection\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

"%PYTHON_EXE%" demo_voice_agent.py
pause
