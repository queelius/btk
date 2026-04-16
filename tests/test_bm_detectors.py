"""Tests for bookmark_memex.detectors module (auto-discovery engine + built-ins)."""
import pytest


@pytest.fixture(autouse=True)
def _reset_detectors():
    """Ensure a clean detector cache before and after every test."""
    from bookmark_memex.detectors import reset_cache
    reset_cache()
    yield
    reset_cache()


# ─── YouTube detector ─────────────────────────────────────────────────────────

class TestYouTubeDetector:
    def test_watch_url_extracts_video_id(self):
        from bookmark_memex.detectors.youtube import detect
        result = detect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result is not None
        assert result["source"] == "youtube"
        assert result["type"] == "video"
        assert result["video_id"] == "dQw4w9WgXcQ"

    def test_short_url_extracts_video_id(self):
        from bookmark_memex.detectors.youtube import detect
        result = detect("https://youtu.be/dQw4w9WgXcQ")
        assert result is not None
        assert result["source"] == "youtube"
        assert result["type"] == "video"
        assert result["video_id"] == "dQw4w9WgXcQ"

    def test_short_url_with_query_params(self):
        from bookmark_memex.detectors.youtube import detect
        result = detect("https://youtu.be/dQw4w9WgXcQ?t=42")
        assert result is not None
        assert result["video_id"] == "dQw4w9WgXcQ"

    def test_watch_url_with_extra_params(self):
        from bookmark_memex.detectors.youtube import detect
        result = detect("https://www.youtube.com/watch?v=abc123XYZ&list=PL123")
        assert result is not None
        assert result["video_id"] == "abc123XYZ"

    def test_playlist_url_extracts_playlist_id(self):
        from bookmark_memex.detectors.youtube import detect
        result = detect("https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknc9TTnDeXLRH")
        assert result is not None
        assert result["source"] == "youtube"
        assert result["type"] == "playlist"
        assert result["playlist_id"] == "PLrAXtmErZgOeiKm4sgNOknc9TTnDeXLRH"

    def test_channel_handle_url(self):
        from bookmark_memex.detectors.youtube import detect
        result = detect("https://www.youtube.com/@mkbhd")
        assert result is not None
        assert result["source"] == "youtube"
        assert result["type"] == "channel"
        assert result["handle"] == "mkbhd"

    def test_channel_id_url(self):
        from bookmark_memex.detectors.youtube import detect
        result = detect("https://www.youtube.com/channel/UCVHFbw7woebEcMRPqPChydg")
        assert result is not None
        assert result["source"] == "youtube"
        assert result["type"] == "channel"
        assert result["channel_id"] == "UCVHFbw7woebEcMRPqPChydg"

    def test_non_youtube_returns_none(self):
        from bookmark_memex.detectors.youtube import detect
        assert detect("https://www.google.com") is None

    def test_vimeo_returns_none(self):
        from bookmark_memex.detectors.youtube import detect
        assert detect("https://vimeo.com/123456") is None

    def test_none_content_is_accepted(self):
        from bookmark_memex.detectors.youtube import detect
        result = detect("https://www.youtube.com/watch?v=abc123", None)
        assert result is not None
        assert result["video_id"] == "abc123"


# ─── ArXiv detector ───────────────────────────────────────────────────────────

class TestArxivDetector:
    def test_abs_url_extracts_paper_id(self):
        from bookmark_memex.detectors.arxiv import detect
        result = detect("https://arxiv.org/abs/2301.00001")
        assert result is not None
        assert result["source"] == "arxiv"
        assert result["type"] == "paper"
        assert result["paper_id"] == "2301.00001"

    def test_abs_url_includes_pdf_url(self):
        from bookmark_memex.detectors.arxiv import detect
        result = detect("https://arxiv.org/abs/2301.00001")
        assert result is not None
        assert result["abs_url"] == "https://arxiv.org/abs/2301.00001"
        assert result["pdf_url"] == "https://arxiv.org/pdf/2301.00001"

    def test_pdf_url_extracts_paper_id(self):
        from bookmark_memex.detectors.arxiv import detect
        result = detect("https://arxiv.org/pdf/2301.00001")
        assert result is not None
        assert result["paper_id"] == "2301.00001"
        assert result["abs_url"] == "https://arxiv.org/abs/2301.00001"
        assert result["pdf_url"] == "https://arxiv.org/pdf/2301.00001"

    def test_versioned_paper_id(self):
        from bookmark_memex.detectors.arxiv import detect
        result = detect("https://arxiv.org/abs/2301.00001v2")
        assert result is not None
        assert result["paper_id"] == "2301.00001v2"

    def test_five_digit_paper_id(self):
        from bookmark_memex.detectors.arxiv import detect
        result = detect("https://arxiv.org/abs/2301.12345")
        assert result is not None
        assert result["paper_id"] == "2301.12345"

    def test_non_arxiv_returns_none(self):
        from bookmark_memex.detectors.arxiv import detect
        assert detect("https://www.google.com") is None

    def test_arxiv_homepage_returns_none(self):
        from bookmark_memex.detectors.arxiv import detect
        assert detect("https://arxiv.org") is None

    def test_arxiv_search_returns_none(self):
        from bookmark_memex.detectors.arxiv import detect
        assert detect("https://arxiv.org/search/?searchtype=all&query=llm") is None


# ─── GitHub detector ──────────────────────────────────────────────────────────

