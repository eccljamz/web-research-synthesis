# Handoff Report: Survey of Requirement R4 & Test Harness Architecture

**Author**: `survey_explorer_3` (Survey Explorer - R4 & Test Harness Architecture)  
**Date**: 2026-10-13T17:10:00Z  
**Parent Conversation ID**: `42364d7e-0273-4faa-be7a-22e0c17eecea`  
**Working Directory**: `C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\survey_explorer_3`  
**Handoff Type**: Hard (Phase 0 Survey Complete)

---

## 1. Observation

### 1.1 Verbatim Requirements from `ORIGINAL_REQUEST.md`
From inspection of `C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\ORIGINAL_REQUEST.md`:
* **Core Objective (lines 5-8)**:
  > "Build an autonomous web research and knowledge synthesis system that investigates user-specified queries, retrieves and parses web sources, filters for relevance, and synthesizes structured, citation-backed research briefs."  
  > "Working directory: ~/teamwork_projects/web_research_synthesis"  
  > "Integrity mode: development"
* **Requirement R4: Automated Verification Harness (lines 21-23)**:
  > "The project must include an automated verification test script that runs the pipeline against sample test queries and asserts that generated reports contain valid structure, non-empty findings, and properly formatted source citations."
* **Acceptance Criteria - Pipeline Functionality (lines 26-28)**:
  > "- [ ] Pipeline executes end-to-end on at least 3 diverse sample test queries without unhandled exceptions."  
  > "- [ ] Generated reports contain a formatted executive summary, key findings, and explicit source references for every major claim."
* **Acceptance Criteria - Automated Verification (lines 30-32)**:
  > "- [ ] An automated test/verification script runs and passes (exit code 0), validating that all generated output briefs conform to the required schema and contain non-empty citation references."

### 1.2 System and Environment State
* The workspace is located at `C:\Users\ecclj\teamwork_projects\web_research_synthesis`.
* Sub-agent division established by `orchestrator_1`:
  * `survey_explorer_1`: Survey R1 & Retrieval Architecture (`QueryDecomposition`, `WebRetrieval`, `ContentParser`, `MetadataExtractor`).
  * `survey_explorer_2`: Survey R2 & R3 Content Filtering, Claim Extraction & Knowledge Synthesis (`RelevanceFilter`, `Deduplication`, `ClaimExtraction`, `SynthesisEngine`).
  * `survey_explorer_3`: Survey R4 & Test Harness Architecture (Verification Runner, Schemas, Deterministic Mock Corpus, Tier 1-4 Test Inventory).
* The execution environment is a standard Python runtime on Windows. To ensure total reliability and zero environment friction, the verification test harness must be able to execute completely offline, deterministically, with standard Python libraries (`unittest`, `json`, `argparse`, `dataclasses`, `re`, `urllib`) while seamlessly integrating with `pytest` and `pydantic`/`jsonschema` when available.

---

## 2. Logic Chain

### 2.1 Deconstruction of R4 and Acceptance Criteria

#### 2.1.1 Selection of 3+ Diverse Sample Test Queries
To satisfy the criteria that the pipeline executes across diverse domains without domain-specific overfitting or brittleness, the harness must feature at least three fundamentally distinct knowledge domains exhibiting different information structures, vocabulary distributions, and citation profiles:

1. **Query 1: Science & Emerging Technology**
   * *Query String*: `"Next-Generation Solid-State Battery Commercialization: Energy Density Roadmaps, Solid Electrolytes, and Manufacturing Scalability"`
   * *Domain Characteristics*: Dense quantitative benchmarks (e.g., $Wh/kg$, ionic conductivity in $mS/cm$, cycle life), chemical terminology (sulfide vs. oxide electrolytes, lithium metal anodes), commercial patent and pilot line roadmaps.
   * *Test Assertion Focus*: Validates accurate preservation of numerical claims, technical terminology extraction, and multi-source corroboration across materials science articles.

