"""Unit and integration tests for SQLite persistent caching and extended search connectors.

Tests:
1. SQLiteDocumentCache storage, retrieval, TTL expiration, and pruning.
2. DuckDuckGoLiteRetrievalClient and WikipediaRetrievalClient interface conformance.
3. CompositeRetrievalClient integration with fallback search engines.
"""

import tempfile
import time
import unittest
from pathlib import Path

from research_synthesis.models import RawWebDocument
from research_synthesis.retrieval.cache import SQLiteDocumentCache
from research_synthesis.retrieval.retriever import (
    CompositeRetrievalClient,
    DuckDuckGoLiteRetrievalClient,
    LiveHttpRetrievalClient,
    MockWebRetrievalClient,
    WikipediaRetrievalClient,
)


class TestSQLiteDocumentCache(unittest.TestCase):
    """Test SQLite-based persistent document and query cache."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_cache.db"
        self.cache = SQLiteDocumentCache(db_path=self.db_path, default_ttl=3600)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_put_and_get_document(self):
        doc = RawWebDocument(
            url="https://example.com/test",
            status_code=200,
            headers={"Content-Type": "text/html"},
            raw_html="<html><body><p>Cached content</p></body></html>",
        )
        self.cache.put_document(doc)

        cached = self.cache.get_document("https://example.com/test")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.url, "https://example.com/test")
        self.assertEqual(cached.status_code, 200)
        self.assertIn("Cached content", cached.raw_html)

    def test_missing_and_expired_document(self):
        # Missing
        self.assertIsNone(self.cache.get_document("https://nonexistent.org"))

        # Expired TTL
        doc = RawWebDocument(
            url="https://example.com/expiring",
            status_code=200,
            headers={},
            raw_html="<p>Expiring fast</p>",
        )
        self.cache.put_document(doc, ttl_seconds=1)
        time.sleep(1.2)
        self.assertIsNone(self.cache.get_document("https://example.com/expiring"))

    def test_put_and_get_search_query(self):
        query = "Solid-State Battery"
        urls = ["https://example.com/1", "https://example.com/2"]
        self.cache.put_search(query, urls)

        cached_urls = self.cache.get_search(query)
        self.assertEqual(cached_urls, urls)

        # Case insensitivity & whitespace trimming
        cached_variant = self.cache.get_search("  solid-state battery  ")
        self.assertEqual(cached_variant, urls)

    def test_clear_and_count(self):
        doc = RawWebDocument(url="https://a.com", status_code=200, headers={}, raw_html="a")
        self.cache.put_document(doc)
        self.cache.put_search("q", ["https://a.com"])

        doc_count, search_count = self.cache.count()
        self.assertEqual(doc_count, 1)
        self.assertEqual(search_count, 1)

        self.cache.clear()
        doc_count, search_count = self.cache.count()
        self.assertEqual(doc_count, 0)
        self.assertEqual(search_count, 0)


class TestExtendedSearchConnectors(unittest.TestCase):
    """Test extended search engine connectors and multi-engine failover."""

    def test_connector_interfaces(self):
        ddg_lite = DuckDuckGoLiteRetrievalClient()
        wiki = WikipediaRetrievalClient()

        self.assertTrue(hasattr(ddg_lite, "search"))
        self.assertTrue(hasattr(ddg_lite, "fetch_url"))
        self.assertTrue(hasattr(wiki, "search"))
        self.assertTrue(hasattr(wiki, "fetch_url"))

    def test_composite_retrieval_with_fallbacks(self):
        mock = MockWebRetrievalClient()
        composite = CompositeRetrievalClient(
            mock_client=mock,
            offline_mode=True,
            fallback_clients=[DuckDuckGoLiteRetrievalClient(), WikipediaRetrievalClient()],
        )
        urls = composite.search("solid-state", limit=2)
        self.assertGreaterEqual(len(urls), 1)

        doc = composite.fetch_url(urls[0])
        self.assertEqual(doc.status_code, 200)
        self.assertTrue(doc.raw_html)


if __name__ == "__main__":
    unittest.main()
