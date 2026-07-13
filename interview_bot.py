import asyncio
import edge_tts
import simpleaudio as sa
from pydub import AudioSegment
import uuid
import time
import webrtcvad
import sounddevice as sd
import numpy as np
from pymongo import MongoClient
import random
import os
import whisper
from gtts import gTTS
import datetime
from supabase import create_client, Client

from dotenv import load_dotenv


# Set COM threading model BEFORE any COM-related imports
os.environ["COINIT_APARTMENT"] = "1"  # Use apartment threading

vad = webrtcvad.Vad(1)  

VOICE = "en-US-JennyNeural"
sample_rate = 16000
frame_duration_ms = 20
frame_size = int(sample_rate * frame_duration_ms / 1000)

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def save_interview_to_db(candidate_name, questions_asked):
    """
    Saves candidate's interview questions to MongoDB.
    
    """
    client = MongoClient(MONGO_URI)
    db = client.empowhr
    col = db.interviews

    record = {
        "candidate_name": candidate_name,
        "questions": questions_asked,
        "timestamp": datetime.datetime.utcnow()
    }

    col.insert_one(record)
    print(f"[DB] Saved interview for {candidate_name}")


async def speak(text):
    filename = f"tts_{uuid.uuid4().hex}.mp3"

    try:
                tts = gTTS(text=text, lang="en")
                tts.save(filename)
    except Exception as e2:
                print("[TTS ERROR] gTTS also failed.")
                print("Reason:", e2)
                return  # Avoid crashing the interview

    # ---------- PLAY AUDIO ----------
    try:
        audio = AudioSegment.from_mp3(filename)
        play_obj = sa.play_buffer(
            
            audio.raw_data,
            num_channels=audio.channels,
            bytes_per_sample=audio.sample_width,
            sample_rate=audio.frame_rate
           

        )
        play_obj.wait_done()
        print(1)
    except Exception as e:
        print("[AUDIO ERROR] Failed to play audio:", e)


def wait_until_silent(max_wait=9):
    print("🎤 Waiting for candidate...")

    print("🎤 Detecting when candidate STARTS speaking...")
    consecutive_speech = 0
    SPEECH_START_THRESHOLD = 4  # ~120ms real speech
    start_timer = time.time()

    while True:
        audio = sd.rec(frame_size, samplerate=sample_rate, channels=1, dtype='int16')
        sd.wait()

        if vad.is_speech(audio.tobytes(), sample_rate):
            consecutive_speech += 1
        else:
            consecutive_speech = 0

        if consecutive_speech >= SPEECH_START_THRESHOLD:
            print("🗣 Candidate STARTED speaking!")
            break

        # --- Timeout: candidate never spoke ---
        if time.time() - start_timer > max_wait:
            print("⏳ Timeout: Candidate did not speak. Moving on.\n")
            return

    # --- Detect candidate STOPPED speaking ---
    print("🎧 Listening until candidate finishes...")

    consecutive_silence = 0
    SILENCE_THRESHOLD = 10 

    while True:
        audio = sd.rec(frame_size, samplerate=sample_rate, channels=1, dtype='int16')
        sd.wait()

        if not vad.is_speech(audio.tobytes(), sample_rate):
            consecutive_silence += 1
        else:
            consecutive_silence = 0

        if consecutive_silence >= SILENCE_THRESHOLD:
            print("🟢 Candidate FINISHED speaking.\n")
            break

def participant_left(max_silence=30):
    """
    Returns True if no audio detected for 30 seconds.
    Means participant likely LEFT the Zoom meeting.
    """
    print("🔍 Monitoring if participant leaves...")

    silence_start = time.time()

    while True:
        audio = sd.rec(frame_size, samplerate=sample_rate, channels=1, dtype='int16')
        sd.wait()

        is_speech = vad.is_speech(audio.tobytes(), sample_rate)

        if is_speech:
            return False  # participant still here

        # No speech: check if exceeded limit
        if time.time() - silence_start > max_silence:
            print("⚠ No audio from participant for 30 seconds — participant might have left.")
            return True

def wait_for_return(timeout_minutes=5):
    """
    Waits up to 5 minutes for participant to return.
    If returns → return True
    If not → return False
    """

    print(f"⏳ Waiting up to {timeout_minutes} minutes for participant to return...")

    timeout_seconds = timeout_minutes * 60
    start = time.time()

    while True:
        audio = sd.rec(frame_size, samplerate=sample_rate, channels=1, dtype='int16')
        sd.wait()

        if vad.is_speech(audio.tobytes(), sample_rate):
            print("🎉 Participant RETURNED! Resuming interview.\n")
            return True

        if time.time() - start > timeout_seconds:
            print("❌ Participant did NOT return within 5 minutes.")
            return False

        time.sleep(0.3)

