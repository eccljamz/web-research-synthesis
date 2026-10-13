# Remediation Strategy Handoff Report: Mock Corpus Loading & Retrieval Client Strategy

**Agent**: Remediation Explorer 2 (`explorer_m1_fix_2`)  
**Mission**: Formulate comprehensive remediation strategy for Mock Corpus Loading & Retrieval and Query Decomposer comparative regex  
**Milestone**: M1 Remediation  
**Status**: COMPLETE  
**Patch Artifact**: `remediation_m1_retrieval_and_decomposer.patch`  
**Test Suite Artifact**: `test_updates.py`

---

## Executive Summary
This report delivers a comprehensive remediation strategy resolving two major defects in Milestone 1:
1. **`MockWebRetrievalClient._load_corpus()` Schema & File Discrepancy**: Fixed parsing of `tests/fixtures/mock_corpus/manifest.json` where documents are structured as a dictionary keyed by document ID (`doc_id`), mapping to `"url"` and relative `"file_path"`. The fix loads raw HTML files from disk, populates document metadata, builds a searchable text `body` for keyword overlap, indexes `_corpus` by canonical URL, provides a secondary `_doc_id_to_url` alias table, and guarantees robust fallback to `DEFAULT_MOCK_CORPUS` when the corpus path is omitted or fixture files are missing.
2. **`HeuristicQueryDecomposer` Comparative Regex Infix Limitation**: Fixed comparative detection in `COMPARATIVE_PATTERNS` to recognize queries beginning with comparative phrases (`"comparison between X and Y"`, `"trade-offs between X and Y"`, `"differences between X and Y"`, `"a comparison between X and Y"`, `"the trade-offs between X and Y"`, `"differences of X and Y"`), separating entities using `"and"` or `"vs"`, while maintaining strict guards against false positives on standard multi-concept queries.

---

## 1. Observation

### 1.1 Manifest Schema Inspection
In `tests/fixtures/mock_corpus/manifest.json`:
- Lines 116-126:
```json
  "documents": {
    "ssb_01_nature_materials": {
      "file_path": "solid_state_battery/doc_01_nature_materials.html",
      "url": "https://mock-science.org/materials/solid-electrolyte-conductivities-breakthrough",
      "title": "Solid Electrolyte Materials and Room-Temperature Ionic Conductivities",
      "author": "Dr. Elena Rostova",
      "published_date": "2025-11-14T08:00:00Z",
      "domain": "mock-science.org",
      "expected_relevance": "high",
      "is_distractor": false
    },
```
- In `manifest.json`, `"documents"` is a JSON dictionary where keys are document identifiers (e.g., `"ssb_01_nature_materials"`), **not** URLs.
- The document URL is located in `item["url"]`.
- The fixture file location is located in `item["file_path"]` relative to the manifest's parent directory (`tests/fixtures/mock_corpus/`).
- The item dictionary does **not** contain pre-rendered `"raw_html"` or pre-extracted `"body"` text; the article text resides entirely within the HTML file referenced by `"file_path"`.

### 1.2 Inspection of `MockWebRetrievalClient._load_corpus()` in `src/research_synthesis/retrieval/retriever.py`
In `src/research_synthesis/retrieval/retriever.py`:
- Lines 189-211:
```python
doc_entries = data.get("documents", data) if isinstance(data, dict) else data
if isinstance(doc_entries, list):
    for item in doc_entries:
        url = item.get("url", "")
        filepath = item.get("file")
        if url and filepath:
            full_p = os.path.join(base_dir, filepath)
            if os.path.exists(full_p):
                with open(full_p, "r", encoding="utf-8") as hf:
                    raw_html = hf.read()
                self._corpus[url] = {
                    "title": item.get("title", ""),
                    "author": item.get("author", ""),
                    "published_date": item.get("published_date", ""),
                    "raw_html": raw_html,
                    "body": item.get("snippet", ""),
                }
elif isinstance(doc_entries, dict):
    for url, item in doc_entries.items():
        if isinstance(item, dict):
            self._corpus[url] = item
```
- When `doc_entries` is a dictionary, the iteration variable named `url` in line 208 (`for url, item in doc_entries.items():`) binds to the dictionary key (e.g., `"ssb_01_nature_materials"`), which is a `doc_id`, not a URL.
- Line 210 assigns `self._corpus[url] = item`, leaving `_corpus` indexed by `doc_id`.
- The code completely omits reading `item["file_path"]` when `doc_entries` is a dictionary, leaving `raw_html` as `None` or absent.
- In `search()` (lines 252-257):
```python
for url, doc in self._corpus.items():
    doc_text = f"{doc.get('title', '')} {doc.get('body', '')} {url}".lower()
    doc_tokens = set(re.findall(r"\w+", doc_text))
    overlap = len(meaningful_query_tokens.intersection(doc_tokens))
    if overlap > 0:
        scored_urls.append((float(overlap), url))
```
  Because `_corpus` keys are doc IDs and `body` is empty, `search()` returns doc IDs (e.g., `["ssb_01_nature_materials"]`), violating the contract requiring `List[str]` of URLs.
