"""ArXiv URL detector for bookmark-memex."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

# ArXiv paper ID pattern: YYMM.NNNNN[vN]
_PAPER_ID_RE = re.compile(r"(\d{4}\.\d{4,5}(?:v\d+)?)")


def detect(url: str, content: Optional[str] = None) -> Optional[dict]:
    """Detect ArXiv URLs and extract structured metadata.

    Patterns:
    - arxiv.org/abs/<paper_id>  -> paper
    - arxiv.org/pdf/<paper_id>  -> paper

    Returns a dict on match, None otherwise.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if host not in ("arxiv.org", "www.arxiv.org"):
        return None

    path = parsed.path
    m = re.fullmatch(r"/(abs|pdf)/(.+)", path)
    if not m:
        return None

    raw_id = m.group(2).rstrip("/")
    id_match = _PAPER_ID_RE.match(raw_id)
    if not id_match:
        return None

    paper_id = id_match.group(1)
    return {
        "source": "arxiv",
        "type": "paper",
        "paper_id": paper_id,
        "abs_url": f"https://arxiv.org/abs/{paper_id}",
        "pdf_url": f"https://arxiv.org/pdf/{paper_id}",
    }
