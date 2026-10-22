"""
Belediye Teknik Destek Terminali
---------------------------------
ESP32-P4-Pico USB belleginden calisan, kurulum gerektirmeyen tasinabilir
Windows teshis/onarim terminali.

Davranis:
  - Internet varsa: DeepSeek API'ye "tool calling" (function calling) ile
    baglanir. DeepSeek, sorunu dinler ve hangi TESHIS/ONARIM aracini
    cagirmak istedigini kendi secer (ornegin disk durumu, event log,
    servis durumu, yazici kuyrugu vs). Model asla komutu DOGRUDAN
    calistirmaz; sadece "su araci su parametrelerle cagirmak istiyorum"
    der, program onu yorumlar.
  - Internet yoksa: yerel kural tabanli (heuristic) teshis motoru calisir.

Guvenlik ilkeleri (ONEMLI):
  - Yalnizca asagida ARAC_KAYDI icinde tanimli, beyaz listedeki araclar
    cagirilabilir. Model baska bir komut uretemez/calistiramaz.
  - Her aracin "destructive" (sistemi degistiren) olup olmadigi isaretli.
    destructive=True olan bir arac cagrilmadan once KULLANICIYA EKRANDA
    acikca onay sorulur ([E/h]); onaylanmadan calismaz.
  - destructive=False olan araclar (salt okunur teshis: disk durumu,
    event log okuma, servis durumu listeleme vb.) otomatik calisir,
    cunku sistemi degistirmezler.
  - DeepSeek'e gonderilen sistem ozetinden bilgisayar adi (hostname) ve
    kullanici adi gibi kisisel/tanimlayici alanlar filtrelenir.
  - Tum arac cagrilari ve kullanici onaylari log dosyasina yazilir.

Derleme (tek exe):
    pip install -r requirements.txt
    pyinstaller --onefile --name ONARIM_BASLAT --console pc_terminal.py
"""

import csv
import ctypes
import json
import os
import platform
import re
import socket
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime

# ------------------------------------------------------------------
# Ayarlar
# ------------------------------------------------------------------

MARKA = "ERDEMUSB"  # terminalin ve konsol penceresinin basligindaki ad

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "BURAYA_DEEPSEEK_API_ANAHTARINI_YAZ")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_ARAC_TURU = 6  # Bir soru basina en fazla kac tool-call turu yapilsin

# USB uzerindeki (exe'nin calistigi) dizin - loglar, ozet raporlar ve
# demirbas kayit defteri buraya, yani USB'nin kendisine yazilir; boylece
# teknisyen USB'yi cikardiginda tum gecmis yaninda gider.
USB_DIZIN = os.path.dirname(os.path.abspath(sys.argv[0]))
LOG_DIR = os.path.join(USB_DIZIN, "loglar")
RAPOR_DIR = os.path.join(USB_DIZIN, "raporlar")
KAYIT_DEFTERI_CSV = os.path.join(USB_DIZIN, "demirbas_kayit_defteri.csv")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(RAPOR_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"oturum_{datetime.now():%Y%m%d_%H%M%S}.log")


def log(msg: str):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    # dosyaya duz, konsola sonuk (dim) gri yazilir - ic izleme kaydi gibi
    # okunur, asil onemli mesajlar (hata/basari/onay) kendi renkleriyle one cikar
    print(r(line, Renk.SONUK, Renk.GRI))
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ------------------------------------------------------------------
# Renkler (ANSI) - terminali okumasi kolay hale getirir: yesil = salt
# okunur/basarili, sari = onay gerektiren/dikkat, kirmizi = riskli/hata,
# cyan/turuncu = basliklar. Hicbir karakter kaybi olmaz; renk kodlari
# desteklenmeyen bir konsolda RENK_ACIK False kalir, metinler duz basilir.
# ------------------------------------------------------------------

class Renk:
    SIFIRLA = "\033[0m"
    KALIN = "\033[1m"
    SONUK = "\033[2m"
    KIRMIZI = "\033[38;5;203m"
    YESIL = "\033[38;5;114m"
    SARI = "\033[38;5;221m"
    MAVI = "\033[38;5;75m"
    MOR = "\033[38;5;177m"
    CYAN = "\033[38;5;80m"
    TURUNCU = "\033[38;5;215m"
    GRI = "\033[38;5;245m"
    BEYAZ = "\033[38;5;255m"


RENK_ACIK = False


def renklendir_etkinlestir():
    """VT100/ANSI renk kodlarini bu konsolda acmayi dener. Windows 10 1511+
    her yerde destekler ama varsayilan kapalidir; eski/alisilmadik bir
    konsolda basarisiz olursa program renksiz calismaya devam eder."""
    global RENK_ACIK
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            h = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mod = ctypes.c_uint32()
            if kernel32.GetConsoleMode(h, ctypes.byref(mod)):
                ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                if kernel32.SetConsoleMode(h, mod.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING):
                    RENK_ACIK = True
            try:
                kernel32.SetConsoleTitleW(f"{MARKA} - Teknik Destek Terminali")
            except Exception:
                pass
        except Exception:
            RENK_ACIK = False
    else:
        RENK_ACIK = sys.stdout.isatty()


def r(metin: str, *renkler: str) -> str:
    """Metni verilen ANSI renk kod(lar)iyla sarar; renk kapaliysa metni
    oldugu gibi dondurur (hicbir yerde renk olmadan okunamaz hale gelmez)."""
    if not RENK_ACIK or not renkler:
        return metin
    return "".join(renkler) + metin + Renk.SIFIRLA


# ------------------------------------------------------------------
# Yonetici yetkisi - sfc, DISM, chkdsk, geri yukleme noktasi, disk temizligi
# ve guc plani yonetici ister; yetkisiz acilan program bunlarda sessizce
# basarisiz oluyordu.
# ------------------------------------------------------------------

def yonetici_mi() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def yonetici_olarak_yeniden_ac() -> bool:
    """Programi UAC onayiyla yonetici olarak yeniden acar. Acildiysa True."""
    try:
        if getattr(sys, "frozen", False):
            exe, argumanlar = sys.executable, sys.argv[1:]
        else:
            exe, argumanlar = sys.executable, [os.path.abspath(sys.argv[0])] + sys.argv[1:]
        parametre = " ".join(f'"{a}"' for a in argumanlar)
        return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, parametre, USB_DIZIN, 1) > 32
    except Exception as e:
        log(f"Yonetici olarak yeniden acilamadi: {e}")
        return False


# Gercek logo dosyasi (PNG) varsa burada aranir; varsa acilista (istege
# baglica) varsayilan resim goruntuleyicide gosterilir. Dosya yoksa
# sessizce atlanir, program yine calisir.
LOGO_PNG_ADAYLAR = ("kurum_logo.png", "sinop_logo.png")  # ilk bulunan kullanilir
LOGO_PNG = next(
    (os.path.join(USB_DIZIN, "assets", ad) for ad in LOGO_PNG_ADAYLAR
     if os.path.exists(os.path.join(USB_DIZIN, "assets", ad))),
    os.path.join(USB_DIZIN, "assets", LOGO_PNG_ADAYLAR[0]),
)
# Terminalde (sadece metin karakterleriyle) gosterilen temsili amblem -

# Terminalde (sadece ASCII metin karakterleriyle - eski Windows konsollarinin
# kod sayfasinda da dogru gorunur) gosterilen bir USB bellek cizimi + MARKA'nin
# buyuk harfli yazisi (pyfiglet "standard" fontu).
ASCII_AMBLEM = r"""
                 _________
                |   ____  |
                |  |    | |
                |  |____| |
                |_________|
                 |       |
                _|_______|_
               [___________]
"""

