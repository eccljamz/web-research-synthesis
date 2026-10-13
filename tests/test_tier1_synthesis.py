"""Tier 1 Unit and Integration Test Suite: Structured Knowledge Synthesis & Master Pipeline.

Milestone 3 Components Tested:
1. ThematicClusterer (F10): Subquery mapping, TF-IDF clustering, section bounds 2 <= K <= 5, consensus, discrepancies.
2. ExtractiveSynthesizer & CitationRegistry (F11): Contiguous order-of-appearance citations, MMR claim selection, narrative generation.
3. MarkdownFormatter & JSONSchemaSerializer (F12, F13): Markdown rendering, schema serialization, round-trip fidelity.
4. ResearchPipeline End-to-End Integration: All 3 canonical queries + edge query against offline mock corpus.
5. Graceful Fallbacks & Boundary Degradation: 0 documents, 0 claims, minimal corpus, blank topic.

Pure Python Standard Library (unittest) - Zero External Dependencies.
"""

from __future__ import annotations

import json
import os
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

try:
    from research_synthesis.models import (
        ClaimType,
        CleanArticle,
        DocumentMetadata,
        ExtractedClaim,
        KeyTakeaway,
        ResearchBrief,
        ScoredPassage,
        SourceCitation,
        SubQuery,
        ThematicSection,
    )
    from research_synthesis.retrieval.retriever import MockWebRetrievalClient
    from research_synthesis.synthesis.cluster import ClaimCluster, ThematicClusterer
    from research_synthesis.synthesis.synthesizer import (
        CitationRegistry,
        ExtractiveSynthesizer,
    )
    from research_synthesis.synthesis.formatters import (
        JSONSchemaSerializer,
        MarkdownFormatter,
    )
    from research_synthesis.pipeline import ResearchPipeline
    from research_synthesis.verification.validator import ResearchBriefValidator
except ImportError:
    from src.research_synthesis.models import (
        ClaimType,
        CleanArticle,
        DocumentMetadata,
        ExtractedClaim,
        KeyTakeaway,
        ResearchBrief,
        ScoredPassage,
        SourceCitation,
        SubQuery,
        ThematicSection,
    )
    from src.research_synthesis.retrieval.retriever import MockWebRetrievalClient
    from src.research_synthesis.synthesis.cluster import ClaimCluster, ThematicClusterer
    from src.research_synthesis.synthesis.synthesizer import (
        CitationRegistry,
        ExtractiveSynthesizer,
    )
    from src.research_synthesis.synthesis.formatters import (
        JSONSchemaSerializer,
        MarkdownFormatter,
    )
    from src.research_synthesis.pipeline import ResearchPipeline
    from src.research_synthesis.verification.validator import ResearchBriefValidator


MANIFEST_PATH = PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "manifest.json"


# ============================================================================
# Test Fixture Helpers
# ============================================================================

def make_sample_claims() -> List[ExtractedClaim]:
    """Generate representative ExtractedClaim objects for unit testing."""
    return [
        ExtractedClaim(
            claim_id="clm-01",
            text="Sulfide solid electrolytes achieve room-temperature ionic conductivity surpassing 12 mS/cm.",
            source_doc_id="doc-ssb-01",
            source_url="https://mock-science.org/materials/solid-electrolyte",
            source_title="Solid Electrolyte Materials",
            passage_snippet="Sulfide argyrodites demonstrated ionic conductivity of 12 mS/cm at 25 degrees.",
            confidence_score=0.95,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Sulfide", "argyrodite"],
            secondary_urls=[],
        ),
        ExtractedClaim(
            claim_id="clm-02",
            text="DOE Battery500 targets commercial cell energy density of 500 Wh/kg by 2030.",
            source_doc_id="doc-ssb-02",
            source_url="https://mock-energy-gov.org/reports/battery500",
            source_title="DOE Battery500 Consortium Roadmap",
            passage_snippet="The consortium roadmap establishes 500 Wh/kg gravimetric density targets.",
            confidence_score=0.92,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["DOE", "Battery500"],
        ),
        ExtractedClaim(
            claim_id="clm-03",
            text="Roll-to-roll dry room processing costs currently exceed $180 per kWh for pilot lines.",
            source_doc_id="doc-ssb-03",
            source_url="https://mock-tech-industrial.com/manufacturing/scalability",
            source_title="Industrial Scaling of Solid-State Batteries",
            passage_snippet="Pilot line dry room environmental controls drive capital expenditures above $180 per kWh.",
            confidence_score=0.88,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["dry room", "roll-to-roll"],
        ),
        ExtractedClaim(
            claim_id="clm-04",
            text="Garnet LLZO electrolytes resist thermal runaway at temperatures up to 800 degrees Celsius.",
            source_doc_id="doc-ssb-01",
            source_url="https://mock-science.org/materials/solid-electrolyte",
            source_title="Solid Electrolyte Materials",
            passage_snippet="LLZO ceramics exhibit exceptional thermal stability up to 800 C.",
            confidence_score=0.85,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["LLZO", "thermal runaway"],
        ),
        ExtractedClaim(
            claim_id="clm-05",
            text="Lithium metal anode integration decreases overall battery pack volume by 35 percent.",
            source_doc_id="doc-ssb-02",
            source_url="https://mock-energy-gov.org/reports/battery500",
            source_title="DOE Battery500 Consortium Roadmap",
            passage_snippet="Pack level integration saves 35 percent volume by replacing porous graphite.",
            confidence_score=0.90,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Lithium metal", "anode"],
        ),
    ]


