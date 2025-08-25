"""
BTK REPL (Read-Eval-Print Loop) implementation.

This module provides an interactive shell for BTK with support for:
- Command history and completion
- Context awareness (current library)
- Embeddable design for web interfaces
"""

import os
import sys
import json
import readline
import atexit
import shlex
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
import traceback
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from . import utils
from . import tools
from . import browser_import
from . import collections
from . import merge
from . import tag_utils
from . import bulk_ops

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """Types of REPL commands."""
    BUILTIN = "builtin"      # REPL built-in commands
    BTK = "btk"              # BTK operations
    SHELL = "shell"          # Shell pass-through
    PYTHON = "python"        # Python evaluation


@dataclass
class ReplContext:
    """Context for the REPL session."""
    current_lib: Optional[str] = None
    current_collection: Optional[str] = None  # Current collection within a set
    collection_set: Optional[collections.CollectionSet] = None
    last_result: Any = None
    variables: Dict[str, Any] = None
    history_file: str = None
    
    def __post_init__(self):
        if self.variables is None:
            self.variables = {}
        if self.history_file is None:
            self.history_file = str(Path.home() / ".btk_repl_history")


class CommandResult:
    """Result of a REPL command execution."""
    
    def __init__(self, success: bool, output: Any = None, 
                 error: str = None, should_exit: bool = False):
        self.success = success
        self.output = output
        self.error = error
        self.should_exit = should_exit


