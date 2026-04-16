"""
Pure content processing functions — no network, no state.

All functions operate on bytes or strings and are safe to call from any
context. Import cost is low; pypdf is lazy-imported only when needed.
"""

import re
import zlib
import hashlib
from typing import Optional


def compress_html(html_content: bytes) -> bytes:
    """Compress with zlib level 9."""
    return zlib.compress(html_content, level=9)


def decompress_html(compressed: bytes) -> bytes:
    """Decompress zlib-compressed bytes."""
    return zlib.decompress(compressed)


def content_hash(data: bytes) -> str:
    """SHA-256 hex digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def html_to_markdown(html_content: bytes, encoding: str = "utf-8") -> str:
    """Convert HTML to markdown.

    Strips script/style/nav/footer/header elements.  Locates the main
    content container (main, article, div.content, div#content, body) and
    converts it to ATX-heading markdown via markdownify.

    Returns an empty string on empty input or on any conversion error.
    """
    if not html_content:
        return ""

    try:
        from bs4 import BeautifulSoup
        from markdownify import markdownify as md

        html_str = html_content.decode(encoding, errors="replace")
        soup = BeautifulSoup(html_str, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_="content")
            or soup.find("div", id="content")
            or soup.find("body")
        )

        if main_content is None:
            return ""

        markdown = md(
            str(main_content),
            heading_style="ATX",
            bullets="-",
            strip=["a"],
        )
        return markdown.strip()

    except Exception:
        return ""


def extract_text(markdown_content: str) -> str:
    """Strip markdown formatting for FTS indexing.

    Removes heading markers, bold/italic markers, link syntax, and inline
    code backticks.  Collapses multiple consecutive blank lines into one.
    Returns an empty string when given an empty string.
    """
    if not markdown_content:
        return ""

    text = markdown_content

    # Remove ATX headings markers (# ## ### …)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Remove bold (**…** and __…__)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)

    # Remove italic (*…* and _…_)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"_(.*?)_", r"\1", text)

    # Remove link syntax [text](url) → text
    text = re.sub(r"\[([^\]]*)\]\([^\)]*\)", r"\1", text)

    # Remove inline code backticks
    text = re.sub(r"`([^`]*)`", r"\1", text)

    # Collapse 3+ consecutive newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_pdf_text(pdf_content: bytes) -> str:
    """Extract text from PDF bytes.

    Requires the *pypdf* package (optional dependency).  Returns an error
    string on failure rather than raising, so callers can treat the result
    uniformly as a string.
    """
    try:
        import io
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_content))
        parts = [page.extract_text() for page in reader.pages if page.extract_text()]
        return "\n\n".join(parts)
    except Exception as exc:
        return f"Error extracting PDF text: {exc}"
