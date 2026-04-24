"""Bookmark-memex URI builder and parser.

Public URI kinds:
    bookmark-memex://bookmark/<unique_id>
    bookmark-memex://marginalia/<uuid>
    bookmark-memex://history-url/<unique_id>
    bookmark-memex://visit/<uuid>

Fragment support (positions inside a record):
    bookmark-memex://bookmark/<unique_id>#paragraph=5
    bookmark-memex://bookmark/<unique_id>#section=intro

The fragment is anything after the first ``#`` and is returned verbatim.

Legacy compatibility:
    ``bookmark-memex://annotation/<uuid>`` is accepted by the parser and
    normalised to ``marginalia``. This preserves any arkiv bundles, notes,
    or cross-archive references produced before the 2026-04 rename.
    Builders emit only the canonical ``marginalia`` form.

This module intentionally has no SQLAlchemy dependency so it can be used by
both archive internals and external consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

SCHEME = "bookmark-memex"
KINDS: frozenset[str] = frozenset({"bookmark", "marginalia", "history-url", "visit"})
# Legacy kinds accepted by parse_uri and normalised to a canonical kind.
_LEGACY_KIND_ALIASES: dict[str, str] = {"annotation": "marginalia"}


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


def build_marginalia_uri(uuid: str) -> str:
    """Return ``bookmark-memex://marginalia/<uuid>``."""
    return _build("marginalia", uuid)


def build_history_url_uri(unique_id: str) -> str:
    """Return ``bookmark-memex://history-url/<unique_id>``."""
    return _build("history-url", unique_id)


def build_visit_uri(uuid: str) -> str:
    """Return ``bookmark-memex://visit/<uuid>``."""
    return _build("visit", uuid)


# Backwards-compat alias. New code should use build_marginalia_uri().
build_annotation_uri = build_marginalia_uri


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_uri(uri: str) -> ParsedUri:
    """Parse a bookmark-memex URI into its components.

    Legacy ``annotation`` kinds are normalised to ``marginalia``.

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
    kind = _LEGACY_KIND_ALIASES.get(kind, kind)
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
