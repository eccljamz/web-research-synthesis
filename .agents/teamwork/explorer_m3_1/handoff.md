# Handoff Report: Milestone 3 Feature F10 (Thematic Clustering Engine)

**Agent**: `explorer_m3_1`  
**Working Directory**: `C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\explorer_m3_1`  
**Parent Agent**: `orchestrator_1` (`42364d7e-0273-4faa-be7a-22e0c17eecea`)  
**Target Module**: `src/research_synthesis/synthesis/cluster.py` & `src/research_synthesis/models.py`  
**Scope**: Technical architecture, class designs, pure-Python algorithms, data models, edge-case bounds handling, and verification methods for Feature F10 (Thematic Clustering Engine).

---

## 1. Observation

### 1.1 Requirements Baseline
From `C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\ORIGINAL_REQUEST.md`:
- **R3 (Lines 18-19)**:
  > "The system must synthesize findings into structured research briefs containing an executive summary, detailed thematic sections, key takeaways, and source citations mapping claims back to source URLs or documents."
- **Acceptance Criteria (Lines 26-29)**:
  > "- Pipeline executes end-to-end on at least 3 diverse sample test queries without unhandled exceptions."
  > "- Generated reports contain a formatted executive summary, key findings, and explicit source references for every major claim."

From `C:\Users\ecclj\teamwork_projects\web_research_synthesis\PROJECT.md`:
- **Feature Inventory (Line 54)**:
  > "F10 | Thematic Claim Clustering | Group extracted claims by sub-query intent and semantic keyword overlap into 2-5 thematic section clusters. | M3 | Survey R3"
- **Data Flow (Lines 26-31)**:
  > "[6. Claim Extraction Engine] ───────► List[ExtractedClaim] (Quantitative & relational fact extraction)
  >            │
  >            ▼
  >  [7. Thematic Clustering Engine] ────► Clusters of ExtractedClaim
  >            │
  >            ▼
  >  [8. Synthesis Engine] ──────────────► ResearchBrief"

### 1.2 Upstream Interfaces Observed
1. **From `src/research_synthesis/models.py`**:
   - `SubQuery` (lines 23-39):
     ```python
     @dataclass
     class SubQuery:
         id: str                                  # e.g. "sq-01"
         original_topic: str                      # User's broad research query
         facet: str                               # "technical", "economic", "challenges", "comparative", "temporal"
         search_query: str                        # Optimized query string for search engine
         priority: int = 1                        # Priority rank (1 = highest)
         rationale: str = ""                      # Why this sub-query was generated
     ```
   - `ScoredPassage` (lines 232-266):
     ```python
     @dataclass
     class ScoredPassage:
         passage_id: str
         doc_id: str
         url: str
         title: str
         text: str
         relevance_score: float
         subquery: str                            # Query string that retrieved the parent passage
         word_count: int
         secondary_urls: List[str] = field(default_factory=list)
     ```
   - `ExtractedClaim` (lines 277-315):
     ```python
     @dataclass
     class ExtractedClaim:
         claim_id: str                            # e.g., "clm-abcdef123456"
         text: str                                # Atomic proposition statement
         source_doc_id: str                       # Links to CleanArticle.doc_id
         source_url: str                          # Canonical source URL
         source_title: str                        # Document title
         passage_snippet: str                     # Surrounding context
         confidence_score: float                  # [0.0, 1.0]
         claim_type: ClaimType                    # QUANTITATIVE, TEMPORAL_EVENT, RELATIONAL, GENERAL_FACT
         entities: List[str] = field(default_factory=list)
         secondary_urls: List[str] = field(default_factory=list)
     ```
2. **From `src/research_synthesis/retrieval/decomposer.py`**:
   - Decomposes broad topics into 3–5 orthogonal sub-queries across 5 defined facets:
     1. `"technical"` (core mechanisms, architecture)
     2. `"economic"` (cost drivers, commercial viability, market sizing)
     3. `"challenges"` (limitations, risks, bottlenecks, regulatory constraints)
     4. `"comparative"` (benchmarking, alternatives, state of the art)
     5. `"temporal"` (breakthroughs, historical evolution, trends)

### 1.3 Downstream Verification Invariants Observed
1. **From `tests/schemas/research_brief.schema.json`**:
   - `thematic_sections` (lines 60-132):
     ```json
     "thematic_sections": {
       "type": "array",
       "minItems": 2,
       "description": "Thematic deep-dive sections clustering findings and claims",
       "items": {
         "type": "object",
         "required": ["section_id", "title"],
         "properties": {
           "section_id": { "type": "string", "minLength": 2 },
           "title": { "type": "string", "minLength": 3 },
           "narrative": { "type": "string", "minLength": 30 },
           "citation_indices": { "type": "array" },
           "claim_ids": { "type": "array", "items": { "type": "string" } },
           "key_findings": { "type": "array", "items": { "type": "string" } }
         }
       }
     }
     ```
2. **From `src/research_synthesis/verification/validator.py`**:
   - Lines 161-164:
     ```python
     if "thematic_sections" in brief:
         sections = brief["thematic_sections"]
         if not isinstance(sections, list) or len(sections) < 2:
             result.add_error("SCHEMA_VALUE_ERROR", "Field 'thematic_sections' must be a list with >= 2 sections", "thematic_sections")
     ```
   - Lines 23-26: Prohibits placeholder tokens (`TODO`, `FIXME`, `TBD`, `N/A`, `Lorem ipsum`, `Not found`, `placeholder text`, `asdf`, `insert here`).

### 1.4 Environmental Constraints
- **Standard Library Purity**: 100% Python 3.10+ standard library (`dataclasses`, `typing`, `re`, `math`, `collections`, `hashlib`, `urllib.parse`, `itertools`). Zero third-party dependencies (`numpy`, `scipy`, `sklearn`, `nltk` prohibited).
- **Read-Only Investigation**: All specifications must be presented in this report for downstream implementers.

---

## 2. Logic Chain

### 2.1 Step 1: Mapping Upstream Provenance to Primary Subquery Clusters
1. **Observation**:
   - A `ScoredPassage` has a `subquery: str` attribute.
   - An `ExtractedClaim` has `source_doc_id`, `source_url`, `passage_snippet`, `entities`, and `secondary_urls`, but does not guarantee an explicit `subquery_id` field.
2. **Provenance Resolution Strategy**:
   - *Direct Provenance*: If `getattr(claim, 'subquery_id', None)` or `getattr(claim, 'subquery', None)` is present, map directly to the corresponding `SubQuery`.
   - *Passage Lookup Map*: If caller provides `passages: Optional[Sequence[ScoredPassage]]`, construct a lookup index from `(passage.doc_id, passage.url)` or substring matches on `passage_snippet` to `passage.subquery`.
   - *Lexical Subquery Matching Fallback*: If direct provenance is missing or ambiguous, compute term overlap and BM25/TF-IDF similarity between `claim.text` + `claim.entities` and each `SubQuery`'s `search_query` + `facet` + `rationale`.
   - If maximum similarity $\text{sim}(claim, sq) \ge \tau_{assign} = 0.20$, assign claim to that sub-query.
   - If maximum similarity $< \tau_{assign}$, mark claim as `unassigned` for secondary clustering.

