# Handoff Report: Milestone 2 Features F6 & F7 (Passage Chunking & Okapi BM25 Relevance)

**Agent**: `explorer_m2_1`  
**Working Directory**: `C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\explorer_m2_1`  
**Parent Agent**: `orchestrator_1` (`42364d7e-0273-4faa-be7a-22e0c17eecea`)  
**Scope**: Technical specifications, pure-Python reference implementations, algorithmic contracts, and test verification suite for Milestone 2 Features F6 (`PassageChunker`) and F7 (`OkapiBM25` / `BM25Filter`).

---

## 1. Observation

### 1.1 Requirements Baseline
From `C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\ORIGINAL_REQUEST.md`:
- **R2 (Lines 15–16)**:
  > "The system must filter retrieved content for relevance, deduplicate overlapping information, and extract discrete factual claims and findings."
- **Acceptance Criteria (Lines 26–29)**:
  > "- Pipeline executes end-to-end on at least 3 diverse sample test queries without unhandled exceptions.  
  > - Generated reports contain a formatted executive summary, key findings, and explicit source references for every major claim."

### 1.2 Architectural Inventory & Code Layout
From `C:\Users\ecclj\teamwork_projects\web_research_synthesis\PROJECT.md`:
- **Data Flow (Lines 19–21)**:
  ```
  [3. Document Parser & Cleaner] ─────► List[CleanArticle]
            │
            ▼
  [4. Relevance Filter] ──────────────► List[ScoredPassage] (Okapi BM25 scoring, passage chunking)
  ```
- **Feature Inventory (Lines 50–51)**:
  - **F6**: *Passage-Level Chunking*: Segment cleaned document texts into overlapping passages (150–250 words) to enable granular relevance scoring. (Milestone: M2)
  - **F7**: *Pure-Python Okapi BM25 Relevance Filter*: Lexical relevance ranking against query tokens with term frequency saturation and length normalization; threshold filtering. (Milestone: M2)
- **Assigned Module Paths (Lines 189–192)**:
  - `src/research_synthesis/extraction/chunker.py` (`PassageChunker`)
  - `src/research_synthesis/extraction/bm25.py` (`PureBM25` / `OkapiBM25`, `BM25Filter`)
  - Directory `src/research_synthesis/extraction/` must be created by Worker M2.

### 1.3 Upstream Data Contracts
From `src/research_synthesis/models.py`:
- `CleanArticle`:
  - `doc_id: str`: Deterministic 16-character SHA-256 hash prefix of canonical URL (`DocumentMetadata.doc_id`).
  - `url: str`: Raw/original URL.
  - `metadata: DocumentMetadata`: Includes `canonical_url`, `domain`, `title`, `author`, `published_date`, `word_count`, `character_count`.
  - `cleaned_text: str`: Full continuous text.
  - `paragraphs: List[str]`: Discrete substantive paragraphs extracted by `RobustHTMLParser`.
  - `headings: List[str]`: Document section headers.
  - `subquery_id: Optional[str]`: Associated subquery ID (e.g. `"sq-01"`).
  - `subquery_facet: Optional[str]`: Associated facet (e.g. `"technical"`).
- `ScoredPassage`:
  - `passage_id: str`: Deterministic passage identifier format `{doc_id}-p{idx:03d}`.
  - `doc_id: str`: Provenance pointer to `CleanArticle.doc_id`.
  - `url: str`: Canonical source URL.
  - `title: str`: Article title.
  - `text: str`: Raw text of the passage chunk.
  - `relevance_score: float`: BM25 score (initialized to `0.0` at chunking; populated during BM25 filtering).
  - `subquery: str`: Query or subquery string that matched this passage.
  - `word_count: int`: Exact word count `len(text.split())`.
  - `secondary_urls: List[str]`: Initially `[]` (populated by subsequent deduplication in F8).

### 1.4 Downstream Fixture & Distractor Invariants
From `TEST_INFRA.md` and `tests/fixtures/mock_corpus/manifest.json`:
- **Boundary Fixture**: `tests/fixtures/mock_corpus/microplastics/doc_04_edge_minimal.html` contains only 56 words. The chunker must preserve this short document as a single chunk (`{doc_id}-p000`) without synthetic padding or premature splitting.
- **Distractor Fixture 1**: `tests/fixtures/mock_corpus/solid_state_battery/doc_05_irrelevant_solar.html` discusses tandem perovskite solar cells and must be rejected by `BM25Filter` when scored against the solid-state battery topic and sub-queries.
- **Distractor Fixture 2**: `tests/fixtures/mock_corpus/supply_chain_reshoring/doc_05_irrelevant_crypto.html` discusses cryptocurrency/DeFi and must be rejected by `BM25Filter` when scored against supply chain re-shoring queries.

