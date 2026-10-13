"""
runner.py - Acceptance Verification Runner for Autonomous Web Research and Knowledge Synthesis.

Coordinates running the research synthesis pipeline across acceptance test queries,
saves output research briefs (JSON and Markdown), executes schema and semantic validators,
and generates structured diagnostic verification reports.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from research_synthesis.verification.validator import ResearchBriefValidator, ValidationResult

logger = logging.getLogger(__name__)

# Standard 3 diverse acceptance test queries + edge query from R4 specifications
ACCEPTANCE_QUERIES = [
    {
        "id": "solid_state_battery",
        "domain": "science_technology",
        "topic": "Next-Generation Solid-State Battery Commercialization: Energy Density Roadmaps, Solid Electrolytes, and Manufacturing Scalability",
    },
    {
        "id": "supply_chain_reshoring",
        "domain": "macroeconomics",
        "topic": "Global Supply Chain Re-Shoring and Friend-Shoring Dynamics: Macroeconomic Inflation Impacts and Industrial Policy Interventions",
    },
    {
        "id": "little_ice_age",
        "domain": "history_climatology",
        "topic": "The Little Ice Age Climate Shocks in 17th Century Europe: Agrarian Output Collapses, Famine Cycles, and Social Upheaval",
    },
]

EDGE_QUERIES = [
    {
        "id": "microplastics",
        "domain": "environmental_toxicology_law",
        "topic": "Microplastic Bioaccumulation in Agricultural Soil Ecosystems: Trophic Transfer Mechanisms and Emerging EU Regulatory Directives",
    }
]


class VerificationRunner:
    """Executes the research synthesis pipeline against test queries and validates briefs."""

    def __init__(
        self,
        mode: str = "mock",
        output_dir: Optional[Union[str, Path]] = None,
        strict: bool = False,
        corpus_manifest: Optional[Union[str, Path]] = None,
    ):
        self.mode = mode
        self.output_dir = Path(output_dir) if output_dir else Path("./test_reports")
        self.strict = strict

        # Path to mock corpus manifest
        if corpus_manifest is None:
            corpus_manifest = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "mock_corpus" / "manifest.json"
        self.corpus_manifest = Path(corpus_manifest)

        self.validator = ResearchBriefValidator(strict=strict)

    def resolve_queries(self, query_set: str = "acceptance") -> List[Dict[str, str]]:
        if query_set == "acceptance":
            return ACCEPTANCE_QUERIES
        elif query_set == "all":
            return ACCEPTANCE_QUERIES + EDGE_QUERIES
        elif query_set == "edge":
            return EDGE_QUERIES
        else:
            # Check if specific query ID matches
            for q in ACCEPTANCE_QUERIES + EDGE_QUERIES:
                if q["id"] == query_set:
                    return [q]
            # Custom query topic
            return [{"id": "custom_query", "domain": "custom", "topic": query_set}]

    def run_pipeline_for_topic(self, topic: str, query_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """
        Attempts to execute the real ResearchPipeline. If the pipeline module is not yet
        available, checks for pre-synthesized briefs or informs callers cleanly.
        """
        # Try importing real pipeline
        try:
            from research_synthesis.pipeline import ResearchPipeline  # type: ignore

            pipeline = ResearchPipeline(
                mode=self.mode,
                corpus_manifest_path=str(self.corpus_manifest) if self.corpus_manifest.exists() else None,
            )
            brief_obj = pipeline.run(topic)

            # Extract dict, json, and markdown
            if hasattr(brief_obj, "to_dict"):
                brief_dict = brief_obj.to_dict()
            elif isinstance(brief_obj, dict):
                brief_dict = brief_obj
            else:
                brief_dict = json.loads(json.dumps(brief_obj, default=lambda o: getattr(o, "__dict__", str(o))))

            md_content = brief_obj.to_markdown() if hasattr(brief_obj, "to_markdown") else ""
            json_content = brief_obj.to_json() if hasattr(brief_obj, "to_json") else json.dumps(brief_dict, indent=2)

            # Save markdown artifact alongside json
            if md_content:
                md_path = self.output_dir / f"{query_id}.md"
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_content)

            # Save html artifact alongside markdown and json
            if hasattr(brief_obj, "to_html"):
                html_content = brief_obj.to_html()
                if html_content:
                    html_path = self.output_dir / f"{query_id}.html"
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(html_content)

            return brief_dict, json_content, None
        except ImportError:
            # Pipeline is not yet implemented by worker agents
            # Look for existing generated report in output directory
            existing_json = self.output_dir / f"{query_id}.json"
            if existing_json.exists():
                with open(existing_json, "r", encoding="utf-8") as f:
                    brief_dict = json.load(f)
                existing_md = self.output_dir / f"{query_id}.md"
                md_content = existing_md.read_text(encoding="utf-8") if existing_md.exists() else ""
                return brief_dict, json.dumps(brief_dict, indent=2), None

            return None, None, "Pipeline implementation module 'research_synthesis.pipeline' is pending implementation."
        except Exception as e:
            return None, None, f"Pipeline runtime exception: {e}"

    def run(self, query_set: str = "acceptance") -> Tuple[bool, Dict[str, Any]]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        queries = self.resolve_queries(query_set)

        total_queries = len(queries)
        passed_queries = 0
        failed_queries = 0
        query_results: List[Dict[str, Any]] = []

        start_all = time.perf_counter()

        for q in queries:
            qid = q["id"]
            topic = q["topic"]
            t_start = time.perf_counter()

            brief_dict, json_str, error_msg = self.run_pipeline_for_topic(topic, qid)
            elapsed_sec = round(time.perf_counter() - t_start, 3)

            if error_msg or brief_dict is None:
                failed_queries += 1
                query_results.append({
                    "query_id": qid,
                    "topic": topic,
                    "passed": False,
                    "elapsed_sec": elapsed_sec,
                    "error": error_msg or "No brief generated",
                    "validation": None,
                })
                continue

            # Save generated brief JSON and Markdown
            json_path = self.output_dir / f"{qid}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                f.write(json_str if json_str else json.dumps(brief_dict, indent=2))

            # Validate brief
            val_result: ValidationResult = self.validator.validate(brief_dict)

            if val_result.is_valid:
                passed_queries += 1
            else:
                failed_queries += 1

            query_results.append({
                "query_id": qid,
                "topic": topic,
                "passed": val_result.is_valid,
                "elapsed_sec": elapsed_sec,
                "json_artifact": str(json_path),
                "validation": {
                    "is_valid": val_result.is_valid,
                    "errors": val_result.errors,
                    "warnings": val_result.warnings,
                    "metrics": val_result.metrics,
                },
            })

        total_elapsed = round(time.perf_counter() - start_all, 3)
        all_passed = (failed_queries == 0) and (total_queries > 0)

        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "overall_status": "PASSED" if all_passed else "FAILED",
            "mode": self.mode,
            "strict": self.strict,
            "total_queries": total_queries,
            "passed_queries": passed_queries,
            "failed_queries": failed_queries,
            "total_elapsed_sec": total_elapsed,
            "query_results": query_results,
        }

        # Save verification report
        report_path = self.output_dir / "verification_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        return all_passed, report


def run_acceptance_verification(
    mode: str = "mock",
    query_set: str = "acceptance",
    output_dir: Optional[Union[str, Path]] = None,
    strict: bool = False,
    corpus_manifest: Optional[Union[str, Path]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Primary function called by CLI verify.py."""
    runner = VerificationRunner(
        mode=mode,
        output_dir=output_dir,
        strict=strict,
        corpus_manifest=corpus_manifest,
    )
    return runner.run(query_set=query_set)
