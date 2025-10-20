# LLM-Based Auto-Tagging Integration

Intelligent tag suggestion using Large Language Models. Works with any OpenAI-compatible API including Ollama, OpenAI, LocalAI, vLLM, and LM Studio.

## Features

- **Context-Aware Tagging**: Understands bookmark content and context
- **Hierarchical Tags**: Generates organized tag hierarchies (e.g., `programming/python`)
- **Universal LLM Support**: Works with any OpenAI-compatible endpoint
- **Flexible Configuration**: Environment variables, config files, or programmatic
- **Intelligent Fallback**: Falls back to domain-based tags if LLM unavailable

## Installation

```bash
pip install requests
```

## Configuration

### Option 1: Environment Variables

```bash
export BTK_LLM_MODEL="llama3.2"
export BTK_LLM_BASE_URL="http://localhost:11434/v1"  # Ollama default
export BTK_LLM_TEMPERATURE="0.7"
export BTK_LLM_TIMEOUT="30.0"
```

### Option 2: Config File

Create `~/.btk/llm_config.json`:

```json
{
    "model": "qwen3:latest",
    "base_url": "http://192.168.0.225:11434/v1",
    "temperature": 0.7,
    "timeout": 30.0
}
```

### Option 3: Programmatic

```python
from integrations.auto_tag_llm.llm_tagger import LLMConfig, HTTPLLMProvider, LLMTagSuggester

# For Ollama
config = LLMConfig.ollama(model="llama3.2", host="localhost", port=11434)

# For OpenAI
config = LLMConfig.openai(api_key="sk-...", model="gpt-3.5-turbo")

# For LocalAI
config = LLMConfig.local_ai(model="mistral", host="localhost", port=8080)

# Create provider and suggester
provider = HTTPLLMProvider(config)
suggester = LLMTagSuggester(provider)
```

## Usage

### As a BTK Plugin

```python
from btk.plugins import PluginRegistry

registry = PluginRegistry()
registry.discover_plugins()

# Get LLM tagger
llm_tagger = registry.get_plugin('llm_tagger_*', 'tag_suggester')

# Suggest tags
tags = llm_tagger.suggest_tags(
    url="https://docs.python.org/3/tutorial/",
    title="Python Tutorial",
    description="Official Python tutorial for beginners",
    content="Learn Python programming..."
)

print(tags)
# ['programming/python', 'content/tutorial', 'level/beginner', 'programming', 'content', ...]
```

### Standalone Usage

```python
from integrations.auto_tag_llm.llm_tagger import LLMConfig, HTTPLLMProvider, LLMTagSuggester

# Initialize
config = LLMConfig.ollama(model="llama3.2")
provider = HTTPLLMProvider(config)
tagger = LLMTagSuggester(provider)

# Suggest tags
tags = tagger.suggest_tags(
    url="https://pytorch.org/tutorials/",
    title="PyTorch Tutorials",
    content="Deep learning framework tutorials..."
)
```

## Supported LLM Providers

### Ollama (Local)

```python
config = LLMConfig.ollama(
    model="llama3.2",  # or mistral, qwen3, phi4, etc.
    host="localhost",
    port=11434
)
```

Popular models:
- `llama3.2`: Meta's latest (recommended)
- `mistral`: Fast and accurate
- `qwen3`: Excellent for code/tech
- `phi4`: Microsoft's efficient model

### OpenAI

```python
config = LLMConfig.openai(
    api_key="sk-...",
    model="gpt-3.5-turbo"  # or gpt-4
)
```

### LocalAI

```python
config = LLMConfig.local_ai(
    model="model-name",
    host="localhost",
    port=8080
)
```

### vLLM / LM Studio / Any OpenAI-compatible

```python
config = LLMConfig(
    base_url="http://your-server:port/v1",
    model="your-model",
    api_key="optional-key"
)
```

## Tag Generation

The LLM generates hierarchical tags based on:

- **Programming languages**: `programming/python`, `programming/javascript`
- **Frameworks**: `framework/react`, `framework/django`
- **Technologies**: `devops/docker`, `cloud/aws`, `database/postgresql`
- **Content type**: `content/tutorial`, `content/documentation`, `content/video`
- **Topics**: `ai/machine-learning`, `security/authentication`, `design/ui`
- **Platforms**: `platform/github`, `platform/stackoverflow`
- **Level**: `level/beginner`, `level/advanced`

## Advanced Usage

### Batch Tagging

```python
import btk.utils as utils

bookmarks = utils.load_bookmarks('/path/to/library')

for bookmark in bookmarks:
    if not bookmark.get('tags'):
        tags = tagger.suggest_tags(
            url=bookmark['url'],
            title=bookmark.get('title'),
            description=bookmark.get('description')
        )
        bookmark['tags'] = tags
        print(f"Tagged {bookmark['title']}: {tags[:3]}")

utils.save_bookmarks('/path/to/library', bookmarks)
```

### Custom Temperature

```python
# More creative/diverse tags (higher temperature)
config.temperature = 0.9

# More focused/consistent tags (lower temperature)
config.temperature = 0.3
```

### Integration with NLP Tagger

```python
from integrations.auto_tag_nlp.nlp_tagger import NLPTagSuggester

nlp_tagger = NLPTagSuggester()

# Use both for better coverage
llm_tags = llm_tagger.suggest_tags(url, title, content)
nlp_tags = nlp_tagger.suggest_tags(url, title, content)

# Merge tags (LLM tags first for priority)
combined = list(dict.fromkeys(llm_tags + nlp_tags))[:15]
```

## Performance

- **Response time**: 1-5 seconds per bookmark (depends on model/hardware)
- **Quality**: Generally better than NLP-based tagging
- **Local models**: No API costs, full privacy
- **Cloud APIs**: Faster but costs money

## Troubleshooting

### LLM Not Available

```bash
# Check if Ollama is running
curl http://localhost:11434/v1/models

# Start Ollama
ollama serve

# Pull a model
ollama pull llama3.2
```

### Timeout Errors

```python
# Increase timeout
config.timeout = 60.0  # 60 seconds

# Use faster model
config.model = "llama3.2"  # instead of larger models
```

### Poor Tag Quality

```python
# Use better model
config.model = "qwen3:latest"  # or gpt-4 for OpenAI

# Adjust temperature
config.temperature = 0.5  # Lower for more focused tags

# Provide more context
tags = tagger.suggest_tags(
    url=url,
    title=title,
    description=description,
    content=full_content  # Include more content
)
```

## License

Part of the BTK (Bookmark Toolkit) project.
