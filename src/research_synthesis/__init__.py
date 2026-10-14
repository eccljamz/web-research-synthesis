"""Autonomous Web Research and Knowledge Synthesis System.

Pure Python standard library implementation for web research decomposition,
retrieval, content filtering, claim extraction, and structured brief synthesis.
"""

from __future__ import annotations

import sys

if __name__ == "research_synthesis":
    sys.modules.setdefault("src.research_synthesis", sys.modules[__name__])
elif __name__ == "src.research_synthesis":
    sys.modules.setdefault("research_synthesis", sys.modules[__name__])

try:
    from research_synthesis.models import (
        BriefMetadata,
        ClaimCluster,
        ClaimType,
        CleanArticle,
        CorroboratedClaimGroup,
        DecompositionResult,
        DiscrepancyGroup,
        DocumentMetadata,
        ExtractedClaim,
        KeyTakeaway,
        RawWebDocument,
        ResearchBrief,
        RetrievalBatch,
        ScoredPassage,
        SourceCitation,
        SubQuery,
        ThematicSection,
    )
    from research_synthesis.pipeline import ResearchPipeline
    from research_synthesis.synthesis.formatters import (
        HTMLReportFormatter,
        JSONSchemaSerializer,
        MarkdownFormatter,
        ObsidianExporter,
    )
    from research_synthesis.synthesis.comparative import (
        ComparativeSynthesisEngine,
        ComparativeSynthesisResult,
        CrossBriefTradeoffRow,
        LongitudinalTracker,
        TemporalShiftIndicator,
    )
    from research_synthesis.retrieval.pdf_parser import (
        ExtractedPDFDocument,
        ZeroDepPDFExtractor,
    )
except ImportError:
    from src.research_synthesis.models import (
        BriefMetadata,
        ClaimCluster,
        ClaimType,
        CleanArticle,
        CorroboratedClaimGroup,
        DecompositionResult,
        DiscrepancyGroup,
        DocumentMetadata,
        ExtractedClaim,
        KeyTakeaway,
        RawWebDocument,
        ResearchBrief,
        RetrievalBatch,
        ScoredPassage,
        SourceCitation,
        SubQuery,
        ThematicSection,
    )
    from src.research_synthesis.pipeline import ResearchPipeline
    from src.research_synthesis.synthesis.formatters import (
        HTMLReportFormatter,
        JSONSchemaSerializer,
        MarkdownFormatter,
        ObsidianExporter,
    )
    from src.research_synthesis.synthesis.comparative import (
        ComparativeSynthesisEngine,
        ComparativeSynthesisResult,
        CrossBriefTradeoffRow,
        LongitudinalTracker,
        TemporalShiftIndicator,
    )
    from src.research_synthesis.retrieval.pdf_parser import (
        ExtractedPDFDocument,
        ZeroDepPDFExtractor,
    )

def run_server(*args, **kwargs):
    from .server import run_server as _run_server
    return _run_server(*args, **kwargs)

__version__ = "0.1.0"

__all__ = [
    "SubQuery",
    "DecompositionResult",
    "DocumentMetadata",
    "RawWebDocument",
    "CleanArticle",
    "RetrievalBatch",
    "ScoredPassage",
    "ClaimType",
    "ExtractedClaim",
    "CorroboratedClaimGroup",
    "DiscrepancyGroup",
    "ClaimCluster",
    "SourceCitation",
    "KeyTakeaway",
    "ThematicSection",
    "BriefMetadata",
    "ResearchBrief",
    "ResearchPipeline",
    "MarkdownFormatter",
    "JSONSchemaSerializer",
    "HTMLReportFormatter",
    "ObsidianExporter",
    "ComparativeSynthesisEngine",
    "ComparativeSynthesisResult",
    "CrossBriefTradeoffRow",
    "LongitudinalTracker",
    "TemporalShiftIndicator",
    "ZeroDepPDFExtractor",
    "ExtractedPDFDocument",
    "run_server",
]
