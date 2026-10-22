# ERDEMUSB Hızlandırıcı — Android

PC tarafındaki `hizlandir` sihirbazının Android karşılığı: telefonundaki
depolama, RAM ve pil durumunu özetler, en çok yer kaplayan uygulamaları
listeler, ilgili sistem ayarlarına (Depolama, Pil, Uygulamalar) tek
dokunuşla götürür.

## Yapay zekâ / internet kullanmaz

`AndroidManifest.xml`'de **`INTERNET` izni bilerek yok** — bu uygulama
hiçbir zaman ağa bağlanamaz, DeepSeek ya da başka bir buluta veri
göndermez. Tüm teşhis, herkese açık Android API'leri (`ActivityManager`,
`StatFs`, `BatteryManager`, `PackageManager`) ile tamamen **cihaz
üzerinde (offline)** hesaplanır.

## Neden "sil/temizle" değil de "ayarları aç"?

Android'in güvenlik modeli (sandbox), kök (root) yetkisi olmadan bir
uygulamanın **başka bir uygulamanın** önbelleğini/verisini silmesine izin
vermez — bu, kötü niyetli bir uygulamanın telefonunu bozmasını önleyen
temel bir korumadır ve ERDEMUSB bu korumayı atlamaya çalışmaz. Bunun
yerine, PC tarafındaki "her adımda onay" ilkesiyle aynı mantıkla: ilgili
sistem ayar ekranını açar, asıl silme/kaldırma işlemini **sen kendi
elinle, kendi onayınla** yaparsın.

## Derleme (APK üretme)

Bu proje, PyInstaller ile derlenen Windows `.exe`'lerin aksine, **Android
Studio** ile açılıp derlenmesi gereken bir Kotlin/Gradle projesidir:

1. [Android Studio](https://developer.android.com/studio) kur.
2. Android Studio'da **Open** → bu `android-app/` klasörünü seç.
3. İlk açılışta Gradle senkronizasyonu otomatik gerekli SDK/Gradle
   sürümlerini indirir (bu depoda `gradle-wrapper.jar` ikili dosyası
   bilerek yok — Android Studio ilk açılışta kendisi oluşturur/indirir).
4. Üstteki araç çubuğundan **Run ▶** ile telefonuna (USB hata ayıklama
   açık) ya da emülatöre doğrudan yükleyebilir, ya da
   **Build → Build Bundle(s) / APK(s) → Build APK(s)** ile
   `app/build/outputs/apk/debug/app-debug.apk` dosyasını üretip telefona
   elle kurabilirsin.
5. Telefonunda "Bilinmeyen kaynaklardan yükleme" iznini vermen gerekebilir
   (Play Store dışından APK kurulumu için).

## Klasör yapısı

```
android-app/
  app/
    src/main/
      java/com/erdemusb/hizlandirici/MainActivity.kt   -> tum mantik
      res/layout/activity_main.xml                       -> arayuz
      AndroidManifest.xml                                 -> izinler (INTERNET YOK)
    build.gradle.kts
  build.gradle.kts
  settings.gradle.kts
```

## Sınırlamalar (bilerek)

- Uygulama boyutu listesi APK dosya boyutuna dayanır (tam veri+önbellek
  boyutu için ek bir sistem izni — `PACKAGE_USAGE_STATS` — gerekir, bu
  ilk sürümde eklenmedi; "Depolama Ayarları"ndan tam detay görülebilir).
- Sadece kullanıcının kendi kurduğu uygulamalar listelenir (sistem
  uygulamaları hariç) — silinmesi anlamlı olanlar zaten bunlardır.
- Root gerektiren hiçbir işlem yoktur, bilerek.
