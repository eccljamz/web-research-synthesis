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
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union
from urllib.parse import urlparse

try:
    from research_synthesis.models import (
        ClaimCluster,
        ClaimType,
        CorroboratedClaimGroup,
        DiscrepancyGroup,
        ExtractedClaim,
        ScoredPassage,
        SubQuery,
    )
except ImportError:
    try:
        from src.research_synthesis.models import (
            ClaimCluster,
            ClaimType,
            CorroboratedClaimGroup,
            DiscrepancyGroup,
            ExtractedClaim,
            ScoredPassage,
            SubQuery,
        )
    except ImportError:
        from ..models import (
            ClaimCluster,
            ClaimType,
            CorroboratedClaimGroup,
            DiscrepancyGroup,
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
    "implications": "Strategic Implications & Future Horizons",
    "general": "Core Empirical Findings & Strategic Perspectives",
}

# Numerical metric extraction pattern
METRIC_REGEX = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(%|percentage|percent|pct|billion|million|trillion|USD|\$|dollars|dollar|EUR|Wh/kg|Wh/L|°C|tons|GW|MW|kWh|nm|mS/cm)?(?!\w)",
    re.IGNORECASE,
)

# Canonical unit alias normalization mapping
UNIT_ALIASES: Dict[str, str] = {
    "%": "percent",
    "pct": "percent",
    "percentage": "percent",
    "$": "usd",
    "dollar": "usd",
    "dollars": "usd",
}


