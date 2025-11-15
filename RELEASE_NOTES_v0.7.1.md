# BTK v0.7.1 Release Notes

**Release Date:** October 20, 2025
**Git Tag:** v0.7.1
**Commit:** 0734578

## 🎉 What's New

### Smart Collections (5 Auto-Updating Directories)

BTK now includes 5 smart collections that automatically filter and organize your bookmarks:

```bash
btk:/$ ls
bookmarks/    (100)   All bookmarks
unread/       (42)    Bookmarks never visited    ← NEW!
popular/      (100)   100 most visited           ← NEW!
broken/       (3)     Unreachable bookmarks      ← NEW!
untagged/     (15)    Bookmarks with no tags     ← NEW!
pdfs/         (8)     PDF bookmarks              ← NEW!
```

**Key Features:**
- Auto-update as bookmarks change
- Show counts in `ls` output
- Full navigation support
- Context-aware commands work in collections

**Example Workflow:**
```bash
btk:/$ cd unread
btk:/unread$ ls | head -10  # See unread bookmarks
btk:/unread$ cat 1001/title # Preview
btk:/unread$ visit 1001     # Open & mark as read
# Bookmark automatically leaves /unread collection
```

### Time-Based Recent Navigation (Hierarchical)

Enhanced `/recent` directory with 18 time-based subdirectories:

```
/recent/
├── today/
│   ├── visited/    # Bookmarks visited today
│   ├── added/      # Bookmarks added today
│   └── starred/    # Bookmarks starred today
├── yesterday/
├── this-week/
├── last-week/
├── this-month/
└── last-month/
```

**Example Workflow:**
```bash
btk:/$ cd recent/today/visited
btk:/recent/today/visited$ ls
5001  4987  4923  4892  ...

btk:/recent/today/visited$ recent
# Shows recently visited sorted by time

btk:/$ cd recent/this-week/added
btk:/recent/this-week/added$ tag 5001 5002 5003 weekly-review
# Bulk tag this week's additions
```

## 🐛 Bug Fixes

- **Fixed:** UNIQUE constraint violation when renaming tags on multiple bookmarks with `mv` command
- **Fixed:** Timezone-aware datetime comparison issues in `/recent` sorting
- **Fixed:** Context detection for smart collection navigation

## 📊 Testing

- ✅ **515 tests passing** (all existing tests + new features)
- ✅ **No regressions** in existing functionality
- ✅ **Shell coverage:** 53.12% (69 tests)
- ✅ **CLI coverage:** 23.11% (41 tests)
- ✅ **Full backward compatibility** maintained

## 📚 Documentation

### New Documentation
- **docs/guide/shell.md** - Comprehensive smart collections guide (~1,250 lines)
- **docs/development/SMART_COLLECTIONS_DESIGN.md** - Design document
- **docs/development/SMART_COLLECTIONS_IMPLEMENTATION.md** - Technical details
- **docs/development/README.md** - Development docs index

### Updated Documentation
- **docs/index.md** - Homepage with v0.7.1 highlights
- **docs/getting-started/quickstart.md** - Smart collections quick start
- **docs/development/changelog.md** - Comprehensive v0.7.1 entry
- **README.md** - Updated roadmap and features

## 🔧 Technical Details

### Architecture Changes
- **New Class:** `SmartCollection` with filter_func pattern
- **New Registry:** `SMART_COLLECTIONS` (easily extensible)
- **New Functions:** `get_time_ranges()`, `filter_by_activity()`
- **Enhanced Methods:** `_get_context()`, `_get_context_for_path()`, `do_ls()`
- **Display Helpers:** `_ls_recent_root()`, `_ls_recent_period()`

### Files Changed
- **btk/shell.py** - ~300 lines added/modified for smart collections
- **pyproject.toml** - Version 0.6.0 → 0.7.1
- **btk/__init__.py** - Version 2.0.0 → 0.7.1 (fixed inconsistency)
- **51 files changed** total: +18,863 insertions, -414 deletions

### Performance
- Collections use lazy evaluation (computed on access)
- No caching (suitable for databases up to 10k bookmarks)
- Future optimization opportunities documented

## 🎯 Design Decisions

1. **No `starred_at` field** - Using `added` timestamp as proxy to avoid schema migration
2. **Show counts** - `unread/ (42)` more informative than just `unread/`
3. **Recently visited default** - `/recent` shows visited (not added) as more intuitive
4. **5 core collections** - Room for growth based on user feedback

## 🔄 Backward Compatibility

- ✅ All existing shell commands work unchanged
- ✅ `/recent/<id>` direct bookmark access still works
- ✅ All CLI commands unchanged
- ✅ No breaking changes to API

## 📦 Release Checklist

- [x] Version updated in pyproject.toml (0.7.1)
- [x] Version updated in btk/__init__.py (0.7.1)
- [x] Shell intro version updated (v0.7.1)
- [x] All 515 tests passing
- [x] Documentation updated (shell guide, changelog, README)
- [x] Repository cleaned up (dev docs organized)
- [x] Git commit created
- [x] Git tag v0.7.1 created

## 🚀 Deployment

### To Deploy

```bash
# Already completed
git commit -m "Release v0.7.1..."
git tag -a v0.7.1 -m "BTK v0.7.1..."

# Next steps (when ready)
git push origin master
git push origin v0.7.1

# Optional: Publish to PyPI
python -m build
twine upload dist/*
```

### Installation

Users can install v0.7.1 with:

```bash
# From PyPI (after publishing)
pip install bookmark-tk==0.7.1

# From git
pip install git+https://github.com/queelius/bookmark-tk.git@v0.7.1

# From source
git clone https://github.com/queelius/bookmark-tk.git
cd bookmark-tk
git checkout v0.7.1
pip install -e .
```

## 🔮 Future Enhancements

Short-term ideas from design document:
- User-defined collections via config
- More time periods (last-7-days, last-30-days)
- Collection parameters (`popular/50` for top 50)
- Performance optimizations for large databases

Medium-term:
- Collection operators (intersection, union, difference)
- Dynamic collection parameters
- Collection-based search
- Export collections to separate files

## 📝 Known Limitations

1. **Starred activity approximation** - Uses `added` timestamp since no `starred_at` field
2. **No caching** - Collections recompute on each access (may be slow for >100k bookmarks)
3. **PDF detection** - Simple URL suffix check (doesn't inspect content type)

## 🙏 Acknowledgments

Developed with assistance from Claude Code (claude.com/claude-code).

---

**For detailed technical implementation, see:**
- `docs/development/SMART_COLLECTIONS_IMPLEMENTATION.md`
- `docs/development/SMART_COLLECTIONS_DESIGN.md`

**For user guides, see:**
- `docs/guide/shell.md`
- `docs/getting-started/quickstart.md`
- `docs/development/changelog.md`