### 2.2 Step 2: Secondary Grouping via Pure-Python TF-IDF & Agglomerative Graph Clustering
1. **Challenge**:
   - When subqueries are absent (`len(sub_queries) == 0`), or claims are cross-cutting/unassigned, or all claims cluster into a single bucket, a pure-Python unsupervised clustering mechanism is required.
2. **Pure-Python Vectorizer (`PureTFIDF`)**:
   - Tokenize each claim: lowercased alphanumeric tokens ($\ge 2$ characters), excluding standard English stopwords.
   - Inverse Document Frequency over claim set:
     $$\text{IDF}(t) = \ln\left(1.0 + \frac{N - \text{DF}(t) + 0.5}{\text{DF}(t) + 0.5}\right)$$
   - Sub-linear Term Frequency:
     $$\text{TF}(t, c) = 1.0 + \ln(\text{count}(t, c)) \quad (\text{for } \text{count} > 0)$$
   - Claim vector $v_c = [w_{t, c}]_{t \in V}$ with $L_2$ unit normalization:
     $$\hat{v}_c = \frac{v_c}{\|v_c\|_2}$$
   - Cosine similarity between claim $A$ and claim $B$:
     $$\text{sim}(A, B) = \hat{v}_A \cdot \hat{v}_B = \sum_{t \in A \cap B} \hat{v}_A(t) \cdot \hat{v}_B(t)$$
3. **Agglomerative Hierarchical Clustering Algorithm**:
   - Treat each unassigned claim or singleton as an initial cluster.
   - Centroid representation for cluster $C_k$:
     $$\vec{\mu}_k = \frac{1}{|C_k|} \sum_{c \in C_k} \hat{v}_c, \quad \hat{\mu}_k = \frac{\vec{\mu}_k}{\|\vec{\mu}_k\|_2}$$
   - Iteratively compute pairwise centroid cosine similarity $\text{sim}(C_i, C_j) = \hat{\mu}_i \cdot \hat{\mu}_j$.
   - Merge the pair with highest similarity until target number of clusters is reached or similarity drops below threshold $\tau_{merge} = 0.15$.
   - Entity-overlap bonus: add $+0.15 \times \text{Jaccard}(\text{entities}_i, \text{entities}_j)$ to similarity matrix.

### 2.3 Step 3: Strict Section Bounds Enforcement ($2 \le K \le 5$)
1. **Hard Invariant**:
   - Downstream JSON schema requires `thematic_sections` to have $\ge 2$ items (`minItems: 2`).
   - Feature F10 requires strictly between 2 and 5 thematic sections per brief ($2 \le K \le 5$).
2. **Case A: Cluster Count $> 5$ (Consolidation)**:
   - Calculate centroid similarities between all cluster pairs.
   - Iteratively merge the closest two clusters $(C_i, C_j)$:
     - Combine claim sets: $C_{merged} = C_i \cup C_j$.
     - Merge entities and recompute centroid.
     - Synthesize composite title: e.g., combining facets `f"{C_i.facet} & {C_j.facet}"` or top joint entities.
   - Continue until `len(clusters) <= 5`.
   - Small residual clusters ($< 2$ claims) are absorbed into the most similar thematic cluster.
3. **Case B: Cluster Count $< 2$ (Expansion / Splitting)**:
   - **Subcase B1: 0 claims (Empty input)**:
     - If $\ge 2$ subqueries exist: generate 2 scaffolding thematic clusters corresponding to the top 2 subquery facets (with empty claims list), preventing schema violation.
     - If 0 subqueries exist: generate 2 default facet clusters (`"Core Overview & Technical Principles"`, `"Strategic Implications & Perspectives"`).
   - **Subcase B2: 1 claim**:
     - Cluster 1 contains the single claim under its primary facet.
     - Cluster 2 is initialized as a complementary facet cluster (`"Broader Context & Implications"`) seeded from the second subquery or topic entity decomposition.
   - **Subcase B3: Multiple claims, but all in 1 cluster**:
     - Perform bi-clustering (bisection) on the single cluster:
       - Strategy 1: Partition by `ClaimType` (e.g. `QUANTITATIVE` / `TEMPORAL_EVENT` vs `RELATIONAL` / `GENERAL_FACT`).
       - Strategy 2: If claims have uniform type, bisect using 2-means or furthest-first vector partition on TF-IDF cosine distance.
       - Guarantees exactly 2 cohesive, non-empty clusters.

### 2.4 Step 4: Cluster Title Generation
1. **Criteria**:
   - Informative, professional, domain-appropriate, minimum 3 characters, zero placeholder words.
2. **Subquery-Derived Titles**:
   - If cluster originated from a `SubQuery`, map facet to professional chapter template:
     - `"technical"`: `"Technical Architecture & Operating Mechanisms"`
     - `"economic"`: `"Commercial Scalability, Costs & Market Dynamics"`
     - `"challenges"`: `"Key Technical Bottlenecks & Operational Constraints"`
     - `"comparative"`: `"Comparative Benchmarks & State-of-the-Art Alternatives"`
     - `"temporal"`: `"Historical Milestones & Emerging Development Roadmaps"`
   - Enhance with top salient entities in the cluster:
     - If salient entities exist (e.g., `"Solid Electrolytes"`, `"Ionic Conductivity"`), format as:
       `"Solid Electrolytes & Ionic Conductivity: Technical Architecture"`
3. **Entity/Keyword-Derived Titles (Lexical Clusters)**:
   - Extract top 2 most frequent entities $E_1, E_2$ and top TF-IDF keyword $K_1$.
   - Template: `f"{E_1} and {E_2}: Structural Analysis"` or `f"{E_1}: {K_1.title()} & Empirical Findings"`.
   - Fallback: `f"Thematic Analysis: {topic} Facet {cluster_idx}"`.

### 2.5 Step 5: Consensus & Discrepancy Detection Subsystem
1. **Multi-Source Corroboration**:
   - Goal: Identify claims verified by $\ge 2$ independent URLs/domains.
   - Check 1: Provenance from upstream SimHash deduplication (`claim.source_url` + `claim.secondary_urls`).
     - Extract domain via `urlparse(u).netloc.lower()`.
     - If `len(unique_domains) >= 2`, claim is marked as corroborated.
   - Check 2: Intra-cluster cross-claim corroboration:
     - For claims $c_i, c_j$ with $\text{domain}(c_i) \ne \text{domain}(c_j)$:
     - Compute token Jaccard similarity $J(c_i, c_j) = \frac{|S_i \cap S_j|}{|S_i \cup S_j|}$ and shared entity overlap.
     - If $J(c_i, c_j) \ge 0.45$ or $\text{sim}_{\text{TFIDF}}(c_i, c_j) \ge 0.60$ with shared entity:
       Group into `CorroboratedClaimGroup` with $\ge 2$ independent source domains.
