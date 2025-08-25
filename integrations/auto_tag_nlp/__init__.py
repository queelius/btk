"""
NLP-based auto-tagging for BTK using classical NLP techniques.

This integration provides tag suggestions using TF-IDF, named entity recognition,
and other classical NLP techniques without requiring external API calls.
"""

from .nlp_tagger import NLPTagSuggester, register_plugins

__all__ = ['NLPTagSuggester', 'register_plugins']