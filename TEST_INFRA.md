# Test Infrastructure & Verification Harness Specification

## 1. Overview
The Test Infrastructure and Verification Harness provides automated, deterministic, and offline acceptance verification for the Autonomous Web Research and Knowledge Synthesis System. It ensures that synthesized research briefs satisfy all architectural requirements (R1–R4), conform to formal structural JSON schemas, and strictly adhere to semantic invariants including referential citation integrity, substantive word counts, and anti-degeneracy rules.

---

## 2. Test Suite Hierarchy (Tiers 1–4)

| Tier | Category | Scope & Objective | Primary Test Files |
|---|---|---|---|
| **Tier 1** | Unit & Feature Tests | Component-level testing for individual pipeline modules: decomposer, retriever, parser, chunker, BM25 filter, deduplicator, claim extractor, and synthesizer. | `tests/test_tier1_retrieval.py`<br>`tests/test_tier1_extraction.py`<br>`tests/test_tier1_synthesis.py`<br>`tests/test_verification.py` |
| **Tier 2** | Boundary & Corner Cases | Extreme inputs, ultra-short/long queries, malformed HTML bodies, duplicate documents, distractor filtering, empty results handling. | `tests/test_tier2_boundaries.py` |
| **Tier 3** | Integration & Contract Tests | Cross-module contract validation: RawDoc to CleanArticle, ExtractedClaim to ThematicSection, dual JSON/Markdown formatting parity. | `tests/test_tier3_cross_feature.py` |
| **Tier 4** | E2E Acceptance Verification | End-to-end execution of the complete pipeline across 3 diverse domain queries (plus edge query), running through `verify.py` and asserting 100% schema & invariant compliance. | `tests/test_tier4_e2e_acceptance.py`<br>`verify.py` |

---

## 3. Deterministic Mock Corpus (`tests/fixtures/mock_corpus/`)

To guarantee 100% offline determinism and zero dependency on external network availability or live rate limits during CI/CD and verification, a comprehensive mock corpus is packaged in `tests/fixtures/mock_corpus/`.

### 3.1 Corpus Directory Layout
```
tests/fixtures/mock_corpus/
├── manifest.json
├── solid_state_battery/
│   ├── doc_01_nature_materials.html         # High-relevance: Ionic conductivity, sulfides vs oxides
│   ├── doc_02_doe_roadmap.html              # High-relevance: DOE Battery500 targets, 500 Wh/kg
│   ├── doc_03_industry_pilot_lines.html     # High-relevance: Roll-to-roll manufacturing, dry rooms
│   ├── doc_04_ad_heavy_duplicate.html       # Near-duplicate: Tests boilerplate stripping & dedup
│   └── doc_05_irrelevant_solar.html         # Distractor: Tests BM25 relevance filter rejection
├── supply_chain_reshoring/
│   ├── doc_01_imf_economic_outlook.html     # High-relevance: Geoeconomic fragmentation, GDP loss
│   ├── doc_02_oecd_trade_shifts.html        # High-relevance: Industrial subsidies, IRA, Chips Act
│   ├── doc_03_mckinsey_manufacturing.html   # High-relevance: Nearshoring Mexico, freight lead times
│   ├── doc_04_near_duplicate_press.html     # Near-duplicate: Press wire of IMF report
│   └── doc_05_irrelevant_crypto.html        # Distractor: Cryptocurrency and DeFi distractor
├── little_ice_age/
│   ├── doc_01_historical_climatology.html   # High-relevance: Maunder Minimum & volcanic aerosol forcing
│   ├── doc_02_agrarian_yield_records.html   # High-relevance: Grain failures, 1690s famine mortality
│   ├── doc_03_oxford_economic_history.html  # High-relevance: General Crisis of the 17th Century
│   └── doc_04_corrupt_malformed.html        # Malformed HTML: Unclosed tags, unquoted attributes
└── microplastics/ (Edge Domain)
    ├── doc_01_soil_accumulation.html        # High-relevance: Sludge and mulch film accumulation
    ├── doc_02_trophic_transfer.html         # High-relevance: Nanoplastic root uptake, food web
    ├── doc_03_eu_regulations.html           # High-relevance: Commission Regulation (EU) 2023/2055
    └── doc_04_edge_minimal.html             # Boundary fixture: 1-paragraph brief note
```

