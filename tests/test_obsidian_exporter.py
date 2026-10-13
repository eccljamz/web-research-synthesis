"""Unit and integration tests for Obsidian PKM and Knowledge Graph Exporter.

Tests:
1. ObsidianExporter.format_single_note: YAML frontmatter, Obsidian callouts, anchor blocks.
2. ObsidianExporter.format_vault: Multi-note vault structure, wikilinks, and Canvas JSON.
3. ObsidianExporter.export_to_directory: Filesystem writing, directory layout, UTF-8 integrity.
4. ResearchBrief.to_obsidian and ResearchBrief.export_obsidian_vault integration.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_synthesis.models import (
    DiscrepancyGroup,
    KeyTakeaway,
    ResearchBrief,
    SourceCitation,
    ThematicSection,
)
from research_synthesis.synthesis.formatters import ObsidianExporter


def create_sample_brief() -> ResearchBrief:
    """Helper to construct a comprehensive synthetic ResearchBrief with citations & conflicts."""
    sources = [
        SourceCitation(
            citation_index=1,
            source_id="SRC-01",
            title="Sulfide Solid-State Electrolytes",
            url="https://example.com/sulfide-electrolytes",
            author="Dr. Sarah Connor",
            publish_date="2025-06-15",
            snippet="Room temperature ionic conductivity exceeds 15 mS/cm.",
        ),
        SourceCitation(
            citation_index=2,
            source_id="SRC-02",
            title="Solid-State Battery Cost Benchmarks",
            url="https://example.com/battery-costs",
            author="Alex Vance",
            publish_date="2025-09-01",
            snippet="Pilot manufacturing indicates initial pack costs around $140/kWh.",
        ),
    ]

    takeaways = [
        KeyTakeaway(
            text="Sulfide solid electrolytes achieve ionic conductivity over 15 mS/cm [1].",
            citation_indices=[1],
        ),
        KeyTakeaway(
            text="Initial cell-level manufacturing costs range between $110 and $140 per kWh [2].",
            citation_indices=[2],
        ),
    ]

    discrepancies = [
        DiscrepancyGroup(
            discrepancy_id="disc-01",
            entity="Manufacturing Cost Parity",
            discrepancy_type="NUMERICAL_VARIATION",
            claim_a_id="claim-01",
            claim_b_id="claim-02",
            claim_a_text="Cost parity projected at $100/kWh by 2028 [1].",
            claim_b_text="Cost parity delayed to 2032 at $140/kWh [2].",
            source_a_url="https://example.com/sulfide-electrolytes",
            source_b_url="https://example.com/battery-costs",
            explanation="Different assumptions regarding roll-to-roll scaling yields.",
        )
    ]

    sections = [
        ThematicSection(
            section_id="sec-01",
            title="Electrolyte Conductivity and Chemistries",
            narrative="Recent innovations in sulfide solid electrolytes demonstrate significant ionic conductivity enhancements [1].",
            key_findings=[
                "Ionic conductivity reaches 15 mS/cm at room temperature [1].",
            ],
            discrepancies=discrepancies,
        ),
        ThematicSection(
            section_id="sec-02",
            title="Manufacturing Cost Trajectories",
            narrative="Industrial pilot facilities report varying cost metrics across dry-room roll-to-roll processes [2].",
            key_findings=[
                "Capital expenditures for 20 GWh facilities exceed $2 billion [2].",
            ],
            discrepancies=[],
        ),
    ]

    return ResearchBrief(
        brief_id="brief-test-obsidian-001",
        topic="Solid-State Battery Breakthroughs",
        executive_summary=(
            "Solid-state battery commercialization has advanced with sulfide-based electrolytes [1]. "
            "However, near-term cost parity remains an operational bottleneck across gigafactories [2]."
        ),
        key_takeaways=takeaways,
        thematic_sections=sections,
        sources=sources,
    )


class TestObsidianExporter(unittest.TestCase):
    """Test suite for Obsidian PKM formatters and knowledge vault generation."""

    def setUp(self):
        self.brief = create_sample_brief()

    def test_format_single_note(self):
        note = ObsidianExporter.format_single_note(self.brief)

        # Frontmatter
        self.assertTrue(note.startswith("---\n"))
        self.assertIn('title: "Solid-State Battery Breakthroughs"', note)
        self.assertIn('brief_id: "brief-test-obsidian-001"', note)
        self.assertIn('type: "research-brief"', note)
        self.assertIn("tags:", note)
        self.assertIn("- research", note)
        self.assertIn("- solid-state-battery-breakthroughs", note)
        self.assertIn("sources_count: 2", note)

        # Callouts
        self.assertIn("> [!summary] Executive Summary", note)
        self.assertIn("> [!tip] Key Takeaways", note)
        self.assertIn("> [!warning] Conflicting Claims & Data Variances", note)

        # Anchor blocks
        self.assertIn("^src-1", note)
        self.assertIn("^src-2", note)
        self.assertIn("[Sulfide Solid-State Electrolytes](https://example.com/sulfide-electrolytes)", note)

    def test_format_vault_structure(self):
        vault = ObsidianExporter.format_vault(self.brief)

        # Verify expected files
        self.assertIn("Index.md", vault)
        self.assertIn("Knowledge_Graph.canvas", vault)

        # Check section notes
        sec_files = [f for f in vault.keys() if f.startswith("Sections/")]
        self.assertEqual(len(sec_files), 2)

        # Check source notes
        src_files = [f for f in vault.keys() if f.startswith("Sources/")]
        self.assertEqual(len(src_files), 2)

        # Check Index note contents
        index_content = vault["Index.md"]
        self.assertIn('parent: "[[Index]]"', vault[sec_files[0]])
        self.assertIn('parent: "[[Index]]"', vault[src_files[0]])
        self.assertIn("[[Sections/", index_content)
        self.assertIn("[[Sources/", index_content)

        # Check Canvas JSON
        canvas_json = json.loads(vault["Knowledge_Graph.canvas"])
        self.assertIn("nodes", canvas_json)
        self.assertIn("edges", canvas_json)
        self.assertGreaterEqual(len(canvas_json["nodes"]), 5)  # Index + 2 Sections + 2 Sources
        self.assertGreaterEqual(len(canvas_json["edges"]), 4)

    def test_export_to_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "obsidian_vault"
            written_paths = ObsidianExporter.export_to_directory(self.brief, out_dir)

            self.assertGreaterEqual(len(written_paths), 5)
            self.assertTrue((out_dir / "Index.md").is_file())
            self.assertTrue((out_dir / "Knowledge_Graph.canvas").is_file())
            self.assertTrue((out_dir / "Sections").is_dir())
            self.assertTrue((out_dir / "Sources").is_dir())

            # Verify UTF-8 readability
            index_text = (out_dir / "Index.md").read_text(encoding="utf-8")
            self.assertIn("Solid-State Battery Breakthroughs", index_text)

    def test_brief_model_methods(self):
        note = self.brief.to_obsidian()
        self.assertIn("> [!summary] Executive Summary", note)

        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = Path(tmpdir) / "model_vault"
            files = self.brief.export_obsidian_vault(vault_dir)
            self.assertGreaterEqual(len(files), 5)
            self.assertTrue((vault_dir / "Index.md").is_file())


if __name__ == "__main__":
    unittest.main()
