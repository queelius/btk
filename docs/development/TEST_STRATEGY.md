# Test Strategy for BTK Shell and CLI

## Overview

This document outlines the testing strategy for the recently refactored `btk/shell.py` and `btk/cli.py` modules. The goal is to achieve meaningful test coverage focusing on behavior rather than implementation details, enabling confident future refactoring.

## Testing Philosophy

Following TDD best practices:
- **Test behavior, not implementation** - Focus on observable outcomes, not internal mechanics
- **Test at the right level** - Unit tests for logic, integration tests for workflows
- **Make tests resilient** - Tests should survive implementation refactoring
- **Clear failure messages** - Tests should clearly indicate what's broken

## Shell.py Test Strategy

### Priority 1: Core Navigation (CRITICAL)

**What to test:**
- Path parsing and normalization (`_parse_path()`)
- Context detection from paths (`_get_context()`, `_get_context_for_path()`)
- Virtual filesystem navigation (`cd`, `ls`, `pwd`)

**Why critical:**
- Foundation for all other shell functionality
- Complex logic with many edge cases
- Easy to break during refactoring

**Test approach:**
- Use test database with known data
- Test behavior, not internal state
- Focus on path resolution edge cases (`.`, `..`, absolute, relative)
- Verify context detection for all virtual directories

**Example tests:**
```python
def test_parse_path_absolute():
    """Absolute paths should resolve correctly."""
    # /bookmarks/123 -> /bookmarks/123

def test_parse_path_relative():
    """Relative paths should resolve from cwd."""
    # cwd=/tags, path=python -> /tags/python

def test_parse_path_parent():
    """Parent navigation (..) should work correctly."""
    # cwd=/tags/python, path=.. -> /tags

def test_context_bookmark():
    """Bookmark context should be detected correctly."""
    # path=/bookmarks/123 -> {type: 'bookmark', bookmark_id: 123, bookmark: <obj>}

def test_context_tag_hierarchy():
    """Hierarchical tags should be navigable."""
    # path=/tags/programming/python -> {type: 'tags', tag_path: 'programming/python', bookmarks: [...]}
```

### Priority 2: Context-Aware Commands (HIGH)

**What to test:**
- Commands that operate on current context (`cat`, `star`, `tag`)
- Commands with path-like syntax (`cat 123/url`)
- New commands (`recent`, `mv`, `cp`)

**Why high priority:**
- User-facing functionality
- Complex argument parsing
- Multiple code paths based on context

**Test approach:**
- Mock or use test database
- Test command behavior in different contexts
- Verify error handling (e.g., not in bookmark context)
- Test with both current context and explicit IDs

**Example tests:**
```python
def test_cat_in_bookmark_context():
    """cat should show field when in bookmark context."""
    # cd /bookmarks/123; cat url -> prints URL

def test_cat_with_path_syntax():
    """cat should support path-like syntax."""
    # cat 123/url -> prints URL of bookmark 123

def test_star_toggle():
    """star should toggle starred status."""
    # Initial: not starred; star -> starred; star -> not starred

def test_mv_tag():
    """mv should rename tags across all bookmarks."""
    # mv old_tag new_tag -> all bookmarks with old_tag now have new_tag
```

### Priority 3: Virtual Filesystem Behavior (MEDIUM)

**What to test:**
- Virtual directory listing (`ls` behavior in different contexts)
- Domain filtering
- Tag filtering by prefix
- Bookmark context in virtual paths (e.g., `/tags/video/3298`)

**Why medium priority:**
- Supporting functionality for navigation
- Less complex than navigation core
- Still important for user experience

**Test approach:**
- Create test data with various tags and domains
- Verify filtering returns correct bookmarks
- Test hierarchical tag display

### Priority 4: Edge Cases and Error Handling (LOW)

**What to test:**
- Invalid paths
- Non-existent bookmarks
- Empty databases
- Malformed input

**Why low priority (but still valuable):**
- Less likely to be exercised
- Often caught during development
- Good for robustness but not critical for core functionality

## CLI.py Test Strategy

### Priority 1: Grouped Argument Parser (CRITICAL)

**What to test:**
- Parser accepts correct command groups (`bookmark`, `tag`, `content`, etc.)
- Subcommands route to correct functions
- Required arguments are enforced
- Optional arguments are handled correctly

**Why critical:**
- Foundation for all CLI functionality
- Breaks would affect all commands
- Easy to verify correct routing