# "ERDEMUSB" - pyfiglet standard font. MARKA degistirilirse bu blok da
# (python -c "import pyfiglet; print(pyfiglet.Figlet(font='standard').renderText('YENI_AD'))")
# ile yeniden uretilip burada elle guncellenmeli.
ASCII_BASLIK = r"""
 _____ ____  ____  _____ __  __ _   _ ____  ____
| ____|  _ \|  _ \| ____|  \/  | | | / ___|| __ )
|  _| | |_) | | | |  _| | |\/| | | | \___ \|  _ \
| |___|  _ <| |_| | |___| |  | | |_| |___) | |_) |
|_____|_| \_\____/|_____|_|  |_|\___/|____/|____/
"""


def logo_ac():
    """Gercek (renkli) logo PNG dosyasi varsa, Windows'un varsayilan
    resim goruntuleyicisinde acar. Dosya yoksa sessizce atlar."""
    if os.path.exists(LOGO_PNG):
        try:
            os.startfile(LOGO_PNG)
        except Exception as e:
            log(f"Logo acilamadi: {e}")


def _ortala_blok(metin: str, genislik: int) -> str:
    """Cok satirli bir metnin TAMAMINI, en uzun satirina gore tek bir
    sol-bosluk miktariyla ortalar (her satiri ayri ayri degil, blok
    olarak - boylece ASCII sekiller bozulmaz)."""
    satirlar = metin.split("\n")
    en_uzun = max((len(s) for s in satirlar), default=0)
    sol_bosluk = max((genislik - en_uzun) // 2, 0)
    return "\n".join((" " * sol_bosluk) + s if s.strip() else s for s in satirlar)


def _renkli_blok(metin: str, *renkler: str) -> str:
    """_ortala_blok ile zaten ortalanmis bir metnin her satirini ayri ayri
    renklendirir (ortalama icin eklenen bosluklar renklendirmeden once
    satirin basina girmis olmali, yoksa dolgu miktari bozulur)."""
    if not RENK_ACIK or not renkler:
        return metin
    return "\n".join(r(satir, *renkler) if satir.strip() else satir for satir in metin.split("\n"))


def baslik():
    renklendir_etkinlestir()
    os.system("cls" if os.name == "nt" else "clear")
    try:
        genislik = os.get_terminal_size().columns
    except OSError:
        genislik = 90

    print(_renkli_blok(_ortala_blok(ASCII_AMBLEM, genislik), Renk.TURUNCU))
    print(_renkli_blok(_ortala_blok(ASCII_BASLIK, genislik), Renk.KALIN, Renk.CYAN))
    print(r(f"{MARKA} TEKNIK DESTEK TERMINALI".center(genislik), Renk.KALIN, Renk.BEYAZ))
    print(r("(Kurulum gerektirmez - USB'den calisir)".center(genislik), Renk.GRI))
    print()
    print(r("=" * min(87, genislik), Renk.SONUK))
    print()


# ------------------------------------------------------------------
# Internet kontrolu
# ------------------------------------------------------------------

def internet_var_mi(timeout=3) -> bool:
    try:
        socket.create_connection(("api.deepseek.com", 443), timeout=timeout)
        return True
    except OSError:
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=timeout)
            return True
        except OSError:
            return False


# ------------------------------------------------------------------
# Gizlilik filtresi - DeepSeek'e giden metinden kisisel/tanimlayici
# bilgileri (bilgisayar adi, kullanici adi, kullanici profil yolu) temizler
# ------------------------------------------------------------------

def gizlilik_filtrele(metin: str) -> str:
    if not metin:
        return metin
    bilgisayar_adi = os.environ.get("COMPUTERNAME", "")
    kullanici_adi = os.environ.get("USERNAME", "")

    temiz = metin
    if bilgisayar_adi:
        temiz = re.sub(re.escape(bilgisayar_adi), "[BILGISAYAR]", temiz, flags=re.IGNORECASE)
    if kullanici_adi:
        temiz = re.sub(re.escape(kullanici_adi), "[KULLANICI]", temiz, flags=re.IGNORECASE)
    # C:\Users\<adi>\... kaliplarini genel olarak maskele
    temiz = re.sub(r"C:\\Users\\[^\\\s]+", r"C:\\Users\\[KULLANICI]", temiz, flags=re.IGNORECASE)
    temiz = re.sub(r"[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+\.[A-Za-z]{2,}", "[EPOSTA]", temiz)
    return temiz


# ------------------------------------------------------------------
# ARAC KAYDI (tool registry)
# ------------------------------------------------------------------
# Her arac: aciklama, parametre semasi (DeepSeek function-calling icin),
# destructive bayragi ve gercek Python fonksiyonu.
#
# destructive=False -> sistemi degistirmez, onay istemeden otomatik calisir
# destructive=True  -> sistemi degistirir, HER ZAMAN onay istenir

def _calistir(komut, timeout=180):
    try:
        sonuc = subprocess.run(komut, capture_output=True, text=True,
                                timeout=timeout, shell=isinstance(komut, str))
        cikti = (sonuc.stdout or "") + ("\n" + sonuc.stderr if sonuc.stderr else "")
        return cikti.strip()[-4000:] or "(cikti yok)"
    except subprocess.TimeoutExpired:
        return "(islem zaman asimina ugradi)"
    except Exception as e:
        return f"(hata: {e})"


