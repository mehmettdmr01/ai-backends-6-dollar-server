# V7 sonuçları, $6 sunucu (DigitalOcean Basic 1 vCPU / 1 GB, ams3), 5-6 Kas 2026

Skor: 5 dakika boyunca p95 < 1 s ve hata < %1 ile geçen en yüksek kullanıcı sayısı (1 kullanıcı = 5-15 sn'de bir tık, 10 kullanıcı ≈ 1 istek/s). Her yarışmacı tek koşu.

| Yarışmacı | Skor (kullanıcı) | Kırılma (artan yükte) | Tutuşta p95 | Tutuşta istek/s | Gizli test |
|---|---|---|---|---|---|
| Codex (gpt-5.6-terra), 7,5 dk | **≥ 22.500** (üretici tavanı) | 25.000'de kırılmadı | 22 ms | 2.011 | geçti |
| Gemini (3.8 Flash), 16 dk | **19.500** | 21.666 | 14 ms | 1.742 | geçti |
| Claude (Sonnet 5.5), 1,5 dk | **18.000** | 20.000 | 259 ms | 1.603 | geçti |
| Express taban (eğitim kodu) | **12.400** | 13.750 | 176 ms | 1.104 | geçti |

Notlar:
- Codex 25.000 kullanıcıda bile kırılmadı (p95 22 ms, CPU %37 boşta). 8 GB'lık tek yük üreticisi ~25.000 kullanıcıdan fazlasını üretemiyor: gerçek sınırı bilinmiyor, ikinci üreticiyle ölçülebilir.
- **Gürültü büyük:** Aynı Express kodu üç denemede ~13.750, ~17.700 ve 20.000'de kırılmadı. Paylaşımlı CPU, komşuların aldığı pay (steal) koşu ortalaması %5-21. Claude (18.000) ile Gemini (19.500) arasındaki fark bu gürültünün içinde; sıralamaları tek koşuyla söylenemez. Codex'in önde, Express'in geride olduğu net.
- Express artan yükte "SYN flooding" ile bağlantı reddetti (Node varsayılan keep-alive 5 sn → her tık yeni bağlantı). Diğer üçünde çekirdek "too many orphaned sockets" yazdı.
- Kalibrasyon: 1 ms/istek kontrol sunucusu 6.800 kullanıcı (teori ~10.000, HTTP yükü + steal).
- Ham veri: her klasörde `kosular.json`, saniyelik sunucu kaydı `*.csv`, gözcü kaydı `*.prob.csv`, `test.txt`, `gizli.txt`.

## 2. tur, 6 Kas 2026: aynı dört kod, iki yük üreticisi (tavan 50.000)

Aynı $6 kutu tipi, yeni kutu (fsync 3.145/s, 1. tur 2.850/s). Önce 25.000'lik rampa, kırılmazsa 50.000'lik. Ham veri `sonuc/tur2/do-6/`.

| Yarışmacı | 1. tur skor | 2. tur skor | 2. tur kırılma | 2. tur tutuşta p95 | 2. tur istek/s | Tutuşta steal (1. / 2. tur) |
|---|---|---|---|---|---|---|
| Codex | ≥ 22.500 (tavan) | **26.200** | 29.166 (hata) | 132 ms | 2.333 | %6,2 / %3,9 |
| Claude | 18.000 | **22.500** | 25.000 (hata) | 279 ms | 2.005 | %21,0 / %6,5 |
| Gemini | 19.500 | **21.000** | 23.333 (bellek doldu, OOM) | 81 ms | 1.874 | %5,5 / %5,6 |
| Express taban | 12.400 | **16.500** | 18.333 (p95) | 554 ms | 1.435 | %4,7 / %5,1 |

Notlar:
- **Codex'in gerçek sınırı:** yaklaşık 26.000-29.000 kullanıcı. İki turda da birinci.
- **Claude ile Gemini berabere sayılır:** 1. turda Gemini 1.500 önde, 2. turda Claude 1.500 önde. Claude'un 1. tur tutuşunda komşuların CPU payı (steal) %21'di, düşük skorun büyük olasılıkla sebebi bu.
- **Kırılma biçimleri farklı:** Gemini belleği bitirip öldürülüyor (1 GB sınırı), Codex ve Claude hata vermeye başlıyor, Express gecikmesi 1 sn'yi aşıyor.
- **Express iki turda da son.** Aynı kod iki turda 4.100 kullanıcı farklı: gürültü bu büyüklükte.
- **Geçersiz koşu:** Gemini'nin ilk 2. tur koşusu (12.700) Ubuntu'nun otomatik güncellemesi rampanın ortasında çalıştığı için atıldı (3,4 dk CPU, 695 MB bellek). `sonuc/tur2/eski/`. Kurulum betiği artık bu zamanlayıcıları kapatıyor. 1. tur kutusunda da çalışmış olabilir, kutu silindiği için doğrulanamaz.
- Dördü de API testini (28/28) ve gizli testi iki turda da geçti.
