"""
LLM-based tag suggester for BTK.

Works with any OpenAI-compatible API endpoint:
- OpenAI API
- Ollama (local models)
- LocalAI
- vLLM
- LM Studio
- Anthropic (via proxy)
- Any OpenAI-compatible endpoint

Configuration can be provided via:
1. Environment variables (BTK_LLM_*)
2. Config file (~/.btk/llm_config.json)
3. Programmatically
"""

import json
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from pathlib import Path
import logging
import requests
from urllib.parse import urlparse

from btk.plugins import TagSuggester, PluginMetadata, PluginPriority

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""
    base_url: str = "http://localhost:11434/v1"
    api_key: Optional[str] = None
    model: Optional[str] = None  # No default model - must be specified
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    timeout: float = 30.0
    
    @classmethod
    def from_env(cls) -> 'LLMConfig':
        """Create config from environment variables."""
        return cls(
            base_url=os.getenv("BTK_LLM_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("BTK_LLM_API_KEY"),
            model=os.getenv("BTK_LLM_MODEL"),  # No default - must be explicitly set
            temperature=float(os.getenv("BTK_LLM_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("BTK_LLM_MAX_TOKENS", "0")) or None,
            timeout=float(os.getenv("BTK_LLM_TIMEOUT", "30.0"))
        )
    
    @classmethod
    def from_file(cls, config_path: Optional[Path] = None) -> Optional['LLMConfig']:
        """
        Load config from JSON file.
        
        Default location: ~/.btk/llm_config.json
        
        Example config file:
        {
            "model": "llama3.2",
            "base_url": "http://localhost:11434/v1",
            "temperature": 0.7,
            "timeout": 30.0
        }
        """
        if config_path is None:
            config_path = Path.home() / ".btk" / "llm_config.json"
        
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            
            return cls(
                base_url=data.get("base_url", "http://localhost:11434/v1"),
                api_key=data.get("api_key"),
                model=data.get("model"),
                temperature=data.get("temperature", 0.7),
                max_tokens=data.get("max_tokens"),
                timeout=data.get("timeout", 30.0)
            )
        except Exception as e:
            logger.warning(f"Failed to load LLM config from {config_path}: {e}")
            return None
    
    @classmethod
    def load(cls) -> Optional['LLMConfig']:
        """
        Load config with priority: environment > config file.
        
        Returns None if no valid configuration found.
        """
        # First check environment variables
        env_config = cls.from_env()
        if env_config.model:  # If model is set in env, use env config
            return env_config
        
        # Then check config file
        file_config = cls.from_file()
        if file_config and file_config.model:
            # Merge with env variables (env takes precedence for non-None values)
            if os.getenv("BTK_LLM_BASE_URL"):
                file_config.base_url = env_config.base_url
            if os.getenv("BTK_LLM_API_KEY"):
                file_config.api_key = env_config.api_key
            if os.getenv("BTK_LLM_TEMPERATURE"):
                file_config.temperature = env_config.temperature
            if os.getenv("BTK_LLM_MAX_TOKENS"):
                file_config.max_tokens = env_config.max_tokens
            if os.getenv("BTK_LLM_TIMEOUT"):
                file_config.timeout = env_config.timeout
            return file_config
        
        return None
    
    @classmethod
    def openai(cls, api_key: str, model: str = "gpt-3.5-turbo") -> 'LLMConfig':
        """Create config for OpenAI API."""
        return cls(
            base_url="https://api.openai.com/v1",
            api_key=api_key,
            model=model
        )
    
    @classmethod
    def ollama(cls, model: str, host: str = "localhost", port: int = 11434) -> 'LLMConfig':
        """Create config for Ollama - model must be specified (e.g., 'llama3.2', 'mistral', 'qwen2.5-coder')."""
        return cls(
            base_url=f"http://{host}:{port}/v1",
            model=model
        )
    
    @classmethod
    def local_ai(cls, model: str, host: str = "localhost", port: int = 8080) -> 'LLMConfig':
        """Create config for LocalAI."""
        return cls(
            base_url=f"http://{host}:{port}/v1",
            model=model
        )


class HTTPLLMProvider:
    """
    Universal HTTP-based LLM provider using OpenAI-compatible API.
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        """Initialize the LLM provider."""
        self.config = config or LLMConfig.from_env()
        self.session = requests.Session()
        
        # Set up headers
        if self.config.api_key:
            self.session.headers["Authorization"] = f"Bearer {self.config.api_key}"
        self.session.headers["Content-Type"] = "application/json"
    
    def complete(self, prompt: str, **kwargs) -> str:
        """
        Get completion from LLM.
        
        Args:
            prompt: The prompt text
            **kwargs: Additional parameters
            
        Returns:
            Generated text
        """
        if not self.config.model:
            raise ValueError("No model specified in LLM configuration")
            
        # Build request using OpenAI-compatible format
        data = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        
        if self.config.max_tokens:
            data["max_tokens"] = self.config.max_tokens
        
        # Add any additional parameters
        for key in ["top_p", "frequency_penalty", "presence_penalty", "stop"]:
            if key in kwargs:
                data[key] = kwargs[key]
        
        try:
            response = self.session.post(
                f"{self.config.base_url}/chat/completions",
                json=data,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except requests.exceptions.Timeout:
            logger.error(f"LLM request timed out after {self.config.timeout}s")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM request failed: {e}")
            raise
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected LLM response format: {e}")
            raise
    
    def complete_json(self, prompt: str, schema: Optional[Dict] = None, **kwargs) -> Dict:
        """
        Get JSON completion from LLM.
        
        Args:
            prompt: The prompt text
            schema: Optional JSON schema to enforce
            **kwargs: Additional parameters
            
        Returns:
            Parsed JSON object
        """
        # Add JSON instruction to prompt
        json_prompt = f"{prompt}\n\nIMPORTANT: Respond with valid JSON only, no additional text."
        
        if schema:
            json_prompt += f"\n\nFollow this exact schema:\n{json.dumps(schema, indent=2)}"
        
        response = self.complete(json_prompt, **kwargs)
        
        # Parse JSON from response
        try:
            # Try direct parsing first
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            
            # Remove markdown code blocks if present
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            
            # Try to find JSON object or array
            json_match = re.search(r'[\{\[].*[\}\]]', cleaned, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            
            # Final attempt
            return json.loads(cleaned)
    
    def is_available(self) -> bool:
        """Check if the LLM provider is available."""
        try:
            # Try a simple health check or model list request
            response = self.session.get(
                f"{self.config.base_url}/models",
                timeout=5.0
            )
            return response.status_code == 200
        except:
            return False


class LLMTagSuggester(TagSuggester):
    """
    Tag suggester using Large Language Models.
    
    This plugin uses LLMs to intelligently suggest tags based on
    bookmark content, providing more context-aware suggestions than
    simple pattern matching.
    """
    
    def __init__(self, provider: Optional[HTTPLLMProvider] = None):
        """Initialize the LLM tag suggester."""
        self.provider = provider or HTTPLLMProvider()
        
        self._metadata = PluginMetadata(
            name=f"llm_tagger_{self.provider.config.model}",
            version="1.0.0",
            author="BTK Team",
            description=f"LLM-based tag suggester using {self.provider.config.model}",
            priority=PluginPriority.HIGH.value  # Higher priority than NLP tagger
        )
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._metadata
    
    @property
    def name(self) -> str:
        """Return plugin name."""
        return self._metadata.name
    
    def validate(self) -> bool:
        """Validate that the LLM provider is available."""
        if not self.provider.is_available():
            logger.warning(f"LLM provider at {self.provider.config.base_url} is not available")
            return False
        return True
    
    def suggest_tags(self, url: str, title: str = None, content: str = None,
                    description: str = None) -> List[str]:
        """
        Suggest tags for a bookmark using LLM.
        
        Args:
            url: The bookmark URL
            title: The bookmark title
            content: Optional page content (first 1000 chars if provided)
            description: Optional description
            
        Returns:
            List of suggested tags
        """
        # Parse domain for context
        try:
            domain = urlparse(url).netloc
        except:
            domain = "unknown"
        
        # Truncate content if too long
        if content and len(content) > 1000:
            content = content[:1000] + "..."
        
        # Build the prompt
        prompt = f"""Analyze this bookmark and suggest relevant hierarchical tags.

URL: {url}
Domain: {domain}
Title: {title or 'N/A'}
Description: {description or 'N/A'}
Content Preview: {content[:500] if content else 'N/A'}

Based on this information, suggest up to 15 relevant tags that would help categorize and find this bookmark.

Use hierarchical tags with '/' separator when appropriate (e.g., "programming/python", "devops/docker").

Categories to consider:
- Programming languages (e.g., programming/python, programming/javascript)
- Frameworks and libraries (e.g., framework/react, framework/django)
- Technologies (e.g., devops/docker, cloud/aws, database/postgresql)
- Content type (e.g., content/tutorial, content/documentation, content/video)
- Topics (e.g., ai/machine-learning, security/authentication, design/ui)
- Platforms (e.g., platform/github, platform/stackoverflow)
- Level (e.g., level/beginner, level/advanced)

Return ONLY a JSON array of tag strings, ordered from most to least relevant.
Example: ["programming/python", "framework/django", "content/tutorial", "database/postgresql", "level/intermediate"]"""

        try:
            # Get tags from LLM
            result = self.provider.complete_json(prompt)
            
            # Validate and clean the response
            if isinstance(result, list):
                tags = result
            elif isinstance(result, dict) and 'tags' in result:
                tags = result['tags']
            else:
                logger.warning(f"Unexpected LLM response format: {result}")
                return []
            
            # Validate each tag
            valid_tags = []
            for tag in tags:
                if isinstance(tag, str) and tag.strip():
                    # Clean and validate the tag
                    tag = tag.strip().lower()
                    # Remove any quotes or special characters
                    tag = tag.strip('"\'')
                    # Ensure it's a reasonable tag
                    if len(tag) < 50 and not tag.startswith('/') and not tag.endswith('/'):
                        valid_tags.append(tag)
            
            # Add parent tags for hierarchical tags
            all_tags = set(valid_tags)
            for tag in valid_tags:
                if '/' in tag:
                    parts = tag.split('/')
                    for i in range(1, len(parts)):
                        parent = '/'.join(parts[:i])
                        all_tags.add(parent)
            
            # Sort by specificity (more specific first)
            final_tags = sorted(list(all_tags), key=lambda x: (x.count('/'), x), reverse=True)
            
            return final_tags[:15]
            
        except Exception as e:
            logger.error(f"LLM tag suggestion failed: {e}")
            # Fall back to basic domain-based tags
            fallback_tags = []
            
            if domain:
                # Common domain patterns
                if 'github.com' in domain:
                    fallback_tags.append('platform/github')
                elif 'stackoverflow.com' in domain:
                    fallback_tags.append('q&a/stackoverflow')
                elif 'youtube.com' in domain:
                    fallback_tags.append('video/youtube')
                elif 'wikipedia.org' in domain:
                    fallback_tags.append('reference/wikipedia')
            
            return fallback_tags


def register_plugins(registry):
    """
    Register the LLM tag suggester with the plugin registry.
    
    Configuration priority:
    1. Environment variables (BTK_LLM_*)
    2. Config file (~/.btk/llm_config.json)
    
    Required configuration:
    - model: The model to use (e.g., 'llama3.2', 'mistral', 'qwen3', 'phi4')
    
    Optional configuration:
    - base_url: API endpoint (default: http://localhost:11434/v1 for Ollama)
    - api_key: API key if required (for OpenAI, etc.)
    - temperature: Temperature for generation (default: 0.7)
    - max_tokens: Max tokens to generate
    - timeout: Request timeout in seconds (default: 30.0)
    
    Example ~/.btk/llm_config.json for your Ollama server:
    {
        "model": "qwen3:latest",
        "base_url": "http://192.168.0.225:11434/v1"
    }
    """
    try:
        # Load config from environment or file
        config = LLMConfig.load()
        
        # Skip if no config or model specified
        if not config or not config.model:
            logger.debug("No LLM configuration found (check BTK_LLM_MODEL env var or ~/.btk/llm_config.json)")
            return
        
        # Try to create provider
        provider = HTTPLLMProvider(config)
        
        # Check if provider is available
        if provider.is_available():
            suggester = LLMTagSuggester(provider)
            registry.register(suggester, 'tag_suggester')
            logger.info(f"Registered LLM tag suggester using {config.model} at {config.base_url}")
        else:
            logger.info(f"LLM provider at {config.base_url} not available, skipping LLM tag suggester registration")
            
    except Exception as e:
        logger.debug(f"Could not register LLM tag suggester: {e}")