"""
Auto-Cleanup Module for BTK.

Provides functionality for automatically cleaning up stale, broken,
or obsolete bookmarks.

Cleanup actions:
- Archive broken bookmarks (unreachable URLs)
- Archive old, unvisited bookmarks
- Flag duplicates for review
- Remove orphaned content cache entries
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from dataclasses import dataclass

from .models import Bookmark


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""
    action: str
    bookmark_id: int
    url: str
    title: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'action': self.action,
            'bookmark_id': self.bookmark_id,
            'url': self.url,
            'title': self.title,
            'reason': self.reason
        }


@dataclass
class CleanupSummary:
    """Summary of cleanup operations."""
    archived: int
    flagged: int
    deleted: int
    skipped: int
    results: List[CleanupResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'archived': self.archived,
            'flagged': self.flagged,
            'deleted': self.deleted,
            'skipped': self.skipped,
            'total_actions': self.archived + self.flagged + self.deleted,
            'results': [r.to_dict() for r in self.results]
        }


def find_broken_bookmarks(db, include_archived: bool = False) -> List[Bookmark]:
    """
    Find bookmarks with unreachable URLs.

    Args:
        db: Database instance
        include_archived: Include already archived bookmarks

    Returns:
        List of bookmarks marked as unreachable
    """
    bookmarks = db.search(reachable=False)

    if not include_archived:
        bookmarks = [b for b in bookmarks if not b.archived]

    return bookmarks


def find_stale_bookmarks(db, days_threshold: int = 365,
                         include_archived: bool = False) -> List[Bookmark]:
    """
    Find bookmarks that haven't been visited in a long time.

    Args:
        db: Database instance
        days_threshold: Number of days without visits to consider stale
        include_archived: Include already archived bookmarks

    Returns:
        List of stale bookmarks
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_threshold)

    all_bookmarks = db.all()
    stale = []

    for b in all_bookmarks:
        if include_archived or not b.archived:
            # Consider stale if never visited or last visit before cutoff
            if b.last_visited is None:
                # Check if added before cutoff
                if b.added:
                    added = b.added
                    if added.tzinfo is None:
                        added = added.replace(tzinfo=timezone.utc)
                    if added < cutoff:
                        stale.append(b)
            else:
                # Make sure last_visited is timezone-aware
                last_visited = b.last_visited
                if last_visited.tzinfo is None:
                    last_visited = last_visited.replace(tzinfo=timezone.utc)
                if last_visited < cutoff:
                    stale.append(b)

    return stale