- In `fetch_url()` (lines 269-292):
```python
if url in self._corpus:
    doc = self._corpus[url]
    raw_html = doc.get("raw_html")
    if not raw_html:
        title = doc.get("title", "Mock Title")
        body = doc.get("body", "")
        raw_html = f"<html><head><title>{title}</title></head><body><p>{body}</p></body></html>"
    return RawWebDocument(url=url, status_code=200, headers={...}, raw_html=raw_html)
return RawWebDocument(url=url, status_code=404, ...)
```
  Calling `fetch_url("https://mock-science.org/...")` looks up the URL in `_corpus`. Because keys are doc IDs, it returns HTTP 404. Calling `fetch_url("ssb_01_nature_materials")` returns dummy HTML (`<p></p>`) because `raw_html` was never read from disk.

### 1.3 Inspection of `HeuristicQueryDecomposer` in `src/research_synthesis/retrieval/decomposer.py`
In `src/research_synthesis/retrieval/decomposer.py`:
- Lines 63-72:
```python
COMPARATIVE_PATTERNS = [
    re.compile(
        r"^(?:comparison\s+of\s+|a\s+comparison\s+between\s+)?(.+?)\s+(?:vs\.?|versus|compared\s+to|trade-offs?\s+between|differences?\s+between)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(.+?)\s+against\s+(.+)$",
        re.IGNORECASE,
    ),
]
```
- Lines 91-103:
```python
def _detect_comparative(self, topic: str) -> Tuple[bool, str, str]:
    """Detect if topic compares two entities."""
    for pattern in self.COMPARATIVE_PATTERNS:
        match = pattern.search(topic)
        if match:
            entity_a = match.group(1).strip()
            entity_b = match.group(2).strip()
            entity_a = re.sub(r"^(?:the\s+)", "", entity_a, flags=re.IGNORECASE).strip()
            entity_b = re.sub(r"^(?:the\s+)", "", entity_b, flags=re.IGNORECASE).strip()
            if entity_a and entity_b and len(entity_a) >= 2 and len(entity_b) >= 2:
                return True, entity_a, entity_b
    return False, "", ""
```
- In pattern 1, `trade-offs?\s+between` and `differences?\s+between` are placed inside the infix operator group `(?:vs\.?|versus|compared\s+to|trade-offs?\s+between|differences?\s+between)`. This requires leading text `(.+?)\s+` before the phrase. When a query begins with `"trade-offs between X and Y"` or `"differences between X and Y"`, pattern 1 fails to match.
- Furthermore, pattern 1 requires an infix delimiter matching `(?:vs\.?|versus|compared\s+to|...)`. In standard English, queries beginning with `"comparison between X and Y"` use `"and"` as the separator between the two entities, not `"vs"`. Thus, `"comparison between X and Y"` fails comparative detection completely.

### 1.4 Inspection of Adversarial Test Suite `tests/test_adversarial_m1.py`
In `tests/test_adversarial_m1.py`:
- Lines 101-126:
```python
def test_comparative_comparison_between_flaw(self):
    topic = "comparison between Solid-State and Lithium-Ion"
    is_comp, ent_a, ent_b = self.decomposer._detect_comparative(topic)
    self.assertFalse(is_comp, "Expected comparative detection to fail due to regex infix flaw")

def test_comparative_tradeoffs_between_flaw(self):
    topic = "trade-offs between Solid-State and Lithium-Ion"
    is_comp, ent_a, ent_b = self.decomposer._detect_comparative(topic)
    self.assertFalse(is_comp, "Expected comparative detection to fail for 'trade-offs between A and B'")
```
- Lines 226-244:
```python
client = MockWebRetrievalClient(corpus_path=str(manifest_path))
corpus_keys = list(client._corpus.keys())
self.assertIn("ssb_01_nature_materials", corpus_keys)
self.assertIsNone(client._corpus["ssb_01_nature_materials"].get("raw_html"))
search_results = client.search("solid electrolyte ionic conductivity", limit=2)
self.assertTrue(any(res == "ssb_01_nature_materials" for res in search_results))
doc = client.fetch_url("https://mock-science.org/materials/solid-electrolyte-conductivities-breakthrough")
self.assertEqual(doc.status_code, 404)
```
- These adversarial tests verify that the flaws exist in the baseline code.

