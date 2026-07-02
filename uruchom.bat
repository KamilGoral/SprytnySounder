@echo off
setlocal
cd /d "%~dp0"
rem PYTHONUTF8=1 -> polskie znaki i emoji nie wysypuja konsoli (cp1250)
set PYTHONUTF8=1

rem Znajdz Pythona 3 - tuz po instalacji sesja moze nie miec go w PATH,
rem a na Win7 instalowany jest Python 3.8 (per-user) zamiast 3.12
set "PYTHON="
python -c "import sys; raise SystemExit(0 if sys.version_info[0]==3 else 1)" >nul 2>&1 && set "PYTHON=python"
if not defined PYTHON for %%P in ("%LocalAppData%\Programs\Python\Python312" "%LocalAppData%\Programs\Python\Python38" "%LocalAppData%\Programs\Python\Python38-32" "%ProgramFiles%\Python312" "%ProgramFiles%\Python38") do if not defined PYTHON if exist "%%~P\python.exe" set "PYTHON=%%~P\python.exe"
if not defined PYTHON set "PYTHON=python"

"%PYTHON%" update.py --no-restart >nul 2>&1
"%PYTHON%" app.py
pause
