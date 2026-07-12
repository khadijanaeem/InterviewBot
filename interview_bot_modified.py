import asyncio
import os
import time
import uuid
import datetime
import random
import wave
import numpy as np
import sounddevice as sd
import webrtcvad
from pymongo import MongoClient
from dotenv import load_dotenv
from supabase import create_client, Client
from gtts import gTTS
from pydub import AudioSegment
import simpleaudio as sa
from transcription import TranscriptionService
from pinecone import Pinecone
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = "interview1536"

pc = Pinecone(api_key=PINECONE_API_KEY)
pinecone_index = pc.Index(PINECONE_INDEX)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

transcriber = TranscriptionService() 
MONGO_URI = os.getenv("MONGO_URI")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")

if not all([MONGO_URI, SUPABASE_URL, SUPABASE_KEY, SUPABASE_BUCKET]):
    raise ValueError("❌ Missing environment variables!")

mongo_client = MongoClient(MONGO_URI)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

sample_rate = 16000
vad = webrtcvad.Vad(1)

async def speak(text: str):
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

import speech_recognition as sr
import asyncio

recognizer = sr.Recognizer()

async def wait_for_silence():
    with sr.Microphone() as source:
        print("Listening...")

        recognizer.adjust_for_ambient_noise(source)

        try:
            # listen until silence
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
            print("User finished speaking")

        except sr.WaitTimeoutError:
            print("Silence detected")

def record_full_interview(duration_limit=600):
    print("🎙 Recording full interview...")

    recording = sd.rec(
        int(duration_limit * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16"
    )
    sd.wait()

    filename = f"interview_{uuid.uuid4().hex}.wav"

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(recording.tobytes())

    print("✅ Recording saved:", filename)
    return filename

def get_random_questions():
    db = mongo_client["EmpowHR_db1"]
    col = db["interview_questions"]

    categories = {
        "introduction": 1,
        "experience": 2,
        "skills": 2,
        
        "behavioral": 2,
        "closing": 1
    }

    final_questions = []

    for cat, count in categories.items():
        docs = list(col.find({"category": cat}))
        if docs:
            selected = random.sample(docs, min(count, len(docs)))
            final_questions.extend([q["text"] for q in selected])

    return final_questions

def upload_to_supabase(local_file, candidate_name):
    filename = f"{candidate_name}_{uuid.uuid4().hex}.wav"

    try:
        with open(local_file, "rb") as f:
            supabase.storage.from_(SUPABASE_BUCKET).upload(
                path=filename,
                file=f,
                file_options={"content-type": "audio/wav"}
            )

        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"
        print("📤 Uploaded:", public_url)
        return public_url

    except Exception as e:
        print("Upload failed:", e)
        return None

def embed_text(text):

    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )

    return response.data[0].embedding

# def evaluate_answer(candidate_answer, pinecone_id):

#     vector = embed_text(candidate_answer)

#     results = pinecone_index.query(
#         id=pinecone_id,
        
#         top_k=1,
#         include_metadata=True
#     )

#     match = results["matches"][0]

#     similarity = match["score"]

#     return similarity

def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def evaluate_answer(candidate_answer, pinecone_id):

    # Prevent empty answers
    if len(candidate_answer.strip()) < 5:
        print("⚠ Answer too short")
        return 0

    # Candidate embedding
    candidate_vector = embed_text(candidate_answer)

    # Fetch correct answer vector from Pinecone
    result = pinecone_index.fetch(ids=[pinecone_id])

    # stored_vector = result["vectors"][pinecone_id]["values"]
    stored_vector = TECH_VECTORS[pinecone_id]["values"]
    # Calculate similarity
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

def save_interview(candidate_name, questions, recording_url):
    db = mongo_client["EmpowHR_db1"]
    col = db["interviews"]

    doc = {
        "candidate_name": candidate_name,
        "questions": questions,
        "recording_url": recording_url,
        "timestamp": datetime.datetime.utcnow()
    }

    col.insert_one(doc)
    print("📁 Interview saved to MongoDB")

def get_technical_questions(job_post):

    db = mongo_client["EmpowHR_db1"]
    col = db["interview_questions"]
    docs = list(col.find({
        "category": "technical",
        "jobPost": job_post
    }))

    if len(docs) < 5:
        raise Exception("Not enough technical questions for this job role")

    selected = random.sample(docs, 5)
    return selected
   # return docs[:3]

def get_question_by_difficulty(difficulty, category="technical"):
    db = mongo_client["EmpowHR_db1"]
    col = db["interview_questions"]

    questions = list(col.find({
        "difficulty": difficulty,
        "category": category
    }))

    if not questions:
        questions = list(col.find({"difficulty": "medium"}))

    if not questions:
        raise Exception("No questions found in database.")

    selected = random.choice(questions)
    return selected["text"]

# def record_answer(max_duration=60, silence_threshold=1.5):
#     print("🎙 Listening... (speak now)")

#     frame_duration = 30  # ms
#     frame_size = int(sample_rate * frame_duration / 1000)

#     silence_limit = int(silence_threshold * 1000 / frame_duration)

#     silence_counter = 0
#     audio_frames = []

#     stream = sd.InputStream(
#         samplerate=sample_rate,
#         channels=1,
#         dtype="int16",
#         blocksize=frame_size
#     )

