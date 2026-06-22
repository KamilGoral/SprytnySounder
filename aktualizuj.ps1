<#
.SYNOPSIS
    SprytnySounder — Aktualizator dla sklepów
.DESCRIPTION
    Jedno kliknięcie i wszystko samo się robi:
    1. Pobiera najnowszą wersję z GitHub
    2. Zapisuje backup starego configu
    3. Nadpisuje pliki (bez venv, logów, statystyk)
    4. Instaluje brakujące biblioteki
    5. Restartuje aplikację
#>

$INSTALL_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACKUP_DIR = "$INSTALL_DIR\backup"
$REPO_URL = "https://github.com/KamilGoral/SprytnySounder"
$ZIP_URL = "$REPO_URL/archive/refs/heads/main.zip"

# Wymuś TLS 1.2 (potrzebne na starszych Windows w sklepach)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   SprytnySounder — Aktualizator v1.1" -ForegroundColor Cyan
Write-Host "   Folder: $INSTALL_DIR" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Krok 1: Backup konfiguracji
Write-Host "[1/5] Backup konfiguracji..." -ForegroundColor Yellow
try {
    if (Test-Path "$INSTALL_DIR\config.json") {
        if (-not (Test-Path $BACKUP_DIR)) { New-Item -ItemType Directory -Force -Path $BACKUP_DIR | Out-Null }
        Copy-Item "$INSTALL_DIR\config.json" "$BACKUP_DIR\config.json.bak" -Force
        Write-Host "  ✅ Backup: config.json → backup\config.json.bak"
    }
} catch {
    Write-Host "  ⚠ Backup nieudany, ale kontynuuję: $_" -ForegroundColor Yellow
}

# Krok 2: Pobierz najnowszą wersję z GitHub
Write-Host "[2/5] Pobieranie z GitHub..." -ForegroundColor Yellow
$TEMP_ZIP = "$env:TEMP\sprytnysounder.zip"
$TEMP_DIR = "$env:TEMP\sprytnysounder_update"

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Write-Host "  Pobieranie $ZIP_URL ..."
    Invoke-WebRequest -Uri $ZIP_URL -OutFile $TEMP_ZIP -UseBasicParsing
    $zipSize = (Get-Item $TEMP_ZIP).Length
    Write-Host "  ✅ Pobrano ZIP ($zipSize bajtów)"
}
catch {
    Write-Host "  ❌ Błąd pobierania: $_" -ForegroundColor Red
    Write-Host "  Spróbuj: skopiuj ręcznie pliki z GitHub" -ForegroundColor Yellow
    Write-Host "  https://github.com/KamilGoral/SprytnySounder" -ForegroundColor Yellow
    Read-Host "Naciśnij Enter by zakończyć"
    exit 1
}

# Krok 3: Wypakuj i skopiuj
Write-Host "[3/5] Aktualizacja plików..." -ForegroundColor Yellow
try {
    if (Test-Path $TEMP_DIR) { Remove-Item $TEMP_DIR -Recurse -Force -ErrorAction SilentlyContinue }
    Expand-Archive -Path $TEMP_ZIP -DestinationPath $TEMP_DIR -Force
    Write-Host "  ✅ ZIP rozpakowany"

    # Znajdź główny folder w ZIP
    $folders = Get-ChildItem $TEMP_DIR | Where-Object { $_.PSIsContainer }
    if ($folders -eq $null -or $folders.Count -eq 0) {
        Write-Host "  ❌ W ZIP nie znaleziono folderu z plikami!" -ForegroundColor Red
        exit 1
    }
    $SOURCE = $folders[0].FullName
    Write-Host "  Znaleziono folder: $($folders[0].Name)"

    # Pliki i foldery do pominięcia
    $SKIP = @('venv', '.git', '__pycache__', 'build', 'dist', '.idea', 'venv_tts')

    # Kopiuj pliki (bez pomijanych)
    Get-ChildItem $SOURCE -Exclude $SKIP | ForEach-Object {
        $DEST = Join-Path $INSTALL_DIR $_.Name
        if ($_.PSIsContainer) {
            if (Test-Path $DEST) { Remove-Item $DEST -Recurse -Force -ErrorAction SilentlyContinue }
            Copy-Item $_.FullName $DEST -Recurse -Force
            Write-Host "  → Folder: $($_.Name)"
        } else {
            Copy-Item $_.FullName $DEST -Force
            Write-Host "  → Plik: $($_.Name)"
        }
    }
    Write-Host "  ✅ Pliki skopiowane"
}
catch {
    Write-Host "  ❌ Błąd kopiowania plików: $_" -ForegroundColor Red
    exit 1
}

