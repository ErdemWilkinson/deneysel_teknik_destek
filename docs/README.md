# ERDEMUSB — Taşınabilir Teknik Destek Terminali (ESP32-P4-Pico)

Sahada kullanılan USB teşhis/onarım terminali. Teknisyen Pico'yu PC'ye
takar → Pico "hazırım" sinyali gönderir → PC'de önceden kurulu dinleyici
bunu görüp bildirim gösterir → teknisyen **tek onayla** (Enter/tık)
terminali açar → internet varsa DeepSeek **ajan modu** (tool calling)
kendi kararıyla teşhis araçlarını çağırıp akıllı bir onarım önerir,
yoksa yerel kural tabanlı teşhis devreye girer.

Terminal (`ONARIM_BASLAT.exe`) renkli, kategorilere ayrılmış bir menüyle
çalışır: **teşhis** (cyan), **hızlandırma** (yeşil), **güvenlik** (sarı),
**ağ** (mavi), **disk** (mor), **sistem onarımı** (kırmızı). Hiçbir komut
onaysız çalışmaz; salt okunur teşhis araçları dışındaki her şey açıkça
`[E/h]` ile sorulur.

## Hızlı başlangıç (ilk kurulum, tek tık)

`.exe` dosyaları bilerek repoda **yok** (içlerine DeepSeek API anahtarın
gömülebiliyor, güvenlik için GitHub'a girmiyor) — kendi PC'nde bir kere
kendin üretmen gerekiyor:

1. [Python](https://www.python.org/downloads/) kur — kurulum ekranında
   **"Add python.exe to PATH"** kutusunu işaretlemeyi unutma.
2. `pc-terminal/pc_terminal.py` içindeki `DEEPSEEK_API_KEY` değişkenine
   kendi API anahtarını yaz (boş bırakırsan sorun değil, o zaman sadece
   internet gerektirmeyen yerel teşhis/hızlandırma araçları çalışır).
3. Repo kökündeki **`HAZIRLA.bat`** dosyasına çift tıkla. Bu, Python
   paketlerini kurar, **üç** exe'yi derler ve doğru klasörlere
   (`usb-paket/`, `dagitim/`) otomatik kopyalar:
   - `ONARIM_BASLAT.exe` — 2. adımda anahtar girdiysen AI destekli,
     girmediysen zaten otomatik yerel çalışır.
   - `ONARIM_BASLAT_YEREL.exe` — anahtar ne olursa olsun **internete/
     DeepSeek'e hiçbir zaman bağlanmaz**, sadece yerel kural tabanlı
     teşhis/hızlandırma araçlarını kullanır (`pc-terminal/derle_yerel.ps1`
     anahtarı derleme sırasında geçici bir kopyada zorla devre dışı
     bırakır).
   - `DINLEYICI.exe` — PC'ye önceden kurulacak bildirim dinleyicisi.
4. `usb-paket/` klasörünün tamamını USB belleğine kopyala — içinde her
   iki `ONARIM_BASLAT*.exe` de var, hangisini istersen çift tıklarsın.
5. (Opsiyonel) Bir PC'de bildirimli otomatik algılama istiyorsan:
   `dagitim/DINLEYICI.exe` ve istediğin `ONARIM_BASLAT*.exe`'yi o PC'de
   bir klasöre (örn. `C:\TeknikDestek\`) kopyala, `DINLEYICI.exe`'nin
   kısayolunu Windows Başlangıç klasörüne ekle (`Win+R` → `shell:startup`).

## Önemli: Donanım kısıtlaması ve mimari kararı

Waveshare ESP32-P4-Pico'da **tek USB-C soketi**, kartın üzerindeki ayrı
bir **CH343 USB-UART çipine** bağlıdır — bu port sadece seri haberleşme
(flashleme, Serial Monitor) taşır. ESP32-P4'ün **native USB OTG**
donanımı (USB Mass Storage/"USB bellek gibi görünme" için gereken tek
yol) karttan **ayrı, lehim gerektiren 4 pinlik bir header** üzerinden
çıkar. Bu yüzden:

- ❌ Pico'yu **USB bellek (MSC)** olarak kullanamıyoruz (lehimsiz).
- ❌ Pico'yu **HID klavye** olarak kullanıp otomatik komut çalıştırmak
  **kasıtlı olarak tercih edilmedi** — bu, kullanıcı onayı olmadan
  otomatik kod çalıştıran klasik BadUSB mekanizmasının ta kendisidir;
  amaç ne olursa olsun bu projede bilinçli olarak kullanılmıyor.
- ✅ Bunun yerine Pico, mevcut çalışan Serial/USB-C bağlantısı üzerinden
  bir **"akıllı tetikleyici"** rolü görür: PC'de önceden kurulu bir
  dinleyici programı Pico'nun sinyalini görünce bildirim gösterir,
  teknisyen **kendi onayıyla** (tek tuş/tık) terminali açar. Hiçbir
  otomatik/onaysız komut çalıştırma yoktur.

### DeepSeek ajan modu nasıl çalışır

`pc_terminal.py` içindeki `ARAC_KAYDI` sözlüğü, DeepSeek'in çağırabileceği
araçların **beyaz listesidir**. Model asla keyfi bir komut üretip
çalıştıramaz — sadece bu listedeki isimlerden birini "çağırmak istiyorum"
der, programın kendisi o aracı yorumlayıp çalıştırır:

- **Salt okunur araçlar** (`hiz_raporu`, `disk_durumu`, `disk_sagligi`,
  `event_log_oku`, `servis_durumu`, `baslangic_programlari`,
  `kaynak_kullanimi`, `surucu_sorunlari`, `ag_durumu`) — sistemi
  değiştirmez, onay istenmeden otomatik çalışır.
- **Onarım ve hızlandırma araçları** (`geri_yukleme_noktasi`,
  `disk_temizligi`, `baslangic_programi_kapat`, `guc_plani_yuksek`,
  `gorsel_efekt_performans`, `uygulamalari_guncelle`, `windows_update_tara`,
  `defender_tarama`, `sfc_tarama`, `dism_onarim`, `disk_kontrolu`,
  `dns_temizle`, `ip_yenile`, `ag_sifirla`, `yazici_kuyrugu_temizle`,
  `windows_update_sifirla`) —
  sistemi değiştirir, model bunlardan birini çağırmak istediğinde ekranda
  **"Çalıştırılsın mı? [E/h]"** diye sorulur, onaylanmadan çalışmaz. AI,
  riskli bir onarıma başlamadan önce `geri_yukleme_noktasi` aracını
  önce çağırmaya teşvik edilir (sistem talimatında tanımlı).

### Hızlandırma sihirbazı (`hizlandir`)

Eski/yavaşlamış bir PC için tek komut: önce `hiz_raporu` ile yavaşlığın
nedenini özetler (Windows sürümü, RAM, disk türü HDD/SSD, boş alan, açılış
programı sayısı, güç planı, görsel efektler, geçici dosya boyutu), açılış
programlarından kapatılacakları sorar, sonra her adımı **tek tek onay
isteyerek** uygular: geri yükleme noktası → disk temizliği → görsel
efektler → güç planı (dizüstünde atlanır) → programları güncelleme (winget)
→ Windows Update → Defender taraması. Sonunda donanım önerisi verir (HDD
ise SSD, 8 GB altı RAM ise RAM yükseltmesi). İnternet ve yapay zekâ
gerekmez.

### Yönetici yetkisi

Onarım ve hızlandırma araçlarının çoğu yönetici ister. Program yönetici
olarak açılmadıysa başta sorar ve UAC onayıyla kendini yönetici olarak
yeniden açar. Yönetici olmadan da salt okunur teşhis araçları çalışır.

### Güvenlik: AI parametreleri

AI'nin araçlara gönderdiği parametreler (servis adı, sürücü harfi, program
adı, açıklama) komutların içine yazıldığı için yalnızca harf, rakam,
boşluk ve `_ . -` karakterlerine izin verilir; aksi halde parametre
yok sayılır. Böylece bir parametrenin içine gizlenmiş komut onaysız
çalıştırılamaz.

### Diğer özellikler

- **Sık sorun kısayolları**: `liste` komutu, en yaygın 9 şikayeti numaralı
  listeden seçmeyi sağlar — teknisyen her seferinde yazmak zorunda kalmaz.
- **Demirbaş/PC kayıt defteri**: her oturum sonunda, girilen demirbaş/PC
  adıyla birlikte `demirbas_kayit_defteri.csv` dosyasına bir satır eklenir
  (USB üzerinde birikir — envanter/rapor amaçlı).
- **Oturum sonu özet raporu**: her oturumda görüşülen sorunlar, verilen
  cevaplar ve çalıştırılan araçların dökümü `raporlar/rapor_*.txt` olarak
  **USB'nin kendisine** yazılır; teknisyen USB'yi çıkardığında geçmiş de
  yanında gider.

DeepSeek'e gönderilen her metinden (kullanıcı sorunu + araç çıktıları)
`gizlilik_filtrele()` fonksiyonu bilgisayar adını, kullanıcı adını,
`C:\Users\<ad>\...` yollarını ve e-posta benzeri dizgileri maskeler.

## Bu BadUSB değildir

- Cihaz **HID (klavye/fare) değildir** — hiçbir tuşa otomatik basmaz,
  hiçbir komutu kendi başına çalıştırmaz.
- Cihaz sade bir **USB Mass Storage (flash disk)** olarak görünür —
  tıpkı normal bir USB bellek gibi. Teknisyen programı **kendi elleriyle
  çift tıklayarak** başlatır.
- `.exe` içindeki hiçbir onarım komutu (`sfc`, `DISM`, `ipconfig` vb.)
  kullanıcı onayı olmadan çalışmaz; "Hızlı onarım" menüsünde her
  komuttan önce `[E/h]` onayı istenir.
- DeepSeek'e yalnızca kullanıcının yazdığı sorun metni ve kişisel
  olmayan bir sistem özeti (işletim sistemi sürümü, disk doluluğu,
  son sistem hataları) gönderilir.
- Tüm işlemler yerel log dosyasına yazılır.

## Mimari

```
[ESP32-P4-Pico]  --USB-C (Serial)-->  [PC: DINLEYICI.exe arka planda calisir]
  her 1sn "HAZIR"                              │
  sinyali yollar                     Pico'yu gorunce bildirim gosterir
                                                │
                                   teknisyen ONAYLAR (Enter/tik)
                                                ▼
                                      [ONARIM_BASLAT.exe acilir]
                                                │
                           internet var mi? ────┼── evet → DeepSeek API (ajan)
                                                └── hayir → yerel kural
                                                             tabanli teshis
```

## Klasör yapısı

```
firmware/firmware_trigger/  ESP32-P4'e yüklenecek - Serial üzerinden "hazırım" sinyali yollar
firmware/firmware_msc/      (Kullanılmıyor) MSC denemesi - bu kartta donanımsal olarak çalışmıyor, referans için duruyor
pc-listener/                 PC'ye önceden kurulacak dinleyici (DINLEYICI.exe)
pc-terminal/                 Asıl onarım terminali (ONARIM_BASLAT.exe)
pc-bridge/                   (Önceki) seri-port köprü prototipi — artık kullanılmıyor
android-app/                 Telefon (Android) için ayrı, bağımsız hızlandırıcı uygulaması
```

## Android sürümü (telefon hızlandırıcı)

`android-app/` klasöründe, PC tarafındaki `hizlandir` sihirbazının
Android karşılığı olan, **ayrı bir uygulama** var: depolama/RAM/pil
durumunu özetler, en çok yer kaplayan uygulamaları listeler, ilgili
sistem ayarlarına (Depolama, Pil, Uygulamalar) tek dokunuşla götürür.
Bu sürüm de **internet/yapay zekâ kullanmaz** — `AndroidManifest.xml`'de
`INTERNET` izni bilerek yok, tüm teşhis cihaz üzerinde hesaplanır.
Pico/USB ile ilgisi yoktur, bağımsız bir Android Studio projesidir.
Derleme adımları: [android-app/README.md](../android-app/README.md).

## Her PC'de çalışması (dinleyici kurulu olmayan PC'ler)

Dinleyici yalnızca önceden kurulduğu PC'lerde çalışır. `ONARIM_BASLAT.exe`
ise kurulum istemez; herhangi bir Windows 10/11 PC'de çift tıklayınca
çalışır. Hiç görülmemiş bir PC'de kullanmak için iki yol var:

1. **Pico'nun USB OTG pinlerini lehimlemek** (önerilen, kalıcı çözüm):
   ESP32-P4'ün native USB'si karttaki 4 pinlik header'a çıkar. Bu pinlere
   bir USB kablo lehimlenirse `firmware/firmware_msc` ile Pico normal bir
   USB bellek gibi görünür ve içindeki `ONARIM_BASLAT.exe` her PC'de çift
   tıklanarak açılır — dinleyiciye bile gerek kalmaz. Adım adım lehim
   rehberi, güvenlik uyarıları ve parça listesi: **[docs/HER_PC_ICIN.md](HER_PC_ICIN.md)**.
2. **Lehimsiz yol** (hemen, alet gerektirmez): `ONARIM_BASLAT.exe`'yi ve
   `usb-paket` içeriğini sıradan bir USB belleğe kopyalayıp teknisyen
   çantasında Pico'nun yanında taşımak.

Dinleyici yalnızca Pico'nun USB-seri çipini (WCH CH343, VID 0x1A86) ve
ESP32'nin kendi USB'sini (Espressif, VID 0x303A) dinler; PC'deki diğer seri
cihazlara dokunmaz.

## Kurulum — Üç Aşama

### Aşama 1: ESP32-P4'e tetikleyici firmware'i yükle (bir kerelik, senin yapacağın)

1. Arduino IDE kur, **Kart Yöneticisi**'nden `esp32` (Espressif) paketini
   kur — ESP32-P4 destekli güncel sürüm (3.x) gerekir.
2. **Araçlar → Kart** → `ESP32P4 Dev Module`.
3. **Araçlar → Flash Size** → kartın gerçek kapasitesi olan **32MB** seç.
4. `firmware/firmware_trigger/firmware_trigger.ino` dosyasını yükle.
5. Seri Monitör'de (115200 baud) her saniye `TEKNIKDESTEK_HAZIR` satırını
   görmelisin.

### Aşama 2: Onarım terminalini derle

```powershell
cd pc-terminal
# Önce DEEPSEEK_API_KEY'i pc_terminal.py içine gir (ya da ortam değişkeni kullan)
powershell -ExecutionPolicy Bypass -File .\derle.ps1
```

Bu, `pc-terminal\dist\ONARIM_BASLAT.exe` dosyasını üretir.

### Aşama 3: PC dinleyicisini derle ve belediye PC'lerine dağıt (PC başına bir kerelik)

```powershell
cd pc-listener
powershell -ExecutionPolicy Bypass -File .\derle.ps1
```

Bu, `pc-listener\dist\DINLEYICI.exe` dosyasını üretir. Her belediye
PC'sinde:

1. Bir klasör oluştur (örn. `C:\TeknikDestek\`).
2. `DINLEYICI.exe` ve `ONARIM_BASLAT.exe` dosyalarını bu klasöre kopyala.
3. `DINLEYICI.exe`'nin bir kısayolunu **Windows Başlangıç klasörüne**
   ekle: `Win+R` → `shell:startup` → kısayolu buraya yapıştır. Böylece
   PC her açıldığında dinleyici otomatik arka planda başlar.

> Bu dağıtımı tüm belediye PC'lerine toplu yapmak için IT biriminin
> mevcut yazılım dağıtım aracını (GPO, SCCM vb.) kullanman önerilir.

## Teknisyenin yapacağı (saha kullanımı)

1. USB-C kabloyu sorunlu PC'ye tak (PC'de dinleyici zaten çalışıyor
   olmalı — Aşama 3'te kurulmuş olması gerekir).
2. Birkaç saniye içinde ekranda/konsol penceresinde bir bildirim belirir:
   *"Teknik Destek Terminali Hazır — Enter'a bas"*.
3. Enter'a bas (ya da 20 saniye içinde onaylamazsan tekrar denemek için
   Pico'yu çıkarıp takman yeterli).
4. `ONARIM_BASLAT.exe` açılır. İstenirse demirbaş/PC adını yaz (boş da
   bırakılabilir).
5. Sorunu kısaca yaz (örn: `bilgisayar cok yavas acilirken takiliyor`) ya
   da `liste` yazıp hazır 9 şikayetten birini numarayla seç. Yavaş bir PC
   için doğrudan `hizlandir` yaz.
6. İnternet varsa DeepSeek ajanının kendi seçtiği teşhis adımlarını ve
   önerisini, yoksa yerel teşhis listesini oku. Sistemi değiştiren her
   adımda ayrıca onay istenir.
7. `hizli` yazarak önceden tanımlı onarım komutlarından birini seçip
   onaylayarak doğrudan çalıştırabilirsin.
8. `cikis` ile programı kapat — oturumun özeti otomatik olarak
   `raporlar/` klasörüne ve `demirbas_kayit_defteri.csv`'ye yazılır.
   Ardından USB'yi çıkar.

## DeepSeek API anahtarını ayarlama

`pc-terminal/pc_terminal.py` içinde:

```python
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "BURAYA_DEEPSEEK_API_ANAHTARINI_YAZ")
```

Anahtarı doğrudan buraya yazabilir ya da derlemeden önce
`$env:DEEPSEEK_API_KEY = "sk-..."` ile ortam değişkeni verebilirsin.
**Anahtarı genel bir repoya push etme** — USB'nin içinde sabit kodlu
gideceği için cihaz kaybolursa anahtarı iptal edip yenisini çıkarman
gerekir (DeepSeek panelinden).

## Yerel teşhis motoru nasıl genişletilir

`pc_terminal.py` içindeki `ANAHTAR_KELIME_KURALLARI` listesine yeni bir
`(anahtar_kelimeler, oneriler)` çifti eklemen yeterli — internet
olmadığında bu kurallar devreye girer.

## Yeni bir araç (DeepSeek ajan + hızlı menü) ekleme

`pc_terminal.py` içindeki `ARAC_KAYDI` sözlüğüne yeni bir giriş eklemen
yeterli: bir Python fonksiyonu yaz (`arac_...` adıyla), sonra
`ARAC_KAYDI`'na `aciklama`, `params`, `destructive` ve `fn` alanlarıyla
kaydet. Hem DeepSeek ajan modu hem de `hizli` menüsü bu tek kayıttan
otomatik beslenir — iki ayrı yerde tanım tutmana gerek yok.
`destructive: True` verirsen otomatik olarak onay istenir.