def make_sample_subqueries() -> List[SubQuery]:
    """Generate representative SubQuery objects."""
    return [
        SubQuery("sq-01", "Solid-State Batteries", "technical", "solid electrolyte ionic conductivity sulfide oxide"),
        SubQuery("sq-02", "Solid-State Batteries", "economic", "manufacturing scalability roll-to-roll pilot line dry room"),
        SubQuery("sq-03", "Solid-State Batteries", "comparative", "energy density Wh/kg roadmap Battery500"),
    ]


# ============================================================================
# Suite 1: Thematic Clusterer Unit Tests (F10)
# ============================================================================

class TestThematicClusterer(unittest.TestCase):
    """Unit tests for ThematicClusterer grouping, bounds, and analysis."""

    def setUp(self):
        self.clusterer = ThematicClusterer(min_sections=2, max_sections=5)
        self.claims = make_sample_claims()
        self.sub_queries = make_sample_subqueries()
        self.topic = "Next-Generation Solid-State Battery Commercialization"

    def test_clustering_standard_claims(self):
        clusters = self.clusterer.cluster(self.claims, self.sub_queries, self.topic)
        self.assertGreaterEqual(len(clusters), 2)
        self.assertLessEqual(len(clusters), 5)
        for cluster in clusters:
            self.assertTrue(cluster.cluster_id)
            self.assertTrue(cluster.title)
            self.assertGreaterEqual(len(cluster.title.split()), 2)
            self.assertFalse(any(bad in cluster.title for bad in ["TODO", "TBD", "placeholder"]))

    def test_section_bounds_consolidation(self):
        # Create 8 subqueries to produce > 5 clusters initially
        many_sqs = [
            SubQuery(f"sq-{i}", self.topic, f"facet-{i}", f"search query facet {i}")
            for i in range(8)
        ]
        many_claims = list(self.claims)
        for i in range(8):
            many_claims.append(
                ExtractedClaim(
                    claim_id=f"extra-{i}",
                    text=f"Specific factual metric for facet {i} showing {i * 10} percent increase.",
                    source_doc_id=f"doc-{i}",
                    source_url=f"https://source-{i}.org/page",
                    source_title=f"Source {i}",
                    passage_snippet=f"Snippet for facet {i}.",
                    confidence_score=0.8,
                    claim_type=ClaimType.QUANTITATIVE,
                )
            )
        clusters = self.clusterer.cluster(many_claims, many_sqs, self.topic)
        self.assertLessEqual(len(clusters), 5, "Clusterer must consolidate clusters if > 5")
        self.assertGreaterEqual(len(clusters), 2)

    def test_section_bounds_scaffolding(self):
        # 1 claim with 0 subqueries
        single_claim = [self.claims[0]]
        clusters = self.clusterer.cluster(single_claim, [], self.topic)
        self.assertGreaterEqual(len(clusters), 2, "Clusterer must scaffold at least 2 clusters")
        self.assertLessEqual(len(clusters), 5)

    def test_cluster_title_generation(self):
        clusters = self.clusterer.cluster(self.claims, self.sub_queries, self.topic)
        for c in clusters:
            self.assertNotIn("Untitled", c.title)
            self.assertNotIn("TODO", c.title)
            self.assertGreaterEqual(len(c.title), 5)

    def test_multi_source_consensus_detection(self):
        # Add corroborating claim with same entity from different domain
        corroborated_claim = ExtractedClaim(
            claim_id="clm-01-corrob",
            text="Independent testing verified sulfide solid electrolyte conductivity of 12.5 mS/cm.",
            source_doc_id="doc-independent",
            source_url="https://mock-automotive-review.de/testing",
            source_title="Automotive Testing Review",
            passage_snippet="Automotive lab verified sulfide solid electrolyte conductivity above 12 mS/cm.",
            confidence_score=0.91,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Sulfide", "conductivity"],
        )
        claims = self.claims + [corroborated_claim]
        clusters = self.clusterer.cluster(claims, self.sub_queries, self.topic)
        total_corrob = sum(len(c.corroborated_claims) for c in clusters)
        self.assertGreaterEqual(total_corrob, 1)

    def test_discrepancy_detection(self):
        # Add contradictory numerical claim
        conflicting_claim = ExtractedClaim(
            claim_id="clm-01-conflict",
            text="Sulfide solid electrolyte room-temperature ionic conductivity fails to exceed 3.2 mS/cm.",
            source_doc_id="doc-skeptic",
            source_url="https://mock-skeptic-journal.org/electrolyte-limits",
            source_title="Electrolyte Limitations Review",
            passage_snippet="Sulfide systems suffer severe degradation, capping room-temperature conductivity at 3.2 mS/cm.",
            confidence_score=0.87,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Sulfide", "ionic conductivity"],
        )
        claims = self.claims + [conflicting_claim]
        clusters = self.clusterer.cluster(claims, self.sub_queries, self.topic)
        total_discrepancies = sum(len(c.discrepancies) for c in clusters)
        self.assertGreaterEqual(total_discrepancies, 1)

    def test_consensus_single_domain_not_corroborated(self):
        """Test that near-duplicate claims from the same domain do NOT emit a CorroboratedClaimGroup."""
        claim_a = ExtractedClaim(
            claim_id="clm-single-domain-1",
            text="Solid-state battery cells achieve commercial energy density of 500 Wh/kg.",
            source_doc_id="doc-domain-01",
            source_url="https://domain.com/a",
            source_title="Domain Article A",
            passage_snippet="Testing confirmed energy density of 500 Wh/kg.",
            confidence_score=0.92,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["solid-state battery", "energy density"],
            secondary_urls=[],
        )
        claim_b = ExtractedClaim(
            claim_id="clm-single-domain-2",
            text="Solid-state battery cells achieve commercial energy density of 500 Wh/kg in testing.",
            source_doc_id="doc-domain-02",
            source_url="https://domain.com/b",
            source_title="Domain Article B",
            passage_snippet="Production runs demonstrated energy density of 500 Wh/kg.",
            confidence_score=0.90,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["solid-state battery", "energy density"],
            secondary_urls=[],
        )
        # Direct consensus evaluation
        direct_groups = self.clusterer._detect_consensus([claim_a, claim_b])
        self.assertEqual(
            len(direct_groups),
            0,
            "Direct _detect_consensus must not emit CorroboratedClaimGroup for single domain",
        )

        # Full clustering pipeline evaluation with companion claim in another facet to maintain 2 sections
        companion = ExtractedClaim(
            claim_id="clm-comp-econ",
            text="Manufacturing capital expenditure exceeds 150 million dollars for pilot lines.",
            source_doc_id="doc-comp",
            source_url="https://mock-manufacturing.org/capex",
            source_title="Manufacturing Capex",
            passage_snippet="Capital expenditure exceeds 150 million dollars.",
            confidence_score=0.85,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["capital expenditure"],
        )
        clusters = self.clusterer.cluster([claim_a, claim_b, companion], self.sub_queries, self.topic)
        total_corroborated = sum(len(c.corroborated_claims) for c in clusters)
        self.assertEqual(
            total_corroborated,
            0,
            "Claims originating from the same domain must NOT emit CorroboratedClaimGroup in any cluster",
        )
        for cluster in clusters:
            self.assertEqual(len(cluster.corroborated_claims), 0)

    def test_consensus_cross_domain_is_corroborated(self):
        """Test that near-duplicate claims from distinct domains DO emit a CorroboratedClaimGroup."""
        claim_a = ExtractedClaim(
            claim_id="clm-cross-domain-1",
            text="Solid-state battery cells achieve commercial energy density of 500 Wh/kg.",
            source_doc_id="doc-domain-a",
            source_url="https://domainA.com/a",
            source_title="Domain A Report",
            passage_snippet="Testing confirmed energy density of 500 Wh/kg.",
            confidence_score=0.92,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["solid-state battery", "energy density"],
            secondary_urls=[],
        )
        claim_b = ExtractedClaim(
            claim_id="clm-cross-domain-2",
            text="Solid-state battery cells achieve commercial energy density of 500 Wh/kg in testing.",
            source_doc_id="doc-domain-b",
            source_url="https://domainB.com/b",
            source_title="Domain B Report",
            passage_snippet="Production runs demonstrated energy density of 500 Wh/kg.",
            confidence_score=0.90,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["solid-state battery", "energy density"],
            secondary_urls=[],
        )
        # Direct consensus evaluation
        direct_groups = self.clusterer._detect_consensus([claim_a, claim_b])
        self.assertGreaterEqual(
            len(direct_groups),
            1,
            "Direct _detect_consensus must emit CorroboratedClaimGroup for distinct domains",
        )
        self.assertGreaterEqual(
            len(direct_groups[0].independent_domains),
            2,
            "Direct CorroboratedClaimGroup must have >= 2 independent domains",
        )

        # Full clustering pipeline evaluation
        companion = ExtractedClaim(
            claim_id="clm-comp-econ",
            text="Manufacturing capital expenditure exceeds 150 million dollars for pilot lines.",
            source_doc_id="doc-comp",
            source_url="https://mock-manufacturing.org/capex",
            source_title="Manufacturing Capex",
            passage_snippet="Capital expenditure exceeds 150 million dollars.",
            confidence_score=0.85,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["capital expenditure"],
        )
        clusters = self.clusterer.cluster([claim_a, claim_b, companion], self.sub_queries, self.topic)
        all_groups = [g for c in clusters for g in c.corroborated_claims]
        self.assertGreaterEqual(
            len(all_groups),
            1,
            "Cross-domain near-duplicate claims MUST emit at least one CorroboratedClaimGroup",
        )
        group = all_groups[0]
        self.assertGreaterEqual(
            len(group.independent_domains),
            2,
            f"CorroboratedClaimGroup must have >= 2 independent domains, got {group.independent_domains}",
        )
        domains_lower = [d.lower() for d in group.independent_domains]
        self.assertIn("domaina.com", domains_lower)
        self.assertIn("domainb.com", domains_lower)

    def test_discrepancy_numerical_unrelated_entities_not_flagged(self):
        """Test that quantitative claims with disjoint entities sharing unit % are NOT flagged as a numerical conflict."""
        claim_margin = ExtractedClaim(
            claim_id="clm-margin-35",
            text="Gross margin reached 35% across commercial manufacturing divisions.",
            source_doc_id="doc-margin-01",
            source_url="https://mock-finance.org/margins",
            source_title="Financial Report",
            passage_snippet="Gross margin reached 35% across commercial manufacturing divisions.",
            confidence_score=0.91,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Gross margin"],
        )
        claim_tax = ExtractedClaim(
            claim_id="clm-tax-21",
            text="Corporate tax rate was 21% for domestic operations.",
            source_doc_id="doc-tax-01",
            source_url="https://mock-tax.gov/corporate",
            source_title="Tax Policy",
            passage_snippet="Corporate tax rate was 21% for domestic operations.",
            confidence_score=0.89,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Corporate tax rate"],
        )
        # Direct discrepancy evaluation
        direct_discrepancies = self.clusterer._detect_discrepancies([claim_margin, claim_tax])
        self.assertEqual(
            len(direct_discrepancies),
            0,
            "Disjoint entities sharing unit % must not produce discrepancies in _detect_discrepancies",
        )

        # Full clustering pipeline evaluation
        companion = ExtractedClaim(
            claim_id="clm-comp-tech",
            text="Sulfide solid electrolyte room-temperature ionic conductivity reached 12 mS/cm.",
            source_doc_id="doc-comp-tech",
            source_url="https://mock-science.org/tech",
            source_title="Tech Study",
            passage_snippet="Sulfide conductivity reached 12 mS/cm.",
            confidence_score=0.92,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Sulfide"],
        )
        clusters = self.clusterer.cluster([claim_margin, claim_tax, companion], self.sub_queries, self.topic)
        total_num_variations = sum(
            len([d for d in c.discrepancies if d.discrepancy_type == "NUMERICAL_VARIATION"])
            for c in clusters
        )
        self.assertEqual(
            total_num_variations,
            0,
            "Quantitative claims on unrelated entities must NOT be flagged as numerical discrepancies",
        )

    def test_discrepancy_numerical_unit_synonyms_flagged(self):
        """Test that quantitative claims on the same entity with variance are correctly flagged as NUMERICAL_VARIATION."""
        claim_high = ExtractedClaim(
            claim_id="clm-density-500",
            text="Energy density reached 500 Wh/kg in advanced solid-state prototype cells.",
            source_doc_id="doc-energy-01",
            source_url="https://mock-science.org/density-high",
            source_title="High Density Report",
            passage_snippet="Testing showed energy density reached 500 Wh/kg.",
            confidence_score=0.94,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Energy density"],
        )
        claim_low = ExtractedClaim(
            claim_id="clm-density-350",
            text="Energy density was capped at 350 Wh/kg under commercial operating conditions.",
            source_doc_id="doc-energy-02",
            source_url="https://mock-industry.org/density-low",
            source_title="Commercial Limits Report",
            passage_snippet="Commercial limits showed energy density was capped at 350 Wh/kg.",
            confidence_score=0.90,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Energy density"],
        )
        # Direct discrepancy evaluation
        direct_discrepancies = self.clusterer._detect_discrepancies([claim_high, claim_low])
        num_variations_direct = [d for d in direct_discrepancies if d.discrepancy_type == "NUMERICAL_VARIATION"]
        self.assertGreaterEqual(
            len(num_variations_direct),
            1,
            "Direct _detect_discrepancies must flag NUMERICAL_VARIATION for same entity with > 15% diff",
        )
        self.assertEqual(num_variations_direct[0].entity, "Energy density")

        # Full clustering pipeline evaluation
        companion = ExtractedClaim(
            claim_id="clm-comp-econ",
            text="Manufacturing capital expenditure exceeds 150 million dollars for pilot lines.",
            source_doc_id="doc-comp",
            source_url="https://mock-manufacturing.org/capex",
            source_title="Manufacturing Capex",
            passage_snippet="Capital expenditure exceeds 150 million dollars.",
            confidence_score=0.85,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["capital expenditure"],
        )
        clusters = self.clusterer.cluster([claim_high, claim_low, companion], self.sub_queries, self.topic)
        all_discrepancies = [d for c in clusters for d in c.discrepancies]
        num_variations = [d for d in all_discrepancies if d.discrepancy_type == "NUMERICAL_VARIATION"]
        self.assertGreaterEqual(
            len(num_variations),
            1,
            "Clustering pipeline must emit at least one NUMERICAL_VARIATION discrepancy",
        )
        disc = num_variations[0]
        self.assertEqual(disc.entity, "Energy density")
        self.assertIn("wh/kg", disc.explanation.lower())

        # Unit synonym alias verification (% vs percent) when UNIT_ALIASES is active
        try:
            from research_synthesis.synthesis import cluster as cluster_mod
        except ImportError:
            from src.research_synthesis.synthesis import cluster as cluster_mod

        if hasattr(cluster_mod, "UNIT_ALIASES"):
            claim_pct_a = ExtractedClaim(
                claim_id="clm-silicon-35",
                text="Silicon anode volumetric expansion reached 35% during continuous cycling.",
                source_doc_id="doc-silicon-01",
                source_url="https://mock-battery-lab.org/anode-expansion",
                source_title="Anode Silicon Expansion Study",
                passage_snippet="Testing showed silicon anode volumetric expansion reached 35%.",
                confidence_score=0.92,
                claim_type=ClaimType.QUANTITATIVE,
                entities=["Silicon anode expansion"],
            )
            claim_pct_b = ExtractedClaim(
                claim_id="clm-silicon-20",
                text="Silicon anode volumetric expansion was limited to 20 percent in composite electrodes.",
                source_doc_id="doc-silicon-02",
                source_url="https://mock-battery-lab.org/composite-electrode",
                source_title="Composite Electrode Performance",
                passage_snippet="Testing showed silicon anode volumetric expansion was limited to 20 percent.",
                confidence_score=0.88,
                claim_type=ClaimType.QUANTITATIVE,
                entities=["Silicon anode expansion"],
            )
            synonym_discrepancies = self.clusterer._detect_discrepancies([claim_pct_a, claim_pct_b])
            num_var_syn = [d for d in synonym_discrepancies if d.discrepancy_type == "NUMERICAL_VARIATION"]
            self.assertGreaterEqual(
                len(num_var_syn),
                1,
                "Unit synonyms (% vs percent) on same entity must be detected as NUMERICAL_VARIATION",
            )


