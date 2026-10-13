"""Query Decomposition and Web Retrieval Module (Milestone 1).

Exposes query decomposition engines, multi-mode retrieval clients,
and HTML/metadata parsers.
"""

from src.research_synthesis.retrieval.decomposer import (
    BaseQueryDecomposer,
    HeuristicQueryDecomposer,
)
from src.research_synthesis.retrieval.parser import (
    DocumentParser,
    RobustHTMLParser,
)
from src.research_synthesis.retrieval.retriever import (
    BaseRetrievalClient,
    CompositeRetrievalClient,
    LiveHttpRetrievalClient,
    MockWebRetrievalClient,
)

__all__ = [
    "BaseQueryDecomposer",
    "HeuristicQueryDecomposer",
    "BaseRetrievalClient",
    "MockWebRetrievalClient",
    "LiveHttpRetrievalClient",
    "CompositeRetrievalClient",
    "RobustHTMLParser",
    "DocumentParser",
]
