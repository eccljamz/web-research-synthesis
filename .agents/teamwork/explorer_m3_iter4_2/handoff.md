# Milestone 3 Iteration 4 Remediation Explorer 2 Handoff Report: Unit Extraction & Discrepancy Scoping

**Agent**: `explorer_m3_iter4_2`  
**Role**: Remediation Explorer 2 (Milestone 3 Iteration 4 Unit Extraction & Discrepancy Scoping)  
**Parent / Recipient**: `orchestrator` (`42364d7e-0273-4faa-be7a-22e0c17eecea`)  
**Working Directory**: `C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\explorer_m3_iter4_2`  
**Target Code**: `src/research_synthesis/synthesis/cluster.py` (lines 80–110, 675–715)  
**Target Test Suite**: `tests/test_tier1_synthesis.py` (lines 380–530)  
**Timestamp**: 2026-10-13T20:22:00Z  

---

## Executive Summary

A comprehensive static analysis, lexical trace simulation, and control-flow proof was conducted on unit extraction and numerical discrepancy detection in `cluster.py`. The findings confirm:
1. **Zero Side Effects on Existing Units**: Every existing unit (`Wh/kg`, `Wh/L`, `°C`, `tons`, `GW`, `MW`, `kWh`, `nm`, `mS/cm`, `USD`, `EUR`, as well as `percentage`, `percent`, `pct`, `billion`, `million`, `trillion`, `dollar`, `dollars`) ends in an ASCII word character ($\in \w$). When $c_{\text{last}} \in \w$, the trailing word boundary assertion `\b` is mathematically equivalent to negative lookahead `(?!\w)` across all terminal contexts (whitespace, punctuation, EOF, and word rejection). Replacing `\b` with `(?!\w)` has **identically zero side effects** on all existing units while fixing extraction for non-word symbol units (`%` and `$`).
2. **Symmetric Unit Normalization**: `UNIT_ALIASES` and `_normalize_unit` partition synonyms into canonical equivalence classes (`% / pct / percentage / percent` $\to$ `"percent"`; `$ / dollar / dollars / usd` $\to$ `"usd"`) with 100% mathematical symmetry and zero cross-family collision.
3. **Preservation of Raw Formatting**: `_detect_discrepancies` compares units strictly via `u1_norm == u2_norm`, but formats `ent_name` fallback (`f"Metric ({unit1})"`) and `explanation` (`f"Numerical variation on {unit1}: ..."`) using the raw captured `{unit1}`, preserving original source casing and notation.

---

## 1. Observation

### 1.1 Current `METRIC_REGEX`, `UNIT_ALIASES`, and `_normalize_unit` in `cluster.py` (Lines 83–105)
Direct inspection of `src/research_synthesis/synthesis/cluster.py`:
```python
83: METRIC_REGEX = re.compile(
84:     r"\b(\d+(?:[.,]\d+)?)\s*(%|percentage|percent|pct|billion|million|trillion|USD|\$|dollars|dollar|EUR|Wh/kg|Wh/L|°C|tons|GW|MW|kWh|nm|mS/cm)?\b",
85:     re.IGNORECASE,
86: )
87: 
88: # Canonical unit alias normalization mapping
89: UNIT_ALIASES: Dict[str, str] = {
90:     "%": "percent",
91:     "pct": "percent",
92:     "percentage": "percent",
93:     "$": "usd",
94:     "dollar": "usd",
95:     "dollars": "usd",
96: }
97: 
98: 
99: def _normalize_unit(unit: Optional[str]) -> str:
100:     """Normalize a metric unit string to its canonical alias in lowercase."""
101:     if not unit:
102:         return ""
103:     u = unit.lower().strip()
104:     return UNIT_ALIASES.get(u, u)
```
- Line 84: `METRIC_REGEX` terminates with trailing `\b`.
- Lines 89–96: `UNIT_ALIASES` maps `"%"`, `"pct"`, `"percentage"` to `"percent"`, and `"$"`, `"dollar"`, `"dollars"` to `"usd"`.
- Lines 99–105: `_normalize_unit` returns `""` if falsy; otherwise lowercases, strips, and consults `UNIT_ALIASES`.