class BtkReplCore:
    """
    Core REPL logic that can be embedded in different interfaces.
    
    This class handles command parsing and execution but not the I/O,
    making it suitable for embedding in web interfaces.
    """
    
    def __init__(self, initial_lib: Optional[str] = None):
        """
        Initialize the REPL core.
        
        Args:
            initial_lib: Initial library directory to use
        """
        self.context = ReplContext(current_lib=initial_lib)
        self.console = Console()
        
        # Command registry
        self.commands: Dict[str, Callable] = {
            # Built-in commands
            "help": self.cmd_help,
            "exit": self.cmd_exit,
            "quit": self.cmd_exit,
            "cd": self.cmd_cd,
            "pwd": self.cmd_pwd,
            "use": self.cmd_use,
            "info": self.cmd_info,
            "clear": self.cmd_clear,
            "set": self.cmd_set,
            "get": self.cmd_get,
            
            # BTK commands
            "list": self.cmd_list,
            "search": self.cmd_search,
            "add": self.cmd_add,
            "remove": self.cmd_remove,
            "edit": self.cmd_edit,
            "tag": self.cmd_tag,
            "star": self.cmd_star,
            "export": self.cmd_export,
            "import": self.cmd_import,
            "stats": self.cmd_stats,
            "dedupe": self.cmd_dedupe,
            "merge": self.cmd_merge,
            
            # Collection commands
            "collections": self.cmd_collections,
            "collection": self.cmd_collection,
            "discover": self.cmd_discover,
            "switch": self.cmd_switch,
            "search-all": self.cmd_search_all,
        }
        
        # Command aliases
        self.aliases = {
            "ls": "list",
            "find": "search",
            "rm": "remove",
            "del": "remove",
            "q": "quit",
            "?": "help",
        }
    
    def execute_command(self, command_line: str) -> CommandResult:
        """
        Execute a command and return the result.
        
        This is the main entry point for embedded use.
        
        Args:
            command_line: The command line to execute
            
        Returns:
            CommandResult with output or error
        """
        try:
            # Strip and check for empty
            command_line = command_line.strip()
            if not command_line:
                return CommandResult(True)
            
            # Check for special prefixes
            if command_line.startswith('!'):
                # Shell command
                return self._execute_shell(command_line[1:])
            elif command_line.startswith('$'):
                # Python expression
                return self._execute_python(command_line[1:])
            
            # Parse command and arguments
            parts = shlex.split(command_line)
            if not parts:
                return CommandResult(True)
            
            command = parts[0].lower()
            args = parts[1:]
            
            # Resolve aliases
            command = self.aliases.get(command, command)
            
            # Execute command
            if command in self.commands:
                return self.commands[command](args)
            else:
                # Try as BTK operation
                return self._execute_btk_operation(command, args)
                
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def _execute_shell(self, command: str) -> CommandResult:
        """Execute a shell command."""
        try:
            import subprocess
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            return CommandResult(result.returncode == 0, output=output)
        except Exception as e:
            return CommandResult(False, error=f"Shell error: {e}")
    
    def _execute_python(self, expression: str) -> CommandResult:
        """Execute a Python expression."""
        try:
            # Provide context variables
            local_vars = {
                'context': self.context,
                'lib': self.context.current_lib,
                'last': self.context.last_result,
                **self.context.variables
            }
            
            # Try as expression first
            try:
                result = eval(expression, globals(), local_vars)
                self.context.last_result = result
                return CommandResult(True, output=result)
            except SyntaxError:
                # Try as statement
                exec(expression, globals(), local_vars)
                return CommandResult(True)
                
        except Exception as e:
            return CommandResult(False, error=f"Python error: {e}")
    
    def _execute_btk_operation(self, operation: str, args: List[str]) -> CommandResult:
        """Execute a BTK operation that's not a built-in command."""
        return CommandResult(False, error=f"Unknown command: {operation}")
    
    # Built-in commands
    
    def cmd_help(self, args: List[str]) -> CommandResult:
        """Show help information."""
        help_text = """
BTK REPL Commands:

Built-in Commands:
  help, ?         Show this help
  exit, quit, q   Exit the REPL
  use <dir>       Set current library directory
  pwd             Show current context (library/collections)
  info            Show library information
  clear           Clear screen
  set <var> <val> Set a variable
  get <var>       Get a variable value

BTK Operations:
  list [filter]   List bookmarks in current library
  search <query>  Search bookmarks in current library
  add <url>       Add a bookmark
  remove <id>     Remove a bookmark
  edit <id>       Edit a bookmark
  tag <id> <tags> Add tags to bookmark
  star <id>       Star/unstar bookmark
  export <format> Export bookmarks
  import <file>   Import bookmarks
  stats           Show statistics
  dedupe          Find duplicates
  merge <libs>    Merge libraries

Collection Operations:
  discover <dir>  Discover and load collections from directory
  collections     List active collections
  collection <n>  Switch to collection or show current
  switch <name>   Switch to collection (alias)
  search-all <q>  Search across all collections
  
  collections create <path>  Create new collection
  collections merge <names...> <op>  Merge collections

Special Prefixes:
  !<command>      Execute shell command
  $<expression>   Evaluate Python expression

Examples - Single Library:
  use ~/bookmarks
  search python
  add https://example.com
  tag 1 programming,tutorial

Examples - Collections:
  discover ~/my-collections
  collections                    # List all collections
  switch work                    # Switch to 'work' collection
  search-all python              # Search all collections
  collections merge personal work union

Python Integration:
  $len(context.last_result)      # Count last search results
  $[b['url'] for b in context.last_result[:5]]
"""
        return CommandResult(True, output=help_text)
    
    def cmd_exit(self, args: List[str]) -> CommandResult:
        """Exit the REPL."""
        return CommandResult(True, should_exit=True)
    
    def cmd_use(self, args: List[str]) -> CommandResult:
        """Set the current library directory."""
        if not args:
            return CommandResult(False, error="Usage: use <directory>")
        
        lib_dir = os.path.expanduser(args[0])
        if not os.path.exists(lib_dir):
            # Create if doesn't exist
            try:
                os.makedirs(lib_dir, exist_ok=True)
                # Initialize as BTK library
                utils.ensure_dir(lib_dir)
                utils.save_bookmarks([], None, lib_dir)
                self.context.current_lib = lib_dir
                return CommandResult(True, output=f"Created and using library: {lib_dir}")
            except Exception as e:
                return CommandResult(False, error=f"Failed to create library: {e}")
        else:
            self.context.current_lib = lib_dir
            return CommandResult(True, output=f"Using library: {lib_dir}")
    
    def cmd_pwd(self, args: List[str]) -> CommandResult:
        """Show current library directory."""
        output = []
        
        if self.context.current_lib:
            output.append(f"Current library: {self.context.current_lib}")
        
        if self.context.collection_set:
            output.append(f"Collection set active with {len(self.context.collection_set.collections)} collections")
            if self.context.current_collection:
                output.append(f"Current collection: {self.context.current_collection}")
        
        if not output:
            return CommandResult(True, output="No library selected. Use 'use <dir>' or 'discover <dir>' to start.")
        
        return CommandResult(True, output='\n'.join(output))
    
    def cmd_cd(self, args: List[str]) -> CommandResult:
        """Change directory (alias for use)."""
        return self.cmd_use(args)
    
    def cmd_info(self, args: List[str]) -> CommandResult:
        """Show information about the current library."""
        if not self.context.current_lib:
            return CommandResult(False, error="No library selected")
        
        try:
            bookmarks = utils.load_bookmarks(self.context.current_lib)
            
            # Calculate statistics
            total = len(bookmarks)
            starred = sum(1 for b in bookmarks if b.get('stars'))
            
            # Count tags
            all_tags = []
            for b in bookmarks:
                all_tags.extend(b.get('tags', []))
            unique_tags = len(set(all_tags))
            
            info = f"""
Library: {self.context.current_lib}
Total bookmarks: {total}
Starred: {starred}
Unique tags: {unique_tags}
"""
            return CommandResult(True, output=info)
            
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_clear(self, args: List[str]) -> CommandResult:
        """Clear the screen."""
        os.system('clear' if os.name == 'posix' else 'cls')
        return CommandResult(True)
    
    def cmd_set(self, args: List[str]) -> CommandResult:
        """Set a variable."""
        if len(args) < 2:
            return CommandResult(False, error="Usage: set <variable> <value>")
        
        var_name = args[0]
        var_value = ' '.join(args[1:])
        
        # Try to parse as JSON
        try:
            var_value = json.loads(var_value)
        except:
            pass  # Keep as string
        
        self.context.variables[var_name] = var_value
        return CommandResult(True, output=f"Set {var_name} = {var_value}")
    
    def cmd_get(self, args: List[str]) -> CommandResult:
        """Get a variable value."""
        if not args:
            # Show all variables
            return CommandResult(True, output=self.context.variables)
        
        var_name = args[0]
        if var_name in self.context.variables:
            return CommandResult(True, output=self.context.variables[var_name])
        else:
            return CommandResult(False, error=f"Variable '{var_name}' not found")
    
    # BTK commands
    
    def cmd_list(self, args: List[str]) -> CommandResult:
        """List bookmarks."""
        if not self.context.current_lib:
            return CommandResult(False, error="No library selected")
        
        try:
            bookmarks = utils.load_bookmarks(self.context.current_lib)
            
            # Apply filter if provided
            if args:
                filter_str = ' '.join(args)
                # Simple tag filter
                if filter_str.startswith('tag:'):
                    tag = filter_str[4:]
                    bookmarks = [b for b in bookmarks if tag in b.get('tags', [])]
                elif filter_str == 'starred':
                    bookmarks = [b for b in bookmarks if b.get('stars')]
            
            # Store in context for further processing
            self.context.last_result = bookmarks
            
            # Format output
            if not bookmarks:
                return CommandResult(True, output="No bookmarks found")
            
            # Create a simple listing
            output = []
            for i, b in enumerate(bookmarks[:20]):  # Limit to 20 for REPL
                stars = "★" if b.get('stars') else " "
                output.append(f"{stars} [{b.get('id', i)}] {b.get('title', 'Untitled')} - {b.get('url', '')}")
            
            if len(bookmarks) > 20:
                output.append(f"\n... and {len(bookmarks) - 20} more")
            
            return CommandResult(True, output='\n'.join(output))
            
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_search(self, args: List[str]) -> CommandResult:
        """Search bookmarks."""
        if not self.context.current_lib:
            return CommandResult(False, error="No library selected")
        
        if not args:
            return CommandResult(False, error="Usage: search <query>")
        
        try:
            bookmarks = utils.load_bookmarks(self.context.current_lib)
            query = ' '.join(args)
            
            results = tools.search_bookmarks(bookmarks, query)
            self.context.last_result = results
            
            if not results:
                return CommandResult(True, output="No matches found")
            
            # Format output
            output = [f"Found {len(results)} matches:\n"]
            for i, b in enumerate(results[:10]):
                stars = "★" if b.get('stars') else " "
                output.append(f"{stars} [{b.get('id', i)}] {b.get('title', 'Untitled')} - {b.get('url', '')}")
            
            if len(results) > 10:
                output.append(f"\n... and {len(results) - 10} more")
            
            return CommandResult(True, output='\n'.join(output))
            
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_add(self, args: List[str]) -> CommandResult:
        """Add a bookmark."""
        if not self.context.current_lib:
            return CommandResult(False, error="No library selected")
        
        if not args:
            return CommandResult(False, error="Usage: add <url> [title]")
        
        try:
            url = args[0]
            title = ' '.join(args[1:]) if len(args) > 1 else url
            
            bookmarks = utils.load_bookmarks(self.context.current_lib)
            
            # Check for duplicates
            if any(b.get('url') == url for b in bookmarks):
                return CommandResult(False, error=f"URL already exists: {url}")
            
            # Create new bookmark
            new_bookmark = {
                'id': utils.get_next_id(bookmarks),
                'unique_id': utils.generate_unique_id(url, title),
                'url': url,
                'title': title,
                'tags': [],
                'stars': False,
                'visit_count': 0,
                'added': utils.datetime.now(utils.timezone.utc).isoformat()
            }
            
            bookmarks.append(new_bookmark)
            utils.save_bookmarks(bookmarks, None, self.context.current_lib)
            
            return CommandResult(True, output=f"Added bookmark #{new_bookmark['id']}: {title}")
            
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_remove(self, args: List[str]) -> CommandResult:
        """Remove a bookmark."""
        if not self.context.current_lib:
            return CommandResult(False, error="No library selected")
        
        if not args:
            return CommandResult(False, error="Usage: remove <id>")
        
        try:
            bookmark_id = int(args[0])
            bookmarks = utils.load_bookmarks(self.context.current_lib)
            
            # Find and remove
            original_count = len(bookmarks)
            bookmarks = [b for b in bookmarks if b.get('id') != bookmark_id]
            
            if len(bookmarks) == original_count:
                return CommandResult(False, error=f"Bookmark #{bookmark_id} not found")
            
            utils.save_bookmarks(bookmarks, None, self.context.current_lib)
            return CommandResult(True, output=f"Removed bookmark #{bookmark_id}")
            
        except ValueError:
            return CommandResult(False, error="Invalid bookmark ID")
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_edit(self, args: List[str]) -> CommandResult:
        """Edit a bookmark."""
        if not self.context.current_lib:
            return CommandResult(False, error="No library selected")
        
        if len(args) < 3:
            return CommandResult(False, error="Usage: edit <id> <field> <value>")
        
        try:
            bookmark_id = int(args[0])
            field = args[1]
            value = ' '.join(args[2:])
            
            bookmarks = utils.load_bookmarks(self.context.current_lib)
            
            # Find bookmark
            bookmark = None
            for b in bookmarks:
                if b.get('id') == bookmark_id:
                    bookmark = b
                    break
            
            if not bookmark:
                return CommandResult(False, error=f"Bookmark #{bookmark_id} not found")
            
            # Update field
            if field == 'tags':
                bookmark['tags'] = [t.strip() for t in value.split(',')]
            elif field == 'stars':
                bookmark['stars'] = value.lower() in ('true', '1', 'yes')
            elif field in ('title', 'url', 'description'):
                bookmark[field] = value
            else:
                return CommandResult(False, error=f"Unknown field: {field}")
            
            utils.save_bookmarks(bookmarks, None, self.context.current_lib)
            return CommandResult(True, output=f"Updated bookmark #{bookmark_id}")
            
        except ValueError:
            return CommandResult(False, error="Invalid bookmark ID")
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_tag(self, args: List[str]) -> CommandResult:
        """Add tags to a bookmark."""
        if not self.context.current_lib:
            return CommandResult(False, error="No library selected")
        
        if len(args) < 2:
            return CommandResult(False, error="Usage: tag <id> <tags>")
        
        try:
            bookmark_id = int(args[0])
            new_tags = [t.strip() for t in ' '.join(args[1:]).split(',')]
            
            bookmarks = utils.load_bookmarks(self.context.current_lib)
            
            # Find bookmark
            bookmark = None
            for b in bookmarks:
                if b.get('id') == bookmark_id:
                    bookmark = b
                    break
            
            if not bookmark:
                return CommandResult(False, error=f"Bookmark #{bookmark_id} not found")
            
            # Add tags
            existing_tags = set(bookmark.get('tags', []))
            existing_tags.update(new_tags)
            bookmark['tags'] = list(existing_tags)
            
            utils.save_bookmarks(bookmarks, None, self.context.current_lib)
            return CommandResult(True, output=f"Added tags to bookmark #{bookmark_id}")
            
        except ValueError:
            return CommandResult(False, error="Invalid bookmark ID")
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_star(self, args: List[str]) -> CommandResult:
        """Star or unstar a bookmark."""
        if not self.context.current_lib:
            return CommandResult(False, error="No library selected")
        
        if not args:
            return CommandResult(False, error="Usage: star <id>")
        
        try:
            bookmark_id = int(args[0])
            bookmarks = utils.load_bookmarks(self.context.current_lib)
            
            # Find bookmark
            bookmark = None
            for b in bookmarks:
                if b.get('id') == bookmark_id:
                    bookmark = b
                    break
            
            if not bookmark:
                return CommandResult(False, error=f"Bookmark #{bookmark_id} not found")
            
            # Toggle star
            bookmark['stars'] = not bookmark.get('stars', False)
            
            utils.save_bookmarks(bookmarks, None, self.context.current_lib)
            status = "Starred" if bookmark['stars'] else "Unstarred"
            return CommandResult(True, output=f"{status} bookmark #{bookmark_id}")
            
        except ValueError:
            return CommandResult(False, error="Invalid bookmark ID")
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_export(self, args: List[str]) -> CommandResult:
        """Export bookmarks."""
        if not self.context.current_lib:
            return CommandResult(False, error="No library selected")
        
        if not args:
            return CommandResult(False, error="Usage: export <format> [file]")
        
        format_type = args[0]
        output_file = args[1] if len(args) > 1 else f"bookmarks.{format_type}"
        
        try:
            bookmarks = utils.load_bookmarks(self.context.current_lib)
            
            if format_type == 'json':
                tools.export_bookmarks_json(bookmarks, output_file)
            elif format_type == 'html':
                tools.export_bookmarks_html(bookmarks, output_file)
            elif format_type == 'csv':
                tools.export_bookmarks_csv(bookmarks, output_file)
            elif format_type == 'markdown':
                tools.export_bookmarks_markdown(bookmarks, output_file)
            else:
                return CommandResult(False, error=f"Unknown format: {format_type}")
            
            return CommandResult(True, output=f"Exported to {output_file}")
            
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_import(self, args: List[str]) -> CommandResult:
        """Import bookmarks."""
        if not self.context.current_lib:
            return CommandResult(False, error="No library selected")
        
        if not args:
            return CommandResult(False, error="Usage: import <file>")
        
        import_file = args[0]
        
        try:
            bookmarks = utils.load_bookmarks(self.context.current_lib)
            
            # Determine format from extension
            if import_file.endswith('.json'):
                bookmarks = tools.import_bookmarks_json(import_file, bookmarks, self.context.current_lib)
            elif import_file.endswith('.html'):
                bookmarks = tools.import_bookmarks(import_file, bookmarks, self.context.current_lib)
            elif import_file.endswith('.csv'):
                bookmarks = tools.import_bookmarks_csv(import_file, bookmarks, self.context.current_lib)
            else:
                return CommandResult(False, error="Unknown file format")
            
            utils.save_bookmarks(bookmarks, None, self.context.current_lib)
            return CommandResult(True, output=f"Imported from {import_file}")
            
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_stats(self, args: List[str]) -> CommandResult:
        """Show library statistics."""
        if not self.context.current_lib:
            return CommandResult(False, error="No library selected")
        
        try:
            bookmarks = utils.load_bookmarks(self.context.current_lib)
            
            # Calculate stats
            total = len(bookmarks)
            starred = sum(1 for b in bookmarks if b.get('stars'))
            
            # Tag stats
            tag_counts = {}
            for b in bookmarks:
                for tag in b.get('tags', []):
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            
            # Visit stats
            total_visits = sum(b.get('visit_count', 0) for b in bookmarks)
            
            output = f"""
Statistics for {self.context.current_lib}:

Total bookmarks: {total}
Starred: {starred}
Total visits: {total_visits}
Unique tags: {len(tag_counts)}

Top 5 tags:
"""
            for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                output += f"  {tag}: {count}\n"
            
            return CommandResult(True, output=output)
            
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_dedupe(self, args: List[str]) -> CommandResult:
        """Find duplicate bookmarks."""
        if not self.context.current_lib:
            return CommandResult(False, error="No library selected")
        
        try:
            from .dedup import find_duplicates
            
            bookmarks = utils.load_bookmarks(self.context.current_lib)
            duplicates = find_duplicates(bookmarks)
            
            if not duplicates:
                return CommandResult(True, output="No duplicates found")
            
            output = [f"Found {len(duplicates)} duplicate groups:\n"]
            for i, group in enumerate(duplicates[:5], 1):
                output.append(f"Group {i} ({len(group)} duplicates):")
                for b in group:
                    output.append(f"  [{b.get('id')}] {b.get('title')} - {b.get('url')}")
                output.append("")
            
            if len(duplicates) > 5:
                output.append(f"... and {len(duplicates) - 5} more groups")
            
            self.context.last_result = duplicates
            return CommandResult(True, output='\n'.join(output))
            
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_merge(self, args: List[str]) -> CommandResult:
        """Merge bookmark libraries."""
        if len(args) < 2:
            return CommandResult(False, error="Usage: merge <lib1> <lib2> [operation]")
        
        lib1 = os.path.expanduser(args[0])
        lib2 = os.path.expanduser(args[1])
        operation = args[2] if len(args) > 2 else 'union'
        
        try:
            # Use current lib as output if set
            output_dir = self.context.current_lib or '/tmp/merged_bookmarks'
            
            if operation == 'union':
                merge.union_libraries([lib1, lib2], output_dir)
            elif operation == 'intersection':
                merge.intersection_libraries([lib1, lib2], output_dir)
            elif operation == 'difference':
                merge.difference_libraries([lib1, lib2], output_dir)
            else:
                return CommandResult(False, error=f"Unknown operation: {operation}")
            
            if not self.context.current_lib:
                self.context.current_lib = output_dir
            
            return CommandResult(True, output=f"Merged libraries to {output_dir}")
            
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_collections(self, args: List[str]) -> CommandResult:
        """Manage bookmark collections."""
        if not args:
            # Show current collections if set is active
            if self.context.collection_set:
                output = ["Active collections:\n"]
                for name, coll in self.context.collection_set.collections.items():
                    stats = coll.get_stats()
                    is_current = " [current]" if name == self.context.current_collection else ""
                    output.append(f"  {name}: {stats['total_bookmarks']} bookmarks{is_current}")
                return CommandResult(True, output='\n'.join(output))
            else:
                return CommandResult(False, error="No collection set active. Use 'discover <path>' to find collections.")
        
        subcommand = args[0]
        
        try:
            if subcommand == 'list':
                # List collections in current directory or specified path
                search_path = args[1] if len(args) > 1 else os.getcwd()
                collection_set = collections.CollectionSet()
                collection_set.discover_collections(search_path)
                
                if not collection_set.collections:
                    return CommandResult(True, output="No collections found")
                
                output = ["Found collections:\n"]
                for name, coll in collection_set.collections.items():
                    stats = coll.get_stats()
                    output.append(f"  {name}: {stats['total_bookmarks']} bookmarks")
                
                return CommandResult(True, output='\n'.join(output))
                
            elif subcommand == 'create':
                if len(args) < 2:
                    return CommandResult(False, error="Usage: collections create <path>")
                
                path = os.path.expanduser(args[1])
                coll = collections.BookmarkCollection(path)
                
                # Add to current set if active
                if self.context.collection_set:
                    name = Path(path).name
                    self.context.collection_set.add_collection(str(path), name)
                    return CommandResult(True, output=f"Created and added collection '{name}'")
                
                return CommandResult(True, output=f"Created collection at {path}")
                
            elif subcommand == 'merge':
                if len(args) < 3:
                    return CommandResult(False, error="Usage: collections merge <names...> <operation>")
                
                if not self.context.collection_set:
                    return CommandResult(False, error="No collection set active")
                
                # Parse arguments
                operation = args[-1] if args[-1] in ['union', 'intersection', 'difference'] else 'union'
                names = args[1:-1] if args[-1] in ['union', 'intersection', 'difference'] else args[1:]
                
                # Perform merge
                target_path = f"/tmp/merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                merged = self.context.collection_set.merge_collections(
                    names, target_path, operation
                )
                
                return CommandResult(True, output=f"Merged {len(names)} collections ({operation}) to '{merged.info.name}'")
                
            else:
                return CommandResult(False, error=f"Unknown subcommand: {subcommand}")
                
        except Exception as e:
            return CommandResult(False, error=str(e))
    
    def cmd_collection(self, args: List[str]) -> CommandResult:
        """Show or switch to a specific collection."""
        if not self.context.collection_set:
            return CommandResult(False, error="No collection set active. Use 'discover <path>' first.")
        
        if not args:
            # Show current collection
            if self.context.current_collection:
                coll = self.context.collection_set.get_collection(self.context.current_collection)
                if coll:
                    stats = coll.get_stats()
                    return CommandResult(True, output=f"Current collection: {self.context.current_collection}\n"
                                                     f"Bookmarks: {stats['total_bookmarks']}\n"
                                                     f"Path: {coll.path}")
            return CommandResult(True, output="No collection selected. Use 'collection <name>' to switch.")
        
        # Switch to collection
        name = args[0]
        if name not in self.context.collection_set.collections:
            return CommandResult(False, error=f"Collection '{name}' not found")
        
        self.context.current_collection = name
        coll = self.context.collection_set.get_collection(name)
        self.context.current_lib = str(coll.path)  # Update current lib for compatibility
        
        stats = coll.get_stats()
        return CommandResult(True, output=f"Switched to collection '{name}' ({stats['total_bookmarks']} bookmarks)")
    
    def cmd_discover(self, args: List[str]) -> CommandResult:
        """Discover and load collections from a directory."""
        if not args:
            return CommandResult(False, error="Usage: discover <directory>")
        
        search_path = os.path.expanduser(args[0])
        if not os.path.exists(search_path):
            return CommandResult(False, error=f"Path does not exist: {search_path}")
        
        # Create collection set and discover
        self.context.collection_set = collections.CollectionSet()
        self.context.collection_set.discover_collections(search_path, recursive=True)
        
        if not self.context.collection_set.collections:
            return CommandResult(True, output=f"No collections found in {search_path}")
        
        output = [f"Discovered {len(self.context.collection_set.collections)} collections:\n"]
        for name, coll in self.context.collection_set.collections.items():
            stats = coll.get_stats()
            output.append(f"  {name}: {stats['total_bookmarks']} bookmarks")
        
        # Auto-select first collection if only one
        if len(self.context.collection_set.collections) == 1:
            name = list(self.context.collection_set.collections.keys())[0]
            self.context.current_collection = name
            coll = self.context.collection_set.get_collection(name)
            self.context.current_lib = str(coll.path)
            output.append(f"\nAuto-selected collection '{name}'")
        
        return CommandResult(True, output='\n'.join(output))
    
    def cmd_switch(self, args: List[str]) -> CommandResult:
        """Switch to a different collection (alias for collection)."""
        return self.cmd_collection(args)
    
    def cmd_search_all(self, args: List[str]) -> CommandResult:
        """Search across all collections."""
        if not self.context.collection_set:
            return CommandResult(False, error="No collection set active. Use 'discover <path>' first.")
        
        if not args:
            return CommandResult(False, error="Usage: search-all <query>")
        
        query = ' '.join(args)
        results = self.context.collection_set.search_all(query)
        
        if not results:
            return CommandResult(True, output="No matches found in any collection")
        
        output = [f"Found matches in {len(results)} collections:\n"]
        total_matches = 0
        
        for coll_name, matches in results.items():
            output.append(f"\n{coll_name} ({len(matches)} matches):")
            for b in matches[:3]:  # Show first 3 from each collection
                stars = "★" if b.get('stars') else " "
                output.append(f"  {stars} [{b.get('id')}] {b.get('title', 'Untitled')}")
            if len(matches) > 3:
                output.append(f"  ... and {len(matches) - 3} more")
            total_matches += len(matches)
        
        output.append(f"\nTotal: {total_matches} matches across all collections")
        self.context.last_result = results
        
        return CommandResult(True, output='\n'.join(output))


