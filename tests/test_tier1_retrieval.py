"""Tier 1 Unit and Component Tests: Query Decomposition & Web Retrieval.

Tests models, HeuristicQueryDecomposer, RobustHTMLParser, DocumentParser,
MockWebRetrievalClient, LiveHttpRetrievalClient, and CompositeRetrievalClient.
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.research_synthesis.models import (
    ClaimType,
    CleanArticle,
    DecompositionResult,
    DocumentMetadata,
    ExtractedClaim,
    KeyTakeaway,
    RawWebDocument,
    ResearchBrief,
    RetrievalBatch,
    SourceCitation,
    SubQuery,
    ThematicSection,
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


class TestModels(unittest.TestCase):
    """Test shared data contracts and serialization."""

    def test_subquery_creation_and_serialization(self):
        sq = SubQuery(
            id="sq-01",
            original_topic="Solid-State Batteries",
            facet="technical",
            search_query="Solid-state battery technical architecture",
            priority=1,
            rationale="Explore core technical mechanism",
        )
        d = sq.to_dict()
        self.assertEqual(d["id"], "sq-01")
        self.assertEqual(d["facet"], "technical")
        recreated = SubQuery.from_dict(d)
        self.assertEqual(recreated.id, sq.id)
        self.assertEqual(recreated.search_query, sq.search_query)

    def test_decomposition_result_roundtrip(self):
        sq = SubQuery("sq-01", "AI", "technical", "AI fundamentals", 1, "Why")
        res = DecompositionResult(topic="AI", sub_queries=[sq])
        d = res.to_dict()
        self.assertEqual(d["topic"], "AI")
        self.assertEqual(len(d["sub_queries"]), 1)
        recreated = DecompositionResult.from_dict(d)
        self.assertEqual(recreated.topic, "AI")
        self.assertEqual(recreated.sub_queries[0].id, "sq-01")

    def test_clean_article_and_metadata_serialization(self):
        meta = DocumentMetadata(
            url="https://example.com/test",
            canonical_url="https://example.com/test",
            domain="example.com",
            title="Example Title",
            author="Jane Doe",
            published_date="2024-01-01",
            word_count=100,
            character_count=600,
        )
        art = CleanArticle(
            doc_id="abcdef0123456789",
            url="https://example.com/test",
            metadata=meta,
            cleaned_text="Paragraph one.\n\nParagraph two.",
            paragraphs=["Paragraph one.", "Paragraph two."],
            headings=["Heading 1"],
            subquery_id="sq-01",
            subquery_facet="technical",
        )
        d = art.to_dict()
        self.assertEqual(d["doc_id"], "abcdef0123456789")
        self.assertEqual(d["metadata"]["author"], "Jane Doe")
        recreated = CleanArticle.from_dict(d)
        self.assertEqual(recreated.doc_id, art.doc_id)
        self.assertEqual(recreated.metadata.title, "Example Title")
        self.assertEqual(len(recreated.paragraphs), 2)

    def test_research_brief_properties_and_serialization(self):
        takeaway = KeyTakeaway(text="Core finding here.", citation_indices=[1])
        section = ThematicSection(
            section_id="sec-01",
            title="Technical Foundations",
            narrative="Solid state batteries provide high density [1].",
            citation_indices=[1],
            claim_ids=["CLM-01"],
            key_findings=["Finding 1"],
        )
        src = SourceCitation(
            citation_index=1,
            source_id="SRC-01",
            title="Battery Journal",
            url="https://example.com/battery",
            author="Dr. Smith",
            publish_date="2024-01-01",
            snippet="High density achieved.",
        )
        brief = ResearchBrief(
            brief_id="brief-1234",
            topic="Solid-State Batteries",
            executive_summary="Solid state batteries are emerging [1].",
            key_takeaways=[takeaway],
            thematic_sections=[section],
            sources=[src],
            metadata={"retrieval_mode": "mock"},
        )

        # Test property aliases
        self.assertEqual(brief.query, "Solid-State Batteries")
        self.assertEqual(len(brief.sections), 1)

        # Test to_dict
        d = brief.to_dict()
        self.assertEqual(d["brief_id"], "brief-1234")
        self.assertEqual(d["query"], "Solid-State Batteries")
        self.assertIn("thematic_sections", d)
        self.assertIn("sections", d)

        # Test to_json
        j_str = brief.to_json()
        parsed_j = json.loads(j_str)
        self.assertEqual(parsed_j["brief_id"], "brief-1234")

        # Test to_markdown
        md = brief.to_markdown()
        self.assertIn("# Research Brief: Solid-State Batteries", md)
        self.assertIn("## Executive Summary", md)
        self.assertIn("[1] **Battery Journal**", md)

        # Test from_dict
        recreated = ResearchBrief.from_dict(d)
        self.assertEqual(recreated.brief_id, brief.brief_id)
        self.assertEqual(recreated.thematic_sections[0].title, "Technical Foundations")


class TestHeuristicQueryDecomposer(unittest.TestCase):
    """Test HeuristicQueryDecomposer logic and edge cases."""

    def setUp(self):
        self.decomposer = HeuristicQueryDecomposer()

    def test_empty_or_invalid_topic_raises_error(self):
        with self.assertRaises(ValueError):
            self.decomposer.decompose("")
        with self.assertRaises(ValueError):
            self.decomposer.decompose("   \n\t  ")
        with self.assertRaises(TypeError):
            self.decomposer.decompose(None)  # type: ignore

    def test_standard_decomposition_orthogonal_facets(self):
        topic = "Solid-State Battery Commercialization"
        result = self.decomposer.decompose(topic, max_subqueries=5)

        self.assertEqual(result.topic, topic)
        self.assertEqual(result.strategy_used, "heuristic_rule_based")
        self.assertEqual(len(result.sub_queries), 5)

        facets = [sq.facet for sq in result.sub_queries]
        expected_facets = ["technical", "economic", "challenges", "comparative", "temporal"]
        self.assertEqual(facets, expected_facets)

        for idx, sq in enumerate(result.sub_queries, start=1):
            self.assertEqual(sq.id, f"sq-{idx:02d}")
            self.assertEqual(sq.priority, idx)
            self.assertTrue(len(sq.search_query) > len(topic))
            self.assertTrue(len(sq.rationale) > 10)

    def test_comparative_pattern_vs(self):
        topic = "Solid-State vs Lithium-Ion"
        result = self.decomposer.decompose(topic)

        self.assertEqual(len(result.sub_queries), 5)
        # Check that comparative and entity-specific queries were generated
        sq_facets = [sq.facet for sq in result.sub_queries]
        self.assertIn("comparative", sq_facets)
        self.assertIn("economic", sq_facets)

        search_texts = [sq.search_query.lower() for sq in result.sub_queries]
        # Should reference solid-state and lithium-ion
        self.assertTrue(any("solid-state" in q for q in search_texts))
        self.assertTrue(any("lithium-ion" in q for q in search_texts))

    def test_comparative_pattern_compared_to(self):
        topic = "Hydrogen Fuel Cells compared to Battery Electric Vehicles"
        result = self.decomposer.decompose(topic)
        self.assertGreaterEqual(len(result.sub_queries), 4)
        queries = " ".join([sq.search_query.lower() for sq in result.sub_queries])
        self.assertIn("hydrogen fuel cells", queries)
        self.assertIn("battery electric vehicles", queries)

    def test_comparative_pattern_comparison_between(self):
        topic = "comparison between Solid-State and Lithium-Ion"
        result = self.decomposer.decompose(topic)
        self.assertEqual(len(result.sub_queries), 5)
        sq_facets = [sq.facet for sq in result.sub_queries]
        self.assertIn("comparative", sq_facets)
        search_texts = [sq.search_query.lower() for sq in result.sub_queries]
        self.assertTrue(any("solid-state" in q for q in search_texts))
        self.assertTrue(any("lithium-ion" in q for q in search_texts))

    def test_comparative_pattern_tradeoffs_between(self):
        topic = "trade-offs between Solid-State and Lithium-Ion"
        result = self.decomposer.decompose(topic)
        self.assertEqual(len(result.sub_queries), 5)
        sq_facets = [sq.facet for sq in result.sub_queries]
        self.assertIn("comparative", sq_facets)

    def test_single_word_expansion(self):
        topic = "Microplastics"
        result = self.decomposer.decompose(topic, max_subqueries=3)
        self.assertEqual(len(result.sub_queries), 3)
        for sq in result.sub_queries:
            self.assertIn("Microplastics", sq.search_query)

    def test_conversational_filler_removal(self):
        topic = "Can you please research the state of global supply chain re-shoring?"
        result = self.decomposer.decompose(topic)
        self.assertEqual(len(result.sub_queries), 5)
        # The sub-queries should not repeat the filler prompt
        first_query = result.sub_queries[0].search_query.lower()
        self.assertNotIn("can you please research", first_query)

    def test_max_subqueries_capping(self):
        topic = "Quantum Computing"
        res2 = self.decomposer.decompose(topic, max_subqueries=2)
        self.assertEqual(len(res2.sub_queries), 2)


class TestRobustHTMLParserAndDocumentParser(unittest.TestCase):
    """Test RobustHTMLParser and DocumentParser."""

    def test_boilerplate_stripping(self):
        raw_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Breakthroughs in Energy Storage - Tech Review</title>
            <meta property="og:title" content="Breakthroughs in Energy Storage">
            <meta name="author" content="Dr. Jane Smith">
            <meta property="article:published_time" content="2024-04-15">
            <link rel="canonical" href="https://techreview.org/energy-storage">
            <style>body { font-size: 16px; } .cookie { display: block; }</style>
            <script>console.log("analytics tracker");</script>
        </head>
        <body>
            <header>
                <nav><a href="/home">Home</a> | <a href="/about">About</a></nav>
            </header>
            <div id="cookie-banner" class="cookie-popup">
                Please accept our cookies to continue reading.
            </div>
            <main>
                <h1>Solid State Battery Developments</h1>
                <p>Solid state electrolytes offer substantial improvements in safety by eliminating flammable liquids.</p>
                <aside class="sidebar-ad">
                    <p>Subscribe to our newsletter for daily updates!</p>
                </aside>
                <p>Commercialization timelines project high volume pilot manufacturing by 2026 across major OEMs.</p>
            </main>
            <footer>
                <p>&copy; 2024 Tech Review. All rights reserved.</p>
            </footer>
        </body>
        </html>
        """
        raw_doc = RawWebDocument(
            url="https://techreview.org/energy-storage",
            status_code=200,
            headers={"Content-Type": "text/html"},
            raw_html=raw_html,
        )

        article = DocumentParser.parse(raw_doc)

        self.assertEqual(article.metadata.title, "Breakthroughs in Energy Storage")
        self.assertEqual(article.metadata.author, "Dr. Jane Smith")
        self.assertEqual(article.metadata.published_date, "2024-04-15")
        self.assertEqual(article.metadata.canonical_url, "https://techreview.org/energy-storage")
        self.assertEqual(article.metadata.domain, "techreview.org")
        self.assertEqual(len(article.doc_id), 16)
        self.assertEqual(len(article.metadata.doc_id), 16)
        self.assertEqual(article.doc_id, article.metadata.doc_id)

        # Assert boilerplate is stripped
        cleaned_text = article.cleaned_text
        self.assertNotIn("analytics tracker", cleaned_text)
        self.assertNotIn("Please accept our cookies", cleaned_text)
        self.assertNotIn("Subscribe to our newsletter", cleaned_text)
        self.assertNotIn("All rights reserved", cleaned_text)

        # Assert valid article paragraphs are retained
        self.assertIn("Solid state electrolytes offer substantial improvements", cleaned_text)
        self.assertIn("Commercialization timelines project high volume pilot", cleaned_text)
        self.assertEqual(len(article.paragraphs), 2)
        self.assertIn("Solid State Battery Developments", article.headings)

    def test_title_and_metadata_fallbacks(self):
        raw_html = """
        <html>
        <head><title>Simple Page Title</title></head>
        <body>
            <p>This is a valid paragraph with sufficient length to pass the minimum character count filter.</p>
        </body>
        </html>
        """
        raw_doc = RawWebDocument(
            url="https://example.org/news/sample-story",
            status_code=200,
            headers={},
            raw_html=raw_html,
        )
        article = DocumentParser.parse(raw_doc)
        self.assertEqual(article.metadata.title, "Simple Page Title")
        self.assertEqual(article.metadata.author, "example.org")
        self.assertIsNone(article.metadata.published_date)

    def test_malformed_html_tolerance(self):
        malformed = "<div><p>Unclosed paragraph with valid content that exceeds the twenty-five character minimum threshold."
        raw_doc = RawWebDocument(
            url="https://example.org/broken",
            status_code=200,
            headers={},
            raw_html=malformed,
        )
        article = DocumentParser.parse(raw_doc)
        self.assertGreaterEqual(len(article.paragraphs), 1)
        self.assertIn("Unclosed paragraph", article.cleaned_text)


