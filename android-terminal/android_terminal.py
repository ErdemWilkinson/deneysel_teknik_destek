"""
ERDEMUSB Android Hizlandirici - PC Terminali (ADB uzerinden)
--------------------------------------------------------------
pc-terminal/pc_terminal.py ile ayni ruh: kategorili, renkli, HER ADIMDA
ONAY isteyen bir terminal. Farki: PC'yi degil, USB ile bagli bir Android
telefonu hedefler - ADB (Android Debug Bridge) ile telefona komut
gonderir.

Yapay zeka / internet YOKTUR (bilerek): bu script hicbir aga baglanmaz,
DeepSeek ya da baska bir bulut servisi cagirmaz. Sadece `adb` araciyla
telefona yerel komutlar gonderir.

Gereksinimler (PC tarafinda):
  - Python 3.8+
  - Android SDK Platform Tools (icinde "adb" var):
    https://developer.android.com/tools/releases/platform-tools
    Indirip zip'i actiktan sonra PATH'e eklemen ya da bu script'i
    "adb.exe" ile ayni klasorde calistirman yeterli.

Telefon tarafinda:
  - Ayarlar -> Telefon Hakkinda -> "Yapi Numarasi"na 7 kere dokunup
    Gelistirici Secenekleri'ni ac.
  - Gelistirici Secenekleri -> "USB Hata Ayiklama"yi (USB Debugging) ac.
  - Telefonu PC'ye USB kablosuyla bagla, telefonda cikan "Bu bilgisayara
    guven?" sorusuna EVET de.

Guvenlik ilkesi (ayni GoodUSB mantigi): hicbir komut onaysiz calismaz.
Veri kaybina yol acabilecek islemler (uygulama verisini temizleme,
uygulama kaldirma) ayrica buyuk harfle uyarilir.
"""

import ctypes
import os
import subprocess
import sys

MARKA = "ERDEMUSB"

# ------------------------------------------------------------------
# Renkler (pc_terminal.py ile ayni mantik)
# ------------------------------------------------------------------


class Renk:
    SIFIRLA = "\033[0m"
    KALIN = "\033[1m"
    SONUK = "\033[2m"
    SARI = "\033[38;5;221m"
    YESIL = "\033[38;5;114m"
    KIRMIZI = "\033[38;5;203m"
    CYAN = "\033[38;5;80m"
    MOR = "\033[38;5;140m"
    TURUNCU = "\033[38;5;215m"
    GRI = "\033[38;5;245m"


RENK_ACIK = False


def renklendir_etkinlestir():
    global RENK_ACIK
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            h = kernel32.GetStdHandle(-11)
            mod = ctypes.c_uint32()
            if kernel32.GetConsoleMode(h, ctypes.byref(mod)):
                if kernel32.SetConsoleMode(h, mod.value | 0x0004):
                    RENK_ACIK = True
            try:
                kernel32.SetConsoleTitleW(f"{MARKA} - Android Hizlandirici")
            except Exception:
                pass
        except Exception:
            RENK_ACIK = False
    else:
        RENK_ACIK = sys.stdout.isatty()


def r(metin: str, *renkler: str) -> str:
    if not RENK_ACIK or not renkler:
        return metin
    return "".join(renkler) + metin + Renk.SIFIRLA


BANNER = r"""
  ______ _____  _____  ______ __  __ _    _  _____ ____
 |  ____|  __ \|  __ \|  ____|  \/  | |  | |/ ____|  _ \
 | |__  | |__) | |  | | |__  | \  / | |  | | (___ | |_) |
 |  __| |  _  /| |  | |  __| | |\/| | |  | |\___ \|  _ <
 | |____| | \ \| |__| | |____| |  | | |__| |____) | |_) |
 |______|_|  \_\_____/|______|_|  |_|\____/|_____/|____/
        Android Hizlandirici - ADB uzerinden, AI YOK
"""

# ------------------------------------------------------------------
# ADB cagri yardimcilari
# ------------------------------------------------------------------

# Android sistemi icin kaldirilmasi telefonu bozabilecek, ASLA
# onermeyecegimiz/kaldirmaya izin vermeyecegimiz paketler.
KORUMALI_PAKETLER = {
    "android", "com.android.systemui", "com.android.settings",
    "com.android.phone", "com.android.providers.settings",
    "com.android.server.telecom", "com.google.android.gms",
    "com.google.android.gsf", "com.android.vending",
    "com.android.launcher", "com.android.launcher3",
}


def adb_yolu_bul() -> str:
    """Once PATH'te 'adb' ara; yoksa bu script ile ayni klasorde
    adb(.exe) var mi diye bak."""
    from shutil import which
    bulunan = which("adb")
    if bulunan:
        return bulunan
    yerel = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
                          "adb.exe" if os.name == "nt" else "adb")
    if os.path.exists(yerel):
        return yerel
    return "adb"  # bulunamadi, calistirinca hata verecek - kullaniciya mesaj basariz


