// Urdu MMLU annotator — static-only. Two screens: picker → annotation (full viewport).
// All progress lives in localStorage under urdumcq:<handle>:<mcq_id>.

// Paths are relative to this folder; annotator/prepare.py bundles data here.
const DATA_BASE = 'data';
const ASSIGNMENTS_URL = 'data/assignments.json';

const $ = id => document.getElementById(id);

const state = {
    handle: null,
    assignments: null,
    subdomains: [],           // full list, loaded from manifest at login
    myBatches: [],
    currentBatch: null,
    currentItems: [],
    idx: 0,
    startedAt: 0,
    advanceTimer: null,
    editing: false,           // edit mode for the currently-displayed MCQ
};

// ── Storage ──────────────────────────────────────────────────────────

const storageKey = mcqId => `urdumcq:${state.handle}:${mcqId}`;

function getRecord(mcqId) {
    const raw = localStorage.getItem(storageKey(mcqId));
    if (!raw) return null;
    try { return JSON.parse(raw); } catch { return null; }
}
function saveRecord(mcqId, payload) {
    localStorage.setItem(storageKey(mcqId), JSON.stringify(payload));
}
function isAnswered(rec) { return !!(rec && rec.selected_key); }
function hasEdits(rec) {
    if (!rec || !rec.edits) return false;
    const e = rec.edits;
    if (e.question != null) return true;
    if (e.subdomain != null) return true;
    if (e.options && Object.keys(e.options).length) return true;
    return false;
}
function hasAnyData(rec) {
    return !!(rec && (rec.selected_key || rec.flagged || hasEdits(rec)));
}

function emptyRecord(item) {
    return {
        annotator: state.handle,
        mcq_id: item.id,
        batch_id: state.currentBatch,
        is_iaa: false,
        selected_key: null,
        flagged: false,
        flag_note: '',
        edits: {},                 // { question?, options?: {A?,B?,...} }
        time_spent_ms: 0,
        submitted_at: null,
    };
}

// Effective text for question / option k, taking record edits into account.
function effectiveQuestion(item, rec) {
    if (rec && rec.edits && rec.edits.question != null) return rec.edits.question;
    return item.question || '';
}
function effectiveOption(item, rec, k) {
    if (rec && rec.edits && rec.edits.options && rec.edits.options[k] != null) {
        return rec.edits.options[k];
    }
    return (item.options || {})[k];
}
function effectiveSubdomain(item, rec) {
    if (rec && rec.edits && rec.edits.subdomain != null) return rec.edits.subdomain;
    return item.subdomain || '';
}

function batchProgress(_batchId, items) {
    let done = 0, flagged = 0;
    for (const it of items) {
        const r = getRecord(it.id);
        if (isAnswered(r)) done++;
        if (r && r.flagged)  flagged++;
    }
    return { done, total: items.length, flagged };
}

// ── Data ─────────────────────────────────────────────────────────────

async function fetchJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.json();
}
async function loadBatchFile(batchId) {
    return await fetchJSON(`${DATA_BASE}/batches/${batchId}.json`);
}

// ── Picker screen ────────────────────────────────────────────────────

async function login() {
    const handle = $('handle').value.trim();
    if (!handle) { $('handle').focus(); return; }
    state.handle = handle;
    try {
        state.assignments = await fetchJSON(ASSIGNMENTS_URL);
        const manifest = await fetchJSON(`${DATA_BASE}/manifest.json`);
        state.subdomains = [...new Set(manifest.batches.map(b => b.primary_subdomain).filter(Boolean))].sort();
    } catch (e) {
        $('batch-list').textContent =
            `Failed to load assignments: ${e.message}. Make sure you're serving this over HTTP (file:// won't work).`;
        return;
    }
    state.myBatches = (state.assignments.assignments || {})[handle] || [];
    $('who').textContent = `signed in as ${handle}`;
    localStorage.setItem('urdumcq:lastHandle', handle);
    await renderBatchList();
}