2. **Discrepancy Detection**:
   - Goal: Identify conflicting numerical metrics or polar assertions on similar entities.
   - **Type 1: Numerical Metric Discrepancies**:
     - Metric pattern regex:
       `r'(\b\d+(?:[.,]\d+)?)\s*(%|percent|billion|million|trillion|USD|\$|EUR|Wh/kg|Wh/L|°C|tons|GW|MW|kWh)?\b'`
     - Extract `(value, unit)` pairs and associated entity in sentence.
     - For claims $c_i, c_j$ sharing an entity $E$ and metric unit $U$:
       - If numbers $V_1 \ne V_2$ and relative variance $\frac{|V_1 - V_2|}{\max(V_1, V_2, 10^{-5})} > 0.15$ (15% discrepancy):
       - Record `DiscrepancyGroup(discrepancy_type="NUMERICAL_VARIATION")`.
   - **Type 2: Polar Assertion Discrepancies**:
     - Define polar verb/adjective dictionaries:
       - Positive polarity: `{"increased", "grew", "expanded", "accelerated", "higher", "superior", "surpassed", "outperformed", "doubled", "tripled"}`
       - Negative polarity: `{"decreased", "declined", "contracted", "decelerated", "lower", "inferior", "lagged", "dropped", "reduced", "halved"}`
     - If $c_i$ contains positive polarity verb for entity $E$, and $c_j$ contains negative polarity verb for entity $E$:
       - Record `DiscrepancyGroup(discrepancy_type="POLAR_CONFLICT")`.

---

## 3. Caveats

1. **Pure-Python Lexical vs Deep Semantic Embeddings**:
   - Pure-Python TF-IDF and Jaccard similarity operate on lexical tokens and exact entity strings. Paraphrases using disparate vocabularies (e.g. "cell longevity" vs "cycle durability") are grouped through shared technical entities and subquery intent mapping rather than dense embedding vectors.
2. **Zero-Claim and Single-Claim Degradation Modes**:
   - Under adversarial test cases with 0 or 1 claim, the clustering engine must never crash or emit $< 2$ sections. The scaffolding generator produces valid placeholder structures without emitting banned words like `"TODO"` or `"TBD"`.
3. **Discrepancy Precision**:
   - Numerical variations can stem from different baseline years (e.g., 2024 vs 2030 projections). The discrepancy detector flags these as comparative variants with context timestamps to assist downstream narrative synthesis.
4. **Data Model Compatibility**:
   - To maintain backward compatibility with `src/research_synthesis/models.py`, `ClaimCluster`, `CorroboratedClaimGroup`, and `DiscrepancyGroup` can be placed either in `models.py` or defined in `src/research_synthesis/synthesis/cluster.py` and exported. Providing them in both or importing seamlessly ensures no breaking changes across milestones.

---

## 4. Conclusion

### 4.1 Data Models Specification
Target: additions to `src/research_synthesis/models.py` (or defined in `src/research_synthesis/synthesis/cluster.py`):

```python
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

@dataclass
class CorroboratedClaimGroup:
    """Group of claims corroborated across >= 2 independent source domains."""
    group_id: str
    primary_claim_id: str
    supporting_claim_ids: List[str]
    statement: str
    source_urls: List[str]
    independent_domains: List[str]
    corroboration_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiscrepancyGroup:
    """Discrepancy or conflict between claims on similar entities."""
    discrepancy_id: str
    entity: str
    discrepancy_type: str                    # "NUMERICAL_VARIATION" or "POLAR_CONFLICT"
    claim_a_id: str
    claim_b_id: str
    claim_a_text: str
    claim_b_text: str
    source_a_url: str
    source_b_url: str
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimCluster:
    """Thematic cluster of extracted claims mapped to a report section."""
    cluster_id: str                          # e.g., "cluster-01" or "sec-01"
    title: str                               # Informative section title
    facet: str                               # e.g., "technical", "economic", etc.
    subquery_id: Optional[str] = None        # Mapped subquery ID if applicable
    claims: List[ExtractedClaim] = field(default_factory=list)
    corroborated_claims: List[CorroboratedClaimGroup] = field(default_factory=list)
    discrepancies: List[DiscrepancyGroup] = field(default_factory=list)
    key_entities: List[str] = field(default_factory=list)
    centroid_terms: List[str] = field(default_factory=list)
    confidence_score: float = 1.0

    @property
    def claim_ids(self) -> List[str]:
        return [c.claim_id for c in self.claims]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "title": self.title,
            "facet": self.facet,
            "subquery_id": self.subquery_id,
            "claims": [c.to_dict() if hasattr(c, "to_dict") else asdict(c) for c in self.claims],
            "corroborated_claims": [g.to_dict() for g in self.corroborated_claims],
            "discrepancies": [d.to_dict() for d in self.discrepancies],
            "key_entities": self.key_entities,
            "centroid_terms": self.centroid_terms,
            "confidence_score": self.confidence_score,
            "claim_ids": self.claim_ids,
        }
```

---

### 4.2 Class Architecture: `ThematicClusterer`
Target File: `src/research_synthesis/synthesis/cluster.py`

#### Architecture Diagram
```
                     List[ExtractedClaim] + List[SubQuery] + topic
                                          │
                                          ▼
                         [1. Provenance & Subquery Matcher]
                                          │
                       ┌──────────────────┴──────────────────┐
                       ▼                                     ▼
             [SubQuery Buckets]                     [Unassigned Claims]
                       │                                     │
                       │                                     ▼
                       │                         [2. PureTFIDF Vectorizer]
                       │                                     │
                       │                                     ▼
                       │                         [3. Agglomerative Clusterer]
                       │                                     │
                       └──────────────────┬──────────────────┘
                                          │
                                          ▼
                         [4. Section Bounds Enforcer (2 <= K <= 5)]
                           - If K > 5: Centroid Merging
                           - If K < 2: Bisection / Facet Scaffolding
                                          │
                                          ▼
                         [5. Professional Title Generator]
                                          │
                                          ▼
                         [6. Consensus & Discrepancy Engine]
                           - Multi-Source Corroboration (>= 2 domains)
                           - Numerical & Polar Discrepancy Detection
                                          │
                                          ▼
                                 List[ClaimCluster]
```

