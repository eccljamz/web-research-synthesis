# Remediation Strategy & Specification: Single-Domain Consensus Corroboration Fix

**Agent**: `explorer_m3_fix_1`  
**Role**: Remediation Explorer 1 (Milestone 3 Thematic Clustering Consensus Domain Fix)  
**Target File**: `src/research_synthesis/synthesis/cluster.py` (`ThematicClusterer._detect_consensus`)  
**Parent / Recipient**: `orchestrator` (`42364d7e-0273-4faa-be7a-22e0c17eecea`)  
**Timestamp**: 2026-10-13T19:27:00Z  
**Verdict**: **REMEDIATION SPECIFICATION READY FOR IMPLEMENTATION**  

---

## 1. Observation

### 1.1 Source Code Observations in `src/research_synthesis/synthesis/cluster.py`
Direct inspection of `src/research_synthesis/synthesis/cluster.py` lines 536–585 (`ThematicClusterer._detect_consensus`):

```python
536:     def _detect_consensus(self, claims: List[ExtractedClaim]) -> List[CorroboratedClaimGroup]:
537:         """Detect claims supported by >= 2 independent source domains."""
538:         groups: List[CorroboratedClaimGroup] = []
539:         seen_primary: Set[str] = set()
540: 
541:         for i, c_i in enumerate(claims):
542:             if c_i.claim_id in seen_primary:
543:                 continue
544: 
545:             all_urls = [c_i.source_url] + c_i.secondary_urls
546:             unique_domains = {self._extract_domain(u) for u in all_urls if self._extract_domain(u)}
547:             supporting_ids: List[str] = []
548: 
549:             # Intra-cluster cross-claim matching
550:             c_i_vec = self.tfidf.transform(c_i.text)
551:             c_i_tokens = set(self.tfidf.tokenize(c_i.text))
552: 
553:             for j, c_j in enumerate(claims):
554:                 if i == j:
555:                     continue
556:                 d_j = self._extract_domain(c_j.source_url)
557:                 c_j_tokens = set(self.tfidf.tokenize(c_j.text))
558:                 jaccard = len(c_i_tokens & c_j_tokens) / max(1, len(c_i_tokens | c_j_tokens))
559:                 c_j_vec = self.tfidf.transform(c_j.text)
560:                 cos_sim = self.tfidf.cosine_similarity(c_i_vec, c_j_vec)
561: 
562:                 # Shared entity bonus
563:                 shared_entities = set(c_i.entities) & set(c_j.entities)
564: 
565:                 if jaccard >= 0.35 or cos_sim >= 0.45 or (shared_entities and (jaccard >= 0.25 or cos_sim >= 0.35)):
566:                     if d_j:
567:                         unique_domains.add(d_j)
568:                     supporting_ids.append(c_j.claim_id)
569:                     all_urls.append(c_j.source_url)
570: 
571:             if len(unique_domains) >= 2 or len(supporting_ids) >= 1:
572:                 seen_primary.add(c_i.claim_id)
573:                 groups.append(
574:                     CorroboratedClaimGroup(
575:                         group_id=f"corrob-{len(groups)+1:02d}",
576:                         primary_claim_id=c_i.claim_id,
577:                         supporting_claim_ids=supporting_ids,
578:                         statement=c_i.text,
579:                         source_urls=sorted(list(set(all_urls))),
580:                         independent_domains=sorted(list(unique_domains)),
581:                         corroboration_score=min(1.0, 0.70 + 0.10 * max(len(unique_domains), len(supporting_ids) + 1)),
582:                     )
583:                 )
584: 
585:         return groups
```

### 1.2 Model Definition in `src/research_synthesis/models.py`
Direct inspection of `src/research_synthesis/models.py` lines 345–355:

```python
345: @dataclass
346: class CorroboratedClaimGroup:
347:     """Group of claims corroborated across >= 2 independent source domains."""
348:     group_id: str
349:     primary_claim_id: str
350:     supporting_claim_ids: List[str]
351:     statement: str
352:     source_urls: List[str]
353:     independent_domains: List[str]
354:     corroboration_score: float = 1.0
```

### 1.3 Domain Extraction Method in `src/research_synthesis/synthesis/cluster.py`
Direct inspection of `src/research_synthesis/synthesis/cluster.py` lines 182–187:

```python
182:     @staticmethod
183:     def _extract_domain(url: str) -> str:
184:         """Extract clean lowercased domain from URL."""
185:         if not url:
186:             return ""
187:         return urlparse(url).netloc.lower()
```

### 1.4 Prior Adversarial and Reviewer Findings
- **Challenger 1 (`challenger_m3_1/handoff.md:80–95`)**:
  - Identified that two claims sharing identical text from the same domain (e.g. `domain.com/a` and `domain.com/b`) result in `len(unique_domains) == 1`, but `len(supporting_ids) == 1`.
  - Condition `len(unique_domains) >= 2 or len(supporting_ids) >= 1` evaluates to `True`, emitting a `CorroboratedClaimGroup` with only 1 independent domain.
  - Recommended replacing lines 571–583 with strict `len(unique_domains) >= 2`, updating `seen_primary` with `supporting_ids`, and computing `corroboration_score = min(1.0, 0.70 + 0.10 * len(unique_domains))`.
- **Reviewer 1 (`reviewer_m3_1/handoff.md:113–118`)**:
  - Challenge 4 (Intra-Domain Consensus Leniency): Recommended tightening the conditional to `if len(unique_domains) >= 2:`.

---

## 2. Logic Chain

### 2.1 Flaw 1: Permissive Disjunction Allows Single-Domain Groups (`or len(supporting_ids) >= 1`)

#### Root Cause Analysis
At line 571:
```python
if len(unique_domains) >= 2 or len(supporting_ids) >= 1:
```
The condition is a logical disjunction ($A \lor B$) where:
- $A \equiv \text{len}(unique\_domains) \ge 2$ (Multi-domain independence requirement)
- $B \equiv \text{len}(supporting\_ids) \ge 1$ (Intra-cluster claim match presence)

#### Failure Execution Trace
Consider two claims $C_1$ and $C_2$ from the same domain:
- Claim $C_1$:
  - `claim_id = "clm-01"`
  - `source_url = "https://example.com/reports/cell-chemistry"`
  - `secondary_urls = []`
  - `text = "Solid-state cells achieve 500 Wh/kg energy density."`
- Claim $C_2$:
  - `claim_id = "clm-02"`
  - `source_url = "https://example.com/blog/2026-roadmap"`
  - `secondary_urls = []`
  - `text = "Next-gen solid-state cells achieve 500 Wh/kg energy density."`

1. **Outer loop iteration $i = 0$ ($C_1$):**
   - `all_urls = ["https://example.com/reports/cell-chemistry"]`
   - `unique_domains = {"example.com"}` ($\text{len} = 1$)
   - `supporting_ids = []`
2. **Inner loop iteration $j = 1$ ($C_2$):**
   - $d_j = \text{urlparse}("https://example.com/blog/2026-roadmap").netloc.lower() = "example.com"$
   - Jaccard and cosine similarity exceed thresholds ($jaccard \ge 0.35$ or $cos\_sim \ge 0.45$).
   - Line 567: `unique_domains.add("example.com")` $\implies$ set remains `{"example.com"}` ($\text{len} = 1$).
   - Line 568: `supporting_ids.append("clm-02")` $\implies$ `supporting_ids = ["clm-02"]` ($\text{len} = 1$).
   - Line 569: `all_urls.append("https://example.com/blog/2026-roadmap")`.
