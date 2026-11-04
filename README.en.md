<div align="center">

<img src="docs/beagle-sniff.gif" alt="Smarty Beagle mascot" width="150" height="150" />

# 🐶 Smarty Beagle

**Legal-risk review agent for open datasets and research papers**

<em>Sniffs out legal risks in a dataset's <b>license · data creation/collection method · personal information · lawsuits</b> 🔍</em>

**English** · [한국어](README.md)

</div>

Request a review of an open dataset (or a research paper) through a GitHub issue and **Gemini (with Google Search
grounding)** reviews it automatically and posts the result as an issue comment. It runs with **no backend server** — only
**GitHub Pages + GitHub Actions + the free Google AI Studio API**.

> This review is a **reference for internal pre-screening of risk**. It does not replace legal advice or legal judgment.

---

## 🌐 English support

- **Website:** click **English** at the top right of the [homepage](https://aigovsensing.github.io/dataset-review/)
  (or open it with `?lang=en`). Your choice is remembered; first-time visitors whose browser language is not Korean see
  English automatically. Everything — request form, results, dashboards, guides — is translated.
- **Request a review in English:** with English selected, the *Request review* button opens the **English issue form**
  (`dataset-review-en.yml` / `paper-review-en.yml`). The review result is then posted **in English**, with the Korean
  original in a collapsed section at the bottom of the same comment.
- **Dashboards:** the aggregated data (CSV/JSON, charts) is built from the Korean original, so labels are translated but
  free-text details (rationales, lawsuit summaries) are shown in the language they were written in — mostly Korean.

See [documents/i18n.md](documents/i18n.md) for how it works and how to extend it.

---

## 🚀 Getting started

### 1. Register a Gemini API key
Get a free key at [AI Studio](https://aistudio.google.com/apikey) (no credit card needed) and add it under
**Settings → Secrets and variables → Actions → Secrets** as `GEMINI_API_KEY`.

To rotate automatically when a free quota runs out, add more keys named `GEMINI_API_KEY_<NAME>`; the order is defined by
[`prompt-book/gemini-api-keys.json`](prompt-book/gemini-api-keys.json). Failure comments only ever show secret **names**,
never values.

> A new key needs three places: ① the repository secret → ② the `order` list in `prompt-book/gemini-api-keys.json` →
> ③ one `NAME: ${{ secrets.NAME }}` line in both workflow files (GitHub cannot inject secrets by dynamic name).

### 2. Create the labels (required ⚠️)
Issue forms only apply labels that **already exist**; without `dataset-review` the workflow is `Skipped`.

```bash
R=<owner>/<repo>
gh label create dataset-review --repo $R --color 1d76db --description "Dataset review request (trigger)" --force
gh label create paper-review   --repo $R --color 8250df --description "Paper review request (trigger)" --force
gh label create reviewing      --repo $R --color fbca04 --description "Review in progress" --force
gh label create reviewed       --repo $R --color 0e8a16 --description "Review done" --force
gh label create review-failed  --repo $R --color d73a4a --description "Review failed" --force
gh label create rerun-review   --repo $R --color 5319e7 --description "Force a re-review" --force
```

### 3. Pages and Actions permissions
- **Settings → Pages → Deploy from a branch → `main` / `/docs`**
- **Settings → Actions → General → Workflow permissions → Read and write**

### 4. Request a review
Open the homepage, switch to **English**, fill in the *Request Review* tab and press the button. A GitHub issue form opens
pre-filled; click *Submit new issue* and a report is posted within **1–3 minutes**. To review again, add the
`rerun-review` label to the issue.

### Run it locally once

```bash
pip install -r scripts/requirements.txt
export GEMINI_API_KEY=...            # AI Studio key
export ISSUE_TITLE="[Dataset Review] CelebA"
export ISSUE_BODY="### Dataset name

CelebA

### Dataset repository URL

https://mmlab.ie.cuhk.edu.hk/projects/CelebA.html"
python scripts/dataset_review.py     # writes review.md (in English, because of the English form headings)
```

Check a key first with `./tools/gemini_api_key_test.sh <API_KEY>`.

---

## 📚 Documentation

The detailed guides are written in Korean in [`documents/`](documents/): [setup](documents/setup.md),
[usage](documents/usage.md), [architecture](documents/architecture.md), [models & quota](documents/models-and-quota.md),
[lawsuit review](documents/litigation.md), [troubleshooting](documents/troubleshooting.md),
[development](documents/development.md), and the English-support guide [documents/i18n.md](documents/i18n.md).

## 🔗 Links

- Live demo: <https://aigovsensing.github.io/dataset-review/>
- Repository: <https://github.com/aigovsensing/dataset-review>

## License

Released under the [Apache License 2.0](LICENSE).