class TestMockWebRetrievalClient(unittest.TestCase):
    """Test MockWebRetrievalClient search, indexing, and fetch."""

    def setUp(self):
        self.client = MockWebRetrievalClient()

    def test_default_corpus_search_and_fetch(self):
        urls = self.client.search("solid-state batteries energy density", limit=2)
        self.assertGreaterEqual(len(urls), 1)
        self.assertIn("energy-tech-review.org", urls[0])

        doc = self.client.fetch_url(urls[0])
        self.assertEqual(doc.status_code, 200)
        self.assertIn("Solid-State Battery Breakthroughs", doc.raw_html)
        self.assertIsNone(doc.error)

    def test_missing_url_returns_404(self):
        doc = self.client.fetch_url("https://unknown-domain-test.org/404")
        self.assertEqual(doc.status_code, 404)
        self.assertIsNotNone(doc.error)

    def test_custom_corpus_injection(self):
        custom = {
            "https://custom-lab.org/study-1": {
                "title": "Quantum Photonics Study",
                "body": "Photonic quantum computing chips demonstrated high qubit fidelity exceeding 99.8% at room temperature.",
            }
        }
        client = MockWebRetrievalClient(corpus_dict=custom)
        urls = client.search("quantum photonics", limit=1)
        self.assertEqual(urls, ["https://custom-lab.org/study-1"])
        doc = client.fetch_url("https://custom-lab.org/study-1")
        self.assertEqual(doc.status_code, 200)
        self.assertIn("Photonic quantum computing", doc.raw_html)

    def test_manifest_corpus_loading_and_fetch(self):
        manifest_p = os.path.join(os.path.dirname(__file__), "fixtures", "mock_corpus", "manifest.json")
        if os.path.exists(manifest_p):
            client = MockWebRetrievalClient(corpus_path=manifest_p)
            self.assertEqual(len(client._corpus), 18)
            urls = client.search("solid electrolyte ionic conductivity", limit=2)
            self.assertGreaterEqual(len(urls), 1)
            self.assertTrue(urls[0].startswith("http"))
            doc = client.fetch_url(urls[0])
            self.assertEqual(doc.status_code, 200)
            self.assertGreater(len(doc.raw_html), 100)
            # Test doc_id alias resolution
            alias_doc = client.fetch_url("ssb_01_nature_materials")
            self.assertEqual(alias_doc.status_code, 200)
            self.assertEqual(alias_doc.url, "https://mock-science.org/materials/solid-electrolyte-conductivities-breakthrough")


