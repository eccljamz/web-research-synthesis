"""Two-Stage Deduplication Engine.

Milestone 2 - Feature F8.
Pure Python Standard Library (3.10+) - Zero External Dependencies.
Combines Stage 1 exact content/URL hashing with Stage 2 64-bit SimHash
locality-sensitive fingerprinting (Hamming distance <= 3) and inverted
index bucket clustering. Preserves multi-source attribution via secondary_urls.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union
from urllib.parse import parse_qsl, urlencode, urlparse

try:
    from research_synthesis.models import ExtractedClaim, ScoredPassage
except ImportError:
    try:
        from src.research_synthesis.models import ExtractedClaim, ScoredPassage
    except ImportError:
        from ..models import ExtractedClaim, ScoredPassage

logger = logging.getLogger(__name__)


# ============================================================================
# Text and URL Normalization Utilities
# ============================================================================

def normalize_text(text: Optional[str]) -> str:
    """Normalize text for exact content hashing.

    Performs Unicode NFKC normalization, lowercasing, punctuation stripping,
    and collapsing of whitespace sequences.

    Args:
        text: Raw text string to normalize.

    Returns:
        Clean normalized text string. Returns empty string if input is None or blank.
    """
    if not text:
        return ""
    # 1. Unicode NFKC normalization
    norm = unicodedata.normalize("NFKC", str(text)).lower()
    # 2. Normalize canonical metric symbols before punctuation stripping
    norm = re.sub(r"%", " percent ", norm)
    norm = re.sub(r"\bkilowatt[-\s]*hours?\b", "kwh", norm)
    # 3. Strip punctuation and symbols
    norm = re.sub(r"[^\w\s]|_", "", norm)
    # 4. Collapse all whitespace sequences to a single space
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


def compute_exact_hash(text: str) -> str:
    """Compute deterministic SHA-256 hex digest of normalized text.

    Args:
        text: Text to hash.

    Returns:
        64-character SHA-256 hexadecimal digest string.
    """
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonicalize_url(url: Optional[str]) -> str:
    """Normalize and canonicalize a URL.

    Strips tracking query parameters (utm_*, ref, etc.), fragments,
    standardizes scheme and netloc to lowercase, removes default ports,
    and normalizes paths.

    Args:
        url: Raw URL string.

    Returns:
        Canonical URL string. Returns empty string if invalid or empty.
    """
    if not url:
        return ""
    url_str = url.strip()
    if not url_str:
        return ""

    try:
        parsed = urlparse(url_str)
    except Exception:
        return url_str

    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()

    # Strip standard default ports
    if ":" in netloc:
        parts = netloc.split(":", 1)
        host = parts[0]
        port = parts[1]
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    path = parsed.path or "/"
    # Collapse double slashes
    path = re.sub(r"/+", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Strip marketing & analytics tracking parameters
    tracking_keys = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "ref", "referrer", "fbclid", "gclid", "_ga", "mc_cid", "mc_eid"
    }
    query_str = ""
    if parsed.query:
        params = parse_qsl(parsed.query, keep_blank_values=False)
        filtered = sorted([(k, v) for k, v in params if k.lower() not in tracking_keys])
        if filtered:
            query_str = f"?{urlencode(filtered)}"

    return f"{scheme}://{netloc}{path}{query_str}"


# ============================================================================
# 64-Bit SimHash Algorithm (Charikar's Locality-Sensitive Hash)
# ============================================================================

class SimHash64:
    """64-bit Locality-Sensitive Hashing via Charikar's SimHash algorithm."""

    @classmethod
    def tokenize(cls, text: str, shingle_size: int = 3) -> List[str]:
        """Tokenize normalized text into hybrid word unigrams and character shingles for robust similarity.

        Args:
            text: Text to shingle.
            shingle_size: Number of words per shingle (default 3).

        Returns:
            List of token strings.
        """
        if not text:
            return []
        norm = unicodedata.normalize("NFKC", str(text)).lower()
        norm = re.sub(r"%", " percent ", norm)
        norm = re.sub(r"\bkilowatt[-\s]*hours?\b", "kwh", norm)
        sim_norm = re.sub(r"-+", " ", norm)
        sim_norm = re.sub(r"[^\w\s]|_", "", sim_norm)
        words = re.sub(r"\s+", " ", sim_norm).strip().split()
        if not words:
            return []
        toks = list(words)
        for w in words:
            if len(w) >= 3:
                toks.extend([w[i : i + 3] for i in range(len(w) - 2)])
        return toks

    @staticmethod
    def _hash_token_64(token: str) -> int:
        """Compute a 64-bit unsigned integer hash for a token using MD5 with seed."""
        digest = hashlib.md5(f"139:{token}".encode("utf-8")).digest()
        return int.from_bytes(digest[4:12], byteorder="big", signed=False)

    @classmethod
    def compute_from_tokens(cls, tokens: Sequence[str]) -> int:
        """Compute 64-bit integer SimHash fingerprint directly from token sequence."""
        if not tokens:
            return 0

        v = [0] * 64
        token_weights = Counter(tokens)

        for token, weight in token_weights.items():
            h = cls._hash_token_64(token)
            for i in range(64):
                bit = (h >> i) & 1
                if bit:
                    v[i] += weight
                else:
                    v[i] -= weight

        fingerprint = 0
        for i in range(64):
            if v[i] > 0:
                fingerprint |= (1 << i)

        return fingerprint

    @classmethod
    def compute_simhash(cls, text: str, shingle_size: int = 3) -> int:
        """Compute a 64-bit integer SimHash fingerprint for the provided text.

        Args:
            text: Input text string.
            shingle_size: Shingle length in words.

        Returns:
            64-bit unsigned integer in [0, 2^64 - 1]. Returns 0 if text is empty.
        """
        tokens = cls.tokenize(text, shingle_size=shingle_size)
        return cls.compute_from_tokens(tokens)

    @classmethod
    def compute(
        cls,
        text_or_tokens: Union[str, Sequence[str]],
        shingle_size: int = 3,
    ) -> int:
        """Ergonomic dispatcher: compute SimHash from either raw text string or token sequence."""
        if isinstance(text_or_tokens, str):
            return cls.compute_simhash(text_or_tokens, shingle_size=shingle_size)
        return cls.compute_from_tokens(text_or_tokens)

    @staticmethod
    def hamming_distance(fp1: int, fp2: int) -> int:
        """Calculate bitwise Hamming distance between two 64-bit fingerprints.

        Uses bitwise XOR and int.bit_count() (POPCNT instruction).

        Args:
            fp1: First 64-bit integer fingerprint.
            fp2: Second 64-bit integer fingerprint.

        Returns:
            Hamming distance as integer in [0, 64].
        """
        return (fp1 ^ fp2).bit_count()


