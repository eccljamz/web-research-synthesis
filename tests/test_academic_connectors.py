"""Unit and integration tests for Academic Literature Retrieval Clients (arXiv & PubMed).

Milestone 4 Extension:
1. ArxivRetrievalClient Atom feed XML parsing, search extraction, and HTML abstraction synthesis.
2. PubMedRetrievalClient NCBI E-utilities (esearch + esummary) JSON retrieval, author mapping, and HTML synthesis.
3. CompositeRetrievalClient multi-engine cascade dispatching to academic providers.
"""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import MagicMock, patch

from research_synthesis.models import RawWebDocument
from research_synthesis.retrieval.cache import SQLiteDocumentCache
from research_synthesis.retrieval.retriever import (
    ArxivRetrievalClient,
    CompositeRetrievalClient,
    MockWebRetrievalClient,
    PubMedRetrievalClient,
)


ARXIV_SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title type="html">arXiv Query: search_query=all:quantum</title>
  <id>http://arxiv.org/api/1234</id>
  <updated>2026-10-13T00:00:00-04:00</updated>
  <entry>
    <id>http://arxiv.org/abs/2301.01234v1</id>
    <published>2023-01-15T12:00:00Z</published>
    <title>Fault-Tolerant Quantum Error Correction with Surface Codes</title>
    <summary>We demonstrate logical qubit threshold fidelity surpassing 99.9% under surface code syndromes.</summary>
    <author>
      <name>Dr. Raymond Chen</name>
    </author>
    <author>
      <name>Elena Rostova</name>
    </author>
    <link rel="alternate" type="text/html" href="https://arxiv.org/abs/2301.01234v1"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2302.05678v2</id>
    <published>2023-02-20T15:30:00Z</published>
    <title>High-Rate Quantum LDPC Architectures</title>
    <summary>Quantum Low-Density Parity-Check (qLDPC) codes significantly reduce physical qubit overhead.</summary>
    <author>
      <name>Prof. Maya Lin</name>
    </author>
    <link rel="alternate" type="text/html" href="https://arxiv.org/abs/2302.05678v2"/>
  </entry>
