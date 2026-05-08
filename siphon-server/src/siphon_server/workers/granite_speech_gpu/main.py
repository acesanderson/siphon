from contextlib import asynccontextmanager
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

import transcribe


class GraniteSegment(BaseModel):
    text: str
    speaker: str | None


class GraniteResponse(BaseModel):
    segments: list[GraniteSegment]
    raw_text: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    transcribe.start_loading()
    yield


app = FastAPI(title="Granite Speech GPU Worker", lifespan=lifespan)


@app.get("/health")
async def health_check():
    if err := transcribe.get_error():
        return {"status": "error", "detail": err}
    if not transcribe.is_ready():
        return {"status": "loading", "service": "granite_speech_gpu"}
    return {"status": "healthy", "service": "granite_speech_gpu"}


@app.post("/process", response_model=GraniteResponse)
async def process_audio_file(file: UploadFile = File(...)):
    if not transcribe.is_ready():
        raise HTTPException(status_code=503, detail="Model still loading, try again shortly")
    tmp_path = None
    try:
        suffix = Path(file.filename).suffix if file.filename else ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)

        segments, raw_text = transcribe.run_transcription(str(tmp_path))
        return GraniteResponse(
            segments=[GraniteSegment(**s) for s in segments],
            raw_text=raw_text,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and tmp_path.exists():
            os.unlink(tmp_path)
