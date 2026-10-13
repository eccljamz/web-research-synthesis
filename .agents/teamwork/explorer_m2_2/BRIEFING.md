# BRIEFING — 2026-10-13T18:05:00Z

## Mission
Investigate and design technical specifications for Milestone 2 Feature F8 (Two-Stage Deduplication Engine).

## 🔒 My Identity
- Archetype: teamwork_preview_explorer
- Roles: Explorer M2-2 (Two-Stage Deduplication Engine)
- Working directory: C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\explorer_m2_2
- Original parent: 42364d7e-0273-4faa-be7a-22e0c17eecea
- Milestone: Milestone 2 Feature F8

## 🔒 Key Constraints
- Read-only investigation — do NOT implement directly in src/
- Design exact technical specs for Feature F8 in `src/research_synthesis/extraction/dedup.py`
- Two-stage deduplication: Stage 1 Exact (SHA-256 text normalization + canonical URL) & Stage 2 Near-Duplicate (64-bit SimHash, Charikar's LSH, Hamming distance <= 3)
- Attribution preservation: secondary URLs and titles appended to preserve co-citation
- Inverted SimHash index / bucket clustering for efficient comparisons
- Deliver handoff report with 5 components in `handoff.md`

## Current Parent
- Conversation ID: 42364d7e-0273-4faa-be7a-22e0c17eecea
- Updated: not yet

## Investigation State
- **Explored paths**:
  - `ORIGINAL_REQUEST.md`, `PROJECT.md`, `survey_explorer_2/handoff.md`, `src/research_synthesis/models.py`
  - `tests/fixtures/mock_corpus/manifest.json` and duplicate document pairs (`ssb_03` vs `ssb_04`, `scr_01` vs `scr_04`)
  - `src/research_synthesis/verification/validator.py`, `tests/test_verification.py`, `tests/schemas/research_brief.schema.json`
  - Peer explorer assignments (`explorer_m2_1` for chunker/BM25, `explorer_m2_3` for claims/tests)
- **Key findings**:
  - Exact text deduplication requires unicode NFKC normalization, lowercasing, punctuation stripping (`re.sub(r'[^\w\s]|_', '', text)`), whitespace collapsing, and SHA-256 hashing.
  - Canonical URL matching strips tracking parameters (`utm_*`, `ref`, `fbclid`, etc.), default ports, fragments, and normalizes paths.
  - SimHash 64-bit fingerprinting with Charikar's vector accumulation over word 3-grams (falling back to unigrams for short texts) reliably identifies editorial/press-release duplicates with Hamming distance <= 3.
  - Inverted SimHash index leverages the Pigeonhole Principle: 64 bits partitioned into 4 blocks of 16 bits. Any two fingerprints with Hamming distance <= 3 must match exactly in at least 1 of the 4 blocks, guaranteeing O(1) average lookup and zero false negatives.
  - Attribution preservation appends secondary canonical URLs to `secondary_urls` without duplicates or self-loops, carries forward existing secondary URLs, preserves title attribution, and updates max relevance/confidence scores.
- **Unexplored areas**: None. Architectural and algorithmic specifications are fully derived.

## Key Decisions Made
- Structure `dedup.py` with modular components:
  1. `normalize_text` and `canonicalize_url` utility functions.
  2. `SimHash64` class for 64-bit fingerprinting, shingling, token hashing, vector accumulation, and Hamming distance.
  3. `SimHashIndex` class implementing the 4-bucket inverted index (Manku et al., 2007) for $O(1)$ near-duplicate candidate retrieval.
  4. `TwoStageDeduplicator` class combining Stage 1 exact hash with Stage 2 SimHash, providing `deduplicate_passages`, `deduplicate_claims`, and generic `deduplicate`, with transitive attribution preservation.
  5. `DeduplicationStats` dataclass tracking exact duplicates, near duplicates, and retained items.

## Artifact Index
- DISPATCH.md — Dispatch instructions from parent
- BRIEFING.md — Working memory and status
- progress.md — Liveness heartbeat and progress tracking
- handoff.md — Final specifications report (being generated)
