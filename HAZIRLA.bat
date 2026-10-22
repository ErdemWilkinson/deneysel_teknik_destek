@echo off
setlocal

echo =========================================================
echo   ERDEMUSB - Tek tikla hazirlama
echo   (Bu pencere Python paketlerini kurar, iki programi
echo    derler ve exe'leri dogru klasorlere kopyalar.)
echo =========================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo HATA: Python bulunamadi.
    echo.
    echo Once Python kur:  https://www.python.org/downloads/
    echo Kurulum sirasinda "Add python.exe to PATH" kutusunu ISARETLE.
    echo Kurduktan sonra bu dosyayi tekrar calistir.
    echo.
    pause
    exit /b 1
)

echo [1/4] Onarim terminali (ONARIM_BASLAT.exe) derleniyor...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0pc-terminal\derle.ps1"
if errorlevel 1 (
    echo.
    echo HATA: ONARIM_BASLAT.exe derlenemedi. Yukaridaki hata mesajina bak.
    pause
    exit /b 1
)

echo.
echo [2/4] Dinleyici (DINLEYICI.exe) derleniyor...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0pc-listener\derle.ps1"
if errorlevel 1 (
    echo.
    echo HATA: DINLEYICI.exe derlenemedi. Yukaridaki hata mesajina bak.
    pause
    exit /b 1
)

echo.
echo [3/4] ONARIM_BASLAT.exe, usb-paket klasorune kopyalaniyor...
copy /Y "%~dp0pc-terminal\dist\ONARIM_BASLAT.exe" "%~dp0usb-paket\ONARIM_BASLAT.exe" >nul
if errorlevel 1 (
    echo HATA: kopyalanamadi, elle "pc-terminal\dist\ONARIM_BASLAT.exe" dosyasini
    echo "usb-paket\" klasorune tasiyabilirsin.
) else (
    echo Tamam: usb-paket\ONARIM_BASLAT.exe
)

echo.
echo [4/4] DINLEYICI.exe, dagitim\ klasorune kopyalaniyor...
if not exist "%~dp0dagitim" mkdir "%~dp0dagitim"
copy /Y "%~dp0pc-listener\dist\DINLEYICI.exe" "%~dp0dagitim\DINLEYICI.exe" >nul
copy /Y "%~dp0pc-terminal\dist\ONARIM_BASLAT.exe" "%~dp0dagitim\ONARIM_BASLAT.exe" >nul
if errorlevel 1 (
    echo HATA: kopyalanamadi, elle "pc-listener\dist\DINLEYICI.exe" dosyasini kopyalayabilirsin.
) else (
    echo Tamam: dagitim\DINLEYICI.exe ve dagitim\ONARIM_BASLAT.exe
)

echo.
echo =========================================================
echo  BITTI.
echo  - USB'ye kopyalanacak: usb-paket\  klasorunun tamami
echo    (ONARIM_BASLAT.exe iceride, cift tiklamaya hazir)
echo  - Dinleyici kurulacak PC'ye: dagitim\DINLEYICI.exe ve
echo    dagitim\ONARIM_BASLAT.exe'yi bir klasore kopyala (orn.
echo    C:\TeknikDestek\), sonra DINLEYICI.exe kisayolunu
echo    Windows Baslangic klasorune ekle (Win+R, shell:startup).
echo =========================================================
echo.
pause