class TestLiveHttpRetrievalClient(unittest.TestCase):
    """Test LiveHttpRetrievalClient error handling, retries, and caching."""

    def setUp(self):
        self.client = LiveHttpRetrievalClient(
            max_retries=2,
            backoff_factor=0.01,
            rate_limit_delay=0.01,
        )

    def test_cache_hit_avoids_repeated_requests(self):
        mock_doc = RawWebDocument("https://cached-example.org", 200, {}, "<html><body><p>Cached text here with length.</p></body></html>")
        self.client._cache["https://cached-example.org"] = mock_doc

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = self.client.fetch_url("https://cached-example.org")
            self.assertEqual(result, mock_doc)
            mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_retry_on_429_then_succeeds(self, mock_urlopen):
        # First call raises 429, second call succeeds
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_response.read.return_value = b"<html><body><p>Success after retry paragraph.</p></body></html>"
        mock_response.__enter__.return_value = mock_response

        err_429 = urllib.error.HTTPError("https://rate-limited.org", 429, "Too Many Requests", {}, io.BytesIO(b""))

        mock_urlopen.side_effect = [err_429, mock_response]

        doc = self.client.fetch_url("https://rate-limited.org")
        self.assertEqual(doc.status_code, 200)
        self.assertIn("Success after retry", doc.raw_html)
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("urllib.request.urlopen")
    def test_non_text_mime_type_skipped(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.__enter__.return_value = mock_response

        mock_urlopen.return_value = mock_response

        doc = self.client.fetch_url("https://example.org/whitepaper.pdf")
        self.assertEqual(doc.status_code, 200)
        self.assertEqual(doc.raw_html, "")
        self.assertIn("Skipping non-text MIME type", doc.error or "")


class TestCompositeRetrievalClient(unittest.TestCase):
    """Test CompositeRetrievalClient failover and batch retrieval."""

    def test_offline_mode_routes_to_mock(self):
        live_client = MagicMock(spec=LiveHttpRetrievalClient)
        mock_client = MockWebRetrievalClient()
        composite = CompositeRetrievalClient(
            live_client=live_client,
            mock_client=mock_client,
            offline_mode=True,
        )

        urls = composite.search("solid-state batteries", limit=2)
        self.assertGreaterEqual(len(urls), 1)
        live_client.search.assert_not_called()

        doc = composite.fetch_url(urls[0])
        self.assertEqual(doc.status_code, 200)
        live_client.fetch_url.assert_not_called()

    def test_live_failure_transparent_fallback(self):
        live_client = MagicMock(spec=LiveHttpRetrievalClient)
        live_client.search.side_effect = urllib.error.URLError("DNS resolution failed")
        live_client.fetch_url.side_effect = urllib.error.URLError("Connection refused")

        mock_client = MockWebRetrievalClient()
        composite = CompositeRetrievalClient(
            live_client=live_client,
            mock_client=mock_client,
            offline_mode=False,
        )

        urls = composite.search("solid-state", limit=2)
        self.assertGreaterEqual(len(urls), 1)
        self.assertTrue(composite.offline_mode)

        doc = composite.fetch_url(urls[0])
        self.assertEqual(doc.status_code, 200)

    def test_retrieve_batch_end_to_end(self):
        decomposer = HeuristicQueryDecomposer()
        composite = CompositeRetrievalClient(offline_mode=True)
        decomp_result = decomposer.decompose("Solid-State Battery Commercialization", max_subqueries=3)

        batch = composite.retrieve_batch(
            topic=decomp_result.topic,
            sub_queries=decomp_result.sub_queries,
            limit_per_subquery=2,
        )

        self.assertIsInstance(batch, RetrievalBatch)
        self.assertEqual(batch.topic, "Solid-State Battery Commercialization")
        self.assertEqual(len(batch.sub_queries), 3)
        self.assertGreaterEqual(len(batch.documents), 1)
        self.assertGreater(batch.total_fetched, 0)
        self.assertGreaterEqual(batch.total_cleaned, 1)

        first_article = batch.documents[0]
        self.assertIsInstance(first_article, CleanArticle)
        self.assertTrue(len(first_article.metadata.title) > 0)
        self.assertTrue(len(first_article.paragraphs) > 0)
        self.assertTrue(len(first_article.cleaned_text) > 50)
        self.assertIsNotNone(first_article.subquery_id)


if __name__ == "__main__":
    unittest.main()
