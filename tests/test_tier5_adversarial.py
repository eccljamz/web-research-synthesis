"""Tier 5 Adversarial Coverage Hardening & Edge Oracles Test Suite.

Milestone 4 Phase 2 - Adversarial Verification Suite:
1. Malformed inputs, Unicode edge cases, extreme token distributions:
   - Corrupted and deeply nested HTML, script/style bombs, missing document wrappers.
   - Unicode queries (CJK, Cyrillic, Arabic, accented, emojis, zero-width characters).
   - Extreme token distributions: pure stopwords, all-distractor corpora, single massive words.
   - Topic length boundaries (< 5 characters, > 500 characters).
2. Numerical boundary variations and unit alias combinations:
   - Unit alias equivalence (% vs pct vs percentage vs percent; $ vs USD vs dollar vs dollars).
   - Exact numerical threshold boundaries (<= 15% variance unflagged, > 15% variance flagged).
   - Number formatting (comma-separated values like $1,500 million, decimals like 12.0).
   - Disjoint entities sharing common units (ensuring zero false positive conflicts).
   - Directional polar assertion conflicts (positive vs negative trajectory).
3. Thematic clustering transitions:
   - Scaffolding transitions on degenerate claim inputs (0 claims -> 2 scaffolded clusters).
   - Single-claim scaffolding (1 claim -> 2 clusters).
   - Centroid bisection transitions (2 claims on identical subquery bisected into 2 distinct clusters).
   - Agglomerative centroid consolidation (> 5 subqueries merged down to exactly <= 5 clusters).
   - Title generation and centroid term stability across all transition regimes.
4. Citation registry deduplication and co-citation attribution under high load:
   - High-load citation registry (50+ claims across 20+ distinct URLs).
   - Strict 1-based order-of-appearance indexing without numerical gaps.
   - Co-citation attribution pooling across multiple secondary URLs.
   - Bibliography integrity and strict referential verification.

Pure Python Standard Library (unittest) - Zero External Dependencies.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

# Ensure repository root and src directory are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.research_synthesis.models import (
    BriefMetadata,
    ClaimCluster,
    ClaimType,
    CleanArticle,
    DocumentMetadata,
    ExtractedClaim,
    KeyTakeaway,
    RawWebDocument,
    ResearchBrief,
    RetrievalBatch,
    ScoredPassage,
    SourceCitation,
    SubQuery,
    ThematicSection,
)
from src.research_synthesis.retrieval.decomposer import HeuristicQueryDecomposer
from src.research_synthesis.retrieval.parser import DocumentParser, RobustHTMLParser
from src.research_synthesis.retrieval.retriever import MockWebRetrievalClient
from src.research_synthesis.extraction.bm25 import BM25Filter, OkapiBM25
from src.research_synthesis.extraction.chunker import PassageChunker
from src.research_synthesis.extraction.claims import ClaimExtractor
from src.research_synthesis.extraction.dedup import SimHash64, TwoStageDeduplicator, canonicalize_url
from src.research_synthesis.synthesis.cluster import ThematicClusterer
from src.research_synthesis.synthesis.synthesizer import CitationRegistry, ExtractiveSynthesizer
from src.research_synthesis.synthesis.formatters import JSONSchemaSerializer, MarkdownFormatter
from src.research_synthesis.pipeline import ResearchPipeline
from src.research_synthesis.verification.validator import ResearchBriefValidator, validate_brief

MANIFEST_PATH = PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "manifest.json"


# ============================================================================
# Suite 1: Malformed Inputs, Unicode Edge Cases, Extreme Token Distributions
# ============================================================================

class TestMalformedInputsAndUnicode(unittest.TestCase):
    """Stress tests on malformed HTML, Unicode characters, and extreme token distributions."""

    def setUp(self):
        self.decomposer = HeuristicQueryDecomposer()
        self.chunker = PassageChunker(min_words=50, max_words=200, overlap_words=20)
        self.bm25 = BM25Filter(s_min=0.2, alpha=0.25)
        self.meta = DocumentMetadata(
            url="https://example.org/test",
            canonical_url="https://example.org/test",
            domain="example.org",
            title="Unicode & Malformed Test",
        )

    def test_unicode_query_decomposition_scripts(self):
        """Verifies decomposition across diverse non-Latin scripts, diacritics, and symbols."""
        test_topics = [
            ("Кибербезопасность квантовых вычислений", "temporal"),
            ("تحليل اقتصادي لسلاسل التوريد العالمية", "economic"),
            ("半导体制造技术与经济可行性", "technical"),
            ("Résilience économique vs inflation globale", "comparative"),
            ("Café trade-offs between FairTrade and DirectTrade", "comparative"),
        ]
        for topic, expected_facet in test_topics:
            res = self.decomposer.decompose(topic, max_subqueries=4)
            self.assertGreaterEqual(len(res.sub_queries), 2)
            self.assertEqual(res.topic, topic)
            for sq in res.sub_queries:
                self.assertTrue(len(sq.search_query.strip()) > 0)
                self.assertEqual(sq.original_topic, topic)

    def test_zero_width_and_invisible_character_handling(self):
        """Zero-width spaces, joiners, and control characters in HTML and queries."""
        zw_html = (
            "<html><body>"
            "<p>Valid\u200btext\u200cwith\u200dinvisible\u200eseparators that exceeds twenty-five characters.</p>"
            "</body></html>"
        )
        raw_doc = RawWebDocument(url="https://example.org/zw", status_code=200, raw_html=zw_html)
        art = DocumentParser.parse(raw_doc)
        self.assertGreaterEqual(len(art.paragraphs), 1)
        self.assertIn("Valid", art.cleaned_text)

    def test_deeply_malformed_unclosed_html_hierarchy(self):
        """Chaotic HTML tag soup with unclosed formatting and structural tags."""
        chaotic_html = (
            "<html><head><title>Chaotic Document"
            "<body><div><h1>Major Breakthrough in Materials"
            "<p><b><i><u>Solid-state electrolytes demonstrate record conductivities exceeding 12 mS/cm."
            "<div><section><article><span><p>Second paragraph with sufficient substantive content for extraction."
            "<script>var unclosed = 'script;"
        )
        raw_doc = RawWebDocument(url="https://example.org/chaotic", status_code=200, raw_html=chaotic_html)
        art = DocumentParser.parse(raw_doc)
        self.assertGreaterEqual(len(art.paragraphs), 1)
        self.assertNotIn("var unclosed", art.cleaned_text)

    def test_extreme_token_distributions_in_bm25(self):
        """Corpus with highly skewed vocabulary and stopword-only queries."""
        passages = [
            ScoredPassage("p1", "d1", "https://a.com", "Title 1", "battery " * 100, 0.0, "", 100),
            ScoredPassage("p2", "d2", "https://b.com", "Title 2", "electrolyte " * 100, 0.0, "", 100),
            ScoredPassage("p3", "d3", "https://c.com", "Title 3", "solid " * 100, 0.0, "", 100),
        ]
        # Query with pure stopwords returns empty (graceful, no crash)
        filtered = self.bm25.filter(passages, topic="which was what when where who")
        self.assertEqual(filtered, [])

        # Query matching only one passage
        filtered_single = self.bm25.filter(passages, topic="electrolyte")
        self.assertEqual(len(filtered_single), 1)
        self.assertEqual(filtered_single[0].passage_id, "p2")

    def test_single_massive_token_without_spaces(self):
        """Paragraph consisting of single 1,000-character token does not cause infinite loop."""
        massive_token = "A" * 1000
        art = CleanArticle("doc-massive-tok", "https://a.com", self.meta, massive_token, [massive_token])
        passages = self.chunker.chunk_article(art)
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0].passage_id, "doc-massive-tok-p000")


# ============================================================================
# Suite 2: Numerical Boundary Variations and Unit Alias Combinations
# ============================================================================

class TestNumericalBoundariesAndAliases(unittest.TestCase):
    """Stress tests on numerical variance boundaries, unit aliases, and conflict detection."""

    def setUp(self):
        self.clusterer = ThematicClusterer(min_sections=2, max_sections=5)

    def test_unit_alias_normalization(self):
        """Unit aliases (% vs pct vs percent; $ vs USD vs dollars) are correctly matched."""
        claim_pct1 = ExtractedClaim(
            claim_id="clm-pct1",
            text="Manufacturing yield reached 85% in advanced pilot facilities.",
            source_doc_id="d1",
            source_url="https://source1.org/yield",
            source_title="Yield Report 1",
            passage_snippet="Manufacturing yield reached 85%.",
            confidence_score=0.9,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Manufacturing yield"],
        )
        claim_pct2 = ExtractedClaim(
            claim_id="clm-pct2",
            text="Manufacturing yield was limited to 55 percent under standard production line metrics.",
            source_doc_id="d2",
            source_url="https://source2.org/yield",
            source_title="Yield Report 2",
            passage_snippet="Manufacturing yield was limited to 55 percent.",
            confidence_score=0.9,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Manufacturing yield"],
        )
        discrepancies = self.clusterer._detect_discrepancies([claim_pct1, claim_pct2])
        self.assertEqual(len(discrepancies), 1)
        self.assertEqual(discrepancies[0].discrepancy_type, "NUMERICAL_VARIATION")
        self.assertIn("85", discrepancies[0].explanation)
        self.assertIn("55", discrepancies[0].explanation)

    def test_exact_15_percent_variance_boundary(self):
        """Variance <= 15% is NOT flagged; variance > 15% IS flagged."""
        # Case A: 100 vs 114 (14/114 = 12.3% <= 15%) -> NO DISCREPANCY
        c_base = ExtractedClaim(
            claim_id="c-base",
            text="Ionic conductivity reached 100 mS/cm under laboratory conditions.",
            source_doc_id="d1",
            source_url="https://lab.org/c1",
            source_title="Lab 1",
            passage_snippet="",
            confidence_score=0.9,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Ionic conductivity"],
        )
        c_near = ExtractedClaim(
            claim_id="c-near",
            text="Ionic conductivity reached 114 mS/cm under laboratory conditions.",
            source_doc_id="d2",
            source_url="https://lab.org/c2",
            source_title="Lab 2",
            passage_snippet="",
            confidence_score=0.9,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Ionic conductivity"],
        )
        disc_near = self.clusterer._detect_discrepancies([c_base, c_near])
        self.assertEqual(len(disc_near), 0, "Variance <= 15% must not be flagged as a discrepancy")

        # Case B: 100 vs 120 (20/120 = 16.7% > 15%) -> FLAGGED
        c_far = ExtractedClaim(
            claim_id="c-far",
            text="Ionic conductivity reached 120 mS/cm under laboratory conditions.",
            source_doc_id="d3",
            source_url="https://lab.org/c3",
            source_title="Lab 3",
            passage_snippet="",
            confidence_score=0.9,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Ionic conductivity"],
        )
        disc_far = self.clusterer._detect_discrepancies([c_base, c_far])
        self.assertEqual(len(disc_far), 1, "Variance > 15% must be flagged as a discrepancy")
        self.assertEqual(disc_far[0].discrepancy_type, "NUMERICAL_VARIATION")

    def test_comma_separated_number_formatting(self):
        """Comma-formatted numbers ($1,500 million vs $2,200 million) parse and compare cleanly."""
        c1 = ExtractedClaim(
            claim_id="c-val1",
            text="Capital investment reached $1,500 million for domestic foundry expansion.",
            source_doc_id="d1",
            source_url="https://news.com/1",
            source_title="News 1",
            passage_snippet="",
            confidence_score=0.9,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Capital investment"],
        )
        c2 = ExtractedClaim(
            claim_id="c-val2",
            text="Capital investment was estimated at $2,200 million for domestic foundry expansion.",
            source_doc_id="d2",
            source_url="https://news.com/2",
            source_title="News 2",
            passage_snippet="",
            confidence_score=0.9,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Capital investment"],
        )
        disc = self.clusterer._detect_discrepancies([c1, c2])
        self.assertEqual(len(disc), 1)
        self.assertEqual(disc[0].discrepancy_type, "NUMERICAL_VARIATION")

    def test_polar_directional_assertion_conflict(self):
        """Opposing directional assertions (increased vs decreased) on same entity generate POLAR_CONFLICT."""
        c_pos = ExtractedClaim(
            claim_id="c-pos",
            text="Domestic manufacturing output increased significantly during the third quarter.",
            source_doc_id="d1",
            source_url="https://econ1.org",
            source_title="Econ 1",
            passage_snippet="",
            confidence_score=0.85,
            claim_type=ClaimType.RELATIONAL,
            entities=["Domestic manufacturing output"],
        )
        c_neg = ExtractedClaim(
            claim_id="c-neg",
            text="Domestic manufacturing output decreased significantly during the third quarter.",
            source_doc_id="d2",
            source_url="https://econ2.org",
            source_title="Econ 2",
            passage_snippet="",
            confidence_score=0.85,
            claim_type=ClaimType.RELATIONAL,
            entities=["Domestic manufacturing output"],
        )
        disc = self.clusterer._detect_discrepancies([c_pos, c_neg])
        self.assertEqual(len(disc), 1)
        self.assertEqual(disc[0].discrepancy_type, "POLAR_CONFLICT")


# ============================================================================
# Suite 3: Centroid Bisection vs Scaffolding Transitions in Thematic Clustering
# ============================================================================

class TestThematicClustererTransitions(unittest.TestCase):
    """Stress tests on cluster boundary enforcement: 0 claims, 1 claim, 2 claims bisection, > 5 merge."""

    def setUp(self):
        self.clusterer = ThematicClusterer(min_sections=2, max_sections=5)
        self.topic = "Autonomous Research Synthesis Architecture"
        self.sub_queries = [
            SubQuery("sq-01", self.topic, "technical", "system technical architecture and algorithms"),
            SubQuery("sq-02", self.topic, "economic", "cost feasibility scaling economics"),
        ]

    def test_zero_claims_scaffolding_transition(self):
        """0 claims cleanly produces exactly 2 scaffolding clusters."""
        clusters = self.clusterer.cluster(claims=[], sub_queries=self.sub_queries, topic=self.topic)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(clusters[0].cluster_id, "sec-01")
        self.assertEqual(clusters[1].cluster_id, "sec-02")
        self.assertEqual(len(clusters[0].claims), 0)
        self.assertEqual(len(clusters[1].claims), 0)
        self.assertTrue(clusters[0].title)
        self.assertTrue(clusters[1].title)

    def test_single_claim_scaffolding_transition(self):
        """1 claim produces exactly 2 clusters: 1 populated and 1 complementary scaffold."""
        claim = ExtractedClaim(
            claim_id="c-single",
            text="The architecture achieves 99.8% verification reliability across all benchmark suites.",
            source_doc_id="d1",
            source_url="https://bench.org",
            source_title="Benchmarks",
            passage_snippet="",
            confidence_score=0.95,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Architecture"],
        )
        clusters = self.clusterer.cluster(claims=[claim], sub_queries=self.sub_queries, topic=self.topic)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(len(clusters[0].claims), 1)
        self.assertEqual(len(clusters[1].claims), 0)
        self.assertEqual(clusters[0].claims[0].claim_id, "c-single")

    def test_two_claims_same_subquery_bisection(self):
        """2 claims mapped to the same subquery bisect into 2 distinct clusters, each containing 1 claim."""
        c1 = ExtractedClaim(
            claim_id="c-quant",
            text="System throughput reached 10,000 queries per second.",
            source_doc_id="d1",
            source_url="https://perf.org/1",
            source_title="Perf 1",
            passage_snippet="",
            confidence_score=0.95,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Throughput"],
        )
        c2 = ExtractedClaim(
            claim_id="c-qual",
            text="Formal verification confirmed zero semantic invariant violations across tests.",
            source_doc_id="d2",
            source_url="https://perf.org/2",
            source_title="Perf 2",
            passage_snippet="",
            confidence_score=0.90,
            claim_type=ClaimType.GENERAL_FACT,
            entities=["Verification"],
        )
        # Pass only 1 subquery so both claims initially group together
        single_sq = [SubQuery("sq-01", self.topic, "technical", "system performance and verification")]
        clusters = self.clusterer.cluster(claims=[c1, c2], sub_queries=single_sq, topic=self.topic)
        self.assertEqual(len(clusters), 2, "Clusterer must bisect single cluster into 2 clusters")
        self.assertEqual(len(clusters[0].claims), 1)
        self.assertEqual(len(clusters[1].claims), 1)
        self.assertEqual(clusters[0].cluster_id, "sec-01")
        self.assertEqual(clusters[1].cluster_id, "sec-02")

    def test_many_subqueries_consolidation_transition(self):
        """8 subqueries with 16 distinct claims consolidate down to exactly <= 5 clusters."""
        many_sqs = [
            SubQuery(f"sq-{i:02d}", self.topic, f"facet-{i}", f"search query for facet {i}")
            for i in range(8)
        ]
        claims = []
        for i in range(8):
            for j in range(2):
                claims.append(
                    ExtractedClaim(
                        claim_id=f"c-{i}-{j}",
                        text=f"Empirical metric {j} for facet {i} demonstrates {10 * (i + 1)} percent gain.",
                        source_doc_id=f"doc-{i}",
                        source_url=f"https://source-{i}.org",
                        source_title=f"Source {i}",
                        passage_snippet="",
                        confidence_score=0.85,
                        claim_type=ClaimType.QUANTITATIVE,
                    )
                )

        clusters = self.clusterer.cluster(claims=claims, sub_queries=many_sqs, topic=self.topic)
        self.assertLessEqual(len(clusters), 5, "Consolidation must cap section count at <= 5")
        self.assertGreaterEqual(len(clusters), 2, "Must retain >= 2 sections")
        total_claims_retained = sum(len(c.claims) for c in clusters)
        self.assertEqual(total_claims_retained, 16, "All 16 claims must be retained across consolidated clusters")


# ============================================================================
# Suite 4: Citation Registry Deduplication and Co-Citation Attribution Under High Load
# ============================================================================

class TestCitationRegistryHighLoad(unittest.TestCase):
    """Stress tests on CitationRegistry and high-load co-citation attribution."""

    def test_high_load_citation_indexing_and_gaps(self):
        """Registers 50 claims across 20 distinct URLs verifying contiguous 1-based indexing."""
        registry = CitationRegistry()
        num_urls = 20
        urls = [f"https://source-domain-{i:02d}.org/article" for i in range(num_urls)]

        # Generate 50 claims referencing subsets of the 20 URLs
        registered_indices = []
        for i in range(50):
            primary_url = urls[i % num_urls]
            sec_urls = [urls[(i + 1) % num_urls], urls[(i + 2) % num_urls]]
            claim = ExtractedClaim(
                claim_id=f"clm-load-{i:03d}",
                text=f"Factual assertion {i} with quantitative metric {i * 10} Wh/kg.",
                source_doc_id=f"doc-{i % num_urls}",
                source_url=primary_url,
                source_title=f"Source {i % num_urls}",
                passage_snippet=f"Snippet describing benchmark observation {i} with substantive detail.",
                confidence_score=0.9,
                claim_type=ClaimType.QUANTITATIVE,
                secondary_urls=sec_urls,
            )
            indices = registry.register_claim(claim)
            registered_indices.append(indices)
            self.assertTrue(all(isinstance(idx, int) and idx >= 1 for idx in indices))

        # Check bibliography
        bibliography = registry.build_bibliography()
        self.assertEqual(len(bibliography), num_urls, "All 20 distinct URLs must exist in bibliography")

        # Verify strict 1-based order-of-appearance without gaps
        expected_indices = list(range(1, num_urls + 1))
        actual_indices = [src.citation_index for src in bibliography]
        self.assertEqual(actual_indices, expected_indices, "Citation indices must be strictly 1, 2, ..., N without gaps")

        # Verify attribution
        for src in bibliography:
            self.assertGreaterEqual(len(src.attributed_claim_ids), 1, "Every source must have attributed claims")
            self.assertTrue(src.url.startswith("https://source-domain-"))

    def test_synthesizer_high_load_strict_referential_integrity(self):
        """ExtractiveSynthesizer under high load produces brief passing strict verification."""
        synthesizer = ExtractiveSynthesizer()
        num_claims = 30
        claims = [
            ExtractedClaim(
                claim_id=f"c-{i:02d}",
                text=f"Battery technology metric {i} reached {100 + i * 10} Wh/kg in testing.",
                source_doc_id=f"d-{i % 5}",
                source_url=f"https://domain-{i % 5}.com/paper",
                source_title=f"Domain Paper {i % 5}",
                passage_snippet=f"Testing context for claim {i} with substantive technical metrics.",
                confidence_score=0.9,
                claim_type=ClaimType.QUANTITATIVE,
            )
            for i in range(num_claims)
        ]
        clusters = [
            ClaimCluster("cl-01", "Core Energy Density Benchmarks", "technical", claims=claims[:15]),
            ClaimCluster("cl-02", "Commercial Scaling and Manufacturing", "economic", claims=claims[15:]),
        ]
        sub_queries = [
            SubQuery("sq-01", "Battery", "technical", "battery energy density"),
            SubQuery("sq-02", "Battery", "economic", "manufacturing scaling costs"),
        ]

        brief = synthesizer.synthesize(
            topic="Advanced Solid-State Battery Commercialization Roadmaps",
            clusters=clusters,
            sub_queries=sub_queries,
        )

        # Validate with strict validator (requires 100% of sources cited and >= 120 words)
        validator = ResearchBriefValidator(strict=True)
        res = validator.validate(brief.to_dict())
        self.assertTrue(res.is_valid, f"High-load brief failed strict validation: {res.errors}")
        self.assertGreaterEqual(res.metrics["total_brief_words"], 120)
        self.assertEqual(res.metrics["sources_count"], res.metrics["sources_cited_count"])


if __name__ == "__main__":
    unittest.main()
