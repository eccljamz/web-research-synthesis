# Test Alignment Strategy & Verification Suite Report: Milestone 2 Remediation

**Agent**: `explorer_m2_fix_3`  
**Role**: Remediation Explorer 3 (Unit & Adversarial Test Alignment)  
**Parent Conversation ID**: `42364d7e-0273-4faa-be7a-22e0c17eecea`  
**Working Directory**: `C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\explorer_m2_fix_3`  
**Date**: 2026-10-13  
**Status**: Investigation & Test Alignment Complete  

---

## 1. Observation

### 1.1 Direct Source Observations: Existing Tier 1 Extraction Tests
In `tests/test_tier1_extraction.py`, three existing tests exercise near-duplicate lookup and deduplication:

#### Observation 1.1: `test_pigeonhole_retrieval` (Lines 335–348)
```python
335:     def test_pigeonhole_retrieval(self):
336:         index = SimHashIndex(threshold=3)
337:         t1 = "Our computable general equilibrium econometric simulations indicate that severe fragmentation into competing trading blocs could reduce global GDP by 1.2% to 1.8%."
338:         fp1 = SimHash64.compute_simhash(t1)
339:         index.add("doc-1", fp1, metadata={"title": "IMF Outlook"})
340: 
341:         # Near-duplicate query
342:         t2 = "Computable general equilibrium econometric simulations indicate that severe fragmentation into competing trading blocs could reduce global GDP by 1.2% to 1.8%."
343:         fp2 = SimHash64.compute_simhash(t2)
344:         matches = index.find_near_duplicates(fp2)
345:         self.assertEqual(len(matches), 1)
346:         self.assertEqual(matches[0][0], "doc-1")
347:         self.assertLessEqual(matches[0][1], 3)
```
- Line 339 passes a mutable `dict` as payload: `metadata={"title": "IMF Outlook"}`.
- Line 344 calls `index.find_near_duplicates(fp2)`. Because `t1` and `t2` differ only by "Our ", Hamming distance is $\le 3$, causing at least one 16-bit block key to match across the 4 index tables.
- In `src/research_synthesis/extraction/dedup.py` line 287, `candidates.update(self.tables[i][key])` executes `set.update()` on `_IndexEntry`. Under Python 3 dataclass semantics (PEP 557), unfrozen dataclasses have `__hash__ = None`. This raises `TypeError: unhashable type: '_IndexEntry'`.

#### Observation 1.2: `test_near_duplicate_passages_merged_with_attribution` (Lines 390–400)
```python
390:     def test_near_duplicate_passages_merged_with_attribution(self):
391:         p1 = ScoredPassage("p-001", "doc-01", "https://source-a.org/article", "Source A",
392:                            "Operating dry rooms at this specification incurs a capital expenditure premium of $18 million to $25 million per gigawatt-hour.", 0.80, "battery", 20)
393:         p2 = ScoredPassage("p-002", "doc-02", "https://source-b.com/reprint", "Source B",
394:                            "Operating dry rooms at this specification incurs capital expenditure premium of $18 million to $25 million per gigawatt-hour.", 0.75, "battery", 19)
395: 
396:         results = self.dedup.deduplicate_passages([p1, p2])
397:         self.assertEqual(len(results), 1)
398:         self.assertEqual(len(results[0].secondary_urls), 1)
399:         self.assertEqual(results[0].secondary_urls[0], "https://source-b.com/reprint")
```
- Line 396 invokes `self.dedup.deduplicate_passages([p1, p2])`.
- In `TwoStageDeduplicator.deduplicate_passages` (line 458), `p1` is stored via `index.add(p.passage_id, fp, metadata=p)` where `p` is an unfrozen `ScoredPassage` dataclass holding mutable list `secondary_urls`.
- For `p2`, exact hashes differ (missing "a"), which routes `p2` to Stage 2 (`index.find_near_duplicates(fp)` at line 449).
- Matching bucket lookup triggers line 287 `candidates.update(...)` and raises `TypeError: unhashable type: '_IndexEntry'`.

