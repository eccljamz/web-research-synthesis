"""Comprehensive Unit & Integration Tests for Tracks A, B, and C.

Track A: Comparative & Longitudinal Synthesis (ComparativeSynthesisEngine, LongitudinalTracker)
Track B: Zero-Dependency PDF Stream Ingestion (ZeroDepPDFExtractor, ArxivRetrievalClient PDF streams)
Track C: Deployment & Release Distribution (Dockerfile, .dockerignore, release workflow invariants)
"""

from __future__ import annotations

import json
import sys
import unittest
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from research_synthesis.models import (
    KeyTakeaway,
    RawWebDocument,
    ResearchBrief,
    SourceCitation,
    ThematicSection,
)
from research_synthesis.pipeline import ResearchPipeline
from research_synthesis.retrieval.parser import DocumentParser
from research_synthesis.retrieval.pdf_parser import ExtractedPDFDocument, ZeroDepPDFExtractor
from research_synthesis.retrieval.retriever import ArxivRetrievalClient
from research_synthesis.synthesis.comparative import (
    ComparativeSynthesisEngine,
    ComparativeSynthesisResult,
    LongitudinalTracker,
)
from research_synthesis.synthesis.formatters import JSONSchemaSerializer


def _build_synthetic_pdf_bytes(
    title: str = "Solid-State vs Sodium-Ion Preprint",
    author: str = "Dr. Aria Chen",
    creation_date: str = "D:20260315120000",
    stream_text_ops: str = "",
    compress: bool = True,
) -> bytes:
    """Construct a valid synthetic PDF byte payload with /FlateDecode stream."""
    if not stream_text_ops:
        stream_text_ops = (
            "BT\n"
            "/F1 14 Tf\n"
            "72 720 Td\n"
            "(1. Introduction) Tj\n"
            "0 -24 Td\n"
            "[(Sulfide) -180 (solid-state) -180 (electrolytes) -180 (demonstrate) -180 "
            "(ionic) -180 (conductivity) -180 (surpassing) -180 (15 mS/cm) -180 (at) -180 (25 C.)] TJ\n"
            "T*\n"
            "(Full-cell prototypes achieve energy density of 480 Wh/kg with capacity retention of 92% after 1000 cycles.) Tj\n"
            "0 -24 Td\n"
            "(2. Experimental Results) Tj\n"
            "0 -18 Td\n"
            "(Operando synchrotron X-ray tomography confirms dendrite suppression up to 4.5 mA/cm2 critical current density.) Tj\n"
            "ET"
        )
    raw_stream = stream_text_ops.encode("latin-1")
    if compress:
        stream_payload = zlib.compress(raw_stream)
        filter_spec = b"/Filter /FlateDecode "
    else:
        stream_payload = raw_stream
        filter_spec = b""

    pdf_parts = [
        b"%PDF-1.4\n",
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>\nendobj\n",
        (
            b"4 0 obj\n<< "
            + filter_spec
            + b"/Length "
            + str(len(stream_payload)).encode("ascii")
            + b" >>\nstream\n"
            + stream_payload
            + b"\nendstream\nendobj\n"
        ),
        (
            f"5 0 obj\n<< /Title ({title}) /Author ({author}) /CreationDate ({creation_date}) >>\nendobj\n"
        ).encode("latin-1"),
        b"%%EOF\n",
    ]
    return b"".join(pdf_parts)