def _ps(betik, timeout=180):
    """Bir PowerShell betigini calistirir (profil yuklemeden, betik politikasina takilmadan)."""
    return _calistir(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", betik], timeout=timeout)


# AI'nin gonderdigi parametreler komutlarin icine yazildigi icin yalnizca guvenli
# karakterlere izin verilir; aksi halde "servis adi" yerine bir komut gonderilip
# onaysiz calistirilabilirdi.
_GUVENLI_AD = re.compile(r"^[A-Za-z0-9 _.\-]{1,64}$")
_GUVENLI_SURUCU = re.compile(r"^[A-Za-z]:$")


def _guvenli(deger, desen, varsayilan=""):
    deger = str(deger or "").strip()
    return deger if deger and desen.match(deger) else varsayilan


def _c_bos_alan_gb():
    try:
        cikti = _ps("[math]::Round((Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='C:'\").FreeSpace/1GB,2)", timeout=30)
        return float(cikti.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None


# ---------------- salt okunur teshis araclari ----------------

def arac_disk_durumu(params):
    # wmic Windows 11 24H2'de kaldirildi; CIM her surumde calisir.
    return _ps("Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | "
               "Select-Object DeviceID,@{n='BoyutGB';e={[math]::Round($_.Size/1GB,1)}},"
               "@{n='BosGB';e={[math]::Round($_.FreeSpace/1GB,1)}},"
               "@{n='Doluluk%';e={[math]::Round(100-($_.FreeSpace/$_.Size*100))}} | Format-Table -AutoSize | Out-String")


def arac_event_log(params):
    adet = int(params.get("adet", 15)) if isinstance(params, dict) and str(params.get("adet", "15")).isdigit() else 15
    adet = max(1, min(adet, 50))
    # Level=2 (Hata) dogrudan sorgulanir; once son N kaydi alip sonra suzmek cok az hata gosteriyordu.
    return _ps(f"Get-WinEvent -FilterHashtable @{{LogName='System'; Level=2}} -MaxEvents {adet} -ErrorAction SilentlyContinue | "
               "Select-Object TimeCreated,Id,ProviderName | Format-Table -AutoSize | Out-String")


def arac_servis_durumu(params):
    servis_adi = _guvenli((params or {}).get("servis_adi"), _GUVENLI_AD)
    if servis_adi:
        return _ps(f"Get-Service -Name '{servis_adi}' -ErrorAction SilentlyContinue | Format-List | Out-String")
    return _ps("Get-Service | Where-Object {$_.Status -eq 'Stopped' -and $_.StartType -eq 'Automatic'} | "
               "Select-Object Name,DisplayName,Status | Format-Table -AutoSize | Out-String")


def arac_baslangic_programlari(params):
    return _ps("Get-CimInstance Win32_StartupCommand | Select-Object Name,Command,Location | Format-Table -AutoSize | Out-String")


def arac_ag_durumu(params):
    return _calistir(["ipconfig", "/all"])


def arac_kaynak_kullanimi(params):
    # Get-Process'in CPU alani toplam calisma suresidir; anlik kullanim icin performans sayaclari okunur.
    return _ps(
        "$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; "
        "$os = Get-CimInstance Win32_OperatingSystem; "
        "$kul = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory)/1MB,2); "
        "$top = [math]::Round($os.TotalVisibleMemorySize/1MB,2); "
        "Write-Output \"CPU kullanimi: %$cpu\"; Write-Output \"RAM kullanimi: $kul GB / $top GB\"; "
        "Write-Output '--- Su an en cok CPU kullanan 5 surec ---'; "
        "Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | Where-Object {$_.Name -notin '_Total','Idle'} | "
        "Sort-Object PercentProcessorTime -Descending | Select-Object -First 5 Name,PercentProcessorTime | Format-Table -AutoSize | Out-String; "
        "Write-Output '--- En cok RAM kullanan 5 surec ---'; "
        "Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 5 Name,@{n='RAM_MB';e={[math]::Round($_.WorkingSet64/1MB)}} | Format-Table -AutoSize | Out-String")


def arac_hiz_raporu(params):
    """Eski bir bilgisayarin neden yavas oldugunu tek bakista gosteren ozet."""
    return _ps(
        "$os = Get-CimInstance Win32_OperatingSystem; $cs = Get-CimInstance Win32_ComputerSystem; "
        "$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1; "
        "Write-Output ('Windows   : ' + $os.Caption + ' (' + $os.Version + ')'); "
        "Write-Output ('Islemci   : ' + $cpu.Name.Trim() + ', ' + $cpu.NumberOfCores + ' cekirdek'); "
        "Write-Output ('RAM       : ' + [math]::Round($cs.TotalPhysicalMemory/1GB,1) + ' GB'); "
        "$up = (Get-Date) - $os.LastBootUpTime; Write-Output ('Acik kalma: ' + [int]$up.TotalDays + ' gun ' + $up.Hours + ' saat (uzun sure yeniden baslatilmadiysa yavaslar)'); "
        "Write-Output '--- Diskler (HDD ise SSD en buyuk hiz farkini yaratir) ---'; "
        "Get-PhysicalDisk | Select-Object FriendlyName,MediaType,@{n='BoyutGB';e={[math]::Round($_.Size/1GB)}},HealthStatus | Format-Table -AutoSize | Out-String; "
        "$c = Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='C:'\"; "
        "Write-Output ('C: bos alan: ' + [math]::Round($c.FreeSpace/1GB,1) + ' GB / ' + [math]::Round($c.Size/1GB,1) + ' GB'); "
        "$bas = @(Get-CimInstance Win32_StartupCommand).Count; Write-Output ('Acilista calisan program sayisi: ' + $bas); "
        "Write-Output ('Guc plani: ' + ((powercfg /getactivescheme) -replace '.*\\((.*)\\).*','$1')); "
        "$vfx = (Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects' -ErrorAction SilentlyContinue).VisualFXSetting; "
        "Write-Output ('Gorsel efektler: ' + $(if ($vfx -eq 2) {'performans icin ayarli'} else {'varsayilan (eski PC icin agir olabilir)'})); "
        "$tmp = (Get-ChildItem $env:TEMP -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum; "
        "Write-Output ('Gecici dosyalar (kullanici): ' + [math]::Round($tmp/1MB) + ' MB')",
        timeout=120)


def arac_disk_sagligi(params):
    return _ps(
        "Get-PhysicalDisk | Select-Object FriendlyName,MediaType,HealthStatus,OperationalStatus | Format-Table -AutoSize | Out-String; "
        "Get-PhysicalDisk | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue | "
        "Select-Object DeviceId,Temperature,Wear,ReadErrorsTotal,WriteErrorsTotal,PowerOnHours | Format-Table -AutoSize | Out-String", timeout=60)


def arac_surucu_sorunlari(params):
    return _ps("$s = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object {$_.Status -ne 'OK'}; "
               "if ($s) { $s | Select-Object Status,Class,FriendlyName | Format-Table -AutoSize | Out-String } "
               "else { 'Sorunlu (unlemli) aygit bulunmadi.' }", timeout=60)


# ---------------- sistemi degistiren onarim / hizlandirma araclari ----------------

def arac_sfc_scan(params):
    return _calistir(["sfc", "/scannow"], timeout=1200)


def arac_dism_repair(params):
    return _calistir(["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"], timeout=1800)


def arac_dns_flush(params):
    return _calistir(["ipconfig", "/flushdns"])


def arac_ip_renew(params):
    _calistir(["ipconfig", "/release"])
    return _calistir(["ipconfig", "/renew"])


def arac_disk_temizligi(params):
    """Gercekten yer acar: gecici klasorler, geri donusum kutusu ve Disk Temizligi'nin
    tum kategorileri. ('cleanmgr /sagerun:1' onceden /sageset:1 ayari yapilmadiysa hicbir sey silmiyordu.)"""
    once = _c_bos_alan_gb()
    cikti = _ps(
        "foreach ($k in @($env:TEMP, \"$env:WINDIR\\Temp\")) { Get-ChildItem -Path $k -Force -ErrorAction SilentlyContinue | "
        "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue }; "
        "Clear-RecycleBin -Force -ErrorAction SilentlyContinue; "
        "$yol = 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VolumeCaches'; "
        "Get-ChildItem $yol -ErrorAction SilentlyContinue | ForEach-Object { "
        "New-ItemProperty -Path $_.PSPath -Name StateFlags0099 -Value 2 -PropertyType DWord -Force -ErrorAction SilentlyContinue | Out-Null }; "
        "Start-Process cleanmgr -ArgumentList '/sagerun:99' -Wait; "
        "Write-Output 'Gecici dosyalar, geri donusum kutusu ve Disk Temizligi kategorileri temizlendi.'", timeout=1800)
    sonra = _c_bos_alan_gb()
    if once is not None and sonra is not None:
        cikti += f"\nC: bos alan: {once} GB -> {sonra} GB (acilan: {round(sonra - once, 2)} GB)"
    return cikti


def arac_yazici_kuyrugu_temizle(params):
    return _ps("Stop-Service -Name Spooler -Force; "
               "Remove-Item -Path 'C:\\Windows\\System32\\spool\\PRINTERS\\*' -Force -ErrorAction SilentlyContinue; "
               "Start-Service -Name Spooler; Write-Output 'Yazdirma kuyrugu temizlendi ve Spooler servisi yeniden baslatildi.'", timeout=60)


def arac_chkdsk(params):
    surucu = _guvenli((params or {}).get("surucu"), _GUVENLI_SURUCU, "C:")
    # /scan cevrimici, salt taramadir; tam onarim (/f /r) yeniden baslatma ister, onu teknisyen ayrica yapar.
    return _calistir(["chkdsk", surucu, "/scan"], timeout=1200)


def arac_windows_update_sifirla(params):
    return _ps("Stop-Service -Name wuauserv,bits,cryptsvc -Force -ErrorAction SilentlyContinue; "
               "Rename-Item -Path 'C:\\Windows\\SoftwareDistribution' -NewName ('SoftwareDistribution.bak' + (Get-Date -Format yyyyMMddHHmm)) -ErrorAction SilentlyContinue; "
               "Rename-Item -Path 'C:\\Windows\\System32\\catroot2' -NewName ('catroot2.bak' + (Get-Date -Format yyyyMMddHHmm)) -ErrorAction SilentlyContinue; "
               "Start-Service -Name wuauserv,bits,cryptsvc -ErrorAction SilentlyContinue; "
               "Write-Output 'Windows Update bilesenleri sifirlandi. Degisikligin etkili olmasi icin PC yeniden baslatilmali.'", timeout=120)


def arac_windows_update_tara(params):
    return _ps("Start-Process 'ms-settings:windowsupdate'; "
               "Start-Process usoclient -ArgumentList 'StartInteractiveScan' -ErrorAction SilentlyContinue; "
               "Write-Output 'Windows Update taramasi baslatildi ve ayarlar sayfasi acildi. Bulunan guncellemeleri oradan yukleyin.'", timeout=60)


def arac_geri_yukleme_noktasi(params):
    aciklama = _guvenli((params or {}).get("aciklama"), _GUVENLI_AD, "Teknik Destek Terminali Onarim Oncesi")
    # Windows varsayilan olarak 24 saatte birden fazla nokta olusturmaz; bu siniri bu islem icin kaldiriyoruz.
    return _ps("Enable-ComputerRestore -Drive 'C:\\' -ErrorAction SilentlyContinue; "
               "New-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\SystemRestore' "
               "-Name SystemRestorePointCreationFrequency -Value 0 -PropertyType DWord -Force -ErrorAction SilentlyContinue | Out-Null; "
               f"Checkpoint-Computer -Description '{aciklama}' -RestorePointType 'MODIFY_SETTINGS'; "
               "Write-Output 'Geri yukleme noktasi olusturuldu.'", timeout=300)


def arac_defender_tarama(params):
    tur = (params or {}).get("tur", "Quick")
    if tur not in ("Quick", "Full"):
        tur = "Quick"
    return _ps(f"Update-MpSignature -ErrorAction SilentlyContinue; Start-MpScan -ScanType {tur}; "
               "Write-Output 'Tarama tamamlandi. Sonuclar Windows Guvenligi uygulamasinda.'", timeout=7200 if tur == "Full" else 1200)


def arac_baslangic_programi_kapat(params):
    """Bir acilis programini Gorev Yoneticisi'nin yaptigi gibi devre disi birakir (silmez, geri acilabilir)."""
    ad = _guvenli((params or {}).get("program_adi"), _GUVENLI_AD)
    if not ad:
        return "Program adi gerekli (once 'baslangic_programlari' ile listeyi alin)."
    return _ps(
        f"$ad = '{ad}'; $bulundu = $false; "
        "foreach ($kok in @('HKCU','HKLM')) { "
        "  $run = \"${kok}:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\"; "
        "  if ((Get-ItemProperty $run -ErrorAction SilentlyContinue).PSObject.Properties.Name -contains $ad) { "
        "    $onay = \"${kok}:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\StartupApproved\\Run\"; "
        "    if (-not (Test-Path $onay)) { New-Item -Path $onay -Force | Out-Null }; "
        "    New-ItemProperty -Path $onay -Name $ad -PropertyType Binary -Value ([byte[]](3,0,0,0,0,0,0,0,0,0,0,0)) -Force | Out-Null; "
        "    $bulundu = $true } }; "
        "if ($bulundu) { \"'$ad' acilista calismayacak (Gorev Yoneticisi > Baslangic sekmesinden geri acilabilir).\" } "
        "else { \"'$ad' Run anahtarlarinda bulunamadi; Baslangic klasorundeyse Gorev Yoneticisi'nden kapatin.\" }")


def arac_guc_plani_yuksek(params):
    return _ps("$h = powercfg /list | Select-String 'High performance|Yuksek performans|Yüksek performans'; "
               "if (-not $h) { powercfg -duplicatescheme 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c | Out-Null }; "
               "powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c; "
               "Write-Output ('Etkin guc plani: ' + (powercfg /getactivescheme))")


def arac_gorsel_efekt_performans(params):
    return _ps("Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects' -Name VisualFXSetting -Value 2 -Type DWord; "
               "Set-ItemProperty -Path 'HKCU:\\Control Panel\\Desktop' -Name MenuShowDelay -Value '50'; "
               "Write-Output 'Gorsel efektler en iyi performansa ayarlandi. Tam etki icin oturumu kapatip acin.'")


def arac_uygulamalari_guncelle(params):
    return _calistir(["winget", "upgrade", "--all", "--silent", "--accept-package-agreements",
                      "--accept-source-agreements", "--disable-interactivity"], timeout=3600)


def arac_ag_sifirla(params):
    return _ps("netsh winsock reset; netsh int ip reset; ipconfig /flushdns; "
               "Write-Output 'Ag yigini sifirlandi. Yeniden baslatma gerekir.'")


ARAC_KAYDI = {
    # ---- salt okunur (onay istemez) ----
    "hiz_raporu": {"kategori": "teshis", "aciklama": "Yavasligin nedenlerini ozetler: Windows surumu, RAM, disk turu (HDD/SSD), bos alan, acilis programi sayisi, guc plani, gorsel efektler, gecici dosya boyutu (salt okunur).", "params": {}, "destructive": False, "fn": arac_hiz_raporu},
    "disk_durumu": {"kategori": "teshis", "aciklama": "Disklerin toplam/bos alanini ve doluluk oranini gosterir (salt okunur).", "params": {}, "destructive": False, "fn": arac_disk_durumu},
    "disk_sagligi": {"kategori": "teshis", "aciklama": "Fiziksel disklerin saglik durumu, sicaklik, asinma ve hata sayaclari (SMART) (salt okunur).", "params": {}, "destructive": False, "fn": arac_disk_sagligi},
    "event_log_oku": {"kategori": "teshis", "aciklama": "Windows Sistem gunlugundeki son hata kayitlarini okur (salt okunur).", "params": {"adet": "integer, opsiyonel, varsayilan 15"}, "destructive": False, "fn": arac_event_log},
    "servis_durumu": {"kategori": "teshis", "aciklama": "Belirli bir Windows servisinin durumunu, ya da calismayan otomatik servisleri listeler (salt okunur).", "params": {"servis_adi": "string, opsiyonel"}, "destructive": False, "fn": arac_servis_durumu},
    "baslangic_programlari": {"kategori": "teshis", "aciklama": "Windows acilisinda otomatik calisan programlari listeler (salt okunur).", "params": {}, "destructive": False, "fn": arac_baslangic_programlari},
    "kaynak_kullanimi": {"kategori": "teshis", "aciklama": "Anlik CPU/RAM kullanimi ve su an en cok CPU ve RAM kullanan surecler (salt okunur).", "params": {}, "destructive": False, "fn": arac_kaynak_kullanimi},
    "surucu_sorunlari": {"kategori": "teshis", "aciklama": "Aygit Yoneticisi'nde sorunlu/unlemli aygitlari listeler (salt okunur).", "params": {}, "destructive": False, "fn": arac_surucu_sorunlari},
    "ag_durumu": {"kategori": "ag", "aciklama": "Ag adaptorlerinin IP/DNS/durumunu gosterir (salt okunur).", "params": {}, "destructive": False, "fn": arac_ag_durumu},
    # ---- sistemi degistirir (her zaman onay ister) ----
    "geri_yukleme_noktasi": {"kategori": "guvenlik", "aciklama": "Onarimdan once sistem geri yukleme noktasi olusturur, risk azaltir.", "params": {"aciklama": "string, opsiyonel"}, "destructive": True, "fn": arac_geri_yukleme_noktasi},
    "disk_temizligi": {"kategori": "hizlandirma", "aciklama": "Gecici dosyalari, geri donusum kutusunu ve Disk Temizligi kategorilerini temizler, acilan alani soyler.", "params": {}, "destructive": True, "fn": arac_disk_temizligi},
    "baslangic_programi_kapat": {"kategori": "hizlandirma", "aciklama": "Bir acilis programini devre disi birakir (silmez, Gorev Yoneticisi'nden geri acilabilir).", "params": {"program_adi": "string, zorunlu, baslangic_programlari listesindeki ad"}, "destructive": True, "fn": arac_baslangic_programi_kapat},
    "guc_plani_yuksek": {"kategori": "hizlandirma", "aciklama": "Guc planini Yuksek Performans yapar (masaustu PC icin; dizustunde pili daha hizli tuketir).", "params": {}, "destructive": True, "fn": arac_guc_plani_yuksek},
    "gorsel_efekt_performans": {"kategori": "hizlandirma", "aciklama": "Animasyon ve gorsel efektleri kapatip en iyi performansa ayarlar (eski PC'lerde belirgin hizlanma).", "params": {}, "destructive": True, "fn": arac_gorsel_efekt_performans},
    "uygulamalari_guncelle": {"kategori": "hizlandirma", "aciklama": "Yuklu programlarin hepsini winget ile gunceller (internet gerekir, uzun surebilir).", "params": {}, "destructive": True, "fn": arac_uygulamalari_guncelle},
    "windows_update_tara": {"kategori": "sistem", "aciklama": "Windows Update taramasini baslatir ve ayarlar sayfasini acar.", "params": {}, "destructive": True, "fn": arac_windows_update_tara},
    "defender_tarama": {"kategori": "guvenlik", "aciklama": "Virus tanimlarini gunceller ve Windows Defender ile hizli (Quick) veya tam (Full) tarama yapar.", "params": {"tur": "string, opsiyonel, 'Quick' veya 'Full', varsayilan 'Quick'"}, "destructive": True, "fn": arac_defender_tarama},
    "sfc_tarama": {"kategori": "sistem", "aciklama": "sfc /scannow calistirir, bozuk sistem dosyalarini onarir.", "params": {}, "destructive": True, "fn": arac_sfc_scan},
    "dism_onarim": {"kategori": "sistem", "aciklama": "DISM /RestoreHealth calistirir, Windows bilesen deposunu onarir.", "params": {}, "destructive": True, "fn": arac_dism_repair},
    "disk_kontrolu": {"kategori": "disk", "aciklama": "chkdsk /scan ile diskte hata taramasi yapar (cevrimici tarama, yeniden baslatma gerektirmez).", "params": {"surucu": "string, opsiyonel, varsayilan 'C:'"}, "destructive": True, "fn": arac_chkdsk},
    "dns_temizle": {"kategori": "ag", "aciklama": "DNS onbellegini temizler (ipconfig /flushdns).", "params": {}, "destructive": True, "fn": arac_dns_flush},
    "ip_yenile": {"kategori": "ag", "aciklama": "IP adresini yeniler (ipconfig /release + /renew).", "params": {}, "destructive": True, "fn": arac_ip_renew},
    "ag_sifirla": {"kategori": "ag", "aciklama": "Winsock ve TCP/IP yiginini sifirlar (inatci internet sorunlari icin, yeniden baslatma gerekir).", "params": {}, "destructive": True, "fn": arac_ag_sifirla},
    "yazici_kuyrugu_temizle": {"kategori": "sistem", "aciklama": "Yazdirma kuyrugunu temizler ve Spooler servisini yeniden baslatir.", "params": {}, "destructive": True, "fn": arac_yazici_kuyrugu_temizle},
    "windows_update_sifirla": {"kategori": "sistem", "aciklama": "Windows Update bilesenlerini (SoftwareDistribution, catroot2) sifirlar. Yeniden baslatma gerektirir.", "params": {}, "destructive": True, "fn": arac_windows_update_sifirla},
}

# Araclarin "hizli" menusunde gruplandigi kategoriler - (baslik, renk).
# Siralama burada belirlenir: once salt okunur teshisler, sonra onarim/
# hizlandirma kategorileri.
KATEGORILER = {
    "teshis": ("TESHIS (salt okunur, direkt calisir)", Renk.CYAN),
    "hizlandirma": ("HIZLANDIRMA", Renk.YESIL),
    "guvenlik": ("GUVENLIK", Renk.SARI),
    "ag": ("AG", Renk.MAVI),
    "disk": ("DISK", Renk.MOR),
    "sistem": ("SISTEM ONARIMI", Renk.KIRMIZI),
}


def _deepseek_tools_semasi():
    """ARAC_KAYDI'ni DeepSeek'in function-calling formatina cevirir."""
    tools = []
    for ad, bilgi in ARAC_KAYDI.items():
        ozellikler = {}
        for p_ad, p_aciklama in bilgi["params"].items():
            p_tip = "integer" if "integer" in p_aciklama else "string"
            ozellikler[p_ad] = {"type": p_tip, "description": p_aciklama}
        tools.append({
            "type": "function",
            "function": {
                "name": ad,
                "description": bilgi["aciklama"] + (" [SISTEMI DEGISTIRIR - kullanici onayi gerekir]" if bilgi["destructive"] else " [salt okunur]"),
                "parameters": {
                    "type": "object",
                    "properties": ozellikler,
                    "required": [],
                },
            },
        })
    return tools


# Oturum boyunca cagrilan araclarin ve sonuclarin dokumu - oturum sonu
# ozet raporu icin kullanilir.
OTURUM_GECMISI = []


def arac_cagir(ad: str, params: dict) -> str:
    """Bir araci guvenlik kurallarina gore calistirir (onay dahil)."""
    if ad not in ARAC_KAYDI:
        return f"HATA: '{ad}' adinda bir arac yok / beyaz listede degil."

    bilgi = ARAC_KAYDI[ad]
    if bilgi["destructive"]:
        print(r(f"\n[Onarim araci]: {ad}", Renk.KALIN, Renk.SARI) + f" - {bilgi['aciklama']}")
        if os.name == "nt" and not yonetici_mi():
            print(r("  UYARI: Program yonetici olarak calismiyor; bu islem basarisiz olabilir.", Renk.KIRMIZI))
        onay = input(r("  Calistirilsin mi? [E/h]: ", Renk.SARI)).strip().lower()
        if onay not in ("e", "evet", "y", "yes"):
            log(f"REDDEDILDI (AI araci): {ad}")
            OTURUM_GECMISI.append({
                "zaman": datetime.now().strftime("%H:%M:%S"), "arac": ad,
                "durum": "REDDEDILDI", "sonuc": "-",
            })
            return "Kullanici bu islemi onaylamadi, calistirilmadi."
        log(f"ONAYLANDI (AI araci): {ad} params={params}")
    else:
        log(f"Otomatik calistirildi (salt okunur): {ad} params={params}")

    try:
        sonuc = bilgi["fn"](params or {})
        log(f"Sonuc ({ad}): {sonuc[:500]}")
        OTURUM_GECMISI.append({
            "zaman": datetime.now().strftime("%H:%M:%S"), "arac": ad,
            "durum": "TAMAMLANDI", "sonuc": sonuc[:1000],
        })
        return sonuc
    except Exception as e:
        log(f"Arac hatasi ({ad}): {e}")
        OTURUM_GECMISI.append({
            "zaman": datetime.now().strftime("%H:%M:%S"), "arac": ad,
            "durum": "HATA", "sonuc": str(e),
        })
        return f"Arac calistirilirken hata olustu: {e}"


# ------------------------------------------------------------------
# Sistem ozeti (baslangic baglami icin, PII filtrelenmis)
# ------------------------------------------------------------------

def sistem_ozeti() -> dict:
    ozet = {
        "isletim_sistemi": platform.platform(),
        "islemci": platform.processor(),
        "python_mimari": platform.architecture()[0],
    }
    ozet["disk_durumu"] = gizlilik_filtrele(arac_disk_durumu({}))
    return ozet


# ------------------------------------------------------------------
# DeepSeek API - Tool-calling ajan dongusu
# ------------------------------------------------------------------

def _deepseek_istek(messages, tools):
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "tools": tools,
        "temperature": 0.2,
        "stream": False,
    }
    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def deepseek_ajan(kullanici_sorunu: str, ozet: dict) -> str:
    sistem_mesaji = (
        "Sen bir Windows sistem teknisyeni yardimcisisin. Sahada kullanilan "
        "tasinabilir bir teknik destek terminali (USB'den calisan) uzerinden "
        "calisiyorsun. "
        "Turkce konus. Elinde gercek sistem bilgisi toplamak ve onarim "
        "yapmak icin ARACLAR (tools) var: disk/servis/event-log okuma gibi "
        "salt okunur araclari istedigin kadar, geregi kadar cagirabilirsin. "
        "sfc_tarama, dism_onarim, disk_kontrolu, windows_update_sifirla gibi "
        "SISTEMI DEGISTIREN araclari cagirdiginda kullaniciya onay sorulacagini "
        "bil - bu normal, sen yine de gerekli gordugun araci cagir. Sistemi "
        "kalici olarak degistirecek riskli bir onarima (sfc_tarama, "
        "dism_onarim, windows_update_sifirla, disk_kontrolu) baslamadan once, "
        "uygunsa once geri_yukleme_noktasi aracini cagirmayi dikkate al. "
        "Yavaslik sikayetlerinde once hiz_raporu aracini cagir; HDD, az RAM, dolu disk, "
        "cok sayida acilis programi gibi nedenleri bul ve buna gore disk_temizligi, "
        "baslangic_programi_kapat, gorsel_efekt_performans, guc_plani_yuksek, "
        "uygulamalari_guncelle gibi araclari oner. Donanim kaynakli yavaslikta (HDD, 4 GB "
        "alti RAM) SSD veya RAM yukseltmesini acikca soyle. "
        "Once gerekiyorsa 1-2 salt okunur aracla teshis bilgisi topla, sonra "
        "kisa ve net bir aciklama ile hangi onarimi onerdigini soyle ve "
        "gerekiyorsa ilgili onarim aracini cagir. Gereksiz yere cok fazla "
        "arac cagirma. Riskli islemlerde (veri kaybi, yeniden baslatma "
        "gerektirme) kullaniciyi metninde de uyar."
    )
    kullanici_mesaji = (
        f"Sorun: {gizlilik_filtrele(kullanici_sorunu)}\n\n"
        f"Sistem bilgisi:\n{json.dumps(ozet, ensure_ascii=False, indent=2)}"
    )

    messages = [
        {"role": "system", "content": sistem_mesaji},
        {"role": "user", "content": kullanici_mesaji},
    ]
    tools = _deepseek_tools_semasi()

    for tur in range(MAX_ARAC_TURU):
        try:
            data = _deepseek_istek(messages, tools)
        except urllib.error.HTTPError as e:
            return f"[DeepSeek API hatasi: {e.code} {e.reason}] Yerel teshis moduna geciliyor.\n\n" + yerel_teshis(kullanici_sorunu)
        except Exception as e:
            return f"[DeepSeek API'ye ulasilamadi: {e}] Yerel teshis moduna geciliyor.\n\n" + yerel_teshis(kullanici_sorunu)

        secim = data["choices"][0]
        mesaj = secim["message"]
        tool_calls = mesaj.get("tool_calls")

        if not tool_calls:
            return mesaj.get("content", "(bos cevap)")

        messages.append(mesaj)
        for tc in tool_calls:
            fn_ad = tc["function"]["name"]
            try:
                fn_params = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                fn_params = {}

            sonuc = arac_cagir(fn_ad, fn_params)
            sonuc_filtreli = gizlilik_filtrele(sonuc)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": sonuc_filtreli,
            })

    return "AI cok fazla arac cagirdi, islem durduruldu. Elle 'hizli' menusunu deneyebilirsin."


