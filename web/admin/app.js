// Urdu MMLU admin dashboard — pure-static. Annotators send JSON; we load it via file input.
// All state lives in `state.byKey` keyed by (annotator, mcq_id).

const DATA_BASE = 'data';
const ASSIGNMENTS_URL = 'data/assignments.json';

const $ = id => document.getElementById(id);

const state = {
    annotations: [],          // flat list, deduped by (annotator, mcq_id) — last wins
    byKey: new Map(),         // (annotator + '::' + mcq_id) → annotation
    submissions: [],          // metadata about each loaded submission file
    assignments: null,        // raw assignments.json
    manifest: null,           // raw manifest.json (for batch sizes etc.)
};

const charts = {};

// ── File loading ────────────────────────────────────────────────────────

async function loadStaticData() {
    try {
        state.manifest = await fetch(`${DATA_BASE}/manifest.json`).then(r => r.json());
        state.assignments = await fetch(ASSIGNMENTS_URL).then(r => r.json());
    } catch (e) {
        console.warn('Could not load reference data:', e);
    }
}

function ingestSubmission(parsed, sourceName) {
    if (!parsed || !Array.isArray(parsed.annotations)) {
        return { ok: false, reason: 'missing annotations[]' };
    }
    let added = 0, updated = 0;
    for (const ann of parsed.annotations) {
        if (!ann || !ann.annotator || ann.mcq_id == null) continue;
        const key = `${ann.annotator}::${ann.mcq_id}`;
        if (state.byKey.has(key)) updated++; else added++;
        state.byKey.set(key, ann);
    }
    state.annotations = Array.from(state.byKey.values());
    state.submissions.push({
        source: sourceName,
        annotator: parsed.annotator,
        batch_id: parsed.batch_id,
        count: (parsed.annotations || []).length,
        added, updated,
        exported_at: parsed.exported_at,
    });
    return { ok: true, added, updated };
}

async function handleFiles(fileList) {
    for (const file of fileList) {
        try {
            const text = await file.text();
            const parsed = JSON.parse(text);
            const r = ingestSubmission(parsed, file.name);
            logLine(r.ok
                ? `loaded ${file.name}: +${r.added} new, ${r.updated} updated`
                : `skipped ${file.name}: ${r.reason}`);
        } catch (e) {
            logLine(`failed ${file.name}: ${e.message}`);
        }
    }
    render();
}

function logLine(msg) {
    const log = $('log');
    if (log.textContent === '—') log.innerHTML = '';
    const div = document.createElement('div');
    div.className = 'line';
    div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    log.prepend(div);
}

// ── Stats / agreement ───────────────────────────────────────────────────

function computeStats() {
    const annotators = new Set();
    const perAnnotator = new Map();
    const selectedCounts = new Map();

    for (const a of state.annotations) {
        annotators.add(a.annotator);
        const ann = perAnnotator.get(a.annotator) || {
            total: 0, unsure: 0, flagged: 0, batches: new Set()
        };
        ann.total++;
        if (a.selected_key === 'unsure') ann.unsure++;
        if (a.flagged) ann.flagged++;
        if (a.batch_id) ann.batches.add(a.batch_id);
        perAnnotator.set(a.annotator, ann);

        const k = a.selected_key || '(none)';
        selectedCounts.set(k, (selectedCounts.get(k) || 0) + 1);
    }

    // Dual-annotation: every MCQ has up to N annotators (target: 2).
    // For each MCQ with ≥2 picks, derive consensus (majority of non-unsure keys).
    const byMcq = new Map();
    for (const a of state.annotations) {
        const arr = byMcq.get(a.mcq_id) || [];
        arr.push(a);
        byMcq.set(a.mcq_id, arr);
    }

    const consensus = new Map();   // mcq_id → consensus key (or null on tie / all unsure)
    let bothAnnotated = 0;
    let bothAgree = 0;
    let bothDisagree = 0;
    for (const [mid, picks] of byMcq) {
        if (picks.length < 2) continue;
        bothAnnotated++;
        const keys = picks.map(p => p.selected_key).filter(k => k && k !== 'unsure');
        if (!keys.length) continue;
        const counts = {};
        keys.forEach(k => counts[k] = (counts[k] || 0) + 1);
        let best = null, bestN = -1, tied = false;
        for (const k in counts) {
            if (counts[k] > bestN) { best = k; bestN = counts[k]; tied = false; }
            else if (counts[k] === bestN) tied = true;
        }
        if (tied) {
            bothDisagree++;
            continue;
        }
        consensus.set(mid, best);
        const uniqueKeys = new Set(keys);
        if (uniqueKeys.size === 1) bothAgree++;
        else bothDisagree++;
    }

    // Per-annotator agreement vs consensus
    const agreePerAnn = new Map();
    for (const [mid, picks] of byMcq) {
        const cons = consensus.get(mid);
        if (!cons || picks.length < 2) continue;
        for (const p of picks) {
            const slot = agreePerAnn.get(p.annotator) || { agree: 0, total: 0 };
            slot.total++;
            if (p.selected_key === cons) slot.agree++;
            agreePerAnn.set(p.annotator, slot);
        }
    }

    return {
        annotators, perAnnotator, selectedCounts,
        byMcq, consensus, agreePerAnn,
        bothAnnotated, bothAgree, bothDisagree,
    };
}

// ── Rendering ───────────────────────────────────────────────────────────

