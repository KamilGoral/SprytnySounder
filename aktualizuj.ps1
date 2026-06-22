<#
.SYNOPSIS
    SprytnySounder — Aktualizator dla sklepow v1.2
.DESCRIPTION
    Jedno klikniecie i wszystko samo sie robi:
    1. Pobiera najnowsza wersje z GitHub
    2. Zapisuje backup starego configu
    3. Nadpisuje pliki (bez venv, logow, statystyk, config.json)
    4. Instaluje brakujace biblioteki
    5. Restartuje aplikacje
#>

$INSTALL_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACKUP_DIR = "$INSTALL_DIR\backup"
$REPO_URL = "https://github.com/KamilGoral/SprytnySounder"
$ZIP_URL = "$REPO_URL/archive/refs/heads/main.zip"

# Wymus TLS 1.2 (potrzebne na starszych Windows w sklepach)
[Net.ServicePointManager]::SecurityProtocol = 3072 -bor 768 -bor 192

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   SprytnySounder - Aktualizator v1.2" -ForegroundColor Cyan
Write-Host "   Folder: $INSTALL_DIR" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---- Krok 1: Backup konfiguracji ----
Write-Host "[1/5] Backup konfiguracji..." -ForegroundColor Yellow
try {
    if (Test-Path "$INSTALL_DIR\config.json") {
        if (-not (Test-Path $BACKUP_DIR)) { New-Item -ItemType Directory -Force -Path $BACKUP_DIR | Out-Null }
        Copy-Item "$INSTALL_DIR\config.json" "$BACKUP_DIR\config.json.bak" -Force
        Write-Host "  OK - backup zrobiony"
    }
} catch {
    Write-Host "  UWAGA - backup nieudany: $_" -ForegroundColor Yellow
}

# ---- Krok 2: Pobierz najnowsza wersje z GitHub ----
Write-Host "[2/5] Pobieranie z GitHub..." -ForegroundColor Yellow
$TEMP_ZIP = "$env:TEMP\sprytnysounder.zip"
$TEMP_DIR = "$env:TEMP\sprytnysounder_update"

try {
    Write-Host "  Pobieranie $ZIP_URL ..."
    Invoke-WebRequest -Uri $ZIP_URL -OutFile $TEMP_ZIP -UseBasicParsing
    $zipSize = (Get-Item $TEMP_ZIP).Length
    Write-Host "  OK - pobrano ZIP ($zipSize bajtow)"
}
catch {
    Write-Host "  BLAD pobierania: $_" -ForegroundColor Red
    Write-Host "  Sprobuj recznie: pobierz ZIP z https://github.com/KamilGoral/SprytnySounder" -ForegroundColor Yellow
    Read-Host "Nacisnij Enter"
    exit 1
}

