# Project: Autonomous Web Research and Knowledge Synthesis System

## Architecture
The system is structured as an end-to-end, multi-stage pipeline that ingests complex research topics, decomposes them into targeted sub-queries, retrieves web documents (supporting both deterministic offline mock corpora and live HTTP fetching), cleans HTML content, filters for relevance, deduplicates text, extracts discrete factual claims with provenance, and synthesizes structured, citation-backed research briefs adhering to strict schema contracts.

### Data Flow
```
User Query / Research Topic
         │
         ▼
[1. Query Decomposition Engine] ───► List[SubQuery] (5 orthogonal facets)
         │
         ▼
[2. Retrieval Client] ──────────────► List[RawWebDocument] (Mock / Live failover)
         │
         ▼
[3. Document Parser & Cleaner] ─────► List[CleanArticle] (Boilerplate stripped, metadata extracted)
         │
         ▼
[4. Relevance Filter] ──────────────► List[ScoredPassage] (Okapi BM25 scoring, passage chunking)
         │
         ▼
[5. Deduplication Engine] ──────────► List[ScoredPassage] (SimHash 64-bit + exact hash)
         │
         ▼
[6. Claim Extraction Engine] ───────► List[ExtractedClaim] (Quantitative & relational fact extraction)
         │
         ▼
[7. Thematic Clustering Engine] ────► Clusters of ExtractedClaim
         │
         ▼
[8. Synthesis Engine] ──────────────► ResearchBrief (Exec Summary, Sections, Takeaways, Citations)
         │
         ├──────────────────────────► JSON Representation (`.to_json()`)
         └──────────────────────────► Markdown Representation (`.to_markdown()`)
```

---