**Test approach:**
- Use argparse with test arguments (don't execute commands)
- Verify parser structure programmatically
- Test argument validation

**Example tests:**
```python
def test_bookmark_add_parser():
    """bookmark add should accept URL and optional arguments."""
    # btk bookmark add <url> --tags "x,y" -> parsed correctly

def test_tag_rename_parser():
    """tag rename should accept old and new tag names."""
    # btk tag rename old new -> parsed correctly

def test_invalid_command_group():
    """Invalid command groups should raise error."""
    # btk invalid -> SystemExit or error
```

### Priority 2: Tag Management Commands (HIGH)

**What to test:**
- `cmd_tag_add()` - adds tags to bookmarks
- `cmd_tag_remove()` - removes tags from bookmarks
- `cmd_tag_rename()` - renames tags globally

**Why high priority:**
- New functionality in refactoring
- Core user-facing features
- Database mutations (need to verify correctness)

**Test approach:**
- Use test database
- Verify database state changes
- Test with multiple bookmarks
- Test error cases (non-existent tags/bookmarks)

**Example tests:**
```python
def test_tag_add_single_bookmark():
    """Adding tag to single bookmark should work."""
    # btk tag add python 123 -> bookmark 123 has python tag

def test_tag_rename_updates_all_bookmarks():
    """Renaming tag should update all bookmarks."""
    # 3 bookmarks with "old" tag; rename to "new" -> all 3 have "new"

def test_tag_rename_cleans_orphans():
    """Renamed tag should be removed from tag table."""
    # After rename, old tag should not exist in database
```

### Priority 3: Filter Building (MEDIUM)

**What to test:**
- `build_filters()` correctly interprets arguments
- Filters work across commands (list, search, export)
- Default behavior (exclude archived)

**Why medium priority:**
- Reusable utility function
- Affects multiple commands
- Relatively simple logic

### Priority 4: Command Integration (LOW to MEDIUM)

**What to test:**
- End-to-end command execution
- Output formatting
- Error handling

**Why varied priority:**
- Some commands already tested elsewhere
- Integration tests are valuable but slower
- Focus on new/changed commands

## Testing Infrastructure

### Fixtures

Create reusable fixtures in `tests/conftest.py`:

```python
@pytest.fixture
def test_shell(temp_db):
    """Create a BookmarkShell with test database."""
    from btk.shell import BookmarkShell
    shell = BookmarkShell(temp_db)
    return shell

@pytest.fixture
def temp_db():
    """Create a temporary database with test data."""
    # Create temp database
    # Populate with known bookmarks, tags
    # Return path

@pytest.fixture
def populated_db():
    """Create database with diverse test data."""
    # Bookmarks with hierarchical tags
    # Multiple domains
    # Starred/archived bookmarks
    # Return Database instance
```

### Mocking Strategy

**Mock at architectural boundaries:**
- ✅ Mock Database for shell command tests (fast, isolated)
- ✅ Use test database for integration tests (realistic, slower)
- ❌ Don't mock internal methods (_parse_path, _get_context) - test behavior

**Rich Console Output:**
- Mock or capture `console.print()` to verify output
- Use `StringIO` for output verification where possible

### Test Organization

```
tests/
├── test_shell.py              # Shell tests
│   ├── TestPathParsing
│   ├── TestContextDetection
│   ├── TestNavigation
│   ├── TestContextAwareCommands
│   └── TestVirtualFilesystem
├── test_cli.py                # CLI tests
│   ├── TestArgumentParser
│   ├── TestTagCommands
│   ├── TestFilterBuilding
│   └── TestCommandIntegration
└── conftest.py                # Shared fixtures
```

## Coverage Goals

**Realistic targets:**
- `shell.py`: 60-70% coverage (focus on testable logic, skip interactive I/O)
- `cli.py`: 50-60% coverage (focus on new tag commands and parser structure)

**What NOT to test:**
- Rich console formatting details (visual output)
- Interactive input prompts (difficult to test, low value)
- System command execution (`do_shell()`)
- Tutorial text display

**What to PRIORITIZE:**
- Path parsing logic
- Context detection
- Database operations
- Tag management
- Argument parsing

## Test Execution

### Running Tests

```bash
# Run all tests
pytest

# Run shell tests only
pytest tests/test_shell.py

# Run CLI tests only
pytest tests/test_cli.py

# Run with coverage
pytest --cov=btk.shell --cov=btk.cli --cov-report=term-missing

# Run specific test class
pytest tests/test_shell.py::TestPathParsing
```

### Coverage Analysis

```bash
# Generate HTML coverage report
pytest --cov=btk --cov-report=html

# View in browser
open htmlcov/index.html
```

## Success Criteria

1. ✅ All priority 1 tests implemented and passing
2. ✅ Shell path parsing has >80% coverage
3. ✅ Shell context detection has >80% coverage
4. ✅ New tag commands have >80% coverage
5. ✅ CLI argument parser structure is verified
6. ✅ Tests enable confident refactoring (implementation can change without breaking tests)
7. ✅ Test failures clearly indicate what's broken

## Implementation Phases

### Phase 1: Foundation (THIS PHASE)
- Path parsing tests
- Context detection tests
- Argument parser tests
- Test database fixtures

### Phase 2: Commands
- Navigation command tests (cd, ls, pwd)
- Context-aware command tests (cat, star, tag)
- Tag management command tests

### Phase 3: Integration
- End-to-end shell workflows
- End-to-end CLI workflows
- Error handling and edge cases

### Phase 4: Refinement
- Increase coverage of critical paths
- Add regression tests for bugs found
- Performance tests if needed

## Notes

- Tests should be **behavior-focused**: "When I cd to /tags/python, ls should show python bookmarks"
- Tests should be **resilient**: Implementation refactoring shouldn't break tests
- Tests should be **clear**: Test names describe behavior, failures indicate what broke
- Tests should be **fast**: Use test database, minimal I/O, parallel execution where possible

## References

- CLAUDE.md - User requirements for TDD approach
- REFACTOR_SUMMARY.md - Details of refactoring
- Existing tests (test_graph.py, test_models.py) - Examples of good test patterns