# ------------------------------------------------------------------
# Yerel kural tabanli (heuristic) teshis motoru - internet yokken
# ------------------------------------------------------------------

ANAHTAR_KELIME_KURALLARI = [
    (["yavas", "donuyor", "kasiyor", "takiliyor", "eski", "hizlandir"], [
        "'hizlandir' yaz: hiz raporu cikarir ve hizlandirma adimlarini tek tek onayinla uygular.",
        "Baslangic programlarini kontrol et: msconfig veya Gorev Yoneticisi > "
        "Baslangic sekmesinden gereksiz programlari kapat.",
        "Disk doluluk oranini kontrol et (C: suruculer %90 uzeriyse yavaslar).",
        "Disk Temizligi (cleanmgr) calistir, gecici dosyalari sil.",
        "Gorev Yoneticisi'nde CPU/RAM/Disk kullanimini en yuksek olan "
        "surecleri kontrol et.",
        "Virus/malware taramasi yap (Windows Defender tam tarama).",
    ]),
    (["internet", "wifi", "ag", "baglanamiyor", "baglanti yok"], [
        "ipconfig /release && ipconfig /renew ile IP yenile.",
        "ipconfig /flushdns ile DNS onbellegini temizle.",
        "netsh winsock reset calistirip bilgisayari yeniden baslat.",
        "Ag adaptoru surucusunu Aygit Yoneticisi'nden guncelle/yeniden yukle.",
        "Router/modem'i yeniden baslat.",
    ]),
    (["mavi ekran", "bsod", "crash", "kapaniyor", "yeniden basliyor"], [
        "Event Viewer > Windows Logs > System'den son BSOD hata kodunu "
        "(Stop code) bul.",
        "sfc /scannow ve DISM /Online /Cleanup-Image /RestoreHealth calistir.",
        "RAM testi yap (Windows Memory Diagnostic - mdsched.exe).",
        "Son yuklenen surucu/program varsa kaldir veya geri al.",
        "Guncel olmayan donanim surucularini guncelle.",
    ]),
    (["acilmiyor", "boot", "baslamiyor", "siyah ekran"], [
        "Guvenli Modda (Safe Mode) acilmayi dene (F8 / Shift+Restart).",
        "Baslangic Onarimi'ni (Startup Repair) Windows kurulum USB'si ile dene.",
        "bootrec /fixmbr, bootrec /fixboot, bootrec /rebuildbcd komutlarini "
        "Windows kurtarma ortaminda dene.",
        "Disk baglantilarini (SATA/guc kablosu) fiziksel olarak kontrol et.",
    ]),
    (["disk dolu", "yer yok", "alan yok"], [
        "Disk Temizligi (cleanmgr /sageset:1) calistir.",
        "Gecici dosyalari (%TEMP%, C:\\Windows\\Temp) temizle.",
        "Buyuk dosyalari bulmak icin WinDirStat benzeri bir arac veya "
        "'Get-ChildItem -Recurse | Sort Length -Descending' kullan.",
        "Geri Donusum Kutusu'nu bosalt.",
        "Kullanilmayan programlari kaldir (Denetim Masasi > Program Kaldir).",
    ]),
    (["yazici", "printer", "yazdirmiyor"], [
        "Yazdirma kuyrugunu temizle ('hizli' menusunden 'Yazici kuyrugu "
        "temizle' secenegini kullan).",
        "Yazici surucusunu kaldirip yeniden yukle.",
        "Yazicinin agda/USB'de dogru algilandigini kontrol et.",
    ]),
    (["update", "guncelleme", "yuklenmiyor"], [
        "'hizli' menusunden 'Windows Update sifirla' secenegini dene.",
        "Disk alaninin yeterli oldugunu kontrol et (update icin en az 10-20GB).",
        "Windows Update sorun gidericisini calistir (Ayarlar > Sorun Giderme).",
    ]),
    (["disk hata", "bad sector", "s.m.a.r.t", "smart"], [
        "'hizli' menusunden 'Disk kontrolu (chkdsk)' secenegini dene.",
        "Diskin fiziksel SATA/guc baglantisini kontrol et.",
        "Onemli veriyi hemen yedekle, SMART hatasi disk arizasina isaret edebilir.",
    ]),
]


