@echo off
cd /d "%~dp0"
echo SprytnySounder v1.1.0 - Autostart
python update.py --status
python app.py
pause