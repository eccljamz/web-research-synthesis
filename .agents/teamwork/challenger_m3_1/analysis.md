# Adversarial Stress Analysis: ThematicClusterer (Milestone 3)

**Target**: `src/research_synthesis/synthesis/cluster.py` (`ThematicClusterer`)  
**Analyst**: Adversarial Challenger 1 (`challenger_m3_1`)  
**Timestamp**: 2026-10-13T19:20:00Z  

---

## 1. Executive Summary

This report delivers the empirical stress-testing results for `ThematicClusterer` across four critical operational dimensions:
1. **Section Bounds Enforcement** ($2 \le K \le 5$) under edge conditions: **PASS**
2. **Consensus Detection** across independent domains vs. identical domains: **FAIL (BUG IDENTIFIED)**
3. **Discrepancy Detection** for numerical variation and polar conflict: **PASS**
4. **Cluster Title Generation** (length, non-emptiness, zero prohibited tokens): **PASS**

### Verdict: **REQUEST_CHANGES**
A functional bug exists in `ThematicClusterer._detect_consensus` at line 571:
```python
if len(unique_domains) >= 2 or len(supporting_ids) >= 1:
```
Because of `or len(supporting_ids) >= 1`, claims originating from the **exact same domain** (e.g. `domain.com/a` and `domain.com/b`) are improperly classified as `CorroboratedClaimGroup` with `len(independent_domains) == 1`. This violates the contract that consensus requires multi-domain corroboration ($\ge 2$ distinct domains).

---

## 2. In-Depth Stress-Test Analysis by Dimension

### Dimension 1: Section Bounds ($2 \le K \le 5$)

#### Test 1.1: Empty Input (0 claims)
- **Input**: `claims = []`, `sub_queries = [...]` or `[]`, `topic = "..."`
- **Control-Flow Trace**:
  - `ThematicClusterer.cluster_claims` line 211:
    ```python
    if not claims_list:
        return self._handle_empty_claims(sub_queries_list, topic)
    ```
  - `_handle_empty_claims` lines 692–703 constructs exactly 2 scaffolding clusters:
    - `ClaimCluster(cluster_id="sec-01", title=c1_title, facet=c1_facet, claims=[])`
    - `ClaimCluster(cluster_id="sec-02", title=c2_title, facet=c2_facet, claims=[])`
- **Result**: $K = 2$, strictly satisfying $2 \le K \le 5$.
- **Status**: **PASS**

#### Test 1.2: Singleton (1 claim)
- **Input**: `claims = [c1]`, `sub_queries = [...]` or `[]`, `topic = "..."`
- **Control-Flow Trace**:
  - `ThematicClusterer.cluster_claims` line 215:
    ```python
    if len(claims_list) == 1:
        return self._handle_single_claim(claims_list[0], sub_queries_list, topic)
    ```
  - `_handle_single_claim` lines 705–727 constructs exactly 2 clusters:
    - `sec-01` containing `[c1]` with `key_entities = list(c1.entities)`
    - `sec-02` containing `[]` as complementary scaffolding
- **Result**: $K = 2$, strictly satisfying $2 \le K \le 5$.
- **Status**: **PASS**

#### Test 1.3: Uniform Cluster Bisection (20 identical claims)
- **Input**: 20 claims with identical proposition text and identical entities.
- **Control-Flow Trace**:
  - In `_primary_subquery_grouping`, all 20 claims map to the same bucket.
  - Initial `clusters` has length 1.
  - In `_enforce_section_bounds` lines 442–448:
    ```python
    if len(non_empty) < self.min_sections:
        if len(non_empty) == 1:
            single = non_empty[0]
            if len(single.claims) >= 2:
                sub1, sub2 = self._bisect_cluster(single)
                non_empty = [sub1, sub2]
    ```
  - In `_bisect_cluster` lines 466–505:
    - Partition heuristic 1 checks `quant_claims and other_claims`. Since all claims are identical, all belong to the same type, so this is skipped.
    - Partition heuristic 2 sorts by cosine similarity to `claims[0]` and bisects at `mid = max(1, 20 // 2) = 10`.
    - Cluster `c1` receives 10 claims; cluster `c2` receives 10 claims.
    - Returned `non_empty` has length 2.
- **Result**: $K = 2$, strictly satisfying $2 \le K \le 5$.
- **Status**: **PASS**

