import os
import time
import pyautogui
import pygetwindow as gw
import threading
from pywinauto import Application
from obs_control import AutoOBSRecorder
import pyautogui
import psutil
import sys
from pymongo import MongoClient
from bson import ObjectId

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

from supabase import create_client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

candidate_name = 'Noor Fatima'
application_id = '30896dc0-822e-4fa0-8a2b-87521e5bf3b9'
job_id = '69148a80cc059aa53701c0e1'

print("Candidate:", candidate_name)
print("Application ID:", application_id)
print("Job ID:", job_id)


MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["EmpowHR_db1"]
jobapplications_collection=db["jobApplications"]

MEETING_URL = "7453011380"
INTERVIEW_BOT_SCRIPT = "bot5.py"

def get_application_data(application_id):
    data = jobapplications_collection.find_one({
        "applicationId": application_id
    })
    if not data:
        raise Exception("Application not found")
    return data

def rename_recording(application_id):
    folder = "recordings"
    files = os.listdir(folder)

    latest_file = max(
        [os.path.join(folder, f) for f in files],
        key=os.path.getctime
    )

    new_name = f"{application_id}.mp4"
    new_path = os.path.join(folder, new_name)

    os.rename(latest_file, new_path)

    return new_path


def upload_to_supabase(file_path, application_id):
    with open(file_path, "rb") as f:
        supabase.storage.from_("videos").upload(
            f"{application_id}.mp4",
            f
        )

    public_url = supabase.storage.from_("videos").get_public_url(f"{application_id}.mp4")

    return public_url

def save_video_url(application_id, url):
    jobapplications_collection.update_one(
        {"applicationId": application_id},
        {"$set": {"analysis.video_url": url}}
    )

def zoom_meeting_active(  ):
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and 'zoom' in proc.info['name'].lower():
            return True
    return False

def admit_with_image():
    img_list = ["admit.png", "admit_all.png", "waiting_room.png"]
    for img in img_list:
        pos = pyautogui.locateCenterOnScreen(img, confidence=0.8)
        if pos:
            pyautogui.click(pos)
            print(f"[BOT] Clicked {img}")
            return True
    return False

def click_image(img, timeout=15, conf=0.75):
    print(f"[BOT] Looking for {img}...")

    start = time.time()
    while time.time() - start < timeout:
        pos = pyautogui.locateCenterOnScreen(img, confidence=conf)
        if pos:
            print(f"[BOT] Found {img}! Clicking...")
            pyautogui.moveTo(pos, duration=0.2)
            pyautogui.click()
            time.sleep(1)
            return True

        time.sleep(0.4)

    raise Exception(f"[ERROR] Could not find {img}!")


admitted_candidate=False
def auto_admit_participants(candidate_name):
    print("[BOT] Waiting room monitor started...")

    global admitted_candidate
    expected_name = candidate_name.lower()

    while not admitted_candidate:
        try:
            app = Application(backend="uia").connect(title_re=".*Zoom Meeting.*")
            win = app.top_window()

            participants = win.descendants(control_type="Text")

            for p in participants:
                name = p.window_text().lower()

                if expected_name in name:
                    admit_btn = win.child_window(title="Admit", control_type="Button")

                    if admit_btn.exists():
                        print(f"[BOT] Admitting {name}")
                        admit_btn.click_input()
                        admitted_candidate = True
                        break
                    jobapplications_collection.update_one(
                            {"application_id": application_id},
                            {"$set": {"interviewstatus": "in_progress"}}
                        )


        except Exception:
            pass

def click_preview_join():
    print("[BOT] Detecting Zoom preview button via UI automation…")

    try:
        app = Application(backend="uia").connect(title_re=".*Personal Meeting Room.*|.*Join meeting.*")
        win = app.top_window()

        print("[BOT] Preview window found.")
        time.sleep(1)

        # Look for the actual "Join" button using UI Automation
        join_btn = win.child_window(title="Join", control_type="Button")

        print("[BOT] Clicking Join button (UI automation)…")
        join_btn.click_input()

        time.sleep(3)
        print("[BOT] Joined meeting successfully!")

    except Exception as e:
        print("[ERROR] UI automation failed:", e)