3. **Evaluation at line 571:**
   - $A: \text{len}(unique\_domains) \ge 2 \implies 1 \ge 2 \implies \mathbf{False}$.
   - $B: \text{len}(supporting\_ids) \ge 1 \implies 1 \ge 1 \implies \mathbf{True}$.
   - $A \lor B \implies \mathbf{False} \lor \mathbf{True} \implies \mathbf{True}$.
4. **Resulting Violation:**
   - A `CorroboratedClaimGroup` is constructed:
     - `independent_domains = ["example.com"]` (Count = 1).
     - `corroboration_score = min(1.0, 0.70 + 0.10 * max(1, 1 + 1)) = 0.90`.
   - **Contract Breach 1**: `src/research_synthesis/models.py:348` states:
     `"""Group of claims corroborated across >= 2 independent source domains."""`
   - **Contract Breach 2**: `src/research_synthesis/synthesis/cluster.py:537` docstring states:
     `"""Detect claims supported by >= 2 independent source domains."""`
   - **System Requirement Breach**: Repeating an assertion on the same domain (e.g. corporate blog vs corporate report) does not constitute *cross-source consensus*. It is internal repetition or redundancy. Emitting it as a corroborated finding misleads the synthesis engine into treating single-publisher claims as independently validated facts.

---

### 2.2 Flaw 2: Omitting `supporting_ids` from `seen_primary` Generates Reciprocal Duplicate Groups

#### Root Cause Analysis
At line 572:
```python
seen_primary.add(c_i.claim_id)
```
Only the primary claim $c_i$ is recorded in `seen_primary`. The claims in `supporting_ids` ($c_j$) are **not** marked as seen.

#### Failure Execution Trace
Continuing from the scenario with $C_1$ and $C_2$ (or with 2 distinct domains $D_1$ and $D_2$):
1. In iteration $i = 0$ ($C_1$):
   - $C_1$ is primary.
   - $C_2$ matches and is added to `supporting_ids = ["clm-02"]`.
   - `seen_primary` becomes `{"clm-01"}`.
   - Group `corrob-01` is emitted:
     `primary_claim_id="clm-01"`, `supporting_claim_ids=["clm-02"]`.
2. In iteration $i = 1$ ($C_2$):
   - Line 542: `if c_i.claim_id in seen_primary:`
   - `c_i.claim_id` is `"clm-02"`. Because `"clm-02"` $\notin$ `seen_primary`, iteration $i = 1$ **proceeds**!
   - Outer loop initializes $C_2$ as a new primary claim candidate.
   - Inner loop matches $C_1$ against $C_2$. Because text similarity metrics (Jaccard and Cosine similarity) are symmetric:
     $$\text{Jaccard}(C_2, C_1) = \text{Jaccard}(C_1, C_2), \quad \text{CosSim}(C_2, C_1) = \text{CosSim}(C_1, C_2)$$
   - $C_1$ matches and is added to $C_2$'s `supporting_ids = ["clm-01"]`.
   - Condition triggers again!
   - Group `corrob-02` is emitted:
     `primary_claim_id="clm-02"`, `supporting_claim_ids=["clm-01"]`.
3. **Resulting Violation:**
   - Two reciprocal groups are produced for the identical consensus fact:
     - Group 1: Primary $C_1$, Supporting $[C_2]$.
     - Group 2: Primary $C_2$, Supporting $[C_1]$.
   - This duplicates consensus groups within `cluster.corroborated_claims`, inflating corroboration counts, generating redundant takeaways, and wasting brief narrative budget.

#### Remediation Mechanism
When a corroboration group is formed for $c_i$ with supporting claims `supporting_ids`:
```python
seen_primary.add(c_i.claim_id)
seen_primary.update(supporting_ids)
```
By adding all `supporting_ids` to `seen_primary`, all supporting claims are suppressed from subsequently initiating redundant reciprocal groups.

---

### 2.3 Flaw 3: Inflation of Corroboration Score via `len(supporting_ids) + 1`

