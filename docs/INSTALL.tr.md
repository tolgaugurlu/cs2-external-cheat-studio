# Kurulum

## Gereksinimler

Windows 10/11 x64, Steam CS2 kurulumu ve kaynak kullanımında Python 3.11 **x64** gerekir. Harita dönüştürücüsü [.NET 10 x64](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) çalışma ortamını kullanır; derleme için SDK gerekir. İlk offset indirmesinde GitHub bağlantısı gerekir.

## Kaynaktan çalıştırma

```powershell
git clone https://github.com/tolgaugurlu/cs2-external-cheat-studio.git
cd cs2-external-cheat-studio
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe memory_bot.py --demo
```

Demo oyuna bağlanmadan arayüzü gösterir. Tam kurulum için .NET 10 x64 SDK kurulduktan sonra:

```powershell
.\.venv\Scripts\python.exe tools/build_release.py --helper-only
.\.venv\Scripts\python.exe setup_runtime.py
.\.venv\Scripts\python.exe offset_manager.py
.\.venv\Scripts\python.exe memory_bot.py
```

Kurulum, CS2'nin `game/csgo/cfg` klasörüne yalnızca harita bilgisi isteyen GSI dosyası yazar. Yerel anahtar `gsi_config.json` içinde tutulur. Önceden farklı bir dosya varsa `offset_backups` altında yedeklenir. Kurulumdan sonra CS2'yi yeniden başlat. Bağlantı yalnızca `127.0.0.1:34371` üzerindedir.

Steam otomatik bulunamazsa kendi kurulumuna göre:

```powershell
$env:CS2_STEAM_INF = 'D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\csgo\steam.inf'
```

Örnekteki sürücüyü kendi yolunla değiştir. Başkasının GSI anahtarını kopyalama.

## Oluşturduğun EXE ile

[Derleme rehberinden](BUILD.tr.md) ZIP'i oluştur, yazılabilir bir klasöre çıkar. EXE ile `map-tools` klasörünü birlikte tut. Çıkardığın klasörde:

```powershell
.\CS2Studio.exe --demo
.\CS2Studio.exe --setup
.\CS2Studio.exe
```

`--setup` sonucu bir iletişim kutusunda gösterir. Sonrasında oyunu yeniden başlat. Normal açılış oyun sürümünü kontrol eder ve eşleşen offsetleri indirir. Veri güncel değilse eski offsetleri zorlayarak kullanma.

Uygulama duraklatılmış açılır. **F2:** başlat/durdur, **F3:** paneli göster/gizle, **F4:** otomatik tetik. Ayrıntılar: [Kullanım](USAGE.tr.md). VAC güvenliği iddiası yoktur.

## Sık sorunlar

- **Modül bulunamadı:** yükleme ve çalıştırmada aynı `.venv\Scripts\python.exe` yolunu kullan.
- **Harita dönüştürücüsü yok:** yardımcıyı derle, .NET 10'un x64 sürümünü kontrol et.
- **Harita sinyali bekleniyor:** kurulumu tamamla, CS2'yi yeniden aç ve haritaya gir.
- **Port kullanımda:** aynı uygulamanın diğer kopyasını kapat.
- **Sürüm uyuşmazlığı:** offset sağlayıcılarının güncel sürümü yayımlamasını bekle.
- **Profil uygulanmıyor:** silah formunu kaydet; otomatik geçiş ve etkin profil göstergesini kontrol et.

Kurulum için Windows güvenlik araçlarını kapatma. Kaldırırken uygulamayı kapat; bu kuruluma ait `gamestate_integration_cs2tool.cfg` dosyasını kaldır veya önceki yedeği geri getir. Windows servisi ya da zamanlanmış görev oluşturulmaz.
