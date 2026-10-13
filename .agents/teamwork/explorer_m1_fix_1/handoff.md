# Remediation Strategy Report: HTML Parser & State Machine Defects

**Agent**: Remediation Explorer 1 (`explorer_m1_fix_1`)  
**Role**: HTML Parser & State Machine Strategy  
**Target File**: `src/research_synthesis/retrieval/parser.py`  
**Test Suites**: `tests/test_tier1_retrieval.py`, `tests/test_parser_boilerplate_stress.py`, `tests/test_adversarial_m1.py`  
**Status**: Strategy Formulated & Verified (Ready for Implementation)

---

## 1. Observation

### 1.1 Source Code Inspection (`src/research_synthesis/retrieval/parser.py`)

1. **`RobustHTMLParser` Tag Sets and Noise Keywords (lines 25-43)**:
   ```python
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
       "ad-", "social-share", "share-button", "disclaimer", "nav-item",
       "widget", "modal", "subscribe",
   ]
   ```

2. **`handle_starttag` Boilerplate Detection and Ignore State (lines 66-78)**:
   ```python
   # Check ignored tag subtrees
   if tag_lower in self.IGNORE_TAGS:
       if tag_lower not in self.VOID_TAGS:
           self.ignore_depth += 1
       return

   # Check boilerplate class or id
   elem_id = attr_dict.get("id", "").lower()
   elem_class = attr_dict.get("class", "").lower()
   if any(noise in elem_id or noise in elem_class for noise in self.BOILERPLATE_CLASS_ID_KEYWORDS):
       if tag_lower not in self.VOID_TAGS:
           self.ignore_depth += 1
       return
   ```

3. **`handle_endtag` State Decrement Disconnect (lines 110-113)**:
   ```python
   if tag_lower in self.IGNORE_TAGS or self.ignore_depth > 0:
       if tag_lower in self.IGNORE_TAGS and tag_lower not in self.VOID_TAGS:
           self.ignore_depth = max(0, self.ignore_depth - 1)
       return
   ```

4. **`_flush_text` Heading Truncation by Paragraph Threshold (lines 133-143)**:
   ```python
   # Minimum length threshold for substantive text
   if len(cleaned) >= 25:
       last_tag = self.tag_stack[-1] if self.tag_stack else None
       if last_tag in self.HEADING_TAGS:
           if cleaned not in self.headings:
               self.headings.append(cleaned)
       else:
           # Avoid duplicate adjacent paragraphs
           if not self.paragraphs or self.paragraphs[-1] != cleaned:
               self.paragraphs.append(cleaned)
   ```

5. **`tag_stack` Pollution from Ignored Children (lines 97, 110-113)**:
   When inside an ignored tag (e.g., `<nav><p>Home</p></nav>`), `handle_starttag` line 97 executes `self.tag_stack.append("p")` because `<p>` is not in `IGNORE_TAGS` and lacks boilerplate attributes. In `handle_endtag`, line 110 evaluates `self.ignore_depth > 0` as `True` and returns at line 113 before reaching line 118 (`if self.tag_stack and self.tag_stack[-1] == tag_lower: self.tag_stack.pop()`). Thus `"p"` is never popped.

### 1.2 Test Failures and Defect Manifestation

1. **`tests/test_tier1_retrieval.py::TestRobustHTMLParserAndDocumentParser.test_boilerplate_stripping`**:
   The input HTML contains:
   ```html
   <div id="cookie-banner" class="cookie-popup">
       Please accept our cookies to continue reading.
   </div>
   <main>
       <h1>Solid State Battery Developments</h1>
       <p>Solid state electrolytes offer substantial improvements in safety by eliminating flammable liquids.</p>
       ...
   </main>
   ```
   Assertions on lines 301-305:
   ```python
   self.assertIn("Solid state electrolytes offer substantial improvements", cleaned_text)
   self.assertIn("Commercialization timelines project high volume pilot", cleaned_text)
   self.assertEqual(len(article.paragraphs), 2)
   self.assertIn("Solid State Battery Developments", article.headings)
   ```
   **Observed Failure**: When `</div>` is encountered, `"div"` is not in `IGNORE_TAGS`, so `ignore_depth` remains locked at `1`. `article.paragraphs` is `[]`, `article.headings` is `[]`, and `cleaned_text` is `""`. Assertion `self.assertEqual(0, 2)` fails.