#     with stream:
#         start_time = time.time()

#         while True:
#             frame, _ = stream.read(frame_size)

#             frame_bytes = frame.tobytes()
#             is_speech = vad.is_speech(frame_bytes, sample_rate)

#             audio_frames.append(frame_bytes)

#             if is_speech:
#                 silence_counter = 0
#             else:
#                 silence_counter += 1

#             # Stop if silence exceeds threshold
#             if silence_counter > silence_limit:
#                 print("🛑 Silence detected. Stopping recording.")
#                 break

#             # Safety stop (max duration)
#             if time.time() - start_time > max_duration:
#                 print("⏱ Max duration reached.")
#                 break

#     filename = f"answer_{uuid.uuid4().hex}.wav"

#     with wave.open(filename, "wb") as wf:
#         wf.setnchannels(1)
#         wf.setsampwidth(2)
#         wf.setframerate(sample_rate)
#         wf.writeframes(b"".join(audio_frames))

#     print("✅ Saved:", filename)

#     return filename




def record_answer(max_duration=120, silence_threshold=2):

    print("Waiting for candidate to start speaking...")

    vad = webrtcvad.Vad(2)

    frame_duration = 30  # ms
    frame_size = int(sample_rate * frame_duration / 1000)

    audio_frames = []

    speaking = False
    silence_start = None
    start_time = None

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16') as stream:

        while True:

            frame, _ = stream.read(frame_size)
            frame_bytes = frame.tobytes()
            is_speech = vad.is_speech(frame_bytes, sample_rate)

            if is_speech:
                if not speaking:
                    print("Candidate started speaking...")
                    speaking = True
                    start_time = time.time()

                silence_start = None
                audio_frames.append(frame)

            else:
                if speaking:
                    audio_frames.append(frame)

                    if silence_start is None:
                        silence_start = time.time()

                    if time.time() - silence_start > silence_threshold:
                        print("Silence detected. Ending recording.")
                        break

            if speaking and time.time() - start_time > max_duration:
                print("⏱ Max duration reached.")
                break

    audio = np.concatenate(audio_frames, axis=0)

    filename = "candidate_answer.wav"

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())

    return filename

def update_difficulty(current_difficulty, similarity):

    if similarity >= 0.75:
        if current_difficulty == "easy":
            return "medium"
        elif current_difficulty == "medium":
            return "hard"
        else:
            return "hard"

    elif similarity <= 0.40:
        if current_difficulty == "hard":
            return "medium"
        elif current_difficulty == "medium":
            return "easy"
        else:
            return "easy"
        
    return current_difficulty

def get_candidate(candidate_id):

    db = mongo_client["EmpowHR_db1"]
    col = db["candidates"]

    return col.find_one({"_id": candidate_id})

TECH_VECTORS = pinecone_index.fetch(
    ids=["fe-tech-9", "fe-tech-8", "fe-tech-1"]
)["vectors"]

async def start_interview():

    # candidate_id = input("Enter candidate id: ")

    # candidate = get_candidate(candidate_id)

    # candidate_name = candidate["name"]
    # job_post = candidate["jobPost"]
    job_post='Frontend Developer'
    general_questions = [
    {
        "question": "Tell me about yourself and your background."
    },
    {
        "question": "Describe a challenging situation you faced and how you handled it."
    },
    {
        "question": "Why do you want to work in this role or field?"
    }
]

    await speak(f"Welcome Hesaan Let's begin the interview.")

    # Non technical questions
 #   general_questions = get_random_questions()

    # for q in general_questions:
    #     question_text = q["question"]
    #     print("\nBOT:", question_text)

    #     await speak(question_text)
    #     await wait_for_silence()
        #input("Press ENTER to continue to the next question...")

        # print("BOT:", q)
        # await speak(q)

    # Technical section
    await speak("Now we will begin the technical section.")
   # technical_questions = get_technical_questions(job_post)
    technical_questions = [
    {
        "text": "What is the difference between var, let, and const in JavaScript?",
        "pineconeId": "fe-tech-9"
    },
    {
        "text": "Explain how the JavaScript event loop works.",
        "pineconeId": "fe-tech-8"
    },
    {
        "text": "What are closures in JavaScript?",
        "pineconeId": "fe-tech-1"
    }
]
    current_difficulty = "medium"

    for q in technical_questions:

        question_text = q["text"]
        pinecone_id = q["pineconeId"]

        print("BOT:", question_text)
        await speak(question_text)

        # Record ONLY technical answers
        answer_audio = record_answer(max_duration=30)

        transcript_data = transcriber.transcribe(answer_audio)
        transcript_text = transcript_data["full_text"]
        print("Candidate transcript:", transcript_text)

        if not transcript_text or transcript_text.strip() == "":
            print("⚠ No answer detected")
            current_difficulty='easy'
        else:
            similarity = evaluate_answer(transcript_text, pinecone_id)
            score = convert_score(similarity)
            print("Technical similarity:", similarity)
            print("Score:", score) 
            current_difficulty = update_difficulty(
                current_difficulty,
                similarity
            ) 
            print("Next difficulty:", current_difficulty)

    await speak("Thank you. This concludes the interview.")

if __name__ == "__main__":
    asyncio.run(start_interview())