def yerel_teshis(sorun_metni: str) -> str:
    sorun_kucuk = sorun_metni.lower()
    eslesen = []
    for anahtarlar, oneriler in ANAHTAR_KELIME_KURALLARI:
        if any(a in sorun_kucuk for a in anahtarlar):
            eslesen.append(oneriler)

    if not eslesen:
        return (
            "Girdigin aciklamada bilinen bir anahtar kelime eslesmedi.\n"
            "Genel teshis adimlari:\n"
            "  1. Olay Goruntuleyici (eventvwr.msc) > Windows Loglari > "
            "Sistem/Uygulama'da son hatalara bak.\n"
            "  2. sfc /scannow ile sistem dosyalarini dogrula.\n"
            "  3. Windows Update'in guncel oldugunu kontrol et.\n"
            "  4. Son yuklenen program/surucu varsa kaldirmayi dene.\n"
        )

    cikti = ["Yerel teshis motoru (internet yok) - olasi nedenler ve adimlar:\n"]
    sayac = 1
    for oneriler in eslesen:
        for oneri in oneriler:
            cikti.append(f"  {sayac}. {oneri}")
            sayac += 1
    return "\n".join(cikti)


# ------------------------------------------------------------------
# Hizli onarim menusu (manuel, AI'siz) - ARAC_KAYDI'ndaki destructive
# araclarin tamamini kullanir, boylece tek bir yerden yonetilir
# ------------------------------------------------------------------