2. **Query 2: Macroeconomics & Global Markets**
   * *Query String*: `"Global Supply Chain Re-Shoring and Friend-Shoring Dynamics: Macroeconomic Inflation Impacts and Industrial Policy Interventions"`
   * *Domain Characteristics*: Economic indicators (labor rate differentials, capital expenditure subsidies, tariff impacts), geopolitical classifications (US, EU, East Asia), diverging expert analyses and policy forecasts.
   * *Test Assertion Focus*: Validates synthesis of nuanced viewpoints, categorization by thematic regions/policies, and proper citation attribution to international economic organizations and financial press.

3. **Query 3: History & Paleoclimatology**
   * *Query String*: `"The Little Ice Age Climate Shocks in 17th Century Europe: Agrarian Output Collapses, Famine Cycles, and Social Upheaval"`
   * *Domain Characteristics*: Historical timeline spanning decades/centuries, paleo-climate proxy data (tree rings, ice cores), socio-economic causal links (grain price spikes, population displacement).
   * *Test Assertion Focus*: Validates chronological narrative synthesis, causal claim extraction, and attribution to historical research archives.

4. **Query 4 (Edge/Stress Query): Interdisciplinary Environmental Toxicology & Regulatory Law**
   * *Query String*: `"Microplastic Bioaccumulation in Agricultural Soil Ecosystems: Trophic Transfer Mechanisms and Emerging EU Regulatory Directives"`
   * *Domain Characteristics*: Hybrid scientific-legal topic crossing biology, environmental chemistry, and legislative directives (REACH, microplastics restriction).
   * *Test Assertion Focus*: Validates cross-domain topic decomposition and bidirectional referencing between biological impacts and regulatory codes.

#### 2.1.2 Schema Conformity & Invariant Rules
The verification script must validate that every synthesized research brief satisfies both structural (syntactic) and semantic invariant rules.

**Core Research Brief Schema (JSON / Dataclass Contract)**:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ResearchBrief",
  "type": "object",
  "required": [
    "brief_id",
    "topic",
    "generated_at",
    "sub_queries",
    "executive_summary",
    "thematic_sections",
    "key_takeaways",
    "sources",
    "metadata"
  ],
  "properties": {
    "brief_id": { "type": "string", "pattern": "^brief-[a-f0-9-]+$" },
    "topic": { "type": "string", "minLength": 5 },
    "generated_at": { "type": "string", "format": "date-time" },
    "sub_queries": {
      "type": "array",
      "minItems": 2,
      "items": { "type": "string", "minLength": 3 }
    },
    "executive_summary": { "type": "string", "minLength": 80 },
    "thematic_sections": {
      "type": "array",
      "minItems": 2,
      "items": {
        "type": "object",
        "required": ["section_id", "title", "content", "claims"],
        "properties": {
          "section_id": { "type": "string" },
          "title": { "type": "string", "minLength": 3 },
          "content": { "type": "string", "minLength": 40 },
          "claims": {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "required": ["claim_id", "claim_text", "citation_keys"],
              "properties": {
                "claim_id": { "type": "string", "pattern": "^CLM-\\d+$" },
                "claim_text": { "type": "string", "minLength": 15 },
                "citation_keys": {
                  "type": "array",
                  "minItems": 1,
                  "items": { "type": "string" }
                },
                "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
              }
            }
          }
        }
      }
    },
    "key_takeaways": {
      "type": "array",
      "minItems": 3,
      "items": { "type": "string", "minLength": 10 }
    },
    "sources": {
      "type": "array",
      "minItems": 2,
      "items": {
        "type": "object",
        "required": ["source_id", "url", "title", "snippet"],
        "properties": {
          "source_id": { "type": "string", "pattern": "^SRC-\\d+$" },
          "url": { "type": "string", "format": "uri" },
          "title": { "type": "string", "minLength": 3 },
          "snippet": { "type": "string", "minLength": 20 },
          "author": { "type": "string" },
          "published_date": { "type": "string" }
        }
      }
    },
    "metadata": {
      "type": "object",
      "required": ["retrieval_mode", "total_sources_scanned", "total_claims_extracted", "processing_time_ms"],
      "properties": {
        "retrieval_mode": { "type": "string", "enum": ["mock", "live"] },
        "total_sources_scanned": { "type": "integer", "minimum": 1 },
        "total_claims_extracted": { "type": "integer", "minimum": 1 },
        "processing_time_ms": { "type": "number", "minimum": 0 }
      }
    }
  }
}
```

#### 2.1.3 Semantic Invariant Assertions
Beyond raw JSON type matching, the verification engine asserts four critical semantic invariants:
1. **Referential Integrity**: Every citation key in `claim.citation_keys` and every bracketed reference in Markdown text (e.g., `[SRC-01]`, `[^1]`) MUST resolve to a valid, existing `source_id` within the `sources` array. Orphan citations are flagged as severe verification failures.
2. **Non-Empty / Anti-Degeneracy Assertions**:
   - `executive_summary` cannot contain placeholder words (`"TODO"`, `"N/A"`, `"Lorem ipsum"`, `"Not found"`).
   - Word count thresholds: Executive Summary $\ge 30$ words; each thematic section $\ge 20$ words; total brief $\ge 150$ words.
   - `key_takeaways` must contain at least 3 distinct non-empty strings.
3. **Claim Grounding / Evidence Linkage**:
   - Every major claim in the thematic sections must have at least 1 citation key.
   - The cited source's snippet or document text must contain topical keyword overlap with the claim text (preventing hallucinated provenance).
4. **Markdown Formatting Conformity**:
   - The system produces a complementary `.md` brief containing:
     - Header level 1 matching the research topic
     - Executive summary section (`## Executive Summary`)
     - Thematic subsections (`## Thematic Synthesis: ...`)
     - Key takeaways bulleted list (`## Key Findings & Takeaways`)
     - Structured References table / list (`## Sources & Citations`) with URLs and source IDs.