#### Observation 1.3: `test_deduplicate_claims` (Lines 401–414)
```python
401:     def test_deduplicate_claims(self):
402:         c1 = ExtractedClaim("clm-1", "Room-temperature ionic conductivities surpassed 12.0 mS/cm at 25°C.", "d1",
403:                             "https://source1.com/art", "Title 1", "snippet", 0.80, ClaimType.QUANTITATIVE, ["LLZO"], [])
404:         c2 = ExtractedClaim("clm-2", "Room temperature ionic conductivities surpassed 12.0 mS/cm at 25°C.", "d2",
405:                             "https://source2.com/art", "Title 2", "snippet", 0.90, ClaimType.QUANTITATIVE, ["argyrodite"], [])
406: 
407:         results = self.dedup.deduplicate_claims([c1, c2])
408:         self.assertEqual(len(results), 1)
409:         survivor = results[0]
410:         self.assertEqual(survivor.confidence_score, 0.90)
411:         self.assertIn("https://source2.com/art", survivor.secondary_urls)
412:         self.assertIn("LLZO", survivor.entities)
413:         self.assertIn("argyrodite", survivor.entities)
```
- Line 407 invokes `self.dedup.deduplicate_claims([c1, c2])`.
- In `TwoStageDeduplicator.deduplicate_claims` (line 504), `c1` is stored via `index.add(c.claim_id, fp, metadata=c)` where `c` is an unfrozen `ExtractedClaim` dataclass holding mutable lists `entities` and `secondary_urls`.
- For `c2`, near-duplicate lookup in Stage 2 triggers `candidates.update(...)` and raises `TypeError: unhashable type: '_IndexEntry'`.

### 1.2 Direct Source Observations: Adversarial Test Gap in Near-Duplicate Stage 2
In `tests/test_adversarial_m2_simhash_claims.py`:
- In `TestSimHashDistinctTextsStress.test_pigeonhole_false_positive_rejection` (lines 147–159):
  The tested pairs are from disjoint domains (Battery vs Agriculture) with Hamming distance > 10. No 16-bit block keys matched across any table. Therefore, `key in self.tables[i]` evaluated to `False` for all tables, and line 287 was never executed.
- In `TestTwoStageDeduplicatorTransitiveAttributionStress`:
  - `test_transitive_attribution_merging_five_passages` (lines 167–198): All 5 passages shared exact identical text string `content`.
  - `test_transitive_attribution_with_preexisting_secondary_urls` (lines 199–223): All passages shared identical text.
  - `test_transitive_claim_attribution_and_entity_merging` (lines 224–249): All claims shared identical text.
- Because the text was identical, Stage 1 exact hash check (`exact_hash in exact_hash_map`) intercepted all duplicates. Stage 2 (`index.find_near_duplicates`) was never called. This explains why the adversarial suite did not flag the `TypeError` during prior reviews.

### 1.3 Direct Source Observations: Abbreviation Heuristics in `claims.py`
In `src/research_synthesis/extraction/claims.py`:
- Line 44 defines:
  ```python
  r"No\.", r"Fig\.", r"Vol\.", r"pp\.", r"p\.", r"Ph\.D\.", r"M\.D\."
  ```
- Line 147 compiles the pattern with `re.IGNORECASE`:
  ```python
  self._abbr_regex = re.compile(rf"\b({abbr_joined})", re.IGNORECASE)
  ```
- In `segment_sentences` (lines 175–181):
  ```python
  def _mask_abbr(m: re.Match) -> str:
      return m.group(0).replace(".", "@@DOT@@")

  cleaned = self._abbr_regex.sub(_mask_abbr, cleaned)
  raw_splits = re.split(r"(?<=[.!?])\s+", cleaned)
  ```
