"""Test additions and updates for M1 Mock Corpus Loading and Query Decomposer."""

import unittest
from pathlib import Path
from src.research_synthesis.retrieval.decomposer import HeuristicQueryDecomposer
from src.research_synthesis.retrieval.retriever import MockWebRetrievalClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "manifest.json"


class TestMockRetrieverRemediationVerification(unittest.TestCase):
    """Verifies that MockWebRetrievalClient parses manifest.json and loads HTML fixtures."""

    def test_manifest_loads_all_fixtures_by_url(self):
        client = MockWebRetrievalClient(corpus_path=str(MANIFEST_PATH))
        # Ensure all 18 documents from manifest.json are indexed
        self.assertEqual(len(client._corpus), 18)

        # Check key format: All keys must be canonical URLs
        for url in client._corpus.keys():
            self.assertTrue(url.startswith("https://") or url.startswith("http://"), f"Key is not a URL: {url}")

        # Check that HTML fixtures were actually loaded from disk
        doc_ssb = client._corpus["https://mock-science.org/materials/solid-electrolyte-conductivities-breakthrough"]
        self.assertIsNotNone(doc_ssb.get("raw_html"))
        self.assertIn("Solid Electrolyte Materials and Room-Temperature", doc_ssb["raw_html"])
        self.assertGreater(len(doc_ssb["raw_html"]), 1000)

        # Check that body was populated for keyword search
        self.assertIn("conductivities", doc_ssb["body"].lower())

    def test_search_and_fetch_with_manifest_corpus(self):
        client = MockWebRetrievalClient(corpus_path=str(MANIFEST_PATH))
        urls = client.search("solid electrolyte ionic conductivity sulfide", limit=3)
        self.assertGreaterEqual(len(urls), 1)
        self.assertTrue(urls[0].startswith("https://"))

        # Fetch canonical URL returns status 200 with raw HTML
        doc = client.fetch_url(urls[0])
        self.assertEqual(doc.status_code, 200)
        self.assertIn("<html", doc.raw_html.lower())
        self.assertIsNone(doc.error)

    def test_fetch_by_doc_id_alias(self):
        client = MockWebRetrievalClient(corpus_path=str(MANIFEST_PATH))
        # Fetching by document ID should resolve to the document via alias
        doc = client.fetch_url("ssb_01_nature_materials")
        self.assertEqual(doc.status_code, 200)
        self.assertEqual(doc.url, "https://mock-science.org/materials/solid-electrolyte-conductivities-breakthrough")
        self.assertIn("Solid Electrolyte Materials", doc.raw_html)

    def test_fallback_when_path_omitted_or_missing(self):
        # Omitted corpus_path -> loads built-in DEFAULT_MOCK_CORPUS
        client_omitted = MockWebRetrievalClient(corpus_path=None)
        self.assertEqual(len(client_omitted._corpus), 4)
        urls = client_omitted.search("solid-state batteries energy density")
        self.assertGreaterEqual(len(urls), 1)

        # Non-existent corpus_path -> loads built-in DEFAULT_MOCK_CORPUS
        client_missing = MockWebRetrievalClient(corpus_path="nonexistent/directory/path")
        self.assertEqual(len(client_missing._corpus), 4)
        urls2 = client_missing.search("solid-state batteries energy density")
        self.assertGreaterEqual(len(urls2), 1)


class TestDecomposerComparativeRemediationVerification(unittest.TestCase):
    """Verifies that HeuristicQueryDecomposer handles queries beginning with comparative phrases."""

    def setUp(self):
        self.decomposer = HeuristicQueryDecomposer()

    def test_comparison_between_detected(self):
        topic = "comparison between Solid-State and Lithium-Ion"
        is_comp, ent_a, ent_b = self.decomposer._detect_comparative(topic)
        self.assertTrue(is_comp)
        self.assertEqual(ent_a, "Solid-State")
        self.assertEqual(ent_b, "Lithium-Ion")

        res = self.decomposer.decompose(topic, max_subqueries=5)
        self.assertEqual(len(res.sub_queries), 5)
        facets = [sq.facet for sq in res.sub_queries]
        self.assertIn("comparative", facets)
        self.assertIn("technical", facets)

    def test_tradeoffs_between_detected(self):
        topic = "trade-offs between Solid-State and Lithium-Ion"
        is_comp, ent_a, ent_b = self.decomposer._detect_comparative(topic)
        self.assertTrue(is_comp)
        self.assertEqual(ent_a, "Solid-State")
        self.assertEqual(ent_b, "Lithium-Ion")

    def test_differences_between_detected(self):
        topic = "differences between Solid-State and Lithium-Ion"
        is_comp, ent_a, ent_b = self.decomposer._detect_comparative(topic)
        self.assertTrue(is_comp)
        self.assertEqual(ent_a, "Solid-State")
        self.assertEqual(ent_b, "Lithium-Ion")

    def test_prefixed_articles_and_variations(self):
        variations = [
            "a comparison between Solar and Wind",
            "the trade-offs between Solar and Wind",
            "the differences between Solar and Wind",
            "differences of Solar and Wind",
            "trade-off between Solar and Wind",
            "comparison of Solar and Wind",
        ]
        for query in variations:
            is_comp, ent_a, ent_b = self.decomposer._detect_comparative(query)
            self.assertTrue(is_comp, f"Failed for query: {query}")
            self.assertEqual(ent_a, "Solar", f"Failed ent_a for: {query}")
            self.assertEqual(ent_b, "Wind", f"Failed ent_b for: {query}")
