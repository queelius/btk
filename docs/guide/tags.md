# Tags & Organization

Tags are the primary way to organize bookmarks in BTK. They support hierarchical structures, making it easy to create sophisticated organizational schemes that scale with your collection.

## Tag Basics

Tags are labels you attach to bookmarks to categorize and find them later. Unlike folders in traditional bookmark managers, a single bookmark can have multiple tags.

### Adding Tags

Add tags when creating a bookmark:

```bash
btk bookmark add https://example.com --tags "tutorial,python,web"
```

Or add tags to existing bookmarks:

```bash
# CLI
btk tag add python 123 456 789

# Shell
btk:/$ cd bookmarks/123
btk:/bookmarks/123$ tag python tutorial
```

### Tag Names

Tag names should be:

- **Lowercase** - For consistency (e.g., `python` not `Python`)
- **Descriptive** - Clear and meaningful (e.g., `machine-learning` not `ml1`)
- **Concise** - Short but descriptive (e.g., `web-dev` not `web-development-resources`)
- **Hierarchical** - Use `/` for hierarchy (e.g., `programming/python/web`)

**Valid tag characters:**

- Letters: `a-z`, `A-Z` (though lowercase is recommended)
- Numbers: `0-9`
- Special: `-`, `_`, `/` (for hierarchy)

**Invalid:** Spaces, commas, or special characters like `@`, `#`, `!`

## Hierarchical Tags

BTK supports hierarchical tags using `/` as a separator, allowing you to create nested organizational structures.

### Creating Hierarchies

Simply use `/` in your tag names:

```bash
# Add hierarchical tags
btk bookmark add https://flask.com \
  --tags "programming/python/web/flask"

btk bookmark add https://numpy.org \
  --tags "programming/python/data-science/numpy"

btk bookmark add https://react.dev \
  --tags "programming/javascript/web/react"
```

This creates a hierarchy:

```
programming/
├── python/
│   ├── web/
│   │   └── flask
│   └── data-science/
│       └── numpy
└── javascript/
    └── web/
        └── react
```

### Viewing Hierarchies

Use the tree view to see your tag structure:

```bash
btk tag tree
```

**Output:**

```
📁 Root
├── 📁 programming (234 bookmarks)
│   ├── 📁 python (127 bookmarks)
│   │   ├── 📁 web (45 bookmarks)
│   │   │   ├── django (23 bookmarks)
│   │   │   ├── flask (15 bookmarks)
│   │   │   └── fastapi (7 bookmarks)
│   │   ├── 📁 data-science (38 bookmarks)
│   │   │   ├── pandas (20 bookmarks)
│   │   │   ├── numpy (12 bookmarks)
│   │   │   └── scikit-learn (6 bookmarks)
│   │   └── 📁 testing (19 bookmarks)
│   │       ├── pytest (12 bookmarks)
│   │       └── unittest (7 bookmarks)
│   ├── 📁 javascript (67 bookmarks)
│   │   ├── 📁 web (45 bookmarks)
│   │   │   ├── react (25 bookmarks)
│   │   │   ├── vue (12 bookmarks)
│   │   │   └── angular (8 bookmarks)
│   │   └── 📁 node (22 bookmarks)
│   └── 📁 go (40 bookmarks)
├── 📁 research (89 bookmarks)
│   ├── 📁 machine-learning (56 bookmarks)
│   │   ├── nlp (23 bookmarks)
│   │   ├── computer-vision (18 bookmarks)
│   │   └── reinforcement-learning (15 bookmarks)
│   └── 📁 papers (33 bookmarks)
└── 📁 tutorial (156 bookmarks)
    ├── video (67 bookmarks)
    └── written (89 bookmarks)
```

### Navigating Hierarchies in Shell

The shell makes hierarchical tags browsable like directories:

```bash
btk:/$ cd tags
btk:/tags$ ls
programming/  research/  tutorial/

btk:/tags$ cd programming
btk:/tags/programming$ ls
python/  javascript/  go/  rust/

btk:/tags/programming$ cd python
btk:/tags/programming/python$ ls
web/  data-science/  testing/
3298  4095  5124  5789  (bookmark IDs)

btk:/tags/programming/python$ cd web
btk:/tags/programming/python/web$ ls
django/  flask/  fastapi/
1001  1002  1003  (more bookmark IDs)
```

