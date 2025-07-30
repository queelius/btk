# BTK Integrations

This directory contains various integrations for the Bookmark Toolkit (BTK) that extend its functionality without bloating the core tool.

## Available Integrations

### mcp-btk
Model Context Protocol (MCP) server that exposes BTK functionality to AI assistants like Claude.

### viz-btk
Visualization tools for creating bookmark graphs, network diagrams, and other visual representations of your bookmark data. Generate interactive HTML graphs, static PNG images, or export graph data as JSON.

## Philosophy

BTK follows the Unix philosophy of doing one thing well. The core `btk` tool focuses on bookmark management operations. These integrations provide additional functionality for specific use cases:

- **mcp-btk**: For AI assistant integration
- **viz-btk**: For data visualization and analysis
- Future integrations could include browser extensions, sync services, etc.

## Structure

Each integration is self-contained with its own:
- README.md with specific documentation
- Dependencies and package management
- Tests
- Examples

This modular approach keeps the core BTK tool lightweight while allowing users to add only the integrations they need.