### 1.2 Numerical Discrepancy Detection Branch in `cluster.py` (Lines 673–710)
Direct inspection of `src/research_synthesis/synthesis/cluster.py`:
```python
673:                 if (
674:                     c1.claim_type == ClaimType.QUANTITATIVE
675:                     and c2.claim_type == ClaimType.QUANTITATIVE
676:                     and (bool(shared_entities) or tok_overlap)
677:                 ):
678:                     m1_matches = METRIC_REGEX.findall(c1.text)
679:                     m2_matches = METRIC_REGEX.findall(c2.text)
680: 
681:                     for val_str1, unit1 in m1_matches:
682:                         for val_str2, unit2 in m2_matches:
683:                             u1_norm = _normalize_unit(unit1)
684:                             u2_norm = _normalize_unit(unit2)
685:                             if u1_norm and u2_norm and u1_norm == u2_norm:
686:                                 try:
687:                                     v1 = float(val_str1.replace(",", ""))
688:                                     v2 = float(val_str2.replace(",", ""))
689:                                     if v1 > 0 and v2 > 0:
690:                                         rel_diff = abs(v1 - v2) / max(v1, v2)
691:                                         if rel_diff > 0.15:  # > 15% variation
692:                                             disc_count += 1
693:                                             ent_name = list(shared_entities)[0] if shared_entities else f"Metric ({unit1})"
694:                                             discrepancies.append(
695:                                                 DiscrepancyGroup(
696:                                                     discrepancy_id=f"disc-{disc_count:02d}",
697:                                                     entity=ent_name,
698:                                                     discrepancy_type="NUMERICAL_VARIATION",
699:                                                     claim_a_id=c1.claim_id,
700:                                                     claim_b_id=c2.claim_id,
701:                                                     claim_a_text=c1.text,
702:                                                     claim_b_text=c2.text,
703:                                                     source_a_url=c1.source_url,
704:                                                     source_b_url=c2.source_url,
705:                                                     explanation=f"Numerical variation on {unit1}: {v1} vs {v2} ({rel_diff*100:.1f}% difference).",
706:                                                 )
707:                                             )
708:                                 except ValueError:
709:                                     continue
```
- Line 685: Condition `if u1_norm and u2_norm and u1_norm == u2_norm:` uses normalized aliases.
- Line 693: `ent_name` fallback is `f"Metric ({unit1})"` using raw `unit1`.
- Line 705: `explanation` is `f"Numerical variation on {unit1}: ..."` using raw `unit1`.

### 1.3 Test Suite Failure Invariant in `tests/test_tier1_synthesis.py` (Lines 501–529)
Direct inspection of `tests/test_tier1_synthesis.py`:
```python
501:             claim_pct_a = ExtractedClaim(
502:                 claim_id="clm-silicon-35",
503:                 text="Silicon anode volumetric expansion reached 35% during continuous cycling.",
...
512:             claim_pct_b = ExtractedClaim(
513:                 claim_id="clm-silicon-20",
514:                 text="Silicon anode volumetric expansion was limited to 20 percent in composite electrodes.",
...
523:             synonym_discrepancies = self.clusterer._detect_discrepancies([claim_pct_a, claim_pct_b])
524:             num_var_syn = [d for d in synonym_discrepancies if d.discrepancy_type == "NUMERICAL_VARIATION"]
525:             self.assertGreaterEqual(
526:                 len(num_var_syn),
527:                 1,
528:                 "Unit synonyms (% vs percent) on same entity must be detected as NUMERICAL_VARIATION",
529:             )
```
- Line 503 has `"35% during"`.
- When line 84 uses `\b`, `METRIC_REGEX.findall(claim_pct_a.text)` produces `[('35', '')]`.
- Line 683 produces `u1_norm = ""`.
- Line 685 evaluates `if "" and "percent" and "" == "percent"` $\to$ `False`.
- Line 525 evaluates `self.assertGreaterEqual(0, 1)`, failing the test.

---

## 2. Logic Chain

