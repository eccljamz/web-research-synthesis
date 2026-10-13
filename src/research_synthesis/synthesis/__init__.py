"""Structured Knowledge Synthesis Subpackage.

Milestone 3 - Features F10, F11, F12, F13.
Pure Python Standard Library (3.10+) - Zero External Dependencies.
"""

from __future__ import annotations

try:
    from research_synthesis.synthesis.cluster import (
        ClaimCluster,
        CorroboratedClaimGroup,
        DiscrepancyGroup,
        ThematicClusterer,
    )
    from research_synthesis.synthesis.synthesizer import (
        CitationRegistry,
        ExtractiveSynthesizer,
    )
    from research_synthesis.synthesis.formatters import (
        JSONSchemaSerializer,
        MarkdownFormatter,
    )
except ImportError:
    try:
        from src.research_synthesis.synthesis.cluster import (
            ClaimCluster,
            CorroboratedClaimGroup,
            DiscrepancyGroup,
            ThematicClusterer,
        )
        from src.research_synthesis.synthesis.synthesizer import (
            CitationRegistry,
            ExtractiveSynthesizer,
        )
        from src.research_synthesis.synthesis.formatters import (
            JSONSchemaSerializer,
            MarkdownFormatter,
        )
    except ImportError:
        from .cluster import (
            ClaimCluster,
            CorroboratedClaimGroup,
            DiscrepancyGroup,
            ThematicClusterer,
        )
        from .synthesizer import (
            CitationRegistry,
            ExtractiveSynthesizer,
        )
        from .formatters import (
            JSONSchemaSerializer,
            MarkdownFormatter,
        )

# Backward-compatibility aliases
KnowledgeSynthesizer = ExtractiveSynthesizer
JsonFormatter = JSONSchemaSerializer

__all__ = [
    "ThematicClusterer",
    "ClaimCluster",
    "CorroboratedClaimGroup",
    "DiscrepancyGroup",
    "ExtractiveSynthesizer",
    "CitationRegistry",
    "MarkdownFormatter",
    "JSONSchemaSerializer",
    "KnowledgeSynthesizer",
    "JsonFormatter",
]
