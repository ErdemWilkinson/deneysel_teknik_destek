"""
ERDEMUSB - PC Dinleyicisi
--------------------------
Bu program, PC'lere ONCEDEN (bir kere) kurulur ve arka planda calisir.
ESP32-P4-Pico takildiginda seri porttan "TEKNIKDESTEK_HAZIR" sinyalini
alinca, Windows bildirim alaninda bir bildirim gosterir ve bu konsol
penceresinde geri sayimli bir onay istemi acar.

Guvenlik ilkesi:
  - Enter'a BASMADAN hicbir program acilmaz. Pico hicbir komutu otomatik
    calistiramaz, sadece "hazirim" sinyali yayar. Karari ve onayi HER
    ZAMAN teknisyen verir.

Kurulum (PC basina bir kere):
  1) requirements.txt'deki paketleri kur: pip install -r requirements.txt
  2) derle.ps1 ile tek-exe'ye paketle (DINLEYICI.exe)
  3) DINLEYICI.exe'yi ve ONARIM_BASLAT.exe'yi ayni klasore koy
     (orn. C:\\TeknikDestek\\)
  4) DINLEYICI.exe'yi Windows Baslangic klasorune kisayol olarak ekle
     (Win+R -> shell:startup) ki PC acilista otomatik calissin.
"""

import ctypes
import os
import queue
import sys
import time
import threading
import subprocess

import serial
import serial.tools.list_ports
from plyer import notification

MARKA = "ERDEMUSB"

HAZIR_SINYALI = "TEKNIKDESTEK_HAZIR"
TARANMA_ARALIGI_SN = 2
BAUD = 115200
ONAY_SURESI_SN = 20

# ONARIM_BASLAT.exe'nin bu programla ayni klasorde oldugunu varsayiyoruz
UYGULAMA_DIZINI = os.path.dirname(os.path.abspath(sys.argv[0]))
ONARIM_EXE = os.path.join(UYGULAMA_DIZINI, "ONARIM_BASLAT.exe")

# Ayni cihaz icin kisa sure icinde tekrar tekrar bildirim gondermemek icin
son_bildirim_zamani = {}
BILDIRIM_SESSIZ_SURE_SN = 30


# ------------------------------------------------------------------
# Renkler (ANSI) - pc_terminal.py ile ayni mantik: Windows konsollarinin
# cogu VT100 destekler ama kapali gelir; acilista denenir, basarisiz
# olursa program renksiz calismaya devam eder, hicbir yerde hataya dusmez.
# ------------------------------------------------------------------

class Renk:
    SIFIRLA = "\033[0m"
    KALIN = "\033[1m"
    SONUK = "\033[2m"
    SARI = "\033[38;5;221m"
    YESIL = "\033[38;5;114m"
    CYAN = "\033[38;5;80m"
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
                kernel32.SetConsoleTitleW(f"{MARKA} - Dinleyici")
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


BOLT = r"/", r"|", r"\\"  # kucuk animasyon icin (kullanilmiyor, basit tutuldu)

BANNER = r"""
     __/|      ERDEMUSB
     \ |       Dinleyici - arka planda calisiyor
      \|
      /|
     / |
    /__|
"""


def uyar_sesi():
    """Pico algilandiginda kisa bir uyari sesi (yalnizca Windows). Ses
    calinamazsa (ses karti yok, vs.) sessizce gecilir - hicbir zaman
    bildirimi engellemez."""
    if os.name != "nt":
        return
    try:
        import winsound
        winsound.Beep(880, 150)
        winsound.Beep(1175, 150)
    except Exception:
        pass


def onarim_terminalini_ac():
    if not os.path.exists(ONARIM_EXE):
        print(r(f"HATA: {ONARIM_EXE} bulunamadi.", Renk.SARI))
        return
    try:
        subprocess.Popen([ONARIM_EXE], creationflags=subprocess.CREATE_NEW_CONSOLE)
    except Exception as e:
        print(r(f"Terminal acilamadi: {e}", Renk.SARI))


# ------------------------------------------------------------------
# Tek, surekli calisan stdin okuyucu. Hem "Enter'a bas -> terminal ac"
# onayi hem de bekleme disinda elle yazilan "ac"/"cikis" komutlari buradan
# okunur - boylece ayni anda birden fazla input() cagrisi stdin'i
# paylasmaya calisip birbirini kilitlemez.
# ------------------------------------------------------------------

GIRDI_KUYRUGU: "queue.Queue[str]" = queue.Queue()


def girdi_dinleyicisi():
    while True:
        try:
            satir = input()
        except Exception:
            return
        GIRDI_KUYRUGU.put(satir.strip().lower())


def _kuyrugu_bosalt():
    while not GIRDI_KUYRUGU.empty():
        try:
            GIRDI_KUYRUGU.get_nowait()
        except queue.Empty:
            break


