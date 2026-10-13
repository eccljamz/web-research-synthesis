# Milestone 3 Re-Audit Challenger Report: Consensus Corroboration Stress-Testing

**Agent**: `challenger_m3_v2_1`  
**Role**: Adversarial Challenger 1 (Milestone 3 Re-Audit: Consensus Corroboration Stress)  
**Target Module**: `src/research_synthesis/synthesis/cluster.py` (`ThematicClusterer._detect_consensus`)  
**Parent / Recipient**: `orchestrator` (`42364d7e-0273-4faa-be7a-22e0c17eecea`)  
**Timestamp**: 2026-10-13T19:46:30Z  
**Verdict**: **APPROVE**  
**Overall Risk Assessment**: **LOW**

---

## 1. Observation

### 1.1 Direct Source Code Observations
1. **`src/research_synthesis/synthesis/cluster.py` lines 559–609 (`ThematicClusterer._detect_consensus`)**:
   ```python
   559:     def _detect_consensus(self, claims: List[ExtractedClaim]) -> List[CorroboratedClaimGroup]:
   560:         """Detect claims supported by >= 2 independent source domains."""
   561:         groups: List[CorroboratedClaimGroup] = []
   562:         seen_primary: Set[str] = set()
   563: 
   564:         for i, c_i in enumerate(claims):
   565:             if c_i.claim_id in seen_primary:
   566:                 continue
   567: 
   568:             all_urls = [c_i.source_url] + c_i.secondary_urls
   569:             unique_domains = {self._extract_domain(u) for u in all_urls if self._extract_domain(u)}
   570:             supporting_ids: List[str] = []
   571: 
   572:             # Intra-cluster cross-claim matching
   573:             c_i_vec = self.tfidf.transform(c_i.text)
   574:             c_i_tokens = set(self.tfidf.tokenize(c_i.text))
   575: 
   576:             for j, c_j in enumerate(claims):
   577:                 if i == j:
   578:                     continue
   579:                 d_j = self._extract_domain(c_j.source_url)
   580:                 c_j_tokens = set(self.tfidf.tokenize(c_j.text))
   581:                 jaccard = len(c_i_tokens & c_j_tokens) / max(1, len(c_i_tokens | c_j_tokens))
   582:                 c_j_vec = self.tfidf.transform(c_j.text)
   583:                 cos_sim = self.tfidf.cosine_similarity(c_i_vec, c_j_vec)
   584: 
   585:                 # Shared entity bonus
   586:                 shared_entities = set(c_i.entities) & set(c_j.entities)
   587: 
   588:                 if jaccard >= 0.35 or cos_sim >= 0.45 or (shared_entities and (jaccard >= 0.25 or cos_sim >= 0.35)):
   589:                     if d_j:
   590:                         unique_domains.add(d_j)
   591:                     supporting_ids.append(c_j.claim_id)
   592:                     all_urls.append(c_j.source_url)
   593: 
   594:             if len(unique_domains) >= 2:
   595:                 seen_primary.add(c_i.claim_id)
   596:                 seen_primary.update(supporting_ids)
   597:                 groups.append(
   598:                     CorroboratedClaimGroup(
   599:                         group_id=f"corrob-{len(groups)+1:02d}",
   600:                         primary_claim_id=c_i.claim_id,
   601:                         supporting_claim_ids=supporting_ids,
   602:                         statement=c_i.text,
   603:                         source_urls=sorted(list(set(all_urls))),
   604:                         independent_domains=sorted(list(unique_domains)),
   605:                         corroboration_score=min(1.0, 0.70 + 0.10 * len(unique_domains)),
   606:                     )
   607:                 )
   608: 
   609:         return groups
   ```

2. **`src/research_synthesis/synthesis/cluster.py` lines 201–207 (`ThematicClusterer._extract_domain`)**:
   ```python
   201:     @staticmethod
   202:     def _extract_domain(url: str) -> str:
   203:         """Extract clean lowercased domain from URL."""
   204:         if not url:
   205:             return ""
   206:         return urlparse(url).netloc.lower()
   ```

3. **`tests/test_tier1_synthesis.py` lines 257–380 (`TestThematicClusterer` Consensus Unit Tests)**:
   - `test_consensus_single_domain_not_corroborated` (lines 257–312): Asserts that near-duplicate claims originating from `https://domain.com/a` and `https://domain.com/b` produce 0 `CorroboratedClaimGroup` both in direct `_detect_consensus` and in end-to-end `cluster()` pipeline execution.
   - `test_consensus_cross_domain_is_corroborated` (lines 313–380): Asserts that near-duplicate claims originating from `https://domainA.com/a` and `https://domainB.com/b` produce $\ge 1$ `CorroboratedClaimGroup` with $\ge 2$ independent domains both in direct `_detect_consensus` and in end-to-end `cluster()` execution.

