"""FastAPI server bridging the web UI to the verticals pipeline."""

import json
import os
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Verticals Video Generator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Paths
VERTICALS_DIR = Path(__file__).parent
NICHES_DIR = VERTICALS_DIR / "niches"
MEDIA_DIR = Path.home() / ".verticals" / "media"
DRAFTS_DIR = Path.home() / ".verticals" / "drafts"

# In-memory job tracker
jobs: dict[str, dict] = {}


class GenerateRequest(BaseModel):
    topic: str
    niche: str = "finance"
    language: str = "en"
    voice_index: int = 0
    platform: str = "shorts"
    provider: str = "claude_cli"
    context: str = ""


# ── API Routes ──


@app.get("/api/niches")
def list_niches():
    """List all available niche profiles."""
    niches = []
    for f in sorted(NICHES_DIR.glob("*.yaml")):
        import yaml
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        niches.append({
            "id": f.stem,
            "name": data.get("display_name", f.stem),
            "description": data.get("description", ""),
        })
    return {"niches": niches}


@app.post("/api/generate")
def generate_video(req: GenerateRequest):
    """Start video generation in background thread."""
    job_id = str(int(time.time()))
    jobs[job_id] = {
        "status": "starting",
        "stage": "Initializing...",
        "progress": 0,
        "draft": None,
        "video_path": None,
        "error": None,
    }

    thread = threading.Thread(target=_run_pipeline, args=(job_id, req), daemon=True)
    thread.start()
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    """Poll job progress."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]


@app.get("/api/videos/{job_id}")
def get_video(job_id: str):
    """Serve the generated video file."""
    if job_id not in jobs or not jobs[job_id].get("video_path"):
        raise HTTPException(404, "Video not found")
    path = Path(jobs[job_id]["video_path"])
    if not path.exists():
        raise HTTPException(404, "Video file missing")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.get("/api/drafts/{job_id}")
def get_draft(job_id: str):
    """Return draft JSON for a job."""
    if job_id not in jobs or not jobs[job_id].get("draft"):
        raise HTTPException(404, "Draft not found")
    return jobs[job_id]["draft"]


# ── Pipeline runner ──


def _run_pipeline(job_id: str, req: GenerateRequest):
    """Run the full verticals pipeline in a background thread."""
    try:
        job = jobs[job_id]

        # Stage 1: Draft
        job.update(status="running", stage="Researching & writing script...", progress=10)
        cmd = [
            "python", "-m", "verticals", "--verbose", "run",
            "--news", req.topic,
            "--niche", req.niche,
            "--voice", "edge",
            "--lang", req.language,
            "--provider", req.provider,
            "--dry-run",
        ]
        if req.context:
            cmd += ["--context", req.context]

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            cwd=str(VERTICALS_DIR), env=env,
            encoding="utf-8", errors="replace",
        )

        # Find the draft file (most recent)
        drafts = sorted(DRAFTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not drafts:
            raise RuntimeError(f"No draft created. stderr: {r.stderr[-500:]}")

        draft_path = drafts[0]
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        job.update(stage="Script ready! Generating video...", progress=30, draft=draft)

        # Stage 2: Produce
        job.update(stage="Downloading video clips...", progress=40)
        cmd2 = [
            "python", "-m", "verticals", "--verbose", "produce",
            "--draft", str(draft_path),
            "--lang", req.language,
            "--voice", "edge",
            "--voice-index", str(req.voice_index),
            "--force",
        ]

        process = subprocess.Popen(
            cmd2, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=str(VERTICALS_DIR), env=env,
            encoding="utf-8", errors="replace",
        )

        # Stream progress from stdout
        for line in iter(process.stdout.readline, ""):
            line = line.strip()
            if not line:
                continue
            if "Pexels video" in line or "Downloading" in line:
                job["stage"] = "Downloading video clips..."
                job["progress"] = min(job["progress"] + 5, 60)
            elif "voiceover" in line.lower() or "Edge TTS" in line:
                job.update(stage="Generating voiceover...", progress=65)
            elif "Whisper" in line:
                job.update(stage="Creating captions...", progress=75)
            elif "Assembling" in line or "Trimming" in line:
                job.update(stage="Assembling final video...", progress=85)
            elif "Video assembled" in line:
                job.update(stage="Video ready!", progress=100)

        process.wait(timeout=600)

        # Find the video
        draft_job_id = draft.get("job_id", "")
        video_path = MEDIA_DIR / f"verticals_{draft_job_id}_{req.language}.mp4"
        if not video_path.exists():
            # Search for most recent mp4
            videos = sorted(MEDIA_DIR.glob("verticals_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            video_path = videos[0] if videos else None

        if video_path and video_path.exists():
            job.update(status="done", stage="Video ready!", progress=100, video_path=str(video_path))
        else:
            raise RuntimeError("Video file not found after production")

    except Exception as e:
        jobs[job_id].update(status="error", stage=f"Error: {e}", error=str(e))


if __name__ == "__main__":
    import uvicorn
    print("\n  Verticals API server starting on http://localhost:8000\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