def _normalize_unit(unit: Optional[str]) -> str:
    """Normalize a metric unit string to its canonical alias in lowercase."""
    if not unit:
        return ""
    u = unit.lower().strip()
    return UNIT_ALIASES.get(u, u)


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
            idf_val = self.idf.get(t, math.log(1.0 + max(1, self.doc_count)))
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
        subquery_match_threshold: float = 0.10,
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

    def cluster(
        self,
        claims: Sequence[ExtractedClaim],
        sub_queries: Sequence[SubQuery],
        topic: str,
        passages: Optional[Sequence[ScoredPassage]] = None,
    ) -> List[ClaimCluster]:
        """Alias for cluster_claims adhering to standard pipeline interface."""
        return self.cluster_claims(claims=claims, sub_queries=sub_queries, topic=topic, passages=passages)

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

        # Fingerprint tracking for near-duplicate claim cluster cohesion
        assigned_fingerprints: List[Tuple[int, str]] = []
        try:
            from research_synthesis.extraction.dedup import SimHash64
        except ImportError:
            try:
                from src.research_synthesis.extraction.dedup import SimHash64
            except ImportError:
                SimHash64 = None

        for claim in claims:
            assigned_sq_id: Optional[str] = None
            claim_fp = SimHash64.compute(claim.text) if SimHash64 else 0

            # 0. Cohesion with near-duplicate claim already assigned
            if claim_fp and assigned_fingerprints and SimHash64:
                for prior_fp, prior_sq in assigned_fingerprints:
                    if SimHash64.hamming_distance(claim_fp, prior_fp) <= 3:
                        assigned_sq_id = prior_sq
                        break

            # 1. Direct provenance attribute
            if not assigned_sq_id:
                if hasattr(claim, "subquery_id") and getattr(claim, "subquery_id") in sq_map:
                    assigned_sq_id = getattr(claim, "subquery_id")
                elif hasattr(claim, "subquery") and getattr(claim, "subquery") in sq_map:
                    assigned_sq_id = getattr(claim, "subquery")

            # 2. Passage lookup map
            if not assigned_sq_id and passage_subquery_map:
                doc_key = f"{claim.source_doc_id}:{claim.source_url}"
                if doc_key in passage_subquery_map:
                    p_sq = passage_subquery_map[doc_key]
                    if p_sq and p_sq.strip():
                        for sq in sub_queries:
                            if sq.search_query and (
                                sq.search_query.lower() in p_sq.lower()
                                or p_sq.lower() in sq.search_query.lower()
                            ):
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
                if claim_fp:
                    assigned_fingerprints.append((claim_fp, assigned_sq_id))
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
                facet="technical",
                claims=quant_claims,
            )
            c2 = ClaimCluster(
                cluster_id=f"{cluster.cluster_id}-b",
                title="",
                facet="economic",
                claims=other_claims,
            )
            return c1, c2

        # Partition heuristic 2: Bisection by vector distance from first claim
        c0_vec = self.tfidf.transform(claims[0].text)
        scored = sorted(claims, key=lambda c: self.tfidf.cosine_similarity(self.tfidf.transform(c.text), c0_vec), reverse=True)
        mid = max(1, len(scored) // 2)

        # Keep highly similar claims (sim >= 0.35 to c0) grouped together in c1
        split_idx = mid
        for idx in range(1, len(scored)):
            sim = self.tfidf.cosine_similarity(self.tfidf.transform(scored[idx].text), c0_vec)
            if sim < 0.35:
                split_idx = idx
                break

        c1 = ClaimCluster(
            cluster_id=f"{cluster.cluster_id}-a",
            title="",
            facet=cluster.facet or "technical",
            claims=scored[:split_idx],
        )
        c2 = ClaimCluster(
            cluster_id=f"{cluster.cluster_id}-b",
            title="",
            facet="comparative" if cluster.facet == "technical" else "economic",
            claims=scored[split_idx:],
        )
        return c1, c2

    # -------------------------------------------------------------------------
    # Title Generation
    # -------------------------------------------------------------------------

    def _generate_cluster_title(self, cluster: ClaimCluster, topic: str, index: int) -> str:
        """Generate an informative, domain-appropriate section title."""
        # If mapped to a known facet
        clean_facet = cluster.facet.split("_")[0].lower() if cluster.facet else "general"
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
                c_j_tokens = set(self.tfidf.tokenize(c_j.text))
                jaccard = len(c_i_tokens & c_j_tokens) / max(1, len(c_i_tokens | c_j_tokens))
                c_j_vec = self.tfidf.transform(c_j.text)
                cos_sim = self.tfidf.cosine_similarity(c_i_vec, c_j_vec)

                # Shared entity bonus
                shared_entities = set(c_i.entities) & set(c_j.entities)

                if jaccard >= 0.35 or cos_sim >= 0.45 or (shared_entities and (jaccard >= 0.25 or cos_sim >= 0.35)):
                    if d_j:
                        unique_domains.add(d_j)
                    supporting_ids.append(c_j.claim_id)
                    all_urls.append(c_j.source_url)

            if len(unique_domains) >= 2:
                seen_primary.add(c_i.claim_id)
                seen_primary.update(supporting_ids)
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

                # Also check lexical overlap if no explicit shared entities
                tok_overlap = len(words1 & words2) >= 2

                if (shared_entities or tok_overlap) and ((has_pos1 and has_neg2) or (has_neg1 and has_pos2)):
                    disc_count += 1
                    ent_name = list(shared_entities)[0] if shared_entities else "directional metric"
                    discrepancies.append(
                        DiscrepancyGroup(
                            discrepancy_id=f"disc-{disc_count:02d}",
                            entity=ent_name,
                            discrepancy_type="POLAR_CONFLICT",
                            claim_a_id=c1.claim_id,
                            claim_b_id=c2.claim_id,
                            claim_a_text=c1.text,
                            claim_b_text=c2.text,
                            source_a_url=c1.source_url,
                            source_b_url=c2.source_url,
                            explanation=f"Conflicting directional assertions detected on entity '{ent_name}'.",
                        )
                    )
                    continue

                # Check 2: Numerical metric variation
                # Guard: Require shared entity or token overlap (>= 2) to prevent false-positive
                # discrepancies between unrelated quantitative metrics sharing a unit.
                if (
                    c1.claim_type == ClaimType.QUANTITATIVE
                    and c2.claim_type == ClaimType.QUANTITATIVE
                    and (bool(shared_entities) or tok_overlap)
                ):
                    m1_matches = METRIC_REGEX.findall(c1.text)
                    m2_matches = METRIC_REGEX.findall(c2.text)

                    for val_str1, unit1 in m1_matches:
                        for val_str2, unit2 in m2_matches:
                            u1_norm = _normalize_unit(unit1)
                            u2_norm = _normalize_unit(unit2)
                            if u1_norm and u2_norm and u1_norm == u2_norm:
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
        primary_facet = sub_queries[0].facet if sub_queries else "technical"
        secondary_facet = sub_queries[1].facet if len(sub_queries) > 1 else "economic"

        c1_title = FACET_TITLE_TEMPLATES.get(primary_facet, f"{topic}: Core Empirical Findings")
        c2_title = FACET_TITLE_TEMPLATES.get(secondary_facet, f"{topic}: Strategic Context & Horizons")

        return [
            ClaimCluster(
                cluster_id="sec-01",
                title=c1_title,
                facet=primary_facet,
                claims=[claim],
                key_entities=list(claim.entities),
            ),
            ClaimCluster(
                cluster_id="sec-02",
                title=c2_title,
                facet=secondary_facet,
                claims=[],
            ),
        ]


__all__ = [
    "ThematicClusterer",
    "PureTFIDF",
    "ClaimCluster",
    "CorroboratedClaimGroup",
    "DiscrepancyGroup",
]