#### Test 1.4: Agglomerative Merging (30 claims across 8 subqueries)
- **Input**: 30 distinct claims mapped across 8 distinct subqueries.
- **Control-Flow Trace**:
  - Primary subquery grouping generates 8 initial clusters (`len(non_empty) == 8`).
  - In `_enforce_section_bounds` lines 423–440:
    ```python
    while len(non_empty) > self.max_sections:
        # compute pairwise centroid cosine similarities
        # merge closest pair (target.claims.extend(source.claims))
        # pop merged cluster
    ```
  - Loop executes 3 times ($8 \to 7 \to 6 \to 5$).
  - Loop terminates strictly when `len(non_empty) == 5`.
  - Step 3 re-indexes cluster IDs to `sec-01` .. `sec-05`.
- **Result**: $K = 5$, strictly satisfying $2 \le K \le 5$.
- **Status**: **PASS**

---

### Dimension 2: Consensus Detection (Multi-Domain vs Single-Domain)

#### Test 2.1: Multi-Domain Corroboration
- **Input**:
  - Claim A: `text = "Solid state batteries achieve 500 Wh/kg."`, `source_url = "https://nature.com/article"`
  - Claim B: `text = "Solid state batteries achieve 500 Wh/kg."`, `source_url = "https://energy.gov/report"`
- **Control-Flow Trace**:
  - Claim A initiates `unique_domains = {"nature.com"}`.
  - In inner loop against Claim B, `d_j = "energy.gov"`, `jaccard = 1.0 >= 0.35`.
  - `unique_domains.add("energy.gov")` $\implies$ `unique_domains = {"nature.com", "energy.gov"}`.
  - `supporting_ids = [claim_b_id]`.
  - Condition at line 571: `len(unique_domains) >= 2` evaluates to `True`.
  - `CorroboratedClaimGroup` emitted with `independent_domains = ["energy.gov", "nature.com"]`.
- **Result**: Grouped into `CorroboratedClaimGroup`.
- **Status**: **PASS**

#### Test 2.2: Single-Domain Claims (Negative Constraint)
- **Input**:
  - Claim A: `text = "Solid state batteries achieve 500 Wh/kg."`, `source_url = "https://domain.com/path1"`, `secondary_urls = []`
  - Claim B: `text = "Solid state batteries achieve 500 Wh/kg."`, `source_url = "https://domain.com/path2"`, `secondary_urls = []`
- **Control-Flow Trace**:
  - In `_detect_consensus` lines 545–571:
    ```python
    all_urls = [c_i.source_url] + c_i.secondary_urls
    unique_domains = {self._extract_domain(u) for u in all_urls if self._extract_domain(u)}
    # unique_domains is {"domain.com"} (size 1)

    for j, c_j in enumerate(claims):
        # jaccard == 1.0 >= 0.35
        if d_j:
            unique_domains.add(d_j)  # Still {"domain.com"} (size 1)
        supporting_ids.append(c_j.claim_id)  # supporting_ids is [claim_b_id] (size 1)
        all_urls.append(c_j.source_url)

    if len(unique_domains) >= 2 or len(supporting_ids) >= 1:
        # HERE IS THE BUG:
        # len(unique_domains) is 1 (False)
        # BUT len(supporting_ids) is 1 (True)
        # Evaluates to True!
    ```
  - Emits `CorroboratedClaimGroup` with:
    - `independent_domains = ["domain.com"]` (Only 1 domain!)
    - `corroboration_score = 0.90`
- **Violation**:
  - Dispatch requirement: *"Claims from identical domain (e.g. `domain.com/a` and `domain.com/b`) -> must NOT count as multi-domain corroborated"*.
  - `models.py:347`: `CorroboratedClaimGroup` docstring: *"Group of claims corroborated across >= 2 independent source domains."*
  - `cluster.py:537`: `_detect_consensus` docstring: *"Detect claims supported by >= 2 independent source domains."*
  - The current code improperly emits a `CorroboratedClaimGroup` for intra-domain duplicates.
- **Status**: **FAIL (DEFECT)**

---

### Dimension 3: Discrepancy Detection

#### Test 3.1: Numerical Variance (500 Wh/kg vs 350 Wh/kg)
- **Input**:
  - Claim 1: `text = "Cell energy density reaches 500 Wh/kg."`, `claim_type = QUANTITATIVE`, `entities = ["Cell"]`
  - Claim 2: `text = "Cell energy density is limited to 350 Wh/kg."`, `claim_type = QUANTITATIVE`, `entities = ["Cell"]`