def hizli_komut_menusu():
    """Butun araclari (salt okunur + onarim/hizlandirma) kategorilere
    ayrilmis, renkli, numarali tek bir listede gosterir. Salt okunur
    araclar hemen calisir; digerleri arac_cagir() icindeki onay adimindan
    gecer. Siralama ARAC_KAYDI'nin tek kaynagindan turer, baska yerde
    ayrica tutulmaz."""
    sirali = []
    print(r("\n  TUM ARACLAR", Renk.KALIN, Renk.BEYAZ))
    for kat_id, (kat_baslik, kat_renk) in KATEGORILER.items():
        kat_araclar = [(ad, b) for ad, b in ARAC_KAYDI.items() if b["kategori"] == kat_id]
        if not kat_araclar:
            continue
        print(r(f"\n  -- {kat_baslik} --", Renk.KALIN, kat_renk))
        for ad, bilgi in kat_araclar:
            sirali.append((ad, bilgi))
            etiket = r("[salt okunur]", Renk.GRI) if not bilgi["destructive"] else r("[onay gerekir]", Renk.SARI)
            print(f"   {r(f'[{len(sirali)}]', kat_renk)} {bilgi['aciklama']} {etiket}")
    print(f"\n   {r('[0]', Renk.GRI)} Geri don")
    secim = input(r("\nSecim: ", Renk.KALIN)).strip()
    if secim == "0" or not secim.isdigit():
        return
    idx = int(secim) - 1
    if idx < 0 or idx >= len(sirali):
        print(r("Gecersiz secim.", Renk.KIRMIZI))
        return
    ad, bilgi = sirali[idx]
    params = {}
    for p_ad, p_aciklama in bilgi["params"].items():
        if "zorunlu" in p_aciklama:
            if ad == "baslangic_programi_kapat":
                print(arac_cagir("baslangic_programlari", {}))
            params[p_ad] = input(f"  {p_ad} ({p_aciklama}): ").strip()
        elif "opsiyonel" in p_aciklama:
            deger = input(f"  {p_ad} ({p_aciklama}, bos=varsayilan): ").strip()
            if deger:
                params[p_ad] = deger
    sonuc = arac_cagir(ad, params)
    print("\n" + sonuc)


