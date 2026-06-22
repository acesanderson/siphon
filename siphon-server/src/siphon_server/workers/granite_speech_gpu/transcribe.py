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
MAX_DURATION_SEC = 300  # 5-min window keeps context stable; 10-min limit is theoretical max
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
            dtype=torch.bfloat16,
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
    max_samples = MAX_DURATION_SEC * TARGET_SR
    if waveform.shape[-1] > max_samples:
        logger.warning(f"[GRANITE] audio {waveform.shape[-1]/TARGET_SR:.0f}s exceeds {MAX_DURATION_SEC}s limit — truncating")
        waveform = waveform[..., :max_samples]
    return waveform.numpy()  # (1, time) float32 numpy array


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
    audio_duration_sec = audio.shape[-1] / TARGET_SR
    # ~3 tokens/second of speech, 20% headroom, hard ceiling of 2000
    max_new_tokens = min(2000, int(audio_duration_sec * 3 * 1.2))
    logger.info(f"[GRANITE] audio shape={audio.shape} duration={audio_duration_sec:.1f}s max_new_tokens={max_new_tokens}")

    tokenizer = _processor.tokenizer
    chat = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": SAA_PROMPT},
    ]
    prompt_text = tokenizer.apply_chat_template(
        chat, tokenize=False, add_generation_prompt=True
    )
    logger.info(f"[GRANITE] prompt_text[:200]={prompt_text[:200]!r}")

    inputs = _processor(prompt_text, audio, sampling_rate=TARGET_SR, return_tensors="pt").to("cuda")
    logger.info(f"[GRANITE] input keys={list(inputs.keys())} input_ids shape={inputs['input_ids'].shape}")

    outputs = _model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=False,
        num_beams=1,
        repetition_penalty=1.5,
    )
    new_tokens = outputs[0, inputs["input_ids"].shape[-1]:]
    raw_text = tokenizer.decode(new_tokens, add_special_tokens=False, skip_special_tokens=True)
    logger.info(f"[GRANITE] raw_text[:200]={raw_text[:200]!r}")

    segments = _parse_saa(raw_text)
    return segments, raw_text
