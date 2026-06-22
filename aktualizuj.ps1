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

$ErrorActionPreference = "Stop"
$INSTALL_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACKUP_DIR = "$INSTALL_DIR\backup"
$REPO_URL = "https://github.com/KamilGoral/SprytnySounder"
$ZIP_URL = "$REPO_URL/archive/refs/heads/main.zip"

# Wymuś TLS 1.2 (potrzebne na starszych Windows w sklepach)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   SprytnySounder — Aktualizator v1.1" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Krok 1: Backup konfiguracji
Write-Host "[1/5] Backup konfiguracji..." -ForegroundColor Yellow
if (Test-Path "$INSTALL_DIR\config.json") {
    New-Item -ItemType Directory -Force -Path $BACKUP_DIR | Out-Null
    Copy-Item "$INSTALL_DIR\config.json" "$BACKUP_DIR\config.json.bak" -Force
    Write-Host "  ✅ Backup: $BACKUP_DIR\config.json.bak"
}

# Krok 2: Pobierz najnowszą wersję z GitHub
Write-Host "[2/5] Pobieranie z GitHub..." -ForegroundColor Yellow
$TEMP_ZIP = "$env:TEMP\sprytnysounder.zip"
$TEMP_DIR = "$env:TEMP\sprytnysounder_update"

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $ZIP_URL -OutFile $TEMP_ZIP -UseBasicParsing
    Write-Host "  ✅ Pobrano: $ZIP_URL"
}
catch {
    Write-Host "  ❌ Błąd pobierania: $_" -ForegroundColor Red
    exit 1
}

# Krok 3: Wypakuj i skopiuj
Write-Host "[3/5] Aktualizacja plików..." -ForegroundColor Yellow
if (Test-Path $TEMP_DIR) { Remove-Item $TEMP_DIR -Recurse -Force }
Expand-Archive -Path $TEMP_ZIP -DestinationPath $TEMP_DIR -Force

# Znajdź główny folder w ZIP
$EXTRACTED = Get-ChildItem $TEMP_DIR | Where-Object { $_.PSIsContainer } | Select-Object -First 1
$SOURCE = $EXTRACTED.FullName

# Pliki do pominięcia
$SKIP = @('venv', '.git', '__pycache__', 'build', 'dist', '.idea', 'log.txt', 'statystyka.txt')

# Kopiuj pliki (bez pomijanych)
Get-ChildItem $SOURCE -Exclude $SKIP | ForEach-Object {
    $DEST = Join-Path $INSTALL_DIR $_.Name
    if ($_.PSIsContainer) {
        if (Test-Path $DEST) { Remove-Item $DEST -Recurse -Force }
        Copy-Item $_.FullName $DEST -Recurse -Force
    } else {
        Copy-Item $_.FullName $DEST -Force
    }
}

# Przywróć stary config (nowy config ma już ustawiony update_url)
if (Test-Path "$BACKUP_DIR\config.json.bak") {
    $OLD_CONFIG = Get-Content "$BACKUP_DIR\config.json.bak" -Raw | ConvertFrom-Json
    $NEW_CONFIG = Get-Content "$INSTALL_DIR\config.json" -Raw | ConvertFrom-Json
    
    # Zachowaj stare ustawienia: host, port, sunday_inverted
    $NEW_CONFIG.host = $OLD_CONFIG.host
    $NEW_CONFIG.port = $OLD_CONFIG.port
    $NEW_CONFIG.sunday_inverted = $OLD_CONFIG.sunday_inverted
    if ($OLD_CONFIG.update_url) { $NEW_CONFIG.update_url = $OLD_CONFIG.update_url }
    if ($OLD_CONFIG.store_name) { $NEW_CONFIG.store_name = $OLD_CONFIG.store_name }
    
    $NEW_CONFIG | ConvertTo-Json | Set-Content "$INSTALL_DIR\config.json" -Encoding UTF8
    Write-Host "  ✅ Przywrócono konfigurację (host, port, sunday_inverted)"
}

# Krok 4: Zainstaluj biblioteki
Write-Host "[4/5] Instalacja bibliotek Python..." -ForegroundColor Yellow
$PIP = if (Test-Path "$INSTALL_DIR\venv\Scripts\pip.exe") { "$INSTALL_DIR\venv\Scripts\pip.exe" } else { "pip" }
try {
    & $PIP install requests -q
    Write-Host "  ✅ Biblioteki OK"
} catch {
    Write-Host "  ⚠ Nie można zainstalować bibliotek (ręcznie: pip install requests)" -ForegroundColor Yellow
}

# Krok 5: Restart
Write-Host "[5/5] Restart aplikacji..." -ForegroundColor Yellow

# Zabij stary proces
Get-Process | Where-Object { $_.ProcessName -like "*python*" -or $_.ProcessName -like "*SprytnySounder*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Uruchom od nowa
if (Test-Path "$INSTALL_DIR\venv\Scripts\python.exe") {
    Start-Process -NoNewWindow -FilePath "$INSTALL_DIR\venv\Scripts\python.exe" -ArgumentList "$INSTALL_DIR\app.py" -WorkingDirectory $INSTALL_DIR
    Write-Host "  ✅ Uruchomiono przez venv"
} else {
    Start-Process -NoNewWindow -FilePath "python" -ArgumentList "$INSTALL_DIR\app.py" -WorkingDirectory $INSTALL_DIR
    Write-Host "  ✅ Uruchomiono przez python"
}

# Cleanup
Remove-Item $TEMP_ZIP -Force -ErrorAction SilentlyContinue
Remove-Item $TEMP_DIR -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   ✅ Gotowe! Aplikacja zrestartowana." -ForegroundColor Green
Write-Host "   Panel: http://localhost:8989" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Koniec. Możesz zamknąć to okno." -ForegroundColor Gray
Read-Host "Naciśnij Enter"
