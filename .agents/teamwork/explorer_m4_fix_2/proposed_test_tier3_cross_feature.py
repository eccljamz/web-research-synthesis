"""Tier 3 Integration and Cross-Feature Contract Test Suite.

Milestone 4 - Contract Testing & Cross-Module Invariant Verification:
1. Contract test: QueryDecomposer output feeds into MockWebRetrievalClient.
2. Contract test: CleanArticle feeds into PassageChunker, BM25Filter, and TwoStageDeduplicator.
3. Contract test: ExtractedClaim feeds into ThematicClusterer with subquery facet mapping.
4. Contract test: ClaimClusters feed into ExtractiveSynthesizer and CitationRegistry.
5. Parity test: ResearchBrief .to_markdown() and .to_json() contain identical substantive claims,
   citation indices, section titles, and source references.
6. Roundtrip test: ResearchBrief.from_dict(brief.to_dict()) and JSON serialization field-by-field equality.

Pure Python standard library (unittest) - Zero external dependencies.
"""

from __future__ import annotations

import json
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
        RetrievalBatch,
        ScoredPassage,
        SourceCitation,
        SubQuery,
        ThematicSection,
    )
    from research_synthesis.retrieval.decomposer import HeuristicQueryDecomposer
    from research_synthesis.retrieval.parser import DocumentParser, RobustHTMLParser
    from research_synthesis.retrieval.retriever import (
        CompositeRetrievalClient,
        MockWebRetrievalClient,
    )
    from research_synthesis.extraction.bm25 import BM25Filter, PureBM25
    from research_synthesis.extraction.chunker import PassageChunker
    from research_synthesis.extraction.claims import ClaimExtractor
    from research_synthesis.extraction.dedup import SimHash64, TwoStageDeduplicator
    from research_synthesis.synthesis.cluster import ThematicClusterer
    from research_synthesis.synthesis.synthesizer import CitationRegistry, ExtractiveSynthesizer
    from research_synthesis.synthesis.formatters import JSONSchemaSerializer, MarkdownFormatter
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
        RetrievalBatch,
        ScoredPassage,
        SourceCitation,
        SubQuery,
        ThematicSection,
    )
    from src.research_synthesis.retrieval.decomposer import HeuristicQueryDecomposer
    from src.research_synthesis.retrieval.parser import DocumentParser, RobustHTMLParser
    from src.research_synthesis.retrieval.retriever import (
        CompositeRetrievalClient,
        MockWebRetrievalClient,
    )
    from src.research_synthesis.extraction.bm25 import BM25Filter, PureBM25
    from src.research_synthesis.extraction.chunker import PassageChunker
    from src.research_synthesis.extraction.claims import ClaimExtractor
    from src.research_synthesis.extraction.dedup import SimHash64, TwoStageDeduplicator
    from src.research_synthesis.synthesis.cluster import ThematicClusterer
    from src.research_synthesis.synthesis.synthesizer import CitationRegistry, ExtractiveSynthesizer
    from src.research_synthesis.synthesis.formatters import JSONSchemaSerializer, MarkdownFormatter
    from src.research_synthesis.pipeline import ResearchPipeline
    from src.research_synthesis.verification.validator import ResearchBriefValidator


MANIFEST_PATH = PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "manifest.json"


# ============================================================================
# Test Suite 1: Contract - QueryDecomposer -> MockWebRetrievalClient
# ============================================================================