### 2.1 Formal Proof: Zero Side Effects of Replacing Trailing `\b` with `(?!\w)` on Existing Units
Let the original pattern be:
$$P_{\text{orig}} = \verb|\b(\d+(?:[.,]\d+)?)\s*(...)?\b|$$
and the proposed pattern be:
$$P_{\text{prop}} = \verb|\b(\d+(?:[.,]\d+)?)\s*(...)?(?!\w)|$$
where the unit alternation is:
$$\mathcal{U} = \{ \%, \text{percentage}, \text{percent}, \text{pct}, \text{billion}, \text{million}, \text{trillion}, \text{USD}, \$, \text{dollars}, \text{dollar}, \text{EUR}, \text{Wh/kg}, \text{Wh/L}, \text{°C}, \text{tons}, \text{GW}, \text{MW}, \text{kWh}, \text{nm}, \text{mS/cm} \}$$

#### Step 1: Character Classification of Final Characters
Let $c_{\text{last}}(u)$ denote the terminal character of unit $u \in \mathcal{U}$:
- For `Wh/kg`: $c_{\text{last}} = \text{'g'} \in [a-z] \subset \w$
- For `Wh/L`: $c_{\text{last}} = \text{'L'} \in [A-Z] \subset \w$
- For `°C`: $c_{\text{last}} = \text{'C'} \in [A-Z] \subset \w$
- For `tons`: $c_{\text{last}} = \text{'s'} \in [a-z] \subset \w$
- For `GW`: $c_{\text{last}} = \text{'W'} \in [A-Z] \subset \w$
- For `MW`: $c_{\text{last}} = \text{'W'} \in [A-Z] \subset \w$
- For `kWh`: $c_{\text{last}} = \text{'h'} \in [a-z] \subset \w$
- For `nm`: $c_{\text{last}} = \text{'m'} \in [a-z] \subset \w$
- For `mS/cm`: $c_{\text{last}} = \text{'m'} \in [a-z] \subset \w$
- For `USD`: $c_{\text{last}} = \text{'D'} \in [A-Z] \subset \w$
- For `EUR`: $c_{\text{last}} = \text{'R'} \in [A-Z] \subset \w$
- For `percentage`, `percent`, `pct`: $c_{\text{last}} \in \{\text{'e'}, \text{'t'}\} \subset \w$
- For `billion`, `million`, `trillion`: $c_{\text{last}} = \text{'n'} \in \w$
- For `dollar`, `dollars`: $c_{\text{last}} \in \{\text{'r'}, \text{'s'}\} \subset \w$

Thus, for all units in $\mathcal{U} \setminus \{\%, \$\}$, $c_{\text{last}}(u) \in \w$.

#### Step 2: Boolean Equivalence of `\b` and `(?!\w)` when $c_{\text{last}} \in \w$
By definition of Python `re`:
A word boundary assertion `\b` at position $p$ between characters $c_{\text{prev}}$ and $c_{\text{next}}$ evaluates to:
$$\b \iff (c_{\text{prev}} \in \w \land c_{\text{next}} \notin \w) \lor (c_{\text{prev}} \notin \w \land c_{\text{next}} \in \w)$$
When a unit $u \in \mathcal{U} \setminus \{\%, \$\}$ matches, the character preceding the boundary is $c_{\text{prev}} = c_{\text{last}}(u) \in \w$.
Substituting $c_{\text{prev}} \in \w$ into the formula:
$$\b \iff (\text{True} \land c_{\text{next}} \notin \w) \lor (\text{False} \land c_{\text{next}} \in \w) \iff c_{\text{next}} \notin \w$$
Now consider the negative lookahead `(?!\w)` at position $p$:
$$(?!\w) \iff c_{\text{next}} \notin \w$$
Because both assertions evaluate to the identical truth condition $c_{\text{next}} \notin \w$:
$$\forall c_{\text{next}} \in \Sigma \cup \{\text{EOF}\}, \quad \b \equiv (?!\w)$$