def find_unvisited_bookmarks(db, days_threshold: int = 90,
                             include_archived: bool = False) -> List[Bookmark]:
    """
    Find bookmarks that have never been visited.

    Args:
        db: Database instance
        days_threshold: Only include if added more than this many days ago
        include_archived: Include already archived bookmarks

    Returns:
        List of unvisited bookmarks
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_threshold)

    all_bookmarks = db.all()
    unvisited = []

    for b in all_bookmarks:
        if include_archived or not b.archived:
            if b.visit_count == 0:
                # Only include if added before cutoff
                if b.added:
                    added = b.added
                    if added.tzinfo is None:
                        added = added.replace(tzinfo=timezone.utc)
                    if added < cutoff:
                        unvisited.append(b)

    return unvisited


def archive_bookmarks(db, bookmark_ids: List[int],
                      reason: str = "auto-cleanup") -> List[CleanupResult]:
    """
    Archive a list of bookmarks.

    Args:
        db: Database instance
        bookmark_ids: List of bookmark IDs to archive
        reason: Reason for archiving

    Returns:
        List of CleanupResult objects
    """
    results = []

    for bid in bookmark_ids:
        bookmark = db.get(id=bid)
        if bookmark and not bookmark.archived:
            db.update(bid, archived=True)
            results.append(CleanupResult(
                action='archived',
                bookmark_id=bid,
                url=bookmark.url,
                title=bookmark.title,
                reason=reason
            ))

    return results


def cleanup_broken(db, dry_run: bool = True) -> CleanupSummary:
    """
    Archive all broken (unreachable) bookmarks.

    Args:
        db: Database instance
        dry_run: If True, don't actually make changes

    Returns:
        CleanupSummary with results
    """
    broken = find_broken_bookmarks(db)

    results = []
    archived = 0

    for b in broken:
        result = CleanupResult(
            action='archive' if dry_run else 'archived',
            bookmark_id=b.id,
            url=b.url,
            title=b.title,
            reason='URL unreachable'
        )
        results.append(result)

        if not dry_run:
            db.update(b.id, archived=True)
            archived += 1

    return CleanupSummary(
        archived=archived,
        flagged=0,
        deleted=0,
        skipped=len(broken) if dry_run else 0,
        results=results
    )


def cleanup_stale(db, days_threshold: int = 365,
                  dry_run: bool = True) -> CleanupSummary:
    """
    Archive stale bookmarks (not visited in a long time).

    Args:
        db: Database instance
        days_threshold: Number of days to consider stale
        dry_run: If True, don't actually make changes

    Returns:
        CleanupSummary with results
    """
    stale = find_stale_bookmarks(db, days_threshold)

    results = []
    archived = 0

    for b in stale:
        result = CleanupResult(
            action='archive' if dry_run else 'archived',
            bookmark_id=b.id,
            url=b.url,
            title=b.title,
            reason=f'Not visited in {days_threshold}+ days'
        )
        results.append(result)

        if not dry_run:
            db.update(b.id, archived=True)
            archived += 1

    return CleanupSummary(
        archived=archived,
        flagged=0,
        deleted=0,
        skipped=len(stale) if dry_run else 0,
        results=results
    )


def cleanup_unvisited(db, days_threshold: int = 90,
                      dry_run: bool = True) -> CleanupSummary:
    """
    Archive bookmarks that have never been visited.

    Args:
        db: Database instance
        days_threshold: Only include if added more than this many days ago
        dry_run: If True, don't actually make changes

    Returns:
        CleanupSummary with results
    """
    unvisited = find_unvisited_bookmarks(db, days_threshold)

    results = []
    archived = 0

    for b in unvisited:
        result = CleanupResult(
            action='archive' if dry_run else 'archived',
            bookmark_id=b.id,
            url=b.url,
            title=b.title,
            reason=f'Never visited (added {days_threshold}+ days ago)'
        )
        results.append(result)

        if not dry_run:
            db.update(b.id, archived=True)
            archived += 1

    return CleanupSummary(
        archived=archived,
        flagged=0,
        deleted=0,
        skipped=len(unvisited) if dry_run else 0,
        results=results
    )


def cleanup_all(db, broken: bool = True, stale_days: int = 365,
                unvisited_days: int = 90, dry_run: bool = True) -> CleanupSummary:
    """
    Run all cleanup operations.

    Args:
        db: Database instance
        broken: Archive broken bookmarks
        stale_days: Days threshold for stale bookmarks (0 to skip)
        unvisited_days: Days threshold for unvisited bookmarks (0 to skip)
        dry_run: If True, don't actually make changes

    Returns:
        Combined CleanupSummary
    """
    all_results = []
    total_archived = 0
    total_skipped = 0

    if broken:
        summary = cleanup_broken(db, dry_run)
        all_results.extend(summary.results)
        total_archived += summary.archived
        total_skipped += summary.skipped

    if stale_days > 0:
        summary = cleanup_stale(db, stale_days, dry_run)
        # Filter out duplicates (already processed)
        processed_ids = {r.bookmark_id for r in all_results}
        new_results = [r for r in summary.results if r.bookmark_id not in processed_ids]
        all_results.extend(new_results)
        total_archived += len([r for r in new_results if r.action == 'archived'])
        total_skipped += len([r for r in new_results if r.action == 'archive'])

    if unvisited_days > 0:
        summary = cleanup_unvisited(db, unvisited_days, dry_run)
        # Filter out duplicates
        processed_ids = {r.bookmark_id for r in all_results}
        new_results = [r for r in summary.results if r.bookmark_id not in processed_ids]
        all_results.extend(new_results)
        total_archived += len([r for r in new_results if r.action == 'archived'])
        total_skipped += len([r for r in new_results if r.action == 'archive'])

    return CleanupSummary(
        archived=total_archived,
        flagged=0,
        deleted=0,
        skipped=total_skipped,
        results=all_results
    )


def get_cleanup_preview(db, broken: bool = True, stale_days: int = 365,
                        unvisited_days: int = 90) -> Dict[str, Any]:
    """
    Get a preview of what cleanup would affect without making changes.

    Args:
        db: Database instance
        broken: Include broken bookmarks
        stale_days: Days threshold for stale (0 to skip)
        unvisited_days: Days threshold for unvisited (0 to skip)

    Returns:
        Dictionary with preview information
    """
    preview = {
        'broken': [],
        'stale': [],
        'unvisited': [],
        'total': 0
    }

    seen_ids = set()

    if broken:
        for b in find_broken_bookmarks(db):
            if b.id not in seen_ids:
                preview['broken'].append({
                    'id': b.id,
                    'url': b.url,
                    'title': b.title
                })
                seen_ids.add(b.id)

    if stale_days > 0:
        for b in find_stale_bookmarks(db, stale_days):
            if b.id not in seen_ids:
                preview['stale'].append({
                    'id': b.id,
                    'url': b.url,
                    'title': b.title,
                    'last_visited': b.last_visited.isoformat() if b.last_visited else None
                })
                seen_ids.add(b.id)

    if unvisited_days > 0:
        for b in find_unvisited_bookmarks(db, unvisited_days):
            if b.id not in seen_ids:
                preview['unvisited'].append({
                    'id': b.id,
                    'url': b.url,
                    'title': b.title,
                    'added': b.added.isoformat() if b.added else None
                })
                seen_ids.add(b.id)

    preview['total'] = len(seen_ids)
    return preview