- Because of `re.IGNORECASE` matching `\bNo\.`:
  In `"The answer was no. We continued."`, `"no."` is matched as an abbreviation. Its period is replaced with `@@DOT@@`. When `re.split` executes, there is no terminal period between "no" and "We", preventing sentence splitting and collapsing the two sentences into one.
- In `"See p. 42 for details."`, `r"p\."` matches `p.`, correctly masking the abbreviation before the page number. However, if unconstrained, `p.` also suppresses periods in ordinary clauses or mathematical variable sentences (e.g., `"Let the probability be p. We calculate..."`).
- Furthermore, in line 194 of `claims.py`:
  ```python
  if len(s) >= 10 and len(s.split()) >= self.min_words:
      sentences.append(s)
  ```
  Where `self.min_words = 5` by default (line 131). If short sentences are segmented, `"The answer was no."` (4 words) and `"We continued."` (2 words) would both be dropped by `len(s.split()) >= self.min_words` unless this length guardrail in `segment_sentences` is aligned with general sentence segmentation, leaving claim-level minimum word filtering to `is_noise_or_non_claim` (lines 209–211).

---

## 2. Logic Chain

### 2.1 Direct Validation of Dictionary Fix by Tier 1 Extraction Tests
1. **Candidate Fix Mechanism**:
   In `src/research_synthesis/extraction/dedup.py`, lines 282–288:
   ```python
   candidates: Dict[str, _IndexEntry] = {}
   for i, key in enumerate(keys):
       if key in self.tables[i]:
           for entry in self.tables[i][key]:
               candidates[entry.item_id] = entry
   ```
2. **Type Safety Validation**:
   - `candidates` is keyed by `entry.item_id: str`. In Python, strings are immutable and hashable.
   - Neither `_IndexEntry` nor its `metadata` field is passed to `hash()`.
   - Therefore, regardless of whether `metadata` is a `dict`, `ScoredPassage`, `ExtractedClaim`, `list`, `set`, or `None`, no `TypeError` can be thrown.
3. **Pigeonhole Retrieval Alignment**:
   - `test_pigeonhole_retrieval` directly exercises `SimHashIndex.find_near_duplicates(fp2)` with `metadata={"title": "IMF Outlook"}`.
   - Under the broken code: Crashes with `TypeError: unhashable type: '_IndexEntry'`.
   - Under the dictionary fix: Populates `candidates["doc-1"] = entry`, calculates Hamming distance $\le 3$, and returns `[('doc-1', dist, {'title': 'IMF Outlook'})]`.
   - `test_pigeonhole_retrieval` directly and strictly validates the candidate fix.
4. **Near-Duplicate Passage Merging Alignment**:
   - `test_near_duplicate_passages_merged_with_attribution` exercises `TwoStageDeduplicator.deduplicate_passages([p1, p2])` where `p1` has `metadata=p1` (`ScoredPassage`).
   - Because `p2` differs by one word, it bypasses Stage 1 exact match and triggers Stage 2 `index.find_near_duplicates`.
   - Under the broken code: Crashes with `TypeError`.
   - Under the dictionary fix: Successfully matches `p1` via `candidates`, merges `p2.url` into `p1.secondary_urls`, pools maximum score (0.80), and returns `[p1]`.
   - `test_near_duplicate_passages_merged_with_attribution` directly validates end-to-end passage deduplication with mutable `ScoredPassage` metadata.
5. **Near-Duplicate Claim Merging Alignment**:
   - `test_deduplicate_claims` exercises `TwoStageDeduplicator.deduplicate_claims([c1, c2])` where `c1` has `metadata=c1` (`ExtractedClaim`).
   - `c1` and `c2` differ by hyphenation ("Room-temperature" vs "Room temperature"), routing `c2` into Stage 2.
   - Under the broken code: Crashes with `TypeError`.
   - Under the dictionary fix: Matches `c1` via `candidates`, merges attribution and secondary URLs, pools confidence score to 0.90, and unions entities `{"LLZO", "argyrodite"}`.
   - `test_deduplicate_claims` directly validates end-to-end claim deduplication with mutable `ExtractedClaim` metadata.

