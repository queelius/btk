# Bookmark Toolkit (BTK)

A modern, database-first bookmark manager with powerful features for organizing, searching, and analyzing your bookmarks.

## Features

- 🗄️ **SQLite-based storage** - Fast, reliable, and portable
- 📥 **Multi-format import** - HTML (Netscape), JSON, CSV, Markdown, plain text
- 📤 **Multi-format export** - HTML (hierarchical folders), JSON, CSV, Markdown
- 🔍 **Advanced search** - Full-text search including cached content
- 🏷️ **Hierarchical tags** - Organize with nested tags (e.g., `programming/python`)
- 🤖 **Auto-tagging** - NLP-powered automatic tag generation
- 📄 **Content caching** - Stores compressed HTML and markdown for offline access
- 📑 **PDF support** - Extracts and indexes text from PDF bookmarks
- 🔌 **Plugin system** - Extensible architecture for custom features
- 🌐 **Browser integration** - Import bookmarks and history from Chrome, Firefox, Safari
- 📊 **Statistics & analytics** - Track usage, duplicates, health scores
- 🕸️ **Graph analysis** - Visualize bookmark relationships and similarity networks
- ⚡ **Parallel processing** - Fast bulk operations with multi-threading

## Quick Example

```bash
# Install
pip install bookmark-tk

# Initialize database
btk init

# Import bookmarks
btk import bookmarks.html

# Search
btk search "python tutorial"

# Add bookmark
btk add https://example.com --title "Example" --tags tutorial,web

# Export to various formats
btk export output.html html --hierarchical
btk export output.json json

# Build bookmark similarity graph
btk graph build --min-edge-weight 4.0

# Export graph for Gephi analysis
btk graph export graph.gexf --format gexf --min-weight 4.0
```

## Why BTK?

**Modern Architecture**: Built on SQLAlchemy ORM with SQLite, BTK provides fast queries, ACID transactions, and a portable database format.

**Powerful Search**: Full-text search across titles, URLs, descriptions, and cached content. Use JMESPath for complex queries.

**Content Preservation**: Automatically fetches and caches webpage content (with zlib compression) and extracts text from PDFs for offline access and search.

**Flexible Export**: Export to browser-compatible HTML with folder hierarchies, or machine-readable JSON/CSV formats.

**Graph Analysis**: Build weighted similarity graphs based on domain similarity, tag overlap, and direct links. Export to Gephi, yEd, or Cytoscape for advanced network analysis.

**Extensible**: Plugin system allows custom functionality without modifying core code.

## Documentation

- [Installation](getting-started/installation.md) - Get BTK installed
- [Quick Start](getting-started/quickstart.md) - Learn the basics
- [User Guide](guide/commands.md) - Complete command reference
- [Graph Analysis](guide/graph.md) - Visualize bookmark relationships
- [Plugin System](advanced/plugins.md) - Extend BTK's functionality

## Community

- **GitHub**: [queelius/bookmark-tk](https://github.com/queelius/bookmark-tk)
- **Issues**: [Report bugs or request features](https://github.com/queelius/bookmark-tk/issues)
- **PyPI**: [bookmark-tk](https://pypi.org/project/bookmark-tk/)

## License

MIT License - see [LICENSE](https://github.com/queelius/bookmark-tk/blob/master/LICENSE) file for details.
