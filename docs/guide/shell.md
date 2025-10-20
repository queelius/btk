# Interactive Shell

BTK's interactive shell provides a powerful, filesystem-like interface for browsing and managing your bookmarks. Think of it as navigating your bookmarks the way you navigate directories in Unix - with familiar commands like `cd`, `ls`, and `pwd`.

## Overview

The shell provides a virtual filesystem where bookmarks, tags, and other collections are organized as directories that you can navigate and interact with using intuitive commands.

```bash
$ btk shell

╔════════════════════════════════════════════════════════════════╗
║                     BTK Shell v1.0                              ║
║          Browse your bookmarks like a filesystem                ║
╚════════════════════════════════════════════════════════════════╝

Type 'help' or '?' to list commands.
Type 'help <command>' for command details.
Type 'tutorial' for a quick tour.

btk:/$ ls
bookmarks  tags  starred  archived  recent  domains

btk:/$ cd tags/programming/python
btk:/tags/programming/python$ ls
3298  4095  5124  5789

btk:/tags/programming/python$ cat 4095/title
Advanced Python Techniques
```

## Virtual Filesystem Structure

The shell organizes your bookmarks into a hierarchical virtual filesystem:

```
btk:/
├── bookmarks/          # All bookmarks by ID
│   └── <id>/          # Individual bookmark directory
│       ├── url        # Bookmark URL
│       ├── title      # Bookmark title
│       ├── tags       # Associated tags
│       └── ...        # Other fields
│
├── tags/              # Hierarchical tag browsing
│   ├── <tag>/         # Tag directory
│   │   ├── <subtag>/  # Nested tag
│   │   └── <id>/      # Bookmark with this tag
│   └── ...
│
├── starred/           # Starred bookmarks
│   └── <id>/          # Starred bookmark
│
├── archived/          # Archived bookmarks
│   └── <id>/          # Archived bookmark
│
├── recent/            # Recently active bookmarks (time-based)
│   ├── today/         # Activity from today
│   │   ├── visited/   # Bookmarks visited today
│   │   ├── added/     # Bookmarks added today
│   │   └── starred/   # Bookmarks starred today
│   ├── yesterday/     # Activity from yesterday
│   ├── this-week/     # Activity from this week
│   ├── last-week/     # Activity from last week
│   ├── this-month/    # Activity from this month
│   └── last-month/    # Activity from last month
│
├── domains/           # Browse by domain
│   ├── <domain>/      # Domain directory
│   └── <domain>/<id>/ # Bookmark from domain
│
├── unread/            # Bookmarks never visited (NEW v0.7.1)
│   └── <id>/          # Unread bookmark
│
├── popular/           # Top 100 most visited bookmarks (NEW v0.7.1)
│   └── <id>/          # Popular bookmark
│
├── broken/            # Unreachable bookmarks (NEW v0.7.1)
│   └── <id>/          # Broken bookmark
│
├── untagged/          # Bookmarks without tags (NEW v0.7.1)
│   └── <id>/          # Untagged bookmark
│
└── pdfs/              # PDF document bookmarks (NEW v0.7.1)
    └── <id>/          # PDF bookmark
```

## Navigation Commands

### Basic Navigation

#### `ls` - List Contents

Lists contents of the current directory. The output adapts based on your location:

=== "Root Directory"
    ```bash
    btk:/$ ls
    bookmarks  tags  starred  archived  recent  domains
    ```

=== "Bookmarks Directory"
    ```bash
    btk:/bookmarks$ ls
    ID    Title                        Tags              Added
    ──────────────────────────────────────────────────────────
    1234  Python Tutorial              python,tutorial   2024-01-15
    5678  Advanced Flask               python,web,flask  2024-02-20
    9012  Machine Learning Guide       ml,python         2024-03-10
    ```

=== "Tags Directory"
    ```bash
    btk:/tags$ ls
    programming/  research/  tutorial/  web/
    ```

=== "Specific Tag"
    ```bash
    btk:/tags/programming/python$ ls
    Bookmarks (4):
    3298  NumPy Documentation
    4095  Advanced Python Techniques
    5124  Python Testing Guide
    5789  Asyncio Tutorial

    Subtags:
    data-science/  web/  testing/
    ```

=== "Individual Bookmark"
    ```bash
    btk:/bookmarks/4095$ ls
    url        title      description  tags
    added      stars      visit_count  last_visited
    ```

**Options:**

- `ls -l` - Long format with detailed information
- `ls -a` - Include archived bookmarks
- `ls -s` - Show only starred bookmarks

#### `cd` - Change Directory

Navigate to different locations in the virtual filesystem.

**Examples:**

```bash
# Absolute paths
btk:/$ cd /bookmarks/4095
btk:/bookmarks/4095$

# Relative paths
btk:/bookmarks$ cd 4095
btk:/bookmarks/4095$

# Navigate to tags
btk:/$ cd tags/programming/python
btk:/tags/programming/python$

# Go back to parent
btk:/tags/programming/python$ cd ..
btk:/tags/programming$

# Multiple levels up
btk:/tags/programming/python/data-science$ cd ../../..
btk:/tags$

# Go to root
btk:/tags/programming/python$ cd /
btk:/$
```

