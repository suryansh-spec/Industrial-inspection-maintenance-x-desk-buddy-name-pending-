@echo off
title DeskBuddy Cloud PC Agent

:: Find project directory (handles running from project root or if copied to Desktop)
set "PROJECT_DIR=%~dp0"
if not exist "%PROJECT_DIR%pc_agent.py" (
    set "PROJECT_DIR=e:\VSCODE\multimodel_inspection_desk_buddy\"
)

cd /d "%PROJECT_DIR%"

set "PYTHON_EXE=C:\Users\Suryansh3584\.conda\envs\inspection\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo ========================================================
echo  Starting DeskBuddy Cloud PC Agent
echo  Project: %PROJECT_DIR%
echo  Pushing PC activity to Railway cloud backend...
echo ========================================================

"%PYTHON_EXE%" "%PROJECT_DIR%pc_agent.py" --url https://industrial-inspection-maintenance-x-desk-buddy-n-production.up.railway.app
pause
