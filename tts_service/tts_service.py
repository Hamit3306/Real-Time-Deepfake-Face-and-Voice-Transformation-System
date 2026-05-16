import os
import torch

# PyTorch 2.6+ güvenlik kısıtlamasını aşmak için monkey-patch
original_load = torch.load
def patched_load(*args, **kwargs):
    if 'weights_only' not in kwargs:
        kwargs['weights_only'] = False
    return original_load(*args, **kwargs)
torch.load = patched_load

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

from TTS.api import TTS

tts_model = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global tts_model
    print("=== TTS Microservice Başlatılıyor ===")
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[{device.upper()}] XTTSv2 Modeli VRAM'e yükleniyor... Bu işlem biraz zaman alabilir.")
    
    try:
        tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        print("✅ XTTSv2 Modeli başarıyla yüklendi!")
    except Exception as e:
        print(f"❌ Model yükleme hatası: {e}")
        
    yield
    
    print("=== TTS Microservice Kapatılıyor ===")

app = FastAPI(
    title="XTTSv2 Microservice",
    description="Python 3.10 İzole Edilmiş Ses Klonlama API'si",
    version="1.0.0",
    lifespan=lifespan
)

class AudioRequest(BaseModel):
    text: str
    reference_audio_path: str
    output_path: str
    language: str = "tr"

@app.post("/generate-audio/")
async def generate_audio(req: AudioRequest):
    if not tts_model:
        raise HTTPException(status_code=500, detail="TTS Modeli başlatılamadı.")
        
    if not os.path.exists(req.reference_audio_path):
        raise HTTPException(status_code=400, detail=f"Referans ses dosyası bulunamadı: {req.reference_audio_path}")
        
    try:
        os.makedirs(os.path.dirname(req.output_path), exist_ok=True)
        
        print(f"Ses Sentezleniyor (Chunking Aktif): '{req.text}' (Referans: {req.reference_audio_path})")
        
        import re
        import soundfile as sf
        import numpy as np
        
        # Metni cümlelere böl (nokta, ünlem, soru işareti vb.)
        sentences = re.split(r'(?<=[.!?]) +', req.text.strip())
        
        all_audio = []
        sample_rate = 24000  # XTTSv2 default sample rate
        
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            # Her cümleyi ayrı ayrı sentezle
            audio_chunk = tts_model.tts(
                text=sentence.strip(),
                speaker_wav=req.reference_audio_path,
                language=req.language
            )
            all_audio.extend(audio_chunk)
            # Cümleler arası kısa bir boşluk ekle (0.2 saniye)
            all_audio.extend([0.0] * int(sample_rate * 0.2))
            
        # Toplu sesi kaydet
        sf.write(req.output_path, np.array(all_audio), sample_rate)
        
        print(f"Ses Sentezleme Tamamlandı: {req.output_path}")
        return {"status": "success", "output_path": req.output_path}
    except Exception as e:
        print(f"Sentezleme Hatası: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
