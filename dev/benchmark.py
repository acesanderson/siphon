from pathlib import Path
from siphon.main.siphon import siphon
from siphon.cli.cli_params import CLIParams
from time import sleep
from youtube_transcript_api._errors import IpBlocked
import random


def convert_duration(original: str) -> str:
    """
    The durations are in the format "1:35:20" or "45:10" (MM:SS), etc.
    Standardize them to "HH:MM:SS".
    """
    parts = original.split(":")
    if len(parts) == 2:
        # MM:SS format
        return f"00:{parts[0].zfill(2)}:{parts[1].zfill(2)}"
    elif len(parts) == 3:
        # HH:MM:SS format
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2].zfill(2)}"
    else:
        raise ValueError(f"Unexpected duration format: {original}")


# Load video titles and durations from a text file
video_file = Path(__file__).parent / "youtube_videos.txt"
# Read video titles and durations from file
videos = [tuple(l.split("\t")) for l in video_file.read_text().strip().splitlines()]
# Convert durations to standardized format
videos = [(title, convert_duration(duration)) for title, duration in videos]
# Sort by second element in each tuple
videos.sort(key=lambda x: x[1])

# Start processing videos
processed = []

MAX_RETRIES = 6  # Total retry attempts
BASE_DELAY = 30  # Start with 30 seconds
MAX_DELAY = 15 * 60  # Cap at 15 minutes

for index, (url, duration) in enumerate(videos):
    attempt = 0
    while attempt <= MAX_RETRIES:
        try:
            print(f"Processing video {index + 1}/{len(videos)} (attempt {attempt + 1})")
            cli_params = CLIParams(source=url, cache_options="u")
            pc = siphon(cli_params)
            title = pc.title
            processed.append(
                {"title": title, "duration": duration, "url": url, "processed": pc}
            )
            sleep(15)  # brief pause between videos
            break  # success → exit retry loop

        except IpBlocked as e:
            attempt += 1
            if attempt > MAX_RETRIES:
                print(
                    f"Giving up on {url} after {MAX_RETRIES} attempts: still IP-blocked."
                )
                break

            # Exponential backoff: delay doubles each attempt (capped)
            delay = min(BASE_DELAY * (2 ** (attempt - 1)), MAX_DELAY)

            # Add jitter (±20%) so multiple runs don't retry in sync
            jitter = random.uniform(0.8, 1.2)
            delay = int(delay * jitter)

            print(f"IP blocked on {url} (attempt {attempt}/{MAX_RETRIES}).")
            print(
                f"Sleeping for {delay // 60} minutes, {delay % 60} seconds before retrying..."
            )
            sleep(delay)

        except Exception as e:
            print(f"Unexpected error on {url}: {e}")
            break
