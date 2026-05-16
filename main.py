"""
Monster PC - GPU Worker (v2 - Integrated & Optimized)
=====================================================
Kendi kendine yeten, asenkron ve AWS bulut ile doğrudan entegre olan ana sistem.
VoiceCloner, FaceSwapper ve ConversationManager modüllerini ayağa kaldırır.

Ngrok kullanmaz! AWS Signaling (34.224.38.75:8000) sunucusuna *doğrudan* 
WebSocket Client olarak bağlanarak kendi portlarını veya tünellerini yönetmesine 
gerek kalmadan, anında WebRTC Offer/Answer alışverişi yapar.

Çalıştırmak için:
    python main.py
"""

import asyncio
import json
import logging
import os
import weakref
from typing import Dict

import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaRelay

# v2 Optimizasyonlu FaceSwap Track'ini gpu_worker altından al
try:
    from gpu_worker.rtc_worker import DeepFakeVideoTrack
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from gpu_worker.rtc_worker import DeepFakeVideoTrack

from modules.voice_cloning import VoiceCloner
from modules.conversation import ConversationManager

# AWS Signaling Server Host Bilgisi (Yerel Test İçin Localhost)
AWS_SIGNALING_WS_URL = "ws://localhost:8000/ws/worker"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MonsterWorker")

# Global aiortc relay (track çoklaması için idare eder)
relay = MediaRelay()
peer_connections: Dict[str, RTCPeerConnection] = {}

class SubsystemManager:
    """Modüllerin bir kerede yüklenip havuzda tutulduğu yer."""
    def __init__(self):
        logger.info("=========================================")
        logger.info("Monster GPU Worker Başlatılıyor...")
        logger.info("=========================================")
        
        # Sadece import ediyoruz. Asıl başlatmalar async event loop içine alınabilir veya senkron başlatılabilir.
        # FaceSwapper zaten DeepFakeVideoTrack çağrıldığında get_face_swapper() ile GPU üzerinde init olacak.
        
        logger.info("[1/3] ConversationManager başlatılıyor...")
        self.conv = ConversationManager()
        
        logger.info("[2/3] VoiceCloner başlatılıyor...")
        self.voice = VoiceCloner()
        
        logger.info("[3/3] FaceSwapper hazır kıta bekliyor (aiortc track gelince tetiklenecek).")
        logger.info("=========================================")

subsystems = SubsystemManager()

async def handle_webrtc_offer(ws: websockets.WebSocketClientProtocol, client_id: str, sdp: str, face_model: str):
    """Buluttan gelen P2P (Peer-to-Peer) bağlantı talebini kabul et ve cevapla."""
    logger.info(f"[{client_id}] Yeni WebRTC Offer alındı. Face Model: {face_model}")

    if client_id in peer_connections:
        await peer_connections[client_id].close()

    pc = RTCPeerConnection()
    peer_connections[client_id] = pc

    @pc.on("icecandidate")
    def on_ice_candidate(candidate):
        if candidate:
            asyncio.ensure_future(ws.send(json.dumps({
                "type": "ice_candidate",
                "client_id": client_id,
                "candidate": {
                    "candidate": candidate.candidate,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex,
                }
            })))

    @pc.on("connectionstatechange")
    async def on_connection_state_change():
        logger.info(f"[{client_id}] P2P Bağlantı durumu: {pc.connectionState}")
        if pc.connectionState in ("failed", "closed"):
            await pc.close()
            peer_connections.pop(client_id, None)

    @pc.on("track")
    def on_track(track):
        logger.info(f"[{client_id}] Medya Akışı Geldi: {track.kind}")
        
        if track.kind == "video":
            # Optimizasyonlu (Face BBox Caching ve Adaptive Skip) GPU track'imizi araya sokuyoruz
            deep_fake_track = DeepFakeVideoTrack(
                relay.subscribe(track),
                face_model=face_model,
            )
            pc.addTrack(deep_fake_track)
            logger.info(f"[{client_id}] DeepFakeVideoTrack GPU hattına bağlandı.")
        elif track.kind == "audio":
            # Gelecekte VoiceCloneModule ile sesi de manipüle edip geri döneceğiz
            # Şimdilik yankıyı önlemek adına pass-through yapmıyoruz
            pass

    # SDP Offer'ı RTCSessionDescription olarak al
    offer = RTCSessionDescription(sdp=sdp, type="offer")
    await pc.setRemoteDescription(offer)

    # İşleyiciyi ayağa kaldırıp SDP Answer üret
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # Signaling (AWS) üzerinden React Client'a Answer dön
    await ws.send(json.dumps({
        "type": "answer",
        "client_id": client_id,
        "sdp": pc.localDescription.sdp
    }))
    logger.info(f"[{client_id}] SDP Answer, AWS üzerinden istemciye iletildi.")

async def handle_ice_candidate(client_id: str, candidate_data: dict):
    if client_id not in peer_connections:
        return
        
    pc = peer_connections[client_id]
    try:
        candidate = RTCIceCandidate(
            component=candidate_data.get("component", 1),
            foundation=candidate_data.get("foundation", ""),
            ip=candidate_data.get("ip", ""),
            port=int(candidate_data.get("port", 0)),
            priority=int(candidate_data.get("priority", 0)),
            protocol=candidate_data.get("protocol", "udp"),
            type=candidate_data.get("type", "host"),
            sdpMid=candidate_data.get("sdpMid"),
            sdpMLineIndex=candidate_data.get("sdpMLineIndex"),
        )
        await pc.addIceCandidate(candidate)
    except Exception as e:
        logger.warning(f"[{client_id}] ICE işleme hatası: {e}")

async def run_worker():
    """AWS ile WebSocket üzerinden sonsuz asenkron el sıkışma (signaling) döngüsü."""
    logger.info(f"AWS Sunucusuna ({AWS_SIGNALING_WS_URL}) bağlanılıyor...")
    
    while True:
        try:
            async with websockets.connect(AWS_SIGNALING_WS_URL) as ws:
                logger.info("✅ AWS Sunucusu ile doğrudan bağlantı kuruldu. Ngrok'suz mod aktif.")
                logger.info("Buluttan gelecek yüz değiştirme (WebRTC) talepleri bekleniyor...")
                
                async for message in ws:
                    data = json.loads(message)
                    msg_type = data.get("type")
                    client_id = data.get("client_id")
                    
                    if not client_id:
                        continue
                        
                    if msg_type == "offer":
                        face_model = data.get("face_model", "face1")
                        sdp = data.get("sdp")
                        # Asenkron çalıştır ki ana WS döngüsü bloklanmasın
                        asyncio.create_task(handle_webrtc_offer(ws, client_id, sdp, face_model))
                        
                    elif msg_type == "ice_candidate":
                        candidate = data.get("candidate")
                        if candidate:
                            asyncio.create_task(handle_ice_candidate(client_id, candidate))

        except websockets.exceptions.ConnectionClosed:
            logger.warning("AWS Sunucusu ile bağlantı koptu. 3 saniye sonra yeniden denenecek...")
        except Exception as e:
            logger.error(f"Bağlantı Hatası: {e}. 3 saniye sonra yeniden denenecek...")
            
        await asyncio.sleep(3)

if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Sistem kullanıcı tarafından kapatıldı.")