---

## 2. Logic Chain

### 2.1 Step 1: Passage Chunking Specification (`PassageChunker`)
1. **Paragraph-Aware Boundary Preservation**:
   - Web documents contain logical paragraphs produced by `RobustHTMLParser.paragraphs`. Cutting across paragraphs or slicing sentences produces broken propositions that disrupt factual claim extraction (F9).
   - `PassageChunker` iterates through paragraphs, accumulating text blocks until the window reaches `min_words` (150 words).
   - Paragraphs are preserved intact unless a single paragraph exceeds `max_words` (250 words), in which case sentence-level windowing is applied to that specific paragraph using regular expression sentence segmentation.
2. **Short Document Preservation (< 150 words)**:
   - When the cumulative word count of all paragraphs in a `CleanArticle` is strictly less than 150 words (and $> 0$), the entire document is emitted as a single passage with index `0` (`idx=0`), producing ID `{doc_id}-p000`.
   - Empty documents (0 words or whitespace only) return an empty list `[]` to prevent phantom passages.
3. **Sliding Overlap Windowing (30–50 words)**:
   - When stepping to the next passage, the chunker backtracks by an overlap window of 30–50 words (target 40 words).
   - In paragraph-aware mode, if the last paragraph of chunk $k$ has between 30 and 60 words, chunk $k+1$ starts with that paragraph. If the last paragraph is larger, sentence-level overlap is used to draw the trailing 30–50 words into the beginning of chunk $k+1$.
   - **Progress Invariant**: The window start index must strictly advance by at least one structural unit on each iteration to guarantee termination ($O(N)$ runtime).
4. **Deterministic Passage ID Generation**:
   - Format: `{doc_id}-p{idx:03d}` (e.g. `e3b0c44298fc1c14-p000`, `e3b0c44298fc1c14-p001`).
   - `idx` is 0-indexed per document, zero-padded to 3 decimal digits.
5. **Metadata Propagation**:
   - `doc_id` copied directly from `article.doc_id`.
   - `url` resolved as `article.metadata.canonical_url or article.url`.
   - `title` resolved as `article.metadata.title or ""`.
   - `subquery` resolved as `article.subquery_id or article.subquery_facet or ""`.
   - `word_count` computed via `len(passage_text.split())`.
   - `relevance_score` initialized to `0.0`.
   - `secondary_urls` initialized to `[]`.

### 2.2 Step 2: Okapi BM25 Ranking Formulation (`OkapiBM25`)
1. **Parameter Tuning**:
   - $k_1 = 1.5$: Term frequency saturation parameter controlling the non-linear asymptote of repeated terms.
   - $b = 0.75$: Document length normalization penalty parameter.
2. **Smoothed Robertson-Spärck Jones IDF**:
   $$\text{IDF}(q) = \ln\left(\frac{N - n(q) + 0.5}{n(q) + 0.5} + 1.0\right)$$
   - $N$: Total number of passages in the corpus.
   - $n(q)$: Number of passages containing query token $q$.
   - Adding $+1.0$ inside the natural logarithm guarantees that $\text{IDF}(q) > 0$ for all terms present in the corpus, eliminating negative weights for frequent terms where $n(q) > N/2$.
   - If $n(q) = 0$, $\text{IDF}(q) = 0.0$.
3. **Length Normalization & Term Frequency Weighting**:
   - Let $\text{len}(D)$ be the token count of passage $D$, and $\text{avgdl}$ be the average token length across all passages in the corpus.
   - Normalization factor:
     $$\text{len\_norm}(D) = 1.0 - b + b \cdot \frac{\text{len}(D)}{\text{avgdl}}$$
   - Term frequency component for token $q$ with frequency $f(q, D)$:
     $$\text{TF\_Score}(q, D) = \frac{f(q, D) \cdot (k_1 + 1.0)}{f(q, D) + k_1 \cdot \text{len\_norm}(D)}$$
   - Total BM25 score:
     $$\text{BM25}(Q, D) = \sum_{q \in Q} \text{IDF}(q) \cdot \frac{f(q, D) \cdot (k_1 + 1.0)}{f(q, D) + k_1 \cdot \left(1.0 - b + b \cdot \frac{\text{len}(D)}{\text{avgdl}}\right)}$$
4. **Tokenization and Stopwords**:
   - Case normalization: `text.lower()`.
   - Alphanumeric boundary token extraction: regex `r'\b[a-zA-Z0-9]{2,}\b'`.
   - Stopword filtering: Standard compact 50-word English stopword set. To prevent degeneracies (e.g. query consisting entirely of stopwords), if stopword removal strips all tokens, the tokenizer falls back to retaining all alphanumeric tokens.

