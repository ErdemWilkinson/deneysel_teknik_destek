# ANDROID_HIZLANDIRICI.exe uretir - adb uzerinden telefonu yoneten terminal.
# Not: adb.exe exe'nin icine gomulmez, ayri dosya olarak ayni klasorde
# bulunmasi gerekir (Android SDK Platform Tools'tan).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Python bagimliliklari kuruluyor..."
python -m pip install --upgrade pip | Out-Null
python -m pip install -r requirements.txt

Write-Host "Tek-exe derleniyor (PyInstaller)..."
python -m PyInstaller --onefile --console --name ANDROID_HIZLANDIRICI --clean android_terminal.py

Write-Host ""
Write-Host "Tamamlandi: $PSScriptRoot\dist\ANDROID_HIZLANDIRICI.exe" -ForegroundColor Green
Write-Host "adb.exe'yi (Android SDK Platform Tools) bu exe ile ayni klasore koy."
