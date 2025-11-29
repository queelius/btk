# BTK MCP Server

Model Context Protocol server for Bookmark Toolkit (BTK).

## Installation

```bash
npm install
```

## Usage

### With Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "btk": {
      "command": "node",
      "args": ["/absolute/path/to/mcp-btk/index.js"]
    }
  }
}
```

### Standalone Testing

```bash
# Run the server (it expects stdio communication)
node index.js

# The server will output "BTK MCP server running on stdio" to stderr
```

## Available Tools

- `btk_search` - Search bookmarks by title or URL
- `btk_list` - List all bookmarks
- `btk_add` - Add a new bookmark
- `btk_remove` - Remove a bookmark by ID
- `btk_jmespath` - Query bookmarks using JMESPath
- `btk_visit` - Visit a bookmark by ID
- `btk_reachable` - Check reachability of bookmarks

## Requirements

- Node.js 18+
- BTK installed and available in PATH (`pip install bookmark-tk`)
- A bookmark library created with BTK

## Development

The server uses the Model Context Protocol SDK to expose BTK functionality as tools that AI assistants can use.

### Testing

```bash
# Run tests
npm test

# Run tests with coverage
npm run test:coverage

# Run tests in watch mode
npm run test:watch
```

Tests are located in the `tests/` directory and use Jest.

### Adding New Tools

1. Add the tool definition in `setupToolHandlers()`
2. Add the command mapping in the `CallToolRequestSchema` handler
3. Add tests for the new tool
4. Update this README and the main integration guide

## License

MIT