def activate_zoom():
    print("[BOT] Activating Zoom window...")

    titles = [t for t in gw.getAllTitles() if "Zoom" in t]

    if not titles:
        print("[BOT ERROR] Zoom window not found!")
        return

    win = gw.getWindowsWithTitle(titles[0])[0]
    win.activate()
    win.maximize()
    time.sleep(1)

def open_zoom():
    print("[BOT] Opening Zoom...")
    os.startfile("C:\\Users\\X1 EXTREME\\AppData\\Roaming\\Zoom\\bin\\Zoom.exe")
    time.sleep(5)
    activate_zoom()

def start_interview_bot():
    print("[BOT] Starting Interview Bot...")
    os.system(f"python {INTERVIEW_BOT_SCRIPT}")

def leave_meeting():
    jobapplications_collection.update_one(
        {"application_id": application_id},
        {"$set": {"interviewstatus": "done"}}
    )
    print("[BOT] Leaving meeting...")
    pyautogui.hotkey("alt", "q")
    time.sleep(1)
    pyautogui.press("enter")
    time.sleep(2)

def maximize_zoom_window():
    print("[BOT] Maximizing Zoom window...")
    try:
        titles = [t for t in gw.getAllTitles() if "Zoom" in t]
        if not titles:
            print("[BOT ERROR] Zoom window not found!")
            return
        win = gw.getWindowsWithTitle(titles[0])[0]
        win.maximize()
        time.sleep(1)
        print("[BOT] Zoom window maximized.")
    except Exception as e:
        print("[ERROR] Could not maximize Zoom window:", e)

import subprocess
def start_interview_bot(application_id):
    print("[BOT] Starting Interview Bot...")

    subprocess.Popen(
        ["python", INTERVIEW_BOT_SCRIPT, application_id]
    )

def main():
    global candidate_name
    print("[BOT] Auto-Join Start")
    data = get_application_data(application_id)

    candidate_name = 'Hisaan Sakhawat'
    MEETING_URL ='7453011380'

    print("Joining:", candidate_name)
    print("Meeting:", MEETING_URL)


    recorder = AutoOBSRecorder()

    if recorder.start_obs():
        print("[RECORDER] OBS started")
        recorder.configure_obs_via_cli()

        connected = False
        for i in range(5):
            if recorder.connect_to_obs():
                connected = True
                break
            print(f"[RECORDER] Retrying OBS WebSocket connection ({i+1}/5)...")
            time.sleep(2)

        if connected:
            recorder.setup_recording_automatically()
            recorder.start_recording()
        else:
            print("[RECORDER] Could not connect to OBS WebSocket, recording may fail.")
    else:
        print("[RECORDER] OBS failed to start, recording will not happen.")

    # 1️⃣ Open Zoom and join
    open_zoom()
    click_image("join_button.jpg")
    click_image("meeting_box.png")

    print("[BOT] Typing meeting URL...")
    pyautogui.typewrite(MEETING_URL)
    pyautogui.press("enter")

    print("[BOT] Waiting for meeting to load...")
    time.sleep(5)
    click_preview_join()
    maximize_zoom_window()

    # Start waiting room monitor in background
    threading.Thread(target=auto_admit_participants, args=(candidate_name,),daemon=True).start()
    time.sleep(10)

    start_interview_bot(application_id)
    

    print("[BOT] Meeting in progress...")
    while zoom_meeting_active():
        time.sleep(5)
    #time.sleep(300)

    #recorder.stop_recording()
    if recorder.connected:
        recorder.stop_recording()
        recorder.ws.disconnect()
        print("[RECORDER] Recording stopped")

    print("[BOT] DONE!")

    video_path = rename_recording(application_id)

    url = upload_to_supabase(video_path, application_id)

    save_video_url(application_id, url)

    print("[BOT] Video uploaded and saved!")

if __name__ == "__main__":
     main()