# Przywróć stary config
Write-Host "[4/5] Przywracanie konfiguracji..." -ForegroundColor Yellow
try {
    if (Test-Path "$BACKUP_DIR\config.json.bak") {
        $OLD_CONFIG = Get-Content "$BACKUP_DIR\config.json.bak" -Raw | ConvertFrom-Json
        $NEW_CONFIG = Get-Content "$INSTALL_DIR\config.json" -Raw | ConvertFrom-Json
        
        $NEW_CONFIG.host = $OLD_CONFIG.host
        $NEW_CONFIG.port = $OLD_CONFIG.port
        $NEW_CONFIG.sunday_inverted = $OLD_CONFIG.sunday_inverted
        if ($OLD_CONFIG.update_url) { $NEW_CONFIG.update_url = $OLD_CONFIG.update_url }
        if ($OLD_CONFIG.store_name) { $NEW_CONFIG.store_name = $OLD_CONFIG.store_name }
        
        $NEW_CONFIG | ConvertTo-Json -Depth 10 | Set-Content "$INSTALL_DIR\config.json" -Encoding UTF8
        Write-Host "  ✅ Przywrócono konfigurację"
    } else {
        Write-Host "  ⚠ Brak backupu configu — używam nowego config.json" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ⚠ Nie udało się przywrócić configu: $_" -ForegroundColor Yellow
}

# Krok 5: Restart
Write-Host "[5/5] Restart aplikacji..." -ForegroundColor Yellow

# Zabij stary proces
try {
    Get-Process | Where-Object { $_.ProcessName -like "*python*" -or $_.ProcessName -like "*SprytnySounder*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "  ✅ Stary proces zatrzymany"
} catch {
    Write-Host "  ⚠ Nie udało się zatrzymać procesu" -ForegroundColor Yellow
}

# Znajdź Python
$PYTHON = "python"
if (Test-Path "$INSTALL_DIR\venv\Scripts\python.exe") {
    $PYTHON = "$INSTALL_DIR\venv\Scripts\python.exe"
    Write-Host "  Użyję Python z venv"
} else {
    # Szukaj python w PATH i typowych lokalizacjach
    $pythonPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python39\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python38\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "$env:ProgramFiles\Python310\python.exe",
        "$env:ProgramFiles\Python39\python.exe",
        "$env:ProgramFiles\Python38\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe",
        "C:\Python39\python.exe",
        "C:\Python38\python.exe",
        "C:\Python36\python.exe"
    )
    foreach ($p in $pythonPaths) {
        if (Test-Path $p) {
            $PYTHON = $p
            Write-Host "  Znaleziono Python: $p"
            break
        }
    }
}

# Instaluj requests przez pip jesli potrzeba
try {
    & "$PYTHON" -c "import requests" 2>$null
    Write-Host "  ✅ Biblioteka requests już zainstalowana"
} catch {
    Write-Host "  Instaluję requests..."
    try {
        & "$PYTHON" -m pip install requests -q
        Write-Host "  ✅ requests zainstalowane"
    } catch {
        Write-Host "  ⚠ Nie można zainstalować requests (pip install requests)" -ForegroundColor Yellow
    }
}

# Uruchom aplikację
try {
    Start-Process -NoNewWindow -FilePath "$PYTHON" -ArgumentList "`"$INSTALL_DIR\app.py`"" -WorkingDirectory $INSTALL_DIR
    Write-Host "  ✅ Aplikacja uruchomiona przez: $PYTHON"
} catch {
    Write-Host "  ❌ Nie można uruchomić: $_" -ForegroundColor Red
}

# Cleanup
Remove-Item $TEMP_ZIP -Force -ErrorAction SilentlyContinue
Remove-Item $TEMP_DIR -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   ✅ Gotowe!" -ForegroundColor Green
Write-Host "   Panel: http://localhost:8989" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Read-Host "Naciśnij Enter by zakończyć"
