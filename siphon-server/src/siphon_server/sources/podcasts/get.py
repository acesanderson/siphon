import difflib
import re
import sys
from html import unescape
from xml.etree import ElementTree as ET

import requests


UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"
SAMPLE_PODCAST_URL = "https://podcasts.apple.com/us/podcast/our-2026-creator-economy-predictions/id1379942034?i=1000743302938"


def _get(url: str) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r


def _extract_podcast_id(apple_url: str) -> str:
    m = re.search(r"id(\d+)", apple_url)
    if not m:
        raise ValueError("Could not find podcast id (id##########) in the URL.")
    return m.group(1)


def _extract_apple_episode_title(apple_url: str) -> str:
    html = _get(apple_url).text

    # Prefer og:title; Apple pages typically have it.
    m = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if not m:
        # Fallback: <title> tag
        m = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)

    if not m:
        raise RuntimeError(
            "Could not extract episode title from the Apple Podcasts page."
        )

    title = unescape(m.group(1)).strip()

    # Apple often formats og:title like: "Episode Name on Apple Podcasts"
    title = re.sub(r"\s+on Apple Podcasts\s*$", "", title, flags=re.IGNORECASE).strip()
    return title


def _lookup_feed_url(podcast_id: str) -> str:
    data = _get(f"https://itunes.apple.com/lookup?id={podcast_id}").json()
    results = data.get("results") or []
    if not results or "feedUrl" not in results[0]:
        raise RuntimeError("Could not get feedUrl from iTunes lookup response.")
    return results[0]["feedUrl"]


def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"[\s\u00a0]+", " ", s)
    s = re.sub(r"[“”]", '"', s)
    s = re.sub(r"[’]", "'", s)
    return s.strip()


def apple_episode_url_to_audio_url(apple_episode_url: str) -> str:
    podcast_id = _extract_podcast_id(apple_episode_url)
    feed_url = _lookup_feed_url(podcast_id)

    episode_title = _extract_apple_episode_title(apple_episode_url)
    target = _norm(episode_title)

    rss = _get(feed_url).content
    root = ET.fromstring(rss)

    items = root.findall(".//item")
    if not items:
        raise RuntimeError("No <item> entries found in RSS feed.")

    best_audio = None
    best_score = -1.0
    best_rss_title = None

    for item in items:
        t = item.findtext("title") or ""
        rss_title = _norm(t)

        # similarity score
        score = difflib.SequenceMatcher(None, target, rss_title).ratio()

        # small boost if one contains the other
        if target and (target in rss_title or rss_title in target):
            score += 0.15

        enclosure = item.find("enclosure")
        if enclosure is None or "url" not in enclosure.attrib:
            continue

        if score > best_score:
            best_score = score
            best_audio = enclosure.attrib["url"]
            best_rss_title = t.strip()

    if not best_audio or best_score < 0.60:
        raise RuntimeError(
            "Could not confidently match the Apple episode page to an RSS item.\n"
            f"Apple title: {episode_title!r}\n"
            f"Best RSS title: {best_rss_title!r}\n"
            f"Match score: {best_score:.3f}\n"
            "This can happen if the feed title differs a lot from Apple’s display title."
        )

    return best_audio


def download(url: str, out_path: str) -> None:
    with _get(url) as r:
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get.py <apple_episode_url> [--download <outfile>]")
        sys.exit(2)

    apple_url = sys.argv[1]
    audio_url = apple_episode_url_to_audio_url(apple_url)
    print(audio_url)

    if "--download" in sys.argv:
        i = sys.argv.index("--download")
        out = sys.argv[i + 1] if i + 1 < len(sys.argv) else "episode_audio"
        download(audio_url, out)
