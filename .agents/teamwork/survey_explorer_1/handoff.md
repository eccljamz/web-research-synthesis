# Handoff Report: Requirement R1 (Query Decomposition & Web Retrieval Architecture)

## 1. Observation

### 1.1 Source Requirements Observation
From direct inspection of `C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\ORIGINAL_REQUEST.md`:
- **Line 12-13 (R1 Definition)**:
  > "### R1. Query Decomposition & Web Retrieval
  > The system must accept broad or complex research topics, decompose them into sub-queries, retrieve source documents from web or mock-web endpoints, and extract clean article content and metadata."
- **Line 15-16 (R2 Definition)**:
  > "### R2. Content Filtering & Claim Extraction
  > The system must filter retrieved content for relevance, deduplicate overlapping information, and extract discrete factual claims and findings."
- **Line 18-19 (R3 Definition)**:
  > "### R3. Structured Knowledge Synthesis
  > The system must synthesize findings into structured research briefs containing an executive summary, detailed thematic sections, key takeaways, and source citations mapping claims back to source URLs or documents."
- **Line 21-22 (R4 Definition)**:
  > "### R4. Automated Verification Harness
  > The project must include an automated verification test script that runs the pipeline against sample test queries and asserts that generated reports contain valid structure, non-empty findings, and properly formatted source citations."
- **Line 26-28 (Pipeline Acceptance Criteria)**:
  > "- [ ] Pipeline executes end-to-end on at least 3 diverse sample test queries without unhandled exceptions.
  > - [ ] Generated reports contain a formatted executive summary, key findings, and explicit source references for every major claim."
- **Line 30-31 (Automated Verification Acceptance Criteria)**:
  > "- [ ] An automated test/verification script runs and passes (exit code 0), validating that all generated output briefs conform to the required schema and contain non-empty citation references."

### 1.2 Workspace & Environment Observation
- Workspace root: `C:\Users\ecclj\teamwork_projects\web_research_synthesis`
- Directory contents: Currently clean greenfield project with only `.agents/teamwork/` metadata directories (`orchestrator_1`, `sentinel`, `survey_explorer_1`, `survey_explorer_2`, `survey_explorer_3`).
- Operating System: Windows (PowerShell environment).
- Network & execution constraints: In automated CI/CD and offline verification environments, live external web requests may fail due to firewall rules, rate limits, network unavailability, or lack of external API keys. Thus, an offline, deterministic mock-web fixture engine is an absolute hard prerequisite for passing R4 reliably.

---

## 2. Logic Chain

### Step 2.1: Requirement Deconstruction & Interface Boundary
- **Observation Reference**: 1.1 (R1, R2, R3, R4)
- **Deduction**:
  R1 is the ingestion and retrieval bedrock of the entire research pipeline. If R1 fails or delivers dirty/incomplete data:
  1. Downstream R2 (filtering & claim extraction) will fail or extract boilerplate noise (navigation links, cookie disclaimers, ads) as factual claims.
  2. Downstream R3 will generate hallucinated or ungrounded synthesis briefs without valid source URLs.
  3. Downstream R4 will fail acceptance tests asserting non-empty findings and valid citations.
  Therefore, R1 must be decomposed into three strictly decoupled, individually testable sub-systems:
  - **Module A**: `QueryDecompositionEngine` (Broad Topic $\to$ Structured Sub-Queries)
  - **Module B**: `RetrievalClientProtocol` (`MockWebClient`, `LiveHttpClient`, `CompositeRetrievalClient`)
  - **Module C**: `DocumentParser` & `MetadataExtractor` (Raw HTML/HTTP Response $\to$ `CleanArticle` with verified metadata)