async function renderBatchList() {
    const list = $('batch-list');
    if (!state.myBatches.length) {
        list.textContent = 'No batches assigned to this handle.';
        return;
    }
    list.innerHTML = '';
    for (const bid of state.myBatches) {
        let items;
        try { items = await loadBatchFile(bid); }
        catch (e) { console.error(e); continue; }
        const { done, total } = batchProgress(bid, items);
        const isDone = done === total && total > 0;
        const row = document.createElement('div');
        row.className = 'batch-row' + (isDone ? ' done' : '');
        row.innerHTML = `
            <span class="label">${bid}</span>
            <span class="progress-tag">${isDone ? '✓ done' : `${done} / ${total}`}</span>
            <button data-batch="${bid}" class="primary">Open</button>
        `;
        row.querySelector('button').addEventListener('click', e => {
            e.stopPropagation();
            openBatch(bid, items);
        });
        row.addEventListener('click', () => openBatch(bid, items));
        list.appendChild(row);
    }
}

// ── Annotation screen ────────────────────────────────────────────────

function openBatch(batchId, items) {
    state.currentBatch = batchId;
    state.currentItems = items;
    state.idx = findNextUnanswered();
    $('picker-screen').classList.add('hidden');
    $('annotate-screen').classList.remove('hidden');
    $('current-batch').textContent = batchId;
    renderCurrent();
}

function backToPicker() {
    state.currentBatch = null;
    state.currentItems = [];
    $('annotate-screen').classList.add('hidden');
    $('picker-screen').classList.remove('hidden');
    renderBatchList();
}

function findNextUnanswered() {
    for (let i = 0; i < state.currentItems.length; i++) {
        if (!isAnswered(getRecord(state.currentItems[i].id))) return i;
    }
    return state.currentItems.length - 1;
}