#### Root Cause Analysis
At line 581:
```python
corroboration_score = min(1.0, 0.70 + 0.10 * max(len(unique_domains), len(supporting_ids) + 1))
```
This formula computes confidence using `max(len(unique_domains), len(supporting_ids) + 1)`.
- If 3 claims originate from the *same* domain, `len(supporting_ids) + 1 = 3`, while `len(unique_domains) = 1`.
- The score becomes $\min(1.0, 0.70 + 0.10 \times 3) = 1.00$.
- This gives a **perfect 1.0 confidence score** to claims with 0 independent cross-domain corroboration simply because the same publisher repeated the text 3 times!

#### Remediation Mechanism
The corroboration score must reflect **domain independence**, not intra-domain claim repetition:
```python
corroboration_score = min(1.0, 0.70 + 0.10 * len(unique_domains))
```
Properties of the remediated formula:
- For $N = 2$ independent domains: $\text{score} = \min(1.0, 0.70 + 0.10 \times 2) = 0.90$.
- For $N = 3$ independent domains: $\text{score} = \min(1.0, 0.70 + 0.10 \times 3) = 1.00$.
- For $N \ge 3$ independent domains: $\text{score} = 1.00$.
- Because `len(unique_domains) >= 2` is strictly enforced, the score is mathematically guaranteed to fall in the range $[0.90, 1.00]$.

---

## 3. Caveats

1. **Subprocess Execution Restriction**: Direct execution via `run_command` is restricted by environment security policy. The analysis and validation were conducted via static code analysis, AST inspection, control-flow proofs, and self-contained test scenarios.
2. **Secondary URLs Support**: Claims with `secondary_urls` pointing to external domains are natively supported. If a single claim already contains $\ge 2$ independent domains between its `source_url` and `secondary_urls`, it satisfies `len(unique_domains) >= 2`. In that case, `supporting_ids` may be empty (`[]`), and `seen_primary.update(supporting_ids)` executes safely as a no-op.
3. **Asymmetric Similarity Edge Cases**: If claim $C_A$ shares entities with $C_B$ but $C_B$ somehow does not share entities with $C_A$, `set(A) & set(B)` is strictly commutative, guaranteeing bidirectional symmetry. Thus, `seen_primary.update(supporting_ids)` cannot prematurely suppress non-matching claims.

---

## 4. Conclusion & Actionable Code Patch

The single-domain corroboration defect and reciprocal duplication issue in `ThematicClusterer._detect_consensus` have a clear, minimal, and fully contained fix in lines 571–585 of `src/research_synthesis/synthesis/cluster.py`.

### 4.1 Side-by-Side Comparison

#### Current Code (`src/research_synthesis/synthesis/cluster.py:571–584`)
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

#### Remediated Code (`src/research_synthesis/synthesis/cluster.py:571–585`)
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

### 4.2 Unified Diff Patch

```diff
--- a/src/research_synthesis/synthesis/cluster.py
+++ b/src/research_synthesis/synthesis/cluster.py
@@ -571,14 +571,15 @@ class ThematicClusterer:
-            if len(unique_domains) >= 2 or len(supporting_ids) >= 1:
+            if len(unique_domains) >= 2:
                 seen_primary.add(c_i.claim_id)
+                seen_primary.update(supporting_ids)
                 groups.append(
                     CorroboratedClaimGroup(
                         group_id=f"corrob-{len(groups)+1:02d}",
                         primary_claim_id=c_i.claim_id,
                         supporting_claim_ids=supporting_ids,
                         statement=c_i.text,
                         source_urls=sorted(list(set(all_urls))),
                         independent_domains=sorted(list(unique_domains)),
-                        corroboration_score=min(1.0, 0.70 + 0.10 * max(len(unique_domains), len(supporting_ids) + 1)),
+                        corroboration_score=min(1.0, 0.70 + 0.10 * len(unique_domains)),
                     )
                 )
```

The patch has also been saved to:
`C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\explorer_m3_fix_1\consensus_domain.patch`

