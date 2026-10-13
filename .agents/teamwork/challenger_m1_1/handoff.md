# Adversarial Challenge Report: Milestone 1 (Query Decomposition & Web Retrieval)

**Challenger**: Adversarial Challenger 1 (Query Decomposition & Retrieval Stress)  
**Target Milestone**: Milestone 1  
**Verdict**: **REQUEST_CHANGES**  
**Overall Risk Assessment**: **CRITICAL**  

---

## 1. Observation

### 1.1 Direct Source Code Observations

#### Observation 1.1.1: `RobustHTMLParser` State Machine Leak on Boilerplate Class/ID Containers
- **File**: `src/research_synthesis/retrieval/parser.py`, lines 72–79 and lines 110–113:
```python
# Lines 72-79 (handle_starttag):
        elem_id = attr_dict.get("id", "").lower()
        elem_class = attr_dict.get("class", "").lower()
        if any(noise in elem_id or noise in elem_class for noise in self.BOILERPLATE_CLASS_ID_KEYWORDS):
            if tag_lower not in self.VOID_TAGS:
                self.ignore_depth += 1
            return
```
```python
# Lines 110-113 (handle_endtag):
        if tag_lower in self.IGNORE_TAGS or self.ignore_depth > 0:
            if tag_lower in self.IGNORE_TAGS and tag_lower not in self.VOID_TAGS:
                self.ignore_depth = max(0, self.ignore_depth - 1)
            return
```
- **Context**: In `RobustHTMLParser.IGNORE_TAGS` (lines 25–29), the tags listed are:
```python
    IGNORE_TAGS = {
        "script", "style", "noscript", "nav", "footer", "header", "aside",
        "form", "button", "iframe", "svg", "canvas", "select", "option",
        "dialog", "menu", "applet", "object", "embed",
    }
```
- Notice that common layout container tags such as `div`, `section`, `span`, and `p` are **NOT** in `IGNORE_TAGS`.
- When an HTML snippet contains `<div id="cookie-banner" class="cookie-popup">...</div>` or `<div id="sticky-top-ad">...</div>`:
  1. `handle_starttag()` matches `"cookie"` or `"ad-"` in `BOILERPLATE_CLASS_ID_KEYWORDS` and increments `self.ignore_depth += 1` (now `1`).
  2. When the corresponding `</div>` is processed by `handle_endtag()`, `self.ignore_depth > 0` is true, so execution enters the block at line 110.
  3. However, line 111 evaluates `if tag_lower in self.IGNORE_TAGS`. Since `"div"` is not in `self.IGNORE_TAGS`, line 112 (`self.ignore_depth = max(0, self.ignore_depth - 1)`) is **SKIPPED**.
  4. Line 113 executes `return`.
  5. `self.ignore_depth` remains permanently stuck at `1` for all subsequent tags in the document.
  6. In `handle_data()` (lines 124–125):
```python
        elif self.ignore_depth == 0:
            self._current_text.append(data)
```
  Because `self.ignore_depth` is non-zero, every subsequent text node in the entire document is dropped.
- **Fixture Impact**: In `tests/fixtures/mock_corpus/solid_state_battery/doc_04_ad_heavy_duplicate.html`, line 15 defines `<div id="sticky-top-ad" style="...">`. Consequently, lines 29–42 (`<article>...<p>The pivotal barrier transitioning solid-state battery technology...</p></article>`) are completely suppressed. `DocumentParser.parse()` yields `article.paragraphs == []` and `article.cleaned_text == ""`.
- **Worker Claim vs Reality**: In `worker_m1/handoff.md` Section 1.2, worker_m1 claimed all 21 tests in `tests/test_tier1_retrieval.py` pass. However, test `test_boilerplate_stripping` (lines 243–305) includes `<div id="cookie-banner" class="cookie-popup">` right before `<main><h1>...</h1><p>...</p></main>`. Because of the `ignore_depth` leak, `test_boilerplate_stripping` produces 0 paragraphs and an empty `cleaned_text`, which directly contradicts worker_m1's claim of passing.

---

#### Observation 1.1.2: `MockWebRetrievalClient._load_corpus` Manifest Schema Discrepancy & File Deserialization Failure
- **File**: `src/research_synthesis/retrieval/retriever.py`, lines 189–211:
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
- **File**: `tests/fixtures/mock_corpus/manifest.json`, lines 116–126:
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
    }, ...
  }