</feed>
"""

PUBMED_ESEARCH_JSON = json.dumps({
    "esearchresult": {
        "count": "2",
        "retmax": "2",
        "retstart": "0",
        "idlist": ["39123456", "39654321"],
    }
}).encode("utf-8")

PUBMED_ESUMMARY_JSON = json.dumps({
    "result": {
        "uids": ["39123456", "39654321"],
        "39123456": {
            "title": "Microplastic Particle Translocation Across Plant Vascular Systems",
            "pubdate": "2025 Jan 12",
            "source": "Nature Plants",
            "authors": [
                {"name": "Rodriguez M"},
                {"name": "Kim SH"},
            ],
        },
        "39654321": {
            "title": "Ecotoxicological Soil Impacts of Biodegradable Polymers",
            "pubdate": "2025 Mar 04",
            "source": "Environmental Pollution",
            "authors": [
                {"name": "Schmidt A"},
            ],
        },
    }
}).encode("utf-8")


class TestArxivRetrievalClient(unittest.TestCase):
    """Test arXiv Atom API retrieval, XML parsing, and structured HTML synthesis."""

    def setUp(self):
        self.client = ArxivRetrievalClient()

    @patch("urllib.request.urlopen")
    def test_search_and_fetch_url(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = ARXIV_SAMPLE_XML
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        urls = self.client.search("quantum error correction", limit=2)
        self.assertEqual(len(urls), 2)
        self.assertEqual(urls[0], "https://arxiv.org/abs/2301.01234v1")
        self.assertEqual(urls[1], "https://arxiv.org/abs/2302.05678v2")

        # Test fetch_url using internal cache
        doc = self.client.fetch_url("https://arxiv.org/abs/2301.01234v1")
        self.assertIsInstance(doc, RawWebDocument)
        self.assertEqual(doc.status_code, 200)
        self.assertIn("Fault-Tolerant Quantum Error Correction", doc.raw_html)
        self.assertIn("Dr. Raymond Chen, Elena Rostova", doc.raw_html)
        self.assertIn("99.9%", doc.raw_html)
        self.assertIn("2023-01-15", doc.raw_html)

    def test_can_handle(self):
        self.assertTrue(self.client.can_handle("https://arxiv.org/abs/2301.01234"))
        self.assertTrue(self.client.can_handle("http://arxiv.org/pdf/2301.01234.pdf"))
        self.assertFalse(self.client.can_handle("https://en.wikipedia.org/wiki/Quantum_computing"))

    @patch("urllib.request.urlopen")
    def test_search_handles_empty_or_error(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection timed out")
        urls = self.client.search("failure test", limit=2)
        self.assertEqual(urls, [])


class TestPubMedRetrievalClient(unittest.TestCase):
    """Test PubMed NCBI E-Utilities retrieval, author extraction, and HTML synthesis."""

    def setUp(self):
        self.client = PubMedRetrievalClient()

    @patch("urllib.request.urlopen")
    def test_search_and_fetch_url(self, mock_urlopen):
        # Return esearch response first, then esummary response
        mock_resp_search = MagicMock()
        mock_resp_search.read.return_value = PUBMED_ESEARCH_JSON
        mock_resp_search.__enter__.return_value = mock_resp_search

        mock_resp_summary = MagicMock()
        mock_resp_summary.read.return_value = PUBMED_ESUMMARY_JSON
        mock_resp_summary.__enter__.return_value = mock_resp_summary

        mock_urlopen.side_effect = [mock_resp_search, mock_resp_summary]

        urls = self.client.search("microplastics plant vascular", limit=2)
        self.assertEqual(len(urls), 2)
        self.assertEqual(urls[0], "https://pubmed.ncbi.nlm.nih.gov/39123456/")
        self.assertEqual(urls[1], "https://pubmed.ncbi.nlm.nih.gov/39654321/")

        # Test fetch_url using cached metadata
        doc = self.client.fetch_url("https://pubmed.ncbi.nlm.nih.gov/39123456/")
        self.assertIsInstance(doc, RawWebDocument)
        self.assertEqual(doc.status_code, 200)
        self.assertIn("Microplastic Particle Translocation Across Plant Vascular Systems", doc.raw_html)
        self.assertIn("Rodriguez M, Kim SH", doc.raw_html)
        self.assertIn("Nature Plants", doc.raw_html)
        self.assertIn("2025 Jan 12", doc.raw_html)

    def test_can_handle(self):
        self.assertTrue(self.client.can_handle("https://pubmed.ncbi.nlm.nih.gov/39123456/"))
        self.assertFalse(self.client.can_handle("https://google.com"))

    @patch("urllib.request.urlopen")
    def test_search_handles_error(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("HTTP 500 Internal Server Error")
        urls = self.client.search("failing pubmed query", limit=2)
        self.assertEqual(urls, [])


class TestAcademicCompositeIntegration(unittest.TestCase):
    """Test CompositeRetrievalClient integration with academic providers."""

    def test_composite_dispatches_to_cached_academic_client(self):
        arxiv_client = ArxivRetrievalClient()
        arxiv_client._entry_cache["https://arxiv.org/abs/test.001"] = {
            "url": "https://arxiv.org/abs/test.001",
            "title": "Quantum Error Mitigations",
            "authors": "Physicist Alpha",
            "published_date": "2026-01-01",
            "summary": "Mitigation techniques for noisy quantum processors.",
        }

        mock_client = MockWebRetrievalClient()
        composite = CompositeRetrievalClient(
            mock_client=mock_client,
            fallback_clients=[arxiv_client],
            offline_mode=False,
        )

        doc = composite.fetch_url("https://arxiv.org/abs/test.001")
        self.assertEqual(doc.status_code, 200)
        self.assertIn("Quantum Error Mitigations", doc.raw_html)
        self.assertIn("Physicist Alpha", doc.raw_html)


if __name__ == "__main__":
    unittest.main()