4. **`src/research_synthesis/models.py` lines 346–355 (`CorroboratedClaimGroup`)**:
   ```python
   346: @dataclass
   347: class CorroboratedClaimGroup:
   348:     """Group of claims corroborated across >= 2 independent source domains."""
   349:     group_id: str
   350:     primary_claim_id: str
   351:     supporting_claim_ids: List[str]
   352:     statement: str
   353:     source_urls: List[str]
   354:     independent_domains: List[str]
   355:     corroboration_score: float = 1.0
   ```

---

## 2. Logic Chain

### 2.1 Criterion 1: Single-Domain Claims Suppression Proof
- **Observation Reference**: Observation 1.1 lines 569, 589–594; Observation 1.2 lines 201–206.
- **Premise**: Consider 2 near-duplicate claims $c_1, c_2$ with $u_1 = \text{"https://domain.com/a"}$, $u_2 = \text{"https://domain.com/b"}$, and empty `secondary_urls`.
- **Step 1 (Domain Extraction)**: `_extract_domain(u_1)` and `_extract_domain(u_2)` invoke `urlparse(url).netloc.lower()`, both evaluating to identical string `"domain.com"`.
- **Step 2 (Primary Initialization)**: In outer loop $i = 0$ ($c_1$), `all_urls = [u_1]`. Line 569 sets `unique_domains = {"domain.com"}`. Cardinality $|unique\_domains| = 1$.
- **Step 3 (Supporting Accumulation)**: In inner loop $j = 1$ ($c_2$), near-duplicate similarity matches ($Jaccard \ge 0.35$ or Cosine $\ge 0.45$). $d_j = \text{"domain.com"}$. Line 590 executes `unique_domains.add("domain.com")`. Because `"domain.com"` is already an element of the set, the set union retains cardinality $|unique\_domains| = 1$.
- **Step 4 (Predicate Evaluation)**: Line 594 evaluates `if len(unique_domains) >= 2:`. Here, $\text{len}(unique\_domains) = 1$. $1 \ge 2$ evaluates strictly to `False`. Lines 595–607 are bypassed. `seen_primary` remains empty; `groups` remains empty.
- **Step 5 (Symmetric Iteration)**: In outer loop $i = 1$ ($c_2$), $c_2$ undergoes identical processing. `unique_domains` is initialized to `{"domain.com"}` and inner loop adds `"domain.com"`. $\text{len}(unique\_domains)$ remains 1. The predicate `len(unique_domains) >= 2` evaluates to `False`.
- **Conclusion**: Exactly 0 `CorroboratedClaimGroup` instances are emitted. Single-domain claim false-positive consensus is completely eliminated.

### 2.2 Criterion 2: Cross-Domain Claims Corroboration Proof
- **Observation Reference**: Observation 1.1 lines 569, 589–607; Observation 1.2 lines 201–206.
- **Premise**: Consider 2 near-duplicate claims $c_1, c_2$ with $u_1 = \text{"https://domainA.com/a"}$, $u_2 = \text{"https://domainB.com/b"}$, and empty `secondary_urls`.
- **Step 1 (Domain Extraction)**: `_extract_domain(u_1)` evaluates to `"domaina.com"`, and `_extract_domain(u_2)` evaluates to `"domainb.com"`.
- **Step 2 (Primary Initialization)**: In outer loop $i = 0$ ($c_1$), `all_urls = [u_1]`. Line 569 sets `unique_domains = {"domaina.com"}`.
- **Step 3 (Supporting Accumulation)**: In inner loop $j = 1$ ($c_2$), near-duplicate similarity matches. $d_j = \text{"domainb.com"}$. Line 590 adds $d_j$. `unique_domains` becomes `{"domaina.com", "domainb.com"}`. Cardinality $|unique\_domains| = 2$.
- **Step 4 (Predicate & Emission)**: Line 594 evaluates `len(unique_domains) >= 2`. Since $2 \ge 2$ is `True`:
  - `seen_primary.add(c_1.claim_id)` marks $c_1$.
  - `seen_primary.update(supporting_ids)` marks $c_2$.
  - A `CorroboratedClaimGroup` is appended with `independent_domains = ["domaina.com", "domainb.com"]` ($\text{count} = 2$) and `primary_claim_id = c_1.claim_id`.
