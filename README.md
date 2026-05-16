# Real-Time Deepfake Face and Voice Transformation System

> GPU-accelerated real-time deepfake video and voice cloning system based on WebRTC, InsightFace, XTTSv2, and Gemini AI.

---

## Table of Contents

- [Overview](#overview)
- [Architecture Diagram](#architecture-diagram)
- [Service Architecture](#service-architecture)
- [Directory Structure](#directory-structure)
- [Technology Stack](#technology-stack)
- [Installation and Setup](#installation-and-setup)
- [API Endpoints](#api-endpoints)
- [Environment Variables](#environment-variables)
- [Performance Optimizations](#performance-optimizations)
- [Evaluation Metrics](#evaluation-metrics)

---

## Overview

This project is a distributed deepfake platform consisting of 4 independent microservices:

| # | Service | Port | Location | Description |
|---|--------|------|-------|----------|
| 1 | **GPU Worker** | `8001` | Local (RTX 3050 Ti) | WebRTC video processing + face swap + voice cloning API |
| 2 | **Signaling Server** | `8000` | AWS t2.micro / Local | WebSocket relay — SDP/ICE signaling |
| 3 | **React Frontend** | `5173` | AWS / Local | Vite + React user interface |
| 4 | **TTS Microservice** | `8002` | Local | XTTSv2 voice cloning service (isolated Python 3.10) |

Additionally, there is a legacy Socket.IO based HTML interface in the `web/` folder for the old architecture, and an alternative GPU worker with direct WebSocket connection without Ngrok in the root `main.py`.

---

## Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                      BROWSER (Client)                           │
│   React 19 + Vite 8  (aws_server/frontend/)                     │
│                                                                 │
│   Hooks:                                                        │
│     useWebRTC.js ─── WebSocket signaling + RTCPeerConnection    │
│     useMediaConstraints.js ─── Camera/microphone management     │
│     useAsyncModules.js ─── Screen share & recording modules     │
│                                                                 │
│   Modules:                                                      │
│     VoiceCloneModule.js ── Voice recording & upload             │
│     ScreenShareModule.js ── Screen sharing                      │
│     MeetingRecordModule.js ── Meeting recording                 │
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
│  /ws/worker  ← GPU Worker (opt.)   │          │
│  (Ngrok-free direct WS mode)       │          │
└────────────────────────────────────┘          │
                                                ▼
                  ┌──────────────────────────────────────────┐
                  │  GPU Worker (port 8001)                  │
                  │  gpu_worker/api.py                       │
                  │                                          │
                  │  ┌─ aiortc WebRTC Handler ──────────┐    │
                  │  │  rtc_worker.py                   │    │
                  │  │  DeepFakeVideoTrack (v2)         │    │
                  │  │    ├─ FaceBBoxCache              │    │
                  │  │    ├─ AdaptiveFrameDropper       │    │
                  │  │    └─ FaceSwapper (CUDA)         │    │
                  │  └──────────────────────────────────┘    │
                  │                                          │
                  │  ┌─ Voice Cloning Client ───────────┐    │
                  │  │  /api/chat                       │    │
                  │  │  /api/voices                     │    │
                  │  │  /api/upload-voice       ────────┼──► TTS Microservice
                  │  └──────────────────────────────────┘    │  (port 8002)
                  │                                          │
                  │  GPU: NVIDIA RTX 3050 Ti                 │
                  │  CUDA + cuDNN + ONNXRuntime-GPU          │
                  └──────────────────────────────────────────┘
                                                │
                                                ▼
                  ┌──────────────────────────────────────────┐
                  │  TTS Microservice (port 8002)            │
                  │  tts_service/tts_service.py              │
                  │                                          │
                  │  XTTSv2 (Coqui TTS)                      │
                  │  POST /generate-audio/                   │
                  │  Reference voices: tts_service/references│
                  └──────────────────────────────────────────┘
```

---

## Service Architecture

### 1. GPU Worker (`gpu_worker/`)

The main processing unit. It manages WebRTC connections and processes incoming video frames on the GPU.

**Core files:**

| File | Purpose |
|-------|-------|
| `api.py` | FastAPI server — WebRTC offer/answer, chat, voice upload endpoints |
| `rtc_worker.py` | `DeepFakeVideoTrack` class — aiortc VideoTransformTrack (v2 optimized) |
| `start_worker.bat` | Script to activate the virtual environment and start the GPU worker |
| `start_ngrok.bat` | Ngrok tunnel (optional, for exposing to the internet) |

**WebRTC Flow:**
1. SDP Offer from React browser → Signaling Server → GPU Worker `/webrtc/offer`
2. GPU Worker creates an `RTCPeerConnection`
3. Incoming video track is wrapped with `DeepFakeVideoTrack`
4. Each frame undergoes face swapping on the GPU → processed frame is returned to the browser via WebRTC

**Additional Endpoints:**
- `POST /api/chat` — Send text, receive AI response + synthesized audio
- `GET /api/voices` — List available voice profiles
- `POST /api/upload-voice` — Upload a new voice recording (converted to WAV via FFmpeg)
- `GET /health` — CUDA status and active connection count

---

### 2. Signaling Server (`aws_server/signaling/`)

Lightweight WebSocket relay server. It forwards SDP/ICE messages between the browser and the GPU Worker.

**Two connection modes:**

| Mode | Description |
|-----|----------|
| **HTTP Proxy** | React → WS → Signaling → HTTP POST → GPU Worker (`:8001`) |
| **WS Relay** | Establishes a persistent connection with GPU Worker via `/ws/worker`, forwarding messages bidirectionally |

**Endpoints:**
- `WS /ws/signal/{client_id}` — React client connection
- `WS /ws/worker` — GPU Worker persistent connection (Ngrok-free mode)
- `GET /health` — Worker and client connection status

Docker support is available (`Dockerfile`).

---

### 3. React Frontend (`aws_server/frontend/`)

Modern SPA built with Vite 8 + React 19.

**Directory Structure:**
```
src/
├── App.jsx                  ← Main application (face selection, video display, chat)
├── index.css                ← Global styles
├── App.css                  ← Component styles
├── main.jsx                 ← React entry point
├── hooks/
│   ├── useWebRTC.js         ← WebRTC connection management (SDP, ICE, track)
│   ├── useMediaConstraints.js ← Camera/microphone permissions and constraints
│   └── useAsyncModules.js   ← Lazy-loading for screen share & record modules
├── components/
│   └── VideoTile.jsx        ← Video stream display component
└── modules/
    ├── VoiceCloneModule.js  ← Voice recording, uploading, and cloning
    ├── ScreenShareModule.js ← Screen sharing
    └── MeetingRecordModule.js ← Meeting recording (MediaRecorder)
```

---

### 4. TTS Microservice (`tts_service/`)

Voice cloning service running in an isolated Python 3.10 environment.

| File | Purpose |
|-------|-------|
| `tts_service.py` | FastAPI server — XTTSv2 model loading and voice synthesis |
| `references/` | Reference voice files (`sample_1.wav`, `sample_2.wav`, etc.) |
| `requirements_tts.txt` | Dependencies: `TTS`, `torch`, `torchaudio` |

**Endpoint:** `POST /generate-audio/` — Text + reference audio → synthesized WAV file

---

### 5. Shared Modules (`modules/`)

| Module | Description |
|-------|----------|
| `face_swap.py` | **FaceSwapper** — Face swapping using InsightFace + Inswapper ONNX model. CUDA prioritized, CPU fallback. Contains pre-configured face models. |
| `voice_cloning.py` | **VoiceCloner** — Async client communicating with the TTS Microservice (`:8002`) over HTTP |
| `conversation.py` | **ConversationManager** — Persona-based chat + secure logging using Google Gemini API |

---

### 6. Evaluation (`evaluation/`)

| Metric | Function | Description |
|--------|-----------|----------|
| MCD | `calculate_mcd()` | Mel-Cepstral Distortion — audio quality measurement (DTW aligned) |
| SNR | `calculate_snr()` | Signal-to-Noise Ratio — audio noise ratio |
| SSIM | `calculate_ssim()` | Structural Similarity Index — image structural similarity |
| PSNR | `calculate_psnr()` | Peak Signal-to-Noise Ratio — image quality |
| Latency | `measure_latency()` | End-to-end latency measurement (ms) |

---

### 7. Alternative Entry Point (`main.py`)

The `main.py` file in the root directory serves as the direct WebSocket mode for the GPU Worker **without Ngrok**. It connects to the AWS Signaling Server via `ws://host:8000/ws/worker` and exchanges SDP/ICE via WS messages. It does not have an HTTP endpoint.

---

### 8. Legacy Interface (`web/`)

Socket.IO based vanilla HTML/CSS/JS interface for the old architecture. It is no longer actively used; the WebRTC-based React frontend (`aws_server/frontend/`) has replaced it.

---

## Directory Structure

```text
DeepFake/
├── aws_server/
│   ├── signaling/
│   │   ├── main.py              ← FastAPI Signaling Server (WS Relay)
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── frontend/                ← React 19 + Vite 8 SPA
│   │   ├── src/
│   │   │   ├── App.jsx          ← Main application component
│   │   │   ├── index.css / App.css
│   │   │   ├── hooks/           ← useWebRTC, useMediaConstraints, useAsyncModules
│   │   │   ├── components/      ← VideoTile
│   │   │   └── modules/         ← VoiceClone, ScreenShare, MeetingRecord
│   │   ├── package.json
│   │   └── vite.config.js
│   └── venv/                    ← Signaling Server virtual environment
│
├── gpu_worker/
│   ├── api.py                   ← FastAPI GPU Worker (WebRTC + REST API)
│   ├── rtc_worker.py            ← DeepFakeVideoTrack v2 (aiortc)
│   ├── requirements.txt
│   ├── start_worker.bat
│   ├── start_ngrok.bat
│   └── venv/                    ← GPU Worker virtual environment
│
├── tts_service/
│   ├── tts_service.py           ← XTTSv2 FastAPI Microservice
│   ├── references/              ← Reference voice files (WAV)
│   ├── requirements_tts.txt
│   └── venv/                    ← TTS isolated virtual environment (Python 3.10)
│
├── modules/
│   ├── face_swap.py             ← FaceSwapper (InsightFace + CUDA)
│   ├── voice_cloning.py         ← VoiceCloner (TTS microservice client)
│   └── conversation.py          ← ConversationManager (Gemini AI)
│
├── data/
│   ├── models/
│   │   └── inswapper_128.onnx   ← Face swap ONNX model (~530MB)
│   └── source_faces/
│       ├── face1.png ...        ← Source face images
│
├── evaluation/
│   └── metrics.py               ← MCD, SNR, SSIM, PSNR, Latency metrics
│
├── web/                         ← [LEGACY] Socket.IO based old interface
│   ├── index.html
│   ├── script.js
│   └── style.css
│
├── outputs/                     ← Generated audio files and logs
├── main.py                      ← Ngrok-free WS mode (alternative entry point)
├── start_all.bat                ← Start all services script
├── requirements.txt             ← Main project dependencies
├── .env.example                 ← Example environment variables
└── .gitignore
```

---

## Technology Stack

### Backend

| Technology | Usage |
|-----------|----------------|
| **Python 3.9 / 3.10** | GPU Worker, Signaling, TTS |
| **FastAPI** | All backend API servers |
| **aiortc** | WebRTC in Python (P2P video) |
| **InsightFace** (`buffalo_l`) | Face detection (FaceAnalysis) |
| **Inswapper** (ONNX) | Face swapping model |
| **ONNXRuntime-GPU** | CUDA-accelerated model inference |
| **Coqui TTS (XTTSv2)** | Zero-shot multilingual voice cloning |
| **Google Gemini API** | AI chat responses |
| **PyTorch + CUDA** | GPU computation framework |
| **OpenCV** | Image processing |
| **FFmpeg** (imageio-ffmpeg) | Audio format conversion |

### Frontend

| Technology | Version |
|-----------|---------|
| **React** | 19.2 |
| **Vite** | 8.0 |
| **WebRTC API** | RTCPeerConnection, getUserMedia |
| **WebSocket** | Signaling channel |
| **MediaRecorder** | Meeting recording |

### Infrastructure

| Component | Description |
|---------|----------|
| **NVIDIA RTX 3050 Ti** | Local GPU (CUDA 12.x) |
| **AWS t2.micro** | Signaling Server (optional) |
| **Ngrok / Cloudflare Tunnel** | GPU Worker exposure (optional) |
| **Docker** | Signaling Server containerization |

---

## Installation and Setup

### Quick Start (Single Command)

```bash
# Starts all 4 services in separate PowerShell windows
start_all.bat
```

### Manual Start

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

### Port Summary

| Service | Port | Protocol |
|--------|------|----------|
| Signaling Server | 8000 | HTTP + WebSocket |
| GPU Worker | 8001 | HTTP (WebRTC via aiortc) |
| TTS Microservice | 8002 | HTTP |
| React Dev Server | 5173 | HTTP |

---

## API Endpoints

### GPU Worker (`:8001`)

| Method | Endpoint | Description |
|--------|----------|----------|
| `GET` | `/health` | CUDA status, GPU name, active connection count |
| `POST` | `/webrtc/offer` | Receive SDP Offer → Return Answer (Start WebRTC) |
| `POST` | `/webrtc/ice` | Add trickle ICE candidate |
| `POST` | `/api/set-face-model/{client_id}` | Change active face model |
| `POST` | `/api/chat` | Send message → AI response + audio synthesis |
| `GET` | `/api/voices` | List available voice profiles |
| `POST` | `/api/upload-voice` | Upload new voice recording (multipart/form-data) |
| `GET` | `/outputs/{filename}` | Serve static audio files |

### Signaling Server (`:8000`)

| Method | Endpoint | Description |
|--------|----------|----------|
| `GET` | `/health` | Worker and client connection status |
| `WS` | `/ws/signal/{client_id}` | React client signaling |
| `WS` | `/ws/worker` | GPU Worker persistent WS connection |

### TTS Microservice (`:8002`)

| Method | Endpoint | Description |
|--------|----------|----------|
| `POST` | `/generate-audio/` | Text + reference audio → synthesized WAV |

---

## Environment Variables

```env
# GPU Worker
GPU_WORKER_PORT=8001

# Signaling Server
GPU_WORKER_URL=http://127.0.0.1:8001

# React Frontend (.env)
VITE_SIGNALING_WS_URL=wss://AWS_IP_OR_DOMAIN:8000

# Gemini AI (project root .env)
GEMINI_API_KEY=your_api_key_here
```

---

## Performance Optimizations

### GPU Worker v2 — `rtc_worker.py`

| Optimization | Mechanism | Gain |
|-------------|-----------|---------|
| **FaceBBoxCache** | Full face detection every 3 frames, cache used in between | ~60-70% reduction in detection load |
| **AdaptiveFrameDropper** | Dynamic frame dropping based on moving average of processing time | Latency protection under heavy GPU load |
| **Singleton FaceSwapper** | One-time GPU model loading via `get_face_swapper()` | Memory and initialization optimization |
| **Executor offload** | Frame processing in separate thread via `run_in_executor()` | Prevents blocking the asyncio event loop |
| **CUDA Provider** | ONNXRuntime CUDAExecutionProvider + optimized settings | ~10x speedup compared to CPU |
| **Warm-up pass** | Models preloaded into VRAM at server startup | No initial frame latency |

### Statistics Logging

A performance report is written to the console every 30 seconds:
```text
[Stats] FPS: 14.8 | Skip: 1x | Avg process: 62.3ms | Cache hit: 66.7% | face_model: face1
```

---

## Evaluation Metrics

Quality measurement functions defined in the `evaluation/metrics.py` file:

| Metric | Function  | Target |
|--------|-----------|-------|
| **MCD** (Mel-Cepstral Distortion) | `calculate_mcd()` | Cloned voice quality (lower = better) |
| **SNR** (Signal-to-Noise Ratio) | `calculate_snr()` | Voice signal-to-noise ratio (higher = better) |
| **SSIM** (Structural Similarity) | `calculate_ssim()` | Deepfake image structural similarity |
| **PSNR** (Peak SNR) | `calculate_psnr()` | Image pixel quality |
| **Latency** | `measure_latency()` | End-to-end system latency (ms) |

---

## Voice Profiles

New voice profiles can be recorded from the browser via the `POST /api/upload-voice` endpoint and are automatically numbered in `kayit_X.wav` format inside `tts_service/references/`.

---

## Security Features

- **Watermark:** `"AI GENERATED - DEEPFAKE"` text is added to every processed video frame.
- **Chat Logging:** All conversations are Base64 encoded and written to `outputs/secure_conversation_log.txt`.
- **CORS:** All services are open during development with `allow_origins=["*"]`.
- **WebRTC:** HTTPS is mandatory in the browser (`getUserMedia` policy).

---

## FAQ

**Is there an alternative to Ngrok?**
Yes, Cloudflare Tunnel can be used: `cloudflared tunnel --url http://localhost:8001`

**WebRTC is not working on some networks?**
If you are behind a symmetric NAT, add a TURN server. Enter the TURN configuration into the `ICE_SERVERS` array in `useWebRTC.js`.

**How do I set up HTTPS?**
Use AWS Certificate Manager + ALB or Let's Encrypt + Nginx reverse proxy.

**Why is the TTS service separate?**
XTTSv2 requires Python 3.10 and has heavy dependencies. Running it in an isolated virtual environment prevents conflicts with the main GPU Worker.