class TestContractDecomposerToRetrieval(unittest.TestCase):
    """Validates interface contract between QueryDecomposer and MockWebRetrievalClient."""

    def setUp(self):
        self.decomposer = HeuristicQueryDecomposer()
        self.retriever = MockWebRetrievalClient(corpus_path=MANIFEST_PATH)

    def test_decomposer_output_satisfies_subquery_contract(self):
        """HeuristicQueryDecomposer output conforms strictly to SubQuery schema."""
        topic = "Next-Generation Solid-State Battery Commercialization"
        decomp_result = self.decomposer.decompose(topic)

        self.assertIsNotNone(decomp_result)
        self.assertEqual(decomp_result.topic, topic)
        self.assertGreaterEqual(len(decomp_result.sub_queries), 3)

        for sq in decomp_result.sub_queries:
            self.assertIsInstance(sq, SubQuery)
            self.assertTrue(sq.id.startswith("sq-"))
            self.assertEqual(sq.original_topic, topic)
            self.assertIn(sq.facet, ["technical", "economic", "challenges", "comparative", "temporal"])
            self.assertTrue(sq.search_query)
            self.assertGreaterEqual(sq.priority, 1)

    def test_subqueries_feed_into_mock_retriever_search_and_batch(self):
        """SubQuery instances feed seamlessly into MockWebRetrievalClient search & batch methods."""
        topic = "Next-Generation Solid-State Battery Commercialization"
        decomp_result = self.decomposer.decompose(topic)
        sub_queries = decomp_result.sub_queries

        # 1. Test individual search call for each subquery
        for sq in sub_queries:
            urls = self.retriever.search(sq.search_query, limit=2)
            self.assertIsInstance(urls, list)
            for u in urls:
                self.assertTrue(u.startswith("http"))
                raw_doc = self.retriever.fetch_url(u)
                self.assertIsInstance(raw_doc, RawWebDocument)
                self.assertEqual(raw_doc.status_code, 200)

        # 2. Test composite retrieve_batch contract
        composite = CompositeRetrievalClient(mock_client=self.retriever, offline_mode=True)
        batch = composite.retrieve_batch(topic=topic, sub_queries=sub_queries, limit_per_subquery=2)
        self.assertIsInstance(batch, RetrievalBatch)
        self.assertEqual(batch.topic, topic)
        self.assertGreater(len(batch.documents), 0)

        for art in batch.documents:
            self.assertIsInstance(art, CleanArticle)
            self.assertTrue(art.doc_id)
            self.assertTrue(art.url.startswith("http"))
            self.assertIsNotNone(art.metadata)
            self.assertTrue(art.subquery_id)
            self.assertTrue(art.subquery_facet)
            self.assertGreater(len(art.cleaned_text), 50)


# ============================================================================
# Test Suite 2: Contract - CleanArticle -> Chunker -> BM25 -> Deduplicator
# ============================================================================

class TestContractCleanArticleToChunkerBM25Dedup(unittest.TestCase):
    """Validates sequential data contracts across CleanArticle, PassageChunker, BM25, and Dedup."""

    def setUp(self):
        self.chunker = PassageChunker(min_words=50, max_words=200, overlap_words=20)
        self.bm25_filter = BM25Filter(min_threshold=0.01)
        self.deduplicator = TwoStageDeduplicator(hamming_threshold=3)

    def test_clean_article_to_passage_chunker_contract(self):
        """CleanArticle feeds into PassageChunker producing valid ScoredPassages."""
        meta = DocumentMetadata(
            url="https://mock-science.org/materials/solid-electrolyte",
            canonical_url="https://mock-science.org/materials/solid-electrolyte",
            domain="mock-science.org",
            title="Solid Electrolyte Materials and Ionic Transport",
            word_count=300,
        )
        paragraphs = [
            (
                "Sulfide-based solid electrolytes, particularly lithium argyrodites, exhibit conductivities "
                "exceeding 12.0 mS/cm at ambient temperatures, fulfilling automotive power delivery criteria. "
                "In contrast, garnet oxide electrolytes such as LLZO exhibit elevated interfacial resistance "
                "against lithium metal anodes, necessitating atomic layer deposition interlayers to suppress dendrite shorting."
            ),
            (
                "Continuous roll-to-roll dry room processing costs currently exceed $180 per kilowatt-hour for pilot lines. "
                "Operating dry rooms at this specification incurs a capital expenditure premium of $18 million to $25 million "
                "per gigawatt-hour of installed annual capacity."
            ),
        ]
        article = CleanArticle(
            doc_id="doc-ssb-01",
            url=meta.url,
            metadata=meta,
            cleaned_text="\n\n".join(paragraphs),
            paragraphs=paragraphs,
            subquery_id="sq-01",
            subquery_facet="technical",
        )

        passages = self.chunker.chunk_article(article)
        self.assertGreaterEqual(len(passages), 1)

        for p in passages:
            self.assertIsInstance(p, ScoredPassage)
            self.assertTrue(p.passage_id.startswith("doc-ssb-01-p"))
            self.assertEqual(p.doc_id, "doc-ssb-01")
            self.assertEqual(p.url, meta.url)
            self.assertEqual(p.title, meta.title)
            self.assertGreaterEqual(p.word_count, 20)
            self.assertIsInstance(p.text, str)

        # Feed ScoredPassages into BM25Filter
        subqueries = [SubQuery("sq-01", "Battery", "technical", "solid electrolyte ionic conductivity", priority=1)]
        scored_passages = self.bm25_filter.filter_passages(
            passages,
            topic="Solid-State Battery Electrolytes",
            sub_queries=subqueries,
        )
        self.assertGreaterEqual(len(scored_passages), 1)
        for sp in scored_passages:
            self.assertIsInstance(sp, ScoredPassage)
            self.assertGreaterEqual(sp.relevance_score, 0.0)

        # Feed scored passages into TwoStageDeduplicator
        deduped = self.deduplicator.deduplicate_passages(scored_passages)
        self.assertGreaterEqual(len(deduped), 1)
        for dp in deduped:
            self.assertIsInstance(dp, ScoredPassage)
            self.assertEqual(dp.doc_id, "doc-ssb-01")


