function resolveApiBase() {
  const params = new URLSearchParams(window.location.search);
  const queryApiBase = params.get('apiBase');
  if (queryApiBase) {
    window.localStorage.setItem('apiBase', queryApiBase);
    return queryApiBase.replace(/\/$/, '');
  }

  const configuredApiBase = window.APP_CONFIG && window.APP_CONFIG.API_BASE;
  if (configuredApiBase) return configuredApiBase.replace(/\/$/, '');

  const savedApiBase = window.localStorage.getItem('apiBase');
  if (savedApiBase) return savedApiBase.replace(/\/$/, '');

  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return 'http://localhost:8000';
  }
  return window.location.origin;
}

const API_BASE = resolveApiBase();

const $ = (id) => document.getElementById(id);

const els = {
  apiStatusDot: $('apiStatusDot'),
  apiStatusText: $('apiStatusText'),
  datasetSelect: $('datasetSelect'),
  refreshDatasets: $('refreshDatasets'),
  questionInput: $('questionInput'),
  runBtn: $('runBtn'),
  btnText: document.querySelector('.btn-text'),
  btnSpinner: document.querySelector('.btn-spinner'),
  debugMode: $('debugMode'),
  welcomeCard: $('welcomeCard'),
  resultsContainer: $('resultsContainer'),
  errorContainer: $('errorContainer'),
  errorMessage: $('errorMessage'),
  intentBadge: $('intentBadge'),
  sqlOutput: $('sqlOutput'),
  copySqlBtn: $('copySqlBtn'),
  rowCount: $('rowCount'),
  tableHead: $('tableHead'),
  tableBody: $('tableBody'),
  emptyState: $('emptyState'),
  metricsCard: $('metricsCard'),
  metricsGrid: $('metricsGrid'),
  debugCard: $('debugCard'),
  debugOutput: $('debugOutput'),
  toggleDebug: $('toggleDebug'),
};

async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      els.apiStatusDot.classList.add('online');
      els.apiStatusDot.classList.remove('offline');
      els.apiStatusText.textContent = `API online · ${API_BASE}`;
      return true;
    }
  } catch (err) {
    els.apiStatusDot.classList.add('offline');
    els.apiStatusDot.classList.remove('online');
    els.apiStatusText.textContent = `API offline · start: uvicorn api.main:app --reload`;
    return false;
  }
}

async function loadDatasets() {
  try {
    const res = await fetch(`${API_BASE}/dataset/list`);
    if (!res.ok) return;
    const data = await res.json();
    const sel = els.datasetSelect;
    sel.innerHTML = '<option value="">-- No dataset (use built-in schema) --</option>';
    (data.datasets || []).forEach((ds) => {
      const opt = document.createElement('option');
      opt.value = ds.dataset_id;
      opt.textContent = `${ds.name} (${ds.db_engine || 'unknown'})`;
      sel.appendChild(opt);
    });
  } catch (err) {
    console.warn('Failed to load datasets', err);
  }
}

function setLoading(loading) {
  els.runBtn.disabled = loading;
  els.btnSpinner.hidden = !loading;
  els.btnText.textContent = loading ? 'Analyzing...' : 'Run Analysis';
}

function showError(msg) {
  els.welcomeCard.hidden = true;
  els.resultsContainer.hidden = true;
  els.metricsCard.hidden = true;
  els.errorContainer.hidden = false;
  els.errorMessage.textContent = msg;
}

function clearError() {
  els.errorContainer.hidden = true;
}

function renderTable(rows) {
  els.tableHead.innerHTML = '';
  els.tableBody.innerHTML = '';

  if (!rows || rows.length === 0) {
    els.emptyState.hidden = false;
    return;
  }
  els.emptyState.hidden = true;

  const cols = Object.keys(rows[0]);
  cols.forEach((c) => {
    const th = document.createElement('th');
    th.textContent = c;
    els.tableHead.appendChild(th);
  });

  rows.forEach((row) => {
    const tr = document.createElement('tr');
    cols.forEach((c) => {
      const td = document.createElement('td');
      const v = row[c];
      td.textContent = v === null || v === undefined ? '—' :
        typeof v === 'object' ? JSON.stringify(v) : String(v);
      tr.appendChild(td);
    });
    els.tableBody.appendChild(tr);
  });
}