### 2.3 Step 3: Multi-Query Scoring Architecture
1. **Primary Topic vs. Sub-Query Facets**:
   - In complex research synthesis, a broad user topic (e.g., *"Next-Generation Solid-State Battery Commercialization"*) is decomposed into 3–5 targeted sub-queries (e.g., *"solid electrolyte materials ionic conductivity"*).
   - Individual passages may address a specific technical facet deeply while only referencing the general topic in passing.
2. **Multi-Query Formulation**:
   - For passage $D$, compute BM25 score against the primary topic: $s_{\text{topic}} = \text{BM25}(Q_{\text{topic}}, D)$.
   - For each decomposed sub-query $SQ_j \in \{SQ_1, \dots, SQ_M\}$, compute $s_{sq_j} = \text{BM25}(SQ_j, D)$.
   - Determine the highest-matching sub-query facet:
     $$s_{\text{best\_facet}} = \max_{j} s_{sq_j}, \quad SQ_{\text{best}} = \arg\max_{j} s_{sq_j}$$
   - Combined multi-query score:
     $$S_{\text{multi}}(D) = w_{\text{topic}} \cdot s_{\text{topic}} + w_{\text{facet}} \cdot s_{\text{best\_facet}}$$
     Default calibrated weights: $w_{\text{topic}} = 0.4$, $w_{\text{facet}} = 0.6$. (If no sub-queries are supplied, $w_{\text{topic}} = 1.0$).
   - The winning facet identifier or query string is updated onto `passage.subquery = SQ_{\text{best}}` for downstream thematic grouping.

### 2.4 Step 4: Calibrated Relative Thresholding & Top-$K$ Fallback
1. **Relative Cutoff Formula**:
   $$\tau = \max(s_{min}, \alpha \cdot s_{max})$$
   - $s_{max} = \max_{D \in \text{corpus}} S_{\text{multi}}(D)$: Highest passage score in the corpus.
   - $\alpha$: Relative cutoff ratio (default $\alpha = 0.25$).
   - $s_{min}$: Absolute baseline score floor (default $s_{min} = 0.5$).
2. **Filtering Condition**:
   - A passage is retained if $S_{\text{multi}}(D) \ge \tau$.
3. **Safety Fallback to Top-$K$**:
   - If the relative threshold $\tau$ is too stringent (e.g. fewer than `min_passages` survive, default `min_passages = 3`), the filter falls back to selecting the top-$K$ scoring passages (default `top_k_fallback = 5`) that have strictly non-zero scores ($S_{\text{multi}}(D) > 0.0$).
   - If all passages in the corpus have score $0.0$ (complete absence of query terms, e.g. unrelated distractor corpus), the filter safely returns `[]` without raising exceptions.

---

## 3. Caveats

1. **Vocabulary Mismatch without Semantic Embeddings**:
   - Pure-Python BM25 relies on exact lexical token matching. If a document discusses *"accumulators"* instead of *"batteries"*, BM25 alone would miss it unless the query decomposition engine (F1) expands synonyms in the sub-queries. The multi-query scoring mechanism mitigates this by aggregating 4–5 distinct sub-queries with expanded vocabulary.
2. **Corpus Size Sensitivity on IDF**:
   - In small corpora (e.g., $N = 5$ documents yielding ~15 passages), a term appearing in 1 passage receives higher IDF than one appearing in 10. The Robertson-Spärck Jones smoothing $+1.0$ prevents negative IDF, but relative thresholding must have an absolute floor ($s_{min} = 0.5$) so common single-term matches in off-topic articles cannot pass.
3. **Subquery Input Formats**:
   - `sub_queries` passed into `BM25Filter.filter` may be a list of `SubQuery` dataclass instances, a list of raw strings, or empty. The implementation must defensively unpack both strings and objects (`getattr(sq, 'search_query', str(sq))`).
4. **Single Large Paragraphs (>250 words)**:
   - When source HTML lacks `<p>` tags (e.g. monolithic `<div>` or `<pre>`), paragraphs may contain 500+ words. The chunker must split long paragraphs along sentence boundaries (`[.!?]\s+`) rather than emitting oversized chunks.

---

## 4. Conclusion

### 4.1 Concrete Specification for `src/research_synthesis/extraction/chunker.py`

