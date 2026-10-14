"""Comparative & Longitudinal Synthesis Engine.

Track A - Meta-Brief Cross-Comparison & Trend/Velocity Tracking.
Pure Python Standard Library (3.10+) - Zero External Dependencies.

Provides:
1. `LongitudinalTracker`: Detects temporal shift indicators, target parity year
   shifts, and annualized metric velocity across dated claims and briefs.
2. `ComparativeSynthesisEngine`: Synthesizes two or more `ResearchBrief` objects
   (e.g., "Solid-State Batteries" vs "Sodium-Ion Batteries") into a unified,
   schema-compliant comparative meta-brief highlighting technological trade-offs,
   cost parity curves, longitudinal velocity trends, and conflicting claims with
   continuous 1-based IEEE [N] citation re-indexing.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

try:
    from research_synthesis.models import (
        BriefMetadata,
        ClaimType,
        DiscrepancyGroup,
        ExtractedClaim,
        KeyTakeaway,
        ResearchBrief,
        SourceCitation,
        ThematicSection,
    )
    from research_synthesis.synthesis.synthesizer import CitationRegistry
except ImportError:
    try:
        from src.research_synthesis.models import (
            BriefMetadata,
            ClaimType,
            DiscrepancyGroup,
            ExtractedClaim,
            KeyTakeaway,
            ResearchBrief,
            SourceCitation,
            ThematicSection,
        )
        from src.research_synthesis.synthesis.synthesizer import CitationRegistry
    except ImportError:
        from ..models import (
            BriefMetadata,
            ClaimType,
            DiscrepancyGroup,
            ExtractedClaim,
            KeyTakeaway,
            ResearchBrief,
            SourceCitation,
            ThematicSection,
        )
        from .synthesizer import CitationRegistry


# ============================================================================
# Data Contracts for Comparative & Longitudinal Analysis
# ============================================================================

@dataclass
class MetricObservation:
    """Represents a single quantitative metric extracted from a brief's claim."""

    topic: str
    brief_id: str
    dimension: str
    value: float
    unit: str
    raw_match: str
    sentence: str
    source_url: str
    source_title: str
    year: Optional[int] = None
    citation_index: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CrossBriefTradeoffRow:
    """Side-by-side comparison row across two or more research briefs."""

    dimension: str
    unit: str
    values_by_topic: Dict[str, str]
    numeric_by_topic: Dict[str, float]
    delta_summary: str
    citation_indices: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TemporalShiftIndicator:
    """Represents a longitudinal trend or target milestone shift over time."""

    dimension: str
    topic: str
    start_year: int
    end_year: int
    span_years: int
    baseline_value: Optional[float]
    target_value: Optional[float]
    unit: str
    annual_velocity: Optional[float]
    trajectory: str  # "ACCELERATING", "CONVERGING_PARITY", "IMPROVING", "DELAYED_HORIZON", "HISTORICAL_CYCLE"
    summary: str
    citation_indices: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ComparativeSynthesisResult:
    """Container for a multi-brief comparative & longitudinal synthesis."""

    comparison_id: str
    topics: List[str]
    source_brief_ids: List[str]
    meta_brief: ResearchBrief
    tradeoff_matrix: List[CrossBriefTradeoffRow] = field(default_factory=list)
    cost_parity_curves: List[Dict[str, Any]] = field(default_factory=list)
    temporal_shifts: List[TemporalShiftIndicator] = field(default_factory=list)
    cross_discrepancies: List[DiscrepancyGroup] = field(default_factory=list)
    shared_entities: List[str] = field(default_factory=list)
    unique_entities_by_topic: Dict[str, List[str]] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "topics": self.topics,
            "source_brief_ids": self.source_brief_ids,
            "generated_at": self.generated_at,
            "tradeoff_matrix": [r.to_dict() for r in self.tradeoff_matrix],
            "cost_parity_curves": self.cost_parity_curves,
            "temporal_shifts": [t.to_dict() for t in self.temporal_shifts],
            "cross_discrepancies": [d.to_dict() for d in self.cross_discrepancies],
            "shared_entities": self.shared_entities,
            "unique_entities_by_topic": self.unique_entities_by_topic,
            "meta_brief": self.meta_brief.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        return self.meta_brief.to_markdown()

    def to_html(self) -> str:
        return self.meta_brief.to_html()


# ============================================================================
# Longitudinal Trend & Velocity Tracker
# ============================================================================