---

## 2. Logic Chain

1. **Manifest Keying and Fixture Ingestion (Observation 1.1 $\to$ Observation 1.2)**:
   - `manifest.json` defines document entries with key = `doc_id` and values containing `"url"` and `"file_path"`.
   - `MockWebRetrievalClient._load_corpus()` in `retriever.py` improperly assumed that dictionary keys were URLs, assigning `self._corpus[doc_id] = item`.
   - It also did not resolve `item["file_path"]` or read HTML fixtures from disk.
   - Consequence: `search()` returned `doc_id` strings instead of URLs. `fetch_url()` with canonical URLs failed with HTTP 404. When queried with `doc_id`, it returned empty placeholder text (`<p></p>`).
   - Remediation: `_load_corpus()` must parse both list and dictionary representations of `manifest.json`, extract `url = item.get("url") or doc_key`, resolve `file_path` against `base_dir`, read the HTML fixture into `raw_html`, extract a clean text `body` for token overlap searching, index `_corpus` by `url`, and map `doc_key` to `url` in `_doc_id_to_url` for aliasing.

2. **Built-in Dictionary Fallback Integrity (Observation 1.2)**:
   - When `corpus_path` is `None`, points to a non-existent path, contains an invalid manifest, or points to missing fixture files, `MockWebRetrievalClient` must fall back cleanly to `DEFAULT_MOCK_CORPUS`.
   - In `_load_corpus()`, if `_corpus` is empty or if no substantive fixture content was loaded, `_corpus` must be cleared and populated from `DEFAULT_MOCK_CORPUS` with pre-rendered synthetic HTML.
   - This guarantees that existing unit tests (`test_default_corpus_search_and_fetch`) and offline execution without fixtures continue to function seamlessly.

3. **Comparative Regex Structure (Observation 1.3 $\to$ Observation 1.4)**:
   - English comparative queries fall into three structural patterns:
     a. **Prefix Comparative Phrases**: Queries starting with `"comparison between X and Y"`, `"trade-offs between X and Y"`, `"differences between X and Y"`, `"a comparison of X and Y"`, where entities are separated by `"and"` or `"vs"`.
     b. **Infix Comparisons**: Queries where two entities are separated by an operator: `"X vs Y"`, `"X versus Y"`, `"X compared to Y"`, `"X against Y"`.
     c. **Suffix Comparisons**: Queries where entities are followed by comparative nouns: `"X and Y trade-offs"`.
   - The current single regex placed `trade-offs between` and `differences between` into the infix group with required leading text and infix delimiters (`vs/versus`), completely failing when queries start with these phrases or use `"and"` as delimiter.
   - Remediation: Implement three dedicated, prioritized regex patterns in `COMPARATIVE_PATTERNS` and expand conversational filler cleaning in `_sanitize_topic()`.

---

## 3. Caveats

1. **Read-Only Explorer Mandate**: Per Teamwork protocol, this explorer has NOT modified source files directly. Concrete machine-applicable changes are delivered via `remediation_m1_retrieval_and_decomposer.patch` and detailed code snippets below for Worker M1 to apply.
2. **Subprocess Permissions**: Direct terminal execution of `python -m unittest` was blocked by environment security permissions. All behaviors, regex matches, and JSON data flows were verified via static analysis, AST verification, and deterministic execution tracing.
3. **Adversarial Test Suite Transition**: `tests/test_adversarial_m1.py` was originally authored to assert the presence of these bugs. Once the remediation is applied, those assertions will fail unless updated to assert the fixed behavior (as detailed in Section 5).

---

## 4. Conclusion & Detailed Remediation Strategy

### 4.1 Changes to `src/research_synthesis/retrieval/retriever.py`

