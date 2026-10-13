"""Query Decomposition Engine.

Decomposes broad or complex research topics into targeted, orthogonal sub-queries
using linguistic entity pattern matching, comparative query analysis, and domain facets.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import List, Tuple

try:
    from research_synthesis.models import DecompositionResult, SubQuery
except ImportError:
    from src.research_synthesis.models import DecompositionResult, SubQuery


class BaseQueryDecomposer(ABC):
    """Abstract base class for query decomposition engines."""

    @abstractmethod
    def decompose(self, topic: str, max_subqueries: int = 5) -> DecompositionResult:
        """Decompose a research topic into structured sub-queries."""
        pass


class HeuristicQueryDecomposer(BaseQueryDecomposer):
    """Deterministic, zero-dependency decomposition engine.

    Leverages linguistic patterns, comparative detection (e.g., 'X vs Y'),
    and 5 orthogonal research facets (technical, economic, challenges,
    comparative, temporal).
    """

    # 5 Orthogonal Facets and Templates
    FACET_TEMPLATES: List[Tuple[str, str, str]] = [
        (
            "technical",
            "{topic} technical architecture mechanism fundamentals principles",
            "Examine core technical architecture, mechanisms, and fundamental operating principles",
        ),
        (
            "economic",
            "{topic} economic cost market feasibility commercialization industry",
            "Analyze cost drivers, commercial viability, market sizing, and industry adoption",
        ),
        (
            "challenges",
            "{topic} limitations challenges risks bottlenecks safety regulatory",
            "Identify critical technical hurdles, safety risks, bottlenecks, and regulatory constraints",
        ),
        (
            "comparative",
            "{topic} comparative analysis benchmarks alternatives state of the art",
            "Benchmark against alternative technologies, solutions, and existing standards",
        ),
        (
            "temporal",
            "{topic} recent developments state of the art trends 2024 2025 2026",
            "Track recent breakthroughs, contemporary industry trends, and near-term projections",
        ),
    ]

    # Comparative regex patterns
    COMPARATIVE_PATTERNS = [
        # Pattern 1: Queries beginning with comparative phrases
        re.compile(
            r"^(?:(?:a|the)\s+)?(?:comparison\s+between|comparison\s+of|trade-offs?\s+between|trade-offs?\s+of|differences?\s+between|differences?\s+of|compare)\s+(.+?)\s+(?:and|vs\.?|versus|to|with)\s+(.+)$",
            re.IGNORECASE,
        ),
        # Pattern 2: Standard infix comparisons
        re.compile(
            r"^(?:(?:a|the)\s+)?(?:comparison\s+of\s+|comparison\s+between\s+)?(.+?)\s+(?:vs\.?|versus|compared\s+to|compared\s+with|against)\s+(.+)$",
            re.IGNORECASE,
        ),
        # Pattern 3: Suffix comparisons
        re.compile(
            r"^(.+?)\s+and\s+(.+?)\s+(?:trade-offs?|differences?|comparison)$",
            re.IGNORECASE,
        ),
    ]

    # Conversational filler prefixes to strip
    FILLER_PREFIXES = [
        re.compile(r"^(?:can\s+you\s+(?:please\s+)?(?:explain|tell\s+me\s+about|research|investigate|explore|analyze))\s+", re.IGNORECASE),
        re.compile(r"^(?:what\s+(?:is|are)\s+(?:the\s+)?(?:state\s+of\s+|details\s+on\s+)?)\s*", re.IGNORECASE),
        re.compile(r"^(?:give\s+me\s+a\s+(?:detailed\s+)?(?:report|overview)\s+on)\s+", re.IGNORECASE),
        re.compile(r"^(?:i\s+want\s+to\s+know\s+about)\s+", re.IGNORECASE),
    ]

    def _sanitize_topic(self, topic: str) -> str:
        """Strip conversational filler, excess punctuation, and whitespace."""
        cleaned = topic.strip()
        for pattern in self.FILLER_PREFIXES:
            cleaned = pattern.sub("", cleaned).strip()
        # Remove trailing question mark or period
        cleaned = re.sub(r"[\.\?!]+$", "", cleaned).strip()
        return cleaned

    def _detect_comparative(self, topic: str) -> Tuple[bool, str, str]:
        """Detect if topic compares two entities."""
        for pattern in self.COMPARATIVE_PATTERNS:
            match = pattern.search(topic)
            if match:
                entity_a = match.group(1).strip()
                entity_b = match.group(2).strip()
                # Clean entities
                entity_a = re.sub(r"^(?:the\s+)", "", entity_a, flags=re.IGNORECASE).strip()
                entity_b = re.sub(r"^(?:the\s+)", "", entity_b, flags=re.IGNORECASE).strip()
                if entity_a and entity_b and len(entity_a) >= 2 and len(entity_b) >= 2:
                    return True, entity_a, entity_b
        return False, "", ""

    def decompose(self, topic: str, max_subqueries: int = 5) -> DecompositionResult:
        """Decompose a research topic into structured sub-queries.

        Args:
            topic: Broad or complex research topic.
            max_subqueries: Maximum number of sub-queries to generate (1-10).

        Returns:
            DecompositionResult containing the generated SubQuery objects.

        Raises:
            ValueError: If topic is empty or whitespace.
        """
        if not isinstance(topic, str):
            raise TypeError("Topic must be a string.")

        cleaned_topic = topic.strip()
        if not cleaned_topic:
            raise ValueError("Topic cannot be empty or whitespace.")

        sanitized_topic = self._sanitize_topic(cleaned_topic)
        if not sanitized_topic:
            sanitized_topic = cleaned_topic

        effective_max = max(1, min(max_subqueries, 10))
        sub_queries: List[SubQuery] = []

        is_comp, entity_a, entity_b = self._detect_comparative(sanitized_topic)

        if is_comp:
            # Generate comparative sub-queries covering both entities and head-to-head facets
            comp_specs = [
                (
                    "sq-01",
                    "technical",
                    f"{entity_a} technical overview architecture performance specifications",
                    1,
                    f"Investigate foundational architecture and capabilities of {entity_a}",
                ),
                (
                    "sq-02",
                    "technical",
                    f"{entity_b} technical overview architecture performance specifications",
                    1,
                    f"Investigate foundational architecture and capabilities of {entity_b}",
                ),
                (
                    "sq-03",
                    "comparative",
                    f"{entity_a} vs {entity_b} direct comparison metrics benchmarks trade-offs",
                    1,
                    f"Direct head-to-head performance and trade-off comparison between {entity_a} and {entity_b}",
                ),
                (
                    "sq-04",
                    "economic",
                    f"{entity_a} {entity_b} economic cost manufacturing scalability commercialization",
                    2,
                    f"Economic, manufacturing cost, and scalability comparison between {entity_a} and {entity_b}",
                ),
                (
                    "sq-05",
                    "challenges",
                    f"{entity_a} {entity_b} limitations bottlenecks future outlook 2025 2026",
                    2,
                    f"Unresolved technical challenges and future adoption outlook for {entity_a} and {entity_b}",
                ),
            ]

            for sq_id, facet, query_str, priority, rationale in comp_specs[:effective_max]:
                sub_queries.append(
                    SubQuery(
                        id=sq_id,
                        original_topic=cleaned_topic,
                        facet=facet,
                        search_query=query_str,
                        priority=priority,
                        rationale=rationale,
                    )
                )
        else:
            # Handle brief / single-word queries with expansion keywords
            words = sanitized_topic.split()
            base_query_phrase = sanitized_topic
            if len(words) == 1:
                base_query_phrase = f"{sanitized_topic} technology system"

            for idx, (facet, template, rationale) in enumerate(self.FACET_TEMPLATES[:effective_max], start=1):
                sq_id = f"sq-{idx:02d}"
                query_str = template.format(topic=base_query_phrase)
                sub_queries.append(
                    SubQuery(
                        id=sq_id,
                        original_topic=cleaned_topic,
                        facet=facet,
                        search_query=query_str,
                        priority=idx,
                        rationale=f"{rationale} for {sanitized_topic}",
                    )
                )

        return DecompositionResult(
            topic=cleaned_topic,
            sub_queries=sub_queries[:effective_max],
            strategy_used="heuristic_rule_based",
        )