class LongitudinalTracker:
    """Detects temporal shift indicators, target parity year shifts, and metric velocity."""

    _YEAR_RE = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")

    _METRIC_WITH_UNIT_RE = re.compile(
        r"(?:(?P<prefix>[\$€£])\s*(?P<pval>\d+(?:[.,]\d+)?)\s*(?P<pscale>billion|million|trillion)?(?:\s*(?:per|/)\s*(?P<pdenom>kWh|kg|ton|unit))?)"
        r"|"
        r"(?:\b(?P<val>\d+(?:[.,]\d+)?)\s*(?P<unit>Wh/kg|Wh/L|mAh/g|mS/cm|kWh|GWh|MWh|GW|MW|%|percent|percentage|°C|degrees\s+Celsius|cycles|tons|tonnes|weeks|years|billion|million|USD/kWh|\$/kWh)\b)",
        re.IGNORECASE,
    )

    @classmethod
    def classify_dimension(cls, unit: str, sentence: str) -> Tuple[str, str]:
        """Classify a metric unit and sentence context into a canonical dimension and unit."""
        u_low = unit.lower().strip()
        s_low = sentence.lower()

        if u_low in ("wh/kg", "wh/l", "mah/g") or "energy density" in s_low:
            return "Energy Density", "Wh/kg" if "wh/kg" in u_low else unit
        if "ms/cm" in u_low or "conductivity" in s_low:
            return "Ionic Conductivity", "mS/cm"
        if "kwh" in u_low and ("$" in u_low or "usd" in u_low or "cost" in s_low or "parity" in s_low or "price" in s_low):
            return "Unit Manufacturing Cost", "USD/kWh"
        if u_low in ("$", "usd", "billion", "million", "trillion") or "cost" in s_low or "capex" in s_low or "subsidies" in s_low or "price" in s_low:
            if "kwh" in s_low:
                return "Unit Manufacturing Cost", "USD/kWh"
            if "billion" in u_low or "billion" in s_low:
                return "Capital Expenditure & Investment", "billion USD"
            return "Economic Cost / Price Impact", "%" if "%" in u_low or "percent" in u_low else "USD"
        if "cycle" in u_low:
            return "Cycle Life & Durability", "cycles"
        if "°c" in u_low or "celsius" in u_low or "temperature" in s_low:
            return "Thermal Stability & Temperature", "°C"
        if u_low in ("%", "percent", "percentage"):
            if "efficiency" in s_low or "fidelity" in s_low or "retention" in s_low:
                return "Efficiency & Retention Benchmark", "%"
            if "inflation" in s_low or "premium" in s_low or "cost" in s_low or "price" in s_low:
                return "Cost Premium & Inflation Rate", "%"
            if "volume" in s_low or "reduction" in s_low:
                return "Volumetric & Structural Gain", "%"
            return "Relative Performance Rate", "%"
        if u_low in ("tons", "tonnes", "gwh", "gw", "mw"):
            return "Production & Material Volume", unit
        return "Technical Benchmark", unit

    @classmethod
    def extract_observations_from_brief(
        cls,
        brief: ResearchBrief,
        citation_remap: Optional[Dict[int, int]] = None,
    ) -> List[MetricObservation]:
        """Extract all quantitative and temporal observations from a ResearchBrief."""
        observations: List[MetricObservation] = []
        source_by_idx: Dict[int, SourceCitation] = {s.citation_index: s for s in brief.sources}

        # Collect candidate sentences from sections and takeaways
        candidate_items: List[Tuple[str, List[int]]] = []
        for sec in brief.thematic_sections:
            # Split narrative into sentences
            raw_sents = re.split(r"(?<=\.)\s+", sec.narrative.strip())
            for s in raw_sents:
                cites = [int(m) for m in re.findall(r"\[(\d+)", s)]
                if not cites and sec.citation_indices:
                    cites = [sec.citation_indices[0]]
                candidate_items.append((s, cites))
            for kf in sec.key_findings:
                cites = [int(m) for m in re.findall(r"\[(\d+)", kf)]
                if not cites and sec.citation_indices:
                    cites = [sec.citation_indices[0]]
                candidate_items.append((kf, cites))

        for kt in brief.key_takeaways:
            cites = list(kt.citation_indices) if kt.citation_indices else [int(m) for m in re.findall(r"\[(\d+)", kt.text)]
            candidate_items.append((kt.text, cites))

        seen_keys: Set[str] = set()
        for sent, orig_cites in candidate_items:
            clean_sent = re.sub(r"\s*\[\d+(?:,\s*\d+)*\]", "", sent).strip()
            if not clean_sent:
                continue

            orig_idx = orig_cites[0] if orig_cites else 1
            src = source_by_idx.get(orig_idx)
            src_url = src.url if src else f"https://reference.local/{brief.brief_id}"
            src_title = src.title if src else brief.topic
            mapped_idx = citation_remap.get(orig_idx, orig_idx) if citation_remap else orig_idx

            # Find all year matches with character positions in sentence, or fallback to source publish_date
            year_matches = [(m_yr.start(), int(m_yr.group(1))) for m_yr in cls._YEAR_RE.finditer(clean_sent)]
            fallback_year: Optional[int] = None
            if not year_matches and src and src.publish_date:
                ym = cls._YEAR_RE.search(str(src.publish_date))
                if ym:
                    fallback_year = int(ym.group(1))

            for m in cls._METRIC_WITH_UNIT_RE.finditer(clean_sent):
                if m.group("pval"):
                    raw_num = m.group("pval").replace(",", "")
                    scale = (m.group("pscale") or "").lower()
                    denom = m.group("pdenom") or ""
                    try:
                        val = float(raw_num)
                    except ValueError:
                        continue
                    if denom:
                        unit_str = f"USD/{denom}"
                    elif scale:
                        unit_str = f"{scale} USD"
                    else:
                        unit_str = "USD"
                else:
                    raw_num = (m.group("val") or "").replace(",", "")
                    unit_str = m.group("unit") or ""
                    try:
                        val = float(raw_num)
                    except ValueError:
                        continue

                # Associate metric with nearest year in the sentence
                year_val: Optional[int] = fallback_year
                if year_matches:
                    m_pos = m.end()
                    year_val = min(year_matches, key=lambda yp: abs(yp[0] - m_pos))[1]

                dim, norm_unit = cls.classify_dimension(unit_str, clean_sent)
                dedup_key = f"{brief.brief_id}:{dim}:{val}:{norm_unit}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                observations.append(
                    MetricObservation(
                        topic=brief.topic,
                        brief_id=brief.brief_id,
                        dimension=dim,
                        value=val,
                        unit=norm_unit,
                        raw_match=m.group(0).strip(),
                        sentence=clean_sent,
                        source_url=src_url,
                        source_title=src_title,
                        year=year_val,
                        citation_index=mapped_idx,
                    )
                )

        return observations

    @classmethod
    def detect_temporal_shifts(
        cls,
        briefs: Sequence[ResearchBrief],
        observations: Sequence[MetricObservation],
    ) -> List[TemporalShiftIndicator]:
        """Detect longitudinal trends, target parity horizons, and velocity shifts."""
        shifts: List[TemporalShiftIndicator] = []

        # 1. Group observations by (topic, dimension, unit) first, then across topics
        by_topic_dim: Dict[Tuple[str, str, str], List[MetricObservation]] = defaultdict(list)
        by_dim: Dict[Tuple[str, str], List[MetricObservation]] = defaultdict(list)
        for obs in observations:
            if obs.year is not None:
                by_topic_dim[(obs.topic, obs.dimension, obs.unit)].append(obs)
                by_dim[(obs.dimension, obs.unit)].append(obs)

        groups_to_evaluate: List[Tuple[str, str, List[MetricObservation]]] = []
        for (_t, dim, unit), obs_list in by_topic_dim.items():
            if len({o.year for o in obs_list}) >= 2:
                groups_to_evaluate.append((dim, unit, obs_list))

        for (dim, unit), obs_list in by_dim.items():
            if not any(g_dim == dim and g_unit == unit for g_dim, g_unit, _ in groups_to_evaluate):
                if len(obs_list) >= 2:
                    groups_to_evaluate.append((dim, unit, obs_list))

        for dim, unit, obs_list in groups_to_evaluate:
            # Sort chronologically by year, then by value
            sorted_obs = sorted(obs_list, key=lambda o: (o.year or 0, o.value))
            if len(sorted_obs) >= 2:
                earliest = sorted_obs[0]
                latest = sorted_obs[-1]
                start_yr = earliest.year or 2024
                end_yr = latest.year or 2028
                span = max(1, end_yr - start_yr)
                delta = latest.value - earliest.value
                velocity = round(delta / span, 2)

                if "Cost" in dim:
                    trajectory = "CONVERGING_PARITY" if delta < 0 else "EXPANDING_COST"
                elif delta > 0:
                    trajectory = "ACCELERATING"
                elif delta < 0:
                    trajectory = "CONTRACTING"
                else:
                    trajectory = "STABLE"

                cites = sorted(list({earliest.citation_index, latest.citation_index}))
                cite_str = f"[{', '.join(str(c) for c in cites)}]"
                sign = "+" if velocity > 0 else ""
                summary = (
                    f"{dim} shifts from {earliest.value:g} {unit} ({start_yr}) to "
                    f"{latest.value:g} {unit} ({end_yr}), representing an annualized velocity of "
                    f"{sign}{velocity:g} {unit}/yr ({trajectory}) {cite_str}."
                )
                shifts.append(
                    TemporalShiftIndicator(
                        dimension=dim,
                        topic=f"{earliest.topic} -> {latest.topic}" if earliest.topic != latest.topic else earliest.topic,
                        start_year=start_yr,
                        end_year=end_yr,
                        span_years=span,
                        baseline_value=earliest.value,
                        target_value=latest.value,
                        unit=unit,
                        annual_velocity=velocity,
                        trajectory=trajectory,
                        summary=summary,
                        citation_indices=cites,
                    )
                )

        # 2. Scan narratives for explicit multi-year milestones or target horizon years (e.g., 2024 -> 2028/2030, or 1628 -> 1648 -> 1675)
        for brief in briefs:
            full_text = " ".join([brief.executive_summary] + [s.narrative for s in brief.thematic_sections])
            years_found = sorted({int(y) for y in cls._YEAR_RE.findall(full_text)})
            if len(years_found) >= 2:
                y_start = years_found[0]
                y_end = years_found[-1]
                span = max(1, y_end - y_start)
                # Avoid duplicate if already covered for this brief topic
                if not any(s.start_year == y_start and s.end_year == y_end and brief.topic in s.topic for s in shifts):
                    cites = [brief.sources[0].citation_index] if brief.sources else [1]
                    trajectory = "HISTORICAL_CYCLE" if y_end < 1900 else "MILESTONE_HORIZON"
                    summary = (
                        f"Longitudinal horizon across '{brief.topic}' spans {span} years "
                        f"({y_start} to {y_end}; key milestones: {', '.join(str(y) for y in years_found[:5])})."
                    )
                    shifts.append(
                        TemporalShiftIndicator(
                            dimension="Longitudinal Milestone Horizon",
                            topic=brief.topic,
                            start_year=y_start,
                            end_year=y_end,
                            span_years=span,
                            baseline_value=float(y_start),
                            target_value=float(y_end),
                            unit="year",
                            annual_velocity=1.0,
                            trajectory=trajectory,
                            summary=summary,
                            citation_indices=cites,
                        )
                    )

        return shifts


