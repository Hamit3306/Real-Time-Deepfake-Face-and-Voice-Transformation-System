# 🎙️ Projeye Yeni Ses Profili Ekleme Rehberi

Bu doküman, DeepFake projesine **Zeki Müren** sesinin nasıl eklendiğini adım adım anlatır.  
Aynı yöntemi kullanarak istediğiniz ünlünün/kişinin sesini projeye ekleyebilirsiniz.

---

## 📋 Genel Bakış

Projede ses klonlama sistemi şu şekilde çalışır:

```
tts_service/references/ klasöründeki .wav dosyaları
        ↓
/api/voices endpoint'i otomatik olarak listeler
        ↓
Frontend'de dropdown menüsünde görünür
        ↓
Kullanıcı seçtiğinde XTTSv2 modeli o sesi klonlar
```

**Yani tek yapmanız gereken:** düzgün formatta bir `.wav` dosyasını `tts_service/references/` klasörüne koymaktır!

---

## 🔧 Adım Adım: Zeki Müren Sesini Nasıl Ekledik?

### Adım 1: Ses Dosyasını Bul ve İndir

YouTube veya benzeri bir kaynaktan Zeki Müren'in net bir şarkı/konuşma kaydını bulup indirdik.

> **İpuçları:**
> - Arka plan müziği mümkün olduğunca az olsun
> - Net ve temiz bir ses kaydı olsun
> - En az 5 saniye, en fazla 15 saniye yeterli
> - Mono ses daha iyi sonuç verir

### Adım 2: Dosyayı Projeye Koy

İndirilen dosyayı şu klasöre koyduk:

```
tts_service/references/zeki müren.wav
```

> ⚠️ **Dikkat:** Dosya adında Türkçe karakter ve boşluk olmaması gerekiyor! 
> Bu yüzden dosyayı `zeki_muren.wav` olarak yeniden adlandırdık.

### Adım 3: Ses Dosyasını İlk 10 Saniyeye Kes

XTTSv2 modeli için referans ses dosyası **5-15 saniye** aralığında olmalıdır.  
Daha uzun dosyalar modeli yavaşlatır ve kaliteyi düşürür.

Kullandığımız Python scripti:

```python
import librosa
import soundfile as sf

# Ses dosyasını yükle
audio, sr = librosa.load("references/zeki_muren.wav", sr=None)

# İlk 10 saniyeyi kes
target_samples = int(sr * 10)  # 10 saniye
audio_trimmed = audio[:target_samples]

# Gerçek WAV formatında kaydet
sf.write("references/zeki_muren.wav", audio_trimmed, sr)
```

> **Not:** Bu scripti `tts_service/venv` sanal ortamında çalıştırdık çünkü `librosa` 
> ve `soundfile` kütüphaneleri orada yüklü.

```bash
# Çalıştırma komutu:
cd tts_service
.\venv\Scripts\python.exe trim_script.py
```

### Adım 4: Dosya Adı Kuralları

Dosya adı = Persona adı. Yani:

| Dosya Adı | API'de Persona Adı | Frontend'de Görünüm |
|-----------|--------------------|--------------------|
| `zeki_muren.wav` | `zeki_muren` | `zeki_muren` |
| `ata.wav` | `ata` | `ata` |
| `rte.wav` | `rte` | `rte` |
| `kayit_1.wav` | `kayit_1` | `kayit_1` |

**Kurallar:**
- ✅ Küçük harf kullanın
- ✅ Boşluk yerine alt çizgi `_` kullanın
- ✅ Türkçe karakter kullanmayın (`ü` → `u`, `ş` → `s`, vb.)
- ✅ `.wav` uzantısı olmalı
- ❌ Büyük harf, boşluk, özel karakter kullanmayın

### Adım 5: Otomatik Tanınma

Dosyayı `tts_service/references/` klasörüne koyduktan sonra **hiçbir kod değişikliği gerekmez!**

Sistem şu şekilde otomatik çalışır:

1. **`/api/voices` endpoint'i** (`gpu_worker/api.py` satır 317-331):
   ```python
   @app.get("/api/voices")
   async def get_voices():
       ref_dir = ".../tts_service/references"
       voices = []
       for file in os.listdir(ref_dir):
           if file.endswith(".wav"):
               voices.append(file.replace(".wav", ""))
       return {"voices": voices}
   ```
   → Klasördeki tüm `.wav` dosyalarını otomatik tarar ve listeler.

2. **`VoiceCloner`** (`modules/voice_cloning.py` satır 25):
   ```python
   reference_path = os.path.join(self.reference_dir, f"{persona}.wav")
   ```
   → Seçilen persona adına göre ilgili `.wav` dosyasını bulur.

3. **`TTS Service`** (`tts_service/tts_service.py` satır 64-68):
   ```python
   tts_model.tts_to_file(
       text=req.text,
       speaker_wav=req.reference_audio_path,
       language=req.language,
       file_path=req.output_path
   )
   ```
   → XTTSv2 modeli referans sesi kullanarak yeni ses üretir.

---

## 📁 Mevcut Ses Dosyaları

```
tts_service/references/
├── fatih.wav        # Fatih  
├── hamit.wav        # Hamit
├── kayit_1.wav      # Kullanıcı kaydı 1
├── kayit_2.wav      # Kullanıcı kaydı 2
├── mazlum.wav       # Mazlum
├── mujdat.wav       # Müjdat
├── okan.wav         # Okan
├── prime.wav        # Prime
├── seda.wav         # Seda
└── zeki_muren.wav   # Zeki Müren (YENİ - 10 saniye)
```

---

## 🚀 Hızlı Yeni Ses Ekleme Özeti

Yeni bir ünlünün sesini eklemek için:

```bash
# 1. Ses dosyasını indir ve references klasörüne koy
#    Örnek: barış manço → baris_manco.wav

# 2. 10 saniyeye kes (opsiyonel - eğer dosya uzunsa)
cd tts_service
.\venv\Scripts\python.exe -c "
import librosa, soundfile as sf
audio, sr = librosa.load('references/baris_manco.wav', sr=None)
sf.write('references/baris_manco.wav', audio[:sr*10], sr)
"

# 3. GPU Worker'ı yeniden başlat (sunucu çalışıyorsa)
# Yeniden başlatma gerekmez - /api/voices endpoint'i 
# her çağrıda klasörü tazeler!
```

**Hepsi bu kadar!** 🎉

---

## ⚠️ Sık Yapılan Hatalar

| Hata | Çözüm |
|------|-------|
| Dosya bulunamadı hatası | Dosya adında boşluk/Türkçe karakter var mı kontrol edin |
| Ses kalitesi düşük | Daha temiz bir kaynak ses dosyası kullanın |
| Model çok yavaş | Referans sesi 10 saniyenin altına kesin |
| Format hatası | Dosyanın gerçek WAV formatında olduğundan emin olun (MP3'ü .wav yaparak kaydetmeyin) |