### Hierarchy Best Practices

**Use consistent patterns:**

```bash
# Good: Consistent depth and naming
programming/python/web/django
programming/python/web/flask
programming/python/data-science/pandas

# Avoid: Inconsistent depth
programming/python
programming/python/web/django/advanced
```

**Don't go too deep:**

```bash
# Good: 3-4 levels maximum
programming/python/web/django

# Too deep: Hard to navigate
programming/languages/python/frameworks/web/backend/django/advanced/deployment
```

**Use parent tags strategically:**

If a bookmark is tagged `programming/python/web/flask`, you can find it by searching for:

- `programming` (finds ALL programming bookmarks)
- `programming/python` (finds ALL Python bookmarks)
- `programming/python/web` (finds ALL Python web bookmarks)
- `programming/python/web/flask` (finds ONLY Flask bookmarks)

## Tag Operations

### Listing Tags

View all tags in your collection:

=== "Simple List"
    ```bash
    btk tag list

    # Output:
    programming
    programming/python
    programming/python/web
    programming/python/web/django
    programming/python/web/flask
    programming/python/data-science
    research
    tutorial
    ```

=== "Tree View"
    ```bash
    btk tag tree

    # Shows hierarchical structure (see above)
    ```

=== "Statistics"
    ```bash
    btk tag stats

    # Output:
    Tag Statistics
    ─────────────────────────────────────────
    Total Tags: 47
    Total Usage: 1,234 (avg 26.3 per tag)

    Most Used Tags:
    1. tutorial (156 bookmarks)
    2. programming (127 bookmarks)
    3. python (89 bookmarks)
    4. research (67 bookmarks)
    5. web (56 bookmarks)

    Least Used Tags:
    1. draft (1 bookmark)
    2. archive (2 bookmarks)
    3. temp (3 bookmarks)
    ```

### Renaming Tags

Rename a tag across all bookmarks using either CLI or shell:

=== "CLI"
    ```bash
    # Simple rename
    btk tag rename javascript js

    # Rename with hierarchy
    btk tag rename programming/python/web programming/python/web-dev

    # Reorganize hierarchy
    btk tag rename backend programming/backend
    ```

=== "Shell"
    ```bash
    # Navigate to tags directory
    btk:/$ cd tags

    # Rename using mv command
    btk:/tags$ mv javascript js
    Renaming tag 'javascript' to 'js'...
    Found 47 bookmarks with tag 'javascript'
    Confirm rename? [y/N]: y
    ✓ Successfully renamed tag in 47 bookmarks

    # Rename with hierarchy
    btk:/tags$ mv programming/python/web programming/python/web-dev
    ```

!!! warning "Global Operation"
    Renaming affects ALL bookmarks with that tag. The operation shows how many bookmarks will be affected and asks for confirmation.

### Copying Tags

Copy a tag to additional bookmarks:

=== "CLI"
    ```bash
    # Copy to specific bookmarks
    btk tag copy featured --to-ids 123 456 789

    # Copy to starred bookmarks
    btk tag copy high-priority --starred

    # Copy to bookmarks with existing tags
    btk tag copy reviewed --filter-tags "programming/python"
    ```

=== "Shell"
    ```bash
    # Copy tag to current bookmark
    btk:/bookmarks/123$ cp important .

    # Copy tag to specific bookmark
    btk:/$ cp featured 123

    # Copy tag to all bookmarks in context
    btk:/tags/programming/python$ cp reviewed *
    Copying tag 'reviewed' to 127 bookmarks...
    Confirm? [y/N]: y
    ✓ Added tag 'reviewed' to 127 bookmarks
    ```

### Filtering by Tags

Filter bookmarks by tag prefix:

=== "CLI"
    ```bash
    # Filter by tag
    btk tag filter programming/python

    # Use with other commands
    btk tag filter programming/python | btk export output.html html
    ```

=== "Shell"
    ```bash
    # Navigate to tag directory
    btk:/$ cd tags/programming/python
    btk:/tags/programming/python$ ls
    # Shows only Python bookmarks

    # Use context-aware commands
    btk:/tags/programming/python$ recent
    # Shows only recent Python bookmarks
    ```

## Organizational Strategies

