package com.erdemusb.hizlandirici

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.BatteryManager
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.StatFs
import android.provider.Settings
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.ListView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import java.io.File
import java.util.Locale
import java.util.concurrent.Executors

/**
 * ERDEMUSB Hizlandirici - Android
 * --------------------------------
 * pc-terminal'deki "hizlandir" sihirbazinin Android karsiligi: cihazin
 * depolama/RAM/pil durumunu ozetler, en cok yer kaplayan uygulamalari
 * listeler ve ilgili sistem ayarlarina (Depolama, Pil, Uygulamalar)
 * tek dokunusla goturur.
 *
 * Bilerek INTERNET izni YOK (bkz. AndroidManifest.xml) - bu surum hicbir
 * zaman aga baglanmaz, yapay zeka kullanmaz. Her sey cihaz uzerinde,
 * genel/herkese acik Android API'leriyle hesaplanir. Android'de uclunci
 * parti bir uygulamanin baska bir uygulamanin onbellegini kok yetkisi
 * olmadan silmesi mumkun degildir (guvenlik sandbox'i) - bu yuzden
 * "temizle" yerine ilgili sistem ayar ekranini aciyoruz, son onayi her
 * zaman kullanici kendi elceriyle veriyor (ERDEMUSB'nin GoodUSB ilkesiyle
 * ayni mantik: hicbir sey onaysiz/otomatik calismaz).
 */
class MainActivity : AppCompatActivity() {

    private lateinit var raporMetni: TextView
    private lateinit var uygulamaListesi: ListView
    private val arkaPlanHavuzu = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        raporMetni = findViewById(R.id.raporMetni)
        uygulamaListesi = findViewById(R.id.uygulamaListesi)

        findViewById<Button>(R.id.yenileButonu).setOnClickListener { raporuYenile() }
        findViewById<Button>(R.id.depolamaButonu).setOnClickListener { depolamaAyarlariniAc() }
        findViewById<Button>(R.id.pilButonu).setOnClickListener { pilAyarlariniAc() }
        findViewById<Button>(R.id.uygulamalarButonu).setOnClickListener { uygulamaAyarlariniAc(null) }
        findViewById<Button>(R.id.onbellekButonu).setOnClickListener { kendiOnbellegimiTemizle() }

