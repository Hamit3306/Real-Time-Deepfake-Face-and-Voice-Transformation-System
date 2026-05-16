"""
GPU Worker - FastAPI API Sunucusu
==================================
Ngrok tüneli aracılığıyla dışarıya açılır.
AWS Signaling Server'dan gelen WebRTC Offer'ları karşılar,
aiortc ile Answer üretir ve WebRTC bağlantısını kurar.

Kurulum:
    pip install -r requirements.txt
    python api.py

Dışarıya açma (ayrı terminalde):
    ngrok http 8001
    -- veya --
    cloudflared tunnel --url http://localhost:8001
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Optional

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from modules.voice_cloning import VoiceCloner

# === Meeting Simulation (FR-4) - Opsiyonel imports ===
# Bunlar başarısız olursa /api/scenarios ve /api/chat-scenario endpoint'leri
# çalışmaz ama mevcut sistem etkilenmez.
try:
    from modules import scenarios as _scenarios_module
except Exception as _scenarios_err:
    _scenarios_module = None
    logging.getLogger(__name__).warning(f"scenarios modülü yüklenemedi: {_scenarios_err}")

try:
    from modules.conversation import ConversationManager as _ConversationManager
except Exception as _conv_err:
    _ConversationManager = None
    logging.getLogger(__name__).warning(f"ConversationManager yüklenemedi: {_conv_err}")
# === / Meeting Simulation ===

# aiortc
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay

from rtc_worker import DeepFakeVideoTrack

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Aktif RTCPeerConnection nesnelerini tutan sözlük {client_id: pc}
peer_connections: Dict[str, RTCPeerConnection] = {}
relay = MediaRelay()

# Voice Cloner Başlat
try:
    voice_cloner = VoiceCloner()
except Exception as e:
    logger.error(f"Voice Cloner başlatılamadı: {e}")
    voice_cloner = None

# === Meeting Simulation (FR-4) - ConversationManager singleton ===
# Senaryo bazlı sohbet için kullanılır. Başlatılamazsa /api/chat-scenario
# fallback yanıt verir; mevcut /api/chat etkilenmez.
if _ConversationManager is not None:
    try:
        conversation_manager_scenario = _ConversationManager()
    except Exception as e:
        logger.warning(f"ConversationManager (senaryo) başlatılamadı: {e}")
        conversation_manager_scenario = None
else:
    conversation_manager_scenario = None
# === / Meeting Simulation ===

# Outputs dizini oluştur
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== GPU Worker başlatılıyor ===")
    logger.info(f"GPU: CUDA desteği kontrol ediliyor...")
    try:
        from rtc_worker import get_face_swapper
        logger.info("GPU Modelleri önceden belleğe yükleniyor (Isınma turu)...")
        get_face_swapper()
    except Exception as e:
        logger.error(f"GPU Modelleri yüklenirken hata: {e}")
        
    yield
    # Sunucu kapanırken tüm peer bağlantılarını kapat
    logger.info("Tüm WebRTC bağlantıları kapatılıyor...")
    coros = [pc.close() for pc in peer_connections.values()]
    await asyncio.gather(*coros)
    peer_connections.clear()
    logger.info("=== GPU Worker kapatıldı ===")


app = FastAPI(
    title="DeepFake GPU Worker",
    description="WebRTC tabanlı gerçek zamanlı DeepFake servisi (aiortc + InsightFace + CUDA).",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Statik dosyaları sun (Ses dosyaları için)
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")


# ---------------------------------------------------------------------------
# Pydantic Modeller
# ---------------------------------------------------------------------------

class RTCOfferRequest(BaseModel):
    """AWS Signaling Server'ın /webrtc/offer endpoint'ine gönderdiği payload."""
    sdp:        str
    type:       str = "offer"
    client_id:  str = ""
    face_model: str = "face1"


class RTCIceRequest(BaseModel):
    """Trickle ICE adayı için."""
    client_id: str
    candidate: dict


class ChatRequest(BaseModel):
    """Chat endpoint'ine gelen istek modeli."""
    message: str
    persona: str = "formal"
    rate: float = 1.0
    pitch: int = 0
    emotion: str = "neutral"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Ngrok tüneli doğrulama ve sağlık kontrolü."""
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if cuda_available else "N/A"
    except ImportError:
        cuda_available = False
        gpu_name = "torch yüklü değil"
    return {
        "status": "ok",
        "cuda": cuda_available,
        "gpu": gpu_name,
        "active_connections": len(peer_connections),
    }


@app.post("/webrtc/offer")
async def webrtc_offer(req: RTCOfferRequest):
    """
    AWS Signaling Server buraya SDP offer gönderir.
    1. RTCPeerConnection oluşturulur.
    2. Gelen video track'e DeepFakeVideoTrack wrap'lenir.
    3. SDP answer üretilip döndürülür (Signaling Server → React'a iletecek).
    """
    client_id = req.client_id or str(uuid.uuid4())
    logger.info(f"Yeni offer alındı. client_id={client_id}, face_model={req.face_model}")

    # Eski bağlantı varsa kapat
    if client_id in peer_connections:
        await peer_connections[client_id].close()

    pc = RTCPeerConnection()
    peer_connections[client_id] = pc

    # Toplanan ICE adaylarını sakla (basit non-trickle ICE)
    ice_candidates = []

    @pc.on("icecandidate")
    def on_ice_candidate(candidate):
        if candidate:
            ice_candidates.append({
                "candidate":     candidate.candidate,
                "sdpMid":        candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex,
            })

    @pc.on("connectionstatechange")
    async def on_connection_state_change():
        logger.info(f"[{client_id}] Bağlantı durumu: {pc.connectionState}")
        if pc.connectionState in ("failed", "closed"):
            await pc.close()
            peer_connections.pop(client_id, None)
            logger.info(f"[{client_id}] Bağlantı kaldırıldı.")

    @pc.on("track")
    def on_track(track):
        """
        Tarayıcıdan gelen video track yakalandı.
        DeepFakeVideoTrack ile wrap'le ve geri gönder.
        """
        logger.info(f"[{client_id}] Track alındı: kind={track.kind}")
        if track.kind == "video":
            deep_fake_track = DeepFakeVideoTrack(
                relay.subscribe(track),
                face_model=req.face_model,
            )
            pc.addTrack(deep_fake_track)
            logger.info(f"[{client_id}] DeepFakeVideoTrack eklendi.")

    # Offer'ı ayarla
    offer = RTCSessionDescription(sdp=req.sdp, type=req.type)
    await pc.setRemoteDescription(offer)

    # Answer üret
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # ICE gathering tamamlanana kadar kısa bir süre bekle
    await asyncio.sleep(1.0)

    logger.info(f"[{client_id}] Answer gönderiliyor. ICE adayı sayısı: {len(ice_candidates)}")

    return {
        "sdp":            pc.localDescription.sdp,
        "type":           pc.localDescription.type,
        "client_id":      client_id,
        "ice_candidates": ice_candidates,
    }


@app.post("/webrtc/ice")
async def webrtc_ice(req: RTCIceRequest):
    """
    Trickle ICE: AWS Signaling Server'dan gelen ek ICE adaylarını ekler.
    """
    client_id = req.client_id
    if client_id not in peer_connections:
        raise HTTPException(status_code=404, detail=f"Bağlantı bulunamadı: {client_id}")

    pc = peer_connections[client_id]
    try:
        from aiortc import RTCIceCandidate
        candidate_data = req.candidate
        candidate = RTCIceCandidate(
            component   = candidate_data.get("component", 1),
            foundation  = candidate_data.get("foundation", ""),
            ip          = candidate_data.get("ip", ""),
            port        = int(candidate_data.get("port", 0)),
            priority    = int(candidate_data.get("priority", 0)),
            protocol    = candidate_data.get("protocol", "udp"),
            type        = candidate_data.get("type", "host"),
            sdpMid       = candidate_data.get("sdpMid"),
            sdpMLineIndex= candidate_data.get("sdpMLineIndex"),
        )
        await pc.addIceCandidate(candidate)
        return {"status": "added"}
    except Exception as e:
        logger.error(f"[{client_id}] ICE aday ekleme hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/set-face-model/{client_id}")
async def set_face_model(client_id: str, payload: dict):
    """
    Aktif bağlantının yüz modelini değiştirir (canlı olarak).
    Payload: { "face_model": "face2" }
    """
    if client_id not in peer_connections:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı.")
    # Not: Track referansına erişmek için DeepFakeVideoTrack'i ayrıca kaydetmek gerekir;
    # bu endpoint forward-compatibility için şimdilik stub'dur.
    model = payload.get("face_model", "face1")
    logger.info(f"[{client_id}] Face model değiştirme isteği: {model}")
    return {"status": "ok", "face_model": model}


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Kullanıcıdan gelen mesajı alır, AI yanıtı oluşturur ve bunu sese dönüştürür.
    """
    logger.info(f"Chat mesajı alındı: {req.message} | Emotion: {req.emotion} | Rate: {req.rate} | Pitch: {req.pitch}")
    
    # Şimdilik basit bir echo / mock AI yanıtı (Gerçek LLM entegrasyonu buraya gelecek)
    if "nasılsın" in req.message.lower():
        ai_response = "Teşekkür ederim, gayet iyiyim! Siz nasılsınız?"
    elif "merhaba" in req.message.lower():
        ai_response = "Merhaba! Size nasıl yardımcı olabilirim?"
    else:
        ai_response = f"Bunu duyduğuma sevindim. Şunu söylediniz: {req.message}"
        
    if not voice_cloner:
        return {"response": ai_response, "audio_url": None, "error": "Voice cloner aktif değil."}

    try:
        # Sesi sentezle
        wav_filename = await voice_cloner.clone_voice(
            target_text=ai_response,
            persona=req.persona,
            rate=req.rate,
            pitch=req.pitch,
            emotion=req.emotion
        )
        
        if wav_filename:
            # Ngrok URL'si veya localhost üzerinden erişilebilir tam URL
            audio_url = f"http://localhost:{os.getenv('GPU_WORKER_PORT', 8001)}/outputs/{wav_filename}"
            return {"response": ai_response, "audio_url": audio_url}
        else:
            return {"response": ai_response, "audio_url": None, "error": "Ses sentezlenemedi."}
    except Exception as e:
        logger.error(f"Chat Endpoint Hatası: {e}")
        return {"response": ai_response, "audio_url": None, "error": str(e)}


@app.get("/api/voices")
async def get_voices():
    """Mevcut tüm ses kayıtlarını (Kayıt 1, Kayıt 2...) liste olarak döndürür."""
    ref_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tts_service", "references")
    if not os.path.exists(ref_dir):
        return {"voices": []}
    
    voices = []
    for file in os.listdir(ref_dir):
        if file.endswith(".wav"):
            voices.append(file.replace(".wav", ""))
    
    # Sıralı gelmesi için isme göre sıralayalım
    voices.sort(key=lambda x: int(x.split("_")[1]) if "_" in x and x.split("_")[1].isdigit() else 0)
    return {"voices": voices}


@app.post("/api/upload-voice")
async def upload_voice(file: UploadFile = File(...)):
    """
    Kullanıcının tarayıcıdan kaydettiği sesleri dinamik 'kayit_X' adıyla kaydeder.
    """
    logger.info(f"Ses yükleme isteği alındı: {file.filename}")
    
    # 1. Dosyayı geçici olarak kaydet
    temp_path = f"temp_{uuid.uuid4().hex}_{file.filename}"
    try:
        with open(temp_path, "wb") as f:
            f.write(await file.read())
            
        # 2. Çıktı dosya yolu (tts_service/references/kayit_X.wav)
        ref_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tts_service", "references")
        os.makedirs(ref_dir, exist_ok=True)
        
        # Klasördeki mevcut kayıtları say
        existing_count = len([f for f in os.listdir(ref_dir) if f.startswith("kayit_") and f.endswith(".wav")])
        new_name = f"kayit_{existing_count + 1}"
        out_wav = os.path.join(ref_dir, f"{new_name}.wav")
        
        # 3. FFmpeg ile dönüştür (wav, mono, 22050Hz)
        import subprocess
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        
        # overwrite existing (-y)
        cmd = [ffmpeg_exe, "-y", "-i", temp_path, "-ac", "1", "-ar", "22050", out_wav]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        logger.info(f"Özel ses kaydedildi ve dönüştürüldü: {out_wav}")
        return {"status": "ok", "message": "Ses dosyası başarıyla yüklendi.", "persona": new_name}
        
    except Exception as e:
        logger.error(f"Ses yükleme/dönüştürme hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Geçici dosyayı temizle
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ===========================================================================
# Meeting Simulation Endpoints (FR-4.1 - FR-4.6)
# ===========================================================================
# Bu blok mevcut endpoint'leri etkilemez. Tamamen additive (ek).
# scenarios modülü veya ConversationManager yüklü değilse bile
# endpoint'ler güvenli hata mesajı döner, sistem çökmez.
# ---------------------------------------------------------------------------

class ScenarioChatRequest(BaseModel):
    """Senaryo bazlı sohbet isteği."""
    message: str
    scenario_id: str                          # FR-4.2..4.5: hangi senaryo
    persona: str = "kayit_1"                  # ses modeli (TTS reference)
    rate: float = 1.0
    pitch: int = 0
    emotion: str = "neutral"
    participant_id: Optional[str] = None      # FR-4.6: çoklu katılımcı desteği


@app.get("/api/scenarios")
async def list_meeting_scenarios():
    """
    FR-4.2..4.5: Önceden tanımlı senaryoların listesini döndürür.
    UI bu listeyi kullanarak senaryo seçim panelini doldurur.
    """
    if _scenarios_module is None:
        return {"scenarios": [], "error": "scenarios modülü yüklenemedi."}
    try:
        return {"scenarios": _scenarios_module.list_scenarios()}
    except Exception as e:
        logger.error(f"list_scenarios hatası: {e}")
        return {"scenarios": [], "error": str(e)}


@app.post("/api/scenario/opening")
async def scenario_opening(payload: dict):
    """
    Senaryo seçildiğinde AI'nin söyleyeceği açılış cümlesini ses olarak üretir.
    Payload: { "scenario_id": "...", "persona": "kayit_1", ... }
    """
    scenario_id = payload.get("scenario_id", "")
    if _scenarios_module is None:
        return {"text": "", "audio_url": None, "error": "scenarios modülü yüklenemedi."}

    scenario = _scenarios_module.get_scenario(scenario_id)
    if not scenario:
        return {"text": "", "audio_url": None, "error": f"Senaryo bulunamadı: {scenario_id}"}

    opening_text = scenario["opening_line"]

    if not voice_cloner:
        return {"text": opening_text, "audio_url": None, "error": "Voice cloner aktif değil."}

    try:
        wav_filename = await voice_cloner.clone_voice(
            target_text=opening_text,
            persona=payload.get("persona", "kayit_1"),
            rate=float(payload.get("rate", 1.0)),
            pitch=int(payload.get("pitch", 0)),
            emotion=payload.get("emotion", "neutral"),
        )
        if wav_filename:
            audio_url = f"http://localhost:{os.getenv('GPU_WORKER_PORT', 8001)}/outputs/{wav_filename}"
            return {"text": opening_text, "audio_url": audio_url, "scenario_id": scenario_id}
        return {"text": opening_text, "audio_url": None, "error": "Ses sentezlenemedi."}
    except Exception as e:
        logger.error(f"scenario_opening hatası: {e}")
        return {"text": opening_text, "audio_url": None, "error": str(e)}


@app.post("/api/chat-scenario")
async def chat_scenario(req: ScenarioChatRequest):
    """
    Senaryo bazlı sohbet (FR-4.2..4.5).

    /api/chat'ten farkı: Gemini'ye verilen prompt, seçilen senaryonun
    system_prompt'u ile başlar. Böylece AI o senaryonun karakterinde kalır.

    FR-4.6 (çoklu katılımcı): participant_id geçilirse log'a yazılır;
    her katılımcının farklı yüz+ses kombinasyonu olabilir, ama bu endpoint
    sadece TEK katılımcının cevabını üretir (frontend sırayla çağırır).
    """
    if _scenarios_module is None:
        return {"response": "", "audio_url": None, "error": "scenarios modülü yüklenemedi."}

    scenario = _scenarios_module.get_scenario(req.scenario_id)
    if not scenario:
        return {"response": "", "audio_url": None, "error": f"Senaryo bulunamadı: {req.scenario_id}"}

    logger.info(
        f"[Scenario={req.scenario_id}] [Participant={req.participant_id or 'single'}] "
        f"Mesaj: {req.message[:60]}..."
    )

    # 1) AI cevabı üret (ConversationManager varsa Gemini'yi kullan)
    ai_response = None
    if conversation_manager_scenario is not None:
        try:
            # Senaryo prompt'unu geçici olarak persona yap
            original_persona = conversation_manager_scenario.active_persona
            conversation_manager_scenario.active_persona = scenario["system_prompt"]
            try:
                ai_response = conversation_manager_scenario.get_response(req.message)
            finally:
                # Persona'yı her durumda eski haline getir (yan etki bırakma)
                conversation_manager_scenario.active_persona = original_persona
        except Exception as e:
            logger.error(f"Gemini çağrısı başarısız: {e}")
            ai_response = None

    # 2) Fallback: Gemini yoksa veya hata olduysa
    if not ai_response:
        ai_response = f"({scenario['label']}) Şunu söylediniz: {req.message}"

    # 3) Ses sentezi
    if not voice_cloner:
        return {
            "response": ai_response,
            "audio_url": None,
            "scenario_id": req.scenario_id,
            "participant_id": req.participant_id,
            "error": "Voice cloner aktif değil.",
        }

    try:
        wav_filename = await voice_cloner.clone_voice(
            target_text=ai_response,
            persona=req.persona,
            rate=req.rate,
            pitch=req.pitch,
            emotion=req.emotion,
        )
        if wav_filename:
            audio_url = f"http://localhost:{os.getenv('GPU_WORKER_PORT', 8001)}/outputs/{wav_filename}"
            return {
                "response": ai_response,
                "audio_url": audio_url,
                "scenario_id": req.scenario_id,
                "participant_id": req.participant_id,
            }
        return {
            "response": ai_response,
            "audio_url": None,
            "scenario_id": req.scenario_id,
            "participant_id": req.participant_id,
            "error": "Ses sentezlenemedi.",
        }
    except Exception as e:
        logger.error(f"chat_scenario ses hatası: {e}")
        return {
            "response": ai_response,
            "audio_url": None,
            "scenario_id": req.scenario_id,
            "participant_id": req.participant_id,
            "error": str(e),
        }

# ===========================================================================
# / Meeting Simulation Endpoints
# ===========================================================================


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("GPU_WORKER_PORT", 8001))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)
