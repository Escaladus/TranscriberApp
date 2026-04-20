from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

import ctranslate2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DEFAULT_MODEL_DIR = BASE_DIR / "models"
JOB_DATA_DIR = BASE_DIR / ".job_data"
JOB_DATA_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Finnish Video Transcriber")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_models: dict[str, WhisperModel] = {}
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
VALID_RUNTIME_MODES = {"auto", "cpu", "gpu"}


def resolve_model_source(model_name: str) -> tuple[str, bool]:
    local_dir = DEFAULT_MODEL_DIR / model_name
    if local_dir.exists():
        return str(local_dir), True
    return model_name, False


def get_cuda_device_count() -> int:
    try:
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def is_cuda_available() -> bool:
    return get_cuda_device_count() > 0


def resolve_runtime_config(runtime_mode: str) -> dict[str, str]:
    requested_mode = runtime_mode.strip().lower()
    if requested_mode not in VALID_RUNTIME_MODES:
        raise HTTPException(status_code=400, detail="runtime_mode must be auto, cpu or gpu")

    if requested_mode == "gpu":
        if not is_cuda_available():
            raise HTTPException(status_code=400, detail="GPU mode requested, but CUDA is not available.")
        return {
            "requested_runtime_mode": requested_mode,
            "runtime_mode": "gpu",
            "device": "cuda",
            "compute_type": "float16",
            "runtime_label": "GPU (CUDA float16)",
        }

    if requested_mode == "cpu":
        return {
            "requested_runtime_mode": requested_mode,
            "runtime_mode": "cpu",
            "device": "cpu",
            "compute_type": "int8",
            "runtime_label": "CPU (int8)",
        }

    if is_cuda_available():
        return {
            "requested_runtime_mode": requested_mode,
            "runtime_mode": "gpu",
            "device": "cuda",
            "compute_type": "float16",
            "runtime_label": "GPU (CUDA float16)",
        }

    return {
        "requested_runtime_mode": requested_mode,
        "runtime_mode": "cpu",
        "device": "cpu",
        "compute_type": "int8",
        "runtime_label": "CPU (int8)",
    }


def get_model(model_name: str, device: str, compute_type: str) -> WhisperModel:
    model_source, local_files_only = resolve_model_source(model_name)
    key = f"{model_source}:{device}:{compute_type}"
    if key not in _models:
        _models[key] = WhisperModel(
            model_source,
            device=device,
            compute_type=compute_type,
            local_files_only=local_files_only,
        )
    return _models[key]


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise HTTPException(
            status_code=500,
            detail="ffmpeg ei loydy. Asenna ffmpeg ja varmista, etta se on PATH:ssa.",
        )


def sanitize_name(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in "-_ .").strip()
    return safe or "transcript"


def extract_audio(input_video: Path, output_wav: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_wav),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Audio extraction failed: {result.stderr}")


