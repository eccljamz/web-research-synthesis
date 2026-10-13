"""Adversarial Stress Test Suite for Milestone 2: SimHash Deduplication & Claim Extraction.

Authored by Adversarial Challenger 2.
Empirically stress-tests:
1. SimHash64 & SimHashIndex:
   - Near-duplicate text pairs (1-word replacement, punctuation change) verifying Hamming distance <= 3
   - Distinct text pairs verifying Hamming distance > 10
2. TwoStageDeduplicator:
   - 3+ duplicate documents verifying transitive attribution merging into secondary_urls and max score pooling
   - Pre-existing secondary_urls propagation and entity set unioning
3. ClaimExtractor:
   - Abbreviation & decimal safe sentence splitting ("U.S. GDP grew by 2.5% in Q3. Dr. Smith reported...")
   - Decimal numbers, metric units (500 Wh/kg), and currency ($10.5 billion)
   - Noise filtering for interrogative sentences ("Why do batteries fail?") and imperatives ("Click here to learn more.")
   - Strict confidence score boundary adherence [0.0, 1.0] across all scenarios
"""

from __future__ import annotations

import re
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

try:
    from research_synthesis.models import (
        ClaimType,
        ExtractedClaim,
        ScoredPassage,
    )
    from research_synthesis.extraction.dedup import (
        SimHash64,
        SimHashIndex,
        TwoStageDeduplicator,
        canonicalize_url,
        compute_exact_hash,
        normalize_text,
    )
    from research_synthesis.extraction.claims import (
        ClaimExtractor,
        FactualClaimExtractor,
    )
except ImportError:
    from src.research_synthesis.models import (
        ClaimType,
        ExtractedClaim,
        ScoredPassage,
    )
    from src.research_synthesis.extraction.dedup import (
        SimHash64,
        SimHashIndex,
        TwoStageDeduplicator,
        canonicalize_url,
        compute_exact_hash,
        normalize_text,
    )
    from src.research_synthesis.extraction.claims import (
        ClaimExtractor,
        FactualClaimExtractor,
    )


class TestSimHashNearDuplicatesStress(unittest.TestCase):
    """Adversarial stress tests for SimHash locality sensitivity on near-duplicates."""

    def test_one_word_replacement_in_standard_passage(self):
        """1-word substitution in a 24-word passage produces Hamming distance <= 3."""
        base = (
            "Commercial roll-to-roll lines must process flexible electrolyte membranes "
            "at line speeds of at least 15 to 30 meters per minute without micro-crack formation."
        )
        variant = (
            "Commercial roll-to-roll lines must process flexible electrolyte membranes "
            "at line speeds of at least 15 to 30 meters per minute without microcrack formation."
        )
        fp1 = SimHash64.compute(base)
        fp2 = SimHash64.compute(variant)
        dist = SimHash64.hamming_distance(fp1, fp2)
        self.assertLessEqual(dist, 3, f"Expected Hamming distance <= 3 for hyphen variation, got {dist}")

    def test_synonym_substitution_in_long_passage(self):
        """Single-word synonym replacement in an ~80 word passage produces Hamming distance <= 3."""
        text_a = (
            "Solid electrolyte research has accelerated substantially across international research consortia. "
            "Sulfide argyrodites demonstrated ionic conductivity surpassing 12.0 mS/cm at 25 degrees Celsius. "
            "Integrating pure lithium metal anodes unlocks theoretical gravimetric energy densities between 450 "
            "and 520 Wh/kg. Automotive original equipment manufacturers including Toyota have targeted pilot lines."
        )
        # Replace 'surpassing' with 'exceeding'
        text_b = (
            "Solid electrolyte research has accelerated substantially across international research consortia. "
            "Sulfide argyrodites demonstrated ionic conductivity exceeding 12.0 mS/cm at 25 degrees Celsius. "
            "Integrating pure lithium metal anodes unlocks theoretical gravimetric energy densities between 450 "
            "and 520 Wh/kg. Automotive original equipment manufacturers including Toyota have targeted pilot lines."
        )
        fp_a = SimHash64.compute(text_a)
        fp_b = SimHash64.compute(text_b)
        dist = SimHash64.hamming_distance(fp_a, fp_b)
        self.assertLessEqual(dist, 3, f"Expected Hamming distance <= 3 for 1-word substitution in 80-word text, got {dist}")

    def test_punctuation_and_formatting_modifications(self):
        """Punctuation variations (semicolons, commas, quotes, hyphens) produce Hamming distance <= 3."""
        t1 = (
            "Operating industrial dry rooms at this tight specification incurs a capital expenditure "
            "premium of $18 million to $25 million per gigawatt-hour; however, high throughput mitigates costs."
        )
        t2 = (
            "Operating industrial dry rooms at this tight specification incurs a capital expenditure "
            "premium of $18 million to $25 million per gigawatt-hour, however, high throughput mitigates costs!"
        )
        fp1 = SimHash64.compute(t1)
        fp2 = SimHash64.compute(t2)
        dist = SimHash64.hamming_distance(fp1, fp2)
        self.assertLessEqual(dist, 3, f"Punctuation alterations should yield Hamming distance <= 3, got {dist}")
        # Note: In normalize_text, both texts collapse to identical tokens, so dist is exactly 0
        self.assertEqual(dist, 0, "Punctuation stripping should normalize identical text to distance 0")

    def test_case_and_whitespace_invariance(self):
        """Case changes and redundant whitespace variations yield identical SimHash (distance 0)."""
        t1 = "Thermal runaway risks in lithium batteries decline sharply when using non-flammable solid electrolytes."
        t2 = "  THERMAL RUNAWAY RISKS IN LITHIUM BATTERIES DECLINE SHARPLY   WHEN USING NON-FLAMMABLE SOLID ELECTROLYTES. \n\t "
        fp1 = SimHash64.compute(t1)
        fp2 = SimHash64.compute(t2)
        self.assertEqual(fp1, fp2)
        self.assertEqual(SimHash64.hamming_distance(fp1, fp2), 0)


