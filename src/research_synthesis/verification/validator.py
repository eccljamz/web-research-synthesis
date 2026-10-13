"""
validator.py - Schema and Semantic Invariant Validator for ResearchBrief objects.

Validates that research briefs conform to structural JSON schemas and adhere to
strict semantic invariant rules:
1. Referential Integrity: Every inline [N] citation and claim citation key resolves
   to an existing entry in the sources table.
2. Anti-Degeneracy & Substance: Executive summary >= 30 words, >= 3 key takeaways,
   >= 2 thematic sections, no placeholder or TODO text.
3. Provenance & Grounding: Every claim and section cites valid sources.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Banned placeholder keywords indicating unfinished or degenerate generation
BANNED_PLACEHOLDER_REGEX = re.compile(
    r"\b(TODO|FIXME|TBD|N/A|Lorem ipsum|Not found|placeholder text|asdf|insert here)\b",
    re.IGNORECASE,
)

# Citation extraction patterns in prose
# Matches [1], [2], [1, 2], [1-3], [SRC-01], [src-1], [^1], [^SRC-01]
PROSE_CITATION_REGEX = re.compile(
    r"\[\^?(?:SRC-)?(\d+)(?:-(?:SRC-)?(\d+))?\]|\[\^?([a-zA-Z0-9_-]+)\]",
    re.IGNORECASE,
)


@dataclass
class ValidationIssue:
    level: str  # "ERROR" or "WARNING"
    code: str  # e.g., "REFERENTIAL_INTEGRITY", "SCHEMA_VIOLATION", "PLACEHOLDER_TEXT"
    message: str
    field_path: Optional[str] = None


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, code: str, message: str, field_path: Optional[str] = None) -> None:
        self.is_valid = False
        formatted = f"[{code}] {message}" + (f" (at {field_path})" if field_path else "")
        self.errors.append(formatted)
        self.issues.append(ValidationIssue(level="ERROR", code=code, message=message, field_path=field_path))

    def add_warning(self, code: str, message: str, field_path: Optional[str] = None) -> None:
        formatted = f"[{code}] {message}" + (f" (at {field_path})" if field_path else "")
        self.warnings.append(formatted)
        self.issues.append(ValidationIssue(level="WARNING", code=code, message=message, field_path=field_path))

    def summary(self) -> str:
        status = "PASSED" if self.is_valid else "FAILED"
        lines = [
            f"Validation Status: {status}",
            f"Errors: {len(self.errors)}",
            f"Warnings: {len(self.warnings)}",
        ]
        if self.metrics:
            lines.append("Metrics:")
            for k, v in self.metrics.items():
                lines.append(f"  - {k}: {v}")
        if self.errors:
            lines.append("Errors:")
            for err in self.errors:
                lines.append(f"  * {err}")
        if self.warnings:
            lines.append("Warnings:")
            for warn in self.warnings:
                lines.append(f"  * {warn}")
        return "\n".join(lines)


class SchemaValidator:
    """Validates structural schema conformance of a ResearchBrief dictionary."""

    def __init__(self, schema_path: Optional[Union[str, Path]] = None):
        if schema_path is None:
            # Default to bundled tests/schemas/research_brief.schema.json
            schema_path = Path(__file__).resolve().parents[3] / "tests" / "schemas" / "research_brief.schema.json"
        self.schema_path = Path(schema_path)
        self._schema_data: Optional[Dict[str, Any]] = None

    @property
    def schema_data(self) -> Dict[str, Any]:
        if self._schema_data is None:
            if self.schema_path.exists():
                with open(self.schema_path, "r", encoding="utf-8") as f:
                    self._schema_data = json.load(f)
            else:
                self._schema_data = {}
        return self._schema_data

    def validate(self, brief: Dict[str, Any], result: ValidationResult) -> None:
        """Validates brief structure, preferring jsonschema if installed with pure-Python fallback."""
        # 1. Try external jsonschema if installed
        try:
            import jsonschema  # type: ignore

            if self.schema_data:
                validator = jsonschema.Draft7Validator(self.schema_data)
                errors = sorted(validator.iter_errors(brief), key=lambda e: e.path)
                for err in errors:
                    path_str = ".".join(str(p) for p in err.path) or "root"
                    result.add_error("SCHEMA_VIOLATION", err.message, path_str)
                return
        except ImportError:
            pass  # Fall through to pure-Python validation

        # 2. Pure-Python structural validation
        self._validate_pure_python(brief, result)

    def _validate_pure_python(self, brief: Dict[str, Any], result: ValidationResult) -> None:
        if not isinstance(brief, dict):
            result.add_error("SCHEMA_VIOLATION", f"Brief must be a dictionary, got {type(brief).__name__}", "root")
            return

        required_keys = [
            "brief_id",
            "topic",
            "generated_at",
            "sub_queries",
            "executive_summary",
            "thematic_sections",
            "key_takeaways",
            "sources",
            "metadata",
        ]
        for key in required_keys:
            if key not in brief or brief[key] is None:
                result.add_error("SCHEMA_MISSING_FIELD", f"Missing required field: '{key}'", key)

        if "brief_id" in brief and not isinstance(brief["brief_id"], str):
            result.add_error("SCHEMA_TYPE_ERROR", "Field 'brief_id' must be a string", "brief_id")

        if "topic" in brief:
            if not isinstance(brief["topic"], str) or len(brief["topic"].strip()) < 5:
                result.add_error("SCHEMA_VALUE_ERROR", "Field 'topic' must be a string with length >= 5", "topic")

        if "sub_queries" in brief:
            sq = brief["sub_queries"]
            if not isinstance(sq, list) or len(sq) < 2:
                result.add_error("SCHEMA_VALUE_ERROR", "Field 'sub_queries' must be a list with >= 2 items", "sub_queries")

        if "executive_summary" in brief:
            if not isinstance(brief["executive_summary"], str):
                result.add_error("SCHEMA_TYPE_ERROR", "Field 'executive_summary' must be a string", "executive_summary")

        if "thematic_sections" in brief:
            sections = brief["thematic_sections"]
            if not isinstance(sections, list) or len(sections) < 2:
                result.add_error("SCHEMA_VALUE_ERROR", "Field 'thematic_sections' must be a list with >= 2 sections", "thematic_sections")
            else:
                for idx, sec in enumerate(sections):
                    sec_path = f"thematic_sections[{idx}]"
                    if not isinstance(sec, dict):
                        result.add_error("SCHEMA_TYPE_ERROR", "Section must be an object", sec_path)
                        continue
                    if "section_id" not in sec:
                        result.add_error("SCHEMA_MISSING_FIELD", "Section missing 'section_id'", f"{sec_path}.section_id")
                    if "title" not in sec:
                        result.add_error("SCHEMA_MISSING_FIELD", "Section missing 'title'", f"{sec_path}.title")
                    if "narrative" not in sec and "content" not in sec:
                        result.add_error("SCHEMA_MISSING_FIELD", "Section must contain 'narrative' or 'content'", sec_path)

        if "key_takeaways" in brief:
            kt = brief["key_takeaways"]
            if not isinstance(kt, list) or len(kt) < 3:
                result.add_error("SCHEMA_VALUE_ERROR", "Field 'key_takeaways' must contain >= 3 items", "key_takeaways")

        if "sources" in brief:
            srcs = brief["sources"]
            if not isinstance(srcs, list) or len(srcs) < 2:
                result.add_error("SCHEMA_VALUE_ERROR", "Field 'sources' must contain >= 2 items", "sources")
            else:
                for idx, src in enumerate(srcs):
                    src_path = f"sources[{idx}]"
                    if not isinstance(src, dict):
                        result.add_error("SCHEMA_TYPE_ERROR", "Source entry must be an object", src_path)
                        continue
                    for req_field in ["source_id", "url", "title", "snippet"]:
                        if req_field not in src or not src[req_field]:
                            result.add_error("SCHEMA_MISSING_FIELD", f"Source missing '{req_field}'", f"{src_path}.{req_field}")

        if "metadata" in brief:
            meta = brief["metadata"]
            if not isinstance(meta, dict):
                result.add_error("SCHEMA_TYPE_ERROR", "Field 'metadata' must be an object", "metadata")
            else:
                for req_meta in ["retrieval_mode", "total_sources_scanned", "total_claims_extracted"]:
                    if req_meta not in meta:
                        result.add_error("SCHEMA_MISSING_FIELD", f"Metadata missing '{req_meta}'", f"metadata.{req_meta}")


class SemanticValidator:
    """Enforces semantic invariant assertions on content substance and referential integrity."""

    def __init__(self, strict: bool = False):
        self.strict = strict

    def validate(self, brief: Dict[str, Any], result: ValidationResult) -> None:
        sources_map = self._build_sources_index(brief.get("sources", []), result)
        cited_keys: Set[str] = set()

        # 1. Validate Executive Summary
        exec_sum = brief.get("executive_summary", "")
        self._validate_text_field(
            text=exec_sum,
            field_name="executive_summary",
            min_words=30,
            result=result,
            sources_map=sources_map,
            cited_keys_acc=cited_keys,
        )

        # 2. Validate Thematic Sections
        sections = brief.get("thematic_sections", [])
        total_section_words = 0
        if isinstance(sections, list):
            for idx, sec in enumerate(sections):
                sec_path = f"thematic_sections[{idx}]"
                sec_text = sec.get("narrative") or sec.get("content") or ""
                words = self._validate_text_field(
                    text=sec_text,
                    field_name=f"{sec_path}.narrative",
                    min_words=20,
                    result=result,
                    sources_map=sources_map,
                    cited_keys_acc=cited_keys,
                )
                total_section_words += words

                # Check explicit citation_indices if present
                indices = sec.get("citation_indices", [])
                if isinstance(indices, list):
                    for c_idx in indices:
                        c_key = str(c_idx)
                        if not self._resolve_citation(c_key, sources_map):
                            result.add_error(
                                "REFERENTIAL_INTEGRITY",
                                f"Section {sec.get('section_id', idx)} lists citation index '{c_idx}' not present in sources",
                                f"{sec_path}.citation_indices",
                            )
                        else:
                            cited_keys.add(c_key)

                # Check claims if present
                claims = sec.get("claims", [])
                if isinstance(claims, list):
                    for c_i, claim in enumerate(claims):
                        claim_path = f"{sec_path}.claims[{c_i}]"
                        if isinstance(claim, dict):
                            c_text = claim.get("claim_text", "")
                            if len(c_text.strip().split()) < 3:
                                result.add_error(
                                    "EMPTY_CLAIM",
                                    f"Claim text too short ({len(c_text.strip().split())} words)",
                                    f"{claim_path}.claim_text",
                                )
                            self._check_placeholders(c_text, f"{claim_path}.claim_text", result)
                            keys = claim.get("citation_keys", [])
                            if not keys:
                                result.add_warning(
                                    "UNGROUNDED_CLAIM",
                                    f"Claim '{claim.get('claim_id', c_i)}' has no citation keys",
                                    claim_path,
                                )
                            else:
                                for ck in keys:
                                    ck_str = str(ck)
                                    if not self._resolve_citation(ck_str, sources_map):
                                        result.add_error(
                                            "REFERENTIAL_INTEGRITY",
                                            f"Claim '{claim.get('claim_id', c_i)}' references unknown source citation '{ck}'",
                                            claim_path,
                                        )
                                    else:
                                        cited_keys.add(ck_str)

        # 3. Validate Key Takeaways
        takeaways = brief.get("key_takeaways", [])
        if isinstance(takeaways, list):
            for idx, item in enumerate(takeaways):
                t_path = f"key_takeaways[{idx}]"
                if isinstance(item, str):
                    t_text = item
                elif isinstance(item, dict):
                    t_text = item.get("text", "")
                    indices = item.get("citation_indices", [])
                    if isinstance(indices, list):
                        for ci in indices:
                            ci_str = str(ci)
                            if not self._resolve_citation(ci_str, sources_map):
                                result.add_error(
                                    "REFERENTIAL_INTEGRITY",
                                    f"Takeaway [{idx}] references citation index '{ci}' not found in sources",
                                    f"{t_path}.citation_indices",
                                )
                            else:
                                cited_keys.add(ci_str)
                else:
                    t_text = ""

                self._validate_text_field(
                    text=t_text,
                    field_name=t_path,
                    min_words=5,
                    result=result,
                    sources_map=sources_map,
                    cited_keys_acc=cited_keys,
                )

        # 4. Validate Sources Integrity
        sources = brief.get("sources", [])
        if isinstance(sources, list):
            for idx, src in enumerate(sources):
                src_path = f"sources[{idx}]"
                if isinstance(src, dict):
                    url = src.get("url", "")
                    if not (url.startswith("http://") or url.startswith("https://")):
                        result.add_error(
                            "INVALID_SOURCE_URL",
                            f"Source URL '{url}' is invalid or missing protocol",
                            f"{src_path}.url",
                        )
                    snippet = src.get("snippet", "")
                    if len(snippet.strip().split()) < 5:
                        result.add_error(
                            "EMPTY_SOURCE_SNIPPET",
                            f"Source snippet too short ({len(snippet.strip().split())} words)",
                            f"{src_path}.snippet",
                        )
                    self._check_placeholders(snippet, f"{src_path}.snippet", result)

        # 5. Check Unreferenced Sources
        total_sources = len(sources) if isinstance(sources, list) else 0
        resolved_source_count = len({id(s_info) for s_info in sources_map.values() if s_info.get("cited")})
        if total_sources > 0 and resolved_source_count == 0:
            result.add_error(
                "REFERENTIAL_INTEGRITY",
                "None of the sources in the sources table are cited in the brief narrative or claims",
                "sources",
            )
        elif total_sources > 0 and resolved_source_count < total_sources:
            uncited_msg = f"{total_sources - resolved_source_count} sources are listed but not cited in text"
            if self.strict:
                result.add_error("UNCITED_SOURCES", uncited_msg, "sources")
            else:
                result.add_warning("UNCITED_SOURCES", uncited_msg, "sources")

        # 6. Overall Metrics
        exec_words = len(exec_sum.strip().split()) if isinstance(exec_sum, str) else 0
        total_words = exec_words + total_section_words
        result.metrics = {
            "executive_summary_words": exec_words,
            "thematic_sections_count": len(sections) if isinstance(sections, list) else 0,
            "thematic_sections_words": total_section_words,
            "total_brief_words": total_words,
            "key_takeaways_count": len(takeaways) if isinstance(takeaways, list) else 0,
            "sources_count": total_sources,
            "sources_cited_count": resolved_source_count,
            "distinct_citations_found": len(cited_keys),
        }

        # Global length check
        if total_words < 120:
            result.add_error(
                "BRIEF_TOO_BRIEF",
                f"Total brief substantive word count ({total_words} words) is below minimum threshold (120 words)",
                "root",
            )

    def _build_sources_index(self, sources: List[Dict[str, Any]], result: ValidationResult) -> Dict[str, Dict[str, Any]]:
        """Index sources by source_id, citation_index, and normalized aliases."""
        index: Dict[str, Dict[str, Any]] = {}
        if not isinstance(sources, list):
            return index

        seen_ids: Set[str] = set()
        for idx, src in enumerate(sources):
            if not isinstance(src, dict):
                continue
            src_id = str(src.get("source_id", "")).strip()
            if not src_id:
                continue

            if src_id in seen_ids:
                result.add_error("DUPLICATE_SOURCE_ID", f"Duplicate source_id: '{src_id}'", f"sources[{idx}]")
            seen_ids.add(src_id)

            record = {
                "source": src,
                "index": idx,
                "cited": False,
            }

            # Map primary ID
            index[src_id] = record
            index[src_id.lower()] = record

            # Map citation_index if present
            c_idx = src.get("citation_index")
            if c_idx is not None:
                index[str(c_idx)] = record
                index[f"[{c_idx}]"] = record

            # Map 1-based array offset
            index[str(idx + 1)] = record

            # Map regex variants: e.g. "SRC-01" -> "1", "SRC-1" -> "1", "1" -> "SRC-01"
            m = re.match(r"^SRC-0*(\d+)$", src_id, re.IGNORECASE)
            if m:
                num = m.group(1)
                index[num] = record
                index[f"SRC-{num}"] = record
                index[f"src-{num}"] = record
                index[f"SRC-{int(num):02d}"] = record

        return index

    def _resolve_citation(self, citation_key: str, sources_map: Dict[str, Dict[str, Any]]) -> bool:
        cleaned = citation_key.strip().strip("[]^#").strip()
        if cleaned in sources_map:
            sources_map[cleaned]["cited"] = True
            return True

        # Try numeric parse if cleaned is digits
        if cleaned.isdigit():
            c_num = str(int(cleaned))
            if c_num in sources_map:
                sources_map[c_num]["cited"] = True
                return True
            src_alias = f"SRC-{int(cleaned):02d}"
            if src_alias in sources_map:
                sources_map[src_alias]["cited"] = True
                return True

        # Try prefix stripping
        norm = re.sub(r"^SRC-0*", "", cleaned, flags=re.IGNORECASE)
        if norm in sources_map:
            sources_map[norm]["cited"] = True
            return True

        return False

    def _validate_text_field(
        self,
        text: str,
        field_name: str,
        min_words: int,
        result: ValidationResult,
        sources_map: Dict[str, Dict[str, Any]],
        cited_keys_acc: Set[str],
    ) -> int:
        if not isinstance(text, str):
            result.add_error("SCHEMA_TYPE_ERROR", f"Expected string for {field_name}", field_name)
            return 0

        # Check placeholders
        self._check_placeholders(text, field_name, result)

        # Word count
        words = len(text.strip().split())
        if words < min_words:
            result.add_error(
                "EMPTY_OR_TRUNCATED_TEXT",
                f"{field_name} word count ({words} words) is below requirement (>= {min_words} words)",
                field_name,
            )

        # Inline citation extraction and resolution
        for match in PROSE_CITATION_REGEX.finditer(text):
            num1, num2, key_str = match.groups()
            keys_to_test = []
            if num1 and num2:
                # Range like [1-3]
                try:
                    start_i, end_i = int(num1), int(num2)
                    for r_i in range(start_i, end_i + 1):
                        keys_to_test.append(str(r_i))
                except ValueError:
                    keys_to_test.append(num1)
            elif num1:
                keys_to_test.append(num1)
            elif key_str:
                keys_to_test.append(key_str)

            for k in keys_to_test:
                cited_keys_acc.add(k)
                if not self._resolve_citation(k, sources_map):
                    result.add_error(
                        "REFERENTIAL_INTEGRITY",
                        f"Prose in '{field_name}' references citation marker '[{k}]' which does not resolve to any source",
                        field_name,
                    )

        return words

    def _check_placeholders(self, text: str, field_name: str, result: ValidationResult) -> None:
        match = BANNED_PLACEHOLDER_REGEX.search(text)
        if match:
            result.add_error(
                "PLACEHOLDER_TEXT",
                f"Found prohibited placeholder text '{match.group(0)}' in {field_name}",
                field_name,
            )


class ResearchBriefValidator:
    """Master validator executing structural schema check followed by semantic invariants."""

    def __init__(
        self,
        schema_path: Optional[Union[str, Path]] = None,
        strict: bool = False,
    ):
        self.schema_validator = SchemaValidator(schema_path=schema_path)
        self.semantic_validator = SemanticValidator(strict=strict)
        self.strict = strict

    def validate(self, brief_input: Union[Dict[str, Any], str, Path]) -> ValidationResult:
        result = ValidationResult(is_valid=True)

        # Parse input
        brief_data: Dict[str, Any]
        if isinstance(brief_input, (str, Path)) and (str(brief_input).endswith(".json") or Path(brief_input).exists()):
            try:
                with open(brief_input, "r", encoding="utf-8") as f:
                    brief_data = json.load(f)
            except Exception as e:
                result.add_error("FILE_READ_ERROR", f"Failed to load JSON brief from '{brief_input}': {e}", "root")
                return result
        elif isinstance(brief_input, str):
            try:
                brief_data = json.loads(brief_input)
            except Exception as e:
                result.add_error("JSON_PARSE_ERROR", f"Failed to parse JSON string: {e}", "root")
                return result
        elif isinstance(brief_input, dict):
            brief_data = brief_input
        else:
            result.add_error(
                "INVALID_INPUT_TYPE",
                f"Unsupported brief input type: {type(brief_input).__name__}",
                "root",
            )
            return result

        # 1. Structural schema validation
        self.schema_validator.validate(brief_data, result)

        # 2. Semantic invariant validation
        self.semantic_validator.validate(brief_data, result)

        return result


def validate_brief(
    brief_data: Union[Dict[str, Any], str, Path],
    schema_path: Optional[Union[str, Path]] = None,
    strict: bool = False,
) -> ValidationResult:
    """Convenience helper function to validate a research brief."""
    validator = ResearchBriefValidator(schema_path=schema_path, strict=strict)
    return validator.validate(brief_data)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="ResearchBrief Schema and Semantic Validator CLI")
    parser.add_argument("--brief", "-b", required=True, help="Path to research brief JSON file")
    parser.add_argument("--schema", "-s", default=None, help="Path to formal JSON Schema file")
    parser.add_argument("--strict", action="store_true", help="Enforce strict invariant checks")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")
    args = parser.parse_args()

    result = validate_brief(Path(args.brief), schema_path=args.schema, strict=args.strict)

    if args.json:
        payload = {
            "is_valid": result.is_valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "metrics": result.metrics,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(result.summary())

    sys.exit(0 if result.is_valid else 1)


if __name__ == "__main__":
    main()