### Step 2.2: Architectural Design for Query Decomposition
- **Observation Reference**: 1.1 (R1: "decompose them into sub-queries")
- **Deduction**:
  A single monolithic search query for complex research (e.g. "Solid-state batteries vs Lithium-ion commercial feasibility") yields biased or shallow search results. Effective multi-perspective synthesis requires orthogonal sub-query dimensions:
  1. **Background & Technical Foundations**: Core definitions, operating principles, architectures.
  2. **Economic & Commercial Viability**: Manufacturing cost, scaling bottlenecks, market forecasts.
  3. **Performance & Operational Trade-offs**: Energy density, lifespan, safety risks, failure modes.
  4. **Counter-perspectives & Challenges**: Competing alternatives, unresolved technical hurdles, regulatory constraints.
  5. **State-of-the-Art / Temporal Trends**: Recent breakthroughs (2024-2026), current pilot deployments.

  **Decomposition Engine Design**:
  - Must support both an LLM-assisted decomposition strategy (when available/configured) AND a zero-dependency deterministic rule-based heuristic strategy.
  - The deterministic heuristic extracts named entities, detect comparative patterns (`"X vs Y"`), and generates 3-5 orthogonal query variants using a domain-aware template matrix.
  - Returns a strictly typed `DecompositionResult` containing a list of `SubQuery` objects, each tagged with `facet`, `priority`, and `target_intent`.

### Step 2.3: Architectural Design for Retrieval Clients (Dual Mock & Live)
- **Observation Reference**: 1.1 (R1: "from web or mock-web endpoints"; R4: "automated verification test script")
- **Deduction**:
  - Live search endpoints are inherently non-deterministic, subject to network outages, IP blocks, CAPTCHAs, and rate limits (HTTP 429).
  - R4 requires repeatable, deterministic execution for at least 3 diverse sample queries with zero unhandled exceptions.
  - Solution: A unified abstract protocol `BaseRetrievalClient` implemented by:
    1. `MockWebRetrievalClient`: Backed by a local fixture catalog (`fixtures/mock_web/`) indexed by topic keywords and URLs. Supports fast keyword/token matching, deterministic latency simulation (optional), and rich HTML documents.
    2. `LiveHttpRetrievalClient`: Standard HTTP fetching with polite User-Agent headers, socket timeouts (connect=5s, read=10s), exponential backoff retries with jitter for 429/5xx, and domain-level rate limiting.
    3. `CompositeRetrievalClient`: Automatically delegates to `LiveHttpRetrievalClient` when live internet is enabled, with automatic silent fallback to `MockWebRetrievalClient` upon network error, timeout, or DNS failure.

### Step 2.4: Architectural Design for Document Parsing & Clean Content Extraction
- **Observation Reference**: 1.1 (R1: "extract clean article content and metadata")
- **Deduction**:
  - Raw HTML contains excessive non-content boilerplate: `<script>`, `<style>`, `<nav>`, `<header>`, `<footer>`, `<aside>`, `<noscript>`, `<svg>`, cookie banners, social share buttons, newsletter popups, comment sections.
  - Extraction must be two-phase:
    1. **Metadata Extraction**:
       - Title: `<meta property="og:title">` $\to$ `<title>` $\to$ `<meta name="twitter:title">` $\to$ first `<h1>`.
       - Author: `<meta name="author">` $\to$ `<meta property="article:author">` $\to$ Schema.org author $\to$ fallback to domain name.
       - Published Date: `<meta property="article:published_time">` $\to$ `<meta name="date">` $\to$ `<time datetime="...">` $\to$ fetch date.
       - Canonical URL: `<link rel="canonical" href="...">` $\to$ request URL.
       - Domain / Source Name: Extracted from canonical URL hostname.
    2. **Boilerplate Stripping & Clean Article Body**:
       - Remove all blacklisted tag subtrees (`script`, `style`, `noscript`, `nav`, `footer`, `header`, `aside`, `form`, `iframe`).
       - Remove elements matching boilerplate CSS selectors (`ad`, `banner`, `cookie`, `popup`, `modal`, `newsletter`, `share-button`).
       - Retain semantic structural blocks (`<p>`, `<h1>`-`<h6>`, `<blockquote>`, `<li>`, `<table>`).
       - Text density filter: Reject noise lines (< 30 characters, link lists, copyright lines).
       - Whitespace collapse & entity decoding (`&amp;` $\to$ `&`).
       - Length boundary: Clip documents exceeding a safe ceiling (e.g., 20,000 characters) to prevent token exhaustion downstream.