---

### 2.2 Design of the Verification Test Harness Architecture

```
                          ┌────────────────────────────────┐
                          │     CLI / Test Entry Point     │
                          │        (verify.py / pytest)    │
                          └───────────────┬────────────────┘
                                          │
                                          ▼
                          ┌────────────────────────────────┐
                          │   VerificationTestRunner       │
                          │  - loads queries               │
                          │  - sets execution mode         │
                          │  - coordinates test matrix     │
                          └───────────────┬────────────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
   ┌──────────────────────────────┐                ┌──────────────────────────────┐
   │    Pipeline Under Test       │                │      Mock Data Corpus        │
   │  - Query Decomposition (R1)  │◄───────────────┤ tests/fixtures/mock_corpus/  │
   │  - Mock / Web Retrieval (R1) │ (offline mock) │ - queries/ (3+ domains)      │
   │  - Relevance & Dedup (R2)    │                │ - raw_html/ & raw_json/      │
   │  - Claim Extraction (R2)     │                │ - ground_truth_sources.json  │
   │  - Knowledge Synthesis (R3)  │                └──────────────────────────────┘
   └──────────────┬───────────────┘
                  │ Outputs: ResearchBrief (JSON + Markdown)
                  ▼
   ┌──────────────────────────────────────────────────────────────┐
   │                  VerificationEngine / Assertions             │
   │  ├─ SchemaValidator (JSON Schema / Dataclass checks)         │
   │  ├─ ReferentialIntegrityValidator (Claims -> Sources check)  │
   │  ├─ NonEmptyFindingsValidator (Substance & length check)     │
   │  ├─ MarkdownFormatValidator (Headings, citations, layout)    │
   │  └─ DiagnosticReporter (Summary table, error traces)         │
   └──────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
                     Exit Code 0 (Pass) / 1 (Fail)
                     + Structured Report (reports/verification.json)
```

#### 2.2.1 Verification CLI Runner (`verify.py`) Specification
`verify.py` sits at the root of the repository as the direct entry point for automated verification and CI/CD:
* **Invocation Options**:
  ```bash
  python verify.py                  # Runs all 3 acceptance queries in mock mode
  python verify.py --mode=mock      # Explicit deterministic offline execution
  python verify.py --mode=live      # Optional live web retrieval verification
  python verify.py --queries=all    # Runs solid_state, supply_chain, little_ice_age
  python verify.py --query-name=solid_state
  python verify.py --strict         # Fails even on non-critical quality warnings
  python verify.py --report-dir=./reports
  python verify.py --json           # Outputs machine-readable JSON summary to stdout
  ```
