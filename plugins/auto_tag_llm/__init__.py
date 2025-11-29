"""
LLM-based auto-tagging for BTK using Large Language Models.

This integration provides intelligent tag suggestions using LLMs through
OpenAI-compatible APIs (OpenAI, Ollama, LocalAI, etc.).
"""

from .llm_tagger import LLMTagSuggester, HTTPLLMProvider, LLMConfig, register_plugins

__all__ = ['LLMTagSuggester', 'HTTPLLMProvider', 'LLMConfig', 'register_plugins']