**Path Support:**

- Absolute paths: `/bookmarks/123`, `/tags/programming`
- Relative paths: `../..`, `bookmarks/123`, `python/web`
- Special symbols: `.` (current directory), `..` (parent directory)
- Tab completion (coming soon): Auto-complete paths and IDs

#### `pwd` - Print Working Directory

Shows your current location in the virtual filesystem.

```bash
btk:/tags/programming/python$ pwd
/tags/programming/python

btk:/bookmarks/4095$ pwd
/bookmarks/4095
```

### Advanced Navigation

#### `which` - Find Bookmark Location

Find where a bookmark exists in the virtual filesystem.

```bash
btk:/$ which 4095
/bookmarks/4095
/tags/programming/python/4095
/tags/tutorial/4095
/starred/4095
```

#### `recent` - View Recent Activity

Context-aware command showing recent activity. The results are filtered based on your current location.

**Syntax:**

```bash
recent [visited|added|starred] [--limit N]
```

**Examples:**

=== "Recently Visited"
    ```bash
    btk:/$ recent
    # Shows most recently visited bookmarks

    ID    Title                        Last Visited      Times
    ───────────────────────────────────────────────────────────
    4095  Advanced Python Techniques   2024-10-19 14:30  15
    3298  NumPy Documentation          2024-10-19 12:15  23
    5789  Asyncio Tutorial             2024-10-18 16:45  8
    ```

=== "Recently Added"
    ```bash
    btk:/$ recent added
    # Shows most recently added bookmarks

    ID    Title                        Added             Tags
    ───────────────────────────────────────────────────────────
    6543  New Python Article           2024-10-19 15:00  python
    6542  Flask Best Practices         2024-10-19 14:30  python,web
    6541  Docker Tutorial              2024-10-19 09:15  devops
    ```

=== "Recently Starred"
    ```bash
    btk:/$ recent starred
    # Shows most recently starred bookmarks

    ID    Title                        Starred           Tags
    ───────────────────────────────────────────────────────────
    5789  Asyncio Tutorial             2024-10-19 11:00  python,async
    4095  Advanced Python Techniques   2024-10-18 16:30  python,advanced
    ```

=== "Context Filtering"
    ```bash
    # When in a tag directory, only shows bookmarks with that tag
    btk:/tags/programming/python$ recent visited
    # Shows only recently visited Python bookmarks

    ID    Title                        Last Visited      Times
    ───────────────────────────────────────────────────────────
    4095  Advanced Python Techniques   2024-10-19 14:30  15
    3298  NumPy Documentation          2024-10-19 12:15  23
    5789  Asyncio Tutorial             2024-10-18 16:45  8

    # When in starred directory
    btk:/starred$ recent added
    # Shows only recently added bookmarks that are starred
    ```

## Smart Collections (v0.7.1)

Smart collections are auto-updating virtual directories that dynamically filter bookmarks based on specific criteria. They provide instant access to useful bookmark subsets without manual organization.

### Available Collections

BTK provides five built-in smart collections:

#### `/unread` - Never Visited Bookmarks

Bookmarks you've saved but never opened. Perfect for finding articles you meant to read.

```bash
btk:/$ cd unread
btk:/unread$ ls
bookmarks/    (42)   Bookmarks never visited

ID    Title                              Tags
──────────────────────────────────────────────────────────
1001  Machine Learning Paper             research,ml,to-read
1005  Python Best Practices Article      python,tutorial
1023  Database Design Guide              database,tutorial
1055  Architecture Patterns              software,design
```

**Use Cases:**

- Find articles saved for later reading
- Identify bookmarks that need attention
- Discover forgotten resources
- Clean up reading backlog

**Example Workflow:**

```bash
btk:/$ cd unread
btk:/unread$ ls
# Browse unread bookmarks

btk:/unread$ cat 1001/title
Machine Learning Paper: Attention Is All You Need

btk:/unread$ visit 1001
# Opens bookmark
# Visit count increments automatically
# Bookmark removed from /unread on next refresh
```

!!! note "Auto-Updating"
    After visiting a bookmark, it automatically disappears from `/unread` since `visit_count` is no longer 0.

#### `/popular` - Most Visited Bookmarks

Your top 100 most-visited bookmarks, sorted by visit count. Great for finding frequently referenced resources.

```bash
btk:/$ cd popular
btk:/popular$ ls
bookmarks/    (100)  100 most visited bookmarks

ID    Title                        Visit Count  Last Visited
────────────────────────────────────────────────────────────────
3298  NumPy Documentation          45           2024-10-19 12:15
4095  Python Style Guide           38           2024-10-19 14:30
5124  SQL Reference                31           2024-10-18 16:45
2891  Git Commands Cheatsheet      28           2024-10-19 09:20
```

**Use Cases:**

- Find your most-used references
- Identify important resources
- See usage patterns
- Quick access to go-to bookmarks

**Example Workflow:**

```bash
btk:/$ cd popular
btk:/popular$ recent visited
# See which popular bookmarks you've accessed recently

btk:/popular$ cp high-priority *
# Tag all popular bookmarks as high-priority
```