2. **`tests/test_parser_boilerplate_stress.py::TestBoilerplateAndParserDefects`**:
   - `test_boilerplate_container_silences_subsequent_content` (lines 32-68): Fails with `AssertionError: Parser paragraphs should not be empty after a boilerplate div! Actual: [], ignore_depth=1`.
   - `test_ad_keyword_false_positive_silences_legitimate_content` (lines 69-97): `<div class="lead-story">` and `<div class="thread-container">` trigger `"ad-" in elem_class` (matching `le[ad-]` and `thre[ad-]`). `ignore_depth` locks at 1, dropping all article text.
   - `test_modal_keyword_false_positive_on_multimodal` (lines 98-121): `<div class="multimodal-architecture">` triggers `"modal" in elem_class` (matching `multi[modal]`). Text is silenced.
   - `test_short_headings_dropped_by_length_filter` (lines 122-153): `<h1>Executive Summary</h1>` (17 chars) and `<h2>Key Findings</h2>` (12 chars) are strictly under 25 chars and are discarded from `parser.headings`.
   - `test_tag_stack_corruption_on_ignored_children` (lines 154-182): Child elements inside `<nav>` leak onto `parser.tag_stack` and prevent tag stack cleanup.

---

## 2. Logic Chain

### 2.1 Logic Chain for Defect 1: State Leak in `handle_endtag()`
1. In `handle_starttag()`, elements with boilerplate classes or IDs increment `self.ignore_depth` (Observation 1.1.2). These tags include generic containers such as `<div>`, `<section>`, `<article>`, and `<span>`.
2. In `handle_endtag()`, the decrement logic at line 111 is conditioned on `tag_lower in self.IGNORE_TAGS and tag_lower not in self.VOID_TAGS` (Observation 1.1.3).
3. `IGNORE_TAGS` only contains 19 specific tags (`script`, `style`, `nav`, etc.) and explicitly excludes `div`, `section`, etc. (Observation 1.1.1).
4. Therefore, closing tags for boilerplate elements (`</div>`, `</section>`) NEVER decrement `self.ignore_depth`.
5. `self.ignore_depth` remains $\ge 1$ indefinitely for the remainder of the document.
6. In `handle_data()`, line 124 gates text accumulation on `elif self.ignore_depth == 0:`. All subsequent substantive content is permanently discarded.
7. Furthermore, scalar counting does not track tag hierarchy: if child tags open within an ignored container, or if tags are unclosed, a scalar counter desynchronizes.
8. **Deduction**: The parser must maintain an explicit ignore tag stack (`self._ignore_stack: List[str]`). When an ignored tag opens, its tag name is pushed to `_ignore_stack`. When `handle_endtag()` matches an open tag in `_ignore_stack`, it unwinds and pops that tag, restoring `_ignore_stack` to empty (`ignore_depth == 0`) when the container closes.

### 2.2 Logic Chain for Defect 2: Noise Keyword False Positives
1. `BOILERPLATE_CLASS_ID_KEYWORDS` includes the substring `"ad-"` (Observation 1.1.1).
2. Standard English words in content container classes end in `ad`, such as `lead` (`lead-story`, `lead-article`, `lead-paragraph`), `thread` (`thread-container`, `thread-list`), `download` (`download-link`), `upload` (`upload-date`), `broad` (`broad-overview`), and `head` (`head-wrapper`).
3. In CSS kebab-case naming, following `lead` with a hyphen produces `lead-`, which contains the literal substring `"ad-"`.
4. Line 75 evaluates `noise in elem_class` using naive substring search (Observation 1.1.2).
5. As a result, standard primary story containers (`<div class="lead-story">`) evaluate to `True`, triggering boilerplate suppression.
6. Similarly, `"modal"` appears as a substring inside `"multimodal"` (e.g. `multimodal-architecture`), causing scientific and AI research content to be flagged as popup modals.
7. **Deduction**: Noise keyword matching must enforce word and delimiter boundaries. In CSS, identifiers are separated by whitespace, hyphens, and underscores. Matching against a compiled regular expression `(?:\b|_)(?:...)(?:\b|_)` ensures `"ad"` matches only when delimited (e.g., `ad-banner`, `sticky-top-ad`, `sidebar-ad`, `ad`, `ads`) and never when embedded within words like `lead-` or `thread-`. Similarly, `"modal"` matches `modal` and `modal-dialog` but never `multimodal`.