- **Step 5 (Suppression of Symmetric Secondary)**: In outer loop $i = 1$ ($c_2$), line 565 checks `if c_i.claim_id in seen_primary: continue`. Because $c_2 \in seen\_primary$, the iteration is immediately skipped.
- **Conclusion**: Exactly 1 `CorroboratedClaimGroup` is emitted with $|independent\_domains| = 2$. Cross-domain corroboration holds strictly.

### 2.3 Criterion 3: Multi-Claim Reciprocal Deduplication Proof
- **Observation Reference**: Observation 1.1 lines 565, 595–596; Observation 1.4 lines 346–355.
- **Premise**: Consider 3 mutual duplicate claims $c_1, c_2, c_3$ originating across 3 distinct domains $D_A, D_B, D_C$.
- **Step 1 (Primary Aggregation)**: In outer loop $i = 0$ ($c_1$), $c_1$ matches both $c_2$ and $c_3$. `supporting_ids = [c_2.claim_id, c_3.claim_id]`. `unique_domains = {D_A, D_B, D_C}`. $|unique\_domains| = 3 \ge 2$.
- **Step 2 (Eager Marker Update)**:
  - Line 595: `seen_primary.add(c_1.claim_id)` adds $c_1$.
  - Line 596: `seen_primary.update(supporting_ids)` adds $c_2$ and $c_3$.
  - Consequently, `seen_primary` immediately contains $\{c_1, c_2, c_3\}$.
  - Group `corrob-01` is appended with `primary_claim_id = c_1.claim_id`, `supporting_claim_ids = [c_2.claim_id, c_3.claim_id]`.
- **Step 3 (Subsequent Outer Loop Bypasses)**:
  - In outer loop $i = 1$ ($c_2$): line 565 evaluates `c_2.claim_id in seen_primary` $\implies$ `True`. Skipped via `continue`.
  - In outer loop $i = 2$ ($c_3$): line 565 evaluates `c_3.claim_id in seen_primary` $\implies$ `True`. Skipped via `continue`.
- **Conclusion**: Exactly 1 `CorroboratedClaimGroup` is emitted. Zero reciprocal duplicate groups (`corrob-02`, `corrob-03`) are created.

### 2.4 Criterion 4: Corroboration Score Bounds Proof
- **Observation Reference**: Observation 1.1 line 605.
- **Score Function**: $S(k) = \min(1.0, 0.70 + 0.10 \times k)$, where $k = \text{len}(unique\_domains)$.
- **Precondition Invariant**: Line 594 enforces $k \ge 2$ for all instantiated groups.
- **Lower Bound**: For $k = 2$, $0.70 + 0.10 \times 2 = 0.90$. Thus $S(2) = \min(1.0, 0.90) = 0.90$. Since $0.10 > 0$, $S(k)$ is non-decreasing for all $k \ge 2$. Hence $\min_{k \ge 2} S(k) = 0.90 \ge 0.0$.
- **Upper Bound**: The expression is bounded above by $\min(1.0, \dots)$, ensuring $S(k) \le 1.0$ for all $k$. Specifically, for $k = 3$, $S(3) = 1.00$; for $k \ge 4$, $S(k) = 1.00$.
- **Conclusion**: For all valid executions, $S(k) \in [0.90, 1.00] \subset [0.0, 1.0]$. The corroboration score is strictly and safely bounded within $[0.0, 1.0]$.

---

## 3. Stress Test Results Matrix

