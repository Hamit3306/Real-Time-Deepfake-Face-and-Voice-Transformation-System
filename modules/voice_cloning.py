import os
import httpx
from datetime import datetime

class VoiceCloner:
    def __init__(self):
        """
        Microservice client for XTTSv2 Voice Cloning.
        Relies on the tts_service running on localhost:8002.
        """
        self.tts_service_url = "http://127.0.0.1:8002/generate-audio/"
        
        # Referans ses dosyalarının bulunacağı dizin
        self.reference_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tts_service", "references")
        os.makedirs(self.reference_dir, exist_ok=True)
        print("VoiceCloner (Microservice Client) initialized with dynamic voices.")

    async def clone_voice(self, target_text, persona="kayit_1", rate=1.0, pitch=0, emotion='neutral'):
        """
        Sends an async HTTP POST request to the local TTS microservice.
        """
        # Duygu durumuna göre metni ayarla
        if emotion == 'happy':
            target_text = target_text.rstrip('.!?') + "!!!"
        elif emotion == 'serious':
            target_text = target_text.rstrip('.!?') + "."
            
        print(f"Requesting voice clone from Microservice: '{target_text}' | Persona: {persona} | Rate: {rate} | Pitch: {pitch} | Emotion: {emotion}")
        
        # Dinamik olarak persona adına göre (.wav) dosyasını bul (Örn: kayit_1.wav)
        reference_path = os.path.join(self.reference_dir, f"{persona}.wav")
        
        if not os.path.exists(reference_path):
            print(f"Uyarı: {reference_path} bulunamadı! İşlem iptal ediliyor.")
            return None

        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "outputs")
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_wav = f"voice_{timestamp}.wav"
        final_path = os.path.join(output_dir, final_wav)
        
        payload = {
            "text": target_text,
            "reference_audio_path": reference_path,
            "output_path": final_path,
            "language": "tr" # Desteklenen dil
        }
        
        try:
            # XTTSv2 GPU'da saniyeler sürebilir, uzun metinlerde zaman aşımını engellemek için timeout artırıldı
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(self.tts_service_url, json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    saved_path = data['output_path']
                    print(f"Microservice Success: Audio saved at {saved_path}")
                    
                    # --- Post-Processing: Konuşma Hızı (Rate) & Ses Tonu (Pitch) ---
                    if rate != 1.0 or pitch != 0:
                        print(f"Applying filters -> Rate: {rate}x, Pitch: {pitch} st")
                        try:
                            import imageio_ffmpeg
                            import subprocess
                            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                            
                            sr = 24000
                            pitch_ratio = 2 ** (pitch / 12.0)
                            new_sr = int(sr * pitch_ratio)
                            tempo = rate / pitch_ratio
                            
                            atempo_filters = []
                            t = tempo
                            while t < 0.5:
                                atempo_filters.append("atempo=0.5")
                                t /= 0.5
                            while t > 100.0:
                                atempo_filters.append("atempo=100.0")
                                t /= 100.0
                            atempo_filters.append(f"atempo={t}")
                            
                            atempo_str = ",".join(atempo_filters)
                            af = f"asetrate={new_sr},{atempo_str},aresample=24000"
                            
                            temp_path = saved_path.replace(".wav", "_temp.wav")
                            os.rename(saved_path, temp_path)
                            
                            cmd = [
                                ffmpeg_exe, "-y", "-i", temp_path,
                                "-filter:a", af,
                                saved_path
                            ]
                            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                            print("Post-processing applied successfully.")
                        except Exception as ex:
                            print(f"Failed to apply rate/pitch: {ex}")

                    return final_wav
                else:
                    print(f"Microservice Error: {response.text}")
                    return None
        except Exception as e:
            print(f"Microservice Connection Error (Is it running on 8002?): {e}")
            return None
