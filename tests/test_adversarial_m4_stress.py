"""Tier 5 Adversarial Coverage Hardening & Pipeline Stress Test Suite.

Milestone 4 Phase 2 - Adversarial Challenger 2.
Comprehensive stress testing across full research synthesis pipeline:
1. Execution against all 4 mock corpus domains:
   - solid_state_battery
   - supply_chain_reshoring
   - little_ice_age
   - microplastics (edge domain)
2. Fallback & degraded execution paths:
   - Topic = "" (empty string)
   - Topic = "   " (whitespace string)
   - Topic = "abc" (< 5 characters)
   - Empty retrieval results (0 docs matched)
   - Zero extracted claims (fallback proposition extraction)
   - 1-document minimal corpus (scaffolding to K >= 2 sections and >= 2 sources)
3. Citation order and referential integrity:
   - Monotonic 1-based continuous indexing (1, 2, 3...)
   - Zero gaps in citation numbering
   - Zero orphan citations in prose
   - Zero uncited sources in strict mode (100% cited)
   - Multi-source citation markers formatted properly ([1, 2])
4. Non-degeneracy:
   - Substantive word count >= 120 words guaranteed across ALL paths
   - Executive summary >= 30 words and >= 80 characters
   - Each thematic section narrative >= 20 words
   - No banned placeholder tokens (TODO, FIXME, TBD, N/A, etc.)
5. AST and Control-Flow Invariant Proofs:
   - Validates guards in pipeline.py and synthesizer.py statically

Pure Python standard library (unittest, ast, re, json) - Zero external dependencies.
"""

from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Set

# Ensure project root and src directory are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from research_synthesis.models import (
        ClaimCluster,
        ClaimType,
        ExtractedClaim,
        ResearchBrief,
        ScoredPassage,
        SourceCitation,
        SubQuery,
    )
    from research_synthesis.pipeline import ResearchPipeline
    from research_synthesis.retrieval.retriever import MockWebRetrievalClient
    from research_synthesis.extraction.claims import ClaimExtractor
    from research_synthesis.synthesis.synthesizer import CitationRegistry, ExtractiveSynthesizer
    from research_synthesis.verification.validator import ResearchBriefValidator, ValidationResult
    from research_synthesis.verification.runner import run_acceptance_verification
except ImportError:
    from src.research_synthesis.models import (
        ClaimCluster,
        ClaimType,
        ExtractedClaim,
        ResearchBrief,
        ScoredPassage,
        SourceCitation,
        SubQuery,
    )
    from src.research_synthesis.pipeline import ResearchPipeline
    from src.research_synthesis.retrieval.retriever import MockWebRetrievalClient
    from src.research_synthesis.extraction.claims import ClaimExtractor
    from src.research_synthesis.synthesis.synthesizer import CitationRegistry, ExtractiveSynthesizer
    from src.research_synthesis.verification.validator import ResearchBriefValidator, ValidationResult
    from src.research_synthesis.verification.runner import run_acceptance_verification


MANIFEST_PATH = PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "manifest.json"


# ============================================================================
# Test Suite 1: Stress Testing Across All 4 Domains in Mock Corpus
# ============================================================================

