# Windows EXE oluşturma

Python 3.11 x64 ve .NET 10 x64 SDK kurulu olmalı. Temiz kaynak klasöründe:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/build_release.py
```

Komut; harita yardımcısını kilitli NuGet bağımlılıklarıyla derler, Python testlerini çalıştırır, PyInstaller ile EXE oluşturur ve temiz ZIP hazırlar:

```text
dist/CS2Studio.exe
dist/map-tools/
release/CS2Studio-Windows-x64.zip
release/SHA256SUMS.txt
```

ZIP'e yalnızca belirlenen yayın dosyaları alınır. Kişisel ayarlar, profiller, bağlantı anahtarları, günlükler, offsetler ve harita önbellekleri dahil edilmez. Her kullanıcı kendi kurulumunda `CS2Studio.exe --setup` çalıştırır.

Oyuna bağlanmadan EXE'yi kontrol et:

```powershell
.\dist\CS2Studio.exe --demo
Get-FileHash .\release\CS2Studio-Windows-x64.zip -Algorithm SHA256
```

Hash değeri `SHA256SUMS.txt` ile eşleşmeli. Bu kontrol dosya bütünlüğünü gösterir; VAC güvenliğini göstermez.

Ek kontroller:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe tools/check_studio_layout.py
```

Bağımlılıkların doğrudan sürümleri sabittir; Python yama sürümü ve derleme ortamı farklıysa EXE'nin hash değeri değişebilir. Birebir aynı baytları üretme garantisi yoktur.