# ============================================================================
# Suite 2: Extractive Synthesizer Unit Tests (F11)
# ============================================================================

class TestExtractiveSynthesizer(unittest.TestCase):
    """Unit tests for ExtractiveSynthesizer, CitationRegistry, and MMR."""

    def setUp(self):
        self.synthesizer = ExtractiveSynthesizer()
        self.claims = make_sample_claims()
        self.sub_queries = make_sample_subqueries()
        self.topic = "Next-Generation Solid-State Battery Commercialization"
        self.clusterer = ThematicClusterer(min_sections=2, max_sections=5)
        self.clusters = self.clusterer.cluster(self.claims, self.sub_queries, self.topic)

    def test_citation_registry_order_of_appearance(self):
        registry = CitationRegistry()
        indices_1 = registry.register_claim(self.claims[0])
        self.assertEqual(indices_1, [1])

        indices_2 = registry.register_claim(self.claims[1])
        self.assertEqual(indices_2, [2])

        # Repeat registration of first claim returns existing index [1]
        indices_1_again = registry.register_claim(self.claims[0])
        self.assertEqual(indices_1_again, [1])

        # Marker formatting
        self.assertEqual(registry.format_citation_marker([1]), "[1]")
        self.assertEqual(registry.format_citation_marker([1, 2]), "[1, 2]")

    def test_select_claims_mmr(self):
        selected = self.synthesizer.select_claims_mmr(
            claims=self.claims,
            query="solid state battery energy density and manufacturing",
            k=3,
        )
        self.assertEqual(len(selected), 3)
        self.assertEqual(len({c.claim_id for c in selected}), 3, "Selected claims must be unique")

    def test_generate_executive_summary(self):
        registry = CitationRegistry()
        exec_summary = self.synthesizer.generate_executive_summary(
            topic=self.topic,
            clusters=self.clusters,
            registry=registry,
        )
        self.assertGreaterEqual(len(exec_summary.split()), 30, "Executive summary must have >= 30 words")
        self.assertGreaterEqual(len(exec_summary), 80, "Executive summary must have >= 80 chars")
        self.assertIn("[1]", exec_summary, "Executive summary must embed inline citations")

    def test_generate_thematic_sections(self):
        registry = CitationRegistry()
        sections = []
        for idx, cl in enumerate(self.clusters, start=1):
            sec = self.synthesizer.generate_thematic_section(cl, idx, registry)
            sections.append(sec)
        self.assertGreaterEqual(len(sections), 2)
        for sec in sections:
            self.assertGreaterEqual(len(sec.narrative.split()), 20, "Section narrative must have >= 20 words")
            self.assertTrue(sec.section_id.startswith("sec-") or sec.section_id.startswith("SEC-"))
            self.assertGreaterEqual(len(sec.title), 3)

    def test_generate_key_takeaways(self):
        registry = CitationRegistry()
        takeaways = self.synthesizer.generate_key_takeaways(self.claims, registry)
        self.assertGreaterEqual(len(takeaways), 3, "Must produce >= 3 key takeaways")
        for kt in takeaways:
            self.assertGreaterEqual(len(kt.text.split()), 5, "Takeaway must have >= 5 words")

    def test_bibliography_construction(self):
        brief = self.synthesizer.synthesize(
            topic=self.topic,
            clusters=self.clusters,
            sub_queries=self.sub_queries,
        )
        self.assertGreaterEqual(len(brief.sources), 2)
        for src in brief.sources:
            self.assertTrue(src.source_id)
            self.assertTrue(src.url.startswith("http"))
            self.assertGreaterEqual(len(src.title), 2)
            self.assertGreaterEqual(len(src.snippet), 15)
            self.assertGreaterEqual(len(src.snippet.split()), 5)

    def test_strict_referential_integrity(self):
        brief = self.synthesizer.synthesize(
            topic=self.topic,
            clusters=self.clusters,
            sub_queries=self.sub_queries,
        )
        self.assertGreaterEqual(len(brief.sources), 2, "Brief must contain >= 2 sources")
        validator = ResearchBriefValidator(strict=True)
        res = validator.validate(brief.to_dict())
        self.assertTrue(res.is_valid, f"Brief failed strict validation: {res.errors}")


