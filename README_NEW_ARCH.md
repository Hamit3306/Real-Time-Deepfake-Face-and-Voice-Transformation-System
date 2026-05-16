# DeepFace Live — Yeni Mimari Kurulum Rehberi

## Genel Bakış

```
┌──────────────────────────────────────────────────────────────┐
│                     TARAYICI (Kullanıcı)                     │
│   React + WebRTC (RTCPeerConnection)                         │
│   • Kamera: getUserMedia()                                   │
│   • Sinyal: WebSocket → AWS Signaling Server                 │
│   • Video:  P2P WebRTC ← GPU Worker (Ngrok üzerinden)       │
└──────────────┬───────────────────────────┬───────────────────┘
               │ WebSocket (SDP/ICE)        │ WebRTC P2P Video
               ▼                            │
┌──────────────────────────────────┐        │
│  AWS t2.micro (Free Tier)        │        │
│  ┌────────────────────────────┐  │        │
│  │  FastAPI Signaling Server  │  │        │
│  │  aws_server/signaling/     │  │        │
│  │  POST /webrtc/offer ──────────────────►│
│  └────────────────────────────┘  │        │
│  ┌────────────────────────────┐  │        │
│  │  React Frontend (Vite)     │  │        │
│  │  aws_server/frontend/      │  │        │
│  └────────────────────────────┘  │        │
└──────────────────────────────────┘        │
                                            ▼
                          ┌─────────────────────────────────┐
                          │  Yerel GPU Makine (RTX 3050 Ti) │
                          │  gpu_worker/api.py              │
                          │  aiortc + InsightFace + CUDA    │
                          │      ↑                          │
                          │  Ngrok HTTP Tüneli (port 8001)  │
                          └─────────────────────────────────┘
```

## Başlatma Adımları

### 1. Yerel GPU Makinesi

**Terminal 1 — GPU Worker'ı başlat:**
```bash
# Proje kökünden
.venv_deepfake\Scripts\activate
cd gpu_worker
pip install -r requirements.txt
uvicorn api:app --host 0.0.0.0 --port 8001
```

**Terminal 2 — Ngrok tüneli aç:**
```bash
gpu_worker\start_ngrok.bat
# Açılan URL'yi kopyala: https://xxxx.ngrok-free.app
```

### 2. AWS t2.micro Sunucu

**Signaling Server'ı başlat:**
```bash
# aws_server/signaling/ dizininde
pip install -r requirements.txt

# .env oluştur
echo "GPU_WORKER_URL=https://xxxx.ngrok-free.app" > .env

uvicorn main:app --host 0.0.0.0 --port 8000
```

**React Frontend'i build et ve sun:**
```bash
# aws_server/frontend/ dizininde
echo "VITE_SIGNALING_WS_URL=wss://AWS_IP:8000" > .env
npm install
npm run build
# dist/ klasörünü Nginx/Caddy ile sun VEYA
npm run preview -- --host --port 3000
```

### 3. Ngrok URL'sini Runtime'da Güncelle

GPU Worker her başlatıldığında yeni URL alabilir. Signaling Server'a HTTP ile bildir:
```bash
curl -X POST http://AWS_IP:8000/api/set-worker-url \
     -H "Content-Type: application/json" \
     -d '{"url": "https://yeni-ngrok-url.ngrok-free.app"}'
```

### 4. Kullanıcı Deneyimi

1. Tarayıcıda `https://AWS_IP:3000` aç.
2. Signaling Server URL'sini doğrula.
3. **🚀 Bağlantıyı Başlat** butonuna tıkla.
4. Kamera izni ver.
5. Birkaç saniye sonra sağ ekranda GPU'dan işlenmiş DeepFake video görünür.

## Dosya Yapısı

```
DeepFake/
├── aws_server/
│   ├── signaling/
│   │   ├── main.py          ← FastAPI Signaling Server
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── frontend/            ← Vite + React (WebRTC UI)
│       ├── src/
│       │   ├── App.jsx
│       │   ├── index.css
│       │   ├── hooks/
│       │   │   └── useWebRTC.js
│       │   └── components/
│       │       └── VideoTile.jsx
│       └── vite.config.js
├── gpu_worker/
│   ├── api.py               ← FastAPI + aiortc WebRTC handler
│   ├── rtc_worker.py        ← DeepFakeVideoTrack (aiortc)
│   ├── requirements.txt
│   ├── start_worker.bat     ← GPU worker başlatma scripti
│   └── start_ngrok.bat      ← Ngrok tüneli scripti
├── modules/
│   └── face_swap.py         ← process_frame_raw() eklendi (WebRTC için)
└── .env.example
```

## Bağımlılıklar

### GPU Worker Eklenenleri
| Paket | Versiyon | Açıklama |
|-------|----------|----------|
| `aiortc` | ≥1.9.0 | Python WebRTC kütüphanesi |
| `av`     | ≥12.0.0 | PyAV — video frame dönüşümü |

### AWS Signaling Server
| Paket | Açıklama |
|-------|----------|
| `fastapi`, `uvicorn` | API sunucu |
| `httpx` | Async HTTP (GPU Worker'a istek) |
| `websockets` | WebSocket desteği |

## Sık Sorulan Sorular

**"WebRTC P2P neden bazı ağlarda çalışmaz?"**  
Simetrik NAT arkasındaysanız STUN sunucusu IP keşfini tamamlayamaz; bu durumda ücretsiz bir TURN sunucusu (ör. [Open Relay](https://www.metered.ca/tools/openrelay/)) eklenmelidir. `useWebRTC.js` → `ICE_SERVERS` dizisine ekleyin.

**"Ngrok yerine Cloudflare Tunnel kullanabilir miyim?"**  
Evet:
```bash
cloudflared tunnel --url http://localhost:8001
```
Açılan URL'yi aynı şekilde Signaling Server'a bildirin.

**"AWS'de HTTPS nasıl kurarım?"**  
AWS Certificate Manager + ALB veya Let's Encrypt + Nginx reverse proxy kullanın. WebRTC tarayıcıda HTTPS zorunlu kılar (getUserMedia).
