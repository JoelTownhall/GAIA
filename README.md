# IA Navigator

A Streamlit app that helps Australian Public Service policy officers prepare an Impact
Analysis under the **Australian Government Impact Analysis Framework** (effective
1 July 2026). It is the successor to the RegCost IA helper, rebuilt to use only the 2026
Framework and the Impact Analysis Practical Guide for Agencies.

> IA Navigator is a drafting aid. It is not advice from the Office of Impact Analysis (OIA)
> and does not assess Impact Analyses.

## How it works

Every IA is a **project folder**. Each tool saves its output into the folder, so the folder
becomes the record of how the analysis was built:

```
<project>/
  project.json            metadata, step status, activity log
  00_brief/               problem statement, your uploaded documents
  01_research/            evidence research briefs and source lists
  02_self_assessment/     Self-Assessment Tool responses and gap list
  03_burden_estimate/     regulatory burden estimate (.xlsx + summary)
  04_drafts/              IA drafts
  05_exports/             final exports
```

Suggested workflow: create a project → **Research** the policy problem → work through the
five steps with **General advice** → run the **Self-assessment** → produce a first-cut
**Burden estimate** → **Draft and export**.

## Status

| Phase | Scope | Status |
|---|---|---|
| 1 | App shell, project folders (local storage), Claude client, framework spec scaffold | Done |
| 2 | Load Framework + Practical Guide PDFs, complete `content/framework_2026.yaml`, retrieval | Waiting on source PDFs |
| 3 | General advice chat (grounded, cited, save to folder) | Planned |
| 4 | Research (Claude web search → research brief) | Planned |
| 5 | Self-assessment | Planned |
| 6 | Burden estimate (validated against the OIA RBE Tool) | Planned |
| 7 | Google Drive storage + Google sign-in | Planned |
| 8 | Draft and export | Planned |

The framework steps are currently summarised from the OIA website. Until they are checked
against the source PDFs, the app flags them as not yet verified.

## Source documents

Put these in `reference_docs/oia_2026/`. The build environment can't fetch them from
oia.pmc.gov.au, so they have to be added by hand:

- `impact-analysis-framework.pdf` — https://oia.pmc.gov.au/sites/default/files/2026-06/impact-analysis-framework.pdf
- `impact-analysis-practical-guide.pdf` — https://oia.pmc.gov.au/sites/default/files/2026-06/impact-analysis-practical-guide.pdf
- the Self-Assessment Tool and the Regulatory Burden Estimation Tool workbook from the OIA website

Additional OIA guidance can go in `content/supplementary/`. The app labels it as
supplementary, separate from the Framework.

## Running locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # add ANTHROPIC_API_KEY
streamlit run app.py
pytest
```

## Configuration (Streamlit secrets)

| Key | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key (required for the AI tools) |
| `CLAUDE_MODEL`, `CLAUDE_MODEL_RESEARCH` | Optional model overrides (default `claude-opus-5-5`) |
| `STORAGE_BACKEND` | `local` (default) or `gdrive` |
| `DRIVE_ROOT_FOLDER_ID`, `[gcp_service_account]` | Google Drive storage (phase 7) |
| `[auth]` | Google sign-in via `st.login` (phase 7) |

## Data handling

Text entered in the app is sent to the Claude API and stored in the project folder. Do not
enter Cabinet-in-confidence or security-classified material.
