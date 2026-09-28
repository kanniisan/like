@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag an audio folder onto this file.
  pause
  exit /b 1
)
echo Watching %~1 (Ctrl+C to stop)
python auto.py "%~1" --watch
