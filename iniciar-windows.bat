@echo off
cd /d "%~dp0"
where ffmpeg >nul 2>nul || (echo Falta FFmpeg. Instalalo con:  winget install ffmpeg & pause & exit /b)
python servidor.py || py servidor.py
pause
