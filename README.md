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
| 2 | Load Framework + Practical Guide PDFs, complete `content/framework_2026.yaml`, retrieval | Done |
| 3 | General advice chat (grounded, cited, save to folder) | Built; not yet tried against the live API |
| 4 | Research (Claude web search → research brief) | Built; not yet tried against the live API |
| 5 | Self-assessment | Built; suggested ratings not yet tried against the live API |
| 6 | Burden estimate (validated against the OIA RBE Tool) | Built; reproduces the tool's four worked examples |
| 7 | Google Drive storage + Google sign-in | Built; needs a Google Cloud project to switch on |
| 8 | Draft and export | Built; drafting not yet tried against the live API |

The AI features are tested with Claude replaced by a fake (`tests/test_views.py`), so the page
logic, saving and exports are checked, but the quality of Claude's output has not yet been
reviewed on a real proposal.

`content/framework_2026.yaml` is checked against the four source documents. It holds the five
steps, scope and the 3 IA thresholds, the 7 IA questions as worded in the Framework, the 26
Self-Assessment Tool criteria (verbatim), the Regulatory Burden Estimation Tool defaults and
method, and the special cases. Every entry has a citation (page for the PDFs, sheet and cell
for the workbooks). The tests check the question and criterion wording against the source
files. `core/retrieval.py` splits the two PDFs into passages by page and section and searches
them with BM25 (`search(query, k)`).

## Source documents

These are in `reference_docs/oia_2026/` (July 2026 versions, from the OIA website):

- `impact-analysis-framework.pdf` — https://oia.pmc.gov.au/sites/default/files/2026-06/impact-analysis-framework.pdf
- `impact-analysis-practical-guide.pdf` — https://oia.pmc.gov.au/sites/default/files/2026-06/impact-analysis-practical-guide.pdf
- `impact-analysis-self-assessment-tool.xlsx` — Impact Analysis Self-Assessment Tool
- `regulatory-burden-estimation-tool.xlsx` — Regulatory Burden Estimation Tool

When OIA releases new versions, replace the files, update the YAML and run `pytest`: the
wording tests will fail wherever the spec no longer matches the documents.

Additional OIA guidance can go in `content/supplementary/`. The app labels it as
supplementary, separate from the Framework.

## The tools

- **General advice** — chat about the IA. Each question retrieves the most relevant passages
  from the Framework and Practical Guide, and answers cite them by page. The project folder is
  given to Claude as context. Conversations can be saved to `04_drafts`.
- **Research** — Claude searches the web (Anthropic's server-side web search and fetch) and
  writes a brief structured on IA questions 1 to 5. The source list is taken from the search
  results themselves, not from Claude's text. Saved to `01_research`.
- **Self-assessment** — the 26 criteria of the OIA Self-Assessment Tool, scored the way the
  workbook scores them. Claude can suggest ratings from a draft IA. Saves the ratings, a gap
  report and a completed copy of the OIA workbook to `02_self_assessment`.
- **Burden estimate** — the OIA Regulatory Burden Estimation Tool's method and default labour
  rates, year by year over the period of analysis, with a threshold 1 check. Claude can
  suggest cost items from the project folder. Saves inputs, a summary and an `.xlsx` with an
  Estimates sheet laid out like the OIA tool's. Recurring costs can start in year 1 or later,
  which the tool's worked examples need.
- **Draft and export** — drafts a Dashboard or Detailed IA section by section, structured on
  the 7 IA questions, from everything in the project folder, with gap markers where
  information is missing. Exports to Word (real heading styles, table header rows) with an
  option to leave out the sections marked for removal before publication.

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
| `DRIVE_ROOT_FOLDER_ID`, `[gcp_service_account]` | Google Drive storage |
| `[auth]` | Google sign-in via `st.login`; each user then sees only their own projects |
| `ALLOWED_EMAIL_DOMAINS` | Optional, e.g. `gov.au`: only these email domains may sign in |

### Google Drive storage

On Streamlit Community Cloud the app's disk is wiped when it restarts, so use Drive for real
work.

1. In Google Cloud, create a project, enable the Google Drive API, and create a service
   account with a JSON key.
2. Create a Drive folder for the projects (a shared drive works too) and share it with the
   service account's email as an Editor.
3. In the app's secrets set `STORAGE_BACKEND = "gdrive"`, `DRIVE_ROOT_FOLDER_ID` (the folder's
   ID from its URL) and a `[gcp_service_account]` section with the key's fields.

### Google sign-in

1. In the same Google Cloud project, create an OAuth client (Web application) with the
   redirect URI `https://<your-app>.streamlit.app/oauth2callback`.
2. Add an `[auth]` section to the secrets (see `.streamlit/secrets.toml.example`).

Without sign-in, everyone using the app sees the same projects.

## Data handling

Text entered in the app is sent to the Claude API and stored in the project folder. Do not
enter Cabinet-in-confidence or security-classified material.
