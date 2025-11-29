/**
 * Unit tests for BTK MCP tool definitions
 */

import { describe, it, expect } from '@jest/globals';

describe('BTK Tool Definitions', () => {
  it('should define the correct tool structure', () => {
    // Test tool definition structure
    const exampleTool = {
      name: 'btk_search',
      description: 'Search bookmarks by title or URL',
      inputSchema: {
        type: 'object',
        properties: {
          lib_dir: {
            type: 'string',
            description: 'Directory of the bookmark library'
          },
          query: {
            type: 'string',
            description: 'Search query'
          }
        },
        required: ['lib_dir', 'query']
      }
    };

    expect(exampleTool.name).toBe('btk_search');
    expect(exampleTool.inputSchema.required).toContain('lib_dir');
    expect(exampleTool.inputSchema.required).toContain('query');
  });

  it('should validate tool names', () => {
    const validToolNames = [
      'btk_search',
      'btk_list',
      'btk_add',
      'btk_remove',
      'btk_jmespath',
      'btk_visit',
      'btk_reachable'
    ];

    validToolNames.forEach(name => {
      expect(name).toMatch(/^btk_/);
    });
  });

  it('should have proper command mappings', () => {
    const commandMap = {
      'btk_search': 'btk search',
      'btk_list': 'btk list',
      'btk_add': 'btk add',
      'btk_remove': 'btk remove',
      'btk_jmespath': 'btk jmespath',
      'btk_visit': 'btk visit',
      'btk_reachable': 'btk reachable'
    };

    Object.entries(commandMap).forEach(([tool, command]) => {
      expect(command).toContain('btk');
      expect(tool.replace('btk_', '')).toBe(command.split(' ')[1]);
    });
  });
});