# ------------------------------------------------------------------
# Sik sorun kisayollari - teknisyen yazmadan 1-9 ile direkt secebilsin
# ------------------------------------------------------------------

SIK_SORUNLAR = [
    "Bilgisayar cok yavas acilyor ve kasiyor",
    "Internet/Wifi baglantisi yok veya kopuyor",
    "Mavi ekran hatasi aliyor / aniden kapaniyor",
    "Bilgisayar acilmiyor / siyah ekranda kaliyor",
    "Disk alani doldu, 'yer yok' hatasi aliyor",
    "Yazici yazdirmiyor / kuyrukta takili kaliyor",
    "Windows Update yuklenmiyor / hata veriyor",
    "Program/uygulama acilmiyor veya donuyor",
    "Virus/malware supheli davranis var",
]


def sik_sorunlar_menusu():
    print(r("\nSik karsilasilan sorunlar:", Renk.KALIN, Renk.CYAN))
    for i, soru in enumerate(SIK_SORUNLAR, 1):
        print(f"  {r(f'[{i}]', Renk.CYAN)} {soru}")
    print(f"  {r('[0]', Renk.GRI)} Geri don (kendi cumlemi yazacagim)")
    secim = input(r("Secim: ", Renk.KALIN)).strip()
    if secim == "0" or not secim.isdigit():
        return None
    idx = int(secim) - 1
    if 0 <= idx < len(SIK_SORUNLAR):
        return SIK_SORUNLAR[idx]
    print(r("Gecersiz secim.", Renk.KIRMIZI))
    return None


# ------------------------------------------------------------------
# Demirbas / PC kayit defteri - USB uzerinde birikir, envanter icin
# ------------------------------------------------------------------

def demirbas_kaydet(demirbas_no: str, sorun: str, sonuc_ozeti: str):
    yeni_dosya = not os.path.exists(KAYIT_DEFTERI_CSV)
    try:
        with open(KAYIT_DEFTERI_CSV, "a", newline="", encoding="utf-8-sig") as f:
            yazici = csv.writer(f)
            if yeni_dosya:
                yazici.writerow(["Tarih", "Saat", "Demirbas/PC", "Sorun", "Ozet", "Mod"])
            yazici.writerow([
                datetime.now().strftime("%Y-%m-%d"),
                datetime.now().strftime("%H:%M:%S"),
                demirbas_no or "(belirtilmedi)",
                sorun,
                sonuc_ozeti[:300].replace("\n", " "),
                "DeepSeek" if (DEEPSEEK_API_KEY and "BURAYA" not in DEEPSEEK_API_KEY) else "Yerel",
            ])
        log(f"Demirbas kayit defterine eklendi: {demirbas_no}")
    except Exception as e:
        log(f"Demirbas kayit defteri yazilamadi: {e}")


# ------------------------------------------------------------------
# Oturum sonu ozet raporu - hem log klasorune hem USB'ye (raporlar/)
# okunabilir bir .txt olarak yazilir
# ------------------------------------------------------------------

def ozet_rapor_yaz(demirbas_no: str, gorusme_ozeti: list):
    rapor_yolu = os.path.join(RAPOR_DIR, f"rapor_{datetime.now():%Y%m%d_%H%M%S}.txt")
    try:
        with open(rapor_yolu, "w", encoding="utf-8") as f:
            f.write(f"{MARKA} - OTURUM OZETI\n")
            f.write("=" * 55 + "\n")
            f.write(f"Tarih/Saat : {datetime.now():%Y-%m-%d %H:%M:%S}\n")
            f.write(f"Demirbas/PC: {demirbas_no or '(belirtilmedi)'}\n\n")

            f.write("-- Gorusulen sorunlar ve cevaplar --\n\n")
            for i, kayit in enumerate(gorusme_ozeti, 1):
                f.write(f"[{i}] Sorun: {kayit['sorun']}\n")
                f.write(f"    Cevap : {kayit['cevap'][:1500]}\n\n")

            if OTURUM_GECMISI:
                f.write("-- Calistirilan araclar --\n\n")
                for kayit in OTURUM_GECMISI:
                    f.write(f"  [{kayit['zaman']}] {kayit['arac']} -> {kayit['durum']}\n")

            f.write("\nBu rapor otomatik olusturulmustur.\n")
        log(f"Ozet rapor yazildi: {rapor_yolu}")
        return rapor_yolu
    except Exception as e:
        log(f"Ozet rapor yazilamadi: {e}")
        return None


