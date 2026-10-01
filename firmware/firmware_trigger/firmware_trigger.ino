/*
 * Waveshare ESP32-P4-Pico — Teknik Destek Terminali TETIKLEYICISI
 * -------------------------------------------------------------------
 * Bu firmware, kartin SADECE calisan USB-C/Serial (CH343) baglantisini
 * kullanir. ESP32-P4'un native USB OTG'si (MSC icin gerekliydi) bu
 * kartta ayri, lehim gerektiren 4 pin ustunden ciktigi icin MSC/USB
 * bellek YAPILAMIYOR (donanim kisitlamasi, bkz. proje notlari).
 *
 * Bu yuzden Pico, bir "USB bellek" degil, bir "akilli anahtar/tetikleyici"
 * olarak calisir:
 *   - Takilinca, Serial (COM port) uzerinden surekli "HAZIR" sinyali yayar.
 *   - PC'de onceden kurulu kucuk bir dinleyici (pc-listener/dinleyici.py)
 *     bu sinyali gorunce ekranda bir bildirim gosterir.
 *   - Teknisyen bildirime TEK TIKLA basar, ONARIM_BASLAT.exe acilir.
 *
 * Bu cihaz HICBIR sekilde klavye/fare (HID) taklidi yapmaz, hicbir
 * komutu otomatik calistirmaz. Butun tetikleme, kullanicinin kendi
 * tikiyla gerceklesir - BadUSB mekanizmasi DEGILDIR.
 */

#define HAZIR_SINYALI "TEKNIKDESTEK_HAZIR"
#define PING_ARALIGI_MS 1000

unsigned long sonPing = 0;

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("Teknik Destek Terminali tetikleyicisi baslatildi.");
}

void loop() {
  unsigned long simdi = millis();
  if (simdi - sonPing >= PING_ARALIGI_MS) {
    sonPing = simdi;
    Serial.println(HAZIR_SINYALI);
  }

  // Dinleyiciden gelebilecek "ACK" (onay) mesajini okuyup yok sayiyoruz,
  // sadece buffer'in dolmasini onlemek icin.
  while (Serial.available() > 0) {
    Serial.read();
  }

  delay(10);
}
