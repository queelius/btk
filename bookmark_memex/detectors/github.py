"""GitHub URL detector for bookmark-memex."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse


def detect(url: str, content: Optional[str] = None) -> Optional[dict]:
    """Detect GitHub URLs and extract structured metadata.

    Patterns (checked in priority order):
    1. github.com/<owner>/<repo>/issues/<n>    -> issue
    2. github.com/<owner>/<repo>/pull/<n>      -> pull_request
    3. gist.github.com/<owner>/<gist_id>       -> gist
    4. github.com/<owner>/<repo>               -> repo

    Returns a dict on match, None otherwise.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path.rstrip("/")

    # Gist
    if host == "gist.github.com":
        m = re.fullmatch(r"/([^/]+)/([^/]+)", path)
        if m:
            return {
                "source": "github",
                "type": "gist",
                "owner": m.group(1),
                "gist_id": m.group(2),
            }
        return None

    if host not in ("github.com", "www.github.com"):
        return None

    # Issue: /<owner>/<repo>/issues/<number>
    m = re.fullmatch(r"/([^/]+)/([^/]+)/issues/(\d+)", path)
    if m:
        return {
            "source": "github",
            "type": "issue",
            "owner": m.group(1),
            "repo": m.group(2),
            "number": int(m.group(3)),
        }

    # Pull request: /<owner>/<repo>/pull/<number>
    m = re.fullmatch(r"/([^/]+)/([^/]+)/pull/(\d+)", path)
    if m:
        return {
            "source": "github",
            "type": "pull_request",
            "owner": m.group(1),
            "repo": m.group(2),
            "number": int(m.group(3)),
        }

    # Repo: /<owner>/<repo>  (exactly two path segments)
    m = re.fullmatch(r"/([^/]+)/([^/]+)", path)
    if m:
        return {
            "source": "github",
            "type": "repo",
            "owner": m.group(1),
            "repo": m.group(2),
        }

    return None
