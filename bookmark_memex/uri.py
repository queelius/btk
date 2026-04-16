"""Bookmark-memex URI builder and parser.

Public URI kinds:
    bookmark-memex://bookmark/<unique_id>
    bookmark-memex://annotation/<uuid>

Fragment support (positions inside a bookmark record):
    bookmark-memex://bookmark/<unique_id>#paragraph=5
    bookmark-memex://bookmark/<unique_id>#section=intro

The fragment is anything after the first ``#`` and is returned verbatim.

This module intentionally has no SQLAlchemy dependency so it can be used by
both archive internals and external consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

SCHEME = "bookmark-memex"
KINDS: frozenset[str] = frozenset({"bookmark", "annotation"})


class InvalidUriError(ValueError):
    """Raised when a URI string does not conform to the bookmark-memex scheme."""


@dataclass(frozen=True)
class ParsedUri:
    scheme: str
    kind: str
    id: str
    fragment: Optional[str]


# ---------------------------------------------------------------------------
# Public build helpers
# ---------------------------------------------------------------------------

def build_bookmark_uri(unique_id: str) -> str:
    """Return ``bookmark-memex://bookmark/<unique_id>``."""
    return _build("bookmark", unique_id)


def build_annotation_uri(uuid: str) -> str:
    """Return ``bookmark-memex://annotation/<uuid>``."""
    return _build("annotation", uuid)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_uri(uri: str) -> ParsedUri:
    """Parse a bookmark-memex URI into its components.

    Raises :class:`InvalidUriError` on any structural problem.
    """
    if not isinstance(uri, str) or "://" not in uri:
        raise InvalidUriError(f"not a URI: {uri!r}")

    scheme, _, rest = uri.partition("://")
    if scheme != SCHEME:
        raise InvalidUriError(
            f"expected scheme {SCHEME!r}, got {scheme!r} in {uri!r}"
        )

    kind, _, tail = rest.partition("/")
    if kind not in KINDS:
        raise InvalidUriError(f"unknown kind {kind!r} in {uri!r}")

    ident, sep, fragment = tail.partition("#")
    if not ident:
        raise InvalidUriError(f"empty id in {uri!r}")

    return ParsedUri(
        scheme=scheme,
        kind=kind,
        id=ident,
        fragment=fragment if sep else None,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build(kind: str, ident: str) -> str:
    if not ident:
        raise ValueError(f"cannot build {kind} URI from empty id")
    if kind not in KINDS:
        raise ValueError(f"unknown URI kind: {kind}")
    return f"{SCHEME}://{kind}/{ident}"
