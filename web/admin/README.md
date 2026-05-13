# Urdu MMLU — Admin dashboard

Local-only dashboard for collecting annotator submissions and computing
inter-annotator agreement.

## Running it

From the project root:

```bash
python -m http.server 8000
```

Then open <http://localhost:8000/admin/>.

## Workflow

1. Annotators export per-batch JSON files (`<handle>__<batch_id>.json`)
   from the annotator dashboard and send them to you (Slack/email/Drive).
2. Click **Load submissions** in the admin dashboard and select the
   JSON files you've received. You can load more files at any time;
   re-loading the same file updates the existing answers.
3. The dashboard recomputes everything in-browser:
   - **Overall progress** counters
   - **Per-annotator table** with IAA agreement scores
   - **IAA detail** listing MCQs where annotators disagreed
   - **selected_key distribution** chart
4. Click **Export merged JSON** to save a single canonical file
   combining every loaded submission (with deduplication on
   `(annotator, mcq_id)` — latest export wins).

## IAA agreement

For each IAA MCQ:
- The **consensus** is the majority pick among non-`unsure` answers.
- Each annotator's **agreement** is `consensus_matches / iaa_picks`.

Annotators below ~70% agreement get a warning highlight; ≥85% gets a
"good" highlight. Tune thresholds in `app.js` if you want.

## Caveats

- This dashboard is **read-only client-side**. Nothing is saved unless
  you click **Export merged JSON**.
- Loading 100+ submission files in one go is fine; the in-memory
  dataset stays under a few MB.