class BtkRepl:
    """
    Interactive REPL for BTK with prompt_toolkit interface.
    """
    
    def __init__(self, initial_lib: Optional[str] = None):
        """
        Initialize the REPL.
        
        Args:
            initial_lib: Initial library directory to use
        """
        self.core = BtkReplCore(initial_lib)
        self.session = None
        self._setup_prompt()
    
    def _setup_prompt(self):
        """Set up the prompt_toolkit session."""
        # Command completer
        commands = list(self.core.commands.keys()) + list(self.core.aliases.keys())
        completer = WordCompleter(commands, ignore_case=True)
        
        # Style
        style = Style.from_dict({
            'prompt': '#00aa00 bold',
            'lib': '#0088ff',
        })
        
        # History
        history = FileHistory(self.core.context.history_file)
        
        # Create session
        self.session = PromptSession(
            completer=completer,
            history=history,
            style=style,
            enable_history_search=True,
        )
    
    def get_prompt(self) -> List[Tuple[str, str]]:
        """Generate the prompt with current context."""
        prompt_parts = []
        
        if self.core.context.current_lib:
            lib_name = os.path.basename(self.core.context.current_lib)
            prompt_parts.append(('class:lib', f"[{lib_name}]"))
        
        prompt_parts.append(('class:prompt', 'btk> '))
        
        return prompt_parts
    
    def run(self):
        """Run the interactive REPL."""
        # Print welcome message
        console = Console()
        console.print(Panel.fit(
            "[bold cyan]BTK Interactive REPL[/bold cyan]\n"
            "Type 'help' for commands, 'exit' to quit",
            border_style="cyan"
        ))
        
        # Main loop
        while True:
            try:
                # Get input
                prompt = self.get_prompt()
                command_line = self.session.prompt(prompt)
                
                # Execute command
                result = self.core.execute_command(command_line)
                
                # Handle result
                if result.should_exit:
                    console.print("[yellow]Goodbye![/yellow]")
                    break
                
                if result.output is not None:
                    # Format output based on type
                    if isinstance(result.output, str):
                        console.print(result.output)
                    elif isinstance(result.output, (dict, list)):
                        console.print(Syntax(
                            json.dumps(result.output, indent=2),
                            "json",
                            theme="monokai"
                        ))
                    else:
                        console.print(str(result.output))
                
                if result.error:
                    console.print(f"[red]Error: {result.error}[/red]")
                    
            except KeyboardInterrupt:
                console.print("\n[yellow]Use 'exit' to quit[/yellow]")
            except EOFError:
                console.print("\n[yellow]Goodbye![/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Unexpected error: {e}[/red]")
                console.print(traceback.format_exc())


