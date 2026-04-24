"""Browser history importer for bookmark-memex.

Supports Chrome/Chromium-family and Firefox browsers. Produces
:class:`HistoryImportResult` with per-URL and per-visit counts.

The importer is idempotent: re-running against the same profile only
inserts visits we have not already captured, thanks to the
``UNIQUE(url_id, visited_at, source_type, source_name)`` dedup contract
on ``history_visits``.

Public API:

    import_history(db, browser="chrome", profile=None, since=None,
                   strip_tracking=True) -> HistoryImportResult
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, NamedTuple, Optional

from bookmark_memex.db import Database, generate_history_unique_id
from bookmark_memex.detectors import run_detectors
from bookmark_memex.importers.browser import (
    BrowserImporter,
    BrowserProfile,
    ChromeImporter,
    FirefoxImporter,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class HistoryImportResult(NamedTuple):
    """Per-call counts returned by :func:`import_history`.

    ``urls_seen`` is the number of distinct source-side URL rows
    processed. ``urls_added`` is the number of new ``history_urls`` rows
    created. ``urls_updated`` counts pre-existing URLs that were touched
    (title backfill, typed_count bump).

    ``visits_seen`` is the number of raw visit rows processed. ``visits_added``
    is the number of new ``history_visits`` rows inserted.
    ``visits_skipped`` counts dedup hits (visits we had already captured).
    """

    urls_seen: int
    urls_added: int
    urls_updated: int
    visits_seen: int
    visits_added: int
    visits_skipped: int


# ---------------------------------------------------------------------------
# Transition mapping
# ---------------------------------------------------------------------------

# Chrome transition core mask is the low 8 bits. Qualifiers live above.
# https://chromium.googlesource.com/chromium/src/+/main/ui/base/page_transition_types.h
_CHROME_CORE_MASK = 0xFF
_CHROME_CORE: dict[int, str] = {
    0: "link",
    1: "typed",
    2: "bookmark",
    3: "subframe",           # auto_subframe
    4: "subframe",           # manual_subframe
    5: "generated",
    6: "typed",              # auto_toplevel
    7: "form_submit",
    8: "reload",
    9: "generated",          # keyword
    10: "generated",          # keyword_generated
}

# Firefox moz_historyvisits.visit_type enum
# https://firefox-source-docs.mozilla.org/browser/places/visit-types.html
_FIREFOX_VISIT_TYPE: dict[int, str] = {
    1: "link",
    2: "typed",
    3: "bookmark",
    4: "subframe",          # EMBED
    5: "redirect",          # REDIRECT_PERMANENT
    6: "redirect",          # REDIRECT_TEMPORARY
    7: "download",
    8: "subframe",          # FRAMED_LINK
    9: "reload",
}


def _decode_chrome_transition(raw: int) -> str:
    core = raw & _CHROME_CORE_MASK
    return _CHROME_CORE.get(core, "other")


def _decode_firefox_visit_type(raw: int) -> str:
    return _FIREFOX_VISIT_TYPE.get(int(raw), "other")


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------


_CHROME_EPOCH_OFFSET_US = 11644473600 * 1_000_000  # 1601-01-01 to 1970-01-01


def _chrome_us_to_datetime(chrome_ts: int) -> Optional[datetime]:
    """Convert Chrome microseconds-since-1601 to naive UTC datetime."""
    if not chrome_ts:
        return None
    unix_ts = (chrome_ts - _CHROME_EPOCH_OFFSET_US) / 1_000_000
    if unix_ts <= 0:
        return None
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).replace(tzinfo=None)


def _datetime_to_chrome_us(dt: datetime) -> int:
    """Convert naive-UTC datetime to Chrome microseconds-since-1601."""
    ts = dt.replace(tzinfo=timezone.utc).timestamp()
    return int(ts * 1_000_000) + _CHROME_EPOCH_OFFSET_US


def _firefox_us_to_datetime(firefox_ts: int) -> Optional[datetime]:
    """Convert Firefox microseconds-since-Unix-epoch to naive UTC datetime."""
    if not firefox_ts:
        return None
    unix_ts = firefox_ts / 1_000_000
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).replace(tzinfo=None)


def _datetime_to_firefox_us(dt: datetime) -> int:
    """Convert naive-UTC datetime to Firefox microseconds-since-Unix-epoch."""
    ts = dt.replace(tzinfo=timezone.utc).timestamp()
    return int(ts * 1_000_000)


# ---------------------------------------------------------------------------
# Source-side readers
# ---------------------------------------------------------------------------


def _read_chrome_history(
    profile_path: Path,
    since: Optional[datetime],
) -> list[dict[str, Any]]:
    """Read all (or post-*since*) rows from Chrome's History DB.

    Returns a list of dicts with keys:
        url, title, typed_count, visit_id (Chrome-side),
        visited_at (datetime), transition (str), duration_ms,
        from_visit (Chrome-side visit id or 0)

    Visits arrive in ascending visited_at order so the referrer-chain
    second pass can resolve from_visit IDs without a secondary lookup
    structure.
    """
    history_db = profile_path / "History"
    if not history_db.exists():
        logger.warning("No Chrome History DB at %s", history_db)
        return []

    base = BrowserImporter()
    temp_db: Optional[Path] = None
    try:
        temp_db = base._copy_database(history_db)
        conn = sqlite3.connect(str(temp_db))
        cur = conn.cursor()

        since_us = (
            _datetime_to_chrome_us(since) if since is not None else None
        )

        params: tuple[Any, ...] = ()
        where = ""
        if since_us is not None:
            where = "WHERE v.visit_time > ?"
            params = (since_us,)

        cur.execute(
            f"""
            SELECT v.id, v.visit_time, v.from_visit, v.transition,
                   v.visit_duration, u.url, u.title, u.typed_count
            FROM   visits v
            JOIN   urls u ON u.id = v.url
            {where}
            ORDER  BY v.visit_time ASC
            """,
            params,
        )
        rows: list[dict[str, Any]] = []
        for vid, vtime, fromv, trans, dur, url, title, typed in cur.fetchall():
            dt = _chrome_us_to_datetime(vtime)
            if dt is None:
                continue
            rows.append({
                "visit_id": int(vid),
                "visited_at": dt,
                "from_visit": int(fromv or 0),
                "transition": _decode_chrome_transition(int(trans or 0)),
                "duration_ms": int((dur or 0) / 1000) if dur else None,
                "url": url or "",
                "title": title or None,
                "typed_count": int(typed or 0),
            })
        conn.close()
        return rows
    finally:
        if temp_db is not None and temp_db.exists():
            try:
                temp_db.unlink()
            except OSError:
                pass


def _read_firefox_history(
    profile_path: Path,
    since: Optional[datetime],
) -> list[dict[str, Any]]:
    """Read all (or post-*since*) rows from Firefox's places.sqlite."""
    places_db = profile_path / "places.sqlite"
    if not places_db.exists():
        logger.warning("No Firefox places.sqlite at %s", places_db)
        return []

    base = BrowserImporter()
    temp_db: Optional[Path] = None
    try:
        temp_db = base._copy_database(places_db)
        conn = sqlite3.connect(str(temp_db))
        cur = conn.cursor()

        since_us = (
            _datetime_to_firefox_us(since) if since is not None else None
        )

        params: tuple[Any, ...] = ()
        where = ""
        if since_us is not None:
            where = "WHERE h.visit_date > ?"
            params = (since_us,)

        cur.execute(
            f"""
            SELECT h.id, h.visit_date, h.from_visit, h.visit_type,
                   p.url, p.title, p.typed
            FROM   moz_historyvisits h
            JOIN   moz_places p ON p.id = h.place_id
            {where}
            ORDER  BY h.visit_date ASC
            """,
            params,
        )
        rows: list[dict[str, Any]] = []
        for vid, vdate, fromv, vtype, url, title, typed in cur.fetchall():
            dt = _firefox_us_to_datetime(vdate)
            if dt is None:
                continue
            rows.append({
                "visit_id": int(vid),
                "visited_at": dt,
                "from_visit": int(fromv or 0),
                "transition": _decode_firefox_visit_type(int(vtype or 0)),
                "duration_ms": None,  # Firefox does not record this
                "url": url or "",
                "title": title or None,
                "typed_count": 1 if typed else 0,
            })
        conn.close()
        return rows
    finally:
        if temp_db is not None and temp_db.exists():
            try:
                temp_db.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# URL guard (mirrors browser.py)