class TestTrackAComparativeLongitudinalSynthesis(unittest.TestCase):
    """Test Track A: Meta-Brief Cross-Comparison & Longitudinal Trend/Velocity Tracking."""

    def setUp(self) -> None:
        self.engine = ComparativeSynthesisEngine()
        self.brief_ssb = ResearchBrief(
            brief_id="brief-ssb01",
            topic="Solid-State Battery Commercialization",
            executive_summary=(
                "Solid-state batteries achieve 450 Wh/kg energy density [1] while pilot manufacturing "
                "costs remain near $180 per kWh in 2024 before projected $100 per kWh parity in 2028 [2]."
            ),
            key_takeaways=[
                KeyTakeaway(
                    text="Sulfide solid-state prototypes achieve 450 Wh/kg energy density and 800 cycles durability [1].",
                    citation_indices=[1],
                ),
                KeyTakeaway(
                    text="Pilot line dry-room manufacturing costs $180 per kWh in 2024, targeting $100 per kWh by 2028 [2].",
                    citation_indices=[2],
                ),
                KeyTakeaway(
                    text="Oxide LLZO electrolytes withstand 800 degrees Celsius without thermal runaway [1].",
                    citation_indices=[1],
                ),
            ],
            thematic_sections=[
                ThematicSection(
                    section_id="sec-01",
                    title="Electrochemical Density & Thermal Stability",
                    narrative=(
                        "Solid-state battery prototypes demonstrate 450 Wh/kg gravimetric energy density and "
                        "12 mS/cm ionic conductivity in 2024 [1]. Ceramic electrolytes remain stable up to 800 degrees Celsius [1]."
                    ),
                    citation_indices=[1],
                    claim_ids=["clm-ssb-1"],
                    key_findings=["Energy density reaches 450 Wh/kg [1]."],
                ),
                ThematicSection(
                    section_id="sec-02",
                    title="Manufacturing Cost Parity Trajectory",
                    narrative=(
                        "Current pilot manufacturing costs $180 per kWh in 2024, whereas commercial scaling "
                        "targets $100 per kWh parity by 2028 with $2.4 billion gigafactory CapEx [2]."
                    ),
                    citation_indices=[2],
                    claim_ids=["clm-ssb-2"],
                    key_findings=["Cost declines from $180 per kWh (2024) to $100 per kWh (2028) [2]."],
                ),
            ],
            sources=[
                SourceCitation(
                    citation_index=1,
                    source_id="SRC-01",
                    title="Solid-State Battery Breakthroughs",
                    url="https://energy-tech-review.org/solid-state-batteries-2024",
                    author="Dr. Elena Vance",
                    publish_date="2024-03-15",
                    snippet="Solid-state prototypes demonstrated energy densities of 450 Wh/kg to 500 Wh/kg.",
                    attributed_claim_ids=["clm-ssb-1"],
                ),
                SourceCitation(
                    citation_index=2,
                    source_id="SRC-02",
                    title="Manufacturing Cost Parity Analysis",
                    url="https://clean-mobility-economics.com/battery-manufacturing-costs",
                    author="Marcus Sterling",
                    publish_date="2024-05-20",
                    snippet="Pilot line dry-room processing costs exceed $180 per kWh, targeting $100 per kWh by 2028.",
                    attributed_claim_ids=["clm-ssb-2"],
                ),
            ],
        )

        self.brief_na = ResearchBrief(
            brief_id="brief-na01",
            topic="Sodium-Ion Battery Grid & EV Scaling",
            executive_summary=(
                "Sodium-ion batteries deliver 160 Wh/kg energy density [1] while achieving low manufacturing "
                "costs of $65 per kWh by 2026 using abundant soda ash precursors [2]."
            ),
            key_takeaways=[
                KeyTakeaway(
                    text="Prussian white and layered oxide sodium-ion cells reach 160 Wh/kg energy density and 4000 cycles [1].",
                    citation_indices=[1],
                ),
                KeyTakeaway(
                    text="Abundant sodium precursors reduce cell manufacturing cost to $65 per kWh by 2026 [2].",
                    citation_indices=[2],
                ),
                KeyTakeaway(
                    text="Sodium-ion packs retain 88% capacity at -20 degrees Celsius operating temperatures [1].",
                    citation_indices=[1],
                ),
            ],
            thematic_sections=[
                ThematicSection(
                    section_id="sec-01",
                    title="Cathode Chemistry & Cycle Durability",
                    narrative=(
                        "Sodium-ion cells achieve 160 Wh/kg energy density and endure 4000 cycles for stationary storage in 2025 [1]."
                    ),
                    citation_indices=[1],
                    claim_ids=["clm-na-1"],
                    key_findings=["Energy density reaches 160 Wh/kg with 4000 cycles [1]."],
                ),
                ThematicSection(
                    section_id="sec-02",
                    title="Supply Chain & Cost Curve Advantage",
                    narrative=(
                        "Eliminating lithium and cobalt lowers cell manufacturing cost to $65 per kWh by 2026 "
                        "with $0.9 billion gigafactory capital expenditure [2]."
                    ),
                    citation_indices=[2],
                    claim_ids=["clm-na-2"],
                    key_findings=["Manufacturing cost reaches $65 per kWh by 2026 [2]."],
                ),
            ],
            sources=[
                SourceCitation(
                    citation_index=1,
                    source_id="SRC-01",
                    title="Sodium-Ion Cathode Architectures",
                    url="https://grid-storage-journal.org/sodium-ion-2025",
                    author="Dr. Wei Zhang",
                    publish_date="2025-02-10",
                    snippet="Sodium-ion cells achieve 160 Wh/kg energy density and 4000 cycles durability.",
                    attributed_claim_ids=["clm-na-1"],
                ),
                SourceCitation(
                    citation_index=2,
                    source_id="SRC-02",
                    title="Sodium-Ion Supply Chain Economics",
                    url="https://battery-cost-monitor.org/sodium-ion-parity-2026",
                    author="Hannah Lind",
                    publish_date="2025-04-01",
                    snippet="Cell manufacturing cost drops to $65 per kWh by 2026.",
                    attributed_claim_ids=["clm-na-2"],
                ),
            ],
        )

    def test_compare_briefs_generates_tradeoff_matrix_and_schema_valid_meta_brief(self) -> None:
        result = self.engine.compare_briefs([self.brief_ssb, self.brief_na])
        self.assertIsInstance(result, ComparativeSynthesisResult)
        self.assertEqual(len(result.topics), 2)
        self.assertGreaterEqual(len(result.tradeoff_matrix), 2)
        self.assertGreaterEqual(len(result.cost_parity_curves), 1)
        self.assertGreaterEqual(len(result.cross_discrepancies), 1)

        # Verify unified 1-based citation re-indexing across all 4 distinct sources
        meta = result.meta_brief
        self.assertEqual(len(meta.sources), 4)
        self.assertEqual([s.citation_index for s in meta.sources], [1, 2, 3, 4])

        # Verify Energy Density and Unit Manufacturing Cost trade-offs were captured
        dimensions = {row.dimension for row in result.tradeoff_matrix}
        self.assertIn("Energy Density", dimensions)
        self.assertIn("Unit Manufacturing Cost", dimensions)

        # Verify JSONSchemaSerializer compliance
        serialized = JSONSchemaSerializer.to_dict(meta)
        self.assertTrue(serialized["brief_id"].startswith("brief-cmp-"))
        self.assertGreaterEqual(len(serialized["thematic_sections"]), 3)
        self.assertGreaterEqual(len(serialized["key_takeaways"]), 3)

    def test_longitudinal_tracker_detects_velocity_and_parity_shifts(self) -> None:
        result = self.engine.compare_briefs([self.brief_ssb, self.brief_na])
        self.assertGreaterEqual(len(result.temporal_shifts), 1)

        # Check cost parity trajectory from $180/kWh (2024) -> $100/kWh (2028)
        cost_shifts = [s for s in result.temporal_shifts if "Cost" in s.dimension]
        self.assertTrue(len(cost_shifts) >= 1)
        cs = cost_shifts[0]
        self.assertEqual(cs.start_year, 2024)
        self.assertEqual(cs.end_year, 2028)
        self.assertEqual(cs.span_years, 4)
        self.assertLess(cs.annual_velocity or 0.0, 0.0)
        self.assertEqual(cs.trajectory, "CONVERGING_PARITY")

    def test_pipeline_compare_integration(self) -> None:
        pipeline = ResearchPipeline(mode="mock", use_cache=False)
        cmp_res = pipeline.compare([
            "Next-Generation Solid-State Battery Commercialization",
            "Global Supply Chain Re-Shoring and Friend-Shoring Dynamics",
        ])
        self.assertIsInstance(cmp_res, ComparativeSynthesisResult)
        self.assertIn("vs.", cmp_res.meta_brief.topic)
        md = cmp_res.to_markdown()
        self.assertIn("Cross-Topic Technological & Domain Trade-Offs", md)
        self.assertIn("Longitudinal Trend & Velocity Tracking", md)


