#Requires -Version 5.1
<#
.SYNOPSIS
    ESP32-P4-Pico Onarim Terminali - PC Koprusu

.DESCRIPTION
    Bu betik, ESP32-P4-Pico'dan USB seri port uzerinden gelen istek
    kodlarini dinler. Pico hicbir komutu dogrudan calistiramaz; sadece
    "bunu yapmak istiyorum" seklinde bir kod gonderir. Bu betik her
    istek icin ONCE EKRANDA KULLANICIYA SORAR, yalnizca "E" (Evet)
    cevabi verilirse ilgili Windows bakim komutunu calistirir.

    Guvenlik ilkeleri:
      - Beyaz listedeki komutlar disinda hicbir sey calistirilmaz.
      - Her calistirmadan once acik onay istenir (varsayilan: Hayir).
      - Tum islemler ve sonuclar log dosyasina yazilir.
      - Yonetici (Administrator) gerektiren islemler ayrica belirtilir;
        betik yonetici olarak calismiyorsa kullaniciyi uyarir ve atlar.

.NOTES
    Calistirmadan once Pico'nun hangi COM portuna baglandigini
    Aygit Yoneticisi'nden (Device Manager) kontrol et.
#>

param(
    [string]$PortName = "",
    [int]$BaudRate = 115200
)