ADB = adb_yolu_bul()


def adb_calistir(args, zaman_asimi=20):
    """adb komutunu calistirir, (basarili_mi, cikti) dondurur."""
    try:
        sonuc = subprocess.run(
            [ADB] + args,
            capture_output=True, text=True, timeout=zaman_asimi
        )
        cikti = (sonuc.stdout or "") + (sonuc.stderr or "")
        return sonuc.returncode == 0, cikti.strip()
    except FileNotFoundError:
        return False, ("HATA: 'adb' bulunamadi. Android SDK Platform Tools'u indirip\n"
                        "PATH'e ekle ya da adb.exe'yi bu script ile ayni klasore koy.\n"
                        "https://developer.android.com/tools/releases/platform-tools")
    except subprocess.TimeoutExpired:
        return False, "HATA: Komut zaman asimina ugradi (telefon yanit vermiyor)."
    except Exception as e:
        return False, f"HATA: {e}"


def adb_shell(komut: str, zaman_asimi=20):
    return adb_calistir(["shell", komut], zaman_asimi)


def cihaz_bagli_mi() -> bool:
    basarili, cikti = adb_calistir(["devices"])
    if not basarili:
        print(r(cikti, Renk.KIRMIZI))
        return False
    satirlar = [s for s in cikti.splitlines()[1:] if s.strip()]
    cihazlar = [s for s in satirlar if s.endswith("device")]
    yetkisizler = [s for s in satirlar if "unauthorized" in s]
    if yetkisizler:
        print(r("Telefon bagli ama ONAYLANMAMIS.", Renk.SARI))
        print("Telefonun ekranina bak, \"Bu bilgisayara guven?\" sorusuna EVET de.")
        return False
    if not cihazlar:
        print(r("Hicbir Android cihaz bulunamadi.", Renk.KIRMIZI))
        print("- Telefon USB ile bagli mi?")
        print("- Telefonda Gelistirici Secenekleri -> USB Hata Ayiklama acik mi?")
        return False
    if len(cihazlar) > 1:
        print(r(f"UYARI: {len(cihazlar)} cihaz bagli, ilki kullanilacak.", Renk.SARI))
    return True


# ------------------------------------------------------------------
# Araclar (hepsi yerel/ADB - internet ve AI yok)
# ------------------------------------------------------------------

def arac_cihaz_bilgisi():
    for ozellik, etiket in [
        ("ro.product.manufacturer", "Marka"),
        ("ro.product.model", "Model"),
        ("ro.build.version.release", "Android surumu"),
        ("ro.build.version.sdk", "API seviyesi"),
    ]:
        _, deger = adb_shell(f"getprop {ozellik}")
        print(f"  {etiket}: {deger}")


def arac_pil_durumu():
    basarili, cikti = adb_shell("dumpsys battery")
    if not basarili:
        print(r(cikti, Renk.KIRMIZI))
        return
    for satir in cikti.splitlines():
        s = satir.strip()
        if s.startswith(("level:", "status:", "health:", "temperature:", "plugged:")):
            print(f"  {s}")


def arac_depolama_durumu():
    basarili, cikti = adb_shell("df /data")
    if not basarili:
        print(r(cikti, Renk.KIRMIZI))
        return
    print(cikti)


def arac_ram_durumu():
    basarili, cikti = adb_shell("cat /proc/meminfo")
    if not basarili:
        print(r(cikti, Renk.KIRMIZI))
        return
    onemli = {"MemTotal", "MemFree", "MemAvailable"}
    for satir in cikti.splitlines():
        if satir.split(":")[0].strip() in onemli:
            print(f"  {satir.strip()}")


def arac_uygulama_listesi():
    """Kullanicinin kurdugu (sistem disi) uygulamalari APK boyutuna
    gore buyukten kucuge listeler - cihaza gore 5-60 sn surebilir."""
    basarili, cikti = adb_shell("pm list packages -3", zaman_asimi=30)
    if not basarili:
        print(r(cikti, Renk.KIRMIZI))
        return
    paketler = [s.replace("package:", "").strip() for s in cikti.splitlines() if s.strip()]
    if not paketler:
        print("  Kullanicinin kurdugu ayri bir uygulama bulunamadi.")
        return
    print(f"  {len(paketler)} uygulama bulundu, boyutlar hesaplaniyor (biraz surebilir)...")
    sonuclar = []
    for paket in paketler:
        basarili2, yol = adb_shell(f"pm path {paket}", zaman_asimi=10)
        if not basarili2 or not yol.startswith("package:"):
            continue
        apk_yolu = yol.replace("package:", "").strip().splitlines()[0]
        basarili3, boyut_cikti = adb_shell(f"stat -c %s {apk_yolu}", zaman_asimi=10)
        try:
            boyut = int(boyut_cikti.strip())
        except Exception:
            boyut = 0
        sonuclar.append((paket, boyut))
    sonuclar.sort(key=lambda x: x[1], reverse=True)
    for paket, boyut in sonuclar[:25]:
        mb = boyut / 1024 / 1024
        print(f"  {mb:7.1f} MB  {paket}")