def format_timestamp(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def segments_to_txt(segments) -> str:
    lines = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            lines.append(text)
    return "\n".join(lines).strip() + "\n"


def segments_to_srt(segments) -> str:
    blocks = []
    idx = 1
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        blocks.append(
            f"{idx}\n{format_timestamp(segment.start)} --> {format_timestamp(segment.end)}\n{text}\n"
        )
        idx += 1
    return "\n".join(blocks).strip() + "\n"


def set_job_state(job_id: str, **updates) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(updates)


def get_job(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job.copy()


def cancel_requested(job: dict) -> bool:
    return bool(job["cancel_event"].is_set())


def cleanup_job_files(job: dict) -> None:
    job_dir = job.get("job_dir")
    if not job_dir:
        return
    shutil.rmtree(job_dir, ignore_errors=True)


def run_transcription_job(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs[job_id]

    try:
        set_job_state(job_id, status="running", message=f"Transcription in progress on {job['runtime_label']}.")

        if cancel_requested(job):
            set_job_state(job_id, status="cancelled", message="Transcription was cancelled before start.")
            cleanup_job_files(job)
            return

        try:
            model = get_model(
                model_name=job["model_name"],
                device=job["device"],
                compute_type=job["compute_type"],
            )
        except Exception as e:
            raise RuntimeError(
                "Model loading failed. Make sure the Whisper model exists in "
                f"'{DEFAULT_MODEL_DIR / job['model_name']}' or that the machine can download it. Details: {e}"
            ) from e

        if cancel_requested(job):
            set_job_state(job_id, status="cancelled", message="Transcription was cancelled before audio extraction.")
            cleanup_job_files(job)
            return

        extract_audio(job["input_path"], job["wav_path"])

        if cancel_requested(job):
            set_job_state(job_id, status="cancelled", message="Transcription was cancelled after audio extraction.")
            cleanup_job_files(job)
            return

        segments_iter, info = model.transcribe(
            str(job["wav_path"]),
            language="fi",
            vad_filter=True,
            beam_size=5,
            word_timestamps=False,
            condition_on_previous_text=True,
        )

        segments = []
        for segment in segments_iter:
            if cancel_requested(job):
                set_job_state(job_id, status="cancelled", message="Transcription was cancelled.")
                cleanup_job_files(job)
                return
            segments.append(segment)

        transcript_text = (
            segments_to_srt(segments) if job["output_format"] == "srt" else segments_to_txt(segments)
        )

        result = {
            "filename": job["suggested_filename"],
            "format": job["output_format"],
            "language": info.language,
            "duration": info.duration,
            "segment_count": len(segments),
            "requested_runtime_mode": job["requested_runtime_mode"],
            "runtime_mode": job["runtime_mode"],
            "runtime_label": job["runtime_label"],
            "device": job["device"],
            "compute_type": job["compute_type"],
            "preview": transcript_text[:4000],
            "content": transcript_text,
            "saved_on_server": False,
        }
        set_job_state(job_id, status="completed", message="Transcription finished.", result=result)
    except Exception as e:
        set_job_state(job_id, status="error", message=str(e))
    finally:
        cleanup_job_files(job)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/capabilities")
def capabilities():
    cuda_device_count = get_cuda_device_count()
    cuda_available = cuda_device_count > 0
    runtime_modes = ["auto", "cpu"]
    if cuda_available:
        runtime_modes.append("gpu")
    return {
        "cuda_available": cuda_available,
        "cuda_device_count": cuda_device_count,
        "runtime_modes": runtime_modes,
        "default_runtime_mode": "auto",
    }


@app.post("/transcribe/start")
async def start_transcription(
    file: UploadFile = File(...),
    output_format: str = Form("txt"),
    model_name: str = Form("medium"),
    runtime_mode: str = Form("auto"),
):
    ensure_ffmpeg()

    if output_format not in {"txt", "srt"}:
        raise HTTPException(status_code=400, detail="output_format must be txt or srt")

    runtime_config = resolve_runtime_config(runtime_mode)
    suffix = Path(file.filename or "video.mp4").suffix or ".mp4"
    base_name = sanitize_name(Path(file.filename or "transcript").stem)
    job_id = uuid.uuid4().hex
    job_dir = Path(tempfile.mkdtemp(prefix=f"job-{job_id[:8]}-", dir=JOB_DATA_DIR))
    input_path = job_dir / f"input{suffix}"
    wav_path = job_dir / "audio.wav"

    with input_path.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    job = {
        "id": job_id,
        "status": "queued",
        "message": f"Queued for transcription on {runtime_config['runtime_label']}.",
        "output_format": output_format,
        "model_name": model_name,
        "suggested_filename": f"{base_name}.{output_format}",
        "input_path": input_path,
        "wav_path": wav_path,
        "job_dir": job_dir,
        "cancel_event": threading.Event(),
        "result": None,
        **runtime_config,
    }

    thread = threading.Thread(target=run_transcription_job, args=(job_id,), daemon=True)
    job["thread"] = thread

    with _jobs_lock:
        _jobs[job_id] = job

    thread.start()
    return JSONResponse(
        {
            "job_id": job_id,
            "status": "queued",
            "message": job["message"],
            "runtime_mode": job["runtime_mode"],
            "runtime_label": job["runtime_label"],
        }
    )


@app.get("/transcribe/status/{job_id}")
def transcription_status(job_id: str):
    job = get_job(job_id)
    payload = {
        "job_id": job["id"],
        "status": job["status"],
        "message": job["message"],
    }
    if job.get("result"):
        payload["result"] = job["result"]
    return JSONResponse(payload)


@app.post("/transcribe/cancel/{job_id}")
def cancel_transcription(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job["status"] in {"completed", "error", "cancelled"}:
            return JSONResponse(
                {"job_id": job_id, "status": job["status"], "message": "Job is already finished."}
            )
        job["cancel_event"].set()
        job["message"] = "Cancellation requested."
    return JSONResponse({"job_id": job_id, "status": "cancelling", "message": "Cancellation requested."})


@app.get("/health")
def health():
    return {"status": "ok"}
