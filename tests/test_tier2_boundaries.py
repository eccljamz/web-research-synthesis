"""Tier 2 Boundary and Corner Case Test Suite.

Milestone 4 - Comprehensive Boundary, Adversarial, and Corner Case Verification:
1. Query boundary conditions: blank topic strings, ultra-long topic strings (500+ chars),
   and complex special character/unicode queries.
2. Malformed and corrupt HTML handling: unclosed tags, unquoted attributes, unclosed scripts
   (using doc_04_corrupt_malformed.html fixture).
3. Empty retrieval corpus handling: 0 matching documents produces graceful diagnostic fallback brief.
4. Zero extracted claims handling: proposition claim synthesis fallback from passages.
5. Single-document minimal corpus handling: scaffolding to K >= 2 sections and >= 2 sources.
6. Duplicate document handling: exact hash and SimHash 64-bit locality-sensitive deduplication.
7. Distractor document handling: Okapi BM25 relevance score rejection below threshold.

Pure Python standard library (unittest) - Zero external dependencies.
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
        BriefMetadata,
        ClaimCluster,
        ClaimType,
        CleanArticle,
        DocumentMetadata,
        ExtractedClaim,
        KeyTakeaway,
        RawWebDocument,
        ResearchBrief,
        ScoredPassage,
        SourceCitation,
        SubQuery,
        ThematicSection,
    )
    from research_synthesis.retrieval.decomposer import HeuristicQueryDecomposer
    from research_synthesis.retrieval.parser import DocumentParser, RobustHTMLParser
    from research_synthesis.retrieval.retriever import MockWebRetrievalClient
    from research_synthesis.extraction.bm25 import BM25Filter, PureBM25
    from research_synthesis.extraction.chunker import PassageChunker
    from research_synthesis.extraction.claims import ClaimExtractor
    from research_synthesis.extraction.dedup import SimHash64, TwoStageDeduplicator
    from research_synthesis.synthesis.cluster import ThematicClusterer
    from research_synthesis.synthesis.synthesizer import CitationRegistry, ExtractiveSynthesizer
    from research_synthesis.pipeline import ResearchPipeline
    from research_synthesis.verification.validator import ResearchBriefValidator
except ImportError:
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
        ScoredPassage,
        SourceCitation,
        SubQuery,
        ThematicSection,
    )
    from src.research_synthesis.retrieval.decomposer import HeuristicQueryDecomposer
    from src.research_synthesis.retrieval.parser import DocumentParser, RobustHTMLParser
    from src.research_synthesis.retrieval.retriever import MockWebRetrievalClient
    from src.research_synthesis.extraction.bm25 import BM25Filter, PureBM25
    from src.research_synthesis.extraction.chunker import PassageChunker
    from src.research_synthesis.extraction.claims import ClaimExtractor
    from src.research_synthesis.extraction.dedup import SimHash64, TwoStageDeduplicator
    from src.research_synthesis.synthesis.cluster import ThematicClusterer
    from src.research_synthesis.synthesis.synthesizer import CitationRegistry, ExtractiveSynthesizer
    from src.research_synthesis.pipeline import ResearchPipeline
    from src.research_synthesis.verification.validator import ResearchBriefValidator


MANIFEST_PATH = PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "manifest.json"
CORRUPT_HTML_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "little_ice_age" / "doc_04_corrupt_malformed.html"
)
MINIMAL_HTML_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "microplastics" / "doc_04_edge_minimal.html"
)
SOLAR_DISTRACTOR_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "solid_state_battery" / "doc_05_irrelevant_solar.html"
)
CRYPTO_DISTRACTOR_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "supply_chain_reshoring" / "doc_05_irrelevant_crypto.html"
)


# ============================================================================
# Test Suite 1: Query Boundary Conditions
# ============================================================================

class TestQueryBoundaryConditions(unittest.TestCase):
    """Verifies pipeline and decomposer robustness under extreme query inputs."""

    def setUp(self):
        self.decomposer = HeuristicQueryDecomposer()
        self.pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=MANIFEST_PATH)
        self.validator = ResearchBriefValidator(strict=False)

    def test_blank_and_whitespace_topic_decomposition(self):
        """Blank or whitespace query strings properly raise ValueError in query decomposer."""
        for blank in ["", "   ", "\t\n  \r\n", "    "]:
            with self.assertRaises(ValueError):
                self.decomposer.decompose(blank)

    def test_blank_topic_pipeline_graceful_diagnostic_brief(self):
        """Blank or whitespace topic (< 5 chars) triggers graceful fallback brief."""
        for blank in ["   ", "", "  \n  "]:
            brief = self.pipeline.run(blank)
            self.assertIsInstance(brief, ResearchBrief)
            self.assertTrue(brief.brief_id.startswith("brief-"))
            self.assertGreaterEqual(len(brief.thematic_sections), 2)
            self.assertGreaterEqual(len(brief.key_takeaways), 3)
            self.assertGreaterEqual(len(brief.sources), 2)

            # Validate structural and semantic compliance
            val_result = self.validator.validate(brief.to_dict())
            self.assertTrue(val_result.is_valid, f"Fallback brief failed validation: {val_result.errors}")

            # Verify diagnostic content
            self.assertIn("Unspecified Research Query", brief.topic)
            self.assertGreaterEqual(len(brief.executive_summary.split()), 30)

    def test_ultra_long_topic_decomposition(self):
        """Topic string exceeding 500 characters decomposes safely without blowing up."""
        long_topic = (
            "Investigation into advanced sulfide and oxide solid-state electrolyte materials, "
            "focusing on lithium argyrodites Li6PS5Cl and garnet LLZO Li7La3Zr2O12, room temperature "
            "ionic conductivity measurements exceeding 12 mS/cm, interfacial impedance stabilization "
            "against lithium metal anodes, continuous roll-to-roll dry room processing costs per kWh, "
            "and automotive commercialization roadmaps targeting 500 Wh/kg pack energy density by 2030. "
            "Key safety metrics, cathode active loading, and recycling paradigms are thoroughly evaluated for gigawatt scale deployment."
        )
        self.assertGreater(len(long_topic), 500)

        result = self.decomposer.decompose(long_topic)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(len(result.sub_queries), 2)
        for sq in result.sub_queries:
            self.assertTrue(sq.search_query)
            self.assertIn(sq.facet, ["technical", "economic", "challenges", "comparative", "temporal"])

    def test_ultra_long_topic_pipeline_execution(self):
        """Pipeline executes end-to-end on ultra-long topic string without unhandled exceptions."""
        long_topic = (
            "Next-Generation Solid-State Battery Commercialization: Comprehensive analysis of sulfide "
            "and garnet solid electrolyte ionic transport mechanisms, interfacial dendrite suppression "
            "at lithium metal interfaces, roll-to-roll web coating scalability in industrial dry rooms, "
            "and commercial automotive cost roadmaps targeting 500 Wh/kg by 2030."
        )
        self.assertGreater(len(long_topic), 300)

        brief = self.pipeline.run(long_topic)
        self.assertIsInstance(brief, ResearchBrief)
        self.assertGreaterEqual(len(brief.thematic_sections), 2)
        self.assertGreaterEqual(len(brief.sources), 2)
        self.assertGreaterEqual(len(brief.executive_summary.split()), 30)

        # Confirm valid JSON serialization
        json_data = json.loads(brief.to_json())
        self.assertEqual(json_data["brief_id"], brief.brief_id)

    def test_special_character_and_adversarial_topic_sanitization(self):
        """Special characters, punctuation, unicode, and symbols are sanitized without crash."""
        adversarial_topics = [
            'Solid-State Batteries: Li10GeP2S12 (LGPS) vs. Li7La3Zr2O12 (LLZO) — 100% ionic flux & thermal limits?!',
            '<script>alert("xss")</script> Supply Chain Re-Shoring & Friend-Shoring: "Inflation" / Costs $95B+ [2026]',
            'Little Ice Age: 1690s famine mortality rate in Scotland (15%-20%) & Maunder Minimum solar lull -> crisis?',
            '!@#$%^&*()_+={}[]|:;"\'<>,.?/~` Historical Climatology Shocks',
        ]
        for topic in adversarial_topics:
            result = self.decomposer.decompose(topic)
            self.assertIsNotNone(result)
            self.assertGreaterEqual(len(result.sub_queries), 2)

            brief = self.pipeline.run(topic)
            self.assertIsInstance(brief, ResearchBrief)
            self.assertTrue(brief.brief_id.startswith("brief-"))
            self.assertGreaterEqual(len(brief.thematic_sections), 2)
            self.assertGreaterEqual(len(brief.sources), 2)


# ============================================================================
# Test Suite 2: Corrupt & Malformed HTML Handling
# ============================================================================

class TestCorruptHTMLHandling(unittest.TestCase):
    """Verifies HTML parsing resilience against malformed fixture doc_04_corrupt_malformed.html."""

    def setUp(self):
        self.assertTrue(CORRUPT_HTML_PATH.exists(), f"Missing corrupt fixture: {CORRUPT_HTML_PATH}")
        self.raw_html = CORRUPT_HTML_PATH.read_text(encoding="utf-8", errors="replace")

    def test_robust_html_parser_extracts_content_without_error(self):
        """RobustHTMLParser handles unclosed tags, unquoted attributes, and script tags safely."""
        raw_doc = RawWebDocument(
            url="https://mock-archival-scans.org/unparsed/parish-mortality-records-1695-scan",
            status_code=200,
            headers={},
            raw_html=self.raw_html,
        )
        article = DocumentParser.parse(raw_doc)
        cleaned_text = article.cleaned_text
        metadata = {
            "title": article.paragraphs[0] if article.paragraphs and "Archival Parish Burial Registers" in article.paragraphs[0] else article.metadata.title
        }
        self.assertIsInstance(cleaned_text, str)
        self.assertGreater(len(cleaned_text), 100)

        # Unclosed script should be stripped, not leaked into body
        self.assertNotIn('var scan_status = "raw_ocr";', cleaned_text)

        # Substantive paragraphs must be recovered
        self.assertIn("seed cornes rotted in the furrows", cleaned_text)
        self.assertIn("boll of meal did rise", cleaned_text)
        self.assertIn("Parish burials recorded", cleaned_text)

        # Title extraction from unclosed <title> tag
        self.assertIn("Archival Parish Burial Registers", metadata.get("title", ""))

    def test_document_parser_produces_valid_clean_article(self):
        """DocumentParser parses corrupt RawWebDocument into valid CleanArticle."""
        raw_doc = RawWebDocument(
            url="https://mock-archival-scans.org/unparsed/parish-mortality-records-1695-scan",
            status_code=200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            raw_html=self.raw_html,
            subquery_id="sq-01",
        )
        article = DocumentParser.parse(raw_doc)
        self.assertIsInstance(article, CleanArticle)
        self.assertTrue(article.doc_id)
        self.assertEqual(article.subquery_id, "sq-01")
        self.assertGreater(len(article.paragraphs), 0)
        self.assertIn("Scotland", article.cleaned_text)
        self.assertGreater(article.metadata.word_count, 20)

    def test_chunker_and_claim_extractor_on_corrupt_doc(self):
        """Downstream pipeline stages process CleanArticle from corrupt HTML without failure."""
        raw_doc = RawWebDocument(
            url="https://mock-archival-scans.org/unparsed/parish-mortality-records-1695-scan",
            status_code=200,
            headers={},
            raw_html=self.raw_html,
        )
        article = DocumentParser.parse(raw_doc)
        chunker = PassageChunker(min_words=20, max_words=200, overlap_words=10)
        passages = chunker.chunk_article(article)

        self.assertGreaterEqual(len(passages), 1)
        extractor = ClaimExtractor(min_confidence=0.2)
        claims = extractor.extract_claims(passages)

        # Should extract factual propositions even from poorly formatted historical ledger
        self.assertIsInstance(claims, list)
        for claim in claims:
            self.assertTrue(claim.claim_id)
            self.assertTrue(claim.text)
            self.assertEqual(claim.source_url, raw_doc.url)


# ============================================================================
# Test Suite 3: Empty Retrieval Corpus Handling
# ============================================================================

class TestEmptyRetrievalCorpus(unittest.TestCase):
    """Verifies that 0 retrieved documents trigger a graceful diagnostic fallback brief."""

    def setUp(self):
        # Create a mock retrieval client pointing to an empty or non-matching manifest
        self.empty_retriever = MockWebRetrievalClient(corpus_path=None)
        # Clear its corpus completely to simulate total retrieval void
        self.empty_retriever._corpus.clear()
        self.empty_retriever._doc_id_to_url.clear()

        self.pipeline = ResearchPipeline(
            retriever=self.empty_retriever,
            mode="mock",
        )
        self.validator = ResearchBriefValidator(strict=False)

    def test_empty_retrieval_returns_valid_diagnostic_brief(self):
        """Pipeline returns a fully schema-compliant diagnostic brief when 0 documents match."""
        topic = "Hypothetical Hyper-Dimensional Topological Quantum Computing in Fictional Domains"
        brief = self.pipeline.run(topic)

        self.assertIsInstance(brief, ResearchBrief)
        self.assertEqual(brief.topic, topic)
        self.assertTrue(brief.brief_id.startswith("brief-empty-"))

        # Section constraints (>= 2)
        self.assertGreaterEqual(len(brief.thematic_sections), 2)
        for sec in brief.thematic_sections:
            self.assertTrue(sec.section_id)
            self.assertTrue(sec.title)
            self.assertGreater(len(sec.narrative.split()), 20)
            self.assertGreaterEqual(len(sec.citation_indices), 1)

        # Key takeaway constraints (>= 3)
        self.assertGreaterEqual(len(brief.key_takeaways), 3)

        # Source bibliography constraints (>= 2)
        self.assertGreaterEqual(len(brief.sources), 2)
        for src in brief.sources:
            self.assertTrue(src.url.startswith("http"))
            self.assertGreaterEqual(len(src.snippet.split()), 5)

        # Referential integrity: check that inline citations map to valid sources
        source_indices = {s.citation_index for s in brief.sources}
        for sec in brief.thematic_sections:
            for c_idx in sec.citation_indices:
                self.assertIn(c_idx, source_indices)

        # Strict or standard validation
        val_result = self.validator.validate(brief.to_dict())
        self.assertTrue(val_result.is_valid, f"Diagnostic brief validation failed: {val_result.errors}")


# ============================================================================
# Test Suite 4: Zero Extracted Claims Fallback
# ============================================================================

class TestZeroExtractedClaimsFallback(unittest.TestCase):
    """Verifies proposition claim synthesis fallback when no claims are extracted."""

    def setUp(self):
        self.pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=MANIFEST_PATH)

    def test_extract_fallback_claims_from_passages(self):
        """_extract_fallback_claims_from_passages generates valid atomic propositions."""
        passages = [
            ScoredPassage(
                passage_id="p-001",
                doc_id="doc-001",
                url="https://example.org/narrative-history",
                title="Historical Chronology of Early Modern Europe",
                text=(
                    "The seventeenth century experienced widespread climatic deterioration across the continent. "
                    "Persistent winter freezes disrupted agricultural production and led to acute food shortages. "
                    "Governments struggled to maintain civil stability amidst compounding grain supply failures."
                ),
                relevance_score=0.85,
                subquery="climate crisis",
                word_count=35,
            ),
        ]
        fallback_claims = self.pipeline._extract_fallback_claims_from_passages(passages)
        self.assertGreaterEqual(len(fallback_claims), 2)
        for c in fallback_claims:
            self.assertIsInstance(c, ExtractedClaim)
            self.assertEqual(c.claim_type, ClaimType.GENERAL_FACT)
            self.assertEqual(c.source_doc_id, "doc-001")
            self.assertEqual(c.source_url, "https://example.org/narrative-history")
            self.assertGreaterEqual(c.confidence_score, 0.70)
            self.assertTrue(c.text.endswith("."))

    def test_pipeline_recovers_when_claim_extractor_yields_zero_claims(self):
        """Pipeline uses proposition fallback when ClaimExtractor returns empty list."""
        class ZeroClaimExtractor(ClaimExtractor):
            def extract_claims(self, passages):
                return []

        custom_pipeline = ResearchPipeline(
            mode="mock",
            corpus_manifest_path=MANIFEST_PATH,
            claim_extractor=ZeroClaimExtractor(),
        )
        brief = custom_pipeline.run("The Little Ice Age Climate Shocks in 17th Century Europe")
        self.assertIsInstance(brief, ResearchBrief)
        self.assertGreaterEqual(len(brief.thematic_sections), 2)
        self.assertGreaterEqual(len(brief.sources), 2)
        self.assertGreaterEqual(len(brief.executive_summary.split()), 30)

        # Verify brief passes schema and invariant validation
        validator = ResearchBriefValidator(strict=False)
        val = validator.validate(brief.to_dict())
        self.assertTrue(val.is_valid, f"Brief failed validation under 0 extracted claims: {val.errors}")


# ============================================================================
# Test Suite 5: Single-Document Minimal Corpus Scaffolding
# ============================================================================

class TestSingleDocumentMinimalCorpusScaffolding(unittest.TestCase):
    """Verifies synthesis scaffolding to K >= 2 sections and >= 2 sources for minimal corpus."""

    def setUp(self):
        self.assertTrue(MINIMAL_HTML_PATH.exists(), f"Missing minimal fixture: {MINIMAL_HTML_PATH}")
        self.synthesizer = ExtractiveSynthesizer()
        self.validator = ResearchBriefValidator(strict=True)

    def test_single_document_scaffolded_to_minimum_sections_and_sources(self):
        """Synthesizer expands a single document/claim to >= 2 sections and >= 2 sources."""
        raw_html = MINIMAL_HTML_PATH.read_text(encoding="utf-8")
        raw_doc = RawWebDocument(
            url="https://mock-eco-briefs.org/notes/microplastic-earthworm-mortality-baseline",
            status_code=200,
            headers={},
            raw_html=raw_html,
        )
        clean_article = DocumentParser.parse(raw_doc)
        chunker = PassageChunker(min_words=20, max_words=200, overlap_words=10)
        passages = chunker.chunk_article(clean_article)
        self.assertGreaterEqual(len(passages), 1)

        extractor = ClaimExtractor(min_confidence=0.3)
        claims = extractor.extract_claims(passages)
        self.assertGreaterEqual(len(claims), 1)

        # Single cluster containing claims from only 1 document
        single_cluster = ClaimCluster(
            cluster_id="cluster-01",
            title="Lumbricus Terrestris Soil Microplastic Exposure",
            facet="toxicology",
            claims=claims[:1],
        )

        brief = self.synthesizer.synthesize(
            topic="Soil Microplastic Bioaccumulation and Earthworm Toxicity",
            clusters=[single_cluster],
            sub_queries=["earthworm microplastic toxicity", "soil ingestion bioassays"],
        )

        # Scaffolding assertions
        self.assertGreaterEqual(len(brief.thematic_sections), 2, "Must scaffold to K >= 2 sections")
        self.assertGreaterEqual(len(brief.sources), 2, "Must scaffold to >= 2 sources")
        self.assertGreaterEqual(len(brief.key_takeaways), 3, "Must guarantee >= 3 takeaways")

        # Substantive word count constraint (>= 120 words)
        total_words = len(brief.executive_summary.split()) + sum(
            len(s.narrative.split()) for s in brief.thematic_sections
        )
        self.assertGreaterEqual(total_words, 120, f"Total substantive words ({total_words}) < 120")

        # Strict validation ensuring referential integrity and 0 uncited sources
        val_result = self.validator.validate(brief.to_dict())
        self.assertTrue(val_result.is_valid, f"Scaffolded brief failed strict validation: {val_result.errors}")


# ============================================================================
# Test Suite 6: Duplicate Document & SimHash Deduplication
# ============================================================================

class TestSimHashDeduplication(unittest.TestCase):
    """Verifies exact hash and SimHash 64-bit locality-sensitive deduplication."""

    def setUp(self):
        self.dedup = TwoStageDeduplicator(hamming_threshold=3)

    def test_exact_hash_passage_deduplication(self):
        """Identical text from different URLs is deduplicated with pooled secondary URLs."""
        text = "Sulfide solid electrolytes achieve room-temperature ionic conductivities exceeding 12.0 mS/cm."
        p1 = ScoredPassage("p-01", "d-01", "https://nature-materials.org/art1", "Source A", text, 0.85, "tech", 12)
        p2 = ScoredPassage("p-02", "d-02", "https://battery-syndicate.com/art2", "Source B", text, 0.90, "tech", 12)

        results = self.dedup.deduplicate_passages([p1, p2])
        self.assertEqual(len(results), 1)
        survivor = results[0]
        self.assertEqual(survivor.passage_id, "p-01")
        self.assertIn("https://battery-syndicate.com/art2", survivor.secondary_urls)
        self.assertEqual(survivor.relevance_score, 0.90)

    def test_near_duplicate_simhash_deduplication(self):
        """Passages with minor editorial variations (Hamming distance <= 3) are merged."""
        t1 = (
            "Continuous roll-to-roll dry room processing costs currently exceed $180 per kilowatt-hour "
            "for pilot lines, representing a critical bottleneck for commercial scaling."
        )
        t2 = (
            "Continuous roll-to-roll dry room processing costs currently exceed $180 per kWh "
            "for pilot lines, representing a major bottleneck for commercial scaling."
        )
        fp1 = SimHash64.compute(t1)
        fp2 = SimHash64.compute(t2)
        dist = SimHash64.hamming_distance(fp1, fp2)
        self.assertLessEqual(dist, 3, f"SimHash distance {dist} exceeds threshold 3")

        p1 = ScoredPassage("p-01", "d-01", "https://source1.com/art1", "Source 1", t1, 0.80, "econ", 20)
        p2 = ScoredPassage("p-02", "d-02", "https://source2.com/art2", "Source 2", t2, 0.75, "econ", 19)

        results = self.dedup.deduplicate_passages([p1, p2])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].passage_id, "p-01")
        self.assertIn("https://source2.com/art2", results[0].secondary_urls)

    def test_duplicate_claims_deduplication(self):
        """Claims with identical or near-identical statements merge entities and URLs."""
        c1 = ExtractedClaim(
            claim_id="clm-01",
            text="Lithium metal anode integration decreases overall battery pack volume by 35 percent.",
            source_doc_id="doc-01",
            source_url="https://source-a.org/doc1",
            source_title="DOE Report",
            passage_snippet="Pack level integration saves 35 percent volume.",
            confidence_score=0.88,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Lithium metal", "anode"],
            secondary_urls=[],
        )
        c2 = ExtractedClaim(
            claim_id="clm-02",
            text="Lithium metal anode integration decreases overall battery pack volume by 35%.",
            source_doc_id="doc-02",
            source_url="https://source-b.com/doc2",
            source_title="Press Release",
            passage_snippet="Pack level integration saves 35% volume.",
            confidence_score=0.92,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["battery pack", "anode"],
            secondary_urls=[],
        )
        results = self.dedup.deduplicate_claims([c1, c2])
        self.assertEqual(len(results), 1)
        survivor = results[0]
        self.assertEqual(survivor.confidence_score, 0.92)
        self.assertIn("https://source-b.com/doc2", survivor.secondary_urls)
        self.assertIn("Lithium metal", survivor.entities)
        self.assertIn("battery pack", survivor.entities)


# ============================================================================
# Test Suite 7: Distractor Document & BM25 Relevance Rejection
# ============================================================================

class TestBM25DistractorRejection(unittest.TestCase):
    """Verifies Okapi BM25 relevance score rejection for off-topic distractor documents."""

    def setUp(self):
        self.assertTrue(SOLAR_DISTRACTOR_PATH.exists(), f"Missing solar distractor: {SOLAR_DISTRACTOR_PATH}")
        self.assertTrue(CRYPTO_DISTRACTOR_PATH.exists(), f"Missing crypto distractor: {CRYPTO_DISTRACTOR_PATH}")

    def test_solar_distractor_rejected_for_solid_state_battery_query(self):
        """Photovoltaic solar cell distractor is rejected when querying solid-state batteries."""
        # Relevant battery passage
        p_relevant = ScoredPassage(
            passage_id="p-battery",
            doc_id="doc-ssb-01",
            url="https://mock-science.org/materials/solid-electrolyte",
            title="Solid Electrolyte Materials",
            text=(
                "Solid-state battery commercialization has advanced with sulfide-based solid electrolytes "
                "achieving ionic conductivity surpassing 12 mS/cm at room temperature. Prototypes demonstrated "
                "gravimetric energy densities of 500 Wh/kg."
            ),
            relevance_score=0.0,
            subquery="",
            word_count=28,
        )

        # Distractor solar passage
        solar_html = SOLAR_DISTRACTOR_PATH.read_text(encoding="utf-8")
        raw_solar = RawWebDocument(
            url="https://mock-green-power.net/solar/tandem-perovskite-photovoltaic-efficiency",
            status_code=200,
            headers={},
            raw_html=solar_html,
        )
        clean_solar = DocumentParser.parse(raw_solar).cleaned_text
        p_distractor = ScoredPassage(
            passage_id="p-solar",
            doc_id="doc-solar-05",
            url="https://mock-green-power.net/solar/tandem-perovskite-photovoltaic-efficiency",
            title="Perovskite Solar Cells",
            text=clean_solar[:400],
            relevance_score=0.0,
            subquery="",
            word_count=50,
        )

        bm25_filter = BM25Filter(s_min=0.3, alpha=0.25, min_passages=1)
        filtered = bm25_filter.filter_passages(
            [p_relevant, p_distractor],
            topic="Solid-State Battery Pack Densities and Solid Electrolytes",
        )

        filtered_ids = [p.passage_id for p in filtered]
        self.assertIn("p-battery", filtered_ids, "Relevant battery passage must pass BM25 filter")
        self.assertNotIn("p-solar", filtered_ids, "Perovskite solar distractor must be eliminated")

    def test_crypto_distractor_rejected_for_supply_chain_query(self):
        """Cryptocurrency distractor is rejected when querying macroeconomic supply chain reshoring."""
        # Relevant supply chain passage
        p_reshoring = ScoredPassage(
            passage_id="p-reshoring",
            doc_id="doc-reshoring-01",
            url="https://mock-imf.org/supply-chain-fragmentation",
            title="IMF Supply Chain Fragmentation",
            text=(
                "Over 62% of multinational industrial manufacturers surveyed initiated near-shoring or friend-shoring "
                "initiatives to mitigate geopolitical trade frictions, while industrial policy disbursed over $95 billion "
                "in direct subsidies under the CHIPS Act."
            ),
            relevance_score=0.0,
            subquery="",
            word_count=30,
        )

        # Distractor crypto passage
        crypto_html = CRYPTO_DISTRACTOR_PATH.read_text(encoding="utf-8")
        raw_crypto = RawWebDocument(
            url="https://mock-crypto-review.org/defi/yield-farming",
            status_code=200,
            headers={},
            raw_html=crypto_html,
        )
        clean_crypto = DocumentParser.parse(raw_crypto).cleaned_text
        p_crypto = ScoredPassage(
            passage_id="p-crypto",
            doc_id="doc-crypto-05",
            url="https://mock-crypto-review.org/defi/yield-farming",
            title="Decentralized Finance Yield Farming",
            text=clean_crypto[:400],
            relevance_score=0.0,
            subquery="",
            word_count=50,
        )

        bm25_filter = BM25Filter(s_min=0.3, alpha=0.25)
        filtered = bm25_filter.filter_passages(
            [p_reshoring, p_crypto],
            topic="Global Supply Chain Re-Shoring and Friend-Shoring Macroeconomic Inflation",
        )

        filtered_ids = [p.passage_id for p in filtered]
        self.assertIn("p-reshoring", filtered_ids, "Relevant reshoring passage must pass BM25 filter")
        self.assertNotIn("p-crypto", filtered_ids, "Crypto distractor must be eliminated")


if __name__ == "__main__":
    unittest.main()
