"""
Tests for content extraction functionality.
"""

import pytest
from unittest.mock import patch, MagicMock, Mock
from bs4 import BeautifulSoup
from btk.content_extractor import BasicContentExtractor, EnhancedTagSuggester


class TestBasicContentExtractor:
    """Test BasicContentExtractor class."""
    
    @pytest.fixture
    def extractor(self):
        """Create a content extractor without cache."""
        return BasicContentExtractor(timeout=5, use_cache=False)
    
    @pytest.fixture
    def extractor_with_cache(self):
        """Create a content extractor with cache."""
        return BasicContentExtractor(timeout=5, use_cache=True)
    
    @pytest.fixture
    def mock_response(self):
        """Create a mock HTTP response with sample HTML."""
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <title>Test Page Title</title>
            <meta name="description" content="This is a test page description">
            <meta name="keywords" content="test, sample, page">
            <meta name="author" content="John Doe">
            <meta property="og:description" content="OpenGraph description">
            <meta property="article:published_time" content="2024-01-01T12:00:00Z">
        </head>
        <body>
            <main>
                <h1>Main Heading</h1>
                <p>This is the main content of the page. It contains some text about programming and Python.</p>
                <p>Another paragraph with more content about web development and JavaScript.</p>
            </main>
            <img src="/image1.jpg" alt="Test Image" title="Image Title">
            <img src="https://example.com/image2.png" alt="Another Image">
            <a href="https://example.com/link1">External Link 1</a>
            <a href="https://example.com/link2">External Link 2</a>
            <a href="/relative/link">Relative Link</a>
        </body>
        </html>
        """
        response = MagicMock()
        response.content = html_content.encode('utf-8')
        response.status_code = 200
        response.raise_for_status = MagicMock()
        return response
    
    @patch('requests.Session.get')
    def test_extract_basic_content(self, mock_get, extractor, mock_response):
        """Test basic content extraction."""
        mock_get.return_value = mock_response
        
        result = extractor.extract('https://example.com')
        
        # Check basic fields
        assert result['url'] == 'https://example.com'
        assert result['title'] == 'Test Page Title'
        assert result['description'] == 'This is a test page description'
        assert result['author'] == 'John Doe'
        assert result['language'] == 'en'
        
        # Check keywords
        assert result['keywords'] == ['test', 'sample', 'page']
        
        # Check text content
        assert 'Main Heading' in result['text']
        assert 'programming and Python' in result['text']
        
        # Check word count and reading time
        assert result['word_count'] > 0
        assert result['reading_time'] > 0
    
    @patch('requests.Session.get')
    def test_extract_meta_tags(self, mock_get, extractor, mock_response):
        """Test meta tag extraction."""
        mock_get.return_value = mock_response
        
        result = extractor.extract('https://example.com')
        
        meta_tags = result['meta_tags']
        assert 'description' in meta_tags
        assert 'keywords' in meta_tags
        assert 'author' in meta_tags
        assert 'og:description' in meta_tags
        assert 'article:published_time' in meta_tags
    
    @patch('requests.Session.get')
    def test_extract_images(self, mock_get, extractor, mock_response):
        """Test image extraction."""
        mock_get.return_value = mock_response
        
        result = extractor.extract('https://example.com')
        
        images = result['images']
        assert len(images) == 2
        
        # Check first image (relative URL should be made absolute)
        assert images[0]['url'] == 'https://example.com/image1.jpg'
        assert images[0]['alt'] == 'Test Image'
        assert images[0]['title'] == 'Image Title'
        
        # Check second image (already absolute)
        assert images[1]['url'] == 'https://example.com/image2.png'
    
    @patch('requests.Session.get')
    def test_extract_links(self, mock_get, extractor, mock_response):
        """Test link extraction."""
        mock_get.return_value = mock_response
        
        result = extractor.extract('https://example.com')
        
        links = result['links']
        assert len(links) == 2  # Only external links
        assert links[0]['url'] == 'https://example.com/link1'
        assert links[0]['text'] == 'External Link 1'
    
    @patch('requests.Session.get')
    def test_extract_with_cache(self, mock_get, extractor_with_cache, mock_response):
        """Test extraction with cache enabled."""
        mock_get.return_value = mock_response
        
        with patch.object(extractor_with_cache.cache, 'get', return_value=None) as mock_cache_get:
            with patch.object(extractor_with_cache.cache, 'set') as mock_cache_set:
                result = extractor_with_cache.extract('https://example.com')
        
        # Cache should be checked first
        mock_cache_get.assert_called_once_with('https://example.com')
        
        # Result should be cached
        mock_cache_set.assert_called_once()
        cached_data = mock_cache_set.call_args[0][1]
        assert cached_data['title'] == 'Test Page Title'
    
    @patch('requests.Session.get')
    def test_extract_from_cache(self, mock_get, extractor_with_cache):
        """Test extraction when content is already cached."""
        cached_content = {
            'title': 'Cached Title',
            'text': 'Cached content',
            'description': 'From cache'
        }
        
        with patch.object(extractor_with_cache.cache, 'get', return_value=cached_content):
            result = extractor_with_cache.extract('https://example.com')
        
        # Should not make HTTP request
        mock_get.assert_not_called()
        
        # Should return cached content
        assert result == cached_content
    
    @patch('requests.Session.get')
    def test_extract_force_fetch(self, mock_get, extractor_with_cache, mock_response):
        """Test force fetch bypasses cache."""
        mock_get.return_value = mock_response
        
        cached_content = {'title': 'Old cached content'}
        
        with patch.object(extractor_with_cache.cache, 'get', return_value=cached_content):
            with patch.object(extractor_with_cache.cache, 'set') as mock_cache_set:
                result = extractor_with_cache.extract('https://example.com', force_fetch=True)
        
        # Should make HTTP request despite cache
        mock_get.assert_called_once()
        
        # Should update cache
        mock_cache_set.assert_called_once()
        
        # Should return fresh content
        assert result['title'] == 'Test Page Title'
    
    @patch('requests.Session.get')
    def test_extract_request_failure(self, mock_get, extractor):
        """Test handling of request failure."""
        mock_get.side_effect = Exception("Network error")
        
        result = extractor.extract('https://example.com')
        
        # Should return basic structure with None values
        assert result['url'] == 'https://example.com'
        assert result['title'] is None
        assert result['text'] is None
    
    @patch('requests.Session.get')
    def test_extract_text_content(self, mock_get, extractor):
        """Test text content extraction from different containers."""
        html_variants = [
            # Test with article tag
            """
            <html><body>
            <article>
                <p>Article content here</p>
            </article>
            </body></html>
            """,
            # Test with main tag
            """
            <html><body>
            <main>
                <p>Main content here</p>
            </main>
            </body></html>
            """,
            # Test with class="content"
            """
            <html><body>
            <div class="content">
                <p>Div content here</p>
            </div>
            </body></html>
            """,
            # Test fallback to body
            """
            <html><body>
                <p>Body content here</p>
            </body></html>
            """
        ]
        
        for html in html_variants:
            response = MagicMock()
            response.content = html.encode('utf-8')
            response.raise_for_status = MagicMock()
            mock_get.return_value = response
            
            result = extractor.extract('https://example.com')
            assert result['text'] is not None
            assert 'content here' in result['text'].lower()
    
    @patch('requests.Session.get')
    def test_extract_removes_scripts_and_styles(self, mock_get, extractor):
        """Test that script and style elements are removed."""
        html = """
        <html>
        <head>
            <style>body { color: red; }</style>
        </head>
        <body>
            <p>Visible content</p>
            <script>console.log('This should not appear');</script>
            <noscript>No script content</noscript>
        </body>
        </html>
        """
        response = MagicMock()
        response.content = html.encode('utf-8')
        response.raise_for_status = MagicMock()
        mock_get.return_value = response
        
        result = extractor.extract('https://example.com')
        
        assert 'Visible content' in result['text']
        assert 'console.log' not in result['text']
        assert 'color: red' not in result['text']
        assert 'No script content' not in result['text']
    
    @patch('requests.Session.get')
    def test_text_content_limit(self, mock_get, extractor):
        """Test that text content is limited to 10000 characters."""
        # Create very long content
        long_text = 'x' * 20000
        html = f"<html><body><p>{long_text}</p></body></html>"
        
        response = MagicMock()
        response.content = html.encode('utf-8')
        response.raise_for_status = MagicMock()
        mock_get.return_value = response
        
        result = extractor.extract('https://example.com')
        
        assert len(result['text']) == 10000
    
    def test_extractor_metadata(self, extractor):
        """Test extractor metadata property."""
        assert extractor.metadata.name == "basic_content_extractor"
        assert extractor.metadata.version == "1.0.0"


class TestEnhancedTagSuggester:
    """Test EnhancedTagSuggester class."""
    
    @pytest.fixture
    def suggester(self):
        """Create a tag suggester."""
        return EnhancedTagSuggester()
    
    def test_suggest_programming_language_tags(self, suggester):
        """Test programming language tag suggestions."""
        # Test Python
        tags = suggester.suggest_tags(
            'https://example.com',
            title='Python Tutorial',
            content='Learn Python programming with Django framework'
        )
        assert 'python' in tags
        
        # Test JavaScript
        tags = suggester.suggest_tags(
            'https://example.com',
            title='React Guide',
            content='Build web apps with JavaScript and React'
        )
        assert 'javascript' in tags
        
        # Test multiple languages
        tags = suggester.suggest_tags(
            'https://example.com',
            content='Compare Python vs JavaScript for web development with Rust backend'
        )
        assert 'python' in tags
        assert 'javascript' in tags
        assert 'rust' in tags
    
    def test_suggest_topic_tags(self, suggester):
        """Test topic tag suggestions."""
        # Machine learning
        tags = suggester.suggest_tags(
            'https://example.com',
            content='Deep learning and neural networks in machine learning'
        )
        assert 'machine-learning' in tags
        
        # Web development
        tags = suggester.suggest_tags(
            'https://example.com',
            content='Frontend and backend web development tutorial'
        )
        assert 'web-development' in tags
        
        # DevOps
        tags = suggester.suggest_tags(
            'https://example.com',
            content='Docker and Kubernetes for CI/CD pipelines'
        )
        assert 'devops' in tags
    
    def test_suggest_content_type_tags(self, suggester):
        """Test content type tag suggestions."""
        # Video
        tags = suggester.suggest_tags(
            'https://example.com',
            title='Watch this YouTube video'
        )
        assert 'video' in tags
        
        # Podcast
        tags = suggester.suggest_tags(
            'https://example.com',
            description='Listen to this podcast episode'
        )
        assert 'podcast' in tags
        
        # Course
        tags = suggester.suggest_tags(
            'https://example.com',
            content='Complete course curriculum with lessons'
        )
        assert 'course' in tags
    
    def test_suggest_technical_tags(self, suggester):
        """Test technical term tag suggestions."""
        # Git
        tags = suggester.suggest_tags(
            'https://example.com',
            content='GitHub repository with version control'
        )
        assert 'git' in tags
        
        # Testing
        tags = suggester.suggest_tags(
            'https://example.com',
            content='Unit testing with pytest framework'
        )
        assert 'testing' in tags
        
        # Algorithm
        tags = suggester.suggest_tags(
            'https://example.com',
            content='Algorithm complexity and data structures'
        )
        assert 'algorithm' in tags
    
    def test_suggest_tags_no_duplicates(self, suggester):
        """Test that suggested tags have no duplicates."""
        tags = suggester.suggest_tags(
            'https://example.com',
            title='Python Python Python',
            content='Python programming with Python'
        )
        
        # Should only have one 'python' tag
        assert tags.count('python') == 1
    
    def test_suggest_tags_empty_input(self, suggester):
        """Test tag suggestion with empty input."""
        tags = suggester.suggest_tags('https://example.com')
        assert tags == []
        
        tags = suggester.suggest_tags('https://example.com', title='', content='', description='')
        assert tags == []
    
    def test_suggest_tags_case_insensitive(self, suggester):
        """Test that tag suggestion is case insensitive."""
        tags = suggester.suggest_tags(
            'https://example.com',
            content='PYTHON and JavaScript with DOCKER'
        )
        assert 'python' in tags
        assert 'javascript' in tags
        assert 'devops' in tags  # Docker triggers devops
    
    def test_suggest_multiple_categories(self, suggester):
        """Test suggestions across multiple categories."""
        tags = suggester.suggest_tags(
            'https://example.com',
            title='Machine Learning Tutorial Video',
            content='Learn Python for data science and machine learning. This tutorial covers neural networks.',
            description='A comprehensive guide to ML'
        )
        
        # Should have tags from different categories
        assert 'python' in tags  # Language
        assert 'machine-learning' in tags  # Topic
        assert 'data-science' in tags  # Topic
        assert 'tutorial' in tags  # Topic
        assert 'video' in tags  # Content type
    
    def test_suggester_metadata(self, suggester):
        """Test suggester metadata property."""
        assert suggester.metadata.name == "enhanced_content"
        assert suggester.metadata.version == "1.0.0"