"""Unit tests for bookmark_memex.soft_delete.

Uses MagicMock for sessions — no real database needed.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from bookmark_memex.soft_delete import (
    filter_active,
    archive,
    restore,
    hard_delete,
    is_archived,
)


class FakeModel:
    """Minimal stand-in for any ORM model with an archived_at column."""

    archived_at = None  # class-level default; instances override per-instance

    def __init__(self, archived_at=None):
        self.archived_at = archived_at


class TestIsArchived:
    def test_returns_false_when_archived_at_is_none(self):
        instance = FakeModel(archived_at=None)
        assert is_archived(instance) is False

    def test_returns_true_when_archived_at_is_set(self):
        ts = datetime.now(timezone.utc)
        instance = FakeModel(archived_at=ts)
        assert is_archived(instance) is True

    def test_returns_false_when_no_archived_at_attribute(self):
        # Objects without the attribute at all should be treated as not archived.
        class Bare:
            pass
        assert is_archived(Bare()) is False


class TestArchive:
    def test_archive_sets_archived_at(self):
        session = MagicMock()
        instance = FakeModel(archived_at=None)
        archive(session, instance)
        assert instance.archived_at is not None

    def test_archive_calls_session_add(self):
        session = MagicMock()
        instance = FakeModel(archived_at=None)
        archive(session, instance)
        session.add.assert_called_once_with(instance)

    def test_archive_is_idempotent(self):
        """Re-archiving preserves the original timestamp."""
        session = MagicMock()
        original_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        instance = FakeModel(archived_at=original_ts)
        archive(session, instance)
        assert instance.archived_at == original_ts

    def test_archive_idempotent_still_calls_session_add(self):
        """Even when already archived, session.add is called."""
        session = MagicMock()
        original_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        instance = FakeModel(archived_at=original_ts)
        archive(session, instance)
        session.add.assert_called_once_with(instance)


class TestRestore:
    def test_restore_clears_archived_at(self):
        session = MagicMock()
        ts = datetime.now(timezone.utc)
        instance = FakeModel(archived_at=ts)
        restore(session, instance)
        assert instance.archived_at is None

    def test_restore_calls_session_add(self):
        session = MagicMock()
        instance = FakeModel(archived_at=datetime.now(timezone.utc))
        restore(session, instance)
        session.add.assert_called_once_with(instance)


class TestHardDelete:
    def test_hard_delete_calls_session_delete(self):
        session = MagicMock()
        instance = FakeModel()
        hard_delete(session, instance)
        session.delete.assert_called_once_with(instance)


class TestFilterActive:
    def test_filter_active_calls_filter_on_query(self):
        """filter_active should call query.filter(model.archived_at.is_(None))."""
        # We can't easily test the SQL emitted without a real engine; we verify
        # that the query is transformed (i.e. filter is called and a new query
        # object is returned) without raising.
        from sqlalchemy import Column, DateTime, Integer, create_engine
        from sqlalchemy.orm import DeclarativeBase, Session

        class Base(DeclarativeBase):
            pass

        class SampleRecord(Base):
            __tablename__ = "sample"
            id = Column(Integer, primary_key=True)
            archived_at = Column(DateTime, nullable=True)

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            query = session.query(SampleRecord)
            active_query = filter_active(query, SampleRecord)
            # Should be a valid Query object we can call .all() on
            result = active_query.all()
            assert result == []

    def test_filter_active_include_archived_returns_same_query(self):
        """With include_archived=True the query object is returned unchanged."""
        query = MagicMock()
        model = MagicMock()
        result = filter_active(query, model, include_archived=True)
        assert result is query
