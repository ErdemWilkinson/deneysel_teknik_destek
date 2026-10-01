# Tek tikla calisan ONARIM_BASLAT.exe dosyasini uretir.
# Cikti: dist\ONARIM_BASLAT.exe  (bunu USB'nin icine, firmware'in
# sundugu mass storage bolgesine kopyalayacaksin)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Python bagimliliklari kuruluyor..."
python -m pip install --upgrade pip | Out-Null
python -m pip install -r requirements.txt

Write-Host "Tek-exe derleniyor (PyInstaller)..."
python -m PyInstaller --onefile --console --name ONARIM_BASLAT --clean pc_terminal.py

Write-Host ""
Write-Host "Tamamlandi: $PSScriptRoot\dist\ONARIM_BASLAT.exe" -ForegroundColor Green
Write-Host "Bu dosyayi USB mass storage imajinin icine kopyala."