---

## 5. Verification Method

### 5.1 Verification Test Cases

To verify that the remediation strictly enforces the contract and prevents regressions, the following test cases should be added to `tests/test_tier1_synthesis.py`:

```python
    def test_single_domain_claims_not_corroborated(self):
        """Claims with identical text from the SAME domain must NOT form a CorroboratedClaimGroup."""
        claim_a = ExtractedClaim(
            claim_id="clm-same-01",
            text="Solid-state battery cells demonstrate energy density of 500 Wh/kg in testing.",
            source_doc_id="doc-01",
            source_url="https://same-domain.org/article-alpha",
            source_title="Article Alpha",
            passage_snippet="Demonstrated energy density of 500 Wh/kg in testing.",
            confidence_score=0.90,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Solid-state battery", "500 Wh/kg"],
        )
        claim_b = ExtractedClaim(
            claim_id="clm-same-02",
            text="Solid-state battery cells demonstrate energy density of 500 Wh/kg in testing.",
            source_doc_id="doc-02",
            source_url="https://same-domain.org/article-beta",
            source_title="Article Beta",
            passage_snippet="Demonstrated energy density of 500 Wh/kg in testing.",
            confidence_score=0.90,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Solid-state battery", "500 Wh/kg"],
        )
        # Call private helper directly to isolate consensus logic
        groups = self.clusterer._detect_consensus([claim_a, claim_b])
        self.assertEqual(len(groups), 0, "Single-domain claims must NOT produce a CorroboratedClaimGroup")

    def test_multi_domain_corroboration_no_reciprocal_duplicates(self):
        """Cross-domain matching claims must form exactly ONE group with independent_domains >= 2 and score >= 0.90."""
        claim_a = ExtractedClaim(
            claim_id="clm-multi-01",
            text="Solid-state battery cells demonstrate energy density of 500 Wh/kg in testing.",
            source_doc_id="doc-01",
            source_url="https://domain-alpha.org/article",
            source_title="Domain Alpha Article",
            passage_snippet="Demonstrated energy density of 500 Wh/kg in testing.",
            confidence_score=0.90,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Solid-state battery", "500 Wh/kg"],
        )
        claim_b = ExtractedClaim(
            claim_id="clm-multi-02",
            text="Solid-state battery cells demonstrate energy density of 500 Wh/kg in testing.",
            source_doc_id="doc-02",
            source_url="https://domain-beta.org/article",
            source_title="Domain Beta Article",
            passage_snippet="Demonstrated energy density of 500 Wh/kg in testing.",
            confidence_score=0.90,
            claim_type=ClaimType.QUANTITATIVE,
            entities=["Solid-state battery", "500 Wh/kg"],
        )
        groups = self.clusterer._detect_consensus([claim_a, claim_b])
        self.assertEqual(len(groups), 1, "Must emit exactly ONE group (no reciprocal duplicates)")
        self.assertEqual(groups[0].primary_claim_id, "clm-multi-01")
        self.assertEqual(groups[0].supporting_claim_ids, ["clm-multi-02"])
        self.assertEqual(len(groups[0].independent_domains), 2)
        self.assertEqual(sorted(groups[0].independent_domains), ["domain-alpha.org", "domain-beta.org"])
        self.assertAlmostEqual(groups[0].corroboration_score, 0.90)
```

### 5.2 Independent Execution Command
Once applied by the implementer, run the full test suite:
```powershell
python -m unittest tests/test_tier1_synthesis.py -v
```

### 5.3 Invalidation Conditions
This remediation specification is invalidated if:
1. `_detect_consensus` allows any `CorroboratedClaimGroup` to be constructed with `len(independent_domains) < 2`.
2. A pair of mutually supporting claims generates more than one `CorroboratedClaimGroup` (reciprocal duplicates).
3. The corroboration score formula diverges from domain count or exceeds $[0.0, 1.0]$.