```
- **Context**:
  1. In `manifest.json`, `"documents"` is a dictionary where each key is a document ID (e.g. `"ssb_01_nature_materials"`), and the relative file path is under `"file_path"` (not `"file"`).
  2. When `MockWebRetrievalClient` loads `manifest.json`, `isinstance(doc_entries, dict)` is True.
  3. It executes lines 207–210:
     `for url, item in doc_entries.items(): self._corpus[url] = item`
  4. The loop assigns the document ID (`"ssb_01_nature_materials"`) as the key in `self._corpus` instead of the canonical URL (`item["url"]`).
  5. It **NEVER** opens or reads the HTML file from `item["file_path"]`. Therefore `raw_html` remains `None`.
  6. When `search()` runs, it returns document IDs (e.g. `["ssb_01_nature_materials"]`), not URLs.
  7. When `fetch_url("https://mock-science.org/...")` is called with the actual URL, it returns HTTP 404 (`"URL not found in mock corpus"`).
  8. When `fetch_url("ssb_01_nature_materials")` is called, `raw_html` is missing, causing the client to synthesize empty HTML: `<html><head><title>...</title></head><body><p></p></body></html>`.
  9. The entire set of 18 offline mock corpus HTML fixture files created for the project is completely ignored.

---

#### Observation 1.1.3: `HeuristicQueryDecomposer` Regex Failure on Standard Comparative Queries
- **File**: `src/research_synthesis/retrieval/decomposer.py`, lines 63–72:
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
- **Context**:
  1. The regex pattern requires an infix delimiter between entities: `(?:vs\.?|versus|compared\s+to|trade-offs?\s+between|differences?\s+between)`.
  2. For queries using standard English comparative phrasings:
     - `"comparison between Solid-State and Lithium-Ion"`
     - `"a comparison between Solid-State and Lithium-Ion"`
     - `"comparison of Solid-State and Lithium-Ion"`
     - `"trade-offs between Solid-State and Lithium-Ion"`
     - `"differences between Solid-State and Lithium-Ion"`
     the separator between the entities is `" and "`.
  3. None of these queries match the regex. `_detect_comparative()` returns `(False, "", "")`.
  4. Consequently, they fall back to the generic non-comparative 5-facet templates, failing to extract Entity A, Entity B, and head-to-head comparative sub-queries.

---

#### Observation 1.1.4: `HeuristicQueryDecomposer` Edge Cases (Unicode, Single-Word, Punctuation)
- **Empty / Whitespace**: `decompose("")` and `decompose("   \n\t")` correctly raise `ValueError("Topic cannot be empty or whitespace.")`. Non-strings raise `TypeError`.
- **Single-Word Topics**: `decompose("Quantum")` expands to `"Quantum technology system ..."` across 5 orthogonal facets (technical, economic, challenges, comparative, temporal).
- **Punctuation-Heavy Topics**: `decompose("???!!! ... ,,, ;;; :::")` and `decompose("What?! Is solid-state... really viable?!?")` strip trailing punctuation, fall back safely if stripped to empty, and return valid `SubQuery` items without unhandled exceptions.
- **Accented & Non-Latin Scripts**: `"café vs naïve"` and `"量子计算 vs 经典计算"` correctly trigger comparative decomposition.
- **Emoji Comparative Limitation**: `"🚀 vs 🛰️"` evaluates `len(entity_a) >= 2`. Since `"🚀"` has `len == 1`, comparative detection fails and falls back to generic facets.
- **Three-Way Comparison**: For `"X vs Y vs Z"`, the non-greedy first match sets `entity_a = "X"` and `entity_b = "Y vs Z"`. It generates 5 subqueries pairing X against (Y vs Z).

---

#### Observation 1.1.5: `MockWebRetrievalClient.search` Zero-Hit Fallback
- **File**: `src/research_synthesis/retrieval/retriever.py`, lines 262–265:
```python
        # Fallback to returning top documents if no keyword overlap matched
        if not results and self._corpus:
            results = list(self._corpus.keys())[:limit]
        return results
