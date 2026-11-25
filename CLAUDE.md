# Bink It — CLAUDE.md

## Proje özeti
Bink It, telefon kamerasıyla bir arabayı tarayıp markasını (ileride modelini) tanıyan ve tahmini değerini gösteren bir mobil uygulama. GTA tarzı oyunlardaki "araç tarama" deneyiminden ilham alıyor ama **hiçbir oyun markası, logosu, ismi veya görseli kullanılmaz**.

- Geliştirici: Deniz Acar (tek kişi, Claude Code ile çalışıyor)
- Hedef platform: **Android önce** (Google Play geliştirici hesabı mevcut). iOS sonra.
- Hedef pazar: **Küresel** (sadece Türkiye değil). Arayüz dili: İngilizce varsayılan + Türkçe.
- "Bink It" geçici isim.

## Temel kural: sıfır çalışma maliyeti
- Tüm yapay zeka **cihazda** çalışır (TensorFlow Lite). Sunucu yok, ücretli API yok, LLM/AI token kullanımı yok.
- Backend, analytics SDK'sı veya bulut servisi eklemeden önce mutlaka sor.
- Model eğitimi ücretsiz Google Colab'da yapılır.

## Gizlilik kuralları (DEĞİŞTİRİLEMEZ)
1. **Plakalar asla okunmaz.** Projede OCR kütüphanesi bulunmaz. Plaka metni çıkaran hiçbir kod yazılmaz.
2. Her kamera karesi önce **plaka tespit modelinden** geçer. Bu model sadece plakanın konumunu (bounding box) bulur. O alan sınıflandırmadan ÖNCE hafızada bulanıklaştırılır veya siyaha boyanır.
3. Karenin büyük kısmını plaka kaplıyorsa (varsayılan eşik: kare alanının %15'inden fazlası, ayarlanabilir sabit) tarama **reddedilir** ve kullanıcıya "Aracın tamamını çek" mesajı gösterilir.
4. Ham kamera görüntüsü **diske yazılmaz, hiçbir yere gönderilmez**. Paylaşım kartları sadece plakası bulanıklaştırılmış görüntüden üretilir.
5. Plakadan araç sorgulama, sahip bilgisi veya konum kaydı gibi bir özellik **eklenmez**.
6. Play Store Data Safety beyanı: "Veri toplanmıyor / paylaşılmıyor." Bu beyanı bozacak bir değişiklik yapma.

## Lisans ve fikri mülkiyet kuralları
- **AGPL/GPL lisanslı model veya kütüphane kullanılmaz.** Ultralytics YOLOv5/v8/v11 ve türevleri AGPL'dir, kullanılmaz. Sadece Apache-2.0, MIT, BSD gibi izin verici lisanslar (örnek: YOLOX, MobileNet, EfficientNet-Lite).
- Yeni bir bağımlılık veya önceden eğitilmiş model eklerken lisansını `docs/LICENSES.md` dosyasına yaz.
- Veri setleri: Stanford Cars ve CompCars sadece ticari olmayan kullanıma izin verir. **Yayınlanan modelin eğitiminde kullanılmaz** (yalnızca yerel deney için). Ticari kullanıma uygun veya kendi toplanan veri kullanılır.
- Sitelerden kullanım koşullarına aykırı scraping yapılmaz (sahibinden, arabam.com vb.).
- GTA, Rockstar, "Wink It" adı, oyun fontları ve oyun UI'ını birebir kopyalayan tasarımlar kullanılmaz. Estetik ilham serbest, kopya yasak.
- Araba marka logoları uygulama arayüzünde ikon olarak kullanılmaz. Marka adı metin olarak gösterilir.

## Teknoloji yığını
- **Uygulama:** Flutter (Dart), Android hedefli
  - `camera`: kamera akışı
  - `tflite_flutter`: cihazda çıkarım
  - `image`: kırpma, ölçekleme, bulanıklaştırma
- **ML:** Python, TensorFlow/Keras, Colab notebook'ları → `.tflite` çıktısı (int8 veya float16 quantization)
  - Plaka tespiti: PyTorch (torchvision SSDLite) yerel GPU'da eğitilir, ai-edge-torch ile `.tflite`'a çevrilir (bkz. `ml/DATASETS.md`)
- **Veri:** Fiyat aralıkları uygulama içindeki statik JSON'da tutulur (API yok)

## Klasör yapısı
```
bink_it/
├── CLAUDE.md
├── app/                      # Flutter uygulaması
│   ├── lib/
│   │   ├── main.dart
│   │   ├── features/
│   │   │   ├── scanner/      # kamera ekranı + tarama akışı
│   │   │   └── result/       # sonuç kartı (GTA tarzı araç kartı)
│   │   ├── ml/
│   │   │   ├── plate_detector.dart   # plaka konumu bulma (OCR YOK)
│   │   │   ├── plate_masker.dart     # bulanıklaştırma / maskeleme
│   │   │   └── car_classifier.dart   # marka/model sınıflandırma
│   │   ├── data/
│   │   │   └── price_repository.dart # statik JSON okuyucu
│   │   └── l10n/             # en, tr
│   └── assets/
│       ├── models/           # plate_detector.tflite, car_classifier.tflite, labels.txt
│       └── data/prices.json
├── ml/                       # model eğitimi
│   ├── notebooks/            # Colab notebook'ları
│   ├── scripts/              # veri hazırlama, dönüştürme, değerlendirme
│   └── README.md
└── docs/
    ├── LICENSES.md
    └── PRIVACY.md            # Play Store için gizlilik politikası taslağı
```

## Tarama akışı
```
Kamera karesi
  → plate_detector  (plaka kutularını bul)
  → plaka alanı > eşik ise: REDDET ("Aracın tamamını çek")
  → plate_masker    (kutuları bulanıklaştır, hafızada)
  → car_classifier  (marka + güven skoru)
  → güven < eşik ise: "Emin değilim, tekrar dene" (yanlış cevap vermektense)
  → price_repository → sonuç kartı
```
- Kareler sürekli değil, kullanıcı "tara" tuşuna basınca işlenir (pil ve performans için).
- Sınıflandırıcı en iyi 3 tahmini ve skorlarını döndürür. Düşük güvende uydurma sonuç gösterme.

## Yol haritası
1. **MVP:** Marka tanıma (~30-40 küresel yaygın marka), plaka maskeleme, sonuç kartı, statik fiyat aralığı. Android yayını.
2. Paylaşılabilir araç kartı görseli (plaka maskeli).
3. Popüler markalar için model seviyesinde tanıma (bölgelere göre dengeli veri ile).
4. iOS (Core ML dönüşümü).

## Çalışma tarzı
- Deniz Claude Code'u mümkün olduğunca kesintisiz (Auto mode) çalıştırmayı tercih ediyor. Rutin adımlar için onay isteme, ama bu dosyadaki gizlilik ve lisans kurallarına dokunan her değişiklikte dur ve sor.
- İletişim Türkçe. Kod, değişken adları ve commit mesajları İngilizce.
- Proje GitHub'da yönetiliyor. Anlamlı ve küçük commit'ler at.
- Bir modelin doğruluğunu iddia etmeden önce ayrı bir test setinde ölç ve sonucu `ml/README.md` dosyasına yaz.