### 2.2 Necessity of Explicit Unit Tests for Mutable Metadata Payloads
1. While the three existing tests provide end-to-end coverage, they do not isolate all possible edge cases:
   - What if an item matches across all 4 bucket tables (Hamming distance 0)? The dictionary approach must ensure the entry is deduplicated and returned only once in `find_near_duplicates`.
   - What if deeply nested mutable structures (e.g., dict containing lists and sets) are stored?
   - What if mutable objects are modified in-place after insertion?
2. Therefore, adding explicit, dedicated unit tests to `TestSimHashIndex` in `tests/test_tier1_extraction.py` and adding a new stress class in `tests/test_adversarial_m2_simhash_claims.py` guarantees long-term regression immunity.

### 2.3 Sentence Splitting Logic & Abbreviation Alignment
1. **Defect in Abbreviation Regex**:
   Matching `r"No\."` with `re.IGNORECASE` treats lowercase `"no."` as an abbreviation. In English prose, `"no."` followed by a space at the end of a sentence (e.g. `"The answer was no. We continued."`) is a sentence boundary, not an abbreviation for "Number".
   Conversely, `"p."` is an abbreviation for "page" when followed by digits (e.g., `"See p. 42 for details."`), but should not swallow terminal periods indiscriminately.
2. **Refined Abbreviation Rules**:
   - `r"No\.\s*\d+"` (or `r"No\.\s*(?=\d)"`): Only treat as abbreviation when followed by a number or digit sequence (e.g., "No. 5", "No. 12").
   - `r"p\.\s*\d+"` (or `r"p\.\s*(?=\d)"`): Only treat as abbreviation when followed by a page number (e.g., "p. 42", "p. 101").
   - Similarly `r"pp\.\s*\d+"`: Only treat as abbreviation when followed by page range (e.g., "pp. 42-45").
3. **Behavior on Target Test Sentences**:
   - `"The answer was no. We continued."`:
     `"no."` is NOT followed by digits $\implies$ Not matched by `_abbr_regex` $\implies$ Period retained $\implies$ Split into 2 sentences:
     1. `"The answer was no."`
     2. `"We continued."`
   - `"See p. 42 for details."`:
     `"p. 42"` IS followed by digits $\implies$ Matched by `_abbr_regex` $\implies$ `.` in `p.` masked with `@@DOT@@` $\implies$ Terminal period in `details.` unmasked $\implies$ Remains 1 sentence:
     1. `"See p. 42 for details."`
4. **Length Guardrail Alignment in `segment_sentences`**:
   Sentence segmentation is a structural tokenizer. Filtering substantive sentences based on claim-level thresholds (`self.min_words = 5`) inside `segment_sentences` causes short sentences (such as `"The answer was no."` [4 words] and `"We continued."` [2 words], as well as existing test sentences like `"First sentence here."` [3 words]) to be discarded entirely.
   In `segment_sentences`, the filter should only reject empty/whitespace fragments (`if len(s.strip()) > 0:` or `if len(s.split()) >= 1:`). Filtering out non-factual or short claims belongs strictly in `is_noise_or_non_claim()` (line 210), which already implements `if word_count < self.min_words or word_count > self.max_words: return True`.

---

## 3. Caveats

1. **Subprocess Execution Policy**:
   Terminal command execution (`run_command`) is restricted by environment security policy. All verification logic has been traced through standard Python runtime semantics (PEP 557), formal AST analysis, regex state transitions, and test assertions.
