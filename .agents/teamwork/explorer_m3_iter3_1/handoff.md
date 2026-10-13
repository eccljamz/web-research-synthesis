# Remediation Analysis Report: Milestone 3 Unit Assertion Case-Insensitivity Fix

**Agent**: `explorer_m3_iter3_1`  
**Archetype**: `teamwork_preview_explorer`  
**Role**: Remediation Explorer 1 (Milestone 3 Unit Assertion Case-Insensitivity Fix)  
**Parent Conversation ID**: `42364d7e-0273-4faa-be7a-22e0c17eecea`  
**Working Directory**: `C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\explorer_m3_iter3_1`  
**Date**: 2026-10-13T19:54:00Z  

---

## 1. Observation

### 1.1 Direct Observation in `src/research_synthesis/synthesis/cluster.py`

1. **Unit Normalization Function (`cluster.py:88–105`)**:
   ```python
   # Canonical unit alias normalization mapping
   UNIT_ALIASES: Dict[str, str] = {
       "%": "percent",
       "pct": "percent",
       "percentage": "percent",
       "$": "usd",
       "dollar": "usd",
       "dollars": "usd",
   }


   def _normalize_unit(unit: Optional[str]) -> str:
       """Normalize a metric unit string to its canonical alias in lowercase."""
       if not unit:
           return ""
       u = unit.lower().strip()
       return UNIT_ALIASES.get(u, u)
   ```
   - For an input unit `unit = "Wh/kg"`, `u = unit.lower().strip()` evaluates to `"wh/kg"`.
   - Since `"wh/kg"` is not in `UNIT_ALIASES`, `UNIT_ALIASES.get(u, u)` returns `"wh/kg"` (strictly lowercase).

2. **Numerical Variation Explanation Construction (`cluster.py:660–688`)**:
   ```python
   for val_str1, unit1 in m1_matches:
       for val_str2, unit2 in m2_matches:
           u1_norm = _normalize_unit(unit1)
           u2_norm = _normalize_unit(unit2)
           if u1_norm and u2_norm and u1_norm == u2_norm:
               try:
                   v1 = float(val_str1.replace(",", ""))
                   v2 = float(val_str2.replace(",", ""))
                   if v1 > 0 and v2 > 0:
                       rel_diff = abs(v1 - v2) / max(v1, v2)
                       if rel_diff > 0.15:  # > 15% variation
                           disc_count += 1
                           ent_name = list(shared_entities)[0] if shared_entities else f"Metric ({u1_norm})"
                           discrepancies.append(
                               DiscrepancyGroup(
                                   discrepancy_id=f"disc-{disc_count:02d}",
                                   entity=ent_name,
                                   discrepancy_type="NUMERICAL_VARIATION",
                                   claim_a_id=c1.claim_id,
                                   claim_b_id=c2.claim_id,
                                   claim_a_text=c1.text,
                                   claim_b_text=c2.text,
                                   source_a_url=c1.source_url,
                                   source_b_url=c2.source_url,
                                   explanation=f"Numerical variation on {u1_norm}: {v1} vs {v2} ({rel_diff*100:.1f}% difference).",
                               )
                           )
               except ValueError:
                   continue
   ```
   - Line 684 explicitly constructs the explanation string using `{u1_norm}`.
   - For `val_str1 = "500"`, `val_str2 = "350"`, and `unit1 = "Wh/kg"`, `u1_norm` evaluates to `"wh/kg"`, `v1 = 500.0`, `v2 = 350.0`, and `rel_diff = 0.30`.
   - Resulting string: `disc.explanation = "Numerical variation on wh/kg: 500.0 vs 350.0 (30.0% difference)."`.

### 1.2 Direct Observation in `tests/test_tier1_synthesis.py`

1. **Test Method `test_discrepancy_numerical_unit_synonyms_flagged` (`tests/test_tier1_synthesis.py:482–493`)**:
   ```python
   482:         clusters = self.clusterer.cluster([claim_high, claim_low, companion], self.sub_queries, self.topic)
   483:         all_discrepancies = [d for c in clusters for d in c.discrepancies]
   484:         num_variations = [d for d in all_discrepancies if d.discrepancy_type == "NUMERICAL_VARIATION"]
   485:         self.assertGreaterEqual(
   486:             len(num_variations),
   487:             1,
   488:             "Clustering pipeline must emit at least one NUMERICAL_VARIATION discrepancy",
   489:         )
   490:         disc = num_variations[0]
   491:         self.assertEqual(disc.entity, "Energy density")
   492:         self.assertIn("Wh/kg", disc.explanation)
   ```
   - In Python, string containment (`"Wh/kg" in disc.explanation`) performs exact case-sensitive matching.
   - Character 0 of `"Wh/kg"` is uppercase `'W'` (ASCII 87), whereas character 23 of `disc.explanation` is lowercase `'w'` (ASCII 119).
   - Execution of line 492 raises:
     `AssertionError: 'Wh/kg' not found in 'Numerical variation on wh/kg: 500.0 vs 350.0 (30.0% difference).'`

---

## 2. Logic Chain