# ---------------------------------------------------------------------------


def _is_http(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_history(
    db: Database,
    browser: str = "chrome",
    profile: Optional[str] = None,
    since: Optional[datetime] = None,
) -> HistoryImportResult:
    """Import visits from *browser* into *db*.

    Args:
        db:        Open :class:`Database` instance.
        browser:   ``"chrome"`` (chromium-family) or ``"firefox"``.
        profile:   Profile name, case-insensitive. Defaults to the flagged
                   default profile, falling back to the first profile.
        since:     If given, only visits strictly after this datetime are
                   considered. The filter runs source-side against the
                   browser's own timestamp column, so it is cheap even on
                   very large history databases.

    Returns:
        :class:`HistoryImportResult` with the six counts.

    Raises:
        ValueError: when *browser* is unsupported, no profiles exist, or
        *profile* does not match a known profile.
    """
    browser_lc = browser.lower()

    if browser_lc in ("chrome", "chromium", "edge", "brave"):
        profile_importer: BrowserImporter = ChromeImporter()
        reader = _read_chrome_history
        source_type = "chrome"
    elif browser_lc == "firefox":
        profile_importer = FirefoxImporter()
        reader = _read_firefox_history
        source_type = "firefox"
    else:
        raise ValueError(f"Unsupported browser: {browser!r}")

    profiles = profile_importer.find_profiles()
    if not profiles:
        raise ValueError(f"No {browser} profiles found on this system")

    if profile is None:
        chosen = next((p for p in profiles if p.is_default), profiles[0])
    else:
        chosen = next(
            (p for p in profiles if p.name.lower() == profile.lower()),
            None,
        )
        if chosen is None:
            avail = ", ".join(p.name for p in profiles)
            raise ValueError(
                f"Profile {profile!r} not found for {browser}. Available: {avail}"
            )

    raw = reader(chosen.path, since)
    profile_name = f"{chosen.browser}/{chosen.name}"

    return _ingest_visits(
        db=db,
        rows=raw,
        source_type=source_type,
        source_name=profile_name,
    )


def _ingest_visits(
    *,
    db: Database,
    rows: Iterable[dict[str, Any]],
    source_type: str,
    source_name: str,
) -> HistoryImportResult:
    """Shared ingestion loop for both browsers.

    Two passes:
    1. :meth:`Database.bulk_ingest_history` writes all URLs and visits in
       a single transaction. WAL + synchronous=NORMAL make this O(1)
       fsyncs for the whole batch rather than O(N).
    2. Media detectors run afterwards on newly-added URLs only. Kept
       out of the bulk transaction so a flaky detector cannot abort the
       import; each detector touch is a tiny UPDATE.
    """
    # Materialise so we can count visits_seen without consuming the iterator.
    entries = [e for e in rows if _is_http(e.get("url") or "")]
    visits_seen = len(entries)

    urls_added, urls_updated, visits_added, visits_skipped, urls_seen = (
        db.bulk_ingest_history(
            entries,
            source_type=source_type,
            source_name=source_name,
        )
    )

    # Best-effort media detection on freshly-added URLs. Done as a
    # separate pass so detector failures cannot roll back the bulk
    # import. Only runs when something new was added.
    if urls_added:
        _attach_media_to_new_urls(db, entries)

    return HistoryImportResult(
        urls_seen=urls_seen,
        urls_added=urls_added,
        urls_updated=urls_updated,
        visits_seen=visits_seen,
        visits_added=visits_added,
        visits_skipped=visits_skipped,
    )


def _attach_media_to_new_urls(
    db: Database,
    entries: list[dict[str, Any]],
) -> None:
    """Run detectors on each distinct URL whose history_url.media is NULL."""
    seen: set[str] = set()
    for entry in entries:
        url = entry.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        row = db.get_history_url_by_unique_id(generate_history_unique_id(url))
        if row is None or row.media is not None:
            continue
        try:
            media = run_detectors(url)
        except Exception:
            media = None
        if media:
            db.upsert_history_url(url, media=media)


def list_history_profiles(
    browser: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Thin wrapper; history and bookmarks share the same profile layout."""
    from bookmark_memex.importers.browser import list_browser_profiles
    return list_browser_profiles(browser)