# ---- Krok 3: Wypakuj i skopiuj ----
Write-Host "[3/5] Aktualizacja plikow..." -ForegroundColor Yellow
try {
    if (Test-Path $TEMP_DIR) { Remove-Item $TEMP_DIR -Recurse -Force -ErrorAction SilentlyContinue }

    # Probuj Expand-Archive (PS 5+), jesli nie ma - uzyj .NET (dziala na starszych PS)
    $extractedOk = $false
    if (Get-Command Expand-Archive -ErrorAction SilentlyContinue) {
        try {
            Expand-Archive -Path $TEMP_ZIP -DestinationPath $TEMP_DIR -Force
            $extractedOk = $true
            Write-Host "  OK - ZIP rozpakowany przez Expand-Archive"
        } catch {
            Write-Host "  Expand-Archive nie dziala, probuje .NET..." -ForegroundColor Yellow
        }
    }

    if (-not $extractedOk) {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($TEMP_ZIP, $TEMP_DIR)
        Write-Host "  OK - ZIP rozpakowany przez .NET"
    }

    # Znajdz glowny folder w ZIP
    $folders = Get-ChildItem $TEMP_DIR | Where-Object { $_.PSIsContainer }
    if ($folders -eq $null -or $folders.Count -eq 0) {
        Write-Host "  BLAD - w ZIP nie znaleziono folderu z plikami!" -ForegroundColor Red
        exit 1
    }
    $SOURCE = $folders[0].FullName
    Write-Host "  Folder zrodlowy: $($folders[0].Name)"

    # Pliki i foldery do pominiecia (NIE nadpisujemy configu sklepu!)
    $SKIP = @('venv', '.git', '__pycache__', 'build', 'dist', '.idea', 'venv_tts', '.secrets', 'config.json', 'aktualizuj.ps1', 'log.txt', 'statystyka.txt')

    # Kopiuj pliki (bez pomijanych)
    Get-ChildItem $SOURCE -Exclude $SKIP | ForEach-Object {
        $DEST = Join-Path $INSTALL_DIR $_.Name
        if ($_.PSIsContainer) {
            if (Test-Path $DEST) { Remove-Item $DEST -Recurse -Force -ErrorAction SilentlyContinue }
            Copy-Item $_.FullName $DEST -Recurse -Force
            Write-Host "  -> Folder: $($_.Name)"
        } else {
            Copy-Item $_.FullName $DEST -Force
            Write-Host "  -> Plik: $($_.Name)"
        }
    }
    Write-Host "  OK - pliki zaktualizowane (config.json zachowany)"
}
catch {
    Write-Host "  BLAD kopiowania plikow: $_" -ForegroundColor Red
    exit 1
}

# ---- Krok 4: Instalacja bibliotek ----
Write-Host "[4/5] Instalacja bibliotek Python..." -ForegroundColor Yellow

# Znajdz Python
$PYTHON = "python"
$pythonPaths = @(
    "$INSTALL_DIR\venv\Scripts\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python39\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python38\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python36\python.exe",
    "$env:ProgramFiles\Python312\python.exe",
    "$env:ProgramFiles\Python311\python.exe",
    "$env:ProgramFiles\Python310\python.exe",
    "C:\Python312\python.exe",
    "C:\Python311\python.exe",
    "C:\Python310\python.exe",
    "C:\Python36\python.exe"
)
foreach ($p in $pythonPaths) {
    if (Test-Path $p) {
        $PYTHON = $p
        Write-Host "  Znaleziono Python: $p"
        break
    }
}

# Instaluj requests przez pip
try {
    & "$PYTHON" -c "import requests" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK - biblioteka requests juz jest"
    } else {
        throw "brak requests"
    }
} catch {
    Write-Host "  Instalowanie requests..."
    try {
        & "$PYTHON" -m pip install requests -q 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  OK - requests zainstalowane"
        } else {
            throw "pip failed"
        }
    } catch {
        Write-Host "  UWAGA - nie mozna zainstalowac requests (pip install requests)" -ForegroundColor Yellow
    }
}

# ---- Krok 5: Restart aplikacji ----
Write-Host "[5/5] Restart aplikacji..." -ForegroundColor Yellow

# Zabij stary proces
try {
    Get-Process | Where-Object { $_.ProcessName -like "*python*" -or $_.ProcessName -like "*SprytnySounder*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "  OK - stary proces zatrzymany"
} catch {
    Write-Host "  UWAGA - nie udalo sie zatrzymac procesu" -ForegroundColor Yellow
}

# Uruchom od nowa (sciezka w cudzyslowiu - dziala nawet ze spacja w nazwie folderu!)
$APP = "$INSTALL_DIR\app.py"
try {
    Start-Process -NoNewWindow -FilePath "$PYTHON" -ArgumentList "`"$APP`"" -WorkingDirectory $INSTALL_DIR
    Write-Host "  OK - aplikacja uruchomiona"
} catch {
    Write-Host "  BLAD - nie mozna uruchomic: $_" -ForegroundColor Red
}

# Cleanup
Remove-Item $TEMP_ZIP -Force -ErrorAction SilentlyContinue
Remove-Item $TEMP_DIR -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   OK - Gotowe!" -ForegroundColor Green
Write-Host "   Panel: http://localhost:8989" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Read-Host "Nacisnij Enter"
