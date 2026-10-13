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
python run_research.py "Perovskite Solar Cells" --output-dir=./reports --format=markdown

# Disable SQLite disk cache
python run_research.py "Little Ice Age Climate Shocks" --no-cache
```

---

## Python API Usage

```python
from research_synthesis.pipeline import ResearchPipeline

# Initialize pipeline in live mode (with SQLite caching enabled)
pipeline = ResearchPipeline(mode="live", use_cache=True)

# Execute end-to-end research synthesis
brief = pipeline.run("Next-Generation Solid-State Battery Commercialization")

print(f"Brief ID: {brief.brief_id}")
print(f"Topic: {brief.topic}")
print(f"Executive Summary:\n{brief.executive_summary}\n")

# Export to Markdown
markdown_text = brief.to_markdown()
with open("solid_state_battery.md", "w", encoding="utf-8") as f:
    f.write(markdown_text)
```

---

## Verification & Test Harness

Run the full unit and adversarial test suite (255 tests):

```bash
python -m unittest discover -s tests -v
```

Execute automated acceptance verification across benchmark domains:

```bash
# Standard mock acceptance verification
python verify.py --mode=mock --queries=all --strict

# Live web acceptance verification
python verify.py --mode=live --queries=all
```
