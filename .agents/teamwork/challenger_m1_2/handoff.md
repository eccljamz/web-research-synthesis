# Adversarial Challenge Report: Parser, Boilerplate Stripping & Model Serialization

**Milestone**: Milestone 1 (Query Decomposition & Web Retrieval)  
**Challenger**: Challenger 2 (Parser & Boilerplate Stress)  
**Verdict**: **REQUEST_CHANGES**  
**Overall Risk Assessment**: **CRITICAL**

---

## 1. Observation

### 1.1 Source Code Observations
1. **`src/research_synthesis/retrieval/parser.py:73-79` and `parser.py:110-113`**:
   ```python
   # Lines 73-78 in handle_starttag:
   elem_id = attr_dict.get("id", "").lower()
   elem_class = attr_dict.get("class", "").lower()
   if any(noise in elem_id or noise in elem_class for noise in self.BOILERPLATE_CLASS_ID_KEYWORDS):
       if tag_lower not in self.VOID_TAGS:
           self.ignore_depth += 1
       return

   # Lines 110-113 in handle_endtag:
   if tag_lower in self.IGNORE_TAGS or self.ignore_depth > 0:
       if tag_lower in self.IGNORE_TAGS and tag_lower not in self.VOID_TAGS:
           self.ignore_depth = max(0, self.ignore_depth - 1)
       return
   ```
   `BOILERPLATE_CLASS_ID_KEYWORDS` matches on tags such as `<div>` or `<section>`. However, `IGNORE_TAGS` (`parser.py:25-29`) contains only:
   `{"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "button", "iframe", "svg", "canvas", "select", "option", "dialog", "menu", "applet", "object", "embed"}`.
   `"div"`, `"section"`, and `"p"` are **not** in `IGNORE_TAGS`.

2. **`src/research_synthesis/retrieval/parser.py:39-43`**:
   ```python
   BOILERPLATE_CLASS_ID_KEYWORDS = [
       "cookie", "popup", "newsletter", "sidebar", "banner", "advertisement",
       "ad-", "social-share", "share-button", "disclaimer", "nav-item",
       "widget", "modal", "subscribe",
   ]
   ```
   The substring `"ad-"` matches words where `"ad-"` occurs as a substring:
   `"lead-story"`, `"lead-article"`, `"lead-summary"`, `"lead-paragraph"`, `"thread-container"`, `"download-link"`, `"upload-date"`, `"broad-overview"`, `"head-wrapper"`.
   The substring `"modal"` matches `"multimodal"` (e.g. `class="multimodal-architecture"`).

3. **`src/research_synthesis/retrieval/parser.py:133-143`**:
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
   The condition `if len(cleaned) >= 25:` wraps both paragraphs and headings. Real-world section headings such as `"Executive Summary"` (17 chars), `"Key Findings"` (12 chars), `"Introduction"` (12 chars), `"Abstract"` (8 chars), `"Methodology"` (11 chars), and `"Conclusion"` (10 chars) are strictly under 25 characters.

4. **`src/research_synthesis/retrieval/parser.py:97` and `parser.py:110-113`**:
   When a child tag (e.g. `<p>`) occurs within an ignored element (e.g. `<nav>`), `handle_starttag` executes line 97: `self.tag_stack.append(tag_lower)`. When the child closes (`</p>`), `handle_endtag` hits line 110 (`self.ignore_depth > 0`) and returns at line 113 **without** popping `tag_stack`.

5. **`src/research_synthesis/models.py:401`**:
   ```python
   # In ResearchBrief.to_dict():
   meta = dict(self.metadata)
   ```
   `models.py:331` defines the `BriefMetadata` dataclass. If `ResearchBrief` is instantiated with `metadata=BriefMetadata(...)`, `dict(self.metadata)` executes `dict(BriefMetadata(...))`, raising `TypeError: 'BriefMetadata' object is not iterable`.

6. **`src/research_synthesis/models.py:153-197`**:
   `RetrievalBatch` and `ScoredPassage` define `.to_dict()`, but define no `.from_dict()` method.

7. **`src/research_synthesis/models.py:94`**:
   ```python
   @classmethod
   def from_dict(cls, data: Dict[str, Any]) -> DocumentMetadata:
       return cls(**data)
   ```
   `DocumentMetadata` has `@property def doc_id(self)`. If a dictionary with key `"doc_id"` is passed to `DocumentMetadata.from_dict()`, `cls(**data)` crashes with `TypeError: DocumentMetadata.__init__() got an unexpected keyword argument 'doc_id'`.

8. **`src/research_synthesis/models.py:436`**:
   ```python
   cites = f" [{' ,'.join(str(c) for c in kt.citation_indices)}]" if kt.citation_indices else ""
   ```
   `' ,'.join` puts a space before the comma instead of after, producing `[1 ,2 ,3]`.

---

## 2. Logic Chain

