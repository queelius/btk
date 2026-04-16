"""YouTube URL detector for bookmark-memex."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse, parse_qs


def detect(url: str, content: Optional[str] = None) -> Optional[dict]:
    """Detect YouTube URLs and extract structured metadata.

    Patterns:
    - youtube.com/watch?v=<id>  -> video
    - youtu.be/<id>             -> video
    - youtube.com/playlist?list=<id> -> playlist
    - youtube.com/@<handle>     -> channel (handle)
    - youtube.com/channel/<id>  -> channel (channel_id)

    Returns a dict on match, None otherwise.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""

    # Short URL: youtu.be/<video_id>
    if host == "youtu.be":
        # Path is /<video_id>[/<anything>]
        video_id = parsed.path.lstrip("/").split("/")[0]
        if video_id:
            return {"source": "youtube", "type": "video", "video_id": video_id}
        return None

    if host not in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        return None

    path = parsed.path.rstrip("/")
    qs = parse_qs(parsed.query)

    # Watch URL
    if path == "/watch" and "v" in qs:
        return {"source": "youtube", "type": "video", "video_id": qs["v"][0]}

    # Playlist URL (no watch component)
    if path == "/playlist" and "list" in qs:
        return {"source": "youtube", "type": "playlist", "playlist_id": qs["list"][0]}

    # Channel by handle: /@<handle>
    handle_match = re.fullmatch(r"/@([^/]+)", path)
    if handle_match:
        return {"source": "youtube", "type": "channel", "handle": handle_match.group(1)}

    # Channel by ID: /channel/<channel_id>
    channel_match = re.fullmatch(r"/channel/([^/]+)", path)
    if channel_match:
        return {"source": "youtube", "type": "channel", "channel_id": channel_match.group(1)}

    return None
