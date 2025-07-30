# BTK Model Context Protocol (MCP) Integration Guide

This guide explains how to use Bookmark Toolkit (BTK) with AI assistants via the Model Context Protocol.

## Overview

BTK provides an MCP server that allows AI assistants like Claude to interact with your bookmarks directly. Instead of embedding LLM functionality within BTK, we expose BTK's capabilities as tools that any MCP-compatible AI can use.

## Installation

### 1. Install BTK

First, ensure BTK is installed and accessible from your command line:

```bash
pip install bookmark-tk
btk --version
```

### 2. Install the MCP Server

```bash
cd integrations/mcp-btk
npm install
```

### 3. Configure Your AI Assistant

#### For Claude Desktop

Add the following to your Claude Desktop configuration (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "btk": {
      "command": "node",
      "args": ["/path/to/btk/integrations/mcp-btk/index.js"],
      "env": {}
    }
  }
}
```

#### For Other MCP-Compatible Tools

Refer to your tool's documentation for adding MCP servers. The server runs on stdio and provides the following tools.

## Available Tools

### btk_search
Search bookmarks by title or URL.

**Parameters:**
- `lib_dir` (string, required): Directory of the bookmark library
- `query` (string, required): Search query

**Example:**
```
Search for bookmarks about "python" in my bookmarks library
```

### btk_list
List all bookmarks in a library.

**Parameters:**
- `lib_dir` (string, required): Directory of the bookmark library

**Example:**
```
Show me all bookmarks in ~/bookmarks
```

### btk_add
Add a new bookmark.

**Parameters:**
- `lib_dir` (string, required): Directory of the bookmark library
- `title` (string, required): Bookmark title
- `url` (string, required): Bookmark URL
- `tags` (array of strings, optional): Tags for the bookmark
- `description` (string, optional): Bookmark description
- `stars` (boolean, optional): Whether to star the bookmark

**Example:**
```
Add a bookmark for https://docs.python.org titled "Python Documentation" with tags ["python", "docs"] to my bookmarks
```

### btk_remove
Remove a bookmark by ID.

**Parameters:**
- `lib_dir` (string, required): Directory of the bookmark library
- `id` (integer, required): Bookmark ID

**Example:**
```
Remove bookmark with ID 42 from my bookmarks
```

### btk_jmespath
Query bookmarks using JMESPath syntax for complex filtering.

**Parameters:**
- `lib_dir` (string, required): Directory of the bookmark library
- `query` (string, required): JMESPath query

**Example:**
```
Find all starred bookmarks that have been visited more than 5 times
```

The AI will translate this to: `[?stars == \`true\` && visit_count > \`5\`]`

### btk_visit
Visit a bookmark by ID (opens in browser).

**Parameters:**
- `lib_dir` (string, required): Directory of the bookmark library
- `id` (integer, required): Bookmark ID

**Example:**
```
Open bookmark 15 from my bookmarks
```

### btk_reachable
Check if all bookmarks are still reachable (valid URLs).

**Parameters:**
- `lib_dir` (string, required): Directory of the bookmark library

**Example:**
```
Check which bookmarks in ~/bookmarks are still accessible
```

## Usage Examples

### Natural Language Queries

With the MCP server configured, you can use natural language to manage your bookmarks:

1. **"Show me all my starred bookmarks"**
   - The AI will use `btk_jmespath` with query `[?stars == \`true\`]`

2. **"Find bookmarks I haven't visited in a while"**
   - The AI will use `btk_jmespath` with a query like `[?visit_count == \`0\`]`

3. **"Add a bookmark for the OpenAI documentation"**
   - The AI will use `btk_add` with appropriate parameters

4. **"Search for all bookmarks about machine learning"**
   - The AI will use `btk_search` with query "machine learning"

5. **"Show me bookmarks tagged with 'research' that I added this year"**
   - The AI will use `btk_jmespath` with a complex query

### Example Conversation

```
User: Can you help me organize my bookmarks in ~/mybookmarks?

AI: I'll help you organize your bookmarks. Let me first see what you have.

[Uses btk_list tool with lib_dir: "~/mybookmarks"]

AI: I see you have 150 bookmarks. Let me analyze them:
- 23 are starred
- 45 have never been visited
- 12 appear to be broken links

Would you like me to:
1. Check which bookmarks are still reachable?
2. Show you bookmarks by category (tags)?
3. Find duplicates?
4. Clean up bookmarks that haven't been visited?

User: Let's start by checking which ones are broken

AI: I'll check the reachability of all your bookmarks.

[Uses btk_reachable tool]

AI: The check is complete. Now let me show you the unreachable bookmarks:

[Uses btk_jmespath with query "[?reachable == `false`]"]

AI: Found 12 unreachable bookmarks:
1. ID 45: "Old Blog Post" - http://example-blog.com/...
2. ID 78: "Defunct Service" - https://old-service.io
...

Would you like me to remove these broken bookmarks?
```

## Advanced Usage

### Creating Bookmark Reports

```
User: Can you create a summary of my most used bookmarks?

AI: [Uses btk_jmespath with "[?visit_count > `10`] | sort_by(@, &visit_count) | reverse(@) | [:10]"]

Here are your top 10 most visited bookmarks:
1. "GitHub" - 45 visits
2. "Python Docs" - 38 visits
...
```

### Bookmark Maintenance

```
User: Find bookmarks I added but never actually used

AI: [Uses btk_jmespath with "[?visit_count == `0` && stars == `false`]"]

Found 23 bookmarks that were added but never visited or starred. These might be candidates for removal.
```

### Complex Queries

```
User: Show me programming-related bookmarks I've starred this year

AI: [Uses btk_jmespath with "[?stars == `true` && added >= `2024-01-01` && (contains(tags, 'programming') || contains(tags, 'development') || contains(title, 'code'))]"]
```

## Tips for AI Assistants

When helping users with BTK:

1. **Always confirm the library directory** - Users might have multiple bookmark libraries
2. **Show counts** - When listing results, mention how many bookmarks match
3. **Suggest next actions** - After showing results, suggest logical next steps
4. **Use JMESPath for complex queries** - It's more powerful than basic search
5. **Be careful with destructive operations** - Always confirm before removing bookmarks

## Troubleshooting

### Common Issues

1. **"btk command not found"**
   - Ensure BTK is installed: `pip install bookmark-tk`
   - Check that btk is in your PATH

2. **"Library directory does not exist"**
   - Verify the path to the bookmark library
   - Create it with: `btk import file.html --lib-dir ~/bookmarks`

3. **"Invalid JMESPath query"**
   - Remember to use backticks for literals: `\`true\``, `\`5\``
   - Test queries with: `btk jmespath lib_dir "query" --json`

### Debugging

To see what commands the MCP server is executing, you can:

1. Check the AI assistant's logs
2. Run BTK commands manually to verify they work
3. Use `--json` flag for structured output

## Benefits Over Embedded LLM

1. **No API Keys Required** - BTK doesn't need LLM credentials
2. **Use Any AI** - Works with Claude, GPT, local models, etc.
3. **Better Privacy** - Your bookmarks aren't sent to external APIs
4. **More Flexible** - Each AI can use its own style and capabilities
5. **Easier Testing** - BTK remains a simple CLI tool

## Future Enhancements

Potential improvements to the MCP integration:

1. **Bulk operations** - Add/remove multiple bookmarks at once
2. **Export formats** - Generate reports in various formats
3. **Smart categorization** - Auto-tag bookmarks based on content
4. **Scheduled maintenance** - Regular reachability checks
5. **Bookmark recommendations** - Based on usage patterns