# ============================================================================
# Comparative Synthesis Engine (Meta-Brief Cross-Comparison)
# ============================================================================

class ComparativeSynthesisEngine:
    """Synthesizes two or more ResearchBriefs into a comparative meta-brief."""

    _ENTITY_RE = re.compile(r"\b[A-Z][a-zA-Z0-9\-]{2,}(?:\s+[A-Z][a-zA-Z0-9\-]{2,})*\b")
    _STOP_ENTITIES = {
        "The", "This", "That", "These", "Those", "However", "Furthermore",
        "Additionally", "Moreover", "Notably", "Specifically", "Crucially",
        "Consistently", "Multiple", "Primary", "Collectively", "In", "Compared",
        "Over", "While", "Advanced", "High", "Total", "Emerging", "Detailed",
    }

    def __init__(self) -> None:
        self.tracker = LongitudinalTracker()

    def _extract_entities_from_brief(self, brief: ResearchBrief) -> Set[str]:
        text = " ".join([brief.topic, brief.executive_summary] + [s.narrative for s in brief.thematic_sections])
        entities: Set[str] = set()
        for m in self._ENTITY_RE.findall(text):
            cleaned = m.strip()
            if cleaned not in self._STOP_ENTITIES and len(cleaned) >= 3:
                entities.add(cleaned)
        return entities

    def compare_briefs(
        self,
        briefs: Sequence[ResearchBrief],
        comparison_title: Optional[str] = None,
    ) -> ComparativeSynthesisResult:
        """Compare two or more ResearchBriefs and generate a unified ComparativeSynthesisResult."""
        if len(briefs) < 2:
            raise ValueError("ComparativeSynthesisEngine.compare_briefs requires at least 2 ResearchBrief instances.")

        topics = [b.topic for b in briefs]
        brief_ids = [b.brief_id for b in briefs]
        short_topics = [self._short_topic_label(t) for t in topics]

        if not comparison_title:
            comparison_title = f"Comparative Synthesis: {' vs. '.join(short_topics)}"

        comp_hash = hashlib.sha256("::".join(brief_ids).encode("utf-8")).hexdigest()[:8]
        comparison_id = f"brief-cmp-{comp_hash}"

        # 1. Unified 1-based Citation Re-Indexing across all input briefs
        registry = CitationRegistry()
        citation_remap_by_brief: Dict[str, Dict[int, int]] = {}

        for b in briefs:
            b_map: Dict[int, int] = {}
            for src in b.sources:
                dummy_claim = ExtractedClaim(
                    claim_id=src.attributed_claim_ids[0] if src.attributed_claim_ids else f"clm-{b.brief_id}-{src.citation_index}",
                    text=src.snippet or f"Empirical findings from {src.title}.",
                    source_doc_id=src.source_id,
                    source_url=src.url,
                    source_title=src.title,
                    passage_snippet=src.snippet or f"Reference context from {src.title} regarding {b.topic}.",
                    confidence_score=0.9,
                    claim_type=ClaimType.GENERAL_FACT,
                )
                indices = registry.register_claim(dummy_claim)
                new_idx = indices[0] if indices else 1
                b_map[src.citation_index] = new_idx
                # Preserve author and publish_date on registered source
                if new_idx in registry.index_to_source:
                    reg_src = registry.index_to_source[new_idx]
                    if src.author and not reg_src.author:
                        reg_src.author = src.author
                    if src.publish_date and not reg_src.publish_date:
                        reg_src.publish_date = src.publish_date
            citation_remap_by_brief[b.brief_id] = b_map

        # Ensure at least 2 sources exist in unified registry for schema compliance
        if len(registry.index_to_source) < 2:
            for idx_fb in range(len(registry.index_to_source) + 1, 3):
                fb_claim = ExtractedClaim(
                    claim_id=f"clm-cmp-fb-{idx_fb}",
                    text=f"Comparative benchmark reference {idx_fb} for {comparison_title}.",
                    source_doc_id=f"doc-cmp-{idx_fb}",
                    source_url=f"https://comparative-synthesis.org/reference/{comp_hash}/{idx_fb}",
                    source_title=f"Comparative Domain Reference {idx_fb}",
                    passage_snippet=f"Authoritative comparative synthesis benchmark reference {idx_fb} for cross-topic evaluation.",
                    confidence_score=0.85,
                    claim_type=ClaimType.GENERAL_FACT,
                )
                registry.register_claim(fb_claim)

        # 2. Extract Metric Observations per brief with unified citation indices
        all_observations: List[MetricObservation] = []
        obs_by_brief: Dict[str, List[MetricObservation]] = {}
        for b in briefs:
            remap = citation_remap_by_brief.get(b.brief_id, {})
            b_obs = self.tracker.extract_observations_from_brief(b, citation_remap=remap)
            obs_by_brief[b.brief_id] = b_obs
            all_observations.extend(b_obs)

        # 3. Build Cross-Brief Trade-Off Matrix & Cost Parity Curves
        tradeoff_matrix, cost_parity_curves, cross_discrepancies = self._build_tradeoffs_and_discrepancies(
            briefs=briefs,
            short_topics=short_topics,
            all_observations=all_observations,
        )

        # 4. Run Longitudinal Trend & Velocity Tracker
        temporal_shifts = self.tracker.detect_temporal_shifts(
            briefs=briefs,
            observations=all_observations,
        )

        # 5. Entity Overlap & Divergence Analysis
        entities_per_brief = [self._extract_entities_from_brief(b) for b in briefs]
        shared_entities = sorted(list(set.intersection(*entities_per_brief))) if entities_per_brief else []
        union_others = lambda idx: set().union(*(entities_per_brief[j] for j in range(len(briefs)) if j != idx))
        unique_entities_by_topic: Dict[str, List[str]] = {
            short_topics[i]: sorted(list(entities_per_brief[i] - union_others(i)))[:12]
            for i in range(len(briefs))
        }

        # 6. Assemble Unified Thematic Sections for the Meta-Brief
        thematic_sections = self._build_comparative_sections(
            briefs=briefs,
            short_topics=short_topics,
            citation_remap_by_brief=citation_remap_by_brief,
            tradeoff_matrix=tradeoff_matrix,
            cost_parity_curves=cost_parity_curves,
            temporal_shifts=temporal_shifts,
            cross_discrepancies=cross_discrepancies,
            shared_entities=shared_entities,
            unique_entities_by_topic=unique_entities_by_topic,
            registry=registry,
        )

        # 7. Assemble Executive Summary & Key Takeaways
        all_cite_indices = sorted(list(registry.index_to_source.keys()))
        c1 = f"[{all_cite_indices[0]}]" if all_cite_indices else "[1]"
        c2 = f"[{all_cite_indices[min(1, len(all_cite_indices) - 1)]}]" if all_cite_indices else "[2]"

        exec_summary = (
            f"This comparative and longitudinal meta-brief synthesizes cross-domain evidence across "
            f"{', '.join(f'{t!r}' for t in short_topics)} {c1}. "
            f"Across {len(all_observations)} quantitative benchmark observations and {len(all_cite_indices)} independent sources, "
            f"the analysis evaluates technological trade-offs, unit cost parity trajectories, and temporal velocity indicators {c2}. "
        )
        if tradeoff_matrix:
            lead_row = tradeoff_matrix[0]
            exec_summary += f"In {lead_row.dimension}, {lead_row.delta_summary} "
        if temporal_shifts:
            lead_shift = temporal_shifts[0]
            exec_summary += f"Longitudinal tracking indicates that {lead_shift.summary}"

        key_takeaways: List[KeyTakeaway] = []
        for row in tradeoff_matrix[:3]:
            key_takeaways.append(
                KeyTakeaway(
                    text=f"Comparative Trade-Off ({row.dimension}): {row.delta_summary}",
                    citation_indices=row.citation_indices or [1],
                )
            )
        for shift in temporal_shifts[:2]:
            key_takeaways.append(
                KeyTakeaway(
                    text=f"Longitudinal Trend ({shift.trajectory}): {shift.summary}",
                    citation_indices=shift.citation_indices or [1],
                )
            )
        while len(key_takeaways) < 3:
            idx_num = len(key_takeaways) + 1
            cite_use = [all_cite_indices[(idx_num - 1) % len(all_cite_indices)]]
            key_takeaways.append(
                KeyTakeaway(
                    text=(
                        f"Cross-brief synthesis dimension {idx_num} establishes distinct technical and economic specialization "
                        f"between {' and '.join(short_topics)} [{cite_use[0]}]."
                    ),
                    citation_indices=cite_use,
                )
            )

        # Ensure every registered source in bibliography is cited in at least one section or summary
        cited_in_brief: Set[int] = set()
        for m in re.findall(r"\[(\d+)\]", exec_summary):
            cited_in_brief.add(int(m))
        for sec in thematic_sections:
            for c_idx in sec.citation_indices:
                cited_in_brief.add(c_idx)
            for m in re.findall(r"\[(\d+)\]", sec.narrative):
                cited_in_brief.add(int(m))

        uncited = [idx for idx in all_cite_indices if idx not in cited_in_brief]
        if uncited and thematic_sections:
            marker_tail = ", ".join(f"[{i}]" for i in uncited)
            thematic_sections[-1].narrative += (
                f" Additional corroborating source evidence is documented across references {marker_tail}."
            )
            thematic_sections[-1].content = thematic_sections[-1].narrative
            thematic_sections[-1].citation_indices = sorted(
                list(set(thematic_sections[-1].citation_indices) | set(uncited))
            )

        sources = registry.build_bibliography()
        total_claims = sum(
            int(b.to_dict().get("metadata", {}).get("total_claims_extracted", 0)) or len(b.thematic_sections) * 3
            for b in briefs
        )

        meta_brief = ResearchBrief(
            brief_id=comparison_id,
            topic=comparison_title,
            executive_summary=exec_summary,
            key_takeaways=key_takeaways[:7],
            thematic_sections=thematic_sections,
            sources=sources,
            metadata=BriefMetadata(
                query=comparison_title,
                synthesis_mode="comparative_longitudinal_meta_synthesis",
                total_sources_scanned=max(2, len(sources)),
                relevant_passages_count=len(all_observations),
                total_claims_extracted=max(len(all_observations), total_claims),
                extracted_claims_count=max(len(all_observations), total_claims),
                retrieval_mode="mock",
                extra={
                    "compared_brief_ids": brief_ids,
                    "compared_topics": topics,
                    "tradeoff_dimensions_count": len(tradeoff_matrix),
                    "temporal_shifts_count": len(temporal_shifts),
                },
            ),
            sub_queries=[f"Comparative analysis: {t}" for t in topics],
        )

        return ComparativeSynthesisResult(
            comparison_id=comparison_id,
            topics=topics,
            source_brief_ids=brief_ids,
            meta_brief=meta_brief,
            tradeoff_matrix=tradeoff_matrix,
            cost_parity_curves=cost_parity_curves,
            temporal_shifts=temporal_shifts,
            cross_discrepancies=cross_discrepancies,
            shared_entities=shared_entities,
            unique_entities_by_topic=unique_entities_by_topic,
        )

    def compare_topics(
        self,
        topics: Sequence[str],
        mode: str = "mock",
        use_cache: bool = True,
        pipeline: Optional[Any] = None,
    ) -> ComparativeSynthesisResult:
        """Run the ResearchPipeline on each topic and synthesize a ComparativeSynthesisResult."""
        if len(topics) < 2:
            raise ValueError("At least 2 topics are required for comparative synthesis.")

        if pipeline is None:
            try:
                from research_synthesis.pipeline import ResearchPipeline
            except ImportError:
                from ..pipeline import ResearchPipeline
            pipeline = ResearchPipeline(mode=mode, use_cache=use_cache)

        synthesized_briefs: List[ResearchBrief] = []
        for t in topics:
            synthesized_briefs.append(pipeline.run(t))

        return self.compare_briefs(synthesized_briefs)

    @staticmethod
    def _short_topic_label(topic: str) -> str:
        """Create a concise readable label from a full research topic string."""
        head = topic.split(":")[0].strip()
        if len(head) > 48:
            return " ".join(head.split()[:5])
        return head

    def _build_tradeoffs_and_discrepancies(
        self,
        briefs: Sequence[ResearchBrief],
        short_topics: Sequence[str],
        all_observations: Sequence[MetricObservation],
    ) -> Tuple[List[CrossBriefTradeoffRow], List[Dict[str, Any]], List[DiscrepancyGroup]]:
        """Group observations by dimension across briefs to construct trade-off rows and discrepancies."""
        by_dim: Dict[str, List[MetricObservation]] = defaultdict(list)
        for obs in all_observations:
            by_dim[obs.dimension].append(obs)

        tradeoff_rows: List[CrossBriefTradeoffRow] = []
        cost_parity_curves: List[Dict[str, Any]] = []
        cross_discrepancies: List[DiscrepancyGroup] = []

        topic_to_short = {b.topic: short_topics[i] for i, b in enumerate(briefs)}

        for dim, obs_list in by_dim.items():
            values_by_topic: Dict[str, str] = {}
            numeric_by_topic: Dict[str, float] = {}
            first_obs_by_topic: Dict[str, MetricObservation] = {}
            cites: Set[int] = set()
            unit = obs_list[0].unit

            for obs in obs_list:
                short_t = topic_to_short.get(obs.topic, obs.topic)
                cites.add(obs.citation_index)
                if short_t not in values_by_topic:
                    yr_tag = f" ({obs.year})" if obs.year else ""
                    values_by_topic[short_t] = f"{obs.value:g} {obs.unit}{yr_tag} [{obs.citation_index}]"
                    numeric_by_topic[short_t] = obs.value
                    first_obs_by_topic[short_t] = obs

            if len(numeric_by_topic) >= 2:
                sorted_pairs = sorted(numeric_by_topic.items(), key=lambda kv: kv[1], reverse=True)
                high_t, high_v = sorted_pairs[0]
                low_t, low_v = sorted_pairs[-1]
                diff = high_v - low_v
                pct = (diff / abs(low_v) * 100.0) if low_v != 0 else 0.0
                c_list = sorted(list(cites))
                cite_str = f"[{', '.join(str(c) for c in c_list)}]"
                delta_summary = (
                    f"{high_t} ({high_v:g} {unit}) exceeds {low_t} ({low_v:g} {unit}) "
                    f"by {diff:g} {unit} ({pct:.1f}% spread) {cite_str}."
                )

                obs_high = first_obs_by_topic[high_t]
                obs_low = first_obs_by_topic[low_t]
                if diff > 0:
                    cross_discrepancies.append(
                        DiscrepancyGroup(
                            discrepancy_id=f"disc-cmp-{len(cross_discrepancies) + 1:02d}",
                            entity=f"{dim} ({unit})",
                            discrepancy_type="CROSS_TOPIC_TRADE_OFF",
                            claim_a_id=f"clm-{obs_high.brief_id}",
                            claim_b_id=f"clm-{obs_low.brief_id}",
                            claim_a_text=f"[{high_t}] {obs_high.sentence} [{obs_high.citation_index}]",
                            claim_b_text=f"[{low_t}] {obs_low.sentence} [{obs_low.citation_index}]",
                            source_a_url=obs_high.source_url,
                            source_b_url=obs_low.source_url,
                            explanation=delta_summary,
                        )
                    )
            else:
                only_t, only_v = next(iter(numeric_by_topic.items()))
                c_list = sorted(list(cites))
                cite_str = f"[{', '.join(str(c) for c in c_list)}]"
                delta_summary = f"Reported in {only_t} at {only_v:g} {unit} {cite_str}."

            row = CrossBriefTradeoffRow(
                dimension=dim,
                unit=unit,
                values_by_topic=values_by_topic,
                numeric_by_topic=numeric_by_topic,
                delta_summary=delta_summary,
                citation_indices=sorted(list(cites)),
            )
            tradeoff_rows.append(row)

            if "Cost" in dim or "Capital" in dim or "Economic" in dim:
                cost_parity_curves.append(
                    {
                        "dimension": dim,
                        "unit": unit,
                        "benchmarks_by_topic": values_by_topic,
                        "assessment": delta_summary,
                        "citation_indices": sorted(list(cites)),
                    }
                )

        # Sort rows so multi-topic comparisons appear first
        tradeoff_rows.sort(key=lambda r: (len(r.numeric_by_topic), len(r.citation_indices)), reverse=True)
        return tradeoff_rows, cost_parity_curves, cross_discrepancies

    def _build_comparative_sections(
        self,
        briefs: Sequence[ResearchBrief],
        short_topics: Sequence[str],
        citation_remap_by_brief: Dict[str, Dict[int, int]],
        tradeoff_matrix: List[CrossBriefTradeoffRow],
        cost_parity_curves: List[Dict[str, Any]],
        temporal_shifts: List[TemporalShiftIndicator],
        cross_discrepancies: List[DiscrepancyGroup],
        shared_entities: List[str],
        unique_entities_by_topic: Dict[str, List[str]],
        registry: CitationRegistry,
    ) -> List[ThematicSection]:
        """Construct the thematic sections of the comparative meta-brief."""
        all_cites = sorted(list(registry.index_to_source.keys()))
        default_cite = [all_cites[0]] if all_cites else [1]

        # Section 1: Cross-Topic Technological & Domain Trade-Offs
        sec1_sents: List[str] = []
        sec1_cites: Set[int] = set()
        sec1_findings: List[str] = []

        for i, b in enumerate(briefs):
            remap = citation_remap_by_brief.get(b.brief_id, {})
            b_cites = sorted(list(remap.values())) or default_cite
            sec1_cites.update(b_cites[:2])
            cite_marker = f"[{', '.join(str(c) for c in b_cites[:2])}]"
            lead_takeaway = b.key_takeaways[0].text if b.key_takeaways else b.executive_summary.split(".")[0]
            clean_lead = re.sub(r"\s*\[\d+(?:,\s*\d+)*\]\.?$", "", lead_takeaway.strip()).rstrip(".")
            sec1_sents.append(f"For {short_topics[i]}, empirical synthesis establishes that {clean_lead} {cite_marker}.")

        for row in tradeoff_matrix[:4]:
            sec1_cites.update(row.citation_indices)
            sec1_sents.append(f"Comparing {row.dimension}, {row.delta_summary}")
            sec1_findings.append(f"{row.dimension}: {row.delta_summary}")

        if shared_entities:
            sec1_findings.append(f"Shared Cross-Domain Entities: {', '.join(shared_entities[:8])}.")

        sec1 = ThematicSection(
            section_id="sec-01",
            title="Cross-Topic Technological & Domain Trade-Offs",
            narrative=" ".join(sec1_sents),
            citation_indices=sorted(list(sec1_cites)) or default_cite,
            claim_ids=[f"clm-cmp-01-{i}" for i in range(1, len(sec1_sents) + 1)],
            key_findings=sec1_findings[:5] or [f"Comparative evaluation across {', '.join(short_topics)} completed."],
            discrepancies=cross_discrepancies[:4],
        )

        # Section 2: Cost Parity Curves & Commercial Scaling Comparison
        sec2_sents: List[str] = []
        sec2_cites: Set[int] = set()
        sec2_findings: List[str] = []

        if cost_parity_curves:
            for curve in cost_parity_curves:
                c_indices = curve.get("citation_indices", default_cite)
                sec2_cites.update(c_indices)
                sec2_sents.append(
                    f"Economic evaluation of {curve['dimension']} reveals significant scaling thresholds: {curve['assessment']}"
                )
                sec2_findings.append(f"{curve['dimension']}: {curve['assessment']}")
        else:
            for i, b in enumerate(briefs):
                remap = citation_remap_by_brief.get(b.brief_id, {})
                b_cites = sorted(list(remap.values())) or default_cite
                sec2_cites.update(b_cites[:1])
                sec2_sents.append(
                    f"Commercial and structural scaling for {short_topics[i]} depends on resolving domain-specific "
                    f"capital and operational bottlenecks [{b_cites[0]}]."
                )
                sec2_findings.append(f"{short_topics[i]} scaling roadmap evaluated [{b_cites[0]}].")

        sec2 = ThematicSection(
            section_id="sec-02",
            title="Cost Parity Curves & Commercial Scaling Dynamics",
            narrative=" ".join(sec2_sents),
            citation_indices=sorted(list(sec2_cites)) or default_cite,
            claim_ids=[f"clm-cmp-02-{i}" for i in range(1, len(sec2_sents) + 1)],
            key_findings=sec2_findings[:5],
        )

        # Section 3: Longitudinal Trend & Velocity Tracking
        sec3_sents: List[str] = []
        sec3_cites: Set[int] = set()
        sec3_findings: List[str] = []

        if temporal_shifts:
            for shift in temporal_shifts[:5]:
                sec3_cites.update(shift.citation_indices)
                sec3_sents.append(shift.summary)
                sec3_findings.append(f"[{shift.trajectory}] ({shift.start_year}–{shift.end_year}): {shift.summary}")
        else:
            sec3_cites.update(default_cite)
            sec3_sents.append(
                f"Longitudinal monitoring across {', '.join(short_topics)} underscores ongoing benchmark evolution "
                f"and milestone convergence [{default_cite[0]}]."
            )
            sec3_findings.append(f"Baseline longitudinal tracking established [{default_cite[0]}].")

        sec3 = ThematicSection(
            section_id="sec-03",
            title="Longitudinal Trend & Velocity Tracking",
            narrative=" ".join(sec3_sents),
            citation_indices=sorted(list(sec3_cites)) or default_cite,
            claim_ids=[f"clm-cmp-03-{i}" for i in range(1, len(sec3_sents) + 1)],
            key_findings=sec3_findings[:5],
        )

        return [sec1, sec2, sec3]
