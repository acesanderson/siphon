import logging
import re
import threading

import numpy as np
import torch
import torchaudio
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MODEL_NAME = "ibm-granite/granite-speech-4.1-2b-plus"
TARGET_SR = 16000
SAA_PROMPT = (
    "<|audio|> Speaker attribution: Transcribe and denote who is speaking by adding "
    "[Speaker 1]: and [Speaker 2]: tags before speaker turns."
)
SYSTEM_PROMPT = (
    "Knowledge Cutoff Date: April 2024.\n"
    "Today's Date: May 2026.\n"
    "You are Granite, developed by IBM. You are a helpful AI assistant"
)

_model = None
_processor = None
_ready = False
_error: str | None = None


def load_model_background():
    global _model, _processor, _ready, _error
    try:
        logger.info("[GRANITE] Loading processor...")
        _processor = AutoProcessor.from_pretrained(MODEL_NAME)
        logger.info("[GRANITE] Loading model...")
        _model = AutoModelForSpeechSeq2Seq.from_pretrained(
            MODEL_NAME,
            device_map="cuda",
            torch_dtype=torch.bfloat16,
        )
        _model.eval()
        _ready = True
        logger.info("[GRANITE] Model ready.")
    except Exception as e:
        _error = str(e)
        logger.error(f"[GRANITE] Model load failed: {e}")


def start_loading():
    thread = threading.Thread(target=load_model_background, daemon=True)
    thread.start()


def is_ready() -> bool:
    return _ready


def get_error() -> str | None:
    return _error


def _load_audio(audio_path: str) -> np.ndarray:
    waveform, sample_rate = torchaudio.load(audio_path)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sample_rate != TARGET_SR:
        resampler = torchaudio.transforms.Resample(sample_rate, TARGET_SR)
        waveform = resampler(waveform)
    return waveform.squeeze(0).numpy()  # (time,) float32 numpy array


def _parse_saa(text: str) -> list[dict]:
    parts = re.split(r"(\[Speaker \d+\])", text)
    segments = []
    current_speaker = None
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if re.match(r"\[Speaker \d+\]$", part):
            current_speaker = part[1:-1]  # strip []
        else:
            content = re.sub(r"^:\s*", "", part)
            if content:
                segments.append({"text": content, "speaker": current_speaker})
    return segments


@torch.inference_mode()
def run_transcription(audio_path: str) -> tuple[list[dict], str]:
    if not _ready:
        raise RuntimeError("Model not yet loaded")

    audio = _load_audio(audio_path)
    tokenizer = _processor.tokenizer

    chat = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": SAA_PROMPT},
    ]
    prompt_text = tokenizer.apply_chat_template(
        chat, tokenize=False, add_generation_prompt=True
    )

    inputs = _processor(prompt_text, audio, device="cuda", return_tensors="pt").to("cuda")
    outputs = _model.generate(**inputs, max_new_tokens=4000, do_sample=False, num_beams=1)
    new_tokens = outputs[0, inputs["input_ids"].shape[-1]:]
    raw_text = tokenizer.decode(new_tokens, add_special_tokens=False, skip_special_tokens=True)

    segments = _parse_saa(raw_text)
    return segments, raw_text
