"""Document Retrieval Clients.

Supports deterministic offline retrieval via MockWebRetrievalClient,
resilient live HTTP fetching via LiveHttpRetrievalClient with exponential
backoff and rate limiting, and seamless failover via CompositeRetrievalClient.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from research_synthesis.models import (
        CleanArticle,
        RawWebDocument,
        RetrievalBatch,
        SubQuery,
    )
    from research_synthesis.retrieval.parser import DocumentParser
    from research_synthesis.retrieval.cache import SQLiteDocumentCache
except ImportError:
    from src.research_synthesis.models import (
        CleanArticle,
        RawWebDocument,
        RetrievalBatch,
        SubQuery,
    )
    from src.research_synthesis.retrieval.parser import DocumentParser
    try:
        from src.research_synthesis.retrieval.cache import SQLiteDocumentCache
    except ImportError:
        SQLiteDocumentCache = None

logger = logging.getLogger(__name__)


# ============================================================================
# Built-in Default Offline Fixture Corpus (Fallback & Fast Testing)
# ============================================================================

DEFAULT_MOCK_CORPUS: Dict[str, Dict[str, Any]] = {
    "https://energy-tech-review.org/solid-state-batteries-2024": {
        "title": "Solid-State Battery Breakthroughs and Energy Density Roadmaps",
        "author": "Dr. Elena Vance",
        "published_date": "2024-03-15",
        "body": (
            "Solid-state battery commercialization has advanced rapidly with sulfide-based solid electrolytes "
            "achieving ionic conductivity surpassing 12 mS/cm at room temperature. Compared to conventional lithium-ion "
            "cells with liquid electrolytes that cap at 280 Wh/kg, solid-state prototypes have demonstrated energy densities "
            "of 450 Wh/kg to 500 Wh/kg. Lithium metal anode integration reduces cell volume by 35% while eliminating flammable "
            "organic solvents. However, dendrite propagation along electrolyte grain boundaries remains a key degradation "
            "mechanism during fast charging cycles above 2C rates."
        ),
    },
    "https://clean-mobility-economics.com/battery-manufacturing-costs": {
        "title": "Manufacturing Cost Parity Analysis: Solid-State vs Lithium-Ion",
        "author": "Marcus Sterling",
        "published_date": "2024-05-20",
        "body": (
            "High-volume manufacturing scaling of solid-state batteries currently faces cost headwinds. Pilot line dry-room "
            "processing costs exceed $180 per kWh, compared to $85 per kWh for mature lithium iron phosphate (LFP) and NMC811 cells. "
            "Scaling bottlenecks center on continuous isostatic pressing and thin-film electrolyte roll-to-roll deposition. "
            "Automotive original equipment manufacturers project commercial cost parity near $100 per kWh will not occur before 2028. "
            "Total capital expenditure for a 20 GWh solid-state gigafactory requires an estimated $2.4 billion."
        ),
    },
    "https://materials-safety-journal.org/dendrites-thermal-runaway": {
        "title": "Degradation Modes and Thermal Safety Benchmarks in Solid Electrolytes",
        "author": "Prof. Kenji Takahashi",
        "published_date": "2024-08-10",
        "body": (
            "Thermal runaway hazards are substantially attenuated in oxide and ceramic electrolytes like LLZO (lithium lanthanum "
            "zirconium oxide), which withstand temperatures up to 800 degrees Celsius without exothermic decomposition. In nail penetration "
            "and crush tests, solid-state cells exhibited zero flame or smoke emission. Nonetheless, critical current density (CCD) "
            "limitations induce micro-void formation at the lithium-electrolyte interface during stripping, leading to rapid impedance "
            "growth and capacity fade after 800 cycles."
        ),
    },
    "https://macro-economics-bulletin.org/supply-chain-reshoring-dynamics": {
        "title": "Global Supply Chain Re-Shoring and Friend-Shoring Trends",
        "author": "Sarah Jenkins",
        "published_date": "2024-02-18",
        "body": (
            "Over 62% of multinational industrial manufacturers surveyed initiated near-shoring or friend-shoring initiatives "
            "to mitigate geopolitical trade frictions and logistics bottlenecks. Industrial policy interventions, including the "
            "US CHIPS and Science Act and the EU Critical Raw Materials Act, disbursed over $95 billion in direct subsidies and tax incentives. "
            "While domestic manufacturing resilience improves, operational costs and wages in reshoring regions increase finished goods "
            "inflation by 3.5% to 6.2% across semiconductor and electronics sectors."
        ),
    },
    "https://industrial-logistics-research.com/semiconductor-reshoring-costs": {
        "title": "Capital Expenditure and Labor Bottlenecks in Reshored Fabrication",
        "author": "David Thorne",
        "published_date": "2024-06-12",
        "body": (
            "Advanced semiconductor fabrication facility construction in North America and Western Europe incurs a 30% to 45% "
            "capital premium over East Asian foundry construction. Skilled cleanroom technician shortages are projected to create "
            "a deficit of 67,000 specialized workers by 2030. Operating expense differentials necessitate sustained tariff protection "
            "or government operational support to avoid margin compression for onshore suppliers."
        ),
    },
    "https://climate-history-archive.org/little-ice-age-climate-shocks": {
        "title": "The Little Ice Age Climate Shocks and 17th Century Agrarian Crises",
        "author": "Dr. Henrik Lindqvist",
        "published_date": "2023-11-04",
        "body": (
            "The 17th century coincided with the Maunder Minimum and intense volcanic aerosol forcing, driving mean summer temperatures "
            "in Western Europe down by 1.2 to 1.8 degrees Celsius. Crop growing seasons contracted by 3 to 5 weeks, causing repeated grain harvest "
            "failures in 1628, 1648, and 1675. Cereal prices surged by over 200% across the Holy Roman Empire, triggering widespread famine, "
            "epidemics of typhus, and profound social unrest during the Thirty Years War."
        ),
    },
    "https://environmental-science-monitor.org/microplastics-agricultural-soils": {
        "title": "Microplastic Bioaccumulation and Soil Ecosystem Ecotoxicology",
        "author": "Dr. Maria Rodriguez",
        "published_date": "2024-04-02",
        "body": (
            "Agricultural soils represent a critical terrestrial sink for microplastic particles, receiving an estimated 44,000 to "
            "300,000 tons of plastic debris annually from plastic mulch films and sewage sludge application. High microplastic concentrations "
            "alter soil bulk density, reduce water retention capacity by 18%, and disrupt earthworm gut microbiomes. Emerging European Union "
            "regulatory directives propose binding limits on synthetic polymers in fertilizing products to halt trophic transfer."
        ),
    },
}


# ============================================================================
# Base Retrieval Client Protocol
# ============================================================================

class BaseRetrievalClient(ABC):
    """Abstract protocol for web document search and retrieval."""

    @abstractmethod
    def search(self, query: str, limit: int = 3) -> List[str]:
        """Search for URLs relevant to query."""
        pass

    @abstractmethod
    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        """Fetch raw HTML document by URL."""
        pass

    def retrieve_for_subqueries(
        self, sub_queries: List[SubQuery], limit_per_subquery: int = 2
    ) -> List[RawWebDocument]:
        """Search and fetch raw web documents for a list of sub-queries."""
        seen_urls: Set[str] = set()
        docs: List[RawWebDocument] = []

        for sq in sub_queries:
            urls = self.search(sq.search_query, limit=limit_per_subquery)
            for url in urls:
                if url not in seen_urls:
                    seen_urls.add(url)
                    doc = self.fetch_url(url)
                    doc.subquery_id = sq.id
                    docs.append(doc)

        return docs


# ============================================================================
# Mock Web Retrieval Client
# ============================================================================

class MockWebRetrievalClient(BaseRetrievalClient):
    """Offline, deterministic retrieval client powered by local fixture catalog."""

    def __init__(
        self,
        corpus_path: Optional[str] = None,
        corpus_dict: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self.corpus_path = str(corpus_path) if corpus_path else None
        self._corpus: Dict[str, Dict[str, Any]] = {}
        self._doc_id_to_url: Dict[str, str] = {}
        if corpus_dict:
            self._corpus.update(corpus_dict)
        self._load_corpus()

    def _load_corpus(self):
        """Load corpus from manifest or HTML files, falling back to built-in fixtures."""
        files_loaded = 0
        if self.corpus_path and os.path.exists(self.corpus_path):
            manifest_file = (
                self.corpus_path
                if os.path.isfile(self.corpus_path)
                else os.path.join(self.corpus_path, "manifest.json")
            )
            if os.path.exists(manifest_file):
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    base_dir = os.path.dirname(manifest_file)
                    # Support either dict of documents or manifest with 'documents' list
                    doc_entries = data.get("documents", data) if isinstance(data, dict) else data
                    items_to_process: List[Tuple[str, Dict[str, Any]]] = []
                    if isinstance(doc_entries, list):
                        for item in doc_entries:
                            if isinstance(item, dict):
                                items_to_process.append(("", item))
                    elif isinstance(doc_entries, dict):
                        for doc_key, item in doc_entries.items():
                            if isinstance(item, dict):
                                items_to_process.append((doc_key, item))

                    for doc_key, item in items_to_process:
                        url = item.get("url", "")
                        if not url and doc_key and (doc_key.startswith("http://") or doc_key.startswith("https://")):
                            url = doc_key
                        if not url and doc_key:
                            url = doc_key

                        if not url:
                            continue

                        filepath = item.get("file_path") or item.get("file") or item.get("path")
                        raw_html = item.get("raw_html", "")

                        if filepath and not raw_html:
                            full_p = os.path.join(base_dir, filepath)
                            if os.path.exists(full_p):
                                try:
                                    with open(full_p, "r", encoding="utf-8") as hf:
                                        raw_html = hf.read()
                                    files_loaded += 1
                                except Exception as read_err:
                                    logger.warning(f"Failed to read fixture file {full_p}: {read_err}")
                            else:
                                logger.debug(f"Fixture file not found: {full_p}")

                        # Extract or fallback body for search indexing
                        body = item.get("body") or item.get("snippet", "")
                        if not body and raw_html:
                            clean_body = re.sub(r"<[^>]+>", " ", raw_html)
                            body = " ".join(clean_body.split())

                        self._corpus[url] = {
                            "doc_id": doc_key or item.get("doc_id", ""),
                            "title": item.get("title", ""),
                            "author": item.get("author", ""),
                            "published_date": item.get("published_date", ""),
                            "domain": item.get("domain", ""),
                            "raw_html": raw_html,
                            "body": body,
                        }
                        if doc_key:
                            self._doc_id_to_url[doc_key] = url
                except Exception as err:
                    logger.warning(f"Failed to load corpus from {manifest_file}: {err}")

        # Fall back to default mock fixtures if corpus is empty or referenced files could not be loaded
        has_substantive_content = any(doc.get("raw_html") or doc.get("body") for doc in self._corpus.values())
        if not self._corpus or not has_substantive_content:
            self._corpus.clear()
            for url, data in DEFAULT_MOCK_CORPUS.items():
                title = data["title"]
                author = data.get("author", "")
                date_val = data.get("published_date", "")
                body = data["body"]
                raw_html = (
                    f"<!DOCTYPE html>\n<html><head>"
                    f"<title>{title}</title>"
                    f'<meta property="og:title" content="{title}">'
                    f'<meta name="author" content="{author}">'
                    f'<meta property="article:published_time" content="{date_val}">'
                    f'<link rel="canonical" href="{url}">'
                    f"</head><body><header><nav><a href='/'>Home</a></nav></header>"
                    f"<main><h1>{title}</h1>"
                    f"<div class='byline'>By {author} on {date_val}</div>"
                    f"<p>{body}</p>"
                    f"</main>"
                    f"<footer><p>Copyright 2024</p></footer>"
                    f"</body></html>"
                )
                self._corpus[url] = {
                    "title": title,
                    "author": author,
                    "published_date": date_val,
                    "body": body,
                    "raw_html": raw_html,
                }

    def search(self, query: str, limit: int = 3) -> List[str]:
        """Search corpus by keyword token overlap."""
        query_tokens = set(re.findall(r"\w+", query.lower()))
        # Filter common stopwords
        stopwords = {"the", "a", "an", "and", "or", "of", "in", "to", "for", "with", "on", "at", "by", "from", "is", "vs"}
        meaningful_query_tokens = query_tokens - stopwords or query_tokens

        scored_urls: List[Tuple[float, str]] = []
        for url, doc in self._corpus.items():
            doc_text = f"{doc.get('title', '')} {doc.get('body', '')} {url}".lower()
            doc_tokens = set(re.findall(r"\w+", doc_text))
            overlap = len(meaningful_query_tokens.intersection(doc_tokens))
            if overlap > 0:
                scored_urls.append((float(overlap), url))

        scored_urls.sort(key=lambda x: x[0], reverse=True)
        results = [url for _, url in scored_urls[:limit]]

        # Fallback to returning top documents if no keyword overlap matched
        if not results and self._corpus:
            results = list(self._corpus.keys())[:limit]
        return results

    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        """Fetch document from offline mock corpus."""
        target_url = url
        doc = self._corpus.get(target_url)
        if doc is None and target_url in self._doc_id_to_url:
            target_url = self._doc_id_to_url[url]
            doc = self._corpus.get(target_url)

        if doc is not None:
            raw_html = doc.get("raw_html")
            if not raw_html:
                title = doc.get("title", "Mock Title")
                body = doc.get("body", "")
                raw_html = (
                    f"<html><head><title>{title}</title></head>"
                    f"<body><p>{body}</p></body></html>"
                )
            return RawWebDocument(
                url=target_url,
                status_code=200,
                headers={"Content-Type": "text/html; charset=utf-8"},
                raw_html=raw_html,
            )

        return RawWebDocument(
            url=url,
            status_code=404,
            headers={},
            raw_html="",
            error=f"URL not found in mock corpus: {url}",
        )


# ============================================================================
# Live HTTP Retrieval Client
# ============================================================================

class LiveHttpRetrievalClient(BaseRetrievalClient):
    """Live HTTP retrieval client with exponential backoff, rate limiting, and size caps."""

    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutonomousResearchBot/1.0"
    MAX_DOWNLOAD_BYTES = 2_000_000  # 2MB safety ceiling against memory exhaustion

    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        rate_limit_delay: float = 0.5,
        user_agent: Optional[str] = None,
        cache: Optional[Any] = None,
    ):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.rate_limit_delay = rate_limit_delay
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.cache = cache
        self._last_request_time: Dict[str, float] = {}
        self._cache: Dict[str, RawWebDocument] = {}

    def _apply_rate_limit(self, domain: str):
        """Enforce domain-level polite rate limiting."""
        now = time.time()
        last_time = self._last_request_time.get(domain, 0.0)
        elapsed = now - last_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time[domain] = time.time()

    def search(self, query: str, limit: int = 3) -> List[str]:
        """Perform search using DuckDuckGo HTML endpoint with optional persistent caching."""
        if self.cache:
            cached_urls = self.cache.get_search(query)
            if cached_urls:
                return cached_urls[:limit]

        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        raw_doc = self.fetch_url(search_url, timeout=10.0)
        if raw_doc.error or not raw_doc.raw_html:
            return []

        # Parse organic result URLs from DuckDuckGo HTML
        urls: List[str] = []
        matches = re.findall(r'<a\s+class="result__url"\s+href="([^"]+)"', raw_doc.raw_html)
        if not matches:
            matches = re.findall(r'<a\s+class="result__snippet[^"]*"\s+href="([^"]+)"', raw_doc.raw_html)

        for match in matches:
            # DuckDuckGo wraps target URLs in /l/?uddg=...
            if "uddg=" in match:
                parsed = urllib.parse.urlparse(match)
                qs = urllib.parse.parse_qs(parsed.query)
                target = qs.get("uddg", [None])[0]
                if target and target.startswith("http"):
                    urls.append(target)
            elif match.startswith("http"):
                urls.append(match)

            if len(urls) >= limit:
                break

        if urls and self.cache:
            self.cache.put_search(query, urls)

        return urls

    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        """Fetch URL with retry, exponential backoff, rate limit, and MIME checks."""
        if url in self._cache:
            return self._cache[url]

        if self.cache:
            cached_doc = self.cache.get_document(url)
            if cached_doc:
                self._cache[url] = cached_doc
                return cached_doc

        domain = urllib.parse.urlparse(url).netloc.lower()
        if domain:
            self._apply_rate_limit(domain)

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        req = urllib.request.Request(url, headers=headers)

        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    status_code = response.getcode()
                    content_type = response.headers.get("Content-Type", "")

                    # Verify MIME type is text/html or text/plain
                    if "text/html" not in content_type and "text/plain" not in content_type and "xml" not in content_type:
                        doc = RawWebDocument(
                            url=url,
                            status_code=status_code,
                            headers=dict(response.headers),
                            raw_html="",
                            error=f"Skipping non-text MIME type: {content_type}",
                        )
                        self._cache[url] = doc
                        if self.cache:
                            self.cache.put_document(doc)
                        return doc

                    # Stream read up to MAX_DOWNLOAD_BYTES
                    raw_bytes = response.read(self.MAX_DOWNLOAD_BYTES)
                    raw_html = raw_bytes.decode("utf-8", errors="replace")

                    doc = RawWebDocument(
                        url=url,
                        status_code=status_code,
                        headers=dict(response.headers),
                        raw_html=raw_html,
                    )
                    self._cache[url] = doc
                    if self.cache:
                        self.cache.put_document(doc)
                    return doc

            except urllib.error.HTTPError as err:
                # Retry transient 429 and 5xx errors
                if (err.code == 429 or 500 <= err.code <= 504) and attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2 ** attempt)
                    time.sleep(sleep_time)
                    continue

                # Permanent failure or retries exhausted
                doc = RawWebDocument(
                    url=url,
                    status_code=err.code,
                    headers=dict(err.headers) if hasattr(err, "headers") else {},
                    raw_html="",
                    error=f"HTTPError: {err.code} {err.reason}",
                )
                self._cache[url] = doc
                return doc

            except (urllib.error.URLError, TimeoutError, OSError) as err:
                if attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2 ** attempt)
                    time.sleep(sleep_time)
                    continue

                doc = RawWebDocument(
                    url=url,
                    status_code=0,
                    headers={},
                    raw_html="",
                    error=f"URLError: {str(err)}",
                )
                self._cache[url] = doc
                return doc

            except Exception as err:
                doc = RawWebDocument(
                    url=url,
                    status_code=0,
                    headers={},
                    raw_html="",
                    error=f"Unexpected error: {str(err)}",
                )
                self._cache[url] = doc
                return doc

        return RawWebDocument(
            url=url,
            status_code=0,
            headers={},
            raw_html="",
            error="Max retries exceeded",
        )


# ============================================================================
# Additional Search Engine Clients (Wikipedia & DuckDuckGo Lite)
# ============================================================================

class DuckDuckGoLiteRetrievalClient(BaseRetrievalClient):
    """Fallback search client querying DuckDuckGo Lite endpoint without JavaScript."""

    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutonomousResearchBot/1.0"

    def __init__(self, user_agent: Optional[str] = None, timeout: float = 8.0):
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.timeout = timeout
        self.fetcher = LiveHttpRetrievalClient(user_agent=self.user_agent)

    def search(self, query: str, limit: int = 3) -> List[str]:
        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"https://lite.duckduckgo.com/lite/?q={encoded_query}"
        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                html = resp.read(500_000).decode("utf-8", errors="replace")
            urls: List[str] = []
            for match in re.findall(r'<a\s+[^>]*class="result-link"[^>]*href="([^"]+)"', html):
                if match.startswith("http"):
                    urls.append(match)
                elif "uddg=" in match:
                    parsed = urllib.parse.urlparse(match)
                    target = urllib.parse.parse_qs(parsed.query).get("uddg", [None])[0]
                    if target and target.startswith("http"):
                        urls.append(target)
                if len(urls) >= limit:
                    break
            return urls
        except Exception as e:
            logger.debug(f"DuckDuckGo Lite search failed: {e}")
            return []

    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        return self.fetcher.fetch_url(url, timeout=timeout)


class WikipediaRetrievalClient(BaseRetrievalClient):
    """Encyclopedic search & retrieval client querying Wikipedia OpenSearch API."""

    API_URL = "https://en.wikipedia.org/w/api.php"
    DEFAULT_USER_AGENT = "ResearchSynthesisBot/1.0 (https://github.com/example/research; info@example.org)"

    def __init__(self, user_agent: Optional[str] = None, timeout: float = 8.0):
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.timeout = timeout
        self.fetcher = LiveHttpRetrievalClient(user_agent=self.user_agent)

    def search(self, query: str, limit: int = 3) -> List[str]:
        """Query Wikipedia OpenSearch API for matching article URLs."""
        params = {
            "action": "opensearch",
            "search": query,
            "limit": str(limit),
            "namespace": "0",
            "format": "json",
        }
        url = f"{self.API_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if len(data) >= 4 and isinstance(data[3], list):
                return data[3][:limit]
            return []
        except Exception as e:
            logger.debug(f"Wikipedia search failed: {e}")
            return []

    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        return self.fetcher.fetch_url(url, timeout=timeout)


class ArxivRetrievalClient(BaseRetrievalClient):
    """Academic literature retrieval client querying the arXiv Atom API (export.arxiv.org).

    Uses standard library urllib.request and xml.etree.ElementTree to query arXiv Atom feeds,
    extracting publication titles, authors, publication dates, and paper abstracts.
    """

    API_URL = "https://export.arxiv.org/api/query"
    ATOM_NS = "{http://www.w3.org/2005/Atom}"
    DEFAULT_USER_AGENT = "AutonomousResearchBot/1.0 (academic-research; mailto:research@example.org)"

    def __init__(
        self,
        user_agent: Optional[str] = None,
        timeout: float = 10.0,
        cache: Optional[Any] = None,
    ):
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.timeout = timeout
        self.cache = cache
        self.fetcher = LiveHttpRetrievalClient(user_agent=self.user_agent)
        self._entry_cache: Dict[str, Dict[str, Any]] = {}

    def can_handle(self, url: str) -> bool:
        """Check if URL is an arXiv paper or cached by this client."""
        return "arxiv.org" in url.lower() or url in self._entry_cache

    def _find_text(self, elem: Any, tag_name: str) -> str:
        for child in elem:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag.lower() == tag_name.lower():
                return (child.text or "").strip()
        return ""

    def search(self, query: str, limit: int = 3) -> List[str]:
        """Query arXiv Atom API and return paper URLs."""
        if self.cache and hasattr(self.cache, "get_search"):
            cached_urls = self.cache.get_search(f"arxiv:{query}")
            if cached_urls:
                return cached_urls[:limit]

        safe_query = re.sub(r"[^\w\s-]", " ", query).strip()
        search_terms = " AND ".join(safe_query.split()) if safe_query else "all"
        params = {
            "search_query": f"all:{search_terms}",
            "start": "0",
            "max_results": str(max(1, limit)),
        }
        url = f"{self.API_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/atom+xml,application/xml,text/xml",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                xml_data = resp.read()

            root = ET.fromstring(xml_data)
            urls: List[str] = []

            for child in root:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag.lower() != "entry":
                    continue

                entry_id = self._find_text(child, "id")
                title = re.sub(r"\s+", " ", self._find_text(child, "title")).strip() or "Untitled arXiv Paper"
                summary = re.sub(r"\s+", " ", self._find_text(child, "summary")).strip()
                published = self._find_text(child, "published")
                if published and "T" in published:
                    published = published.split("T")[0]

                authors: List[str] = []
                for sub in child:
                    sub_tag = sub.tag.split("}")[-1] if "}" in sub.tag else sub.tag
                    if sub_tag.lower() == "author":
                        name = self._find_text(sub, "name")
                        if name:
                            authors.append(name)

                # Locate canonical abstract or alternate link
                paper_url = ""
                for link in child:
                    l_tag = link.tag.split("}")[-1] if "}" in link.tag else link.tag
                    if l_tag.lower() == "link":
                        if link.get("rel") == "alternate" and link.get("href"):
                            paper_url = link.get("href")
                            break
                        if not paper_url and link.get("href", "").startswith("http"):
                            paper_url = link.get("href")

                if not paper_url:
                    paper_url = entry_id

                if paper_url:
                    urls.append(paper_url)
                    self._entry_cache[paper_url] = {
                        "url": paper_url,
                        "title": title,
                        "authors": ", ".join(authors) if authors else "arXiv Contributor",
                        "published_date": published,
                        "summary": summary,
                    }

                if len(urls) >= limit:
                    break

            if urls and self.cache and hasattr(self.cache, "put_search"):
                self.cache.put_search(f"arxiv:{query}", urls)

            return urls
        except Exception as e:
            logger.debug(f"arXiv search failed: {e}")
            return []

    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        """Fetch paper abstract and metadata as structured HTML document."""
        entry = self._entry_cache.get(url)
        if entry:
            title = entry.get("title", "arXiv Paper")
            authors = entry.get("authors", "")
            date_str = entry.get("published_date", "")
            summary = entry.get("summary", "")
            raw_html = (
                f"<!DOCTYPE html>\n"
                f"<html lang=\"en\"><head>\n"
                f"<title>{html.escape(title)}</title>\n"
                f'<meta name="author" content="{html.escape(authors)}">\n'
                f'<meta property="article:published_time" content="{html.escape(date_str)}">\n'
                f'<link rel="canonical" href="{html.escape(url)}">\n'
                f"</head><body><main>\n"
                f"<h1>{html.escape(title)}</h1>\n"
                f'<div class="byline">By {html.escape(authors)} on {html.escape(date_str)}</div>\n'
                f'<div class="abstract"><p>{html.escape(summary)}</p></div>\n'
                f"</main></body></html>"
            )
            return RawWebDocument(
                url=url,
                status_code=200,
                headers={"Content-Type": "text/html; charset=utf-8"},
                raw_html=raw_html,
            )

        return self.fetcher.fetch_url(url, timeout=timeout)


class PubMedRetrievalClient(BaseRetrievalClient):
    """Biomedical and life sciences literature client querying NCBI E-utilities (PubMed).

    Uses standard library urllib.request and json to query:
    1. esearch.fcgi to retrieve PMIDs
    2. esummary.fcgi to retrieve structured article metadata
    """

    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    DEFAULT_USER_AGENT = "AutonomousResearchBot/1.0 (biomedical-research; mailto:research@example.org)"

    def __init__(
        self,
        user_agent: Optional[str] = None,
        timeout: float = 10.0,
        cache: Optional[Any] = None,
    ):
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.timeout = timeout
        self.cache = cache
        self.fetcher = LiveHttpRetrievalClient(user_agent=self.user_agent)
        self._entry_cache: Dict[str, Dict[str, Any]] = {}

    def can_handle(self, url: str) -> bool:
        """Check if URL is a PubMed article or cached by this client."""
        return "pubmed.ncbi.nlm.nih.gov" in url.lower() or url in self._entry_cache

    def search(self, query: str, limit: int = 3) -> List[str]:
        """Query NCBI ESearch + ESummary for PubMed articles."""
        if self.cache and hasattr(self.cache, "get_search"):
            cached_urls = self.cache.get_search(f"pubmed:{query}")
            if cached_urls:
                return cached_urls[:limit]

        # Step 1: ESearch to get PMIDs
        search_params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": str(max(1, limit)),
        }
        esearch_url = f"{self.ESEARCH_URL}?{urllib.parse.urlencode(search_params)}"
        req = urllib.request.Request(esearch_url, headers={"User-Agent": self.user_agent})

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                search_data = json.loads(resp.read().decode("utf-8"))

            id_list = search_data.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                return []

            # Step 2: ESummary to get article summaries
            summary_params = {
                "db": "pubmed",
                "id": ",".join(id_list),
                "retmode": "json",
            }
            esummary_url = f"{self.ESUMMARY_URL}?{urllib.parse.urlencode(summary_params)}"
            req_sum = urllib.request.Request(esummary_url, headers={"User-Agent": self.user_agent})

            with urllib.request.urlopen(req_sum, timeout=self.timeout) as resp_sum:
                sum_data = json.loads(resp_sum.read().decode("utf-8"))

            results_dict = sum_data.get("result", {})
            urls: List[str] = []

            for pmid in id_list:
                item = results_dict.get(pmid)
                if not item:
                    continue
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                title = item.get("title", f"PubMed Article {pmid}")
                pubdate = item.get("pubdate", "")
                source = item.get("source", "")
                authors_list = [
                    a.get("name", "")
                    for a in item.get("authors", [])
                    if isinstance(a, dict) and a.get("name")
                ]
                authors_str = ", ".join(authors_list) if authors_list else "PubMed Contributor"

                urls.append(url)
                self._entry_cache[url] = {
                    "url": url,
                    "title": title,
                    "authors": authors_str,
                    "published_date": pubdate,
                    "source": source,
                    "summary": f"{title}. Published in {source} ({pubdate}).",
                }

                if len(urls) >= limit:
                    break

            if urls and self.cache and hasattr(self.cache, "put_search"):
                self.cache.put_search(f"pubmed:{query}", urls)

            return urls
        except Exception as e:
            logger.debug(f"PubMed search failed: {e}")
            return []

    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        """Fetch article abstract and metadata as structured HTML document."""
        entry = self._entry_cache.get(url)
        if entry:
            title = entry.get("title", "PubMed Article")
            authors = entry.get("authors", "")
            date_str = entry.get("published_date", "")
            summary = entry.get("summary", "")
            source = entry.get("source", "")
            raw_html = (
                f"<!DOCTYPE html>\n"
                f"<html lang=\"en\"><head>\n"
                f"<title>{html.escape(title)}</title>\n"
                f'<meta name="author" content="{html.escape(authors)}">\n'
                f'<meta property="article:published_time" content="{html.escape(date_str)}">\n'
                f'<link rel="canonical" href="{html.escape(url)}">\n'
                f"</head><body><main>\n"
                f"<h1>{html.escape(title)}</h1>\n"
                f'<div class="byline">By {html.escape(authors)} on {html.escape(date_str)} | {html.escape(source)}</div>\n'
                f'<div class="abstract"><p>{html.escape(summary)}</p></div>\n'
                f"</main></body></html>"
            )
            return RawWebDocument(
                url=url,
                status_code=200,
                headers={"Content-Type": "text/html; charset=utf-8"},
                raw_html=raw_html,
            )

        return self.fetcher.fetch_url(url, timeout=timeout)


# ============================================================================
# Composite Failover Retrieval Client
# ============================================================================

class CompositeRetrievalClient(BaseRetrievalClient):
    """Transparent failover client: tries Live, falls back seamlessly to Mock."""

    def __init__(
        self,
        live_client: Optional[LiveHttpRetrievalClient] = None,
        mock_client: Optional[MockWebRetrievalClient] = None,
        fallback_clients: Optional[List[BaseRetrievalClient]] = None,
        offline_mode: bool = False,
    ):
        self.live_client = live_client or LiveHttpRetrievalClient()
        self.mock_client = mock_client or MockWebRetrievalClient()
        self.fallback_clients = (
            fallback_clients
            if fallback_clients is not None
            else [
                ArxivRetrievalClient(),
                PubMedRetrievalClient(),
                DuckDuckGoLiteRetrievalClient(),
                WikipediaRetrievalClient(),
            ]
        )
        self.offline_mode = offline_mode

    def search(self, query: str, limit: int = 3) -> List[str]:
        """Search query, attempting live first, then fallback engines, and falling back to mock."""
        if not self.offline_mode:
            try:
                results = self.live_client.search(query, limit=limit)
                if results:
                    return results
            except Exception as err:
                logger.warning(f"Live search failed: {err}. Falling back to mock corpus.")
                self.offline_mode = True

            if not self.offline_mode:
                for fb in self.fallback_clients:
                    try:
                        results = fb.search(query, limit=limit)
                        if results:
                            return results
                    except Exception as fb_err:
                        logger.debug(f"Fallback search engine failed: {fb_err}")

        return self.mock_client.search(query, limit=limit)

    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        """Fetch URL, attempting live first and falling back to mock upon failure."""
        if not self.offline_mode:
            # First check if any fallback client can handle this specific URL or has it cached
            for fb in self.fallback_clients:
                if hasattr(fb, "can_handle") and fb.can_handle(url):
                    try:
                        doc = fb.fetch_url(url, timeout=timeout)
                        if not doc.error and doc.raw_html:
                            return doc
                    except Exception as fb_err:
                        logger.debug(f"Specialized client fetch failed for {url}: {fb_err}")

            try:
                doc = self.live_client.fetch_url(url, timeout=timeout)
                if not doc.error and doc.raw_html:
                    return doc
                logger.info(f"Live fetch produced error ({doc.error}), falling back to mock for {url}")
            except Exception as err:
                logger.warning(f"Live fetch failed for {url}: {err}. Falling back to mock.")

        return self.mock_client.fetch_url(url, timeout=timeout)

    def retrieve_batch(
        self,
        topic: str,
        sub_queries: List[SubQuery],
        parser: Optional[DocumentParser] = None,
        limit_per_subquery: int = 2,
    ) -> RetrievalBatch:
        """Execute end-to-end retrieval and parsing for a topic and sub-queries.

        Args:
            topic: Research topic string.
            sub_queries: List of decomposed SubQuery instances.
            parser: DocumentParser instance (defaults to DocumentParser).
            limit_per_subquery: Maximum URLs to retrieve per sub-query.

        Returns:
            RetrievalBatch containing cleaned articles and retrieval metadata.
        """
        start_time = time.time()
        active_parser = parser or DocumentParser()

        seen_urls: Set[str] = set()
        cleaned_articles: List[CleanArticle] = []
        failed_urls: List[Dict[str, str]] = []
        total_fetched = 0

        for sq in sub_queries:
            urls = self.search(sq.search_query, limit=limit_per_subquery)
            for url in urls:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                total_fetched += 1

                raw_doc = self.fetch_url(url)
                raw_doc.subquery_id = sq.id

                if raw_doc.error or not raw_doc.raw_html:
                    failed_urls.append({"url": url, "error": raw_doc.error or "Empty payload"})
                    continue

                article = active_parser.parse(raw_doc)
                article.subquery_id = sq.id
                article.subquery_facet = sq.facet
                cleaned_articles.append(article)

        execution_time = time.time() - start_time

        return RetrievalBatch(
            topic=topic,
            sub_queries=sub_queries,
            documents=cleaned_articles,
            failed_urls=failed_urls,
            total_fetched=total_fetched,
            total_cleaned=len(cleaned_articles),
            cache_hits=0,
            execution_time_seconds=execution_time,
        )