```python
"""Passage-Level Chunking Module.

Pure Python Standard Library (3.10+) - Zero External Dependencies.
Segments cleaned document texts (CleanArticle) into overlapping passages
(150-250 words) with 30-50 word overlap, respecting paragraph boundaries.
"""

from __future__ import annotations

import re
from typing import List, Optional, Union

from src.research_synthesis.models import CleanArticle, RetrievalBatch, ScoredPassage


class PassageChunker:
    """Paragraph-aware passage chunker for CleanArticle documents.

    Targets 150-250 words per passage with 30-50 word overlap.
    Preserves short documents (<150 words) as single chunks.
    Generates deterministic passage IDs: {doc_id}-p{idx:03d}.
    """

    SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")

    def __init__(
        self,
        min_words: int = 150,
        max_words: int = 250,
        overlap_words: int = 40,
    ) -> None:
        """Initialize chunker with configurable word boundary targets.

        Args:
            min_words: Minimum target words per passage (default: 150).
            max_words: Maximum target words per passage (default: 250).
            overlap_words: Target word overlap between consecutive passages (default: 40).
        """
        self.min_words = min_words
        self.max_words = max_words
        self.overlap_words = overlap_words

    @classmethod
    def _split_into_sentences(cls, text: str) -> List[str]:
        """Split text into sentences while protecting common abbreviations."""
        if not text.strip():
            return []
        # Protect common abbreviations
        protected = re.sub(
            r"\b(e\.g\.|i\.e\.|U\.S\.|Dr\.|Mr\.|Ms\.|Inc\.|Corp\.|Ltd\.|vs\.)",
            lambda m: m.group(0).replace(".", "<DOT>"),
            text,
        )
        raw_sentences = cls.SENTENCE_SPLIT_PATTERN.split(protected)
        cleaned = [s.replace("<DOT>", ".").strip() for s in raw_sentences if s.strip()]
        return cleaned if cleaned else [text.strip()]

    def _split_long_paragraph(self, paragraph: str) -> List[str]:
        """Break down paragraphs exceeding max_words into sentence-level blocks."""
        words = paragraph.split()
        if len(words) <= self.max_words:
            return [paragraph]

        sentences = self._split_into_sentences(paragraph)
        blocks: List[str] = []
        current_block: List[str] = []
        current_count = 0

        for sent in sentences:
            sent_count = len(sent.split())
            if current_count + sent_count > self.max_words and current_block:
                blocks.append(" ".join(current_block))
                current_block = [sent]
                current_count = sent_count
            else:
                current_block.append(sent)
                current_count += sent_count

        if current_block:
            blocks.append(" ".join(current_block))
        return blocks

    def chunk_article(self, article: CleanArticle) -> List[ScoredPassage]:
        """Segment a CleanArticle into a list of ScoredPassage instances.

        Args:
            article: The clean article to segment.

        Returns:
            List of ScoredPassage instances with deterministic IDs and metadata.
        """
        # Retrieve candidate paragraphs
        paragraphs = [p.strip() for p in article.paragraphs if p.strip()]
        if not paragraphs and article.cleaned_text.strip():
            paragraphs = [p.strip() for p in article.cleaned_text.split("\n\n") if p.strip()]

        if not paragraphs:
            return []

        # Total word count across document
        total_words = sum(len(p.split()) for p in paragraphs)
        if total_words == 0:
            return []

        doc_url = article.metadata.canonical_url or article.url
        doc_title = article.metadata.title or ""
        subquery_ref = article.subquery_id or article.subquery_facet or ""

        # Short document rule: preserve as single chunk if < min_words
        if total_words < self.min_words:
            full_text = "\n\n".join(paragraphs)
            return [
                ScoredPassage(
                    passage_id=f"{article.doc_id}-p000",
                    doc_id=article.doc_id,
                    url=doc_url,
                    title=doc_title,
                    text=full_text,
                    relevance_score=0.0,
                    subquery=subquery_ref,
                    word_count=len(full_text.split()),
                    secondary_urls=[],
                )
            ]

        # Break any individual paragraphs larger than max_words into atomic units
        atomic_blocks: List[str] = []
        for p in paragraphs:
            atomic_blocks.extend(self._split_long_paragraph(p))

        # Sliding window accumulator over atomic blocks
        passages: List[ScoredPassage] = []
        start_idx = 0
        n_blocks = len(atomic_blocks)
        passage_index = 0

        while start_idx < n_blocks:
            current_window: List[str] = []
            current_words = 0
            end_idx = start_idx

            while end_idx < n_blocks:
                block = atomic_blocks[end_idx]
                block_words = len(block.split())

                if current_words + block_words > self.max_words and current_words >= self.min_words:
                    break

                current_window.append(block)
                current_words += block_words
                end_idx += 1

                if current_words >= self.max_words:
                    break

            if not current_window:
                current_window.append(atomic_blocks[start_idx])
                current_words = len(atomic_blocks[start_idx].split())
                end_idx = start_idx + 1

            passage_text = "\n\n".join(current_window)
            passages.append(
                ScoredPassage(
                    passage_id=f"{article.doc_id}-p{passage_index:03d}",
                    doc_id=article.doc_id,
                    url=doc_url,
                    title=doc_title,
                    text=passage_text,
                    relevance_score=0.0,
                    subquery=subquery_ref,
                    word_count=len(passage_text.split()),
                    secondary_urls=[],
                )
            )
            passage_index += 1

            if end_idx >= n_blocks:
                break

            # Calculate overlap starting point: backtrack ~overlap_words from end_idx
            overlap_accum = 0
            overlap_start = end_idx
            for k in range(end_idx - 1, start_idx, -1):
                overlap_accum += len(atomic_blocks[k].split())
                if overlap_accum >= self.overlap_words:
                    overlap_start = k
                    break

            # Strictly advance start_idx by at least 1 to guarantee termination
            start_idx = max(start_idx + 1, overlap_start)

        return passages

    def chunk_batch(
        self,
        batch: Union[RetrievalBatch, List[CleanArticle]],
    ) -> List[ScoredPassage]:
        """Chunk a batch or collection of CleanArticles into ScoredPassages.

        Args:
            batch: RetrievalBatch or List of CleanArticle objects.

        Returns:
            Flat list of all ScoredPassages across all documents.
        """
        articles = batch.documents if isinstance(batch, RetrievalBatch) else batch
        all_passages: List[ScoredPassage] = []
        for art in articles:
            all_passages.extend(self.chunk_article(art))
        return all_passages
```

