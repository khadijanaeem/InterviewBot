import asyncio
import os
import time
import uuid
import wave
import numpy as np
import sounddevice as sd
import webrtcvad
from gtts import gTTS
from pydub import AudioSegment
import simpleaudio as sa
from pinecone import Pinecone
from openai import OpenAI
from dotenv import load_dotenv
from transcription import TranscriptionService
import speech_recognition as sr
from pymongo import MongoClient
import random



from scipy.signal import resample

load_dotenv()

import sys
application_id = sys.argv[1]
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

pc = Pinecone(api_key=PINECONE_API_KEY)
pinecone_index = pc.Index("interview1536")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

transcriber = TranscriptionService()
MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
db = client["EmpowHR_db1"]
questions_collection = db["interview_questions"]
jobapplications_collection=db["jobApplications"]

data = jobapplications_collection.find_one({"applicationId": application_id})
questions = data.get("interviewQuestions", [])
jobPost = data["formData"]["title"]


def save_question(application_id, question_text):
    jobapplications_collection.update_one(
        {"applicationId": application_id},
        {"$push": {"interviewQuestions": question_text}}
    )
vad = webrtcvad.Vad(2)

def get_general_questions():
    categories = ["introduction", "skills", "experience", "communication", "availability","culture", "communication",  "iq-pattern","iq-logic", "iq-analytical",  "iq-math", "closing"]
    selected_questions = []

    for cat in categories:
        qs = list(questions_collection.find({"category": cat}))
        random.shuffle(qs)
        selected_questions.extend(qs[:2])  # take 2 from each

    return selected_questions

def get_technical_questions(job_post, difficulty=None):
    query = {"category": "technical", "jobPost": job_post}
    questions = []

    if difficulty:
        query["difficulty"] = difficulty
        questions = list(questions_collection.find(query))
    else:
        # fetch all difficulties
        questions += list(questions_collection.find({**query, "difficulty": "Easy"}))
        questions += list(questions_collection.find({**query, "difficulty": "Medium"}))
        questions += list(questions_collection.find({**query, "difficulty": "Hard"}))

    return questions

def next_difficulty(current_difficulty, score):
    if current_difficulty == "Easy":
        if score >= 8:
            return "Medium"   
        return "Easy"         
    elif current_difficulty == "Medium":
        if score >= 8:
            return "Hard"
        elif score <= 4:
            return "Easy"
        return "Medium"
    elif current_difficulty == "Hard":
        if score <= 6:
            return "Medium"  
        return "Hard"
    else:
        return "Medium"

# def get_technical_questions(job_post,difficulty):
#     medium = list(questions_collection.find({
#         "category": "technical",
#         "jobPost": job_post,
#         "difficulty": "Medium"
#     }))

#     easy = list(questions_collection.find({
#         "category": "technical",
#         "jobPost": job_post,
#         "difficulty": "Easy"
#     }))

#     hard = list(questions_collection.find({
#         "category": "technical",
#         "jobPost": job_post,
#         "difficulty": "Hard"
#     }))

#     return medium + easy + hard

async def speak(text):

    filename = f"tts_{uuid.uuid4().hex}.mp3"

    try:
        tts = gTTS(text=text, lang="en")
        tts.save(filename)

        audio = AudioSegment.from_mp3(filename)

        play_obj = sa.play_buffer(
            audio.raw_data,
            num_channels=audio.channels,
            bytes_per_sample=audio.sample_width,
            sample_rate=audio.frame_rate
        )

        play_obj.wait_done()

        os.remove(filename)

    except Exception as e:
        print("TTS Error:", e)

def embed_text(text):

    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )

    return response.data[0].embedding

def cosine_similarity(a, b):

    a = np.array(a)
    b = np.array(b)

    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def load_technical_vectors(technical_questions):
    ids = [q["pineconeId"] for q in technical_questions if "pineconeId" in q]

    print("Fetching Pinecone vectors for:", ids)

    result = pinecone_index.fetch(ids=ids)

    return result["vectors"]  # dictionary {id: vector_data}

