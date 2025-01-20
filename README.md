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

- **cloud**: Generate a URL mention graph from bookmarks.
  ```sh
  btk cloud mybookmarks --output graph.png
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

- **llm**: Use a large language model (LLM) to automatically generate appropriate queries from natural language prompts.
  ```sh
  btk llm mybookmarks "Find bookmarks that are starred and have a visit count greater than 0."
  ```

  Or, more complex:
  ```sh
  btk llm bookmarks "search for bookmarks with chatgpt in the title and has been visited at least once or it also has awesome in the title in addition to chatgpt. or, finally, it was added after 2022"
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



## License

This project is licensed under the MIT License.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue if you have suggestions or improvements.

## Author

Developed by [Alex Towell](https://github.com/queelius).