function renderCurrent() {
    const items = state.currentItems;
    if (!items.length) return;
    state.idx = Math.max(0, Math.min(state.idx, items.length - 1));
    const item = items[state.idx];
    const { done, total } = batchProgress(state.currentBatch, items);

    $('progress').textContent = `MCQ ${state.idx + 1} / ${items.length} · ${done} done`;
    $('progress-fill').style.width = total ? `${100 * done / total}%` : '0%';

    const rec = getRecord(item.id) || {};

    // tags
    const tags = [];
    // Editable subdomain dropdown (always live, no edit-mode gate)
    if (item.subdomain || state.subdomains.length) {
        const editedSub = !!(rec.edits && rec.edits.subdomain != null);
        const currentSub = effectiveSubdomain(item, rec);
        // Make sure the current value is in the option list, even if it isn't in the manifest
        const subList = state.subdomains.includes(currentSub)
            ? state.subdomains
            : [...state.subdomains, currentSub].sort();
        const subOptsHtml = subList.map(s =>
            `<option value="${esc(s)}" ${s === currentSub ? 'selected' : ''}>${esc(s)}</option>`
        ).join('');
        tags.push(`<select id="subdomain-select" class="tag tag-select ${editedSub ? 'edited' : ''}"
            title="${editedSub ? 'subdomain edited' : 'change subdomain'}">${subOptsHtml}</select>`);
        if (editedSub) {
            tags.push(`<button id="subdomain-revert" class="tag-revert" title="revert subdomain to original">×</button>`);
        }
    }
    if (item.level)     tags.push(`<span class="tag">${esc(item.level)}</span>`);
    if (item.length_tier) tags.push(`<span class="tag">${esc(item.length_tier)}</span>`);
    (item.quality_flags || []).forEach(f => tags.push(`<span class="tag flag">${esc(f)}</span>`));
    tags.push(`<span class="tag">id ${item.id}</span>`);
    $('mcq-tags').innerHTML = tags.join('');

    const opts = item.options || {};
    const selected = rec.selected_key;
    const editedQ = rec.edits && rec.edits.question != null;
    const editedOpts = (rec.edits && rec.edits.options) || {};

    // Question — display vs edit mode
    if (state.editing) {
        $('question-view').classList.add('hidden');
        $('question-edit').classList.remove('hidden');
        $('question-edit').value = effectiveQuestion(item, rec);
    } else {
        $('question-view').classList.remove('hidden');
        $('question-edit').classList.add('hidden');
        $('question-view').innerHTML =
            (editedQ ? '<span class="edited-marker" data-revert="question" title="Revert to original">edited<span class="revert" title="Revert to original">×</span></span>' : '') +
            esc(effectiveQuestion(item, rec));
        $('question-view').classList.toggle('edited', editedQ);
    }

    // Options — display vs edit mode
    const lis = Object.entries(opts).map(([k, v], i) => {
        const display = effectiveOption(item, rec, k);
        const isEdited = editedOpts[k] != null;
        if (state.editing) {
            return `<li data-key="${k}" data-num="${i + 1}" class="editing">
                <span class="label">${k}</span>
                <input class="opt-input" data-key="${k}" type="text" value="${esc(display)}">
             </li>`;
        }
        const marker = isEdited
            ? `<span class="edited-marker" data-revert="option" data-revert-key="${k}" title="Revert to original">edited<span class="revert" title="Revert to original">×</span></span>`
            : '';
        return `<li data-key="${k}" data-num="${i + 1}" class="${selected === k ? 'selected' : ''}">
            ${marker}
            <span class="label">${k}</span>
            <span class="text">${esc(display)}</span>
         </li>`;
    });
    if (!state.editing) {
        const unsureNum = Object.keys(opts).length + 1;
        lis.push(
            `<li data-key="unsure" data-num="${unsureNum}" class="unsure ${selected === 'unsure' ? 'selected' : ''}">
                <span class="label">?</span>
                <span class="text">unsure / skip</span>
             </li>`
        );
    }
    $('mcq-options').innerHTML = lis.join('');

    if (state.editing) {
        $('mcq-options').querySelectorAll('input.opt-input').forEach(inp => {
            inp.addEventListener('input', () => saveOptionEdit(inp.dataset.key, inp.value));
        });
    } else {
        $('mcq-options').querySelectorAll('li').forEach(li => {
            li.addEventListener('click', e => {
                // Don't pick when clicking the revert chip
                if (e.target.closest('.edited-marker')) return;
                pickAnswer(li.dataset.key);
            });
        });
        $('mcq-options').querySelectorAll('.edited-marker[data-revert="option"]').forEach(el => {
            el.addEventListener('click', e => {
                e.stopPropagation();
                revertOptionEdit(el.dataset.revertKey);
            });
        });
        const qMarker = $('question-view').querySelector('.edited-marker[data-revert="question"]');
        if (qMarker) qMarker.addEventListener('click', revertQuestionEdit);
    }

    // Subdomain dropdown — live, regardless of edit mode
    const subSelect = $('subdomain-select');
    if (subSelect) {
        subSelect.addEventListener('change', e => saveSubdomainEdit(e.target.value));
    }
    const subRevert = $('subdomain-revert');
    if (subRevert) {
        subRevert.addEventListener('click', revertSubdomainEdit);
    }

    // Flag state
    const isFlagged = !!rec.flagged;
    $('flag-btn').classList.toggle('flagged', isFlagged);
    $('flag-btn').textContent = isFlagged ? '⚑ flagged' : '⚑ flag';
    $('mcq-card').classList.toggle('flagged', isFlagged);
    $('flag-panel').classList.toggle('hidden', !isFlagged);
    $('flag-note').value = rec.flag_note || '';

    // Edit-mode UI state
    $('edit-btn').classList.toggle('active', state.editing);
    $('edit-btn').classList.toggle('has-edits', !state.editing && hasEdits(rec));
    $('edit-btn').textContent = state.editing ? '✓ done editing'
        : (hasEdits(rec) ? '✎ edited' : '✎ edit');

    state.startedAt = Date.now();
    refreshExportButton();

    if (window.MathJax && window.MathJax.typesetPromise) {
        window.MathJax.typesetPromise([$('mcq-question'), $('mcq-options')]).catch(() => {});
    }
}

