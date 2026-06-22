@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -Command "& { try { python update.py --no-restart | Out-Null } catch {} }"
python app.py
pause