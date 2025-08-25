"""Tests for bookmark collections management."""

import pytest
import json
import tempfile
import shutil
from pathlib import Path

from btk.collections import BookmarkCollection, CollectionSet, CollectionInfo, is_collection, find_collections


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_bookmarks():
    """Sample bookmarks for testing."""
    return [
        {
            "id": 1,
            "unique_id": "abc123",
            "title": "Example",
            "url": "https://example.com",
            "tags": ["test", "sample"],
            "stars": False,
            "visit_count": 5,
            "added": "2024-01-01T00:00:00"
        },
        {
            "id": 2,
            "unique_id": "def456",
            "title": "Google",
            "url": "https://google.com",
            "tags": ["search"],
            "stars": True,
            "visit_count": 10,
            "added": "2024-01-02T00:00:00"
        }
    ]


@pytest.fixture
def sample_bookmarks2():
    """Another set of sample bookmarks for testing merges."""
    return [
        {
            "id": 1,
            "unique_id": "def456",  # Same as in sample_bookmarks
            "title": "Google",
            "url": "https://google.com",
            "tags": ["search", "engine"],
            "stars": True,
            "visit_count": 15,
            "added": "2024-01-02T00:00:00"
        },
        {
            "id": 2,
            "unique_id": "ghi789",
            "title": "GitHub",
            "url": "https://github.com",
            "tags": ["code", "git"],
            "stars": False,
            "visit_count": 20,
            "added": "2024-01-03T00:00:00"
        }
    ]


class TestBookmarkCollection:
    """Test BookmarkCollection class."""
    
    def test_init_creates_collection(self, temp_dir):
        """Test that initializing a collection creates necessary files."""
        collection_path = Path(temp_dir) / "test_collection"
        collection = BookmarkCollection(str(collection_path))
        
        assert collection_path.exists()
        assert (collection_path / "bookmarks.json").exists()
        
        # Check that bookmarks.json contains empty list
        with open(collection_path / "bookmarks.json", 'r') as f:
            data = json.load(f)
            assert data == []
    
    def test_init_existing_collection(self, temp_dir, sample_bookmarks):
        """Test initializing with existing collection."""
        collection_path = Path(temp_dir) / "existing"
        collection_path.mkdir(parents=True)
        
        # Create existing bookmarks.json
        with open(collection_path / "bookmarks.json", 'w') as f:
            json.dump(sample_bookmarks, f)
        
        collection = BookmarkCollection(str(collection_path))
        bookmarks = collection.get_bookmarks()
        
        assert len(bookmarks) == 2
        assert bookmarks[0]["title"] == "Example"
    
    def test_get_and_save_bookmarks(self, temp_dir, sample_bookmarks):
        """Test getting and saving bookmarks."""
        collection = BookmarkCollection(str(Path(temp_dir) / "test"))
        
        # Initially empty
        assert collection.get_bookmarks() == []
        
        # Save bookmarks
        collection.save_bookmarks(sample_bookmarks)
        
        # Retrieve and verify
        bookmarks = collection.get_bookmarks()
        assert len(bookmarks) == 2
        assert bookmarks[0]["unique_id"] == "abc123"
    
    def test_add_bookmark(self, temp_dir):
        """Test adding a bookmark to collection."""
        collection = BookmarkCollection(str(Path(temp_dir) / "test"))
        
        bookmark = {
            "title": "Test Site",
            "url": "https://test.com",
            "tags": ["test"]
        }
        
        result = collection.add_bookmark(bookmark)
        assert result is True
        
        bookmarks = collection.get_bookmarks()
        assert len(bookmarks) == 1
        assert bookmarks[0]["title"] == "Test Site"
        assert "id" in bookmarks[0]
        assert "unique_id" in bookmarks[0]
        assert "added" in bookmarks[0]
    
    def test_add_duplicate_bookmark(self, temp_dir):
        """Test that duplicate bookmarks are not added."""
        collection = BookmarkCollection(str(Path(temp_dir) / "test"))
        
        bookmark = {
            "title": "Test",
            "url": "https://test.com"
        }
        
        collection.add_bookmark(bookmark)
        result = collection.add_bookmark(bookmark)
        
        assert result is False
        assert len(collection.get_bookmarks()) == 1
    
    def test_remove_bookmark(self, temp_dir, sample_bookmarks):
        """Test removing a bookmark."""
        collection = BookmarkCollection(str(Path(temp_dir) / "test"))
        collection.save_bookmarks(sample_bookmarks)
        
        # Remove bookmark with id=1
        result = collection.remove_bookmark(1)
        assert result is True
        
        bookmarks = collection.get_bookmarks()
        assert len(bookmarks) == 1
        assert bookmarks[0]["id"] == 2
        
        # Try to remove non-existent
        result = collection.remove_bookmark(999)
        assert result is False
    
    def test_search(self, temp_dir, sample_bookmarks):
        """Test searching bookmarks in collection."""
        collection = BookmarkCollection(str(Path(temp_dir) / "test"))
        collection.save_bookmarks(sample_bookmarks)
        
        results = collection.search("google")
        assert len(results) == 1
        assert results[0]["title"] == "Google"
        
        results = collection.search("test")
        assert len(results) == 1
        assert results[0]["title"] == "Example"
    
    def test_get_stats(self, temp_dir, sample_bookmarks):
        """Test getting collection statistics."""
        collection = BookmarkCollection(str(Path(temp_dir) / "test"))
        collection.save_bookmarks(sample_bookmarks)
        
        stats = collection.get_stats()
        
        assert stats["name"] == "test"
        assert stats["total_bookmarks"] == 2
        assert stats["starred"] == 1  # One starred bookmark
        assert stats["total_tags"] == 3  # test, sample, search
        assert len(stats["top_tags"]) == 3
    
    def test_collection_info(self, temp_dir):
        """Test collection info metadata."""
        collection = BookmarkCollection(str(Path(temp_dir) / "test"))
        
        # Set info
        collection.info.description = "Test collection"
        collection.info.tags = ["test", "sample"]
        collection._save_info()
        
        # Create new instance and verify info is loaded
        collection2 = BookmarkCollection(str(Path(temp_dir) / "test"))
        assert collection2.info.description == "Test collection"
        assert collection2.info.tags == ["test", "sample"]


