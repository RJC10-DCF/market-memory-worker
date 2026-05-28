import os
import subprocess
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

jobs = (
    supabase.table("processing_jobs")
    .select("id, source_id, status")
    .eq("status", "pending")
    .order("created_at")
    .limit(1)
    .execute()
)

if not jobs.data:
    print("No pending jobs.")
    raise SystemExit

job = jobs.data[0]
job_id = job["id"]

print(f"Processing job: {job_id}")

try:
    supabase.table("processing_jobs").update({
        "status": "processing"
    }).eq("id", job_id).execute()

    result = subprocess.run(
        ["python", "extract_newsrun.py"],
        capture_output=True,
        text=True
    )

    print(result.stdout)

    if result.returncode != 0:
        raise Exception(result.stderr)

    supabase.table("processing_jobs").update({
        "status": "completed",
        "processed_at": "now()"
    }).eq("id", job_id).execute()

    print("Job completed.")

except Exception as e:
    supabase.table("processing_jobs").update({
        "status": "failed",
        "error": str(e)
    }).eq("id", job_id).execute()

    print("Job failed:")
    print(e)