# ============================================================================
# Test Suite 3: Contract - ExtractedClaim -> ThematicClusterer
# ============================================================================

class TestContractClaimExtractionToThematicClustering(unittest.TestCase):
    """Validates data flow between ClaimExtractor and ThematicClusterer with facet mapping."""

    def setUp(self):
        self.extractor = ClaimExtractor(min_confidence=0.3)
        self.clusterer = ThematicClusterer(min_sections=2, max_sections=5)

    def test_extracted_claim_contract_and_thematic_clustering(self):
        """ExtractedClaim instances adhere to schema and cluster cleanly into ClaimClusters."""
        passages = [
            ScoredPassage(
                passage_id="p-01",
                doc_id="doc-01",
                url="https://mock-science.org/solid-electrolyte",
                title="Solid Electrolyte Science",
                text="Sulfide solid electrolytes achieved ionic conductivity of 12.5 mS/cm at 25 degrees Celsius.",
                relevance_score=0.92,
                subquery="ionic conductivity",
                word_count=16,
            ),
            ScoredPassage(
                passage_id="p-02",
                doc_id="doc-02",
                url="https://mock-energy.gov/battery500",
                title="Battery500 Roadmap",
                text="The DOE Battery500 consortium established targets of 500 Wh/kg cell energy density by 2030.",
                relevance_score=0.90,
                subquery="energy density",
                word_count=16,
            ),
            ScoredPassage(
                passage_id="p-03",
                doc_id="doc-03",
                url="https://mock-tech.com/pilot-lines",
                title="Manufacturing Pilot Lines",
                text="Pilot line dry room capital expenditures currently exceed $180 per kWh across automotive facilities.",
                relevance_score=0.88,
                subquery="manufacturing cost",
                word_count=17,
            ),
        ]

        claims = self.extractor.extract_claims(passages)
        self.assertGreaterEqual(len(claims), 2)

        for c in claims:
            self.assertIsInstance(c, ExtractedClaim)
            self.assertTrue(c.claim_id)
            self.assertTrue(c.text)
            self.assertTrue(c.source_doc_id)
            self.assertTrue(c.source_url.startswith("http"))
            self.assertGreater(c.confidence_score, 0.0)
            self.assertIsInstance(c.claim_type, ClaimType)

        sub_queries = [
            SubQuery("sq-01", "Solid-State Batteries", "technical", "solid electrolyte ionic conductivity", priority=1),
            SubQuery("sq-02", "Solid-State Batteries", "economic", "manufacturing costs and pilot lines", priority=2),
        ]

        clusters = self.clusterer.cluster(
            claims=claims,
            sub_queries=sub_queries,
            topic="Solid-State Batteries",
            passages=passages,
        )

        self.assertGreaterEqual(len(clusters), 2, "Clusterer must produce >= 2 clusters")
        self.assertLessEqual(len(clusters), 5, "Clusterer must produce <= 5 clusters")

        for cl in clusters:
            self.assertIsInstance(cl, ClaimCluster)
            self.assertTrue(cl.cluster_id)
            self.assertTrue(cl.title)
            self.assertTrue(cl.facet)
            self.assertIsInstance(cl.claims, list)
            self.assertIsInstance(cl.centroid_terms, list)


