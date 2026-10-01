# Belediye Teknik Destek Terminali — ESP32-P4-Pico

Sahada kullanılan USB teşhis/onarım terminali. Teknisyen Pico'yu PC'ye
takar → Pico "hazırım" sinyali gönderir → PC'de önceden kurulu dinleyici
bunu görüp bildirim gösterir → teknisyen **tek onayla** (Enter/tık)
terminali açar → internet varsa DeepSeek **ajan modu** (tool calling)
kendi kararıyla teşhis araçlarını çağırıp akıllı bir onarım önerir,
yoksa yerel kural tabanlı teşhis devreye girer.

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

- **Salt okunur araçlar** (`disk_durumu`, `event_log_oku`, `servis_durumu`,
  `baslangic_programlari`, `ag_durumu`) — sistemi değiştirmez, onay
  istenmeden otomatik çalışır.
- **Salt okunur araçlar** ayrıca `kaynak_kullanimi` (anlık CPU/RAM ve en
  çok kaynak tüketen süreçler) içerir.
- **Onarım araçları** (`sfc_tarama`, `dism_onarim`, `dns_temizle`,
  `ip_yenile`, `disk_temizligi`, `yazici_kuyrugu_temizle`, `disk_kontrolu`,
  `windows_update_sifirla`, `geri_yukleme_noktasi`, `defender_tarama`) —
  sistemi değiştirir, model bunlardan birini çağırmak istediğinde ekranda
  **"Çalıştırılsın mı? [E/h]"** diye sorulur, onaylanmadan çalışmaz. AI,
  riskli bir onarıma başlamadan önce `geri_yukleme_noktasi` aracını
  önce çağırmaya teşvik edilir (sistem talimatında tanımlı).

### Diğer özellikler

- **Sık sorun kısayolları**: `sik` komutu, en yaygın 9 şikayeti numaralı
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
```

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
   da `sik` yazıp hazır 9 şikayetten birini numarayla seç.
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
