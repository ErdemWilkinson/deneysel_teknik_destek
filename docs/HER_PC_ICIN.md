# Her PC'de çalışması — Pico'yu gerçek bir USB belleğe çevirmek (lehim)

Bu belge, **ERDEMUSB**'nin dinleyici kurulu olmayan, hiç görülmemiş bir
PC'de de çift tıklamayla çalışması için Waveshare ESP32-P4-Pico'nun
**USB-OTG pinlerini lehimleme** adımlarını anlatır. Bunu yapmak
istemiyorsan README'deki "lehimsiz yol" (Pico'yu dinleyici kurulu
PC'lerde kullanmak, ya da `ONARIM_BASLAT.exe`'yi sıradan bir USB bellekte
çantada taşımak) seni aynı sonuca, aletsiz, hemen götürür.

## Neden lehim gerekiyor?

Karttaki **tek USB-C soketi**, ESP32-P4'e değil, karttaki ayrı bir
**CH343 USB-UART çipine** bağlı — bu port sadece seri haberleşme
taşıyabilir (flashleme, Serial Monitor), USB bellek (Mass Storage)
*olamaz*. ESP32-P4'ün kendi **native USB-OTG** donanımı — Mass Storage
için gereken tek yol — karttan ayrı, **lehimsiz, boş bir 4 pinlik
header** üzerinden çıkıyor. O header'a bir USB-C/USB-A kablo
lehimlenmeden ESP32-P4'ün native USB'si dışarıya çıkmaz.

## ÖNCE OKU — Güvenlik uyarıları

- **Pico'yu PC'den ve her güç kaynağından çıkar**, lehim işlemini
  fişsiz/güçsüz yap.
- **Doğru pinleri lehimlediğinden kesinlikle emin ol.** Bu belge pin
  numaralarını *tahmin ederek* vermez — Waveshare'in ESP32-P4-Pico
  için yayınladığı **resmi ürün sayfası/şematik/pinout diyagramını**
  (wiki.waveshare.com üzerindeki ESP32-P4-Pico sayfası) açıp, kartın
  üzerindeki **"USB-OTG" / "Native USB" / "USB_DM, USB_DP"** olarak
  etiketlenmiş 4 pinlik header'ı bul. Yanlış pinlere (özellikle güç
  pinlerine ters polarite ile) lehim yapmak kartı veya bağladığın PC'yi
  **kalıcı olarak bozabilir** — bu yüzden burada "pin 3 ve 4" gibi
  numara **vermiyorum**; kartın üzerindeki serigrafi etiketine ve resmi
  şemaya bak.
- Lehim yapmadan önce kart üzerindeki etiketleri bir büyüteç/telefon
  kamerasıyla yakından fotoğrafla, her pinin adını oku.
- ESD (statik elektrik) önlemi al: topraklanmış bir yüzeyde çalış,
  mümkünse antistatik bilek bandı kullan.
- İnce uçlu bir havya (ideal: ayarlanabilir sıcaklık, ~320 °C), ince
  lehim teli (0.5-0.6 mm, kurşunsuz da olur) ve varsa flux kalemi
  kullan — kalın lehim ucu bu kadar küçük pinlerde yakın pinleri
  birbirine kısa devre yaptırabilir.
- **Lehimden sonra, PC'ye takmadan önce bir multimetre ile süreklilik
  (continuity) testi yap**: lehimlediğin iki pin arasında (USB_DM ve
  USB_DP) kısa devre OLMAMALI; her birinin kendi kablosuna doğru
  süreklilik OLMALI. Ayrıca yan yana duran, lehimlemediğin pinlerle
  aralarında da kısa devre olmadığını kontrol et.
- Sonuçtan şüphen varsa PC'ye takmadan önce ucuz/eski bir USB
  hub/kablo ile test et, doğrudan ana bilgisayara değil.

## Parça listesi

