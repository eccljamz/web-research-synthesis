#!/usr/bin/env python3
"""
verify.py - Automated Verification Test Script for Autonomous Web Research System.

Executes the pipeline against acceptance test queries, validates structural schema
conformance, referential integrity (citations [N] resolving to valid sources),
non-empty findings, and anti-degeneracy invariants.

Exits with:
  0 - All verification assertions passed.
  1 - Verification failure (schema violation, broken citation, degenerate text).
  2 - Pipeline unhandled execution error.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure 'src' directory is in python search path
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Autonomous Web Research & Knowledge Synthesis - Verification Test Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python verify.py                  # Standard acceptance run (3 diverse queries, mock mode)
  python verify.py --mode=mock      # Explicit offline deterministic mock run
  python verify.py --strict         # Enforce strict length and citation thresholds
  python verify.py --queries=all    # Run 3 standard queries + edge query
  python verify.py --json           # Machine-readable output to stdout
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["mock", "live"],
        default="mock",
        help="Retrieval execution mode (default: mock for deterministic offline execution)",
    )
    parser.add_argument(
        "--queries",
        "--query-set",
        dest="query_set",
        default="acceptance",
        help="Query set to execute: 'acceptance' (3 standard domains), 'all' (+ edge), or specific query id",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_ROOT / "test_reports"),
        help="Directory to save generated research briefs and verification reports (default: ./test_reports)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enforce strict invariant checks (all sources cited, elevated word counts)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary to stdout",
    )
    args = parser.parse_args()

    try:
        from research_synthesis.verification.runner import run_acceptance_verification
    except ImportError as e:
        print(f"[FATAL] Failed to import verification harness: {e}", file=sys.stderr)
        sys.exit(2)

    output_dir = Path(args.output_dir)
    manifest_path = PROJECT_ROOT / "tests" / "fixtures" / "mock_corpus" / "manifest.json"

    if not args.json:
        print("================================================================================")
        print(" Autonomous Web Research System - Acceptance Verification Harness (R4)")
        print("================================================================================")
        print(f" Mode:       {args.mode.upper()}")
        print(f" Query Set:  {args.query_set}")
        print(f" Strict:     {args.strict}")
        print(f" Reports:    {output_dir}")
        print(f" Manifest:   {manifest_path}")
        print("--------------------------------------------------------------------------------")

    success, report = run_acceptance_verification(
        mode=args.mode,
        query_set=args.query_set,
        output_dir=output_dir,
        strict=args.strict,
        corpus_manifest=manifest_path,
    )

    if args.json:
        print(json.dumps(report, indent=2))
        sys.exit(0 if success else 1)

    print("\nTest Execution Results:")
    for qr in report.get("query_results", []):
        qid = qr.get("query_id")
        status = "[PASS]" if qr.get("passed") else "[FAIL]"
        elapsed = qr.get("elapsed_sec", 0.0)
        topic = qr.get("topic", "")
        print(f"  {status} {qid:<25} ({elapsed}s) - {topic[:60]}...")

        if not qr.get("passed"):
            if qr.get("error"):
                print(f"         Error: {qr.get('error')}")
            val = qr.get("validation")
            if val and val.get("errors"):
                for err in val.get("errors", [])[:5]:
                    print(f"         Assertion Failure: {err}")
                if len(val.get("errors", [])) > 5:
                    print(f"         ... and {len(val.get('errors')) - 5} more errors")

    print("--------------------------------------------------------------------------------")
    print(f"Total: {report.get('total_queries')} | Passed: {report.get('passed_queries')} | Failed: {report.get('failed_queries')} | Elapsed: {report.get('total_elapsed_sec')}s")
    print("================================================================================")

    if success:
        print(" [PASS] AUTOMATED VERIFICATION PASSED: ALL ACCEPTANCE ASSERTIONS MET")
        print("================================================================================")
        sys.exit(0)
    else:
        print(" [FAIL] AUTOMATED VERIFICATION FAILED: ONE OR MORE ASSERTIONS FAILED")
        print("================================================================================")
        sys.exit(1)


if __name__ == "__main__":
    main()