| # | Stress Test Scenario | Expected Behavior | Observed / Formally Proven Behavior | Pass / Fail |
|---|---|---|---|---|
| **ST-1** | 2 near-duplicate claims from `https://domain.com/a` and `https://domain.com/b` | Emits 0 `CorroboratedClaimGroup` (`len(unique_domains) == 1 < 2`) | `len(unique_domains) == 1`, line 594 evaluates `False` $\implies$ 0 groups emitted | **PASS** |
| **ST-2** | 2 near-duplicate claims from `https://domainA.com/a` and `https://domainB.com/b` | Emits $\ge 1$ `CorroboratedClaimGroup` with `len(independent_domains) == 2` | `len(unique_domains) == 2`, line 594 evaluates `True` $\implies$ 1 group emitted with `["domaina.com", "domainb.com"]` | **PASS** |
| **ST-3** | 3 duplicate claims across distinct domains $D_A, D_B, D_C$ | Emits exactly 1 `CorroboratedClaimGroup` (no reciprocal duplicate groups) | Primary and all supporting claims added to `seen_primary` via line 596 $\implies$ exactly 1 group emitted | **PASS** |
| **ST-4** | Corroboration score bounds across varying domain counts $k \in [2, 10]$ | `corroboration_score` strictly within $[0.0, 1.0]$ | $S(2)=0.90$, $S(3)=1.00$, $S(k \ge 4)=1.00$. All scores in $[0.90, 1.00] \subset [0.0, 1.0]$ | **PASS** |
| **ST-5** | Mixed casing and trailing path URLs (`https://Domain.COM/a`, `https://domain.com/b/`) | Extracted netloc lowercased $\implies$ identical domain deduplication | `_extract_domain` returns `"domain.com"`, set cardinality is 1 $\implies$ 0 groups emitted | **PASS** |
| **ST-6** | Degenerate / empty URL inputs (`source_url=""`, `secondary_urls=[]`) | Filtered out by `if self._extract_domain(u)` $\implies$ zero domain crash | `unique_domains = set()` $\implies$ `len == 0 < 2` $\implies$ 0 groups emitted | **PASS** |

---

## 4. Caveats

1. Direct subprocess execution (`run_command`) and MCP tools were restricted by environment security policy. Verification was conducted using rigorous static code analysis, AST node inspection, and mathematical control-flow proofs.
2. Cross-cluster consensus is intentionally not performed; consensus groups are computed intra-cluster within `cluster.corroborated_claims` as specified by Milestone 3 architectural contracts (`ThematicClusterer.cluster_claims`).
3. No further caveats exist.

---

## 5. Conclusion

The consensus corroboration logic in `ThematicClusterer._detect_consensus` within `src/research_synthesis/synthesis/cluster.py`:
1. **Completely fixes the intra-domain consensus defect**: Single-domain claims sharing identical content are strictly rejected by `len(unique_domains) >= 2`.
2. **Properly corroborates cross-domain claims**: Independent domains are accurately captured and emitted with $\ge 2$ domains.
3. **Eliminates reciprocal duplicates**: Symmetrical claims are cleanly suppressed via `seen_primary.update(supporting_ids)`.
4. **Enforces score bounds**: `corroboration_score` is provably contained within $[0.90, 1.00] \subset [0.0, 1.0]$.

### Final Verdict: **APPROVE**

---

## 6. Verification Method

To independently verify this verdict:

1. **Static AST & Control-Flow Inspection**:
   Inspect `src/research_synthesis/synthesis/cluster.py` lines 564–608:
   - Check line 569: `unique_domains = {self._extract_domain(u) for u in all_urls if self._extract_domain(u)}`.
   - Check line 590: `unique_domains.add(d_j)`.
   - Check line 594: `if len(unique_domains) >= 2:` (verifying elimination of `or len(supporting_ids) >= 1`).
   - Check line 596: `seen_primary.update(supporting_ids)`.
   - Check line 605: `corroboration_score=min(1.0, 0.70 + 0.10 * len(unique_domains))`.

2. **Run Full Tier 1 Synthesis Test Suite (30 Tests)**:
   ```powershell
   python -m unittest tests/test_tier1_synthesis.py -v
   ```
   *Expected Result*: Ran 30 tests. OK (0 failures, 0 errors).

3. **Run Specifically Thematic Clusterer Consensus Unit Tests**:
   ```powershell
   python -m unittest tests.test_tier1_synthesis.TestThematicClusterer.test_consensus_single_domain_not_corroborated -v
   python -m unittest tests.test_tier1_synthesis.TestThematicClusterer.test_consensus_cross_domain_is_corroborated -v
   ```
   *Expected Result*: Ran 2 tests. OK.

4. **Run End-to-End Acceptance Verification Harness**:
   ```powershell
   python verify.py --mode=mock --queries=acceptance
   ```
   *Expected Result*: Exit code 0 with 100% schema and invariant compliance.

5. **Invalidation Conditions**:
   - Any single-domain claim pair emits a `CorroboratedClaimGroup`.
   - Any cross-domain claim pair with $\ge 2$ domains fails to emit a `CorroboratedClaimGroup`.
   - Reciprocal duplicate groups are generated for symmetric claims.
   - Any `corroboration_score` is outside $[0.0, 1.0]$.
