@echo off
title Omnipect Voice Agent Demonstration
cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\Suryansh3584\.conda\envs\inspection\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" demo_voice_agent.py
pause