class TestGitHubDetector:
    def test_repo_url_extracts_owner_and_repo(self):
        from bookmark_memex.detectors.github import detect
        result = detect("https://github.com/torvalds/linux")
        assert result is not None
        assert result["source"] == "github"
        assert result["type"] == "repo"
        assert result["owner"] == "torvalds"
        assert result["repo"] == "linux"

    def test_issue_url_extracts_number(self):
        from bookmark_memex.detectors.github import detect
        result = detect("https://github.com/python/cpython/issues/12345")
        assert result is not None
        assert result["source"] == "github"
        assert result["type"] == "issue"
        assert result["owner"] == "python"
        assert result["repo"] == "cpython"
        assert result["number"] == 12345

    def test_pr_url_extracts_number(self):
        from bookmark_memex.detectors.github import detect
        result = detect("https://github.com/rust-lang/rust/pull/42")
        assert result is not None
        assert result["source"] == "github"
        assert result["type"] == "pull_request"
        assert result["owner"] == "rust-lang"
        assert result["repo"] == "rust"
        assert result["number"] == 42

    def test_gist_url(self):
        from bookmark_memex.detectors.github import detect
        result = detect("https://gist.github.com/torvalds/abc123def456")
        assert result is not None
        assert result["source"] == "github"
        assert result["type"] == "gist"
        assert result["owner"] == "torvalds"
        assert result["gist_id"] == "abc123def456"

    def test_repo_url_with_trailing_slash(self):
        from bookmark_memex.detectors.github import detect
        result = detect("https://github.com/torvalds/linux/")
        assert result is not None
        assert result["type"] == "repo"

    def test_issue_not_mistaken_for_repo(self):
        from bookmark_memex.detectors.github import detect
        result = detect("https://github.com/python/cpython/issues/99")
        assert result is not None
        assert result["type"] == "issue"
        assert result["type"] != "repo"

    def test_non_github_returns_none(self):
        from bookmark_memex.detectors.github import detect
        assert detect("https://www.google.com") is None

    def test_gitlab_returns_none(self):
        from bookmark_memex.detectors.github import detect
        assert detect("https://gitlab.com/user/repo") is None

    def test_github_homepage_returns_none(self):
        from bookmark_memex.detectors.github import detect
        assert detect("https://github.com") is None


# ─── run_detectors integration tests ──────────────────────────────────────────

class TestRunDetectors:
    def test_youtube_url_returns_youtube_result(self):
        from bookmark_memex.detectors import run_detectors
        result = run_detectors("https://www.youtube.com/watch?v=abc123")
        assert result is not None
        assert result["source"] == "youtube"

    def test_arxiv_url_returns_arxiv_result(self):
        from bookmark_memex.detectors import run_detectors
        result = run_detectors("https://arxiv.org/abs/2301.00001")
        assert result is not None
        assert result["source"] == "arxiv"

    def test_github_url_returns_github_result(self):
        from bookmark_memex.detectors import run_detectors
        result = run_detectors("https://github.com/torvalds/linux")
        assert result is not None
        assert result["source"] == "github"

    def test_unknown_url_returns_none(self):
        from bookmark_memex.detectors import run_detectors
        result = run_detectors("https://www.some-random-site.example")
        assert result is None

    def test_content_passed_to_detectors(self):
        from bookmark_memex.detectors import run_detectors
        # Content is optional and doesn't break anything
        result = run_detectors("https://arxiv.org/abs/2301.00001", "Some content")
        assert result is not None
        assert result["source"] == "arxiv"


# ─── discover() / reset_cache() unit tests ────────────────────────────────────

class TestDiscoverCache:
    def test_discover_returns_list_of_tuples(self):
        from bookmark_memex.detectors import discover
        detectors = discover()
        assert isinstance(detectors, list)
        for name, fn in detectors:
            assert isinstance(name, str)
            assert callable(fn)

    def test_discover_includes_builtin_detectors(self):
        from bookmark_memex.detectors import discover
        detectors = discover()
        names = [name for name, _ in detectors]
        assert "youtube" in names
        assert "arxiv" in names
        assert "github" in names

    def test_discover_is_cached(self):
        from bookmark_memex.detectors import discover
        result1 = discover()
        result2 = discover()
        assert result1 is result2  # Same list object (cached)

    def test_reset_cache_invalidates_cache(self):
        from bookmark_memex.detectors import discover, reset_cache
        result1 = discover()
        reset_cache()
        result2 = discover()
        assert result1 is not result2  # Fresh list after reset

    def test_user_detector_overrides_builtin(self, tmp_path, monkeypatch):
        """A user detector with the same filename shadows the built-in."""
        import bookmark_memex.detectors as det_mod
        from bookmark_memex.detectors import discover, reset_cache

        # Create a fake user detectors directory with a 'youtube.py' override
        user_dir = tmp_path / "detectors"
        user_dir.mkdir()
        (user_dir / "youtube.py").write_text(
            "def detect(url, content=None):\n    return {'source': 'user_youtube'}\n"
        )

        # Patch get_config to return a Config with detectors_dir pointing to user_dir
        import bookmark_memex.config as cfg_mod

        class FakeConfig:
            detectors_dir = str(user_dir)

        monkeypatch.setattr(cfg_mod, "get_config", lambda: FakeConfig())
        reset_cache()

        detectors = discover()
        names_fns = {name: fn for name, fn in detectors}
        assert "youtube" in names_fns
        # User version should win
        result = names_fns["youtube"]("https://www.youtube.com/watch?v=x")
        assert result["source"] == "user_youtube"