#### Step 3: Terminal Context Exhaustion
For every possible succeeding token:
1. Whitespace (`' '`, `'\t'`, `'\n'`): $c_{\text{next}} \notin \w$. Both `\b` and `(?!\w)` match.
2. Punctuation (`'.' `, `','`, `';'`, `')'`, `'-'`): $c_{\text{next}} \notin \w$. Both `\b` and `(?!\w)` match.
3. End of string (`EOF`): $c_{\text{next}} \notin \w$. Both `\b` and `(?!\w)` match.
4. Word characters (`'a'-'z'`, `'0'-'9'`): $c_{\text{next}} \in \w$. Both `\b` and `(?!\w)` fail (e.g. `"500 Wh/kgfoo"` or `"100percentile"` correctly rejected).

#### Step 4: Unitless Number Matching
When no unit matches (Group 2 is $\epsilon$):
In input `"500 cells"`:
- Under `\b`: `\s*` matches `" "`. Position before `'c'` has $c_{\text{prev}} = \text{' '} \in \W$ and $c_{\text{next}} = \text{'c'} \in \w$. `\b` matches. Output: `('500', '')`.
- Under `(?!\w)`: If `\s*` matches `" "`, position before `'c'` has $c_{\text{next}} = \text{'c'} \in \w$. `(?!\w)` fails. Regex engine backtracks: `\s*` matches $\epsilon$. Position after `'0'` has $c_{\text{next}} = \text{' '} \notin \w$. `(?!\w)` matches. Output: `('500', '')`.
The returned 2-tuple `(val_str, unit)` is identical.

#### Step 5: Symbol Units (`%` and `$`) Defect Resolution
When unit is `%`:
$c_{\text{last}} = \text{'%'} \in \W$.
In natural text `"35% during"`, $c_{\text{next}} = \text{' '} \in \W$.
- Under `\b`: $(\text{False} \land \text{True}) \lor (\text{True} \land \text{False}) \implies \text{False}$. `\b` fails. Backtracks and drops `%`.
- Under `(?!\w)`: $c_{\text{next}} = \text{' '} \notin \w \implies \text{True}$. Successfully captures `unit = "%"`.

**Conclusion for Point 1**: Replacing `\b` with `(?!\w)` has **zero side effects** on `Wh/kg`, `Wh/L`, `°C`, `tons`, `GW`, `MW`, `kWh`, `nm`, `mS/cm`, `USD`, `EUR` (and all other word units), while strictly restoring `%` and `$`.

---

### 2.2 Formal Verification of `UNIT_ALIASES` Mapping & `_normalize_unit`
Direct analysis of lines 89–105:
```python
UNIT_ALIASES: Dict[str, str] = {
    "%": "percent",
    "pct": "percent",
    "percentage": "percent",
    "$": "usd",
    "dollar": "usd",
    "dollars": "usd",
}
```

#### Equivalence Relation Verification
Let $\sim$ be the relation on unit strings defined by:
$$u_1 \sim u_2 \iff \text{\_normalize\_unit}(u_1) == \text{\_normalize\_unit}(u_2)$$

1. **Percentage Equivalence Class**:
   - `_normalize_unit("%")` $\to$ `UNIT_ALIASES["%"]` = `"percent"`
   - `_normalize_unit("pct")` $\to$ `UNIT_ALIASES["pct"]` = `"percent"`
   - `_normalize_unit("percentage")` $\to$ `UNIT_ALIASES["percentage"]` = `"percent"`
   - `_normalize_unit("percent")` $\to$ `UNIT_ALIASES.get("percent", "percent")` = `"percent"`
   All 4 elements map to the identical representative `"percent"`.
   Pairwise symmetry: $\forall u_i, u_j \in \{\%, \text{pct}, \text{percentage}, \text{percent}\}, u_i \sim u_j \land u_j \sim u_i$.

