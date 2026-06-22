@echo off
cd /d "%~dp0"
echo SprytnySounder — Aktualizator v1.1
echo ===============================
echo.
echo Pobieram najnowsza wersje z GitHub...
echo.
powershell -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; irm https://raw.githubusercontent.com/KamilGoral/SprytnySounder/main/aktualizuj.ps1 | iex"
pause