function pickAnswer(key) {
    const item = state.currentItems[state.idx];
    const rec = getRecord(item.id) || emptyRecord(item);
    rec.selected_key = key;
    rec.time_spent_ms = (rec.time_spent_ms || 0) + (Date.now() - state.startedAt);
    rec.submitted_at = new Date().toISOString();
    saveRecord(item.id, rec);
    state.startedAt = Date.now();

    document.querySelectorAll('#mcq-options li').forEach(li => {
        li.classList.toggle('selected', li.dataset.key === key);
    });
    refreshProgress();
    refreshExportButton();
}

function toggleFlag() {
    const item = state.currentItems[state.idx];
    const rec = getRecord(item.id) || emptyRecord(item);
    rec.flagged = !rec.flagged;
    if (!rec.flagged) rec.flag_note = '';
    rec.submitted_at = new Date().toISOString();
    saveRecord(item.id, rec);

    $('flag-btn').classList.toggle('flagged', rec.flagged);
    $('flag-btn').textContent = rec.flagged ? '⚑ flagged' : '⚑ flag';
    $('mcq-card').classList.toggle('flagged', rec.flagged);
    $('flag-panel').classList.toggle('hidden', !rec.flagged);
    if (rec.flagged) {
        $('flag-note').value = rec.flag_note || '';
        $('flag-note').focus();
    }
    refreshProgress();
    refreshExportButton();
}

function saveFlagNote() {
    const item = state.currentItems[state.idx];
    const rec = getRecord(item.id) || emptyRecord(item);
    if (!rec.flagged) return;          // shouldn't be visible if not flagged
    rec.flag_note = $('flag-note').value;
    rec.submitted_at = new Date().toISOString();
    saveRecord(item.id, rec);
}

function toggleEdit() {
    state.editing = !state.editing;
    renderCurrent();
    if (state.editing) $('question-edit').focus();
}

function saveQuestionEdit() {
    const item = state.currentItems[state.idx];
    const rec = getRecord(item.id) || emptyRecord(item);
    rec.edits = rec.edits || {};
    const newValue = $('question-edit').value;
    const original = item.question || '';
    if (newValue === original) {
        delete rec.edits.question;
    } else {
        rec.edits.question = newValue;
    }
    rec.submitted_at = new Date().toISOString();
    saveRecord(item.id, rec);
    refreshExportButton();
}

function saveOptionEdit(key, value) {
    const item = state.currentItems[state.idx];
    const rec = getRecord(item.id) || emptyRecord(item);
    rec.edits = rec.edits || {};
    rec.edits.options = rec.edits.options || {};
    const original = (item.options || {})[key] || '';
    if (value === original) {
        delete rec.edits.options[key];
        if (!Object.keys(rec.edits.options).length) delete rec.edits.options;
    } else {
        rec.edits.options[key] = value;
    }
    rec.submitted_at = new Date().toISOString();
    saveRecord(item.id, rec);
    refreshExportButton();
}

function revertQuestionEdit() {
    const item = state.currentItems[state.idx];
    const rec = getRecord(item.id);
    if (!rec || !rec.edits || rec.edits.question == null) return;
    delete rec.edits.question;
    rec.submitted_at = new Date().toISOString();
    saveRecord(item.id, rec);
    renderCurrent();
}

function revertOptionEdit(key) {
    const item = state.currentItems[state.idx];
    const rec = getRecord(item.id);
    if (!rec || !rec.edits || !rec.edits.options || rec.edits.options[key] == null) return;
    delete rec.edits.options[key];
    if (!Object.keys(rec.edits.options).length) delete rec.edits.options;
    rec.submitted_at = new Date().toISOString();
    saveRecord(item.id, rec);
    renderCurrent();
}

function saveSubdomainEdit(value) {
    const item = state.currentItems[state.idx];
    const rec = getRecord(item.id) || emptyRecord(item);
    rec.edits = rec.edits || {};
    const original = item.subdomain || '';
    if (value === original) {
        delete rec.edits.subdomain;
    } else {
        rec.edits.subdomain = value;
    }
    rec.submitted_at = new Date().toISOString();
    saveRecord(item.id, rec);
    renderCurrent();
}

