"""Unit tests for bookmark_memex.uri."""
import pytest

from bookmark_memex.uri import (
    build_bookmark_uri,
    build_marginalia_uri,
    build_annotation_uri,  # legacy alias for build_marginalia_uri
    parse_uri,
    ParsedUri,
    InvalidUriError,
    SCHEME,
    KINDS,
)


class TestConstants:
    def test_scheme(self):
        assert SCHEME == "bookmark-memex"

    def test_kinds(self):
        assert "bookmark" in KINDS
        assert "marginalia" in KINDS
        # Legacy 'annotation' was renamed to 'marginalia' and is accepted
        # by the parser but is NOT part of the canonical KINDS frozenset.
        assert "annotation" not in KINDS


class TestBuilders:
    def test_build_bookmark_uri(self):
        assert build_bookmark_uri("abc123") == "bookmark-memex://bookmark/abc123"

    def test_build_marginalia_uri(self):
        assert (
            build_marginalia_uri("uuid-val")
            == "bookmark-memex://marginalia/uuid-val"
        )

    def test_build_annotation_uri_is_alias(self):
        """Legacy alias emits the canonical marginalia form."""
        assert build_annotation_uri("uuid-val") == build_marginalia_uri("uuid-val")

    def test_build_bookmark_uri_preserves_id(self):
        uid = "sha256:deadbeef01234567"
        assert build_bookmark_uri(uid) == f"bookmark-memex://bookmark/{uid}"

    def test_build_bookmark_uri_rejects_empty_id(self):
        with pytest.raises(ValueError):
            build_bookmark_uri("")

    def test_build_marginalia_uri_rejects_empty_id(self):
        with pytest.raises(ValueError):
            build_marginalia_uri("")


class TestParser:
    def test_parse_bookmark_uri(self):
        result = parse_uri("bookmark-memex://bookmark/abc123")
        assert result == ParsedUri(scheme=SCHEME, kind="bookmark", id="abc123", fragment=None)

    def test_parse_marginalia_uri(self):
        result = parse_uri("bookmark-memex://marginalia/uuid-xyz")
        assert result.kind == "marginalia"
        assert result.id == "uuid-xyz"
        assert result.fragment is None

    def test_parse_legacy_annotation_uri_normalises_to_marginalia(self):
        """Old arkiv bundles used 'annotation'; parser transparently upgrades."""
        result = parse_uri("bookmark-memex://annotation/uuid-xyz")
        assert result.kind == "marginalia"
        assert result.id == "uuid-xyz"

    def test_parse_uri_with_fragment(self):
        result = parse_uri("bookmark-memex://bookmark/abc123#paragraph=5")
        assert result.kind == "bookmark"
        assert result.id == "abc123"
        assert result.fragment == "paragraph=5"

    def test_parse_uri_fragment_is_verbatim(self):
        result = parse_uri("bookmark-memex://bookmark/x#section=intro&line=3")
        assert result.fragment == "section=intro&line=3"

    def test_parse_rejects_wrong_scheme(self):
        with pytest.raises(InvalidUriError):
            parse_uri("book-memex://book/abc")

    def test_parse_rejects_unknown_scheme(self):
        with pytest.raises(InvalidUriError):
            parse_uri("llm-memex://conversation/abc")

    def test_parse_rejects_unknown_kind(self):
        with pytest.raises(InvalidUriError):
            parse_uri("bookmark-memex://trail/abc")

    def test_parse_rejects_empty_id(self):
        with pytest.raises(InvalidUriError):
            parse_uri("bookmark-memex://bookmark/")

    def test_parse_rejects_non_uri_string(self):
        with pytest.raises(InvalidUriError):
            parse_uri("not-a-uri")

    def test_parse_rejects_missing_scheme_separator(self):
        with pytest.raises(InvalidUriError):
            parse_uri("bookmark-memex/bookmark/abc")

    def test_invalid_uri_error_is_value_error(self):
        with pytest.raises(ValueError):
            parse_uri("not-a-uri")


class TestRoundtrip:
    def test_bookmark_uri_roundtrip(self):
        uid = "test-unique-id"
        uri = build_bookmark_uri(uid)
        parsed = parse_uri(uri)
        assert parsed.scheme == SCHEME
        assert parsed.kind == "bookmark"
        assert parsed.id == uid
        assert parsed.fragment is None

    def test_marginalia_uri_roundtrip(self):
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        uri = build_marginalia_uri(uuid)
        parsed = parse_uri(uri)
        assert parsed.kind == "marginalia"
        assert parsed.id == uuid