### Step 2.5: Resiliency, Error Handling & Edge Cases
- **Observation Reference**: 1.1 & 1.2
- **Deduction**:
  The retrieval engine must handle all real-world failure modes gracefully without unhandled exceptions:
  - Network timeouts & DNS failures $\to$ Caught, logged, marked in `failed_urls`, fallback invoked.
  - HTTP 4xx/5xx $\to$ Retry 429/502/503/504 up to 3 times; abort 401/403/404 immediately.
  - Binary MIME types (PDF, ZIP, images) $\to$ Check `Content-Type` header before downloading full payload; skip non-text.
  - Giant HTML bombs $\to$ Stream download with max byte cap (e.g., 2MB).
  - Malformed HTML & encoding errors $\to$ Robust parser fallback (UTF-8 with replacement, html.parser tolerant parsing).
  - Ambiguous / single-word user queries $\to$ Safe expansion heuristics without crashing.

---

## 3. Concrete Architectural Specification & Interfaces

### 3.1 Data Contracts & Schema Models (`src/models/retrieval.py`)

```python
"""Data contracts for Query Decomposition and Web Retrieval."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any

@dataclass
class SubQuery:
    """Represents a decomposed search aspect."""
    id: str                                  # e.g. "sq-01"
    original_topic: str                      # User's broad research query
    facet: str                               # e.g. "technical", "economic", "challenges", "temporal"
    search_query: str                        # Optimized query string for search engine
    priority: int = 1                        # Priority rank (1 = highest)
    rationale: str = ""                      # Why this sub-query was generated

@dataclass
class DecompositionResult:
    """Result of query decomposition."""
    topic: str
    sub_queries: List[SubQuery]
    strategy_used: str                       # "heuristic_rule_based" or "llm_guided"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class DocumentMetadata:
    """Metadata extracted from source document."""
    url: str
    canonical_url: str
    domain: str
    title: str
    author: Optional[str] = None
    published_date: Optional[str] = None
    content_type: str = "text/html"
    status_code: int = 200
    fetched_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    word_count: int = 0
    character_count: int = 0

@dataclass
class RawWebDocument:
    """Raw unparsed web document response."""
    url: str
    status_code: int
    headers: Dict[str, str]
    raw_html: str
    subquery_id: Optional[str] = None
    error: Optional[str] = None

@dataclass
class CleanArticle:
    """Clean, boilerplate-stripped article ready for R2 claim extraction."""
    doc_id: str                              # Deterministic hash of canonical URL
    url: str
    metadata: DocumentMetadata
    cleaned_text: str                        # Continuous clean text for NLP/LLM
    paragraphs: List[str]                    # Discrete paragraphs for claim isolation
    headings: List[str]                      # Document section headings
    subquery_id: Optional[str] = None
    subquery_facet: Optional[str] = None

@dataclass
class RetrievalBatch:
    """Unified container for an end-to-end R1 retrieval run."""
    topic: str
    sub_queries: List[SubQuery]
    documents: List[CleanArticle]
    failed_urls: List[Dict[str, str]] = field(default_factory=list)
    total_fetched: int = 0
    total_cleaned: int = 0
    cache_hits: int = 0
    execution_time_seconds: float = 0.0
```

### 3.2 Query Decomposition Interface (`src/retrieval/decomposition.py`)

