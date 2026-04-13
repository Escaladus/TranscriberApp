from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

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


def get_model(model_name: str, device: str, compute_type: str) -> WhisperModel:
    key = f"{model_name}:{device}:{compute_type}"
    if key not in _models:
        _models[key] = WhisperModel(model_name, device=device, compute_type=compute_type)
    return _models[key]


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise HTTPException(
            status_code=500,
            detail="ffmpeg ei löydy. Asenna ffmpeg ja varmista, että se on PATH:ssa.",
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
        raise RuntimeError(f"Äänen irrotus epäonnistui: {result.stderr}")


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


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    output_format: str = Form("txt"),
    model_name: str = Form("medium"),
    device: str = Form("cpu"),
):
    ensure_ffmpeg()

    if output_format not in {"txt", "srt"}:
        raise HTTPException(status_code=400, detail="output_format pitää olla txt tai srt")

    compute_type = "int8" if device == "cpu" else "float16"
    model = get_model(model_name=model_name, device=device, compute_type=compute_type)

    suffix = Path(file.filename or "video.mp4").suffix or ".mp4"
    base_name = sanitize_name(Path(file.filename or "transcript").stem)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        input_path = tmp_dir_path / f"input{suffix}"
        wav_path = tmp_dir_path / "audio.wav"

        with input_path.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)

        try:
            extract_audio(input_path, wav_path)
            segments, info = model.transcribe(
                str(wav_path),
                language="fi",
                vad_filter=True,
                beam_size=5,
                word_timestamps=False,
                condition_on_previous_text=True,
            )
            segments = list(segments)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    transcript_text = segments_to_srt(segments) if output_format == "srt" else segments_to_txt(segments)
    output_path = OUTPUT_DIR / f"{base_name}.{output_format}"
    output_path.write_text(transcript_text, encoding="utf-8")

    return JSONResponse(
        {
            "filename": output_path.name,
            "download_url": f"/download/{output_path.name}",
            "format": output_format,
            "language": info.language,
            "duration": info.duration,
            "segment_count": len(segments),
            "preview": transcript_text[:4000],
        }
    )


@app.get("/download/{filename}")
def download(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Tiedostoa ei löytynyt")
    return FileResponse(path, filename=filename)


@app.get("/health")
def health():
    return {"status": "ok"}