#### 4.1.1 Target: `MockWebRetrievalClient.__init__`
Initialize `self._doc_id_to_url` and cast `corpus_path` to string:
```python
<<<< BEFORE
    def __init__(
        self,
        corpus_path: Optional[str] = None,
        corpus_dict: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self.corpus_path = corpus_path
        self._corpus: Dict[str, Dict[str, Any]] = {}
        if corpus_dict:
            self._corpus.update(corpus_dict)
        self._load_corpus()
==== AFTER
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
>>>>
```

#### 4.1.2 Target: `MockWebRetrievalClient._load_corpus()`
Correctly parse manifest `documents` dict/list, load HTML fixtures, populate `body`, index by URL, alias doc IDs, and fall back to `DEFAULT_MOCK_CORPUS`:
```python
<<<< BEFORE
    def _load_corpus(self):
        """Load corpus from manifest or HTML files, falling back to built-in fixtures."""
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
                    if isinstance(doc_entries, list):
                        for item in doc_entries:
                            url = item.get("url", "")
                            filepath = item.get("file")
                            if url and filepath:
                                full_p = os.path.join(base_dir, filepath)
                                if os.path.exists(full_p):
                                    with open(full_p, "r", encoding="utf-8") as hf:
                                        raw_html = hf.read()
                                    self._corpus[url] = {
                                        "title": item.get("title", ""),
                                        "author": item.get("author", ""),
                                        "published_date": item.get("published_date", ""),
                                        "raw_html": raw_html,
                                        "body": item.get("snippet", ""),
                                    }
                    elif isinstance(doc_entries, dict):
                        for url, item in doc_entries.items():
                            if isinstance(item, dict):
                                self._corpus[url] = item
                except Exception as err:
                    logger.warning(f"Failed to load corpus from {manifest_file}: {err}")

        # Always ensure default mock fixtures are present if corpus is empty
        if not self._corpus:
            for url, data in DEFAULT_MOCK_CORPUS.items():
...
==== AFTER
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
                            # Strip tags to create searchable body text for token overlap
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
>>>>
```

#### 4.1.3 Target: `MockWebRetrievalClient.fetch_url()`
Support doc_id alias resolution while maintaining canonical URL lookup:
```python
<<<< BEFORE
    def fetch_url(self, url: str, timeout: float = 8.0) -> RawWebDocument:
        """Fetch document from offline mock corpus."""
        if url in self._corpus:
            doc = self._corpus[url]
            raw_html = doc.get("raw_html")
            if not raw_html:
                title = doc.get("title", "Mock Title")
                body = doc.get("body", "")
                raw_html = (
                    f"<html><head><title>{title}</title></head>"
                    f"<body><p>{body}</p></body></html>"
                )
            return RawWebDocument(
                url=url,
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
==== AFTER
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
>>>>
```

---

### 4.2 Changes to `src/research_synthesis/retrieval/decomposer.py`

#### 4.2.1 Target: `HeuristicQueryDecomposer.COMPARATIVE_PATTERNS` & `FILLER_PREFIXES`
```python
<<<< BEFORE
    # Comparative regex patterns
    COMPARATIVE_PATTERNS = [
        re.compile(
            r"^(?:comparison\s+of\s+|a\s+comparison\s+between\s+)?(.+?)\s+(?:vs\.?|versus|compared\s+to|trade-offs?\s+between|differences?\s+between)\s+(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(.+?)\s+against\s+(.+)$",
            re.IGNORECASE,
        ),
    ]

    # Conversational filler prefixes to strip
    FILLER_PREFIXES = [
        re.compile(r"^(?:can\s+you\s+(?:please\s+)?(?:explain|tell\s+me\s+about|research|investigate))\s+", re.IGNORECASE),
        re.compile(r"^(?:what\s+(?:is|are)\s+the\s+(?:state\s+of|details\s+on))\s+", re.IGNORECASE),
        re.compile(r"^(?:give\s+me\s+a\s+(?:detailed\s+)?(?:report|overview)\s+on)\s+", re.IGNORECASE),
        re.compile(r"^(?:i\s+want\s+to\s+know\s+about)\s+", re.IGNORECASE),
    ]
==== AFTER
    # Comparative regex patterns
    COMPARATIVE_PATTERNS = [
        # Pattern 1: Queries beginning with comparative phrases
        re.compile(
            r"^(?:(?:a|the)\s+)?(?:comparison\s+between|comparison\s+of|trade-offs?\s+between|trade-offs?\s+of|differences?\s+between|differences?\s+of|compare)\s+(.+?)\s+(?:and|vs\.?|versus|to|with)\s+(.+)$",
            re.IGNORECASE,
        ),
        # Pattern 2: Standard infix comparisons
        re.compile(
            r"^(?:(?:a|the)\s+)?(?:comparison\s+of\s+|comparison\s+between\s+)?(.+?)\s+(?:vs\.?|versus|compared\s+to|compared\s+with|against)\s+(.+)$",
            re.IGNORECASE,
        ),
        # Pattern 3: Suffix comparisons
        re.compile(
            r"^(.+?)\s+and\s+(.+?)\s+(?:trade-offs?|differences?|comparison)$",
            re.IGNORECASE,
        ),
    ]

    # Conversational filler prefixes to strip
    FILLER_PREFIXES = [
        re.compile(r"^(?:can\s+you\s+(?:please\s+)?(?:explain|tell\s+me\s+about|research|investigate|explore|analyze))\s+", re.IGNORECASE),
        re.compile(r"^(?:what\s+(?:is|are)\s+(?:the\s+)?(?:state\s+of\s+|details\s+on\s+)?)\s*", re.IGNORECASE),
        re.compile(r"^(?:give\s+me\s+a\s+(?:detailed\s+)?(?:report|overview)\s+on)\s+", re.IGNORECASE),
        re.compile(r"^(?:i\s+want\s+to\s+know\s+about)\s+", re.IGNORECASE),
    ]
>>>>
```

