# Kullanım

**F2:** başlat/durdur · **F3:** paneli göster/gizle · **F4:** otomatik tetik. Demo modunda global tuşlar ve oyun girdisi yoktur. Normal açılış duraklatılmıştır.

Görünümde yalnızca **Oyun konturu / Glow** ve renk paleti bulunur. Ayrı ESP çizimi kaldırılmıştır. Tepki biçimleri ve EXE güncelleme davranışı için [güncelleme notlarına](UPDATES.tr.md) bak.

## Silaha özel profil

**Profiller → Silaha özel** bölümünden silah veya grup seç. Formu düzenleyip **Profili kaydet** düğmesine bas. Kaydetmeden forma yazılanlar uygulanmaz. Öncelik **silah → grup → genel** şeklindedir. Kontroller sekmesi genel ayarları düzenler; kayıtlı silah profilini değiştirmez.

**Genelden kopyala** genel değerleri forma alır; ayrıca kaydetmek gerekir. **Özel ayarı kaldır** o kuralı siler. **Eldeki silah** gözlenen silahı seçer. Tuşlar, takım filtresi ve başlat/durdur durumu genel kalır.

## Ayar profilleri

**Ayar profilleri** genel ayarlar ve silah kurallarını birlikte saklar. İsim yazıp **Mevcut ayarları kaydet** düğmesine bas. Aynı isimle kaydetmek o kaydı günceller. **Yükle** uygular, **Yüklemeyi geri al** son yüklemeden önceki değerlere döner. Başlat/durdur durumu kayda dahil değildir.

İlk normal açılışta **Başlangıç ayarlarım** korumalı kaydı oluşur; arayüzden silinemez veya üzerine yazılamaz.

## Durum ve performans

Alt satır bekleme nedenini ve etkin silah profilini gösterir. Performans ekranındaki CPU, RAM ve özel bellek bu uygulamaya aittir. P95, yakın zamandaki döngü örneklerinin %95'inin altında kaldığı süredir. Saniyede bir yenilenir; CS2 FPS'si veya ağ gecikmesi ölçülmez.

## Flick

İlk işlem silah eldeyken başlar. Sonraki basışlarda bıçaktayken önceki silah tuşu gönderilir, aynı silahın hazır olduğu doğrulanır, işlem yapılır ve bıçağa dönülür. Tuşu basılı tutmak tekrarlamaz. Ölümde hatırlanan silah sıfırlanır. Gerçek silah çekilme ve atış süreleri atlanmaz.

Şarjör azalması atışı doğrular; isabeti veya öldürmeyi doğrulamaz. R8 ve burst modu bu akışta desteklenmez. Odak kaybı veya geçersiz durum işlemi iptal eder.

## Dosyalar

`ayar.json`: genel ayarlar; `profiller.json`: profiller; `gsi_config.json`: yerel bağlantı anahtarı; `output/`: offsetler; `map-cache/`: yerel harita önbelleği; `CS2Tool.log`: günlük. Özellikle bağlantı dosyası ve günlükleri incelemeden herkese açık paylaşma.
