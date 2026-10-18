# Güncelleme ve sürüm adları

Offset güncelleyicisi, kurulu oyun sürümüyle eşleşen veriyi indirir. Başarıyla doğrulanan veriyi yerleştirir ve önceki veriyi yedekler. Python kodunu veya EXE'yi değiştirmez; yeni EXE oluşturmaz. Uyumlu offset verisi bulunamıyorsa başlatma engellenir.

Kod değişiklikleri için yeniden derlemek gerekir. `app_version.py` uygulama adını ve sürüm numarasını tutar; derleyici `StudioPanel-1.1.2.exe` gibi bir ad üretir. Aynı sürüm Windows dosya özelliklerinde ve panel başlığında da görünür. Rastgele ad değiştirme veya yeniden paketleme bir güvenlik özelliği değildir. Bu proje otomatik kod/EXE güncellemesi sunmaz.

1.1.2'den itibaren uygulamanın adı **Studio Panel**. Gelecek derlemeler de `StudioPanel-<sürüm>.exe` biçimini kullanır. Bir Windows hizmetini taklit etmez; Microsoft ile ilişkisi yoktur. Mevcut kurulumların çalışmaya devam etmesi için ayar, profil ve GSI dosyaları ile tek örnek denetiminin iç adları değiştirilmemiştir.

Yeni EXE'yi kullanmadan önce açık eski uygulamayı kapat. `ayar.json`, `profiller.json`, `gsi_config.json` ve `map-tools` aynı klasörde kaldığında ayar ve kurulum korunur. Farklı klasöre taşırken önce bu dosyaları yedekle. Eski EXE aynı klasörde dursa da yeni sürüm adını seçerek aç.

1.1.0'da bağımsız ESP kaldırıldı. Eski profillerdeki siluet/iskelet/kutu/etiket alanları yok sayılır; Oyun konturu ve renk paleti korunur. Eski bir profili yüklemek ayrı ESP'yi geri getirmez.

**Akıcı takip** süre ve hız sınırını; **Ayarlanabilir** yumuşatma ve hız ayarını kullanır. **Keskin kilit** anlık dönüş yapar. AWP seçeneği yalnızca gövde noktasını seçer, tepki biçimini değiştirmez. Flick ayrı bir anlık dönüş akışıdır. Silaha özel profil varsa genel tepki biçiminin üzerine geçebilir.

Bir bekleme süresinin nedenini bu uygulamanın günlüklerinden saptamak mümkün değildir. İsim değiştirme, yumuşatma veya testlerin geçmesi VAC güvenliği sağlamaz. [Steam'in bekleme süreleri açıklaması](https://help.steampowered.com/en/faqs/view/7580-7BDB-1C9A-AC67).

1.1.1: EXE klasörü taşındığında eksik GSI bağlantı dosyası, oyunda zaten kurulu olan bu uygulamaya ait yerel bağlantıdan otomatik geri alınır. Aynı portu ikinci uygulamanın paylaşmasına izin verilmez. Kontur onarımı yalnızca sıfırlanma gözlendiğinde geçici olarak hızlanır; oyunun başlangıç zamanına yazılmaz. Bu değişiklik sıfır yanıp sönme garantisi değildir.
