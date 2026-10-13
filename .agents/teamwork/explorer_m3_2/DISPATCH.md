## 2026-10-13T18:47:33Z
Your Identity:
- Archetype: teamwork_preview_explorer
- Role: Explorer M3-2 (Extractive Synthesizer & Formatters)
- Working directory: C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\explorer_m3_2
- Parent Conversation ID: 42364d7e-0273-4faa-be7a-22e0c17eecea

Mandatory Source:
Read C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\ORIGINAL_REQUEST.md before starting work.
Also read C:\Users\ecclj\teamwork_projects\web_research_synthesis\PROJECT.md.
Also read C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\survey_explorer_2\handoff.md.
Also inspect C:\Users\ecclj\teamwork_projects\web_research_synthesis\src\research_synthesis\models.py.
Also inspect C:\Users\ecclj\teamwork_projects\web_research_synthesis\tests\schemas\research_brief.schema.json.

Objective:
Investigate and design the exact technical specifications for Milestone 3 Features F11, F12, and F13:
1. `src/research_synthesis/synthesis/synthesizer.py`:
   - `ExtractiveSynthesizer`:
     - Maximal Marginal Relevance (MMR) or centroid-based claim selection within each cluster to maximize relevance while penalizing redundancy.
     - Narrative generation: Construct coherent prose paragraphs connecting selected claims with logical transition connectives ("Furthermore", "In contrast", "Notably", "Consistently across reports").
     - Inline Citation Insertion: Embed IEEE-style numeric citations `[N]` or `[N, M]` directly in prose for every asserted claim.
     - Global Citation Registry: Map unique URLs to contiguous 1-based indices `[1], [2], ...` based strictly on order of appearance in prose.
     - Executive Summary Generation: Synthesize top claims across all clusters into a cohesive overview ($\ge 30$ words) answering the core research query with inline citations.
     - Key Takeaways Generation: Extract 3 to 7 distinct actionable insight bullets (`KeyTakeaway`), each with source citations.
     - Bibliography construction: Construct `List[SourceCitation]` containing `citation_index`, `title`, `url`, `snippet`, and attributed claim IDs.
2. `src/research_synthesis/synthesis/formatters.py`:
   - `MarkdownFormatter`: Render `ResearchBrief` into clean, human-readable Markdown with executive summary, thematic sections, key takeaways, and numbered bibliography.
   - `JSONSchemaSerializer`: Render `ResearchBrief` into JSON strictly conforming to `tests/schemas/research_brief.schema.json`.
3. Standard library purity (100% Python 3.10+ stdlib).
Deliver your detailed specifications to C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\explorer_m3_2\handoff.md. Update progress.md as you work.
When finished, send a brief message to parent 42364d7e-0273-4faa-be7a-22e0c17eecea.