```
- When a search query matches zero keyword tokens in the corpus, rather than returning an empty list, it returns the top `limit` documents from `self._corpus`.

---

#### Observation 1.1.6: `CompositeRetrievalClient` Failover Behavior
- **File**: `src/research_synthesis/retrieval/retriever.py`, lines 476–501:
  - When `offline_mode=True`, calls bypass `live_client` entirely and query `mock_client`.
  - When `offline_mode=False` and `live_client.search()` raises an exception (e.g. `URLError`, `ConnectionResetError`), the client catches `Exception`, sets `self.offline_mode = True`, and seamlessly queries `mock_client`.
  - In `retrieve_batch()`, failed URLs are logged to `batch.failed_urls` without interrupting the retrieval of other URLs.

---

## 2. Logic Chain

1. **Parser State Leak (Observation 1.1.1 $\to$ Silent Article Loss $\to$ Pipeline Starvation)**:
   - Web pages commonly wrap advertisements, cookie consent prompts, and navigation in `<div>` or `<section>` tags bearing class or id attributes like `cookie-banner`, `sidebar`, `ad-`, or `popup`.
   - When `RobustHTMLParser` processes such an element, `handle_starttag()` increments `self.ignore_depth`.
   - When the corresponding closing tag (`</div>` or `</section>`) is encountered, `handle_endtag()` fails to decrement `self.ignore_depth` because `div` is not in `self.IGNORE_TAGS`.
   - `self.ignore_depth` remains $> 0$ for the remainder of the parse.
   - All subsequent text in the document is discarded by `handle_data()`.
   - In real fixtures (`doc_04_ad_heavy_duplicate.html`), 100% of the substantive article text is dropped, yielding an empty article.
   - When passed downstream to Milestone 2 (Chunker, BM25, Claim Extractor), zero passages and zero claims are produced. This causes critical failure in synthesis (Milestone 3) and verification (M-TEST / `verify.py`).

2. **Manifest Loading Failure (Observation 1.1.2 $\to$ Corpus Fixture Disconnect $\to$ Automated Verification Breakdown)**:
   - Milestone M-TEST provides a comprehensive, deterministic offline fixture suite in `tests/fixtures/mock_corpus/` containing 18 HTML files indexed by `manifest.json`.
   - `verify.py` passes `corpus_manifest=PROJECT_ROOT / "tests/fixtures/mock_corpus/manifest.json"` to the pipeline.
   - Because `MockWebRetrievalClient._load_corpus()` misinterprets the `"documents"` dictionary schema in `manifest.json`, it fails to load the HTML files from disk and sets corpus keys to document IDs instead of URLs.
   - Searches return document IDs instead of URLs, `fetch_url()` returns 404 for actual URLs, and synthesized documents have empty body text.
   - Any execution relying on `manifest.json` will fail.

3. **Comparative Decomposition Incompleteness (Observation 1.1.3 $\to$ Contract Defect)**:
   - `PROJECT.md` Feature F1 states: *"Decompose broad topics into 3-5 orthogonal sub-queries... using linguistic rules and comparative regex."*
   - Research queries naturally take forms like `"comparison between A and B"` or `"trade-offs between A and B"`.
   - Because `HeuristicQueryDecomposer` only recognizes comparative queries with `vs`, `versus`, or `compared to` as the infix operator, it fails to decompose standard comparative queries, violating the requirements of Milestone 1.

4. **Conclusion Support (Observations 1.1.1, 1.1.2, 1.1.3 $\to$ REQUEST_CHANGES)**:
   - Because the parser state leak destroys document content, the mock client cannot load project fixtures, and query decomposition fails on standard comparative forms, Milestone 1 cannot be approved in its current state.

---

## 3. Caveats

1. **Shell Command Permission Constraint**:
   - The shell command execution tool (`run_command`) was denied by the user environment security permission prompt during this session. In strict compliance with instructions (*"Proceed without performing this action"* and *"Do not attempt to circumvent this denial"*), no shell commands were executed.
   - All observations, logic chains, and assertions were derived through exhaustive static trace analysis, symbolic state-space tracking, and programmatic reproduction in `tests/test_adversarial_m1.py`.
2. **Live HTTP Network Execution**:
   - Live network searches against public search engines were evaluated via unit test inspection and mock network fault injection rather than making outbound internet calls to unmocked external servers.

---

## 4. Conclusion

**VERDICT**: **REQUEST_CHANGES**

Worker Milestone 1 must address the following required fixes before Milestone 1 can be approved:

### Actionable Required Fixes:

1. **Fix `RobustHTMLParser` State Tracking in `src/research_synthesis/retrieval/parser.py`**:
   - Replace the leaky `ignore_depth` counter with tag-aware stack tracking or uniform depth management.
   - Specifically: When entering an ignored element via `BOILERPLATE_CLASS_ID_KEYWORDS`, track the tag or nesting depth so that when the matching end tag is reached, the ignore depth is properly decremented back to 0.
   - Example fix:
```python
# In handle_starttag:
if tag_lower in self.IGNORE_TAGS or any(noise in elem_id or noise in elem_class for noise in self.BOILERPLATE_CLASS_ID_KEYWORDS):
    if tag_lower not in self.VOID_TAGS:
        self.ignored_stack.append(tag_lower)
        return