---

### 4.2 Concrete Specification for `src/research_synthesis/extraction/bm25.py`

```python
"""Okapi BM25 Relevance Scoring and Passage Filtering Module.

Pure Python Standard Library (3.10+) - Zero External Dependencies.
Implements:
1. OkapiBM25 / PureBM25: Robertson-Spärck Jones smoothed IDF + length-normalized ranking.
2. BM25Filter: Multi-query score aggregator and relative threshold filter with top-K fallback.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from src.research_synthesis.models import ScoredPassage, SubQuery


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
    "with", "would", "you", "your", "yours", "yourself", "yourselves",
}


class OkapiBM25:
    """Pure-Python standard library implementation of Okapi BM25 ranking."""

    TOKEN_PATTERN = re.compile(r"\b[a-zA-Z0-9]{2,}\b")

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        """Initialize BM25 model parameters.

        Args:
            k1: Term frequency saturation tuning parameter (default: 1.5).
            b: Document length normalization tuning parameter (default: 0.75).
        """
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avg_doc_len = 0.0
        self.doc_freqs: Counter[str] = Counter()
        self.idf: Dict[str, float] = {}

    @classmethod
    def tokenize(cls, text: str, filter_stopwords: bool = True) -> List[str]:
        """Extract alphanumeric tokens (length >= 2) with optional stopword filtering."""
        if not text:
            return []
        raw_tokens = [w.lower() for w in cls.TOKEN_PATTERN.findall(text)]
        if not filter_stopwords:
            return raw_tokens

        filtered = [w for w in raw_tokens if w not in STOPWORDS]
        # Fall back to raw tokens if all tokens were stopwords
        return filtered if filtered else raw_tokens

    def fit(self, corpus_tokens: List[List[str]]) -> OkapiBM25:
        """Fit BM25 statistics (corpus_size, avg_doc_len, doc_freqs, idf) on tokenized corpus.

        Args:
            corpus_tokens: List of tokenized documents/passages.

        Returns:
            self for method chaining.
        """
        self.corpus_size = len(corpus_tokens)
        self.doc_freqs.clear()
        self.idf.clear()

        if self.corpus_size == 0:
            self.avg_doc_len = 0.0
            return self

        total_length = sum(len(doc) for doc in corpus_tokens)
        self.avg_doc_len = total_length / self.corpus_size if self.corpus_size > 0 else 0.0

        for doc in corpus_tokens:
            for term in set(doc):
                self.doc_freqs[term] += 1

        # Smoothed Robertson-Spärck Jones IDF: ln((N - n + 0.5) / (n + 0.5) + 1.0)
        for term, freq in self.doc_freqs.items():
            smoothed_ratio = (self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0
            self.idf[term] = math.log(smoothed_ratio)

        return self

    def score(self, query_tokens: List[str], doc_tokens: List[str]) -> float:
        """Calculate Okapi BM25 score for a single document against query tokens.

        Args:
            query_tokens: List of query tokens.
            doc_tokens: List of document tokens.

        Returns:
            BM25 relevance score (non-negative float).
        """
        if not query_tokens or not doc_tokens or self.corpus_size == 0 or self.avg_doc_len == 0.0:
            return 0.0

        doc_len = len(doc_tokens)
        len_norm = 1.0 - self.b + self.b * (doc_len / self.avg_doc_len)
        if len_norm <= 0:
            return 0.0

        term_counts = Counter(doc_tokens)
        score = 0.0

        for q in query_tokens:
            if q not in self.idf:
                continue
            tf = term_counts[q]
            if tf <= 0:
                continue

            numerator = tf * (self.k1 + 1.0)
            denominator = tf + self.k1 * len_norm
            score += self.idf[q] * (numerator / denominator)

        return max(0.0, score)

    def score_batch(
        self,
        query_tokens: List[str],
        corpus_tokens: List[List[str]],
    ) -> List[float]:
        """Compute BM25 scores for all documents in a corpus against query tokens."""
        return [self.score(query_tokens, doc) for doc in corpus_tokens]


# Alias PureBM25 for backward compatibility with project references
PureBM25 = OkapiBM25


class BM25Filter:
    """Filters ScoredPassage collections using multi-query BM25 scoring and relative thresholding."""

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        alpha: float = 0.25,
        s_min: float = 0.5,
        min_passages: int = 3,
        top_k_fallback: int = 5,
        topic_weight: float = 0.4,
        facet_weight: float = 0.6,
    ) -> None:
        """Initialize filter configuration.

        Args:
            k1: BM25 k1 parameter.
            b: BM25 b parameter.
            alpha: Relative threshold cutoff factor (tau = max(s_min, alpha * s_max)).
            s_min: Absolute baseline score floor.
            min_passages: Desired minimum passages before fallback engages.
            top_k_fallback: Number of top passages to retain if threshold is too strict.
            topic_weight: Weight assigned to primary topic score in multi-query scoring.
            facet_weight: Weight assigned to best subquery score in multi-query scoring.
        """
        self.k1 = k1
        self.b = b
        self.alpha = alpha
        self.s_min = s_min
        self.min_passages = min_passages
        self.top_k_fallback = top_k_fallback
        self.topic_weight = topic_weight
        self.facet_weight = facet_weight
        self.bm25 = OkapiBM25(k1=k1, b=b)

    def _extract_query_strings(
        self,
        sub_queries: Optional[List[Union[SubQuery, str]]],
    ) -> List[Tuple[str, str]]:
        """Normalize sub-queries into list of (query_id_or_label, search_text) tuples."""
        if not sub_queries:
            return []
        extracted: List[Tuple[str, str]] = []
        for idx, sq in enumerate(sub_queries):
            if isinstance(sq, SubQuery):
                label = sq.facet or sq.id or f"sq-{idx:02d}"
                text = sq.search_query or sq.original_topic
            elif isinstance(sq, str):
                label = f"sq-{idx:02d}"
                text = sq
            else:
                label = f"sq-{idx:02d}"
                text = str(sq)
            extracted.append((label, text))
        return extracted

    def filter(
        self,
        passages: List[ScoredPassage],
        topic: str,
        sub_queries: Optional[List[Union[SubQuery, str]]] = None,
    ) -> List[ScoredPassage]:
        """Score passages across primary topic and subqueries, and filter by relative threshold.

        Args:
            passages: Candidate ScoredPassage list from PassageChunker.
            topic: Broad canonical research topic string.
            sub_queries: List of decomposed sub-queries or query strings.

        Returns:
            Filtered list of ScoredPassage instances with updated relevance_score and
            subquery fields, ordered by descending relevance_score.
        """
        if not passages:
            return []

        # Tokenize corpus passages
        tokenized_corpus = [OkapiBM25.tokenize(p.text) for p in passages]
        self.bm25.fit(tokenized_corpus)

        # Tokenize topic query
        topic_tokens = OkapiBM25.tokenize(topic)
        topic_scores = self.bm25.score_batch(topic_tokens, tokenized_corpus)

        # Tokenize and score subqueries
        normalized_subqueries = self._extract_query_strings(sub_queries)
        subquery_score_matrices: List[Tuple[str, str, List[float]]] = []
        for label, sq_text in normalized_subqueries:
            sq_tokens = OkapiBM25.tokenize(sq_text)
            scores = self.bm25.score_batch(sq_tokens, tokenized_corpus)
            subquery_score_matrices.append((label, sq_text, scores))

        # Compute multi-query composite scores for each passage
        scored_candidates: List[Tuple[float, str, ScoredPassage]] = []
        for i, passage in enumerate(passages):
            s_top = topic_scores[i]
            best_facet_score = 0.0
            best_facet_name = passage.subquery or topic

            for label, sq_text, scores in subquery_score_matrices:
                if scores[i] > best_facet_score:
                    best_facet_score = scores[i]
                    best_facet_name = sq_text

            if subquery_score_matrices:
                combined_score = self.topic_weight * s_top + self.facet_weight * best_facet_score
            else:
                combined_score = s_top

            scored_candidates.append((combined_score, best_facet_name, passage))

        # Determine maximum score
        s_max = max((sc[0] for sc in scored_candidates), default=0.0)
        tau = max(self.s_min, self.alpha * s_max)

        # Apply threshold filtering
        retained: List[ScoredPassage] = []
        for final_score, facet_name, passage in scored_candidates:
            if final_score >= tau and final_score > 0.0:
                passage.relevance_score = round(final_score, 4)
                if facet_name:
                    passage.subquery = facet_name
                retained.append(passage)

        # Fallback to top-K if threshold is too strict
        if len(retained) < self.min_passages:
            # Sort all non-zero candidates by score descending
            non_zero_candidates = [
                (final_score, facet_name, passage)
                for final_score, facet_name, passage in scored_candidates
                if final_score > 0.0
            ]
            non_zero_candidates.sort(key=lambda x: x[0], reverse=True)

            fallback_passages: List[ScoredPassage] = []
            for final_score, facet_name, passage in non_zero_candidates[: self.top_k_fallback]:
                passage.relevance_score = round(final_score, 4)
                if facet_name:
                    passage.subquery = facet_name
                fallback_passages.append(passage)
            retained = fallback_passages

        # Sort final output descending by relevance_score
        retained.sort(key=lambda p: p.relevance_score, reverse=True)
        return retained
```