### By Topic/Category

Organize bookmarks by subject matter:

```
programming/
├── python/
├── javascript/
├── go/
└── rust/

research/
├── machine-learning/
├── databases/
└── networking/

design/
├── ui-ux/
├── graphics/
└── typography/
```

### By Project

Organize bookmarks by work projects:

```
projects/
├── website-redesign/
│   ├── inspiration/
│   ├── tools/
│   └── resources/
├── ml-classifier/
│   ├── papers/
│   ├── datasets/
│   └── libraries/
└── mobile-app/
    ├── react-native/
    └── apis/
```

### By Status/Workflow

Track bookmark lifecycle:

```
status/
├── to-read/
├── reading/
├── completed/
└── reference/

priority/
├── high/
├── medium/
└── low/

work/
├── active/
├── backlog/
└── archived/
```

### By Content Type

Organize by the type of content:

```
content-type/
├── article/
├── video/
│   ├── tutorial/
│   └── conference-talk/
├── documentation/
├── tool/
└── course/
```

### Hybrid Approach

Combine multiple strategies:

```bash
# Topic + Status
btk bookmark add https://example.com \
  --tags "programming/python/web,status/to-read,priority/high"

# Project + Content Type
btk bookmark add https://example.com \
  --tags "projects/ml-classifier,content-type/paper,research/machine-learning"

# Category + Workflow
btk bookmark add https://example.com \
  --tags "design/ui-ux,work/active,content-type/tool"
```

## Tag Maintenance

### Finding Unused Tags

Find tags with few bookmarks:

```bash
btk tag stats

# Look at "Least Used Tags" section
```

### Consolidating Tags

Merge similar or duplicate tags:

```bash
# Find duplicates
btk tag list | grep -i "javascript\|js"

# Consolidate
btk tag rename javascript js
btk tag rename js-framework javascript/framework
```

### Cleaning Up Hierarchies

Reorganize your tag structure:

```bash
# Before: Flat structure
backend
frontend
fullstack

# After: Hierarchical structure
btk tag rename backend programming/backend
btk tag rename frontend programming/frontend
btk tag rename fullstack programming/fullstack

# Result:
programming/
├── backend/
├── frontend/
└── fullstack/
```

### Batch Tagging

Add tags to groups of bookmarks:

=== "CLI"
    ```bash
    # Tag all starred bookmarks
    btk tag copy reviewed --starred

    # Tag bookmarks with existing tags
    btk tag copy important --filter-tags "priority/high"
    ```

=== "Shell"
    ```bash
    # Navigate to context
    btk:/$ cd starred

    # Tag all in context
    btk:/starred$ cp reviewed *
    ```

## Advanced Tag Techniques

### Multi-Dimensional Tagging

Use tags from different dimensions to create rich metadata:

```bash
# Dimension 1: Topic
# Dimension 2: Skill Level
# Dimension 3: Content Type
# Dimension 4: Status

btk bookmark add https://example.com \
  --tags "programming/python/web,level/advanced,type/tutorial,status/completed"
```

Query using any dimension:

```bash
# All advanced Python content
btk tag filter level/advanced | btk tag filter programming/python

# All completed tutorials
btk tag filter type/tutorial | btk tag filter status/completed
```

### Temporal Tags

Track when bookmarks were added or relevant:

```bash
# Year-based
added/2024/
├── q1/
├── q2/
├── q3/
└── q4/

# Event-based
events/
├── conference-2024/
├── hackathon-spring/
└── workshop-ml/
```

### Source Tags

Track where bookmarks came from:

```bash
source/
├── reddit/
│   ├── r-programming/
│   └── r-python/
├── twitter/
├── newsletter/
│   ├── python-weekly/
│   └── javascript-weekly/
└── personal/
```

### Relationship Tags

Indicate relationships between bookmarks:

```bash
# Prerequisites
prereq/linear-algebra
prereq/probability

# Related topics
related/docker
related/kubernetes

# Alternatives
alternative-to/tool-x
alternative-to/library-y
```

## Tag Integration with Shell

The shell provides powerful ways to work with tags:

### Browse by Tag Hierarchy

