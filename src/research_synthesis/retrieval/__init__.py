"""Query Decomposition and Web Retrieval Module (Milestone 1).

Exposes query decomposition engines, multi-mode retrieval clients,
and HTML/metadata parsers.
"""

try:
    from research_synthesis.retrieval.decomposer import (
        BaseQueryDecomposer,
        HeuristicQueryDecomposer,
    )
    from research_synthesis.retrieval.parser import (
        DocumentParser,
        RobustHTMLParser,
    )
    from research_synthesis.retrieval.retriever import (
        ArxivRetrievalClient,
        BaseRetrievalClient,
        CompositeRetrievalClient,
        DuckDuckGoLiteRetrievalClient,
        LiveHttpRetrievalClient,
        MockWebRetrievalClient,
        PubMedRetrievalClient,
        WikipediaRetrievalClient,
    )
    from research_synthesis.retrieval.cache import SQLiteDocumentCache
except ImportError:
    from src.research_synthesis.retrieval.decomposer import (
        BaseQueryDecomposer,
        HeuristicQueryDecomposer,
    )
    from src.research_synthesis.retrieval.parser import (
        DocumentParser,
        RobustHTMLParser,
    )
    from src.research_synthesis.retrieval.retriever import (
        ArxivRetrievalClient,
        BaseRetrievalClient,
        CompositeRetrievalClient,
        DuckDuckGoLiteRetrievalClient,
        LiveHttpRetrievalClient,
        MockWebRetrievalClient,
        PubMedRetrievalClient,
        WikipediaRetrievalClient,
    )
    from src.research_synthesis.retrieval.cache import SQLiteDocumentCache

__all__ = [
    "BaseQueryDecomposer",
    "HeuristicQueryDecomposer",
    "BaseRetrievalClient",
    "MockWebRetrievalClient",
    "LiveHttpRetrievalClient",
    "DuckDuckGoLiteRetrievalClient",
    "WikipediaRetrievalClient",
    "ArxivRetrievalClient",
    "PubMedRetrievalClient",
    "CompositeRetrievalClient",
    "RobustHTMLParser",
    "DocumentParser",
    "SQLiteDocumentCache",
]