---

### 4.3 End-to-End Pipeline Integration Example

```python
# Upstream: CleanArticle list produced by DocumentParser / RetrievalClient
clean_articles: List[CleanArticle] = retrieval_batch.documents

# Step 1: Passage Chunking (F6)
chunker = PassageChunker(min_words=150, max_words=250, overlap_words=40)
raw_passages: List[ScoredPassage] = chunker.chunk_batch(clean_articles)

# Step 2: Okapi BM25 Filtering & Multi-Query Scoring (F7)
bm25_filter = BM25Filter(
    k1=1.5,
    b=0.75,
    alpha=0.25,
    s_min=0.5,
    min_passages=3,
    top_k_fallback=5,
    topic_weight=0.4,
    facet_weight=0.6,
)
relevant_passages: List[ScoredPassage] = bm25_filter.filter(
    passages=raw_passages,
    topic=retrieval_batch.topic,
    sub_queries=retrieval_batch.sub_queries,
)

# Downstream: relevant_passages passed to DeduplicationEngine (F8) and ClaimExtractor (F9)
```

---

## 5. Verification Method

### 5.1 Verification Matrix for Implementation Agent (Worker M2)

| Test Category | Target / Requirement | Verification Assertion | Invalidation Condition |
|---|---|---|---|
| **Short Doc Preservation** | `PassageChunker` | Document with 56 words (`doc_04_edge_minimal.html`) produces exactly 1 `ScoredPassage` with ID `{doc_id}-p000`. | Splitting into multiple passages or empty passage returned. |
| **Word Budget & Overlap** | `PassageChunker` | In multi-paragraph doc of 600 words, chunks have 150–250 words and consecutive chunks share 30–50 words of overlap text. | Passages $< 150$ words (unless short doc) or $> 280$ words; 0 overlap. |
| **Deterministic ID** | `PassageChunker` | Every generated passage matches regex `^[a-f0-9]{16}-p\d{3}$`. | Missing padding (`-p0` instead of `-p000`) or non-deterministic IDs. |
| **Metadata Propagation** | `PassageChunker` | `ScoredPassage.url == article.metadata.canonical_url`, `title == article.metadata.title`, `word_count == len(text.split())`. | Missing metadata or mismatching word count. |
| **Mathematical IDF** | `OkapiBM25` | For $N=3, n=1$, smoothed IDF equals $\ln(2.6667) \approx 0.98083$. For $n=2$, IDF equals $\ln(1.6) \approx 0.47000$. | Non-smoothed formula yielding negative IDF or IDF $\le 0$. |
| **Length Normalization** | `OkapiBM25` | Document shorter than `avgdl` has `len_norm < 1.0` (boosted TF); longer document has `len_norm > 1.0` (dampened TF). | Incorrect denominator causing zero division or reverse scaling. |
| **Distractor Rejection** | `BM25Filter` | `doc_05_irrelevant_solar.html` scores 0.0 against solid-state battery topic and is filtered out by $\tau = \max(s_{min}, \alpha \cdot s_{max})$. | Solar passage passes filter and appears in output brief. |
| **Top-K Fallback** | `BM25Filter` | When high threshold $\tau > s_{max}$ would reject all items, filter falls back to top-3 non-zero items. | Empty list returned when relevant passages exist. |
| **Empty Input Safety** | `BM25Filter` | Empty passage list or empty queries return `[]` without `ZeroDivisionError` or exceptions. | Unhandled exception on empty corpus. |