def arac_calisan_uygulamalar():
    basarili, cikti = adb_shell("ps -A -o NAME 2>/dev/null || ps", zaman_asimi=15)
    if not basarili:
        print(r(cikti, Renk.KIRMIZI))
        return
    satirlar = [s for s in cikti.splitlines() if s.strip()]
    print(f"  Toplam {len(satirlar)} process (sistem dahil).")
    for s in satirlar[:40]:
        print(f"  {s}")


def arac_onbellekleri_temizle():
    """pm trim-caches: uygulama VERILERINE dokunmaz, sadece onbellek
    dosyalarini siler - guvenli, Android'in kendi dahili mekanizmasi."""
    basarili, cikti = adb_shell("pm trim-caches 2G", zaman_asimi=60)
    if basarili:
        print(r("  Tum uygulamalarin onbellegi (gerektigi kadar) temizlendi.", Renk.YESIL))
    else:
        print(r(f"  {cikti}", Renk.KIRMIZI))


def arac_animasyonlari_hizlandir():
    for ayar in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
        adb_shell(f"settings put global {ayar} 0.5")
    print(r("  Sistem animasyonlari hizlandirildi (0.5x) - arayuz daha hizli hissettirecek.", Renk.YESIL))


def arac_animasyonlari_eski_haline_getir():
    for ayar in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
        adb_shell(f"settings put global {ayar} 1")
    print(r("  Sistem animasyonlari varsayilana (1x) dondu.", Renk.YESIL))


def arac_uygulama_zorla_durdur(paket: str):
    basarili, cikti = adb_shell(f"am force-stop {paket}")
    if basarili:
        print(r(f"  {paket} durduruldu.", Renk.YESIL))
    else:
        print(r(f"  {cikti}", Renk.KIRMIZI))


def arac_uygulama_verisini_temizle(paket: str):
    """DIKKAT: pm clear sadece onbellegi degil, UYGULAMA VERISINI
    (giris bilgileri, ayarlar, kayitli ilerleme) de siler. Geri alinamaz."""
    if paket in KORUMALI_PAKETLER:
        print(r("  REDDEDILDI: bu sistem paketi icin veri temizleme guvenli degil.", Renk.KIRMIZI))
        return
    basarili, cikti = adb_shell(f"pm clear {paket}")
    if basarili:
        print(r(f"  {paket} verileri temizlendi (sifirlandi).", Renk.YESIL))
    else:
        print(r(f"  {cikti}", Renk.KIRMIZI))


def arac_uygulama_kaldir(paket: str):
    """pm uninstall -k --user 0: uygulamayi SADECE bu kullanicidan
    kaldirir (sistem uygulamalariysa fabrika ayarlarina donuste ya da
    'adb shell cmd package install-existing <paket>' ile geri gelir -
    gercek/kalici silme degildir, bu yuzden daha guvenlidir)."""
    if paket in KORUMALI_PAKETLER:
        print(r("  REDDEDILDI: bu paket sistem icin kritik, kaldirilamaz.", Renk.KIRMIZI))
        return
    basarili, cikti = adb_shell(f"pm uninstall -k --user 0 {paket}")
    if basarili:
        print(r(f"  {paket} kaldirildi.", Renk.YESIL))
        print("  (Geri almak icin: adb shell cmd package install-existing " + paket + ")")
    else:
        print(r(f"  {cikti}", Renk.KIRMIZI))


# ------------------------------------------------------------------
# Menu
# ------------------------------------------------------------------

KATEGORILER = {
    "teshis": ("TESHIS (salt okunur)", Renk.CYAN),
    "hizlandirma": ("HIZLANDIRMA", Renk.YESIL),
    "uygulama": ("UYGULAMA YONETIMI", Renk.MOR),
}

