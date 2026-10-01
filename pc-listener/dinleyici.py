"""
Teknik Destek Terminali - PC Dinleyicisi
------------------------------------------
Bu program, belediye PC'lerine ONCEDEN (bir kere) kurulur ve arka planda
calisir. ESP32-P4-Pico takildiginda seri porttan "TEKNIKDESTEK_HAZIR"
sinyalini alinca, Windows bildirim alanında bir bildirim gosterir.

Guvenlik ilkesi:
  - Bildirime TIKLAMADAN hicbir program acilmaz. Pico hicbir komutu
    otomatik calistiramaz, sadece "hazirim" sinyali yayar. Karari ve
    tiklamayi HER ZAMAN teknisyen yapar.

Kurulum (PC basina bir kere):
  1) requirements.txt'deki paketleri kur: pip install -r requirements.txt
  2) derle.ps1 ile tek-exe'ye paketle (DINLEYICI.exe)
  3) DINLEYICI.exe'yi ve ONARIM_BASLAT.exe'yi ayni klasore koy
     (orn. C:\\TeknikDestek\\)
  4) DINLEYICI.exe'yi Windows Baslangic klasorune kisayol olarak ekle
     (Win+R -> shell:startup) ki PC acilista otomatik calissin.
"""

import os
import sys
import time
import threading
import subprocess

import serial
import serial.tools.list_ports
from plyer import notification

HAZIR_SINYALI = "TEKNIKDESTEK_HAZIR"
TARANMA_ARALIGI_SN = 2
BAUD = 115200

# ONARIM_BASLAT.exe'nin bu programla ayni klasorde oldugunu varsayiyoruz
UYGULAMA_DIZINI = os.path.dirname(os.path.abspath(sys.argv[0]))
ONARIM_EXE = os.path.join(UYGULAMA_DIZINI, "ONARIM_BASLAT.exe")

# Ayni cihaz icin kisa sure icinde tekrar tekrar bildirim gondermemek icin
son_bildirim_zamani = {}
BILDIRIM_SESSIZ_SURE_SN = 30


def onarim_terminalini_ac():
    if not os.path.exists(ONARIM_EXE):
        print(f"HATA: {ONARIM_EXE} bulunamadi.")
        return
    try:
        subprocess.Popen([ONARIM_EXE], creationflags=subprocess.CREATE_NEW_CONSOLE)
    except Exception as e:
        print(f"Terminal acilamadi: {e}")


def onay_bekle_ve_ac(port_adi: str, sure_sn: int = 20):
    """Konsolda net bir onay istemi gosterir; kullanici 'e'/Enter basarsa
    terminali acar. Bu, bildirime 'tiklama' yerine guvenilir ana yoldur -
    Windows toast bildirimlerinde tiklama callback'i her ortamda calismaz."""
    onay_kutusu = {"cevap": None}

    def girdi_oku():
        try:
            cevap = input()
            onay_kutusu["cevap"] = cevap
        except Exception:
            pass

    t = threading.Thread(target=girdi_oku, daemon=True)
    t.start()
    t.join(timeout=sure_sn)

    if onay_kutusu["cevap"] is not None:
        print(f"[{port_adi}] Onaylandi, terminal aciliyor...")
        onarim_terminalini_ac()
    else:
        print(f"[{port_adi}] Sure doldu, acilmadi. Tekrar denemek icin Pico'yu "
              f"cikarip takabilir ya da 'ac' yazip Enter'a basabilirsin.")


def bildirim_goster(port_adi: str):
    try:
        notification.notify(
            title="Teknik Destek Terminali Hazir",
            message=f"ESP32-P4-Pico ({port_adi}) algilandi. Bu pencereye gelip Enter'a bas.",
            timeout=15,
        )
    except Exception as e:
        print(f"Bildirim gosterilemedi: {e}")

    print(f"\n[{port_adi}] Teknik Destek Terminali hazir.")
    print(f"Acmak icin bu pencereye gelip Enter'a bas (20 saniye icinde)...")
    onay_bekle_ve_ac(port_adi)


def cihaz_dinle(port_adi: str, durdur_event: threading.Event):
    try:
        with serial.Serial(port_adi, BAUD, timeout=1) as ser:
            print(f"Dinleniyor: {port_adi}")
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
        print(f"Port {port_adi} dinlenemedi: {e}")


def aktif_portlari_bul():
    portlar = serial.tools.list_ports.comports()
    # CH343/ESP32 cihazlarini tahmin etmeye calisir ama emin olamadigimiz
    # icin TUM seri portlari deniyoruz (zararsiz: sinyal gelmezse sessiz kalir)
    return [p.device for p in portlar]


def main():
    print("Teknik Destek Terminali Dinleyicisi calisiyor (arka planda).")
    print(f"Onarim programi: {ONARIM_EXE}")
    print("Cikmak icin bu pencereyi kapat.\n")

    izlenen_threadler = {}
    durdur_event = threading.Event()

    try:
        while True:
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
        print("\nDinleyici kapatiliyor.")


if __name__ == "__main__":
    main()
