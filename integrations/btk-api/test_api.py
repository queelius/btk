#!/usr/bin/env python3
"""
Test script for BTK API server.
Run this while the server is running to verify functionality.
"""

import requests
import json
import sys
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"


def test_endpoint(method: str, endpoint: str, data: Dict[str, Any] = None, 
                 expected_status: int = 200, description: str = "") -> bool:
    """Test an API endpoint."""
    url = f"{BASE_URL}{endpoint}"
    print(f"\n{'='*60}")
    print(f"Testing: {description or endpoint}")
    print(f"Method: {method} {endpoint}")
    
    try:
        if method == "GET":
            response = requests.get(url, params=data)
        elif method == "POST":
            response = requests.post(url, json=data)
        elif method == "PUT":
            response = requests.put(url, json=data)
        elif method == "DELETE":
            response = requests.delete(url)
        else:
            print(f"❌ Unknown method: {method}")
            return False
        
        if response.status_code == expected_status:
            print(f"✅ Status: {response.status_code}")
            if response.text:
                try:
                    result = response.json()
                    print(f"Response: {json.dumps(result, indent=2)[:200]}...")
                except:
                    print(f"Response: {response.text[:200]}...")
            return True
        else:
            print(f"❌ Expected status {expected_status}, got {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Connection failed. Is the server running on {BASE_URL}?")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def run_tests():
    """Run all API tests."""
    print("BTK API Test Suite")
    print("=" * 60)
    
    results = []
    
    # Test root endpoint
    results.append(test_endpoint(
        "GET", "/", 
        description="Root endpoint"
    ))
    
    # Test getting bookmarks (might be empty)
    results.append(test_endpoint(
        "GET", "/bookmarks",
        description="Get all bookmarks"
    ))
    
    # Test adding a bookmark
    test_bookmark = {
        "url": "https://example.com",
        "title": "Test Bookmark",
        "tags": ["test", "api"],
        "description": "Created by API test",
        "stars": True
    }
    results.append(test_endpoint(
        "POST", "/bookmarks",
        data=test_bookmark,
        expected_status=201,
        description="Create a bookmark"
    ))
    
    # Test searching
    results.append(test_endpoint(
        "POST", "/search",
        data={"query": "test", "limit": 10},
        description="Search bookmarks"
    ))
    
    # Test getting tags
    results.append(test_endpoint(
        "GET", "/tags",
        description="Get all tags"
    ))
    
    # Test tag tree
    results.append(test_endpoint(
        "GET", "/tags?format=tree",
        description="Get tag tree"
    ))
    
    # Test statistics
    results.append(test_endpoint(
        "GET", "/stats",
        description="Get statistics"
    ))
    
    # Test deduplication preview
    results.append(test_endpoint(
        "POST", "/dedupe",
        data={"strategy": "merge", "preview": True},
        description="Preview deduplication"
    ))
    
    # Test export
    results.append(test_endpoint(
        "GET", "/export/json",
        description="Export as JSON"
    ))
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("✅ All tests passed!")
        return 0
    else:
        print(f"❌ {total - passed} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())