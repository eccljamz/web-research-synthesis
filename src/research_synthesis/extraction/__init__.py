"""Content Filtering and Claim Extraction Module.

Milestone 2 - Features F6, F7, F8, F9.
Pure Python Standard Library (3.10+) - Zero External Dependencies.
Exports PassageChunker, OkapiBM25, PureBM25, BM25Filter, SimHash64,
SimHashIndex, TwoStageDeduplicator, ClaimExtractor, and FactualClaimExtractor.
"""

from __future__ import annotations

from .bm25 import BM25Filter, OkapiBM25, PureBM25
from .chunker import PassageChunker
from .claims import ClaimExtractor, FactualClaimExtractor
from .dedup import (
    DeduplicationStats,
    SimHash64,
    SimHashIndex,
    TwoStageDeduplicator,
    canonicalize_url,
    compute_exact_hash,
    normalize_text,
)

__all__ = [
    "PassageChunker",
    "OkapiBM25",
    "PureBM25",
    "BM25Filter",
    "SimHash64",
    "SimHashIndex",
    "TwoStageDeduplicator",
    "DeduplicationStats",
    "ClaimExtractor",
    "FactualClaimExtractor",
    "normalize_text",
    "compute_exact_hash",
    "canonicalize_url",
]