2. **Currency Equivalence Class**:
   - `_normalize_unit("$")` $\to$ `UNIT_ALIASES["$"]` = `"usd"`
   - `_normalize_unit("dollar")` $\to$ `UNIT_ALIASES["dollar"]` = `"usd"`
   - `_normalize_unit("dollars")` $\to$ `UNIT_ALIASES["dollars"]` = `"usd"`
   - `_normalize_unit("usd")` $\to$ `UNIT_ALIASES.get("usd", "usd")` = `"usd"`
   - `_normalize_unit("USD")` $\to$ `UNIT_ALIASES.get("usd", "usd")` = `"usd"`
   All 5 elements map to the identical representative `"usd"`.
   Pairwise symmetry: $\forall u_i, u_j \in \{\$, \text{dollar}, \text{dollars}, \text{usd}, \text{USD}\}, u_i \sim u_j \land u_j \sim u_i$.

3. **Disjointness**:
   `_normalize_unit("%")` ("percent") $\ne$ `_normalize_unit("$")` ("usd"). False positive cross-family collisions: 0.

4. **Non-aliased Units Pass-Through**:
   For any $u \notin \text{dom}(\text{UNIT\_ALIASES})$:
   `_normalize_unit(u)` returns `u.lower().strip()`.
   Hence `_normalize_unit("Wh/kg") == _normalize_unit("wh/kg") == "wh/kg"`.
   Casing differences are normalized symmetrically.

5. **Empty / None Handling**:
   `_normalize_unit(None) == ""` and `_normalize_unit("") == ""`.
   In `_detect_discrepancies:685`, `if u1_norm and u2_norm:` guards against comparing unitless numbers.

**Conclusion for Point 2**: `UNIT_ALIASES` and `_normalize_unit` handle `%`, `pct`, `percentage`, `$`, `dollar`, and `dollars` completely symmetrically and correctly.

---

### 2.3 Formal Verification of Raw Formatting Preservation vs Normalized Alias Comparison
Direct analysis of lines 681–707:

1. **Comparison Guard (Line 685)**:
   ```python
   u1_norm = _normalize_unit(unit1)
   u2_norm = _normalize_unit(unit2)
   if u1_norm and u2_norm and u1_norm == u2_norm:
   ```
   The normalization is performed into temporary local variables `u1_norm` and `u2_norm`.
   This ensures that `"35%"` and `"20 percent"` evaluate to `"percent" == "percent"` $\implies \text{True}$.
   Similarly, `"Wh/kg"` and `"wh/kg"` evaluate to `"wh/kg" == "wh/kg"` $\implies \text{True}$.

2. **Entity Name Fallback (Line 693)**:
   ```python
   ent_name = list(shared_entities)[0] if shared_entities else f"Metric ({unit1})"
   ```
   When no shared entity is specified, the entity name is formatted using `{unit1}` (the raw captured string from `c1.text`), NOT `u1_norm`.
   - For `c1.text` with `"Wh/kg"`: `ent_name = "Metric (Wh/kg)"` (exact case preserved).
   - For `c1.text` with `"%"`: `ent_name = "Metric (%)"` (verbatim symbol preserved).

3. **Explanation Formatting (Line 705)**:
   ```python
   explanation = f"Numerical variation on {unit1}: {v1} vs {v2} ({rel_diff*100:.1f}% difference)."
   ```
   The explanation interpolates `{unit1}`, NOT `u1_norm`.
   - For `"Wh/kg"`: `"Numerical variation on Wh/kg: 500.0 vs 350.0 (30.0% difference)."`
   - Matches test requirement at `tests/test_tier1_synthesis.py:492`:
     `self.assertIn("wh/kg", disc.explanation.lower())`.
   - For `"%"`: `"Numerical variation on %: 35.0 vs 20.0 (42.9% difference)."`
   - For `"$"`: `"Numerical variation on $: 150.0 vs 100.0 (33.3% difference)."`

**Conclusion for Point 3**: `ent_name` and `explanation` preserve raw `{unit1}` formatting while `u1_norm == u2_norm` compares normalized aliases.

---

## 3. Caveats

