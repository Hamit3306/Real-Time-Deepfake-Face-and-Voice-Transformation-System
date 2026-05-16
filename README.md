# 🎭 DeepFake Live — Gerçek Zamanlı Yüz Değiştirme & Ses Klonlama Platformu

> **WebRTC + InsightFace + XTTSv2 + Gemini AI** tabanlı, GPU hızlandırmalı gerçek zamanlı deepfake video ve ses klonlama sistemi.

---

## 📋 İçindekiler

- [Genel Bakış](#-genel-bakış)
- [Mimari Diyagram](#-mimari-diyagram)
- [Servis Mimarisi](#-servis-mimarisi)
- [Dosya Yapısı](#-dosya-yapısı)
- [Teknoloji Yığını](#-teknoloji-yığını)
- [Kurulum & Başlatma](#-kurulum--başlatma)
- [API Endpoint'leri](#-api-endpointleri)
- [Ortam Değişkenleri](#-ortam-değişkenleri)
- [Performans Optimizasyonları](#-performans-optimizasyonları)
- [Değerlendirme Metrikleri](#-değerlendirme-metrikleri)

---

## 🔭 Genel Bakış

Bu proje, **4 bağımsız mikro servis**ten oluşan dağıtık bir deepfake platformudur:

| # | Servis | Port | Konum | Açıklama |
|---|--------|------|-------|----------|
| 1 | **GPU Worker** | `8001` | Yerel (RTX 3050 Ti) | WebRTC video işleme + yüz değiştirme + ses klonlama API |
| 2 | **Signaling Server** | `8000` | AWS t2.micro / Yerel | WebSocket relay — SDP/ICE sinyalizasyonu |
| 3 | **React Frontend** | `5173` | AWS / Yerel | Vite + React kullanıcı arayüzü |
| 4 | **TTS Microservice** | `8002` | Yerel | XTTSv2 ses klonlama servisi (izole Python 3.10) |

**Ek olarak** `web/` klasöründe eski mimari için Socket.IO tabanlı legacy bir HTML arayüzü ve `main.py` kökünde Ngrok'suz doğrudan WebSocket bağlantılı alternatif bir GPU worker bulunur.

---

## 🏗 Mimari Diyagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      TARAYICI (Kullanıcı)                       │
│   React 19 + Vite 8  (aws_server/frontend/)                    │
│                                                                 │
│   Hooks:                                                        │
│     useWebRTC.js ─── WebSocket sinyalizasyon + RTCPeerConnection│
│     useMediaConstraints.js ─── Kamera/mikrofon yönetimi         │
│     useAsyncModules.js ─── Ekran paylaşım & kayıt modülleri    │
│                                                                 │
│   Modules:                                                      │
│     VoiceCloneModule.js ── Ses kayıt & yükleme                  │
│     ScreenShareModule.js ── Ekran paylaşımı                     │
│     MeetingRecordModule.js ── Toplantı kaydı                    │
└────────────┬──────────────────────────────────┬─────────────────┘
             │ WebSocket (SDP/ICE)              │ P2P WebRTC Video
             ▼                                  │
┌────────────────────────────────────┐          │
│  Signaling Server (port 8000)      │          │
│  aws_server/signaling/main.py      │          │
│                                    │          │
│  /ws/signal/{client_id}  ← React   │          │
│         │                          │          │
│         │ HTTP POST (offer/ice)    │          │
│         ▼                          │          │
│  /ws/worker  ← GPU Worker (opsiy.) │          │
│  (Ngrok-free doğrudan WS modu)     │          │
└────────────────────────────────────┘          │
                                                ▼
                  ┌──────────────────────────────────────────┐
                  │  GPU Worker (port 8001)                   │
                  │  gpu_worker/api.py                        │
                  │                                          │
                  │  ┌─ aiortc WebRTC Handler ──────────┐    │
                  │  │  rtc_worker.py                    │    │
                  │  │  DeepFakeVideoTrack (v2)          │    │
                  │  │    ├─ FaceBBoxCache               │    │
                  │  │    ├─ AdaptiveFrameDropper         │    │
                  │  │    └─ FaceSwapper (CUDA)           │    │
                  │  └──────────────────────────────────┘    │
                  │                                          │
                  │  ┌─ Voice Cloning Client ───────────┐    │
                  │  │  /api/chat                        │    │
                  │  │  /api/voices                      │    │
                  │  │  /api/upload-voice        ────────┼──► TTS Microservice
                  │  └──────────────────────────────────┘    │  (port 8002)
                  │                                          │
                  │  GPU: NVIDIA RTX 3050 Ti                 │
                  │  CUDA + cuDNN + ONNXRuntime-GPU           │
                  └──────────────────────────────────────────┘
                                                │
                                                ▼
                  ┌──────────────────────────────────────────┐
                  │  TTS Microservice (port 8002)             │
                  │  tts_service/tts_service.py               │
                  │                                          │
                  │  XTTSv2 (Coqui TTS)                      │
                  │  POST /generate-audio/                    │
                  │  Referans sesler: tts_service/references/  │
                  └──────────────────────────────────────────┘
```

---

## 🧩 Servis Mimarisi

### 1. GPU Worker (`gpu_worker/`)

Ana işlem birimi. WebRTC bağlantılarını yönetir ve gelen video karelerini GPU üzerinde işler.

**Temel dosyalar:**

| Dosya | Görev |
|-------|-------|
| `api.py` | FastAPI sunucusu — WebRTC offer/answer, chat, ses yükleme endpoint'leri |
| `rtc_worker.py` | `DeepFakeVideoTrack` sınıfı — aiortc VideoTransformTrack (v2 optimizasyonlu) |
| `start_worker.bat` | Sanal ortamı aktive edip GPU worker'ı başlatan script |
| `start_ngrok.bat` | Ngrok tüneli (opsiyonel, dışarıya açma) |

**WebRTC Akışı:**
1. React tarayıcıdan SDP Offer → Signaling Server → GPU Worker `/webrtc/offer`
2. GPU Worker `RTCPeerConnection` oluşturur
3. Gelen video track `DeepFakeVideoTrack` ile sarmalanır
4. Her kare GPU'da yüz değiştirme → işlenmiş kare WebRTC ile tarayıcıya geri döner

**Ek Endpoint'ler:**
- `POST /api/chat` — Metin gönder, AI yanıtı + ses sentezi al
- `GET /api/voices` — Mevcut ses profillerini listele
- `POST /api/upload-voice` — Yeni ses kaydı yükle (FFmpeg ile WAV'a dönüştürülür)
- `GET /health` — CUDA durumu ve aktif bağlantı sayısı

---

### 2. Signaling Server (`aws_server/signaling/`)

Hafif WebSocket relay sunucusu. Tarayıcı ile GPU Worker arasında SDP/ICE mesajlarını iletir.

**İki bağlantı modu:**

| Mod | Açıklama |
|-----|----------|
| **HTTP Proxy** | React → WS → Signaling → HTTP POST → GPU Worker (`:8001`) |
| **WS Relay** | GPU Worker `/ws/worker` ile kalıcı bağlantı kurar, mesajları iki yönlü iletir |

**Endpoint'ler:**
- `WS /ws/signal/{client_id}` — React istemci bağlantısı
- `WS /ws/worker` — GPU Worker kalıcı bağlantısı (Ngrok-free modu)
- `GET /health` — Worker ve istemci bağlantı durumu

Docker desteği mevcuttur (`Dockerfile`).

---

### 3. React Frontend (`aws_server/frontend/`)

Vite 8 + React 19 ile geliştirilmiş modern SPA.

**Dizin yapısı:**
```
src/
├── App.jsx                  ← Ana uygulama (yüz seçimi, video görüntüleme, chat)
├── index.css                ← Global stiller
├── App.css                  ← Bileşen stilleri
├── main.jsx                 ← React entry point
├── hooks/
│   ├── useWebRTC.js         ← WebRTC bağlantı yönetimi (SDP, ICE, track)
│   ├── useMediaConstraints.js ← Kamera/mikrofon izinleri ve kısıtlamaları
│   └── useAsyncModules.js   ← Ekran paylaşım & kayıt modülleri lazy-load
├── components/
│   └── VideoTile.jsx        ← Video akışı görüntüleme bileşeni
└── modules/
    ├── VoiceCloneModule.js  ← Ses kayıt, yükleme ve klonlama
    ├── ScreenShareModule.js ← Ekran paylaşımı
    └── MeetingRecordModule.js ← Toplantı kaydı (MediaRecorder)
```

---

### 4. TTS Microservice (`tts_service/`)

İzole Python 3.10 ortamında çalışan ses klonlama servisi.

| Dosya | Görev |
|-------|-------|
| `tts_service.py` | FastAPI sunucu — XTTSv2 model yükleme ve ses sentezi |
| `references/` | Referans ses dosyaları (`kayit_1.wav`, `kayit_2.wav`, `ata.wav`, vb.) |
| `requirements_tts.txt` | Bağımlılıklar: `TTS`, `torch`, `torchaudio` |

**Endpoint:** `POST /generate-audio/` — Metin + referans ses → sentezlenmiş WAV dosyası

---

### 5. Paylaşılan Modüller (`modules/`)

| Modül | Açıklama |
|-------|----------|
| `face_swap.py` | **FaceSwapper** — InsightFace + Inswapper ONNX modeli ile yüz değiştirme. CUDA öncelikli, CPU fallback. 6 adet hazır yüz modeli. |
| `voice_cloning.py` | **VoiceCloner** — TTS Microservice (`:8002`) ile HTTP üzerinden haberleşen async istemci |
| `conversation.py` | **ConversationManager** — Google Gemini 2.5 Flash API ile persona bazlı sohbet + güvenli loglama |

---

### 6. Değerlendirme (`evaluation/`)

| Metrik | Fonksiyon | Açıklama |
|--------|-----------|----------|
| MCD | `calculate_mcd()` | Mel-Cepstral Distortion — ses kalite ölçümü (DTW hizalı) |
| SNR | `calculate_snr()` | Signal-to-Noise Ratio — ses gürültü oranı |
| SSIM | `calculate_ssim()` | Structural Similarity Index — görüntü yapısal benzerliği |
| PSNR | `calculate_psnr()` | Peak Signal-to-Noise Ratio — görüntü kalitesi |
| Latency | `measure_latency()` | Uçtan uca gecikme ölçümü (ms) |

---

### 7. Alternatif Giriş Noktası (`main.py`)

Kök dizindeki `main.py`, GPU Worker'ın **Ngrok'suz** doğrudan WebSocket modudur. AWS Signaling Server'a `ws://host:8000/ws/worker` üzerinden bağlanır ve SDP/ICE alışverişini WS mesajları ile yapar. HTTP endpoint'i yoktur.

---

### 8. Legacy Arayüz (`web/`)

Eski mimari için Socket.IO tabanlı vanilya HTML/CSS/JS arayüzü. Artık aktif olarak kullanılmamaktadır; WebRTC tabanlı React frontend (`aws_server/frontend/`) onun yerini almıştır.

---

## 📁 Dosya Yapısı

```
DeepFake/
├── aws_server/
│   ├── signaling/
│   │   ├── main.py              ← FastAPI Signaling Server (WS Relay)
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── frontend/                ← React 19 + Vite 8 SPA
│   │   ├── src/
│   │   │   ├── App.jsx          ← Ana uygulama bileşeni
│   │   │   ├── index.css / App.css
│   │   │   ├── hooks/           ← useWebRTC, useMediaConstraints, useAsyncModules
│   │   │   ├── components/      ← VideoTile
│   │   │   └── modules/         ← VoiceClone, ScreenShare, MeetingRecord
│   │   ├── package.json
│   │   └── vite.config.js
│   └── venv/                    ← Signaling Server sanal ortamı
│
├── gpu_worker/
│   ├── api.py                   ← FastAPI GPU Worker (WebRTC + REST API)
│   ├── rtc_worker.py            ← DeepFakeVideoTrack v2 (aiortc)
│   ├── requirements.txt
│   ├── start_worker.bat
│   ├── start_ngrok.bat
│   └── venv/                    ← GPU Worker sanal ortamı
│
├── tts_service/
│   ├── tts_service.py           ← XTTSv2 FastAPI Microservice
│   ├── references/              ← Referans ses dosyaları (WAV)
│   ├── requirements_tts.txt
│   └── venv/                    ← TTS izole sanal ortamı (Python 3.10)
│
├── modules/
│   ├── face_swap.py             ← FaceSwapper (InsightFace + CUDA)
│   ├── voice_cloning.py         ← VoiceCloner (TTS microservice client)
│   └── conversation.py          ← ConversationManager (Gemini AI)
│
├── data/
│   ├── models/
│   │   └── inswapper_128.onnx   ← Yüz değiştirme ONNX modeli (~530MB)
│   └── source_faces/
│       ├── face1.png ... face6.jpeg  ← 6 adet kaynak yüz görseli
│
├── evaluation/
│   └── metrics.py               ← MCD, SNR, SSIM, PSNR, Latency metrikleri
│
├── web/                         ← [LEGACY] Socket.IO tabanlı eski arayüz
│   ├── index.html
│   ├── script.js
│   └── style.css
│
├── outputs/                     ← Üretilen ses dosyaları ve loglar
├── main.py                      ← Ngrok-free WS modu (alternatif giriş)
├── start_all.bat                ← Tüm servisleri tek seferde başlatma
├── requirements.txt             ← Ana proje bağımlılıkları
├── .env.example                 ← Örnek ortam değişkenleri
└── .gitignore
```

---

## ⚙ Teknoloji Yığını

### Backend

| Teknoloji | Kullanım Alanı |
|-----------|----------------|
| **Python 3.9 / 3.10** | GPU Worker, Signaling, TTS |
| **FastAPI** | Tüm backend API sunucuları |
| **aiortc** | Python tarafında WebRTC (P2P video) |
| **InsightFace** (`buffalo_l`) | Yüz algılama (FaceAnalysis) |
| **Inswapper** (ONNX) | Yüz değiştirme modeli |
| **ONNXRuntime-GPU** | CUDA hızlandırmalı model çıkarımı |
| **Coqui TTS (XTTSv2)** | Zero-shot çok dilli ses klonlama |
| **Google Gemini 2.5 Flash** | AI sohbet yanıtları |
| **PyTorch + CUDA** | GPU hesaplama altyapısı |
| **OpenCV** | Görüntü işleme |
| **FFmpeg** (imageio-ffmpeg) | Ses format dönüşümü |

### Frontend

| Teknoloji | Versiyon |
|-----------|---------|
| **React** | 19.2 |
| **Vite** | 8.0 |
| **WebRTC API** | RTCPeerConnection, getUserMedia |
| **WebSocket** | Sinyalizasyon kanalı |
| **MediaRecorder** | Toplantı kaydı |

### Altyapı

| Bileşen | Açıklama |
|---------|----------|
| **NVIDIA RTX 3050 Ti** | Yerel GPU (CUDA 12.x) |
| **AWS t2.micro** | Signaling Server (opsiyonel) |
| **Ngrok / Cloudflare Tunnel** | GPU Worker dışa açma (opsiyonel) |
| **Docker** | Signaling Server konteynerizasyon |

---

## 🚀 Kurulum & Başlatma

### Hızlı Başlatma (Tek Komut)

```bash
# Tüm 4 servisi ayrı PowerShell pencerelerinde başlatır
start_all.bat
```

### Manuel Başlatma

#### 1. GPU Worker (Terminal 1)
```bash
cd gpu_worker
venv\Scripts\activate
uvicorn api:app --host 0.0.0.0 --port 8001
```

#### 2. Signaling Server (Terminal 2)
```bash
cd aws_server\signaling
..\venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

#### 3. React Frontend (Terminal 3)
```bash
cd aws_server\frontend
npm run dev
```

#### 4. TTS Microservice (Terminal 4)
```bash
cd tts_service
venv\Scripts\activate
uvicorn tts_service:app --host 127.0.0.1 --port 8002
```

### Port Özeti

| Servis | Port | Protokol |
|--------|------|----------|
| Signaling Server | 8000 | HTTP + WebSocket |
| GPU Worker | 8001 | HTTP (WebRTC via aiortc) |
| TTS Microservice | 8002 | HTTP |
| React Dev Server | 5173 | HTTP |

---

## 📡 API Endpoint'leri

### GPU Worker (`:8001`)

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `GET` | `/health` | CUDA durumu, GPU adı, aktif bağlantı sayısı |
| `POST` | `/webrtc/offer` | SDP Offer al → Answer dön (WebRTC başlat) |
| `POST` | `/webrtc/ice` | Trickle ICE adayı ekle |
| `POST` | `/api/set-face-model/{client_id}` | Aktif yüz modelini değiştir |
| `POST` | `/api/chat` | Mesaj gönder → AI yanıt + ses sentezi |
| `GET` | `/api/voices` | Mevcut ses profillerini listele |
| `POST` | `/api/upload-voice` | Yeni ses kaydı yükle (multipart/form-data) |
| `GET` | `/outputs/{filename}` | Statik ses dosyalarını sun |

### Signaling Server (`:8000`)

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `GET` | `/health` | Worker ve istemci bağlantı durumu |
| `WS` | `/ws/signal/{client_id}` | React istemci sinyalizasyonu |
| `WS` | `/ws/worker` | GPU Worker kalıcı WS bağlantısı |

### TTS Microservice (`:8002`)

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `POST` | `/generate-audio/` | Metin + referans ses → sentezlenmiş WAV |

---

## 🔐 Ortam Değişkenleri

```env
# GPU Worker
GPU_WORKER_PORT=8001

# Signaling Server
GPU_WORKER_URL=http://127.0.0.1:8001

# React Frontend (.env)
VITE_SIGNALING_WS_URL=wss://AWS_IP_VEYA_DOMAIN:8000

# Gemini AI (proje kökü .env)
GEMINI_API_KEY=your_api_key_here
```

---

## ⚡ Performans Optimizasyonları

### GPU Worker v2 — `rtc_worker.py`

| Optimizasyon | Mekanizma | Kazanım |
|-------------|-----------|---------|
| **FaceBBoxCache** | Her 3 karede 1 tam yüz algılama, arada cache kullanımı | ~%60-70 detection yükü azalması |
| **AdaptiveFrameDropper** | İşleme süresi hareketli ortalamasına göre dinamik kare atlama | GPU aşırı yüklendiğinde latency koruması |
| **Singleton FaceSwapper** | `get_face_swapper()` ile tek seferlik GPU model yüklemesi | Bellek ve başlatma optimizasyonu |
| **Executor offload** | `run_in_executor()` ile frame işleme ayrı thread'de | asyncio event loop bloklanmaz |
| **CUDA Provider** | ONNXRuntime CUDAExecutionProvider + optimize ayarlar | CPU'ya göre ~10x hız artışı |
| **Isınma turu** | Sunucu başlangıcında modeller önceden VRAM'e yüklenir | İlk kare gecikmesi yok |

### İstatistik Loglama

Her 30 saniyede bir konsola performans raporu yazılır:
```
[Stats] FPS: 14.8 | Skip: 1x | Avg process: 62.3ms | Cache hit: 66.7% | face_model: face1
```

---

## 📊 Değerlendirme Metrikleri

`evaluation/metrics.py` dosyasında tanımlanan kalite ölçüm fonksiyonları:

| Metrik | Fonksiyon | Hedef |
|--------|-----------|-------|
| **MCD** (Mel-Cepstral Distortion) | `calculate_mcd()` | Klonlanmış ses kalitesi (düşük = iyi) |
| **SNR** (Signal-to-Noise Ratio) | `calculate_snr()` | Ses sinyal/gürültü oranı (yüksek = iyi) |
| **SSIM** (Structural Similarity) | `calculate_ssim()` | DeepFake görüntü yapısal benzerliği |
| **PSNR** (Peak SNR) | `calculate_psnr()` | Görüntü piksel kalitesi |
| **Latency** | `measure_latency()` | Uçtan uca sistem gecikmesi (ms) |

---

## 🔧 Yüz Modelleri

`data/source_faces/` dizininde 6 adet hazır kaynak yüz bulunur:

| Model ID | Dosya |
|----------|-------|
| `face1` | `face1.png` |
| `face2` | `face2.png` |
| `face3` | `face3.jpeg` |
| `face4` | `face4.jpeg` |
| `face5` | `face5.jpeg` |
| `face6` | `face6.jpeg` |

Yüz değiştirme modeli: `data/models/inswapper_128.onnx` (~530 MB)

---

## 🎤 Ses Profilleri

`tts_service/references/` dizinindeki WAV dosyaları:

| Dosya | Açıklama |
|-------|----------|
| `kayit_1.wav`, `kayit_2.wav` | Kullanıcı mikrofon kayıtları |
| `ata.wav`, `aziz.wav`, `fatih.wav`, `okan.wav`, `rte.wav` | Hazır kişi referansları |
| `prime.wav` | Uzun referans ses kaydı |

Yeni ses profilleri `POST /api/upload-voice` endpoint'i ile tarayıcıdan kaydedilip otomatik olarak `kayit_X.wav` formatında numaralandırılır.

---

## 🔒 Güvenlik Özellikleri

- **Filigran:** Her işlenmiş video karesine `"AI GENERATED - DEEPFAKE"` metni eklenir
- **Sohbet Loglama:** Tüm konuşmalar Base64 ile kodlanarak `outputs/secure_conversation_log.txt`'e yazılır
- **CORS:** Tüm servisler geliştirme aşamasında `allow_origins=["*"]` ile açıktır
- **WebRTC:** Tarayıcıda HTTPS zorunludur (`getUserMedia` politikası)

---

## ❓ SSS

**Ngrok yerine alternatif var mı?**
Evet, Cloudflare Tunnel kullanılabilir: `cloudflared tunnel --url http://localhost:8001`

**WebRTC bazı ağlarda çalışmıyor?**
Simetrik NAT arkasındaysanız TURN sunucusu ekleyin. `useWebRTC.js` → `ICE_SERVERS` dizisine TURN konfigürasyonu girin.

**HTTPS nasıl kurarım?**
AWS Certificate Manager + ALB veya Let's Encrypt + Nginx reverse proxy kullanın.

**TTS servisi neden ayrı?**
XTTSv2 Python 3.10 gerektirir ve ağır bağımlılıkları vardır. İzole sanal ortamda çalışarak ana GPU Worker ile çakışma önlenir.