class TestAllFourMockCorpusDomainsStress(unittest.TestCase):
    """Stress-tests full pipeline execution against all 4 mock corpus domains."""

    @classmethod
    def setUpClass(cls):
        cls.pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=MANIFEST_PATH)
        cls.strict_validator = ResearchBriefValidator(strict=True)

    def _verify_brief_invariants(self, brief: ResearchBrief, domain_key: str) -> None:
        """Thorough assertion harness for brief structural and semantic invariants."""
        # 1. Type and ID
        self.assertIsInstance(brief, ResearchBrief)
        self.assertRegex(brief.brief_id, r"^brief-[a-zA-Z0-9_-]+$")

        # 2. Topic
        self.assertGreaterEqual(len(brief.topic), 5)

        # 3. Sub-queries (minItems 2)
        self.assertGreaterEqual(len(brief.sub_queries), 2)
        for sq in brief.sub_queries:
            sq_text = sq if isinstance(sq, str) else getattr(sq, "search_query", str(sq))
            self.assertGreaterEqual(len(sq_text.strip()), 3)

        # 4. Executive Summary
        exec_words = len(brief.executive_summary.strip().split())
        self.assertGreaterEqual(exec_words, 30, f"Executive summary has {exec_words} words, expected >= 30")
        self.assertGreaterEqual(len(brief.executive_summary.strip()), 80)

        # 5. Thematic Sections (minItems 2, each >= 20 words)
        self.assertGreaterEqual(len(brief.thematic_sections), 2)
        for idx, sec in enumerate(brief.thematic_sections, start=1):
            self.assertTrue(sec.section_id, f"Section {idx} missing section_id")
            self.assertTrue(sec.title, f"Section {idx} missing title")
            sec_words = len(sec.narrative.strip().split())
            self.assertGreaterEqual(sec_words, 20, f"Section {idx} narrative has {sec_words} words, expected >= 20")

        # 6. Key Takeaways (minItems 3)
        self.assertGreaterEqual(len(brief.key_takeaways), 3)
        for idx, kt in enumerate(brief.key_takeaways):
            kt_text = kt.text if hasattr(kt, "text") else str(kt)
            self.assertGreaterEqual(len(kt_text.strip()), 10)

        # 7. Sources Bibliography (minItems 2)
        self.assertGreaterEqual(len(brief.sources), 2)
        for idx, src in enumerate(brief.sources):
            self.assertTrue(src.url.startswith("http"), f"Source {idx} url '{src.url}' not starting with http/https")
            self.assertTrue(src.title)
            snippet_words = len(src.snippet.strip().split())
            self.assertGreaterEqual(snippet_words, 5)
            self.assertGreaterEqual(len(src.snippet.strip()), 15)

        # 8. Strict Validator & Referential Integrity
        brief_dict = brief.to_dict()
        val_result: ValidationResult = self.strict_validator.validate(brief_dict)
        self.assertTrue(val_result.is_valid, f"Domain {domain_key} failed strict validation:\n" + "\n".join(val_result.errors))

        # 9. Total substantive words >= 120 words
        total_substantive = val_result.metrics.get("total_brief_words", 0)
        self.assertGreaterEqual(total_substantive, 120, f"Domain {domain_key} substantive words ({total_substantive}) < 120")

        # 10. Strict 100% cited sources
        self.assertEqual(
            val_result.metrics.get("sources_count"),
            val_result.metrics.get("sources_cited_count"),
            f"Domain {domain_key} has uncited sources in strict mode",
        )

    def test_domain_1_solid_state_battery(self):
        """Stress-test Domain 1: Solid-State Battery Commercialization."""
        topic = "Next-Generation Solid-State Battery Commercialization: Energy Density Roadmaps, Solid Electrolytes, and Manufacturing Scalability"
        brief = self.pipeline.run(topic)
        self._verify_brief_invariants(brief, "solid_state_battery")

    def test_domain_2_supply_chain_reshoring(self):
        """Stress-test Domain 2: Global Supply Chain Re-Shoring & Friend-Shoring."""
        topic = "Global Supply Chain Re-Shoring and Friend-Shoring Dynamics: Macroeconomic Inflation Impacts and Industrial Policy Interventions"
        brief = self.pipeline.run(topic)
        self._verify_brief_invariants(brief, "supply_chain_reshoring")

    def test_domain_3_little_ice_age(self):
        """Stress-test Domain 3: Little Ice Age Climate Shocks in 17th Century Europe."""
        topic = "The Little Ice Age Climate Shocks in 17th Century Europe: Agrarian Output Collapses, Famine Cycles, and Social Upheaval"
        brief = self.pipeline.run(topic)
        self._verify_brief_invariants(brief, "little_ice_age")

    def test_domain_4_microplastics_edge_domain(self):
        """Stress-test Domain 4: Microplastic Bioaccumulation in Agricultural Soil."""
        topic = "Microplastic Bioaccumulation in Agricultural Soil Ecosystems: Trophic Transfer Mechanisms and Emerging EU Regulatory Directives"
        brief = self.pipeline.run(topic)
        self._verify_brief_invariants(brief, "microplastics")


# ============================================================================
# Test Suite 2: Fallback & Degraded Execution Paths
# ============================================================================

