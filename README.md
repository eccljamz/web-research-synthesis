# Autonomous Web Research & Knowledge Synthesis System

A high-performance, modular autonomous research and structured brief synthesis engine written in **Pure Python Standard Library (3.10+)** with **Zero External Dependencies**.

Given an arbitrary broad research query, the system autonomously decomposes the inquiry into orthogonal research facets, retrieves relevant web and academic sources with resilient rate limiting and failover, strips boilerplate, chunks passages, scores semantic relevance via BM25, deduplicates content using 64-bit locality-sensitive SimHash fingerprinting, extracts discrete factual claims with provenance, and synthesizes publication-grade research briefs featuring inline referential citations.

---

## Key Features

- **Zero External Dependencies**: Engineered 100% on the Python Standard Library (`urllib`, `sqlite3`, `dataclasses`, `hashlib`, `re`, `html.parser`, etc.).
- **Orthogonal Query Decomposition**: Heuristic facet classification identifying technical, economic, comparative, and regulatory research sub-queries.
- **Resilient Multi-Engine Retrieval**:
  - `LiveHttpRetrievalClient`: Live web fetching with exponential backoff, domain rate limiting, and size safeguards.
  - Multi-engine search: Primary DuckDuckGo HTML, fallback DuckDuckGo Lite, and Wikipedia OpenSearch API.
  - `CompositeRetrievalClient`: Transparent failover to local offline mock corpora.
  - `SQLiteDocumentCache`: Persistent disk-backed caching with TTL eviction.
- **Okapi BM25 Lexical Scoring**: Custom vectorized Okapi BM25 ranking and dynamic threshold filtering.
- **Two-Stage Deduplication**: Exact SHA-256 content/URL canonicalization paired with Charikar's 64-bit SimHash locality-sensitive fingerprinting ($\le 3$ Hamming distance threshold).
- **Extractive Claim Synthesis & Clustering**: Thematic hierarchical agglomeration and consensus resolution across corroborated evidence with strict 1-based citation referential integrity.
- **Interactive CLI & REPL**: Direct command-line synthesis, progress tracking, and multi-format Markdown/JSON exporting.

---

## Installation & Packaging

You can install the package directly in editable mode:

```bash
pip install -e .
```

Or run directly from the workspace without installation:

```bash
python run_research.py "Your Research Query"
```

---

## Quickstart CLI Usage

### 1. Single-Shot Research Synthesis
Run an autonomous research pass on any topic:

```bash
python run_research.py "Next-Generation Solid-State Battery Commercialization"
```

Outputs will be synthesized and exported to `./output/<topic_slug>.md` and `./output/<topic_slug>.json`.

### 2. Interactive REPL Mode
Launch an ongoing research session:

```bash
python run_research.py --interactive
```

### 3. Execution Options
```bash
# Explicit offline mock corpus mode
python run_research.py "Global Supply Chain Reshoring" --mode=mock

# Custom output directory and format
python run_research.py "Perovskite Solar Cells" --output-dir=./reports --format=all

# Disable SQLite disk cache
python run_research.py "Little Ice Age Climate Shocks" --no-cache
```

---

## Local Web Dashboard & REST Server

Launch the zero-dependency interactive Web Dashboard on `http://127.0.0.1:8080`:

```bash
# Launch server with default settings
python run_server.py

# Or via package module
python -m research_synthesis.server --port 8080 --mode mock --open-browser
```

### Server Endpoints:
- `GET /` — Interactive Web Dashboard (query input, real-time stage progress, embedded HTML viewer, Markdown/JSON code tabs).
- `GET /api/health` — Health check & system status.
- `GET /api/briefs` — List all archived briefs.
- `GET /api/briefs/{brief_id}` — Get raw JSON schema of brief.
- `GET /brief/{brief_id}` — Standalone rendered HTML report.
- `GET /brief/{brief_id}/markdown` — Formatted Markdown report.
- `POST /api/synthesize` — Trigger synthesis job (`{"topic": "...", "mode": "mock"|"live", "async": true}`).
- `POST /api/compare` — Synthesize comparative & longitudinal meta-brief across multiple topics or brief IDs.
- `GET /api/jobs/{job_id}` — Poll background synthesis progress and stage status.

---

## Comparative & Longitudinal Synthesis (Track A)

Synthesize a cross-topic comparative meta-brief with technological trade-off matrices, cost parity curves, and longitudinal velocity tracking:

```bash
python -m research_synthesis.cli "Solid-State Battery Commercialization" \
  --compare "Global Supply Chain Re-Shoring" --mode=mock
```

Or via Python API:

```python
from research_synthesis import ComparativeSynthesisEngine, ResearchPipeline

pipeline = ResearchPipeline(mode="mock")
comparison = pipeline.compare([
    "Next-Generation Solid-State Battery Commercialization",
    "Global Supply Chain Re-Shoring and Friend-Shoring Dynamics",
])
print(comparison.meta_brief.to_markdown())
```

---

## Zero-Dependency PDF Stream Ingestion (Track B)

Extract full-text academic preprints and `/FlateDecode` compressed PDF streams using pure Python standard library (`zlib`):

```python
from research_synthesis import ZeroDepPDFExtractor

extracted = ZeroDepPDFExtractor.extract_from_bytes(pdf_bytes)
print(extracted.title, extracted.page_count, len(extracted.paragraphs))
```

---

## Containerized Deployment (Track C)

Build and run the minimal `< 60 MB` `python:3.11-alpine` container image:

```bash
docker build -t research-synthesis:0.1.0 .
docker run --rm -p 8080:8080 research-synthesis:0.1.0
```

---

## Python API Usage

```python
from research_synthesis.pipeline import ResearchPipeline

# Initialize pipeline in live mode (with SQLite caching enabled)
pipeline = ResearchPipeline(mode="live", use_cache=True)

# Execute end-to-end research synthesis with progress tracking
def on_progress(stage, total, message):
    print(f"[{stage}/{total}] {message}")

brief = pipeline.run("Next-Generation Solid-State Battery Commercialization", progress_callback=on_progress)

print(f"Brief ID: {brief.brief_id}")
print(f"Topic: {brief.topic}")
print(f"Executive Summary:\n{brief.executive_summary}\n")

# Multi-format exports:
markdown_text = brief.to_markdown()
html_report = brief.to_html()
json_dict = brief.to_dict()
```

---

## Verification & Test Harness

Run the full unit and adversarial test suite (280+ tests, zero deprecation warnings):

```bash
python -W error::DeprecationWarning -m unittest discover -s tests -v
```

Execute automated acceptance verification across benchmark domains:

```bash
# Standard mock acceptance verification (strict mode)
python verify.py --mode=mock --queries=all --strict

# Live web acceptance verification
python verify.py --mode=live --queries=all
```
