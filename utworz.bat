@echo off
setlocal
cd /d "%~dp0"
title SprytnySounder - Instalator v1.3
cls

echo ========================================
echo    SprytnySounder - Instalator v1.3
echo    Nowa instalacja na czystym sklepie
echo    (Windows 7 / 8 / 10 / 11)
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

set "INSTALL_DIR=%CD%"

:: === Wykryj Windows i architekture ===
:: Win7/8 (wersja < 10): ostatni Python dzialajacy na tych systemach to 3.8.10
set "WINMAJ=10"
for /f "tokens=4 delims=.[] " %%i in ('ver') do set "WINMAJ=%%i"
set "ARCH=amd64"
if "%PROCESSOR_ARCHITECTURE%"=="x86" if not defined PROCESSOR_ARCHITEW6432 set "ARCH=win32"

if %WINMAJ% LSS 10 (
    set "PYVER=3.8.10"
) else (
    set "PYVER=3.12.10"
)
if "%ARCH%"=="win32" (
    set "PYSUFFIX="
) else (
    set "PYSUFFIX=-amd64"
)
echo Wykryto: Windows %WINMAJ% (%ARCH%) - Python %PYVER%
echo.

:: === Krok 1: Python ===
echo [1/6] Sprawdzanie Pythona...
call :FIND_PYTHON
if defined PYTHON goto :PYTHON_OK

echo   Python nie znaleziony. Pobieram Python %PYVER%...
call :DOWNLOAD "https://www.python.org/ftp/python/%PYVER%/python-%PYVER%%PYSUFFIX%.exe" "%TEMP%\python-installer.exe"
if errorlevel 1 (
    echo   BLAD - nie mozna pobrac Pythona. Sprawdz polaczenie z internetem.
    echo   Na Windows 7: upewnij sie, ze jest IE11 i wlaczone TLS 1.2
    echo   w Opcjach internetowych - Zaawansowane.
    pause
    exit /b 1
)
echo   Instalowanie Pythona (to moze chwile potrwac)...
:: Instalacja per-user (InstallAllUsers=0) - nie wymaga uprawnien administratora
start /wait "" "%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1
call :FIND_PYTHON
if not defined PYTHON (
    echo   BLAD - Python sie nie zainstalowal. Uruchom recznie: %TEMP%\python-installer.exe
    echo   Na Windows 7 wymagany jest Service Pack 1.
    pause
    exit /b 1
)
:PYTHON_OK
"%PYTHON%" --version
echo   OK - Python: %PYTHON%

:: === Krok 2: Pobierz pliki z GitHub ===
:: Pobiera Python (ma wlasny OpenSSL z TLS 1.2 - dziala tez na Win7),
:: fallback: narzedzia systemowe
echo [2/6] Pobieranie plikow z GitHub...
set "REPO_URL=https://github.com/KamilGoral/SprytnySounder"
set "ZIP_URL=%REPO_URL%/archive/refs/heads/main.zip"
set "TEMP_ZIP=%TEMP%\sprytnysounder.zip"
set "TEMP_DIR=%TEMP%\sprytnysounder_install"

"%PYTHON%" -c "import urllib.request; urllib.request.urlretrieve('%ZIP_URL%', r'%TEMP_ZIP%')" >nul 2>&1
if errorlevel 1 call :DOWNLOAD "%ZIP_URL%" "%TEMP_ZIP%"
if errorlevel 1 (
    echo   BLAD - nie mozna pobrac plikow. Sprawdz polaczenie.
    pause
    exit /b 1
)
echo   OK - ZIP pobrany

:: === Krok 3: Wypakuj (przez Pythona - dziala tak samo na kazdym Windows) ===
echo [3/6] Wypakowywanie...
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
"%PYTHON%" -m zipfile -e "%TEMP_ZIP%" "%TEMP_DIR%"
if errorlevel 1 (
    echo   BLAD wypakowywania
    pause
    exit /b 1
)

:: Znajdz glowny folder w ZIP
set "SOURCE="
for /d %%i in ("%TEMP_DIR%\*") do set "SOURCE=%%i"
if not defined SOURCE set "SOURCE=%TEMP_DIR%"
if not exist "%SOURCE%\app.py" (
    echo   BLAD - archiwum niekompletne - brak app.py
    pause
    exit /b 1
)
echo   OK - ZIP rozpakowany

:: Kopiuj pliki. UWAGA: /XF utworz.bat - ten plik wlasnie sie wykonuje,
:: a cmd czyta .bat z dysku na biezaco; nadpisanie go w trakcie psuje skrypt.
echo [4/6] Kopiowanie plikow...
robocopy "%SOURCE%" "%INSTALL_DIR%" /E /XF utworz.bat /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo   BLAD kopiowania plikow
    pause
    exit /b 1
)
echo   OK - pliki skopiowane do %INSTALL_DIR%

