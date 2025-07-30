/**
 * Tests for BTK MCP Server
 * 
 * These tests verify that the MCP server correctly exposes BTK functionality
 * and handles various edge cases.
 */

import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

describe('BTK MCP Server', () => {
  let serverProcess;

  beforeEach(() => {
    // Start server process for testing
    serverProcess = spawn('node', [path.join(__dirname, '..', 'index.js')], {
      stdio: ['pipe', 'pipe', 'pipe']
    });
  });

  afterEach(() => {
    // Clean up server process
    if (serverProcess) {
      serverProcess.kill();
    }
  });

  describe('Server Initialization', () => {
    it('should start without errors', (done) => {
      serverProcess.stderr.on('data', (data) => {
        const output = data.toString();
        expect(output).toContain('BTK MCP server running on stdio');
        done();
      });
    });
  });

  describe('Tool Registration', () => {
    it('should register all BTK tools', async () => {
      // Send ListTools request
      const request = {
        jsonrpc: '2.0',
        id: 1,
        method: 'tools/list',
        params: {}
      };

      serverProcess.stdin.write(JSON.stringify(request) + '\n');

      const response = await new Promise((resolve) => {
        serverProcess.stdout.once('data', (data) => {
          resolve(JSON.parse(data.toString()));
        });
      });

      expect(response.result.tools).toHaveLength(7);
      const toolNames = response.result.tools.map(t => t.name);
      expect(toolNames).toContain('btk_search');
      expect(toolNames).toContain('btk_list');
      expect(toolNames).toContain('btk_add');
      expect(toolNames).toContain('btk_remove');
      expect(toolNames).toContain('btk_jmespath');
      expect(toolNames).toContain('btk_visit');
      expect(toolNames).toContain('btk_reachable');
    });
  });

  describe('Tool Execution', () => {
    it('should handle btk_list command', async () => {
      const request = {
        jsonrpc: '2.0',
        id: 2,
        method: 'tools/call',
        params: {
          name: 'btk_list',
          arguments: {
            lib_dir: '/tmp/test-bookmarks'
          }
        }
      };

      serverProcess.stdin.write(JSON.stringify(request) + '\n');

      const response = await new Promise((resolve) => {
        serverProcess.stdout.once('data', (data) => {
          resolve(JSON.parse(data.toString()));
        });
      });

      // Should return a result (even if it's an error for non-existent directory)
      expect(response).toHaveProperty('result');
    });

    it('should handle invalid tool name', async () => {
      const request = {
        jsonrpc: '2.0',
        id: 3,
        method: 'tools/call',
        params: {
          name: 'btk_invalid',
          arguments: {}
        }
      };

      serverProcess.stdin.write(JSON.stringify(request) + '\n');

      const response = await new Promise((resolve) => {
        serverProcess.stdout.once('data', (data) => {
          resolve(JSON.parse(data.toString()));
        });
      });

      expect(response.result.isError).toBe(true);
      expect(response.result.content[0].text).toContain('Unknown tool');
    });
  });
});

describe('BTK Command Integration', () => {
  // These tests would require a test bookmark library to be set up
  // They test the actual BTK command execution through the MCP server
  
  it.todo('should search bookmarks successfully');
  it.todo('should add a new bookmark');
  it.todo('should remove a bookmark');
  it.todo('should execute JMESPath queries');
  it.todo('should handle reachability checks');
});