# WebSocket handler for embedded REPL
class WebSocketReplHandler:
    """
    Handler for WebSocket-based REPL communication.
    
    This can be used to embed the REPL in a web interface.
    """
    
    def __init__(self, initial_lib: Optional[str] = None):
        """Initialize the WebSocket REPL handler."""
        self.core = BtkReplCore(initial_lib)
    
    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a WebSocket message.
        
        Args:
            message: Incoming message with 'type' and 'data' fields
            
        Returns:
            Response message with 'type', 'success', and 'data' fields
        """
        msg_type = message.get('type')
        data = message.get('data', {})
        
        if msg_type == 'execute':
            # Execute a command
            command_line = data.get('command', '')
            result = self.core.execute_command(command_line)
            
            return {
                'type': 'result',
                'success': result.success,
                'data': {
                    'output': result.output,
                    'error': result.error,
                    'should_exit': result.should_exit,
                }
            }
        
        elif msg_type == 'get_context':
            # Get current context
            return {
                'type': 'context',
                'success': True,
                'data': {
                    'current_lib': self.core.context.current_lib,
                    'variables': self.core.context.variables,
                }
            }
        
        elif msg_type == 'set_lib':
            # Set current library
            lib_dir = data.get('lib_dir')
            result = self.core.cmd_use([lib_dir])
            
            return {
                'type': 'result',
                'success': result.success,
                'data': {
                    'output': result.output,
                    'error': result.error,
                }
            }
        
        else:
            return {
                'type': 'error',
                'success': False,
                'data': {
                    'error': f"Unknown message type: {msg_type}"
                }
            }


def run_repl(initial_lib: Optional[str] = None):
    """
    Run the BTK REPL.
    
    Args:
        initial_lib: Initial library directory to use
    """
    repl = BtkRepl(initial_lib)
    repl.run()


if __name__ == "__main__":
    # Run REPL when module is executed directly
    import argparse
    
    parser = argparse.ArgumentParser(description="BTK Interactive REPL")
    parser.add_argument('--lib', type=str, help="Initial library directory")
    args = parser.parse_args()
    
    run_repl(args.lib)