from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, HTTPException, File
from pydantic import BaseModel
import tempfile
import os
from pathlib import Path

import transcribe


class TranscriptionSegment(BaseModel):
    text: str
    start: float | None
    end: float | None


class TranscriptionResponse(BaseModel):
    segments: list[TranscriptionSegment]


@asynccontextmanager
async def lifespan(app: FastAPI):
    transcribe.load_model()
    yield


app = FastAPI(title="Whisper GPU Worker", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "whisper_gpu"}


@app.post("/process", response_model=TranscriptionResponse)
async def process_audio_file(file: UploadFile = File(...)):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)

        segments = transcribe.run_transcription(str(tmp_path))
        return TranscriptionResponse(
            segments=[TranscriptionSegment(**s) for s in segments]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and tmp_path.exists():
            os.unlink(tmp_path)