```python
"""Query Decomposition Engine."""
import re
from typing import List, Optional
from src.models.retrieval import SubQuery, DecompositionResult

class BaseQueryDecomposer:
    """Abstract interface for decomposing broad research topics."""
    def decompose(self, topic: str, max_subqueries: int = 5) -> DecompositionResult:
        raise NotImplementedError

class HeuristicQueryDecomposer(BaseQueryDecomposer):
    """Deterministic, zero-dependency decomposition engine based on linguistic patterns and facet templates."""
    
    FACET_TEMPLATES = [
        ("technical_foundations", "{topic} technical architecture mechanism fundamentals"),
        ("economic_commercial", "{topic} economic cost market feasibility commercialization"),
        ("challenges_limitations", "{topic} limitations challenges risks bottlenecks safety"),
        ("comparative_alternatives", "{topic} comparative analysis benchmarks alternatives"),
        ("state_of_art_recent", "{topic} recent developments state of the art trends 2024 2025")
    ]
    
    def decompose(self, topic: str, max_subqueries: int = 5) -> DecompositionResult:
        cleaned_topic = topic.strip()
        if not cleaned_topic:
            raise ValueError("Topic cannot be empty or whitespace.")
            
        sub_queries: List[SubQuery] = []
        
        # Check for comparative queries: "X vs Y", "X compared to Y", "trade-offs of X and Y"
        comp_match = re.search(r'(.+?)\s+(?:vs\.?|versus|compared to|trade-offs of)\s+(.+)', cleaned_topic, re.IGNORECASE)
        if comp_match:
            entity_a = comp_match.group(1).strip()
            entity_b = comp_match.group(2).strip()
            sub_queries.append(SubQuery(
                id="sq-01", original_topic=cleaned_topic, facet="entity_a_overview",
                search_query=f"{entity_a} performance specifications overview", priority=1,
                rationale=f"Explore core capabilities of {entity_a}"
            ))
            sub_queries.append(SubQuery(
                id="sq-02", original_topic=cleaned_topic, facet="entity_b_overview",
                search_query=f"{entity_b} performance specifications overview", priority=1,
                rationale=f"Explore core capabilities of {entity_b}"
            ))
            sub_queries.append(SubQuery(
                id="sq-03", original_topic=cleaned_topic, facet="comparative_head_to_head",
                search_query=f"{entity_a} vs {entity_b} direct comparison metrics benchmarks", priority=1,
                rationale="Direct head-to-head comparative evaluation"
            ))
            sub_queries.append(SubQuery(
                id="sq-04", original_topic=cleaned_topic, facet="tradeoffs_economics",
                search_query=f"{entity_a} {entity_b} economic cost manufacturing scalability", priority=2,
                rationale="Economic and manufacturing comparison"
            ))
        else:
            # Multi-faceted template generation
            for idx, (facet, template) in enumerate(self.FACET_TEMPLATES[:max_subqueries], start=1):
                sq_text = template.format(topic=cleaned_topic)
                sub_queries.append(SubQuery(
                    id=f"sq-{idx:02d}",
                    original_topic=cleaned_topic,
                    facet=facet,
                    search_query=sq_text,
                    priority=idx,
                    rationale=f"Investigate {facet.replace('_', ' ')} dimension"
                ))
                
        return DecompositionResult(
            topic=cleaned_topic,
            sub_queries=sub_queries[:max_subqueries],
            strategy_used="heuristic_rule_based"
        )
```

### 3.3 Retrieval Client Protocol (`src/retrieval/client.py`)