!!! tip "Limited to Top 100"
    The collection shows only your top 100 most-visited bookmarks to keep the list focused and useful.

#### `/broken` - Unreachable Bookmarks

Bookmarks where the URL returns an error or timeout. Helps identify dead links.

```bash
btk:/$ cd broken
btk:/broken$ ls
bookmarks/    (3)    Unreachable bookmarks

ID    Title                        URL
───────────────────────────────────────────────────────────
2345  Old Tutorial Site            https://oldsite.com/tutorial
3456  Defunct Blog Post            https://blog.example.com/post
4567  Archived Documentation       https://docs.oldversion.com
```

**Use Cases:**

- Find and fix broken links
- Update URLs to archived versions
- Remove outdated bookmarks
- Maintain collection health

**Example Workflow:**

```bash
btk:/$ cd broken
btk:/broken$ ls
# Review broken bookmarks

btk:/broken$ cat 2345/url
https://oldsite.com/tutorial

# Search for archived version
btk:/broken$ !firefox "https://web.archive.org/web/*/https://oldsite.com/tutorial"

# Update to archived URL or remove
btk:/broken$ edit 2345 url
# Or
btk:/broken$ rm 2345
```

!!! warning "Reachability Checks"
    Bookmarks are marked as `reachable=false` when content refresh fails. Run `btk content refresh --all` to update reachability status.

#### `/untagged` - Bookmarks Without Tags

Bookmarks that don't have any tags. Useful for maintaining organization.

```bash
btk:/$ cd untagged
btk:/untagged$ ls
bookmarks/    (15)   Bookmarks with no tags

ID    Title                              URL
────────────────────────────────────────────────────────────
5001  Interesting Article                https://example.com/article
5002  Random Blog Post                   https://blog.test.com/post
5003  GitHub Repository                  https://github.com/user/repo
```

**Use Cases:**

- Find bookmarks needing organization
- Systematically tag your collection
- Identify imported bookmarks without tags
- Maintain consistent tagging

**Example Workflow:**

```bash
btk:/$ cd untagged
btk:/untagged$ ls
# Find untagged bookmarks

btk:/untagged$ cd 5001
btk:/untagged/5001$ cat url title
URL: https://example.com/article
Title: Introduction to Machine Learning

btk:/untagged/5001$ tag programming/python/ml tutorial
✓ Added tags

# Bookmark automatically removed from /untagged
```

!!! tip "Bulk Tagging"
    Use the shell's bulk operations to efficiently tag multiple untagged bookmarks at once.

#### `/pdfs` - PDF Documents

Bookmarks pointing to PDF files (URLs ending with `.pdf`). Quick access to papers, books, and documents.

```bash
btk:/$ cd pdfs
btk:/pdfs$ ls
bookmarks/    (8)    PDF bookmarks

ID    Title                              URL
────────────────────────────────────────────────────────────
4201  Attention Is All You Need          https://arxiv.org/pdf/1706.03762.pdf
4305  Python Best Practices              https://docs.python.org/guide.pdf
4506  Database Design Patterns           https://example.com/db-patterns.pdf
```

**Use Cases:**

- Quick access to research papers
- Browse technical documentation PDFs
- Organize academic resources
- Download documents for offline reading

**Example Workflow:**

```bash
btk:/$ cd pdfs
btk:/pdfs$ ls
# Browse PDF bookmarks

btk:/pdfs$ cat 4201/title
Attention Is All You Need

# View cached PDF text
btk:/pdfs$ cd 4201
btk:/pdfs/4201$ !btk content view 4201

# Tag all ML papers
btk:/pdfs$ find "machine learning" | cp research/ml *
```

!!! note "PDF Detection"
    Bookmarks are included if their URL ends with `.pdf`. Some PDFs served dynamically may not appear in this collection.

### Working with Smart Collections

#### Combining with Other Features

Smart collections work seamlessly with all shell features:

```bash
# Find and star important unread bookmarks
btk:/$ cd unread
btk:/unread$ find "important"
btk:/unread$ star 1001 1005 1023

# Tag all broken bookmarks for review
btk:/$ cd broken
btk:/broken$ cp needs-update *

# Export popular bookmarks
btk:/$ cd popular
btk:/popular$ !btk export json popular-bookmarks.json --ids-from-stdin
```

#### Context-Aware Commands

All context-aware commands work within smart collections:

```bash
# View statistics for unread bookmarks
btk:/unread$ stat
Unread Bookmarks Statistics
───────────────────────────────
Total Bookmarks:     42
Total Tags:          87
Most Common Tags:    tutorial (12), research (9), python (8)
Oldest Unread:       2023-05-12 (18 months ago)
Newest Unread:       2024-10-19 (today)

# Recent activity in popular bookmarks
btk:/popular$ recent visited
# Shows only popular bookmarks you've recently visited
```

#### Nested Navigation

Navigate from collections to bookmarks and back:

```bash
btk:/$ cd unread/1001
btk:/unread/1001$ cat title
Machine Learning Paper

btk:/unread/1001$ tag research/ml/transformers to-read

btk:/unread/1001$ cd /tags/research/ml
btk:/tags/research/ml$ ls
# See bookmark in tag context too

# Bookmark exists in multiple places
btk:/$ which 1001
/bookmarks/1001
/unread/1001
/tags/research/ml/transformers/1001
/tags/to-read/1001
```

