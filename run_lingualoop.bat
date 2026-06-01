@echo off
set QT_MEDIA_BACKEND=ffmpeg
set PYTHONPATH=%~dp0src;%PYTHONPATH%
.venv\Scripts\python.exe -m immersion_app.app
pause