# ------------------------------------------------------------------
# Hizlandirma sihirbazi - eski/yavaslamis bir PC icin adim adim, her
# adimda onay isteyerek (AI'siz da calisir)
# ------------------------------------------------------------------

HIZLANDIRMA_ADIMLARI = [
    "geri_yukleme_noktasi",
    "disk_temizligi",
    "gorsel_efekt_performans",
    "guc_plani_yuksek",
    "uygulamalari_guncelle",
    "windows_update_tara",
    "defender_tarama",
]


BOLT_ICON = r"""
     __/|
     \ |
      \|
      /|
     / |
    /__|
"""


def hizlandirma_sihirbazi() -> str:
    print(r(BOLT_ICON, Renk.SARI))
    print(r("  HIZLANDIRMA SIHIRBAZI", Renk.KALIN, Renk.YESIL))
    print(r("  " + "=" * 50, Renk.SONUK))
    print("Once bu PC'nin neden yavas oldugunu ozetliyorum, sonra her adimi tek tek soruyorum.\n")
    rapor = arac_cagir("hiz_raporu", {})
    print(rapor)

    print(r("\n-- Acilista calisan programlar --", Renk.KALIN, Renk.CYAN))
    print(arac_cagir("baslangic_programlari", {}))
    secim = input(r("Acilista kapatilacak programlarin adlarini virgulle yaz (bos = atla): ", Renk.KALIN)).strip()
    for ad in [a.strip() for a in secim.split(",") if a.strip()]:
        print(arac_cagir("baslangic_programi_kapat", {"program_adi": ad}))

    dizustu = _ps("[bool](Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue)", timeout=30).strip().lower() == "true"
    yapilan = []
    for adim in HIZLANDIRMA_ADIMLARI:
        if adim == "guc_plani_yuksek" and dizustu:
            print(r("\n(Dizustu bilgisayar: Yuksek Performans guc plani pili hizli bitirecegi icin atlandi.)", Renk.GRI))
            continue
        sonuc = arac_cagir(adim, {})
        print(sonuc)
        if not sonuc.startswith("Kullanici bu islemi onaylamadi"):
            yapilan.append(adim)

    oneriler = []
    if "HDD" in rapor or "Unspecified" in rapor:
        oneriler.append("Disk HDD (ya da turu belirsiz) gorunuyor: SSD'ye gecmek en buyuk hiz farkini yaratir.")
    m = re.search(r"RAM\s*:\s*([\d.,]+)\s*GB", rapor)
    if m and float(m.group(1).replace(",", ".")) < 8:
        oneriler.append(f"RAM {m.group(1)} GB: 8 GB veya uzerine cikarmak belirgin hizlandirir.")
    oneriler.append("Bilgisayari simdi yeniden baslatin; yapilan ayarlarin bir kismi ancak yeniden baslatinca etkili olur.")

    ozet = "Hizlandirma sihirbazi - uygulanan adimlar: " + (", ".join(yapilan) or "yok") + "\n" + "\n".join("- " + o for o in oneriler)
    print("\n" + r("Ozet", Renk.KALIN, Renk.YESIL) + "\n" + ozet)
    return ozet


# ------------------------------------------------------------------
# Ana akis
# ------------------------------------------------------------------

def main():
    baslik()
    log("Terminal baslatildi.")

    if os.name == "nt" and not yonetici_mi():
        print(r("Bu program yonetici olarak calismiyor.", Renk.SARI) + " Onarim ve hizlandirma araclarinin")
        print("cogu (sfc, DISM, disk temizligi, guc plani, geri yukleme noktasi) yonetici ister.")
        if input(r("Yonetici olarak yeniden acilsin mi? [E/h]: ", Renk.KALIN)).strip().lower() in ("", "e", "evet", "y", "yes"):
            if yonetici_olarak_yeniden_ac():
                log("Yonetici olarak yeniden acildi, bu pencere kapaniyor.")
                return
            print(r("Yonetici olarak acilamadi; salt okunur teshis araclari yine calisir.\n", Renk.GRI))

    if os.path.exists(LOGO_PNG):
        logo_sec = input("Logoyu ayri pencerede acmak ister misin? [e/H]: ").strip().lower()
        if logo_sec in ("e", "evet", "y", "yes"):
            logo_ac()

    demirbas_no = input(r("Demirbas/PC adi ya da no (bos birakabilirsin): ", Renk.KALIN)).strip()
    log(f"Demirbas/PC: {demirbas_no or '(belirtilmedi)'}")

    online = internet_var_mi()
    if online:
        print(r("\nInternet baglantisi bulundu -> DeepSeek AI ajan modu aktif.", Renk.YESIL))
        print(r("(AI, gerektiginde teshis araclarini kendisi cagirir; sistemi", Renk.GRI))
        print(r(" degistiren her islem icin senden onay ister.)\n", Renk.GRI))
    else:
        print(r("\nInternet baglantisi yok -> Yerel teshis motoru calisacak.\n", Renk.SARI))

    gorusme_ozeti = []

    while True:
        print(r("-" * 60, Renk.SONUK))
        print("Karsilastigin sorunu kisaca yaz (orn: 'bilgisayar cok yavas')")
        print(r("Komutlar:", Renk.KALIN)
              + r(" 'hizlandir'", Renk.YESIL) + " = yavas PC'yi adim adim hizlandir,")
        print(r("          'liste'", Renk.CYAN) + " = sik sorun listesi,"
              + r(" 'hizli'", Renk.MOR) + " = tum araclar (kategorili menu),")
        print(r("          'cikis'", Renk.GRI) + " = programi kapat")
        sorun = input(r("\n> ", Renk.KALIN, Renk.BEYAZ)).strip()

        if sorun.lower() in ("cikis", "exit", "q"):
            log("Kullanici cikis yapti.")
            break

        if sorun.lower() == "hizli":
            hizli_komut_menusu()
            continue

        if sorun.lower() in ("hizlandir", "hizlandirma"):
            gorusme_ozeti.append({"sorun": "Hizlandirma sihirbazi", "cevap": hizlandirma_sihirbazi()})
            continue

        if sorun.lower() == "liste":
            secilen = sik_sorunlar_menusu()
            if not secilen:
                continue
            sorun = secilen
            print(f"\nSecilen sorun: {sorun}")

        if not sorun:
            continue

        log(f"Kullanici sorunu: {sorun}")

        if online and DEEPSEEK_API_KEY and "BURAYA" not in DEEPSEEK_API_KEY:
            print(r("\nDeepSeek ajani calisiyor...\n", Renk.MOR))
            ozet = sistem_ozeti()
            cevap = deepseek_ajan(sorun, ozet)
            print("\n" + cevap)
            log(f"DeepSeek nihai cevabi:\n{cevap}")
        else:
            cevap = yerel_teshis(sorun)
            print("\n" + cevap)
            log(f"Yerel teshis cevabi:\n{cevap}")

        gorusme_ozeti.append({"sorun": sorun, "cevap": cevap})
        print()

    if gorusme_ozeti:
        demirbas_kaydet(demirbas_no, gorusme_ozeti[-1]["sorun"], gorusme_ozeti[-1]["cevap"])
        rapor_yolu = ozet_rapor_yaz(demirbas_no, gorusme_ozeti)
        if rapor_yolu:
            print(r(f"\nOturum ozet raporu USB'ye kaydedildi: {rapor_yolu}", Renk.GRI))

    print(r(f"\n{MARKA} kapatiliyor.", Renk.KALIN, Renk.CYAN), r("Loglar:", Renk.GRI), r(LOG_FILE, Renk.GRI))
    input(r("Cikmak icin Enter'a bas...", Renk.SONUK))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log(f"BEKLENMEYEN HATA: {e}")
        print(f"\nBeklenmeyen hata: {e}")
        input("Cikmak icin Enter'a bas...")