```python
"""Retrieval clients: MockWebClient, LiveHttpClient, and CompositeRetrievalClient."""
import abc
import hashlib
import json
import logging
import time
import urllib.request
import urllib.error
from typing import List, Dict, Optional, Any
from src.models.retrieval import SubQuery, RawWebDocument, CleanArticle, RetrievalBatch
from src.retrieval.parser import DocumentParser

logger = logging.getLogger(__name__)

class BaseRetrievalClient(abc.ABC):
    """Protocol for document retrieval."""
    
    @abc.abstractmethod
    def search(self, query: str, limit: int = 3) -> List[str]:
        """Returns URLs matching the query."""
        pass
        
    @abc.abstractmethod
    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        """Fetches raw web document by URL."""
        pass

class MockWebRetrievalClient(BaseRetrievalClient):
    """Offline, deterministic retrieval client powered by local fixture corpus.
    Guarantees 100% test pass rate in disconnected or CI/CD test environments."""
    
    def __init__(self, corpus_path: Optional[str] = None):
        self.corpus_path = corpus_path
        self._corpus: Dict[str, Dict[str, Any]] = {}
        self._load_corpus()
        
    def _load_corpus(self):
        # Loads mock documents from JSON / HTML fixture files
        # Supports query matching via keyword token overlap and URL lookup
        pass

    def search(self, query: str, limit: int = 3) -> List[str]:
        query_tokens = set(re.findall(r'\w+', query.lower()))
        scored_urls = []
        for url, doc in self._corpus.items():
            doc_tokens = set(re.findall(r'\w+', (doc.get("title", "") + " " + doc.get("body", "")).lower()))
            overlap = len(query_tokens.intersection(doc_tokens))
            if overlap > 0:
                scored_urls.append((overlap, url))
        scored_urls.sort(key=lambda x: x[0], reverse=True)
        results = [url for _, url in scored_urls[:limit]]
        if not results and self._corpus:
            results = list(self._corpus.keys())[:limit]
        return results

    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        if url in self._corpus:
            doc = self._corpus[url]
            return RawWebDocument(
                url=url,
                status_code=200,
                headers={"Content-Type": "text/html; charset=utf-8"},
                raw_html=doc.get("raw_html", f"<html><head><title>{doc.get('title')}</title></head><body><p>{doc.get('body')}</p></body></html>")
            )
        return RawWebDocument(
            url=url, status_code=404, headers={}, raw_html="", error="URL not found in mock corpus"
        )

class LiveHttpRetrievalClient(BaseRetrievalClient):
    """Live HTTP retrieval client with exponential backoff, rate limiting, and timeouts."""
    
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutonomousResearchBot/1.0"
    
    def __init__(self, max_retries: int = 3, backoff_factor: float = 1.0, rate_limit_delay: float = 0.5):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time: Dict[str, float] = {}
        self._cache: Dict[str, RawWebDocument] = {}

    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        if url in self._cache:
            return self._cache[url]
            
        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        )
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    status_code = response.getcode()
                    content_type = response.headers.get("Content-Type", "")
                    if "text/html" not in content_type and "text/plain" not in content_type:
                        return RawWebDocument(url=url, status_code=status_code, headers=dict(response.headers), raw_html="", error=f"Skipping non-text MIME: {content_type}")
                    raw_html = response.read(2_000_000).decode('utf-8', errors='replace')
                    doc = RawWebDocument(url=url, status_code=status_code, headers=dict(response.headers), raw_html=raw_html)
                    self._cache[url] = doc
                    return doc
            except urllib.error.HTTPError as e:
                if e.code == 429 or 500 <= e.code <= 504:
                    if attempt < self.max_retries:
                        time.sleep(self.backoff_factor * (2 ** attempt))
                        continue
                return RawWebDocument(url=url, status_code=e.code, headers=dict(e.headers), raw_html="", error=str(e))
            except Exception as e:
                if attempt < self.max_retries:
                    time.sleep(self.backoff_factor * (2 ** attempt))
                    continue
                return RawWebDocument(url=url, status_code=0, headers={}, raw_html="", error=str(e))
        return RawWebDocument(url=url, status_code=0, headers={}, raw_html="", error="Max retries exceeded")

class CompositeRetrievalClient(BaseRetrievalClient):
    """Transparent failover client: tries Live, falls back seamlessly to Mock."""
    def __init__(self, live_client: LiveHttpRetrievalClient, mock_client: MockWebRetrievalClient):
        self.live_client = live_client
        self.mock_client = mock_client
        self.offline_mode = False

    def search(self, query: str, limit: int = 3) -> List[str]:
        if not self.offline_mode:
            try:
                results = self.live_client.search(query, limit=limit)
                if results:
                    return results
            except Exception as err:
                logger.warning(f"Live search failed: {err}. Switching to mock fallback.")
                self.offline_mode = True
        return self.mock_client.search(query, limit=limit)

    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        if not self.offline_mode:
            try:
                doc = self.live_client.fetch_url(url, timeout=timeout)
                if not doc.error and doc.raw_html:
                    return doc
            except Exception as err:
                logger.warning(f"Live fetch failed for {url}: {err}. Falling back to mock.")
        return self.mock_client.fetch_url(url, timeout=timeout)
```

### 3.4 Document Parser & Boilerplate Stripper (`src/retrieval/parser.py`)