:: === Krok 5: Instalacja bibliotek ===
echo [5/6] Instalacja bibliotek Python...
"%PYTHON%" -m pip install -q --upgrade pip >nul 2>&1
"%PYTHON%" -m pip install -q -r "%INSTALL_DIR%\requirements.txt"
if errorlevel 1 (
    echo   UWAGA - niektore biblioteki moga sie nie zainstalowac. Sprobuj recznie:
    echo   "%PYTHON%" -m pip install -r requirements.txt
) else (
    echo   OK - biblioteki zainstalowane
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

:: Utworz config.json (LOKALNY, per maszyna) - tylko host i port.
:: Reszta (store_name, sunday_inverted, update_url...) idzie z repo:
:: config.defaults.json + locations\<lokalizacja>.json
:: Zapis przez echo (ConvertTo-Json nie istnieje w PowerShell 2.0 na Win7)
(
    echo {
    echo     "host": "%IP%",
    echo     "port": 8989
    echo }
) > "%INSTALL_DIR%\config.json"
echo   OK - config.json utworzony z IP %IP%:8989

:: Zapytaj o KROTKA nazwe lokalizacji -> location.txt (per maszyna, nie w repo)
echo.
echo   Podaj KROTKA nazwe lokalizacji - male litery, bez spacji i polskich znakow.
echo   Przyklady: kilinskiego, bielska, sulkowice, krotka2a
echo   Mozna zostawic puste - app dopasuje lokalizacje po IP
echo    z pliku locations\machines.json w repo
set /p LOC="   Lokalizacja: "
if not "%LOC%"=="" (
    >"%INSTALL_DIR%\location.txt" echo %LOC%
    echo   OK - location.txt = %LOC%
    echo   WAZNE: w repo musi istniec plik  locations\%LOC%.json
    echo          ze store_name i sunday_inverted. Patrz locations\README.md
) else (
    echo   Pominieto - lokalizacja zostanie dopasowana po IP z repo
)

:: Dodaj autostart w Windows (PowerShell w JEDNEJ linii - cmd nie obsluguje
:: cudzyslowu przez kilka linii; skladnia zgodna z PowerShell 2.0)
echo   Dodawanie autostartu...
powershell -NoProfile -Command "$wsh = New-Object -ComObject WScript.Shell; $s = $wsh.CreateShortcut([Environment]::GetFolderPath('Startup') + '\SprytnySounder.lnk'); $s.TargetPath = '%INSTALL_DIR%\uruchom.bat'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.WindowStyle = 7; $s.Save()"
if errorlevel 1 (
    echo   UWAGA - nie mozna dodac autostartu. Dodaj recznie skrot do uruchom.bat
    echo   w folderze: shell:startup
) else (
    echo   OK - autostart dodany
)

:: Sprzatanie
del "%TEMP_ZIP%" 2>nul
del "%TEMP%\ss_download.vbs" 2>nul
rmdir /s /q "%TEMP_DIR%" 2>nul

:: Uruchom aplikacje
echo.
echo ========================================
echo    Instalacja zakonczona!
echo    Panel: http://%IP%:8989
echo ========================================
echo.
set PYTHONUTF8=1
echo Uruchamiam aplikacje...
start "" "%PYTHON%" app.py
echo.
echo Aplikacja wystartowala. Zamknij to okno.
echo Przy kazdym resecie komputera uruchomi sie automatycznie.
echo.
pause
exit /b 0

:: ============================================================
:: Podprogramy
:: ============================================================

:: Znajdz dzialajacego Pythona 3 (nie stub z Microsoft Store, nie Python 2)
:: i ustaw PYTHON. Po swiezej instalacji biezaca sesja cmd nie widzi
:: nowego PATH, dlatego sprawdzamy tez pelne sciezki instalacji.
:FIND_PYTHON
set "PYTHON="
python -c "import sys; raise SystemExit(0 if sys.version_info[0]==3 else 1)" >nul 2>&1 && set "PYTHON=python"
if defined PYTHON exit /b 0
for %%P in (
    "%LocalAppData%\Programs\Python\Python312"
    "%LocalAppData%\Programs\Python\Python38"
    "%LocalAppData%\Programs\Python\Python38-32"
    "%ProgramFiles%\Python312"
    "%ProgramFiles%\Python38"
) do if not defined PYTHON if exist "%%~P\python.exe" set "PYTHON=%%~P\python.exe"
exit /b 0

:: :DOWNLOAD <url> <plik>  - probuje kolejno: curl (Win10/11),
:: PowerShell WebClient, VBScript przez WinINet (Win7 z IE11 ma tam TLS 1.2)
:DOWNLOAD
set "DL_URL=%~1"
set "DL_OUT=%~2"
del "%DL_OUT%" 2>nul
where curl >nul 2>&1
if not errorlevel 1 curl -fsSL -o "%DL_OUT%" "%DL_URL%"
call :DL_CHECK && exit /b 0
del "%DL_OUT%" 2>nul
powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072 } catch {}; (New-Object Net.WebClient).DownloadFile('%DL_URL%','%DL_OUT%')" >nul 2>&1
call :DL_CHECK && exit /b 0
del "%DL_OUT%" 2>nul
set "DL_VBS=%TEMP%\ss_download.vbs"
>  "%DL_VBS%" echo Set h = CreateObject("MSXML2.XMLHTTP")
>> "%DL_VBS%" echo h.Open "GET", WScript.Arguments(0), False
>> "%DL_VBS%" echo h.Send
>> "%DL_VBS%" echo If h.Status = 200 Then
>> "%DL_VBS%" echo   Set s = CreateObject("ADODB.Stream")
>> "%DL_VBS%" echo   s.Open
>> "%DL_VBS%" echo   s.Type = 1
>> "%DL_VBS%" echo   s.Write h.responseBody
>> "%DL_VBS%" echo   s.SaveToFile WScript.Arguments(1), 2
>> "%DL_VBS%" echo   s.Close
>> "%DL_VBS%" echo End If
cscript //nologo "%DL_VBS%" "%DL_URL%" "%DL_OUT%" >nul 2>&1
call :DL_CHECK && exit /b 0
exit /b 1

:: Sprawdz czy pobrany plik istnieje i nie jest pusty/uciety
:DL_CHECK
if not exist "%DL_OUT%" exit /b 1
for %%A in ("%DL_OUT%") do if %%~zA LSS 1000 exit /b 1
exit /b 0