# ============================================================================
# Test Suite 4: Contract - ClaimClusters -> ExtractiveSynthesizer & CitationRegistry
# ============================================================================

class TestContractClusteringToSynthesisAndCitationRegistry(unittest.TestCase):
    """Validates contract between ClaimClusters, CitationRegistry, and ExtractiveSynthesizer."""

    def setUp(self):
        self.synthesizer = ExtractiveSynthesizer()

    def test_citation_registry_1_based_indexing_and_attribution(self):
        """CitationRegistry maintains continuous 1-based order-of-appearance indexing."""
        registry = CitationRegistry()
        c1 = ExtractedClaim(
            claim_id="clm-01",
            text="Sulfide solid electrolytes achieve ionic conductivity over 12 mS/cm.",
            source_doc_id="doc-01",
            source_url="https://mock-science.org/electrolyte",
            source_title="Electrolyte Research",
            passage_snippet="Sulfide argyrodites demonstrated ionic conductivity of 12 mS/cm at 25 degrees.",
            confidence_score=0.95,
            claim_type=ClaimType.QUANTITATIVE,
        )
        c2 = ExtractedClaim(
            claim_id="clm-02",
            text="DOE Battery500 establishes cell energy density targets of 500 Wh/kg.",
            source_doc_id="doc-02",
            source_url="https://mock-energy.gov/roadmap",
            source_title="DOE Roadmap",
            passage_snippet="DOE Battery500 targets 500 Wh/kg by 2030 for commercial automotive cells.",
            confidence_score=0.92,
            claim_type=ClaimType.QUANTITATIVE,
        )

        indices1 = registry.register_claim(c1)
        indices2 = registry.register_claim(c2)

        self.assertEqual(indices1, [1])
        self.assertEqual(indices2, [2])

        marker1 = registry.format_citation_marker(indices1)
        marker2 = registry.format_citation_marker(indices2)
        self.assertEqual(marker1, "[1]")
        self.assertEqual(marker2, "[2]")

        # Multi-source corroboration yields sorted marker
        indices_both = registry.register_claim(c1) + registry.register_claim(c2)
        marker_both = registry.format_citation_marker(sorted(list(set(indices_both))))
        self.assertEqual(marker_both, "[1, 2]")

        # Bibliography inspection
        sources = registry.build_bibliography()
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0].citation_index, 1)
        self.assertEqual(sources[0].url, "https://mock-science.org/electrolyte")
        self.assertEqual(sources[1].citation_index, 2)
        self.assertEqual(sources[1].url, "https://mock-energy.gov/roadmap")

    def test_synthesizer_produces_fully_connected_research_brief(self):
        """ExtractiveSynthesizer synthesizes complete ResearchBrief with referential integrity."""
        c1 = ExtractedClaim(
            claim_id="clm-01",
            text="Sulfide solid electrolytes achieve ionic conductivity over 12 mS/cm.",
            source_doc_id="doc-01",
            source_url="https://mock-science.org/electrolyte",
            source_title="Electrolyte Research",
            passage_snippet="Sulfide argyrodites demonstrated ionic conductivity of 12 mS/cm at 25 degrees.",
            confidence_score=0.95,
            claim_type=ClaimType.QUANTITATIVE,
        )
        c2 = ExtractedClaim(
            claim_id="clm-02",
            text="DOE Battery500 establishes cell energy density targets of 500 Wh/kg.",
            source_doc_id="doc-02",
            source_url="https://mock-energy.gov/roadmap",
            source_title="DOE Roadmap",
            passage_snippet="DOE Battery500 targets 500 Wh/kg by 2030 for commercial automotive cells.",
            confidence_score=0.92,
            claim_type=ClaimType.QUANTITATIVE,
        )

        clusters = [
            ClaimCluster("cl-01", "Solid Electrolytes & Transport", "technical", claims=[c1]),
            ClaimCluster("cl-02", "Automotive Roadmaps & Energy Targets", "economic", claims=[c2]),
        ]

        sub_queries = [
            SubQuery("sq-01", "Battery", "technical", "solid electrolyte ionic conductivity", priority=1),
            SubQuery("sq-02", "Battery", "economic", "battery density roadmaps", priority=2),
        ]

        brief = self.synthesizer.synthesize(
            topic="Solid-State Battery Commercialization",
            clusters=clusters,
            sub_queries=sub_queries,
        )

        self.assertIsInstance(brief, ResearchBrief)
        self.assertGreaterEqual(len(brief.thematic_sections), 2)
        self.assertGreaterEqual(len(brief.sources), 2)
        self.assertGreaterEqual(len(brief.key_takeaways), 3)

        # Referential integrity check: every citation in narrative exists in sources
        sources_by_idx = {s.citation_index: s for s in brief.sources}
        for sec in brief.thematic_sections:
            for ci in sec.citation_indices:
                self.assertIn(ci, sources_by_idx)