### Collection Counts

Smart collections display item counts in `ls` output for quick reference:

```bash
btk:/$ ls
bookmarks/    (100)   All bookmarks
tags/                 Browse by tag hierarchy
starred/      (15)    Starred bookmarks
archived/     (5)     Archived bookmarks
recent/               Recently active (time-based)
domains/              Browse by domain
unread/       (42)    Bookmarks never visited
popular/      (100)   100 most visited bookmarks
broken/       (3)     Unreachable bookmarks
untagged/     (15)    Bookmarks with no tags
pdfs/         (8)     PDF bookmarks
```

### Performance Notes

!!! info "Lazy Evaluation"
    Collections are computed when accessed, not stored. This keeps them always up-to-date but means very large collections (>10k bookmarks) may have slight delays.

!!! tip "Optimization"
    For large collections, consider using CLI commands with SQL queries for better performance on bulk operations.

## Time-Based Recent Navigation (v0.7.1)

The `/recent` directory provides hierarchical access to bookmark activity organized by time periods. Unlike the simple `recent` command, this creates a browsable directory structure for exploring activity across different timeframes.

### Structure Overview

```
/recent/
├── today/          # Activity from 00:00 today to now
│   ├── visited/    # Bookmarks visited today
│   ├── added/      # Bookmarks added today
│   └── starred/    # Bookmarks starred today
├── yesterday/      # Activity from yesterday (00:00 yesterday to 00:00 today)
│   ├── visited/
│   ├── added/
│   └── starred/
├── this-week/      # Activity from start of week (Monday) to now
│   ├── visited/
│   ├── added/
│   └── starred/
├── last-week/      # Activity from previous Monday to start of this week
│   ├── visited/
│   ├── added/
│   └── starred/
├── this-month/     # Activity from 1st of month to now
│   ├── visited/
│   ├── added/
│   └── starred/
└── last-month/     # Activity from 1st of previous month to 1st of this month
    ├── visited/
    ├── added/
    └── starred/
```

### Time Periods

BTK provides six time-based periods:

| Period | Definition | Example (for 2024-10-20) |
|--------|------------|--------------------------|
| `today` | 00:00 today to now | 2024-10-20 00:00 to now |
| `yesterday` | 00:00 yesterday to 00:00 today | 2024-10-19 00:00 to 2024-10-20 00:00 |
| `this-week` | Start of week (Monday) to now | 2024-10-14 00:00 to now |
| `last-week` | Previous Monday to this Monday | 2024-10-07 00:00 to 2024-10-14 00:00 |
| `this-month` | 1st of month to now | 2024-10-01 00:00 to now |
| `last-month` | 1st of previous month to 1st of this month | 2024-09-01 00:00 to 2024-10-01 00:00 |

!!! note "Week Starts on Monday"
    BTK uses Monday as the first day of the week for consistent weekly reporting.

### Activity Types

Each time period has three activity types:

#### `visited` - Browsing Activity

Bookmarks visited during the time period, sorted by `last_visited` timestamp:

```bash
btk:/recent/today/visited$ ls
ID    Title                        Last Visited      Visit Count
───────────────────────────────────────────────────────────────────
4892  Python Tutorial              2024-10-20 14:30  15
4765  NumPy Documentation          2024-10-20 12:15  23
4501  SQL Reference                2024-10-20 09:45  8
```

**Use Cases:**

- Review what you've been reading today/this week
- Find recently accessed references
- Track your browsing patterns
- Revisit pages you looked at earlier

#### `added` - New Bookmarks

Bookmarks added during the time period, sorted by `added` timestamp:

```bash
btk:/recent/today/added$ ls
ID    Title                        Added             Tags
─────────────────────────────────────────────────────────────
5001  New Python Article           2024-10-20 15:00  python
5002  Flask Best Practices         2024-10-20 14:30  python,web
5003  Docker Tutorial              2024-10-20 09:15  devops
```

**Use Cases:**

- Review bookmarks added today/this week
- Organize new additions with tags
- Quality check recent imports
- Track collection growth

#### `starred` - Favorited Bookmarks

Bookmarks starred during the time period, using `added` timestamp as a proxy:

```bash
btk:/recent/today/starred$ ls
ID    Title                        Added             Tags
─────────────────────────────────────────────────────────────
4892  Python Tutorial              2024-10-20 14:30  python,tutorial
4765  Important Reference          2024-10-20 11:00  reference
```

**Use Cases:**

- See what you've marked important recently
- Review starred items for organization
- Track favorites over time

!!! warning "Starred Timestamp Approximation"
    BTK doesn't currently track when bookmarks were starred separately, so it uses the `added` timestamp. This means starred bookmarks appear based on when they were added, not when they were starred.

### Navigation Examples

#### Browsing Today's Activity