class TestTrackBZeroDepPDFStreamIngestion(unittest.TestCase):
    """Test Track B: Pure standard-library PDF /FlateDecode stream extraction & arXiv PDF parsing."""

    def test_flatedecode_pdf_extraction_and_metadata(self) -> None:
        pdf_bytes = _build_synthetic_pdf_bytes(
            title="High-Conductivity Sulfide Solid Electrolytes",
            author="Dr. Elena Vance, Prof. Kenji Takahashi",
            creation_date="D:20260218093000",
            compress=True,
        )
        self.assertTrue(ZeroDepPDFExtractor.is_pdf_bytes(pdf_bytes))

        extracted = ZeroDepPDFExtractor.extract_from_bytes(pdf_bytes)
        self.assertIsInstance(extracted, ExtractedPDFDocument)
        self.assertEqual(extracted.title, "High-Conductivity Sulfide Solid Electrolytes")
        self.assertEqual(extracted.author, "Dr. Elena Vance, Prof. Kenji Takahashi")
        self.assertEqual(extracted.published_date, "2026-02-18")
        self.assertEqual(extracted.page_count, 1)
        self.assertGreaterEqual(extracted.decompressed_streams, 1)
        self.assertIn("15 mS/cm", extracted.text)
        self.assertIn("480 Wh/kg", extracted.text)
        self.assertIn("4.5 mA/cm2", extracted.text)

    def test_literal_octal_and_hex_string_decoding(self) -> None:
        decoded_lit = ZeroDepPDFExtractor.decode_pdf_literal_string(r"Battery \050Li-Metal\051 Efficiency \n 99.5%")
        self.assertIn("Battery (Li-Metal) Efficiency", decoded_lit)

        # UTF-16BE hex string with BOM FEFF for "arXiv"
        utf16_hex = "FEFF00610072005800690076"
        self.assertEqual(ZeroDepPDFExtractor.decode_pdf_hex_string(utf16_hex), "arXiv")

    def test_document_parser_ingests_raw_pdf_document(self) -> None:
        pdf_bytes = _build_synthetic_pdf_bytes()
        raw_doc = RawWebDocument(
            url="https://arxiv.org/pdf/2602.12345.pdf",
            status_code=200,
            headers={"Content-Type": "application/pdf"},
            raw_html=pdf_bytes.decode("latin-1"),
        )
        article = DocumentParser.parse(raw_doc)
        self.assertEqual(article.metadata.content_type, "application/pdf")
        self.assertEqual(article.metadata.title, "Solid-State vs Sodium-Ion Preprint")
        self.assertEqual(article.metadata.author, "Dr. Aria Chen")
        self.assertEqual(article.metadata.published_date, "2026-03-15")
        self.assertIn("480 Wh/kg", article.cleaned_text)

    @patch("urllib.request.urlopen")
    def test_arxiv_client_direct_pdf_and_fulltext_enrichment(self, mock_urlopen: MagicMock) -> None:
        pdf_bytes = _build_synthetic_pdf_bytes()
        mock_resp = MagicMock()
        mock_resp.read.return_value = pdf_bytes
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        client = ArxivRetrievalClient(fetch_pdf=True)
        self.assertEqual(
            client.derive_pdf_url("https://arxiv.org/abs/2301.01234v1"),
            "https://arxiv.org/pdf/2301.01234v1.pdf",
        )

        doc = client.fetch_url("https://arxiv.org/pdf/2301.01234v1.pdf")
        self.assertEqual(doc.status_code, 200)
        self.assertIn("480 Wh/kg", doc.raw_html)
        self.assertIn("15 mS/cm", doc.raw_html)