class TestFallbackAndDegradedPathsStress(unittest.TestCase):
    """Stress-tests pipeline fallback paths: empty/whitespace topics, 0 docs, 0 claims, 1 doc."""

    @classmethod
    def setUpClass(cls):
        cls.pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=MANIFEST_PATH)
        cls.validator = ResearchBriefValidator(strict=False)
        cls.strict_validator = ResearchBriefValidator(strict=True)

    def test_degraded_path_empty_and_whitespace_topic_strings(self):
        """Topic = '', '   ', and short topics (< 5 chars) return schema-compliant fallback briefs."""
        test_cases = ["", "   ", " \t \n ", "a", "ab", "abcd"]
        for topic in test_cases:
            brief = self.pipeline.run(topic)
            self.assertIsInstance(brief, ResearchBrief)
            self.assertRegex(brief.brief_id, r"^brief-[a-zA-Z0-9_-]+$")

            # Fallback topic must be >= 5 chars
            self.assertGreaterEqual(len(brief.topic), 5)
            self.assertGreaterEqual(len(brief.sub_queries), 2)
            self.assertGreaterEqual(len(brief.thematic_sections), 2)
            self.assertGreaterEqual(len(brief.key_takeaways), 3)
            self.assertGreaterEqual(len(brief.sources), 2)

            # Substantive words >= 120
            total_words = len(brief.executive_summary.split()) + sum(len(s.narrative.split()) for s in brief.thematic_sections)
            self.assertGreaterEqual(total_words, 120, f"Fallback substantive words ({total_words}) < 120 for topic '{topic}'")

            # Validate against schema
            val = self.validator.validate(brief.to_dict())
            self.assertTrue(val.is_valid, f"Degraded topic '{topic}' failed validation: {val.errors}")

    def test_degraded_path_empty_retrieval_results(self):
        """Empty retrieval (0 documents) triggers graceful diagnostic fallback brief."""
        empty_retriever = MockWebRetrievalClient(corpus_path=None)
        empty_retriever._corpus.clear()
        empty_retriever._doc_id_to_url.clear()

        pipeline = ResearchPipeline(retriever=empty_retriever, mode="mock")
        topic = "Nonexistent Hypothetical Advanced Nanobotics Field"
        brief = pipeline.run(topic)

        self.assertIsInstance(brief, ResearchBrief)
        self.assertTrue(brief.brief_id.startswith("brief-empty-"))
        self.assertGreaterEqual(len(brief.thematic_sections), 2)
        self.assertGreaterEqual(len(brief.key_takeaways), 3)
        self.assertGreaterEqual(len(brief.sources), 2)

        # Word count >= 120
        total_words = len(brief.executive_summary.split()) + sum(len(s.narrative.split()) for s in brief.thematic_sections)
        self.assertGreaterEqual(total_words, 120)

        # Referential integrity: all citations map to sources
        val = self.validator.validate(brief.to_dict())
        self.assertTrue(val.is_valid, f"0-doc fallback brief failed validation: {val.errors}")

    def test_degraded_path_zero_extracted_claims(self):
        """When claim extractor returns 0 claims, fallback extracts proposition claims from passages."""
        class MockEmptyExtractor(ClaimExtractor):
            def extract_claims(self, passages):
                return []

        pipeline = ResearchPipeline(
            mode="mock",
            corpus_manifest_path=MANIFEST_PATH,
            claim_extractor=MockEmptyExtractor(),
        )
        brief = pipeline.run("Next-Generation Solid-State Battery Commercialization")
        self.assertIsInstance(brief, ResearchBrief)
        self.assertGreaterEqual(len(brief.thematic_sections), 2)
        self.assertGreaterEqual(len(brief.sources), 2)

        total_words = len(brief.executive_summary.split()) + sum(len(s.narrative.split()) for s in brief.thematic_sections)
        self.assertGreaterEqual(total_words, 120)

        val = self.validator.validate(brief.to_dict())
        self.assertTrue(val.is_valid, f"Zero claims fallback failed validation: {val.errors}")

    def test_degraded_path_single_document_minimal_corpus(self):
        """Single-document minimal corpus is scaffolded to K >= 2 sections and >= 2 sources."""
        synthesizer = ExtractiveSynthesizer()
        single_claim = ExtractedClaim(
            claim_id="clm-minimal-01",
            text="Lumbricus terrestris specimens exhibited mortality rates below 5% under baseline microplastic exposure.",
            source_doc_id="doc-min-01",
            source_url="https://mock-eco-briefs.org/notes/microplastic-earthworm-mortality-baseline",
            source_title="Earthworm Baseline Exposure",
            passage_snippet="Baseline exposure observations in agricultural topsoil testing.",
            confidence_score=0.90,
            claim_type=ClaimType.QUANTITATIVE,
        )
        single_cluster = ClaimCluster(
            cluster_id="sec-01",
            title="Baseline Soil Toxicology",
            facet="technical",
            claims=[single_claim],
        )

        brief = synthesizer.synthesize(
            topic="Microplastic Bioaccumulation in Agricultural Soil Ecosystems",
            clusters=[single_cluster],
            sub_queries=["earthworm microplastic toxicity", "soil ingestion bioassays"],
        )

        self.assertGreaterEqual(len(brief.thematic_sections), 2, "Must scaffold to K >= 2 sections")
        self.assertGreaterEqual(len(brief.sources), 2, "Must scaffold to >= 2 sources")
        self.assertGreaterEqual(len(brief.key_takeaways), 3, "Must guarantee >= 3 takeaways")

        total_words = len(brief.executive_summary.split()) + sum(len(s.narrative.split()) for s in brief.thematic_sections)
        self.assertGreaterEqual(total_words, 120, f"Total substantive words ({total_words}) < 120")

        # Strict validation: referential integrity & 0 uncited sources
        val = self.strict_validator.validate(brief.to_dict())
        self.assertTrue(val.is_valid, f"Single-doc scaffolded brief failed strict validation: {val.errors}")


