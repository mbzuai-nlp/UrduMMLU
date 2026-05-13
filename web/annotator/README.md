# Urdu MMLU — Annotator dashboard

Static page. Deployable to GitHub Pages.

## How an annotator uses it

1. Open the page (your team admin will share the URL).
2. Type your **handle** (whatever the admin assigned to you) and click
   **Load my batches**.
3. Click **Open** on any batch (start with **IAA — everyone**).
4. For each MCQ, click the option you believe is correct (A/B/C/D/E)
   or "unsure / skip" if you don't know. Your answer is saved instantly
   in your browser.
5. You can leave and come back later — the page resumes at the first
   unanswered MCQ.
6. When a batch is done (or whenever you want to send progress), click
   **Export batch JSON** and send the file (`<handle>__<batch>.json`)
   to the admin via Slack/email/Drive.

## Deploying to GitHub Pages

This folder is **self-contained**. Before deploying, bundle the data:

```bash
python annotator/prepare.py
```

That copies `data/15-batching/*` and `data/16-assignments/assignments.json`
into `annotator/data/`, so the `annotator/` subtree has everything it
needs to fetch at runtime.

Two deployment options:

**1. Same repo, root-served Pages.**
- Settings → Pages → Source: `main` branch, folder `/` (root).
- Annotators visit `https://<user>.github.io/<repo>/annotator/`.

**2. Separate public repo (recommended if main repo is private).**
- Create a new public repo, e.g. `urdu-mmlu-annotation-ui`.
- Copy the contents of `annotator/` into the root of that repo.
- Enable Pages on the new repo.
- Annotators visit `https://<user>.github.io/<repo>/`.

Either way, only the `annotator/` subtree needs to ship — none of the
rest of the project pipeline is exposed.

## Privacy

- Answers are stored in the annotator's **browser localStorage** until
  they export. Nothing is uploaded automatically.
- Export → email/Slack to admin is the only data transfer.
