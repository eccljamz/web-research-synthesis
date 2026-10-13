"""Tier 1 Unit and Component Tests for Milestone 2: Content Filtering & Claim Extraction.

Comprehensive test suite covering:
1. PassageChunker (F6): word budget, paragraph awareness, short doc preservation, oversized split.
2. OkapiBM25 & PureBM25 (F7): RSJ smoothed IDF, TF saturation, length normalization, tokenization.
3. BM25Filter (F7): multi-query composite scoring, relative thresholding, top-K fallback, distractor filtering.
4. SimHash64 & SimHashIndex (F8): 64-bit fingerprinting, Hamming distance, 4-bucket inverted index.
5. TwoStageDeduplicator (F8): exact hash stage, SimHash stage, co-citation/attribution preservation, score pooling.
6. ClaimExtractor (F9): abbreviation-safe segmentation, noise rejection, taxonomy classification,
   entity extraction, deterministic claim ID, confidence scoring, provenance snippets.
7. End-to-end integration across all four Milestone 2 components.

Pure Python standard library (unittest) - Zero external dependencies.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

# Ensure workspace root and src directory are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.research_synthesis.models import (
    ClaimType,
    CleanArticle,
    DocumentMetadata,
    ExtractedClaim,
    RetrievalBatch,
    ScoredPassage,
    SubQuery,
)
from src.research_synthesis.extraction.chunker import PassageChunker
from src.research_synthesis.extraction.bm25 import BM25Filter, OkapiBM25, PureBM25
from src.research_synthesis.extraction.dedup import (
    SimHash64,
    SimHashIndex,
    TwoStageDeduplicator,
    canonicalize_url,
    compute_exact_hash,
    normalize_text,
)
from src.research_synthesis.extraction.claims import ClaimExtractor, FactualClaimExtractor


# ============================================================================
# Test Suite 1: Feature F6 - Passage Chunker
# ============================================================================

class TestPassageChunker(unittest.TestCase):
    """Unit tests for paragraph-aware passage chunking."""

    def setUp(self):
        self.chunker = PassageChunker(min_words=150, max_words=250, overlap_words=40)
        self.meta = DocumentMetadata(
            url="https://example.com/test",
            canonical_url="https://example.com/test",
            domain="example.com",
            title="Test Battery Analysis",
            word_count=500,
        )

    def test_chunk_standard_article(self):
        """Standard ~500 word article produces multiple chunks with overlap."""
        paragraphs = [
            " ".join(["battery"] * 100),
            " ".join(["electrolyte"] * 100),
            " ".join(["density"] * 100),
            " ".join(["scalability"] * 100),
            " ".join(["commercialization"] * 100),
        ]
        article = CleanArticle(
            doc_id="doc-001",
            url="https://example.com/test",
            metadata=self.meta,
            cleaned_text="\n\n".join(paragraphs),
            paragraphs=paragraphs,
        )

        passages = self.chunker.chunk_article(article)
        self.assertGreater(len(passages), 1)
        for idx, p in enumerate(passages):
            self.assertEqual(p.doc_id, "doc-001")
            self.assertEqual(p.url, "https://example.com/test")
            self.assertEqual(p.title, "Test Battery Analysis")
            self.assertEqual(p.passage_id, f"doc-001-p{idx:03d}")
            self.assertGreater(p.word_count, 50)

    def test_chunk_short_article_preserved_single_chunk(self):
        """Short document (<150 words) preserved as a single chunk with -p000."""
        short_text = "This is a brief report with only fifty words describing a single factual development. " * 3
        article = CleanArticle(
            doc_id="doc-short",
            url="https://example.com/short",
            metadata=self.meta,
            cleaned_text=short_text,
            paragraphs=[short_text],
        )

        passages = self.chunker.chunk_article(article)
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0].passage_id, "doc-short-p000")
        self.assertEqual(passages[0].text, short_text.strip())
        self.assertEqual(passages[0].word_count, len(short_text.split()))

    def test_chunk_empty_and_minimal_article(self):
        """Empty or whitespace article produces an empty list."""
        empty_article = CleanArticle(
            doc_id="doc-empty",
            url="https://example.com/empty",
            metadata=self.meta,
            cleaned_text="   \n\t  ",
            paragraphs=[],
        )
        self.assertEqual(self.chunker.chunk_article(empty_article), [])

    def test_chunk_oversized_paragraph_split(self):
        """Monolithic paragraph (>250 words) is split at sentence boundaries."""
        sentences = [f"Sentence number {i} provides detailed engineering observations on solid electrolytes." for i in range(35)]
        long_paragraph = " ".join(sentences)
        self.assertGreater(len(long_paragraph.split()), 250)

        article = CleanArticle(
            doc_id="doc-oversized",
            url="https://example.com/oversized",
            metadata=self.meta,
            cleaned_text=long_paragraph,
            paragraphs=[long_paragraph],
        )

        passages = self.chunker.chunk_article(article)
        self.assertGreater(len(passages), 1)
        for p in passages:
            self.assertTrue(p.passage_id.startswith("doc-oversized-p"))
            self.assertLessEqual(p.word_count, 280)

    def test_chunk_batch_with_retrieval_batch(self):
        """chunk_batch correctly processes RetrievalBatch instances."""
        art1 = CleanArticle("d1", "https://a.com", self.meta, "Short doc 1 text.", ["Short doc 1 text."])
        art2 = CleanArticle("d2", "https://b.com", self.meta, "Short doc 2 text.", ["Short doc 2 text."])
        batch = RetrievalBatch(topic="Battery", sub_queries=[], documents=[art1, art2])

        passages = self.chunker.chunk_batch(batch)
        self.assertEqual(len(passages), 2)
        self.assertEqual(passages[0].passage_id, "d1-p000")
        self.assertEqual(passages[1].passage_id, "d2-p000")


# ============================================================================
# Test Suite 2: Feature F7 - Okapi BM25 Scorer
# ============================================================================

class TestOkapiBM25(unittest.TestCase):
    """Unit tests for pure-Python Okapi BM25 relevance scoring."""

    def setUp(self):
        self.bm25 = PureBM25(k1=1.5, b=0.75)
        self.corpus = [
            ["solid", "state", "battery", "energy", "density", "lithium", "metal"],
            ["solar", "photovoltaic", "panel", "efficiency", "silicon", "cells"],
            ["global", "supply", "chain", "logistics", "semiconductor", "shortage"],
        ]
        self.bm25.fit(self.corpus)

    def test_basic_scoring_and_ranking(self):
        """Matching document receives highest positive score; off-topic scores zero."""
        query = ["solid", "state", "battery"]
        score_doc0 = self.bm25.score(query, self.corpus[0])
        score_doc1 = self.bm25.score(query, self.corpus[1])
        score_doc2 = self.bm25.score(query, self.corpus[2])

        self.assertGreater(score_doc0, 0.0)
        self.assertEqual(score_doc1, 0.0)
        self.assertEqual(score_doc2, 0.0)

    def test_term_frequency_saturation(self):
        """Sub-linear term frequency scaling due to k1 parameter."""
        query = ["battery"]
        doc_2x = ["battery", "battery", "car", "motor"]
        doc_10x = ["battery"] * 10 + ["car", "motor"]

        score_2x = self.bm25.score(query, doc_2x)
        score_10x = self.bm25.score(query, doc_10x)

        self.assertGreater(score_10x, score_2x)
        self.assertLess(score_10x, score_2x * 5.0, "Score should saturate sub-linearly")

    def test_document_length_normalization(self):
        """Shorter document with same term count scores higher than longer document."""
        query = ["electrolyte"]
        short_doc = ["sulfide", "electrolyte", "powder"]
        long_doc = ["sulfide", "electrolyte", "powder"] + ["filler"] * 50

        bm25_len = PureBM25(k1=1.5, b=0.75)
        bm25_len.fit([short_doc, long_doc])

        score_short = bm25_len.score(query, short_doc)
        score_long = bm25_len.score(query, long_doc)

        self.assertGreater(score_short, score_long)

    def test_smoothed_idf_is_strictly_positive(self):
        """Robertson-Spärck Jones smoothed IDF ln((N - n + 0.5)/(n + 0.5) + 1.0) is > 0 even when n = N."""
        bm25 = OkapiBM25()
        # Corpus where "common" appears in all 3 documents
        corpus = [["common", "a"], ["common", "b"], ["common", "c"]]
        bm25.fit(corpus)
        self.assertIn("common", bm25.idf)
        self.assertGreater(bm25.idf["common"], 0.0)
        expected_idf = math.log((3 - 3 + 0.5) / (3 + 0.5) + 1.0)
        self.assertAlmostEqual(bm25.idf["common"], expected_idf, places=5)

    def test_tokenization_and_stopword_fallback(self):
        """Tokenizer strips stopwords but falls back to raw tokens if all tokens are stopwords."""
        tokens_normal = OkapiBM25.tokenize("The solid state battery of 2026")
        self.assertNotIn("the", tokens_normal)
        self.assertNotIn("of", tokens_normal)
        self.assertIn("solid", tokens_normal)
        self.assertIn("battery", tokens_normal)

        # All stopwords string
        tokens_all_stops = OkapiBM25.tokenize("to be or not to be")
        self.assertGreater(len(tokens_all_stops), 0, "Should fall back rather than returning empty")


# ============================================================================
# Test Suite 3: Feature F7 - BM25Filter
# ============================================================================

class TestBM25Filter(unittest.TestCase):
    """Unit tests for BM25Filter multi-query scoring and thresholding."""

    def test_distractor_elimination(self):
        """Off-topic distractor document receives low/zero score and is eliminated."""
        passages = [
            ScoredPassage("p1", "d1", "u1", "T1", "Solid-state electrolyte ionic conductivity at room temperature.", 0.0, "q", 8),
            ScoredPassage("p2", "d2", "u2", "T2", "High energy density lithium metal anode solid battery.", 0.0, "q", 9),
            ScoredPassage("p3", "d3", "u3", "T3", "Tandem perovskite solar photovoltaic cells achieve 33% efficiency.", 0.0, "q", 9),
        ]
        bm25_filter = BM25Filter(alpha=0.25, s_min=0.5)
        filtered = bm25_filter.filter(passages, topic="solid state battery electrolyte")

        passage_ids = [p.passage_id for p in filtered]
        self.assertIn("p1", passage_ids)
        self.assertNotIn("p3", passage_ids, "Solar distractor must be eliminated")

    def test_fallback_to_top_k(self):
        """When stringent threshold would prune all items, top-K fallback engages."""
        passages = [
            ScoredPassage("p1", "d1", "u1", "T1", "Marginally relevant mention of battery cells.", 0.0, "q", 6),
            ScoredPassage("p2", "d2", "u2", "T2", "Another small mention of battery technology.", 0.0, "q", 6),
            ScoredPassage("p3", "d3", "u3", "T3", "Completely unrelated text about gardening flowers.", 0.0, "q", 6),
        ]
        # Set an unrealistically high s_min
        bm25_filter = BM25Filter(s_min=10.0, min_passages=2, top_k_fallback=2)
        filtered = bm25_filter.filter(passages, topic="battery")

        self.assertGreaterEqual(len(filtered), 1)
        self.assertNotIn("p3", [p.passage_id for p in filtered])

    def test_multi_query_scoring_with_subqueries(self):
        """Sub-query matching boosts passage relevance score via facet weighting."""
        passages = [
            ScoredPassage("p1", "d1", "u1", "T1", "General overview of electric vehicle batteries.", 0.0, "q", 6),
            ScoredPassage("p2", "d2", "u2", "T2", "Argyrodite sulfide ionic conductivity reaching twelve mS per cm.", 0.0, "q", 10),
        ]
        subqueries = [
            SubQuery("sq-01", "Solid-State Battery", "ionic conductivity", "argyrodite sulfide ionic conductivity", priority=1),
        ]
        bm25_filter = BM25Filter(topic_weight=0.4, facet_weight=0.6, s_min=0.1)
        filtered = bm25_filter.filter(passages, topic="Solid-State Battery", sub_queries=subqueries)

        self.assertGreater(len(filtered), 0)
        self.assertEqual(filtered[0].passage_id, "p2")
        self.assertEqual(filtered[0].subquery, "argyrodite sulfide ionic conductivity")

    def test_empty_input_safety(self):
        """Empty passages or queries execute safely without exceptions."""
        bm25_filter = BM25Filter()
        self.assertEqual(bm25_filter.filter([], topic="battery"), [])
        self.assertEqual(bm25_filter.filter_passages([], query="battery"), [])


# ============================================================================
# Test Suite 4: Feature F8 - SimHash64 & SimHashIndex
# ============================================================================

class TestSimHash64(unittest.TestCase):
    """Unit tests for 64-bit locality-sensitive SimHash fingerprinting."""

    def test_identical_texts_zero_distance(self):
        text = "Commercial roll-to-roll lines must process flexible electrolyte membranes at 15 to 30 meters per minute."
        fp1 = SimHash64.compute_simhash(text)
        fp2 = SimHash64.compute_simhash(text)
        self.assertEqual(fp1, fp2)
        self.assertEqual(SimHash64.hamming_distance(fp1, fp2), 0)

    def test_near_duplicates_within_threshold(self):
        t1 = "Commercial roll-to-roll lines must process flexible electrolyte membranes at line speeds of at least 15 to 30 meters per minute without micro-crack formation."
        t2 = "Commercial roll-to-roll lines must process flexible electrolyte membranes at speeds of at least 15 to 30 meters per minute without micro crack formation."
        fp1 = SimHash64.compute(t1)
        fp2 = SimHash64.compute(t2)
        dist = SimHash64.hamming_distance(fp1, fp2)
        self.assertLessEqual(dist, 3, f"Expected Hamming distance <= 3, got {dist}")

    def test_distinct_texts_large_distance(self):
        t1 = "Sulfide solid electrolytes degrade rapidly when exposed to humidity above -40 degrees Celsius dew point."
        t2 = "Perovskite-silicon tandem photovoltaic cells achieve 33 percent efficiency record in solar testing."
        fp1 = SimHash64.compute(t1)
        fp2 = SimHash64.compute(t2)
        dist = SimHash64.hamming_distance(fp1, fp2)
        self.assertGreater(dist, 10, f"Expected distinct texts to have large Hamming distance, got {dist}")

    def test_empty_tokens_returns_zero(self):
        self.assertEqual(SimHash64.compute([]), 0)
        self.assertEqual(SimHash64.compute(""), 0)

    def test_compute_from_token_list(self):
        tokens = ["battery", "electrolyte", "conductivity", "sulfide", "membrane"]
        fp = SimHash64.compute(tokens)
        self.assertIsInstance(fp, int)
        self.assertGreater(fp, 0)


class TestSimHashIndex(unittest.TestCase):
    """Unit tests for 4-bucket inverted SimHash index."""

    def test_pigeonhole_retrieval(self):
        index = SimHashIndex(threshold=3)
        t1 = "Our computable general equilibrium econometric simulations indicate that severe fragmentation into competing trading blocs could reduce global GDP by 1.2% to 1.8%."
        fp1 = SimHash64.compute_simhash(t1)
        index.add("doc-1", fp1, metadata={"title": "IMF Outlook"})

        # Near-duplicate query
        t2 = "Computable general equilibrium econometric simulations indicate that severe fragmentation into competing trading blocs could reduce global GDP by 1.2% to 1.8%."
        fp2 = SimHash64.compute_simhash(t2)
        matches = index.find_near_duplicates(fp2)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "doc-1")
        self.assertLessEqual(matches[0][1], 3)

    def test_index_clear_and_len(self):
        index = SimHashIndex(threshold=3)
        index.add("d1", 12345, metadata="m1")
        self.assertEqual(len(index), 1)
        index.clear()
        self.assertEqual(len(index), 0)

    def test_simhash_index_with_mutable_dict_metadata(self):
        """Verify inserting mutable dict metadata does not raise TypeError."""
        index = SimHashIndex(threshold=3)
        meta = {"source": "IMF", "nested": {"count": 42}, "tags": ["econ", "trade"]}
        fp = 0x1234567890ABCDEF
        index.add("item-dict", fp, metadata=meta)
        matches = index.find_near_duplicates(fp)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "item-dict")
        self.assertEqual(matches[0][1], 0)
        self.assertEqual(matches[0][2], meta)

    def test_simhash_index_with_scored_passage_metadata(self):
        """Verify inserting ScoredPassage (mutable dataclass) does not raise TypeError."""
        index = SimHashIndex(threshold=3)
        passage = ScoredPassage(
            passage_id="p-001",
            doc_id="d-01",
            url="https://example.com/p",
            title="Battery Density Advances",
            text="Operating dry rooms incurs significant capital expenditure.",
            relevance_score=0.88,
            subquery="battery",
            word_count=8,
            secondary_urls=["https://example.com/sec1"],
        )
        fp = 0x1111222233334444
        index.add(passage.passage_id, fp, metadata=passage)
        matches = index.find_near_duplicates(fp)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "p-001")
        self.assertIs(matches[0][2], passage)
        self.assertIn("https://example.com/sec1", matches[0][2].secondary_urls)

    def test_simhash_index_with_extracted_claim_metadata(self):
        """Verify inserting ExtractedClaim (mutable dataclass) does not raise TypeError."""
        index = SimHashIndex(threshold=3)
        claim = ExtractedClaim(
            claim_id="clm-001",
            text="Solid-state cells achieved 500 Wh/kg energy density in laboratory testing.",
            source_doc_id="d-01",
            source_url="https://example.com/c",
            source_title="Battery Research",
            passage_snippet="Snippet context",
            confidence_score=0.92,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["LLZO", "Lithium"],
            secondary_urls=["https://example.com/c2"],
        )
        fp = 0xAAAABBBBCCCCDDDD
        index.add(claim.claim_id, fp, metadata=claim)
        matches = index.find_near_duplicates(fp)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "clm-001")
        self.assertIs(matches[0][2], claim)
        self.assertIn("LLZO", matches[0][2].entities)

    def test_simhash_index_multi_bucket_match_deduplication(self):
        """Verify that an item matching across multiple 16-bit blocks is returned exactly once."""
        index = SimHashIndex(threshold=3)
        index.add("multi-match", 0x0000000000000000, metadata={"k": "v"})
        # Query with exact match (all 4 blocks match identically)
        matches = index.find_near_duplicates(0x0000000000000000)
        self.assertEqual(len(matches), 1, "Candidate matching all 4 tables must not be duplicated in results")
        self.assertEqual(matches[0][0], "multi-match")


# ============================================================================
# Test Suite 5: Feature F8 - TwoStageDeduplicator
# ============================================================================

class TestTwoStageDeduplicator(unittest.TestCase):
    """Unit tests for exact hash and SimHash deduplication with attribution preservation."""

    def setUp(self):
        self.dedup = TwoStageDeduplicator(hamming_threshold=3)

    def test_exact_hash_and_url_canonicalization(self):
        t1 = "  The post-Cold War era... (2025). \n\t "
        t2 = "the postcold war era 2025"
        self.assertEqual(normalize_text(t1), t2)
        self.assertEqual(compute_exact_hash(t1), compute_exact_hash(t2))

        raw_url = "HTTPS://mock-science.org:443/materials/solid-electrolyte/?utm_source=twitter&ref=123#overview"
        expected_url = "https://mock-science.org/materials/solid-electrolyte"
        self.assertEqual(canonicalize_url(raw_url), expected_url)

    def test_exact_duplicate_passages_merged_with_attribution(self):
        p1 = ScoredPassage("p-001", "doc-01", "https://mock-imf-research.org/reports/geoeconomic-fragmentation", "IMF Report",
                           "Severe fragmentation into competing trading blocs could reduce global GDP by 1.2% to 1.8%.", 0.85, "trade", 16)
        p2 = ScoredPassage("p-002", "doc-04", "https://mock-global-market-wire.com/wire/imf-warns", "Market Wire",
                           "Severe fragmentation into competing trading blocs could reduce global GDP by 1.2% to 1.8%.", 0.92, "trade", 16)

        results = self.dedup.deduplicate_passages([p1, p2])
        self.assertEqual(len(results), 1)
        survivor = results[0]
        self.assertEqual(survivor.passage_id, "p-001")
        self.assertIn("https://mock-global-market-wire.com/wire/imf-warns", survivor.secondary_urls)
        self.assertEqual(survivor.relevance_score, 0.92, "Should retain maximum relevance score")

    def test_near_duplicate_passages_merged_with_attribution(self):
        p1 = ScoredPassage("p-001", "doc-01", "https://source-a.org/article", "Source A",
                           "Operating dry rooms at this specification incurs a capital expenditure premium of $18 million to $25 million per gigawatt-hour.", 0.80, "battery", 20)
        p2 = ScoredPassage("p-002", "doc-02", "https://source-b.com/reprint", "Source B",
                           "Operating dry rooms at this specification incurs capital expenditure premium of $18 million to $25 million per gigawatt-hour.", 0.75, "battery", 19)

        results = self.dedup.deduplicate_passages([p1, p2])
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0].secondary_urls), 1)
        self.assertEqual(results[0].secondary_urls[0], "https://source-b.com/reprint")

    def test_deduplicate_claims(self):
        c1 = ExtractedClaim("clm-1", "Room-temperature ionic conductivities surpassed 12.0 mS/cm at 25°C.", "d1",
                            "https://source1.com/art", "Title 1", "snippet", 0.80, ClaimType.QUANTITATIVE, ["LLZO"], [])
        c2 = ExtractedClaim("clm-2", "Room temperature ionic conductivities surpassed 12.0 mS/cm at 25°C.", "d2",
                            "https://source2.com/art", "Title 2", "snippet", 0.90, ClaimType.QUANTITATIVE, ["argyrodite"], [])

        results = self.dedup.deduplicate_claims([c1, c2])
        self.assertEqual(len(results), 1)
        survivor = results[0]
        self.assertEqual(survivor.confidence_score, 0.90)
        self.assertIn("https://source2.com/art", survivor.secondary_urls)
        self.assertIn("LLZO", survivor.entities)
        self.assertIn("argyrodite", survivor.entities)

    def test_deduplicate_polymorphic_entry_point(self):
        p = ScoredPassage("p-1", "d-1", "https://a.com", "A", "Sample text.", 0.5, "q", 2)
        res_passages = self.dedup.deduplicate([p])
        self.assertEqual(len(res_passages), 1)

        c = ExtractedClaim("c-1", "Sample text.", "d-1", "https://a.com", "A", "snip", 0.5, ClaimType.GENERAL_FACT, [], [])
        res_claims = self.dedup.deduplicate([c])
        self.assertEqual(len(res_claims), 1)


# ============================================================================
# Test Suite 6: Feature F9 - Sentence Segmentation Subsystem
# ============================================================================

class TestSentenceSegmentation(unittest.TestCase):
    """Unit tests for robust sentence segmentation with abbreviation protection."""

    def setUp(self):
        self.extractor = ClaimExtractor()

    def test_standard_multi_sentence_split(self):
        text = "First sentence here. Second sentence follows. Third sentence concludes."
        sents = self.extractor.segment_sentences(text)
        self.assertEqual(len(sents), 3)

    def test_abbreviation_protection(self):
        text = "The U.S. Department of Energy funded Dr. Smith et al. for battery R&D (e.g., solid-state cells). The pilot launched in Inc. facilities."
        sents = self.extractor.segment_sentences(text)
        self.assertEqual(len(sents), 2)
        self.assertIn("U.S.", sents[0])
        self.assertIn("Dr.", sents[0])
        self.assertIn("et al.", sents[0])
        self.assertIn("e.g.", sents[0])
        self.assertIn("Inc.", sents[1])

    def test_decimal_numbers_protection(self):
        text = "Conductivity reached 12.0 mS/cm at 25.5°C. Total funding exceeded $4.5 billion."
        sents = self.extractor.segment_sentences(text)
        self.assertEqual(len(sents), 2)
        self.assertIn("12.0", sents[0])
        self.assertIn("25.5°C", sents[0])
        self.assertIn("$4.5", sents[1])

    def test_url_protection(self):
        text = "For full details visit https://energy.gov/research.html before proceeding. Next phase begins soon."
        sents = self.extractor.segment_sentences(text)
        self.assertEqual(len(sents), 2)
        self.assertIn("https://energy.gov/research.html", sents[0])

    def test_sentence_terminal_no_does_not_suppress_split(self):
        """Sentence ending with 'no.' must split properly and not merge with next sentence."""
        text = "The initial hypothesis was no. Further testing disproved the theory."
        sents = self.extractor.segment_sentences(text)
        self.assertEqual(len(sents), 2, f"Expected 2 sentences, got {len(sents)}: {sents}")
        self.assertEqual(sents[0], "The initial hypothesis was no.")
        self.assertEqual(sents[1], "Further testing disproved the theory.")

    def test_sentence_terminal_variable_p_does_not_suppress_split(self):
        """Sentence ending with single letter variable 'p.' must split properly."""
        text = "The statistical parameter is denoted by p. Subsequent iterations update this value."
        sents = self.extractor.segment_sentences(text)
        self.assertEqual(len(sents), 2, f"Expected 2 sentences, got {len(sents)}: {sents}")
        self.assertEqual(sents[0], "The statistical parameter is denoted by p.")
        self.assertEqual(sents[1], "Subsequent iterations update this value.")

    def test_page_citation_abbreviation_protected_intra_sentence(self):
        """Page citation 'p. 42' must not trigger a split between 'p.' and '42'."""
        text = "Experimental protocols are described in p. 42 for replication. The results were confirmed."
        sents = self.extractor.segment_sentences(text)
        self.assertEqual(len(sents), 2)
        self.assertIn("p. 42", sents[0])
        self.assertEqual(sents[1], "The results were confirmed.")

    def test_issue_number_abbreviation_protected_intra_sentence(self):
        """Publication issue 'No. 5' must not trigger a split between 'No.' and '5'."""
        text = "The patent office issued Patent No. 5 to the research team. Commercial production began in 2026."
        sents = self.extractor.segment_sentences(text)
        self.assertEqual(len(sents), 2)
        self.assertIn("Patent No. 5", sents[0])
        self.assertEqual(sents[1], "Commercial production began in 2026.")

    def test_page_citation_at_sentence_boundary(self):
        """Page citation ending a sentence ('p. 42.') must terminate the sentence properly."""
        text = "The benchmark scores are summarized on p. 42. Next-generation prototypes showed further gains."
        sents = self.extractor.segment_sentences(text)
        self.assertEqual(len(sents), 2)
        self.assertEqual(sents[0], "The benchmark scores are summarized on p. 42.")
        self.assertEqual(sents[1], "Next-generation prototypes showed further gains.")

    def test_single_word_abbreviation_vs_terminal_period(self):
        """Confirm 'The answer was no. We continued.' splits into 2 sentences, while 'See p. 42 for details.' remains 1 sentence."""
        split_text = "The answer was no. We continued."
        sents_split = self.extractor.segment_sentences(split_text)
        self.assertEqual(len(sents_split), 2, f"Expected 2 sentences, got {len(sents_split)}: {sents_split}")
        self.assertEqual(sents_split[0], "The answer was no.")
        self.assertEqual(sents_split[1], "We continued.")

        single_text = "See p. 42 for details."
        sents_single = self.extractor.segment_sentences(single_text)
        self.assertEqual(len(sents_single), 1, f"Expected 1 sentence, got {len(sents_single)}: {sents_single}")
        self.assertEqual(sents_single[0], "See p. 42 for details.")


# ============================================================================
# Test Suite 7: Feature F9 - Claim Taxonomy & Classification
# ============================================================================

class TestClaimExtractorTaxonomy(unittest.TestCase):
    """Unit tests for claim taxonomy classification (QUANTITATIVE, TEMPORAL_EVENT, RELATIONAL, GENERAL_FACT)."""

    def setUp(self):
        self.extractor = ClaimExtractor()

    def test_extract_quantitative_claims(self):
        samples = [
            "Room-temperature ionic conductivities surpassed 12.0 mS/cm, yielding energy densities of 450 Wh/kg.",
            "Operating dry rooms incurs an estimated capital expenditure premium of $18 million to $25 million.",
            "Econometric simulations indicate global GDP could decline by between 1.2% and 1.8%.",
        ]
        for s in samples:
            c_type = self.extractor.classify_claim_type(s)
            self.assertEqual(c_type, ClaimType.QUANTITATIVE, f"Failed on: {s}")

    def test_extract_temporal_event_claims(self):
        samples = [
            "The Maunder Minimum solar lull occurred between 1645 and 1715 across Western Eurasia.",
            "Automotive OEMs have initiated pilot line production targeting sample cells by late 2026.",
            "Major volcanic eruptions occurred in 1600, 1641, and during 1693.",
        ]
        for s in samples:
            c_type = self.extractor.classify_claim_type(s)
            self.assertEqual(c_type, ClaimType.TEMPORAL_EVENT, f"Failed on: {s}")

    def test_extract_relational_claims(self):
        samples = [
            "Sulfide argyrodites demonstrated ionic conductivity superior to traditional oxide ceramics.",
            "Duplicative investments in parallel fabrication plants resulted in lower aggregate capital efficiency.",
            "Supply chain disruptions were directly correlated with semiconductor shortages across automotive plants.",
        ]
        for s in samples:
            c_type = self.extractor.classify_claim_type(s)
            self.assertEqual(c_type, ClaimType.RELATIONAL, f"Failed on: {s}")

    def test_extract_general_fact_claims(self):
        samples = [
            "The Department of Energy established a national laboratory consortium to accelerate battery commercialization.",
            "QuantumScape and Solid Power deployed dry electrode processing technologies in their pilot facilities.",
        ]
        for s in samples:
            c_type = self.extractor.classify_claim_type(s)
            self.assertEqual(c_type, ClaimType.GENERAL_FACT, f"Failed on: {s}")


# ============================================================================
# Test Suite 8: Feature F9 - Noise and Gatekeeping Rejection
# ============================================================================

class TestClaimExtractorNoiseFiltering(unittest.TestCase):
    """Unit tests verifying that noise, imperatives, questions, and baseless hedges are filtered out."""

    def setUp(self):
        self.extractor = ClaimExtractor()

    def test_reject_interrogatives(self):
        questions = [
            "Will solid-state batteries replace lithium-ion cells in mass market EVs?",
            "Can domestic supply chain reshoring lower consumer goods inflation?",
        ]
        for q in questions:
            self.assertIsNone(self.extractor.classify_claim_type(q))

    def test_reject_imperatives_and_calls_to_action(self):
        actions = [
            "Click here to download our full investment whitepaper and register for updates!",
            "Sign up for our newsletter to receive weekly battery technology updates.",
            "Be the first to leave a comment on this post!",
        ]
        for a in actions:
            self.assertIsNone(self.extractor.classify_claim_type(a))

    def test_reject_speculative_hedges_without_grounding(self):
        hedges = [
            "It remains to be seen whether any of these ambitious concepts will ever materialize in the real world.",
            "In our view, nobody knows whether current market dynamics will persist over time.",
        ]
        for h in hedges:
            self.assertIsNone(self.extractor.classify_claim_type(h))

    def test_reject_short_fragments(self):
        fragments = [
            "Table of Contents.",
            "Home > Articles > Battery Tech.",
            "Figure 1: Overview.",
        ]
        for f in fragments:
            self.assertIsNone(self.extractor.classify_claim_type(f))


# ============================================================================
# Test Suite 9: Feature F9 - Provenance, Entities, Confidence & Deterministic ID
# ============================================================================

class TestClaimExtractorProvenanceAndConfidence(unittest.TestCase):
    """Unit tests for entity extraction, deterministic claim ID, and confidence scoring."""

    def setUp(self):
        self.extractor = ClaimExtractor()
        self.passage = ScoredPassage(
            passage_id="p-001",
            doc_id="doc-abc123",
            url="https://mock-science.org/battery-materials",
            title="Breakthrough in Argyrodite Solid Electrolytes",
            text=(
                "Solid electrolyte research has accelerated worldwide. "
                "Sulfide argyrodites achieved ionic conductivities surpassing 12.0 mS/cm at 25°C. "
                "Toyota and QuantumScape have validated these results on pilot lines."
            ),
            relevance_score=0.88,
            subquery="solid electrolyte ionic conductivity",
            word_count=28,
            secondary_urls=["https://mirror-news.com/battery"],
        )

    def test_deterministic_claim_id(self):
        text = "Sulfide argyrodites achieved ionic conductivities surpassing 12.0 mS/cm at 25°C."
        url = "https://mock-science.org/battery-materials"

        id1 = ClaimExtractor.generate_claim_id(url, text)
        id2 = ClaimExtractor.generate_claim_id(url, text)
        id_diff_url = ClaimExtractor.generate_claim_id("https://other.org", text)
        id_diff_text = ClaimExtractor.generate_claim_id(url, "Different text.")

        self.assertEqual(id1, id2, "Claim ID must be 100% deterministic")
        self.assertTrue(id1.startswith("clm-"))
        self.assertEqual(len(id1), 16)
        self.assertNotEqual(id1, id_diff_url)
        self.assertNotEqual(id1, id_diff_text)

    def test_entity_extraction(self):
        sent = "Toyota and QuantumScape deployed LLZO oxide electrolytes in the United States."
        entities = self.extractor.extract_entities(sent)
        self.assertIn("Toyota", entities)
        self.assertIn("QuantumScape", entities)
        self.assertIn("LLZO", entities)
        self.assertIn("United States", entities)

    def test_passage_extraction_provenance_and_snippets(self):
        claims = self.extractor.extract_claims_from_passage(self.passage)
        self.assertGreaterEqual(len(claims), 1)

        target_claim = next(c for c in claims if "12.0 mS/cm" in c.text)
        self.assertEqual(target_claim.source_doc_id, "doc-abc123")
        self.assertEqual(target_claim.source_url, "https://mock-science.org/battery-materials")
        self.assertEqual(target_claim.source_title, "Breakthrough in Argyrodite Solid Electrolytes")
        self.assertEqual(target_claim.claim_type, ClaimType.QUANTITATIVE)
        self.assertIn("https://mirror-news.com/battery", target_claim.secondary_urls)
        self.assertIn("Solid electrolyte research has accelerated worldwide", target_claim.passage_snippet)
        self.assertGreaterEqual(target_claim.confidence_score, 0.70)
        self.assertLessEqual(target_claim.confidence_score, 1.0)


# ============================================================================
# Test Suite 10: End-to-End Extraction Pipeline Integration
# ============================================================================

class TestExtractionPipelineIntegration(unittest.TestCase):
    """Integration test connecting Chunker -> BM25 -> Deduplication -> Claim Extraction."""

    def test_end_to_end_m2_pipeline(self):
        doc_meta = DocumentMetadata(
            url="https://nature.org/ssb-advances",
            canonical_url="https://nature.org/ssb-advances",
            domain="nature.org",
            title="Next-Generation Solid-State Battery Commercialization",
            word_count=350,
        )
        paragraphs = [
            "Next-generation solid-state lithium batteries offer enhanced safety and energy density.",
            "Sulfide-based argyrodite electrolytes demonstrated ionic conductivity surpassing 12.0 mS/cm at 25°C. "
            "Integrating pure lithium metal anodes unlocks theoretical gravimetric energy densities between 450 and 520 Wh/kg.",
            "Automotive original equipment manufacturers (OEMs), including Toyota and BMW, targeting pilot production by late 2026. "
            "Operating industrial dry rooms incurs a capital expenditure premium of $18 million to $25 million per GWh.",
        ]
        article = CleanArticle(
            doc_id="doc-integration-1",
            url=doc_meta.url,
            metadata=doc_meta,
            cleaned_text="\n\n".join(paragraphs),
            paragraphs=paragraphs,
        )

        # 1. Chunking
        chunker = PassageChunker(min_words=30, max_words=200, overlap_words=10)
        passages = chunker.chunk_article(article)
        self.assertGreater(len(passages), 0)

        # 2. BM25 Filtering
        bm25_filter = BM25Filter(min_threshold=0.01)
        scored_passages = bm25_filter.filter_passages(passages, query="solid state battery ionic conductivity energy density")
        self.assertGreater(len(scored_passages), 0)

        # 3. Deduplication
        dedup = TwoStageDeduplicator()
        deduped_passages = dedup.deduplicate_passages(scored_passages)
        self.assertGreater(len(deduped_passages), 0)

        # 4. Claim Extraction
        extractor = ClaimExtractor(min_confidence=0.4)
        claims = extractor.extract_claims(deduped_passages)
        self.assertGreater(len(claims), 0)

        # Assert claims have valid taxonomy and non-empty IDs
        claim_types = {c.claim_type for c in claims}
        self.assertIn(ClaimType.QUANTITATIVE, claim_types)
        for c in claims:
            self.assertTrue(c.claim_id.startswith("clm-"))
            self.assertGreaterEqual(c.confidence_score, 0.4)
            self.assertEqual(c.source_url, "https://nature.org/ssb-advances")


if __name__ == "__main__":
    unittest.main()
