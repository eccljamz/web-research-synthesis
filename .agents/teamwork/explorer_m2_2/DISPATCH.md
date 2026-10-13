## 2026-10-13T17:58:54Z
Your Identity:
- Archetype: teamwork_preview_explorer
- Role: Explorer M2-2 (Two-Stage Deduplication Engine)
- Working directory: C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\explorer_m2_2
- Parent Conversation ID: 42364d7e-0273-4faa-be7a-22e0c17eecea

Mandatory Source:
Read C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\ORIGINAL_REQUEST.md before starting work.
Also read C:\Users\ecclj\teamwork_projects\web_research_synthesis\PROJECT.md.
Also read C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\survey_explorer_2\handoff.md.
Also inspect C:\Users\ecclj\teamwork_projects\web_research_synthesis\src\research_synthesis\models.py.

Objective:
Investigate and design the exact technical specifications for Milestone 2 Feature F8:
1. `src/research_synthesis/extraction/dedup.py`:
   - `TwoStageDeduplicator`:
     - Stage 1: Exact Deduplication. SHA-256 hash of normalized text (lowercase, whitespace-collapsed, punctuation-stripped) and canonical URL matching.
     - Stage 2: Near-Duplicate Detection via 64-bit SimHash (Charikar's locality-sensitive hash).
       - Tokenization (word n-grams / shingles).
       - 64-bit hash per token (via hashlib.md5 or sha256).
       - Vector accumulation across 64 bit positions (+1 if bit is 1, -1 if bit is 0).
       - 64-bit integer fingerprint construction: set bit $i$ to 1 if $V[i] > 0$, else 0.
       - Hamming distance calculation via bitwise XOR: `(fp1 ^ fp2).bit_count()`.
       - Near-duplicate threshold: Hamming distance $\le 3$.
   - Attribution Preservation: When merging near-duplicate passages or claims, append secondary URLs and titles into `secondary_urls` so credit and co-citation are never lost.
   - Inverted SimHash index / bucket clustering for efficient $O(N)$ comparisons.
2. Formulate concrete class interfaces, method signatures, error handling, and test criteria.
Deliver your detailed specifications to C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\explorer_m2_2\handoff.md. Update progress.md as you work.
When finished, send a brief message to parent 42364d7e-0273-4faa-be7a-22e0c17eecea.