* **Exit Codes**:
  * `0`: All test queries executed successfully, reports produced, 100% schema valid, referential integrity confirmed, non-empty findings verified.
  * `1`: Verification assertion failure (schema error, broken citation, empty finding).
  * `2`: Pipeline runtime exception / fatal unhandled error.
* **Console Output**:
  * Clean, formatted terminal output with checkmarks (`[PASS]`/`[FAIL]`), elapsed time per stage, and detailed diagnostics upon failure.

#### 2.2.2 Mock Data Corpus Architecture
To guarantee 100% deterministic, offline, fast, and repeatable verification that never fails due to network downtime, rate limits, or paywalls, a comprehensive mock corpus must be bundled in `tests/fixtures/mock_corpus/`:
* Directory structure:
  ```
  tests/fixtures/mock_corpus/
  ├── manifest.json
  ├── solid_state_battery/
  │   ├── doc_01_nature_materials.html
  │   ├── doc_02_doe_roadmap.html
  │   ├── doc_03_industry_pilot_lines.html
  │   ├── doc_04_ad_heavy_duplicate.html      # For testing R2 dedup and cleaning
  │   └── doc_05_irrelevant_solar.html        # For testing R2 relevance filter
  ├── supply_chain_reshoring/
  │   ├── doc_01_imf_economic_outlook.html
  │   ├── doc_02_oecd_trade_shifts.html
  │   ├── doc_03_mckinsey_manufacturing.html
  │   └── doc_04_near_duplicate_press.html   # Near duplicate
  └── little_ice_age/
      ├── doc_01_historical_climatology.html
      ├── doc_02_agrarian_yield_records.html
      ├── doc_03_oxford_economic_history.html
      └── doc_04_corrupt_malformed.html      # For testing R1 HTML parser resilience
  ```
* `manifest.json`: Maps sub-queries and topic keywords to corresponding document fixtures, complete with synthetic URLs (`https://mock-research.org/...`), published dates, and author metadata.

#### 2.2.3 Error Tolerance and Fault Handling in Harness
* **Per-query isolation**: If Query 1 experiences an assertion failure, the harness does NOT abort; it logs the failure and proceeds to execute Query 2 and Query 3, providing a full diagnostic report across all test cases.
* **Pipeline Graceful Degradation**:
  * If a single document in the retrieval batch has malformed HTML or empty content, the pipeline logs a warning, falls back cleanly, and continues synthesizing remaining documents.
  * If deduplication reduces 10 retrieved documents to 3 unique documents, the pipeline synthesizes from the 3 unique documents without error.
  * In mock mode, if a sub-query matches 0 documents, the synthesizer utilizes available documents from companion sub-queries, recording the partial retrieval in `metadata.retrieval_warnings`.

---

## 3. Caveats

1. **Python Dependency Strategy (Zero-External-Dependency Fallback)**:
   * While modern Python environments typically have `pytest`, `pydantic`, `jsonschema`, and `beautifulsoup4`, the verification harness and core pipeline must include a zero-dependency fallback (using standard library `json`, `dataclasses`, `re`, `html.parser`, and `unittest`). This ensures that `python verify.py` can execute and pass with exit code 0 even on a minimal, locked-down environment.
2. **Determinism vs. Stochastic Synthesis**:
   * If an LLM backend (e.g. Gemini, OpenAI) is integrated for synthesis, temperature should be set to `0.0` or a deterministic heuristic synthesis engine (extractive clustering + template-based synthesis) must be available as the default baseline for automated test runs. Automated tests must not rely on non-deterministic external LLM APIs that could trigger rate limits, billing issues, or format drift.
3. **Live Web Mode Caveat**:
   * Live web requests are subject to network timeouts, dynamic JavaScript rendering, anti-scraping Cloudflare captchas, and site modifications. Live tests must be marked as optional integration tests, while the automated verification harness that gatekeeps acceptance criteria MUST execute against the deterministic mock corpus by default.
