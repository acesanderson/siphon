# YouTube API Client Usage Guide

A minimal, read-only Python client for the YouTube Data API v3 with clean abstractions, automatic pagination, rate limiting, and retry logic.

## Setup

### Get an API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable YouTube Data API v3
4. Create credentials (API Key)
5. Set environment variable:

```bash
export YOUTUBE_API_KEY2="your-api-key-here"
```

### Initialize Client

```python
import os
from client import YouTubeClient

api_key = os.getenv("YOUTUBE_API_KEY2")
client = YouTubeClient(api_key)
```

## Core Methods

### Get Videos

Fetch video data by ID(s). Returns list of `Video` objects.

```python
# Single video
videos = client.get_videos("OkEGJ5G3foU")
video = videos[0]

print(video.title)              # Video title
print(video.channel_title)      # Channel name
print(video.duration)           # timedelta object
print(video.view_count)         # Integer
print(video.like_count)         # Integer
print(video.published_at)       # datetime object
print(video.description)        # Full description
print(video.tags)               # List of tags

# Multiple videos
videos = client.get_videos(["id1", "id2", "id3"])
for video in videos:
    print(f"{video.title}: {video.view_count:,} views")
```

**Available Video fields:**
- `id`, `title`, `description`
- `channel_id`, `channel_title`
- `published_at` (datetime)
- `view_count`, `like_count`, `comment_count` (int)
- `duration` (timedelta)
- `definition` ('hd' or 'sd')
- `caption` (bool)
- `licensed_content` (bool)
- `tags` (list[str])
- `category_id`, `default_language`, `default_audio_language`

### Get Channels

Fetch channel data by ID(s) or username(s). Returns list of `Channel` objects.

```python
# By channel ID
channels = client.get_channels(channel_ids="UCLKPca3kwwd-B59HNr-_lvA")
channel = channels[0]

print(channel.title)            # Channel name
print(channel.subscriber_count) # Integer
print(channel.video_count)      # Total videos
print(channel.view_count)       # Total views
print(channel.custom_url)       # @username
print(channel.description)      # Channel description

# By username (legacy usernames only)
channels = client.get_channels(usernames="GoogleDevelopers")

# Multiple channels
channels = client.get_channels(channel_ids=["id1", "id2"])
```

**Available Channel fields:**
- `id`, `title`, `description`
- `custom_url` (handle like @username)
- `published_at` (datetime)
- `subscriber_count`, `video_count`, `view_count` (int)
- `country`

### Get Playlists

Fetch playlist data by ID(s) or channel. Returns list of `Playlist` objects.

```python
# By playlist ID
playlists = client.get_playlists(playlist_ids="PLcfpQ4tk2k0V9bxtzGspxhx3CfxZASk0u")
playlist = playlists[0]

print(playlist.title)           # Playlist name
print(playlist.item_count)      # Number of videos
print(playlist.channel_title)   # Owner channel
print(playlist.description)     # Playlist description

# Get all playlists for a channel
playlists = client.get_playlists(channel_id="UCLKPca3kwwd-B59HNr-_lvA")
for playlist in playlists:
    print(f"{playlist.title}: {playlist.item_count} videos")
```

**Available Playlist fields:**
- `id`, `title`, `description`
- `channel_id`, `channel_title`
- `published_at` (datetime)
- `item_count` (int)

### Get Playlist Items

Fetch videos in a playlist with automatic pagination. Returns list of `PlaylistItem` objects.

```python
# Get first 10 items (default)
items = client.get_playlist_items("PLcfpQ4tk2k0V9bxtzGspxhx3CfxZASk0u")

# Get up to 50 items
items = client.get_playlist_items("PLcfpQ4tk2k0V9bxtzGspxhx3CfxZASk0u", n_results=50)

# Get all items (up to 200 max)
items = client.get_playlist_items("PLcfpQ4tk2k0V9bxtzGspxhx3CfxZASk0u", n_results=200)

for item in items:
    print(f"{item.position}: {item.title}")
    print(f"   Video ID: {item.video_id}")
```

**Available PlaylistItem fields:**
- `id`, `playlist_id`, `video_id`
- `title`, `description`
- `channel_id`, `channel_title`
- `published_at` (datetime)
- `position` (int - order in playlist)

### Search

Search for videos, channels, or playlists. Returns list of `SearchResult` objects.

```python
# Search for videos (default)
results = client.search("python tutorial")

# Search with more results
results = client.search("python tutorial", n_results=25)

# Search for channels
results = client.search("AI engineering", search_type="channel")

# Search for playlists
results = client.search("machine learning", search_type="playlist")

# Search multiple types
results = client.search("pytorch", search_type=["video", "channel"])

# Search with ordering
results = client.search("AI", order="viewCount")  # Most viewed
results = client.search("AI", order="date")       # Most recent
results = client.search("AI", order="rating")     # Highest rated

# Additional filters
results = client.search(
    "python",
    n_results=20,
    order="relevance",
    regionCode="US",
    relevanceLanguage="en"
)

for result in results:
    print(f"[{result.kind}] {result.title}")
    print(f"   Channel: {result.channel_title}")
```

