"""Adversarial Stress Test Suite for Milestone 1: Query Decomposition & Retrieval.

Authored by Adversarial Challenger 1.
Empirically tests edge cases, failure modes, contract violations, and state leaks
in HeuristicQueryDecomposer, RobustHTMLParser, DocumentParser, MockWebRetrievalClient,
and CompositeRetrievalClient.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.research_synthesis.models import (
    CleanArticle,
    DecompositionResult,
    DocumentMetadata,
    RawWebDocument,
    RetrievalBatch,
    SubQuery,
)
from src.research_synthesis.retrieval.decomposer import (
    HeuristicQueryDecomposer,
)
from src.research_synthesis.retrieval.parser import (
    DocumentParser,
    RobustHTMLParser,
)
from src.research_synthesis.retrieval.retriever import (
    CompositeRetrievalClient,
    LiveHttpRetrievalClient,
    MockWebRetrievalClient,
)


class TestDecomposerStressAndAdversarial(unittest.TestCase):
    """Stress tests and boundary condition validation for HeuristicQueryDecomposer."""

    def setUp(self):
        self.decomposer = HeuristicQueryDecomposer()

    def test_empty_string_and_whitespace_rejection(self):
        """Verify strict input validation against empty, whitespace, and non-string inputs."""
        with self.assertRaises(ValueError):
            self.decomposer.decompose("")
        with self.assertRaises(ValueError):
            self.decomposer.decompose("   \t\n  \r\n")
        with self.assertRaises(TypeError):
            self.decomposer.decompose(None)  # type: ignore
        with self.assertRaises(TypeError):
            self.decomposer.decompose(12345)  # type: ignore

    def test_single_word_expansion(self):
        """Verify single-word topics are properly expanded without crashing."""
        result = self.decomposer.decompose("Quantum", max_subqueries=5)
        self.assertEqual(len(result.sub_queries), 5)
        # Verify base expansion occurred
        self.assertTrue(any("technology system" in sq.search_query for sq in result.sub_queries))

    def test_punctuation_heavy_queries_tolerance(self):
        """Verify extreme punctuation sequences do not trigger unhandled exceptions."""
        result_punc = self.decomposer.decompose("???!!! ... ,,, ;;; :::", max_subqueries=3)
        self.assertIsInstance(result_punc, DecompositionResult)
        self.assertEqual(len(result_punc.sub_queries), 3)

        result_mixed = self.decomposer.decompose("What?! Is solid-state... really viable?!?", max_subqueries=3)
        self.assertIsInstance(result_mixed, DecompositionResult)
        self.assertEqual(len(result_mixed.sub_queries), 3)

    def test_unicode_and_emojis(self):
        """Verify Unicode, accents, non-Latin scripts, and emojis."""
        # Non-Latin scripts (length >= 2)
        res_cjk = self.decomposer.decompose("量子计算 vs 经典计算", max_subqueries=3)
        self.assertIn("comparative", [sq.facet for sq in res_cjk.sub_queries])

        # Accented characters
        res_accent = self.decomposer.decompose("café vs naïve", max_subqueries=3)
        self.assertIn("comparative", [sq.facet for sq in res_accent.sub_queries])

        # Emojis (single emoji length is 1, so len >= 2 check in decomposer causes non-comparative fallback)
        res_emoji = self.decomposer.decompose("🚀 vs 🛰️", max_subqueries=3)
        self.assertIsInstance(res_emoji, DecompositionResult)
        self.assertEqual(len(res_emoji.sub_queries), 3)

    def test_comparative_vs_and_versus_detected(self):
        """Verify standard 'vs' and 'versus' comparative detection."""
        res_vs = self.decomposer.decompose("Solid-State vs Lithium-Ion", max_subqueries=5)
        facets_vs = [sq.facet for sq in res_vs.sub_queries]
        self.assertIn("comparative", facets_vs)
        self.assertTrue(any("Solid-State" in sq.search_query for sq in res_vs.sub_queries))
        self.assertTrue(any("Lithium-Ion" in sq.search_query for sq in res_vs.sub_queries))

    def test_comparative_comparison_between_flaw(self):
        """Verify that 'comparison between A and B' succeeds in comparative detection."""
        topic = "comparison between Solid-State and Lithium-Ion"
        is_comp, ent_a, ent_b = self.decomposer._detect_comparative(topic)
        self.assertTrue(is_comp, "Comparative detection succeeds for 'comparison between A and B'")
        self.assertEqual(ent_a, "Solid-State")
        self.assertEqual(ent_b, "Lithium-Ion")

    def test_comparative_tradeoffs_between_flaw(self):
        """Verify that 'trade-offs between A and B' succeeds in comparative detection."""
        topic = "trade-offs between Solid-State and Lithium-Ion"
        is_comp, ent_a, ent_b = self.decomposer._detect_comparative(topic)
        self.assertTrue(is_comp, "Comparative detection succeeds for 'trade-offs between A and B'")
        self.assertEqual(ent_a, "Solid-State")
        self.assertEqual(ent_b, "Lithium-Ion")

    def test_three_way_comparison_behavior(self):
        """Examine three-way comparison 'X vs Y vs Z'."""
        topic = "Lithium vs Sodium vs Solid-State"
        is_comp, ent_a, ent_b = self.decomposer._detect_comparative(topic)
        self.assertTrue(is_comp)
        # Non-greedy first group captures 'Lithium', second group captures 'Sodium vs Solid-State'
        self.assertEqual(ent_a, "Lithium")
        self.assertEqual(ent_b, "Sodium vs Solid-State")


class TestRobustHTMLParserAdversarialStateLeak(unittest.TestCase):
    """Empirical verification of the ignore_depth state leak in RobustHTMLParser."""

    def test_boilerplate_class_id_causes_permanent_text_suppression(self):
        """CRITICAL DEFECT: RobustHTMLParser permanently suppresses text after boilerplate elements.
        
        In handle_starttag():
            if any(noise in elem_id or noise in elem_class for noise in self.BOILERPLATE_CLASS_ID_KEYWORDS):
                self.ignore_depth += 1
        
        In handle_endtag():
            if tag_lower in self.IGNORE_TAGS or self.ignore_depth > 0:
                if tag_lower in self.IGNORE_TAGS and tag_lower not in self.VOID_TAGS:
                    self.ignore_depth = max(0, self.ignore_depth - 1)
                return
        
        Because 'div', 'section', 'span', etc. are NOT in self.IGNORE_TAGS, self.ignore_depth
        is NEVER decremented when closing a boilerplate div/section/span.
        Result: Every following paragraph in the entire document is dropped!
        """
        html_sample = """
        <html>
        <head><title>Test Article</title></head>
        <body>
            <div id="cookie-banner" class="cookie-popup">
                Please accept cookies.
            </div>
            <main>
                <h1>Solid State Battery Developments</h1>
                <p>Solid state electrolytes offer substantial improvements in safety by eliminating flammable liquids.</p>
                <p>Commercialization timelines project high volume pilot manufacturing by 2026 across major OEMs.</p>
            </main>
        </body>
        </html>
        """
        parser = RobustHTMLParser()
        parser.feed(html_sample)
        parser._flush_text()

        # With the fix, ignore_depth returns to 0 after boilerplate element closes
        self.assertEqual(parser.ignore_depth, 0, "ignore_depth returns to 0 after boilerplate element closes")
        self.assertEqual(len(parser.paragraphs), 2, "Article paragraphs are preserved after boilerplate element closes")
        self.assertEqual(len(parser.headings), 1, "Headings are preserved")

    def test_mock_corpus_ad_heavy_fixture_dropped_by_state_leak(self):
        """Verify the state leak against the actual fixture tests/fixtures/mock_corpus/solid_state_battery/doc_04_ad_heavy_duplicate.html."""
        fixture_path = PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "solid_state_battery" / "doc_04_ad_heavy_duplicate.html"
        if not fixture_path.exists():
            self.skipTest("Fixture not found")

        with open(fixture_path, "r", encoding="utf-8") as f:
            raw_html = f.read()

        raw_doc = RawWebDocument(
            url="https://mock-battery-news-daily.com/reposts/quantum-solid-scaling-dry-process",
            status_code=200,
            headers={"Content-Type": "text/html"},
            raw_html=raw_html,
        )

        article = DocumentParser.parse(raw_doc)
        # With the fix, paragraphs and cleaned_text are preserved despite ad containers
        self.assertGreaterEqual(len(article.paragraphs), 2, "Paragraphs are extracted from real ad-heavy fixture")
        self.assertNotEqual(article.cleaned_text, "")


class TestMockRetrieverManifestLoadingBug(unittest.TestCase):
    """Empirical verification of MockWebRetrievalClient manifest loading discrepancy."""

    def test_manifest_dict_schema_discrepancy(self):
        """Verify MockWebRetrievalClient loads files from manifest.json keyed by canonical URL."""
        manifest_path = PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "manifest.json"
        if not manifest_path.exists():
            self.skipTest("Manifest fixture not found")

        client = MockWebRetrievalClient(corpus_path=str(manifest_path))

        # 1. Check corpus keys: They are canonical URLs!
        canonical_url = "https://mock-science.org/materials/solid-electrolyte-conductivities-breakthrough"
        corpus_keys = list(client._corpus.keys())
        self.assertIn(canonical_url, corpus_keys, "Corpus keys are canonical URLs rather than document IDs")

        # 2. Check raw_html: It was loaded from disk!
        doc_entry = client._corpus[canonical_url]
        self.assertIsNotNone(doc_entry.get("raw_html"), "raw_html was loaded from disk")
        self.assertGreater(len(doc_entry["raw_html"]), 100)

        # 3. Check search(): Returns canonical URLs!
        search_results = client.search("solid electrolyte ionic conductivity", limit=2)
        self.assertTrue(any(res == canonical_url for res in search_results))

        # 4. Check fetch_url() with canonical URL: returns 200!
        doc = client.fetch_url(canonical_url)
        self.assertEqual(doc.status_code, 200, "fetch_url with canonical URL returns 200")
        self.assertIn("<html", doc.raw_html.lower())


class TestCompositeRetrievalFailoverAndFallbacks(unittest.TestCase):
    """Test CompositeRetrievalClient failover and fallback behaviors."""

    def test_live_search_exception_failover(self):
        """Verify seamless failover when live search throws an unhandled exception."""
        live_client = MagicMock(spec=LiveHttpRetrievalClient)
        live_client.search.side_effect = ConnectionResetError("Connection reset by peer")
        live_client.fetch_url.side_effect = ConnectionResetError("Connection reset by peer")

        mock_client = MockWebRetrievalClient()
        composite = CompositeRetrievalClient(
            live_client=live_client,
            mock_client=mock_client,
            offline_mode=False,
        )

        urls = composite.search("energy density", limit=2)
        self.assertGreaterEqual(len(urls), 1)
        self.assertTrue(composite.offline_mode, "Client should switch to offline mode upon search failure")

    def test_empty_search_hits_fallback_behavior(self):
        """Verify behavior when search query has zero keyword overlap."""
        mock_client = MockWebRetrievalClient()
        # Nonexistent token
        urls = mock_client.search("xyzzynonexistenttoken99999", limit=2)
        # Mock client has a built-in fallback returning top documents
        self.assertGreaterEqual(len(urls), 1)

    def test_failed_urls_recorded_in_batch(self):
        """Verify failed URLs in batch retrieval are recorded and pipeline does not crash."""
        mock_client = MagicMock(spec=MockWebRetrievalClient)
        # Return a URL that will 404
        mock_client.search.return_value = ["https://missing-page.org/404"]
        mock_client.fetch_url.return_value = RawWebDocument(
            url="https://missing-page.org/404",
            status_code=404,
            raw_html="",
            error="404 Not Found",
        )

        composite = CompositeRetrievalClient(mock_client=mock_client, offline_mode=True)
        sq = SubQuery("sq-01", "Testing", "technical", "test query", 1, "test")

        batch = composite.retrieve_batch(topic="Testing", sub_queries=[sq])
        self.assertIsInstance(batch, RetrievalBatch)
        self.assertEqual(len(batch.failed_urls), 1)
        self.assertEqual(batch.failed_urls[0]["url"], "https://missing-page.org/404")
        self.assertEqual(len(batch.documents), 0)


if __name__ == "__main__":
    unittest.main()