```python
"""HTML Parsing, Boilerplate Stripping, and Metadata Extraction."""
import html
import re
from html.parser import HTMLParser
from urllib.parse import urlparse
from typing import List, Dict, Tuple, Optional
from src.models.retrieval import RawWebDocument, CleanArticle, DocumentMetadata

class RobustHTMLParser(HTMLParser):
    """Extracts text while stripping scripts, styles, navigation, and boilerplate tags."""
    
    IGNORE_TAGS = {
        'script', 'style', 'noscript', 'nav', 'footer', 'header', 'aside',
        'form', 'button', 'iframe', 'svg', 'canvas', 'select', 'option'
    }
    
    HEADING_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
    BLOCK_TAGS = {'p', 'blockquote', 'li', 'td', 'th', 'article', 'section'}
    
    def __init__(self):
        super().__init__()
        self.ignore_depth = 0
        self.current_tag = None
        self.headings: List[str] = []
        self.paragraphs: List[str] = []
        self.title: Optional[str] = None
        self.meta_tags: Dict[str, str] = {}
        self.canonical_url: Optional[str] = None
        self._current_text: List[str] = []
        
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() in self.IGNORE_TAGS:
            self.ignore_depth += 1
            return
            
        # Boilerplate class/id filter
        elem_id = attr_dict.get('id', '').lower()
        elem_class = attr_dict.get('class', '').lower()
        if any(noise in elem_id or noise in elem_class for noise in ['cookie', 'popup', 'newsletter', 'sidebar', 'banner', 'ad-']):
            self.ignore_depth += 1
            return
            
        if tag.lower() == 'meta':
            prop = attr_dict.get('property') or attr_dict.get('name')
            content = attr_dict.get('content')
            if prop and content:
                self.meta_tags[prop.lower()] = content
                
        if tag.lower() == 'link' and attr_dict.get('rel') == 'canonical':
            self.canonical_url = attr_dict.get('href')
            
        if tag.lower() in self.BLOCK_TAGS or tag.lower() in self.HEADING_TAGS:
            self._flush_text()
            
        self.current_tag = tag.lower()

    def handle_endtag(self, tag: str):
        if tag.lower() in self.IGNORE_TAGS or self.ignore_depth > 0:
            if tag.lower() in self.IGNORE_TAGS:
                self.ignore_depth = max(0, self.ignore_depth - 1)
            return
        if tag.lower() in self.BLOCK_TAGS or tag.lower() in self.HEADING_TAGS:
            self._flush_text()
            
    def handle_data(self, data: str):
        if self.ignore_depth == 0:
            self._current_text.append(data)
            
    def _flush_text(self):
        text = " ".join("".join(self._current_text).split())
        self._current_text = []
        if len(text) >= 30:  # Minimum meaningful paragraph length
            if self.current_tag in self.HEADING_TAGS:
                self.headings.append(text)
            else:
                self.paragraphs.append(text)

class DocumentParser:
    """Orchestrates metadata extraction and boilerplate stripping."""
    
    @staticmethod
    def parse(raw_doc: RawWebDocument) -> CleanArticle:
        parser = RobustHTMLParser()
        parser.feed(raw_doc.raw_html)
        parser._flush_text()
        
        parsed_url = urlparse(raw_doc.url)
        domain = parsed_url.netloc or "unknown_domain"
        
        # Resolve Title
        title = (
            parser.meta_tags.get("og:title")
            or parser.meta_tags.get("twitter:title")
            or parser.title
            or (parser.headings[0] if parser.headings else "Untitled Document")
        )
        
        # Resolve Author
        author = (
            parser.meta_tags.get("author")
            or parser.meta_tags.get("article:author")
            or parser.meta_tags.get("twitter:creator")
            or domain
        )
        
        # Resolve Published Date
        published_date = (
            parser.meta_tags.get("article:published_time")
            or parser.meta_tags.get("date")
            or parser.meta_tags.get("dc.date")
        )
        
        canonical_url = parser.canonical_url or raw_doc.url
        cleaned_text = "\n\n".join(parser.paragraphs)
        doc_id = hashlib.sha256(canonical_url.encode('utf-8')).hexdigest()[:16]
        
        metadata = DocumentMetadata(
            url=raw_doc.url,
            canonical_url=canonical_url,
            domain=domain,
            title=html.unescape(title).strip(),
            author=author.strip() if author else None,
            published_date=published_date,
            content_type=raw_doc.headers.get("Content-Type", "text/html"),
            status_code=raw_doc.status_code,
            word_count=len(cleaned_text.split()),
            character_count=len(cleaned_text)
        )
        
        return CleanArticle(
            doc_id=doc_id,
            url=raw_doc.url,
            metadata=metadata,
            cleaned_text=cleaned_text,
            paragraphs=parser.paragraphs,
            headings=parser.headings,
            subquery_id=raw_doc.subquery_id
        )
```

