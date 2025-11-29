"""
Semantic search engine for BTK bookmarks.

This module provides semantic search capabilities using sentence embeddings,
allowing users to find bookmarks by meaning and context rather than just keywords.
"""

import logging
import pickle
import json
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import numpy as np
from datetime import datetime

from btk.plugins import SearchEnhancer, PluginMetadata, PluginPriority

logger = logging.getLogger(__name__)

# Try to import sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers not available. Install with: pip install sentence-transformers")


class SemanticSearchEngine(SearchEnhancer):
    """
    Semantic search engine using sentence embeddings.
    
    This plugin uses sentence-transformers to create embeddings of bookmark
    content and enables semantic search based on meaning similarity.
    """
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', 
                 cache_dir: Optional[str] = None,
                 device: str = 'cpu'):
        """
        Initialize the semantic search engine.
        
        Args:
            model_name: Name of the sentence-transformer model to use
            cache_dir: Directory to cache embeddings
            device: Device to run model on ('cpu', 'cuda', etc.)
        """
        self._metadata = PluginMetadata(
            name="semantic_search",
            version="1.0.0",
            author="BTK Team",
            description="Semantic search using sentence embeddings",
            priority=PluginPriority.HIGH.value
        )
        
        self.model_name = model_name
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / '.btk' / 'semantic_cache'
        self.device = device
        
        # Initialize model if available
        self.model = None
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.model = SentenceTransformer(model_name, device=device)
                logger.info(f"Loaded sentence transformer model: {model_name}")
            except Exception as e:
                logger.error(f"Failed to load model {model_name}: {e}")
        
        # Cache for embeddings
        self.embeddings_cache = {}
        self.ensure_cache_dir()
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._metadata
    
    @property
    def name(self) -> str:
        """Return plugin name."""
        return self._metadata.name
    
    def validate(self) -> bool:
        """Check if the plugin can function."""
        return SENTENCE_TRANSFORMERS_AVAILABLE and self.model is not None
    
    def ensure_cache_dir(self):
        """Ensure cache directory exists."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_bookmark_text(self, bookmark: Dict[str, Any]) -> str:
        """
        Extract searchable text from a bookmark.
        
        Args:
            bookmark: The bookmark dictionary
            
        Returns:
            Combined text for embedding
        """
        parts = []
        
        # Title (most important)
        if bookmark.get('title'):
            parts.append(bookmark['title'])
        
        # URL (domain and path can be meaningful)
        if bookmark.get('url'):
            parts.append(bookmark['url'])
        
        # Description
        if bookmark.get('description'):
            parts.append(bookmark['description'])
        
        # Tags (important for context)
        if bookmark.get('tags'):
            parts.append(' '.join(bookmark['tags']))
        
        # Content (if extracted)
        if bookmark.get('content'):
            # Limit content to first 500 chars for efficiency
            content = bookmark['content'][:500]
            parts.append(content)
        
        return ' '.join(parts)
    
    def create_embeddings(self, bookmarks: List[Dict[str, Any]], 
                         force_rebuild: bool = False) -> np.ndarray:
        """
        Create embeddings for bookmarks.
        
        Args:
            bookmarks: List of bookmarks to embed
            force_rebuild: Force rebuilding embeddings even if cached
            
        Returns:
            Numpy array of embeddings
        """
        if not self.model:
            raise RuntimeError("Sentence transformer model not available")
        
        # Check cache
        cache_file = self.cache_dir / f"{self.model_name.replace('/', '_')}_embeddings.pkl"
        
        if not force_rebuild and cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    cached_data = pickle.load(f)
                    
                # Check if bookmarks match
                if len(cached_data['bookmarks']) == len(bookmarks):
                    # Simple check: compare first and last bookmark IDs
                    if (bookmarks[0].get('id') == cached_data['bookmarks'][0] and
                        bookmarks[-1].get('id') == cached_data['bookmarks'][-1]):
                        logger.info(f"Loaded {len(bookmarks)} embeddings from cache")
                        return cached_data['embeddings']
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        
        # Create new embeddings
        logger.info(f"Creating embeddings for {len(bookmarks)} bookmarks...")
        
        # Extract text from bookmarks
        texts = [self.get_bookmark_text(bookmark) for bookmark in bookmarks]
        
        # Create embeddings
        embeddings = self.model.encode(texts, show_progress_bar=True)
        
        # Cache the embeddings
        try:
            cache_data = {
                'bookmarks': [b.get('id') for b in bookmarks],
                'embeddings': embeddings,
                'model': self.model_name,
                'created_at': datetime.utcnow().isoformat()
            }
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            logger.info(f"Cached embeddings to {cache_file}")
        except Exception as e:
            logger.warning(f"Failed to cache embeddings: {e}")
        
        return embeddings
    
    def search(self, query: str, bookmarks: List[Dict[str, Any]], 
              top_k: int = 10, threshold: float = 0.0) -> List[Dict[str, Any]]:
        """
        Perform semantic search on bookmarks.
        
        Args:
            query: Search query
            bookmarks: List of bookmarks to search
            top_k: Number of top results to return
            threshold: Minimum similarity threshold (0-1)
            
        Returns:
            List of bookmarks sorted by relevance
        """
        if not self.model:
            logger.warning("Semantic search not available, falling back to keyword search")
            # Fallback to simple keyword search
            query_lower = query.lower()
            results = []
            for bookmark in bookmarks:
                text = self.get_bookmark_text(bookmark).lower()
                if query_lower in text:
                    results.append(bookmark)
            return results[:top_k]
        
        # Create embeddings for bookmarks if needed
        embeddings = self.create_embeddings(bookmarks)
        
        # Encode query
        query_embedding = self.model.encode([query])
        
        # Calculate cosine similarities
        similarities = self.cosine_similarity(query_embedding, embeddings)[0]
        
        # Get top k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        # Filter by threshold and create results
        results = []
        for idx in top_indices:
            similarity = float(similarities[idx])
            if similarity >= threshold:
                bookmark = bookmarks[idx].copy()
                bookmark['semantic_score'] = similarity
                results.append(bookmark)
        
        return results
    
    def find_similar(self, bookmark: Dict[str, Any], 
                    bookmarks: List[Dict[str, Any]], 
                    top_k: int = 5,
                    threshold: float = 0.5) -> List[Dict[str, Any]]:
        """
        Find bookmarks similar to a given bookmark.
        
        Args:
            bookmark: Reference bookmark
            bookmarks: List of bookmarks to search
            top_k: Number of similar bookmarks to return
            threshold: Minimum similarity threshold
            
        Returns:
            List of similar bookmarks
        """
        if not self.model:
            return []
        
        # Get text from reference bookmark
        ref_text = self.get_bookmark_text(bookmark)
        
        # Use search with the reference text
        # Filter out the reference bookmark itself
        all_results = self.search(ref_text, bookmarks, top_k + 1, threshold)
        
        # Remove the reference bookmark if present
        ref_id = bookmark.get('id')
        results = [b for b in all_results if b.get('id') != ref_id]
        
        return results[:top_k]
    
    def cluster_bookmarks(self, bookmarks: List[Dict[str, Any]], 
                         n_clusters: int = 5) -> Dict[int, List[Dict[str, Any]]]:
        """
        Cluster bookmarks into groups based on semantic similarity.
        
        Args:
            bookmarks: List of bookmarks to cluster
            n_clusters: Number of clusters
            
        Returns:
            Dictionary mapping cluster ID to list of bookmarks
        """
        if not self.model:
            return {0: bookmarks}  # Single cluster fallback
        
        try:
            from sklearn.cluster import KMeans
        except ImportError:
            logger.warning("scikit-learn not available for clustering")
            return {0: bookmarks}
        
        # Create embeddings
        embeddings = self.create_embeddings(bookmarks)
        
        # Perform clustering
        kmeans = KMeans(n_clusters=min(n_clusters, len(bookmarks)), random_state=42)
        cluster_labels = kmeans.fit_predict(embeddings)
        
        # Group bookmarks by cluster
        clusters = {}
        for idx, label in enumerate(cluster_labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(bookmarks[idx])
        
        return clusters
    
    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """
        Calculate cosine similarity between vectors.
        
        Args:
            a: First vector or matrix
            b: Second vector or matrix
            
        Returns:
            Similarity scores
        """
        # Normalize vectors
        a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
        b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)
        
        # Calculate cosine similarity
        return np.dot(a_norm, b_norm.T)
    
    def update_bookmark_embedding(self, bookmark: Dict[str, Any]):
        """
        Update embedding for a single bookmark.
        
        Args:
            bookmark: Bookmark to update
        """
        if not self.model:
            return
        
        bookmark_id = bookmark.get('id')
        if bookmark_id:
            text = self.get_bookmark_text(bookmark)
            embedding = self.model.encode([text])[0]
            self.embeddings_cache[bookmark_id] = embedding


def register_plugins(registry):
    """Register the semantic search engine with the plugin registry."""
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        logger.info("Semantic search not available - install sentence-transformers")
        return
    
    try:
        engine = SemanticSearchEngine()
        if engine.validate():
            registry.register(engine, 'search_enhancer')
            logger.info("Registered semantic search engine")
        else:
            logger.warning("Semantic search engine validation failed")
    except Exception as e:
        logger.warning(f"Could not register semantic search: {e}")