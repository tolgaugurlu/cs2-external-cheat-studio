# CS2 Studio — Harici CS2 Hile Araçları

**Counter-Strike 2 · Python · Windows x64 · ESP · Aim / RCS · Silah profilleri**

[English](README.md) · [Kurulum](docs/INSTALL.tr.md) · [EXE oluşturma](docs/BUILD.tr.md) · [Kullanım](docs/USAGE.tr.md)

CS2 Studio; ESP, nişan takibi, geri tepme düzeltmesi, flick dizisi, silaha özel profiller ve performans göstergelerini tek panelde toplar. Oyun belleğini okur/yazar ve girdi üretir. Arayüz Türkçedir.

> **Hesap riski:** VAC güvenliği veya tespit edilmeme garantisi yoktur. Kullanım, bekleme süresine veya yasaklamaya neden olabilir. EXE adını değiştirmek güvenlik sağlamaz. Testlerin geçmesi anti-cheat uyumluluğu anlamına gelmez; sıfır kaçırma veya tek mermiyle öldürme garantisi verilmez.

![Görünüm sekmesi — çevrimdışı demo](docs/images/01-appearance.png)

Ekran görüntüleri gerçek arayüzün **oyuna bağlanmayan demo modundan** alınmıştır. Karakter çizimleri ve profiller örnektir. Oyun içi başarı veya FPS ölçümü göstermezler.

## Neler var?

- **Görünüm:** oyun Glow'u, bağımsız yaklaşık siluet, isteğe bağlı iskelet, kutu, sağlık ve etiketler.
- **Kontroller:** nişan tepkisi, FOV, tuş, hedef noktası ve dikey/yatay geri tepme ayarları.
- **Flick shot:** seçilebilir tuş, tek işlem, önceki bakışa dönüş, bıçak ve önceki silah geçişi.
- **Profiller:** silah → grup → genel önceliği; isimli ayar kaydı, yükleme ve geri alma.
- **Durum / Performans:** bekleme nedeni, etkin profil, uygulama CPU/RAM kullanımı ve döngü süreleri.
- **Kompakt panel:** 980 × 650 içerik alanında beş sekme; %100, %125 ve %150 ölçeklerde kontrol edildi.

## Oyunsuz önizleme

Windows x64 ve Python 3.11 x64 gerekir. PowerShell'de:

```powershell
git clone https://github.com/tolgaugurlu/cs2-external-cheat-studio.git
cd cs2-external-cheat-studio
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe memory_bot.py --demo
```

Demo oyuna bağlanmaz, offset indirmez, ayar dosyası yazmaz ve oyun girdisi göndermez. Başlat düğmesi kapalıdır. Profilleri bellekte deneyebilirsin.

Tam kurulum için [kurulum rehberini](docs/INSTALL.tr.md), EXE ve taşınabilir ZIP oluşturmak için [derleme rehberini](docs/BUILD.tr.md) takip et.

## Sekmeler

| Kontroller | Silaha özel profiller |
| --- | --- |
| ![Kontroller](docs/images/02-controls.png) | ![Silah profilleri](docs/images/04-weapon-profiles.png) |

| Ayar profilleri | Durum / Performans |
| --- | --- |
| ![Ayar profilleri](docs/images/05-settings-profiles.png) | ![Performans](docs/images/06-performance.png) |

[Tüm ekran görüntüleri](docs/SCREENSHOTS.md)

## Kurulum ve veri düzeni

Kişisel `ayar.json`, `profiller.json`, `gsi_config.json`, günlükler, oyun dosyaları ve offset önbellekleri depoya dahil değildir. Kurulum her makine için ayrı yerel GSI anahtarı üretir. İlk normal açılış varsayılan ayarları kullanır; silaha özel kayıt oluşturmadıkça genel değerler geçerlidir.

Güncellemeden önce mevcut `ayar.json`, `profiller.json` ve `gsi_config.json` dosyalarını yedekle. EXE yanında `map-tools` klasörü bulunmalıdır. Harita önbelleği ilk kullanımda yerel oyun dosyalarından hazırlanır.

## Sınırlar

Duvar testi sabit harita çarpışmasını kapsar; duman, hareketli kapılar ve sonradan kırılan nesnelerin tüm durumlarını kapsamaz. Bağımsız siluet gerçek modelin birebir dış çizgisi değildir. Oyun konturu seçeneğinde oyunun aynı alanlara yazması yanıp sönmeye yol açabilir. Yeni oyun sürümüyle eşleşen offset bulunamazsa etkinleştirme engellenir.

Testler sentetik bellek ve sahte girdiler kullanır; canlı oyunda isabet veya FPS kazancı doğrulamaz.

## Lisans ve kaynaklar

Özgün telif bildirimi korunarak [MIT lisansı](LICENSE) ile paylaşılır. Offset kaynakları [a2x](https://github.com/a2x/cs2-dumper) ve [sezzyaep](https://github.com/sezzyaep/CS2-OFFSETS); harita dönüştürme [ValveResourceFormat](https://github.com/ValveResourceFormat/ValveResourceFormat) kullanır. [Bağımlılık bildirimleri](THIRD_PARTY_NOTICES.md).

Valve veya Counter-Strike tarafından desteklenen/resmî bir proje değildir.