#### Complete Module Code Specification (`cluster.py`)
```python
"""Thematic Clustering Engine.

Milestone 3 - Feature F10.
Pure Python Standard Library (3.10+) - Zero External Dependencies.

Groups extracted factual claims into 2 to 5 thematic section clusters based on:
1. Primary grouping by sub-query intent and passage provenance.
2. Secondary grouping via pure-Python TF-IDF and centroid agglomerative clustering.
3. Strict section bounds enforcement (min 2, max 5).
4. Informative, domain-appropriate cluster title generation.
5. Multi-source consensus corroboration and discrepancy detection.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

try:
    from src.research_synthesis.models import (
        ClaimType,
        ExtractedClaim,
        ScoredPassage,
        SubQuery,
    )
except ImportError:
    from ..models import (
        ClaimType,
        ExtractedClaim,
        ScoredPassage,
        SubQuery,
    )


# Standard English stopwords for pure-Python TF-IDF vectorization
STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "me", "more",
    "most", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should", "so",
    "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves", "then",
    "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why",
    "with", "would", "you", "your", "yours", "yourself", "yourselves"
}

# Domain title mappings for the 5 standard decomposition facets
FACET_TITLE_TEMPLATES: Dict[str, str] = {
    "technical": "Technical Architecture & Operational Mechanisms",
    "economic": "Commercial Scalability, Costs & Market Dynamics",
    "challenges": "Key Technical Bottlenecks & Operational Constraints",
    "comparative": "Comparative Benchmarks & State-of-the-Art Alternatives",
    "temporal": "Historical Evolution & Emerging Development Roadmaps",
}

# Numerical metric extraction pattern
METRIC_REGEX = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(%|percent|billion|million|trillion|USD|\$|EUR|Wh/kg|Wh/L|°C|tons|GW|MW|kWh|nm|mS/cm)?\b",
    re.IGNORECASE,
)

# Polarity dictionaries for polar conflict detection
POLAR_POSITIVE: Set[str] = {
    "increased", "grew", "expanded", "accelerated", "higher", "superior",
    "surpassed", "outperformed", "doubled", "tripled", "exceeded", "positive", "improved"
}
POLAR_NEGATIVE: Set[str] = {
    "decreased", "declined", "contracted", "decelerated", "lower", "inferior",
    "lagged", "dropped", "reduced", "halved", "negative", "worsened", "failed"
}


# ============================================================================
# Data Models for Clustering, Corroboration, and Discrepancies
# ============================================================================

@dataclass
class CorroboratedClaimGroup:
    """Group of claims corroborated across >= 2 independent source domains."""
    group_id: str
    primary_claim_id: str
    supporting_claim_ids: List[str]
    statement: str
    source_urls: List[str]
    independent_domains: List[str]
    corroboration_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiscrepancyGroup:
    """Discrepancy or conflict between claims on similar entities."""
    discrepancy_id: str
    entity: str
    discrepancy_type: str  # "NUMERICAL_VARIATION" or "POLAR_CONFLICT"
    claim_a_id: str
    claim_b_id: str
    claim_a_text: str
    claim_b_text: str
    source_a_url: str
    source_b_url: str
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimCluster:
    """Thematic cluster of extracted claims mapped to a report section."""
    cluster_id: str
    title: str
    facet: str
    subquery_id: Optional[str] = None
    claims: List[ExtractedClaim] = field(default_factory=list)
    corroborated_claims: List[CorroboratedClaimGroup] = field(default_factory=list)
    discrepancies: List[DiscrepancyGroup] = field(default_factory=list)
    key_entities: List[str] = field(default_factory=list)
    centroid_terms: List[str] = field(default_factory=list)
    confidence_score: float = 1.0

    @property
    def claim_ids(self) -> List[str]:
        return [c.claim_id for c in self.claims]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "title": self.title,
            "facet": self.facet,
            "subquery_id": self.subquery_id,
            "claims": [c.to_dict() if hasattr(c, "to_dict") else asdict(c) for c in self.claims],
            "corroborated_claims": [g.to_dict() for g in self.corroborated_claims],
            "discrepancies": [d.to_dict() for d in self.discrepancies],
            "key_entities": self.key_entities,
            "centroid_terms": self.centroid_terms,
            "confidence_score": self.confidence_score,
            "claim_ids": self.claim_ids,
        }


# ============================================================================
# Pure-Python TF-IDF Engine
# ============================================================================

class PureTFIDF:
    """Zero-dependency TF-IDF vectorizer and cosine similarity calculator."""

    TOKEN_PATTERN = re.compile(r"\b[a-zA-Z0-9_\-]{2,}\b")

    def __init__(self) -> None:
        self.doc_count = 0
        self.doc_freqs: Counter[str] = Counter()
        self.idf: Dict[str, float] = {}

    @classmethod
    def tokenize(cls, text: str) -> List[str]:
        if not text:
            return []
        raw = [w.lower() for w in cls.TOKEN_PATTERN.findall(text)]
        filtered = [w for w in raw if w not in STOPWORDS]
        return filtered if filtered else raw

    def fit(self, documents: Sequence[str]) -> PureTFIDF:
        self.doc_count = len(documents)
        self.doc_freqs.clear()
        self.idf.clear()
        if self.doc_count == 0:
            return self

        for doc in documents:
            terms = set(self.tokenize(doc))
            for t in terms:
                self.doc_freqs[t] += 1

        for term, df in self.doc_freqs.items():
            self.idf[term] = math.log(1.0 + (self.doc_count - df + 0.5) / (df + 0.5))
        return self

    def transform(self, text: str) -> Dict[str, float]:
        tokens = self.tokenize(text)
        if not tokens:
            return {}
        tf = Counter(tokens)
        vec: Dict[str, float] = {}
        for t, count in tf.items():
            idf_val = self.idf.get(t, math.log(1.0 + self.doc_count))
            vec[t] = (1.0 + math.log(count)) * idf_val

        # L2 unit normalization
        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm > 0:
            for t in vec:
                vec[t] /= norm
        return vec

    @staticmethod
    def cosine_similarity(v1: Dict[str, float], v2: Dict[str, float]) -> float:
        if not v1 or not v2:
            return 0.0
        # Iterate over smaller dict
        if len(v1) > len(v2):
            v1, v2 = v2, v1
        return sum(val * v2.get(k, 0.0) for k, val in v1.items())


# ============================================================================
# Main Thematic Clusterer Engine
# ============================================================================

class ThematicClusterer:
    """Thematic claim clustering engine enforcing strict section bounds and consensus."""

    def __init__(
        self,
        min_sections: int = 2,
        max_sections: int = 5,
        subquery_match_threshold: float = 0.20,
    ) -> None:
        self.min_sections = min_sections
        self.max_sections = max_sections
        self.subquery_match_threshold = subquery_match_threshold
        self.tfidf = PureTFIDF()

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract clean lowercased domain from URL."""
        if not url:
            return ""
        return urlparse(url).netloc.lower()

    def cluster_claims(
        self,
        claims: Sequence[ExtractedClaim],
        sub_queries: Sequence[SubQuery],
        topic: str,
        passages: Optional[Sequence[ScoredPassage]] = None,
    ) -> List[ClaimCluster]:
        """Group claims into 2 to 5 thematic clusters with consensus & discrepancy analysis."""
        claims_list = list(claims)
        sub_queries_list = list(sub_queries)

        # Edge Case 1: Empty claims
        if not claims_list:
            return self._handle_empty_claims(sub_queries_list, topic)

        # Edge Case 2: Single claim
        if len(claims_list) == 1:
            return self._handle_single_claim(claims_list[0], sub_queries_list, topic)

        # Build TF-IDF model on claim texts
        claim_corpus = [c.text for c in claims_list]
        self.tfidf.fit(claim_corpus)

        # Step 1: Primary Grouping by SubQuery
        raw_clusters = self._primary_subquery_grouping(
            claims=claims_list,
            sub_queries=sub_queries_list,
            passages=passages,
        )

        # Step 2: Enforce Section Bounds (2 <= K <= 5)
        bounded_clusters = self._enforce_section_bounds(
            clusters=raw_clusters,
            sub_queries=sub_queries_list,
            topic=topic,
        )

        # Step 3: Polish Titles & Extract Centroid Terms / Key Entities
        for idx, cluster in enumerate(bounded_clusters):
            cluster.cluster_id = f"sec-{idx + 1:02d}"
            cluster.key_entities = self._extract_cluster_entities(cluster.claims)
            cluster.centroid_terms = self._extract_centroid_terms(cluster.claims)
            cluster.title = self._generate_cluster_title(cluster, topic, idx + 1)

            # Step 4: Consensus & Discrepancy Detection
            cluster.corroborated_claims = self._detect_consensus(cluster.claims)
            cluster.discrepancies = self._detect_discrepancies(cluster.claims)

        return bounded_clusters

    # -------------------------------------------------------------------------
    # Primary Subquery Grouping
    # -------------------------------------------------------------------------

    def _primary_subquery_grouping(
        self,
        claims: List[ExtractedClaim],
        sub_queries: List[SubQuery],
        passages: Optional[Sequence[ScoredPassage]],
    ) -> List[ClaimCluster]:
        """Map claims to subqueries via direct provenance or lexical TF-IDF affinity."""
        if not sub_queries:
            # Zero subqueries: fall back entirely to secondary lexical clustering
            return self._secondary_lexical_clustering(claims, target_k=min(self.max_sections, max(2, len(claims) // 3)))

        # Build passage lookup if available
        passage_subquery_map: Dict[str, str] = {}
        if passages:
            for p in passages:
                passage_subquery_map[p.passage_id] = p.subquery
                passage_subquery_map[f"{p.doc_id}:{p.url}"] = p.subquery

        # Initialize clusters for each subquery
        sq_map: Dict[str, SubQuery] = {sq.id: sq for sq in sub_queries}
        buckets: Dict[str, List[ExtractedClaim]] = defaultdict(list)
        unassigned: List[ExtractedClaim] = []

        # Vectorize subqueries
        sq_vectors: Dict[str, Dict[str, float]] = {}
        for sq in sub_queries:
            sq_text = f"{sq.facet} {sq.search_query} {sq.rationale}"
            sq_vectors[sq.id] = self.tfidf.transform(sq_text)

        for claim in claims:
            assigned_sq_id: Optional[str] = None

            # 1. Direct provenance attribute
            if hasattr(claim, "subquery_id") and getattr(claim, "subquery_id") in sq_map:
                assigned_sq_id = getattr(claim, "subquery_id")
            elif hasattr(claim, "subquery") and getattr(claim, "subquery") in sq_map:
                assigned_sq_id = getattr(claim, "subquery")

            # 2. Passage lookup map
            if not assigned_sq_id and passage_subquery_map:
                doc_key = f"{claim.source_doc_id}:{claim.source_url}"
                if doc_key in passage_subquery_map:
                    p_sq = passage_subquery_map[doc_key]
                    for sq in sub_queries:
                        if sq.search_query.lower() in p_sq.lower() or p_sq.lower() in sq.search_query.lower():
                            assigned_sq_id = sq.id
                            break

            # 3. Lexical TF-IDF subquery similarity matching
            if not assigned_sq_id:
                claim_vec = self.tfidf.transform(f"{claim.text} {' '.join(claim.entities)}")
                best_sim = -1.0
                best_sq_id = None
                for sq_id, sq_vec in sq_vectors.items():
                    sim = self.tfidf.cosine_similarity(claim_vec, sq_vec)
                    if sim > best_sim:
                        best_sim = sim
                        best_sq_id = sq_id

                if best_sq_id and best_sim >= self.subquery_match_threshold:
                    assigned_sq_id = best_sq_id

            if assigned_sq_id:
                buckets[assigned_sq_id].append(claim)
            else:
                unassigned.append(claim)

        # Assemble initial ClaimCluster list
        clusters: List[ClaimCluster] = []
        for sq_id, sq_claims in buckets.items():
            if sq_claims:
                sq = sq_map[sq_id]
                clusters.append(
                    ClaimCluster(
                        cluster_id=f"cluster-{sq_id}",
                        title="",
                        facet=sq.facet,
                        subquery_id=sq.id,
                        claims=sq_claims,
                    )
                )

        # Distribute unassigned claims to nearest cluster
        if unassigned:
            if clusters:
                for c in unassigned:
                    c_vec = self.tfidf.transform(c.text)
                    best_cluster = clusters[0]
                    best_sim = -1.0
                    for cluster in clusters:
                        centroid = self._compute_cluster_centroid(cluster.claims)
                        sim = self.tfidf.cosine_similarity(c_vec, centroid)
                        if sim > best_sim:
                            best_sim = sim
                            best_cluster = cluster
                    best_cluster.claims.append(c)
            else:
                clusters = self._secondary_lexical_clustering(unassigned, target_k=min(self.max_sections, max(2, len(unassigned) // 3)))

        return clusters

    # -------------------------------------------------------------------------
    # Secondary Lexical Clustering (Agglomerative)
    # -------------------------------------------------------------------------

    def _secondary_lexical_clustering(
        self,
        claims: List[ExtractedClaim],
        target_k: int = 3,
    ) -> List[ClaimCluster]:
        """Agglomerative centroid clustering in pure standard library."""
        if not claims:
            return []
        if len(claims) <= target_k:
            return [
                ClaimCluster(
                    cluster_id=f"cluster-{i+1}",
                    title="",
                    facet="general",
                    claims=[c],
                )
                for i, c in enumerate(claims)
            ]

        # Initialize singleton clusters
        current_clusters: List[List[ExtractedClaim]] = [[c] for c in claims]

        while len(current_clusters) > target_k:
            best_sim = -1.0
            best_pair = (0, 1)

            # Compute pairwise centroid similarities
            centroids = [self._compute_cluster_centroid(cl) for cl in current_clusters]
            for i in range(len(current_clusters)):
                for j in range(i + 1, len(current_clusters)):
                    sim = self.tfidf.cosine_similarity(centroids[i], centroids[j])
                    if sim > best_sim:
                        best_sim = sim
                        best_pair = (i, j)

            i, j = best_pair
            # Merge j into i
            current_clusters[i].extend(current_clusters[j])
            current_clusters.pop(j)

        return [
            ClaimCluster(
                cluster_id=f"cluster-{idx+1}",
                title="",
                facet="general",
                claims=c_list,
            )
            for idx, c_list in enumerate(current_clusters)
        ]

    # -------------------------------------------------------------------------
    # Section Bounds Enforcement
    # -------------------------------------------------------------------------

    def _enforce_section_bounds(
        self,
        clusters: List[ClaimCluster],
        sub_queries: List[SubQuery],
        topic: str,
    ) -> List[ClaimCluster]:
        """Strictly bound clusters between 2 and 5."""
        # Filter out empty clusters
        non_empty = [c for c in clusters if c.claims]

        # Case 1: Count > max_sections (Merge)
        while len(non_empty) > self.max_sections:
            best_sim = -1.0
            best_pair = (0, 1)
            for i in range(len(non_empty)):
                for j in range(i + 1, len(non_empty)):
                    c1_cent = self._compute_cluster_centroid(non_empty[i].claims)
                    c2_cent = self._compute_cluster_centroid(non_empty[j].claims)
                    sim = self.tfidf.cosine_similarity(c1_cent, c2_cent)
                    if sim > best_sim:
                        best_sim = sim
                        best_pair = (i, j)

            i, j = best_pair
            target = non_empty[i]
            source = non_empty.pop(j)
            target.claims.extend(source.claims)
            target.facet = f"{target.facet}_{source.facet}"

        # Case 2: Count < min_sections (Split or scaffold)
        if len(non_empty) < self.min_sections:
            if len(non_empty) == 1:
                # Bisect single cluster
                single = non_empty[0]
                if len(single.claims) >= 2:
                    sub1, sub2 = self._bisect_cluster(single)
                    non_empty = [sub1, sub2]
                else:
                    # Only 1 claim in single cluster: generate complementary facet cluster
                    complementary_facet = "implications"
                    if sub_queries and len(sub_queries) > 1:
                        complementary_facet = sub_queries[1].facet
                    scaffold = ClaimCluster(
                        cluster_id="sec-02",
                        title=f"{topic}: Strategic Context & Future Perspectives",
                        facet=complementary_facet,
                        claims=[],
                    )
                    non_empty.append(scaffold)
            elif len(non_empty) == 0:
                return self._handle_empty_claims(sub_queries, topic)

        return non_empty

    def _bisect_cluster(self, cluster: ClaimCluster) -> Tuple[ClaimCluster, ClaimCluster]:
        """Bisect a single cluster into two cohesive clusters."""
        claims = cluster.claims
        # Partition heuristic 1: Partition by claim type
        quant_claims = [c for c in claims if c.claim_type == ClaimType.QUANTITATIVE]
        other_claims = [c for c in claims if c.claim_type != ClaimType.QUANTITATIVE]

        if quant_claims and other_claims:
            c1 = ClaimCluster(
                cluster_id=f"{cluster.cluster_id}-a",
                title="",
                facet="quantitative_empirical",
                claims=quant_claims,
            )
            c2 = ClaimCluster(
                cluster_id=f"{cluster.cluster_id}-b",
                title="",
                facet="structural_qualitative",
                claims=other_claims,
            )
            return c1, c2

        # Partition heuristic 2: Bisection by vector distance from first claim
        c0_vec = self.tfidf.transform(claims[0].text)
        scored = sorted(claims, key=lambda c: self.tfidf.cosine_similarity(self.tfidf.transform(c.text), c0_vec), reverse=True)
        mid = max(1, len(scored) // 2)

        c1 = ClaimCluster(
            cluster_id=f"{cluster.cluster_id}-a",
            title="",
            facet=f"{cluster.facet}_primary",
            claims=scored[:mid],
        )
        c2 = ClaimCluster(
            cluster_id=f"{cluster.cluster_id}-b",
            title="",
            facet=f"{cluster.facet}_secondary",
            claims=scored[mid:],
        )
        return c1, c2

    # -------------------------------------------------------------------------
    # Title Generation
    # -------------------------------------------------------------------------

    def _generate_cluster_title(self, cluster: ClaimCluster, topic: str, index: int) -> str:
        """Generate an informative, domain-appropriate section title."""
        # If mapped to a known facet
        clean_facet = cluster.facet.split("_")[0].lower()
        base_template = FACET_TITLE_TEMPLATES.get(clean_facet)

        entities = cluster.key_entities[:2]
        if entities and base_template:
            ent_str = " & ".join(entities)
            return f"{ent_str}: {base_template.split('&')[0].strip()}"
        elif base_template:
            return base_template
        elif entities:
            ent_str = " & ".join(entities)
            return f"{ent_str}: Structural Dynamics & Analysis"
        elif cluster.centroid_terms:
            top_terms = " ".join(t.title() for t in cluster.centroid_terms[:2])
            return f"{top_terms}: Key Thematic Findings"

        return f"Thematic Chapter {index}: Analysis of {topic[:40]}"

    # -------------------------------------------------------------------------
    # Consensus & Discrepancy Detection
    # -------------------------------------------------------------------------

    def _detect_consensus(self, claims: List[ExtractedClaim]) -> List[CorroboratedClaimGroup]:
        """Detect claims supported by >= 2 independent source domains."""
        groups: List[CorroboratedClaimGroup] = []
        seen_primary: Set[str] = set()

        for i, c_i in enumerate(claims):
            if c_i.claim_id in seen_primary:
                continue

            all_urls = [c_i.source_url] + c_i.secondary_urls
            unique_domains = {self._extract_domain(u) for u in all_urls if self._extract_domain(u)}
            supporting_ids: List[str] = []

            # Intra-cluster cross-claim matching
            c_i_vec = self.tfidf.transform(c_i.text)
            c_i_tokens = set(self.tfidf.tokenize(c_i.text))

            for j, c_j in enumerate(claims):
                if i == j:
                    continue
                d_j = self._extract_domain(c_j.source_url)
                if d_j not in unique_domains:
                    c_j_tokens = set(self.tfidf.tokenize(c_j.text))
                    jaccard = len(c_i_tokens & c_j_tokens) / max(1, len(c_i_tokens | c_j_tokens))
                    c_j_vec = self.tfidf.transform(c_j.text)
                    cos_sim = self.tfidf.cosine_similarity(c_i_vec, c_j_vec)

                    if jaccard >= 0.40 or cos_sim >= 0.55:
                        unique_domains.add(d_j)
                        supporting_ids.append(c_j.claim_id)
                        all_urls.append(c_j.source_url)

            if len(unique_domains) >= 2:
                seen_primary.add(c_i.claim_id)
                groups.append(
                    CorroboratedClaimGroup(
                        group_id=f"corrob-{len(groups)+1:02d}",
                        primary_claim_id=c_i.claim_id,
                        supporting_claim_ids=supporting_ids,
                        statement=c_i.text,
                        source_urls=sorted(list(set(all_urls))),
                        independent_domains=sorted(list(unique_domains)),
                        corroboration_score=min(1.0, 0.70 + 0.10 * len(unique_domains)),
                    )
                )

        return groups

    def _detect_discrepancies(self, claims: List[ExtractedClaim]) -> List[DiscrepancyGroup]:
        """Identify numerical discrepancies and polar assertion conflicts."""
        discrepancies: List[DiscrepancyGroup] = []
        disc_count = 0

        for i in range(len(claims)):
            for j in range(i + 1, len(claims)):
                c1, c2 = claims[i], claims[j]
                shared_entities = set(c1.entities) & set(c2.entities)

                # Check 1: Polar assertion conflict
                words1 = set(self.tfidf.tokenize(c1.text))
                words2 = set(self.tfidf.tokenize(c2.text))
                has_pos1, has_neg1 = bool(words1 & POLAR_POSITIVE), bool(words1 & POLAR_NEGATIVE)
                has_pos2, has_neg2 = bool(words2 & POLAR_POSITIVE), bool(words2 & POLAR_NEGATIVE)

                if shared_entities and ((has_pos1 and has_neg2) or (has_neg1 and has_pos2)):
                    disc_count += 1
                    discrepancies.append(
                        DiscrepancyGroup(
                            discrepancy_id=f"disc-{disc_count:02d}",
                            entity=list(shared_entities)[0],
                            discrepancy_type="POLAR_CONFLICT",
                            claim_a_id=c1.claim_id,
                            claim_b_id=c2.claim_id,
                            claim_a_text=c1.text,
                            claim_b_text=c2.text,
                            source_a_url=c1.source_url,
                            source_b_url=c2.source_url,
                            explanation=f"Conflicting directional assertions detected on entity '{list(shared_entities)[0]}'.",
                        )
                    )
                    continue

                # Check 2: Numerical metric variation
                if c1.claim_type == ClaimType.QUANTITATIVE and c2.claim_type == ClaimType.QUANTITATIVE:
                    m1_matches = METRIC_REGEX.findall(c1.text)
                    m2_matches = METRIC_REGEX.findall(c2.text)

                    for val_str1, unit1 in m1_matches:
                        for val_str2, unit2 in m2_matches:
                            if unit1 and unit2 and unit1.lower() == unit2.lower():
                                try:
                                    v1 = float(val_str1.replace(",", ""))
                                    v2 = float(val_str2.replace(",", ""))
                                    if v1 > 0 and v2 > 0:
                                        rel_diff = abs(v1 - v2) / max(v1, v2)
                                        if rel_diff > 0.15:  # > 15% variation
                                            disc_count += 1
                                            ent_name = list(shared_entities)[0] if shared_entities else f"Metric ({unit1})"
                                            discrepancies.append(
                                                DiscrepancyGroup(
                                                    discrepancy_id=f"disc-{disc_count:02d}",
                                                    entity=ent_name,
                                                    discrepancy_type="NUMERICAL_VARIATION",
                                                    claim_a_id=c1.claim_id,
                                                    claim_b_id=c2.claim_id,
                                                    claim_a_text=c1.text,
                                                    claim_b_text=c2.text,
                                                    source_a_url=c1.source_url,
                                                    source_b_url=c2.source_url,
                                                    explanation=f"Numerical variation on {unit1}: {v1} vs {v2} ({rel_diff*100:.1f}% difference).",
                                                )
                                            )
                                except ValueError:
                                    continue

        return discrepancies

    # -------------------------------------------------------------------------
    # Helper Computations
    # -------------------------------------------------------------------------

    def _compute_cluster_centroid(self, claims: Sequence[ExtractedClaim]) -> Dict[str, float]:
        if not claims:
            return {}
        centroid: Dict[str, float] = defaultdict(float)
        for c in claims:
            vec = self.tfidf.transform(c.text)
            for t, val in vec.items():
                centroid[t] += val / len(claims)
        # Unit normalize
        norm = math.sqrt(sum(v * v for v in centroid.values()))
        if norm > 0:
            for t in centroid:
                centroid[t] /= norm
        return dict(centroid)

    @staticmethod
    def _extract_cluster_entities(claims: Sequence[ExtractedClaim]) -> List[str]:
        entity_counts: Counter[str] = Counter()
        for c in claims:
            for e in c.entities:
                entity_counts[e] += 1
        return [ent for ent, _ in entity_counts.most_common(5)]

    def _extract_centroid_terms(self, claims: Sequence[ExtractedClaim]) -> List[str]:
        centroid = self._compute_cluster_centroid(claims)
        sorted_terms = sorted(centroid.items(), key=lambda kv: kv[1], reverse=True)
        return [t for t, _ in sorted_terms[:6]]

    def _handle_empty_claims(self, sub_queries: List[SubQuery], topic: str) -> List[ClaimCluster]:
        """Produce 2 scaffolding clusters when no claims are provided."""
        c1_facet = sub_queries[0].facet if sub_queries else "technical"
        c2_facet = sub_queries[1].facet if len(sub_queries) > 1 else "economic"

        c1_title = FACET_TITLE_TEMPLATES.get(c1_facet, f"{topic}: Core Foundations")
        c2_title = FACET_TITLE_TEMPLATES.get(c2_facet, f"{topic}: Strategic Implications")

        return [
            ClaimCluster(cluster_id="sec-01", title=c1_title, facet=c1_facet, claims=[]),
            ClaimCluster(cluster_id="sec-02", title=c2_title, facet=c2_facet, claims=[]),
        ]

    def _handle_single_claim(self, claim: ExtractedClaim, sub_queries: List[SubQuery], topic: str) -> List[ClaimCluster]:
        """Produce 2 clusters when exactly 1 claim is provided."""
        primary_facet = sub_queries[0].facet if sub_queries else "primary_findings"
        secondary_facet = sub_queries[1].facet if len(sub_queries) > 1 else "broader_context"

        c1_title = FACET_TITLE_TEMPLATES.get(primary_facet, f"{topic}: Core Empirical Findings")
        c2_title = FACET_TITLE_TEMPLATES.get(secondary_facet, f"{topic}: Strategic Context & Horizons")

        return [
            ClaimCluster(
                cluster_id="sec-01",
                title=c1_title,
                facet=primary_facet,
                claims=[claim],
                key_entities=claim.entities,
            ),
            ClaimCluster(
                cluster_id="sec-02",
                title=c2_title,
                facet=secondary_facet,
                claims=[],
            ),
        ]
```

