# Bookmark Toolkit (btk) LLM Context Guide

## Command Reference

### Importing Bookmarks
```sh
btk import bookmarks.html --format netscape --output $lib_dir
```

### Searching Bookmarks
```sh
btk search $lib_dir "statistics"
```

### Listing Bookmarks by Index
```sh
btk list-index $lib_dir 1 2 3
```

### Adding a Bookmark
```sh
btk add $lib_dir --title "Example Site" --url "https://example.com"
```

### Editing a Bookmark
```sh
btk edit $lib_dir 1 --title "Updated Title"
```

### Removing a Bookmark
```sh
btk remove $lib_dir 2
```

### Listing All Bookmarks
```sh
btk list $lib_dir
```

### Visiting a Bookmark
```sh
btk visit $lib_dir 103
```

### Merging Bookmarks (Set Operations)
```sh
btk merge union lib1 lib2 lib3 --output merged
```

### Generating a URL Mention Graph
```sh
btk cloud $lib_dir --output graph.png
```
Additional options:
```sh
btk cloud $lib_dir --output graph.html --max-bookmarks 100 --stats
```

### Checking Reachability of Bookmarks
```sh
btk reachable $lib_dir
```

### Purging Unreachable Bookmarks
```sh
btk purge $lib_dir --output purged
```

### Exporting Bookmarks
```sh
btk export $lib_dir --output bookmarks.csv
```

## JMESPath Querying for Structured Bookmark Retrieval

#### Get all starred bookmarks:
```sh
btk jmespath $lib_dir "[?stars == `true`]"
```

#### Get frequently visited bookmarks:
```sh
btk jmespath $lib_dir "[?visit_count > `5`]"
```

Note that it is really important to use backticks around numbers in JMESPath queries.

#### Find bookmarks containing 'wikipedia' in the URL and only show title and URL:
```sh
btk jmespath $lib_dir "[?contains(url, 'wikipedia')].{title: title, url: url}"
```

#### Retrieve bookmarks added after a specific date:
```sh
btk jmespath $lib_dir "[?added > `2023-01-01`]"
```

#### Find bookmarks tagged with 'research':
```sh
btk jmespath $lib_dir "[?contains(tags, 'research')]"
```

#### Query Example for LLM:
```sh
btk jmespath $lib_dir "[?stars == `true` && visit_count > `0`]"
```

## Structure of `bookmarks.json`

In the bookmark library stored in the directory `$lib_dir`, we have a number of files, but the main file of interest is `bookmarks.json`.
The `bookmarks.json` file contains structured data for bookmarks.

### Example `bookmarks.json`:

```json
[
  {
    "id": 1,
    "unique_id": "db558d9a",
    "title": "1.3 Stochastic convergence review | Notes for Nonparametric Statistics",
    "url": "https://bookdown.org/egarpor/NP-UC3M/intro-stoch.html",
    "added": "2023-02-24T13:59:56+00:00",
    "stars": false,
    "tags": [],
    "visit_count": 2,
    "description": "",
    "favicon": "favicons/105c261084b53d11005aa610b5262770.ico",
    "last_visited": "2025-01-19T06:14:54.355523+00:00",
    "reachable": true
  },
  {
    "id": 10,
    "unique_id": "9136cf33",
    "title": "1. Overview - YouTube",
    "url": "https://www.youtube.com/watch?v=qs2uCuDL2OQ&ab_channel=GaryKing",
    "added": "2023-02-24T13:59:56+00:00",
    "stars": true,
    "tags": [
      "test1",
      "test2"
    ],
    "visit_count": 4,
    "description": "What?",
    "favicon": "favicons/3e15e41c6dfde52a0e8d726798992425.png",
    "last_visited": "2025-01-19T06:15:08.642855+00:00",
    "reachable": true
  }  
]
```

## Response Format for LLM Queries

When you are prompted with a query, respond in JSON. The JSON should take the following general format:

```json
{
  "command": "command_name",
  "args": ["$lib_dir", "<args>"]
}
```

### Example 1

Suppose the query is "Find bookmarks that are starred and have a visit count greater than 0."
Then, you might respond with the output:

```json
{
  "command": "jmespath",
  "args": ["$lib_dir", "[?stars == `true` && visit_count > `0`]"]
}
```

### Example 2

If the prompt was slightly different, for example "Find bookmark that are starred and have a visit count greater than 3, and only show me the title and URL", the response might be:

```json
{
  "command": "jmespath",
  "args": ["$lib_dir", "[?stars == `true` && visit_count > `3`].{title: title, url: url}"]
}
```

A full list of commands is give by:

- `import`: Import bookmarks from a Netscape Bookmark Format HTML file
  - `html_file`: Path to the HTML bookmark file
  - `lib_dir`: Directory to store the imported bookmarks library

- `search`: Search bookmarks by query
- `list-index`: List the bookmarks with the given indices
- `add`: Add a new bookmark
- `edit`: Edit a bookmark by its ID
- `remove`: Remove a bookmark by its ID
- `list`: List all bookmarks with their IDs and unique IDs
- `visit`: Visit a bookmark by its ID
- `merge`: Perform merge (set) operations on bookmark libraries
- `cloud`: Generate a URL mention graph from bookmarks
- `reachable`: Check and mark bookmarks as reachable or not
- `purge`: Remove bookmarks marked as not reachable
- `export`:  Export bookmarks to a different format
- `jmespath`: Query bookmarks using JMESPath
- `llm`: Query the bookmark library using a Large Language Model
