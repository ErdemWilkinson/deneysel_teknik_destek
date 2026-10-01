/*
 * Waveshare ESP32-P4-Pico — Tak-Calistir USB Bellek (Mass Storage)
 * -------------------------------------------------------------------
 * Amac: Teknisyen USB-C'yi PC'ye taktiginda, PC bu karti sıradan bir
 * USB bellek (flash disk) gibi gorsun. Icinde ONARIM_BASLAT.exe ve
 * bir OKU_BENI.txt bulunur. Hicbir surucu kurulumu, hicbir HID/klavye
 * taklidi, hicbir otomatik komut calistirma YOKTUR — bu klasik
 * "USB bellek tak, programa cift tikla" deneyimidir.
 *
 * Teknik:
 *   - ESP32-P4'un dahili SPI flash'inda "ffat" adli bir bolum, FAT ile
 *     bicimlendirilip wear-levelling (wl_handle) katmani uzerinden
 *     TinyUSB MSC (Mass Storage Class) ile PC'ye HAM SEKTOR erisimi
 *     olarak sunulur. PC bu bolumu normal bir USB disk olarak Gezgin'de
 *     gorur ve FAT dosya sistemini kendisi okur/yazar.
 *   - Not: FFat kutuphanesinin readRAW()/writeRAW() gibi bir API'si YOK;
 *     bu yuzden partition'a dogrudan ESP-IDF'in wear_levelling.h
 *     (wl_mount/wl_read/wl_write) katmaniyla erisiyoruz. Ilk acilista
 *     ayrica FFat.begin() ile ayni bolum FAT olarak bicimlendirilip
 *     OKU_BENI.txt yazilir, sonra FFat kapatilip wl_handle MSC'ye
 *     devredilir (ikisinin ayni anda acik olmasi cakismaya yol acar).
 *
 * Kurulum:
 *   1) Arduino IDE -> Kart Yoneticisi -> "esp32" (Espressif) 3.x surumu.
 *   2) Arac -> Kart -> "ESP32P4 Dev Module"
 *   3) Arac -> USB Mode -> "USB-OTG (TinyUSB)" / "Hardware CDC and JTAG"
 *      (TinyUSB MSC + Serial'in birlikte calistigi secenek)
 *   4) Bu klasordeki partitions_msc.csv'yi ozel bolum tablosu olarak
 *      kullan (Partition Scheme -> "Custom").
 *   5) Bu dosyayi yukle.
 *   6) Ilk acilista flash bos oldugu icin otomatik FAT ile bicimlenir
 *      ve OKU_BENI.txt yazilir. Ardindan PC'den gorunen USB diskine
 *      ONARIM_BASLAT.exe dosyasini SURUKLE-BIRAK ile bir kere kopyala.
 *
 * NOT - EXE boyutu:
 *   ESP32-P4'un flash alaninda bu proje icin ayrilan "ffat" bolumu
 *   partitions_msc.csv'de ~14.4MB. pc-terminal/dist/ONARIM_BASLAT.exe
 *   (~8-9MB) bu alana rahatca sigar.
 */

#include "FFat.h"
#include "USB.h"
#include "USBMSC.h"
#include "esp_partition.h"
#include "wear_levelling.h"

USBMSC MSC;

static const char *BOLUM_ETIKETI = "ffat";
static wl_handle_t s_wl_handle = WL_INVALID_HANDLE;
static const esp_partition_t *s_partition = nullptr;

