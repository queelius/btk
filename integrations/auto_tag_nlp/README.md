# NLP-Based Auto-Tagging Integration

Classical NLP tag suggestion using TF-IDF and pattern matching. No external dependencies, fast and lightweight.

## Features

- **TF-IDF Term Extraction**: Identifies important terms
- **Technology Recognition**: Detects languages, frameworks, databases
- **Domain-Based Tags**: Platform and content type detection
- **Hierarchical Tags**: Generates organized tag hierarchies
- **Zero Dependencies**: Uses only Python standard library
- **Fast Performance**: <100ms per bookmark

## Installation

No dependencies required - uses Python standard library only.

## Usage

### As a BTK Plugin

```python
from btk.plugins import PluginRegistry

registry = PluginRegistry()
registry.discover_plugins()

nlp_tagger = registry.get_plugin('nlp_tagger', 'tag_suggester')

tags = nlp_tagger.suggest_tags(
    url="https://docs.djangoproject.com/",
    title="Django Documentation",
    description="Web framework for Python",
    content="Django is a high-level Python web framework..."
)

print(tags)
# ['framework/django', 'programming/python', 'content/documentation', 'framework', 'programming', ...]
```

### Standalone Usage

```python
from integrations.auto_tag_nlp.nlp_tagger import NLPTagSuggester

tagger = NLPTagSuggester()

tags = tagger.suggest_tags(
    url="https://reactjs.org/tutorial/",
    title="React Tutorial",
    description="Learn React",
    content="React is a JavaScript library..."
)
```

## How It Works

1. **TF-IDF Scoring**: Calculates term importance using pre-computed IDF scores
2. **Pattern Matching**: Regex patterns detect technologies, languages, frameworks
3. **Domain Analysis**: Extracts platform tags from URL domains
4. **Content Type Detection**: Identifies tutorials, documentation, videos, etc.
5. **Hierarchical Generation**: Creates parent tags for nested hierarchies

## Tag Categories

### Programming Languages
Detects: Python, JavaScript, TypeScript, Java, Rust, Go, Ruby, C++, C#, Swift, Kotlin, PHP, Perl, R

### Frameworks & Libraries
Detects: React, Angular, Vue, Svelte, Django, Flask, FastAPI, Rails, Spring, Express, Next.js

### Databases
Detects: PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, Cassandra, DynamoDB, SQLite

### DevOps & Cloud
Detects: Docker, Kubernetes, Terraform, Ansible, Jenkins, GitHub Actions, AWS, Azure, GCP

### AI/ML
Detects: Machine Learning, Deep Learning, Neural Networks, NLP, Computer Vision, TensorFlow, PyTorch, scikit-learn

### Platforms
Detects: GitHub, GitLab, Stack Overflow, Reddit, YouTube, Wikipedia, Medium, Dev.to

### Content Types
Detects: Tutorial, Guide, Documentation, Blog, Video, PDF, Book, Course, Research

## Configuration

### Custom IDF Scores

```python
tagger = NLPTagSuggester()

# Add custom term importance scores
tagger.idf_scores['customterm'] = 5.0  # Higher = more important
```

### Custom Patterns

```python
# Add custom technology patterns
tagger.lang_patterns[r'\\bzig\\b'] = 'programming/zig'
tagger.framework_patterns[r'\\bhtmx\\b'] = 'framework/htmx'
```

## Examples

### Batch Tagging

```python
import btk.utils as utils

bookmarks = utils.load_bookmarks('/path/to/library')
tagger = NLPTagSuggester()

for bookmark in bookmarks:
    if not bookmark.get('tags'):
        tags = tagger.suggest_tags(
            url=bookmark['url'],
            title=bookmark.get('title', ''),
            description=bookmark.get('description', '')
        )
        bookmark['tags'] = tags

utils.save_bookmarks('/path/to/library', bookmarks)
```

### Combine with LLM Tagger

```python
from integrations.auto_tag_nlp.nlp_tagger import NLPTagSuggester
from integrations.auto_tag_llm.llm_tagger import LLMTagSuggester, LLMConfig, HTTPLLMProvider

nlp_tagger = NLPTagSuggester()

# Try LLM tagger first
try:
    config = LLMConfig.load()
    if config:
        provider = HTTPLLMProvider(config)
        llm_tagger = LLMTagSuggester(provider)
        tags = llm_tagger.suggest_tags(url, title, content)
    else:
        raise ValueError("No LLM config")
except:
    # Fall back to NLP tagger
    tags = nlp_tagger.suggest_tags(url, title, content)
```

## Performance

- **Speed**: <100ms per bookmark (much faster than LLM)
- **Accuracy**: Good for technical content, less context-aware than LLM
- **Resource Usage**: Minimal memory and CPU
- **No Network**: Works completely offline

## Comparison: NLP vs LLM Tagging

| Feature | NLP Tagger | LLM Tagger |
|---------|------------|------------|
| Speed | Very fast (<100ms) | Slower (1-5s) |
| Dependencies | None | LLM server |
| Network | Not required | Required (unless local) |
| Quality | Good | Excellent |
| Context Awareness | Pattern-based | Deep understanding |
| Resource Usage | Minimal | Moderate-High |
| Cost | Free | Free (local) or paid (API) |

**Recommendation**: Use NLP tagger for fast batch processing or as fallback. Use LLM tagger when quality matters most.

## Extending the Tagger

### Add New Patterns

```python
class CustomNLPTagger(NLPTagSuggester):
    def _init_patterns(self):
        super()._init_patterns()

        # Add custom patterns
        self.lang_patterns[r'\\bdarl\\b'] = 'programming/dart'
        self.framework_patterns[r'\\bflutter\\b'] = 'framework/flutter'
        self.db_patterns[r'\\bsurrealdb\\b'] = 'database/surrealdb'
```

### Custom IDF Weights

```python
# Increase importance of domain-specific terms
tagger.idf_scores.update({
    'blockchain': 6.0,
    'cryptocurrency': 6.0,
    'defi': 6.5,
    'nft': 6.0
})
```

## License

Part of the BTK (Bookmark Toolkit) project.
