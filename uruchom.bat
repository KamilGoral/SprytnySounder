@echo off
cd /d "%~dp0"
rem PYTHONUTF8=1 -> polskie znaki i emoji nie wysypuja konsoli (cp1250)
set PYTHONUTF8=1
powershell -ExecutionPolicy Bypass -Command "& { try { python update.py --no-restart | Out-Null } catch {} }"
python app.py
pause