function renderMetrics(data) {
  const debug = data.debug || {};
  const metrics = [
    { label: 'Status', value: data.evaluator_status || '—', cls: data.evaluator_status === 'ok' ? 'success' : 'warning' },
    { label: 'Rows', value: (data.rows || []).length },
    { label: 'Retries', value: data.retries_used ?? 0 },
    { label: 'Cache Hit', value: debug.cache_hit ? 'Yes' : 'No', cls: debug.cache_hit ? 'success' : '' },
    { label: 'Planner', value: data.planner_source || '—' },
    { label: 'DB Engine', value: debug.db_engine || '—' },
  ];

  els.metricsGrid.innerHTML = '';
  metrics.forEach((m) => {
    const div = document.createElement('div');
    div.className = 'metric';
    div.innerHTML = `
      <div class="metric-label">${m.label}</div>
      <div class="metric-value ${m.cls || ''}">${m.value}</div>
    `;
    els.metricsGrid.appendChild(div);
  });
  els.metricsCard.hidden = false;
}

function renderResults(data) {
  els.welcomeCard.hidden = true;
  els.resultsContainer.hidden = false;
  clearError();

  els.intentBadge.textContent = data.intent || 'unknown';
  els.sqlOutput.textContent = data.sql || '-- no SQL generated';

  const rows = data.rows || [];
  els.rowCount.textContent = `${rows.length} row${rows.length === 1 ? '' : 's'}`;
  renderTable(rows);
  renderMetrics(data);

  if (data.debug) {
    els.debugCard.hidden = false;
    els.debugOutput.textContent = JSON.stringify(data.debug, null, 2);
  } else {
    els.debugCard.hidden = true;
  }
}

async function runAnalysis() {
  const question = els.questionInput.value.trim();
  if (!question) {
    showError('Please enter a question.');
    return;
  }
  if (question.length < 3) {
    showError('Question must be at least 3 characters.');
    return;
  }

  const datasetId = els.datasetSelect.value || null;
  const debugMode = els.debugMode.checked;

  const payload = {
    question,
    row_limit: 100,
    timeout_ms: 30000,
  };
  if (datasetId) payload.dataset_id = datasetId;

  setLoading(true);
  clearError();

  try {
    const endpoint = debugMode ? '/analyze/debug' : '/analyze';
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errBody.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    renderResults(data);
  } catch (err) {
    showError(err.message || String(err));
  } finally {
    setLoading(false);
  }
}

async function copySql() {
  const text = els.sqlOutput.textContent;
  try {
    await navigator.clipboard.writeText(text);
    els.copySqlBtn.textContent = '✓';
    setTimeout(() => { els.copySqlBtn.textContent = '⧉'; }, 1200);
  } catch {
    /* clipboard unavailable */
  }
}

document.querySelectorAll('.example-chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    els.questionInput.value = chip.dataset.q;
    els.questionInput.focus();
  });
});

els.runBtn.addEventListener('click', runAnalysis);
els.refreshDatasets.addEventListener('click', loadDatasets);
els.copySqlBtn.addEventListener('click', copySql);

els.questionInput.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    runAnalysis();
  }
});

els.toggleDebug.addEventListener('click', () => {
  const visible = els.debugOutput.style.display !== 'none';
  els.debugOutput.style.display = visible ? 'none' : 'block';
  els.toggleDebug.textContent = visible ? '▸' : '▾';
});

(async function init() {
  await checkHealth();
  await loadDatasets();
  setInterval(checkHealth, 15000);
})();