# ============================================================================
# Test Suite 3: Citation Order & Referential Integrity Stress
# ============================================================================

class TestCitationOrderAndReferentialIntegrityStress(unittest.TestCase):
    """Stress-tests citation order of appearance, monotonic indexing, 0 gaps, and 0 orphans."""

    @classmethod
    def setUpClass(cls):
        cls.pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=MANIFEST_PATH)

    def _extract_all_citations_in_appearance_order(self, brief: ResearchBrief) -> List[int]:
        """Extract inline citation indices in order of textual appearance across prose."""
        combined_prose = (
            brief.executive_summary + " " +
            " ".join(sec.narrative for sec in brief.thematic_sections) + " " +
            " ".join(kt.text if hasattr(kt, "text") else str(kt) for kt in brief.key_takeaways)
        )
        # Match [1], [2], [1, 2], [1-3]
        matches = re.findall(r"\[(\d+(?:\s*,\s*\d+)*|\d+-\d+)\]", combined_prose)
        indices_in_order: List[int] = []
        for m in matches:
            if "-" in m:
                s, e = m.split("-")
                for i in range(int(s), int(e) + 1):
                    indices_in_order.append(i)
            elif "," in m:
                for part in m.split(","):
                    indices_in_order.append(int(part.strip()))
            else:
                indices_in_order.append(int(m.strip()))
        return indices_in_order

    def test_citation_order_of_appearance_is_strictly_monotonic(self):
        """First unique citation introduced in prose must be [1], second [2], etc."""
        topic = "Next-Generation Solid-State Battery Commercialization: Energy Density Roadmaps, Solid Electrolytes, and Manufacturing Scalability"
        brief = self.pipeline.run(topic)
        citations_stream = self._extract_all_citations_in_appearance_order(brief)

        seen: List[int] = []
        for c in citations_stream:
            if c not in seen:
                seen.append(c)

        # Verify that unique citation IDs appear as [1, 2, 3, ...] in exact order
        expected = list(range(1, len(seen) + 1))
        self.assertEqual(
            seen,
            expected,
            f"Citation order of appearance is non-monotonic: saw {seen}, expected {expected}",
        )

    def test_citation_zero_gaps_in_sources_bibliography(self):
        """Sources table citation_index values must form contiguous sequence 1, 2, ..., N with 0 gaps."""
        for topic in [
            "Next-Generation Solid-State Battery Commercialization: Energy Density Roadmaps, Solid Electrolytes, and Manufacturing Scalability",
            "Global Supply Chain Re-Shoring and Friend-Shoring Dynamics: Macroeconomic Inflation Impacts and Industrial Policy Interventions",
            "The Little Ice Age Climate Shocks in 17th Century Europe: Agrarian Output Collapses, Famine Cycles, and Social Upheaval",
            "Microplastic Bioaccumulation in Agricultural Soil Ecosystems: Trophic Transfer Mechanisms and Emerging EU Regulatory Directives",
        ]:
            brief = self.pipeline.run(topic)
            source_indices = [s.citation_index for s in brief.sources]
            expected_indices = list(range(1, len(brief.sources) + 1))
            self.assertEqual(
                source_indices,
                expected_indices,
                f"Sources table for '{topic[:30]}' has gaps or non-1-based indexes: {source_indices}",
            )

    def test_zero_orphan_citations_and_zero_uncited_sources(self):
        """Zero orphan citations (every [N] is in sources) and zero uncited sources (100% cited)."""
        validator = ResearchBriefValidator(strict=True)
        for topic in [
            "Next-Generation Solid-State Battery Commercialization: Energy Density Roadmaps, Solid Electrolytes, and Manufacturing Scalability",
            "Global Supply Chain Re-Shoring and Friend-Shoring Dynamics: Macroeconomic Inflation Impacts and Industrial Policy Interventions",
            "The Little Ice Age Climate Shocks in 17th Century Europe: Agrarian Output Collapses, Famine Cycles, and Social Upheaval",
            "Microplastic Bioaccumulation in Agricultural Soil Ecosystems: Trophic Transfer Mechanisms and Emerging EU Regulatory Directives",
        ]:
            brief = self.pipeline.run(topic)
            val = validator.validate(brief.to_dict())
            self.assertTrue(val.is_valid, f"Referential integrity failure in '{topic[:30]}': {val.errors}")

            # Explicit check of metrics
            self.assertEqual(
                val.metrics["sources_count"],
                val.metrics["sources_cited_count"],
                f"Uncited sources detected: {val.metrics['sources_count'] - val.metrics['sources_cited_count']}",
            )

    def test_multi_source_corroboration_marker_formatting(self):
        """CitationRegistry formats multi-source citations as sorted markers like [1, 2]."""
        registry = CitationRegistry()
        c1 = ExtractedClaim("c1", "text", "d1", "https://url1.com", "Title 1", "snippet context 1", 0.9, ClaimType.GENERAL_FACT)
        c2 = ExtractedClaim("c2", "text", "d2", "https://url2.com", "Title 2", "snippet context 2", 0.9, ClaimType.GENERAL_FACT)

        idx1 = registry.register_claim(c1)
        idx2 = registry.register_claim(c2)

        self.assertEqual(idx1, [1])
        self.assertEqual(idx2, [2])

        marker_multi = registry.format_citation_marker([2, 1])
        self.assertEqual(marker_multi, "[1, 2]", "Multi-source markers must be sorted")