**Available SearchResult fields:**
- `id`, `kind` ('video', 'channel', or 'playlist')
- `title`, `description`
- `published_at` (datetime)
- `channel_id`, `channel_title`

**Search order options:**
- `relevance` (default)
- `date` (most recent)
- `rating` (highest rated)
- `viewCount` (most viewed)
- `title` (alphabetical)

## Common Patterns

### Extract video ID from URL

```python
def extract_video_id(url: str) -> str:
    """Extract video ID from YouTube URL."""
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return url  # Assume it's already an ID

video_id = extract_video_id("https://www.youtube.com/watch?v=OkEGJ5G3foU")
videos = client.get_videos(video_id)
```

### Extract playlist ID from URL

```python
def extract_playlist_id(url: str) -> str:
    """Extract playlist ID from YouTube URL."""
    if "list=" in url:
        return url.split("list=")[1].split("&")[0]
    return url  # Assume it's already an ID

playlist_id = extract_playlist_id("https://www.youtube.com/watch?v=xxx&list=PLcfpQ4tk2k0V9bxtzGspxhx3CfxZASk0u")
items = client.get_playlist_items(playlist_id)
```

### Get channel from video

```python
# Get video to extract channel ID
videos = client.get_videos("OkEGJ5G3foU")
channel_id = videos[0].channel_id

# Fetch full channel data
channels = client.get_channels(channel_ids=channel_id)
channel = channels[0]
```

### Batch process videos

```python
video_ids = ["id1", "id2", "id3", "id4", "id5"]

# Single request (efficient)
videos = client.get_videos(video_ids)

for video in videos:
    print(f"{video.title}: {video.view_count:,} views")
```

### Search and get full video details

```python
# Search returns limited data
results = client.search("AI agents", n_results=10)

# Extract video IDs
video_ids = [r.id for r in results if r.kind == "video"]

# Get full video data with statistics
videos = client.get_videos(video_ids)

for video in videos:
    print(f"{video.title}")
    print(f"  Duration: {video.duration}")
    print(f"  Views: {video.view_count:,}")
```

### Format duration for display

```python
def format_duration(td):
    """Convert timedelta to readable format."""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"

videos = client.get_videos("OkEGJ5G3foU")
video = videos[0]
print(f"Duration: {format_duration(video.duration)}")  # "2:42:28"
```

## Error Handling

The client raises `YouTubeAPIError` for API failures.

```python
from client import YouTubeAPIError

try:
    videos = client.get_videos("invalid_id")
except YouTubeAPIError as e:
    print(f"API error: {e}")
```

**Common errors:**
- Invalid API key: `HTTP 400: API key not valid`
- Quota exceeded: `HTTP 403: quotaExceeded`
- Video not found: Returns empty list (not an error)
- Rate limit: Automatically retried with backoff

## Client Features

### Automatic Pagination

Search and playlist items automatically handle pagination up to the max limit:

```python
# Makes multiple API calls behind the scenes if needed
items = client.get_playlist_items("playlist_id", n_results=100)  # Up to 200 max
results = client.search("query", n_results=75)  # Up to 200 max
```

### Rate Limiting

Client automatically enforces 5 requests/second to avoid quota issues.

### Retry Logic

Failed requests (429, 5xx errors) are retried 3 times with exponential backoff (1s, 2s, 4s).

### Timeout

All requests timeout after 10 seconds by default:

```python
# Custom timeout
client = YouTubeClient(api_key, timeout=30)
```

## API Quota Considerations

YouTube API has daily quota limits (10,000 units/day by default).

**Cost per operation:**
- `get_videos`: 1 unit per request (up to 50 videos)
- `get_channels`: 1 unit per request
- `get_playlists`: 1 unit per request
- `get_playlist_items`: 1 unit per request (50 items)
- `search`: 100 units per request (50 results)

**Tips to conserve quota:**
- Batch video/channel requests when possible
- Cache results locally
- Use search sparingly (100 units per call)
- Prefer direct ID lookups over search when IDs are known

## Complete Example

```python
import os
from client import YouTubeClient

# Initialize
api_key = os.getenv("YOUTUBE_API_KEY2")
client = YouTubeClient(api_key)

# Search for recent AI videos
results = client.search("AI engineering", n_results=20, order="date")

# Filter to videos only
video_ids = [r.id for r in results if r.kind == "video"]

# Get full video details
videos = client.get_videos(video_ids)

# Analyze
for video in videos:
    engagement = (video.like_count / video.view_count * 100) if video.view_count > 0 else 0
    print(f"{video.title}")
    print(f"  Channel: {video.channel_title}")
    print(f"  Views: {video.view_count:,}")
    print(f"  Engagement: {engagement:.2f}%")
    print()
```