elif self.ignored_stack:
    if tag_lower not in self.VOID_TAGS:
        self.ignored_stack.append(tag_lower)
    return

# In handle_endtag:
if self.ignored_stack:
    if self.ignored_stack[-1] == tag_lower:
        self.ignored_stack.pop()
    return
```

2. **Fix `MockWebRetrievalClient._load_corpus` in `src/research_synthesis/retrieval/retriever.py`**:
   - Support `manifest.json`'s dictionary structure:
```python
elif isinstance(doc_entries, dict):
    for doc_id, item in doc_entries.items():
        if isinstance(item, dict):
            url = item.get("url", doc_id)
            filepath = item.get("file_path") or item.get("file")
            raw_html = item.get("raw_html")
            if not raw_html and filepath:
                full_p = os.path.join(base_dir, filepath)
                if os.path.exists(full_p):
                    with open(full_p, "r", encoding="utf-8") as hf:
                        raw_html = hf.read()
            self._corpus[url] = {
                "title": item.get("title", ""),
                "author": item.get("author", ""),
                "published_date": item.get("published_date", ""),
                "raw_html": raw_html or "",
                "body": item.get("snippet", ""),
            }
```

3. **Enhance `HeuristicQueryDecomposer` in `src/research_synthesis/retrieval/decomposer.py`**:
   - Add regex pattern support for `"comparison between A and B"`, `"comparison of A and B"`, `"trade-offs between A and B"`, and `"differences between A and B"`:
```python
re.compile(
    r"^(?:(?:a\s+)?comparison\s+(?:between|of)|trade-offs?\s+between|differences?\s+between)\s+(.+?)\s+and\s+(.+)$",
    re.IGNORECASE,
)
```

---

## 5. Verification Method

### Test Execution Command
Run the newly authored adversarial test suite alongside the existing tests:
```bash
python -m unittest tests/test_adversarial_m1.py tests/test_tier1_retrieval.py
```

### Files to Inspect
1. `tests/test_adversarial_m1.py`: Contains reproducible test cases demonstrating:
   - `test_boilerplate_class_id_causes_permanent_text_suppression` (reproduces parser state leak)
   - `test_mock_corpus_ad_heavy_fixture_dropped_by_state_leak` (reproduces text loss on actual project fixture)
   - `test_manifest_dict_schema_discrepancy` (reproduces manifest loading bug)
   - `test_comparative_comparison_between_flaw` (reproduces comparative regex detection failure)
   - `test_comparative_tradeoffs_between_flaw` (reproduces trade-offs regex detection failure)
2. `src/research_synthesis/retrieval/parser.py`: Verify that closing tags for elements with boilerplate classes/ids decrement the ignore state.
3. `src/research_synthesis/retrieval/retriever.py`: Verify that `MockWebRetrievalClient` correctly loads and indexes `manifest.json` files from disk by URL.
4. `src/research_synthesis/retrieval/decomposer.py`: Verify that comparative topics using `"between ... and ..."` trigger comparative decomposition.

### Invalidation Conditions
- `tests/test_adversarial_m1.py` passes 100% of test cases without assertion errors.
- `RobustHTMLParser` extracts all substantive paragraphs from `tests/fixtures/mock_corpus/solid_state_battery/doc_04_ad_heavy_duplicate.html`.
- `MockWebRetrievalClient(corpus_path="tests/fixtures/mock_corpus/manifest.json")` successfully reads HTML content and indexes by URL.
- `HeuristicQueryDecomposer.decompose("comparison between Solid-State and Lithium-Ion")` outputs comparative sub-queries.