# ============================================================================
# Suite 3: Formatters & Serializers Unit Tests (F12, F13)
# ============================================================================

class TestFormattersAndSerializers(unittest.TestCase):
    """Unit tests for MarkdownFormatter and JSONSchemaSerializer."""

    def setUp(self):
        synthesizer = ExtractiveSynthesizer()
        claims = make_sample_claims()
        sub_queries = make_sample_subqueries()
        topic = "Next-Generation Solid-State Battery Commercialization"
        clusters = ThematicClusterer(min_sections=2, max_sections=5).cluster(claims, sub_queries, topic)
        self.brief = synthesizer.synthesize(topic=topic, clusters=clusters, sub_queries=sub_queries)

    def test_markdown_formatter_structure(self):
        formatter = MarkdownFormatter()
        md = formatter.format(self.brief)
        self.assertIn("# Research Brief:", md)
        self.assertIn("## Executive Summary", md)
        self.assertIn("## Key Takeaways", md)
        self.assertIn("## Sources & Citations", md)
        self.assertIn("[1]", md)

    def test_json_schema_serializer_validity(self):
        serializer = JSONSchemaSerializer()
        json_data = serializer.serialize_to_dict(self.brief)
        self.assertIn("brief_id", json_data)
        self.assertIn("executive_summary", json_data)
        self.assertIn("thematic_sections", json_data)
        self.assertIn("key_takeaways", json_data)
        self.assertIn("sources", json_data)
        self.assertIn("metadata", json_data)

    def test_research_brief_validator_pass(self):
        validator = ResearchBriefValidator(strict=False)
        result = validator.validate(self.brief.to_dict())
        self.assertTrue(result.is_valid, f"Validation failed: {result.errors}")

    def test_roundtrip_serialization(self):
        brief_dict = self.brief.to_dict()
        reconstructed = ResearchBrief.from_dict(brief_dict)
        self.assertEqual(reconstructed.brief_id, self.brief.brief_id)
        self.assertEqual(reconstructed.topic, self.brief.topic)
        self.assertEqual(len(reconstructed.thematic_sections), len(self.brief.thematic_sections))
        self.assertEqual(len(reconstructed.sources), len(self.brief.sources))

    def test_html_formatter_rendering(self):
        html = self.brief.to_html()
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<title>Research Brief:", html)
        self.assertIn("Executive Summary</h2>", html)
        self.assertIn("Key Takeaways</h2>", html)
        self.assertIn("Sources & Citations</h2>", html)
        self.assertIn('class="citation"', html)
        self.assertIn('class="badge"', html)

    def test_discrepancy_matrix_rendering_markdown_and_html(self):
        """Test that sections with discrepancies render formatted variance tables in Markdown and HTML."""
        from research_synthesis.models import DiscrepancyGroup

        disc = DiscrepancyGroup(
            discrepancy_id="disc-test-01",
            entity="Energy Density",
            discrepancy_type="NUMERICAL_VARIATION",
            claim_a_id="clm-test-a",
            claim_b_id="clm-test-b",
            claim_a_text="Solid-state cells achieve 500 Wh/kg in laboratory testing [1].",
            claim_b_text="Commercial prototype cells operate at 380 Wh/kg [2].",
            source_a_url="https://source-a.org/spec",
            source_b_url="https://source-b.org/spec",
            explanation="Numerical variation on Wh/kg: 500.0 vs 380.0 (31.6% difference).",
        )

        test_brief = ResearchBrief(
            brief_id="brief-disc-test",
            topic="Solid-State Battery Energy Density Analysis",
            executive_summary=(
                "An integrated assessment of solid-state battery energy density demonstrates substantial empirical variance "
                "across published literature and laboratory measurements [1, 2]. While advanced sulfide electrolyte cells achieve "
                "exceptional laboratory performance, commercial prototypes exhibit lower operational ceilings that dictate initial "
                "market deployment trajectories across consumer electronics and electric mobility sectors."
            ),
            key_takeaways=[
                KeyTakeaway(text="Laboratory testing demonstrates 500 Wh/kg ceiling [1].", citation_indices=[1]),
                KeyTakeaway(text="Production yield constraints limit initial scaling to 380 Wh/kg [2].", citation_indices=[2]),
                KeyTakeaway(text="Electrolyte conductivity remains a critical deployment dependency.", citation_indices=[]),
            ],
            thematic_sections=[
                ThematicSection(
                    section_id="sec-01",
                    title="Energy Density and Volumetric Performance",
                    narrative=(
                        "Evaluation of solid-state cathode loadings demonstrates high theoretical energy densities alongside practical "
                        "prototype limits observed across cell evaluations [1, 2]. Notably, conflicting empirical evidence emerged regarding "
                        "Energy Density: Numerical variation on Wh/kg: 500.0 vs 380.0 (31.6% difference). Specifically, initial findings state "
                        "that laboratory cells reach 500 Wh/kg [1], whereas commercial reports indicate that stabilized prototypes deliver 380 Wh/kg [2]."
                    ),
                    citation_indices=[1, 2],
                    claim_ids=["clm-test-a", "clm-test-b"],
                    key_findings=[
                        "Laboratory cells reach 500 Wh/kg under optimized conditions [1].",
                        "Data Variance (Energy Density): Numerical variation on Wh/kg: 500.0 vs 380.0 ([1] vs [2]).",
                    ],
                    discrepancies=[disc],
                ),
                ThematicSection(
                    section_id="sec-02",
                    title="Industrial Scaling and Manufacturing Viability",
                    narrative=(
                        "Manufacturing pilot lines demonstrate progressive yield stabilization across sulfide and oxide separator lines, "
                        "reducing micro-crack defect frequencies during dry-room pouch assembly [1]. Continuous slot-die coating and roll-to-roll "
                        "calendaring protocols enable reproducible electrolyte membrane fabrication meeting industrial automotive tolerance levels."
                    ),
                    citation_indices=[1],
                    claim_ids=["clm-test-c"],
                    key_findings=["Pilot lines achieve baseline mechanical integrity [1]."],
                ),
            ],
            sources=[
                SourceCitation(
                    citation_index=1,
                    source_id="SRC-01",
                    title="Solid-State Laboratory Benchmarks",
                    url="https://source-a.org/spec",
                    snippet="Laboratory testing of sulfide solid-state cells achieved 500 Wh/kg density.",
                ),
                SourceCitation(
                    citation_index=2,
                    source_id="SRC-02",
                    title="Commercial Prototype Production Report",
                    url="https://source-b.org/spec",
                    snippet="Initial commercial prototypes demonstrated stabilized density of 380 Wh/kg.",
                ),
            ],
            sub_queries=[
                "Solid-state battery energy density benchmarks",
                "Solid-state battery manufacturing and commercial scaling",
            ],
        )

        # 1. Verify Markdown Formatter renders Data Variance table
        md = test_brief.to_markdown()
        self.assertIn("**Data Variance & Conflicting Claims**:", md)
        self.assertIn("| Entity / Metric | Conflict Type | Claim A | Claim B | Variance Analysis |", md)
        self.assertIn("Energy Density", md)
        self.assertIn("`NUMERICAL_VARIATION`", md)
        self.assertIn("500 Wh/kg", md)
        self.assertIn("380 Wh/kg", md)

        # 2. Verify HTML Formatter renders discrepancy table and CSS classes
        html = test_brief.to_html()
        self.assertIn("discrepancy-box", html)
        self.assertIn("discrepancy-table", html)
        self.assertIn("Data Variance &amp; Conflicting Claims", html)
        self.assertIn("NUMERICAL_VARIATION", html)
        self.assertIn("31.6% difference", html)

        # 3. Verify Schema & Strict Referential Integrity
        validator = ResearchBriefValidator(strict=True)
        res = validator.validate(test_brief.to_dict())
        self.assertTrue(res.is_valid, f"Discrepancy brief must satisfy strict validation: {res.errors}")