```bash
btk:/$ cd recent/today
btk:/recent/today$ ls
visited/    (12)   Bookmarks visited today
added/      (3)    Bookmarks added today
starred/    (1)    Bookmarks starred today

btk:/recent/today$ cd visited
btk:/recent/today/visited$ ls
4892  4765  4501  4305  4201  (bookmark IDs)

btk:/recent/today/visited$ cat 4892/title
Python Tutorial: Advanced Techniques

btk:/recent/today/visited$ cd 4892
btk:/recent/today/visited/4892$ file
Bookmark #4892
─────────────────────────────────
Title:        Python Tutorial
URL:          https://tutorial.com
Last Visited: 2024-10-20 14:30:00
Visit Count:  15 times
Tags:         python, tutorial, advanced
```

#### Weekly Review

```bash
btk:/$ cd recent/this-week
btk:/recent/this-week$ ls
visited/    (89)   Bookmarks visited this week
added/      (12)   Bookmarks added this week
starred/    (5)    Bookmarks starred this week

btk:/recent/this-week$ cd added
btk:/recent/this-week/added$ ls
# Review all bookmarks added this week

btk:/recent/this-week/added$ stat
This Week's Added Bookmarks
───────────────────────────────
Total Added:         12
Tags Applied:        34
Most Common Tags:    python (5), tutorial (3), research (2)
Average per Day:     1.7 bookmarks
```

#### Monthly Activity Comparison

```bash
# This month's activity
btk:/$ cd recent/this-month/visited
btk:/recent/this-month/visited$ stat
This Month's Visited Bookmarks
──────────────────────────────
Total Visits:        324
Unique Bookmarks:    87
Average per Day:     16.2
Most Visited:        NumPy Docs (12 times)

# Compare with last month
btk:/$ cd ../../../last-month/visited
btk:/recent/last-month/visited$ stat
Last Month's Visited Bookmarks
──────────────────────────────
Total Visits:        289
Unique Bookmarks:    76
Average per Day:     9.3
Most Visited:        Python Guide (15 times)
```

#### Yesterday's Reading List

```bash
btk:/$ cd recent/yesterday/visited
btk:/recent/yesterday/visited$ ls
ID    Title                        Last Visited      Tags
────────────────────────────────────────────────────────────
4876  Machine Learning Paper       2024-10-19 16:45  research,ml
4654  Python Best Practices        2024-10-19 14:20  python
4321  Database Design              2024-10-19 09:15  database

# Re-visit interesting articles
btk:/recent/yesterday/visited$ visit 4876
```

### Practical Workflows

#### Daily Bookmark Triage

Organize bookmarks added today:

```bash
btk:/$ cd recent/today/added
btk:/recent/today/added$ ls
5001  5002  5003

# Review each one
btk:/recent/today/added$ cd 5001
btk:/recent/today/added/5001$ cat url title
URL: https://example.com/article
Title: Interesting Machine Learning Article

# Add appropriate tags
btk:/recent/today/added/5001$ tag research/ml/transformers to-read

# Star if important
btk:/recent/today/added/5001$ star

# Move to next
btk:/recent/today/added/5001$ cd ..
```

#### Weekly Reading Review

See what you read this week vs. what you added:

```bash
btk:/$ cd recent/this-week
btk:/recent/this-week$ ls

# Compare counts
btk:/recent/this-week$ cd added
btk:/recent/this-week/added$ ls | wc -l
12 bookmarks added

btk:/recent/this-week/added$ cd ../visited
btk:/recent/this-week/visited$ ls | wc -l
89 bookmarks visited

# Find bookmarks added but not yet read
btk:/recent/this-week$ cd added
btk:/recent/this-week/added$ !comm -13 <(cd ../visited && ls | sort) <(ls | sort)
# Shows added bookmarks not yet visited
```

#### Monthly Productivity Metrics

```bash
# This month's additions
btk:/$ cd recent/this-month/added
btk:/recent/this-month/added$ ls | wc -l
45 new bookmarks

# Most productive day
btk:/recent/this-month/added$ ls -l | grep "2024-10-15" | wc -l
8 bookmarks added on Oct 15

# Categories added
btk:/recent/this-month/added$ !btk bookmark list --ids-from-stdin | grep Tags | sort | uniq -c
     12 python
      8 research
      7 tutorial
      6 web
```

### Combining with Other Features

#### Time-Based + Tag Filtering

```bash
# Python bookmarks visited this week
btk:/$ cd recent/this-week/visited
btk:/recent/this-week/visited$ find "python"
# Or navigate to tag first
btk:/$ cd tags/programming/python
btk:/tags/programming/python$ recent visited
# Shows only Python bookmarks visited recently
```

#### Time-Based + Collections

```bash
# Unread bookmarks added this month
btk:/$ cd recent/this-month/added
btk:/recent/this-month/added$ !comm -12 <(cd /unread && ls | sort) <(ls | sort)
# Shows bookmarks added this month that are still unread

# Popular bookmarks visited today
btk:/$ cd recent/today/visited
btk:/recent/today/visited$ !comm -12 <(cd /popular && ls | sort) <(ls | sort)
# Shows which popular bookmarks you accessed today
```

### Backward Compatibility

The `/recent` directory maintains backward compatibility with the old `recent` command:

```bash
# Old behavior: /recent shows recently visited bookmarks
btk:/$ cd recent
btk:/recent$ ls
today/  yesterday/  this-week/  ...
4892  4765  4501  (also shows bookmark IDs - recently visited)

# Direct bookmark access still works
btk:/$ cd recent/4892
btk:/recent/4892$ cat title
Python Tutorial
```

This ensures existing workflows continue to work while providing new hierarchical navigation.

### Time Zone Handling

!!! info "UTC Timezone"
    All time calculations use UTC. Ensure your system clock is set correctly for accurate time-based filtering.

!!! tip "Timezone-Aware Timestamps"
    BTK stores all timestamps as timezone-aware datetime objects, ensuring consistent behavior across different systems.

## Viewing Commands

### `cat` - Display Content

Display bookmark fields or content.

**Examples:**

```bash
# View specific field
btk:/bookmarks/4095$ cat title
Advanced Python Techniques

# View URL
btk:/bookmarks/4095$ cat url
https://realpython.com/advanced-python-techniques/

# View tags
btk:/bookmarks/4095$ cat tags
python, advanced, techniques, best-practices

# Path syntax from anywhere
btk:/$ cat bookmarks/4095/title
Advanced Python Techniques

# View multiple fields
btk:/bookmarks/4095$ cat url title tags
URL: https://realpython.com/advanced-python-techniques/
Title: Advanced Python Techniques
Tags: python, advanced, techniques, best-practices
```

### `file` - Show Metadata Summary

Display a summary of bookmark metadata.

```bash
btk:/bookmarks/4095$ file
Bookmark #4095
─────────────────────────────────────────
Title:        Advanced Python Techniques
URL:          https://realpython.com/...
Type:         webpage
Domain:       realpython.com
Added:        2024-03-15 14:30:00
Stars:        ★ Starred
Visits:       15 times
Last Visited: 2024-10-19 14:30:00
Tags:         python, advanced, techniques
Size:         45.2 KB (cached)
Status:       ✓ Reachable
```

### `stat` - Detailed Statistics

Show detailed statistics about bookmarks in the current context.

```bash
btk:/tags/programming/python$ stat
Python Bookmarks Statistics
─────────────────────────────────────────
Total Bookmarks:     127
Starred:             23 (18.1%)
Visited:             89 (70.1%)
Cached Content:      102 (80.3%)
Total Visits:        1,847
Avg Visits/Bookmark: 14.5

Most Visited:
  1. NumPy Documentation (45 visits)
  2. Advanced Python Techniques (38 visits)
  3. Python Testing Guide (31 visits)

Recent Activity:
  Last 7 days:  12 new bookmarks, 89 visits
  Last 30 days: 45 new bookmarks, 324 visits

Top Subtags:
  1. web (34 bookmarks)
  2. data-science (28 bookmarks)
  3. testing (19 bookmarks)
```

## Tag Operations

### Hierarchical Tags

Tags support hierarchy using `/` as a separator, creating a navigable structure:

```bash
btk:/$ cd tags
btk:/tags$ ls
programming/  research/  tutorial/  web/  video/

btk:/tags$ cd programming
btk:/tags/programming$ ls
python/  javascript/  go/  rust/

btk:/tags$ cd programming/python
btk:/tags/programming/python$ ls
web/  data-science/  testing/  async/
3298  4095  5124  5789  (and more bookmark IDs)
```

**Tag Path Examples:**

- `programming/python/django`
- `research/machine-learning/nlp`
- `tutorial/video/beginner`
- `work/projects/active/high-priority`

### `tag` - Add Tags

Add tags to bookmarks.

```bash
# Add tag to current bookmark
btk:/bookmarks/4095$ tag advanced important

# Add tag to specific bookmark
btk:/$ tag 4095 advanced important

# Add hierarchical tags
btk:/bookmarks/4095$ tag programming/python/advanced

# Add tag in context
btk:/tags/programming/python$ tag 4095 data-science
```

### `untag` - Remove Tags

Remove tags from bookmarks.

```bash
# Remove tag from current bookmark
btk:/bookmarks/4095$ untag old-tag

# Remove tag from specific bookmark
btk:/$ untag 4095 old-tag

# Remove multiple tags
btk:/bookmarks/4095$ untag beginner outdated draft
```

### `mv` - Rename Tags

Rename tags across all bookmarks. This is a powerful operation that updates all bookmarks with the old tag.

**Syntax:**

```bash
mv <old_tag> <new_tag>
```

**Examples:**

```bash
# Simple rename
btk:/tags$ mv javascript js
Renaming tag 'javascript' to 'js'...
Found 47 bookmarks with tag 'javascript'
Confirm rename? [y/N]: y
✓ Successfully renamed tag in 47 bookmarks

# Rename with hierarchy
btk:/tags$ mv programming/python/web programming/python/web-dev
Renaming tag 'programming/python/web' to 'programming/python/web-dev'...
Found 23 bookmarks with tag 'programming/python/web'
Confirm rename? [y/N]: y
✓ Successfully renamed tag in 23 bookmarks

# Automatic cleanup of orphaned tags
Tag 'javascript' no longer in use, removed from tag database
```

!!! warning "Confirmation Required"
    The `mv` command will prompt for confirmation before making changes. Use this carefully as it affects all bookmarks with the tag.