function revertSubdomainEdit() {
    const item = state.currentItems[state.idx];
    const rec = getRecord(item.id);
    if (!rec || !rec.edits || rec.edits.subdomain == null) return;
    delete rec.edits.subdomain;
    rec.submitted_at = new Date().toISOString();
    saveRecord(item.id, rec);
    renderCurrent();
}

function refreshProgress() {
    const items = state.currentItems;
    const { done, total, flagged } = batchProgress(state.currentBatch, items);
    const flagPart = flagged ? ` · ${flagged} flagged` : '';
    $('progress').textContent = `MCQ ${state.idx + 1} / ${items.length} · ${done} done${flagPart}`;
    $('progress-fill').style.width = total ? `${100 * done / total}%` : '0%';
}

function goPrev() { state.editing = false; state.idx--; renderCurrent(); }
function goNext() { state.editing = false; state.idx++; renderCurrent(); }

function refreshExportButton() {
    const { done, total, flagged } = batchProgress(state.currentBatch, state.currentItems);
    const anyData = done > 0 || flagged > 0;
    $('export').disabled = !anyData;
    $('export').textContent = done === total
        ? `Export ✓ (${total})`
        : `Export (${done}/${total})`;
}

function exportBatch() {
    const records = state.currentItems
        .map(it => getRecord(it.id))
        .filter(hasAnyData);
    const payload = {
        annotator: state.handle,
        batch_id: state.currentBatch,
        exported_at: new Date().toISOString(),
        count: records.length,
        n_answered: records.filter(isAnswered).length,
        n_flagged: records.filter(r => r.flagged).length,
        annotations: records,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${state.handle}__${state.currentBatch}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

// ── Keyboard shortcuts ───────────────────────────────────────────────

document.addEventListener('keydown', e => {
    // Skip shortcuts while typing in any text field.
    const t = document.activeElement && document.activeElement.tagName;
    if (t === 'INPUT' || t === 'TEXTAREA') {
        if (e.key === 'Enter' && document.activeElement.id === 'handle') login();
        return;
    }
    if ($('annotate-screen').classList.contains('hidden')) return;

    const items = state.currentItems;
    if (!items.length) return;
    const optsCount = Object.keys(items[state.idx].options || {}).length;

    if (e.key >= '1' && e.key <= '9') {
        const i = parseInt(e.key, 10) - 1;
        const keys = Object.keys(items[state.idx].options || {});
        if (i < keys.length) { pickAnswer(keys[i]); e.preventDefault(); return; }
        if (i === optsCount) { pickAnswer('unsure'); e.preventDefault(); return; }
    }
    if (e.key === 'ArrowLeft')  { goPrev();        e.preventDefault(); }
    if (e.key === 'ArrowRight') { goNext();        e.preventDefault(); }
    if (e.key === 'Escape')     { backToPicker();  e.preventDefault(); }
    if (e.key === 'f' || e.key === 'F') { toggleFlag(); e.preventDefault(); }
    if (e.key === 'e' || e.key === 'E') { toggleEdit(); e.preventDefault(); }
});

// ── Utils ────────────────────────────────────────────────────────────

function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ── Wire up ──────────────────────────────────────────────────────────

$('login').addEventListener('click', login);
$('back').addEventListener('click', backToPicker);
$('prev').addEventListener('click', goPrev);
$('next').addEventListener('click', goNext);
$('export').addEventListener('click', exportBatch);
$('flag-btn').addEventListener('click', toggleFlag);
$('flag-remove').addEventListener('click', toggleFlag);
$('flag-note').addEventListener('input', saveFlagNote);
$('edit-btn').addEventListener('click', toggleEdit);
$('question-edit').addEventListener('input', saveQuestionEdit);

const last = localStorage.getItem('urdumcq:lastHandle');
if (last) $('handle').value = last;
