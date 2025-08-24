"""
Tests for bookmark archiver functionality.
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock
from btk.archiver import BookmarkArchiver, get_archiver


class TestBookmarkArchiver:
    """Test BookmarkArchiver class."""
    
    @pytest.fixture
    def temp_archive_dir(self):
        """Create a temporary directory for archive testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def archiver(self, temp_archive_dir):
        """Create an archiver instance with temporary directory."""
        return BookmarkArchiver(archive_dir=temp_archive_dir)
    
    @pytest.fixture
    def mock_cache(self):
        """Create a mock cache."""
        cache = MagicMock()
        cache.get.return_value = None
        cache.set.return_value = None
        return cache
    
    @pytest.fixture
    def mock_extractor(self):
        """Create a mock content extractor."""
        extractor = MagicMock()
        extractor.extract.return_value = {
            'title': 'Test Page',
            'text': 'Test content',
            'description': 'A test page',
            'author': 'Test Author',
            'keywords': ['test', 'example']
        }
        return extractor
    
    @pytest.fixture
    def sample_bookmark(self):
        """Create a sample bookmark."""
        return {
            'url': 'https://example.com',
            'title': 'Example Site',
            'tags': ['test', 'example'],
            'description': 'A test bookmark',
            'stars': True,
            'added': datetime.now().isoformat()
        }
    
    def test_archiver_initialization(self, archiver, temp_archive_dir):
        """Test archiver initialization."""
        assert archiver.archive_dir == Path(temp_archive_dir)
        assert archiver.index_file == Path(temp_archive_dir) / "archive_index.json"
        assert isinstance(archiver.index, dict)
    
    def test_archive_bookmark_from_cache(self, archiver, sample_bookmark, mock_cache, mock_extractor):
        """Test archiving when content is in cache."""
        # Mock cache to return content
        cached_content = {
            'title': 'Cached Title',
            'text': 'Cached content',
            'description': 'From cache'
        }
        mock_cache.get.return_value = cached_content
        
        with patch.object(archiver, 'cache', mock_cache):
            with patch.object(archiver, 'extractors', [mock_extractor]):
                with patch.object(archiver, '_save_to_wayback', return_value='https://web.archive.org/web/123/example.com'):
                    result = archiver.archive_bookmark(sample_bookmark, save_to_wayback=True)
        
        # Verify cache was checked
        mock_cache.get.assert_called_once_with(sample_bookmark['url'])
        
        # Verify extractor was not called (content from cache)
        mock_extractor.extract.assert_not_called()
        
        # Verify result
        assert 'archive_key' in result
        assert 'timestamp' in result
        assert 'file' in result
        assert result['wayback_url'] == 'https://web.archive.org/web/123/example.com'
        
        # Verify file was created
        archive_key = result['archive_key']
        assert archive_key in archiver.index
    
    def test_archive_bookmark_fresh_fetch(self, archiver, sample_bookmark, mock_cache, mock_extractor):
        """Test archiving with fresh content fetch."""
        # Mock cache to return None (cache miss)
        mock_cache.get.return_value = None
        
        with patch.object(archiver, 'cache', mock_cache):
            with patch.object(archiver, 'extractors', [mock_extractor]):
                with patch.object(archiver, '_save_to_wayback', return_value=None):
                    result = archiver.archive_bookmark(sample_bookmark, force_fetch=True)
        
        # Verify extractor was called
        mock_extractor.extract.assert_called_once_with(sample_bookmark['url'])
        
        # Verify cache was updated
        mock_cache.set.assert_called_once()
        
        # Verify result
        assert 'archive_key' in result
        assert 'timestamp' in result
        assert result['wayback_url'] is None
    
    @patch('requests.get')
    def test_save_to_wayback(self, mock_get, archiver):
        """Test saving to Wayback Machine."""
        url = 'https://example.com'
        
        # Mock successful Wayback response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = f'https://web.archive.org/web/20240101120000/{url}'
        mock_get.return_value = mock_response
        
        result = archiver._save_to_wayback(url)
        
        assert result == mock_response.url
        mock_get.assert_called_once_with(
            f'https://web.archive.org/save/{url}',
            timeout=30,
            allow_redirects=True
        )
    
    @patch('requests.get')
    def test_save_to_wayback_failure(self, mock_get, archiver):
        """Test Wayback Machine save failure."""
        url = 'https://example.com'
        
        # Mock failed response
        mock_get.side_effect = Exception("Network error")
        
        result = archiver._save_to_wayback(url)
        
        assert result is None
    
    @patch('requests.get')
    def test_get_wayback_snapshots(self, mock_get, archiver):
        """Test getting Wayback Machine snapshots."""
        url = 'https://example.com'
        
        # Mock CDX API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            ['timestamp', 'original', 'statuscode', 'digest', 'length'],
            ['20240101120000', url, '200', 'abc123', '1234'],
            ['20240102120000', url, '200', 'def456', '5678']
        ]
        mock_get.return_value = mock_response
        
        snapshots = archiver.get_wayback_snapshots(url)
        
        assert len(snapshots) == 2
        assert snapshots[0]['timestamp'] == '20240101120000'
        assert 'wayback_url' in snapshots[0]
        assert 'datetime' in snapshots[0]
    
    def test_get_archive_versions(self, archiver, sample_bookmark):
        """Test getting archive versions."""
        # Archive the same bookmark multiple times
        with patch.object(archiver, '_save_to_wayback', return_value=None):
            with patch.object(archiver, 'cache') as mock_cache:
                mock_cache.get.return_value = {'title': 'Test', 'text': 'Content'}
                
                # Archive twice
                result1 = archiver.archive_bookmark(sample_bookmark)
                result2 = archiver.archive_bookmark(sample_bookmark)
        
        versions = archiver.get_archive_versions(sample_bookmark['url'])
        
        assert len(versions) >= 2
        assert all('timestamp' in v for v in versions)
        assert all('file' in v for v in versions)
    
    def test_get_archived_content(self, archiver, sample_bookmark):
        """Test retrieving archived content."""
        # Archive a bookmark
        with patch.object(archiver, '_save_to_wayback', return_value=None):
            with patch.object(archiver, 'cache') as mock_cache:
                mock_cache.get.return_value = {'title': 'Test', 'text': 'Content'}
                result = archiver.archive_bookmark(sample_bookmark)
        
        # Retrieve archived content
        content = archiver.get_archived_content(sample_bookmark['url'])
        
        assert content is not None
        assert content['url'] == sample_bookmark['url']
        assert 'content' in content
        assert 'timestamp' in content
    
    def test_get_archived_content_specific_version(self, archiver, sample_bookmark):
        """Test retrieving specific version of archived content."""
        # Archive a bookmark
        with patch.object(archiver, '_save_to_wayback', return_value=None):
            with patch.object(archiver, 'cache') as mock_cache:
                mock_cache.get.return_value = {'title': 'Test', 'text': 'Content'}
                result = archiver.archive_bookmark(sample_bookmark)
        
        timestamp = result['timestamp']
        
        # Retrieve specific version
        content = archiver.get_archived_content(sample_bookmark['url'], timestamp)
        
        assert content is not None
        assert content['timestamp'] == timestamp
    
    def test_bulk_archive(self, archiver, mock_cache, mock_extractor):
        """Test bulk archiving of bookmarks."""
        bookmarks = [
            {'url': 'https://example1.com', 'title': 'Example 1'},
            {'url': 'https://example2.com', 'title': 'Example 2'},
            {'url': 'https://example3.com', 'title': 'Example 3'}
        ]
        
        # Mock cache and extractor
        mock_cache.get.return_value = {'title': 'Test', 'text': 'Content'}
        
        progress_calls = []
        def progress_callback(current, total, url):
            progress_calls.append((current, total, url))
        
        with patch.object(archiver, 'cache', mock_cache):
            with patch.object(archiver, 'extractors', [mock_extractor]):
                with patch.object(archiver, '_save_to_wayback', return_value='https://archive.org/...'):
                    with patch('time.sleep'):  # Speed up test
                        stats = archiver.bulk_archive(bookmarks, progress_callback=progress_callback)
        
        assert stats['total'] == 3
        assert stats['archived'] == 3
        assert stats['wayback_saved'] == 3
        assert len(progress_calls) == 3
    
    def test_bulk_archive_skip_recent(self, archiver, sample_bookmark):
        """Test bulk archive skips recently archived bookmarks."""
        # Archive a bookmark
        with patch.object(archiver, '_save_to_wayback', return_value=None):
            with patch.object(archiver, 'cache') as mock_cache:
                mock_cache.get.return_value = {'title': 'Test', 'text': 'Content'}
                archiver.archive_bookmark(sample_bookmark)
        
        # Try to archive again in bulk (should skip)
        with patch('time.sleep'):
            stats = archiver.bulk_archive([sample_bookmark])
        
        assert stats['already_archived'] == 1
        assert stats['archived'] == 0
    
    def test_export_archive_summary(self, archiver, sample_bookmark, tmp_path):
        """Test exporting archive summary."""
        # Archive some bookmarks
        with patch.object(archiver, '_save_to_wayback', return_value='https://archive.org/test'):
            with patch.object(archiver, 'cache') as mock_cache:
                mock_cache.get.return_value = {'title': 'Test', 'text': 'Content'}
                archiver.archive_bookmark(sample_bookmark)
        
        # Export summary
        summary = archiver.export_archive_summary()
        
        assert '# BTK Archive Summary' in summary
        assert sample_bookmark['url'] in summary
        assert 'Wayback' in summary
        
        # Export to file
        output_file = tmp_path / 'summary.md'
        archiver.export_archive_summary(str(output_file))
        assert output_file.exists()
    
    def test_archive_key_generation(self, archiver):
        """Test archive key generation is consistent."""
        url = 'https://example.com'
        key1 = archiver._get_archive_key(url)
        key2 = archiver._get_archive_key(url)
        
        assert key1 == key2
        assert len(key1) == 16  # SHA256 truncated to 16 chars
    
    def test_index_persistence(self, archiver, sample_bookmark):
        """Test that index is persisted and reloaded."""
        # Archive a bookmark
        with patch.object(archiver, '_save_to_wayback', return_value=None):
            with patch.object(archiver, 'cache') as mock_cache:
                mock_cache.get.return_value = {'title': 'Test', 'text': 'Content'}
                archiver.archive_bookmark(sample_bookmark)
        
        # Create new archiver instance (should load index)
        new_archiver = BookmarkArchiver(archive_dir=str(archiver.archive_dir))
        
        archive_key = archiver._get_archive_key(sample_bookmark['url'])
        assert archive_key in new_archiver.index
        assert new_archiver.index[archive_key]['url'] == sample_bookmark['url']


class TestGlobalArchiver:
    """Test global archiver instance."""
    
    def test_singleton_archiver(self):
        """Test that get_archiver returns singleton."""
        archiver1 = get_archiver()
        archiver2 = get_archiver()
        assert archiver1 is archiver2