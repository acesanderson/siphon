from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, HTTPException, File
from pydantic import BaseModel
import tempfile
import os
from pathlib import Path

import diarize


class DiarizationSegment(BaseModel):
    start: float
    end: float
    speaker: str


class DiarizationResponse(BaseModel):
    segments: list[DiarizationSegment]


@asynccontextmanager
async def lifespan(app: FastAPI):
    diarize.load_model()
    yield


app = FastAPI(title="Diarization GPU Worker", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "diarization_gpu"}


@app.post("/process", response_model=DiarizationResponse)
async def process_audio_file(file: UploadFile = File(...)):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)

        annotation = diarize.run_diarization(tmp_path)
        segments = [
            DiarizationSegment(start=turn.start, end=turn.end, speaker=speaker)
            for turn, _, speaker in annotation.itertracks(yield_label=True)
        ]
        return DiarizationResponse(segments=segments)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and tmp_path.exists():
            os.unlink(tmp_path)