class TestSimHashDistinctTextsStress(unittest.TestCase):
    """Adversarial stress tests verifying that distinct texts have Hamming distance > 10."""

    def test_disjoint_domain_texts_large_hamming_distance(self):
        """Texts from completely different domains must have Hamming distance > 10."""
        text_battery = (
            "Sulfide argyrodite solid electrolytes achieve ionic conductivity of 12.0 mS/cm at 25°C, "
            "enabling solid-state battery cells with energy densities up to 500 Wh/kg."
        )
        text_climate = (
            "The Maunder Minimum solar lull occurred between 1645 and 1715, correlating with extreme "
            "winter freezes across Western Europe and severe agricultural disruption during the Little Ice Age."
        )
        text_trade = (
            "Supply chain reshoring initiatives and domestic tariff structures reduced critical component "
            "import volumes from East Asian manufacturing hubs by 18 percent over a three year period."
        )

        fp_bat = SimHash64.compute(text_battery)
        fp_cli = SimHash64.compute(text_climate)
        fp_tra = SimHash64.compute(text_trade)

        dist_bat_cli = SimHash64.hamming_distance(fp_bat, fp_cli)
        dist_bat_tra = SimHash64.hamming_distance(fp_bat, fp_tra)
        dist_cli_tra = SimHash64.hamming_distance(fp_cli, fp_tra)

        self.assertGreater(dist_bat_cli, 10, f"Expected Hamming distance > 10 between Battery & Climate, got {dist_bat_cli}")
        self.assertGreater(dist_bat_tra, 10, f"Expected Hamming distance > 10 between Battery & Trade, got {dist_bat_tra}")
        self.assertGreater(dist_cli_tra, 10, f"Expected Hamming distance > 10 between Climate & Trade, got {dist_cli_tra}")

    def test_pigeonhole_false_positive_rejection(self):
        """Distinct items must not be returned as duplicates by the 4-bucket SimHash index."""
        index = SimHashIndex(threshold=3)
        text1 = "Battery energy density reached 450 Wh/kg using lithium metal anodes and composite sulfur cathodes."
        text2 = "Agricultural wheat yields declined sharply following the 1600 Huaynaputina volcanic eruption."

        fp1 = SimHash64.compute(text1)
        fp2 = SimHash64.compute(text2)

        index.add("doc-1", fp1, metadata={"topic": "battery"})
        matches = index.find_near_duplicates(fp2)
        self.assertEqual(len(matches), 0, "Distinct item must not be matched in SimHashIndex")