---

## 5. Verification Method

### 5.1 Verification Commands
Once the implementer applies the changes, verify using standard `unittest`:
```bash
# 1. Verify standard Tier 1 Retrieval test suite (all tests pass)
python -m unittest tests/test_tier1_retrieval.py

# 2. Run adversarial stress test suite
python -m unittest tests/test_adversarial_m1.py

# 3. Run automated acceptance verification CLI in mock mode
python verify.py --mode=mock
```

### 5.2 Standalone Python Test Script
Inspect and execute the verification test suite written to:
`C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\explorer_m1_fix_2\test_updates.py`

This script validates:
1. `TestMockRetrieverRemediationVerification.test_manifest_loads_all_fixtures_by_url`: Asserts that `manifest.json` loads all 18 fixtures keyed by canonical URL, `raw_html` is non-empty from disk, and `body` is searchable.
2. `TestMockRetrieverRemediationVerification.test_search_and_fetch_with_manifest_corpus`: Asserts that searching keywords returns valid URLs and `fetch_url()` returns HTTP 200 with fixture HTML.
3. `TestMockRetrieverRemediationVerification.test_fetch_by_doc_id_alias`: Asserts that doc_id alias resolves correctly.
4. `TestMockRetrieverRemediationVerification.test_fallback_when_path_omitted_or_missing`: Asserts that `corpus_path=None` or non-existent path loads all 4 `DEFAULT_MOCK_CORPUS` entries.
5. `TestDecomposerComparativeRemediationVerification`: Asserts comparative detection and decomposition for:
   - `"comparison between Solid-State and Lithium-Ion"`
   - `"trade-offs between Solid-State and Lithium-Ion"`
   - `"differences between Solid-State and Lithium-Ion"`
   - `"a comparison between Solar and Wind"`
   - `"the trade-offs between Solar and Wind"`
   - `"differences of Solar and Wind"`

### 5.3 Invalidation Conditions
The remediation is considered invalidated if:
- `MockWebRetrievalClient._corpus` keys are doc IDs rather than canonical URLs.
- `fetch_url()` returns HTTP 404 when given a canonical URL present in `manifest.json`.
- `MockWebRetrievalClient._corpus[url]["raw_html"]` is `None` or empty when fixture files exist on disk.
- Initializing `MockWebRetrievalClient(corpus_path=None)` results in an empty `_corpus` rather than falling back to `DEFAULT_MOCK_CORPUS`.
- `HeuristicQueryDecomposer._detect_comparative("comparison between Solid-State and Lithium-Ion")` returns `False`.
- `HeuristicQueryDecomposer._detect_comparative("trade-offs between Solid-State and Lithium-Ion")` returns `False`.
- `HeuristicQueryDecomposer._detect_comparative("differences between Solid-State and Lithium-Ion")` returns `False`.
- Non-comparative topics (e.g., `"Solid-State Battery Commercialization"`) are falsely detected as comparative.