def end_meeting_for_all():
    print("[BOT] Attempting to end meeting for all...")
    
    try:
        # Import pywinauto and pyautogui locally to avoid COM conflicts
        
        from pywinauto.application import Application
        import pyautogui
        
        # Initialize COM for this thread
        import comtypes
        comtypes.CoInitialize()
        
        try:
            # Connect to the Zoom meeting window
            app = Application(backend="uia").connect(title_re=".*Zoom Meeting.*|.*Meeting.*")
            win = app.top_window()

            print("[BOT] Meeting window found.")

            # Click the "End" button (bottom-right usually)
            end_btn = win.child_window(title="End", control_type="Button")
            print("[BOT] Clicking End button...")
            end_btn.click_input()
            time.sleep(10)

            # Then select "End Meeting for All"
            end_all_btn = win.child_window(title="End Meeting for All", control_type="Button")
            print("[BOT] Clicking 'End Meeting for All'...")
            end_all_btn.click_input()

            print("🛑 Meeting ended for all participants.")
        finally:
            # Uninitialize COM
            comtypes.CoUninitialize()
            
    except Exception as e:
        print("[ERROR] Could not end meeting automatically:", e)
        print("Trying fallback method (Alt+Q)...")
        
        # fallback using hotkeys
        try:
            import pyautogui
            pyautogui.hotkey("alt", "q")
            time.sleep(1)
            pyautogui.press("enter")
        except:
            print("Fallback also failed. Please end meeting manually.")


def get_random_questions_per_category():
    client = MongoClient("MONGO_URI")
    db = client.EmpowHR_db1
    col = db.interview_questions

    categories = {
        "introduction": 2,
        "experience": 2,
        "skills": 2,
        "availability": 2,
        "culture": 2,
        "communication": 2,   
        "iq-pattern": 2,
        "iq-logic": 2,
        "iq-analytical": 2,
        "iq-math": 2,
        "SE-introduction": 2,
        "SE-technical": 2,
        "SE-language": 2,
        "SE-problem-solving": 2,
        "SE-behavioral": 2,
        "SE-communication": 2,
        "closing": 1   
    }

    final_questions = []

    for cat, count in categories.items():
        docs = list(col.find({"category": cat}))

        if len(docs) == 0:
            continue

        selected = random.sample(docs, min(count, len(docs)))
        final_questions.extend([q["text"] for q in selected])

    return final_questions

model = whisper.load_model("tiny")

async def wait_for_candidate_signal():
    print("\n🎤 Candidate, say 'next' when ready for the next question...")

    while True:
        fs = 16000
        duration = 2  # listen 2 seconds
        audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32')
        sd.wait()

        # convert to numpy
        audio_np = audio.flatten().astype(np.float32)

        # transcribe speech
        try:
            result = model.transcribe(audio_np, fp16=False, language="en")
            text = result["text"].lower().strip()
        except:
            text = ""

        if text:
            print("🗣 Candidate said:", text)

        if "next" in text:
            print("➡ Candidate said NEXT — continuing...\n")
            return

def upload_recording_to_supabase(candidate_name, local_file_path):
    filename = f"{candidate_name}.wav"  # final name in Supabase
    
    try:
        with open(local_file_path, "rb") as f:
            supabase.storage.from_(SUPABASE_BUCKET).upload(
                path=filename,
                file=f,
                file_options={"content-type": "audio/wav"}
            )

        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"
        print("📤 Uploaded recording:", public_url)
        return public_url

    except Exception as e:
        print("❌ Supabase upload failed:", e)
        return None

def save_interview_to_mongo(candidate_name, questions, recording_url):
    doc = {
        "candidate_name": candidate_name,
        "questions": questions,
        "recording_url": recording_url,
        "timestamp": datetime.datetime.utcnow(),
    }
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["EmpowHR_db1"]  

    result = db.interviews.insert_one(doc)
    print(f"📁 Saved interview for {candidate_name} (ID: {result.inserted_id})")
    return result.inserted_id


def detect_speech(timeout=30):
    print("🎤 Listening for candidate...")

    start_time = time.time()
    consecutive_speech = 0
    SPEECH_THRESHOLD = 3  # 3 frames = ~60 ms

    def callback(indata, frames, time_info, status):
        nonlocal consecutive_speech

        audio_bytes = indata.tobytes()
        if vad.is_speech(audio_bytes, sample_rate):
            consecutive_speech += 1
        else:
            consecutive_speech = 0

        if consecutive_speech >= SPEECH_THRESHOLD:
            raise sd.CallbackStop  # stop stream once speech detected

    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype='int16',
        blocksize=frame_size,
        callback=callback
    ):
        while time.time() - start_time < timeout:
            sd.sleep(50)  # keep loop alive

    print("🗣 Candidate started speaking!")