class TestTwoStageDeduplicatorTransitiveAttributionStress(unittest.TestCase):
    """Stress tests verifying transitive attribution merging across 3+ duplicate documents."""

    def setUp(self):
        self.dedup = TwoStageDeduplicator(hamming_threshold=3)

    def test_transitive_attribution_merging_five_passages(self):
        """5 duplicates of the same passage across different wire sources merge into 1 item with all secondary URLs."""
        content = "Sulfide solid electrolytes achieved record ionic conductivity of 12.0 mS/cm at 25 degrees Celsius."
        passages = [
            ScoredPassage("p-01", "d-01", "https://news.source-alpha.org/article", "Alpha News", content, 0.70, "ssb", 15),
            ScoredPassage("p-02", "d-02", "https://reuters-mirror.com/report", "Reuters Mirror", content, 0.95, "ssb", 15),
            ScoredPassage("p-03", "d-03", "https://bloomberg-wire.com/feed", "Bloomberg Wire", content, 0.82, "ssb", 15),
            ScoredPassage("p-04", "d-04", "https://techcrunch-digest.io/post", "TechCrunch Digest", content, 0.88, "ssb", 15),
            ScoredPassage("p-05", "d-05", "https://energy-storage.net/brief", "Energy Storage", content, 0.65, "ssb", 15),
        ]

        deduped = self.dedup.deduplicate_passages(passages)
        self.assertEqual(len(deduped), 1, "All 5 duplicates must collapse to 1 representative passage")

        survivor = deduped[0]
        # Primary retains first doc ID and canonical URL
        self.assertEqual(survivor.passage_id, "p-01")
        self.assertEqual(survivor.url, "https://news.source-alpha.org/article")

        # Must retain the maximum relevance score among all 5 (0.95)
        self.assertEqual(survivor.relevance_score, 0.95, "Survivor must pool the maximum relevance score (0.95)")

        # secondary_urls must contain all 4 other distinct sources
        expected_urls = {
            "https://reuters-mirror.com/report",
            "https://bloomberg-wire.com/feed",
            "https://techcrunch-digest.io/post",
            "https://energy-storage.net/brief",
        }
        self.assertEqual(set(survivor.secondary_urls), expected_urls)
        self.assertEqual(len(survivor.secondary_urls), 4)

    def test_transitive_attribution_with_preexisting_secondary_urls(self):
        """Duplicate documents that already have secondary_urls correctly merge all URLs without duplication."""
        content = "Global semiconductor manufacturing subsidies reached $52 billion across major economies."
        p1 = ScoredPassage(
            "p-10", "d-10", "https://main-source.com/chips", "Main Source", content, 0.80, "chips", 10,
            secondary_urls=["https://prior-syndication.org/chips"]
        )
        p2 = ScoredPassage(
            "p-20", "d-20", "https://secondary-wire.com/chips", "Secondary Wire", content, 0.85, "chips", 10,
            secondary_urls=["https://another-feed.com/chips", "https://main-source.com/chips"]  # contains primary url
        )

        deduped = self.dedup.deduplicate_passages([p1, p2])
        self.assertEqual(len(deduped), 1)
        survivor = deduped[0]

        # Primary URL should NOT appear in its own secondary_urls
        self.assertNotIn("https://main-source.com/chips", survivor.secondary_urls)

        # All distinct other URLs must be present
        self.assertIn("https://prior-syndication.org/chips", survivor.secondary_urls)
        self.assertIn("https://secondary-wire.com/chips", survivor.secondary_urls)
        self.assertIn("https://another-feed.com/chips", survivor.secondary_urls)
        self.assertEqual(len(survivor.secondary_urls), 3)

    def test_transitive_claim_attribution_and_entity_merging(self):
        """Merging 3 duplicate claims pools confidence scores, secondary URLs, and unions entities."""
        text = "Pilot roll-to-roll manufacturing lines achieved line speeds of 25 meters per minute."
        c1 = ExtractedClaim("clm-1", text, "d-1", "https://source1.com/art", "Title 1", "snippet", 0.60,
                            ClaimType.QUANTITATIVE, ["Toyota"], [])
        c2 = ExtractedClaim("clm-2", text, "d-2", "https://source2.com/art", "Title 2", "snippet", 0.85,
                            ClaimType.QUANTITATIVE, ["QuantumScape"], ["https://extra-source.com/art"])
        c3 = ExtractedClaim("clm-3", text, "d-3", "https://source3.com/art", "Title 3", "snippet", 0.75,
                            ClaimType.QUANTITATIVE, ["Solid Power", "Toyota"], [])

        deduped = self.dedup.deduplicate_claims([c1, c2, c3])
        self.assertEqual(len(deduped), 1)
        survivor = deduped[0]

        # Highest confidence score
        self.assertEqual(survivor.confidence_score, 0.85)

        # Entity set union
        expected_entities = {"Toyota", "QuantumScape", "Solid Power"}
        self.assertEqual(set(survivor.entities), expected_entities)

        # Transitive secondary URLs
        expected_urls = {"https://source2.com/art", "https://extra-source.com/art", "https://source3.com/art"}
        self.assertEqual(set(survivor.secondary_urls), expected_urls)