## Feature Inventory
Every feature identified during Phase 0 Survey is cataloged below with its assigned milestone.

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Multi-Facet Query Decomposition | Decompose broad topics into 3-5 orthogonal sub-queries (technical, economic, challenges, comparative, temporal) using linguistic rules and comparative regex. | M1 | Survey R1 |
| F2 | Dual-Mode Retrieval Client | Unified `BaseRetrievalClient` protocol implemented by `MockWebRetrievalClient` (local corpus matching) and `LiveHttpRetrievalClient` (with retry & rate limiting). | M1 | Survey R1 |
| F3 | Composite Retrieval Failover | `CompositeRetrievalClient` attempting live HTTP fetch and falling back seamlessly to mock fixtures upon network error or offline mode. | M1 | Survey R1 |
| F4 | Robust Zero-Dependency HTML Parser | `RobustHTMLParser` stripping boilerplate tags (`script`, `style`, `nav`, `footer`, `aside`, ads) and extracting clean paragraphs. | M1 | Survey R1 |
| F5 | Document Metadata Extractor | Extracts OpenGraph title, canonical URL, author, published date, and domain with robust fallback logic. | M1 | Survey R1 |
| F6 | Passage-Level Chunking | Segment cleaned document texts into overlapping passages (150-250 words) to enable granular relevance scoring. | M2 | Survey R2 |
| F7 | Pure-Python Okapi BM25 Relevance Filter | Lexical relevance ranking against query tokens with term frequency saturation and length normalization; threshold filtering. | M2 | Survey R2 |
| F8 | Two-Stage Deduplication Engine | Exact URL/content hashing combined with 64-bit SimHash locality-sensitive fingerprinting (Hamming distance <= 3) to eliminate redundancy while preserving co-citations. | M2 | Survey R2 |
| F9 | Discrete Factual Claim Extractor | Rule-based factuality extractor isolating atomic propositions containing quantitative metrics, dates, percentages, and relational assertions with provenance attribution. | M2 | Survey R2 |
| F10 | Thematic Claim Clustering | Group extracted claims by sub-query intent and semantic keyword overlap into 2-5 thematic section clusters. | M3 | Survey R3 |
| F11 | Knowledge Synthesis Engine | Deterministic extractive synthesis with Maximal Marginal Relevance (MMR) and logical narrative generation with bidirectional citation markers `[N]`. | M3 | Survey R3 |
| F12 | Research Brief Schema & Models | Strongly typed `ResearchBrief` dataclass container comprising Executive Summary, Thematic Sections, Key Takeaways, Source Citations, and Metadata. | M3 | Survey R3 |
| F13 | Dual Format Serializers | Serializers rendering structured JSON schema conformant outputs (`.to_json()`) and clean human-readable Markdown briefs (`.to_markdown()`). | M3 | Survey R3 |
| F14 | Comprehensive Mock Corpus Fixtures | Rich offline HTML fixtures across 3 diverse domains (Solid-State Batteries, Supply Chain Re-Shoring, Little Ice Age Climate) plus edge queries. | M-TEST | Survey R4 |
| F15 | Verification Engine & Invariant Validator | Validates JSON schema conformance, referential integrity (every inline `[N]` citation resolves to a valid source), and non-empty substantive findings. | M-TEST | Survey R4 |
| F16 | Automated Verification CLI Runner (`verify.py`) | Standalone CLI script executing the pipeline across 3 diverse sample queries, verifying all invariant assertions, and exiting with return code 0. | M-TEST | Survey R4 |
| F17 | Multi-Tier Test Suite (Tiers 1-4) | Comprehensive unit, boundary, integration, and E2E acceptance tests covering >30 test items across all modules. | M-TEST | Survey R4 |
| F18 | End-to-End Pipeline Integration & Hardening | Full integration running end-to-end pipeline across all 3 sample queries passing 100% of E2E verification tests. | M4 | Acceptance Criteria |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Query Decomposition & Web Retrieval | Features F1, F2, F3, F4, F5: `src/research_synthesis/models.py` (retrieval models), `src/research_synthesis/retrieval/` (`decomposer.py`, `retriever.py`, `parser.py`). Unit tests in `tests/test_tier1_retrieval.py`. | None | DONE |
| M2 | Content Filtering & Claim Extraction | Features F6, F7, F8, F9: `src/research_synthesis/extraction/` (`chunker.py`, `bm25.py`, `dedup.py`, `claims.py`). Unit tests in `tests/test_tier1_extraction.py`. | M1 | DONE |
| M3 | Structured Knowledge Synthesis | Features F10, F11, F12, F13: `src/research_synthesis/synthesis/` (`cluster.py`, `synthesizer.py`, `formatters.py`), `src/research_synthesis/pipeline.py`. Unit tests in `tests/test_tier1_synthesis.py`. | M2 | DONE |
| M-TEST | Test Infrastructure & E2E Harness | Features F14, F15, F16, F17: `tests/fixtures/mock_corpus/`, `tests/schemas/research_brief.schema.json`, `src/research_synthesis/verification/` (`validator.py`, `runner.py`), `verify.py`, Tiers 1-4 test suite. | Interface Contracts | DONE |
| M4 | Final Milestone: E2E Verification & Hardening | Feature F18: Integration verification, running `verify.py` across 3 diverse queries, Tier 1-4 test pass (100%), adversarial testing (Tier 5), Forensic Auditor validation. | M1, M2, M3, M-TEST | DONE |

---

## Interface Contracts

### 1. Retrieval Module ↔ Extraction Module (`src/research_synthesis/models.py`)
```python
@dataclass
class DocumentMetadata:
    url: str
    canonical_url: str
    domain: str
    title: str
    author: Optional[str] = None
    published_date: Optional[str] = None
    content_type: str = "text/html"
    status_code: int = 200
    word_count: int = 0

@dataclass
class CleanArticle:
    doc_id: str                              # SHA-256 hash prefix of canonical URL
    url: str
    metadata: DocumentMetadata
    cleaned_text: str                        # Full cleaned text
    paragraphs: List[str]                    # Paragraph blocks
    headings: List[str]                      # Section headings
    subquery_id: Optional[str] = None
    subquery_facet: Optional[str] = None

@dataclass
class RetrievalBatch:
    topic: str
    sub_queries: List[SubQuery]
    documents: List[CleanArticle]
    failed_urls: List[Dict[str, str]] = field(default_factory=list)
```