4. **Scope Boundaries**:
   * The verification harness evaluates structural validity, semantic integrity, referential grounding, and format compliance. It cannot grade deep literary prose style or novel academic insights beyond objective linguistic and statistical criteria.

---

## 4. Conclusion & Actionable Blueprint

### 4.1 Feature Inventory Mapping: Requirements to Tests (Tiers 1-4)

The table below establishes a complete, traceable mapping from requirements (R1-R4) to automated test suites across all 4 tiers:

| Tier | Test ID | Target Component | Requirement | Test Description / Scenario | Expected Assertion & Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tier 1: Feature Coverage** | `T1.1` | `Decomposer` | R1 | Decompose broad research topic into sub-queries | Output $\ge 2$ non-empty, distinct sub-queries with keyword variance |
| | `T1.2` | `MockRetriever` | R1 | Retrieve documents for sub-query from mock corpus | Returns `List[RawDocument]` matching manifest keywords, status 200 |
| | `T1.3` | `ContentCleaner` | R1 | Strip HTML tags, navigation, scripts, and CSS | Returns clean article text; zero `<script>`, `<style>`, or nav boilerplate |
| | `T1.4` | `MetadataExtractor` | R1 | Extract document title, author, URL, published date | Returns populated `DocumentMetadata` with fallback values if absent |
| | `T1.5` | `RelevanceFilter` | R2 | Filter retrieved documents by relevance score against topic | High-relevance docs retained; zero-relevance distractor docs removed |
| | `T1.6` | `Deduplicator` | R2 | Exact and near-duplicate document elimination | Duplicate documents removed; unique content count matches expected |
| | `T1.7` | `ClaimExtractor` | R2 | Extract discrete factual statements and figures | Returns `List[Claim]` with non-empty text and source URL provenance |
| | `T1.8` | `Synthesizer` | R3 | Generate Executive Summary from claims | Non-empty summary $\ge 30$ words, synthesizing multiple perspectives |
| | `T1.9` | `Synthesizer` | R3 | Generate Thematic Sections with clustered claims | At least 2 thematic sections, each with $\ge 1$ claim and $\ge 20$ words |
| | `T1.10` | `Synthesizer` | R3 | Generate Key Takeaways | At least 3 discrete bullet points summarizing critical findings |
| | `T1.11` | `CitationMapper` | R3 | Map every claim to source citation keys | Every claim has valid `citation_keys` pointing to valid `sources` list |
| | `T1.12` | `Formatters` | R3 | Render both JSON and Markdown representations | Valid JSON brief and valid Markdown brief generated without errors |
| | `T1.13` | `VerifyCLI` | R4 | Execute `verify.py --help` and arg parsing | Returns exit code 0; shows available arguments and options |
| **Tier 2: Boundary & Corner Cases** | `T2.1` | `Decomposer` | R1, R4 | Single-word or ultra-short topic (e.g. `"Batteries"`) | Graceful expansion into basic sub-queries without crash |
| | `T2.2` | `Decomposer` | R1, R4 | Ultra-long topic (> 300 words) with extraneous fluff | Truncates/summarizes topic safely into focused sub-queries |
| | `T2.3` | `Retriever` | R1, R4 | Zero search results found for a sub-query | Continues pipeline with empty batch; logs warning; no crash |
| | `T2.4` | `ContentCleaner` | R1, R4 | Malformed HTML (unclosed tags, pure binary, blank body) | Parser recovers safely; returns empty or partial text without crash |
| | `T2.5` | `Deduplicator` | R2, R4 | 100% duplicate documents retrieved | Retains exactly 1 document; does not discard entire corpus |
| | `T2.6` | `RelevanceFilter`| R2, R4 | All retrieved documents are irrelevant distractors | Returns graceful "Insufficient relevant sources found" brief; no unhandled exception |
| | `T2.7` | `ClaimExtractor` | R2, R4 | Document with no extractable numbers or factual claims | Extracts high-level thematic assertions or skips cleanly |
| | `T2.8` | `CitationMapper` | R3, R4 | Source with missing title or missing URL | Assigns synthetic fallback URL/title (`"Unknown Source"`); preserves referential integrity |
| | `T2.9` | `VerifyEngine` | R4 | Research brief with broken citation key (deliberate bug) | Verification engine catches violation, flags `ReferentialIntegrityError`, exits 1 |
| | `T2.10` | `VerifyEngine` | R4 | Research brief with empty executive summary | Verification engine catches violation, flags `EmptyFindingsError`, exits 1 |
| **Tier 3: Cross-Feature Combinations**| `T3.1` | `Pipeline` | R1+R2 | Decompose -> Multi-source Retrieve -> Filter & Dedup | Clean, filtered, deduplicated documents preserve source URL lineage |
| | `T3.2` | `Pipeline` | R2+R3 | Filtered Claims -> Thematic Clustering -> Citation Linking | Every claim in synthesized section maps to a deduplicated source |
| | `T3.3` | `Pipeline` | R1+R2+R3 | Mock Mode vs. Live Mode Interface Parity | Same pipeline API and data models work identically for both backends |
| | `T3.4` | `Pipeline` | R3 | JSON AST to Markdown Roundtrip Parity | Every claim, citation, and takeaway in JSON appears in Markdown output |
| | `T3.5` | `Pipeline` | R3+R4 | Dual Serialization (Dict -> JSON string -> Object) | Perfect serialization/deserialization roundtrip without loss |
| | `T3.6` | `Pipeline` | R1..R4 | Partial Retrieval Fault Tolerance | Pipeline with 1 failed sub-query out of 3 still produces valid brief |
| **Tier 4: Real-World E2E Scenarios** | `T4.1` | `Acceptance` | R1..R4 | **Scenario 1**: Solid-State Battery (Science/Tech) | Full pipeline execution; valid schema; $\ge 4$ sources; exit code 0 |
| | `T4.2` | `Acceptance` | R1..R4 | **Scenario 2**: Supply Chain Re-Shoring (Economics) | Full pipeline execution; valid schema; $\ge 4$ sources; exit code 0 |
| | `T4.3` | `Acceptance` | R1..R4 | **Scenario 3**: Little Ice Age (History/Climate) | Full pipeline execution; valid schema; $\ge 3$ sources; exit code 0 |
| | `T4.4` | `Acceptance` | R1..R4 | **Scenario 4**: Microplastics (Interdisciplinary Edge) | Full pipeline execution; valid schema; $\ge 3$ sources; exit code 0 |
| | `T4.5` | `Acceptance` | R4 | **Automated Harness CLI Run**: `python verify.py` | Runs Scenarios 1-3 end-to-end, validates all assertions, returns exit code 0 |

