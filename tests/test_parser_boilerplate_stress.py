"""Adversarial Stress Test Suite: HTML Parsing, Boilerplate Stripping, and Model Serialization.

Tests RobustHTMLParser, DocumentParser, and models under stress, edge cases,
and adversarial conditions.
"""

from __future__ import annotations

import json
import unittest

from src.research_synthesis.models import (
    BriefMetadata,
    CleanArticle,
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
from src.research_synthesis.retrieval.parser import DocumentParser, RobustHTMLParser


class TestBoilerplateAndParserDefects(unittest.TestCase):
    """Stress tests exposing critical defects in RobustHTMLParser and DocumentParser."""

    def test_boilerplate_container_silences_subsequent_content(self):
        """CRITICAL DEFECT 1: A boilerplate class/id on a non-IGNORE_TAG (e.g. div)

        permanently leaves ignore_depth >= 1 because handle_endtag only decrements
        ignore_depth if tag_lower in IGNORE_TAGS. Consequently, all valid content
        after the boilerplate container is completely lost!
        """
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Test Article</title></head>
        <body>
            <div class="cookie-banner">
                <p>Please accept cookies.</p>
            </div>
            <main>
                <h1>Valid Article Heading That Is Long Enough</h1>
                <p>This is substantive article paragraph one that contains important research findings.</p>
                <p>This is substantive article paragraph two that contains even more valuable knowledge.</p>
            </main>
        </body>
        </html>
        """
        parser = RobustHTMLParser()
        parser.feed(html)
        parser._flush_text()

        # EXPECTED: The boilerplate cookie banner is ignored, but paragraphs inside <main> are retained.
        # ACTUAL BUG: ignore_depth is incremented on <div class="cookie-banner">.
        # When </div> is reached, 'div' is not in IGNORE_TAGS, so ignore_depth remains 1 forever!
        # Result: parser.paragraphs is empty!
        self.assertGreater(
            len(parser.paragraphs),
            0,
            f"Parser paragraphs should not be empty after a boilerplate div! Actual: {parser.paragraphs}, ignore_depth={parser.ignore_depth}",
        )

    def test_ad_keyword_false_positive_silences_legitimate_content(self):
        """CRITICAL DEFECT 2: BOILERPLATE_CLASS_ID_KEYWORDS contains 'ad-', which matches

        any class or ID containing 'lead-', 'thread-', 'upload-', 'broad-', 'head-', etc.
        Because these are standard content wrapper classes on <div>, they trigger
        boilerplate filtering AND permanently freeze ignore_depth >= 1!
        """
        html = """
        <html>
        <body>
            <div class="lead-story">
                <p>Leading research from global institutes reveals breakthrough energy densities.</p>
            </div>
            <div class="thread-container">
                <p>Discussion threads highlight substantial manufacturing efficiencies achieved in 2025.</p>
            </div>
        </body>
        </html>
        """
        parser = RobustHTMLParser()
        parser.feed(html)
        parser._flush_text()

        self.assertGreater(
            len(parser.paragraphs),
            0,
            f"Legitimate content in 'lead-story' or 'thread-container' was falsely silenced by 'ad-' keyword! ignore_depth={parser.ignore_depth}",
        )

    def test_modal_keyword_false_positive_on_multimodal(self):
        """CRITICAL DEFECT 3: BOILERPLATE_CLASS_ID_KEYWORDS contains 'modal', which matches

        'multimodal' in AI/technical articles (e.g. class='multimodal-architecture').
        """
        html = """
        <html>
        <body>
            <div class="multimodal-architecture">
                <p>Multimodal architectures combine vision, text, and sensory telemetry into unified embeddings.</p>
            </div>
        </body>
        </html>
        """
        parser = RobustHTMLParser()
        parser.feed(html)
        parser._flush_text()

        self.assertGreater(
            len(parser.paragraphs),
            0,
            f"'multimodal-architecture' was falsely silenced by 'modal' keyword! ignore_depth={parser.ignore_depth}",
        )

    def test_short_headings_dropped_by_length_filter(self):
        """DEFECT 4: RobustHTMLParser applies `if len(cleaned) >= 25:` to BOTH paragraphs

        AND headings in _flush_text(). Common section headings like 'Executive Summary',
        'Key Findings', 'Introduction', 'Abstract', 'Conclusion' are shorter than 25 chars
        and are discarded!
        """
        html = """
        <html>
        <body>
            <h1>Executive Summary</h1>
            <p>This is a substantive paragraph discussing the executive summary details in full length.</p>
            <h2>Key Findings</h2>
            <p>Another substantive paragraph presenting key findings and metrics across all evaluations.</p>
        </body>
        </html>
        """
        parser = RobustHTMLParser()
        parser.feed(html)
        parser._flush_text()

        self.assertIn(
            "Executive Summary",
            parser.headings,
            f"Headings under 25 chars should not be dropped! parser.headings: {parser.headings}",
        )
        self.assertIn(
            "Key Findings",
            parser.headings,
            f"Headings under 25 chars should not be dropped! parser.headings: {parser.headings}",
        )

    def test_tag_stack_corruption_on_ignored_children(self):
        """DEFECT 5: When an ignored tag contains standard tags (e.g. <nav><p>Home</p></nav>),

        handle_starttag appends 'p' to self.tag_stack (line 97) even when ignore_depth > 0,
        but handle_endtag returns at line 113 without popping self.tag_stack!
        This permanently pollutes tag_stack.
        """
        html = """
        <html>
        <body>
            <nav>
                <p>Nav Item 1</p>
                <p>Nav Item 2</p>
            </nav>
            <p>Actual article text that has enough length to be a valid paragraph.</p>
        </body>
        </html>
        """
        parser = RobustHTMLParser()
        parser.feed(html)
        parser._flush_text()

        # tag_stack should not contain leaked tags from the nav
        self.assertEqual(
            parser.tag_stack,
            [],
            f"tag_stack was corrupted by ignored container children: {parser.tag_stack}",
        )


class TestHTMLParserExtremeStress(unittest.TestCase):
    """Stress tests with malformed HTML, deep nesting, and extreme boilerplate."""

    def test_unclosed_tags_and_missing_body(self):
        """Malformed HTML with unclosed tags, missing html/body wrapper."""
        raw_html = (
            "<p>First unclosed paragraph with sufficient text to exceed twenty-five characters."
            "<p>Second unclosed paragraph with sufficient text to exceed twenty-five characters."
            "<div><span>Third unclosed paragraph with sufficient text to exceed twenty-five characters."
        )
        raw_doc = RawWebDocument(
            url="https://example.org/unclosed",
            status_code=200,
            raw_html=raw_html,
        )
        article = DocumentParser.parse(raw_doc)
        self.assertGreaterEqual(len(article.paragraphs), 2)

    def test_deeply_nested_elements(self):
        """1,000 levels of nested div tags enclosing substantive text."""
        depth = 1000
        nested_html = "<div>" * depth + "<p>Substantive text deeply nested inside one thousand HTML div containers.</p>" + "</div>" * depth
        raw_doc = RawWebDocument(
            url="https://example.org/nested",
            status_code=200,
            raw_html=nested_html,
        )
        article = DocumentParser.parse(raw_doc)
        self.assertEqual(len(article.paragraphs), 1)
        self.assertIn("Substantive text deeply nested", article.cleaned_text)

    def test_extreme_boilerplate_thousands_of_scripts_styles(self):
        """HTML containing 2,000 script and style tags interleaved with text."""
        boilerplate_tags = [
            f"<script>var tracker_{i} = 'analytics_{i}';</script><style>.style_{i} {{ color: red; }}</style>"
            for i in range(1000)
        ]
        html_content = (
            "<html><head>"
            + "".join(boilerplate_tags)
            + "</head><body>"
            + "<p>This is the real article paragraph that must survive two thousand boilerplate script tags.</p>"
            + "</body></html>"
        )
        raw_doc = RawWebDocument(
            url="https://example.org/script-bomb",
            status_code=200,
            raw_html=html_content,
        )
        article = DocumentParser.parse(raw_doc)
        self.assertEqual(len(article.paragraphs), 1)
        self.assertNotIn("tracker_", article.cleaned_text)
        self.assertNotIn("style_", article.cleaned_text)
        self.assertIn("real article paragraph that must survive", article.cleaned_text)

    def test_missing_metadata_graceful_fallbacks(self):
        """Document with zero title, author, date, and bare URL."""
        raw_html = "<html><body><p>Bare document paragraph with enough characters to pass the substantive filter.</p></body></html>"
        raw_doc = RawWebDocument(
            url="https://example.com/",
            status_code=200,
            raw_html=raw_html,
        )
        article = DocumentParser.parse(raw_doc)
        self.assertIsNotNone(article.metadata.title)
        self.assertEqual(article.metadata.domain, "example.com")
        self.assertEqual(article.metadata.author, "example.com")
        self.assertIsNone(article.metadata.published_date)
        self.assertEqual(len(article.doc_id), 16)

    def test_html_entities_and_unicode_oddities(self):
        """Text containing complex HTML entities, emoji, and Unicode characters."""
        raw_html = """
        <html>
        <head><title>Unicode &amp; Entities &mdash; Test</title></head>
        <body>
            <p>Energy density reached 450&nbsp;Wh/kg &plusmn; 5% in laboratory tests &copy; 2025.</p>
            <p>Advancements in nanotech &#x1F52C; yield 99.9&#37; purity across solid electrolytes &#128640;.</p>
        </body>
        </html>
        """
        raw_doc = RawWebDocument(
            url="https://example.org/unicode",
            status_code=200,
            raw_html=raw_html,
        )
        article = DocumentParser.parse(raw_doc)
        self.assertIn("450 Wh/kg ± 5%", article.cleaned_text)
        self.assertIn("99.9% purity", article.cleaned_text)
        self.assertIn("🔬", article.cleaned_text)
        self.assertIn("🚀", article.cleaned_text)


class TestModelSerializationStress(unittest.TestCase):
    """Stress tests on dataclass models serialization and deserialization."""

    def test_brief_metadata_object_in_research_brief_raises_type_error(self):
        """CRITICAL DEFECT 6: In ResearchBrief.to_dict(), line 401 has `meta = dict(self.metadata)`.

        If metadata is a BriefMetadata dataclass instance (defined in models.py!),
        dict(BriefMetadata) raises TypeError: 'BriefMetadata' object is not iterable!
        """
        brief_meta = BriefMetadata(
            query="Solid-State Batteries",
            synthesis_mode="deterministic_extractive",
            total_sources_scanned=10,
        )
        brief = ResearchBrief(
            brief_id="brief-001",
            topic="Solid-State Batteries",
            executive_summary="Executive summary text with [1] citation.",
            key_takeaways=[KeyTakeaway(text="Takeaway 1", citation_indices=[1])],
            thematic_sections=[
                ThematicSection(
                    section_id="sec-01",
                    title="Section 1",
                    narrative="Section narrative with [1].",
                    citation_indices=[1],
                    claim_ids=["c1"],
                )
            ],
            sources=[
                SourceCitation(
                    citation_index=1,
                    source_id="src-01",
                    title="Source Title",
                    url="https://example.com/src1",
                )
            ],
            metadata=brief_meta,  # type: ignore
        )

        d = brief.to_dict()
        self.assertEqual(d["metadata"]["query"], "Solid-State Batteries")
        self.assertEqual(d["metadata"]["total_sources_scanned"], 10)
        self.assertIn("total_claims_extracted", d["metadata"])

    def test_markdown_citation_spacing_typo(self):
        """DEFECT 7: In ResearchBrief.to_markdown() line 436:

        `cites = f" [{' ,'.join(str(c) for c in kt.citation_indices)}]" if kt.citation_indices else ""`
        uses `' ,'.join` instead of `', '.join`, producing '[1 ,2]' instead of '[1, 2]'.
        """
        brief = ResearchBrief(
            brief_id="brief-001",
            topic="Solid-State Batteries",
            executive_summary="Summary.",
            key_takeaways=[KeyTakeaway(text="Takeaway with citations", citation_indices=[1, 2, 3])],
            thematic_sections=[],
            sources=[],
        )
        md = brief.to_markdown()
        self.assertIn("[1, 2, 3]", md, "Proper formatting with comma-space in citation rendering.")
        self.assertNotIn("[1 ,2 ,3]", md, "Space-before-comma typo should not be present.")

    def test_missing_from_dict_on_retrieval_batch_and_scored_passage(self):
        """DEFECT 8: RetrievalBatch and ScoredPassage define to_dict() but omit from_dict(),

        violating symmetry across pipeline serialization contracts.
        """
        self.assertTrue(hasattr(RetrievalBatch, "from_dict"), "RetrievalBatch must provide from_dict()")
        self.assertTrue(hasattr(ScoredPassage, "from_dict"), "ScoredPassage must provide from_dict()")

    def test_document_metadata_from_dict_fails_on_doc_id(self):
        """DEFECT 9: DocumentMetadata has @property doc_id. If a serialized dict

        containing 'doc_id' is passed to DocumentMetadata.from_dict(),
        cls(**data) fails with unexpected keyword argument 'doc_id'.
        """
        meta = DocumentMetadata(
            url="https://example.org/doc",
            canonical_url="https://example.org/doc",
            domain="example.org",
            title="Title",
        )
        data = meta.to_dict()
        data["doc_id"] = meta.doc_id  # common in serialized document dicts

        restored = DocumentMetadata.from_dict(data)
        self.assertEqual(restored.url, meta.url)
        self.assertEqual(restored.doc_id, meta.doc_id)

    def test_research_brief_full_json_roundtrip(self):
        """Verify full JSON serialization roundtrip on complex nested ResearchBrief."""
        brief = ResearchBrief(
            brief_id="brief-test-42",
            topic="Autonomous Web Research Synthesis",
            executive_summary="Executive summary synthesizes claims across sources [1] and [2].",
            key_takeaways=[
                KeyTakeaway(text="Takeaway alpha", citation_indices=[1]),
                KeyTakeaway(text="Takeaway beta", citation_indices=[1, 2]),
            ],
            thematic_sections=[
                ThematicSection(
                    section_id="sec-01",
                    title="Architecture & Methodology",
                    narrative="Detailed technical synthesis with evidence [1].",
                    citation_indices=[1],
                    claim_ids=["claim-01", "claim-02"],
                    key_findings=["Finding A", "Finding B"],
                ),
                ThematicSection(
                    section_id="sec-02",
                    title="Empirical Validation",
                    narrative="Empirical validation findings confirm assertions [2].",
                    citation_indices=[2],
                    claim_ids=["claim-03"],
                    key_findings=["Finding C"],
                ),
            ],
            sources=[
                SourceCitation(
                    citation_index=1,
                    source_id="src-01",
                    title="Source One: Technical Foundations",
                    url="https://example.org/foundations",
                    author="Dr. Alice Smith",
                    publish_date="2024-01-15",
                    snippet="Foundational principles of extraction.",
                    attributed_claim_ids=["claim-01", "claim-02"],
                ),
                SourceCitation(
                    citation_index=2,
                    source_id="src-02",
                    title="Source Two: Empirical Rigor",
                    url="https://example.org/rigor",
                    author="Dr. Bob Jones",
                    publish_date="2024-02-20",
                    snippet="Empirical testing frameworks.",
                    attributed_claim_ids=["claim-03"],
                ),
            ],
            metadata={
                "pipeline_version": "1.0.0",
                "execution_mode": "mock",
                "total_sources_scanned": 5,
            },
            sub_queries=["Subquery 1", "Subquery 2"],
        )

        # 1. to_json
        json_str = brief.to_json(indent=2)
        self.assertIsInstance(json_str, str)

        # 2. json.loads
        parsed_dict = json.loads(json_str)

        # 3. from_dict
        restored_brief = ResearchBrief.from_dict(parsed_dict)

        # 4. Verify fields match exactly
        self.assertEqual(restored_brief.brief_id, brief.brief_id)
        self.assertEqual(restored_brief.topic, brief.topic)
        self.assertEqual(restored_brief.query, brief.topic)
        self.assertEqual(restored_brief.executive_summary, brief.executive_summary)
        self.assertEqual(len(restored_brief.key_takeaways), 2)
        self.assertEqual(restored_brief.key_takeaways[0].text, "Takeaway alpha")
        self.assertEqual(restored_brief.key_takeaways[0].citation_indices, [1])
        self.assertEqual(len(restored_brief.thematic_sections), 2)
        self.assertEqual(restored_brief.thematic_sections[0].title, "Architecture & Methodology")
        self.assertEqual(restored_brief.thematic_sections[0].key_findings, ["Finding A", "Finding B"])
        self.assertEqual(len(restored_brief.sources), 2)
        self.assertEqual(restored_brief.sources[0].title, "Source One: Technical Foundations")
        self.assertEqual(restored_brief.metadata["pipeline_version"], "1.0.0")
        self.assertEqual(restored_brief.sub_queries, ["Subquery 1", "Subquery 2"])


if __name__ == "__main__":
    unittest.main()