ARAC_KAYDI = {
    "cihaz_bilgisi": {"kategori": "teshis", "aciklama": "Marka/model/Android surumu", "destructive": False, "fn": arac_cihaz_bilgisi},
    "pil_durumu": {"kategori": "teshis", "aciklama": "Pil seviyesi, saglik, sicaklik", "destructive": False, "fn": arac_pil_durumu},
    "depolama_durumu": {"kategori": "teshis", "aciklama": "Bos/dolu depolama alani", "destructive": False, "fn": arac_depolama_durumu},
    "ram_durumu": {"kategori": "teshis", "aciklama": "RAM kullanimi", "destructive": False, "fn": arac_ram_durumu},
    "uygulama_listesi": {"kategori": "teshis", "aciklama": "En buyuk uygulamalar (APK boyutuna gore)", "destructive": False, "fn": arac_uygulama_listesi},
    "calisan_uygulamalar": {"kategori": "teshis", "aciklama": "Su an calisan process'ler", "destructive": False, "fn": arac_calisan_uygulamalar},
    "onbellekleri_temizle": {"kategori": "hizlandirma", "aciklama": "Tum uygulamalarin ONBELLEGINI temizle (veriye dokunmaz, guvenli)", "destructive": True, "fn": arac_onbellekleri_temizle},
    "animasyonlari_hizlandir": {"kategori": "hizlandirma", "aciklama": "Sistem animasyonlarini hizlandir (0.5x)", "destructive": True, "fn": arac_animasyonlari_hizlandir},
    "animasyonlari_eski_haline_getir": {"kategori": "hizlandirma", "aciklama": "Animasyon hizini varsayilana dondur (1x)", "destructive": True, "fn": arac_animasyonlari_eski_haline_getir},
    "uygulama_zorla_durdur": {"kategori": "uygulama", "aciklama": "Bir uygulamayi hemen durdur (paket adi sorulur)", "destructive": True, "parametreli": True, "fn": arac_uygulama_zorla_durdur},
    "uygulama_verisini_temizle": {"kategori": "uygulama", "aciklama": "UYARI: uygulamanin TUM verisini siler (giris bilgileri dahil), sadece onbellek degil", "destructive": True, "parametreli": True, "fn": arac_uygulama_verisini_temizle},
    "uygulama_kaldir": {"kategori": "uygulama", "aciklama": "Uygulamayi bu kullanicidan kaldir (geri alinabilir)", "destructive": True, "parametreli": True, "fn": arac_uygulama_kaldir},
}


def menu_goster():
    print()
    print(r(f"=== {MARKA} Android Hizlandirici ===", Renk.KALIN, Renk.TURUNCU))
    numara = 1
    sira = {}
    for kat_anahtar, (baslik, renk) in KATEGORILER.items():
        print(r(f"\n-- {baslik} --", renk, Renk.KALIN))
        for ad, bilgi in ARAC_KAYDI.items():
            if bilgi["kategori"] != kat_anahtar:
                continue
            etiket = r("[onay gerekir]", Renk.SARI) if bilgi["destructive"] else r("[salt okunur]", Renk.GRI)
            print(f"  {numara:2d}) {ad} {etiket} - {bilgi['aciklama']}")
            sira[numara] = ad
            numara += 1
    print(r("\n  0) Cikis", Renk.GRI))
    return sira


def main():
    renklendir_etkinlestir()
    print(r(BANNER, Renk.TURUNCU))
    print(r("Bu terminal internete/yapay zekaya baglanmaz - tum islemler", Renk.GRI))
    print(r("ADB uzerinden, dogrudan telefona, senin onayinla calisir.\n", Renk.GRI))

    if not cihaz_bagli_mi():
        input("\nEnter'a basinca tekrar denenecek (telefonu bagla/onayla)...")
        if not cihaz_bagli_mi():
            print(r("Cikiliyor.", Renk.GRI))
            return

    while True:
        sira = menu_goster()
        secim = input(r("\nSecim (numara, veya 'cikis'): ", Renk.KALIN)).strip().lower()
        if secim in ("0", "cikis", "q", "exit"):
            break
        if not secim.isdigit() or int(secim) not in sira:
            print(r("Gecersiz secim.", Renk.SARI))
            continue

        ad = sira[int(secim)]
        bilgi = ARAC_KAYDI[ad]
        parametre = None
        if bilgi.get("parametreli"):
            parametre = input("  Paket adi (orn. com.example.uygulama): ").strip()
            if not parametre:
                print(r("  Paket adi girilmedi, iptal.", Renk.SARI))
                continue

        if bilgi["destructive"]:
            uyari = r(f"  '{ad}' calistirilacak.", Renk.SARI, Renk.KALIN)
            if "UYARI" in bilgi["aciklama"]:
                uyari += r("\n  " + bilgi["aciklama"], Renk.KIRMIZI, Renk.KALIN)
            print(uyari)
            onay = input("  Onayliyor musun? [E/h]: ").strip().lower()
            if onay not in ("e", "evet", "y", "yes", ""):
                print(r("  Iptal edildi.", Renk.GRI))
                continue

        print()
        try:
            if parametre is not None:
                bilgi["fn"](parametre)
            else:
                bilgi["fn"]()
        except Exception as e:
            print(r(f"  HATA: {e}", Renk.KIRMIZI))

    print(r(f"\n{MARKA} Android Hizlandirici kapatiliyor. Iyi gunler!", Renk.TURUNCU))


if __name__ == "__main__":
    main()
