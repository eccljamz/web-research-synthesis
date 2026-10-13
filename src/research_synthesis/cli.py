"""Interactive Command-Line Interface (CLI) and REPL for Autonomous Research Synthesis.

Pure Python Standard Library (3.10+) - Zero External Dependencies.
Supports single-shot topic execution, interactive continuous REPL mode,
real-time pipeline stage progress reporting, and multi-format exports.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from research_synthesis.models import ResearchBrief
    from research_synthesis.pipeline import ResearchPipeline
except ImportError:
    from src.research_synthesis.models import ResearchBrief
    from src.research_synthesis.pipeline import ResearchPipeline


# ANSI Color Codes for enhanced terminal UX (gracefully degrades on basic terminals)
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

# Reconfigure stdout/stderr encoding for UTF-8 safety on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Disable ANSI if NO_COLOR environment variable is set or running in non-tty
if os.environ.get("NO_COLOR") or not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
    CYAN = GREEN = YELLOW = BOLD = DIM = RESET = ""


def print_banner() -> None:
    print(f"\n{CYAN}{BOLD}================================================================================")
    print(" [*] AUTONOMOUS WEB RESEARCH & KNOWLEDGE SYNTHESIS ENGINE")
    print(f"================================================================================{RESET}")


def slugify(text: str) -> str:
    """Generate a clean filesystem slug from a topic string."""
    clean = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    slug = re.sub(r"[\s-]+", "_", clean)
    return slug[:50] or "research_brief"


def run_single_research(
    topic: str,
    mode: str = "live",
    output_dir: str = "output",
    export_format: str = "both",
    use_cache: bool = True,
    strict_check: bool = False,
    quiet: bool = False,
) -> Optional[ResearchBrief]:
    """Execute end-to-end research synthesis with terminal progress reporting."""
    if not quiet:
        print(f"\n{BOLD}Research Topic:{RESET} {topic}")
        print(f"{DIM}Execution Mode:{RESET} {mode.upper()} | {DIM}Cache:{RESET} {'Enabled' if use_cache else 'Disabled'}")
        print(f"{DIM}--------------------------------------------------------------------------------{RESET}")

    start_time = time.time()
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    try:
        if not quiet:
            print(f"{YELLOW}[1/6]{RESET} [*] Decomposing query into orthogonal research facets...")

        pipeline = ResearchPipeline(mode=mode, use_cache=use_cache)

        if not quiet:
            print(f"{YELLOW}[2/6]{RESET} [*] Retrieving candidate web sources & literature...")
            print(f"{YELLOW}[3/6]{RESET} [*] Parsing HTML boilerplate & chunking passages...")
            print(f"{YELLOW}[4/6]{RESET} [*] BM25 relevance scoring & SimHash deduplication...")
            print(f"{YELLOW}[5/6]{RESET} [*] Extracting factual & quantitative claims with attribution...")
            print(f"{YELLOW}[6/6]{RESET} [*] Thematic clustering & structured brief synthesis...")

        brief = pipeline.run(topic)
        elapsed = time.time() - start_time

        slug = slugify(topic)
        md_file = out_path / f"{slug}.md"
        json_file = out_path / f"{slug}.json"
        html_file = out_path / f"{slug}.html"
        obsidian_note_file = out_path / f"{slug}_obsidian.md"
        obsidian_vault_dir = out_path / f"{slug}_vault"

        # Export requested formats
        if export_format in ("markdown", "both", "all"):
            md_file.write_text(brief.to_markdown(), encoding="utf-8")

        if export_format in ("json", "both", "all"):
            json_file.write_text(brief.to_json(indent=2), encoding="utf-8")

        if export_format in ("html", "both", "all"):
            html_file.write_text(brief.to_html(), encoding="utf-8")

        if export_format in ("obsidian", "all"):
            obsidian_note_file.write_text(brief.to_obsidian(), encoding="utf-8")
            brief.export_obsidian_vault(obsidian_vault_dir)

        if not quiet:
            print(f"\n{GREEN}{BOLD}[DONE] SYNTHESIS COMPLETE ({elapsed:.2f}s){RESET}")
            print(f"{CYAN}{BOLD}Brief Topic:{RESET} {brief.topic}")
            print(f"{DIM}Brief ID:{RESET} {brief.brief_id} | {DIM}Sections:{RESET} {len(brief.thematic_sections)} | {DIM}Sources:{RESET} {len(brief.sources)}")
            
            print(f"\n{BOLD}Executive Summary:{RESET}")
            summary_preview = brief.executive_summary.split("\n")[0]
            print(f"{summary_preview[:280]}...")

            print(f"\n{BOLD}Key Takeaways:{RESET}")
            for idx, kt in enumerate(brief.key_takeaways[:3], 1):
                kt_text = getattr(kt, "text", str(kt))
                clean_kt = re.sub(r"\s*\[\d+\]", "", kt_text).strip()
                print(f"  {idx}. {clean_kt[:140]}...")

            print(f"\n{BOLD}Exported Artifacts:{RESET}")
            if export_format in ("markdown", "both", "all"):
                print(f"  - Markdown:       {md_file.resolve()}")
            if export_format in ("json", "both", "all"):
                print(f"  - JSON:           {json_file.resolve()}")
            if export_format in ("html", "both", "all"):
                print(f"  - HTML:           {html_file.resolve()}")
            if export_format in ("obsidian", "all"):
                print(f"  - Obsidian Note:  {obsidian_note_file.resolve()}")
                print(f"  - Obsidian Vault: {obsidian_vault_dir.resolve()}")
            print(f"{CYAN}================================================================================{RESET}")

        return brief

    except Exception as err:
        print(f"\n\033[91m[ERROR] Research synthesis failed: {err}{RESET}", file=sys.stderr)
        return None


def repl_mode(
    mode: str = "live",
    output_dir: str = "output",
    export_format: str = "both",
    use_cache: bool = True,
) -> None:
    """Interactive Continuous REPL loop."""
    print_banner()
    print("Welcome to the interactive research session. Enter any topic to begin research.")
    print("Type 'exit', 'quit', or press Ctrl+C to terminate.")
    print(f"Current Output Directory: {Path(output_dir).resolve()}\n")

    while True:
        try:
            topic = input(f"{BOLD}research> {RESET}").strip()
            if not topic:
                continue
            if topic.lower() in ("exit", "quit", "q"):
                print("Exiting research session. Goodbye!")
                break
            if topic.lower() == "help":
                print("Enter any scientific, economic, or historical research topic.")
                print("Commands: 'exit' to quit, 'clear' to clear screen.")
                continue
            if topic.lower() == "clear":
                os.system("cls" if os.name == "nt" else "clear")
                print_banner()
                continue

            run_single_research(
                topic=topic,
                mode=mode,
                output_dir=output_dir,
                export_format=export_format,
                use_cache=use_cache,
            )
            print()
        except (KeyboardInterrupt, EOFError):
            print("\nSession interrupted. Exiting.")
            break


def main() -> None:
    """CLI Entrypoint parser."""
    parser = argparse.ArgumentParser(
        prog="research-synthesis",
        description="Autonomous Web Research & Knowledge Synthesis CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m research_synthesis.cli "Solid-State Battery Commercialization"
  python -m research_synthesis.cli --interactive
  python -m research_synthesis.cli "Supply Chain Reshoring" --mode=live --output-dir=./reports
        """,
    )
    parser.add_argument(
        "topic",
        nargs="?",
        default=None,
        help="Research topic query to analyze and synthesize into a brief",
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Launch interactive REPL mode for consecutive research tasks",
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["live", "mock"],
        default="live",
        help="Retrieval execution mode (default: live with failover)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="output",
        help="Directory to save generated Markdown and JSON reports (default: ./output)",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["markdown", "json", "html", "obsidian", "both", "all"],
        default="all",
        help="Output export format (default: all - markdown, json, html, obsidian)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable SQLite persistent document caching",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-essential progress output",
    )

    args = parser.parse_args()

    if args.interactive or args.topic is None:
        repl_mode(
            mode=args.mode,
            output_dir=args.output_dir,
            export_format=args.format,
            use_cache=not args.no_cache,
        )
    else:
        print_banner()
        brief = run_single_research(
            topic=args.topic,
            mode=args.mode,
            output_dir=args.output_dir,
            export_format=args.format,
            use_cache=not args.no_cache,
            quiet=args.quiet,
        )
        if brief is None:
            sys.exit(1)


if __name__ == "__main__":
    main()