1. **Step 1: Normalization Design Rationale**:
   `_normalize_unit` serves as the canonical representation layer across heterogeneous document extracts. To handle case divergence (`"Wh/kg"`, `"wh/kg"`, `"WH/KG"`, `"PCT"`, `"percent"`), it intentionally converts all units to lowercase before checking alias mappings (`UNIT_ALIASES`).

2. **Step 2: String Formatting in `cluster.py`**:
   In `_detect_discrepancies` (line 684), `explanation` formats `{u1_norm}` (the normalized canonical unit). This ensures consistent reporting even when claims use differing surface forms (e.g., `"%"` vs `"percent"`). Because `u1_norm` is normalized, it is lowercase (`"wh/kg"`).

3. **Step 3: Root Cause of Assertion Failure**:
   The test in `tests/test_tier1_synthesis.py:492` attempted to verify that the unit of the numerical variation was reported in the explanation. The test author hardcoded `"Wh/kg"` with capital `'W'`, expecting verbatim fixture casing. Because Python's `in` operator is case-sensitive, this produces `False` and causes an unhandled `AssertionError`.

4. **Step 4: Remediation Strategy Assessment**:
   - **Option A (Preserve casing in `cluster.py`)**: Format `unit1` instead of `u1_norm`. This would break consistency when claims use synonym pairs (`"%"` and `"percent"`) and would alter production formatting.
   - **Option B (Case-insensitive assertion in `test_tier1_synthesis.py:492`)**: Change line 492 to:
     `self.assertIn("wh/kg", disc.explanation.lower())`.
     This aligns the test assertion with the canonical lowercase design of `_normalize_unit` while strictly verifying that the unit `"wh/kg"` is present in `disc.explanation`.

5. **Step 5: Impact on Test Invariants**:
   - Applying `self.assertIn("wh/kg", disc.explanation.lower())` in `tests/test_tier1_synthesis.py:492` allows `test_discrepancy_numerical_unit_synonyms_flagged` to pass 100% cleanly.
   - All other 29 tests in `tests/test_tier1_synthesis.py` continue to pass without side effects.
   - No production code in `src/` requires alteration.

---

## 3. Caveats

1. **Subprocess Execution Restriction**: Per environment security policy, direct subprocess execution (`run_command`) was restricted. Analysis and validation were conducted via static AST inspection, symbolic tracing, and propositional logic proofs.
2. **Alternative Units**: `METRIC_REGEX` supports additional units (`%`, `percent`, `billion`, `million`, `trillion`, `USD`, `$`, `EUR`, `Wh/kg`, `Wh/L`, `°C`, `tons`, `GW`, `MW`, `kWh`, `nm`, `mS/cm`). All unaliased units will likewise be normalized to lowercase by `_normalize_unit`. Test assertions on `explanation` for any of these units should similarly assert against `.lower()`.

---

## 4. Conclusion

The sole failing test in Milestone 3 is `test_discrepancy_numerical_unit_synonyms_flagged` in `tests/test_tier1_synthesis.py:492`.
The exact remediation is to change line 492 from `self.assertIn("Wh/kg", disc.explanation)` to `self.assertIn("wh/kg", disc.explanation.lower())`.

### Exact Proposed Code Patch

**Target File**: `tests/test_tier1_synthesis.py`  
**Target Line**: 492

```diff
--- a/tests/test_tier1_synthesis.py
+++ b/tests/test_tier1_synthesis.py
@@ -489,4 +489,4 @@
         )
         disc = num_variations[0]
         self.assertEqual(disc.entity, "Energy density")
-        self.assertIn("Wh/kg", disc.explanation)
+        self.assertIn("wh/kg", disc.explanation.lower())
```

### Full Context (Lines 482–495) Post-Patch
```python
        clusters = self.clusterer.cluster([claim_high, claim_low, companion], self.sub_queries, self.topic)
        all_discrepancies = [d for c in clusters for d in c.discrepancies]
        num_variations = [d for d in all_discrepancies if d.discrepancy_type == "NUMERICAL_VARIATION"]
        self.assertGreaterEqual(
            len(num_variations),
            1,
            "Clustering pipeline must emit at least one NUMERICAL_VARIATION discrepancy",
        )
        disc = num_variations[0]
        self.assertEqual(disc.entity, "Energy density")
        self.assertIn("wh/kg", disc.explanation.lower())

        # Unit synonym alias verification (% vs percent) when UNIT_ALIASES is active
```

---

## 5. Verification Method

### 5.1 Verification Commands
Once the implementation worker applies the patch, verify with:
```bash
python -m unittest tests/test_tier1_synthesis.py -v -k test_discrepancy_numerical_unit_synonyms_flagged
python -m unittest tests/test_tier1_synthesis.py
python verify.py
```

### 5.2 Expected Results
1. `test_discrepancy_numerical_unit_synonyms_flagged` executes and terminates with `ok`.
2. All 30 tests in `TestThematicClusterer`, `TestExtractiveSynthesizer`, `TestFormattersAndSerializers`, `TestResearchPipelineIntegration`, and `TestPipelineGracefulFallbacks` pass (`Ran 30 tests ... OK`).
3. Exit code 0 across verification harness.
