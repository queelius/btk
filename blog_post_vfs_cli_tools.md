# Everything is a File: Applying Unix Philosophy to Modern Data Management

*How virtual filesystem interfaces turned my scattered data tools into navigable, composable systems*

---

## The Problem: CLIs That Don't Scale With Complexity

I had a bookmark manager. Then an ebook library manager. Then a chat history manager. Each started simple:

```bash
# Traditional CRUD approach
btk add https://example.com --tags python,tutorial
btk list --tag python
btk search "async"
btk delete 1234

ebk import book.pdf --author "Knuth"
ebk list --author Knuth
ebk search "algorithms"
```

This works fine... until it doesn't.

**The breaking point:** I had 10,000+ bookmarks organized with hierarchical tags like `programming/python/async`, `research/ml/transformers`, `work/clients/acme`. My ebook library had similar structure. My exported chat conversations from Claude, ChatGPT, and Copilot were piling up.

Traditional CRUD commands became unwieldy:

```bash
# Getting specific without a VFS
btk list --tag programming/python/async/io --format json | jq '.[].title'
ebk list --category "Computer Science/Algorithms/Graph Theory" --limit 50
ctk search "machine learning" --source ChatGPT --date-from 2024-01-01
```

Each command required precise arguments. Each tool had different flag conventions. I couldn't *navigate* my data—I could only *query* it. And queries require knowing exactly what you're looking for.

## The Unix Revelation: Everything is a File

The insight came from an unlikely place: managing files on my system.

When I have thousands of source files organized in directories, I don't run:
```bash
list-files --path /src/components/auth --extension .tsx
```

I run:
```bash
cd src/components/auth
ls *.tsx
```

**The difference is profound:** With a filesystem, I can:
- **Navigate incrementally**: `cd` from general to specific
- **Explore**: `ls` to see what's there
- **Compose**: `cat file | grep pattern | wc -l`
- **Use familiar tools**: `find`, `grep`, `xargs`, pipes, redirection

What if my bookmarks, ebooks, and chat histories were filesystems?

## The Pattern: Virtual Filesystems + POSIX Commands

Over the past year, I've built six Python tools that all follow the same architectural pattern:

| Tool | Domain | VFS Root Structure |
|------|--------|-------------------|
| **btk** | Bookmarks | `/bookmarks/`, `/tags/`, `/recent/`, `/domains/`, `/unread/`, `/popular/` |
| **ebk** | Ebook library | `/books/`, `/authors/`, `/series/`, `/subjects/`, `/recent/`, `/unread/` |
| **ctk** | Chat conversations | `/conversations/`, `/sources/`, `/topics/`, `/starred/`, `/recent/` |
| **ghops** | Git repositories | `/repos/`, `/languages/`, `/topics/`, `/stars/`, `/recent/` |
| **infinigram** | N-gram models | `/datasets/`, `/models/`, `/corpora/` |
| **AlgoTree** | Tree structures | `/nodes/`, `/paths/`, `/subtrees/` |

Each tool provides:

1. **A stateless CLI** for scriptability: `btk bookmark add URL`, `ebk import book.pdf`
2. **An interactive shell** with a virtual filesystem: `btk shell`, `ebk shell`, `ctk chat`
3. **POSIX-like commands**: `cd`, `ls`, `pwd`, `cat`, `mv`, `cp`, `rm`, `find`, `grep`
4. **Unix pipeline support**: Most commands output JSONL by default for piping

The magic is in the shell. Let me show you.

## Live Session: Navigating 10,000 Bookmarks