# ============================================================================
# Inverted SimHash Index / 4-Bucket Clustering
# ============================================================================

@dataclass
class _IndexEntry:
    item_id: str
    fingerprint: int
    metadata: Any


class SimHashIndex:
    """Inverted SimHash Index utilizing 4-table bucket clustering.

    Partitions 64-bit fingerprints into 4 blocks of 16 bits. By the Pigeonhole
    Principle, any two fingerprints with Hamming distance <= 3 are guaranteed
    to match on at least one 16-bit block, ensuring O(1) average lookup and
    zero false negatives.
    """

    def __init__(self, threshold: int = 3) -> None:
        self.threshold = threshold
        # 4 hash tables corresponding to the four 16-bit blocks
        self.tables: List[Dict[int, List[_IndexEntry]]] = [{} for _ in range(4)]
        self._items: Dict[str, _IndexEntry] = {}

    def _get_block_keys(self, fingerprint: int) -> List[int]:
        """Extract four 16-bit block keys from 64-bit fingerprint."""
        return [(fingerprint >> (16 * i)) & 0xFFFF for i in range(4)]

    def add(self, item_id: str, fingerprint: int, metadata: Any = None) -> None:
        """Insert an item fingerprint and metadata into the index.

        Args:
            item_id: Unique string identifier.
            fingerprint: 64-bit integer SimHash.
            metadata: Associated payload (e.g. ScoredPassage or ExtractedClaim).
        """
        entry = _IndexEntry(item_id=item_id, fingerprint=fingerprint, metadata=metadata)
        self._items[item_id] = entry
        keys = self._get_block_keys(fingerprint)
        for i, key in enumerate(keys):
            self.tables[i].setdefault(key, []).append(entry)

    def find_near_duplicates(
        self, fingerprint: int, threshold: Optional[int] = None
    ) -> List[Tuple[str, int, Any]]:
        """Find all indexed items with Hamming distance <= threshold.

        Args:
            fingerprint: 64-bit fingerprint to search.
            threshold: Hamming distance threshold (defaults to self.threshold).

        Returns:
            List of tuples: (item_id, hamming_distance, metadata) sorted by distance.
        """
        t = self.threshold if threshold is None else threshold
        keys = self._get_block_keys(fingerprint)
        candidates: Dict[str, _IndexEntry] = {}

        # Query all 4 bucket tables, deduplicating candidate entries by item_id
        for i, key in enumerate(keys):
            if key in self.tables[i]:
                for entry in self.tables[i][key]:
                    candidates[entry.item_id] = entry

        # Compute exact Hamming distance for candidates
        results: List[Tuple[str, int, Any]] = []
        for cand in candidates.values():
            dist = SimHash64.hamming_distance(fingerprint, cand.fingerprint)
            if dist <= t:
                results.append((cand.item_id, dist, cand.metadata))

        results.sort(key=lambda x: (x[1], x[0]))
        return results

    def clear(self) -> None:
        """Clear all entries from index."""
        self.tables = [{} for _ in range(4)]
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