2. **Coordinated Multi-Explorer Alignment**:
   Remediation Explorer 1 (`explorer_m2_fix_1`) focuses on the code patch for `dedup.py`. Remediation Explorer 2 (`explorer_m2_fix_2`) focuses on the code patch for `claims.py`. This report (`explorer_m2_fix_3`) provides the unified test alignment specifications and test suite enhancements across both files.

---

## 4. Conclusion

1. **Candidate Fix Validation**:
   The three existing tests in `tests/test_tier1_extraction.py` (`test_pigeonhole_retrieval`, `test_near_duplicate_passages_merged_with_attribution`, `test_deduplicate_claims`) directly and strictly validate the dictionary-based `SimHashIndex` fix.
2. **Unit Test Suite Enhancement**:
   Four new explicit unit tests in `tests/test_tier1_extraction.py` and an adversarial test suite in `tests/test_adversarial_m2_simhash_claims.py` are specified to verify that mutable metadata (`dict`, `ScoredPassage`, `ExtractedClaim`, nested structures) never raises `TypeError` and that multi-bucket matches are cleanly deduplicated.
3. **Abbreviation Sentence Splitting Verification**:
   Refining `No.` and `p.` to require following numeric context (`r"No\.\s*\d+"`, `r"p\.\s*\d+"`) and aligning `segment_sentences` length filtering confirms:
   - `"The answer was no. We continued."` splits into **2 sentences**.
   - `"See p. 42 for details."` remains **1 sentence**.

---

## 5. Test Alignment Specifications & Code Additions

### 5.1 Additions to `tests/test_tier1_extraction.py`

#### A. Add Explicit Mutable Metadata Tests to `TestSimHashIndex`
Insert into `TestSimHashIndex` (after line 355):

```python
    def test_simhash_index_with_mutable_dict_metadata(self):
        """Verify inserting mutable dict metadata does not raise TypeError."""
        index = SimHashIndex(threshold=3)
        meta = {"source": "IMF", "nested": {"count": 42}, "tags": ["econ", "trade"]}
        fp = 0x1234567890ABCDEF
        index.add("item-dict", fp, metadata=meta)
        matches = index.find_near_duplicates(fp)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "item-dict")
        self.assertEqual(matches[0][1], 0)
        self.assertEqual(matches[0][2], meta)

    def test_simhash_index_with_scored_passage_metadata(self):
        """Verify inserting ScoredPassage (mutable dataclass) does not raise TypeError."""
        index = SimHashIndex(threshold=3)
        passage = ScoredPassage(
            passage_id="p-001",
            doc_id="d-01",
            url="https://example.com/p",
            title="Battery Density Advances",
            text="Operating dry rooms incurs significant capital expenditure.",
            relevance_score=0.88,
            subquery="battery",
            word_count=8,
            secondary_urls=["https://example.com/sec1"],
        )
        fp = 0x1111222233334444
        index.add(passage.passage_id, fp, metadata=passage)
        matches = index.find_near_duplicates(fp)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "p-001")
        self.assertIs(matches[0][2], passage)
        self.assertIn("https://example.com/sec1", matches[0][2].secondary_urls)

    def test_simhash_index_with_extracted_claim_metadata(self):
        """Verify inserting ExtractedClaim (mutable dataclass) does not raise TypeError."""
        index = SimHashIndex(threshold=3)
        claim = ExtractedClaim(
            claim_id="clm-001",
            text="Solid-state cells achieved 500 Wh/kg energy density in laboratory testing.",
            source_doc_id="d-01",
            source_url="https://example.com/c",
            source_title="Battery Research",
            passage_snippet="Snippet context",
            confidence_score=0.92,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["LLZO", "Lithium"],
            secondary_urls=["https://example.com/c2"],
        )
        fp = 0xAAAABBBBCCCCDDDD
        index.add(claim.claim_id, fp, metadata=claim)
        matches = index.find_near_duplicates(fp)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "clm-001")
        self.assertIs(matches[0][2], claim)
        self.assertIn("LLZO", matches[0][2].entities)

    def test_simhash_index_multi_bucket_match_deduplication(self):
        """Verify that an item matching across multiple 16-bit blocks is returned exactly once."""
        index = SimHashIndex(threshold=3)
        index.add("multi-match", 0x0000000000000000, metadata={"k": "v"})
        # Query with exact match (all 4 blocks match identically)
        matches = index.find_near_duplicates(0x0000000000000000)
        self.assertEqual(len(matches), 1, "Candidate matching all 4 tables must not be duplicated in results")
        self.assertEqual(matches[0][0], "multi-match")
```