- **Control-Flow Trace**:
  - `METRIC_REGEX` extracts `("500", "Wh/kg")` and `("350", "Wh/kg")`.
  - Both unit strings match (`"wh/kg" == "wh/kg"`).
  - $v_1 = 500.0, v_2 = 350.0 \implies \text{rel\_diff} = |500 - 350| / 500 = 0.30 > 0.15$.
  - Line 642 appends `DiscrepancyGroup(discrepancy_type="NUMERICAL_VARIATION", entity="Cell", explanation="Numerical variation on Wh/kg: 500.0 vs 350.0 (30.0% difference).")`.
- **Status**: **PASS**

#### Test 3.2: Polar Conflict ("increased capacity" vs "declined capacity")
- **Input**:
  - Claim 1: `text = "The cell demonstrated increased capacity over 500 cycles."`, `entities = ["cell"]`
  - Claim 2: `text = "The cell demonstrated declined capacity over 500 cycles."`, `entities = ["cell"]`
- **Control-Flow Trace**:
  - `words1` intersects `POLAR_POSITIVE` (`"increased"`).
  - `words2` intersects `POLAR_NEGATIVE` (`"declined"`).
  - `shared_entities` is `{"cell"}`.
  - Condition `(shared_entities or tok_overlap) and ((has_pos1 and has_neg2) or ...)` evaluates to `True`.
  - Line 610 appends `DiscrepancyGroup(discrepancy_type="POLAR_CONFLICT", entity="cell", explanation="Conflicting directional assertions detected on entity 'cell'.")`.
- **Status**: **PASS**

---

### Dimension 4: Title Generation Stress-Testing
- **Constraints**: Non-empty, length $\ge 3$, zero prohibited placeholder words (`TODO`, `TBD`, `placeholder`, `Untitled`, `FIXME`, `N/A`, `insert here`, `asdf`).
- **Control-Flow Audit**:
  - Subquery-derived templates: all templates in `FACET_TITLE_TEMPLATES` range from 40 to 54 characters.
  - Entity-augmented titles: `f"{ent_str}: {base_template.split('&')[0].strip()}"` ($\ge 15$ characters).
  - Centroid-term titles: `f"{top_terms}: Key Thematic Findings"` ($\ge 20$ characters).
  - Generic chapter fallback: `f"Thematic Chapter {index}: Analysis of {topic[:40]}"` ($\ge 25$ characters).
  - Empty/single-claim handlers: `f"{topic}: Core Foundations"`, `f"{topic}: Strategic Context & Horizons"` ($\ge 20$ characters).
  - Regex check for prohibited tokens: **0 occurrences found across all title generator branches**.
- **Status**: **PASS**

---

## 3. Required Mitigation / Patch

To resolve Defect 2.2, `src/research_synthesis/synthesis/cluster.py` must be updated at line 571:

### Current Defective Code (Lines 571–583):
```python
            if len(unique_domains) >= 2 or len(supporting_ids) >= 1:
                seen_primary.add(c_i.claim_id)
                groups.append(
                    CorroboratedClaimGroup(
                        group_id=f"corrob-{len(groups)+1:02d}",
                        primary_claim_id=c_i.claim_id,
                        supporting_claim_ids=supporting_ids,
                        statement=c_i.text,
                        source_urls=sorted(list(set(all_urls))),
                        independent_domains=sorted(list(unique_domains)),
                        corroboration_score=min(1.0, 0.70 + 0.10 * max(len(unique_domains), len(supporting_ids) + 1)),
                    )
                )
```

### Required Fix:
```python
            if len(unique_domains) >= 2:
                seen_primary.add(c_i.claim_id)
                seen_primary.update(supporting_ids)
                groups.append(
                    CorroboratedClaimGroup(
                        group_id=f"corrob-{len(groups)+1:02d}",
                        primary_claim_id=c_i.claim_id,
                        supporting_claim_ids=supporting_ids,
                        statement=c_i.text,
                        source_urls=sorted(list(set(all_urls))),
                        independent_domains=sorted(list(unique_domains)),
                        corroboration_score=min(1.0, 0.70 + 0.10 * len(unique_domains)),
                    )
                )
```

This ensures:
1. Claims sharing identical content from $\ge 2$ distinct domains are properly grouped into `CorroboratedClaimGroup`.
2. Claims from identical domains (`domain.com/a` and `domain.com/b`) strictly evaluate `len(unique_domains) == 1 < 2` and are **NOT** added to `CorroboratedClaimGroup`.
3. Adding `seen_primary.update(supporting_ids)` prevents duplicate reciprocal groups.