def evaluate_answer(candidate_answer, pinecone_id, TECH_VECTORS):
    if len(candidate_answer.strip()) < 5:
        print("⚠ Answer too short")
        return 0
    candidate_vector = embed_text(candidate_answer)
    stored_vector = TECH_VECTORS[pinecone_id]["values"]
    similarity = cosine_similarity(candidate_vector, stored_vector)
    return similarity

def convert_score(similarity):
    if similarity > 0.9:
        return 10
    elif similarity > 0.8:
        return 8
    elif similarity > 0.7:
        return 6
    elif similarity > 0.6:
        return 4
    elif similarity > 0.5:
        return 3
    elif similarity > 0.4:
        return 2
    else:
        return 0


recognizer = sr.Recognizer()

async def wait_for_silence():
    with sr.Microphone() as source:
        print("Listening...")
        recognizer.adjust_for_ambient_noise(source)
        try:
            recognizer.pause_threshold = 2.0  
            recognizer.non_speaking_duration = 1.0

            # listen until silence
            audio = recognizer.listen(source, timeout=5)
            print("User finished speaking")

        except sr.WaitTimeoutError:
            print("Silence detected")

sample_rate = 48000  
frame_duration_ms = 20
frame_size = int(sample_rate * frame_duration_ms / 1000)

def get_default_input_device():
    """Automatically pick the first input device with at least 1 channel."""
    for i, dev in enumerate(sd.query_devices()):
        if dev['max_input_channels'] > 0:
            return i
    return None

vad = webrtcvad.Vad()
vad.set_mode(2)

def get_default_input_device():
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            return i
    return None

def record_answer(max_duration=90, max_silence_sec=3.0):
    print("🎙 Calibrating for ambient noise...")
    MIN_SPEECH_DURATION = 1.5 
    device_index = 17  
    sample_rate = 48000
    frame_duration_ms = 20
    frame_size = int(sample_rate * frame_duration_ms / 1000)  # 960

    if device_index is None:
        raise RuntimeError("No input device found!")

    ambient_frames = []
    with sd.InputStream(device=device_index, samplerate=sample_rate,
                        channels=1, dtype='int16', blocksize=frame_size) as stream:

        for _ in range(int(0.5 * 1000 / frame_duration_ms)):
            frame, _ = stream.read(frame_size)
            ambient_frames.append(frame)

    ambient_energy = np.mean([np.abs(f).mean() for f in ambient_frames])
    ENERGY_THRESHOLD = max(ambient_energy * 1.5, 30)

    print(f"Ambient energy: {ambient_energy:.2f}, Threshold set to: {ENERGY_THRESHOLD:.2f}")
    print("🎙 Waiting for candidate to start speaking...")

    audio_frames = []
    pre_speech_buffer = []
    speaking = False
    start_time = None

    PRE_SPEECH_FRAMES = int(0.5 * 1000 / frame_duration_ms)
    max_silence_frames = int(max_silence_sec * 1000 / frame_duration_ms)
    silence_counter = 0

    with sd.InputStream(device=device_index, samplerate=sample_rate,
                        channels=1, dtype='int16', blocksize=frame_size) as stream:

        while True:
            frame, _ = stream.read(frame_size)
            if speaking:
                audio_frames.append(frame.copy())
            energy = np.abs(frame).mean()
            mono = frame
            if mono.ndim > 1:
                mono = mono.mean(axis=1)
            mono_16k = mono[::3].astype(np.int16)
            if len(mono_16k) < 320:
                continue

            vad_frame = mono_16k[:320].tobytes()
            is_speech = vad.is_speech(vad_frame, 16000)

            speech_detected = is_speech and energy > ENERGY_THRESHOLD

            if not speaking:
                pre_speech_buffer.append(frame)
                if len(pre_speech_buffer) > PRE_SPEECH_FRAMES:
                    pre_speech_buffer.pop(0)

            if speech_detected:
                if not speaking:
                    print("🗣 Candidate started speaking")
                    speaking = True
                    start_time = time.time()
                    audio_frames.extend(pre_speech_buffer)

                silence_counter = 0

            else:
                if speaking:
                    silence_counter += 1
                    if silence_counter >= max_silence_frames:
                        if time.time() - start_time > MIN_SPEECH_DURATION:
                          print("🟢 Candidate finished speaking.")
                          break

            if speaking and time.time() - start_time > max_duration:
                print("⏱ Max duration reached")
                break

    if len(audio_frames) == 0:
        print("⚠ No speech detected")
        return None
    audio = np.concatenate(audio_frames, axis=0)
    audio = audio.astype(np.int16)

    filename = f"answer_{uuid.uuid4().hex}.wav"
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(48000)   
        wf.writeframes(audio.tobytes())

    print("✅ Answer saved:", filename)

    return filename