### `cp` - Copy Tags

Copy tags to bookmarks. This is useful for bulk tagging operations.

**Syntax:**

```bash
cp <tag> <target>
```

**Targets:**

- `.` - Current bookmark (when in bookmark context)
- `<id>` - Specific bookmark ID
- `*` - All bookmarks in current context

**Examples:**

```bash
# Copy tag to current bookmark
btk:/bookmarks/4095$ cp important .
✓ Added tag 'important' to bookmark #4095

# Copy tag to specific bookmark
btk:/$ cp featured 4095
✓ Added tag 'featured' to bookmark #4095

# Copy tag to all bookmarks in current context
btk:/tags/programming/python$ cp reviewed *
Copying tag 'reviewed' to 127 bookmarks...
Confirm? [y/N]: y
✓ Added tag 'reviewed' to 127 bookmarks

# Copy tag to starred bookmarks
btk:/starred$ cp high-priority *
Copying tag 'high-priority' to 23 bookmarks...
Confirm? [y/N]: y
✓ Added tag 'high-priority' to 23 starred bookmarks
```

!!! tip "Bulk Tagging"
    Use `cp` with `*` in filtered contexts (like `/tags/python` or `/starred`) to efficiently tag groups of bookmarks.

## Bookmark Operations

### `star` - Toggle Star Status

Star or unstar bookmarks to mark them as favorites.

```bash
# Star current bookmark
btk:/bookmarks/4095$ star
★ Starred bookmark #4095

# Star specific bookmark
btk:/$ star 4095
★ Starred bookmark #4095

# Toggle (unstar if already starred)
btk:/bookmarks/4095$ star
☆ Unstarred bookmark #4095
```

### `edit` - Edit Bookmark Fields

Edit bookmark metadata directly in the shell.

```bash
# Edit title
btk:/bookmarks/4095$ edit title
Current: Advanced Python Techniques
New title: Advanced Python Techniques and Best Practices
✓ Updated title

# Edit description
btk:/bookmarks/4095$ edit description
Enter description (Ctrl+D to finish):
A comprehensive guide to advanced Python features...
✓ Updated description

# Edit URL
btk:/bookmarks/4095$ edit url
Current: https://old-url.com
New URL: https://new-url.com
✓ Updated URL
```

### `rm` - Remove Bookmark

Remove the current bookmark (requires confirmation).

```bash
btk:/bookmarks/4095$ rm
Remove bookmark #4095 "Advanced Python Techniques"? [y/N]: y
✓ Bookmark #4095 removed

# You can also specify ID
btk:/$ rm 4095
Remove bookmark #4095 "Advanced Python Techniques"? [y/N]: y
✓ Bookmark #4095 removed
```

!!! danger "Permanent Deletion"
    The `rm` command permanently deletes bookmarks. Use with caution.

### `visit` - Open Bookmark

Open a bookmark in your default browser.

```bash
# Visit current bookmark
btk:/bookmarks/4095$ visit
Opening https://realpython.com/advanced-python-techniques/

# Visit specific bookmark
btk:/$ visit 4095
Opening https://realpython.com/advanced-python-techniques/
```

## Search Commands

### `find` - Search Bookmarks

Search for bookmarks matching a query.

```bash
# Simple search
btk:/$ find "python tutorial"
Found 23 bookmarks:
ID    Title                        Tags
───────────────────────────────────────────────
4095  Advanced Python Techniques   python,advanced
5124  Python Testing Guide         python,testing
5789  Asyncio Tutorial             python,async

# Search within current context
btk:/tags/programming$ find "tutorial"
# Only searches programming bookmarks

# Search with options
btk:/$ find "machine learning" --starred --limit 10
# Only starred bookmarks, max 10 results
```

### `grep` - Search in Fields

Search for patterns in specific bookmark fields.

```bash
# Search in URLs
btk:/$ grep "github.com" url
Found 45 bookmarks with github.com in URL

# Search in descriptions
btk:/$ grep "tutorial" description
Found 23 bookmarks with 'tutorial' in description

# Case-insensitive search
btk:/$ grep -i "PYTHON" title
Found 127 bookmarks with 'python' in title
```

## Utility Commands

### `help` - Show Help

Display help for commands.

```bash
# General help
btk:/$ help
Available commands:
  Navigation:  ls, cd, pwd, which
  Viewing:     cat, file, stat
  Tags:        tag, untag, mv, cp
  Bookmarks:   star, edit, rm, visit
  Search:      find, grep, recent
  Utilities:   help, exit, clear, history

# Command-specific help
btk:/$ help cd
cd - Change directory

Usage:
  cd <path>    Navigate to path
  cd ..        Go to parent directory
  cd /         Go to root
  cd           Go to home (/bookmarks)
```

### `history` - Command History

View and manage command history.

```bash
# Show recent commands
btk:/$ history
1  cd tags/programming/python
2  ls
3  cat 4095/title
4  star 4095
5  recent visited

# Re-execute command by number
btk:/$ !3
Advanced Python Techniques

# Re-execute last command
btk:/$ !!
```

### `clear` - Clear Screen

Clear the terminal screen.

```bash
btk:/$ clear
```

### System Commands

