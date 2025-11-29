"""
NLP-based tag suggester using TF-IDF and other classical techniques.
"""

import re
import math
from typing import List, Dict, Any, Optional, Set
from collections import Counter
from urllib.parse import urlparse
import logging

from btk.plugins import TagSuggester, PluginMetadata, PluginPriority

logger = logging.getLogger(__name__)


class NLPTagSuggester(TagSuggester):
    """
    Tag suggester using classical NLP techniques like TF-IDF.
    
    Features:
    - TF-IDF for important term extraction
    - Domain-based categorization
    - Named entity-like recognition for technologies
    - Hierarchical tag generation
    """
    
    def __init__(self):
        """Initialize the NLP tag suggester."""
        self._metadata = PluginMetadata(
            name="nlp_tagger",
            version="1.0.0",
            author="BTK Team",
            description="NLP-based tag suggester using TF-IDF and pattern matching",
            priority=PluginPriority.NORMAL.value
        )
        
        # Build corpus statistics for TF-IDF
        self._build_corpus_stats()
        
        # Technology patterns for recognition
        self._init_patterns()
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._metadata
    
    @property
    def name(self) -> str:
        """Return plugin name."""
        return self._metadata.name
    
    def _build_corpus_stats(self):
        """Build document frequency statistics for common terms."""
        # Common English stop words (extended)
        self.stop_words = {
            'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
            'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
            'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she',
            'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there', 'their',
            'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get', 'which', 'go',
            'me', 'when', 'make', 'can', 'like', 'time', 'no', 'just', 'him', 'know',
            'take', 'people', 'into', 'year', 'your', 'good', 'some', 'could', 'them',
            'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come', 'its', 'over',
            'think', 'also', 'back', 'after', 'use', 'two', 'how', 'our', 'work',
            'first', 'well', 'way', 'even', 'new', 'want', 'because', 'any', 'these',
            'give', 'day', 'most', 'us', 'is', 'was', 'are', 'been', 'has', 'had',
            'were', 'am', 'being', 'have', 'has', 'had', 'having', 'do', 'does',
            'did', 'will', 'would', 'should', 'may', 'might', 'must', 'can', 'could',
            'www', 'http', 'https', 'com', 'org', 'net', 'io'
        }
        
        # Approximate IDF scores for common web/tech terms (log scale)
        # Higher values = more specific/important
        self.idf_scores = {
            # Programming languages (high specificity)
            'python': 4.5, 'javascript': 4.5, 'typescript': 5.0, 'java': 4.3,
            'rust': 5.2, 'golang': 5.3, 'ruby': 4.8, 'php': 4.6, 'swift': 5.0,
            'kotlin': 5.2, 'scala': 5.3, 'clojure': 5.5, 'haskell': 5.5,
            'erlang': 5.6, 'elixir': 5.6, 'perl': 4.9, 'cpp': 5.0, 'csharp': 5.0,
            
            # Frameworks (high specificity)
            'react': 4.8, 'angular': 4.8, 'vue': 5.0, 'svelte': 5.5,
            'django': 5.0, 'flask': 5.1, 'fastapi': 5.5, 'rails': 4.9,
            'spring': 4.7, 'express': 4.8, 'nextjs': 5.3, 'nuxt': 5.4,
            
            # Technologies (medium-high specificity)
            'docker': 4.6, 'kubernetes': 5.0, 'terraform': 5.2, 'ansible': 5.1,
            'jenkins': 5.0, 'github': 3.8, 'gitlab': 4.5, 'git': 3.5,
            'aws': 4.2, 'azure': 4.4, 'gcp': 5.0, 'cloud': 3.0,
            
            # Databases (high specificity)
            'postgresql': 5.1, 'mysql': 4.7, 'mongodb': 5.0, 'redis': 5.1,
            'elasticsearch': 5.3, 'cassandra': 5.4, 'dynamodb': 5.4,
            'sqlite': 4.9, 'oracle': 4.5, 'mariadb': 5.2,
            
            # AI/ML terms (medium-high specificity)
            'machine': 2.5, 'learning': 2.5, 'deep': 3.0, 'neural': 4.5,
            'ai': 3.5, 'ml': 4.0, 'tensorflow': 5.2, 'pytorch': 5.2,
            'scikit': 5.3, 'keras': 5.2, 'nlp': 4.8, 'cv': 4.5,
            
            # Web terms (medium specificity)
            'api': 3.5, 'rest': 4.0, 'graphql': 5.2, 'websocket': 5.0,
            'http': 2.5, 'https': 2.5, 'json': 3.8, 'xml': 3.9,
            'html': 3.0, 'css': 3.5, 'sass': 4.8, 'webpack': 5.0,
            
            # General tech terms (lower specificity)
            'tutorial': 3.0, 'guide': 2.8, 'documentation': 3.2, 'blog': 2.5,
            'article': 2.3, 'video': 2.7, 'course': 3.1, 'book': 2.9,
            'tool': 2.4, 'software': 2.2, 'application': 2.3, 'system': 2.0,
            'framework': 3.0, 'library': 2.8, 'package': 2.9, 'module': 3.0,
            
            # Security terms
            'security': 3.5, 'encryption': 4.5, 'authentication': 4.2,
            'authorization': 4.3, 'oauth': 5.0, 'jwt': 5.2, 'ssl': 4.5,
            'vulnerability': 4.0, 'penetration': 4.5, 'firewall': 4.2,
            
            # Default IDF for unknown terms
            'default': 3.0
        }
    
    def _init_patterns(self):
        """Initialize regex patterns for entity recognition."""
        # Programming language patterns
        self.lang_patterns = {
            r'\bpython\b': 'programming/python',
            r'\bjavascript\b|\bjs\b': 'programming/javascript',
            r'\btypescript\b|\bts\b': 'programming/typescript',
            r'\bjava\b(?!script)': 'programming/java',
            r'\brust\b': 'programming/rust',
            r'\bgolang\b|\bgo\b(?=\s+(?:lang|programming|code))': 'programming/go',
            r'\bruby\b': 'programming/ruby',
            r'\bc\+\+\b|\bcpp\b': 'programming/cpp',
            r'\bc#\b|\bcsharp\b': 'programming/csharp',
            r'\bswift\b': 'programming/swift',
            r'\bkotlin\b': 'programming/kotlin',
            r'\bphp\b': 'programming/php',
            r'\bperl\b': 'programming/perl',
            r'\br\b(?=\s+(?:lang|programming|statistics))': 'programming/r',
        }
        
        # Framework patterns
        self.framework_patterns = {
            r'\breact(?:\.?js)?\b': 'framework/react',
            r'\bangular(?:\.?js)?\b': 'framework/angular',
            r'\bvue(?:\.?js)?\b': 'framework/vue',
            r'\bsvelte\b': 'framework/svelte',
            r'\bdjango\b': 'framework/django',
            r'\bflask\b': 'framework/flask',
            r'\bfastapi\b': 'framework/fastapi',
            r'\brails\b|\bruby on rails\b': 'framework/rails',
            r'\bspring\b(?:\s+boot)?\b': 'framework/spring',
            r'\bexpress(?:\.?js)?\b': 'framework/express',
            r'\bnext(?:\.?js)?\b': 'framework/nextjs',
        }
        
        # Database patterns  
        self.db_patterns = {
            r'\bpostgres(?:ql)?\b': 'database/postgresql',
            r'\bmysql\b': 'database/mysql',
            r'\bmongodb?\b': 'database/mongodb',
            r'\bredis\b': 'database/redis',
            r'\belasticsearch\b': 'database/elasticsearch',
            r'\bcassandra\b': 'database/cassandra',
            r'\bdynamodb?\b': 'database/dynamodb',
            r'\bsqlite\b': 'database/sqlite',
        }
        
        # Cloud/DevOps patterns
        self.devops_patterns = {
            r'\bdocker\b': 'devops/docker',
            r'\bkubernetes\b|\bk8s\b': 'devops/kubernetes',
            r'\bterraform\b': 'devops/terraform',
            r'\bansible\b': 'devops/ansible',
            r'\bjenkins\b': 'devops/jenkins',
            r'\bgithub\s+actions\b': 'devops/ci-cd',
            r'\bgitlab\s+ci\b': 'devops/ci-cd',
            r'\baws\b|\bamazon\s+web\s+services\b': 'cloud/aws',
            r'\bazure\b': 'cloud/azure',
            r'\bgcp\b|\bgoogle\s+cloud\b': 'cloud/gcp',
        }
        
        # AI/ML patterns
        self.ml_patterns = {
            r'\bmachine\s+learning\b': 'ai/machine-learning',
            r'\bdeep\s+learning\b': 'ai/deep-learning',
            r'\bneural\s+network': 'ai/neural-networks',
            r'\bnatural\s+language\s+processing\b|\bnlp\b': 'ai/nlp',
            r'\bcomputer\s+vision\b': 'ai/computer-vision',
            r'\btensorflow\b': 'ai/tensorflow',
            r'\bpytorch\b': 'ai/pytorch',
            r'\bscikit[\-\s]?learn\b': 'ai/scikit-learn',
        }
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into words."""
        # Convert to lowercase and split on non-word characters
        text = text.lower()
        tokens = re.findall(r'\b[a-z]+(?:\.?[a-z]+)*\b', text)
        
        # Filter stop words and very short tokens
        tokens = [t for t in tokens if t not in self.stop_words and len(t) > 2]
        
        return tokens
    
    def _calculate_tf(self, tokens: List[str]) -> Dict[str, float]:
        """Calculate term frequency."""
        token_count = Counter(tokens)
        total_tokens = len(tokens)
        
        if total_tokens == 0:
            return {}
        
        # Normalized TF (frequency / total tokens)
        tf = {term: count / total_tokens for term, count in token_count.items()}
        return tf
    
    def _get_idf(self, term: str) -> float:
        """Get IDF score for a term."""
        return self.idf_scores.get(term, self.idf_scores['default'])
    
    def _calculate_tfidf(self, text: str) -> Dict[str, float]:
        """Calculate TF-IDF scores for terms in text."""
        tokens = self._tokenize(text)
        tf = self._calculate_tf(tokens)
        
        tfidf = {}
        for term, tf_score in tf.items():
            idf_score = self._get_idf(term)
            tfidf[term] = tf_score * idf_score
        
        return tfidf
    
    def _extract_domain_tags(self, url: str) -> List[str]:
        """Extract tags based on URL domain."""
        tags = []
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Common platform mappings
            domain_tags = {
                'github.com': 'platform/github',
                'gitlab.com': 'platform/gitlab',
                'bitbucket.org': 'platform/bitbucket',
                'stackoverflow.com': 'q&a/stackoverflow',
                'reddit.com': 'social/reddit',
                'youtube.com': 'video/youtube',
                'vimeo.com': 'video/vimeo',
                'arxiv.org': 'research/arxiv',
                'wikipedia.org': 'reference/wikipedia',
                'medium.com': 'blog/medium',
                'dev.to': 'blog/dev.to',
                'hackernews.com': 'news/hackernews',
                'news.ycombinator.com': 'news/hackernews',
            }
            
            for domain_pattern, tag in domain_tags.items():
                if domain_pattern in domain:
                    tags.append(tag)
                    break
            
            # Check for documentation sites
            if any(doc in domain for doc in ['docs.', 'documentation.', 'api.', 'developer.']):
                tags.append('documentation')
            
            # Check for news sites
            news_domains = ['nytimes', 'bbc', 'cnn', 'reuters', 'bloomberg', 'wsj', 'guardian']
            if any(news in domain for news in news_domains):
                tags.append('news')
            
        except Exception as e:
            logger.debug(f"Error parsing URL {url}: {e}")
        
        return tags
    
    def _extract_pattern_tags(self, text: str) -> List[str]:
        """Extract tags using regex patterns."""
        tags = []
        text_lower = text.lower()
        
        # Check all pattern categories
        all_patterns = [
            self.lang_patterns,
            self.framework_patterns,
            self.db_patterns,
            self.devops_patterns,
            self.ml_patterns
        ]
        
        for patterns in all_patterns:
            for pattern, tag in patterns.items():
                if re.search(pattern, text_lower):
                    tags.append(tag)
        
        return tags
    
    def _extract_content_type_tags(self, url: str, title: str) -> List[str]:
        """Extract tags based on content type."""
        tags = []
        combined = f"{url} {title}".lower()
        
        # Content type indicators
        if 'tutorial' in combined:
            tags.append('content/tutorial')
        if 'guide' in combined or 'how-to' in combined or 'howto' in combined:
            tags.append('content/guide')
        if 'documentation' in combined or '/docs/' in url:
            tags.append('content/documentation')
        if 'blog' in combined or '/blog/' in url:
            tags.append('content/blog')
        if 'video' in combined or 'youtube.com' in url or 'vimeo.com' in url:
            tags.append('content/video')
        if '.pdf' in url:
            tags.append('content/pdf')
        if 'book' in combined or 'ebook' in combined:
            tags.append('content/book')
        if 'course' in combined:
            tags.append('content/course')
        if 'paper' in combined or 'research' in combined:
            tags.append('content/research')
        
        return tags
    
    def _generate_hierarchical_tags(self, base_tags: List[str]) -> List[str]:
        """Generate parent tags from hierarchical tags."""
        all_tags = set(base_tags)
        
        for tag in base_tags:
            parts = tag.split('/')
            for i in range(1, len(parts)):
                parent = '/'.join(parts[:i])
                all_tags.add(parent)
        
        return list(all_tags)
    
    def suggest_tags(self, url: str, title: str = None, content: str = None,
                    description: str = None) -> List[str]:
        """
        Suggest tags for a bookmark using NLP techniques.
        
        Args:
            url: The bookmark URL
            title: The bookmark title
            content: Optional page content
            description: Optional description
            
        Returns:
            List of suggested tags
        """
        all_tags = []
        
        # Extract domain-based tags
        domain_tags = self._extract_domain_tags(url)
        all_tags.extend(domain_tags)
        
        # Combine all text for analysis
        combined_text = ' '.join(filter(None, [title, description, content]))
        
        if combined_text:
            # Extract pattern-based tags
            pattern_tags = self._extract_pattern_tags(combined_text)
            all_tags.extend(pattern_tags)
            
            # Calculate TF-IDF and extract top terms as tags
            tfidf_scores = self._calculate_tfidf(combined_text)
            
            # Get top terms with high TF-IDF scores
            top_terms = sorted(tfidf_scores.items(), key=lambda x: x[1], reverse=True)[:10]
            
            for term, score in top_terms:
                if score > 0.15:  # Threshold for significance
                    # Check if term maps to a known category
                    if term in ['python', 'javascript', 'typescript', 'java', 'rust', 'go']:
                        all_tags.append(f'programming/{term}')
                    elif term in ['docker', 'kubernetes', 'terraform']:
                        all_tags.append(f'devops/{term}')
                    elif term in ['react', 'angular', 'vue', 'django', 'flask']:
                        all_tags.append(f'framework/{term}')
                    elif term in ['postgresql', 'mysql', 'mongodb', 'redis']:
                        all_tags.append(f'database/{term}')
                    elif term in ['aws', 'azure', 'gcp']:
                        all_tags.append(f'cloud/{term}')
                    elif score > 0.25:  # Higher threshold for generic terms
                        # Add as a standalone tag if very significant
                        all_tags.append(term)
        
        # Extract content type tags
        content_tags = self._extract_content_type_tags(url, title or '')
        all_tags.extend(content_tags)
        
        # Generate hierarchical tags
        all_tags = self._generate_hierarchical_tags(all_tags)
        
        # Deduplicate and sort
        unique_tags = list(set(all_tags))
        
        # Sort by specificity (more specific tags first)
        unique_tags.sort(key=lambda x: (x.count('/'), x), reverse=True)
        
        # Limit to reasonable number of tags
        return unique_tags[:15]


def register_plugins(registry):
    """Register the NLP tag suggester with the plugin registry."""
    registry.register(NLPTagSuggester(), 'tag_suggester')