---

### 4.2 Architectural Design of Code Components

To guide the Implementation and Testing agents, the following file layout and interfaces are recommended:

#### Recommended Layout
```
web_research_synthesis/
├── pyproject.toml / requirements.txt
├── verify.py                          # Primary CLI Verification Runner (Acceptance test entry)
├── src/
│   └── research_synthesis/
│       ├── __init__.py
│       ├── models.py                  # Topic, RawDoc, CleanDoc, Claim, ResearchBrief
│       ├── pipeline.py                # ResearchPipeline orchestrator (R1 -> R2 -> R3)
│       ├── retrieval/
│       │   ├── __init__.py
│       │   ├── decomposer.py          # Query decomposition heuristics
│       │   ├── retriever.py           # BaseRetriever, MockRetriever, WebRetriever
│       │   └── parser.py              # HTML cleaning, text extraction, metadata
│       ├── extraction/
│       │   ├── __init__.py
│       │   ├── filter.py              # Relevance filtering
│       │   ├── dedup.py               # Exact and near-duplicate deduplication
│       │   └── claims.py              # Discrete claim and factual statement extraction
│       ├── synthesis/
│       │   ├── __init__.py
│       │   ├── synthesizer.py         # Knowledge synthesis engine
│       │   ├── json_formatter.py      # Serializes ResearchBrief to JSON
│       │   └── md_formatter.py        # Serializes ResearchBrief to Markdown
│       └── verification/
│           ├── __init__.py
│           ├── validator.py           # Schema and semantic validator
│           ├── integrity.py           # Referential integrity and citation checks
│           └── runner.py              # Verification test runner logic
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_tier1_units.py            # Unit tests for components
    ├── test_tier2_boundaries.py       # Boundary and negative tests
    ├── test_tier3_integration.py      # Integration and contract tests
    ├── test_tier4_e2e_acceptance.py   # E2E test suite running 3 diverse queries
    ├── schemas/
    │   └── research_brief.schema.json # JSON Schema definition
    └── fixtures/
        └── mock_corpus/               # Deterministic documents for 3+ queries
```

