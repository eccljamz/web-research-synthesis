"""Data models and schema contracts for Research Synthesis.

Pure Python Standard Library (3.10+) - Zero External Dependencies.
Defines contracts across Retrieval (M1), Extraction (M2), Synthesis (M3),
and Verification (M-TEST).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse


# ============================================================================
# Tier 1: Query Decomposition & Web Retrieval Models (Milestone 1)
# ============================================================================

@dataclass
class SubQuery:
    """Represents a decomposed research facet and search query."""
    id: str                                  # e.g. "sq-01"
    original_topic: str                      # User's broad research query
    facet: str                               # e.g. "technical", "economic", "challenges", "comparative", "temporal"
    search_query: str                        # Optimized query string for search engine
    priority: int = 1                        # Priority rank (1 = highest)
    rationale: str = ""                      # Why this sub-query was generated

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SubQuery:
        return cls(**data)


@dataclass
class DecompositionResult:
    """Container for the output of query decomposition."""
    topic: str
    sub_queries: List[SubQuery]
    strategy_used: str = "heuristic_rule_based"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "sub_queries": [sq.to_dict() for sq in self.sub_queries],
            "strategy_used": self.strategy_used,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DecompositionResult:
        sub_queries = [
            sq if isinstance(sq, SubQuery) else SubQuery.from_dict(sq)
            for sq in data.get("sub_queries", [])
        ]
        return cls(
            topic=data["topic"],
            sub_queries=sub_queries,
            strategy_used=data.get("strategy_used", "heuristic_rule_based"),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
        )


@dataclass
class DocumentMetadata:
    """Metadata extracted from a web source document."""
    url: str
    canonical_url: str
    domain: str
    title: str
    author: Optional[str] = None
    published_date: Optional[str] = None
    content_type: str = "text/html"
    status_code: int = 200
    fetched_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    word_count: int = 0
    character_count: int = 0

    @property
    def doc_id(self) -> str:
        """Deterministic 16-character SHA-256 hash prefix of canonical URL."""
        import hashlib
        return hashlib.sha256(self.canonical_url.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["doc_id"] = self.doc_id
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DocumentMetadata:
        """Safely deserialize DocumentMetadata, ignoring doc_id property or extra keys."""
        known_keys = {
            "url", "canonical_url", "domain", "title", "author",
            "published_date", "content_type", "status_code",
            "fetched_at", "word_count", "character_count"
        }
        filtered = {k: v for k, v in data.items() if k in known_keys}
        if "canonical_url" not in filtered and "url" in filtered:
            filtered["canonical_url"] = filtered["url"]
        if "domain" not in filtered and "url" in filtered:
            filtered["domain"] = urlparse(filtered["url"]).netloc.lower()
        if "title" not in filtered:
            filtered["title"] = ""
        return cls(**filtered)


@dataclass
class RawWebDocument:
    """Raw unparsed web document response from retrieval client."""
    url: str
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    raw_html: str = ""
    subquery_id: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RawWebDocument:
        return cls(
            url=data["url"],
            status_code=data["status_code"],
            headers=data.get("headers", {}),
            raw_html=data.get("raw_html", ""),
            subquery_id=data.get("subquery_id"),
            error=data.get("error"),
        )


@dataclass
class CleanArticle:
    """Clean, boilerplate-stripped article ready for content filtering and extraction."""
    doc_id: str                              # SHA-256 hash prefix of canonical URL
    url: str
    metadata: DocumentMetadata
    cleaned_text: str                        # Continuous cleaned text
    paragraphs: List[str] = field(default_factory=list) # Discrete paragraphs
    headings: List[str] = field(default_factory=list)   # Document headings
    subquery_id: Optional[str] = None
    subquery_facet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "url": self.url,
            "metadata": self.metadata.to_dict() if hasattr(self.metadata, "to_dict") else asdict(self.metadata),
            "cleaned_text": self.cleaned_text,
            "paragraphs": self.paragraphs,
            "headings": self.headings,
            "subquery_id": self.subquery_id,
            "subquery_facet": self.subquery_facet,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CleanArticle:
        meta_data = data["metadata"]
        meta = meta_data if isinstance(meta_data, DocumentMetadata) else DocumentMetadata.from_dict(meta_data)
        return cls(
            doc_id=data["doc_id"],
            url=data["url"],
            metadata=meta,
            cleaned_text=data["cleaned_text"],
            paragraphs=data.get("paragraphs", []),
            headings=data.get("headings", []),
            subquery_id=data.get("subquery_id"),
            subquery_facet=data.get("subquery_facet"),
        )


@dataclass
class RetrievalBatch:
    """Unified container for an end-to-end R1 retrieval run."""
    topic: str
    sub_queries: List[SubQuery]
    documents: List[CleanArticle]
    failed_urls: List[Dict[str, str]] = field(default_factory=list)
    total_fetched: int = 0
    total_cleaned: int = 0
    cache_hits: int = 0
    execution_time_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "sub_queries": [sq.to_dict() for sq in self.sub_queries],
            "documents": [doc.to_dict() for doc in self.documents],
            "failed_urls": self.failed_urls,
            "total_fetched": self.total_fetched,
            "total_cleaned": self.total_cleaned,
            "cache_hits": self.cache_hits,
            "execution_time_seconds": self.execution_time_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RetrievalBatch:
        """Deserialize RetrievalBatch from dictionary, handling nested SubQuery and CleanArticle objects."""
        raw_sqs = data.get("sub_queries", [])
        sub_queries = [
            sq if isinstance(sq, SubQuery) else SubQuery.from_dict(sq)
            for sq in raw_sqs
        ]
        raw_docs = data.get("documents", [])
        documents = [
            doc if isinstance(doc, CleanArticle) else CleanArticle.from_dict(doc)
            for doc in raw_docs
        ]
        return cls(
            topic=data.get("topic", ""),
            sub_queries=sub_queries,
            documents=documents,
            failed_urls=data.get("failed_urls", []),
            total_fetched=int(data.get("total_fetched", len(documents))),
            total_cleaned=int(data.get("total_cleaned", len(documents))),
            cache_hits=int(data.get("cache_hits", 0)),
            execution_time_seconds=float(data.get("execution_time_seconds", 0.0)),
        )


# ============================================================================
# Tier 2: Content Filtering & Claim Extraction Models (Milestone 2)
# ============================================================================

@dataclass
class ScoredPassage:
    """Represents a passage chunk evaluated for relevance."""
    passage_id: str
    doc_id: str
    url: str
    title: str
    text: str
    relevance_score: float
    subquery: str
    word_count: int
    secondary_urls: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScoredPassage:
        """Deserialize ScoredPassage from dictionary with defensive type coercion."""
        text = data.get("text", "")
        word_count = data.get("word_count")
        if word_count is None:
            word_count = len(text.split()) if text else 0
        return cls(
            passage_id=data["passage_id"],
            doc_id=data["doc_id"],
            url=data["url"],
            title=data.get("title", ""),
            text=text,
            relevance_score=float(data.get("relevance_score", 0.0)),
            subquery=data.get("subquery", ""),
            word_count=int(word_count),
            secondary_urls=data.get("secondary_urls", []),
        )


class ClaimType(str, Enum):
    """Taxonomy of factual claims extracted from sources."""
    QUANTITATIVE = "QUANTITATIVE"
    TEMPORAL_EVENT = "TEMPORAL_EVENT"
    RELATIONAL = "RELATIONAL"
    GENERAL_FACT = "GENERAL_FACT"


@dataclass
class ExtractedClaim:
    """Represents a discrete, atomic factual proposition with full provenance."""
    claim_id: str                            # Unique deterministic claim hash
    text: str                                # Atomic proposition statement
    source_doc_id: str                       # Links to CleanArticle.doc_id
    source_url: str                          # Canonical source URL
    source_title: str                        # Document title
    passage_snippet: str                     # Surrounding context
    confidence_score: float                  # [0.0, 1.0]
    claim_type: ClaimType
    entities: List[str] = field(default_factory=list)
    secondary_urls: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["claim_type"] = self.claim_type.value if hasattr(self.claim_type, "value") else str(self.claim_type)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExtractedClaim:
        c_type = data.get("claim_type", ClaimType.GENERAL_FACT)
        if isinstance(c_type, str):
            try:
                c_type = ClaimType(c_type)
            except ValueError:
                c_type = ClaimType.GENERAL_FACT
        return cls(
            claim_id=data["claim_id"],
            text=data["text"],
            source_doc_id=data["source_doc_id"],
            source_url=data["source_url"],
            source_title=data["source_title"],
            passage_snippet=data.get("passage_snippet", ""),
            confidence_score=float(data.get("confidence_score", 1.0)),
            claim_type=c_type,
            entities=data.get("entities", []),
            secondary_urls=data.get("secondary_urls", []),
        )


# ============================================================================
# Tier 3: Structured Knowledge Synthesis Models (Milestone 3)
# ============================================================================

@dataclass
class SourceCitation:
    """Represents a formal bibliography reference with attribution."""
    citation_index: int                      # 1-based index matching [1], [2] in prose
    source_id: str                           # e.g., "SRC-01"
    title: str
    url: str
    author: Optional[str] = None
    publish_date: Optional[str] = None
    retrieved_at: Optional[str] = None
    snippet: str = ""
    attributed_claim_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if "published_date" not in d and d.get("publish_date"):
            d["published_date"] = d["publish_date"]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SourceCitation:
        p_date = data.get("publish_date") or data.get("published_date")
        return cls(
            citation_index=int(data.get("citation_index", 1)),
            source_id=data.get("source_id", "SRC-01"),
            title=data.get("title", ""),
            url=data.get("url", ""),
            author=data.get("author"),
            publish_date=p_date,
            retrieved_at=data.get("retrieved_at"),
            snippet=data.get("snippet", ""),
            attributed_claim_ids=data.get("attributed_claim_ids", []),
        )


@dataclass
class KeyTakeaway:
    """Actionable insight bullet with source citations."""
    text: str
    citation_indices: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> KeyTakeaway:
        if isinstance(data, str):
            return cls(text=data, citation_indices=[])
        if isinstance(data, dict):
            return cls(
                text=data.get("text", ""),
                citation_indices=data.get("citation_indices", []),
            )
        return cls(text=str(data))


@dataclass
class ThematicSection:
    """Thematic chapter in the research brief."""
    section_id: str
    title: str
    narrative: str                           # Markdown text containing inline citations [1], [2]
    citation_indices: List[int] = field(default_factory=list)
    claim_ids: List[str] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    content: Optional[str] = None

    def __post_init__(self):
        if not self.content and self.narrative:
            self.content = self.narrative
        elif not self.narrative and self.content:
            self.narrative = self.content

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "narrative": self.narrative,
            "content": self.content or self.narrative,
            "citation_indices": self.citation_indices,
            "claim_ids": self.claim_ids,
            "key_findings": self.key_findings,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ThematicSection:
        narrative = data.get("narrative") or data.get("content", "")
        return cls(
            section_id=data["section_id"],
            title=data["title"],
            narrative=narrative,
            citation_indices=data.get("citation_indices", []),
            claim_ids=data.get("claim_ids", []),
            key_findings=data.get("key_findings", []),
            content=data.get("content", narrative),
        )


@dataclass
class BriefMetadata:
    """Audit and operational metadata for a synthesized brief."""
    query: str = ""
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    synthesis_mode: str = "deterministic_extractive"
    total_sources_scanned: int = 1
    relevant_passages_count: int = 0
    total_claims_extracted: int = 0
    extracted_claims_count: int = 0
    execution_time_seconds: float = 0.0
    retrieval_mode: str = "mock"
    processing_time_ms: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.total_claims_extracted == 0 and self.extracted_claims_count > 0:
            self.total_claims_extracted = self.extracted_claims_count
        elif self.extracted_claims_count == 0 and self.total_claims_extracted > 0:
            self.extracted_claims_count = self.total_claims_extracted

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        extra_items = res.pop("extra", {})
        if extra_items:
            res.update(extra_items)
        if "total_claims_extracted" not in res:
            res["total_claims_extracted"] = self.total_claims_extracted
        if "extracted_claims_count" not in res:
            res["extracted_claims_count"] = res["total_claims_extracted"]
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BriefMetadata:
        data_copy = dict(data)
        claims = data_copy.get("total_claims_extracted", data_copy.get("extracted_claims_count", 0))
        known_keys = {
            "query", "generated_at", "synthesis_mode", "total_sources_scanned",
            "relevant_passages_count", "total_claims_extracted", "extracted_claims_count",
            "execution_time_seconds", "retrieval_mode", "processing_time_ms"
        }
        known_args = {k: v for k, v in data_copy.items() if k in known_keys}
        known_args.setdefault("total_claims_extracted", claims)
        known_args.setdefault("extracted_claims_count", claims)
        extra_args = {k: v for k, v in data_copy.items() if k not in known_keys}
        return cls(**known_args, extra=extra_args)


@dataclass
class ResearchBrief:
    """Complete, structured, citation-backed research brief adhering to schema contracts."""
    brief_id: str
    topic: str
    executive_summary: str                   # Prose embedding inline [N] citations
    key_takeaways: List[KeyTakeaway]         # Bullet points with citation indices
    thematic_sections: List[ThematicSection] # Thematic chapters
    sources: List[SourceCitation]            # Bibliography table
    metadata: Union[Dict[str, Any], BriefMetadata] = field(default_factory=dict)
    sub_queries: List[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def query(self) -> str:
        """Alias for topic."""
        return self.topic

    @property
    def sections(self) -> List[ThematicSection]:
        """Alias for thematic_sections."""
        return self.thematic_sections

    def to_dict(self) -> Dict[str, Any]:
        """Serialize research brief to dictionary with compatibility aliases."""
        serialized_takeaways = [
            kt.to_dict() if hasattr(kt, "to_dict") else asdict(kt)
            for kt in self.key_takeaways
        ]
        serialized_sections = [
            sec.to_dict() if hasattr(sec, "to_dict") else asdict(sec)
            for sec in self.thematic_sections
        ]
        serialized_sources = [
            src.to_dict() if hasattr(src, "to_dict") else asdict(src)
            for src in self.sources
        ]

        # Handle metadata polymorphically whether BriefMetadata, dict, or other dataclass
        if hasattr(self.metadata, "to_dict"):
            meta = self.metadata.to_dict()
        elif is_dataclass(self.metadata) and not isinstance(self.metadata, type):
            meta = asdict(self.metadata)
        elif isinstance(self.metadata, dict):
            meta = dict(self.metadata)
        elif self.metadata is None:
            meta = {}
        else:
            try:
                meta = dict(self.metadata)
            except (TypeError, ValueError):
                meta = {}

        if "query" not in meta:
            meta["query"] = self.topic
        if "generated_at" not in meta:
            meta["generated_at"] = self.generated_at
        if "retrieval_mode" not in meta:
            meta["retrieval_mode"] = "mock"
        if "total_sources_scanned" not in meta or meta["total_sources_scanned"] < 1:
            meta["total_sources_scanned"] = max(1, len(self.sources))
        if "total_claims_extracted" not in meta:
            meta["total_claims_extracted"] = meta.get("extracted_claims_count", 0)
        if "extracted_claims_count" not in meta:
            meta["extracted_claims_count"] = meta["total_claims_extracted"]

        return {
            "brief_id": self.brief_id,
            "topic": self.topic,
            "query": self.topic,
            "generated_at": self.generated_at,
            "sub_queries": self.sub_queries,
            "executive_summary": self.executive_summary,
            "key_takeaways": serialized_takeaways,
            "thematic_sections": serialized_sections,
            "sections": serialized_sections,
            "sources": serialized_sources,
            "metadata": meta,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert brief to pretty JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Render brief as clean, professional Markdown."""
        lines: List[str] = []
        lines.append(f"# Research Brief: {self.topic}")
        lines.append(f"**Brief ID**: `{self.brief_id}` | **Generated**: {self.generated_at}\n")
        lines.append("## Executive Summary\n")
        lines.append(self.executive_summary.strip() + "\n")

        if self.key_takeaways:
            lines.append("## Key Takeaways\n")
            for kt in self.key_takeaways:
                cites = f" [{', '.join(str(c) for c in kt.citation_indices)}]" if kt.citation_indices else ""
                lines.append(f"- {kt.text}{cites}")
            lines.append("")

        if self.thematic_sections:
            for sec in self.thematic_sections:
                lines.append(f"### {sec.title}\n")
                lines.append(sec.narrative.strip() + "\n")
                if sec.key_findings:
                    lines.append("**Key Findings**:")
                    for finding in sec.key_findings:
                        lines.append(f"- {finding}")
                    lines.append("")

        if self.sources:
            lines.append("## Sources & Citations\n")
            for src in self.sources:
                author_str = f" by {src.author}" if src.author else ""
                date_str = f" ({src.publish_date})" if src.publish_date else ""
                lines.append(f"[{src.citation_index}] **{src.title}**{author_str}{date_str}")
                lines.append(f"    *URL*: {src.url}")
                if src.snippet:
                    lines.append(f"    *Context*: \"{src.snippet}\"")
                lines.append("")

        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ResearchBrief:
        """Deserialize research brief from dictionary."""
        topic = data.get("topic") or data.get("query", "")
        raw_takeaways = data.get("key_takeaways", [])
        key_takeaways = [
            kt if isinstance(kt, KeyTakeaway) else KeyTakeaway.from_dict(kt)
            for kt in raw_takeaways
        ]

        raw_sections = data.get("thematic_sections") or data.get("sections", [])
        sections = [
            sec if isinstance(sec, ThematicSection) else ThematicSection.from_dict(sec)
            for sec in raw_sections
        ]

        raw_sources = data.get("sources", [])
        sources = [
            src if isinstance(src, SourceCitation) else SourceCitation.from_dict(src)
            for src in raw_sources
        ]

        return cls(
            brief_id=data["brief_id"],
            topic=topic,
            executive_summary=data.get("executive_summary", ""),
            key_takeaways=key_takeaways,
            thematic_sections=sections,
            sources=sources,
            metadata=data.get("metadata", {}),
            sub_queries=data.get("sub_queries", []),
            generated_at=data.get("generated_at", datetime.utcnow().isoformat()),
        )
