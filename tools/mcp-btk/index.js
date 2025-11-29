#!/usr/bin/env node

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { exec } from 'child_process';
import { promisify } from 'util';
import path from 'path';
import { fileURLToPath } from 'url';

const execAsync = promisify(exec);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

class BTKServer {
  constructor() {
    this.server = new Server(
      {
        name: 'mcp-btk',
        version: '0.1.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupToolHandlers();
    
    // Error handling
    this.server.onerror = (error) => console.error('[MCP Error]', error);
    process.on('SIGINT', async () => {
      await this.server.close();
      process.exit(0);
    });
  }

  setupToolHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: [
        {
          name: 'btk_search',
          description: 'Search bookmarks by title or URL',
          inputSchema: {
            type: 'object',
            properties: {
              lib_dir: {
                type: 'string',
                description: 'Directory of the bookmark library',
              },
              query: {
                type: 'string',
                description: 'Search query',
              },
            },
            required: ['lib_dir', 'query'],
          },
        },
        {
          name: 'btk_list',
          description: 'List all bookmarks',
          inputSchema: {
            type: 'object',
            properties: {
              lib_dir: {
                type: 'string',
                description: 'Directory of the bookmark library',
              },
            },
            required: ['lib_dir'],
          },
        },
        {
          name: 'btk_add',
          description: 'Add a new bookmark',
          inputSchema: {
            type: 'object',
            properties: {
              lib_dir: {
                type: 'string',
                description: 'Directory of the bookmark library',
              },
              title: {
                type: 'string',
                description: 'Bookmark title',
              },
              url: {
                type: 'string',
                description: 'Bookmark URL',
              },
              tags: {
                type: 'array',
                items: { type: 'string' },
                description: 'Tags for the bookmark',
              },
              description: {
                type: 'string',
                description: 'Bookmark description',
              },
              stars: {
                type: 'boolean',
                description: 'Whether to star the bookmark',
              },
            },
            required: ['lib_dir', 'title', 'url'],
          },
        },
        {
          name: 'btk_remove',
          description: 'Remove a bookmark by ID',
          inputSchema: {
            type: 'object',
            properties: {
              lib_dir: {
                type: 'string',
                description: 'Directory of the bookmark library',
              },
              id: {
                type: 'integer',
                description: 'Bookmark ID',
              },
            },
            required: ['lib_dir', 'id'],
          },
        },
        {
          name: 'btk_jmespath',
          description: 'Query bookmarks using JMESPath',
          inputSchema: {
            type: 'object',
            properties: {
              lib_dir: {
                type: 'string',
                description: 'Directory of the bookmark library',
              },
              query: {
                type: 'string',
                description: 'JMESPath query (e.g., "[?stars == `true`]")',
              },
            },
            required: ['lib_dir', 'query'],
          },
        },
        {
          name: 'btk_visit',
          description: 'Visit a bookmark by ID',
          inputSchema: {
            type: 'object',
            properties: {
              lib_dir: {
                type: 'string',
                description: 'Directory of the bookmark library',
              },
              id: {
                type: 'integer',
                description: 'Bookmark ID',
              },
            },
            required: ['lib_dir', 'id'],
          },
        },
        {
          name: 'btk_reachable',
          description: 'Check reachability of all bookmarks',
          inputSchema: {
            type: 'object',
            properties: {
              lib_dir: {
                type: 'string',
                description: 'Directory of the bookmark library',
              },
            },
            required: ['lib_dir'],
          },
        },
      ],
    }));

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      try {
        let command;
        let useJson = false;

        switch (name) {
          case 'btk_search':
            command = `btk search "${args.lib_dir}" "${args.query}"`;
            break;

          case 'btk_list':
            command = `btk list "${args.lib_dir}"`;
            break;

          case 'btk_add':
            command = `btk add "${args.lib_dir}" --title "${args.title}" --url "${args.url}"`;
            if (args.tags && args.tags.length > 0) {
              command += ` --tags ${args.tags.join(',')}`;
            }
            if (args.description) {
              command += ` --description "${args.description}"`;
            }
            if (args.stars) {
              command += ` --stars`;
            }
            break;

          case 'btk_remove':
            command = `btk remove "${args.lib_dir}" ${args.id}`;
            break;

          case 'btk_jmespath':
            command = `btk jmespath "${args.lib_dir}" '${args.query}' --json`;
            useJson = true;
            break;

          case 'btk_visit':
            command = `btk visit "${args.lib_dir}" ${args.id}`;
            break;

          case 'btk_reachable':
            command = `btk reachable "${args.lib_dir}"`;
            break;

          default:
            throw new Error(`Unknown tool: ${name}`);
        }

        const { stdout, stderr } = await execAsync(command);
        
        let content = stdout || stderr;
        
        // Try to parse as JSON if expected
        if (useJson) {
          try {
            content = JSON.parse(stdout);
          } catch (e) {
            // If not JSON, return as string
          }
        }

        return {
          content: [
            {
              type: 'text',
              text: typeof content === 'string' ? content : JSON.stringify(content, null, 2),
            },
          ],
        };
      } catch (error) {
        return {
          content: [
            {
              type: 'text',
              text: `Error executing BTK command: ${error.message}`,
            },
          ],
          isError: true,
        };
      }
    });
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('BTK MCP server running on stdio');
  }
}

const server = new BTKServer();
server.run().catch(console.error);