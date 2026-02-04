"""
Base classes for service importers.

Service importers fetch data from external services (YouTube, Twitter, etc.)
and convert them to BTK bookmarks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Generator
from datetime import datetime
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """Configuration for a service importer."""
    name: str
    api_key: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    token_path: Optional[Path] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls, name: str, prefix: Optional[str] = None) -> 'ServiceConfig':
        """Load config from environment variables."""
        import os
        prefix = prefix or name.upper()
        return cls(
            name=name,
            api_key=os.environ.get(f'{prefix}_API_KEY'),
            client_id=os.environ.get(f'{prefix}_CLIENT_ID'),
            client_secret=os.environ.get(f'{prefix}_CLIENT_SECRET'),
        )

    @classmethod
    def from_file(cls, path: Path) -> 'ServiceConfig':
        """Load config from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(**data)


@dataclass
class ImportResult:
    """Result of an import operation."""
    # Bookmark data ready for insertion
    url: str
    title: str
    description: str = ""
    tags: List[str] = field(default_factory=list)

    # Media metadata
    media_type: Optional[str] = None  # video, audio, document, image
    media_source: Optional[str] = None  # youtube, spotify, etc.
    media_id: Optional[str] = None  # Platform-specific ID
    author_name: Optional[str] = None
    author_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    published_at: Optional[datetime] = None

    # Extra data that doesn't fit standard fields
    extra_data: Dict[str, Any] = field(default_factory=dict)

    def to_bookmark_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary suitable for db.add()."""
        data = {
            'url': self.url,
            'title': self.title,
            'description': self.description,
            'tags': self.tags,
            'media_type': self.media_type,
            'media_source': self.media_source,
            'media_id': self.media_id,
            'author_name': self.author_name,
            'author_url': self.author_url,
            'thumbnail_url': self.thumbnail_url,
            'published_at': self.published_at,
        }
        if self.extra_data:
            data['extra_data'] = self.extra_data
        # Remove None values
        return {k: v for k, v in data.items() if v is not None}


class ServiceImporter(ABC):
    """
    Base class for service importers.

    Subclasses implement service-specific logic for authentication
    and data fetching. Each importer should:

    1. Handle authentication (API key, OAuth, etc.)
    2. Provide methods to import different content types
    3. Convert service data to ImportResult objects
    """

    # Service metadata
    service_name: str = "unknown"
    service_url: str = ""
    requires_auth: bool = True
    auth_type: str = "api_key"  # api_key, oauth2, cookies

    def __init__(self, config: Optional[ServiceConfig] = None):
        """Initialize the importer with optional config."""
        self.config = config or ServiceConfig(name=self.service_name)
        self._authenticated = False

    @property
    def is_authenticated(self) -> bool:
        """Check if the importer is authenticated."""
        return self._authenticated

    @abstractmethod
    def authenticate(self, **kwargs) -> bool:
        """
        Authenticate with the service.

        Returns:
            True if authentication successful
        """
        pass

    @abstractmethod
    def get_import_targets(self) -> List[Dict[str, str]]:
        """
        List available import targets for this service.

        Returns:
            List of dicts with 'name', 'description', 'requires_auth' keys
        """
        pass

    def import_all(self, target: str, **kwargs) -> Generator[ImportResult, None, None]:
        """
        Import all items from a target.

        Args:
            target: The import target name (e.g., 'library', 'subscriptions')
            **kwargs: Target-specific options

        Yields:
            ImportResult for each imported item
        """
        method_name = f'import_{target}'
        if hasattr(self, method_name):
            method = getattr(self, method_name)
            yield from method(**kwargs)
        else:
            raise ValueError(f"Unknown import target: {target}")

    def auto_tag(self, result: ImportResult) -> List[str]:
        """
        Generate automatic tags based on the import result.

        Override in subclasses for service-specific tagging.
        """
        tags = list(result.tags)  # Start with existing tags

        # Add service tag
        if self.service_name:
            tags.append(self.service_name)

        # Add media type tag
        if result.media_type:
            tags.append(f"content/{result.media_type}")

        return list(set(tags))  # Deduplicate

    def validate_url(self, url: str) -> bool:
        """Check if a URL belongs to this service."""
        return self.service_url in url if self.service_url else False

    def extract_id(self, url: str) -> Optional[str]:
        """Extract the service-specific ID from a URL."""
        return None  # Override in subclasses