class TestTrackCDeploymentAndDistribution(unittest.TestCase):
    """Test Track C: Containerization & Release Distribution Artifacts."""

    def test_dockerfile_and_dockerignore_exist_and_follow_invariants(self) -> None:
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        dockerignore_path = PROJECT_ROOT / ".dockerignore"
        release_yml_path = PROJECT_ROOT / ".github" / "workflows" / "release.yml"

        self.assertTrue(dockerfile_path.exists(), "Dockerfile must exist at project root")
        self.assertTrue(dockerignore_path.exists(), ".dockerignore must exist at project root")
        self.assertTrue(release_yml_path.exists(), "release.yml must exist in .github/workflows")

        dockerfile_text = dockerfile_path.read_text(encoding="utf-8")
        self.assertIn("FROM python:3.11-alpine", dockerfile_text)
        self.assertIn("EXPOSE 8080", dockerfile_text)
        self.assertIn("HEALTHCHECK", dockerfile_text)
        self.assertIn("USER research", dockerfile_text)

    def test_dashboard_html_exposes_compare_and_velocity_ui_tab(self) -> None:
        from research_synthesis.server import DASHBOARD_HTML

        self.assertIn("switchTab('compare')", DASHBOARD_HTML)
        self.assertIn('id="compareTab"', DASHBOARD_HTML)
        self.assertIn('id="tradeoffTable"', DASHBOARD_HTML)
        self.assertIn('id="velocitySvg"', DASHBOARD_HTML)
        self.assertIn("async function runComparison()", DASHBOARD_HTML)
        self.assertIn("function renderVelocityChart(", DASHBOARD_HTML)


if __name__ == "__main__":
    unittest.main()