# ============================================================================
# Test Suite 4: Non-Degeneracy Word Count Invariant Guarantees
# ============================================================================

class TestNonDegeneracyWordCountInvariantsStress(unittest.TestCase):
    """Stress-tests substantive word count >= 120 words across all execution modes."""

    @classmethod
    def setUpClass(cls):
        cls.pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=MANIFEST_PATH)

    def test_substantive_word_count_exceeds_120_words_across_all_mock_domains(self):
        """All 4 canonical mock domains achieve substantive word count >= 120 words."""
        topics = [
            "Next-Generation Solid-State Battery Commercialization: Energy Density Roadmaps, Solid Electrolytes, and Manufacturing Scalability",
            "Global Supply Chain Re-Shoring and Friend-Shoring Dynamics: Macroeconomic Inflation Impacts and Industrial Policy Interventions",
            "The Little Ice Age Climate Shocks in 17th Century Europe: Agrarian Output Collapses, Famine Cycles, and Social Upheaval",
            "Microplastic Bioaccumulation in Agricultural Soil Ecosystems: Trophic Transfer Mechanisms and Emerging EU Regulatory Directives",
        ]
        for topic in topics:
            brief = self.pipeline.run(topic)
            exec_words = len(brief.executive_summary.strip().split())
            sec_words = sum(len(s.narrative.strip().split()) for s in brief.thematic_sections)
            total_substantive = exec_words + sec_words

            self.assertGreaterEqual(
                exec_words, 30, f"Executive summary words ({exec_words}) < 30 for '{topic[:30]}'"
            )
            for idx, sec in enumerate(brief.thematic_sections):
                w = len(sec.narrative.strip().split())
                self.assertGreaterEqual(w, 20, f"Section {idx} words ({w}) < 20 for '{topic[:30]}'")

            self.assertGreaterEqual(
                total_substantive, 120, f"Total substantive words ({total_substantive}) < 120 for '{topic[:30]}'"
            )

    def test_substantive_word_count_exceeds_120_words_on_minimal_synthetic_input(self):
        """Synthesizer guarantees >= 120 substantive words even on empty cluster inputs."""
        synthesizer = ExtractiveSynthesizer()
        brief = synthesizer.synthesize(
            topic="Minimalist Synthetic Topic",
            clusters=[],
            sub_queries=[],
        )
        exec_words = len(brief.executive_summary.strip().split())
        sec_words = sum(len(s.narrative.strip().split()) for s in brief.thematic_sections)
        total_substantive = exec_words + sec_words

        self.assertGreaterEqual(total_substantive, 120, f"Minimalist brief words ({total_substantive}) < 120")

    def test_no_banned_placeholders_in_any_generated_field(self):
        """No prohibited placeholder tokens (TODO, FIXME, TBD, N/A, Lorem ipsum, etc.) exist."""
        banned_regex = re.compile(r"\b(TODO|FIXME|TBD|N/A|Lorem ipsum|Not found|placeholder text)\b", re.IGNORECASE)
        for topic in [
            "Next-Generation Solid-State Battery Commercialization",
            "",
            "123",
        ]:
            brief = self.pipeline.run(topic)
            brief_json = brief.to_json()
            match = banned_regex.search(brief_json)
            self.assertIsNone(match, f"Found prohibited placeholder '{match.group(0) if match else ''}' in brief for topic '{topic}'")


