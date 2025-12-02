"""
Bookmark Health Checker

Verifies bookmark URLs are still reachable and updates their status.
"""
import asyncio
import aiohttp
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check result status."""
    OK = "ok"
    REDIRECT = "redirect"
    CLIENT_ERROR = "client_error"  # 4xx
    SERVER_ERROR = "server_error"  # 5xx
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    SSL_ERROR = "ssl_error"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check for a single bookmark."""
    bookmark_id: int
    url: str
    status: HealthStatus
    status_code: Optional[int] = None
    redirect_url: Optional[str] = None
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    checked_at: datetime = None

    def __post_init__(self):
        if self.checked_at is None:
            self.checked_at = datetime.now(timezone.utc)

    @property
    def is_reachable(self) -> bool:
        """Whether the URL is considered reachable."""
        return self.status in (HealthStatus.OK, HealthStatus.REDIRECT)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'bookmark_id': self.bookmark_id,
            'url': self.url,
            'status': self.status.value,
            'status_code': self.status_code,
            'redirect_url': self.redirect_url,
            'response_time_ms': self.response_time_ms,
            'error_message': self.error_message,
            'checked_at': self.checked_at.isoformat() if self.checked_at else None,
            'is_reachable': self.is_reachable
        }


async def check_url(
    session: aiohttp.ClientSession,
    bookmark_id: int,
    url: str,
    timeout: float = 10.0
) -> HealthCheckResult:
    """Check if a single URL is reachable.

    Args:
        session: aiohttp session
        bookmark_id: ID of the bookmark
        url: URL to check
        timeout: Request timeout in seconds

    Returns:
        HealthCheckResult with check details
    """
    import time
    start_time = time.time()

    try:
        async with session.head(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
            ssl=False  # Don't fail on SSL issues, just check reachability
        ) as response:
            elapsed_ms = (time.time() - start_time) * 1000

            # Check for redirects
            redirect_url = None
            if response.history:
                redirect_url = str(response.url)

            if response.status < 400:
                status = HealthStatus.REDIRECT if redirect_url else HealthStatus.OK
            elif response.status < 500:
                status = HealthStatus.CLIENT_ERROR
            else:
                status = HealthStatus.SERVER_ERROR

            return HealthCheckResult(
                bookmark_id=bookmark_id,
                url=url,
                status=status,
                status_code=response.status,
                redirect_url=redirect_url,
                response_time_ms=elapsed_ms
            )

    except asyncio.TimeoutError:
        return HealthCheckResult(
            bookmark_id=bookmark_id,
            url=url,
            status=HealthStatus.TIMEOUT,
            error_message="Request timed out"
        )
    except aiohttp.ClientSSLError as e:
        return HealthCheckResult(
            bookmark_id=bookmark_id,
            url=url,
            status=HealthStatus.SSL_ERROR,
            error_message=str(e)
        )
    except aiohttp.ClientConnectorError as e:
        return HealthCheckResult(
            bookmark_id=bookmark_id,
            url=url,
            status=HealthStatus.CONNECTION_ERROR,
            error_message=str(e)
        )
    except Exception as e:
        return HealthCheckResult(
            bookmark_id=bookmark_id,
            url=url,
            status=HealthStatus.UNKNOWN,
            error_message=str(e)
        )


async def check_bookmarks(
    bookmarks: List[Tuple[int, str]],
    concurrency: int = 10,
    timeout: float = 10.0,
    progress_callback=None
) -> List[HealthCheckResult]:
    """Check multiple bookmarks concurrently.

    Args:
        bookmarks: List of (bookmark_id, url) tuples
        concurrency: Maximum concurrent requests
        timeout: Request timeout in seconds
        progress_callback: Optional callback(completed, total) for progress

    Returns:
        List of HealthCheckResult objects
    """
    results = []
    semaphore = asyncio.Semaphore(concurrency)
    completed = 0

    async def check_with_semaphore(session, bookmark_id, url):
        nonlocal completed
        async with semaphore:
            result = await check_url(session, bookmark_id, url, timeout)
            completed += 1
            if progress_callback:
                progress_callback(completed, len(bookmarks))
            return result

    connector = aiohttp.TCPConnector(limit=concurrency, ssl=False)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={'User-Agent': 'BTK-HealthChecker/1.0'}
    ) as session:
        tasks = [
            check_with_semaphore(session, bid, url)
            for bid, url in bookmarks
        ]
        results = await asyncio.gather(*tasks)

    return results


def run_health_check(
    bookmarks: List[Tuple[int, str]],
    concurrency: int = 10,
    timeout: float = 10.0,
    progress_callback=None
) -> List[HealthCheckResult]:
    """Synchronous wrapper for check_bookmarks.

    Args:
        bookmarks: List of (bookmark_id, url) tuples
        concurrency: Maximum concurrent requests
        timeout: Request timeout in seconds
        progress_callback: Optional callback(completed, total)

    Returns:
        List of HealthCheckResult objects
    """
    return asyncio.run(
        check_bookmarks(bookmarks, concurrency, timeout, progress_callback)
    )


def summarize_results(results: List[HealthCheckResult]) -> Dict:
    """Generate a summary of health check results.

    Args:
        results: List of HealthCheckResult objects

    Returns:
        Summary dictionary with counts and stats
    """
    summary = {
        'total': len(results),
        'reachable': 0,
        'unreachable': 0,
        'by_status': {},
        'avg_response_time_ms': None,
        'broken_bookmarks': [],
        'redirected_bookmarks': []
    }

    response_times = []

    for result in results:
        # Count by status
        status_key = result.status.value
        summary['by_status'][status_key] = summary['by_status'].get(status_key, 0) + 1

        # Reachable vs unreachable
        if result.is_reachable:
            summary['reachable'] += 1
        else:
            summary['unreachable'] += 1
            summary['broken_bookmarks'].append({
                'id': result.bookmark_id,
                'url': result.url,
                'status': result.status.value,
                'error': result.error_message
            })

        # Track redirects
        if result.redirect_url:
            summary['redirected_bookmarks'].append({
                'id': result.bookmark_id,
                'url': result.url,
                'redirect_url': result.redirect_url
            })

        # Collect response times
        if result.response_time_ms is not None:
            response_times.append(result.response_time_ms)

    # Calculate average response time
    if response_times:
        summary['avg_response_time_ms'] = sum(response_times) / len(response_times)

    return summary