```bash
btk:/$ cd tags/programming/python/web
btk:/tags/programming/python/web$ ls
django/  flask/  fastapi/
1234  5678  9012  (bookmark IDs)

# View bookmark in tag context
btk:/tags/programming/python/web$ cd 1234
btk:/tags/programming/python/web/1234$ ls
url  title  tags  description
```

### Context-Aware Operations

Commands adapt to your tag context:

```bash
# Recent bookmarks in Python web category
btk:/tags/programming/python/web$ recent visited

# Statistics for Python web bookmarks
btk:/tags/programming/python/web$ stat

# Search within context
btk:/tags/programming/python/web$ find "django"
```

### Quick Tag Operations

```bash
# Add tag to bookmark in context
btk:/tags/programming/python/web$ cd 1234
btk:/tags/programming/python/web/1234$ tag tutorial advanced

# Copy tag to all in context
btk:/tags/programming/python$ cp reviewed *

# Rename tag from anywhere
btk:/tags$ mv old-name new-name
```

## Tag Patterns and Anti-Patterns

### Good Patterns

**Consistent naming:**

```bash
# Good: Consistent style
programming/python
programming/javascript
programming/go

# Bad: Inconsistent style
programming/python
ProgrammingJavaScript
prog_go
```

**Meaningful hierarchies:**

```bash
# Good: Clear hierarchy
programming/python/web/django
programming/python/web/flask

# Bad: Unclear hierarchy
python-django
web-python-django
programming-web-django-python
```

**Appropriate specificity:**

```bash
# Good: Balance of general and specific
programming/python
programming/python/web
programming/python/web/django

# Bad: Too general or too specific
programming
programming/python/web/django/admin/authentication/oauth2
```

### Anti-Patterns to Avoid

**Don't use tags as folders:**

```bash
# Bad: Treating tags like exclusive folders
folder1/bookmark-a
folder2/bookmark-b
# Bookmarks can't be in multiple folders

# Good: Using tags for flexible categorization
programming/python, tutorial, beginner
# Bookmark can have multiple relevant tags
```

**Don't create overly long tag names:**

```bash
# Bad: Too long
programming-languages-python-web-frameworks-django-tutorials

# Good: Hierarchical
programming/python/web/django, tutorial
```

**Don't use spaces in tags:**

```bash
# Bad: Spaces cause issues
"machine learning", "web development"

# Good: Use hyphens or hierarchy
machine-learning, web-development
# or
ml/machine-learning, programming/web/development
```

## Tag Export and Import

### Exporting with Tag Structure

Export bookmarks with hierarchical tag folders:

```bash
# Export as hierarchical HTML
btk export html bookmarks.html --hierarchical

# Result in browser:
# 📁 Programming
#   📁 Python
#     📁 Web
#       🔖 Django Tutorial
#       🔖 Flask Docs
```

### Importing Tagged Bookmarks

Import bookmarks while preserving tags:

```bash
# Import HTML with tags
btk import html bookmarks.html

# Import with additional tags
btk import html bookmarks.html --add-tags "imported,backup-2024"

# Import JSON with full tag data
btk import json bookmarks.json
```

## Tag Analytics

### Tag Usage Statistics

Analyze how you use tags:

```bash
btk tag stats

# Shows:
# - Total tags
# - Total usage
# - Most/least used tags
# - Average tags per bookmark
```

### Finding Tag Patterns

Discover tag relationships:

```bash
# Bookmarks with multiple Python-related tags
btk bookmark query "tags LIKE '%python%'"

# Most popular tag combinations
btk db stats --tags
```

### Tag Health

Identify tag issues:

```bash
# Find bookmarks with no tags
btk bookmark query "tags IS NULL OR tags = ''"

# Find bookmarks with many tags (possible over-tagging)
# Use shell or custom query

# Find single-use tags (candidates for removal)
btk tag stats  # Look at "Least Used Tags"
```

## Next Steps

- **[Interactive Shell](shell.md)** - Learn to navigate tag hierarchies in the shell
- **[Core Commands](commands.md)** - Tag management commands
- **[Search & Query](search.md)** - Search by tags
- **[Import & Export](import-export.md)** - Export hierarchical tag structures

## See Also

- **[Shell Guide](shell.md)** - Tag navigation in the shell
- **[CLI Reference](../api/cli.md)** - Complete tag command reference
- **[Architecture](../development/architecture.md)** - How tags are stored
