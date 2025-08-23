# Bookmark Toolkit (btk)

Bookmark Toolkit (btk) is a command-line tool for managing and analyzing bookmarks. It provides features for importing, searching, editing, and exporting bookmarks, as well as querying them using JMESPath.

## Installation

To install `bookmark-tk`, you can use `pip`:

```sh
pip install bookmark-tk
```

## Usage

It installs a command-line took, `btk`. To see how to use it, type:

```sh
btk --help
```

### Commands

- **import**: Import bookmarks from various formats, e.g., Netscape Bookmark Format HTML file.
  ```sh
  btk import oldbookmarks --format netscape --output bookmarks
  ```

- **search**: Search bookmarks by query.
  ```sh
  btk search mybookmarks "statistics"
  ```

- **list-index**: List the bookmarks with the given indices.
  ```sh
  btk list-index mybookmarks 1 2 3
  ```

- **add**: Add a new bookmark.
  ```sh
  btk add mybookmarks --title "My Bookmark" --url "https://example.com"
  ```

- **edit**: Edit a bookmark by its ID.
  ```sh
  btk edit mybookmarks 1 --title "Updated Title"
  ```

- **remove**: Remove a bookmark by its ID.
  ```sh
  btk remove mybookmarks 2
  ```

- **list**: List all bookmarks (including metadata).
  ```sh
  btk list mybookmarks
  ```

- **visit**: Visit a bookmark by its ID.
  ```sh
  btk visit mybookmarks 103
  ```

- **merge**: Perform merge (set) operations on bookmark libraries.
  ```sh
  btk merge union lib1 lib2 lib3 --output merged
  ```


- **reachable**: Check and mark bookmarks as reachable or not.
  ```sh
  btk reachable mybookmarks
  ```

- **purge**: Remove bookmarks marked as not reachable.
  ```sh
  btk purge mybookmarks --output purged
  ```

- **export**: Export bookmarks to a different format.
  ```sh
  btk export mybookmarks --output bookmarks.csv
  ```

- **jmespath**: Query bookmarks using JMESPath.
  ```sh
  btk jmespath mybookmarks "[?visit_count > `0`].title"
  ```

- **stats**: Get statistics about bookmarks.
  ```sh
  btk stats mybookmarks
  ```

- **about**: Get information about the tool.
  ```sh
  btk about
  ```

- **version**: Get the version of the tool.
  ```sh
  btk version
  ```


## Example JMESPath Queries

- Get all starred bookmarks:
  ```sh
  btk jmespath mybookmarks "[?stars == `true`].title"
  ```
- Get URLs of frequently visited bookmarks:
  ```sh
  btk jmespath mybookmarks "[?visit_count > `5`].url"
  ```
- Get bookmarks that contain 'wikipedia' in the URL:
  ```sh
  btk jmespath mybookmarks "[?contains(url, 'wikipedia')].{title: title, url: url}"
  ```



## Roadmap and Future Plans

BTK is actively evolving with a plugin-based architecture that enables extensibility while keeping the core lightweight. Here's our comprehensive roadmap:

### Recently Completed ✅

- **Plugin Architecture**: Extensible system for adding new capabilities without modifying core
- **Auto-tagging**: Automatic tag generation using domain rules, keywords, and content analysis
- **Content Extraction**: Fetches and analyzes webpage content for enhanced tagging
- **FastAPI Server**: REST API for programmatic access to BTK functionality
- **Web Dashboard**: Beautiful frontend interface with statistics, search, and management
- **Hierarchical Tags**: Support for nested tags with tree views and operations
- **Deduplication**: Smart duplicate detection and removal with multiple strategies
- **Bulk Operations**: Add, edit, and remove multiple bookmarks at once

### In Progress 🚧

- **Bookmark Collections/Sets**: Organize bookmarks into named collections with set operations
- **BTK REPL**: Interactive shell with tab completion and stateful operations

### Short-term Goals (Q1 2024) 🎯