**Recording Note:** *These sessions can be recorded with [asciinema](https://asciinema.org/) for interactive playback. Each keystroke is captured, and the final recording is just a few KB of text—perfect for embedding in blog posts.*

### Traditional Approach (CRUD CLI)
```bash
$ btk search "python async" --tag programming --limit 10
# Returns JSON blob... now what?

$ btk list --tag "programming/python/async"
# Hope I remembered the exact tag path

$ btk bookmark get 4095 --format json | jq '.tags'
# One bookmark at a time, verbose
```

### VFS Approach (Interactive Shell)
```bash
$ btk shell

      __    __  __
     / /_  / /_/ /__
    / __ \/ __/ //_/
   / /_/ / /_/ ,<
  /_.___/\__/_/|_|  v0.7.1

  Bookmark Toolkit - Virtual Filesystem Shell

btk:/$ ls
bookmarks/    (10,247)    All bookmarks
tags/                    Tag hierarchy
recent/                  Time-based navigation
domains/                 Browse by domain
unread/       (2,431)    Never visited
popular/      (100)      Most visited
broken/       (14)       Dead links
starred/      (156)      Starred bookmarks

btk:/$ cd tags/programming/python

btk:/tags/programming/python$ ls
async/        (87)
web/          (124)
data/         (156)
ml/           (89)
testing/      (45)

btk:/tags/programming/python/async$ ls | head -5
4095  5234  6012  6891  7234

btk:/tags/programming/python/async$ cat 4095/title
Real Python - Async IO in Python: A Complete Walkthrough

btk:/tags/programming/python/async$ cat 4095/url
https://realpython.com/async-io-python/

btk:/tags/programming/python/async$ star 4095
★ Starred bookmark #4095

btk:/tags/programming/python/async$ cd /recent/today/added

btk:/recent/today/added$ ls
8901  8902  8903  8904

btk:/recent/today/added$ tag 8901 8902 8903 todo
✓ Tagged 3 bookmarks
```

**Notice what just happened:**
- **No flag memorization**: Just `cd` and `ls`
- **Incremental exploration**: Narrow down step by step
- **Context-aware commands**: `tag` and `star` work on IDs in current directory
- **Familiar mental model**: It's just directories and files

## The Same Pattern, Different Data

This pattern works beautifully across domains:

### Managing Ebooks (ebk)
```bash
ebk:/$ cd subjects/Computer\ Science/Algorithms

ebk:/subjects/Computer Science/Algorithms$ ls
Introduction to Algorithms.pdf
The Algorithm Design Manual.pdf
Algorithms (Sedgewick).pdf

ebk:/subjects/Computer Science/Algorithms$ cat "Introduction to Algorithms.pdf"/metadata
Title: Introduction to Algorithms
Authors: Cormen, Leiserson, Rivest, Stein
ISBN: 978-0262033848
Pages: 1312
Rating: 5/5

ebk:/subjects/Computer Science/Algorithms$ rate * 5
✓ Rated 3 books

ebk:/subjects/Computer Science/Algorithms$ cd /recent/this-week/added

ebk:/recent/this-week/added$ ls
Advanced Programming in the Unix Environment.pdf
Designing Data-Intensive Applications.pdf

ebk:/recent/this-week/added$ tag * must-read
✓ Tagged 2 books
```

### Exploring Chat History (ctk)
```bash
ctk:/$ cd sources/ChatGPT

ctk:/sources/ChatGPT$ ls | wc -l
423

ctk:/sources/ChatGPT$ cd /topics/machine-learning

ctk:/topics/machine-learning$ ls
conv_a1b2c3  conv_d4e5f6  conv_g7h8i9

ctk:/topics/machine-learning$ show conv_a1b2c3
[Shows conversation tree with messages]

ctk:/topics/machine-learning$ star conv_a1b2c3
★ Starred conversation

ctk:/topics/machine-learning$ cd /starred

ctk:/starred$ export --format markdown > starred_ml_convos.md
✓ Exported 5 starred conversations to starred_ml_convos.md
```

### Managing Git Repositories (ghops)
```bash
ghops:/$ cd languages/Python

ghops:/languages/Python$ ls
btk/  ebk/  ctk/  ghops/  infinigram/  AlgoTree/

ghops:/languages/Python$ cd btk

ghops:/languages/Python/btk$ status
Branch: master
Commits ahead: 0
Uncommitted changes: 0
Last commit: Release v0.7.1 (2 days ago)

ghops:/languages/Python/btk$ cd /topics/cli-tools

ghops:/topics/cli-tools$ ls
btk/  ebk/  ctk/  ghops/

ghops:/topics/cli-tools$ audit all --fix
✓ Added .gitignore to 2 repositories
✓ Added LICENSE to 1 repository
✓ Updated README badges in 4 repositories
```

## Design Principles: What Makes This Work

After building six of these tools, clear patterns emerged:

### 1. **Local-First, Stateless CLI + Stateful Shell**

Every tool offers two interfaces:

**CLI (stateless, scriptable):**
```bash
btk bookmark add https://example.com --tags python,tutorial
ebk import book.pdf --author "Knuth"
ctk export --format jsonl > training.jsonl
```

**Shell (stateful, exploratory):**
```bash
btk shell
cd tags/python
star *
```

The CLI is for automation and scripting. The shell is for humans.

### 2. **Everything is a File, Even Dynamic Data**

Traditional filesystems are static. Our VFS exposes dynamic, computed views:

```bash
btk:/$ ls
unread/       (2,431)    # SELECT * WHERE visit_count = 0
popular/      (100)      # SELECT * ORDER BY visit_count DESC LIMIT 100
broken/       (14)       # SELECT * WHERE reachable = false
recent/today/added/      # SELECT * WHERE added >= TODAY
```

These "directories" don't exist on disk—they're computed queries. But they *feel* like directories.

### 3. **Context-Aware Commands**

Commands understand where you are:

```bash
btk:/bookmarks/4095$ cat title
# Shows title of bookmark 4095

btk:/tags/python$ star *
# Stars all Python-tagged bookmarks

btk:/recent/today/added$ tag * review
# Tags today's additions

btk:/broken$ rm *
# Removes all broken bookmarks
```

The current path becomes implicit context. No need to repeat IDs or filters.

### 4. **JSONL by Default, Pretty on Demand**

All commands output newline-delimited JSON (JSONL) by default:

```bash
# Pipe to jq, grep, awk, any Unix tool
btk list | jq 'select(.stars == true)'
ebk status | grep "rating: 5"
ctk search "python" | jq '.id' | xargs ctk export --ids

# Pretty-print for humans
btk list --pretty
ebk status --pretty
```

This makes tools composable with the Unix ecosystem.

### 5. **Hierarchical Tags = Navigable Directories**

The killer feature: hierarchical tags map directly to filesystem paths.

```bash
# Tag with hierarchy
btk tag 4095 programming/python/async/io

# Navigate the hierarchy
btk:/$ cd tags/programming
btk:/tags/programming$ ls
python/  javascript/  rust/  go/

btk:/tags/programming$ cd python/async
btk:/tags/programming/python/async$ ls
io/  frameworks/  patterns/

# Bulk operations on a hierarchy
btk:/tags/programming/python$ star */advanced/*
# Stars all bookmarks under any advanced subtag
```

**Compare with flat tags:**
- Flat: `python`, `python-async`, `python-async-io`, `python-web`, `python-web-django`
- Hierarchical: `python/async/io`, `python/web/django`

Hierarchical tags give you free navigation and organization.

### 6. **Smart Collections: Dynamic Virtual Directories**

Beyond tags, we can expose any query as a "directory":

```bash
btk:/$ cd unread
btk:/unread$ ls | wc -l
2431

# Visit one, it disappears from /unread
btk:/unread$ visit 5234
✓ Opened bookmark 5234

btk:/unread$ ls | wc -l
2430
```

Collections auto-update based on state changes. It's like smart playlists for data.

### 7. **Time-Based Navigation**

Recency is a dimension worth navigating:

```bash
btk:/$ cd recent/today/visited
btk:/recent/today/visited$ ls
5001  4987  4923

btk:/$ cd recent/this-week/added
btk:/recent/this-week/added$ tag * weekly-review
✓ Tagged 47 bookmarks

btk:/$ cd recent/last-month/starred
btk:/recent/last-month/starred$ export > highlights.md
```

This beats remembering exact date ranges in queries.

## Implementation: How It's Built

Each tool shares a similar architecture:

### Core Components

1. **Database Layer** (SQLAlchemy + SQLite)
   - Normalized schema for entities (bookmarks, books, conversations)
   - Full-text search with FTS5
   - Efficient indexing for common queries

2. **VFS Layer** (Python `cmd.Cmd`)
   - Path parsing: `/tags/programming/python` → context
   - Context detection: "Where am I? What objects are here?"
   - Command routing: context + command → appropriate handler

3. **Command Layer**
   - Context-aware implementations: `do_ls()`, `do_cd()`, `do_cat()`, etc.
   - Smart defaults based on current path
   - Pretty printing vs. JSONL output

4. **CLI Layer** (Typer/argparse)
   - Stateless commands for scripting
   - Output as JSONL for Unix pipes
   - Shares same database as shell

### Example: Context Detection in BTK

```python
def _get_context(self):
    """Determine what 'directory' we're in."""
    if self.current_path == "/":
        return {'type': 'root'}

    parts = self.current_path.strip('/').split('/')

    if parts[0] == 'tags':
        # /tags/programming/python
        tag_path = '/'.join(parts[1:])
        bookmarks = self.db.filter_by_tag_prefix(tag_path)
        return {'type': 'tag', 'tag': tag_path, 'bookmarks': bookmarks}

    elif parts[0] == 'recent':
        # /recent/today/added
        period = parts[1]  # 'today'
        activity = parts[2] if len(parts) > 2 else 'visited'
        bookmarks = filter_by_time_and_activity(period, activity)
        return {'type': 'recent_activity', 'period': period,
                'activity': activity, 'bookmarks': bookmarks}

    elif parts[0] == 'unread':
        # /unread - smart collection
        bookmarks = self.db.filter(visit_count=0)
        return {'type': 'smart_collection', 'name': 'unread',
                'bookmarks': bookmarks}

    elif parts[0] == 'bookmarks' and len(parts) == 2:
        # /bookmarks/4095
        bookmark_id = int(parts[1])
        bookmark = self.db.get(bookmark_id)
        return {'type': 'bookmark', 'bookmark_id': bookmark_id,
                'bookmark': bookmark}
```

Once we know the context, commands adapt:

```python
def do_ls(self, args):
    """List items in current directory."""
    context = self._get_context()

    if context['type'] == 'root':
        self._ls_root()
    elif context['type'] == 'tag':
        self._ls_tag(context['tag'], context['bookmarks'])
    elif context['type'] == 'recent_activity':
        self._ls_bookmarks(context['bookmarks'])
    elif context['type'] == 'smart_collection':
        self._ls_collection(context['name'], context['bookmarks'])
    elif context['type'] == 'bookmark':
        self._ls_bookmark(context['bookmark'])
```

This pattern—**context detection + polymorphic commands**—is the secret sauce.

## Beyond These Six: The Pattern Scales

The VFS + POSIX pattern isn't limited to these tools. I've applied it to:

- **json-algebra**: Navigate and manipulate JSON structures as filesystems
  ```bash
  json:/$ cd users/[0]/posts/[2]
  json:/users/[0]/posts/[2]$ cat title
  "My First Post"
  ```

- **log-analyzer**: Navigate structured logs as directories
  ```bash
  logs:/$ cd errors/2024-01/
  logs:/errors/2024-01$ group-by level
  ```

- **api-explorer**: Explore REST APIs as navigable resources
  ```bash
  api:/$ cd users/123/posts
  api:/users/123/posts$ ls
  post_456  post_789  post_012
  ```

The pattern is **universally applicable to hierarchical data**.

## Why This Matters: Cognitive Fit

Traditional CLIs force you to:
1. **Remember exact syntax**: `--filter-by-tag`, `--limit`, `--format`
2. **Construct precise queries**: Get it wrong, start over
3. **Process JSON blobs**: Pipe to `jq` for every operation

VFS interfaces let you:
1. **Explore incrementally**: `cd` → `ls` → `cd` → `ls`
2. **Discover what exists**: See tags/categories you forgot about
3. **Operate on context**: "Star everything here" not "Star IDs 1,2,3,..."

It matches how humans think: **spatial navigation** over **query construction**.

We already know filesystems. We already know `cd`, `ls`, `grep`, `find`. Why not leverage that knowledge?

## The Unix Philosophy Lives

Doug McIlroy's Unix philosophy (1978):

> 1. Make each program do one thing well.
> 2. Expect the output of every program to become the input to another.
> 3. Design and build software to be tried early.

We've applied this to data:

1. **One thing well**: Each tool manages one domain (bookmarks, ebooks, chats)
2. **Composable output**: JSONL everywhere, pipe to jq/grep/awk
3. **Interactive experimentation**: Shell for exploration, CLI for automation

And we've extended it:

4. **Everything is a file**: Even dynamic queries and computed collections
5. **Navigation over query**: `cd` to context before operating
6. **Context is king**: Current directory implies scope

## Getting Started: Build Your Own

Want to apply this pattern to your data? Here's the recipe:

### 1. Identify Your Hierarchies

What natural hierarchies exist in your domain?

- **Bookmarks**: Tags, domains, time
- **Ebooks**: Authors, subjects, series
- **Chats**: Sources, topics, time
- **Your domain**: ?

### 2. Design Your VFS Root

What "directories" should exist at the top level?

```
/
├── <primary-entities>/    # /bookmarks, /books, /conversations
├── <hierarchy-1>/          # /tags, /authors, /sources
├── <hierarchy-2>/          # /domains, /subjects, /topics
├── <time-based>/           # /recent/today, /recent/this-week
└── <smart-collections>/    # /unread, /starred, /popular
```

### 3. Implement Context Detection

Map paths to database queries:

```python
def parse_path(path):
    parts = path.strip('/').split('/')
    if parts[0] == 'tags':
        return Tag.query.filter_by_prefix('/'.join(parts[1:]))
    elif parts[0] == 'recent':
        return Recent.query.filter_by_time(parts[1])
    # ... etc
```

### 4. Add POSIX Commands

Start with the essentials:
- `cd` - Change context
- `ls` - List items in context
- `pwd` - Show current path
- `cat` - Show item details
- `find` - Search within subtree
- `grep` - Filter items

Then add domain-specific commands:
- Bookmarks: `visit`, `star`, `tag`
- Ebooks: `rate`, `read`, `export`
- Your domain: ?

### 5. Provide Both Interfaces

```python
# Shell (stateful, cmd.Cmd-based)
class DataShell(cmd.Cmd):
    def do_cd(self, path): ...
    def do_ls(self, args): ...
    # ...

# CLI (stateless, Typer/argparse-based)
@app.command()
def add(url: str, tags: List[str]): ...

@app.command()
def list(tag: str = None): ...
```

Users choose based on use case:
- **Automation**: Use CLI with pipes
- **Exploration**: Use shell with `cd`/`ls`

### 6. Output JSONL by Default

Every command should output newline-delimited JSON unless `--pretty` is specified:

```python
def output(data, pretty=False):
    if pretty:
        print_table(data)  # Rich table
    else:
        for item in data:
            print(json.dumps(item))  # JSONL
```

This makes your tool a first-class Unix citizen.

## Real-World Benefits: What I've Gained

Since building these tools, I've:

1. **Found forgotten treasures**: Exploring `/tags/` revealed bookmark categories I'd forgotten
2. **Automated workflows**: `cd /recent/this-week/added && tag * weekly-review`
3. **Composed with Unix tools**: `btk list | jq '.url' | xargs -I {} curl -I {}`
4. **Reduced cognitive load**: No memorizing flags; just `cd` and `ls`
5. **Built faster**: New tools reuse the same VFS pattern

Most importantly: **I actually use these tools daily.** They're not abandoned side projects—they're integral to my workflow.

## The Repository

All six tools are open source:

- **btk** (Bookmark Toolkit): [github.com/queelius/btk](https://github.com/queelius/btk)
- **ebk** (eBook Manager): [github.com/queelius/ebk](https://github.com/queelius/ebk)
- **ctk** (Conversation Toolkit): [github.com/queelius/ctk](https://github.com/queelius/ctk)
- **ghops** (Git Repository Manager): [github.com/queelius/ghops](https://github.com/queelius/ghops)
- **infinigram** (N-gram Models): [github.com/queelius/infinigram](https://github.com/queelius/infinigram)
- **AlgoTree** (Tree Structures): [github.com/queelius/AlgoTree](https://github.com/queelius/AlgoTree)

Each is on PyPI, fully documented, and well-tested.

## Call to Action: Join the Movement

**If you build CLI tools for hierarchical data:**

Consider the VFS pattern. Your users already know `cd` and `ls`. Why make them learn 47 flags?

**If you maintain complex data:**

Try one of these tools. Install with `pip install btk` or `pip install ebk`. See if the VFS interface clicks.

**If you want to contribute:**

All six projects welcome contributors. The pattern is proven; the features are endless. Pick your domain (bookmarks, ebooks, chats, repos) and add:
- New smart collections
- New commands
- Better visualizations
- MCP integrations
- Browser extensions

**If you're just here for the philosophy:**

Spread the word. The Unix philosophy isn't dead—it's *evolving*. We've gone from "everything is a file" to "everything *can be presented as* a file."

Your data deserves to be navigable. Make it a filesystem.

---

## Technical Notes

### On Recording Shell Sessions

The shell sessions shown above can be recorded with [asciinema](https://asciinema.org/):

```bash
asciinema rec btk-demo.cast
btk shell
# ... do your demo ...
exit
```

The resulting `.cast` file is pure text (JSON), usually just a few KB. You can:
- Embed in blog posts with [asciinema-player](https://github.com/asciinema/asciinema-player)
- Share with viewers who can copy/paste from the recording
- Host on asciinema.org for free

This is *way* better than GIFs or videos for terminal demos.

### On JSONL vs. Pretty Printing

JSONL (newline-delimited JSON) is crucial for Unix composability:

```bash
# Each line is valid JSON
btk list | jq 'select(.stars == true)' | jq '.title'

# vs. array JSON (breaks streaming)
btk list --format json | jq '.[] | select(.stars == true) | .title'
```

JSONL is:
- **Streamable**: Process line-by-line, no need to load entire array
- **Appendable**: `echo '{"new":"item"}' >> data.jsonl`
- **Grepable**: `grep '"stars":true' data.jsonl`
- **Robust**: One malformed record doesn't break the entire file

Make it your default. Provide `--pretty` for humans.

### On Test Coverage

All six tools have comprehensive test suites:
- **btk**: 515 tests (53% shell coverage, 23% CLI coverage)
- **ebk**: Similar architecture, similar coverage
- **ctk**: Extensive integration tests with multiple LLM providers
- **ghops**: 138 tests, 86% coverage
- **infinigram**: 36 tests with benchmarks
- **AlgoTree**: 197 tests, 86% coverage

The VFS pattern is *highly testable*:
1. Mock database queries
2. Test path parsing
3. Test context detection
4. Test command handlers

Each component is isolated and pure.

---

## Conclusion: The Future is Navigable

We've spent 50 years making filesystems fast, reliable, and ubiquitous. Every operating system has them. Every programmer understands them.

Why build new mental models for every data domain?

**Make your data navigable. Make it a filesystem.**

The tools are here. The pattern is proven. The Unix philosophy endures.

Now go forth and `cd` into your data.

---

*Alex Towell builds tools at the intersection of systems programming, language models, and data wrangling. Find more at [metafunctor.com](https://metafunctor.com) or follow the projects on [GitHub](https://github.com/queelius).*

*Published: 2025-10-20*
*Topics: #python #cli #unix #data-management #open-source*
