from __future__ import annotations

import os

from client import YouTubeClient

API_KEY = os.getenv("YOUTUBE_API_KEY2")

if not API_KEY:
    raise ValueError("YOUTUBE_API_KEY2 environment variable not set")


def test_video():
    """Test fetching a single video."""
    client = YouTubeClient(API_KEY)
    video_id = "OkEGJ5G3foU"

    print("=" * 60)
    print("TEST: Get Video")
    print("=" * 60)

    videos = client.get_videos(video_id)

    if not videos:
        print("❌ No video found")
        return

    video = videos[0]
    print(f"✅ Video fetched successfully")
    print(f"   ID: {video.id}")
    print(f"   Title: {video.title}")
    print(f"   Channel: {video.channel_title}")
    print(f"   Duration: {video.duration}")
    print(f"   Views: {video.view_count:,}")
    print(f"   Likes: {video.like_count:,}")
    print(f"   Comments: {video.comment_count:,}")
    print(f"   Published: {video.published_at}")
    print()


def test_channel():
    """Test fetching a channel.

    Note: @aiDotEngineer is a handle. We'll get the channel ID from the video first.
    """
    client = YouTubeClient(API_KEY)

    # First, get the video to extract channel_id
    video_id = "OkEGJ5G3foU"
    videos = client.get_videos(video_id)

    if not videos:
        print("❌ Could not get video to extract channel ID")
        return

    channel_id = videos[0].channel_id

    print("=" * 60)
    print("TEST: Get Channel")
    print("=" * 60)

    channels = client.get_channels(channel_ids=channel_id)

    if not channels:
        print("❌ No channel found")
        return

    channel = channels[0]
    print(f"✅ Channel fetched successfully")
    print(f"   ID: {channel.id}")
    print(f"   Title: {channel.title}")
    print(f"   Custom URL: {channel.custom_url}")
    print(f"   Subscribers: {channel.subscriber_count:,}")
    print(f"   Videos: {channel.video_count:,}")
    print(f"   Total views: {channel.view_count:,}")
    print(f"   Country: {channel.country}")
    print(f"   Published: {channel.published_at}")
    print()


def test_playlist():
    """Test fetching playlist and its items."""
    client = YouTubeClient(API_KEY)
    playlist_id = "PLcfpQ4tk2k0V9bxtzGspxhx3CfxZASk0u"

    print("=" * 60)
    print("TEST: Get Playlist")
    print("=" * 60)

    playlists = client.get_playlists(playlist_ids=playlist_id)

    if not playlists:
        print("❌ No playlist found")
        return

    playlist = playlists[0]
    print(f"✅ Playlist fetched successfully")
    print(f"   ID: {playlist.id}")
    print(f"   Title: {playlist.title}")
    print(f"   Channel: {playlist.channel_title}")
    print(f"   Item count: {playlist.item_count}")
    print(f"   Published: {playlist.published_at}")
    print()

    print("=" * 60)
    print("TEST: Get Playlist Items (first 5)")
    print("=" * 60)

    items = client.get_playlist_items(playlist_id, n_results=5)

    if not items:
        print("❌ No playlist items found")
        return

    print(f"✅ Fetched {len(items)} playlist items")
    for i, item in enumerate(items, 1):
        print(f"\n   {i}. {item.title}")
        print(f"      Video ID: {item.video_id}")
        print(f"      Position: {item.position}")
        print(f"      Published: {item.published_at}")
    print()


def test_search():
    """Test search functionality."""
    client = YouTubeClient(API_KEY)
    query = "AI engineering tutorial"

    print("=" * 60)
    print("TEST: Search")
    print("=" * 60)

    results = client.search(query, n_results=5)

    if not results:
        print("❌ No search results found")
        return

    print(f"✅ Search returned {len(results)} results")
    for i, result in enumerate(results, 1):
        print(f"\n   {i}. {result.title}")
        print(f"      Type: {result.kind}")
        print(f"      Channel: {result.channel_title}")
        print(f"      Published: {result.published_at}")
    print()


if __name__ == "__main__":
    test_video()
    test_channel()
    test_playlist()
    test_search()
    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)
