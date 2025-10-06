"""
This is our main enum for all source types, and the canonical SOT for source types supported by siphon.
"""

from enum import Enum


class SourceType(str, Enum):
    # Annotations for source types
    IMAGE = "Image"  # Image files like JPEG, PNG, etc.
    AUDIO = "Audio"  # Audio files like MP3, WAV, etc.
    VIDEO = "Video"  # Video files like MP4, AVI, etc.
    TEXT = "Text"  # Text files like TXT, MD, etc.
    DOC = "Doc"  # Document files like DOCX, PPTX, XLSX, PDF, etc.
    ARTICLE = "Article"  # Online articles or blog posts
    YOUTUBE = "YouTube"  # YouTube videos
    GITHUB = "GitHub"  # GitHub repositories or files
    OBSIDIAN = "Obsidian"  # Obsidian notes or vaults
    DRIVE = "Drive"  # Google Drive files (Docs, Sheets, etc.)
    EMAIL = "Email"  # Email messages or threads


# Park future implementation ideas here
"""
BOOK (for example those oreilly books I bought)
EPHEMERAL (stdin, clipboard, and other temporary sources like web scraping)
ARXIV
TODO
TEXTMESSAGES
CALENDAR
PODCAST (maybe)
RSS (the first "self-updating" source type)
REDDIT (scrape an entire subreddit)
"""