#### Core Features
- **Complete API Coverage**: Add missing endpoints (JMESPath, reachability, library merge)
- **Similarity Detection**: Find related bookmarks using content analysis
- **Smart Search**: Natural language queries and semantic search
- **Reading Time & Analytics**: Track reading patterns and bookmark usage

#### Integrations
- **Browser Extensions**: Chrome/Firefox extensions for one-click bookmarking
- **Static Site Export**: Generate beautiful static websites from bookmarks
- **MCP Integration**: AI-powered natural language interface via Model Context Protocol

### Medium-term Goals (Q2-Q3 2024) 🚀

#### Smart Features
- **Auto-categorization**: Automatically organize bookmarks into collections
- **Link Rot Detection**: Periodic checks for dead links with Wayback Machine fallback
- **Content Summarization**: AI-powered summaries of bookmarked content
- **Recommendation Engine**: Suggest related content based on bookmarking patterns
- **Full-text Search**: Index and search within bookmarked page content

#### Organization & Discovery
- **Smart Collections**: Rule-based auto-organization (e.g., "All Python tutorials from 2024")
- **Bookmark Relationships**: Link related bookmarks and create knowledge graphs
- **Reading Lists**: Prioritized queues with reading goals
- **Rich Notes**: Markdown notes and annotations for bookmarks
- **Version History**: Track all changes to bookmarks over time

#### Visualization & Analytics
- **Network Visualization**: Interactive graphs showing tag and content relationships
- **Activity Heatmaps**: Visualize bookmarking patterns over time
- **Domain Analytics**: Detailed insights into your most bookmarked sources
- **Tag Evolution**: Track how your interests change over time
- **Reading Statistics**: Time spent, completion rates, reading velocity

### Long-term Vision (2024+) 🌟

#### Collaboration Features
- **Shared Collections**: Public/private bookmark collections with permissions
- **Team Libraries**: Collaborative bookmarking for organizations
- **Social Features**: Follow users, discover trending bookmarks
- **Comments & Discussions**: Community annotations on bookmarks

#### Advanced Integrations
- **NLP Integrations**: 
  - spaCy for named entity recognition
  - Transformers for semantic understanding
  - NLTK for linguistic analysis
- **Data Sources**:
  - RSS feed generation from collections
  - Two-way sync with Pocket, Instapaper, Pinboard
  - Import from browser history
  - Social media saved posts (Twitter, Reddit, HN)
- **Workflow Automation**:
  - Webhooks for bookmark events
  - IFTTT/Zapier integration
  - Email digests and reports
  - Scriptable hooks for custom actions

#### Power User Features
- **Query Language**: SQL-like queries for complex bookmark searches
- **Macro System**: Record and replay bookmark operations
- **Custom Fields**: User-defined metadata schemas
- **Bookmark Templates**: Predefined structures for common bookmark types
- **API-first Design**: Everything accessible via API for custom tooling

#### AI & Machine Learning
- **Smart Tagging**: ML models trained on your tagging patterns
- **Duplicate Detection**: Fuzzy matching for similar content
- **Content Classification**: Automatic quality and relevance scoring
- **Trend Detection**: Identify emerging topics in your bookmarks
- **Personal Knowledge Base**: Transform bookmarks into a queryable knowledge graph

### Architecture Principles

1. **Plugin-based Extensibility**: Core remains lightweight with optional heavy features
2. **Progressive Enhancement**: Basic features work without dependencies, advanced features are opt-in
3. **API-first Design**: All functionality exposed via APIs
4. **Privacy-focused**: Local-first with optional cloud features
5. **Standards Compliance**: Support common formats (Netscape, OPML, JSON-LD)

### Contributing to the Roadmap

We welcome contributions in any of these areas! The plugin architecture makes it easy to add new features without touching the core. See CONTRIBUTING.md for guidelines.

## License

This project is licensed under the MIT License.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue if you have suggestions or improvements.

## Author

Developed by [Alex Towell](https://github.com/queelius).