#### B. Add Single-Word Abbreviation & Sentence Boundary Test to `TestSentenceSegmentation`
Insert into `TestSentenceSegmentation` (after line 463):

```python
    def test_single_word_abbreviation_vs_terminal_period(self):
        """Confirm 'The answer was no. We continued.' splits into 2 sentences, while 'See p. 42 for details.' remains 1 sentence."""
        split_text = "The answer was no. We continued."
        sents_split = self.extractor.segment_sentences(split_text)
        self.assertEqual(len(sents_split), 2, f"Expected 2 sentences, got {len(sents_split)}: {sents_split}")
        self.assertEqual(sents_split[0], "The answer was no.")
        self.assertEqual(sents_split[1], "We continued.")

        single_text = "See p. 42 for details."
        sents_single = self.extractor.segment_sentences(single_text)
        self.assertEqual(len(sents_single), 1, f"Expected 1 sentence, got {len(sents_single)}: {sents_single}")
        self.assertEqual(sents_single[0], "See p. 42 for details.")
```

---

### 5.2 Additions to `tests/test_adversarial_m2_simhash_claims.py`

Append the following new test class to `tests/test_adversarial_m2_simhash_claims.py`:

```python
class TestSimHashMutableMetadataAndCandidateStress(unittest.TestCase):
    """Stress tests verifying that mutable metadata structures and near-duplicate lookups never raise TypeError."""

    def test_mutable_metadata_types_in_index(self):
        """Heterogeneous mutable objects (dicts, sets, lists, dataclasses) stored in index without TypeError."""
        index = SimHashIndex(threshold=3)
        passage = ScoredPassage("p1", "d1", "https://a.com", "T", "text", 0.8, "q", 10)
        claim = ExtractedClaim("c1", "text", "d1", "https://a.com", "T", "s", 0.9, ClaimType.GENERAL_FACT)
        raw_dict = {"deep": {"nested": [1, 2, 3]}, "tags": {"science", "energy"}}

        index.add("p1", 0x1234, metadata=passage)
        index.add("c1", 0x1234, metadata=claim)
        index.add("d1", 0x1234, metadata=raw_dict)

        matches = index.find_near_duplicates(0x1234)
        self.assertEqual(len(matches), 3)
        retrieved_ids = {m[0] for m in matches}
        self.assertEqual(retrieved_ids, {"p1", "c1", "d1"})

    def test_near_duplicate_passages_stage2_stress(self):
        """Verify that TwoStageDeduplicator handles non-identical near-duplicates through SimHash Stage 2."""
        dedup = TwoStageDeduplicator(hamming_threshold=3)
        # Non-identical passages that bypass Stage 1 exact hash and exercise Stage 2 SimHash
        p1 = ScoredPassage(
            "p-01", "d-01", "https://source1.com/a", "Source 1",
            "Operating dry rooms incurs a capital expenditure premium of $18 million to $25 million per gigawatt-hour.",
            0.80, "q", 18
        )
        p2 = ScoredPassage(
            "p-02", "d-02", "https://source2.com/b", "Source 2",
            "Operating dry rooms incurs capital expenditure premium of $18 million to $25 million per gigawatt-hour.",
            0.85, "q", 17
        )
        results = dedup.deduplicate_passages([p1, p2])
        self.assertEqual(len(results), 1, "Near-duplicates must be merged in Stage 2")
        self.assertEqual(results[0].relevance_score, 0.85, "Should pool maximum relevance score")
        self.assertIn("https://source2.com/b", results[0].secondary_urls)

    def test_abbreviation_sentence_split_boundary_stress(self):
        """Stress sentence segmentation with common trailing word 'no.' vs page citation 'p. 42'."""
        extractor = ClaimExtractor(min_words=1)
        split_res = extractor.segment_sentences("The answer was no. We continued.")
        self.assertEqual(len(split_res), 2)
        self.assertEqual(split_res[0], "The answer was no.")
        self.assertEqual(split_res[1], "We continued.")

        single_res = extractor.segment_sentences("See p. 42 for details.")
        self.assertEqual(len(single_res), 1)
        self.assertEqual(single_res[0], "See p. 42 for details.")
```

