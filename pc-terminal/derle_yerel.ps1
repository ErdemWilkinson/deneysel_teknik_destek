# DeepSeek'siz (tamamen yerel/offline) ONARIM_BASLAT_YEREL.exe uretir.
# pc_terminal.py icindeki DEEPSEEK_API_KEY'de ne yazarsa yazsin
# (hatta gercek bir anahtar girilmis olsa bile), bu script gecici bir
# kopya uzerinde anahtari zorla bos/placeholder yapar ve ONDAN derler.
# Boylece bu exe internete/DeepSeek'e HICBIR ZAMAN baglanmaz, sadece
# yerel kural tabanli teshis/hizlandirma araclariyla calisir.
#
# Cikti: dist\ONARIM_BASLAT_YEREL.exe

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Python bagimliliklari kuruluyor..."
python -m pip install --upgrade pip | Out-Null
python -m pip install -r requirements.txt

$gecici = "pc_terminal_yerel_gecici.py"
Write-Host "Yerel (DeepSeek'siz) gecici kopya hazirlaniyor: $gecici"

(Get-Content pc_terminal.py -Raw) `
    -replace 'DEEPSEEK_API_KEY = os\.environ\.get\("DEEPSEEK_API_KEY", ".*"\)', `
             'DEEPSEEK_API_KEY = "BURAYA_DEEPSEEK_API_ANAHTARINI_YAZ"  # derle_yerel.ps1 ile zorla devre disi birakildi' `
    | Set-Content $gecici -Encoding UTF8

Write-Host "Tek-exe derleniyor (PyInstaller)..."
python -m PyInstaller --onefile --console --name ONARIM_BASLAT_YEREL --clean $gecici

Remove-Item $gecici -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Tamamlandi: $PSScriptRoot\dist\ONARIM_BASLAT_YEREL.exe" -ForegroundColor Green
Write-Host "Bu surum internete/DeepSeek'e hic baglanmaz; sadece yerel kural"
Write-Host "tabanli teshis ve hizlandirma araclariyla calisir."
