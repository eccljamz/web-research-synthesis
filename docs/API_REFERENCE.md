# REST API & Python SDK Reference Manual

The Autonomous Web Research and Knowledge Synthesis System provides both a **RESTful HTTP Service** and a **Python SDK**.

---

## 1. Local REST API Endpoints

The web server defaults to `http://127.0.0.1:8080`. All JSON endpoints return standard HTTP status codes and CORS headers (`Access-Control-Allow-Origin: *`).

### Summary of Endpoints

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Interactive Single-Page Web Dashboard |
| `GET` | `/api/health` | Service health status, version, and loaded brief count |
| `GET` | `/api/briefs` | List all synthesized research briefs in the archive |
| `GET` | `/api/briefs/{brief_id}` | Retrieve complete brief JSON matching schema |
| `GET` | `/api/jobs/{job_id}` | Poll background synthesis job progress and status |
| `GET` | `/api/jobs/{job_id}/stream` | Stream real-time stage progress via Server-Sent Events |
| `POST` | `/api/synthesize` | Submit a new research topic (synchronous or asynchronous) |
| `GET` | `/brief/{brief_id}` | View standalone styled HTML brief report |
| `GET` | `/brief/{brief_id}/markdown` | Retrieve clean GitHub-flavored Markdown text |
| `GET` | `/brief/{brief_id}/obsidian` | Retrieve single Obsidian Markdown note with callouts |
| `GET` | `/brief/{brief_id}/obsidian-vault` | Retrieve JSON manifest of atomic PKM vault files |
| `GET` | `/brief/{brief_id}/obsidian-vault.zip` | Download complete PKM vault packaged as a `.zip` archive |

---

### Endpoint Details

#### `GET /api/health`
Returns system operational metadata.

**Response `200 OK`**:
```json
{
  "status": "ok",
  "version": "0.1.0",
  "mode": "live",
  "total_briefs": 4
}
```

---

#### `POST /api/synthesize`
Trigger synthesis of a research brief on a given topic.

**Request Headers**:
- `Content-Type: application/json`

**Request Body**:
```json
{
  "topic": "Quantum Computing Error Correction",
  "mode": "live",
  "async": true
}
```
*Parameters*:
- `topic` (*string*, required): The research query to investigate.
- `mode` (*string*, optional): `"live"` (default) with automatic search engine cascade or `"mock"` for offline testing.
- `async` (*boolean*, optional): If `true`, returns immediately with `202 Accepted` and a `job_id`. If `false`, blocks until synthesis completes and returns `200 OK`.

**Response `202 Accepted` (Async)**:
```json
{
  "job_id": "job-199de42b821",
  "status": "queued",
  "topic": "Quantum Computing Error Correction",
  "mode": "live",
  "poll_url": "/api/jobs/job-199de42b821",
  "stream_url": "/api/jobs/job-199de42b821/stream"
}
```

---

#### `GET /api/jobs/{job_id}`
Poll the status of an asynchronous synthesis job.

**Response `200 OK` (Running)**:
```json
{
  "job_id": "job-199de42b821",
  "status": "running",
  "topic": "Quantum Computing Error Correction",
  "mode": "live",
  "progress": {
    "stage": 3,
    "total_stages": 6,
    "percentage": 50,
    "message": "Parsing HTML boilerplate & chunking passages..."
  },
  "created_at": "2026-10-13T23:45:10Z"
}
```

**Response `200 OK` (Completed)**:
```json
{
  "job_id": "job-199de42b821",
  "status": "completed",
  "brief_id": "brief-dfb6fb20",
  "progress": {
    "stage": 6,
    "total_stages": 6,
    "percentage": 100,
    "message": "Thematic clustering & structured brief synthesis..."
  },
  "completed_at": "2026-10-13T23:45:31Z"
}
```

---

#### `GET /api/briefs`
Returns metadata list of all synthesized research briefs.

**Response `200 OK`**:
```json
[
  {
    "brief_id": "brief-ce74671e",
    "topic": "Solid-State Battery Commercialization",
    "generated_at": "2026-10-13T23:55:54Z",
    "sections_count": 2,
    "sources_count": 2,
    "file_stem": "solid_state_battery_commercialization"
  }
]
```

---

#### `GET /brief/{brief_id}/obsidian-vault.zip`
Streams a standard binary ZIP file containing the full multi-note Obsidian vault (`Index.md`, `Sections/*.md`, `Sources/*.md`, `Knowledge_Graph.canvas`).

**Response Headers**:
- `Content-Type: application/zip`
- `Content-Disposition: attachment; filename="{brief_id}_obsidian_vault.zip"`

---

## 2. Python SDK Reference

The library can be imported and executed programmatically within any Python 3.10+ application without external dependencies.

### Basic Pipeline Execution

```python
from research_synthesis import ResearchPipeline

# 1. Initialize pipeline (mode="live" or mode="mock")
pipeline = ResearchPipeline(mode="live", use_cache=True)

# 2. Run synthesis on a topic
brief = pipeline.run("Next-Generation Solid-State Battery Commercialization")

# 3. Access structured properties
print(f"Topic: {brief.topic} (ID: {brief.brief_id})")
print(f"Executive Summary: {brief.executive_summary[:200]}...")
print(f"Total Sections: {len(brief.thematic_sections)}")
print(f"Total Sources: {len(brief.sources)}")

# 4. Export to multiple formats
markdown_content = brief.to_markdown()
json_content = brief.to_json(indent=2)
html_content = brief.to_html()
obsidian_note = brief.to_obsidian()

# 5. Export multi-note Obsidian vault
brief.export_obsidian_vault("./my_obsidian_vault")
```

---

### Retrieval Connectors & Persistent Caching

```python
from research_synthesis.retrieval import (
    ArxivRetrievalClient,
    PubMedRetrievalClient,
    WikipediaRetrievalClient,
    SQLiteDocumentCache,
    CompositeRetrievalClient,
)

# Persistent SQLite cache with 12h TTL
cache = SQLiteDocumentCache(db_path="./research_cache.db", default_ttl=43200)

# Instantiate specialized search clients
arxiv = ArxivRetrievalClient(cache=cache)
pubmed = PubMedRetrievalClient(cache=cache)

# Search papers
arxiv_urls = arxiv.search("quantum error correction", limit=3)
doc = arxiv.fetch_url(arxiv_urls[0])
print(f"Fetched arXiv article: {doc.url} (status: {doc.status_code})")
```
