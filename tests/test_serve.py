"""Tests for btk.serve REST API."""

import os
import tempfile

import pytest

from btk.db import Database
from btk.serve import ALLOWED_UPDATE_FIELDS


class TestFieldWhitelist:
    """Verify that the REST API only allows safe fields to be updated."""

    @pytest.fixture
    def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(os.path.join(tmpdir, "test.db"))
            db.add(url="https://example.com", title="Original")
            yield db

    def test_allowed_fields_exist(self):
        """ALLOWED_UPDATE_FIELDS should contain expected safe fields."""
        assert "title" in ALLOWED_UPDATE_FIELDS
        assert "description" in ALLOWED_UPDATE_FIELDS
        assert "stars" in ALLOWED_UPDATE_FIELDS
        assert "tags" in ALLOWED_UPDATE_FIELDS

    def test_disallowed_fields_excluded(self):
        """ALLOWED_UPDATE_FIELDS must NOT contain dangerous fields."""
        assert "id" not in ALLOWED_UPDATE_FIELDS
        assert "unique_id" not in ALLOWED_UPDATE_FIELDS
        assert "reachable" not in ALLOWED_UPDATE_FIELDS

    def test_filter_data_rejects_unknown_fields(self, db):
        """Passing disallowed fields like 'id' should be filtered out."""
        data = {"title": "Updated", "id": 999, "reachable": True}
        filtered = {k: v for k, v in data.items() if k in ALLOWED_UPDATE_FIELDS}
        assert "title" in filtered
        assert "id" not in filtered
        assert "reachable" not in filtered
        # Confirm that update with filtered data works
        success = db.update(1, **filtered)
        assert success
        bookmark = db.get(id=1)
        assert bookmark.title == "Updated"
