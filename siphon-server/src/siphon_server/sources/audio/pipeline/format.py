from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def format_simple(chunks: list[dict]) -> str:
    """
    Format transcript chunks without speaker labels.

    Args:
        chunks: Output from transcribe() — list of {text, start, end}

    Returns:
        str: Formatted transcript with timestamps, e.g. "[0.0s] text of segment"
    """
    if not chunks:
        return ""
    lines = []
    for chunk in chunks:
        start = chunk["start"]
        text = chunk["text"].strip()
        if text:
            lines.append(f"[{start:.1f}s] {text}")
    return "\n".join(lines)


def format(annotated_transcript, group_by_speaker=True):
    """
    Format a diarized annotated transcript into readable text.

    Args:
        annotated_transcript: Output from combine()
        group_by_speaker: Whether to group consecutive words by same speaker

    Returns:
        str: Formatted transcript
    """
    if not annotated_transcript:
        return ""

    if not group_by_speaker:
        logger.warning(
            "[FORMAT] Formatting without grouping by speaker may produce less readable output."
        )
        lines = []
        for item in annotated_transcript:
            timestamp = f"[{item['start_time']:.1f}s]"
            lines.append(f"{timestamp} {item['speaker']}: {item['word']}")
        return "\n".join(lines)

    logger.debug("[FORMAT] Formatting transcript by grouping words by speaker.")
    lines = []
    current_speaker = None
    current_words = []
    current_start_time = None

    for item in annotated_transcript:
        speaker = item["speaker"]

        if speaker != current_speaker:
            if current_speaker is not None and current_words:
                timestamp = f"[{current_start_time:.1f}s]"
                text = " ".join(current_words)
                lines.append(f"{timestamp} {current_speaker}: {text}")
            current_speaker = speaker
            current_words = [item["word"]]
            current_start_time = item["start_time"]
        else:
            current_words.append(item["word"])

    logger.debug("[FORMAT] Finalizing transcript for last speaker.")
    if current_speaker is not None and current_words:
        timestamp = f"[{current_start_time:.1f}s]"
        text = " ".join(current_words)
        lines.append(f"{timestamp} {current_speaker}: {text}")

    return "\n".join(lines)