1. **Boilerplate Container `ignore_depth` Leak (Observation 1.1 $\to$ Failure Mode 1)**:
   - When any element with a boilerplate class or id is encountered (such as `<div class="cookie-banner">` or `<div class="sidebar">`), `handle_starttag` increments `self.ignore_depth` by 1.
   - When the matching closing tag `</div>` is processed, `handle_endtag` checks `if tag_lower in self.IGNORE_TAGS and tag_lower not in self.VOID_TAGS:`.
   - Because `"div"` is not in `self.IGNORE_TAGS`, `self.ignore_depth` is never decremented.
   - `self.ignore_depth` remains $\ge 1$ for the rest of the document.
   - In `handle_data`, text is only captured when `self.ignore_depth == 0`.
   - **Result**: Every valid paragraph and heading following a cookie banner or sidebar is dropped. The parser emits an empty article or misses all substantive content.

2. **Noise Keyword Collisions Destroying Real Content (Observation 1.2 $\to$ Failure Mode 2)**:
   - Substring matching for `"ad-"` evaluates to `True` for `"lead-story"`, `"lead-article"`, `"thread-container"`, `"download-link"`, and `"broad-overview"`.
   - Substring matching for `"modal"` evaluates to `True` for `"multimodal-architecture"`.
   - Legitimate article sections with these classes are classified as ads. Combined with Failure Mode 1, opening any `lead-` div permanently silences the entire article.

3. **Heading Loss and Title Fallback Collapse (Observation 1.3 $\to$ Failure Mode 3)**:
   - Standard headings like `"Executive Summary"`, `"Key Findings"`, and `"Conclusion"` have fewer than 25 characters.
   - Line 134 filters out all text under 25 characters before checking `last_tag in self.HEADING_TAGS`.
   - As a result, `parser.headings` drops all standard headings.
   - In `DocumentParser.parse()`, line 188 falls back to `parser.headings[0]` when `<title>` and `og:title` are missing. Because `parser.headings` is empty, this fallback fails.

4. **Tag Stack Desynchronization (Observation 1.4 $\to$ Failure Mode 4)**:
   - Tags inside ignored trees push to `tag_stack` but are skipped on pop due to the early `return` in `handle_endtag`.
   - This corrupts `tag_stack[-1]`, leading subsequent text flushes to misidentify block types.

5. **`TypeError` in `ResearchBrief.to_dict()` (Observation 1.5 $\to$ Failure Mode 5)**:
   - `models.py` provides `BriefMetadata` as the standard schema container for brief metadata.
   - Calling `to_dict()` on a `ResearchBrief` holding a `BriefMetadata` instance executes `dict(self.metadata)`, which crashes with `TypeError`.

---

## 3. Adversarial Challenges & Mitigations

### [Critical] Challenge 1: Boilerplate `<div>` / `<section>` Silences Entire Document
- **Assumption challenged**: `RobustHTMLParser` accurately tracks nested ignore depth across boilerplate containers.
- **Attack scenario**: Real-world pages typically place cookie popups (`<div class="cookie-banner">`) or sidebars (`<div class="sidebar">`) near the top of the body before the main article.
- **Blast radius**: Complete data loss. The parser extracts 0 paragraphs for any page containing a boilerplate container tag not in `IGNORE_TAGS`.
- **Mitigation**:
  Track opened boilerplate tags on a stack or record tag identity. For example:
  ```python
  # In handle_starttag:
  if is_ignored or is_boilerplate:
      if tag_lower not in self.VOID_TAGS:
          self.ignored_stack.append(tag_lower)
      return

  # In handle_endtag:
  if self.ignored_stack:
      if self.ignored_stack[-1] == tag_lower:
          self.ignored_stack.pop()
      return
  ```
  And check `self.ignore_depth = len(self.ignored_stack)`.

### [Critical] Challenge 2: Keyword False Positives on Standard Class Names
- **Assumption challenged**: Substring matching against `BOILERPLATE_CLASS_ID_KEYWORDS` is specific to noise.
- **Attack scenario**: News and technical sites widely use `lead-story`, `thread-container`, `download-paper`, and `multimodal-pipeline`.
- **Blast radius**: Falsely flags core article sections as ads, triggering Challenge 1 and discarding the entire article.
- **Mitigation**:
  Match against tokenized class names (`elem_class.split()`) and check prefixes/words rather than naive substrings (e.g., `cls.startswith("ad-")` or `cls in {"ad", "ads", "advertisement"}`). For `"modal"`, match exact word `"modal"` rather than substring `"modal"` inside `"multimodal"`.

### [High] Challenge 3: Dropping Headings Under 25 Characters
- **Assumption challenged**: Substantive content length threshold ($\ge 25$) should apply uniformly to headings and body text.
- **Attack scenario**: Articles structured with standard academic or industry headings (`"Key Findings"`, `"Overview"`, `"Abstract"`).
- **Blast radius**: All short headings are wiped from `CleanArticle.headings`, and `DocumentParser` fallback title resolution fails.
- **Mitigation**:
  Separate threshold logic: allow headings with `len(cleaned) >= 2`, and apply $\ge 25$ only to paragraphs:
  ```python
  last_tag = self.tag_stack[-1] if self.tag_stack else None
  if last_tag in self.HEADING_TAGS:
      if len(cleaned) >= 2 and cleaned not in self.headings:
          self.headings.append(cleaned)
  elif len(cleaned) >= 25:
      if not self.paragraphs or self.paragraphs[-1] != cleaned:
          self.paragraphs.append(cleaned)
  ```