class TestClaimExtractorAbbreviationAndNumberStress(unittest.TestCase):
    """Stress tests verifying ClaimExtractor on texts packed with abbreviations, decimals, and currency."""

    def setUp(self):
        self.extractor = ClaimExtractor(min_confidence=0.35)

    def test_abbreviation_and_decimal_dense_paragraph_segmentation(self):
        """Text packed with abbreviations ('U.S.', 'Dr.', 'Q3.') and decimals ('2.5%') splits correctly."""
        raw_text = (
            "U.S. GDP grew by 2.5% in Q3. "
            "Dr. Smith reported that battery density surpassed 500 Wh/kg in 2025. "
            "Total investment in domestic manufacturing reached $10.5 billion."
        )

        sentences = self.extractor.segment_sentences(raw_text)
        self.assertEqual(len(sentences), 3, f"Expected exactly 3 sentences, got {len(sentences)}: {sentences}")

        # Sentence 1 checks
        self.assertIn("U.S. GDP", sentences[0])
        self.assertIn("2.5%", sentences[0])
        self.assertTrue(sentences[0].endswith("Q3."))

        # Sentence 2 checks
        self.assertIn("Dr. Smith", sentences[1])
        self.assertIn("500 Wh/kg", sentences[1])

        # Sentence 3 checks
        self.assertIn("$10.5 billion", sentences[2])

    def test_claim_taxonomy_classification_on_dense_text(self):
        """Each segmented sentence from the dense paragraph is classified into the correct ClaimType."""
        s1 = "U.S. GDP grew by 2.5% in Q3."
        s2 = "Dr. Smith reported that battery density surpassed 500 Wh/kg in 2025."
        s3 = "Total investment in domestic manufacturing reached $10.5 billion."

        type1 = self.extractor.classify_claim_type(s1)
        type2 = self.extractor.classify_claim_type(s2)
        type3 = self.extractor.classify_claim_type(s3)

        self.assertEqual(type1, ClaimType.QUANTITATIVE, "2.5% metric must classify as QUANTITATIVE")
        self.assertEqual(type2, ClaimType.QUANTITATIVE, "500 Wh/kg metric must classify as QUANTITATIVE")
        self.assertEqual(type3, ClaimType.QUANTITATIVE, "$10.5 billion metric must classify as QUANTITATIVE")

    def test_academic_and_corporate_abbreviations(self):
        """Sentence splitter does not fragment on 'e.g.', 'i.e.', 'et al.', 'Inc.', 'Corp.'."""
        text = (
            "Researchers at Solid Power Inc. published findings (e.g., ionic conductivity data) with Prof. Davis et al. "
            "The consortium achieved 12.0 mS/cm at ambient temperature."
        )
        sentences = self.extractor.segment_sentences(text)
        self.assertEqual(len(sentences), 2)
        self.assertIn("Inc.", sentences[0])
        self.assertIn("e.g.", sentences[0])
        self.assertIn("Prof.", sentences[0])
        self.assertIn("et al.", sentences[0])
        self.assertIn("12.0 mS/cm", sentences[1])


