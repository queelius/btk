"""
Content fetching and processing utilities for BTK.

Handles fetching web content, compression, HTML to Markdown conversion,
and integration with the ContentCache database model.
"""

import zlib
import hashlib
import time
from typing import Optional, Dict, Any
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md


class ContentFetcher:
    """Fetch and process web content for bookmark caching."""

    def __init__(self, timeout: int = 10, user_agent: Optional[str] = None):
        """
        Initialize the content fetcher.

        Args:
            timeout: Request timeout in seconds
            user_agent: Custom user agent string
        """
        self.timeout = timeout
        self.user_agent = user_agent or (
            "Mozilla/5.0 (compatible; BTK/1.0; +https://github.com/queelius/btk)"
        )
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    def fetch(self, url: str) -> Dict[str, Any]:
        """
        Fetch content from a URL.

        Args:
            url: The URL to fetch

        Returns:
            Dictionary containing:
                - success: bool
                - status_code: int
                - html_content: bytes (raw HTML)
                - title: str
                - encoding: str
                - content_type: str
                - response_time_ms: float
                - error: str (if failed)
        """
        result = {
            "success": False,
            "status_code": 0,
            "html_content": b"",
            "title": "",
            "encoding": "utf-8",
            "content_type": "",
            "response_time_ms": 0.0,
            "error": None,
        }

        try:
            start_time = time.time()
            response = self.session.get(
                url, timeout=self.timeout, allow_redirects=True
            )
            response_time = (time.time() - start_time) * 1000  # Convert to ms

            result["status_code"] = response.status_code
            result["response_time_ms"] = response_time
            result["content_type"] = response.headers.get("Content-Type", "")
            result["encoding"] = response.encoding or "utf-8"

            if response.status_code == 200:
                result["success"] = True
                result["html_content"] = response.content

                # Extract title
                soup = BeautifulSoup(response.content, "html.parser")
                title_tag = soup.find("title")
                if title_tag:
                    result["title"] = title_tag.get_text().strip()

            else:
                result["error"] = f"HTTP {response.status_code}"

        except requests.Timeout:
            result["error"] = "Request timeout"
        except requests.ConnectionError:
            result["error"] = "Connection error"
        except Exception as e:
            result["error"] = str(e)

        return result

    @staticmethod
    def compress_html(html_content: bytes) -> bytes:
        """
        Compress HTML content using zlib.

        Args:
            html_content: Raw HTML as bytes

        Returns:
            Compressed content
        """
        return zlib.compress(html_content, level=9)

    @staticmethod
    def decompress_html(compressed_content: bytes) -> bytes:
        """
        Decompress HTML content.

        Args:
            compressed_content: Compressed HTML

        Returns:
            Decompressed HTML as bytes
        """
        return zlib.decompress(compressed_content)

    @staticmethod
    def html_to_markdown(html_content: bytes, encoding: str = "utf-8") -> str:
        """
        Convert HTML to Markdown.

        Args:
            html_content: Raw HTML as bytes
            encoding: Character encoding

        Returns:
            Markdown string
        """
        try:
            html_str = html_content.decode(encoding)
            soup = BeautifulSoup(html_str, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Find main content (try common content containers)
            main_content = (
                soup.find("main")
                or soup.find("article")
                or soup.find("div", class_="content")
                or soup.find("div", id="content")
                or soup.find("body")
            )

            if main_content:
                # Convert to markdown
                markdown = md(
                    str(main_content),
                    heading_style="ATX",
                    bullets="-",
                    strip=["a"],  # Keep link text but remove href
                )
                return markdown.strip()

            return ""

        except Exception as e:
            return f"Error converting to markdown: {e}"

    @staticmethod
    def calculate_content_hash(html_content: bytes) -> str:
        """
        Calculate SHA256 hash of content for change detection.

        Args:
            html_content: Raw HTML as bytes

        Returns:
            Hex digest of hash
        """
        return hashlib.sha256(html_content).hexdigest()

    @staticmethod
    def extract_pdf_text(pdf_content: bytes) -> str:
        """
        Extract text from PDF content.

        Args:
            pdf_content: Raw PDF bytes

        Returns:
            Extracted text
        """
        try:
            from pypdf import PdfReader
            import io

            pdf_file = io.BytesIO(pdf_content)
            reader = PdfReader(pdf_file)

            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

            return "\n\n".join(text_parts)
        except Exception as e:
            return f"Error extracting PDF text: {e}"

    def fetch_and_process(self, url: str) -> Dict[str, Any]:
        """
        Fetch URL and process content for database storage.

        Args:
            url: The URL to fetch

        Returns:
            Dictionary ready for ContentCache model:
                - html_content: compressed bytes
                - markdown_content: str
                - content_hash: str
                - content_length: int
                - compressed_size: int
                - status_code: int
                - response_time_ms: float
                - content_type: str
                - encoding: str
                - title: str (for updating bookmark)
                - success: bool
                - error: str (if failed)
        """
        # Fetch content
        fetch_result = self.fetch(url)

        if not fetch_result["success"]:
            return {
                "success": False,
                "error": fetch_result["error"],
                "status_code": fetch_result["status_code"],
                "html_content": None,
                "markdown_content": None,
                "content_hash": None,
                "content_length": 0,
                "compressed_size": 0,
                "response_time_ms": fetch_result["response_time_ms"],
                "content_type": fetch_result.get("content_type", ""),
                "encoding": fetch_result.get("encoding", "utf-8"),
                "title": None,
            }

        html_content = fetch_result["html_content"]

        # Calculate hash
        content_hash = self.calculate_content_hash(html_content)

        # Compress
        compressed = self.compress_html(html_content)

        # Check if this is a PDF
        content_type = fetch_result.get("content_type", "").lower()
        is_pdf = "application/pdf" in content_type or url.lower().endswith(".pdf")

        if is_pdf:
            # Extract text from PDF
            markdown = self.extract_pdf_text(html_content)
            # Extract title from first line if available
            title = fetch_result.get("title")
            if not title and markdown:
                first_line = markdown.split('\n')[0].strip()
                if first_line and len(first_line) < 200:
                    title = first_line
        else:
            # Convert HTML to markdown
            markdown = self.html_to_markdown(
                html_content, fetch_result.get("encoding", "utf-8")
            )
            title = fetch_result.get("title")

        return {
            "success": True,
            "html_content": compressed,
            "markdown_content": markdown,
            "content_hash": content_hash,
            "content_length": len(html_content),
            "compressed_size": len(compressed),
            "status_code": fetch_result["status_code"],
            "response_time_ms": fetch_result["response_time_ms"],
            "content_type": fetch_result.get("content_type", ""),
            "encoding": fetch_result.get("encoding", "utf-8"),
            "title": title,
            "error": None,
        }


def create_fetcher(**kwargs) -> ContentFetcher:
    """Create a ContentFetcher instance with optional configuration."""
    return ContentFetcher(**kwargs)
