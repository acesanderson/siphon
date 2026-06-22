---
name: granite-speech-4.1-2b-plus evaluation
description: Results of evaluating IBM granite-speech as a whisper replacement with built-in diarization
type: project
---

Evaluated ibm-granite/granite-speech-4.1-2b-plus as a potential whisper + pyannote replacement.

**Why:** claims to do STT + speaker diarization in one shot.

**Verdict: not production-ready, shelved.**

**Why:**
- Hard 10-minute limit per inference — all real recordings (30-50 min) require chunking
- Over-generates past end-of-speech, requiring manual token budget per chunk
- Diarization (SAA mode) never produced clean multi-speaker output in testing
- Sensitive to audio quality — Zoom recordings degrade badly, locally-recorded audio fares better
- Inherits LLM generation pathology (repetition loops, hallucination) on top of STT

**What works:** the pipeline is correct and short clean audio transcribes accurately. If IBM improves the model, worth retesting.

**How to apply:** don't invest more engineering time on this until the model matures. whisper + pyannote already covers the use case reliably.
