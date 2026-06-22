@echo off
cd /d "%~dp0"
echo SprytnySounder — Aktualizator
echo ===============================
echo.
echo Pobieram najnowsza wersje z GitHub...
echo.
powershell -ExecutionPolicy Bypass -File "aktualizuj.ps1"
pause