$ErrorActionPreference = "Stop"
$LogDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir ("session_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date))

function Write-Log {
    param([string]$Message)
    $line = "[{0:yyyy-MM-dd HH:mm:ss}] {1}" -f (Get-Date), $Message
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ---- Beyaz liste: Pico'dan gelebilecek komut kodu -> gercek islem ----
# Her giris: Aciklama, Yonetici gerekli mi, calistirilacak ScriptBlock
$CommandTable = @{
    "CMD:WIN_REPAIR" = @{
        Desc = "Windows sistem dosyasi onarimi (sfc /scannow + DISM RestoreHealth)"
        NeedsAdmin = $true
        Action = {
            Write-Log "SFC taramasi basliyor..."
            sfc /scannow 2>&1 | Tee-Object -FilePath $LogFile -Append
            Write-Log "DISM RestoreHealth basliyor..."
            DISM /Online /Cleanup-Image /RestoreHealth 2>&1 | Tee-Object -FilePath $LogFile -Append
        }
    }
    "CMD:DISK_CLEAN" = @{
        Desc = "Gecici dosyalari ve Windows gecici klasorlerini temizle"
        NeedsAdmin = $false
        Action = {
            $targets = @(
                $env:TEMP,
                "$env:WINDIR\Temp"
            )
            foreach ($t in $targets) {
                Write-Log "Temizleniyor: $t"
                Get-ChildItem -Path $t -Recurse -Force -ErrorAction SilentlyContinue |
                    Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
            }
            Write-Log "Disk temizligi tamamlandi."
            cleanmgr /sagerun:1 2>&1 | Out-Null
        }
    }
    "CMD:NET_RESET" = @{
        Desc = "Ag ayarlarini sifirla (ipconfig renew, DNS flush, Winsock reset)"
        NeedsAdmin = $true
        Action = {
            ipconfig /release 2>&1   | Tee-Object -FilePath $LogFile -Append
            ipconfig /renew 2>&1     | Tee-Object -FilePath $LogFile -Append
            ipconfig /flushdns 2>&1  | Tee-Object -FilePath $LogFile -Append
            netsh winsock reset 2>&1 | Tee-Object -FilePath $LogFile -Append
            Write-Log "Ag sifirlama tamamlandi. Degisikliklerin tamami icin yeniden baslatma onerilir."
        }
    }
    "CMD:DIAG_REPORT" = @{
        Desc = "Sistem teshis raporu olustur (CPU, RAM, disk, son hatalar)"
        NeedsAdmin = $false
        Action = {
            $reportPath = Join-Path $LogDir ("diag_{0:yyyyMMdd_HHmmss}.txt" -f (Get-Date))
            "== Sistem Bilgisi ==" | Out-File $reportPath
            Get-ComputerInfo | Out-File $reportPath -Append
            "`n== Disk Durumu ==" | Out-File $reportPath -Append
            Get-PSDrive -PSProvider FileSystem | Out-File $reportPath -Append
            "`n== Son 20 Sistem Hatasi ==" | Out-File $reportPath -Append
            Get-WinEvent -LogName System -MaxEvents 50 -ErrorAction SilentlyContinue |
                Where-Object { $_.LevelDisplayName -eq "Error" } |
                Select-Object -First 20 TimeCreated, Id, Message |
                Format-List | Out-File $reportPath -Append
            Write-Log "Teshis raporu olusturuldu: $reportPath"
        }
    }
    "CMD:STARTUP_LIST" = @{
        Desc = "Baslangicta calisan programlari listele"
        NeedsAdmin = $false
        Action = {
            Get-CimInstance Win32_StartupCommand |
                Select-Object Name, Command, Location |
                Format-Table -AutoSize | Out-String | Write-Log
        }
    }
    "CMD:DISK_HEALTH" = @{
        Desc = "Disk alani ve SMART (fiziksel disk) durumu"
        NeedsAdmin = $false
        Action = {
            Get-Volume | Format-Table -AutoSize | Out-String | Write-Log
            Get-PhysicalDisk | Select-Object FriendlyName, HealthStatus, OperationalStatus |
                Format-Table -AutoSize | Out-String | Write-Log
        }
    }
}

# ---- COM portu bul ----
if ([string]::IsNullOrWhiteSpace($PortName)) {
    Write-Host "Takili seri portlar araniyor..."
    $ports = Get-CimInstance Win32_SerialPort -ErrorAction SilentlyContinue
    if (-not $ports) {
        $ports = [System.IO.Ports.SerialPort]::GetPortNames() | ForEach-Object {
            [PSCustomObject]@{ DeviceID = $_; Description = "Bilinmeyen cihaz" }
        }
    }
    if (-not $ports -or $ports.Count -eq 0) {
        Write-Error "Hicbir seri port bulunamadi. ESP32-P4-Pico'nun USB-C ile bagli oldugundan emin ol."
        exit 1
    }
    Write-Host "Bulunan portlar:"
    $i = 0
    $portArr = @($ports)
    foreach ($p in $portArr) {
        Write-Host ("  [{0}] {1} - {2}" -f $i, $p.DeviceID, $p.Description)
        $i++
    }
    if ($portArr.Count -eq 1) {
        $PortName = $portArr[0].DeviceID
        Write-Host "Tek port bulundu, otomatik seciliyor: $PortName"
    } else {
        $sel = Read-Host "Kullanilacak portun numarasini gir"
        $PortName = $portArr[[int]$sel].DeviceID
    }
}

Write-Log "ESP32-P4-Pico Onarim Terminali Koprusu baslatiliyor. Port: $PortName, Baud: $BaudRate"
if (-not (Test-IsAdmin)) {
    Write-Log "UYARI: Bu PowerShell yonetici olarak calismiyor. Yonetici gerektiren islemler (SFC/DISM/ag sifirlama) atlanacak."
}

try {
    $port = New-Object System.IO.Ports.SerialPort $PortName, $BaudRate, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
    $port.ReadTimeout = 2000
    $port.NewLine = "`n"
    $port.Open()
} catch {
    Write-Error "Port acilamadi: $($_.Exception.Message)"
    exit 1
}

Write-Host ""
Write-Host "Baglanti kuruldu. Pico uzerindeki menuden secim yap. Cikmak icin Ctrl+C." -ForegroundColor Green
Write-Host ""

try {
    while ($true) {
        try {
            $line = $port.ReadLine()
        } catch [TimeoutException] {
            continue
        }
        $line = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        if ($line.StartsWith("CMD:")) {
            if ($CommandTable.ContainsKey($line)) {
                $entry = $CommandTable[$line]
                Write-Host ""
                Write-Host "Pico'dan istek geldi: $($entry.Desc)" -ForegroundColor Yellow
                if ($entry.NeedsAdmin -and -not (Test-IsAdmin)) {
                    Write-Host "Bu islem yonetici yetkisi gerektirir ama PowerShell yonetici degil. ATLANIYOR." -ForegroundColor Red
                    Write-Log "ATLANDI (yonetici yok): $line"
                    continue
                }
                $confirm = Read-Host "Bu islemi calistirmak istiyor musun? [E/h]"
                if ($confirm -match '^(e|evet|y|yes)$') {
                    Write-Log "ONAYLANDI: $line - $($entry.Desc)"
                    try {
                        & $entry.Action
                        Write-Log "TAMAMLANDI: $line"
                    } catch {
                        Write-Log "HATA: $line - $($_.Exception.Message)"
                    }
                } else {
                    Write-Log "REDDEDILDI: $line"
                    Write-Host "Islem iptal edildi." -ForegroundColor DarkYellow
                }
            } else {
                Write-Log "Bilinmeyen komut kodu (yok sayildi): $line"
            }
        } else {
            # Pico'dan gelen normal menu metni / echo - sadece goster
            Write-Host $line
        }
    }
} finally {
    if ($port.IsOpen) { $port.Close() }
    Write-Log "Baglanti kapatildi."
}