// ------------------------------------------------------------------
// Ilk kurulumda: partition'u FAT ile bicimle (gerekiyorsa) ve
// OKU_BENI.txt dosyasini yaz. FFat kutuphanesi uzerinden yapilir,
// islem bitince FFat.end() ile kapatilir ki wl_handle MSC tarafindan
// acilabilsin.
// ------------------------------------------------------------------
void ilkKurulumVeBenioku() {
  bool ilkSeferMi = !FFat.begin(false, "/ffat", 10, BOLUM_ETIKETI);

  if (ilkSeferMi) {
    Serial.println("FFat bos/bicimlenmemis, bicimlendiriliyor...");
    if (!FFat.begin(true, "/ffat", 10, BOLUM_ETIKETI)) {
      Serial.println("HATA: FFat bicimlendirilemedi!");
      return;
    }
  }

  if (!FFat.exists("/OKU_BENI.txt")) {
    File f = FFat.open("/OKU_BENI.txt", FILE_WRITE);
    if (f) {
      f.println("BELEDIYE TEKNIK DESTEK TERMINALI");
      f.println("================================");
      f.println();
      f.println("1) ONARIM_BASLAT.exe dosyasina CIFT TIKLA.");
      f.println("2) Acilan siyah pencerede sorunu kisaca yaz.");
      f.println("3) Internet varsa yapay zeka destegi, yoksa yerel");
      f.println("   teshis onerileri gelecek.");
      f.println();
      f.println("Bu USB bellek herhangi bir yazilim kurmaz ve");
      f.println("izinsiz hicbir komut calistirmaz.");
      f.close();
      Serial.println("OKU_BENI.txt yazildi.");
    }
  }

  FFat.end();  // wl_handle'i MSC'ye devretmeden once FFat'i kapat
}

// ------------------------------------------------------------------
// MSC callback'leri - dogrudan wear-levelling katmani uzerinden
// ham sektor okuma/yazma. wl_read/wl_write LBA*sectorSize ofsetini
// kendileri hesaplar.
// ------------------------------------------------------------------

static int32_t onRead(uint32_t lba, uint32_t offset, void *buffer, uint32_t bufsize) {
  if (s_wl_handle == WL_INVALID_HANDLE) return -1;
  size_t sectorSize = wl_sector_size(s_wl_handle);
  esp_err_t err = wl_read(s_wl_handle, (size_t)lba * sectorSize + offset, buffer, bufsize);
  return (err == ESP_OK) ? (int32_t)bufsize : -1;
}

static int32_t onWrite(uint32_t lba, uint32_t offset, uint8_t *buffer, uint32_t bufsize) {
  if (s_wl_handle == WL_INVALID_HANDLE) return -1;
  size_t sectorSize = wl_sector_size(s_wl_handle);
  esp_err_t err = wl_erase_range(s_wl_handle, (size_t)lba * sectorSize + offset, bufsize);
  if (err != ESP_OK) return -1;
  err = wl_write(s_wl_handle, (size_t)lba * sectorSize + offset, buffer, bufsize);
  return (err == ESP_OK) ? (int32_t)bufsize : -1;
}

static bool onStartStop(uint8_t power_condition, bool start, bool load_eject) {
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(300);

  // 1) Ilk kurulum: FAT bicimlendir + OKU_BENI.txt yaz (FFat uzerinden)
  ilkKurulumVeBenioku();

  // 2) Partition'u bul ve wear-levelling handle'ini MSC icin ac
  s_partition = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_FAT, BOLUM_ETIKETI);
  if (!s_partition) {
    Serial.println("HATA: 'ffat' partition bulunamadi! partitions_msc.csv dogru mu secildi?");
    return;
  }

  esp_err_t err = wl_mount(s_partition, &s_wl_handle);
  if (err != ESP_OK) {
    Serial.printf("HATA: wl_mount basarisiz: %d\n", err);
    return;
  }

  uint32_t sectorSize = wl_sector_size(s_wl_handle);
  uint32_t sectorCount = wl_size(s_wl_handle) / sectorSize;

  // 3) USB MSC'yi baslat
  MSC.vendorID("BLDYE");
  MSC.productID("TeknikDestek");
  MSC.productRevision("1.0");
  MSC.onRead(onRead);
  MSC.onWrite(onWrite);
  MSC.onStartStop(onStartStop);
  MSC.mediaPresent(true);
  MSC.isWritable(true);
  MSC.begin(sectorCount, sectorSize);

  USB.begin();

  Serial.printf("USB Mass Storage hazir. Sektor sayisi: %u, sektor boyu: %u\n", sectorCount, sectorSize);
  Serial.println("PC'de bir disk olarak gorunmeli.");
}

void loop() {
  // Watchdog'u beslemek icin kisa kisa bekle (uzun delay() TinyUSB/arka
  // plan gorevlerini aclikta birakip HP_SYS_HP_WDT_RESET'e yol acabiliyor)
  delay(10);
}