### [High] Challenge 4: Dataclass Type Error in `ResearchBrief.to_dict()`
- **Assumption challenged**: `ResearchBrief.to_dict()` supports both dictionary and `BriefMetadata` dataclass instances.
- **Attack scenario**: Synthesis module passes `BriefMetadata` object into `ResearchBrief(..., metadata=brief_meta)`.
- **Blast radius**: `brief.to_dict()` and `brief.to_json()` raise an unhandled `TypeError`.
- **Mitigation**:
  ```python
  meta = self.metadata.to_dict() if hasattr(self.metadata, "to_dict") else asdict(self.metadata) if is_dataclass(self.metadata) else dict(self.metadata)
  ```

### [Medium] Challenge 5: Missing `from_dict()` on `RetrievalBatch` and `ScoredPassage`
- **Assumption challenged**: Models provide symmetric serialization.
- **Attack scenario**: Upstream or test fixtures attempt to reconstruct `RetrievalBatch` from JSON/dict.
- **Blast radius**: `AttributeError` when attempting deserialization.
- **Mitigation**: Implement `from_dict()` for `RetrievalBatch` and `ScoredPassage`.

### [Medium] Challenge 6: `DocumentMetadata.from_dict()` Rejection of `doc_id`
- **Assumption challenged**: `DocumentMetadata` can deserialize dicts output by `asdict` or storage layers where `doc_id` is included.
- **Attack scenario**: Worker claimed compatibility between `meta.doc_id` and `article.doc_id`. Deserializing any document dictionary containing `doc_id` crashes.
- **Blast radius**: `TypeError` on metadata restoration.
- **Mitigation**: Filter out `doc_id` or ignore unexpected keys in `DocumentMetadata.from_dict()`.

### [Low] Challenge 7: Spacing Typo in Citation Rendering
- **Assumption challenged**: Markdown citations conform to clean typography.
- **Attack scenario**: `brief.to_markdown()` with multiple takeaway citations.
- **Blast radius**: Emits `[1 ,2 ,3]` with a space before the comma.
- **Mitigation**: Replace `' ,'.join` with `', '.join`.

---

## 4. Caveats

- Live network scraping rate-limiting under high concurrency was not evaluated via network calls due to offline environment guidelines.
- Tested against standard Python 3.10+ `html.parser.HTMLParser` behavior.

---

## 5. Conclusion & Actionable Items

**Verdict**: **REQUEST_CHANGES**

Milestone 1 cannot be approved in its current state because `RobustHTMLParser` contains a fatal logic flaw that silences substantive content on any real-world web page containing a cookie popup or sidebar, false-positive keyword matching deletes legitimate content, and `ResearchBrief.to_dict()` crashes when using `BriefMetadata`.

### Required Fixes for Worker:
1. Fix `RobustHTMLParser` to properly track and decrement `ignore_depth` when non-`IGNORE_TAGS` (like `div`, `section`) with boilerplate classes close.
2. Refine `BOILERPLATE_CLASS_ID_KEYWORDS` matching to avoid false positives on `"lead-"`, `"thread-"`, `"download-"`, and `"multimodal"`.
3. Separate the heading length threshold from the paragraph threshold so that headings under 25 characters are preserved.
4. Ensure child tags within ignored elements do not leak onto `tag_stack`.
5. Update `ResearchBrief.to_dict()` to handle `BriefMetadata` dataclass instances without raising `TypeError`.
6. Add `from_dict()` methods to `RetrievalBatch` and `ScoredPassage`.
7. Allow `DocumentMetadata.from_dict()` to ignore `doc_id` if present.
8. Fix citation list separator in `ResearchBrief.to_markdown()` from `' ,'` to `', '`.

---

## 6. Verification Method

### Test Suite Location
Adversarial test suite created at:
`tests/test_parser_boilerplate_stress.py`

### Inspection Points
1. `src/research_synthesis/retrieval/parser.py`: Inspect `handle_starttag` lines 73-79 and `handle_endtag` lines 110-113.
2. `src/research_synthesis/retrieval/parser.py`: Inspect `_flush_text` line 134.
3. `src/research_synthesis/models.py`: Inspect line 401 (`meta = dict(self.metadata)`).

### Invalidation Conditions
- A web page with `<div class="cookie-banner"><p>Cookies</p></div><p>Substantive article paragraph...</p>` successfully returns the article paragraph in `CleanArticle.paragraphs`.
- `CleanArticle.headings` includes `"Executive Summary"` when parsed from `<h1>Executive Summary</h1>`.
- `ResearchBrief(..., metadata=BriefMetadata(...)).to_dict()` executes without `TypeError`.
