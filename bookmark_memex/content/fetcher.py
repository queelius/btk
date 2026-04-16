"""
HTTP content fetcher for the bookmark-memex content pipeline.

ContentFetcher wraps a requests.Session and provides:
  - fetch()             — raw HTTP fetch, returns metadata + bytes
  - fetch_and_process() — fetch + compress + hash + html_to_markdown
"""

import time
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

from bookmark_memex.content.extractor import (
    compress_html,
    content_hash,
    extract_pdf_text,
    extract_text,
    html_to_markdown,
)

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; bookmark-memex/1.0; +https://github.com/queelius/btk)"
)


class ContentFetcher:
    """Fetch and process web content for bookmark caching."""

    def __init__(
        self,
        timeout: int = 10,
        user_agent: Optional[str] = None,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent or _DEFAULT_USER_AGENT
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    def fetch(self, url: str) -> dict[str, Any]:
        """Fetch *url* and return a result dict.

        Keys:
            success (bool), status_code (int), html_content (bytes),
            title (str), encoding (str), content_type (str),
            response_time_ms (float), error (str | None)
        """
        result: dict[str, Any] = {
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
            t0 = time.time()
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            result["response_time_ms"] = (time.time() - t0) * 1000.0

            result["status_code"] = response.status_code
            result["content_type"] = response.headers.get("Content-Type", "")
            result["encoding"] = response.encoding or "utf-8"

            if response.status_code == 200:
                result["success"] = True
                result["html_content"] = response.content

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
        except Exception as exc:
            result["error"] = str(exc)

        return result

    def fetch_and_process(self, url: str) -> dict[str, Any]:
        """Fetch *url* and return a dict ready for ContentCache storage.

        On success the returned dict includes compressed html_content,
        markdown_content, extracted_text, content_hash, content_length,
        compressed_size, and all fields from fetch().

        On failure success=False, html_content/markdown_content are None.
        """
        fetch_result = self.fetch(url)

        if not fetch_result["success"]:
            return {
                "success": False,
                "error": fetch_result["error"],
                "status_code": fetch_result["status_code"],
                "html_content": None,
                "markdown_content": None,
                "extracted_text": None,
                "content_hash": None,
                "content_length": 0,
                "compressed_size": 0,
                "response_time_ms": fetch_result["response_time_ms"],
                "content_type": fetch_result.get("content_type", ""),
                "encoding": fetch_result.get("encoding", "utf-8"),
                "title": None,
            }

        raw = fetch_result["html_content"]
        hash_val = content_hash(raw)
        compressed = compress_html(raw)

        content_type = fetch_result.get("content_type", "").lower()
        is_pdf = "application/pdf" in content_type or url.lower().endswith(".pdf")

        if is_pdf:
            markdown = extract_pdf_text(raw)
            title = fetch_result.get("title") or None
            if not title and markdown:
                first_line = markdown.split("\n")[0].strip()
                if first_line and len(first_line) < 200:
                    title = first_line
        else:
            markdown = html_to_markdown(raw, fetch_result.get("encoding", "utf-8"))
            title = fetch_result.get("title") or None

        return {
            "success": True,
            "error": None,
            "html_content": compressed,
            "markdown_content": markdown,
            "extracted_text": extract_text(markdown),
            "content_hash": hash_val,
            "content_length": len(raw),
            "compressed_size": len(compressed),
            "status_code": fetch_result["status_code"],
            "response_time_ms": fetch_result["response_time_ms"],
            "content_type": fetch_result.get("content_type", ""),
            "encoding": fetch_result.get("encoding", "utf-8"),
            "title": title,
        }
