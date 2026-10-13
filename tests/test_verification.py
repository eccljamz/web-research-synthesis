"""
Unit and integration tests for ResearchBrief schema and semantic verification engine.
"""

import json
import sys
import unittest
from pathlib import Path

# Ensure src is on sys.path
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from research_synthesis.verification.validator import (
    ResearchBriefValidator,
    SchemaValidator,
    SemanticValidator,
    ValidationResult,
    validate_brief,
)


class TestMockCorpusIntegrity(unittest.TestCase):
    """Verifies that the mock corpus files and manifest are complete, valid, and present on disk."""

    def setUp(self):
        self.project_root = Path(__file__).resolve().parents[1]
        self.manifest_path = self.project_root / "tests" / "fixtures" / "mock_corpus" / "manifest.json"

    def test_manifest_exists_and_parses(self):
        self.assertTrue(self.manifest_path.exists(), f"Manifest not found at {self.manifest_path}")
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertIn("queries", manifest)
        self.assertIn("documents", manifest)
        self.assertGreaterEqual(len(manifest["queries"]), 3, "Manifest must declare at least 3 queries")
        self.assertGreaterEqual(len(manifest["documents"]), 10, "Manifest must declare documents")

    def test_all_manifest_documents_exist_on_disk(self):
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        mock_dir = self.manifest_path.parent
        for doc_id, doc_meta in manifest["documents"].items():
            rel_path = doc_meta.get("file_path")
            self.assertIsNotNone(rel_path, f"Document '{doc_id}' missing 'file_path'")
            full_path = mock_dir / rel_path
            self.assertTrue(full_path.exists(), f"Fixture file '{full_path}' does not exist on disk")
            content = full_path.read_text(encoding="utf-8", errors="replace")
            self.assertGreater(len(content), 100, f"Fixture file '{rel_path}' is too small/empty")