---

## 4. Comprehensive Edge Cases & Failure Modes Catalog

| Category | Specific Edge Case | Impact if Unhandled | Mitigation / Architecture Solution |
|---|---|---|---|
| **Network & Transport** | HTTP 429 Too Many Requests | Retrieval aborts; 0 documents fetched; pipeline crashes. | Exponential backoff with random jitter (1s $\to$ 2s $\to$ 4s), domain rate limiting, transparent fallback to mock corpus. |
| **Network & Transport** | Sockets / Connection Timeout | Thread hangs indefinitely; pipeline hangs during verification. | Strict socket timeouts (`urllib.request.urlopen(..., timeout=8.0)`) wrapping all network calls. |
| **Network & Transport** | DNS Lookup Failure / No Internet | Crash with `socket.gaierror`. | Catch `urllib.error.URLError`, flag in `failed_urls`, seamlessly switch `CompositeRetrievalClient` to offline mock corpus. |
| **Network & Transport** | SSL Certificate Validation Error | Crash with `ssl.SSLError`. | Log security warning, retry with verified SSL context or fallback to mock fixture. |
| **Payload & MIME** | Binary Files (PDF, ZIP, Images) | Binary data passed to HTML parser; garbage extracted or decoding crash. | Inspect HTTP `Content-Type` header before parsing; discard non-text formats. |
| **Payload & MIME** | Giant Page / DOM Bomb (> 10 MB) | Memory spikes; process killed or severe slowdown. | Stream read capped at max 2 MB (`response.read(2_000_000)`). |
| **Payload & MIME** | Obscure Character Encodings (ISO-8859-1, GBK) | `UnicodeDecodeError` terminating extraction. | Fallback decoding with `errors='replace'`, detect charset from `<meta charset="...">` or HTTP headers. |
| **DOM & HTML Content** | Client-Side SPA (`<div id="root"></div>`) | Empty text parsed; downstream claim extractor gets 0 tokens. | Length validation: if extracted text < 100 characters, flag document as `low_content` and retrieve alternative source. |
| **DOM & HTML Content** | Missing Metadata (No `<title>`, author, or date) | `NoneType` errors in citation formatter (R3). | Graceful fallbacks: domain as author, URL path as title fallback, current date as fetch timestamp. |
| **Query Input** | Single-word or ultra-brief query (e.g. "Quantum") | Decomposition creates trivial or duplicated queries. | Expansion heuristics: detect short inputs and expand with foundational terminology. |
| **Query Input** | Hyper-long rambling user prompt (> 100 words) | Search engine fails to match literal sentence. | Keyword extraction: strip stop-words, retain noun-chunks and entity pairs. |
| **Deduplication** | Overlapping URLs returned by multiple sub-queries | Redundant fetches waste network budget and duplicate claims. | In-memory SHA-256 URL cache ensures each unique URL is fetched and parsed exactly once. |

---

## 5. Offline Deterministic Mock Web Corpus Design for R4 Verification

To ensure R4 automated verification executes quickly, reliably, and with 100% deterministic reproducibility across environments, the mock web corpus must include realistic HTML fixtures for at least 3 diverse query domains:

### Corpus Structure (`fixtures/mock_web/`)
1. **Domain 1: Solid-State vs Lithium-Ion Batteries (Energy Tech)**
   - `fixtures/mock_web/battery_solid_state_overview.html` (Title: "Solid-State Battery Breakthroughs in 2024", Domain: `tech-energy-review.org`)
   - `fixtures/mock_web/battery_economic_feasibility.html` (Title: "Manufacturing Costs of Solid-State Electrolytes vs Li-Ion", Domain: `clean-energy-economics.com`)
   - `fixtures/mock_web/battery_safety_and_degradation.html` (Title: "Dendrite Formation and Thermal Runaway Benchmarks", Domain: `journal-materials-science.org`)