#### Verification CLI Interface Prototype (`verify.py`)
```python
"""
verify.py - Automated Verification Test Script for Autonomous Web Research System.
Asserts schema conformity, non-empty findings, properly formatted source citations,
and returns exit code 0 on complete pass.
"""
import sys
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Autonomous Web Research Verification Harness")
    parser.add_argument("--mode", choices=["mock", "live"], default="mock",
                        help="Retrieval execution mode (default: mock for deterministic test)")
    parser.add_argument("--query-set", choices=["acceptance", "all", "quick"], default="acceptance",
                        help="Query set to execute (acceptance = 3 diverse queries)")
    parser.add_argument("--output-dir", type=str, default="./test_reports",
                        help="Directory to save generated research briefs and validation results")
    parser.add_argument("--strict", action="store_true",
                        help="Enforce strict length and citation thresholds")
    args = parser.parse_args()

    from research_synthesis.verification.runner import run_acceptance_verification
    success, report = run_acceptance_verification(
        mode=args.mode,
        query_set=args.query_set,
        output_dir=Path(args.output_dir),
        strict=args.strict
    )

    if success:
        print("\n========================================================")
        print(" [PASS] AUTOMATED VERIFICATION PASSED: ALL ASSERTIONS MET")
        print("========================================================")
        sys.exit(0)
    else:
        print("\n========================================================")
        print(" [FAIL] AUTOMATED VERIFICATION FAILED")
        print("========================================================")
        for failure in report.get("failures", []):
            print(f"  - Query: {failure['query']}")
            print(f"    Reason: {failure['error']}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

---

## 5. Verification Method

To independently verify the test harness design, validation logic, and acceptance compliance once implemented:

### 5.1 Verification Commands
1. **Primary Automated Verification Script Execution (Requirement R4 & Acceptance Criteria)**:
   ```bash
   python verify.py --mode mock
   ```
   *Expected outcome*: Pipeline runs against all 3 diverse sample queries (Science/Technology, Economics/Markets, History/Climate), validates schemas, asserts referential integrity and non-empty citations, outputs summary report, and exits with return code `0`.

2. **Full Pytest Test Suite Execution (Covering Tiers 1-4)**:
   ```bash
   pytest tests/ -v
   ```
   *Expected outcome*: All unit, boundary, integration, and E2E acceptance test cases pass with 100% success rate.

3. **Standalone Schema Validation Check**:
   ```bash
   python -m research_synthesis.verification.validator --brief-path test_reports/solid_state_battery.json --schema tests/schemas/research_brief.schema.json
   ```
   *Expected outcome*: JSON file validates cleanly against the JSON Schema with zero errors.

### 5.2 Invalidation Conditions
The verification harness and acceptance criteria are invalidated if any of the following occur:
* `python verify.py` exits with non-zero code ($1$ or $2$).
* Any major claim in a generated brief lacks a source citation, or refers to a citation key that does not exist in the `sources` list (broken referential integrity).
* An executive summary or key findings section is empty, truncated to $< 30$ words, or populated with placeholder strings (`"TODO"`, `"N/A"`).
* The pipeline crashes with an unhandled exception when processing any of the 3 required acceptance queries or when handling malformed HTML in mock fixtures.
* The test harness depends on an active external internet connection to pass acceptance tests.
