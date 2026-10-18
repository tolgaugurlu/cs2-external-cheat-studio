# Sürüm notları

## 1.1.2 — 18 Ekim 2026

### Adlandırma ve yayın

- Uygulamanın görünen adı **Studio Panel** olarak değiştirildi. Windows paketi `StudioPanel-1.1.2.exe` ve `StudioPanel-1.1.2-Windows-x64.zip` adlarıyla oluşturulur.
- Panel başlığı, EXE adı ve Windows dosya özelliklerindeki ürün/dosya sürümü aynı `app_version.py` kaynağından alınır. Sonraki derlemelerde de bu adlandırma kullanılır.
- Mevcut ayar, profil ve yerel harita bağlantısı dosyalarının adları korundu. Yeni EXE aynı klasörde kullanıldığında mevcut kayıtlar okunur; yeniden ayar yapmak gerekmez.
- Türkçe sürüm notları ile kurulum ve güncelleme belgeleri yenilendi. ZIP'e sürüm notları ve güncelleme rehberi eklendi; kişisel ayarlar, bağlantı anahtarları ve günlükler pakete alınmaz.

Uygulama bağımsız bir masaüstü aracıdır; bir Microsoft ürünü veya Windows hizmeti değildir. Ad değişikliği gizleme ya da VAC güvenliği sağlamaz. Offset güncelleyicisi yalnızca veri indirir; EXE'yi yeniden derlemez veya değiştirmez.

Bu yayın, aşağıdaki 1.1.0 ve 1.1.1 değişikliklerini de içerir.

## 1.1.1 — 18 Ekim 2026

### Harita bağlantısı

- EXE taşındıktan sonra yerel `gsi_config.json` eksikse, oyunda daha önce kurulmuş olan bu uygulamaya ait bağlantıdan geri alınır. Oyun yapılandırması yeniden yazılmaz ve yeni anahtar üretilmez. Harita verisini bekleyen Nişan/Flick akışının bu nedenle durması giderilir.
- Yerel harita portu tek uygulamaya ayrılır. İkinci uygulamanın aynı porttaki güncellemeleri paylaşması engellenir ve bağlantı durumundaki değişiklikler günlüğe kaydedilir.

### Oyun konturu

- Oyunun yönettiği kontur başlangıç zamanına yazılması kaldırıldı.
- Kontur alanlarının sıfırlandığı görüldüğünde onarım sıklığı geçici olarak saniyede en fazla 240 döngüye çıkar; durum kararlı hâle geldiğinde 60 döngüye döner. Döngüde geçen çalışma süresi bekleme hesabından düşülür; sürekli işlemci kullanan boş döngü oluşturulmaz.
- Yalnızca mevcut oyun konturu kullanılır; ayrı bir ESP penceresi eklenmez.

**Bilinen sınırlama:** Canlı, yalnızca okuma yapan kontrolde 1.1.1 ile de kontur sıfırlanmaları görüldü. Oyunun aynı alanları güncellemesiyle oluşan çakışma tamamen giderilmiş değildir; yanıp sönmenin bittiği veya FPS'nin arttığı iddia edilmez.

## 1.1.0 — 18 Ekim 2026

- Bağımsız ESP penceresi, GDI siluetleri, kutular, iskelet, sağlık etiketleri, bomba bandı ve düzenli ekran çizimi kaldırıldı. Oyun konturu (Glow) ve renk paletleri korundu.
- Eski ayar dosyaları ve isimli profiller okunmaya devam eder. Kaldırılan ESP'ye ait alanlar yok sayılır; diğer ayarlar ve silah profilleri korunur.
- AWP gövde hedeflemesi seçilen tepki biçimine uyar; akıcı takibi kendiliğinden atlamaz. Keskin kilit ve Flick, anlık dönüş davranışını korur.
- Tepki biçimleri için açıklamalar ve kontur döngüsünün çalışma süreleri eklendi. Renk önizlemesi yalnızca panel içinde, gerektiğinde çizilir.
- EXE dosyaları sürüm numarasıyla adlandırılmaya başlandı. Çevrimdışı demo ekran görüntüleri ve belgeler güncellendi.

Otomatik testler sentetik bellek ve sahte girdi kullanır; canlı oyunda isabet, FPS kazancı veya anti-cheat uyumluluğu ölçmez.