class TestClaimExtractorNoiseFilteringStress(unittest.TestCase):
    """Stress tests verifying that interrogatives, imperatives, and calls to action are rejected."""

    def setUp(self):
        self.extractor = ClaimExtractor()

    def test_interrogative_sentence_rejection(self):
        """Interrogative questions are strictly filtered out and never classified as claims."""
        questions = [
            "Why do batteries fail?",
            "Why do commercial solid-state batteries fail under high current density?",
            "How will new tariff structures affect domestic semiconductor fabrication?",
            "Can argyrodite sulfide electrolytes withstand atmospheric moisture?",
            "What caused the sudden climate cooling during the Maunder Minimum?",
        ]
        for q in questions:
            self.assertIsNone(
                self.extractor.classify_claim_type(q),
                f"Question was erroneously classified as a claim: {q}"
            )

    def test_imperative_and_call_to_action_rejection(self):
        """Imperative statements and web marketing noise are rejected."""
        calls_to_action = [
            "Click here to learn more.",
            "Click here to download our full investment whitepaper and register for updates!",
            "Sign up for our newsletter to receive weekly battery technology updates.",
            "Read more about our research methodology and download the data.",
            "Leave a comment below to share your perspective on battery technology.",
            "Subscribe today for exclusive access to industry market reports.",
        ]
        for cta in calls_to_action:
            self.assertIsNone(
                self.extractor.classify_claim_type(cta),
                f"Call-to-action was erroneously classified as a claim: {cta}"
            )

    def test_mixed_paragraph_with_noise_extraction(self):
        """In a mixed paragraph with facts and noise, only factual claims are extracted."""
        passage = ScoredPassage(
            passage_id="p-mix-01",
            doc_id="doc-mix-01",
            url="https://mock-battery-blog.com/guide",
            title="Guide to Solid State Batteries",
            text=(
                "Why do batteries fail? "
                "Solid-state lithium batteries achieve energy densities surpassing 500 Wh/kg in testing. "
                "Total investment in the technology reached $10.5 billion worldwide. "
                "Click here to learn more."
            ),
            relevance_score=0.85,
            subquery="solid state battery",
            word_count=32,
        )

        claims = self.extractor.extract_claims_from_passage(passage)
        self.assertEqual(len(claims), 2, f"Expected exactly 2 claims, got {len(claims)}")

        claim_texts = [c.text for c in claims]
        self.assertTrue(any("500 Wh/kg" in t for t in claim_texts))
        self.assertTrue(any("$10.5 billion" in t for t in claim_texts))
        self.assertFalse(any("Why do batteries" in t for t in claim_texts))
        self.assertFalse(any("Click here" in t for t in claim_texts))


class TestClaimExtractorConfidenceBoundsStress(unittest.TestCase):
    """Stress tests verifying that confidence scores remain strictly in [0.0, 1.0]."""

    def setUp(self):
        self.extractor = ClaimExtractor()

    def test_confidence_scores_strictly_bounded_extreme_inputs(self):
        """Confidence score must remain in [0.0, 1.0] under extreme boosting and extreme penalization."""
        # Scenario 1: Maximum boosting (high base relevance, quantitative, multiple entities, assertion verb, ideal length)
        max_boost_sentence = (
            "QuantumScape and Toyota officially demonstrated that argyrodite electrolytes achieved 12.0 mS/cm "
            "ionic conductivity at 25°C in pilot testing."
        )
        conf_high = self.extractor.calculate_confidence(
            sentence=max_boost_sentence,
            claim_type=ClaimType.QUANTITATIVE,
            base_relevance=10.0,  # adversarial high relevance
            entities=["QuantumScape", "Toyota", "argyrodite"],
        )
        self.assertGreaterEqual(conf_high, 0.0)
        self.assertLessEqual(conf_high, 1.0, f"Confidence exceeded 1.0: {conf_high}")

        # Scenario 2: Heavy penalization (negative base relevance, mild hedges, short sentence, no entities)
        min_penalized_sentence = "It is perhaps likely that some things happened."
        conf_low = self.extractor.calculate_confidence(
            sentence=min_penalized_sentence,
            claim_type=ClaimType.GENERAL_FACT,
            base_relevance=-5.0,  # adversarial negative relevance
            entities=[],
        )
        self.assertGreaterEqual(conf_low, 0.0, f"Confidence fell below 0.0: {conf_low}")
        self.assertLessEqual(conf_low, 1.0)

    def test_confidence_scores_across_diverse_claims(self):
        """Every claim extracted from a diverse set of passages must satisfy 0.0 <= confidence <= 1.0."""
        passages = [
            ScoredPassage(
                passage_id="p-bound-01", doc_id="d1", url="https://u1.com", title="T1",
                text="U.S. GDP grew by 2.5% in Q3. Dr. Smith reported that battery density surpassed 500 Wh/kg.",
                relevance_score=0.9, subquery="q", word_count=20
            ),
            ScoredPassage(
                passage_id="p-bound-02", doc_id="d2", url="https://u2.com", title="T2",
                text="The Maunder Minimum occurred between 1645 and 1715. Severe winter cold resulted in crop failure.",
                relevance_score=0.1, subquery="q", word_count=20
            ),
            ScoredPassage(
                passage_id="p-bound-03", doc_id="d3", url="https://u3.com", title="T3",
                text="Sulfide solid electrolytes demonstrated performance superior to oxide ceramics in conductivity.",
                relevance_score=0.5, subquery="q", word_count=15
            ),
        ]

        extractor = ClaimExtractor(min_confidence=0.0)  # do not drop any claims
        claims = extractor.extract_claims(passages)
        self.assertGreater(len(claims), 0)

        for c in claims:
            self.assertGreaterEqual(
                c.confidence_score, 0.0,
                f"Claim {c.claim_id} confidence < 0.0: {c.confidence_score}"
            )
            self.assertLessEqual(
                c.confidence_score, 1.0,
                f"Claim {c.claim_id} confidence > 1.0: {c.confidence_score}"
            )