class TestSchemaAndSemanticValidation(unittest.TestCase):
    """Tests schema and semantic invariant validation logic against valid and invalid payloads."""

    def setUp(self):
        self.valid_brief = {
            "brief_id": "brief-7f8e9a10-2026",
            "topic": "Next-Generation Solid-State Battery Commercialization: Energy Density Roadmaps, Solid Electrolytes, and Manufacturing Scalability",
            "generated_at": "2026-10-13T17:00:00Z",
            "sub_queries": [
                "solid electrolyte materials ionic conductivity sulfide oxide",
                "energy density Wh/kg roadmap Battery500 commercial targets",
                "manufacturing scalability roll-to-roll pilot line dry room",
            ],
            "executive_summary": (
                "Next-generation solid-state battery technology represents a foundational paradigm shift "
                "for electric mobility, transitioning away from volatile liquid organic electrolytes toward "
                "inorganic ceramic and sulfide solid separators [1]. Recent advances in sulfide argyrodites "
                "have unlocked room-temperature ionic conductivities surpassing 12 mS/cm, enabling high-rate "
                "operation while eliminating catastrophic thermal runaway hazards [1, 2]. However, significant "
                "commercialization hurdles persist in industrial-scale roll-to-roll manufacturing and dry-room humidity controls [3]."
            ),
            "thematic_sections": [
                {
                    "section_id": "SEC-01",
                    "title": "Solid Electrolyte Materials and Ionic Transport",
                    "narrative": (
                        "Sulfide-based solid electrolytes, particularly lithium argyrodites, exhibit conductivities "
                        "exceeding 12.0 mS/cm at ambient temperatures, fulfilling automotive power delivery criteria [1]. "
                        "In contrast, garnet oxide electrolytes such as LLZO exhibit elevated interfacial resistance "
                        "against lithium metal anodes, necessitating atomic layer deposition interlayers to suppress dendrite shorting [1]."
                    ),
                    "citation_indices": [1],
                    "claim_ids": ["CLM-01"],
                    "claims": [
                        {
                            "claim_id": "CLM-01",
                            "claim_text": "Sulfide argyrodite solid electrolytes achieve room-temperature ionic conductivities above 12 mS/cm.",
                            "citation_keys": ["1"],
                            "confidence": 0.95,
                        }
                    ],
                },
                {
                    "section_id": "SEC-02",
                    "title": "Industrial Scaling and Manufacturing Bottlenecks",
                    "narrative": (
                        "Transitioning from laboratory pellet pressing to continuous roll-to-roll web coating requires "
                        "maintaining ultra-dry processing environments with dew points below -40 degrees Celsius [3]. "
                        "Pilot lines operated by leading automotive consortia are deploying dry-electrode coating methods "
                        "to curtail energy usage and factory footprint by over thirty percent [3]."
                    ),
                    "citation_indices": [3],
                    "claim_ids": ["CLM-02"],
                    "claims": [
                        {
                            "claim_id": "CLM-02",
                            "claim_text": "Dry electrode coating reduces pilot line manufacturing energy consumption by 42%.",
                            "citation_keys": ["3"],
                            "confidence": 0.91,
                        }
                    ],
                },
            ],
            "key_takeaways": [
                "Sulfide electrolytes match or exceed liquid electrolytes in room-temperature ionic conductivity [1].",
                "Commercial automotive roadmaps target 500 Wh/kg cell energy density and pack costs under $75/kWh by 2030 [2].",
                "Continuous roll-to-roll manufacturing and dry-room atmospheric control represent the primary capital cost barriers [3].",
            ],
            "sources": [
                {
                    "source_id": "SRC-01",
                    "citation_index": 1,
                    "url": "https://mock-science.org/materials/solid-electrolyte-conductivities-breakthrough",
                    "title": "Solid Electrolyte Materials and Room-Temperature Ionic Conductivities",
                    "snippet": "Breakthroughs in sulfide and oxide solid electrolytes exceeding 12 mS/cm ionic conductivity at room temperature.",
                    "author": "Dr. Elena Rostova",
                    "published_date": "2025-11-14T08:00:00Z",
                },
                {
                    "source_id": "SRC-02",
                    "citation_index": 2,
                    "url": "https://mock-energy-gov.org/reports/battery500-consortium-roadmap-2030",
                    "title": "DOE Battery500 Consortium: Energy Density and Commercial Cost Roadmaps",
                    "snippet": "Technical roadmaps targeting 500 Wh/kg and pack costs below $75/kWh by 2030 for solid-state architectures.",
                    "author": "Office of Energy Efficiency & Renewable Energy",
                    "published_date": "2025-08-22T14:30:00Z",
                },
                {
                    "source_id": "SRC-03",
                    "citation_index": 3,
                    "url": "https://mock-tech-industrial.com/manufacturing/solid-state-pilot-line-scalability",
                    "title": "Industrial Scaling of Solid-State Batteries: Roll-to-Roll Coating and Dry Rooms",
                    "snippet": "Analyzing continuous roll-to-roll manufacturing, dry-room dew point control, and pilot line metrics across automotive consortia.",
                    "author": "Marcus Sterling",
                    "published_date": "2026-01-10T11:15:00Z",
                },
            ],
            "metadata": {
                "retrieval_mode": "mock",
                "total_sources_scanned": 5,
                "total_claims_extracted": 12,
                "processing_time_ms": 340.5,
            },
        }

    def test_valid_brief_passes_validation(self):
        result = validate_brief(self.valid_brief)
        self.assertTrue(result.is_valid, f"Valid brief failed validation: {result.errors}")
        self.assertEqual(len(result.errors), 0)
        self.assertGreaterEqual(result.metrics["total_brief_words"], 120)

    def test_referential_integrity_catches_orphan_citations(self):
        corrupt_brief = json.loads(json.dumps(self.valid_brief))
        # Insert reference to [99] which doesn't exist in sources
        corrupt_brief["executive_summary"] += " Furthermore, unverified studies suggest anomalous behavior [99]."
        result = validate_brief(corrupt_brief)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("REFERENTIAL_INTEGRITY" in err for err in result.errors))
        self.assertTrue(any("99" in err for err in result.errors))

    def test_referential_integrity_catches_orphan_claim_key(self):
        corrupt_brief = json.loads(json.dumps(self.valid_brief))
        corrupt_brief["thematic_sections"][0]["claims"][0]["citation_keys"] = ["SRC-999"]
        result = validate_brief(corrupt_brief)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("REFERENTIAL_INTEGRITY" in err for err in result.errors))

    def test_placeholder_detection_fails(self):
        corrupt_brief = json.loads(json.dumps(self.valid_brief))
        corrupt_brief["executive_summary"] = (
            "TODO: complete this section later with additional literature findings and real metrics. "
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore."
        )
        result = validate_brief(corrupt_brief)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("PLACEHOLDER_TEXT" in err for err in result.errors))

    def test_short_executive_summary_fails(self):
        corrupt_brief = json.loads(json.dumps(self.valid_brief))
        corrupt_brief["executive_summary"] = "Solid state batteries are promising and will be commercialized soon."
        result = validate_brief(corrupt_brief)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("EMPTY_OR_TRUNCATED_TEXT" in err for err in result.errors))

    def test_fewer_than_three_takeaways_fails(self):
        corrupt_brief = json.loads(json.dumps(self.valid_brief))
        corrupt_brief["key_takeaways"] = [
            "Solid state batteries offer high energy density [1].",
            "Manufacturing scalability is the primary hurdle [3].",
        ]
        result = validate_brief(corrupt_brief)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("key_takeaways" in err for err in result.errors))

    def test_missing_required_fields_fails_schema(self):
        corrupt_brief = json.loads(json.dumps(self.valid_brief))
        del corrupt_brief["executive_summary"]
        result = validate_brief(corrupt_brief)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("executive_summary" in err for err in result.errors))

    def test_strict_mode_flags_uncited_sources(self):
        # Brief with 3 sources, but only sources 1 and 2 are cited in text
        partial_cited_brief = json.loads(json.dumps(self.valid_brief))
        partial_cited_brief["executive_summary"] = partial_cited_brief["executive_summary"].replace("[3]", "[1]")
        partial_cited_brief["thematic_sections"][1]["narrative"] = (
            "Continuous roll-to-roll web coating requires ultra-dry processing environments "
            "with dew points below negative forty degrees Celsius to avert moisture degradation [1]."
        )
        partial_cited_brief["thematic_sections"][1]["citation_indices"] = [1]
        partial_cited_brief["thematic_sections"][1]["claims"][0]["citation_keys"] = ["1"]
        partial_cited_brief["key_takeaways"][2] = (
            "Atmospheric control and roll-to-roll web coating remain the principal commercial barriers [1]."
        )
        # Normal mode should warn
        normal_res = validate_brief(partial_cited_brief, strict=False)
        self.assertTrue(normal_res.is_valid)
        self.assertTrue(any("UNCITED_SOURCES" in w for w in normal_res.warnings))

        # Strict mode should error
        strict_res = validate_brief(partial_cited_brief, strict=True)
        self.assertFalse(strict_res.is_valid)
        self.assertTrue(any("UNCITED_SOURCES" in err for err in strict_res.errors))


class TestRunnerLogic(unittest.TestCase):
    """Tests the verification runner resolution and query management."""

    def test_resolve_queries(self):
        from research_synthesis.verification.runner import VerificationRunner

        runner = VerificationRunner()
        acceptance_q = runner.resolve_queries("acceptance")
        self.assertEqual(len(acceptance_q), 3)

        all_q = runner.resolve_queries("all")
        self.assertEqual(len(all_q), 4)

        single_q = runner.resolve_queries("solid_state_battery")
        self.assertEqual(len(single_q), 1)
        self.assertEqual(single_q[0]["id"], "solid_state_battery")


if __name__ == "__main__":
    unittest.main()
