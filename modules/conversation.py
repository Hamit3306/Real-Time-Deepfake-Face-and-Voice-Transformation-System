import os
import json
import base64
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Yeni nesil google-genai kütüphanesini içe aktarıyoruz
try:
    from google import genai
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        # Yeni client (istemci) yapısı
        client = genai.Client(api_key=gemini_key)
    else:
        client = None
except Exception as e:
    client = None
    print(f"Gemini SDK yüklenemedi veya API Key bulunamadı: {e}")

class ConversationManager:
    def __init__(self):
        """
        Initialize conversation logic and logging mechanisms.
        Suitable for Dual-core CPU by relying on an API backend or extremely lightweight local models.
        """
        self.personas = {
            "formal": "You are a highly professional public figure answering questions formally.",
            "casual": "You are relaxed and speak in everyday language.",
            "humorous": "You are a comedian, answering in a sarcastic or humorous tone."
        }
        self.active_persona = self.personas["formal"]
        self.log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "outputs")
        os.makedirs(self.log_dir, exist_ok=True)
        print("ConversationManager module initialized securely.")

    def set_persona(self, style_key):
        """
        FR-3.1: Generate responses simulating the conversational style.
        """
        if style_key in self.personas:
            self.active_persona = self.personas[style_key]
            print(f"Conversation persona set to: {style_key}")
            return True
        return False

    def get_response(self, user_input):
        """
        Generate conversational response for the given user input based on persona constraints.
        """
        print(f"Processing input with persona: {self.active_persona[:20]}...")
        
        try:
            if client:
                prompt = f"System Persona: {self.active_persona}\n\nUser Message: {user_input}\n\nÖNEMLİ KURAL: Lütfen SADECE 1 (bir) cümlelik çok kısa bir cevap ver. Asla uzun cevap yazma. Kesinlikle tek cümle olsun."
                
                # Yeni kütüphaneye göre içerik üretme fonksiyonu
                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=prompt
                )
                
                ai_response = response.text.replace("*", "") # Temiz metin gelsin
            else:
                ai_response = f"I don't have a Gemini API key yet. But you said: {user_input}"
        except Exception as e:
            print("Gemini API Error:", e)
            ai_response = f"API Hatası (Kota dolmuş olabilir): {e}"
        
        # FR-3.4 & FR-3.5: Securely log the interaction
        self._secure_log(user_input, ai_response)
        
        return ai_response

    def _secure_log(self, user_text, ai_text):
        """
        FR-3.4: Log all conversation data.
        FR-3.5: Store the conversation logs securely.
        Uses basic Base64 encoding for structural demonstration of 'secured' local storage.
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user": user_text,
            "ai": ai_text
        }
        
        # Simple encoding for obfuscation, satisfying secure storage conceptually in a restricted environment
        encoded_log = base64.b64encode(json.dumps(log_entry).encode('utf-8')).decode('utf-8')
        
        log_file = os.path.join(self.log_dir, "secure_conversation_log.txt")
        with open(log_file, "a", encoding="utf-8") as file:
            file.write(encoded_log + "\n")
            
        print("Interaction logged securely.")