def detect_end_of_speech(max_silence_sec=0.8):
    print("🎧 Listening for candidate to finish speaking...")

    silence_ms = 0
    frame_duration_ms = 20
    max_silence_frames = int(max_silence_sec * 1000 / frame_duration_ms)

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16', blocksize=frame_size) as stream:
        while True:
            audio = stream.read(frame_size)[0]
            is_speech = vad.is_speech(audio.tobytes(), sample_rate)

            if not is_speech:
                silence_ms += 1
            else:
                silence_ms = 0  # reset when speech detected

            if silence_ms >= max_silence_frames:
                break

    print("🟢 Candidate finished speaking.")


async def start_interview():
    intro_question = "Welcome to the interview. What's your name? Please introduce yourself."
   
    candidate_name = "ali"
    questions_asked =   [intro_question] + get_random_questions_per_category()
    print(questions_asked)
    # 3️⃣ Ask questions
    for q in questions_asked:

        await wait_for_candidate_signal() 
        wait_until_silent()
        print(f"[BOT] {q}")
        await speak(q)
        detect_speech(timeout=5)
        detect_end_of_speech(max_silence_sec=5)
        wait_until_silent()  
    local_audio_file = "{candidate_name}_interview.mp4"       
    recording_url = upload_recording_to_supabase(candidate_name, local_audio_file)
    # 4️⃣ Save to MongoDB
    save_interview_to_mongo({candidate_name}, questions_asked,recording_url)

    print("[BOT] Interview complete!")


# Run the interview
if __name__ == "__main__":
    asyncio.run(start_interview())



















# import wave
# import speech_recognition as sr

# def record_until_silence(max_duration=8):
#     """
#     Records audio until silence is detected using your existing VAD config.
#     Returns recorded audio as a NumPy array.
#     """
#     sample_rate = 16000
#     buffer_duration = 30  # ms
#     chunk_size = int(sample_rate * buffer_duration / 1000)

#     print("[BOT] Listening...")

#     frames = []
#     silence_count = 0
#     silence_threshold = 15  # number of consecutive silent chunks → stop

#     stream = sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16')
#     stream.start()

#     start_time = time.time()

#     while True:
#         data, _ = stream.read(chunk_size)
#         audio = data.flatten().tobytes()

#         is_speech = vad.is_speech(audio, sample_rate)

#         if is_speech:
#             silence_count = 0
#         else:
#             silence_count += 1

#         frames.append(audio)

#         # Stop if too much silence
#         if silence_count > silence_threshold:
#             break

#         # Safety stop
#         if time.time() - start_time > max_duration:
#             break

#     stream.stop()

#     return b"".join(frames), sample_rate


# def save_wav(filename, audio_bytes, sample_rate):
#     with wave.open(filename, "wb") as f:
#         f.setnchannels(1)
#         f.setsampwidth(2)
#         f.setframerate(sample_rate)
#         f.writeframes(audio_bytes)


# import openai
# client = openai.OpenAI()

# def transcribe_audio(file_path):
#     with open(file_path, "rb") as f:
#         result = client.audio.transcriptions.create(
#             model="gpt-4o-mini-tts",  # whisper model
#             file=f
#         )
#     return result.text

# async def get_candidate_name():
#     # Record answer
#     audio_bytes, sr = record_until_silence()

#     filename = f"name_{uuid.uuid4()}.wav"
#     save_wav(filename, audio_bytes, sr)

#     print("[BOT] Processing name...")

#     # Transcribe with Whisper
#     try:
#         name_text = transcribe_audio(filename)
#     except Exception as e:
#         print("Transcription error:", e)
#         name_text = ""

#     # Cleanup file
#     try:
#         os.remove(filename)
#     except:
#         pass

#     if not name_text.strip():
#         return "Unknown"

#     return name_text.strip()


# async def wait_for_user_signal():
#     print("\n🔵 Press ENTER to ask the next question...")
#     await asyncio.get_event_loop().run_in_executor(None, input)
#     print("➡ Continuing...\n")

# from vosk import Model, KaldiRecognizer
# import pyaudio
# import json

# async def wait_for_user_signal():
#     print("\n🎤 Say 'next' to continue...")

#     model = Model("vosk-model-small-en-us-0.15")
#     rec = KaldiRecognizer(model, 16000)

#     p = pyaudio.PyAudio()
#     stream = p.open(format=pyaudio.paInt16,
#                     channels=1,
#                     rate=16000,
#                     input=True,
#                     frames_per_buffer=4096)

#     stream.start_stream()

#     while True:
#         data = stream.read(4096, exception_on_overflow=False)
#         if rec.AcceptWaveform(data):
#             result = json.loads(rec.Result())
#             text = result.get("text", "")

#             if "next" in text.lower():
#                 print("➡ Keyword detected: NEXT. Continuing...\n")
#                 stream.stop_stream()
#                 stream.close()
#                 p.terminate()
#                 return