### 3.2 Manifest Schema (`manifest.json`)
The manifest coordinates queries, sub-queries, and document registries:
- `queries`: Array of domain records containing `query_id`, `domain`, `canonical_topic`, `keywords`, `sub_queries`, and mapped `document_ids`.
- `documents`: Dictionary mapping document keys to file paths, synthetic canonical URLs, author metadata, publication dates, and expected relevance tags.

---

## 4. Formal Schema Contract (`tests/schemas/research_brief.schema.json`)

The output of knowledge synthesis is validated against `research_brief.schema.json` (JSON Schema Draft-07).

### Required Top-Level Properties:
1. `brief_id`: String matching regex `^brief-[a-zA-Z0-9_-]+$`.
2. `topic`: Non-empty topic string ($\ge 5$ characters).
3. `generated_at`: ISO 8601 UTC timestamp string.
4. `sub_queries`: Array with $\ge 2$ decomposed sub-queries.
5. `executive_summary`: Synthesized prose ($\ge 80$ characters, $\ge 30$ words).
6. `thematic_sections`: Array with $\ge 2$ structured sections, each having `section_id`, `title`, and substantive `narrative` (or `content`).
7. `key_takeaways`: Array with $\ge 3$ distinct findings.
8. `sources`: Array with $\ge 2$ bibliographic citations with `source_id`, `url`, `title`, and `snippet`.
9. `metadata`: Audit metadata containing `retrieval_mode`, `total_sources_scanned`, `total_claims_extracted`, and `processing_time_ms`.

---

## 5. Verification Engine Architecture

Located at `src/research_synthesis/verification/`:
- **`validator.py`**:
  - `SchemaValidator`: Validates structural dictionary format, utilizing `jsonschema` when available with an automatic pure-Python fallback.
  - `SemanticValidator`: Asserts critical invariant rules:
    - **Referential Integrity**: Scans executive summary, thematic sections, takeaways, and claim objects for inline citation markers (e.g., `[1]`, `[2]`, `[1-3]`, `[SRC-01]`, `[^1]`). Every referenced marker must resolve to a valid entry in the `sources` table. Orphan citations trigger an immediate verification error.
    - **Anti-Degeneracy & Substance**: Executive summary $\ge 30$ words, each thematic section $\ge 20$ words, total brief $\ge 120$ words.
    - **Placeholder Detection**: Flags prohibited placeholder tokens (`TODO`, `FIXME`, `TBD`, `N/A`, `Lorem ipsum`, `Not found`, `placeholder`).
    - **Source Sanity**: Asserts valid URLs and non-empty snippets ($\ge 5$ words).
- **`runner.py`**:
  - Orchestrates execution of acceptance queries, executes `ResearchPipeline` (or reads pre-synthesized briefs), serializes briefs to JSON and Markdown, runs validators, and compiles `verification_report.json`.

---

## 6. Verification CLI Runner (`verify.py`)

Root-level command-line interface for acceptance verification and CI/CD testing.

### Usage:
```bash
# Run standard acceptance verification across 3 diverse domains (mock mode)
python verify.py

# Run explicitly with mock mode
python verify.py --mode=mock

# Run all queries including the edge microplastics domain
python verify.py --queries=all

# Enforce strict invariant checks (all sources cited, elevated thresholds)
python verify.py --strict

# Output machine-readable JSON to stdout
python verify.py --json

# Specify custom output report directory
python verify.py --output-dir=./custom_reports
```

### Exit Codes:
- `0`: **SUCCESS** — All queries executed, briefs generated, 100% schema valid, referential integrity confirmed, non-empty findings verified.
- `1`: **VERIFICATION FAILURE** — One or more schema or semantic invariant assertions failed (e.g., broken citation, degenerate text, missing field).
- `2`: **FATAL ERROR** — Unhandled pipeline exception or missing execution environment.

---

## 7. Running Unit & Verification Tests

```bash
# Run verification unit tests
python -m unittest tests/test_verification.py -v

# Run full test suite with pytest (if installed)
pytest tests/ -v
```
