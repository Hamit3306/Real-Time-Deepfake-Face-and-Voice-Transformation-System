import os
import json
import uuid
from datetime import datetime
from modules.conversation import ConversationManager
from modules.voice_cloning import VoiceCloner

class MeetingParticipant:
    def __init__(self, name, p_type='human', face_model='face1', voice_model='voice1', persona='formal'):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = p_type  # 'human' or 'ai'
        self.face_model = face_model
        self.voice_model = voice_model
        self.persona = persona

class MeetingManager:
    def __init__(self):
        self.meetings = {}
        self.log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "outputs")
        os.makedirs(self.log_dir, exist_ok=True)
        # Shared instances for AI processing
        self.conversation_manager = ConversationManager()
        self.voice_cloner = VoiceCloner()

    def create_meeting(self, title, scenario):
        meeting_id = str(uuid.uuid4())
        self.meetings[meeting_id] = {
            "title": title,
            "scenario": scenario,
            "participants": {},
            "transcript": [],
            "created_at": datetime.now().isoformat(),
            "status": "ongoing"
        }
        self._log_event(meeting_id, "MEETING_CREATED", f"Scenario: {scenario}")
        return meeting_id

    def add_human_participant(self, meeting_id, name, face_model, voice_model):
        if meeting_id not in self.meetings: return None
        p = MeetingParticipant(name, 'human', face_model, voice_model)
        self.meetings[meeting_id]["participants"][p.id] = p
        self._log_event(meeting_id, "PARTICIPANT_ADDED", f"Human: {name}")
        return p.id

    def add_ai_participant(self, meeting_id, name, face_model, voice_model, persona):
        if meeting_id not in self.meetings: return None
        p = MeetingParticipant(name, 'ai', face_model, voice_model, persona)
        self.meetings[meeting_id]["participants"][p.id] = p
        self._log_event(meeting_id, "PARTICIPANT_ADDED", f"AI: {name} (Persona: {persona})")
        return p.id

    def human_speak(self, meeting_id, participant_id, text):
        if meeting_id not in self.meetings: return None
        p = self.meetings[meeting_id]["participants"].get(participant_id)
        if not p or p.type != 'human': return None
        
        self.meetings[meeting_id]["transcript"].append({
            "timestamp": datetime.now().isoformat(),
            "speaker": p.name,
            "text": text
        })
        self._log_event(meeting_id, "HUMAN_SPEAK", text)
        return True

    def ai_speak(self, meeting_id, participant_id, prompt, emotion='neutral'):
        """ FR 2.9: Mix human prompts and let AI participant generate dialogue and voice """
        if meeting_id not in self.meetings: return None
        p = self.meetings[meeting_id]["participants"].get(participant_id)
        if not p or p.type != 'ai': return None
        
        # Determine context by taking last few lines of transcript
        context = " ".join([f"{t['speaker']}: {t['text']}" for t in self.meetings[meeting_id]["transcript"][-3:]])
        
        self.conversation_manager.set_persona(p.persona)
        full_prompt = f"Meeting Scenario: {self.meetings[meeting_id]['scenario']}.\nPrior context: {context}\nNow you must naturally respond to this prompt: {prompt}"
        
        ai_response = self.conversation_manager.get_response(full_prompt)
        
        # Generate voice
        self.voice_cloner.select_model(p.voice_model)
        audio_file = self.voice_cloner.clone_voice(ai_response, emotion=emotion)
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "speaker": p.name,
            "text": ai_response,
            "audio_file": audio_file
        }
        self.meetings[meeting_id]["transcript"].append(entry)
        self._log_event(meeting_id, "AI_SPEAK", ai_response)
        
        return entry

    def get_meeting(self, meeting_id):
        return self.meetings.get(meeting_id)
        
    def get_all_meetings(self):
        return [{"id": k, "title": v["title"], "status": v["status"]} for k,v in self.meetings.items()]

    def end_meeting(self, meeting_id):
        if meeting_id in self.meetings:
            self.meetings[meeting_id]["status"] = "ended"
            self.meetings[meeting_id]["ended_at"] = datetime.now().isoformat()
            self._log_event(meeting_id, "MEETING_ENDED", "Ended")
            return True
        return False

    def _log_event(self, meeting_id, event_type, details):
        """ FR 3.5: All events logged to meeting_events.log """
        log_file = os.path.join(self.log_dir, "meeting_events.log")
        entry = {
            "timestamp": datetime.now().isoformat(),
            "meeting_id": meeting_id,
            "event": event_type,
            "details": details
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
