@echo off
set PYTHONPATH=%~dp0src;%PYTHONPATH%
.venv\Scripts\python.exe -m immersion_app.app
pause