### 2. Extraction Module ↔ Synthesis Module
```python
class ClaimType(str, Enum):
    QUANTITATIVE = "QUANTITATIVE"
    TEMPORAL_EVENT = "TEMPORAL_EVENT"
    RELATIONAL = "RELATIONAL"
    GENERAL_FACT = "GENERAL_FACT"

@dataclass
class ExtractedClaim:
    claim_id: str                            # Unique claim hash
    text: str                                # Atomic proposition statement
    source_doc_id: str                       # Links to CleanArticle.doc_id
    source_url: str                          # Canonical source URL
    source_title: str                        # Document title
    passage_snippet: str                     # Surrounding context
    confidence_score: float                  # [0.0, 1.0]
    claim_type: ClaimType
    entities: List[str] = field(default_factory=list)
    secondary_urls: List[str] = field(default_factory=list)
```

### 3. Synthesis Module ↔ Verification Harness & Output
```python
@dataclass
class SourceCitation:
    citation_index: int                      # 1, 2, ... matching [1], [2] in prose
    source_id: str                           # e.g., "SRC-01"
    title: str
    url: str
    author: Optional[str] = None
    publish_date: Optional[str] = None
    snippet: str = ""
    attributed_claim_ids: List[str] = field(default_factory=list)

@dataclass
class ThematicSection:
    section_id: str
    title: str
    narrative: str                           # Prose embedding inline [N] citations
    citation_indices: List[int]
    claim_ids: List[str]
    key_findings: List[str] = field(default_factory=list)

@dataclass
class ResearchBrief:
    brief_id: str
    topic: str
    executive_summary: str                   # Prose embedding inline [N] citations
    key_takeaways: List[KeyTakeaway]         # Bullet points with citation indices
    thematic_sections: List[ThematicSection] # Thematic chapters
    sources: List[SourceCitation]            # Bibliography table
    metadata: Dict[str, Any]                 # Execution audit data

    def to_dict(self) -> Dict[str, Any]: ...
    def to_json(self, indent: int = 2) -> str: ...
    def to_markdown(self) -> str: ...
```

---

## Code Layout
```
C:\Users\ecclj\teamwork_projects\web_research_synthesis\
├── pyproject.toml
├── verify.py                                # Acceptance CLI script (exits 0 on pass)
├── src/
│   └── research_synthesis/
│       ├── __init__.py
│       ├── models.py                        # Shared dataclasses & schemas
│       ├── pipeline.py                      # Master ResearchPipeline (R1 -> R2 -> R3)
│       ├── retrieval/
│       │   ├── __init__.py
│       │   ├── decomposer.py                # HeuristicQueryDecomposer
│       │   ├── retriever.py                 # MockRetriever, LiveRetriever, CompositeRetriever
│       │   └── parser.py                    # RobustHTMLParser, DocumentParser
│       ├── extraction/
│       │   ├── __init__.py
│       │   ├── chunker.py                   # PassageChunker
│       │   ├── bm25.py                      # PureBM25 relevance scorer
│       │   ├── dedup.py                     # SimHash64 & URL/text hash deduplicator
│       │   └── claims.py                    # FactualClaimExtractor
│       ├── synthesis/
│       │   ├── __init__.py
│       │   ├── cluster.py                   # ThematicClusterer
│       │   ├── synthesizer.py               # KnowledgeSynthesizer
│       │   └── formatters.py                # MarkdownFormatter, JsonFormatter
│       └── verification/
│           ├── __init__.py
│           ├── validator.py                 # SchemaValidator & SemanticValidator
│           └── runner.py                    # Acceptance verification runner logic
└── tests/
    ├── __init__.py
    ├── schemas/
    │   └── research_brief.schema.json       # JSON Schema definition
    ├── fixtures/
    │   └── mock_corpus/                     # Deterministic offline test corpus
    │       ├── manifest.json
    │       ├── solid_state_battery/
    │       ├── supply_chain_reshoring/
    │       └── little_ice_age/
    ├── test_tier1_retrieval.py
    ├── test_tier1_extraction.py
    ├── test_tier1_synthesis.py
    ├── test_tier2_boundaries.py
    ├── test_tier3_cross_feature.py
    └── test_tier4_e2e_acceptance.py
```
