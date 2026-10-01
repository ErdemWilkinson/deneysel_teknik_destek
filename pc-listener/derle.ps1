# DINLEYICI.exe uretir - PC baslangicina eklenecek, Pico'yu dinleyen program.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Python bagimliliklari kuruluyor..."
python -m pip install --upgrade pip | Out-Null
python -m pip install -r requirements.txt

Write-Host "Tek-exe derleniyor (PyInstaller)..."
python -m PyInstaller --onefile --console --name DINLEYICI --clean dinleyici.py

Write-Host ""
Write-Host "Tamamlandi: $PSScriptRoot\dist\DINLEYICI.exe" -ForegroundColor Green
Write-Host "Bu dosyayi ONARIM_BASLAT.exe ile ayni klasore koy (orn. C:\TeknikDestek\)"
Write-Host "ve Windows Baslangic klasorune kisayol ekle (Win+R -> shell:startup)."