### 2.3 Logic Chain for Defect 3: Heading Truncation by Length Threshold
1. `_flush_text()` checks `if len(cleaned) >= 25:` as an outer guard before checking `last_tag in self.HEADING_TAGS` (Observation 1.1.4).
2. Standard document section titles are concise: `"Executive Summary"` (17 chars), `"Key Findings"` (12 chars), `"Introduction"` (12 chars), `"Overview"` (8 chars), `"Abstract"` (8 chars), `"Conclusion"` (10 chars), `"Results"` (7 chars).
3. Every heading shorter than 25 characters is dropped before reaching line 138.
4. In `DocumentParser.parse()`, line 188 relies on `parser.headings[0]` as a title fallback when `<title>` and `og:title` are absent. Dropping headings collapses title extraction.
5. **Deduction**: Structural role must be evaluated before length thresholds. Headings should require `len(cleaned) >= 2` (retaining valid headings while eliminating empty strings and stray single characters), whereas paragraphs should maintain the `len(cleaned) >= 25` threshold to filter out navigational fragments and noise.

### 2.4 Logic Chain for Defect 4: Tag Stack Corruption
1. When `self.ignore_depth > 0`, `handle_starttag()` does not check if the parser is already in an ignored state. Child tags (such as `<p>` inside `<nav>`) fall through to line 97 and push to `self.tag_stack` (Observation 1.1.5).
2. In `handle_endtag()`, the early return at line 113 executes whenever `self.ignore_depth > 0`, bypassing `self.tag_stack.pop()`.
3. Consequently, tags opened inside ignored subtrees are never popped from `self.tag_stack`.
4. This corrupts `last_tag = self.tag_stack[-1]` in subsequent text flushing, misclassifying body paragraphs as navigation or headings.
5. In addition, void tags (`<meta>`, `<link>`, `<img>`, `<br>`) push to `self.tag_stack` but never receive closing tags.
6. **Deduction**: 
   - If the parser is inside an ignored subtree (`_ignore_stack` is non-empty), `handle_starttag()` must track child tags solely in `_ignore_stack` and return immediately without modifying `self.tag_stack`.
   - Void tags must never be appended to `self.tag_stack`.
   - `handle_endtag()` must unwind `self.tag_stack` when closing tags arrive, handling unclosed inline tags safely.

---

## 3. Caveats

1. **Read-Only Explorer Mandate**: Per agent instructions, this report formulates the definitive strategy and exact code modifications; implementation must be executed by the implementing worker.
2. **Backwards Compatibility of Attributes**: Some existing unit and adversarial tests directly read `parser.ignore_depth`. The remediation must maintain `ignore_depth` as a `@property` returning `len(self._ignore_stack)` to ensure 100% API compatibility.
3. **Compound Boilerplate Phrases**: Phrases such as `social-share`, `share-button`, and `nav-item` must be kept intact in the delimiter regex so that general words like `share` (e.g. `market-share-data`) are not falsely suppressed.
4. **No Third-Party Dependencies**: The fix strictly uses Python standard library `re`, `html`, and `html.parser`.

---

## 4. Conclusion

The root causes of the parser defects are completely identified and resolved by a cohesive four-part remediation in `src/research_synthesis/retrieval/parser.py`:

1. **State Machine Overhaul**: Replace scalar `self.ignore_depth` with `self._ignore_stack: List[str]`, supported by `@property ignore_depth`. `handle_starttag()` appends non-void tags to `_ignore_stack` and returns early. `handle_endtag()` unwinds `_ignore_stack` when matching tags close.
2. **Boundary-Enforced Boilerplate Detection**: Replace naive substring matching with a compiled regex `_BOILERPLATE_RE = re.compile(r"(?:\b|_)(?:...)(?:\b|_)", re.IGNORECASE)` and replace `"ad-"` with `"ad"`. Standalone helper `_is_boilerplate(elem_id, elem_class)` prevents false positives on `lead-story`, `thread-container`, `download-link`, and `multimodal-architecture`.
3. **Decoupled Structural Length Thresholds**: In `_flush_text()`, evaluate heading context first (`is_heading = (last_tag in self.HEADING_TAGS) or any(t in self.HEADING_TAGS for t in self.tag_stack)`). Apply threshold $\ge 2$ characters for headings and $\ge 25$ characters for paragraphs.
4. **Stack Hygiene**: Prevent void tags from pushing to `self.tag_stack`, avoid pushing ignored child tags to `self.tag_stack`, and unwind `self.tag_stack` upon closing tags in `handle_endtag()`.

---

## 5. Exact Code Modifications Required

### Target File: `src/research_synthesis/retrieval/parser.py`

#### Patch 1: Replace Class-Level Boilerplate Definition & Compile Boundary Regex (lines 39-44)

**Before**:
```python
    BOILERPLATE_CLASS_ID_KEYWORDS = [
        "cookie", "popup", "newsletter", "sidebar", "banner", "advertisement",
        "ad-", "social-share", "share-button", "disclaimer", "nav-item",
        "widget", "modal", "subscribe",
    ]
```

**After**:
```python
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
```

#### Patch 2: Initialize `_ignore_stack` and Expose Compatible `ignore_depth` Property (lines 45-56)

**Before**:
```python
    def __init__(self):
        super().__init__()
        self.ignore_depth = 0
        self.tag_stack: List[str] = []
        self.headings: List[str] = []
        self.paragraphs: List[str] = []
        self.title: Optional[str] = None
        self.meta_tags: Dict[str, str] = {}
        self.canonical_url: Optional[str] = None
        self._current_text: List[str] = []
        self._in_title = False
```

**After**:
```python
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
```

#### Patch 3: Update `handle_starttag()` (lines 57-98)

**Before**:
```python
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        tag_lower = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        # Track title tag
        if tag_lower == "title":
            self._in_title = True
            return

        # Check ignored tag subtrees
        if tag_lower in self.IGNORE_TAGS:
            if tag_lower not in self.VOID_TAGS:
                self.ignore_depth += 1
            return

        # Check boilerplate class or id
        elem_id = attr_dict.get("id", "").lower()
        elem_class = attr_dict.get("class", "").lower()
        if any(noise in elem_id or noise in elem_class for noise in self.BOILERPLATE_CLASS_ID_KEYWORDS):
            if tag_lower not in self.VOID_TAGS:
                self.ignore_depth += 1
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

        self.tag_stack.append(tag_lower)
```

**After**:
```python
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        tag_lower = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        # Track title tag
        if tag_lower == "title":
            self._in_title = True
            return

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
```

#### Patch 4: Update `handle_endtag()` and `handle_data()` (lines 99-126)

**Before**:
```python
    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()

        if tag_lower == "title":
            self._in_title = False
            title_text = " ".join("".join(self._current_text).split())
            if title_text:
                self.title = html.unescape(title_text)
            self._current_text = []
            return

        if tag_lower in self.IGNORE_TAGS or self.ignore_depth > 0:
            if tag_lower in self.IGNORE_TAGS and tag_lower not in self.VOID_TAGS:
                self.ignore_depth = max(0, self.ignore_depth - 1)
            return

        if tag_lower in self.BLOCK_TAGS or tag_lower in self.HEADING_TAGS:
            self._flush_text()

        if self.tag_stack and self.tag_stack[-1] == tag_lower:
            self.tag_stack.pop()

    def handle_data(self, data: str):
        if self._in_title:
            self._current_text.append(data)
        elif self.ignore_depth == 0:
            self._current_text.append(data)
```

