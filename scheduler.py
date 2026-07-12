import time
import subprocess
from datetime import datetime, timezone
from pymongo import MongoClient
import os
# 🔌 MongoDB connection

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["EmpowHR_db1"]
jobapplications_collection=db["jobApplications"]

print("Scheduler running...")

is_running = False

while True:
    try:
        if is_running:
            time.sleep(10)
            continue

        now = datetime.now(timezone.utc)
        interview = jobapplications_collection.find_one_and_update(
            {
                "interviewstatus": "pending",
                "interviewtime": {"$lte": now}
            },
            {
                "$set": {"interviewstatus": "running"}
            },
            sort=[("interviewtime", 1)]
        )

        if interview:
            is_running = True
            candidate_name = interview["formData"]["fullName"]
            application_id = interview["applicationId"]
            job_id = interview["jobId"]

            print(f"Starting interview for {candidate_name}")
            result = subprocess.run(
                [
                    "python",
                    "auto_join_zoom.py",
                    candidate_name,
                    application_id,
                    job_id
                ],
                capture_output=True,
                text=True
            )

            print(result.stdout)

            if result.returncode != 0:
                print("Bot failed:", result.stderr)
                jobapplications_collection.update_one(
                    {"_id": interview["_id"]},
                    {"$set": {"interviewstatus": "failed"}}
                )
            else:
                print("Interview completed")
                jobapplications_collection.update_one(
                    {"_id": interview["_id"]},
                    {"$set": {"interviewstatus": "completed"}}
                )

            is_running = False

        time.sleep(300)  # check every 5 min 
    except Exception as e:
        print("Error:", e)
        time.sleep(10)