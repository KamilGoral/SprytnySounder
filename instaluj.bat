@echo off
cd /d "%~dp0"
title SprytnySounder - Instalator v1.0
cls

echo ========================================
echo    SprytnySounder - Instalator v1.0
echo    Nowa instalacja na czystym sklepie
echo ========================================
echo.
echo Ten skrypt:
echo 1. Zainstaluje Pythona (jesli nie ma)
echo 2. Pobierze pliki z GitHub
echo 3. Zainstaluje biblioteki
echo 4. Skonfiguruje IP i autostart
echo 5. Uruchomi aplikacje
echo.

set /p GOTOWY="Gotowy? (Enter = kontynuuj, Ctrl+C = anuluj)"
echo.

:: === Krok 1: Python ===
echo [1/6] Sprawdzanie Pythona...
python --version >nul 2>&1
if %errorlevel% equ 0 (
    python --version
    echo   OK - Python jest
) else (
    echo   Python nie znaleziony. Pobieram Python 3.12...
    curl -sL -o "%TEMP%\python-installer.exe" https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
    if %errorlevel% neq 0 (
        echo   BLAD - nie mozna pobrac Pythona. Sprawdz polaczenie z internetem.
        pause
        exit /b 1
    )
    echo   Instalowanie Pythona (to moze chwile potrwac)...
    start /wait "" "%TEMP%\python-installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_freethreaded=0
    echo   OK - Python zainstalowany
)

:: === Krok 2: Pobierz pliki z GitHub ===
echo [2/6] Pobieranie plikow z GitHub...
set "INSTALL_DIR=%CD%"
set "REPO_URL=https://github.com/KamilGoral/SprytnySounder"
set "ZIP_URL=%REPO_URL%/archive/refs/heads/main.zip"
set "TEMP_ZIP=%TEMP%\sprytnysounder.zip"
set "TEMP_DIR=%TEMP%\sprytnysounder_install"

powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = 3072 -bor 768 -bor 192; Invoke-WebRequest -Uri '%ZIP_URL%' -OutFile '%TEMP_ZIP%' -UseBasicParsing"
if %errorlevel% neq 0 (
    echo   BLAD - nie mozna pobrac plikow. Sprawdz polaczenie.
    pause
    exit /b 1
)
echo   OK - ZIP pobrany

:: === Krok 3: Wypakuj ===
echo [3/6] Wypakowywanie...
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"

powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = 3072 -bor 768 -bor 192; try { Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath '%TEMP_DIR%' -Force } catch { Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::ExtractToDirectory('%TEMP_ZIP%', '%TEMP_DIR%') }"
if %errorlevel% neq 0 (
    echo   BLAD wypakowywania
    pause
    exit /b 1
)

:: Znajdz glowny folder w ZIP
for /d %%i in ("%TEMP_DIR%\*") do set "SOURCE=%%i"
echo   OK - ZIP rozpakowany

:: Kopiuj pliki
echo [4/6] Kopiowanie plikow...
xcopy /E /Y /Q "%SOURCE%\." "%INSTALL_DIR%\" >nul
echo   OK - pliki skopiowane do %INSTALL_DIR%

:: === Krok 5: Instalacja bibliotek ===
echo [5/6] Instalacja bibliotek Python...
pip install flask flask-cors pygame psutil pycaw comtypes pywin32 flask-limiter requests -q
if %errorlevel% equ 0 (
    echo   OK - biblioteki zainstalowane
) else (
    echo   UWAGA - niektore biblioteki moga sie nie zainstalowac. Sprobuj recznie:
    echo   pip install flask flask-cors pygame psutil pycaw comtypes pywin32 flask-limiter requests
)

:: === Krok 6: Konfiguracja IP i autostart ===
echo [6/6] Konfiguracja...

:: Auto-detekcja IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set "IP=%%a"
    goto :IP_DONE
)
:IP_DONE
set "IP=%IP: =%"
if "%IP%"=="" set "IP=127.0.0.1"
echo   Wykryte IP: %IP%

:: Utworz config.json z wykrytym IP
powershell -NoProfile -Command "
$cfg = @{
    host = '%IP%'
    port = 8989
    sound_folder = 'static/sounds'
    log_file = 'log.txt'
    stats_file = 'statystyka.txt'
    template_folder = 'templates'
    static_folder = 'static'
    version = '1.1.0'
    sunday_inverted = $false
    update_enabled = $true
    update_url = 'https://github.com/KamilGoral/SprytnySounder'
    update_check_interval_hours = 24
    store_name = 'Nowy sklep'
}
$cfg | ConvertTo-Json | Set-Content '%INSTALL_DIR%\config.json' -Encoding UTF8
"

echo   OK - config.json utworzony z IP %IP%:8989

:: Zapytaj o nazwe sklepu
set /p NAZWA="Podaj nazwe sklepu (np. Lidl Krotka): "
if not "%NAZWA%"=="" (
    powershell -NoProfile -Command "(Get-Content '%INSTALL_DIR%\config.json' -Raw | ConvertFrom-Json) | ForEach-Object { \$_.store_name = '%NAZWA%'; \$_- } | ConvertTo-Json | Set-Content '%INSTALL_DIR%\config.json' -Encoding UTF8"
)

:: Zapytaj o odwrocone niedziele
set /p NIEDZIELE="Czy to sklep Krotka 2a (odwrocone niedziele)? (t/n): "
if /i "%NIEDZIELE%"=="t" (
    powershell -NoProfile -Command "(Get-Content '%INSTALL_DIR%\config.json' -Raw | ConvertFrom-Json) | ForEach-Object { \$_.sunday_inverted = \$true; \$_- } | ConvertTo-Json | Set-Content '%INSTALL_DIR%\config.json' -Encoding UTF8"
    echo   OK - odwrocone niedziele wlaczone
)

:: Dodaj autostart w Windows
echo   Dodawanie autostartu...
powershell -NoProfile -Command "
try {
    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut([Environment]::GetFolderPath('Startup') + '\SprytnySounder.lnk')
    $shortcut.TargetPath = 'cmd.exe'
    $shortcut.Arguments = '/c cd /d \"%INSTALL_DIR%\" && python app.py'
    $shortcut.WorkingDirectory = '%INSTALL_DIR%'
    $shortcut.WindowStyle = 7
    $shortcut.Save()
    Write-Host '  OK - autostart dodany'
} catch {
    Write-Host '  UWAGA - nie mozna dodac autostartu: ' + $_.Exception.Message -ForegroundColor Yellow
}
"

:: Sprzatanie
del "%TEMP_ZIP%" 2>nul
rmdir /s /q "%TEMP_DIR%" 2>nul

:: Uruchom aplikacje
echo.
echo ========================================
echo    Instalacja zakonczona!
echo    Panel: http://%IP%:8989
echo ========================================
echo.
echo Uruchamiam aplikacje...
start "" python "%INSTALL_DIR%\app.py"
echo.
echo Aplikacja wystartowala. Zamknij to okno.
echo Przy kazdym resecie komputera uruchomi sie automatycznie.
echo.
pause