### 5.2 Mathematical Verification Vectors for Unit Tests

Given corpus of 3 passages:
- $D_1$: `"solid state battery electrolytes"` (length = 4)
- $D_2$: `"solid electrolyte materials ionic conductivity"` (length = 5)
- $D_3$: `"solar photovoltaic cell panel"` (length = 4)

Parameters: $N = 3$, $k_1 = 1.5$, $b = 0.75$, $\text{avgdl} = 13 / 3 \approx 4.3333$.
1. **Term Frequencies & IDFs**:
   - $\text{"solid"}$: $n = 2 \implies \text{IDF} = \ln\left(\frac{3 - 2 + 0.5}{2 + 0.5} + 1.0\right) = \ln(1.6) \approx 0.470003$
   - $\text{"battery"}$: $n = 1 \implies \text{IDF} = \ln\left(\frac{3 - 1 + 0.5}{1 + 0.5} + 1.0\right) = \ln(2.6667) \approx 0.980829$
   - $\text{"solar"}$: $n = 1 \implies \text{IDF} = \ln(2.6667) \approx 0.980829$
2. **Length Normalization for $D_1$ ($\text{len}=4$)**:
   $$\text{len\_norm}(D_1) = 0.25 + 0.75 \times \frac{4}{4.3333} = 0.25 + 0.692308 = 0.942308$$