# ============================================================================
# Suite 4: Research Pipeline End-to-End Integration Tests
# ============================================================================

class TestResearchPipelineIntegration(unittest.TestCase):
    """End-to-end integration tests executing ResearchPipeline against Mock Corpus."""

    @classmethod
    def setUpClass(cls):
        cls.manifest_path = MANIFEST_PATH
        cls.validator = ResearchBriefValidator(strict=False)
        cls.strict_validator = ResearchBriefValidator(strict=True)

    def test_pipeline_default_initialization(self):
        pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=self.manifest_path)
        self.assertIsNotNone(pipeline.decomposer)
        self.assertIsNotNone(pipeline.retriever)
        self.assertIsNotNone(pipeline.chunker)
        self.assertIsNotNone(pipeline.bm25_filter)
        self.assertIsNotNone(pipeline.deduplicator)
        self.assertIsNotNone(pipeline.claim_extractor)
        self.assertIsNotNone(pipeline.clusterer)
        self.assertIsNotNone(pipeline.synthesizer)

    def test_pipeline_solid_state_battery(self):
        pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=self.manifest_path)
        topic = "Next-Generation Solid-State Battery Commercialization: Energy Density Roadmaps, Solid Electrolytes, and Manufacturing Scalability"
        brief = pipeline.run(topic)

        self.assertIsInstance(brief, ResearchBrief)
        self.assertEqual(brief.topic, topic)
        self.assertGreaterEqual(len(brief.thematic_sections), 2)
        self.assertLessEqual(len(brief.thematic_sections), 5)
        self.assertGreaterEqual(len(brief.key_takeaways), 3)
        self.assertGreaterEqual(len(brief.sources), 2)

        # Validate schema and invariants
        res = self.validator.validate(brief.to_dict())
        self.assertTrue(res.is_valid, f"Solid-state battery brief validation failed: {res.errors}")

        # Assert substantive word count >= 120 words
        exec_words = len(brief.executive_summary.split())
        sec_words = sum(len(s.narrative.split()) for s in brief.thematic_sections)
        self.assertGreaterEqual(exec_words + sec_words, 120)

    def test_pipeline_supply_chain_reshoring(self):
        pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=self.manifest_path)
        topic = "Global Supply Chain Re-Shoring and Friend-Shoring Dynamics: Macroeconomic Inflation Impacts and Industrial Policy Interventions"
        brief = pipeline.run(topic)

        self.assertIsInstance(brief, ResearchBrief)
        res = self.validator.validate(brief.to_dict())
        self.assertTrue(res.is_valid, f"Supply chain brief validation failed: {res.errors}")

    def test_pipeline_little_ice_age(self):
        pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=self.manifest_path)
        topic = "The Little Ice Age Climate Shocks in 17th Century Europe: Agrarian Output Collapses, Famine Cycles, and Social Upheaval"
        brief = pipeline.run(topic)

        self.assertIsInstance(brief, ResearchBrief)
        res = self.validator.validate(brief.to_dict())
        self.assertTrue(res.is_valid, f"Little Ice Age brief validation failed: {res.errors}")

    def test_pipeline_edge_microplastics(self):
        pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=self.manifest_path)
        topic = "Microplastic Bioaccumulation in Agricultural Soil Ecosystems: Trophic Transfer Mechanisms and Emerging EU Regulatory Directives"
        brief = pipeline.run(topic)

        self.assertIsInstance(brief, ResearchBrief)
        res = self.validator.validate(brief.to_dict())
        self.assertTrue(res.is_valid, f"Microplastics brief validation failed: {res.errors}")


