# BTK Integrations

This directory contains various integrations for the Bookmark Toolkit (BTK) that extend its functionality without bloating the core tool.

## Available Integrations

### Core Integrations

#### mcp-btk
Model Context Protocol (MCP) server that exposes BTK functionality to AI assistants like Claude.
- **Language**: Node.js/TypeScript
- **Use Case**: AI assistant integration via MCP protocol
- **Features**: Search, list, add, remove bookmarks through AI interfaces

#### viz-btk
Visualization tools for creating bookmark graphs, network diagrams, and other visual representations of your bookmark data.
- **Language**: Python
- **Use Case**: Data visualization and network analysis
- **Features**: Generate interactive HTML graphs, static PNG images, or export graph data as JSON

#### btk-frontend
Modern web dashboard for managing and visualizing bookmarks in a browser.
- **Language**: HTML/JavaScript
- **Use Case**: Web-based bookmark management interface
- **Features**: Real-time statistics, search/filter, tag cloud, activity timeline, domain stats

#### miniweb
Export bookmarks as an interactive static website with network-aware navigation.
- **Language**: Python
- **Use Case**: Static site generation with semantic navigation
- **Features**: Navigate bookmarks by graph distance, semantic similarity, embedded pages

### Plugin Integrations

All plugin integrations implement the BTK plugin system and can be loaded via the plugin registry.

#### semantic_search
Semantic search engine using sentence embeddings for meaning-based bookmark discovery.
- **Type**: SearchEnhancer plugin
- **Dependencies**: sentence-transformers, numpy, scikit-learn
- **Features**: Semantic search, similarity detection, bookmark clustering
- **Use Case**: Find bookmarks by meaning rather than keywords

#### link_checker
Check bookmark URLs for availability, redirects, and issues.
- **Type**: BookmarkEnricher plugin
- **Dependencies**: requests
- **Features**: Dead link detection, redirect tracking, SSL validation, response time monitoring
- **Use Case**: Maintain bookmark quality and detect broken links

#### auto_tag_nlp
NLP-based automatic tag suggestion using TF-IDF and pattern matching.
- **Type**: TagSuggester plugin
- **Dependencies**: None (uses standard library)
- **Features**: TF-IDF term extraction, technology recognition, hierarchical tag generation
- **Use Case**: Automatically suggest relevant tags for bookmarks

#### auto_tag_llm
LLM-based tag suggestion using any OpenAI-compatible API (Ollama, OpenAI, LocalAI, etc.).
- **Type**: TagSuggester plugin
- **Dependencies**: requests
- **Features**: Context-aware tagging, hierarchical tags, configurable LLM providers
- **Use Case**: AI-powered intelligent tag suggestions

#### readability_extractor
Extract clean, readable content from web pages using readability algorithms.
- **Type**: ContentExtractor plugin
- **Dependencies**: requests, beautifulsoup4
- **Features**: Main content extraction, metadata parsing, reading time estimation
- **Use Case**: Extract article content for searchability and archival

#### social_metadata
Extract Open Graph, Twitter Card, and Schema.org metadata from web pages.
- **Type**: BookmarkEnricher plugin
- **Dependencies**: requests, beautifulsoup4
- **Features**: Social media metadata extraction, preview images, author/date extraction
- **Use Case**: Enrich bookmarks with social sharing metadata

#### wayback_archiver
Archive bookmarks to the Internet Archive's Wayback Machine for permanent preservation.
- **Type**: BookmarkEnricher plugin
- **Dependencies**: requests
- **Features**: Automatic archival, snapshot tracking, bulk archiving with rate limiting
- **Use Case**: Preserve web content permanently

#### browser_sync
Two-way synchronization between BTK and browser bookmarks (Chrome, Firefox, Edge, Brave, Vivaldi).
- **Type**: Standalone plugin
- **Dependencies**: None (direct file access)
- **Features**: Bidirectional sync, conflict resolution, change detection
- **Use Case**: Keep browser bookmarks in sync with BTK

#### bookmark_scheduler
Schedule bookmarks for reading, review, and reminders with spaced repetition.
- **Type**: Standalone plugin
- **Dependencies**: None (standard library)
- **Features**: Read-later queue, reminders, periodic review, spaced repetition algorithm
- **Use Case**: Manage reading queue and learning materials

## Philosophy

BTK follows the Unix philosophy of doing one thing well. The core `btk` tool focuses on bookmark management operations. These integrations provide additional functionality for specific use cases:

- **AI Integration**: mcp-btk for AI assistants
- **Visualization**: viz-btk and btk-frontend for visual exploration
- **Content Enhancement**: readability_extractor, social_metadata for richer bookmark data
- **Organization**: auto_tag_nlp, auto_tag_llm for intelligent tagging
- **Maintenance**: link_checker, wayback_archiver for bookmark health
- **Workflow**: browser_sync, bookmark_scheduler for productivity
- **Search**: semantic_search for meaning-based discovery

## Structure

Each integration is self-contained with its own:
- README.md with specific documentation
- Dependencies and package management (requirements.txt or package.json)
- Tests (where applicable)
- Examples and usage documentation

This modular approach keeps the core BTK tool lightweight while allowing users to add only the integrations they need.

## Installation

### Python Plugin Integrations

Most plugins can be used directly through BTK's plugin system:

```python
from btk.plugins import PluginRegistry

registry = PluginRegistry()
registry.discover_plugins()  # Auto-discovers plugins in integrations/
```

For standalone use:

```bash
cd integrations/<integration-name>
pip install -r requirements.txt  # If requirements.txt exists
python -m <integration-name>     # If CLI provided
```

### Node.js Integrations

```bash
cd integrations/mcp-btk
npm install
node index.js
```

### Web Integrations

```bash
# btk-frontend - just open in browser
open integrations/btk-frontend/index.html

# Or serve with any static server
cd integrations/btk-frontend
python -m http.server 8080
```

## Plugin Priority System

Plugins implement a priority system for execution order:

- **CRITICAL** (1): Must run first, system-critical operations
- **HIGH** (2): Important enrichments like social metadata, LLM tagging
- **NORMAL** (3): Standard operations like NLP tagging, link checking
- **LOW** (4): Optional enhancements like archiving
- **BACKGROUND** (5): Background tasks

## Configuration

Many plugins support configuration through:
1. Environment variables (BTK_*)
2. Config files (~/.btk/*.json)
3. Programmatic configuration

See individual integration READMEs for specific configuration options.