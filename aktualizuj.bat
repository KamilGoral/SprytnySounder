@echo off
cd /d "%~dp0"
echo SprytnySounder - Aktualizator v1.1
echo ===============================
echo.
echo Pobieram najnowsza wersje z GitHub...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = 3072 -bor 768 -bor 192; try { Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/KamilGoral/SprytnySounder/main/aktualizuj.ps1' -OutFile 'aktualizuj.ps1' -UseBasicParsing; & '.\aktualizuj.ps1' } catch { Write-Host ''; Write-Host ('BLAD: ' + $_.Exception.Message) -ForegroundColor Red }"
pause
