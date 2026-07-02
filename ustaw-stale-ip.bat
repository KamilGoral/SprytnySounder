@echo off
setlocal
cd /d "%~dp0"
title SprytnySounder - stale IP
set "AUTOMODE=%~1"

:: Wykryj aktualne IPv4 (pierwsze z ipconfig - tak samo jak instalator)
set "IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set "IP=%%a"
    goto :IP_DONE
)
:IP_DONE
set "IP=%IP: =%"
if "%IP%"=="" (
    echo BLAD - nie wykryto adresu IPv4
    if not "%AUTOMODE%"=="auto" pause
    exit /b 1
)
echo Wykryte IP: %IP%
echo Ustawiam to IP na stale w Windows - potwierdz okno uprawnien...

:: Skrypt PowerShell przez WMI - bez parsowania zlokalizowanego ipconfig,
:: przenosi tez brame i DNS; zgodny z PowerShell 2.0 (Win7)
set "PS1=%TEMP%\ss_staticip.ps1"
>  "%PS1%" echo $ErrorActionPreference = 'Stop'
>> "%PS1%" echo $ip = '%IP%'
>> "%PS1%" echo $dir = '%CD%'
>> "%PS1%" echo $nic = $null
>> "%PS1%" echo $nics = Get-WmiObject Win32_NetworkAdapterConfiguration -Filter "IPEnabled=true"
>> "%PS1%" echo foreach ($n in $nics) { if ($n.IPAddress -contains $ip) { $nic = $n } }
>> "%PS1%" echo if ($nic -eq $null) { exit 1 }
>> "%PS1%" echo $idx = [array]::IndexOf($nic.IPAddress, $ip)
>> "%PS1%" echo $mask = $nic.IPSubnet[$idx]
>> "%PS1%" echo $gw = @()
>> "%PS1%" echo foreach ($g in $nic.DefaultIPGateway) { if ($g -match '^^\d+\.') { $gw += $g } }
>> "%PS1%" echo $dns = @()
>> "%PS1%" echo foreach ($d in $nic.DNSServerSearchOrder) { if ($d -match '^^\d+\.') { $dns += $d } }
>> "%PS1%" echo $mac = $nic.MACAddress
>> "%PS1%" echo $r = $nic.EnableStatic($ip, $mask)
>> "%PS1%" echo if ($r.ReturnValue -ne 0) { exit 2 }
>> "%PS1%" echo if ($gw.Count -gt 0) { [void]$nic.SetGateways($gw) }
>> "%PS1%" echo if ($dns.Count -gt 0) { [void]$nic.SetDNSServerSearchOrder($dns) }
>> "%PS1%" echo $txt = @()
>> "%PS1%" echo $txt += 'SprytnySounder - ten komputer ma na stale ustawione IP w Windows'
>> "%PS1%" echo $txt += ''
>> "%PS1%" echo $txt += ('IP:    ' + $ip)
>> "%PS1%" echo $txt += ('Maska: ' + $mask)
>> "%PS1%" echo $txt += ('Brama: ' + [string]$gw)
>> "%PS1%" echo $txt += ('MAC:   ' + $mac)
>> "%PS1%" echo $txt += ''
>> "%PS1%" echo $txt += 'ZALECANE: zarezerwuj ten adres takze na routerze, zeby DHCP'
>> "%PS1%" echo $txt += 'nie przydzielil go innemu urzadzeniu. Jak to zrobic:'
>> "%PS1%" echo $txt += ('1. W przegladarce otworz adres bramy: http://' + [string]$gw)
>> "%PS1%" echo $txt += '2. Zaloguj sie - login i haslo czesto sa na naklejce na routerze.'
>> "%PS1%" echo $txt += '3. Znajdz sekcje DHCP i w niej: Rezerwacja adresow /'
>> "%PS1%" echo $txt += '   Address Reservation / Static Lease - nazwa zalezy od routera.'
>> "%PS1%" echo $txt += ('4. Dodaj wpis: MAC ' + $mac + '  -^>  IP ' + $ip)
>> "%PS1%" echo $txt += '5. Zapisz. Od tej pory router zawsze przydzieli temu'
>> "%PS1%" echo $txt += '   komputerowi ten sam adres.'
>> "%PS1%" echo Set-Content -Path ($dir + '\STALE-IP-INFO.txt') -Value $txt
>> "%PS1%" echo exit 0

powershell -NoProfile -Command "$p = Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%PS1%' -Verb RunAs -Wait -PassThru; exit $p.ExitCode" >nul 2>&1
set "PSEXIT=%errorlevel%"
del "%PS1%" 2>nul

:: Weryfikacja: ps1 musial zglosic sukces, a adres ma nadal byc na karcie
if not "%PSEXIT%"=="0" goto :STATIC_FAIL
ipconfig | findstr /c:"%IP%" >nul
if errorlevel 1 goto :STATIC_FAIL
goto :STATIC_OK
:STATIC_FAIL
echo UWAGA - nie udalo sie ustawic stalego IP. Ustaw recznie:
echo Panel sterowania - Centrum sieci - Zmien ustawienia karty sieciowej
echo - Wlasciwosci - Protokol internetowy w wersji 4.
if not "%AUTOMODE%"=="auto" pause
exit /b 1

:STATIC_OK
echo OK - IP %IP% ustawione na stale w Windows.
if exist "STALE-IP-INFO.txt" echo Poradnik rezerwacji na routerze: STALE-IP-INFO.txt
if not "%AUTOMODE%"=="auto" pause
exit /b 0