class TestCollectionSet:
    """Test CollectionSet class."""
    
    def test_init_and_add_collection(self, temp_dir):
        """Test initializing collection set and adding collections."""
        collection_set = CollectionSet()
        
        # Add a collection
        collection_path = Path(temp_dir) / "coll1"
        collection = collection_set.add_collection(str(collection_path), "first")
        
        assert "first" in collection_set.collections
        assert collection is not None
        assert collection_path.exists()
    
    def test_discover_collections(self, temp_dir):
        """Test discovering collections in a directory."""
        # Create some collections
        for i in range(3):
            coll_path = Path(temp_dir) / f"coll{i}"
            coll_path.mkdir(parents=True)
            with open(coll_path / "bookmarks.json", 'w') as f:
                json.dump([], f)
        
        # Also create a non-collection directory
        (Path(temp_dir) / "not_collection").mkdir()
        
        collection_set = CollectionSet()
        collection_set.discover_collections(temp_dir, recursive=False)
        
        assert len(collection_set.collections) == 3
        assert "coll0" in collection_set.collections
        assert "coll1" in collection_set.collections
        assert "coll2" in collection_set.collections
        assert "not_collection" not in collection_set.collections
    
    def test_discover_recursive(self, temp_dir):
        """Test recursive discovery of collections."""
        # Create nested collections
        nested_path = Path(temp_dir) / "parent" / "child"
        nested_path.mkdir(parents=True)
        with open(nested_path / "bookmarks.json", 'w') as f:
            json.dump([], f)
        
        collection_set = CollectionSet()
        collection_set.discover_collections(temp_dir, recursive=True)
        
        assert "child" in collection_set.collections
    
    def test_create_collection(self, temp_dir):
        """Test creating a new collection."""
        collection_set = CollectionSet()
        
        collection_path = Path(temp_dir) / "new_coll"
        collection = collection_set.create_collection(str(collection_path), "new")
        
        assert "new" in collection_set.collections
        assert collection_path.exists()
        assert (collection_path / "bookmarks.json").exists()
    
    def test_get_collection(self, temp_dir):
        """Test getting a collection by name."""
        collection_set = CollectionSet()
        collection_path = Path(temp_dir) / "test"
        collection_set.add_collection(str(collection_path), "test")
        
        collection = collection_set.get_collection("test")
        assert collection is not None
        assert collection.path == collection_path
        
        # Non-existent collection
        assert collection_set.get_collection("nonexistent") is None
    
    def test_list_collections(self, temp_dir):
        """Test listing collection names."""
        collection_set = CollectionSet()
        
        for name in ["alpha", "beta", "gamma"]:
            collection_set.add_collection(
                str(Path(temp_dir) / name), name
            )
        
        names = collection_set.list_collections()
        assert len(names) == 3
        assert "alpha" in names
        assert "beta" in names
        assert "gamma" in names
    
    def test_remove_collection(self, temp_dir):
        """Test removing a collection from the set."""
        collection_set = CollectionSet()
        collection_path = Path(temp_dir) / "test"
        collection_set.add_collection(str(collection_path), "test")
        
        collection_set.remove_collection("test")
        assert "test" not in collection_set.collections
        
        # Files should still exist
        assert collection_path.exists()
        
        # Should raise error for non-existent
        with pytest.raises(ValueError):
            collection_set.remove_collection("nonexistent")
    
    def test_merge_collections_union(self, temp_dir, sample_bookmarks, sample_bookmarks2):
        """Test merging collections with union operation."""
        collection_set = CollectionSet()
        
        # Create two collections
        coll1_path = Path(temp_dir) / "coll1"
        coll1 = collection_set.add_collection(str(coll1_path), "coll1")
        coll1.save_bookmarks(sample_bookmarks)
        
        coll2_path = Path(temp_dir) / "coll2"
        coll2 = collection_set.add_collection(str(coll2_path), "coll2")
        coll2.save_bookmarks(sample_bookmarks2)
        
        # Merge with union
        merged_path = Path(temp_dir) / "merged"
        merged = collection_set.merge_collections(
            ["coll1", "coll2"],
            str(merged_path),
            operation="union",
            target_name="merged"
        )
        
        bookmarks = merged.get_bookmarks()
        assert len(bookmarks) == 3  # abc123, def456, ghi789 (def456 is duplicate)
        
        # Check that merged collection is in the set
        assert "merged" in collection_set.collections
    
    def test_merge_collections_intersection(self, temp_dir, sample_bookmarks, sample_bookmarks2):
        """Test merging collections with intersection operation."""
        collection_set = CollectionSet()
        
        # Create two collections
        coll1 = collection_set.add_collection(str(Path(temp_dir) / "coll1"), "coll1")
        coll1.save_bookmarks(sample_bookmarks)
        
        coll2 = collection_set.add_collection(str(Path(temp_dir) / "coll2"), "coll2")
        coll2.save_bookmarks(sample_bookmarks2)
        
        # Merge with intersection
        merged = collection_set.merge_collections(
            ["coll1", "coll2"],
            str(Path(temp_dir) / "merged"),
            operation="intersection"
        )
        
        bookmarks = merged.get_bookmarks()
        assert len(bookmarks) == 1  # Only def456 is in both
        assert bookmarks[0]["unique_id"] == "def456"
    
    def test_merge_collections_difference(self, temp_dir, sample_bookmarks, sample_bookmarks2):
        """Test merging collections with difference operation."""
        collection_set = CollectionSet()
        
        # Create two collections
        coll1 = collection_set.add_collection(str(Path(temp_dir) / "coll1"), "coll1")
        coll1.save_bookmarks(sample_bookmarks)
        
        coll2 = collection_set.add_collection(str(Path(temp_dir) / "coll2"), "coll2")
        coll2.save_bookmarks(sample_bookmarks2)
        
        # Merge with difference (coll1 - coll2)
        merged = collection_set.merge_collections(
            ["coll1", "coll2"],
            str(Path(temp_dir) / "merged"),
            operation="difference"
        )
        
        bookmarks = merged.get_bookmarks()
        assert len(bookmarks) == 1  # Only abc123 is in coll1 but not coll2
        assert bookmarks[0]["unique_id"] == "abc123"
    
    def test_search_all(self, temp_dir, sample_bookmarks, sample_bookmarks2):
        """Test searching across all collections."""
        collection_set = CollectionSet()
        
        coll1 = collection_set.add_collection(str(Path(temp_dir) / "coll1"), "coll1")
        coll1.save_bookmarks(sample_bookmarks)
        
        coll2 = collection_set.add_collection(str(Path(temp_dir) / "coll2"), "coll2")
        coll2.save_bookmarks(sample_bookmarks2)
        
        # Search for "google"
        results = collection_set.search_all("google")
        assert len(results) == 2  # Found in both collections
        assert "coll1" in results
        assert "coll2" in results
        assert len(results["coll1"]) == 1
        assert len(results["coll2"]) == 1
        
        # Search for "github"
        results = collection_set.search_all("github")
        assert len(results) == 1  # Only in coll2
        assert "coll2" in results
        assert len(results["coll2"]) == 1
    
    def test_get_all_bookmarks(self, temp_dir, sample_bookmarks, sample_bookmarks2):
        """Test getting all bookmarks from all collections."""
        collection_set = CollectionSet()
        
        coll1 = collection_set.add_collection(str(Path(temp_dir) / "coll1"), "coll1")
        coll1.save_bookmarks(sample_bookmarks)
        
        coll2 = collection_set.add_collection(str(Path(temp_dir) / "coll2"), "coll2")
        coll2.save_bookmarks(sample_bookmarks2)
        
        all_bookmarks = collection_set.get_all_bookmarks()
        
        assert len(all_bookmarks) == 2
        assert "coll1" in all_bookmarks
        assert "coll2" in all_bookmarks
        assert len(all_bookmarks["coll1"]) == 2
        assert len(all_bookmarks["coll2"]) == 2
    
    def test_get_stats(self, temp_dir, sample_bookmarks, sample_bookmarks2):
        """Test getting statistics for all collections."""
        collection_set = CollectionSet()
        
        coll1 = collection_set.add_collection(str(Path(temp_dir) / "coll1"), "coll1")
        coll1.save_bookmarks(sample_bookmarks)
        
        coll2 = collection_set.add_collection(str(Path(temp_dir) / "coll2"), "coll2")
        coll2.save_bookmarks(sample_bookmarks2)
        
        stats = collection_set.get_stats()
        
        assert stats["total_collections"] == 2
        assert stats["total_bookmarks"] == 4  # 2 + 2
        assert "coll1" in stats["collections"]
        assert "coll2" in stats["collections"]
    
    def test_export_collection(self, temp_dir, sample_bookmarks):
        """Test exporting a collection."""
        collection_set = CollectionSet()
        
        coll = collection_set.add_collection(str(Path(temp_dir) / "coll"), "test")
        coll.save_bookmarks(sample_bookmarks)
        
        # Export to JSON
        output_file = str(Path(temp_dir) / "export.json")
        collection_set.export_collection("test", output_file, format="json")
        
        assert Path(output_file).exists()
        with open(output_file, 'r') as f:
            exported = json.load(f)
            assert len(exported) == 2
            assert exported[0]["unique_id"] == "abc123"
    
    def test_import_to_collection(self, temp_dir, sample_bookmarks):
        """Test importing bookmarks to a collection."""
        collection_set = CollectionSet()
        
        # Create empty collection
        coll = collection_set.add_collection(str(Path(temp_dir) / "coll"), "test")
        
        # Create a file to import
        import_file = Path(temp_dir) / "import.json"
        with open(import_file, 'w') as f:
            json.dump(sample_bookmarks, f)
        
        # Import
        collection_set.import_to_collection("test", str(import_file))
        
        bookmarks = coll.get_bookmarks()
        assert len(bookmarks) == 2
        # Check that URLs and titles were imported correctly
        urls = [b["url"] for b in bookmarks]
        assert "https://example.com" in urls
        assert "https://google.com" in urls
        titles = [b["title"] for b in bookmarks]
        assert "Example" in titles
        assert "Google" in titles


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_is_collection(self, temp_dir):
        """Test is_collection function."""
        # Not a collection
        assert is_collection(temp_dir) is False
        
        # Create bookmarks.json
        with open(Path(temp_dir) / "bookmarks.json", 'w') as f:
            json.dump([], f)
        
        # Now it's a collection
        assert is_collection(temp_dir) is True
    
    def test_find_collections(self, temp_dir):
        """Test find_collections function."""
        # Create nested collections
        paths = [
            Path(temp_dir) / "coll1",
            Path(temp_dir) / "nested" / "coll2",
            Path(temp_dir) / "nested" / "deep" / "coll3"
        ]
        
        for path in paths:
            path.mkdir(parents=True, exist_ok=True)
            with open(path / "bookmarks.json", 'w') as f:
                json.dump([], f)
        
        # Find all collections
        collections = find_collections(temp_dir)
        assert len(collections) == 3
        
        # Check that all paths are found
        collection_names = [Path(c).name for c in collections]
        assert "coll1" in collection_names
        assert "coll2" in collection_names
        assert "coll3" in collection_names


class TestCollectionInfo:
    """Test CollectionInfo dataclass."""
    
    def test_dataclass_creation(self):
        """Test creating CollectionInfo."""
        info = CollectionInfo(
            name="test",
            path=Path("/tmp/test"),
            description="Test collection",
            tags=["test", "sample"]
        )
        
        assert info.name == "test"
        assert info.path == Path("/tmp/test")
        assert info.description == "Test collection"
        assert info.tags == ["test", "sample"]
    
    def test_default_values(self):
        """Test default values in CollectionInfo."""
        info = CollectionInfo(name="test", path="/tmp/test")
        
        assert info.description == ""
        assert info.created == ""
        assert info.modified == ""
        assert info.tags == []
        assert info.source == ""
    
    def test_path_conversion(self):
        """Test that path is converted to Path object."""
        info = CollectionInfo(name="test", path="/tmp/test")
        assert isinstance(info.path, Path)
        
        # Also works with Path object
        info2 = CollectionInfo(name="test", path=Path("/tmp/test"))
        assert isinstance(info2.path, Path)