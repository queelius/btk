"""
Test CLI integration for hierarchical export command.
"""
import pytest
import os
import json
from pathlib import Path
import subprocess
import sys


class TestCLIHierarchicalExport:
    """Test hierarchical export CLI command."""
    
    def create_test_library(self, lib_dir):
        """Create a test bookmark library with hierarchical tags."""
        bookmarks = [
            {
                'id': 1,
                'unique_id': 'test1',
                'url': 'https://python.org',
                'title': 'Python',
                'tags': ['programming/languages/python', 'documentation'],
                'description': 'Python programming language',
                'stars': True,
                'added': '2024-01-01T00:00:00Z',
                'visit_count': 5,
                'last_visited': None,
                'favicon': None,
                'reachable': True
            },
            {
                'id': 2,
                'unique_id': 'test2',
                'url': 'https://golang.org',
                'title': 'Go',
                'tags': ['programming/languages/go'],
                'description': 'Go programming language',
                'stars': False,
                'added': '2024-01-01T00:00:00Z',
                'visit_count': 2,
                'last_visited': None,
                'favicon': None,
                'reachable': True
            }
        ]
        
        os.makedirs(lib_dir, exist_ok=True)
        with open(os.path.join(lib_dir, 'bookmarks.json'), 'w') as f:
            json.dump(bookmarks, f)
    
    def test_hierarchical_export_markdown_cli(self, temp_lib_dir):
        """Test hierarchical export via CLI with markdown format."""
        # Create test library
        lib_dir = os.path.join(temp_lib_dir, 'test_lib')
        self.create_test_library(lib_dir)
        
        # Export hierarchically via CLI
        output_dir = os.path.join(temp_lib_dir, 'hierarchical_output')
        result = subprocess.run([
            sys.executable, '-m', 'btk.cli', 'export', lib_dir, 'hierarchical',
            '--output', output_dir,
            '--hierarchical-format', 'markdown'
        ], capture_output=True, text=True)
        
        # Check command succeeded
        assert result.returncode == 0
        assert 'Exported' in result.stdout
        assert 'Index file created' in result.stdout
        
        # Verify output structure
        assert os.path.exists(output_dir)
        assert os.path.exists(os.path.join(output_dir, 'index.md'))
        assert os.path.exists(os.path.join(output_dir, 'programming'))
        assert os.path.exists(os.path.join(output_dir, 'documentation'))
        
        # Check content
        prog_file = os.path.join(output_dir, 'programming', 'programming.md')
        assert os.path.exists(prog_file)
        with open(prog_file) as f:
            content = f.read()
            assert 'Python' in content
            assert 'Go' in content
            assert '## languages > python' in content
            assert '## languages > go' in content
    
    def test_hierarchical_export_json_cli(self, temp_lib_dir):
        """Test hierarchical export via CLI with JSON format."""
        # Create test library
        lib_dir = os.path.join(temp_lib_dir, 'test_lib')
        self.create_test_library(lib_dir)
        
        # Export hierarchically via CLI
        output_dir = os.path.join(temp_lib_dir, 'hierarchical_json')
        result = subprocess.run([
            sys.executable, '-m', 'btk.cli', 'export', lib_dir, 'hierarchical',
            '--output', output_dir,
            '--hierarchical-format', 'json'
        ], capture_output=True, text=True)
        
        # Check command succeeded
        assert result.returncode == 0
        
        # Verify JSON files were created
        prog_file = os.path.join(output_dir, 'programming', 'programming.json')
        assert os.path.exists(prog_file)
        
        with open(prog_file) as f:
            data = json.load(f)
            assert len(data) == 2
            assert any(b['title'] == 'Python' for b in data)
            assert any(b['title'] == 'Go' for b in data)
    
    def test_hierarchical_export_custom_separator_cli(self, temp_lib_dir):
        """Test hierarchical export with custom separator via CLI."""
        # Create test library with custom separator
        lib_dir = os.path.join(temp_lib_dir, 'test_lib')
        bookmarks = [{
            'id': 1,
            'unique_id': 'test1',
            'url': 'https://example.com',
            'title': 'Example',
            'tags': ['work:projects:client-a'],
            'description': 'Client A project',
            'stars': True,
            'added': '2024-01-01T00:00:00Z',
            'visit_count': 0,
            'last_visited': None,
            'favicon': None,
            'reachable': True
        }]
        
        os.makedirs(lib_dir, exist_ok=True)
        with open(os.path.join(lib_dir, 'bookmarks.json'), 'w') as f:
            json.dump(bookmarks, f)
        
        # Export with custom separator
        output_dir = os.path.join(temp_lib_dir, 'custom_sep_output')
        result = subprocess.run([
            sys.executable, '-m', 'btk.cli', 'export', lib_dir, 'hierarchical',
            '--output', output_dir,
            '--tag-separator', ':'
        ], capture_output=True, text=True)
        
        # Check command succeeded
        assert result.returncode == 0
        
        # Verify structure uses custom separator
        work_dir = os.path.join(output_dir, 'work')
        assert os.path.exists(work_dir)
        
        work_file = os.path.join(work_dir, 'work.md')
        with open(work_file) as f:
            content = f.read()
            assert '## projects > client-a' in content