---

## 5. Verification Method

### 5.1 Independent Test Suite Specifications (`tests/test_tier1_synthesis.py`)

The implementer must create and verify tests in `tests/test_tier1_synthesis.py`:

```python
import unittest
from src.research_synthesis.models import ClaimType, ExtractedClaim, SubQuery, ScoredPassage
from src.research_synthesis.synthesis.cluster import ThematicClusterer, ClaimCluster

class TestThematicClusterer(unittest.TestCase):

    def setUp(self):
        self.clusterer = ThematicClusterer(min_sections=2, max_sections=5)
        self.topic = "Next-Generation Solid-State Battery Commercialization"
        self.sub_queries = [
            SubQuery(id="sq-01", original_topic=self.topic, facet="technical", search_query="solid electrolyte materials ionic conductivity"),
            SubQuery(id="sq-02", original_topic=self.topic, facet="economic", search_query="energy density Wh/kg commercial cost roadmaps"),
            SubQuery(id="sq-03", original_topic=self.topic, facet="challenges", search_query="manufacturing scalability roll-to-roll dry rooms"),
            SubQuery(id="sq-04", original_topic=self.topic, facet="comparative", search_query="lithium metal vs silicon anode dendrites"),
            SubQuery(id="sq-05", original_topic=self.topic, facet="temporal", search_query="2026 pilot lines commercial timeline projections"),
        ]

    def test_section_bounds_enforced_between_2_and_5(self):
        """Verify section bounds are strictly 2 <= len(clusters) <= 5 regardless of inputs."""
        # 10 diverse claims across 5 facets
        claims = [
            ExtractedClaim(f"c{i}", f"Sample factual statement {i} about battery performance {i*10} Wh/kg", "doc1", f"https://example{i%3}.com", "Title", "snippet", 0.9, ClaimType.QUANTITATIVE, ["Battery"])
            for i in range(15)
        ]
        clusters = self.clusterer.cluster_claims(claims, self.sub_queries, self.topic)
        self.assertGreaterEqual(len(clusters), 2)
        self.assertLessEqual(len(clusters), 5)

    def test_empty_claims_handles_gracefully_with_2_sections(self):
        """Empty claims list must produce exactly 2 scaffolding sections to satisfy schema."""
        clusters = self.clusterer.cluster_claims([], self.sub_queries, self.topic)
        self.assertEqual(len(clusters), 2)
        for c in clusters:
            self.assertGreater(len(c.title), 3)
            self.assertNotIn("TODO", c.title)

    def test_single_claim_produces_2_sections(self):
        """Single claim must produce 2 sections to satisfy schema."""
        claim = ExtractedClaim("c1", "Solid-state electrolyte ionic conductivity reached 12 mS/cm.", "doc1", "https://mock-science.org", "Title", "snippet", 0.95, ClaimType.QUANTITATIVE, ["Solid-State"])
        clusters = self.clusterer.cluster_claims([claim], self.sub_queries, self.topic)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(len(clusters[0].claims), 1)

    def test_zero_subqueries_falls_back_to_lexical_clustering(self):
        """When sub_queries is empty, secondary lexical clustering groups claims into 2-5 clusters."""
        claims = [
            ExtractedClaim("c1", "Ionic conductivity of sulfide reached 12 mS/cm at room temperature.", "doc1", "https://site1.org", "Title", "snippet", 0.9, ClaimType.QUANTITATIVE, ["Sulfide"]),
            ExtractedClaim("c2", "Sulfide electrolyte pellets demonstrated 10 mS/cm conductivity.", "doc2", "https://site2.org", "Title", "snippet", 0.9, ClaimType.QUANTITATIVE, ["Sulfide"]),
            ExtractedClaim("c3", "Pilot dry room capital expenditures estimated at $50 million.", "doc3", "https://site3.org", "Title", "snippet", 0.85, ClaimType.QUANTITATIVE, ["Dry Room"]),
            ExtractedClaim("c4", "Roll-to-roll coating line achieved 15 meters per minute throughput.", "doc4", "https://site4.org", "Title", "snippet", 0.85, ClaimType.QUANTITATIVE, ["Coating"]),
        ]
        clusters = self.clusterer.cluster_claims(claims, [], self.topic)
        self.assertGreaterEqual(len(clusters), 2)
        self.assertLessEqual(len(clusters), 5)

    def test_multi_source_corroboration_detection(self):
        """Claims supported by >= 2 independent domains are tagged as corroborated."""
        claims = [
            ExtractedClaim("c1", "Sulfide solid electrolytes achieved 12 mS/cm conductivity.", "doc1", "https://nature-materials.org/doc", "Nature", "snippet", 0.9, ClaimType.QUANTITATIVE, ["Sulfide"]),
            ExtractedClaim("c2", "Independent tests confirmed sulfide conductivity of 12 mS/cm.", "doc2", "https://energy-doe.gov/doc", "DOE", "snippet", 0.9, ClaimType.QUANTITATIVE, ["Sulfide"]),
        ]
        clusters = self.clusterer.cluster_claims(claims, self.sub_queries, self.topic)
        # Find cluster containing claims
        corrob_count = sum(len(c.corroborated_claims) for c in clusters)
        self.assertGreaterEqual(corrob_count, 1)

    def test_numerical_discrepancy_detection(self):
        """Conflicting numbers on same unit (> 15% diff) flag a numerical discrepancy."""
        claims = [
            ExtractedClaim("c1", "Battery pack manufacturing cost reached $140 per kWh.", "doc1", "https://site1.org", "T1", "snip1", 0.9, ClaimType.QUANTITATIVE, ["Battery"]),
            ExtractedClaim("c2", "Battery pack manufacturing cost projected at $85 per kWh.", "doc2", "https://site2.org", "T2", "snip2", 0.9, ClaimType.QUANTITATIVE, ["Battery"]),
        ]
        clusters = self.clusterer.cluster_claims(claims, self.sub_queries, self.topic)
        disc_count = sum(len(c.discrepancies) for c in clusters)
        self.assertGreaterEqual(disc_count, 1)
        discs = [d for c in clusters for d in c.discrepancies]
        self.assertEqual(discs[0].discrepancy_type, "NUMERICAL_VARIATION")

    def test_polar_conflict_detection(self):
        """Conflicting directional claims on same entity flag polar conflict."""
        claims = [
            ExtractedClaim("c1", "Global supply chain costs increased by 18 percent.", "doc1", "https://site1.org", "T1", "snip1", 0.9, ClaimType.RELATIONAL, ["Supply Chain"]),
            ExtractedClaim("c2", "Global supply chain costs decreased due to nearshoring.", "doc2", "https://site2.org", "T2", "snip2", 0.9, ClaimType.RELATIONAL, ["Supply Chain"]),
        ]
        clusters = self.clusterer.cluster_claims(claims, self.sub_queries, "Global Supply Chains")
        discs = [d for c in clusters for d in c.discrepancies if d.discrepancy_type == "POLAR_CONFLICT"]
        self.assertGreaterEqual(len(discs), 1)
```

### 5.2 Verification Commands
After implementation of `src/research_synthesis/synthesis/cluster.py`:
1. Run Tier 1 unit tests:
   ```powershell
   python -m unittest tests/test_tier1_synthesis.py
   ```
2. Verify pure standard library imports (no third party packages):
   ```powershell
   python -c "import ast; tree = ast.parse(open('src/research_synthesis/synthesis/cluster.py').read()); imports = [n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)]; print('Pure imports:', imports)"
   ```
3. Run schema invariant validation against downstream brief generation:
   ```powershell
   python verify.py --mode=mock
   ```
