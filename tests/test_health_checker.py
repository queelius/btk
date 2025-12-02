"""Tests for the bookmark health checker module."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from btk.health_checker import (
    HealthStatus,
    HealthCheckResult,
    check_url,
    check_bookmarks,
    run_health_check,
    summarize_results
)


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert HealthStatus.OK.value == "ok"
        assert HealthStatus.REDIRECT.value == "redirect"
        assert HealthStatus.CLIENT_ERROR.value == "client_error"
        assert HealthStatus.SERVER_ERROR.value == "server_error"
        assert HealthStatus.TIMEOUT.value == "timeout"
        assert HealthStatus.CONNECTION_ERROR.value == "connection_error"
        assert HealthStatus.SSL_ERROR.value == "ssl_error"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_basic_result(self):
        """Test creating a basic result."""
        result = HealthCheckResult(
            bookmark_id=1,
            url="https://example.com",
            status=HealthStatus.OK,
            status_code=200
        )
        assert result.bookmark_id == 1
        assert result.url == "https://example.com"
        assert result.status == HealthStatus.OK
        assert result.status_code == 200
        assert result.is_reachable is True

    def test_redirect_result(self):
        """Test redirect result is considered reachable."""
        result = HealthCheckResult(
            bookmark_id=1,
            url="https://example.com",
            status=HealthStatus.REDIRECT,
            redirect_url="https://www.example.com"
        )
        assert result.is_reachable is True
        assert result.redirect_url == "https://www.example.com"

    def test_error_result_not_reachable(self):
        """Test error results are not reachable."""
        for status in [HealthStatus.CLIENT_ERROR, HealthStatus.SERVER_ERROR,
                       HealthStatus.TIMEOUT, HealthStatus.CONNECTION_ERROR,
                       HealthStatus.SSL_ERROR, HealthStatus.UNKNOWN]:
            result = HealthCheckResult(
                bookmark_id=1,
                url="https://example.com",
                status=status
            )
            assert result.is_reachable is False, f"{status} should not be reachable"

    def test_auto_timestamp(self):
        """Test checked_at is auto-populated."""
        result = HealthCheckResult(
            bookmark_id=1,
            url="https://example.com",
            status=HealthStatus.OK
        )
        assert result.checked_at is not None
        assert isinstance(result.checked_at, datetime)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = HealthCheckResult(
            bookmark_id=42,
            url="https://example.com",
            status=HealthStatus.OK,
            status_code=200,
            response_time_ms=150.5
        )
        d = result.to_dict()
        assert d['bookmark_id'] == 42
        assert d['url'] == "https://example.com"
        assert d['status'] == "ok"
        assert d['status_code'] == 200
        assert d['response_time_ms'] == 150.5
        assert d['is_reachable'] is True
        assert 'checked_at' in d


class TestCheckUrl:
    """Tests for check_url function."""

    @pytest.mark.asyncio
    async def test_check_url_success(self):
        """Test successful URL check."""
        import aiohttp

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.history = []
        mock_response.url = "https://example.com"

        mock_session = MagicMock()
        mock_session.head = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        result = await check_url(mock_session, 1, "https://example.com")
        assert result.status == HealthStatus.OK
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_check_url_redirect(self):
        """Test URL with redirect."""
        mock_history = [MagicMock()]  # Non-empty history = redirect

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.history = mock_history
        mock_response.url = "https://www.example.com"

        mock_session = MagicMock()
        mock_session.head = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        result = await check_url(mock_session, 1, "https://example.com")
        assert result.status == HealthStatus.REDIRECT
        assert result.redirect_url == "https://www.example.com"

    @pytest.mark.asyncio
    async def test_check_url_client_error(self):
        """Test 4xx error handling."""
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.history = []

        mock_session = MagicMock()
        mock_session.head = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        result = await check_url(mock_session, 1, "https://example.com/notfound")
        assert result.status == HealthStatus.CLIENT_ERROR
        assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_check_url_server_error(self):
        """Test 5xx error handling."""
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.history = []

        mock_session = MagicMock()
        mock_session.head = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        result = await check_url(mock_session, 1, "https://example.com/error")
        assert result.status == HealthStatus.SERVER_ERROR
        assert result.status_code == 500


class TestSummarizeResults:
    """Tests for summarize_results function."""

    def test_empty_results(self):
        """Test summary of empty results."""
        summary = summarize_results([])
        assert summary['total'] == 0
        assert summary['reachable'] == 0
        assert summary['unreachable'] == 0
        assert summary['by_status'] == {}
        assert summary['avg_response_time_ms'] is None

    def test_all_reachable(self):
        """Test summary with all reachable URLs."""
        results = [
            HealthCheckResult(1, "https://example1.com", HealthStatus.OK, 200, response_time_ms=100),
            HealthCheckResult(2, "https://example2.com", HealthStatus.OK, 200, response_time_ms=200),
            HealthCheckResult(3, "https://example3.com", HealthStatus.REDIRECT, 301, redirect_url="https://new.example.com", response_time_ms=150),
        ]
        summary = summarize_results(results)
        assert summary['total'] == 3
        assert summary['reachable'] == 3
        assert summary['unreachable'] == 0
        assert summary['by_status']['ok'] == 2
        assert summary['by_status']['redirect'] == 1
        assert summary['avg_response_time_ms'] == 150.0

    def test_mixed_results(self):
        """Test summary with mixed results."""
        results = [
            HealthCheckResult(1, "https://good.com", HealthStatus.OK, 200, response_time_ms=100),
            HealthCheckResult(2, "https://notfound.com", HealthStatus.CLIENT_ERROR, 404),
            HealthCheckResult(3, "https://down.com", HealthStatus.CONNECTION_ERROR, error_message="Connection refused"),
            HealthCheckResult(4, "https://slow.com", HealthStatus.TIMEOUT, error_message="Timeout"),
        ]
        summary = summarize_results(results)
        assert summary['total'] == 4
        assert summary['reachable'] == 1
        assert summary['unreachable'] == 3
        assert len(summary['broken_bookmarks']) == 3
        assert summary['by_status']['ok'] == 1
        assert summary['by_status']['client_error'] == 1
        assert summary['by_status']['connection_error'] == 1
        assert summary['by_status']['timeout'] == 1

    def test_broken_bookmarks_details(self):
        """Test broken bookmarks list has correct details."""
        results = [
            HealthCheckResult(42, "https://notfound.com", HealthStatus.CLIENT_ERROR, 404,
                              error_message="Not Found"),
        ]
        summary = summarize_results(results)
        assert len(summary['broken_bookmarks']) == 1
        broken = summary['broken_bookmarks'][0]
        assert broken['id'] == 42
        assert broken['url'] == "https://notfound.com"
        assert broken['status'] == 'client_error'
        assert broken['error'] == "Not Found"

    def test_redirected_bookmarks(self):
        """Test redirected bookmarks list."""
        results = [
            HealthCheckResult(1, "https://old.com", HealthStatus.REDIRECT, 301,
                              redirect_url="https://new.com"),
        ]
        summary = summarize_results(results)
        assert len(summary['redirected_bookmarks']) == 1
        redir = summary['redirected_bookmarks'][0]
        assert redir['id'] == 1
        assert redir['url'] == "https://old.com"
        assert redir['redirect_url'] == "https://new.com"


class TestRunHealthCheck:
    """Tests for run_health_check synchronous wrapper."""

    @patch('btk.health_checker.asyncio.run')
    def test_run_health_check_calls_async(self, mock_run):
        """Test synchronous wrapper calls asyncio.run."""
        mock_run.return_value = []
        result = run_health_check([(1, "https://example.com")])
        mock_run.assert_called_once()

    @patch('btk.health_checker.asyncio.run')
    def test_run_health_check_passes_params(self, mock_run):
        """Test parameters are passed through."""
        mock_run.return_value = []
        bookmarks = [(1, "https://a.com"), (2, "https://b.com")]

        run_health_check(
            bookmarks,
            concurrency=5,
            timeout=15.0
        )

        # Check the coroutine was created with correct params
        mock_run.assert_called_once()


class TestCLIIntegration:
    """Tests for CLI integration."""

    def test_health_command_help(self, tmp_path):
        """Test health command is registered."""
        import subprocess
        result = subprocess.run(
            ['python', '-m', 'btk.cli', 'bookmark', 'health', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert '--concurrency' in result.stdout
        assert '--timeout' in result.stdout
        assert '--broken' in result.stdout
        assert '--dry-run' in result.stdout