---

### 5.3 Implementation Alignment Requirements in Source Code

For the tests to pass without regression, the implementer must ensure:

1. **In `src/research_synthesis/extraction/dedup.py`**:
   Replace `candidates: Set[_IndexEntry] = set()` with:
   ```python
   candidates: Dict[str, _IndexEntry] = {}
   for i, key in enumerate(keys):
       if key in self.tables[i]:
           for entry in self.tables[i][key]:
               candidates[entry.item_id] = entry

   results: List[Tuple[str, int, Any]] = []
   for cand in candidates.values():
       dist = SimHash64.hamming_distance(fingerprint, cand.fingerprint)
       if dist <= t:
           results.append((cand.item_id, dist, cand.metadata))
   ```

2. **In `src/research_synthesis/extraction/claims.py`**:
   - Refine `ABBREVIATIONS` (line 44):
     ```python
     # Replace:
     # r"No\.", r"Fig\.", r"Vol\.", r"pp\.", r"p\.", r"Ph\.D\.", r"M\.D\."
     # With numeric context constraints for No. and p.:
     r"No\.\s*(?=\d)", r"Fig\.", r"Vol\.", r"pp\.\s*(?=\d)", r"p\.\s*(?=\d)", r"Ph\.D\.", r"M\.D\."
     ```
     *(Note: using lookahead `(?=\d)` ensures only the abbreviation is masked, preserving the following digit).*
   - Align length guardrail in `segment_sentences` (line 194):
     ```python
     # Replace:
     # if len(s) >= 10 and len(s.split()) >= self.min_words:
     # With substantive length guard:
     if len(s.strip()) > 0:
         sentences.append(s)
     ```
     *(The substantive word count filtering $[min\_words, max\_words]$ remains strictly enforced by `is_noise_or_non_claim()` during claim extraction).*

---

## 6. Verification Method

To independently verify the aligned test suite post-implementation:

### 6.1 Test Suite Commands
When running in an environment with subprocess execution enabled:
```bash
# Run Tier 1 unit tests (including TestSimHashIndex, TestSentenceSegmentation, TwoStageDeduplicator)
python -m unittest tests/test_tier1_extraction.py -v

# Run Adversarial stress tests (including TestSimHashMutableMetadataAndCandidateStress)
python -m unittest tests/test_adversarial_m2_simhash_claims.py -v

# Run both suites together
python -m unittest discover -s tests -p "test_*.py" -v
```

### 6.2 Invalidation Conditions
The test suite or remediation is invalid if:
1. `TestSimHashIndex.test_pigeonhole_retrieval` or `test_simhash_index_with_mutable_dict_metadata` raises `TypeError: unhashable type`.
2. An exact duplicate (distance 0) matching all 4 tables in `SimHashIndex` is returned multiple times in `results`.
3. `"The answer was no. We continued."` fails to split into 2 sentences.
4. `"See p. 42 for details."` splits into 2 sentences at `"p."`.
5. Non-identical near-duplicate passages bypass attribution merging or fail to merge `secondary_urls`.
