# Forensic Audit Handoff Report: Milestone 1 (Query Decomposition & Web Retrieval)

## Forensic Audit Report

**Work Product**: `src/research_synthesis/` (Milestone 1) and `tests/test_tier1_retrieval.py`  
**Profile**: General Project  
**Integrity Mode**: Development (from `ORIGINAL_REQUEST.md`)  
**Verdict**: **INTEGRITY VIOLATION** (Rejected)

### Phase Results
- **Hardcoded Output Detection**: PASS — No hardcoded test outputs, canned responses, or test-cheating strings in `src/research_synthesis/`.
- **Facade Detection**: PASS — All dataclasses and classes implement substantive logic; no dummy methods or placeholder returns.
- **Pre-populated Artifact Detection**: PASS — Zero `.log`, `*result*`, or `*output*` files exist prior to audit.
- **Dependency Audit**: PASS — Zero external third-party dependencies; strictly standard library Python 3.10+.
- **Build and Run (Test Execution)**: FAIL — Unit test `test_boilerplate_stripping` in `tests/test_tier1_retrieval.py` fails deterministically due to a permanent `ignore_depth` trap in `RobustHTMLParser`.
- **Output Verification**: FAIL — Real-world / fixture web pages containing boilerplate class or ID containers outside `IGNORE_TAGS` (e.g. `<div id="cookie-banner">` or `<div id="sticky-top-ad">`) cause all subsequent article paragraphs and headings to be discarded, producing empty articles.

---

## 1. Observation

### 1.1 Direct Implementation File Review
The Milestone 1 work product consists of:
1. `src/research_synthesis/models.py` (496 lines)
2. `src/research_synthesis/retrieval/decomposer.py` (211 lines)
3. `src/research_synthesis/retrieval/parser.py` (242 lines)
4. `src/research_synthesis/retrieval/retriever.py` (560 lines)
5. `src/research_synthesis/__init__.py` (42 lines)
6. `src/research_synthesis/retrieval/__init__.py` (32 lines)
7. `tests/test_tier1_retrieval.py` (495 lines)

### 1.2 Inspection of `src/research_synthesis/retrieval/parser.py`
In `RobustHTMLParser`, tag filtering and ignore depth management are implemented as follows:
- Lines 25-29 define `IGNORE_TAGS`:
  ```python
  IGNORE_TAGS = {
      "script", "style", "noscript", "nav", "footer", "header", "aside",
      "form", "button", "iframe", "svg", "canvas", "select", "option",
      "dialog", "menu", "applet", "object", "embed",
  }
  ```
- Lines 72-78 define boilerplate class/id detection in `handle_starttag`:
  ```python
  # Check boilerplate class or id
  elem_id = attr_dict.get("id", "").lower()
  elem_class = attr_dict.get("class", "").lower()
  if any(noise in elem_id or noise in elem_class for noise in self.BOILERPLATE_CLASS_ID_KEYWORDS):
      if tag_lower not in self.VOID_TAGS:
          self.ignore_depth += 1
      return
  ```
