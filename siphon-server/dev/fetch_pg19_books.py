#!/usr/bin/env python
"""
Load non-fiction books from the PG-19 corpus (deepmind/pg19) into Siphon DB
to fill summarization eval bins 17, 19, and 20.

Bins 16 and 18 are already satisfied by fetch_long_transcripts.py.

Usage:
    PYTHONPATH=src .venv/bin/python -u dev/fetch_pg19_books.py
    PYTHONPATH=src .venv/bin/python -u dev/fetch_pg19_books.py --dry-run
    PYTHONPATH=src .venv/bin/python -u dev/fetch_pg19_books.py --bin 20

Env vars required:
    POSTGRES_PASSWORD    Siphon DB password
    POSTGRES_USERNAME    Siphon DB username
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import time
import urllib.request
from typing import Any

from conduit.async_ import ModelAsync
from siphon_server.database.postgres.connection import SessionLocal
from siphon_server.database.postgres.models import ProcessedContentORM

# ---------------------------------------------------------------------------
# Bins — only the ones still needing fill after the YouTube transcript load
# ---------------------------------------------------------------------------
BINS: list[dict[str, Any]] = [
    {"bin": 17, "min_tok": 60_341,  "max_tok": 81_418,  "need": 4},
    {"bin": 19, "min_tok": 109_856, "max_tok": 148_226, "need": 4},
    {"bin": 20, "min_tok": 148_226, "max_tok": 200_000, "need": 8},
]

LOAD_EXTRA = 3  # overshoot per bin in case some inserts fail

PG_CATALOG_URL = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"
PG_CATALOG_PATH = "/tmp/pg_catalog.csv"

NONFICTION_SUBJECTS = {
    "history", "biography", "science", "technology", "philosophy",
    "economics", "geography", "sociology", "political science",
    "education", "medicine", "agriculture", "law",
}
FICTION_SUBJECTS = {
    "fiction", "poetry", "drama", "music", "juvenile", "short stories",
}

tokenizer = ModelAsync("gpt3")


# ---------------------------------------------------------------------------
# Token counting — ModelAsync directly (avoids ContentData wrapper overhead)
# ---------------------------------------------------------------------------

def count_tokens(text: str) -> int:
    try:
        return asyncio.run(tokenizer.tokenize(text))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# PG catalog: download and filter for non-fiction
# ---------------------------------------------------------------------------

def download_catalog() -> None:
    if os.path.exists(PG_CATALOG_PATH):
        print(f"Catalog cached at {PG_CATALOG_PATH}")
        return
    print(f"Downloading PG catalog → {PG_CATALOG_PATH} ...")
    urllib.request.urlretrieve(PG_CATALOG_URL, PG_CATALOG_PATH)
    print("Done.")


def load_nonfiction_ids() -> dict[int, dict[str, str]]:
    """Returns {pg_id: {title, author, subject, pub_date}} for non-fiction only."""
    result: dict[int, dict[str, str]] = {}
    with open(PG_CATALOG_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_subjects = row.get("Subjects", "").lower()
            if not raw_subjects:
                continue
            # Drop fiction and ambiguous entries
            if any(fs in raw_subjects for fs in FICTION_SUBJECTS):
                continue
            # Must have at least one non-fiction subject
            if not any(nf in raw_subjects for nf in NONFICTION_SUBJECTS):
                continue
            try:
                pg_id = int(row["Text#"])
            except (KeyError, ValueError):
                continue
            result[pg_id] = {
                "title": row.get("Title", ""),
                "author": row.get("Authors", ""),
                "subject": row.get("Subjects", ""),
                "pub_date": row.get("Issued", ""),
            }
    return result


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def load_existing_pg_ids() -> set[int]:
    """All Gutenberg pg_ids already in the DB."""
    db = SessionLocal()
    try:
        rows = (
            db.query(ProcessedContentORM.content_metadata)
            .filter(ProcessedContentORM.source_type == "Gutenberg")
            .all()
        )
        ids: set[int] = set()
        for (meta,) in rows:
            if meta and "pg_id" in meta:
                ids.add(int(meta["pg_id"]))
        return ids
    finally:
        db.close()


def count_existing_in_bin(bin_num: int) -> int:
    """How many Gutenberg records are already loaded for this bin."""
    db = SessionLocal()
    try:
        rows = (
            db.query(ProcessedContentORM.content_metadata)
            .filter(ProcessedContentORM.source_type == "Gutenberg")
            .all()
        )
        return sum(
            1 for (meta,) in rows
            if meta and meta.get("eval_bin") == bin_num
        )
    finally:
        db.close()


def insert_record(
    pg_id: int,
    book_text: str,
    meta: dict[str, str],
    bin_num: int,
    token_count: int,
    dry_run: bool,
) -> bool:
    uri = f"gutenberg:///{pg_id}"
    title = meta.get("title", "")
    author = meta.get("author", "")
    subject = meta.get("subject", "")
    pub_date = meta.get("pub_date", "")

    if dry_run:
        print(f"    [dry-run] {uri}  {token_count:,} tok  \"{title[:60]}\"")
        return True

    now = int(time.time())
    db = SessionLocal()
    try:
        record = ProcessedContentORM(
            uri=uri,
            source_type="Gutenberg",
            original_source=f"https://www.gutenberg.org/ebooks/{pg_id}",
            source_hash=None,
            content_text=book_text,
            content_metadata={
                "pg_id": pg_id,
                "title": title,
                "author": author,
                "subject": subject,
                "publication_date": pub_date,
                "token_count": token_count,
                "eval_bin": bin_num,
            },
            title=title,
            description=f"{author}. {subject}",
            summary="",
            topics=[],
            entities=[],
            tags=[f"eval-bin-{bin_num}", "pg19", "non-fiction"],
            created_at=now,
            updated_at=now,
            embedding=None,
            embed_model=None,
        )
        db.add(record)
        db.commit()
        print(f"    [ok] {uri}  {token_count:,} tok  \"{title[:60]}\"")
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
    parser.add_argument(
        "--bin", type=int, metavar="N",
        help="Process only this bin number (17, 19, or 20)",
    )
    args = parser.parse_args()

    target_bins = BINS if not args.bin else [b for b in BINS if b["bin"] == args.bin]
    if not target_bins:
        sys.exit(f"Error: --bin={args.bin} is not a valid target (valid: 17, 19, 20)")

    # --- Prep ---
    download_catalog()
    nonfiction = load_nonfiction_ids()
    print(f"Non-fiction books in PG catalog: {len(nonfiction):,}")

    existing_pg_ids = load_existing_pg_ids()
    print(f"Existing Gutenberg records in DB: {len(existing_pg_ids)}")

    # Determine per-bin quota accounting for what's already loaded
    active_bins: list[dict[str, Any]] = []
    for b in target_bins:
        already = count_existing_in_bin(b["bin"])
        remaining = max(0, b["need"] - already)
        quota = remaining + LOAD_EXTRA
        print(f"  Bin {b['bin']}: {already} already loaded, need {b['need']}, targeting {quota}")
        if quota > 0:
            active_bins.append({**b, "quota": quota, "loaded": 0})

    if not active_bins:
        print("All target bins already satisfied.")
        return

    # --- Fetch books directly from Project Gutenberg mirror ---
    # deepmind/pg19 uses a HuggingFace loading script (no longer supported).
    # We pull plain-text files directly via HTTP instead.
    #
    # Gutenberg asks: no more than 100 requests/minute. We stay well under that
    # since tokenization dominates per-book time anyway.

    import random
    import urllib.error

    GUTENBERG_TXT_URL = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"
    FETCH_DELAY = 1.0  # seconds between HTTP requests

    # Candidate IDs: non-fiction books not yet in DB, in random order
    candidate_ids = [
        pg_id for pg_id in nonfiction
        if pg_id not in existing_pg_ids
    ]
    rng = random.Random(42)
    rng.shuffle(candidate_ids)

    print(f"\nFetching books from Project Gutenberg ({len(candidate_ids):,} candidates)...")
    print("(Tokenizing each qualifying book — this will take a while)\n")

    for pg_id in candidate_ids:
        if all(b["loaded"] >= b["quota"] for b in active_bins):
            print("All quotas filled.")
            break

        url = GUTENBERG_TXT_URL.format(id=pg_id)
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                pass  # many IDs have no plain-text version; silent skip
            else:
                print(f"  [warn] HTTP {e.code} for pg{pg_id}")
            time.sleep(FETCH_DELAY)
            continue
        except Exception as e:
            print(f"  [warn] fetch failed pg{pg_id}: {e}")
            time.sleep(FETCH_DELAY)
            continue

        time.sleep(FETCH_DELAY)

        # Char pre-filter: bin 17 starts at 60K tokens ≈ 240K chars
        if len(text) < 200_000:
            continue

        tok = count_tokens(text)
        if tok == 0:
            continue

        matched = next(
            (b for b in active_bins if b["min_tok"] <= tok < b["max_tok"] and b["loaded"] < b["quota"]),
            None,
        )
        if matched is None:
            continue

        meta = nonfiction[pg_id]
        print(f"  Bin {matched['bin']}  [{matched['loaded'] + 1}/{matched['quota']}]  pg{pg_id}  {tok:,} tok")
        if insert_record(pg_id, text, meta, matched["bin"], tok, args.dry_run):
            existing_pg_ids.add(pg_id)
            matched["loaded"] += 1

    # --- Summary ---
    print("\n=== Summary ===")
    for b in active_bins:
        status = "OK" if b["loaded"] >= b["need"] else f"SHORT by {b['need'] - b['loaded']}"
        print(f"  Bin {b['bin']}: {b['loaded']} loaded  [{status}]")


if __name__ == "__main__":
    main()