# ============================================================================
# Suite 5: Pipeline Graceful Fallback & Boundary Tests
# ============================================================================

class TestPipelineGracefulFallbacks(unittest.TestCase):
    """Boundary and degradation testing verifying no unhandled exceptions."""

    def setUp(self):
        self.validator = ResearchBriefValidator(strict=False)

    def test_empty_retrieval_graceful_fallback(self):
        empty_retriever = MockWebRetrievalClient(corpus_dict={})
        pipeline = ResearchPipeline(retriever=empty_retriever, mode="mock")
        topic = "Completely Obscure Untracked Research Topic Without Any Fixtures"
        brief = pipeline.run(topic)

        self.assertIsInstance(brief, ResearchBrief)
        self.assertGreaterEqual(len(brief.thematic_sections), 2)
        self.assertGreaterEqual(len(brief.key_takeaways), 3)
        self.assertGreaterEqual(len(brief.sources), 2)
        res = self.validator.validate(brief.to_dict())
        self.assertTrue(res.is_valid, f"Empty retrieval brief must be schema valid: {res.errors}")

    def test_zero_claims_fallback(self):
        class DummyEmptyExtractor:
            def extract_claims(self, passages):
                return []

        pipeline = ResearchPipeline(
            claim_extractor=DummyEmptyExtractor(),
            mode="mock",
            corpus_manifest_path=MANIFEST_PATH,
        )
        topic = "Next-Generation Solid-State Battery Commercialization"
        brief = pipeline.run(topic)

        self.assertIsInstance(brief, ResearchBrief)
        res = self.validator.validate(brief.to_dict())
        self.assertTrue(res.is_valid, f"Zero claims fallback brief must be schema valid: {res.errors}")

    def test_minimal_corpus_fallback(self):
        minimal_corpus = {
            "https://tiny-source.org/single-doc": {
                "title": "Minimal Study Document",
                "body": "Solid state batteries represent a technological milestone with 500 Wh/kg density demonstrated in late 2025.",
            }
        }
        mini_client = MockWebRetrievalClient(corpus_dict=minimal_corpus)
        pipeline = ResearchPipeline(retriever=mini_client, mode="mock")
        topic = "Next-Generation Solid-State Battery Commercialization"
        brief = pipeline.run(topic)

        self.assertIsInstance(brief, ResearchBrief)
        self.assertGreaterEqual(len(brief.thematic_sections), 2)
        self.assertGreaterEqual(len(brief.key_takeaways), 3)
        res = self.validator.validate(brief.to_dict())
        self.assertTrue(res.is_valid, f"Minimal corpus brief must be schema valid: {res.errors}")

    def test_degenerate_blank_topic_fallback(self):
        pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=MANIFEST_PATH)
        brief = pipeline.run("   ")
        self.assertIsInstance(brief, ResearchBrief)
        self.assertGreaterEqual(len(brief.thematic_sections), 2)
        res = self.validator.validate(brief.to_dict())
        self.assertTrue(res.is_valid, f"Blank topic brief must be schema valid: {res.errors}")


if __name__ == "__main__":
    unittest.main()
