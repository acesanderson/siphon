#!/usr/bin/env python
"""
Fetch long-form YouTube transcripts and load them into Siphon DB.

Targets videos in the 4-20 hour range to fill token bins 16-20
(44K-200K tokens) in the summarization eval dataset.

Discovery uses yt-dlp channel enumeration (zero API quota cost).
YouTube Data API is only used for snippet batch-fetching on successful
transcript hits (1 unit per 50 videos).

Usage:
    # Run with siphon-server venv directly (faster than uv run):
    PYTHONPATH=src .venv/bin/python dev/fetch_long_transcripts.py

    # Dry run:
    PYTHONPATH=src .venv/bin/python dev/fetch_long_transcripts.py --dry-run

    # Single bin:
    PYTHONPATH=src .venv/bin/python dev/fetch_long_transcripts.py --bin 16

Env vars required:
    POSTGRES_PASSWORD      Siphon DB password
    POSTGRES_USERNAME      Siphon DB username

Env vars optional:
    YOUTUBE_API_KEY        Enables batch snippet fetching (saves yt-dlp calls)
    WEBSHARE_USERNAME      Webshare proxy for transcript fetching
    WEBSHARE_PASS
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from typing import Any

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from siphon_server.database.postgres.connection import SessionLocal
from siphon_server.database.postgres.models import ProcessedContentORM

# ---------------------------------------------------------------------------
# Channel sources
# Extend this list with any channel URL that has long-form uploads/streams.
# Both /streams and /videos tabs work; /streams surfaces live recordings.
# ---------------------------------------------------------------------------
CHANNEL_URLS: list[str] = [
    "https://www.youtube.com/@aiDotEngineer/streams",
]

# ---------------------------------------------------------------------------
# Duration bins
# ---------------------------------------------------------------------------
BINS: list[dict[str, Any]] = [
    {"bin": 16, "label": "4-6h",   "min_sec": 4 * 3600,  "max_sec": 6 * 3600,  "target": 15},
    {"bin": 17, "label": "6-8h",   "min_sec": 6 * 3600,  "max_sec": 8 * 3600,  "target": 15},
    {"bin": 18, "label": "8-11h",  "min_sec": 8 * 3600,  "max_sec": 11 * 3600, "target": 15},
    {"bin": 19, "label": "11-15h", "min_sec": 11 * 3600, "max_sec": 15 * 3600, "target": 10},
    {"bin": 20, "label": "15-20h", "min_sec": 15 * 3600, "max_sec": 20 * 3600, "target": 10},
]

MIN_SEC_GLOBAL = min(b["min_sec"] for b in BINS)
MAX_SEC_GLOBAL = max(b["max_sec"] for b in BINS)


# ---------------------------------------------------------------------------
# Channel enumeration via yt-dlp (zero API quota)
# ---------------------------------------------------------------------------

def enumerate_channel(url: str, max_items: int = 200) -> list[dict[str, Any]]:
    """
    List videos from a channel URL using yt-dlp flat extraction.
    Returns list of dicts with at least: id, title, duration (seconds or None).
    Cost: zero YouTube Data API quota.
    """
    opts: dict[str, Any] = {
        "quiet": True,
        "extract_flat": True,
        "playlistend": max_items,
        "ignoreerrors": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return []
    return [e for e in info.get("entries", []) if e and e.get("id")]


def assign_bin(duration_sec: int) -> int | None:
    """Return bin number for a duration, or None if outside all bins."""
    for b in BINS:
        if b["min_sec"] <= duration_sec < b["max_sec"]:
            return b["bin"]
    return None


# ---------------------------------------------------------------------------
# Metadata: yt-dlp single-video extraction (fallback when no API key)
# ---------------------------------------------------------------------------

def get_metadata_ytdlp(video_id: str) -> dict[str, Any]:
    """Full yt-dlp extraction for one video. Slow (~2-3s) but zero quota."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts: dict[str, Any] = {"quiet": True, "ignoreerrors": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}
    return {
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "channel": info.get("channel", ""),
        "duration_sec": info.get("duration", 0),
        "published_at": info.get("upload_date", ""),
    }


# ---------------------------------------------------------------------------
# Metadata: YouTube Data API batch (1 unit per 50 videos, optional)
# ---------------------------------------------------------------------------