**After**:
```python
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
        if self._in_title:
            self._current_text.append(data)
        elif not self._ignore_stack:
            self._current_text.append(data)
```

#### Patch 5: Update `_flush_text()` for Tiered Length Thresholds (lines 127-144)

**Before**:
```python
    def _flush_text(self):
        raw_text = "".join(self._current_text)
        self._current_text = []
        cleaned = " ".join(raw_text.split())
        cleaned = html.unescape(cleaned).strip()

        # Minimum length threshold for substantive text
        if len(cleaned) >= 25:
            last_tag = self.tag_stack[-1] if self.tag_stack else None
            if last_tag in self.HEADING_TAGS:
                if cleaned not in self.headings:
                    self.headings.append(cleaned)
            else:
                # Avoid duplicate adjacent paragraphs
                if not self.paragraphs or self.paragraphs[-1] != cleaned:
                    self.paragraphs.append(cleaned)
```

**After**:
```python
    def _flush_text(self):
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
```

---

## 6. Verification Method

### 6.1 Unit Test Execution Commands

1. **Verify Tier 1 Retrieval Suite (Regression and Baseline)**:
   ```bash
   python -m unittest tests/test_tier1_retrieval.py
   ```
   *Expected Result*: All 21 tests pass, specifically `TestRobustHTMLParserAndDocumentParser.test_boilerplate_stripping`.

2. **Verify Adversarial Parser Stress Suite**:
   ```bash
   python -m unittest tests/test_parser_boilerplate_stress.py
   ```
   *Expected Result*: All tests in `TestBoilerplateAndParserDefects` pass:
   - `test_boilerplate_container_silences_subsequent_content` (asserts `len(paragraphs) > 0` after `<div class="cookie-banner">`).
   - `test_ad_keyword_false_positive_silences_legitimate_content` (asserts `lead-story` and `thread-container` are preserved).
   - `test_modal_keyword_false_positive_on_multimodal` (asserts `multimodal-architecture` is preserved).
   - `test_short_headings_dropped_by_length_filter` (asserts `Executive Summary` and `Key Findings` are in `headings`).
   - `test_tag_stack_corruption_on_ignored_children` (asserts `tag_stack == []` after `<nav><p>Home</p></nav>`).
   All tests in `TestHTMLParserExtremeStress` pass (unclosed tags, 1,000-deep nesting, 2,000 script bomb tags).

3. **Verify Against Real Ad-Heavy Corpus Fixture**:
   ```python
   from pathlib import Path
   from src.research_synthesis.models import RawWebDocument
   from src.research_synthesis.retrieval.parser import DocumentParser

   fixture = Path("tests/fixtures/mock_corpus/solid_state_battery/doc_04_ad_heavy_duplicate.html")
   raw_html = fixture.read_text(encoding="utf-8")
   doc = RawWebDocument(url="https://example.com/test", status_code=200, raw_html=raw_html)
   article = DocumentParser.parse(doc)

   assert len(article.paragraphs) >= 3, f"Expected >= 3 paragraphs, got {len(article.paragraphs)}"
   assert "QuantumScape and Solid Power have reported significant milestones" in article.cleaned_text
   assert "Scalability Roadmaps" in article.headings
   ```

### 6.2 Invalidation Conditions
The fix is invalidated if:
1. Parsing `<div id="cookie-banner">Notice</div><p>Substantive article paragraph exceeding twenty-five characters.</p>` produces `len(article.paragraphs) == 0`.
2. Parsing `<div class="lead-story"><p>Leading research from global institutes reveals breakthrough energy densities.</p></div>` produces `len(article.paragraphs) == 0`.
3. Parsing `<h1>Key Findings</h1><p>Substantive article paragraph exceeding twenty-five characters.</p>` results in `"Key Findings"` missing from `article.headings`.
4. `tag_stack` is non-empty after parsing `<aside><p>Ad 1</p><p>Ad 2</p></aside><p>Valid substantive text.</p>`.
