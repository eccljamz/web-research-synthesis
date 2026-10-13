"""HTML Parsing, Boilerplate Stripping, and Document Metadata Extraction.

Pure Python standard library implementation using html.parser.HTMLParser.
Zero external dependencies.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    from research_synthesis.models import CleanArticle, DocumentMetadata, RawWebDocument
except ImportError:
    from src.research_synthesis.models import CleanArticle, DocumentMetadata, RawWebDocument

logger = logging.getLogger(__name__)


class RobustHTMLParser(HTMLParser):
    """Zero-dependency HTML parser stripping scripts, styles, navigation, ads, and noise."""

    IGNORE_TAGS = {
        "script", "style", "noscript", "nav", "footer", "header", "aside",
        "form", "button", "iframe", "svg", "canvas", "select", "option",
        "dialog", "menu", "applet", "object", "embed",
    }

    VOID_TAGS = {
        "meta", "link", "img", "br", "hr", "input", "area", "base", "col",
        "embed", "param", "source", "track", "wbr",
    }

    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    BLOCK_TAGS = {"p", "blockquote", "li", "td", "th", "article", "section", "div", "pre"}

    BOILERPLATE_CLASS_ID_KEYWORDS = [
        "cookie", "popup", "newsletter", "sidebar", "banner", "advertisement",
        "ad", "social-share", "share-button", "disclaimer", "nav-item",
        "widget", "modal", "subscribe",
    ]

    _BOILERPLATE_RE = re.compile(
        r"(?:\b|_)(?:"
        r"cookie|cookies|popup|popups|newsletter|sidebar|banner|advertisement|advertisements|advert|"
        r"ad|ads|social-share|share-button|disclaimer|nav-item|widget|modal|subscribe"
        r")(?:\b|_)",
        re.IGNORECASE,
    )

    @classmethod
    def _is_boilerplate(cls, elem_id: str, elem_class: str) -> bool:
        """Check if element ID or class matches boilerplate patterns using boundary-aware regex."""
        if not elem_id and not elem_class:
            return False
        return bool(cls._BOILERPLATE_RE.search(elem_id) or cls._BOILERPLATE_RE.search(elem_class))

    @classmethod
    def _preprocess_html(cls, raw_html: str) -> str:
        """Heuristically patch common catastrophic malformations in raw HTML."""
        if not raw_html:
            return ""
        # 1. Close unclosed <title> tag if next tag appears before </title>
        fixed = re.sub(r"<title>([^<]+?)(?=\s*<|$)", r"<title>\1</title>", raw_html, flags=re.IGNORECASE)
        # 2. Fix unclosed opening tags that run into the next tag without closing '>'
        fixed = re.sub(r"(<[a-zA-Z0-9_-]+(?:\s+[^<>]*)?)(?=\s*<)", r"\1>", fixed)
        return fixed

    @classmethod
    def clean(cls, raw_html: str) -> Tuple[str, Dict[str, Any]]:
        """Parse raw HTML string and return tuple of (cleaned_text, metadata_dict)."""
        preprocessed = cls._preprocess_html(raw_html)
        parser = cls()
        try:
            parser.feed(preprocessed)
            parser._flush_text()
        except Exception:
            pass
        cleaned_text = "\n\n".join(parser.paragraphs)
        meta: Dict[str, Any] = dict(parser.meta_tags)
        if parser.title:
            meta["title"] = parser.title
        if parser.canonical_url:
            meta["canonical_url"] = parser.canonical_url
        return cleaned_text, meta

    def __init__(self):
        super().__init__()
        self._ignore_stack: List[str] = []
        self.tag_stack: List[str] = []
        self.headings: List[str] = []
        self.paragraphs: List[str] = []
        self.title: Optional[str] = None
        self.meta_tags: Dict[str, str] = {}
        self.canonical_url: Optional[str] = None
        self._current_text: List[str] = []
        self._in_title = False

    @property
    def ignore_depth(self) -> int:
        """Backwards-compatible integer property reflecting the depth of the ignore stack."""
        return len(self._ignore_stack)

    @ignore_depth.setter
    def ignore_depth(self, value: int):
        # Compatibility setter if external callers attempt direct assignment
        pass

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        tag_lower = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        # Track title tag
        if tag_lower == "title":
            self._in_title = True
            return

        # Reset title state if unclosed <title> encounters any other tag
        if self._in_title and tag_lower != "title":
            if not self.title:
                title_text = " ".join("".join(self._current_text).split())
                if title_text:
                    self.title = html.unescape(title_text)
            self._current_text = []
            self._in_title = False

        # Close unclosed heading tags when entering block or heading elements
        if tag_lower in self.BLOCK_TAGS or tag_lower in self.HEADING_TAGS:
            self._flush_text()
            while self.tag_stack and self.tag_stack[-1] in self.HEADING_TAGS:
                self.tag_stack.pop()

        # If already inside an ignored subtree, track nested tags to match endtags accurately
        if self._ignore_stack:
            if tag_lower not in self.VOID_TAGS:
                self._ignore_stack.append(tag_lower)
            return

        # Check ignored tag subtrees
        if tag_lower in self.IGNORE_TAGS:
            if tag_lower not in self.VOID_TAGS:
                self._ignore_stack.append(tag_lower)
            return

        # Check boilerplate class or id with boundary-aware regex
        elem_id = attr_dict.get("id", "").lower()
        elem_class = attr_dict.get("class", "").lower()
        if self._is_boilerplate(elem_id, elem_class):
            if tag_lower not in self.VOID_TAGS:
                self._ignore_stack.append(tag_lower)
            return

        # Extract metadata from meta tags
        if tag_lower == "meta":
            prop = attr_dict.get("property") or attr_dict.get("name") or attr_dict.get("http-equiv")
            content = attr_dict.get("content")
            if prop and content:
                self.meta_tags[prop.lower()] = content.strip()

        # Extract canonical URL from link tags
        if tag_lower == "link" and attr_dict.get("rel", "").lower() == "canonical":
            href = attr_dict.get("href")
            if href:
                self.canonical_url = href.strip()

        # Flush text when encountering structural blocks or headings
        if tag_lower in self.BLOCK_TAGS or tag_lower in self.HEADING_TAGS:
            self._flush_text()

        # Avoid pushing void tags (meta, link, img, br, etc.) onto tag_stack
        if tag_lower not in self.VOID_TAGS:
            self.tag_stack.append(tag_lower)

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()

        if tag_lower == "title":
            self._in_title = False
            title_text = " ".join("".join(self._current_text).split())
            if title_text:
                self.title = html.unescape(title_text)
            self._current_text = []
            return

        # If inside an ignored subtree, unwind matching tag from _ignore_stack
        if self._ignore_stack:
            if tag_lower in self._ignore_stack:
                while self._ignore_stack:
                    popped = self._ignore_stack.pop()
                    if popped == tag_lower:
                        break
            return

        if tag_lower in self.BLOCK_TAGS or tag_lower in self.HEADING_TAGS:
            self._flush_text()

        # Unwind tag_stack up to tag_lower to tolerate unclosed inline formatting tags
        if tag_lower in self.tag_stack:
            while self.tag_stack:
                popped = self.tag_stack.pop()
                if popped == tag_lower:
                    break

    def handle_data(self, data: str):
        if self._ignore_stack:
            return
        if self._in_title:
            self._current_text.append(data)
        else:
            self._current_text.append(data)

    def _flush_text(self):
        self._in_title = False
        raw_text = "".join(self._current_text)
        self._current_text = []
        cleaned = " ".join(raw_text.split())
        cleaned = html.unescape(cleaned).strip()

        if not cleaned:
            return

        last_tag = self.tag_stack[-1] if self.tag_stack else None
        is_heading = (last_tag in self.HEADING_TAGS) or any(t in self.HEADING_TAGS for t in self.tag_stack)

        if is_heading:
            # Concise section headings (e.g. "AI", "Overview", "Key Findings") preserved
            if len(cleaned) >= 2 and cleaned not in self.headings:
                self.headings.append(cleaned)
        elif len(cleaned) >= 25:
            # Substantive paragraphs threshold (>= 25 characters) preserved
            if not self.paragraphs or self.paragraphs[-1] != cleaned:
                self.paragraphs.append(cleaned)


class DocumentParser:
    """Orchestrates metadata extraction, boilerplate removal, and CleanArticle synthesis."""

    @staticmethod
    def _clean_title(raw_title: Optional[str]) -> Optional[str]:
        if not raw_title:
            return None
        # Strip common site suffixes like " - The New York Times" or " | TechCrunch"
        title = re.sub(r"\s+[-|–—]\s+[A-Za-z0-9\s\.]+$", "", raw_title).strip()
        return html.unescape(title) if title else None

    @classmethod
    def parse(cls, raw_doc: RawWebDocument) -> CleanArticle:
        """Parse a RawWebDocument into a clean, structured CleanArticle.

        Args:
            raw_doc: The raw retrieved web document.

        Returns:
            CleanArticle with extracted metadata and boilerplate-stripped text.
        """
        parser = RobustHTMLParser()
        try:
            preprocessed = RobustHTMLParser._preprocess_html(raw_doc.raw_html)
            parser.feed(preprocessed)
            parser._flush_text()
        except Exception as err:
            logger.warning(f"HTMLParser error for {raw_doc.url}: {err}. Falling back to text extraction.")
            # Fallback regex extraction if parser feeds encounter catastrophic syntax
            clean_regex = re.sub(r"<[^>]+>", " ", raw_doc.raw_html)
            paragraphs = [p.strip() for p in clean_regex.split("\n") if len(p.strip()) >= 25]
            parser.paragraphs = paragraphs

        parsed_url = urlparse(raw_doc.url)
        domain = parsed_url.netloc.lower() or "unknown_domain"

        # Resolve Canonical URL
        canonical_url = parser.canonical_url or raw_doc.url

        # Resolve Title
        raw_candidate_title = (
            parser.meta_tags.get("og:title")
            or parser.meta_tags.get("twitter:title")
            or parser.title
            or (parser.headings[0] if parser.headings else None)
        )
        resolved_title = cls._clean_title(raw_candidate_title)
        if not resolved_title:
            # Fallback to URL path or domain
            path_part = parsed_url.path.strip("/").split("/")[-1].replace("-", " ").replace("_", " ")
            resolved_title = path_part.title() if path_part else f"Document from {domain}"

        # Resolve Author
        author = (
            parser.meta_tags.get("author")
            or parser.meta_tags.get("article:author")
            or parser.meta_tags.get("twitter:creator")
            or parser.meta_tags.get("dc.creator")
        )
        if author:
            author = html.unescape(author).strip()
        else:
            author = domain

        # Resolve Published Date
        published_date = (
            parser.meta_tags.get("article:published_time")
            or parser.meta_tags.get("date")
            or parser.meta_tags.get("dc.date")
            or parser.meta_tags.get("pubdate")
            or parser.meta_tags.get("article:modified_time")
        )

        cleaned_text = "\n\n".join(parser.paragraphs)
        doc_id = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]

        metadata = DocumentMetadata(
            url=raw_doc.url,
            canonical_url=canonical_url,
            domain=domain,
            title=resolved_title,
            author=author,
            published_date=published_date,
            content_type=raw_doc.headers.get("Content-Type", "text/html"),
            status_code=raw_doc.status_code,
            word_count=len(cleaned_text.split()),
            character_count=len(cleaned_text),
        )

        return CleanArticle(
            doc_id=doc_id,
            url=raw_doc.url,
            metadata=metadata,
            cleaned_text=cleaned_text,
            paragraphs=parser.paragraphs,
            headings=parser.headings,
            subquery_id=raw_doc.subquery_id,
        )
