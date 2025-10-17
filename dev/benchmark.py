from pathlib import Path
from siphon.main.siphon import siphon


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

# Now that we have our list of videos sorted by duration, we can use it in our benchmarks
processed = []
for index, video in enumerate(videos):
    print(f"Processing video {index + 1}/{len(videos)}")
    url, duration = video
    pc = siphon(url)
    title = pc.title
    processed.append(
        {
            "title": title,
            "duration": duration,
            "url": url,
            "processed": pc,
        }
    )