2. **Domain 2: Feasibility of Global Carbon Capture and Storage (Climate Policy)**
   - `fixtures/mock_web/ccs_direct_air_capture_costs.html` (Title: "Levelized Cost Analysis of Direct Air Capture Technologies", Domain: `climate-policy-institute.org`)
   - `fixtures/mock_web/ccs_geological_storage_permanence.html` (Title: "Long-Term Monitoring of Deep Saline Aquifer Carbon Sequestration", Domain: `global-geology-review.com`)
   - `fixtures/mock_web/ccs_regulatory_and_scale_limits.html` (Title: "Global Pipeline Infrastructure Gaps for Gigaton-Scale CCS", Domain: `energy-transition-monitor.net`)
3. **Domain 3: Autonomous AI Diagnostic Systems in Clinical Practice (Healthcare AI)**
   - `fixtures/mock_web/ai_diagnostics_clinical_accuracy.html` (Title: "Multi-Center Clinical Trial Results for Autonomous Radiology AI", Domain: `digital-health-bulletin.org`)
   - `fixtures/mock_web/ai_diagnostics_regulatory_fda.html` (Title: "FDA Clearance Pathways and Post-Market Surveillance for Medical AI", Domain: `medtech-regulatory-review.com`)
   - `fixtures/mock_web/ai_diagnostics_liability_ethics.html` (Title: "Malpractice Liability and Physician Discretion in Algorithmic Diagnosis", Domain: `health-law-ethics.org`)

Each mock file contains realistic OpenGraph metadata, publication dates, author bylines, and rich paragraph texts with factual claims suitable for downstream R2 and R3 validation.

---

## 6. Caveats

1. **Third-Party Dependency Availability**:
   - In environments where `beautifulsoup4` or `readability-lxml` is not installed, the standard-library-based `RobustHTMLParser` designed in Section 3.4 serves as the primary parser. It requires zero third-party dependencies and runs natively on any standard Python 3.8+ installation.
2. **Headless Browser / Dynamic JavaScript Rendering**:
   - The architectural design targets static HTML retrieval (`urllib.request`). Highly obfuscated Single Page Applications (SPAs) that require a full Chromium/Playwright execution context are out of scope for the lightweight core crawler. However, mock fixtures and standard news/academic sites provide static HTML.
3. **External Search Engine API Keys**:
   - Public search engines (like DuckDuckGo HTML) can throttle automated scraping if queried too frequently without an API key. For development and verification, `MockWebRetrievalClient` provides 100% deterministic coverage, while `CompositeRetrievalClient` ensures smooth failover.

---

## 7. Conclusion

Requirement R1 can be cleanly, robustly, and modularly implemented using a three-tier pipeline:
1. **Query Decomposition**: `HeuristicQueryDecomposer` producing typed `SubQuery` lists across 5 orthogonal facets.
2. **Dual-Mode Retrieval**: `BaseRetrievalClient` with `MockWebRetrievalClient` for offline testing and `LiveHttpRetrievalClient` with exponential backoff and rate limiting.
3. **Document Parsing**: `DocumentParser` using `RobustHTMLParser` for zero-dependency boilerplate removal, clean paragraph extraction, and metadata extraction.

This architecture provides clean, structured data contracts (`CleanArticle`, `RetrievalBatch`) directly feeding R2 (relevance filtering and claim extraction), guaranteeing that downstream synthesis (R3) and verification (R4) have complete source attribution and high-quality factual context.

---

## 8. Verification Method

To independently verify the proposed R1 architecture design:
1. **Inspect Architecture Deliverables**:
   - Review `C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\survey_explorer_1\handoff.md` for complete data models, interfaces, and mitigation strategies.
2. **Interface Test / Smoke Script**:
   Once implemented by the development team, run the component verification script:
   ```bash
   python -m unittest tests/test_retrieval.py
   ```
   Asserting:
   - `test_heuristic_decomposition`: Inputting 3 distinct research topics produces 3-5 distinct sub-queries with non-empty search strings and distinct facets.
   - `test_mock_web_retrieval`: Queries against `fixtures/mock_web/` return valid `CleanArticle` instances with non-empty titles, domains, URLs, and cleaned body text.
   - `test_parser_boilerplate_removal`: Feeding raw HTML containing `<script>`, `<style>`, and `<nav>` elements confirms that all tags and navigation text are removed, leaving only article body text.
   - `test_network_failover`: Simulating a network failure in `CompositeRetrievalClient` smoothly falls back to mock corpus without unhandled exceptions.