def get_metadata_api_batch(
    video_ids: list[str],
    yt: Any,
) -> dict[str, dict[str, Any]]:
    """
    Batch-fetch snippet for up to 50 video IDs via videos.list.
    Returns {video_id: {title, description, channel, published_at}}.
    """
    if not video_ids:
        return {}
    resp = (
        yt.videos()
        .list(part="snippet", id=",".join(video_ids[:50]))
        .execute()
    )
    result: dict[str, dict[str, Any]] = {}
    for item in resp.get("items", []):
        vid = item["id"]
        s = item["snippet"]
        result[vid] = {
            "title": s.get("title", ""),
            "description": s.get("description", ""),
            "channel": s.get("channelTitle", ""),
            "published_at": s.get("publishedAt", ""),
        }
    return result


# ---------------------------------------------------------------------------
# Transcript fetching
# ---------------------------------------------------------------------------

def fetch_transcript(video_id: str, api: YouTubeTranscriptApi) -> str | None:
    """Returns concatenated transcript text, or None if unavailable."""
    try:
        fetched = api.fetch(video_id)
        return " ".join(seg.text for seg in fetched)
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
        return None
    except Exception as e:
        print(f"    [warn] transcript error {video_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def load_existing_uris() -> set[str]:
    db = SessionLocal()
    try:
        rows = (
            db.query(ProcessedContentORM.uri)
            .filter(ProcessedContentORM.source_type == "YouTube")
            .all()
        )
        return {row.uri for row in rows}
    finally:
        db.close()


def insert_record(
    video_id: str,
    transcript: str,
    meta: dict[str, Any],
    bin_num: int,
    dry_run: bool,
) -> bool:
    uri = f"youtube:///{video_id}"
    duration_sec = meta.get("duration_sec", 0)
    h, rem = divmod(duration_sec, 3600)
    label = f"{h}h{rem // 60:02d}m"

    if dry_run:
        print(f"    [dry-run] {uri}  {label}  \"{meta.get('title', '')[:60]}\"")
        return True

    now = int(time.time())
    db = SessionLocal()
    try:
        record = ProcessedContentORM(
            uri=uri,
            source_type="YouTube",
            original_source=f"https://www.youtube.com/watch?v={video_id}",
            source_hash=None,
            content_text=transcript,
            content_metadata={
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "domain": "youtube.com",
                "channel": meta.get("channel", ""),
                "duration": duration_sec,
                "published_at": meta.get("published_at", ""),
                "eval_bin": bin_num,
            },
            title=meta.get("title", ""),
            description=meta.get("description", "")[:4000],
            summary="",
            topics=[],
            entities=[],
            tags=[f"eval-bin-{bin_num}"],
            created_at=now,
            updated_at=now,
            embedding=None,
            embed_model=None,
        )
        db.add(record)
        db.commit()
        print(f"    [ok] {uri}  {label}  \"{meta.get('title', '')[:60]}\"")
        return True
    except Exception as e:
        db.rollback()
        print(f"    [error] {uri}: {e}")
        return False
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--bin", type=int, metavar="N", help="Process only this bin number (16-20)")
    parser.add_argument(
        "--channel",
        metavar="URL",
        action="append",
        dest="extra_channels",
        help="Additional channel URL to enumerate (can repeat)",
    )
    args = parser.parse_args()

    # Build channel list
    channels = list(CHANNEL_URLS)
    if args.extra_channels:
        channels.extend(args.extra_channels)

    # Optional API client for batch snippet fetching
    api_key = os.environ.get("YOUTUBE_API_KEY")
    yt = None
    if api_key:
        from googleapiclient.discovery import build
        try:
            yt = build("youtube", "v3", developerKey=api_key)
            print("YouTube Data API: available (batch snippet mode)")
        except Exception as e:
            print(f"YouTube Data API: failed to init ({e}), falling back to yt-dlp")

    # Transcript API
    webshare_user = os.environ.get("WEBSHARE_USERNAME")
    webshare_pass = os.environ.get("WEBSHARE_PASS")
    if webshare_user and webshare_pass:
        from youtube_transcript_api.proxies import WebshareProxyConfig
        transcript_api = YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=webshare_user,
                proxy_password=webshare_pass,
            )
        )
        print("Transcript API: Webshare proxy active")
    else:
        transcript_api = YouTubeTranscriptApi()
        print("Transcript API: no proxy")

    existing_uris = load_existing_uris()
    print(f"Existing YouTube records in DB: {len(existing_uris)}\n")

    target_bins = BINS if not args.bin else [b for b in BINS if b["bin"] == args.bin]
    if not target_bins:
        sys.exit(f"Error: no bin matches --bin={args.bin} (valid: 16-20)")

    # ---------------------------------------------------------------------------
    # Step 1: enumerate all channels, collect candidates binned by duration
    # ---------------------------------------------------------------------------
    # bin_num -> list of {id, title, duration_sec, channel}
    binned: dict[int, list[dict[str, Any]]] = {b["bin"]: [] for b in target_bins}

    for channel_url in channels:
        print(f"Enumerating channel: {channel_url}")
        entries = enumerate_channel(channel_url)
        print(f"  Found {len(entries)} entries")

        for entry in entries:
            vid = entry.get("id")
            if not vid:
                continue
            uri = f"youtube:///{vid}"
            if uri in existing_uris:
                continue

            duration_sec = entry.get("duration")
            if not duration_sec:
                continue  # duration unavailable in flat extraction, skip

            bin_num = assign_bin(int(duration_sec))
            if bin_num is None or bin_num not in binned:
                continue

            binned[bin_num].append({
                "id": vid,
                "title": entry.get("title", ""),
                "duration_sec": int(duration_sec),
                "channel": entry.get("channel") or entry.get("uploader", ""),
            })

        print(f"  Binned candidates: { {b: len(binned[b]) for b in binned} }\n")

    # ---------------------------------------------------------------------------
    # Step 2: process each bin
    # ---------------------------------------------------------------------------
    totals: dict[int, tuple[int, int]] = {}

    for bin_spec in target_bins:
        bin_num = bin_spec["bin"]
        label = bin_spec["label"]
        target = bin_spec["target"]
        candidates = binned[bin_num]

        print(f"=== Bin {bin_num} ({label}) — {len(candidates)} candidates, target: {target} ===")

        loaded = 0
        # Collect IDs of successful transcript fetches to batch-fetch snippets
        pending_snippet: list[tuple[str, str, dict[str, Any]]] = []  # (vid, transcript, partial_meta)

        for entry in candidates:
            if loaded >= target:
                break
            vid = entry["id"]
            uri = f"youtube:///{vid}"
            if uri in existing_uris:
                continue

            print(f"  [{loaded + 1}/{target}] {vid} — '{entry['title'][:50]}'")
            transcript = fetch_transcript(vid, transcript_api)
            if not transcript:
                print(f"    [skip] no transcript")
                continue

            # Build metadata — use API batch if available, else yt-dlp
            if yt:
                # Defer snippet fetch; batch later
                pending_snippet.append((vid, transcript, entry))
            else:
                full = get_metadata_ytdlp(vid)
                # Merge flat-extraction title/channel as fallback
                if not full["title"]:
                    full["title"] = entry["title"]
                if not full["channel"]:
                    full["channel"] = entry["channel"]
                if insert_record(vid, transcript, full, bin_num, args.dry_run):
                    existing_uris.add(uri)
                    loaded += 1

        # Batch snippet fetch via API (when yt is available)
        if yt and pending_snippet:
            vids = [x[0] for x in pending_snippet]
            # Process in batches of 50
            for i in range(0, len(vids), 50):
                batch_ids = vids[i : i + 50]
                try:
                    snippets = get_metadata_api_batch(batch_ids, yt)
                except Exception as e:
                    print(f"  [warn] API snippet fetch failed: {e}, falling back to yt-dlp")
                    snippets = {}

                for vid, transcript, partial in pending_snippet[i : i + 50]:
                    if loaded >= target:
                        break
                    uri = f"youtube:///{vid}"
                    if uri in existing_uris:
                        continue
                    if vid in snippets:
                        meta = {
                            **snippets[vid],
                            "duration_sec": partial["duration_sec"],
                        }
                    else:
                        # Fallback to yt-dlp for this video
                        meta = get_metadata_ytdlp(vid)
                        if not meta["title"]:
                            meta["title"] = partial["title"]

                    if insert_record(vid, transcript, meta, bin_num, args.dry_run):
                        existing_uris.add(uri)
                        loaded += 1

        totals[bin_num] = (loaded, target)
        print(f"\nBin {bin_num} complete: {loaded}/{target} loaded\n")

    print("=== Summary ===")
    for bin_num, (loaded, target) in totals.items():
        status = "OK" if loaded >= target else f"SHORT by {target - loaded}"
        print(f"  Bin {bin_num}: {loaded}/{target}  [{status}]")


if __name__ == "__main__":
    main()
