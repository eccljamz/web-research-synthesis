# Personal Knowledge Management (PKM) & Obsidian Integration Guide

The Autonomous Web Research System includes native export capabilities for **Obsidian**, **Logseq**, **Foam**, and standard markdown knowledge bases. It compiles research findings into an atomic, inter-linked knowledge vault with visual graph representations.

---

## 1. Vault Directory Architecture

When exporting via CLI (`--format=obsidian` or `--format=all`), Python SDK (`brief.export_obsidian_vault()`), or the web dashboard ZIP download, the following folder hierarchy is produced:

```text
{topic_slug}_vault/
├── Index.md                     # Main research brief overview & table of contents
├── Knowledge_Graph.canvas       # Native Obsidian 2D Canvas visual mind map
├── Sections/                    # Atomic thematic section notes
│   ├── 01_technical_mechanisms.md
│   ├── 02_economic_feasibility.md
│   └── 03_regulatory_frameworks.md
└── Sources/                     # Dedicated source bibliography notes
    ├── Source_1_doe_consortium_benchmark.md
    ├── Source_2_nature_nanotechnology_review.md
    └── Source_3_industry_patent_survey.md
```

---

## 2. Note Structure & Markdown Features

### A. Index Note (`Index.md`)
- **YAML Frontmatter**: Includes `title`, `brief_id`, `type: research-index`, tags (`#research`, `#index`, `#<topic>`), and timestamp.
- **Obsidian Callouts**:
  - `> [!summary] Executive Summary`: High-level synthesis with inline citation wikilinks.
  - `> [!tip] Key Takeaways`: Direct findings mapped to sources.
- **Table of Contents**: Linked to atomic sections using Obsidian wikilink syntax:
  ```markdown
  - [[Sections/01_technical_mechanisms|1. Technical Mechanisms]]
  - [[Sections/02_economic_feasibility|2. Economic Feasibility]]
  ```
- **References & Sources**: Links to individual source notes:
  ```markdown
  - [[Sources/Source_1_doe_consortium|[1] DOE Consortium Benchmark]]
  ```

### B. Atomic Section Notes (`Sections/*.md`)
- **Breadcrumb Navigation**: Header contains `[[Index|Back to Research Brief Overview]]` for frictionless backlinking.
- **Parent Metadata**: Frontmatter defines `parent: "[[Index]]"`.
- **Inline Citation Wikilinks**: Every citation `[1]` in the narrative prose is transformed into a direct wikilink:
  ```markdown
  Sulfide electrolytes achieve ionic conductivity exceeding 12 mS/cm [[Sources/Source_1|[1]]].
  ```
- **Discrepancy Tables**: Conflicting assertions between sources are highlighted in Markdown comparison tables.

### C. Source Notes (`Sources/*.md`)
- **Metadata Card**: URL, Author, Publication Date.
- **Evidence Snippets**: Extracted verbatim evidence context wrapped in quote callouts:
  ```markdown
  > [!quote] Evidence Context
  > "Room temperature ionic conductivity exceeds 15 mS/cm under ambient laboratory conditions."
  ```

### D. Obsidian Visual Canvas (`Knowledge_Graph.canvas`)
- Native Obsidian Canvas JSON format with predefined coordinate nodes and directional connecting edges:
  - **Index Node** positioned at origin `(0, 0)`.
  - **Section Nodes** arrayed vertically at $X = 500\text{px}$.
  - **Source Nodes** arrayed vertically at $X = 1000\text{px}$.
- Opening this file inside Obsidian renders an interactive visual concept map instantly.

---

## 3. Importing into Knowledge Management Tools

### Obsidian
1. **Option A: Drag-and-Drop into Existing Vault**:
   - Download the `.zip` archive or copy the `{topic_slug}_vault` folder directly into your existing Obsidian vault folder.
   - Obsidian will automatically index all `[[wikilinks]]`, tags, and canvas files.
2. **Option B: Open as Independent Vault**:
   - In Obsidian, click **Open folder as vault** and select the `{topic_slug}_vault` directory.
   - Click on `Knowledge_Graph.canvas` in the file explorer to view the 2D visual layout.

### Logseq
- Place the vault directory inside your Logseq working directory.
- Logseq natively understands `[[wikilinks]]` and parses the YAML frontmatter properties.

### VS Code (Foam / Dendron)
- Open the vault folder in VS Code with the **Foam** extension installed.
- Press `Ctrl + Shift + P` and select **Foam: Show Graph** to explore the interactive visual graph.
