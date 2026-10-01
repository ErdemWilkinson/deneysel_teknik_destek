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
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# Gercek logo dosyasi (PNG) varsa burada aranir; varsa acilista (istege
# baglica) varsayilan resim goruntuleyicide gosterilir. Dosya yoksa
# sessizce atlanir, program yine calisir.
LOGO_PNG = os.path.join(USB_DIZIN, "assets", "sinop_logo.png")

# Terminalde (sadece metin karakterleriyle) gosterilen temsili amblem -
# gunes isinlari cercevesini cagristiran sade bir ASCII cizim + buyuk
# "SINOP BELEDIYESI" yazisi.
ASCII_AMBLEM = r"""
                \   |   /
              \  \  |  /  /
                \ \ | / /
          -- -- -- () -- -- --
                / / | \ \
              /  /  |  \  \
                /   |   \
"""

ASCII_BASLIK = r"""
 ____  _ _   _  ___  ____    ____  _____ _     _____ ____ _____     _______ ____ ___
/ ___|(_) \ | |/ _ \|  _ \  | __ )| ____| |   | ____|  _ \_ _\ \   / / ____/ ___|_ _|
\___ \| |  \| | | | | |_) | |  _ \|  _| | |   |  _| | | | | | \ \ / /|  _| \___ \| |
 ___) | | |\  | |_| |  __/  | |_) | |___| |___| |___| |_| | |  \ V / | |___ ___) | |
|____/|_|_| \_|\___/|_|     |____/|_____|_____|_____|____/___|  \_/  |_____|____/___|
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


def baslik():
    os.system("cls" if os.name == "nt" else "clear")
    try:
        genislik = os.get_terminal_size().columns
    except OSError:
        genislik = 90

    print(_ortala_blok(ASCII_AMBLEM, genislik))
    print(_ortala_blok(ASCII_BASLIK, genislik))
    print("TEKNIK DESTEK TERMINALI".center(genislik))
    print("(Kurulum gerektirmez - USB'den calisir)".center(genislik))
    print()
    print("=" * min(87, genislik))
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


def arac_disk_durumu(params):
    return _calistir(["wmic", "logicaldisk", "get", "size,freespace,caption"])


def arac_event_log(params):
    adet = int(params.get("adet", 15)) if isinstance(params, dict) else 15
    adet = max(1, min(adet, 50))
    return _calistir([
        "powershell", "-NoProfile", "-Command",
        f"Get-WinEvent -LogName System -MaxEvents {adet} -ErrorAction SilentlyContinue | "
        "Where-Object {$_.LevelDisplayName -eq 'Error'} | "
        "Select-Object TimeCreated,Id,ProviderName | Format-Table -AutoSize | Out-String"
    ])


def arac_servis_durumu(params):
    servis_adi = (params or {}).get("servis_adi", "")
    if servis_adi:
        return _calistir(["powershell", "-NoProfile", "-Command",
                           f"Get-Service -Name '{servis_adi}' | Format-List | Out-String"])
    return _calistir(["powershell", "-NoProfile", "-Command",
                       "Get-Service | Where-Object {$_.Status -eq 'Stopped' -and $_.StartType -eq 'Automatic'} | "
                       "Select-Object Name,DisplayName,Status | Format-Table -AutoSize | Out-String"])


def arac_baslangic_programlari(params):
    return _calistir(["powershell", "-NoProfile", "-Command",
                       "Get-CimInstance Win32_StartupCommand | Select-Object Name,Command,Location | "
                       "Format-Table -AutoSize | Out-String"])


def arac_ag_durumu(params):
    return _calistir(["ipconfig", "/all"])


def arac_sfc_scan(params):
    return _calistir(["sfc", "/scannow"], timeout=600)


def arac_dism_repair(params):
    return _calistir(["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"], timeout=900)


def arac_dns_flush(params):
    return _calistir(["ipconfig", "/flushdns"])


def arac_ip_renew(params):
    _calistir(["ipconfig", "/release"])
    return _calistir(["ipconfig", "/renew"])


def arac_disk_temizligi(params):
    return _calistir(["cleanmgr", "/sagerun:1"], timeout=300)


def arac_yazici_kuyrugu_temizle(params):
    return _calistir([
        "powershell", "-NoProfile", "-Command",
        "Stop-Service -Name Spooler -Force; "
        "Remove-Item -Path 'C:\\Windows\\System32\\spool\\PRINTERS\\*' -Force -ErrorAction SilentlyContinue; "
        "Start-Service -Name Spooler; "
        "Write-Output 'Yazdirma kuyrugu temizlendi ve Spooler servisi yeniden baslatildi.'"
    ], timeout=60)


def arac_chkdsk(params):
    surucu = (params or {}).get("surucu", "C:")
    # /f ve /r kullanicinin onayiyla ve sadece /scan (read-only, yeniden
    # baslatma gerektirmeyen) modunda calisir; tam onarim icin kullanici
    # ayrica yeniden baslatmayi kendi yapar.
    return _calistir(["chkdsk", surucu, "/scan"], timeout=600)


def arac_windows_update_sifirla(params):
    return _calistir([
        "powershell", "-NoProfile", "-Command",
        "Stop-Service -Name wuauserv,bits,cryptsvc -Force -ErrorAction SilentlyContinue; "
        "Rename-Item -Path 'C:\\Windows\\SoftwareDistribution' -NewName 'SoftwareDistribution.bak' -ErrorAction SilentlyContinue; "
        "Rename-Item -Path 'C:\\Windows\\System32\\catroot2' -NewName 'catroot2.bak' -ErrorAction SilentlyContinue; "
        "Start-Service -Name wuauserv,bits,cryptsvc -ErrorAction SilentlyContinue; "
        "Write-Output 'Windows Update bilesenleri sifirlandi. Degisikligin etkili olmasi icin PC yeniden baslatilmali.'"
    ], timeout=120)


def arac_geri_yukleme_noktasi(params):
    aciklama = (params or {}).get("aciklama", "Teknik Destek Terminali Onarim Oncesi")
    return _calistir([
        "powershell", "-NoProfile", "-Command",
        "Enable-ComputerRestore -Drive 'C:\\' -ErrorAction SilentlyContinue; "
        f"Checkpoint-Computer -Description '{aciklama}' -RestorePointType 'MODIFY_SETTINGS'; "
        "Write-Output 'Geri yukleme noktasi olusturuldu (veya zaten yakin zamanda olusturulmus).'"
    ], timeout=120)


def arac_kaynak_kullanimi(params):
    return _calistir([
        "powershell", "-NoProfile", "-Command",
        "$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; "
        "$ram = Get-CimInstance Win32_OperatingSystem; "
        "$ramKullanimGB = [math]::Round(($ram.TotalVisibleMemorySize - $ram.FreePhysicalMemory)/1MB,2); "
        "$ramToplamGB = [math]::Round($ram.TotalVisibleMemorySize/1MB,2); "
        "Write-Output \"CPU kullanimi: %$cpu\"; "
        "Write-Output \"RAM kullanimi: $ramKullanimGB GB / $ramToplamGB GB\"; "
        "Write-Output '--- En cok CPU kullanan 5 surec ---'; "
        "Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 Name,CPU,WorkingSet | Format-Table -AutoSize | Out-String"
    ])


def arac_defender_tarama(params):
    tur = (params or {}).get("tur", "Quick")
    if tur not in ("Quick", "Full"):
        tur = "Quick"
    return _calistir([
        "powershell", "-NoProfile", "-Command",
        f"Start-MpScan -ScanType {tur}; "
        "Write-Output 'Tarama baslatildi/tamamlandi. Sonuclari Windows Guvenligi uygulamasindan da gorebilirsin.'"
    ], timeout=900 if tur == "Full" else 300)


ARAC_KAYDI = {
    "disk_durumu": {
        "aciklama": "Disklerin toplam/bos alanini gosterir (salt okunur).",
        "params": {},
        "destructive": False,
        "fn": arac_disk_durumu,
    },
    "event_log_oku": {
        "aciklama": "Windows Sistem gunlugundeki son hata kayitlarini okur (salt okunur).",
        "params": {"adet": "integer, opsiyonel, varsayilan 15"},
        "destructive": False,
        "fn": arac_event_log,
    },
    "servis_durumu": {
        "aciklama": "Belirli bir Windows servisinin durumunu, ya da calismayan otomatik servisleri listeler (salt okunur).",
        "params": {"servis_adi": "string, opsiyonel"},
        "destructive": False,
        "fn": arac_servis_durumu,
    },
    "baslangic_programlari": {
        "aciklama": "Windows baslangicinda otomatik calisan programlari listeler (salt okunur).",
        "params": {},
        "destructive": False,
        "fn": arac_baslangic_programlari,
    },
    "ag_durumu": {
        "aciklama": "Ag adaptorlerinin IP/DNS/durumunu gosterir (salt okunur).",
        "params": {},
        "destructive": False,
        "fn": arac_ag_durumu,
    },
    "sfc_tarama": {
        "aciklama": "sfc /scannow calistirir, bozuk sistem dosyalarini onarir.",
        "params": {},
        "destructive": True,
        "fn": arac_sfc_scan,
    },
    "dism_onarim": {
        "aciklama": "DISM /RestoreHealth calistirir, Windows bilesen deposunu onarir.",
        "params": {},
        "destructive": True,
        "fn": arac_dism_repair,
    },
    "dns_temizle": {
        "aciklama": "DNS onbellegini temizler (ipconfig /flushdns).",
        "params": {},
        "destructive": True,
        "fn": arac_dns_flush,
    },
    "ip_yenile": {
        "aciklama": "IP adresini yeniler (ipconfig /release + /renew).",
        "params": {},
        "destructive": True,
        "fn": arac_ip_renew,
    },
    "disk_temizligi": {
        "aciklama": "Gecici dosyalari temizler (cleanmgr).",
        "params": {},
        "destructive": True,
        "fn": arac_disk_temizligi,
    },
    "yazici_kuyrugu_temizle": {
        "aciklama": "Yazdirma kuyrugunu ve Spooler servisini temizleyip yeniden baslatir.",
        "params": {},
        "destructive": True,
        "fn": arac_yazici_kuyrugu_temizle,
    },
    "disk_kontrolu": {
        "aciklama": "chkdsk /scan ile diskte hata taramasi yapar (salt tarama, dosya sistemini degistirmez).",
        "params": {"surucu": "string, opsiyonel, varsayilan 'C:'"},
        "destructive": True,
        "fn": arac_chkdsk,
    },
    "windows_update_sifirla": {
        "aciklama": "Windows Update bilesenlerini (SoftwareDistribution, catroot2) sifirlar. Yeniden baslatma gerektirir.",
        "params": {},
        "destructive": True,
        "fn": arac_windows_update_sifirla,
    },
    "geri_yukleme_noktasi": {
        "aciklama": "Onarimdan once sistem geri yukleme noktasi (restore point) olusturur, risk azaltir.",
        "params": {"aciklama": "string, opsiyonel"},
        "destructive": True,
        "fn": arac_geri_yukleme_noktasi,
    },
    "kaynak_kullanimi": {
        "aciklama": "Anlik CPU/RAM kullanimini ve en cok kaynak tuketen 5 sureci gosterir (salt okunur).",
        "params": {},
        "destructive": False,
        "fn": arac_kaynak_kullanimi,
    },
    "defender_tarama": {
        "aciklama": "Windows Defender ile hizli (Quick) veya tam (Full) virus taramasi baslatir.",
        "params": {"tur": "string, opsiyonel, 'Quick' veya 'Full', varsayilan 'Quick'"},
        "destructive": True,
        "fn": arac_defender_tarama,
    },
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
        print(f"\n[AI bir onarim araci cagirmak istiyor]: {ad} - {bilgi['aciklama']}")
        onay = input("  Calistirilsin mi? [E/h]: ").strip().lower()
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
        "Sen bir Windows sistem teknisyeni yardimcisisin. Belediye BT "
        "teknisyeninin sahada kullandigi bir terminal uzerinden calisiyorsun. "
        "Turkce konus. Elinde gercek sistem bilgisi toplamak ve onarim "
        "yapmak icin ARACLAR (tools) var: disk/servis/event-log okuma gibi "
        "salt okunur araclari istedigin kadar, geregi kadar cagirabilirsin. "
        "sfc_tarama, dism_onarim, disk_kontrolu, windows_update_sifirla gibi "
        "SISTEMI DEGISTIREN araclari cagirdiginda kullaniciya onay sorulacagini "
        "bil - bu normal, sen yine de gerekli gordugun araci cagir. Sistemi "
        "kalici olarak degistirecek riskli bir onarima (sfc_tarama, "
        "dism_onarim, windows_update_sifirla, disk_kontrolu) baslamadan once, "
        "uygunsa once geri_yukleme_noktasi aracini cagirmayi dikkate al. "
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
    (["yavas", "donuyor", "kasiyor", "takiliyor"], [
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
    destructive_araclar = [(ad, b) for ad, b in ARAC_KAYDI.items() if b["destructive"]]
    print("\nHizli onarim komutlari (her biri icin onay istenir):")
    for i, (ad, bilgi) in enumerate(destructive_araclar, 1):
        print(f"  [{i}] {bilgi['aciklama']}")
    print("  [0] Geri don")
    secim = input("Secim: ").strip()
    if secim == "0" or not secim.isdigit():
        return
    idx = int(secim) - 1
    if idx < 0 or idx >= len(destructive_araclar):
        print("Gecersiz secim.")
        return
    ad, bilgi = destructive_araclar[idx]
    sonuc = arac_cagir(ad, {})
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
    print("\nSik karsilasilan sorunlar:")
    for i, s in enumerate(SIK_SORUNLAR, 1):
        print(f"  [{i}] {s}")
    print("  [0] Geri don (kendi cumlemi yazacagim)")
    secim = input("Secim: ").strip()
    if secim == "0" or not secim.isdigit():
        return None
    idx = int(secim) - 1
    if 0 <= idx < len(SIK_SORUNLAR):
        return SIK_SORUNLAR[idx]
    print("Gecersiz secim.")
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
            f.write("BELEDIYE TEKNIK DESTEK TERMINALI - OTURUM OZETI\n")
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
# Ana akis
# ------------------------------------------------------------------

def main():
    baslik()
    log("Terminal baslatildi.")

    if os.path.exists(LOGO_PNG):
        logo_sec = input("Sinop Belediyesi logosunu ayri pencerede acmak ister misin? [e/H]: ").strip().lower()
        if logo_sec in ("e", "evet", "y", "yes"):
            logo_ac()

    demirbas_no = input("Demirbas/PC adi ya da no (bos birakabilirsin): ").strip()
    log(f"Demirbas/PC: {demirbas_no or '(belirtilmedi)'}")

    online = internet_var_mi()
    if online:
        print("\nInternet baglantisi bulundu -> DeepSeek AI ajan modu aktif.")
        print("(AI, gerektiginde teshis araclarini kendisi cagirir; sistemi")
        print(" degistiren her islem icin senden onay ister.)\n")
    else:
        print("\nInternet baglantisi yok -> Yerel teshis motoru calisacak.\n")

    gorusme_ozeti = []

    while True:
        print("-" * 60)
        print("Karsilastigin sorunu kisaca yaz (orn: 'bilgisayar cok yavas')")
        print("Komutlar: 'liste' = sik sorun listesi, 'hizli' = hizli onarim menusu,")
        print("          'cikis' = programi kapat")
        sorun = input("\n> ").strip()

        if sorun.lower() in ("cikis", "exit", "q"):
            log("Kullanici cikis yapti.")
            break

        if sorun.lower() == "hizli":
            hizli_komut_menusu()
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
            print("\nDeepSeek ajani calisiyor...\n")
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
            print(f"\nOturum ozet raporu USB'ye kaydedildi: {rapor_yolu}")

    print("\nTerminal kapatiliyor. Loglar:", LOG_FILE)
    input("Cikmak icin Enter'a bas...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log(f"BEKLENMEYEN HATA: {e}")
        print(f"\nBeklenmeyen hata: {e}")
        input("Cikmak icin Enter'a bas...")