function render() {
    if (!state.annotations.length) {
        $('overall').textContent = 'No submissions loaded yet.';
        $('per-ann').textContent = '—';
        $('iaa').textContent = '—';
        return;
    }
    const s = computeStats();

    // Overall
    $('overall').innerHTML = `
        <div class="stat-row">
            <div class="stat"><div class="num">${state.annotations.length}</div><div class="label">annotations</div></div>
            <div class="stat"><div class="num">${s.annotators.size}</div><div class="label">annotators</div></div>
            <div class="stat"><div class="num">${s.bothAnnotated}</div><div class="label">MCQs with ≥2 annotators</div></div>
            <div class="stat"><div class="num">${s.bothAgree}</div><div class="label">agreed</div></div>
            <div class="stat"><div class="num">${s.bothDisagree}</div><div class="label">disagreed</div></div>
            <div class="stat"><div class="num">${state.submissions.length}</div><div class="label">submission files</div></div>
        </div>
    `;

    // Per annotator
    let assigned = (state.assignments && state.assignments.assignments) || {};
    const batchSize = (state.manifest && state.manifest.batch_size) || 50;
    const annRows = [...s.perAnnotator.entries()]
        .sort((a, b) => b[1].total - a[1].total)
        .map(([name, d]) => {
            const expected = assigned[name] ? assigned[name].length * batchSize : 0;
            const ag = s.agreePerAnn.get(name);
            const pct = ag && ag.total ? (100 * ag.agree / ag.total).toFixed(1) : null;
            const cls = pct == null ? '' : pct >= 85 ? 'good' : pct >= 70 ? '' : 'warn';
            const cell = pct == null ? '—' : `${pct}% (${ag.agree}/${ag.total})`;
            return `<tr class="${cls}">
                <td>${escape(name)}</td>
                <td class="num">${d.total}</td>
                <td class="num">${d.batches.size}</td>
                <td class="num">${expected || '—'}</td>
                <td class="num">${d.unsure}</td>
                <td class="num">${d.flagged}</td>
                <td class="num iaa">${cell}</td>
            </tr>`;
        }).join('');
    $('per-ann').innerHTML = `
        <table>
            <thead><tr>
                <th>annotator</th><th>annotations</th>
                <th>batches touched</th><th>expected (assigned)</th>
                <th>unsure</th><th>flagged</th>
                <th>agreement w/ consensus</th>
            </tr></thead>
            <tbody>${annRows}</tbody>
        </table>
    `;

    // Disagreement detail
    if (s.bothAnnotated === 0) {
        $('iaa').textContent = 'No MCQs yet have ≥2 annotators.';
    } else {
        const conflictItems = [...s.byMcq.entries()]
            .filter(([mid, picks]) => {
                if (picks.length < 2) return false;
                const keys = new Set(picks.map(p => p.selected_key).filter(k => k && k !== 'unsure'));
                return keys.size > 1;
            })
            .map(([mid, picks]) => ({
                mid,
                picks: picks.map(p => `${p.annotator}=${p.selected_key}`).join(', '),
            }));
        $('iaa').innerHTML = `
            <div class="hint">
                ${conflictItems.length} IAA MCQs have disagreement so far.
                Sample (first 15):
            </div>
            <pre style="font-family: ui-monospace, Menlo, monospace; font-size: 12px; max-height: 240px; overflow:auto; background: #fafafa; padding: 10px; border-radius: 6px;">
${conflictItems.slice(0, 15).map(c => `id=${c.mid}  ${c.picks}`).join('\n') || '(none)'}
            </pre>
        `;
    }

    // Charts
    const subCanvas = document.getElementById('chart-subdomain');
    // We don't have subdomain in the submission payload — skip if absent
    if (charts.sub) { charts.sub.destroy(); charts.sub = null; }
    if (charts.sel) charts.sel.destroy();

    charts.sel = new Chart(document.getElementById('chart-selected'), {
        type: 'bar',
        data: {
            labels: [...s.selectedCounts.keys()].sort(),
            datasets: [{
                data: [...s.selectedCounts.keys()].sort().map(k => s.selectedCounts.get(k)),
                backgroundColor: '#6dbf8c',
                borderRadius: 3,
            }],
        },
        options: {
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, title: { display: true, text: 'selected_key distribution' } },
            scales: { y: { beginAtZero: true } },
        },
    });

    // Log already shows submissions
    renderSubmissionsLog();
}

function renderSubmissionsLog() {
    // No-op — log lines added on file load already in #log.
}

// ── Export merged ──────────────────────────────────────────────────────

function exportMerged() {
    if (!state.annotations.length) { alert('Nothing to export.'); return; }
    const payload = {
        merged_at: new Date().toISOString(),
        n_annotations: state.annotations.length,
        n_submissions: state.submissions.length,
        submissions: state.submissions,
        annotations: state.annotations,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `urdu_mmlu_annotations_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

function clearAll() {
    if (!confirm('Discard all loaded submissions?')) return;
    state.annotations = [];
    state.byKey.clear();
    state.submissions = [];
    $('log').textContent = '—';
    render();
}

// ── Utils ──────────────────────────────────────────────────────────────

function escape(s) {
    return String(s ?? '').replace(/[&<>"']/g, c =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ── Wire up ────────────────────────────────────────────────────────────

$('file-input').addEventListener('change', e => {
    handleFiles(e.target.files);
    e.target.value = '';   // allow re-selecting the same file
});
$('clear').addEventListener('click', clearAll);
$('export-all').addEventListener('click', exportMerged);

loadStaticData().then(render);