def load_technical_vectors(technical_questions):
    ids = [q["pineconeId"] for q in technical_questions if "pineconeId" in q]

    print("Fetching Pinecone vectors for:", ids)

    result = pinecone_index.fetch(ids=ids)

    return result["vectors"]  # dictionary {id: vector_data}


async def start_interview(application_id):
    general_questions = get_general_questions()
    await speak("Welcome. Let's begin the interview.")

    loop = asyncio.get_event_loop()

    for q in general_questions:
        question_text = q["text"]
        print("\nBOT:", question_text)
        await speak(question_text)

        answer_audio = record_answer()
        time.sleep(2)
        transcript_data = await loop.run_in_executor(None, transcriber.transcribe, answer_audio)
        transcript_text = transcript_data["full_text"]
        print("Candidate transcript:", transcript_text)

    await speak("Now we will begin the technical section.")

    current_difficulty = "Medium"
    technical_questions_all = get_technical_questions(jobPost, difficulty=current_difficulty)
    TECH_VECTORS = load_technical_vectors(technical_questions_all)

    technical_questions = technical_questions_all[:5]

    for q in technical_questions:
        question_text = q["text"]
        pinecone_id = q["pineconeId"]

        print("\nBOT:", question_text)
        await speak(question_text)

        answer_audio = record_answer()
        time.sleep(2)

        if answer_audio is None:
            print("⚠ No answer recorded")
            continue

        transcript_data = await loop.run_in_executor(None, transcriber.transcribe, answer_audio)
        transcript_text = transcript_data["full_text"]
        print("Candidate transcript:", transcript_text)

        await speak("Thank you. Evaluating your answer.")
        similarity = await loop.run_in_executor(None, evaluate_answer, transcript_text, pinecone_id, TECH_VECTORS)
        score = convert_score(similarity)
        print("Similarity:", similarity)
        print("Score:", score)

        current_difficulty = next_difficulty(current_difficulty, score)

# async def start_interview(application_id):   
#  #   job_post='Frontend Developer'
#     general_questions = get_general_questions()

#     await speak("Welcome. Let's begin the interview.")

#     loop = asyncio.get_event_loop()
    
#     for q in general_questions:
#         question_text = q["text"]
#         #save_question(candidate["_id"], question_text) 
#         print("\nBOT:", question_text)

#         await speak(question_text)
      
#         answer_audio = record_answer()
#         time.sleep(2)
#         transcript_data = await loop.run_in_executor(
#             None,
#             transcriber.transcribe,
#             answer_audio
#         )

#         transcript_text = transcript_data["full_text"]
#         print("Candidate transcript:", transcript_text)
        
#     await speak("Now we will begin the technical section.")
#     technical_questions = get_technical_questions(jobPost)

#     TECH_VECTORS = load_technical_vectors(technical_questions)

#     for q in technical_questions:

#         question_text = q["text"]
#         pinecone_id = q["pineconeId"]
#         print("\nBOT:", question_text)
#         await speak(question_text)
#         answer_audio = record_answer()
#         time.sleep(2)

#         if answer_audio is None:
#             print("⚠ No answer recorded")
#             continue

#         transcript_data = await loop.run_in_executor(
#             None,
#             transcriber.transcribe,
#             answer_audio
#         )

#         transcript_text = transcript_data["full_text"]
#         print("Candidate transcript:", transcript_text)
#         await speak("Thank you. Evaluating your answer.")

#         similarity = await loop.run_in_executor(
#             None,
#             evaluate_answer,
#             transcript_text,
#             pinecone_id,
#             TECH_VECTORS
#         )

#         score = convert_score(similarity)
#         print("Similarity:", similarity)
#         print("Score:", score)
   
#     await speak("Thank you. This concludes the interview.")

if __name__ == "__main__":
    asyncio.run(start_interview(application_id))