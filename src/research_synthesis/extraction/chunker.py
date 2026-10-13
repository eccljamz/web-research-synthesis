"""Passage-Level Chunking Module.

Milestone 2 - Feature F6.
Pure Python Standard Library (3.10+) - Zero External Dependencies.
Segments cleaned document texts (CleanArticle) into overlapping passages
(150-250 words) with 30-50 word overlap, respecting paragraph boundaries.
"""

from __future__ import annotations

import re
from typing import List, Optional, Union

try:
    from research_synthesis.models import CleanArticle, RetrievalBatch, ScoredPassage
except ImportError:
    try:
        from src.research_synthesis.models import CleanArticle, RetrievalBatch, ScoredPassage
    except ImportError:
        from ..models import CleanArticle, RetrievalBatch, ScoredPassage


class PassageChunker:
    """Paragraph-aware passage chunker for CleanArticle documents.

    Targets 150-250 words per passage with 30-50 word overlap.
    Preserves short documents (<150 words) as single chunks ({doc_id}-p000).
    Generates deterministic passage IDs: {doc_id}-p{idx:03d}.
    """

    SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")

    def __init__(
        self,
        min_words: int = 150,
        max_words: int = 250,
        overlap_words: int = 40,
    ) -> None:
        """Initialize chunker with configurable word boundary targets.

        Args:
            min_words: Minimum target words per passage (default: 150).
            max_words: Maximum target words per passage (default: 250).
            overlap_words: Target word overlap between consecutive passages (default: 40).
        """
        self.min_words = min_words
        self.max_words = max_words
        self.overlap_words = overlap_words

    @classmethod
    def _split_into_sentences(cls, text: str) -> List[str]:
        """Split text into sentences while protecting common abbreviations and decimals."""
        if not text or not text.strip():
            return []
        # Protect common abbreviations
        protected = re.sub(
            r"\b(e\.g\.|i\.e\.|et al\.|U\.S\.|Dr\.|Mr\.|Mrs\.|Ms\.|Prof\.|Inc\.|Corp\.|Ltd\.|vs\.)",
            lambda m: m.group(0).replace(".", "<DOT>"),
            text,
            flags=re.IGNORECASE,
        )
        # Protect decimal numbers (e.g. 12.0)
        protected = re.sub(r"(?<=\d)\.(?=\d)", "<DOT>", protected)
        raw_sentences = cls.SENTENCE_SPLIT_PATTERN.split(protected)
        cleaned = [s.replace("<DOT>", ".").strip() for s in raw_sentences if s.strip()]
        return cleaned if cleaned else [text.strip()]

    def _split_long_paragraph(self, paragraph: str) -> List[str]:
        """Break down paragraphs exceeding max_words into sentence-level blocks."""
        words = paragraph.split()
        if len(words) <= self.max_words:
            return [paragraph]

        sentences = self._split_into_sentences(paragraph)
        blocks: List[str] = []
        current_block: List[str] = []
        current_count = 0

        for sent in sentences:
            sent_count = len(sent.split())
            if current_count + sent_count > self.max_words and current_block:
                blocks.append(" ".join(current_block))
                current_block = [sent]
                current_count = sent_count
            else:
                current_block.append(sent)
                current_count += sent_count

        if current_block:
            blocks.append(" ".join(current_block))
        return blocks

    def chunk_article(self, article: CleanArticle) -> List[ScoredPassage]:
        """Segment a CleanArticle into a list of ScoredPassage instances.

        Args:
            article: The clean article to segment.

        Returns:
            List of ScoredPassage instances with deterministic IDs and metadata.
        """
        paragraphs = [p.strip() for p in article.paragraphs if p.strip()]
        if not paragraphs and article.cleaned_text and article.cleaned_text.strip():
            paragraphs = [p.strip() for p in article.cleaned_text.split("\n\n") if p.strip()]

        if not paragraphs or not any(re.search(r"\w", p) for p in paragraphs):
            return []

        total_words = sum(len(p.split()) for p in paragraphs)
        if total_words == 0:
            return []

        doc_url = (
            article.metadata.canonical_url
            if (article.metadata and getattr(article.metadata, "canonical_url", None))
            else article.url
        )
        doc_title = (
            article.metadata.title
            if (article.metadata and getattr(article.metadata, "title", None))
            else ""
        )
        subquery_ref = article.subquery_id or article.subquery_facet or ""

        # Short document rule: preserve as single chunk if < min_words
        if total_words < self.min_words:
            full_text = "\n\n".join(paragraphs)
            return [
                ScoredPassage(
                    passage_id=f"{article.doc_id}-p000",
                    doc_id=article.doc_id,
                    url=doc_url,
                    title=doc_title,
                    text=full_text,
                    relevance_score=0.0,
                    subquery=subquery_ref,
                    word_count=len(full_text.split()),
                    secondary_urls=[],
                )
            ]

        # Break any individual paragraphs larger than max_words into atomic units
        atomic_blocks: List[str] = []
        for p in paragraphs:
            atomic_blocks.extend(self._split_long_paragraph(p))

        passages: List[ScoredPassage] = []
        start_idx = 0
        n_blocks = len(atomic_blocks)
        passage_index = 0

        while start_idx < n_blocks:
            current_window: List[str] = []
            current_words = 0
            end_idx = start_idx

            while end_idx < n_blocks:
                block = atomic_blocks[end_idx]
                block_words = len(block.split())

                if current_words + block_words > self.max_words and current_words >= self.min_words:
                    break

                current_window.append(block)
                current_words += block_words
                end_idx += 1

                if current_words >= self.max_words:
                    break

            if not current_window:
                current_window.append(atomic_blocks[start_idx])
                current_words = len(atomic_blocks[start_idx].split())
                end_idx = start_idx + 1

            passage_text = "\n\n".join(current_window)
            passages.append(
                ScoredPassage(
                    passage_id=f"{article.doc_id}-p{passage_index:03d}",
                    doc_id=article.doc_id,
                    url=doc_url,
                    title=doc_title,
                    text=passage_text,
                    relevance_score=0.0,
                    subquery=subquery_ref,
                    word_count=len(passage_text.split()),
                    secondary_urls=[],
                )
            )
            passage_index += 1

            if end_idx >= n_blocks:
                break

            # Calculate overlap starting point: backtrack ~overlap_words from end_idx
            overlap_accum = 0
            overlap_start = end_idx
            for k in range(end_idx - 1, start_idx, -1):
                overlap_accum += len(atomic_blocks[k].split())
                if overlap_accum >= self.overlap_words:
                    overlap_start = k
                    break

            # Strictly advance start_idx by at least 1 to guarantee termination
            start_idx = max(start_idx + 1, overlap_start)

        return passages

    def chunk_batch(
        self,
        batch: Union[RetrievalBatch, List[CleanArticle]],
    ) -> List[ScoredPassage]:
        """Chunk a batch or collection of CleanArticles into ScoredPassages.

        Args:
            batch: RetrievalBatch or List of CleanArticle objects.

        Returns:
            Flat list of all ScoredPassages across all documents.
        """
        articles = batch.documents if hasattr(batch, "documents") else batch
        all_passages: List[ScoredPassage] = []
        for art in articles:
            all_passages.extend(self.chunk_article(art))
        return all_passages
