# transcription.py

import whisper
import os
import uuid

class TranscriptionService:

    def __init__(self, model_size="base"):
        print("🔄 Loading Whisper model...")
        self.model = whisper.load_model(model_size)
        print("✅ Whisper ready.")

    def transcribe(self, audio_path: str):
        if not os.path.exists(audio_path):
            raise FileNotFoundError("Audio file not found")

        result = self.model.transcribe(audio_path)

        transcript_data = {
            "full_text": result["text"],
            "language": result.get("language"),
            "segments": result.get("segments"),
        }

        return transcript_data

    def save_transcript(self, transcript_text: str):
        filename = f"transcript_{uuid.uuid4().hex}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(transcript_text)
        return filename