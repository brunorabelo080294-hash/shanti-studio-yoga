@echo off
title Yoga Studio - Assistente WhatsApp IA
cd /d "%~dp0"
echo ========================================================
echo Iniciando o Yoga Studio App com Assistente IA...
echo ========================================================
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run.py
    goto end
)

if exist "C:\Users\Bruno\.gemini\antigravity\scratch\yoga-studio-app\.venv\Scripts\python.exe" (
    "C:\Users\Bruno\.gemini\antigravity\scratch\yoga-studio-app\.venv\Scripts\python.exe" run.py
    goto end
)

python run.py

:end
pause