Execute system commands using `!` prefix:

```bash
# Run shell commands
btk:/$ !ls -la
# Executes system 'ls' command

# Pipe bookmark data to system commands
btk:/$ find "python" | !grep "tutorial"
# Find bookmarks, then grep in results
```

## Practical Workflows

### Organizing New Bookmarks

```bash
# Start at recent bookmarks
btk:/$ cd recent
btk:/recent$ ls

# Review and tag new bookmarks
btk:/recent$ cd 6543
btk:/recent/6543$ cat url title
URL: https://newsite.com/article
Title: Great Python Article

btk:/recent/6543$ tag programming/python/tutorial
✓ Added tag

btk:/recent/6543$ star
★ Starred bookmark #6543

# Move to next
btk:/recent/6543$ cd ..
btk:/recent$ cd 6542
```

### Cleaning Up Tags

```bash
# Review all tags
btk:/$ cd tags
btk:/tags$ ls
javascript/  js/  programming/

# Consolidate duplicate tags
btk:/tags$ mv javascript js
✓ Renamed 'javascript' to 'js' in 47 bookmarks

# Review and reorganize
btk:/tags$ cd programming
btk:/tags/programming$ ls
python/  web/  backend/

# Reorganize structure
btk:/tags/programming$ mv backend programming/backend
✓ Renamed tag
```

### Research Session

```bash
# Navigate to research area
btk:/$ cd tags/research/machine-learning
btk:/tags/research/machine-learning$ ls

# Review bookmarks
btk:/tags/research/machine-learning$ recent visited
# See what I've been reading

# Star important papers
btk:/tags/research/machine-learning$ cd 7890
btk:/tags/research/machine-learning/7890$ file
# Review details

btk:/tags/research/machine-learning/7890$ star
★ Starred

# Tag for current project
btk:/tags/research/machine-learning/7890$ tag project/nlp-classifier
✓ Added tag

# Visit bookmark
btk:/tags/research/machine-learning/7890$ visit
Opening in browser...
```

### Bulk Operations

```bash
# Tag all Python bookmarks as reviewed
btk:/$ cd tags/programming/python
btk:/tags/programming/python$ cp reviewed *
✓ Added 'reviewed' to 127 bookmarks

# Star all tutorial bookmarks
btk:/$ cd tags/tutorial
btk:/tags/tutorial$ find "beginner" | star
# Star each result

# Export starred programming bookmarks
btk:/$ cd starred
btk:/starred$ find "" | !btk export --ids-from-stdin programming-stars.html
# Export to file using CLI
```

## Tips and Tricks

### Quick Navigation

!!! tip "Use Absolute Paths"
    ```bash
    # Instead of multiple cd commands
    btk:/$ cd tags
    btk:/tags$ cd programming
    btk:/tags/programming$ cd python

    # Use absolute path
    btk:/$ cd /tags/programming/python
    ```

### Context-Aware Operations

!!! tip "Leverage Current Location"
    Commands like `recent`, `stat`, and `find` filter results based on your current location. Use this to focus on specific areas:

    ```bash
    btk:/tags/work$ recent visited
    # Only shows visited work bookmarks

    btk:/starred$ stat
    # Statistics for starred bookmarks only
    ```

### Combining Commands

!!! tip "Shell History"
    Use `history` to repeat complex command sequences:

    ```bash
    btk:/$ history
    15  cd /tags/programming/python
    16  recent added --limit 10
    17  stat

    btk:/$ !15
    # Re-executes command #15
    ```

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+D` | Exit shell |
| `Ctrl+C` | Cancel current command |
| `Ctrl+L` | Clear screen |
| `↑` / `↓` | Navigate command history |
| `Tab` | Auto-complete (coming soon) |

## Shell vs CLI

The shell and CLI interfaces are complementary:

| Use Case | Shell | CLI |
|----------|-------|-----|
| **Exploring bookmarks** | ✅ Better - navigate and discover | ❌ Less suitable |
| **Quick operations** | ✅ Great - context remembered | ✅ Great - single command |
| **Bulk operations** | ⚠️ Manual iteration | ✅ Better - batch commands |
| **Scripting/automation** | ❌ Not suitable | ✅ Perfect for scripts |
| **Learning/discovery** | ✅ Interactive, forgiving | ⚠️ Need to know commands |
| **Complex workflows** | ✅ Build context gradually | ⚠️ Long command lines |

**When to use the shell:**

- Browsing and exploring your bookmark collection
- Interactive tag organization and cleanup
- Reviewing recent activity
- Learning about your bookmarks

**When to use the CLI:**

- Automation and scripting
- Batch operations on many bookmarks
- Integration with other tools
- One-off quick commands

## Next Steps

- **[Core Commands](commands.md)** - Learn the CLI commands
- **[Tags & Organization](tags.md)** - Deep dive into hierarchical tags
- **[Search & Query](search.md)** - Advanced search techniques
- **[Import & Export](import-export.md)** - Working with bookmark files

## See Also

- **[CLI Reference](../api/cli.md)** - Complete command-line reference
- **[Configuration](../getting-started/configuration.md)** - Configure shell behavior
- **[Architecture](../development/architecture.md)** - How the shell works internally