1. **Execution Restriction**: Subprocess execution (`run_command`) and MCP tools were restricted by environment security policy. All verifications were established via rigorous static code analysis, formal AST parsing, character-set classification proofs, and lexical trace simulations.
2. **Prefix Currency Amounts**: As noted in reviewer feedback, English currency amounts often use prefix notation (e.g. `"$180"`). In `cluster.py`, `METRIC_REGEX` matches suffix units (`\d+\s*(...)`). Suffix currency expressions (`"180 dollars"`, `"180 $"`, `"180 USD"`) are parsed and normalized, but prefix amounts (`"$180"`) without a following unit are parsed as unitless numbers. This is an existing architectural constraint, outside the scope of the trailing boundary fix.

---

## 4. Conclusion

The audit is complete and conclusive:
1. In `src/research_synthesis/synthesis/cluster.py:84`, replacing trailing `\b` with `(?!\w)` is provably safe, has zero side effects on any existing units (`Wh/kg`, `Wh/L`, `°C`, `tons`, `GW`, `MW`, `kWh`, `nm`, `mS/cm`, `USD`, `EUR`), and fixes the non-word symbol extraction failure on `%` and `$`.
2. `UNIT_ALIASES` and `_normalize_unit` correctly and symmetrically map `% / pct / percentage / percent` to `"percent"` and `$ / dollar / dollars / usd` to `"usd"`.
3. `ent_name` and `explanation` preserve raw `{unit1}` formatting while `u1_norm == u2_norm` compares normalized aliases.

### Recommended Implementation Patch
In `src/research_synthesis/synthesis/cluster.py`:
```diff
--- a/src/research_synthesis/synthesis/cluster.py
+++ b/src/research_synthesis/synthesis/cluster.py
@@ -81,7 +81,7 @@ FACET_TITLE_TEMPLATES: Dict[str, str] = {
 
 # Numerical metric extraction pattern
 METRIC_REGEX = re.compile(
-    r"\b(\d+(?:[.,]\d+)?)\s*(%|percentage|percent|pct|billion|million|trillion|USD|\$|dollars|dollar|EUR|Wh/kg|Wh/L|°C|tons|GW|MW|kWh|nm|mS/cm)?\b",
+    r"\b(\d+(?:[.,]\d+)?)\s*(%|percentage|percent|pct|billion|million|trillion|USD|\$|dollars|dollar|EUR|Wh/kg|Wh/L|°C|tons|GW|MW|kWh|nm|mS/cm)?(?!\w)",
     re.IGNORECASE,
 )
```

---

## 5. Verification Method

### 5.1 Static Code Inspection
1. Inspect `src/research_synthesis/synthesis/cluster.py:84`:
   Confirm line matches:
   `r"\b(\d+(?:[.,]\d+)?)\s*(%|percentage|percent|pct|billion|million|trillion|USD|\$|dollars|dollar|EUR|Wh/kg|Wh/L|°C|tons|GW|MW|kWh|nm|mS/cm)?(?!\w)",`
2. Inspect `src/research_synthesis/synthesis/cluster.py:683-693`:
   Confirm `u1_norm = _normalize_unit(unit1)` and `u2_norm = _normalize_unit(unit2)` are compared via `u1_norm == u2_norm`.
3. Inspect `src/research_synthesis/synthesis/cluster.py:693, 705`:
   Confirm `ent_name` and `explanation` format `{unit1}`.

### 5.2 Unit Test Execution (when test runner is invoked)
Execute test suite:
```bash
python -m unittest tests/test_tier1_synthesis.py -v
```
Specifically verify:
- `TestThematicClusterer.test_discrepancy_numerical_unit_synonyms_flagged` passes (exit 0).
- `TestThematicClusterer.test_discrepancy_numerical_unrelated_entities_not_flagged` passes (exit 0).
- `TestThematicClusterer.test_discrepancy_detection` passes (exit 0).

### 5.3 Invalidation Conditions
The conclusion is invalidated if:
- Any unit ending in `\w` fails to match when followed by whitespace or punctuation under `(?!\w)`.
- `METRIC_REGEX.findall("35% during")` returns `[('35', '')]` instead of `[('35', '%')]`.
- `_normalize_unit("%")` returns anything other than `"percent"`.
- `disc.explanation` uses downcased `wh/kg` rather than raw `Wh/kg`.
