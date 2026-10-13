"""Adversarial Stress Test Suite for Milestone 2: Chunking & BM25 Relevance Filtering.

Authored by Adversarial Challenger 1.
Empirically stress-tests PassageChunker and BM25Filter against:
- Empty, whitespace, zero-width, and minimal documents
- Short documents (<150 words like doc_04_edge_minimal.html) and exact boundary transitions
- Single massive paragraphs (>1000 words) with and without sentence punctuation
- Unicode, chemical formulas (Li6PS5Cl), temperatures (°C), currency, and decimal numbers (12.0)
- Documents with empty/intermingled paragraphs
- Deterministic passage ID sequences ({doc_id}-p{idx:03d}) and word count invariants
- Distractor fixture rejection (doc_05_irrelevant_solar.html, doc_05_irrelevant_crypto.html)
- Pure distractor corpora and zero-match disjoint queries (all scores 0.0)
- Stopword-only queries and tokenizer fallback
- Multi-query composite weighting (0.4 topic + 0.6 facet) and subquery attribution
- Relative thresholding, absolute floor (s_min), and top-K fallback boundaries
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

# Ensure project root and src directory are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.research_synthesis.models import (
    CleanArticle,
    DocumentMetadata,
    RawWebDocument,
    RetrievalBatch,
    ScoredPassage,
    SubQuery,
)
from src.research_synthesis.extraction.chunker import PassageChunker
from src.research_synthesis.extraction.bm25 import BM25Filter, OkapiBM25, PureBM25
from src.research_synthesis.retrieval.parser import DocumentParser


# ============================================================================
# Test Suite 1: Adversarial Stress Testing of PassageChunker
# ============================================================================

class TestPassageChunkerAdversarial(unittest.TestCase):
    """Adversarial stress harness for PassageChunker (Feature F6)."""

    def setUp(self):
        self.chunker = PassageChunker(min_words=150, max_words=250, overlap_words=40)
        self.meta = DocumentMetadata(
            url="https://example.org/test-doc",
            canonical_url="https://example.org/canonical-test-doc",
            domain="example.org",
            title="Adversarial Test Document",
            word_count=0,
        )

    def test_empty_and_whitespace_documents_produce_empty_list(self):
        """Empty, whitespace-only, and zero-width text documents must return empty list."""
        cases = [
            # 1. Completely empty paragraphs and text
            CleanArticle(doc_id="empty-1", url="https://a.com", metadata=self.meta, cleaned_text="", paragraphs=[]),
            # 2. Whitespace-only paragraphs
            CleanArticle(doc_id="empty-2", url="https://a.com", metadata=self.meta, cleaned_text="   \n\n\t  ", paragraphs=["   ", "\t\t", "\n\n"]),
            # 3. None-like paragraphs with empty text
            CleanArticle(doc_id="empty-3", url="https://a.com", metadata=self.meta, cleaned_text="   ", paragraphs=[]),
            # 4. Zero-width and invisible unicode characters
            CleanArticle(doc_id="empty-4", url="https://a.com", metadata=self.meta, cleaned_text="\u200b\u200c\u200d", paragraphs=["\u200b\u200c"]),
        ]
        for article in cases:
            passages = self.chunker.chunk_article(article)
            self.assertEqual(passages, [], f"Article {article.doc_id} should return empty list, got {passages}")

    def test_documents_with_intermingled_empty_paragraphs(self):
        """Paragraphs containing empty strings or whitespace must be stripped without corrupting sequence."""
        paragraphs = [
            "",
            "This is the first valid substantive paragraph with adequate information about solid-state materials.",
            "   ",
            "\n\t",
            "This is the second valid paragraph containing critical findings on ionic conductivity and impedance.",
            "",
        ]
        article = CleanArticle(
            doc_id="intermingled-1",
            url="https://a.com",
            metadata=self.meta,
            cleaned_text="\n\n".join(paragraphs),
            paragraphs=paragraphs,
        )
        passages = self.chunker.chunk_article(article)
        self.assertEqual(len(passages), 1, "Total words < 150 should emit single passage")
        self.assertEqual(passages[0].passage_id, "intermingled-1-p000")
        self.assertNotIn("   ", passages[0].text)
        self.assertIn("first valid substantive paragraph", passages[0].text)
        self.assertIn("second valid paragraph", passages[0].text)

    def test_short_document_preservation_with_fixture(self):
        """Real fixture doc_04_edge_minimal.html (<150 words) preserved as exactly one -p000 passage."""
        fixture_path = PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "microplastics" / "doc_04_edge_minimal.html"
        self.assertTrue(fixture_path.exists(), f"Fixture missing at {fixture_path}")

        raw_doc = RawWebDocument(
            url="https://mock-eco-briefs.org/notes/microplastic-earthworm-mortality-baseline",
            raw_html=fixture_path.read_text(encoding="utf-8"),
            status_code=200,
            headers={"Content-Type": "text/html"},
        )
        article = DocumentParser.parse(raw_doc)
        self.assertLess(article.metadata.word_count, 150)

        passages = self.chunker.chunk_article(article)
        self.assertEqual(len(passages), 1, "Short document fixture must yield exactly one passage")
        passage = passages[0]
        self.assertEqual(passage.passage_id, f"{article.doc_id}-p000")
        self.assertEqual(passage.doc_id, article.doc_id)
        self.assertEqual(passage.url, article.metadata.canonical_url)
        self.assertEqual(passage.title, article.metadata.title)
        self.assertEqual(passage.word_count, len(passage.text.split()))
        self.assertLess(passage.word_count, 150)
        self.assertIn("Lumbricus terrestris", passage.text)

    def test_boundary_condition_149_vs_150_words(self):
        """149-word article preserved as single -p000 chunk; 150-word article chunked properly."""
        words_149 = ["word"] * 149
        art_149 = CleanArticle("bound-149", "https://a.com", self.meta, " ".join(words_149), [" ".join(words_149)])
        passages_149 = self.chunker.chunk_article(art_149)
        self.assertEqual(len(passages_149), 1)
        self.assertEqual(passages_149[0].passage_id, "bound-149-p000")
        self.assertEqual(passages_149[0].word_count, 149)

        words_150 = ["word"] * 150
        art_150 = CleanArticle("bound-150", "https://a.com", self.meta, " ".join(words_150), [" ".join(words_150)])
        passages_150 = self.chunker.chunk_article(art_150)
        self.assertEqual(len(passages_150), 1)
        self.assertEqual(passages_150[0].passage_id, "bound-150-p000")
        self.assertEqual(passages_150[0].word_count, 150)

    def test_single_massive_paragraph_over_1000_words(self):
        """Monolithic paragraph with >1000 words must split at sentence boundaries without data loss."""
        sentence_template = "The electrochemical performance of sulfide solid electrolytes demonstrates high ionic conductivity of 12.0 mS/cm under ambient dry conditions."
        # Repeat sentence 60 times (~1080 words)
        sentences = [f"Observation {i}: {sentence_template}" for i in range(60)]
        massive_text = " ".join(sentences)
        total_words = len(massive_text.split())
        self.assertGreater(total_words, 1000)

        article = CleanArticle(
            doc_id="massive-doc",
            url="https://a.com/massive",
            metadata=self.meta,
            cleaned_text=massive_text,
            paragraphs=[massive_text],
        )

        passages = self.chunker.chunk_article(article)
        self.assertGreater(len(passages), 4, f"Expected >= 5 passages for >1000 words, got {len(passages)}")

        # Verify sequential ID numbering: -p000, -p001, -p002, etc.
        for idx, p in enumerate(passages):
            self.assertEqual(p.passage_id, f"massive-doc-p{idx:03d}")
            self.assertEqual(p.doc_id, "massive-doc")
            self.assertGreater(p.word_count, 50)
            self.assertLessEqual(p.word_count, 280, f"Passage {idx} word count {p.word_count} exceeds upper budget")

        # Verify no data loss: first observation in passage 0, last observation in last passage
        self.assertIn("Observation 0:", passages[0].text)
        self.assertIn("Observation 59:", passages[-1].text)

    def test_monolithic_paragraph_without_punctuation(self):
        """Unbroken >1000-word paragraph with zero punctuation terminates safely without hanging."""
        unbroken_text = "word " * 1200
        article = CleanArticle(
            doc_id="unbroken-doc",
            url="https://a.com/unbroken",
            metadata=self.meta,
            cleaned_text=unbroken_text.strip(),
            paragraphs=[unbroken_text.strip()],
        )
        passages = self.chunker.chunk_article(article)
        self.assertGreaterEqual(len(passages), 1)
        self.assertEqual(passages[0].passage_id, "unbroken-doc-p000")
        self.assertEqual(passages[0].word_count, 1200)

    def test_unicode_and_scientific_notation_preservation(self):
        """Preserves chemical formulas, decimal numbers, abbreviations, and international characters."""
        text = (
            "In recent tests, Dr. Rostova examined Li6PS5Cl argyrodite electrolytes at 25 °C. "
            "The room-temperature ionic conductivity reached 12.0 mS/cm, exceeding conventional standards by 33.2%. "
            "Furthermore, e.g., in the U.S. and EU, capital investment surpassed $50M in 2025. "
            "Interfacial shear modulus reached ~60 GPa without dendrite short-circuiting."
        )
        # Repeat to create ~300 words
        full_text = "\n\n".join([f"Paragraph {i}: {text}" for i in range(6)])
        article = CleanArticle(
            doc_id="unicode-doc",
            url="https://a.com/unicode",
            metadata=self.meta,
            cleaned_text=full_text,
            paragraphs=[f"Paragraph {i}: {text}" for i in range(6)],
        )

        passages = self.chunker.chunk_article(article)
        self.assertGreater(len(passages), 1)
        for p in passages:
            # Verify abbreviations & decimals are intact and not fragmented
            self.assertIn("12.0 mS/cm", p.text)
            self.assertIn("Li6PS5Cl", p.text)
            self.assertIn("°C", p.text)
            self.assertIn("U.S.", p.text)

    def test_chunk_batch_heterogeneous_collection(self):
        """chunk_batch seamlessly processes mixed batches of empty, short, and standard articles."""
        short_art = CleanArticle("art-short", "https://s.com", self.meta, "Short text under 150 words.", ["Short text under 150 words."])
        empty_art = CleanArticle("art-empty", "https://e.com", self.meta, "", [])
        standard_paras = [" ".join(["cell"] * 75), " ".join(["battery"] * 75), " ".join(["anode"] * 75)]
        standard_art = CleanArticle("art-std", "https://std.com", self.meta, "\n\n".join(standard_paras), standard_paras)

        batch = RetrievalBatch(topic="Battery", sub_queries=[], documents=[short_art, empty_art, standard_art])
        passages = self.chunker.chunk_batch(batch)

        doc_ids = {p.doc_id for p in passages}
        self.assertIn("art-short", doc_ids)
        self.assertNotIn("art-empty", doc_ids, "Empty article should produce 0 passages")
        self.assertIn("art-std", doc_ids)


# ============================================================================
# Test Suite 2: Adversarial Stress Testing of BM25Filter & OkapiBM25
# ============================================================================

class TestBM25FilterAdversarial(unittest.TestCase):
    """Adversarial stress harness for BM25 relevance filtering (Feature F7)."""

    def setUp(self):
        self.chunker = PassageChunker(min_words=150, max_words=250, overlap_words=40)
        self.bm25_filter = BM25Filter(k1=1.5, b=0.75, alpha=0.25, s_min=0.5, min_passages=2, top_k_fallback=3)

    def _load_and_chunk_fixture(self, rel_path: str) -> list[ScoredPassage]:
        fixture_path = PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / rel_path
        self.assertTrue(fixture_path.exists(), f"Fixture missing: {fixture_path}")
        raw_doc = RawWebDocument(
            url=f"https://mock-test.org/{Path(rel_path).stem}",
            raw_html=fixture_path.read_text(encoding="utf-8"),
            status_code=200,
            headers={"Content-Type": "text/html"},
        )
        article = DocumentParser.parse(raw_doc)
        return self.chunker.chunk_article(article)

    def test_distractor_elimination_solar_against_solid_state_battery(self):
        """doc_05_irrelevant_solar.html must be completely rejected when queried on solid-state batteries."""
        battery_passages = self._load_and_chunk_fixture("solid_state_battery/doc_01_nature_materials.html")
        solar_passages = self._load_and_chunk_fixture("solid_state_battery/doc_05_irrelevant_solar.html")

        self.assertGreater(len(battery_passages), 0)
        self.assertGreater(len(solar_passages), 0)

        corpus = battery_passages + solar_passages
        topic = "solid-state lithium battery electrolyte ionic conductivity"
        subqueries = [
            SubQuery("sq-1", topic, "electrolyte conductivity", "sulfide oxide solid electrolyte ionic conductivity"),
            SubQuery("sq-2", topic, "lithium metal interface", "interfacial contact impedance lithium metal LLZO"),
        ]

        filtered = self.bm25_filter.filter(corpus, topic=topic, sub_queries=subqueries)
        retained_doc_ids = {p.doc_id for p in filtered}
        solar_doc_id = solar_passages[0].doc_id
        battery_doc_id = battery_passages[0].doc_id

        self.assertIn(battery_doc_id, retained_doc_ids, "Relevant battery document must be retained")
        self.assertNotIn(solar_doc_id, retained_doc_ids, "Solar distractor must be completely eliminated")

    def test_distractor_elimination_crypto_against_supply_chain_reshoring(self):
        """doc_05_irrelevant_crypto.html must be completely rejected when queried on supply chain reshoring."""
        reshoring_passages = self._load_and_chunk_fixture("supply_chain_reshoring/doc_01_imf_economic_outlook.html")
        crypto_passages = self._load_and_chunk_fixture("supply_chain_reshoring/doc_05_irrelevant_crypto.html")

        corpus = reshoring_passages + crypto_passages
        topic = "semiconductor supply chain reshoring manufacturing incentives"
        subqueries = [
            SubQuery("sq-1", topic, "industrial subsidies", "semiconductor fab subsidies manufacturing reshoring"),
        ]

        filtered = self.bm25_filter.filter(corpus, topic=topic, sub_queries=subqueries)
        retained_doc_ids = {p.doc_id for p in filtered}
        crypto_doc_id = crypto_passages[0].doc_id
        reshoring_doc_id = reshoring_passages[0].doc_id

        self.assertIn(reshoring_doc_id, retained_doc_ids, "Relevant reshoring document must be retained")
        self.assertNotIn(crypto_doc_id, retained_doc_ids, "Crypto distractor must be completely eliminated")

    def test_pure_distractor_corpus_returns_empty_list(self):
        """Corpus containing ONLY distractor passages returns empty list, not false positives."""
        solar_passages = self._load_and_chunk_fixture("solid_state_battery/doc_05_irrelevant_solar.html")
        filtered = self.bm25_filter.filter(
            solar_passages,
            topic="solid-state lithium battery electrolyte ionic conductivity",
        )
        self.assertEqual(filtered, [], "Pure distractor corpus must yield empty list without fallback hallucinations")

    def test_zero_match_query_returns_empty_list(self):
        """Query with terms completely disjoint from corpus returns empty list (all scores 0.0)."""
        passages = [
            ScoredPassage("p1", "d1", "u1", "T1", "Solid-state electrolyte ionic conductivity at room temperature.", 0.0, "", 8),
            ScoredPassage("p2", "d2", "u2", "T2", "Lithium metal anode degradation in pouch cells.", 0.0, "", 8),
        ]
        # Disjoint query terms
        filtered = self.bm25_filter.filter(passages, topic="astronomical telescope gravitational lensing cosmology")
        self.assertEqual(filtered, [], "Disjoint query with zero term matches must yield empty list")

    def test_queries_consisting_solely_of_stopwords(self):
        """Queries containing only stopwords must trigger tokenizer fallback and handle gracefully."""
        passages = [
            ScoredPassage("p1", "d1", "u1", "T1", "Solid electrolyte materials with high ionic transport.", 0.0, "", 8),
            ScoredPassage("p2", "d2", "u2", "T2", "Battery performance under cycling pressure.", 0.0, "", 6),
        ]
        # Query of pure stopwords
        stopword_query = "to be or not to be and what is the"
        tokens = OkapiBM25.tokenize(stopword_query, filter_stopwords=True)
        # Tokenizer fallback: returns raw tokens if all tokens were stopwords
        self.assertGreater(len(tokens), 0, "Stopword query must fall back to raw tokens rather than returning []")

        # When filtered against passages containing content words, score is 0.0, returning empty
        filtered = self.bm25_filter.filter(passages, topic=stopword_query)
        self.assertEqual(filtered, [])

    def test_multi_query_composite_weighting(self):
        """Passage matching narrow subquery receives facet boost (0.6 facet vs 0.4 topic)."""
        # Passage A matches broad topic words ("battery", "materials")
        p_topic = ScoredPassage("p-topic", "d1", "u1", "T1", "Battery materials battery testing battery cells battery research.", 0.0, "", 8)
        # Passage B matches specific facet query ("argyrodite sulfide ionic conductivity")
        p_facet = ScoredPassage("p-facet", "d2", "u2", "T2", "Argyrodite sulfide ionic conductivity reaches 12 mS/cm under dry argon.", 0.0, "", 10)

        subqueries = [
            SubQuery("sq-01", "Battery", "ionic conductivity", "argyrodite sulfide ionic conductivity"),
        ]

        # Multi-query filter: 0.4 * topic + 0.6 * facet
        f = BM25Filter(topic_weight=0.4, facet_weight=0.6, s_min=0.1, min_passages=1)
        filtered = f.filter([p_topic, p_facet], topic="Battery materials", sub_queries=subqueries)

        self.assertGreaterEqual(len(filtered), 1)
        # Passage B should rank highest due to 0.6 facet weight on exact technical tokens
        self.assertEqual(filtered[0].passage_id, "p-facet")
        self.assertEqual(filtered[0].subquery, "argyrodite sulfide ionic conductivity")

    def test_relative_threshold_tau_computation(self):
        """Threshold tau = max(s_min, alpha * s_max) correctly enforces relative pruning."""
        passages = [
            ScoredPassage("p1", "d1", "u1", "T1", "Solid state electrolyte ionic conductivity lithium battery.", 0.0, "", 8),
            ScoredPassage("p2", "d2", "u2", "T2", "Solid state electrolyte ionic conductivity.", 0.0, "", 5),
            ScoredPassage("p3", "d3", "u3", "T3", "Marginal mention of battery.", 0.0, "", 4),
        ]
        # alpha=0.5: requires score to be >= 50% of the top passage score
        f = BM25Filter(alpha=0.5, s_min=0.1, min_passages=1)
        filtered = f.filter(passages, topic="Solid state electrolyte ionic conductivity lithium battery")

        passage_ids = [p.passage_id for p in filtered]
        self.assertIn("p1", passage_ids)
        self.assertNotIn("p3", passage_ids, "Low-scoring passage p3 should be pruned by alpha=0.5 cutoff")

    def test_top_k_fallback_when_threshold_is_too_stringent(self):
        """When s_min is set unrealistically high, fallback retains top-K scoring passages with score > 0."""
        passages = [
            ScoredPassage("p1", "d1", "u1", "T1", "Solid-state electrolyte ionic conductivity.", 0.0, "", 5),
            ScoredPassage("p2", "d2", "u2", "T2", "Lithium battery cell manufacturing.", 0.0, "", 5),
            ScoredPassage("p3", "d3", "u3", "T3", "Completely unrelated gardening flowers.", 0.0, "", 4),
        ]
        # s_min=99.0 would filter everything
        f = BM25Filter(s_min=99.0, min_passages=2, top_k_fallback=2)
        filtered = f.filter(passages, topic="solid-state battery")

        self.assertEqual(len(filtered), 2, "Fallback should retain exactly 2 non-zero scoring passages")
        self.assertNotIn("p3", [p.passage_id for p in filtered], "Zero-scoring distractor must never be retained by fallback")


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    unittest.main()
