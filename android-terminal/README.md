# ERDEMUSB Android Hızlandırıcı — PC Terminali (ADB)

Telefonunu **USB ile PC'ye bağlayıp**, PC'de çalışan bu terminalden
yönetip hızlandırmak için. `pc-terminal/pc_terminal.py` ile aynı ruhta:
renkli, kategorili, **her işlemden önce onay isteyen** bir terminal —
farkı, PC'yi değil, bağlı Android telefonunu hedeflemesi.

## Yapay zekâ / internet kullanmaz

Bu script hiçbir ağa bağlanmaz, DeepSeek ya da başka bir buluta istek
atmaz. Sadece `adb` (Android Debug Bridge) üzerinden, doğrudan telefona
yerel komutlar gönderir — tamamen `android-app/` (telefona kurulan
uygulama) ile aynı "AI yok" ilkesinde, ama PC'den terminal üzerinden
çalışır.

## Kurulum

### 1) PC'ye `adb` kur

- [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools)'u indir.
- Zip'i aç, içindeki `adb.exe` (Windows) dosyasını ya PATH'ine ekle ya da
  doğrudan bu klasöre (`android-terminal/`) kopyala — script onu otomatik
  bulur.

### 2) Telefonda USB hata ayıklamayı aç

1. **Ayarlar → Telefon Hakkında → Yapı Numarası**'na art arda 7 kere dokun
   ("Artık geliştiricisiniz" mesajı çıkana kadar) — Geliştirici
   Seçenekleri açılır.
2. **Ayarlar → Sistem → Geliştirici Seçenekleri → USB Hata Ayıklama**'yı
   aç.
3. Telefonu PC'ye USB kablosuyla bağla. Telefon ekranında çıkan
   **"Bu bilgisayara güven?"** sorusuna **İzin Ver** de (bu onay olmadan
   script telefona hiçbir komut gönderemez).

### 3) Çalıştır

```powershell
cd android-terminal
python android_terminal.py
```

(İstersen `derle.ps1` ile tek-exe'ye de paketleyebilirsin — bkz. aşağı.)

## Neler yapabiliyor?

- **Teşhis** (salt okunur): cihaz bilgisi, pil durumu, depolama/RAM
  kullanımı, en büyük uygulamalar, çalışan process'ler.
- **Hızlandırma**: tüm uygulamaların önbelleğini temizler (`pm
  trim-caches` — veriye dokunmaz, Android'in kendi güvenli mekanizması),
  sistem animasyonlarını hızlandırır/eski haline döndürür.
- **Uygulama yönetimi**: bir uygulamayı zorla durdurur, verisini
  temizler (⚠️ bu, önbellekten farklı olarak giriş bilgileri dahil TÜM
  uygulama verisini siler — geri alınamaz, bilerek ayrı ve daha sert
  uyarılı), ya da kullanıcıdan kaldırır (`pm uninstall -k --user 0` —
  kalıcı silme değildir, `adb shell cmd package install-existing
  <paket>` ile geri gelir).

Kritik sistem paketleri (`com.android.systemui`, `com.google.android.gms`
vb.) kod içinde bir koruma listesiyle (`KORUMALI_PAKETLER`) kaldırma/veri
temizleme işlemlerinden **bilerek hariç tutulmuştur** — telefonu
bozabilecek bir işlemi script kendiliğinden engeller.

## Tek-exe olarak derleme (opsiyonel)

```powershell
cd android-terminal
powershell -ExecutionPolicy Bypass -File .\derle.ps1
```

Çıktı: `dist\ANDROID_HIZLANDIRICI.exe` — `adb.exe`'yi yine aynı klasöre
koyman gerekir (PyInstaller exe'nin içine gömmüyoruz, ayrı dosya olarak
kalıyor).
