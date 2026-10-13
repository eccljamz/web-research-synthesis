"""Tier 4 End-to-End Acceptance Verification Test Suite.

Milestone 4 - Full Acceptance Verification per TEST_INFRA.md and Acceptance Criteria:
1. Test Query 1 (solid_state_battery): Executes ResearchPipeline.run() against offline mock corpus,
   validates with ResearchBriefValidator(strict=True), asserts all formal schema properties and
   substantive word count >= 120.
2. Test Query 2 (supply_chain_reshoring): Executes pipeline, validates with strict validator.
3. Test Query 3 (little_ice_age): Executes pipeline, validates with strict validator.
4. Test Query 4 (microplastics edge domain): Executes pipeline on edge domain, validates with strict validator.
5. Programmatic invocation of run_acceptance_verification(strict=True) from runner.py across standard
   and full query sets.

Pure Python standard library (unittest) - Zero external dependencies.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

# Ensure repository root and src directory are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from research_synthesis.models import ResearchBrief
    from research_synthesis.pipeline import ResearchPipeline
    from research_synthesis.verification.validator import ResearchBriefValidator, ValidationResult
    from research_synthesis.verification.runner import (
        ACCEPTANCE_QUERIES,
        EDGE_QUERIES,
        run_acceptance_verification,
    )
except ImportError:
    from src.research_synthesis.models import ResearchBrief
    from src.research_synthesis.pipeline import ResearchPipeline
    from src.research_synthesis.verification.validator import ResearchBriefValidator, ValidationResult
    from src.research_synthesis.verification.runner import (
        ACCEPTANCE_QUERIES,
        EDGE_QUERIES,
        run_acceptance_verification,
    )


MANIFEST_PATH = PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "manifest.json"


# ============================================================================
# Test Suite: Tier 4 End-to-End Acceptance Verification
# ============================================================================

class TestTier4E2EAcceptance(unittest.TestCase):
    """End-to-End acceptance verification of ResearchPipeline against canonical acceptance queries."""

    @classmethod
    def setUpClass(cls):
        cls.pipeline = ResearchPipeline(mode="mock", corpus_manifest_path=MANIFEST_PATH)
        cls.strict_validator = ResearchBriefValidator(strict=True)

    def _assert_valid_brief_contract(self, brief: ResearchBrief, expected_topic_substring: str) -> None:
        """Helper asserting complete schema, substantive content, and strict invariant compliance."""
        self.assertIsInstance(brief, ResearchBrief)

        # 1. Brief ID regex: ^brief-[a-zA-Z0-9_-]+$
        self.assertRegex(
            brief.brief_id,
            r"^brief-[a-zA-Z0-9_-]+$",
            f"brief_id '{brief.brief_id}' does not match required format",
        )

        # 2. Topic
        self.assertIn(expected_topic_substring.lower(), brief.topic.lower())
        self.assertGreaterEqual(len(brief.topic), 5)

        # 3. Sub-queries (minItems >= 2)
        self.assertGreaterEqual(
            len(brief.sub_queries),
            2,
            f"Expected >= 2 sub-queries, got {len(brief.sub_queries)}",
        )

        # 4. Executive Summary (>= 30 words, >= 80 characters)
        exec_words = len(brief.executive_summary.strip().split())
        self.assertGreaterEqual(
            exec_words,
            30,
            f"Executive summary word count ({exec_words}) is below 30 words",
        )
        self.assertGreaterEqual(
            len(brief.executive_summary.strip()),
            80,
            "Executive summary character length is below 80 characters",
        )

        # 5. Thematic Sections (minItems >= 2, each >= 20 words)
        self.assertGreaterEqual(
            len(brief.thematic_sections),
            2,
            f"Expected >= 2 thematic sections, got {len(brief.thematic_sections)}",
        )
        for idx, sec in enumerate(brief.thematic_sections, start=1):
            self.assertTrue(sec.section_id, f"Section {idx} missing section_id")
            self.assertTrue(sec.title, f"Section {idx} missing title")
            sec_words = len(sec.narrative.strip().split())
            self.assertGreaterEqual(
                sec_words,
                20,
                f"Section {idx} narrative word count ({sec_words}) is below 20 words",
            )
            self.assertGreaterEqual(
                len(sec.citation_indices),
                1,
                f"Section {idx} has no citation indices",
            )

        # 6. Key Takeaways (minItems >= 3, each non-empty)
        self.assertGreaterEqual(
            len(brief.key_takeaways),
            3,
            f"Expected >= 3 key takeaways, got {len(brief.key_takeaways)}",
        )
        for idx, kt in enumerate(brief.key_takeaways):
            kt_text = kt.text if hasattr(kt, "text") else str(kt)
            self.assertGreater(len(kt_text.strip()), 10, f"Takeaway {idx} is degenerate")

        # 7. Sources Bibliography (minItems >= 2)
        self.assertGreaterEqual(
            len(brief.sources),
            2,
            f"Expected >= 2 sources, got {len(brief.sources)}",
        )
        for idx, src in enumerate(brief.sources):
            self.assertTrue(src.url.startswith("http"), f"Source {idx} url '{src.url}' missing http/https")
            self.assertTrue(src.title, f"Source {idx} missing title")
            snippet_words = len(src.snippet.strip().split())
            self.assertGreaterEqual(
                snippet_words,
                5,
                f"Source {idx} snippet ({snippet_words} words) is below minimum 5 words",
            )

        # 8. Strict Validator Invariant Assertions
        brief_dict = brief.to_dict()
        val_result: ValidationResult = self.strict_validator.validate(brief_dict)
        self.assertTrue(
            val_result.is_valid,
            f"Strict validation failed with errors:\n" + "\n".join(val_result.errors),
        )

        # 9. Substantive Word Count Constraint (>= 120 words)
        total_substantive = val_result.metrics.get("total_brief_words", 0)
        self.assertGreaterEqual(
            total_substantive,
            120,
            f"Substantive word count ({total_substantive}) is below strict threshold of 120 words",
        )

        # 10. Strict Referential Integrity: 100% of listed sources are cited
        sources_count = val_result.metrics.get("sources_count", 0)
        sources_cited = val_result.metrics.get("sources_cited_count", 0)
        self.assertEqual(
            sources_count,
            sources_cited,
            f"Strict invariant violation: {sources_count - sources_cited} uncited sources in bibliography",
        )

    def test_query_1_solid_state_battery(self):
        """Acceptance Test 1: Solid-State Battery Commercialization (Science & Emerging Technology)."""
        topic = (
            "Next-Generation Solid-State Battery Commercialization: Energy Density Roadmaps, "
            "Solid Electrolytes, and Manufacturing Scalability"
        )
        brief = self.pipeline.run(topic)
        self._assert_valid_brief_contract(brief, expected_topic_substring="Solid-State Battery")

        # Domain-specific verification
        brief_text = (brief.executive_summary + " " + " ".join(s.narrative for s in brief.thematic_sections)).lower()
        self.assertTrue(
            any(k in brief_text for k in ["electrolyte", "ionic", "density", "sulfide", "conductiv"]),
            "Solid-state battery brief lacks core domain terminology",
        )

    def test_query_2_supply_chain_reshoring(self):
        """Acceptance Test 2: Supply Chain Re-Shoring & Friend-Shoring (Macroeconomics & Global Markets)."""
        topic = (
            "Global Supply Chain Re-Shoring and Friend-Shoring Dynamics: Macroeconomic Inflation Impacts "
            "and Industrial Policy Interventions"
        )
        brief = self.pipeline.run(topic)
        self._assert_valid_brief_contract(brief, expected_topic_substring="Supply Chain")

        # Domain-specific verification
        brief_text = (brief.executive_summary + " " + " ".join(s.narrative for s in brief.thematic_sections)).lower()
        self.assertTrue(
            any(k in brief_text for k in ["supply chain", "reshoring", "near-shoring", "chips", "inflation", "trade"]),
            "Supply chain reshoring brief lacks core macroeconomic terminology",
        )

    def test_query_3_little_ice_age(self):
        """Acceptance Test 3: Little Ice Age Climate Shocks (History & Paleoclimatology)."""
        topic = (
            "The Little Ice Age Climate Shocks in 17th Century Europe: Agrarian Output Collapses, "
            "Famine Cycles, and Social Upheaval"
        )
        brief = self.pipeline.run(topic)
        self._assert_valid_brief_contract(brief, expected_topic_substring="Little Ice Age")

        # Domain-specific verification
        brief_text = (brief.executive_summary + " " + " ".join(s.narrative for s in brief.thematic_sections)).lower()
        self.assertTrue(
            any(k in brief_text for k in ["climate", "famine", "agrarian", "seventeenth", "harvest", "scotland", "mortality"]),
            "Little Ice Age brief lacks core climatology/history terminology",
        )

    def test_query_4_microplastics_edge_domain(self):
        """Acceptance Test 4: Microplastic Bioaccumulation (Edge Domain: Environmental Toxicology & Law)."""
        topic = (
            "Microplastic Bioaccumulation in Agricultural Soil Ecosystems: Trophic Transfer Mechanisms "
            "and Emerging EU Regulatory Directives"
        )
        brief = self.pipeline.run(topic)
        self._assert_valid_brief_contract(brief, expected_topic_substring="Microplastic")

        # Domain-specific verification
        brief_text = (brief.executive_summary + " " + " ".join(s.narrative for s in brief.thematic_sections)).lower()
        self.assertTrue(
            any(k in brief_text for k in ["microplastic", "soil", "trophic", "earthworm", "reach", "regulation"]),
            "Microplastics edge brief lacks core environmental/toxicology terminology",
        )


# ============================================================================
# Test Suite: Programmatic Acceptance Verification Runner (runner.py)
# ============================================================================

class TestProgrammaticAcceptanceRunner(unittest.TestCase):
    """Verifies runner.py run_acceptance_verification() programmatic invocation and output artifacts."""

    def test_run_acceptance_verification_standard_queries_strict(self):
        """run_acceptance_verification(query_set='acceptance', strict=True) returns True and passes all 3 queries."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            success, report = run_acceptance_verification(
                mode="mock",
                query_set="acceptance",
                output_dir=tmp_dir,
                strict=True,
                corpus_manifest=MANIFEST_PATH,
            )

            self.assertTrue(success, f"Acceptance verification failed: {report}")
            self.assertEqual(report.get("overall_status"), "PASSED")
            self.assertEqual(report.get("total_queries"), 3)
            self.assertEqual(report.get("passed_queries"), 3)
            self.assertEqual(report.get("failed_queries"), 0)

            # Check output files were written
            report_dir = Path(tmp_dir)
            self.assertTrue((report_dir / "verification_report.json").exists())
            self.assertTrue((report_dir / "solid_state_battery.json").exists())
            self.assertTrue((report_dir / "solid_state_battery.md").exists())
            self.assertTrue((report_dir / "supply_chain_reshoring.json").exists())
            self.assertTrue((report_dir / "supply_chain_reshoring.md").exists())
            self.assertTrue((report_dir / "little_ice_age.json").exists())
            self.assertTrue((report_dir / "little_ice_age.md").exists())

    def test_run_acceptance_verification_all_queries_strict(self):
        """run_acceptance_verification(query_set='all', strict=True) passes 4 queries including edge domain."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            success, report = run_acceptance_verification(
                mode="mock",
                query_set="all",
                output_dir=tmp_dir,
                strict=True,
                corpus_manifest=MANIFEST_PATH,
            )

            self.assertTrue(success, f"All-queries verification failed: {report}")
            self.assertEqual(report.get("overall_status"), "PASSED")
            self.assertEqual(report.get("total_queries"), 4)
            self.assertEqual(report.get("passed_queries"), 4)
            self.assertEqual(report.get("failed_queries"), 0)

            # Edge query artifact should also exist
            report_dir = Path(tmp_dir)
            self.assertTrue((report_dir / "microplastics.json").exists())
            self.assertTrue((report_dir / "microplastics.md").exists())


if __name__ == "__main__":
    unittest.main()