def onay_bekle_ve_ac(port_adi: str, sure_sn: int = ONAY_SURESI_SN):
    """Konsolda geri sayimli, renkli bir onay istemi gosterir; kullanici
    Enter'a basarsa terminali acar. Bu, bildirime 'tiklama' yerine guvenilir
    ana yoldur - Windows toast bildirimlerinde tiklama callback'i her
    ortamda calismaz."""
    _kuyrugu_bosalt()  # eski/bekleyen bir Enter burada sayilmasin
    onaylandi = False
    kalan = sure_sn
    while kalan > 0:
        print(r(f"\r  >> Enter'a bas, terminal acilsin   [{kalan:2d} sn kaldi]  ", Renk.SARI, Renk.KALIN), end="", flush=True)
        try:
            GIRDI_KUYRUGU.get(timeout=1)
            onaylandi = True
            break
        except queue.Empty:
            kalan -= 1
    print()

    if onaylandi:
        print(r(f"[{port_adi}] Onaylandi, terminal aciliyor...", Renk.YESIL, Renk.KALIN))
        onarim_terminalini_ac()
    else:
        print(r(f"[{port_adi}] Sure doldu, acilmadi.", Renk.GRI)
              + " Tekrar denemek icin Pico'yu cikarip takabilir ya da "
              + r("'ac'", Renk.CYAN) + " yazip Enter'a basabilirsin.")


def bildirim_goster(port_adi: str):
    try:
        notification.notify(
            title=f"{MARKA} Hazir",
            message=f"ESP32-P4-Pico ({port_adi}) algilandi. Bu pencereye gelip Enter'a bas.",
            timeout=15,
        )
    except Exception as e:
        print(r(f"Bildirim gosterilemedi: {e}", Renk.GRI))

    uyar_sesi()
    print(r(f"\n  [{port_adi}] {MARKA} hazir.", Renk.KALIN, Renk.TURUNCU))
    onay_bekle_ve_ac(port_adi)


def cihaz_dinle(port_adi: str, durdur_event: threading.Event):
    try:
        with serial.Serial(port_adi, BAUD, timeout=1) as ser:
            print(r(f"Dinleniyor: {port_adi}", Renk.GRI))
            while not durdur_event.is_set():
                try:
                    satir = ser.readline().decode("utf-8", errors="ignore").strip()
                except Exception:
                    continue
                if satir == HAZIR_SINYALI:
                    simdi = time.time()
                    son = son_bildirim_zamani.get(port_adi, 0)
                    if simdi - son >= BILDIRIM_SESSIZ_SURE_SN:
                        son_bildirim_zamani[port_adi] = simdi
                        bildirim_goster(port_adi)
    except Exception as e:
        print(r(f"Port {port_adi} dinlenemedi: {e}", Renk.GRI))


# Pico'nun USB-seri cipi WCH CH343 (VID 0x1A86); ESP32'nin kendi USB'si Espressif (VID 0x303A).
# Yalnizca bu portlar dinlenir: hepsini acmak, PC'deki baska seri cihazlari (yazar kasa,
# barkod okuyucu, olcum cihazi...) mesgul edip kullanilamaz hale getirebiliyordu.
PICO_VIDLERI = {0x1A86, 0x303A}


def aktif_portlari_bul():
    portlar = serial.tools.list_ports.comports()
    return [p.device for p in portlar if p.vid in PICO_VIDLERI]


def main():
    renklendir_etkinlestir()
    print(r(BANNER, Renk.TURUNCU))
    print(f"Onarim programi: {ONARIM_EXE}")
    print(r("Komutlar: ", Renk.KALIN) + r("'ac'", Renk.CYAN) + " = terminali hemen ac, "
          + r("'cikis'", Renk.GRI) + " = dinleyiciyi kapat.\n")

    threading.Thread(target=girdi_dinleyicisi, daemon=True).start()

    izlenen_threadler = {}
    durdur_event = threading.Event()

    try:
        while True:
            # Cihaz algilanmasini beklemeden elle yazilan komutlari isle
            try:
                while True:
                    komut = GIRDI_KUYRUGU.get_nowait()
                    if komut in ("ac", "a"):
                        print(r("Elle acildi.", Renk.YESIL))
                        onarim_terminalini_ac()
                    elif komut in ("cikis", "q", "exit"):
                        raise KeyboardInterrupt
            except queue.Empty:
                pass

            mevcut_portlar = set(aktif_portlari_bul())

            # Yeni takilan portlar icin thread baslat
            for port in mevcut_portlar:
                if port not in izlenen_threadler:
                    t = threading.Thread(target=cihaz_dinle, args=(port, durdur_event), daemon=True)
                    t.start()
                    izlenen_threadler[port] = t

            # Cikarilan portlari listeden temizle (thread kendiliginden hata verip duracak)
            for port in list(izlenen_threadler.keys()):
                if port not in mevcut_portlar:
                    del izlenen_threadler[port]

            time.sleep(TARANMA_ARALIGI_SN)
    except KeyboardInterrupt:
        durdur_event.set()
        print(r("\nDinleyici kapatiliyor.", Renk.GRI))


if __name__ == "__main__":
    main()
