#!/usr/bin/env python3
"""
Test script for new BTK integration plugins.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from btk.plugins import PluginRegistry
from integrations.duplicate_finder import DuplicateFinder
from integrations.social_metadata import SocialMetadataExtractor

def test_duplicate_finder():
    """Test the duplicate finder plugin."""
    print("\n=== Testing Duplicate Finder ===")
    
    finder = DuplicateFinder()
    
    # Test bookmarks with various duplicate patterns
    bookmarks = [
        {
            'id': 1,
            'url': 'https://example.com/page?utm_source=twitter',
            'title': 'Example Page',
            'tags': ['test'],
            'visit_count': 5
        },
        {
            'id': 2,
            'url': 'https://www.example.com/page',  # Same page, different protocol/www
            'title': 'Example Page',
            'tags': ['demo'],
            'visit_count': 3
        },
        {
            'id': 3,
            'url': 'https://example.com/page?fbclid=abc123',  # Same page with tracking
            'title': 'Example Page - Best Version',
            'description': 'This is the example page',
            'tags': ['test', 'example'],
            'visit_count': 10
        },
        {
            'id': 4,
            'url': 'https://different.com/article',
            'title': 'Different Article',
            'tags': ['article'],
            'visit_count': 1
        },
        {
            'id': 5,
            'url': 'https://different.com/article',  # Exact duplicate
            'title': 'Different Article',
            'tags': ['reading'],
            'visit_count': 2
        }
    ]
    
    # Find duplicates
    duplicates = finder.find_duplicates(bookmarks)
    
    print(f"\nFound duplicate strategies: {list(duplicates.keys())}")
    
    for strategy, groups in duplicates.items():
        if groups:
            print(f"\n{strategy}: {len(groups)} groups")
            for i, group in enumerate(groups, 1):
                print(f"  Group {i}:")
                for bookmark in group:
                    print(f"    - ID {bookmark['id']}: {bookmark['url']}")
    
    # Test merging
    if duplicates.get('normalized_url'):
        group = duplicates['normalized_url'][0]
        print(f"\nMerging group with {len(group)} bookmarks...")
        merged = finder.merge_duplicates(group, 'merge_all')
        print(f"Merged bookmark:")
        print(f"  Title: {merged.get('title')}")
        print(f"  Tags: {merged.get('tags')}")
        print(f"  Visit count: {merged.get('visit_count')}")
        print(f"  Description: {merged.get('description')}")
        print(f"  Merged from: {merged.get('merged_from')} bookmarks")
    
    # Get stats
    stats = finder.get_duplicate_stats(bookmarks)
    print(f"\nDuplicate Statistics:")
    print(f"  Total bookmarks: {stats['total_bookmarks']}")
    print(f"  Total duplicates: {stats['total_duplicates']}")
    print(f"  Duplicate percentage: {stats['duplicate_percentage']:.1f}%")


def test_social_metadata():
    """Test the social metadata extractor."""
    print("\n=== Testing Social Metadata Extractor ===")
    
    extractor = SocialMetadataExtractor(timeout=5)
    
    # Test bookmarks
    test_urls = [
        {
            'id': 1,
            'url': 'https://github.com/anthropics/claude-code',
            'title': 'URL Only'
        },
        {
            'id': 2,
            'url': 'https://www.python.org/',
            'title': 'Python'
        }
    ]
    
    for bookmark in test_urls:
        print(f"\nExtracting metadata for: {bookmark['url']}")
        enriched = extractor.enrich(bookmark.copy())
        
        if enriched.get('social_metadata'):
            metadata = enriched['social_metadata']
            
            # Show Open Graph data
            if metadata.get('open_graph'):
                print("  Open Graph:")
                for key, value in list(metadata['open_graph'].items())[:5]:
                    if isinstance(value, str) and len(value) > 100:
                        value = value[:100] + "..."
                    print(f"    {key}: {value}")
            
            # Show Twitter Card data
            if metadata.get('twitter_card'):
                print("  Twitter Card:")
                for key, value in list(metadata['twitter_card'].items())[:5]:
                    if isinstance(value, str) and len(value) > 100:
                        value = value[:100] + "..."
                    print(f"    {key}: {value}")
            
            # Show enriched fields
            print("  Enriched bookmark fields:")
            for field in ['title', 'description', 'preview_image', 'site_name', 'author']:
                if enriched.get(field) and enriched.get(field) != bookmark.get(field):
                    value = enriched[field]
                    if isinstance(value, str) and len(value) > 100:
                        value = value[:100] + "..."
                    print(f"    {field}: {value}")
        else:
            print("  No social metadata extracted")


def test_plugin_registry():
    """Test plugin registration."""
    print("\n=== Testing Plugin Registry ===")
    
    registry = PluginRegistry()
    
    # Register plugins
    finder = DuplicateFinder()
    registry.register(finder)  # Use default type
    
    extractor = SocialMetadataExtractor()
    registry.register(extractor, 'bookmark_enricher')
    
    # List plugins
    print("\nRegistered plugins by type:")
    for plugin_type in registry.list_types():
        plugins = registry.get_plugins(plugin_type)
        print(f"  {plugin_type}:")
        for plugin in plugins:
            print(f"    - {plugin.name} (v{plugin.metadata.version}): {plugin.metadata.description}")


if __name__ == "__main__":
    print("Testing new BTK integration plugins...")
    
    test_duplicate_finder()
    test_social_metadata()
    test_plugin_registry()
    
    print("\n✅ All tests completed!")