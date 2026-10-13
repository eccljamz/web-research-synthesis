## 2026-10-13T17:11:31Z
Your Identity:
- Archetype: teamwork_preview_test_writer
- Role: Test Writer (Test Infrastructure & E2E Verification Harness)
- Working directory: C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\test_writer_mtest
- Parent Conversation ID: 42364d7e-0273-4faa-be7a-22e0c17eecea

Mandatory Source:
Read C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\ORIGINAL_REQUEST.md before starting work.
Also read C:\Users\ecclj\teamwork_projects\web_research_synthesis\PROJECT.md.
Also read C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\survey_explorer_3\handoff.md for test architecture.

File Ownership:
You have exclusive write ownership over:
- tests/fixtures/mock_corpus/ (manifest.json, HTML fixture files for the 3 diverse domains: Solid-State Battery, Supply Chain Re-Shoring, Little Ice Age Climate, plus edge fixtures)
- tests/schemas/research_brief.schema.json
- src/research_synthesis/verification/__init__.py
- src/research_synthesis/verification/validator.py
- src/research_synthesis/verification/runner.py
- verify.py
- TEST_INFRA.md (at project root)
- TEST_READY.md (at project root)
Do NOT touch implementation files owned by workers.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Objective:
Build the Test Infrastructure, Mock Corpus, Verification Validator, and Acceptance Harness:
1. Create `tests/fixtures/mock_corpus/manifest.json` and realistic HTML fixtures for at least 3 diverse domains:
   - Science/Tech: Solid-state battery commercialization
   - Economics: Global supply chain re-shoring
   - History/Climate: Little Ice Age climate shocks
   - Edge: Microplastics & regulatory directives
2. Create `tests/schemas/research_brief.schema.json` formal JSON schema for ResearchBrief.
3. Implement `src/research_synthesis/verification/validator.py`: Schema validator and semantic invariant validator (verifying referential integrity: every [N] citation resolves to a valid source in sources table, non-empty executive summary >= 30 words, >= 3 key takeaways, no TODO/placeholder text).
4. Implement `src/research_synthesis/verification/runner.py` and `verify.py` CLI runner with `--mode`, `--strict` options, exiting with return code 0 on pass and 1 on failure.
5. Create `TEST_INFRA.md` at project root per the template in Project Pattern.
6. Create `TEST_READY.md` at project root once the test harness, mock corpus, and validators are ready.
7. Run tests on the validation components to verify functionality.
8. Write a complete, self-contained handoff report at C:\Users\ecclj\teamwork_projects\web_research_synthesis\.agents\teamwork\test_writer_mtest\handoff.md detailing created files, validation test results, caveats, and conclusions. Update progress.md as you work.
When finished, send a brief message to parent 42364d7e-0273-4faa-be7a-22e0c17eecea.
