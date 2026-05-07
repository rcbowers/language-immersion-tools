@echo off
set PYTHONPATH=%~dp0src;%PYTHONPATH%
.venv\Scripts\pythonw.exe -m immersion_app.app
