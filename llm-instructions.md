# Bookmark Toolkit (btk) LLM Context Guide

## Command Reference

### Importing Bookmarks
```sh
btk import bookmarks.html --format netscape --output mybookmarks
```

### Searching Bookmarks
```sh
btk search mybookmarks "statistics"
```

### Listing Bookmarks by Index
```sh
btk list-index mybookmarks 1 2 3
```

### Adding a Bookmark
```sh
btk add mybookmarks --title "Example Site" --url "https://example.com"
```

### Editing a Bookmark
```sh
btk edit mybookmarks 1 --title "Updated Title"
```

### Removing a Bookmark
```sh
btk remove mybookmarks 2
```

### Listing All Bookmarks
```sh
btk list mybookmarks
```

### Visiting a Bookmark
```sh
btk visit mybookmarks 103
```

### Merging Bookmarks (Set Operations)
```sh
btk merge union lib1 lib2 lib3 --output merged
```

### Generating a URL Mention Graph
```sh
btk cloud mybookmarks --output graph.png
```
Additional options:
```sh
btk cloud mybookmarks --output graph.html --max-bookmarks 100 --stats
```

### Checking Reachability of Bookmarks
```sh
btk reachable mybookmarks
```

### Purging Unreachable Bookmarks
```sh
btk purge mybookmarks --output purged
```

### Exporting Bookmarks
```sh
btk export mybookmarks --output bookmarks.csv
```

## JMESPath Querying for Structured Bookmark Retrieval

#### Get all starred bookmarks:
```sh
btk jmespath mybookmarks "[?stars == `true`].title"
```

#### Get frequently visited bookmarks:
```sh
btk jmespath mybookmarks "[?visit_count > `5`].url"
```

#### Find bookmarks containing 'wikipedia' in the URL:
```sh
btk jmespath mybookmarks "[?contains(url, 'wikipedia')].{title: title, url: url}"
```

#### Retrieve bookmarks added after a specific date:
```sh
btk jmespath mybookmarks "[?added > `2023-01-01`].title"
```

#### Find bookmarks tagged with 'research':
```sh
btk jmespath mybookmarks "[?contains(tags, 'research')].title"
```

#### Query Example for LLM:
```sh
btk jmespath mybookmarks "[?stars == `true` && visit_count > `0`].title"
```

## Structure of `bookmarks.json`

The `bookmarks.json` file contains structured data for bookmarks. Example format:
```json
[
  {
    "id": 1,
    "title": "Example Site",
    "url": "https://example.com",
    "added": "2023-01-15T12:34:56Z",
    "stars": true,
    "tags": ["reference", "research"],
    "visit_count": 7,
    "last_visited": "2023-06-01T08:00:00Z"
  },
  {
    "id": 2,
    "title": "Another Bookmark",
    "url": "https://another.com",
    "added": "2022-12-10T09:20:30Z",
    "stars": false,
    "tags": ["reading"],
    "visit_count": 3,
    "last_visited": "2023-05-20T10:15:00Z"
  }
]
```

## LLM-Specific Querying

The `.btkrc` file contains LLM API settings:
```ini
[llm]
endpoint = https://api.openai.com/v1/chat/completions
api_key = your_openai_api_key_here
```

Invoke LLM-assisted queries:
```sh
btk llm mybookmarks "Summarize my most visited bookmarks."
```

#### Example for LLM Contextual Processing
```sh
btk llm mybookmarks "Give me a list of titles that are starred and have a visit count greater than 0"
```
This query ensures the LLM retrieves structured bookmark data efficiently.