# ============================================================================
# Test Suite 5: Parity - ResearchBrief .to_markdown() vs .to_json()
# ============================================================================

class TestParityMarkdownAndJson(unittest.TestCase):
    """Verifies substantive claim, citation, and source parity across Markdown and JSON."""

    def setUp(self):
        self.pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=MANIFEST_PATH)
        self.brief = self.pipeline.run(
            "Next-Generation Solid-State Battery Commercialization: Energy Density Roadmaps, Solid Electrolytes, and Manufacturing Scalability"
        )

    def test_markdown_and_json_content_and_citation_parity(self):
        """Markdown and JSON representations contain identical substantive components."""
        md_text = self.brief.to_markdown()
        json_str = self.brief.to_json()
        json_data = json.loads(json_str)

        # 1. Topic / Title parity
        self.assertIn(json_data["topic"], md_text)
        self.assertIn(json_data["brief_id"], md_text)

        # 2. Source URLs and titles parity
        for src in json_data["sources"]:
            self.assertIn(src["url"], md_text, f"Source URL {src['url']} missing in Markdown")
            self.assertIn(f"[{src['citation_index']}]", md_text, f"Citation [{src['citation_index']}] missing in Markdown")

        # 3. Thematic section titles parity
        for sec in json_data["thematic_sections"]:
            self.assertIn(sec["title"], md_text, f"Section title '{sec['title']}' missing in Markdown")
            for finding in sec.get("key_findings", []):
                self.assertIn(finding, md_text, f"Key finding '{finding}' missing in Markdown")

        # 4. Key Takeaways parity
        for kt in json_data["key_takeaways"]:
            kt_text = kt.get("text", "") if isinstance(kt, dict) else str(kt)
            # Remove trailing citation brackets for substring search if needed
            clean_kt = re.sub(r"\s*\[[\d,\s]+\]", "", kt_text).strip()
            self.assertIn(clean_kt[:40], md_text, f"Takeaway snippet '{clean_kt[:40]}' missing in Markdown")

        # 5. Citation indices parity
        json_citations = set()
        for sec in json_data["thematic_sections"]:
            json_citations.update(sec.get("citation_indices", []))

        # Check that citation markers like [1], [2] exist in Markdown
        for c_idx in json_citations:
            self.assertRegex(md_text, rf"\[{c_idx}[,\s\]]", f"Citation index {c_idx} not found in Markdown text")


# ============================================================================
# Test Suite 6: Roundtrip Serialization Fidelity
# ============================================================================