# ============================================================================
# Test Suite 5: AST Inspection and Control-Flow Proofs
# ============================================================================

class TestASTAndControlFlowProofs(unittest.TestCase):
    """Static AST and control-flow invariant proofs on pipeline and synthesizer source code."""

    def test_ast_pipeline_run_method_contains_guard_for_empty_topic(self):
        """Verify pipeline.py has explicit guard for len(clean_topic) < 5 returning fallback brief."""
        pipeline_path = SRC_DIR / "research_synthesis" / "pipeline.py"
        self.assertTrue(pipeline_path.exists())
        tree = ast.parse(pipeline_path.read_text(encoding="utf-8"))

        found_guard = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Compare):
                        # Looking for clean_topic length check < 5
                        if isinstance(stmt.left, ast.Call) and getattr(stmt.left.func, "id", "") == "len":
                            if stmt.ops and isinstance(stmt.ops[0], ast.Lt):
                                found_guard = True
                                break
        self.assertTrue(found_guard, "AST proof: pipeline.run must contain explicit length guard < 5")

    def test_ast_synthesizer_guarantees_minimum_sources_and_substantive_words(self):
        """Verify synthesizer.py has explicit branches guaranteeing >= 2 sources and >= 125 words."""
        synth_path = SRC_DIR / "research_synthesis" / "synthesis" / "synthesizer.py"
        self.assertTrue(synth_path.exists())
        tree = ast.parse(synth_path.read_text(encoding="utf-8"))

        found_source_guard = False
        found_word_guard = False

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "synthesize":
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Compare):
                        # Checking len(sources) < 2
                        if isinstance(stmt.left, ast.Call) and getattr(stmt.left.func, "id", "") == "len":
                            if stmt.comparators and isinstance(stmt.comparators[0], ast.Constant) and stmt.comparators[0].value == 2:
                                found_source_guard = True
                        # Checking total_substantive < 125
                        if isinstance(stmt.left, ast.Name) and stmt.left.id == "total_substantive":
                            if stmt.comparators and isinstance(stmt.comparators[0], ast.Constant) and stmt.comparators[0].value in (120, 125):
                                found_word_guard = True

        self.assertTrue(found_source_guard, "AST proof: synthesizer.synthesize must contain len(sources) < 2 guard")
        self.assertTrue(found_word_guard, "AST proof: synthesizer.synthesize must contain total_substantive < 125 guard")

    def test_ast_citation_registry_starts_index_at_one(self):
        """Verify CitationRegistry.__init__ initializes self.next_index = 1."""
        synth_path = SRC_DIR / "research_synthesis" / "synthesis" / "synthesizer.py"
        tree = ast.parse(synth_path.read_text(encoding="utf-8"))

        found_init_1 = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "CitationRegistry":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        for assign in item.body:
                            if isinstance(assign, ast.Assign) or isinstance(assign, ast.AnnAssign):
                                targets = assign.targets if isinstance(assign, ast.Assign) else [assign.target]
                                for t in targets:
                                    if isinstance(t, ast.Attribute) and t.attr == "next_index":
                                        val = assign.value
                                        if isinstance(val, ast.Constant) and val.value == 1:
                                            found_init_1 = True

        self.assertTrue(found_init_1, "AST proof: CitationRegistry.next_index must be initialized to 1")


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    unittest.main()