3. **Score of $D_1$ against query `"solid battery"`**:
   $$\text{TF\_contrib}(\text{"solid"}) = \frac{1 \times 2.5}{1 + 1.5 \times 0.942308} = \frac{2.5}{2.41346} \approx 1.035858$$
   $$\text{Score}(\text{"solid"}) = 0.470003 \times 1.035858 \approx 0.486856$$
   $$\text{TF\_contrib}(\text{"battery"}) = 1.035858$$
   $$\text{Score}(\text{"battery"}) = 0.980829 \times 1.035858 \approx 1.015998$$
   $$\text{Total BM25}(D_1) = 0.486856 + 1.015998 = 1.502854$$
4. **Score of $D_3$ against `"solid battery"`**:
   $$\text{Total BM25}(D_3) = 0.0$$
5. **Threshold Verification**:
   - $s_{max} = 1.502854$, $\alpha = 0.25$, $s_{min} = 0.5$.
   - $\tau = \max(0.5, 0.25 \times 1.502854) = \max(0.5, 0.375713) = 0.5$.
   - $D_1$ score $1.502854 \ge 0.5 \implies \text{RETAINED}$.
   - $D_3$ score $0.0 < 0.5 \implies \text{FILTERED (REJECTED)}$.

### 5.3 Test Suite Specification for `tests/test_tier1_extraction.py`
The implementation worker must include the following test cases in `tests/test_tier1_extraction.py`:
1. `test_passage_chunker_short_document_preservation`: Asserts document $<150$ words yields 1 passage with `-p000`.
2. `test_passage_chunker_word_boundary_and_overlap`: Asserts passages fall within word count limits and adjacent chunks have non-empty word overlap.
3. `test_passage_chunker_metadata_propagation`: Asserts `doc_id`, `url`, `title`, and `word_count` match `ScoredPassage`.
4. `test_passage_chunker_empty_article`: Asserts empty text returns `[]`.
5. `test_okapi_bm25_smoothed_idf_positive`: Asserts IDF is strictly positive for all terms, including terms with $n = N$.
6. `test_okapi_bm25_length_normalization`: Asserts short doc scores higher than identical long doc with same term count.
7. `test_bm25_filter_distractor_elimination`: Asserts solar distractor document is rejected when topic is battery.
8. `test_bm25_filter_fallback_to_top_k`: Asserts fallback activates when threshold is high.
9. `test_bm25_filter_multi_query_scoring`: Asserts passages matching specific subqueries receive boost from $w_{\text{facet}}$.
10. `test_bm25_filter_zero_division_safety`: Asserts empty corpus or empty queries execute safely with zero errors.