class TestResearchBriefRoundtrip(unittest.TestCase):
    """Verifies lossless roundtrip serialization through to_dict(), from_dict(), and to_json()."""

    def setUp(self):
        self.pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=MANIFEST_PATH)
        self.original_brief = self.pipeline.run(
            "Global Supply Chain Re-Shoring and Friend-Shoring Dynamics: Macroeconomic Inflation Impacts and Industrial Policy Interventions"
        )

    def test_from_dict_field_by_field_equality(self):
        """ResearchBrief.from_dict(brief.to_dict()) preserves all fields losslessly."""
        brief_dict = self.original_brief.to_dict()
        reconstructed = ResearchBrief.from_dict(brief_dict)

        # Top-level primitives
        self.assertEqual(reconstructed.brief_id, self.original_brief.brief_id)
        self.assertEqual(reconstructed.topic, self.original_brief.topic)
        self.assertEqual(reconstructed.executive_summary, self.original_brief.executive_summary)
        self.assertEqual(reconstructed.generated_at, self.original_brief.generated_at)
        self.assertEqual(reconstructed.sub_queries, self.original_brief.sub_queries)

        # Thematic sections
        self.assertEqual(len(reconstructed.thematic_sections), len(self.original_brief.thematic_sections))
        for rec_sec, orig_sec in zip(reconstructed.thematic_sections, self.original_brief.thematic_sections):
            self.assertEqual(rec_sec.section_id, orig_sec.section_id)
            self.assertEqual(rec_sec.title, orig_sec.title)
            self.assertEqual(rec_sec.narrative, orig_sec.narrative)
            self.assertEqual(rec_sec.citation_indices, orig_sec.citation_indices)
            self.assertEqual(rec_sec.claim_ids, orig_sec.claim_ids)
            self.assertEqual(rec_sec.key_findings, orig_sec.key_findings)

        # Key takeaways
        self.assertEqual(len(reconstructed.key_takeaways), len(self.original_brief.key_takeaways))
        for rec_kt, orig_kt in zip(reconstructed.key_takeaways, self.original_brief.key_takeaways):
            self.assertEqual(rec_kt.text, orig_kt.text)
            self.assertEqual(rec_kt.citation_indices, orig_kt.citation_indices)

        # Sources
        self.assertEqual(len(reconstructed.sources), len(self.original_brief.sources))
        for rec_src, orig_src in zip(reconstructed.sources, self.original_brief.sources):
            self.assertEqual(rec_src.citation_index, orig_src.citation_index)
            self.assertEqual(rec_src.source_id, orig_src.source_id)
            self.assertEqual(rec_src.title, orig_src.title)
            self.assertEqual(rec_src.url, orig_src.url)
            self.assertEqual(rec_src.snippet, orig_src.snippet)
            self.assertEqual(rec_src.attributed_claim_ids, orig_src.attributed_claim_ids)

        # Metadata
        orig_meta = self.original_brief.metadata.to_dict() if hasattr(self.original_brief.metadata, "to_dict") else dict(self.original_brief.metadata)
        rec_meta = reconstructed.metadata.to_dict() if hasattr(reconstructed.metadata, "to_dict") else dict(reconstructed.metadata)
        self.assertEqual(rec_meta["retrieval_mode"], orig_meta["retrieval_mode"])
        self.assertEqual(rec_meta["total_sources_scanned"], orig_meta["total_sources_scanned"])

    def test_json_string_roundtrip_equality(self):
        """Roundtrip through JSON string matches original brief structure."""
        json_str = self.original_brief.to_json()
        parsed_dict = json.loads(json_str)
        reconstructed_from_json = ResearchBrief.from_dict(parsed_dict)

        self.assertEqual(reconstructed_from_json.brief_id, self.original_brief.brief_id)
        self.assertEqual(reconstructed_from_json.topic, self.original_brief.topic)
        self.assertEqual(len(reconstructed_from_json.thematic_sections), len(self.original_brief.thematic_sections))
        self.assertEqual(len(reconstructed_from_json.sources), len(self.original_brief.sources))


if __name__ == "__main__":
    unittest.main()