        raporuYenile()
    }

    // ------------------------------------------------------------
    // Sistem ozeti (RAM, depolama, pil, cihaz bilgisi)
    // ------------------------------------------------------------

    private fun raporuYenile() {
        raporMetni.text = sistemRaporuOlustur()
        uygulamaListesiniYukle()
    }

    private fun sistemRaporuOlustur(): String {
        val satirlar = StringBuilder()

        satirlar.append("Cihaz: ${Build.MANUFACTURER} ${Build.MODEL}\n")
        satirlar.append("Android: ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})\n\n")

        // RAM
        val am = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memInfo = ActivityManager.MemoryInfo()
        am.getMemoryInfo(memInfo)
        val toplamRamGb = memInfo.totalMem / 1024.0 / 1024.0 / 1024.0
        val bosRamGb = memInfo.availMem / 1024.0 / 1024.0 / 1024.0
        val ramYuzde = 100.0 * (1.0 - memInfo.availMem.toDouble() / memInfo.totalMem.toDouble())
        satirlar.append(
            String.format(
                Locale.getDefault(),
                "RAM: %.1f / %.1f GB kullanimda (%%%.0f)%s\n",
                toplamRamGb - bosRamGb, toplamRamGb, ramYuzde,
                if (memInfo.lowMemory) "  [DUSUK BELLEK!]" else ""
            )
        )

        // Depolama
        try {
            val yol = Environment.getDataDirectory()
            val stat = StatFs(yol.path)
            val toplamGb = stat.totalBytes / 1024.0 / 1024.0 / 1024.0
            val bosGb = stat.availableBytes / 1024.0 / 1024.0 / 1024.0
            val doluYuzde = 100.0 * (1.0 - stat.availableBytes.toDouble() / stat.totalBytes.toDouble())
            satirlar.append(
                String.format(
                    Locale.getDefault(),
                    "Depolama: %.1f GB bos / %.1f GB toplam (%%%.0f dolu)\n",
                    bosGb, toplamGb, doluYuzde
                )
            )
            if (bosGb < 1.0) {
                satirlar.append("  UYARI: Bos alan 1 GB'in altinda, cihaz yavaslayabilir!\n")
            }
        } catch (e: Exception) {
            satirlar.append("Depolama bilgisi alinamadi: ${e.message}\n")
        }

        // Pil
        try {
            val pilDurumu = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            if (pilDurumu != null) {
                val seviye = pilDurumu.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
                val olcek = pilDurumu.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
                val yuzde = if (seviye >= 0 && olcek > 0) (100 * seviye / olcek) else -1
                val sarjDurumu = pilDurumu.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
                val sarjOluyorMu = sarjDurumu == BatteryManager.BATTERY_STATUS_CHARGING ||
                    sarjDurumu == BatteryManager.BATTERY_STATUS_FULL
                satirlar.append("Pil: %$yuzde${if (sarjOluyorMu) " (sarj oluyor)" else ""}\n")
            }
        } catch (e: Exception) {
            satirlar.append("Pil bilgisi alinamadi: ${e.message}\n")
        }

        return satirlar.toString().trimEnd()
    }

    // ------------------------------------------------------------
    // En cok yer kaplayan uygulamalar (APK boyutuna gore, yaklasik)
    // ------------------------------------------------------------

    private data class UygulamaBilgisi(val ad: String, val paketAdi: String, val boyutBayt: Long)

    private fun uygulamaListesiniYukle() {
        arkaPlanHavuzu.execute {
            val pm = packageManager
            val uygulamalar: List<ApplicationInfo> = try {
                pm.getInstalledApplications(PackageManager.GET_META_DATA)
            } catch (e: Exception) {
                emptyList()
            }

            val liste = uygulamalar
                .filter { (it.flags and ApplicationInfo.FLAG_SYSTEM) == 0 } // sadece kullanicinin kurdugu uygulamalar
                .mapNotNull { app ->
                    try {
                        val boyut = File(app.sourceDir).length()
                        UygulamaBilgisi(
                            ad = pm.getApplicationLabel(app).toString(),
                            paketAdi = app.packageName,
                            boyutBayt = boyut
                        )
                    } catch (e: Exception) {
                        null
                    }
                }
                .sortedByDescending { it.boyutBayt }
                .take(30)

            runOnUiThread {
                val gosterilecek = liste.map {
                    "${it.ad} — ${boyutMetni(it.boyutBayt)}"
                }
                val adapter = ArrayAdapter(
                    this@MainActivity,
                    android.R.layout.simple_list_item_1,
                    gosterilecek
                )
                uygulamaListesi.adapter = adapter
                uygulamaListesi.setOnItemClickListener { _, _, pozisyon, _ ->
                    uygulamaAyarlariniAc(liste[pozisyon].paketAdi)
                }
            }
        }
    }

    private fun boyutMetni(bayt: Long): String {
        val mb = bayt / 1024.0 / 1024.0
        return if (mb >= 1024) String.format(Locale.getDefault(), "%.2f GB", mb / 1024.0)
        else String.format(Locale.getDefault(), "%.1f MB", mb)
    }

    // ------------------------------------------------------------
    // Sistem ayar ekranlarini acma (asil silme/temizleme islemini
    // kullanici kendi onayiyla orada yapar - onaysiz/otomatik hicbir
    // sey calismaz)
    // ------------------------------------------------------------

    private fun depolamaAyarlariniAc() {
        val niyet = Intent(Settings.ACTION_INTERNAL_STORAGE_SETTINGS)
        guvenliBaslat(niyet, "Depolama ayarlari acilamadi")
    }

    private fun pilAyarlariniAc() {
        val niyet = Intent(Settings.ACTION_BATTERY_SAVER_SETTINGS)
        guvenliBaslat(niyet, "Pil ayarlari acilamadi")
    }

    private fun uygulamaAyarlariniAc(paketAdi: String?) {
        val niyet = if (paketAdi != null) {
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.fromParts("package", paketAdi, null)
            }
        } else {
            Intent(Settings.ACTION_APPLICATION_SETTINGS)
        }
        guvenliBaslat(niyet, "Uygulama ayarlari acilamadi")
    }

    private fun guvenliBaslat(niyet: Intent, hataMetni: String) {
        try {
            startActivity(niyet)
        } catch (e: Exception) {
            Toast.makeText(this, "$hataMetni: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun kendiOnbellegimiTemizle() {
        // Bir uygulama, kok yetkisi olmadan sadece KENDI onbellegini
        // silebilir - baska uygulamalarin onbellegine erisemez. Bu
        // yuzden bu buton sadece ERDEMUSB'nin kendi onbellegini
        // temizler, ornek/demo amaclidir; asil yer acma islemi yukaridaki
        // "Depolama Ayarlari" / uygulama bazli "Ayarlari Ac" ile olur.
        try {
            cacheDir.deleteRecursively()
            externalCacheDir?.deleteRecursively()
            Toast.makeText(this, "ERDEMUSB'nin kendi onbellegi temizlendi.", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(this, "Onbellek temizlenemedi: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }
}
