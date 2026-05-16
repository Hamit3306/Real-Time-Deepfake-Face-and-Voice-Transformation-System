"""
AWS Signaling Server (WebSocket Relay) - Ngrok'suz Doğrudan Bağlantı
=====================================================================
AWS t2.micro üzerinde çalışır. Tek görevi:
1. React frontend'den gelen WebRTC "offer" (SDP) paketlerini almak.
2. Bu teklifi doğrudan kendisine bağlı olan (Monster PC) "GPU Worker" WebSocket'ine iletmek.
3. GPU'dan dönen "answer" paketini tekrar React'a göndermek.

Kurulum:
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import json
import logging
import httpx
from contextlib import asynccontextmanager
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Sistemin durumu
connected_clients: Dict[str, WebSocket] = {}
gpu_worker_socket: Optional[WebSocket] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Signaling Server başlatılıyor (Ngrok-Free Mode) ===")
    yield
    logger.info("=== Signaling Server kapatılıyor ===")


app = FastAPI(
    title="DeepFake Signaling Server",
    description="WebRTC P2P bağlantısı için ngrok'suz WebSocket relay sunucusu.",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {
        "status": "ok", 
        "worker_connected": gpu_worker_socket is not None,
        "clients_connected": len(connected_clients)
    }

# ---------------------------------------------------------------------------
# GPU Worker Bağlantısı (Monster PC buraya bağlanacak)
# ---------------------------------------------------------------------------
@app.websocket("/ws/worker")
async def worker_endpoint(websocket: WebSocket):
    global gpu_worker_socket
    await websocket.accept()
    
    # Sadece 1 worker aktif olabilir (basitlik için)
    if gpu_worker_socket is not None:
        logger.warning("Eski worker bağlantısı kapatılıyor...")
        try:
            await gpu_worker_socket.close()
        except: pass
        
    gpu_worker_socket = websocket
    logger.info("🟢 GPU Worker bağlandı! Sistem hazır.")

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            client_id = message.get("client_id")
            
            # GPU'dan gelen cevapları (answer/ice) doğru istemciye yönlendir
            if client_id and client_id in connected_clients:
                client_ws = connected_clients[client_id]
                await client_ws.send_text(raw)
                logger.info(f"[Worker -> İstemci {client_id}] Mesaj iletildi: {message.get('type')}")
            else:
                logger.warning(f"Bilinmeyen veya kopmuş istemciye (ID: {client_id}) Worker mesajı geldi.")
    except WebSocketDisconnect:
        logger.info("🔴 GPU Worker bağlantıyı kesti!")
    except Exception as e:
        logger.error(f"Worker hatası: {e}")
    finally:
        gpu_worker_socket = None


# ---------------------------------------------------------------------------
# İstemci (React) Bağlantısı
# ---------------------------------------------------------------------------
@app.websocket("/ws/signal/{client_id}")
async def signaling_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    connected_clients[client_id] = websocket
    logger.info(f"🔵 İstemci bağlandı: {client_id}  (Toplam: {len(connected_clients)})")

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            msg_type = message.get("type")

            logger.info(f"[{client_id}] Mesaj alındı: type={msg_type}")

            # React'tan gelen offer veya ice_candidate'i Worker'a forward et
            if msg_type == "offer":
                message["client_id"] = client_id
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.post("http://127.0.0.1:8001/webrtc/offer", json=message, timeout=15.0)
                        if resp.status_code == 200:
                            answer_data = resp.json()
                            await websocket.send_text(json.dumps(answer_data))
                            logger.info(f"[{client_id} <- Worker] HTTP Answer React'e iletildi.")
                        else:
                            print(f"Worker'dan hata döndü: {resp.text}")
                except Exception as e:
                    print(f"Worker'a ulaşılamadı: {e}")
                    await websocket.send_text(json.dumps({"type": "error", "message": f"Worker'a ulaşılamadı: {e}"}))

            elif msg_type == "ice_candidate":
                message["client_id"] = client_id
                try:
                    async with httpx.AsyncClient() as client:
                        await client.post("http://127.0.0.1:8001/webrtc/ice", json=message, timeout=5.0)
                except Exception as e:
                    print(f"Worker ICE endpoint'ine ulaşılamadı: {e}")

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            else:
                logger.warning(f"[{client_id}] Bilinmeyen mesaj tipi: {msg_type}")

    except WebSocketDisconnect:
        logger.info(f"İstemci bağlantıyı kesti: {client_id}")
    except Exception as e:
        logger.error(f"[{client_id}] Beklenmeyen hata: {e}")
    finally:
        connected_clients.pop(client_id, None)
        logger.info(f"İstemci kaldırıldı: {client_id}  (Kalan: {len(connected_clients)})")
