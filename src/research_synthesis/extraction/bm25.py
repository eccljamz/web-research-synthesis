"""Okapi BM25 Relevance Scoring and Passage Filtering Module.

Milestone 2 - Feature F7.
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

try:
    from research_synthesis.models import ScoredPassage, SubQuery
except ImportError:
    try:
        from src.research_synthesis.models import ScoredPassage, SubQuery
    except ImportError:
        from ..models import ScoredPassage, SubQuery


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
        min_threshold: Optional[float] = None,
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
            s_min: Absolute baseline score floor (default 0.5).
            min_threshold: Alias for s_min if specified.
            min_passages: Desired minimum passages before fallback engages.
            top_k_fallback: Number of top passages to retain if threshold is too strict.
            topic_weight: Weight assigned to primary topic score in multi-query scoring.
            facet_weight: Weight assigned to best subquery score in multi-query scoring.
        """
        self.k1 = k1
        self.b = b
        self.alpha = alpha
        self.s_min = min_threshold if min_threshold is not None else s_min
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
            if isinstance(sq, SubQuery) or hasattr(sq, "search_query"):
                label = getattr(sq, "facet", "") or getattr(sq, "id", "") or f"sq-{idx:02d}"
                text = getattr(sq, "search_query", "") or getattr(sq, "original_topic", "")
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

    def filter_passages(
        self,
        passages: List[ScoredPassage],
        query: Optional[str] = None,
        topic: Optional[str] = None,
        sub_queries: Optional[List[Union[SubQuery, str]]] = None,
    ) -> List[ScoredPassage]:
        """Ergonomic wrapper around filter, accepting query or topic."""
        search_topic = query if query is not None else (topic or "")
        return self.filter(passages, topic=search_topic, sub_queries=sub_queries)
