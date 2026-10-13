"""Discrete Factual Claim Extraction Engine.

Milestone 2 - Feature F9.
Pure Python Standard Library (3.10+) - Zero External Dependencies.

Segments sentences with abbreviation protection, filters noise and non-factual content,
classifies factual claims into taxonomy types (QUANTITATIVE, TEMPORAL_EVENT, RELATIONAL, GENERAL_FACT),
extracts named entities, calculates heuristic confidence scores, and generates deterministic claim IDs.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

try:
    from research_synthesis.models import ClaimType, CleanArticle, ExtractedClaim, ScoredPassage
except ImportError:
    try:
        from src.research_synthesis.models import ClaimType, CleanArticle, ExtractedClaim, ScoredPassage
    except ImportError:
        from ..models import ClaimType, CleanArticle, ExtractedClaim, ScoredPassage


# English sentence-initial discourse markers to ignore during entity extraction
DISCOURSE_STOPWORDS: Set[str] = {
    "a", "an", "the", "this", "that", "these", "those",
    "in", "on", "at", "for", "with", "by", "from", "as", "into", "through",
    "however", "although", "moreover", "furthermore", "additionally",
    "consequently", "nonetheless", "meanwhile", "according", "despite",
    "while", "after", "before", "since", "if", "when", "where", "whereas",
    "overall", "similarly", "notably", "critically", "importantly", "finally"
}

# Common abbreviations to protect during sentence splitting.
# Note: Single-letter and common-word abbreviations ('p.', 'No.', 'pp.') require following digits
# to prevent masking sentence-terminal periods on standard words (e.g. "The answer was no.").
ABBREVIATIONS: Sequence[str] = (
    # Latin / academic
    r"e\.g\.", r"i\.e\.", r"et al\.(?-i:(?!\s+[A-Z]))", r"etc\.", r"vs\.", r"cf\.", r"ibid\.", r"ca\.",
    # Titles & Honorifics
    r"Dr\.", r"Mr\.", r"Mrs\.", r"Ms\.", r"Prof\.", r"Sr\.", r"Jr\.", r"Gen\.", r"Gov\.", r"Sen\.", r"Rep\.", r"St\.",
    # Corporate & Legal
    r"Inc\.", r"Corp\.", r"Ltd\.", r"Co\.", r"LLC\.",
    # Geographic & Acronyms
    r"U\.S\.", r"U\.S\.A\.", r"U\.K\.", r"E\.U\.", r"D\.C\.",
    # Publications & Reference (require numeric context for 'No.', 'p.', and 'pp.')
    r"No\.\s*(?=\d)", r"Fig\.", r"Vol\.", r"pp\.\s*(?=\d)", r"p\.\s*(?=\d)", r"Ph\.D\.", r"M\.D\."
)


class ClaimExtractor:
    """Extracts discrete, verifiable factual claims from scored passages or clean articles."""

    # 1. Quantitative Pattern
    QUANTITATIVE_PATTERN = re.compile(
        r"(?:"
        r"\b\d+(?:[.,]\d+)?\s*(?:%|percent\b|percentage\b|basis points\b|bps\b)|"
        r"[\$€£¥]\s*\d+(?:[.,]\d+)?\s*(?:billion|million|trillion|k|m|b)?\b|"
        r"\b\d+(?:[.,]\d+)?\s*(?:USD|EUR|GBP|dollars|cents)\b|"
        r"\b\d+(?:[.,]\d+)?\s*(?:Wh/kg|Wh/L|mAh/g|mS/cm|ohm-cm2|mA/cm2|GPa|MPa|V|kW|MW|GW|GWh|kWh|m/min|nm|μm|mm|cm|m|km)\b|"
        r"\b\d+(?:[.,]\d+)?\s*(?:°C|degrees\s+Celsius|degrees|kelvin|K)\b|"
        r"\b\d+(?:[.,]\d+)?\s*(?:tons|tonnes|kg|g|liters|gallons|hours|cycles|weeks|months|years)\b|"
        r"\b\d+(?:[.,]\d+)?\s*(?:billion|million|trillion|thousand)\b|"
        r"\b\d+(?:[.,]\d+)?\s*(?:-|–|to)\s*\d+(?:[.,]\d+)?\s*(?:%|Wh/kg|°C|mS/cm|billion|million|USD|\$|tons)(?:\b|$)"
        r")",
        re.IGNORECASE,
    )

    # 2. Temporal Pattern (1400-2099 or specific historical/projected milestones)
    TEMPORAL_PATTERN = re.compile(
        r"(?:"
        r"\b(?:by|in|since|until|from|during|between)\s+(?:late\s+|early\s+|mid-)?(1[4-9]\d\d|20\d\d)\b|"
        r"\b(1[4-9]\d\d|20\d\d)\s*[-–—]\s*(1[4-9]\d\d|20\d\d)\b|"
        r"\b(?:late|early|mid)?\s*(?:Q[1-4]\s+)?(1[4-9]\d\d|20\d\d)\b|"
        r"\b(?:Maunder Minimum|Little Ice Age|Cold War|Industrial Revolution)\b|"
        r"\b\d{1,2}(?:st|nd|rd|th)\s+century\b"
        r")",
        re.IGNORECASE,
    )

    # 3. Relational & Comparative Predicates
    RELATIONAL_PATTERN = re.compile(
        r"\b(?:"
        r"increased\s+by|decreased\s+by|reduced\s+by|grew\s+by|dropped\s+by|"
        r"superior\s+to|inferior\s+to|greater\s+than|less\s+than|higher\s+than|lower\s+than|"
        r"exceeded|surpassed|outperformed|outpaced|lagged\s+behind|"
        r"correlated\s+with|associated\s+with|driven\s+by|resulted\s+in|attributed\s+to|"
        r"compared\s+to|in\s+contrast\s+to|relative\s+to|"
        r"accelerated|decelerated|doubled|tripled|halved"
        r")\b",
        re.IGNORECASE,
    )

    # 4. General Assertion Verbs
    ASSERTION_VERBS: Set[str] = {
        "demonstrated", "achieved", "published", "discovered", "established",
        "confirmed", "revealed", "announced", "implemented", "manufactured",
        "synthesized", "identified", "concluded", "showed", "indicates",
        "operates", "consists", "utilizes", "deploys", "reported", "found",
        "developed", "produced", "unlocked", "projected", "modeled", "tested"
    }

    # 5. Noise and Call-To-Action Patterns
    NOISE_CALL_TO_ACTION = re.compile(
        r"\b(?:"
        r"click\s+here|sign\s+up|read\s+more|subscribe|register\s+now|download\s+the|"
        r"learn\s+more|contact\s+us|leave\s+a\s+comment|log\s+in|join\s+our|"
        r"share\s+this|follow\s+us|buy\s+now|order\s+today|check\s+out|"
        r"sponsored|advertisement|recommended\s+for\s+you|newsletter"
        r")\b",
        re.IGNORECASE,
    )

    # 6. Speculative Hedges
    SPECULATIVE_HEDGE = re.compile(
        r"^(?:"
        r"it\s+remains\s+to\s+be\s+seen|in\s+(?:our|my)\s+(?:opinion|view)|"
        r"i\s+(?:think|believe)|we\s+(?:think|believe)|"
        r"some\s+might\s+argue|there\s+is\s+speculation\s+that|"
        r"critics\s+wonder\s+if|nobody\s+knows\s+whether"
        r")\b",
        re.IGNORECASE,
    )

    # 7. Mild Hedging Words for Confidence Dampening
    MILD_HEDGES: Set[str] = {
        "likely", "suggests", "estimated", "may", "might", "potentially",
        "presumably", "possibly", "tentatively", "unclear", "purportedly"
    }

    def __init__(
        self,
        min_confidence: float = 0.35,
        min_words: int = 5,
        max_words: int = 80,
    ) -> None:
        """Initialize ClaimExtractor with configurable thresholds.

        Args:
            min_confidence: Minimum confidence threshold to retain claim (default 0.35).
            min_words: Minimum words per sentence to qualify as claim (default 5).
            max_words: Maximum words per sentence to qualify as claim (default 80).
        """
        self.min_confidence = min_confidence
        self.min_words = min_words
        self.max_words = max_words

        # Compile abbreviation replacement regex
        abbr_joined = "|".join(f"(?:{p})" for p in ABBREVIATIONS)
        self._abbr_regex = re.compile(rf"\b({abbr_joined})", re.IGNORECASE)

    # -------------------------------------------------------------------------
    # Sentence Segmentation Subsystem
    # -------------------------------------------------------------------------

    def segment_sentences(self, text: str) -> List[str]:
        """Split text into sentences while protecting abbreviations, decimals, and ellipses."""
        if not text or not text.strip():
            return []

        cleaned = text.strip()

        # Step 1: Protect URLs
        url_matches: List[str] = []
        def _mask_url(m: re.Match) -> str:
            url_matches.append(m.group(0))
            return f"__URL_{len(url_matches)-1}__"

        cleaned = re.sub(r"https?://[^\s]+", _mask_url, cleaned)

        # Step 2: Protect decimal numbers (e.g. 12.0, 3.14, $4.5)
        cleaned = re.sub(r"(?<=\d)\.(?=\d)", "@@DECIMAL@@", cleaned)

        # Step 3: Protect ellipses
        cleaned = re.sub(r"\.{3,}|…", "@@ELLIPSIS@@", cleaned)

        # Step 4: Protect known abbreviations
        def _mask_abbr(m: re.Match) -> str:
            return m.group(0).replace(".", "@@DOT@@")

        cleaned = self._abbr_regex.sub(_mask_abbr, cleaned)

        # Step 5: Split by sentence terminal punctuation followed by space or newline
        raw_splits = re.split(r"(?<=[.!?])\s+", cleaned)

        sentences: List[str] = []
        for s in raw_splits:
            # Restore protected tokens
            s = s.replace("@@DOT@@", ".")
            s = s.replace("@@DECIMAL@@", ".")
            s = s.replace("@@ELLIPSIS@@", "...")
            for idx, orig_url in enumerate(url_matches):
                s = s.replace(f"__URL_{idx}__", orig_url)

            s = s.strip()
            # Retain non-empty segmented sentences (word count bounds validated in is_noise_or_non_claim)
            if s:
                sentences.append(s)

        return sentences

    # -------------------------------------------------------------------------
    # Noise and Gatekeeping Subsystem
    # -------------------------------------------------------------------------

    def is_noise_or_non_claim(self, sentence: str) -> bool:
        """Evaluate if a sentence is noise, an imperative command, a question, or a baseless hedge."""
        s = sentence.strip()
        words = re.findall(r"\b\w+\b", s.lower())
        word_count = len(words)

        # Guardrails: word count bounds
        if word_count < self.min_words or word_count > self.max_words:
            return True

        # Rule 1: Interrogative sentence
        if s.endswith("?") or re.search(r"^(?:is|are|can|will|should|could|would|why|how|what|where|who)\b.*\?", s, re.IGNORECASE):
            return True

        # Rule 2: Imperative / Call to action / Ad boilerplate
        if self.NOISE_CALL_TO_ACTION.search(s):
            return True

        # Rule 3: Speculative hedge without facts
        if self.SPECULATIVE_HEDGE.search(s):
            has_numbers = bool(re.search(r"\d", s))
            has_entities = len(self.extract_entities(s)) > 0
            if not has_numbers and not has_entities:
                return True

        return False

    # -------------------------------------------------------------------------
    # Taxonomy Classification Subsystem
    # -------------------------------------------------------------------------

    def classify_claim_type(self, sentence: str) -> Optional[ClaimType]:
        """Classify candidate sentence into ClaimType taxonomy or None if not factual."""
        if self.is_noise_or_non_claim(sentence):
            return None

        # Priority 1: Quantitative claim (numerical metrics, units, percentages)
        if self.QUANTITATIVE_PATTERN.search(sentence):
            return ClaimType.QUANTITATIVE

        # Priority 2: Temporal event claim (dates, milestones, historical epochs)
        if self.TEMPORAL_PATTERN.search(sentence):
            return ClaimType.TEMPORAL_EVENT

        # Priority 3: Relational claim (comparative/relational predicates)
        if self.RELATIONAL_PATTERN.search(sentence):
            return ClaimType.RELATIONAL

        # Priority 4: General fact (assertion verb + concrete named entities/acronyms)
        words = set(re.findall(r"\b\w+\b", sentence.lower()))
        has_assertion = bool(words & self.ASSERTION_VERBS)
        entities = self.extract_entities(sentence)

        if has_assertion and len(entities) >= 1:
            return ClaimType.GENERAL_FACT

        # Substantive sentence with at least 2 distinct entities
        if len(entities) >= 2 and len(words) >= 10:
            return ClaimType.GENERAL_FACT

        return None

    # -------------------------------------------------------------------------
    # Entity Extraction Subsystem
    # -------------------------------------------------------------------------

    def extract_entities(self, sentence: str) -> List[str]:
        """Extract capitalized proper names, technical acronyms, and domain keywords."""
        entities: List[str] = []
        seen: Set[str] = set()

        # 1. Capitalized multi-word or single-word sequences (including CamelCase like QuantumScape)
        cap_candidates = re.findall(r"\b[A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)*\b", sentence)
        for cand in cap_candidates:
            cand_clean = cand.strip()
            # Exclude sentence-initial stopwords
            if cand_clean.lower() in DISCOURSE_STOPWORDS:
                continue
            if len(cand_clean) > 2 and cand_clean.lower() not in seen:
                seen.add(cand_clean.lower())
                entities.append(cand_clean)

        # 2. All-caps technical acronyms (2 to 6 characters)
        acronyms = re.findall(r"\b[A-Z]{2,6}\b", sentence)
        for acr in acronyms:
            if acr.lower() not in seen:
                seen.add(acr.lower())
                entities.append(acr)

        return entities

    # -------------------------------------------------------------------------
    # Confidence Scoring Subsystem
    # -------------------------------------------------------------------------

    def calculate_confidence(
        self,
        sentence: str,
        claim_type: ClaimType,
        base_relevance: float = 0.5,
        entities: Optional[List[str]] = None,
    ) -> float:
        """Calculate heuristic confidence score between 0.0 and 1.0."""
        score = min(0.75, max(0.40, base_relevance * 0.6 + 0.20))
        ents = entities if entities is not None else self.extract_entities(sentence)
        words = set(re.findall(r"\b\w+\b", sentence.lower()))

        # Additive indicators
        if claim_type == ClaimType.QUANTITATIVE:
            score += 0.25
        elif claim_type == ClaimType.TEMPORAL_EVENT:
            score += 0.15
        elif claim_type == ClaimType.RELATIONAL:
            score += 0.15

        if len(ents) >= 2:
            score += 0.15
        elif len(ents) == 1:
            score += 0.10

        if words & self.ASSERTION_VERBS:
            score += 0.10

        word_count = len(words)
        if 12 <= word_count <= 45:
            score += 0.05

        # Deductive indicators
        if words & self.MILD_HEDGES:
            score -= 0.10
        if not ents:
            score -= 0.10
        if word_count < 8:
            score -= 0.15
        elif word_count > 55:
            score -= 0.05

        return round(max(0.0, min(1.0, score)), 2)

    # -------------------------------------------------------------------------
    # Deterministic Claim ID Subsystem
    # -------------------------------------------------------------------------

    @staticmethod
    def generate_claim_id(source_url: str, text: str) -> str:
        """Generate deterministic 16-character SHA-256 hash prefix for a claim."""
        norm_url = (source_url or "").strip().lower()
        norm_text = re.sub(r"\s+", " ", (text or "").strip().lower())
        payload = f"{norm_url}::{norm_text}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"clm-{digest[:12]}"

    # -------------------------------------------------------------------------
    # High-Level Extraction APIs
    # -------------------------------------------------------------------------

    def extract_claims_from_passage(self, passage: ScoredPassage) -> List[ExtractedClaim]:
        """Extract all valid factual claims from a single ScoredPassage."""
        claims: List[ExtractedClaim] = []
        sentences = self.segment_sentences(passage.text)

        for idx, sent in enumerate(sentences):
            claim_type = self.classify_claim_type(sent)
            if claim_type is None:
                continue

            entities = self.extract_entities(sent)
            confidence = self.calculate_confidence(
                sentence=sent,
                claim_type=claim_type,
                base_relevance=passage.relevance_score,
                entities=entities,
            )

            if confidence < self.min_confidence:
                continue

            # Context snippet: surrounding sentences
            start_ctx = max(0, idx - 1)
            end_ctx = min(len(sentences), idx + 2)
            snippet = " ".join(sentences[start_ctx:end_ctx])

            claim_id = self.generate_claim_id(passage.url, sent)

            claims.append(
                ExtractedClaim(
                    claim_id=claim_id,
                    text=sent,
                    source_doc_id=passage.doc_id,
                    source_url=passage.url,
                    source_title=passage.title,
                    passage_snippet=snippet,
                    confidence_score=confidence,
                    claim_type=claim_type,
                    entities=entities,
                    secondary_urls=list(passage.secondary_urls),
                )
            )

        return claims

    def extract_claims_from_article(self, article: CleanArticle) -> List[ExtractedClaim]:
        """Extract all valid factual claims from a CleanArticle."""
        claims: List[ExtractedClaim] = []
        text_source = article.cleaned_text or " ".join(article.paragraphs)
        sentences = self.segment_sentences(text_source)

        for idx, sent in enumerate(sentences):
            claim_type = self.classify_claim_type(sent)
            if claim_type is None:
                continue

            entities = self.extract_entities(sent)
            confidence = self.calculate_confidence(
                sentence=sent,
                claim_type=claim_type,
                base_relevance=0.6,
                entities=entities,
            )

            if confidence < self.min_confidence:
                continue

            start_ctx = max(0, idx - 1)
            end_ctx = min(len(sentences), idx + 2)
            snippet = " ".join(sentences[start_ctx:end_ctx])

            claim_id = self.generate_claim_id(article.url, sent)

            claims.append(
                ExtractedClaim(
                    claim_id=claim_id,
                    text=sent,
                    source_doc_id=article.doc_id,
                    source_url=article.url,
                    source_title=article.metadata.title if article.metadata else "",
                    passage_snippet=snippet,
                    confidence_score=confidence,
                    claim_type=claim_type,
                    entities=entities,
                    secondary_urls=[],
                )
            )

        return claims

    def extract_claims(self, passages: Sequence[ScoredPassage]) -> List[ExtractedClaim]:
        """Batch extraction across a list of ScoredPassage objects."""
        all_claims: List[ExtractedClaim] = []
        seen_ids: Set[str] = set()

        for passage in passages:
            extracted = self.extract_claims_from_passage(passage)
            for claim in extracted:
                if claim.claim_id not in seen_ids:
                    seen_ids.add(claim.claim_id)
                    all_claims.append(claim)

        return all_claims


# Backward compatibility and ergonomic alias
FactualClaimExtractor = ClaimExtractor