class TestSimHashMutableMetadataAndCandidateStress(unittest.TestCase):
    """Stress tests verifying that mutable metadata structures and near-duplicate lookups never raise TypeError."""

    def test_mutable_metadata_types_in_index(self):
        """Heterogeneous mutable objects (dicts, sets, lists, dataclasses) stored in index without TypeError."""
        index = SimHashIndex(threshold=3)
        passage = ScoredPassage("p1", "d1", "https://a.com", "T", "text", 0.8, "q", 10)
        claim = ExtractedClaim("c1", "text", "d1", "https://a.com", "T", "s", 0.9, ClaimType.GENERAL_FACT)
        raw_dict = {"deep": {"nested": [1, 2, 3]}, "tags": {"science", "energy"}}

        index.add("p1", 0x1234, metadata=passage)
        index.add("c1", 0x1234, metadata=claim)
        index.add("d1", 0x1234, metadata=raw_dict)

        matches = index.find_near_duplicates(0x1234)
        self.assertEqual(len(matches), 3)
        retrieved_ids = {m[0] for m in matches}
        self.assertEqual(retrieved_ids, {"p1", "c1", "d1"})

    def test_near_duplicate_passages_stage2_stress(self):
        """Verify that TwoStageDeduplicator handles non-identical near-duplicates through SimHash Stage 2."""
        dedup = TwoStageDeduplicator(hamming_threshold=3)
        # Non-identical passages that bypass Stage 1 exact hash and exercise Stage 2 SimHash
        p1 = ScoredPassage(
            "p-01", "d-01", "https://source1.com/a", "Source 1",
            "Operating dry rooms incurs a capital expenditure premium of $18 million to $25 million per gigawatt-hour.",
            0.80, "q", 18
        )
        p2 = ScoredPassage(
            "p-02", "d-02", "https://source2.com/b", "Source 2",
            "Operating dry rooms incurs capital expenditure premium of $18 million to $25 million per gigawatt-hour.",
            0.85, "q", 17
        )
        results = dedup.deduplicate_passages([p1, p2])
        self.assertEqual(len(results), 1, "Near-duplicates must be merged in Stage 2")
        self.assertEqual(results[0].relevance_score, 0.85, "Should pool maximum relevance score")
        self.assertIn("https://source2.com/b", results[0].secondary_urls)

    def test_abbreviation_sentence_split_boundary_stress(self):
        """Stress sentence segmentation with common trailing word 'no.' vs page citation 'p. 42'."""
        extractor = ClaimExtractor(min_words=1)
        split_res = extractor.segment_sentences("The answer was no. We continued.")
        self.assertEqual(len(split_res), 2)
        self.assertEqual(split_res[0], "The answer was no.")
        self.assertEqual(split_res[1], "We continued.")

        single_res = extractor.segment_sentences("See p. 42 for details.")
        self.assertEqual(len(single_res), 1)
        self.assertEqual(single_res[0], "See p. 42 for details.")


if __name__ == "__main__":
    unittest.main()