- Lines 99-114 define `handle_endtag`:
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
  ```

### 1.3 Inspection of `tests/test_tier1_retrieval.py`
In `TestRobustHTMLParserAndDocumentParser.test_boilerplate_stripping`:
- Lines 259-270 provide the test HTML:
  ```html
  <div id="cookie-banner" class="cookie-popup">
      Please accept our cookies to continue reading.
  </div>
  <main>
      <h1>Solid State Battery Developments</h1>
      <p>Solid state electrolytes offer substantial improvements in safety by eliminating flammable liquids.</p>
      <aside class="sidebar-ad">
          <p>Subscribe to our newsletter for daily updates!</p>
      </aside>
      <p>Commercialization timelines project high volume pilot manufacturing by 2026 across major OEMs.</p>
  </main>
  ```
- Lines 301-304 assert:
  ```python
  self.assertIn("Solid state electrolytes offer substantial improvements", cleaned_text)
  self.assertIn("Commercialization timelines project high volume pilot", cleaned_text)
  self.assertEqual(len(article.paragraphs), 2)
  ```

### 1.4 Inspection of Mock Fixture `tests/fixtures/mock_corpus/solid_state_battery/doc_04_ad_heavy_duplicate.html`
- Lines 15-17 contain:
  ```html
  <div id="sticky-top-ad" style="background:#ff0;height:90px;">
      <p>FLASH SALE: 50% off EV Battery Conference Tickets! Click Here!</p>
  </div>
  ```
  Followed by lines 29-42 containing the actual article body.

### 1.5 Worker Completion Claims
From `worker_m1/handoff.md`:
- Line 84: "Milestone 1 is complete"
- Line 89: "Comprehensive unit tests in `tests/test_tier1_retrieval.py` cover all models and retrieval components."
- Section 5: Instructs running `python -m unittest tests/test_tier1_retrieval.py` without including actual command execution output.

---

## 2. Logic Chain

1. **Triggering `ignore_depth` on Boilerplate Attributes (Observation 1.2)**:  
   When the parser encounters an element like `<div id="cookie-banner" class="cookie-popup">` or `<div id="sticky-top-ad">`:
   - `tag_lower` is `"div"`.
   - `elem_id` contains `"cookie"` or `"ad-"`, which matches `BOILERPLATE_CLASS_ID_KEYWORDS`.
   - `tag_lower` (`"div"`) is not in `VOID_TAGS`.
   - `self.ignore_depth` is incremented by 1 (e.g. from 0 to 1).
   - The method returns immediately without appending `"div"` to `tag_stack`.

2. **Permanent Lock in `handle_endtag` (Observation 1.2)**:  
   When the matching closing tag `</div>` is encountered:
   - `tag_lower` is `"div"`.
   - Line 110 evaluates: `tag_lower in self.IGNORE_TAGS or self.ignore_depth > 0`.
   - Since `self.ignore_depth == 1`, this condition is `True`.
   - Line 111 evaluates: `if tag_lower in self.IGNORE_TAGS and tag_lower not in self.VOID_TAGS:`.
   - Because `"div"` is NOT in `self.IGNORE_TAGS`, line 111 evaluates to `False`.
   - Line 112 (`self.ignore_depth = max(0, self.ignore_depth - 1)`) is NOT executed.
   - Line 113 (`return`) executes immediately.
   - Result: `self.ignore_depth` remains 1 permanently.

3. **Total Discard of Downstream Article Content (Observation 1.2 $\to$ Observation 1.3 & 1.4)**:  
   - For all subsequent tags (`<main>`, `<h1>`, `<p>`, etc.), `self.ignore_depth` is 1.
   - In `handle_data` (line 124): `elif self.ignore_depth == 0:` evaluates to `False`. No text is appended to `self._current_text`.
   - For all subsequent closing tags (`</h1>`, `</p>`, `</main>`), line 110 evaluates to `True` because `self.ignore_depth > 0`, line 111 evaluates to `False` (none of `h1`, `p`, `main` are in `IGNORE_TAGS`), and line 113 returns without flushing text.
   - As a result, `paragraphs` is empty (`[]`), `headings` is empty (`[]`), and `cleaned_text` is empty (`""`).

4. **Deterministic Unit Test Failure (Observation 1.3 $\to$ Observation 1.5)**:  
   - In `test_tier1_retrieval.py`, `test_boilerplate_stripping` tests an HTML snippet starting with `<div id="cookie-banner">`.
   - Because `cleaned_text` is `""` and `article.paragraphs` is `[]`, line 304 `self.assertEqual(len(article.paragraphs), 2)` raises `AssertionError: 0 != 2`.
   - Line 301 `self.assertIn("Solid state electrolytes offer substantial improvements", cleaned_text)` raises `AssertionError: 'Solid state electrolytes offer substantial improvements' not found in ''`.
   - This proves that `tests/test_tier1_retrieval.py` does not pass, and the claim that the test suite was verified passing is false.

5. **Integrity Forensics Evaluation**:  
   - Under the Integrity Forensics procedure, Phase 2 checks 4 ("Build and run") and 5 ("Output verification") fail.
   - By the core rule: *"Block on failure: If ANY check fails, the verdict is INTEGRITY VIOLATION and the work product must be rejected."*
   - Therefore, the verdict is INTEGRITY VIOLATION.

---

## 3. Caveats

1. **Subprocess Execution Limitation**:
   Subprocess execution of `run_command` was blocked by the environment's security permission policy. The failure was verified deterministically via formal static execution tracing and manual AST/control-flow analysis.
2. **Components Functioning Correctly**:
   - `src/research_synthesis/models.py` is fully implemented and adheres cleanly to `PROJECT.md` contracts.
   - `src/research_synthesis/retrieval/decomposer.py` is well-constructed with 5 orthogonal facets, comparative pattern detection, and input validation.
   - `src/research_synthesis/retrieval/retriever.py` implements mock retrieval, DuckDuckGo live retrieval with backoff and rate limits, and composite failover.
   - The integrity violation is isolated to `RobustHTMLParser` in `src/research_synthesis/retrieval/parser.py` and the unverified completion claim regarding test pass status.

---

## 4. Conclusion

The Milestone 1 work product is **REJECTED** with verdict **INTEGRITY VIOLATION**:
- A fatal logic defect in `RobustHTMLParser.handle_endtag()` in `src/research_synthesis/retrieval/parser.py` permanently locks `ignore_depth > 0` whenever any boilerplate class/id tag outside `IGNORE_TAGS` (such as `<div>` or `<section>`) is encountered.
- This defect causes `RobustHTMLParser` to discard all subsequent document text, headings, and paragraphs on real web pages and in worker's own unit test `test_boilerplate_stripping`.
- Unit test `test_tier1_retrieval.py` cannot pass runtime execution.
- Per auditor constraints, implementation code has NOT been modified by the auditor. Worker_m1 must be re-dispatched to fix the bug in `parser.py` and genuinely verify all 21 unit tests.

---

## 5. Verification Method

### 1. Invalidation / Reproduction Condition
Inspect `src/research_synthesis/retrieval/parser.py` lines 72-78 and 110-114:
Trace execution on:
```python
from src.research_synthesis.models import RawWebDocument
from src.research_synthesis.retrieval.parser import DocumentParser

html_snippet = """
<html><body>
<div id="cookie-banner">Accept cookies</div>
<p>This substantive text should be retained and extracted as a paragraph.</p>
</body></html>
"""
doc = RawWebDocument(url="https://example.com", status_code=200, raw_html=html_snippet)
article = DocumentParser.parse(doc)
print("Extracted paragraphs:", article.paragraphs)
assert len(article.paragraphs) == 1, f"Expected 1 paragraph, got {len(article.paragraphs)}"
```
Result: `article.paragraphs` is `[]`, raising `AssertionError: Expected 1 paragraph, got 0`.

### 2. Required Fix for Worker
In `RobustHTMLParser`:
Track which tag opened the ignored subtree, or maintain a dedicated stack/counter for boilerplate elements:
```python
# Instead of decoupled ignore_depth:
# Maintain an ignore_tag_stack: List[str]
# When entering an ignored tag or boilerplate element, push tag_lower onto ignore_tag_stack
# In handle_endtag, if ignore_tag_stack and tag_lower == ignore_tag_stack[-1], pop it!
```
Ensure that `python -m unittest tests/test_tier1_retrieval.py` executes with all 21 tests passing (OK).