# ============================================================================
# Two-Stage Deduplication Engine
# ============================================================================

@dataclass
class DeduplicationStats:
    """Execution telemetry for a deduplication run."""
    total_input: int = 0
    exact_duplicates_pruned: int = 0
    near_duplicates_pruned: int = 0
    unique_retained: int = 0
    attributions_merged: int = 0


class TwoStageDeduplicator:
    """Two-Stage Deduplication Engine for passages and factual claims.

    Stage 1: Exact text hashing (SHA-256 of normalized text) and canonical URL matching.
    Stage 2: Near-duplicate detection via 64-bit SimHash (Hamming distance <= 3)
             using 4-bucket inverted indexing.

    Preserves attribution by appending secondary URLs into secondary_urls,
    updating maximum relevance/confidence scores.
    """

    def __init__(
        self,
        hamming_threshold: int = 3,
        shingle_size: int = 3,
        include_title_annotation: bool = False,
    ) -> None:
        """Initialize deduplicator with calibrated hyperparameters.

        Args:
            hamming_threshold: Maximum Hamming distance for near-duplicates (default 3).
            shingle_size: Word n-gram length for SimHash (default 3).
            include_title_annotation: If True, format secondary_urls entries as
                                      'URL (Title)'. If False, store clean canonical URL.
        """
        self.hamming_threshold = hamming_threshold
        self.shingle_size = shingle_size
        self.include_title_annotation = include_title_annotation
        self.last_stats = DeduplicationStats()
        self._source_title_map: Dict[str, str] = {}

    def _format_secondary_attribution(self, url: str, title: Optional[str]) -> str:
        """Format secondary URL entry with optional title annotation."""
        clean_url = canonicalize_url(url)
        if not clean_url:
            return ""
        if title:
            self._source_title_map[clean_url] = title.strip()
        if self.include_title_annotation and title:
            return f"{clean_url} ({title.strip()})"
        return clean_url

    def _merge_passage_attribution(
        self, representative: ScoredPassage, duplicate: ScoredPassage
    ) -> None:
        """Merge attribution and relevance scores from duplicate into representative passage."""
        # 1. Retain maximum relevance score
        if duplicate.relevance_score > representative.relevance_score:
            representative.relevance_score = duplicate.relevance_score

        # 2. Extract all URLs from duplicate
        candidate_urls = [duplicate.url] + list(duplicate.secondary_urls)
        primary_canon = canonicalize_url(representative.url)

        for raw_u in candidate_urls:
            formatted = self._format_secondary_attribution(raw_u, duplicate.title)
            if not formatted:
                continue
            bare_u = canonicalize_url(raw_u)
            if bare_u == primary_canon:
                continue
            if formatted not in representative.secondary_urls and bare_u not in representative.secondary_urls:
                representative.secondary_urls.append(formatted)
                self.last_stats.attributions_merged += 1

    def _merge_claim_attribution(
        self, representative: ExtractedClaim, duplicate: ExtractedClaim
    ) -> None:
        """Merge attribution and confidence scores from duplicate into representative claim."""
        # 1. Retain maximum confidence score
        if duplicate.confidence_score > representative.confidence_score:
            representative.confidence_score = duplicate.confidence_score

        # 2. Merge entities union
        existing_entities = set(representative.entities)
        for ent in duplicate.entities:
            if ent not in existing_entities:
                representative.entities.append(ent)
                existing_entities.add(ent)

        # 3. Merge secondary URLs
        candidate_urls = [duplicate.source_url] + list(duplicate.secondary_urls)
        primary_canon = canonicalize_url(representative.source_url)

        for raw_u in candidate_urls:
            formatted = self._format_secondary_attribution(raw_u, duplicate.source_title)
            if not formatted:
                continue
            bare_u = canonicalize_url(raw_u)
            if bare_u == primary_canon:
                continue
            if formatted not in representative.secondary_urls and bare_u not in representative.secondary_urls:
                representative.secondary_urls.append(formatted)
                self.last_stats.attributions_merged += 1

    def deduplicate_passages(self, passages: List[ScoredPassage]) -> List[ScoredPassage]:
        """Perform two-stage deduplication on a collection of ScoredPassage objects.

        Args:
            passages: Input list of ScoredPassage objects.

        Returns:
            Deduplicated list of ScoredPassage objects with attribution preserved.
        """
        self.last_stats = DeduplicationStats(total_input=len(passages))
        if not passages:
            return []

        exact_hash_map: Dict[str, ScoredPassage] = {}
        index = SimHashIndex(threshold=self.hamming_threshold)
        deduped: List[ScoredPassage] = []

        for p in passages:
            if not p or not p.text or not p.text.strip():
                continue

            # Stage 1: Exact Deduplication (SHA-256 of normalized text)
            exact_hash = compute_exact_hash(p.text)
            if exact_hash in exact_hash_map:
                rep = exact_hash_map[exact_hash]
                self._merge_passage_attribution(rep, p)
                self.last_stats.exact_duplicates_pruned += 1
                continue

            # Stage 2: Near-Duplicate Detection via 64-bit SimHash
            fp = SimHash64.compute_simhash(p.text, shingle_size=self.shingle_size)
            near_dups = index.find_near_duplicates(fp, threshold=self.hamming_threshold)
            if near_dups:
                rep = near_dups[0][2]
                self._merge_passage_attribution(rep, p)
                self.last_stats.near_duplicates_pruned += 1
                continue

            # Item is unique
            exact_hash_map[exact_hash] = p
            index.add(p.passage_id, fp, metadata=p)
            deduped.append(p)
            self.last_stats.unique_retained += 1

        return deduped

    def deduplicate_claims(self, claims: List[ExtractedClaim]) -> List[ExtractedClaim]:
        """Perform two-stage deduplication on a collection of ExtractedClaim objects.

        Args:
            claims: Input list of ExtractedClaim objects.

        Returns:
            Deduplicated list of ExtractedClaim objects with attribution preserved.
        """
        self.last_stats = DeduplicationStats(total_input=len(claims))
        if not claims:
            return []

        exact_hash_map: Dict[str, ExtractedClaim] = {}
        index = SimHashIndex(threshold=self.hamming_threshold)
        deduped: List[ExtractedClaim] = []

        for c in claims:
            if not c or not c.text or not c.text.strip():
                continue

            # Stage 1: Exact Deduplication (SHA-256 of normalized text)
            exact_hash = compute_exact_hash(c.text)
            if exact_hash in exact_hash_map:
                rep = exact_hash_map[exact_hash]
                self._merge_claim_attribution(rep, c)
                self.last_stats.exact_duplicates_pruned += 1
                continue

            # Stage 2: Near-Duplicate Detection via 64-bit SimHash
            fp = SimHash64.compute_simhash(c.text, shingle_size=self.shingle_size)
            near_dups = index.find_near_duplicates(fp, threshold=self.hamming_threshold)
            if near_dups:
                rep = near_dups[0][2]
                self._merge_claim_attribution(rep, c)
                self.last_stats.near_duplicates_pruned += 1
                continue

            # Unique claim
            exact_hash_map[exact_hash] = c
            index.add(c.claim_id, fp, metadata=c)
            deduped.append(c)
            self.last_stats.unique_retained += 1

        return deduped

    def deduplicate(self, items: List[Union[ScoredPassage, ExtractedClaim]]) -> List[Any]:
        """Polymorphic entry point for deduplicating either passages or claims."""
        if not items:
            return []
        first = items[0]
        if isinstance(first, ScoredPassage) or type(first).__name__ == "ScoredPassage":
            return self.deduplicate_passages(items)  # type: ignore
        elif isinstance(first, ExtractedClaim) or type(first).__name__ == "ExtractedClaim":
            return self.deduplicate_claims(items)  # type: ignore
        raise TypeError(f"Unsupported item type for TwoStageDeduplicator: {type(first)}")