- Waveshare ESP32-P4-Pico (üzerinde boş 4 pinlik USB-OTG header'ı olan)
- USB-A veya USB-C kablo/konnektör (hurda bir kablonun ucunu kesip
  kullanabilirsin) — 4 damar: VBUS, D-, D+, GND
- İnce uçlu havya, ince lehim teli, flux (opsiyonel ama tavsiye edilir)
- Multimetre (süreklilik/continuity modu)
- Pens, üçüncü el (opsiyonel), büyüteç

## Adımlar

1. **Pico'yu PC'den çıkar.** Güçsüz çalış.
2. Waveshare'in resmi ESP32-P4-Pico sayfasındaki pinout diyagramını aç,
   **native USB-OTG / USB_DM / USB_DP** pinlerinin kart üzerindeki tam
   konumunu doğrula. Karttaki serigrafi etiketiyle şemayı karşılaştır.
3. Kestiğin USB kablonun içindeki 4 teli (genelde kırmızı=VBUS,
   beyaz=D-, yeşil=D+, siyah=GND — ama **kendi kablonda multimetre ile
   doğrula**, renk standardı her kabloda garanti değil) header'daki
   karşılık gelen pinlere lehimle. Küçük, temiz lehim noktaları yap;
   yan pinlere değmediğinden emin ol.
4. Lehim bittikten sonra **multimetre ile süreklilik testi** yap (yukarı
   bakınız). Sorun yoksa kabloyu küçük bir sıcak tutkal/bant ile
   gerilmeye karşı sabitle (pinleri koruman için).
5. Kartı **sadece seri port üzerinden** (eski CH343 USB-C portu) bir
   kere daha PC'ye takıp temel bir "merhaba dünya" ile hâlâ çalıştığını
   doğrula — lehim sırasında komşu bir pine ısı/kısa devre
   gitmediğinden emin olmak için.

## Firmware: `firmware/firmware_msc` ile yükleme

Lehim bittikten sonra, Pico'ya artık normal tetikleyici yerine **MSC
(Mass Storage)** firmware'ini yüklüyorsun — bu, Pico'yu PC'ye gerçek bir
USB bellek gibi tanıtan, içinde `ONARIM_BASLAT.exe` ve `OKU_BENI.txt`
barındıran sürümdür (`firmware/firmware_msc/firmware_msc.ino`).

1. Arduino IDE → Kart Yöneticisi → `esp32` (Espressif) paketi, 3.x sürüm.
2. **Araçlar → Kart** → `ESP32P4 Dev Module`.
3. **Araçlar → USB Mode** → **"USB-OTG (TinyUSB)"** (TinyUSB MSC ile
   Serial'in birlikte çalıştığı seçenek — `firmware_msc.ino`'nun başındaki
   yorumda da belirtilir).
4. **Araçlar → Partition Scheme** → **"Custom"**, ve bu klasördeki
   `firmware/firmware_msc/partitions_msc.csv` dosyasını özel bölüm
   tablosu olarak seç (ffat bölümü ~14.4MB, `ONARIM_BASLAT.exe`'nin
   ~8-9MB boyutuna yetiyor).
5. **Araçlar → Flash Size** → kartın gerçek kapasitesi (32MB).
6. `firmware/firmware_msc/firmware_msc.ino` dosyasını, artık lehimli
   USB-OTG hattı üzerinden PC'ye bağlıyken yükle (yükleme sırasında
   normal USB-C/seri port da gerekebilir — IDE hangi portu istiyorsa
   onu kullan).
7. İlk açılışta flash boş olduğu için Pico otomatik FAT ile biçimlenir
   ve `OKU_BENI.txt` yazılır. Ardından PC'den görünen USB diskine
   `ONARIM_BASLAT.exe` dosyasını (ve istersen `usb-paket/` içindeki
   diğer dosyaları) sürükle-bırak ile bir kere kopyala.
8. Bundan sonra Pico'yu **lehimlediğin USB hattından** herhangi bir
   PC'ye taktığında, PC onu sıradan bir USB bellek olarak görür;
   dinleyici programına ihtiyaç yoktur — teknisyen doğrudan
   `ONARIM_BASLAT.exe`'ye çift tıklar.

## Test etme

- Önce kendi PC'nde dene: Dosya Gezgini'nde yeni bir USB sürücü
  görünmeli, içinde `ONARIM_BASLAT.exe` ve `OKU_BENI.txt` olmalı.
- Çift tıkla, terminalin normal şekilde açıldığını doğrula.
- Başka, hiç görülmemiş bir Windows 10/11 PC'de dene — sürücü kurulumu
  istemeden tanınmalı.
- Bir sorun olursa (tanınmıyor, dosya bozuk görünüyor), önce lehim
  noktalarını tekrar multimetre ile kontrol et; donanım sorunlarının
  çoğu gevşek/eksik bir lehim bağlantısından kaynaklanır.

## Alternatif: Lehim yapmak istemiyorsan

İki lehimsiz yol da tamamen geçerli ve günlük kullanım için yeterli:

1. Pico'yu sadece **dinleyici kurulu PC'lerde** (`pc-listener/`) kullan —
   bildirim gelir, Enter'a basarsın, terminal açılır.
2. `ONARIM_BASLAT.exe`'yi ve `usb-paket/` klasörünü sıradan bir USB
   belleğe kopyalayıp çantanda taşı — herhangi bir PC'de çift tıklayınca
   çalışır, dinleyici veya lehim gerekmez.

Detaylar için ana [docs/README.md](README.md) dosyasına bak.
