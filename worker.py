import time
import subprocess

POLL_SECONDS = 30

print("Market Memory worker started...")

while True:
    try:
        print("Checking pending jobs...")
        subprocess.run(["py", "process_jobs.py"], check=False)
    except Exception as e:
        print("Worker error:", e)

    time.sleep(POLL_SECONDS)