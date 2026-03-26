/* ==========================================================================
   Daily Parameter Review — Light Professional Theme
   Pure CSS charts, no external libraries
   ========================================================================== */

// Data loaded from local static files (public/data/) committed by GH Actions
const DATA_BASE = '/data';

// SVG Icons
const ICONS = {
  check: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M3 8.5l3.5 3.5L13 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  alert: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2l6.93 12H1.07L8 2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 7v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="12.5" r="0.7" fill="currentColor"/></svg>`,
  x: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/><path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>`,
  clock: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/><path d="M8 5v3l2 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  download: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M3 11v2.5h10V11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 2.5v7.5m0 0l-2.5-2.5M8 10l2.5-2.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  chevron: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  clockLg: `<svg width="24" height="24" viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="12" stroke="currentColor" stroke-width="1.5"/><path d="M16 10v6l3.5 2.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
};

// ---------------------------------------------------------------------------
// Mock Data — matches runner output schema
// ---------------------------------------------------------------------------

const MOCK_DATES = ['2026-03-26', '2026-03-25', '2026-03-24'];

function buildMockReport(date) {
  return {
    report: {
      date,
      generated_at: `${date}T08:05:00Z`,
      status: 'warning',
      total_issues: 7,
      chapters: [
        { slug: 'price-limit', title: 'Price Limit Review', status: 'warning',
          summary: '7 issues found across 1472 instruments.',
          metrics: { instruments_scanned: 1472, ema_coverage: 1472, issues_found: 7, source: 'OKX API', generated_at: `${date}T08:05:00Z` } },
        { slug: 'mmr-futures', title: 'MMR Futures Review', status: 'pending',
          summary: 'Integration pending \u2014 ETA March 28, 2026.',
          metrics: { instruments_scanned: 0, ema_coverage: 0, issues_found: 0, source: 'n/a', generated_at: `${date}T08:05:00Z` } },
        { slug: 'index-review', title: 'Index Review', status: 'pending',
          summary: 'Integration pending \u2014 ETA March 28, 2026.',
          metrics: { instruments_scanned: 0, ema_coverage: 0, issues_found: 0, source: 'n/a', generated_at: `${date}T08:05:00Z` } },
      ],
    },
    chapters: [
      {
        slug: 'price-limit',
        title: 'Price Limit Review',
        status: 'warning',
        summary: '7 issues found across 1472 instruments. 5 instruments have buffers marginally thin, 2 have asset-type consistency issues.',
        metrics: { instruments_scanned: 1472, ema_coverage: 1472, issues_found: 7, source: 'OKX API (live)', generated_at: `${date}T08:05:00Z` },
        rule_blocks: [
          {
            ruleId: 'buffer_tight', title: 'Buffer Too Tight', status: 'warning',
            description: 'Checks if limitUp/limitDn buffer EMA is negative, indicating price persistently near a limit. BNB-USDT lower buffer (0.16%) is marginally thin.',
            table: {
              headers: ['INSTRUMENT', 'LIMITUP_BUFFER', 'LIMITDN_BUFFER', 'STATUS'],
              rows: [
                ['SOL-AUD', '2.1557%', '1.5173%', 'pass'],
                ['XRP-AUD', '2.0731%', '1.6131%', 'pass'],
                ['BANANA-USDT', '1.9625%', '1.9009%', 'pass'],
                ['BNB-USDT', '0.8449%', '0.1642%', 'warning'],
                ['CRV-USDT', '1.5747%', '0.4275%', 'pass'],
              ],
            }, note: null,
          },
          {
            ruleId: 'basis_asymmetric', title: 'Asymmetric Basis vs Z Cap', status: 'critical',
            description: 'Compares basis EMA against Z cap. SOL-AUD and XRP-AUD are missing basis data.',
            table: {
              headers: ['INSTRUMENT', 'BASIS_EMA', 'RELEVANT Z CAP', 'STATUS'],
              rows: [
                ['SOL-AUD', 'N/A', '\u2014', 'missing'],
                ['XRP-AUD', 'N/A', '\u2014', 'missing'],
              ],
            }, note: null,
          },
          {
            ruleId: 'consistency', title: 'Asset-Type Consistency', status: 'warning',
            description: 'SOL-AUD and XRP-AUD are Topcoins with Y=2%, Z=5%. Expected: Y=0.5\u20131%, Z=1\u20132%. Over-wide.',
            table: {
              headers: ['INSTRUMENT', 'ASSET TYPE', 'CURRENT Y', 'CURRENT Z', 'EXPECTED Y', 'EXPECTED Z', 'STATUS'],
              rows: [
                ['SOL-AUD', 'Topcoins', '2%', '5%', '0.5\u20131%', '1\u20132%', 'warning'],
                ['XRP-AUD', 'Topcoins', '2%', '5%', '0.5\u20131%', '1\u20132%', 'warning'],
              ],
            }, note: null,
          },
          {
            ruleId: 'z_gt_y', title: 'Z Cap > Y Cap', status: 'pass',
            description: 'Z cap (outer hard limit) must always be wider than Y cap (inner band).',
            table: null, note: null,
          },
        ],
        recommended_changes: {
          headers: ['INSTRUMENT', 'CHANGE', 'REASON'],
          rows: [
            ['SOL-AUD', 'Y: 2%\u21921%, Z: 5%\u21922%', 'Rule 3: Topcoins standard'],
            ['XRP-AUD', 'Y: 2%\u21921%, Z: 5%\u21922%', 'Rule 3: Topcoins standard'],
          ],
        },
        downloads: [{
          label: 'Spot adjustment CSV (2 rows)',
          filename: 'spot_adjustment.csv',
          content: 'Task Object,timeType,openMaxThresholdRate,openMinThresholdRate,limitMaxThresholdRate,limitMinThresholdRate,indexMaxThresholdRate,indexMinThresholdRate\nSOL-AUD,IMMEDIATE,1.1,0.9,1.01,0.99,1.02,0.98\nXRP-AUD,IMMEDIATE,1.1,0.9,1.01,0.99,1.02,0.98',
        }],
        markdown: '', error: null,
      },
      {
        slug: 'mmr-futures', title: 'MMR Futures Review', status: 'pending',
        summary: 'Integration pending \u2014 ETA March 28, 2026.',
        metrics: { instruments_scanned: 0, ema_coverage: 0, issues_found: 0, source: 'n/a', generated_at: `${date}T08:05:00Z` },
        rule_blocks: [], recommended_changes: null, downloads: [], markdown: '', error: null,
      },
      {
        slug: 'index-review', title: 'Index Review', status: 'pending',
        summary: 'Integration pending \u2014 ETA March 28, 2026.',
        metrics: { instruments_scanned: 0, ema_coverage: 0, issues_found: 0, source: 'n/a', generated_at: `${date}T08:05:00Z` },
        rule_blocks: [], recommended_changes: null, downloads: [], markdown: '', error: null,
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Data Loading
// ---------------------------------------------------------------------------

let currentReport = null;
let currentDate = MOCK_DATES[0];
let availableDates = [...MOCK_DATES];

async function loadReport(date) {
  date = date || currentDate;
  try {
    const res = await fetch(`${DATA_BASE}/reports/${date}/report.json`);
    if (res.ok) return await res.json();
  } catch (e) { console.warn('Failed to load report:', e.message); }
  // Fallback to mock data if no real report exists
  return buildMockReport(date);
}

async function loadDates() {
  try {
    const res = await fetch(`${DATA_BASE}/reports/index.json`);
    if (res.ok) { const d = await res.json(); if (d.dates?.length) return d.dates; }
  } catch (e) {}
  return [...MOCK_DATES];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function esc(s) { const d = document.createElement('div'); d.textContent = String(s ?? ''); return d.innerHTML; }

function fmtDate(iso) {
  const d = new Date(iso);
  const m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${m[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

function fmtTime(iso) {
  const d = new Date(iso);
  const hh = String(d.getUTCHours()).padStart(2,'0');
  const mm = String(d.getUTCMinutes()).padStart(2,'0');
  return `${hh}:${mm} UTC`;
}

// ---------------------------------------------------------------------------
// Status Pill
// ---------------------------------------------------------------------------

function statusPill(status, lg) {
  const sz = lg ? ' status-pill--lg' : '';
  const label = status.charAt(0).toUpperCase() + status.slice(1);
  const map = {
    pass: ['status-pill--pass', ICONS.check],
    warning: ['status-pill--warning', ICONS.alert],
    watch: ['status-pill--warning', ICONS.alert],
    critical: ['status-pill--critical', ICONS.x],
    missing: ['status-pill--missing', ICONS.x],
    pending: ['status-pill--pending', ICONS.clock],
    info: ['status-pill--info', ICONS.check],
  };
  const [cls, icon] = map[status] || ['status-pill--pending', ''];
  return `<span class="status-pill ${cls}${sz}" aria-label="Status: ${label}">${icon} ${esc(label)}</span>`;
}

function navDot(status) {
  const c = { pass:'#16a34a', warning:'#d97706', critical:'#dc2626', pending:'#9ca3af', missing:'#dc2626' }[status] || '#9ca3af';
  return `<span class="nav-status" aria-hidden="true"><svg width="7" height="7"><circle cx="3.5" cy="3.5" r="3.5" fill="${c}"/></svg></span>`;
}

// ---------------------------------------------------------------------------
// Summary Overview — KPIs + Donut + Bar Chart
// ---------------------------------------------------------------------------

function renderSummaryOverview(data) {
  const r = data.report;
  const totalInst = r.chapters.reduce((s, c) => s + (c.metrics?.instruments_scanned || 0), 0);
  const totalSections = r.chapters.length;
  const activeChapters = data.chapters.filter(c => c.status !== 'pending');

  // Count rule statuses across all active chapters
  let passCount = 0, warnCount = 0, critCount = 0;
  activeChapters.forEach(ch => {
    (ch.rule_blocks || []).forEach(rb => {
      if (rb.status === 'pass') passCount++;
      else if (rb.status === 'warning' || rb.status === 'watch') warnCount++;
      else if (rb.status === 'critical' || rb.status === 'missing') critCount++;
    });
  });
  const totalRules = passCount + warnCount + critCount;

  // KPIs
  document.getElementById('summary-kpis').innerHTML = `
    <div class="kpi-card kpi-card--status">
      ${statusPill(r.status, true)}
      <div><div class="kpi-label">Overall Verdict</div></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value">${esc(totalInst)}</div>
      <div class="kpi-label">Instruments</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value">${esc(r.total_issues)}</div>
      <div class="kpi-label">Issues Found</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value">${totalSections}</div>
      <div class="kpi-label">Sections</div>
    </div>
  `;

  // Donut Chart (SVG)
  const circumference = 2 * Math.PI * 50;
  const total = totalRules || 1;
  const passArc = (passCount / total) * circumference;
  const warnArc = (warnCount / total) * circumference;
  const critArc = (critCount / total) * circumference;

  document.getElementById('summary-donut').innerHTML = `
    <div class="donut-ring">
      <svg viewBox="0 0 140 140">
        <circle stroke="#e5e7eb" stroke-dasharray="${circumference}" stroke-dashoffset="0" />
        <circle stroke="#16a34a" stroke-dasharray="${passArc} ${circumference - passArc}" stroke-dashoffset="0" style="transition:stroke-dasharray 0.8s ease" />
        <circle stroke="#d97706" stroke-dasharray="${warnArc} ${circumference - warnArc}" stroke-dashoffset="${-passArc}" style="transition:stroke-dasharray 0.8s ease" />
        <circle stroke="#dc2626" stroke-dasharray="${critArc} ${circumference - critArc}" stroke-dashoffset="${-(passArc + warnArc)}" style="transition:stroke-dasharray 0.8s ease" />
      </svg>
      <div class="donut-center">
        <div class="donut-center-value">${totalRules}</div>
        <div class="donut-center-label">Rules</div>
      </div>
    </div>
    <div class="donut-legend">
      <div class="donut-legend-item"><span class="donut-legend-dot" style="background:#16a34a"></span><span class="donut-legend-label">Pass</span><span class="donut-legend-count">${passCount}</span></div>
      <div class="donut-legend-item"><span class="donut-legend-dot" style="background:#d97706"></span><span class="donut-legend-label">Warning</span><span class="donut-legend-count">${warnCount}</span></div>
      <div class="donut-legend-item"><span class="donut-legend-dot" style="background:#dc2626"></span><span class="donut-legend-label">Critical</span><span class="donut-legend-count">${critCount}</span></div>
    </div>
  `;

  // Bar Chart — issues per rule
  const bars = [];
  activeChapters.forEach(ch => {
    (ch.rule_blocks || []).forEach(rb => {
      const count = rb.table?.rows?.length || 0;
      const color = rb.status === 'pass' ? 'pass' : rb.status === 'warning' || rb.status === 'watch' ? 'warning' : 'critical';
      bars.push({ label: rb.title, count, color });
    });
  });
  const maxCount = Math.max(...bars.map(b => b.count), 1);

  document.getElementById('summary-bars').innerHTML = `
    <div class="bar-chart-title">Findings by Rule</div>
    ${bars.map(b => `
      <div class="bar-row">
        <div class="bar-label">${esc(b.label)}</div>
        <div class="bar-track">
          <div class="bar-fill bar-fill--${b.color}" style="width:${Math.max((b.count / maxCount) * 100, b.count > 0 ? 4 : 0)}%"></div>
        </div>
        <div class="bar-count">${b.count}</div>
      </div>
    `).join('')}
  `;
}

// ---------------------------------------------------------------------------
// Masthead
// ---------------------------------------------------------------------------

function renderMasthead(data) {
  const r = data.report;
  document.getElementById('masthead-date').textContent = fmtDate(r.date + 'T00:00:00Z');
  document.getElementById('masthead-meta').textContent = `Generated ${fmtTime(r.generated_at)}`;
  document.getElementById('footer-date').textContent = fmtDate(r.date + 'T00:00:00Z');
}

// ---------------------------------------------------------------------------
// Date Picker & Chapter Nav
// ---------------------------------------------------------------------------

function renderDatePicker(dates, current) {
  const list = document.getElementById('date-list');
  list.innerHTML = dates.map(d => `<li><button class="date-btn" role="option" aria-selected="${d === current}" data-date="${esc(d)}">${fmtDate(d + 'T00:00:00Z')}</button></li>`).join('');
  list.querySelectorAll('.date-btn').forEach(btn => {
    btn.addEventListener('click', () => { if (btn.dataset.date !== currentDate) { currentDate = btn.dataset.date; init(); } });
  });
}

function renderChapterNav(chapters) {
  document.getElementById('chapter-nav').innerHTML = chapters.map(ch => `
    <li><a href="#chapter-${esc(ch.slug)}" class="chapter-link" data-chapter="${esc(ch.slug)}">
      <span>${esc(ch.title)}</span>${navDot(ch.status)}
    </a></li>
  `).join('');
}

let scrollObs = null;
function initScrollSpy() {
  if (scrollObs) scrollObs.disconnect();
  const links = document.querySelectorAll('.chapter-link');
  const secs = document.querySelectorAll('.chapter');
  if (!secs.length) return;
  scrollObs = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) { const id = e.target.id.replace('chapter-',''); links.forEach(l => l.classList.toggle('active', l.dataset.chapter === id)); } });
  }, { rootMargin: '-80px 0px -60% 0px', threshold: 0 });
  secs.forEach(s => scrollObs.observe(s));
}

// ---------------------------------------------------------------------------
// Tables
// ---------------------------------------------------------------------------

function cellContent(val, hdr) {
  const h = hdr.toUpperCase();
  if (h === 'STATUS') return statusPill(val);
  if (h === 'INSTRUMENT') return `<span class="inst-tag">${esc(val)}</span>`;
  return esc(val);
}

function renderTable(headers, rows, id) {
  return `<div class="table-wrap"><table class="data-table" aria-label="Data table">
    <thead><tr>${headers.map((h,i) => `<th class="sortable" data-col="${i}" role="columnheader" aria-sort="none">${esc(h)} <span class="sort-indicator">\u2195</span></th>`).join('')}</tr></thead>
    <tbody>${rows.map(row => `<tr>${row.map((c,i) => `<td>${cellContent(c, headers[i])}</td>`).join('')}</tr>`).join('')}</tbody>
  </table></div>`;
}

function attachSorting(container) {
  container.querySelectorAll('.data-table').forEach(tbl => {
    tbl.querySelectorAll('th.sortable').forEach(th => {
      th.addEventListener('click', () => {
        const ci = +th.dataset.col;
        const dir = th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
        tbl.querySelectorAll('th').forEach(h => { h.setAttribute('aria-sort','none'); h.classList.remove('sort-asc','sort-desc'); h.querySelector('.sort-indicator').textContent = '\u2195'; });
        th.setAttribute('aria-sort', dir);
        th.classList.add(dir === 'ascending' ? 'sort-asc' : 'sort-desc');
        th.querySelector('.sort-indicator').textContent = dir === 'ascending' ? '\u2191' : '\u2193';
        const tbody = tbl.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a,b) => {
          const at = a.children[ci].textContent.trim(), bt = b.children[ci].textContent.trim();
          const an = parseFloat(at), bn = parseFloat(bt);
          const cmp = (!isNaN(an) && !isNaN(bn)) ? an - bn : at.localeCompare(bt);
          return dir === 'ascending' ? cmp : -cmp;
        });
        rows.forEach(r => tbody.appendChild(r));
      });
    });
  });
}

// ---------------------------------------------------------------------------
// Rule Block
// ---------------------------------------------------------------------------

function renderRuleBlock(rule) {
  const tbl = rule.table;
  const hasIssues = tbl?.rows?.length > 0;
  let body = '';
  if (rule.description) body += `<p class="rule-description">${esc(rule.description)}</p>`;
  if (rule.note) body += `<p class="rule-description">${esc(rule.note)}</p>`;
  if (hasIssues) body += renderTable(tbl.headers, tbl.rows, rule.ruleId);
  else body += `<div class="empty-state">${ICONS.check} All instruments pass.</div>`;

  return `<details class="rule-block" id="rule-${esc(rule.ruleId)}"${hasIssues ? ' open' : ''}>
    <summary class="rule-header">
      <span class="rule-header-left"><span class="rule-title">${esc(rule.title)}</span></span>
      <span class="rule-header-right">${statusPill(rule.status)}<span class="rule-chevron" aria-hidden="true">${ICONS.chevron}</span></span>
    </summary>
    <div class="rule-body">${body}</div>
  </details>`;
}

// ---------------------------------------------------------------------------
// Chapters
// ---------------------------------------------------------------------------

function renderChapter(ch) {
  const m = ch.metrics;
  let metricsHtml = '';
  if (m?.instruments_scanned) {
    metricsHtml = `<div class="chapter-metrics">
      <div class="chapter-metric"><div class="metric-value">${esc(m.instruments_scanned)}</div><div class="metric-label">Instruments</div></div>
      <div class="chapter-metric"><div class="metric-value">${esc(m.ema_coverage)}</div><div class="metric-label">EMA Coverage</div></div>
      <div class="chapter-metric"><div class="metric-value">${esc(m.issues_found)}</div><div class="metric-label">Issues</div></div>
      <div class="chapter-metric"><div class="metric-value">${esc(m.source)}</div><div class="metric-label">Source</div></div>
    </div>`;
  }

  let rulesHtml = (ch.rule_blocks || []).map(r => renderRuleBlock(r)).join('');

  let recHtml = '';
  if (ch.recommended_changes?.rows?.length) {
    recHtml = `<div class="section-block"><div class="section-block-title">Recommended Changes</div>${renderTable(ch.recommended_changes.headers, ch.recommended_changes.rows, ch.slug+'-rec')}</div>`;
  }

  let dlHtml = '';
  if (ch.downloads?.length) {
    dlHtml = ch.downloads.map((dl, i) => `<div class="section-block">
      <div class="adj-preview-header">
        <span class="adj-preview-label">${esc(dl.label)}</span>
        <button class="btn-download" data-dl-idx="${i}" data-slug="${esc(ch.slug)}">${ICONS.download} Download CSV</button>
      </div>
    </div>`).join('');
  }

  return `<section class="chapter" id="chapter-${esc(ch.slug)}">
    <div class="chapter-header"><h2 class="chapter-title">${esc(ch.title)}</h2>${statusPill(ch.status)}</div>
    <p class="chapter-summary">${esc(ch.summary)}</p>
    ${metricsHtml}${rulesHtml}${recHtml}${dlHtml}
  </section>`;
}

function renderPending(ch) {
  return `<section class="chapter chapter--pending" id="chapter-${esc(ch.slug)}">
    <div class="chapter-header"><h2 class="chapter-title">${esc(ch.title)}</h2>${statusPill('pending')}</div>
    <div class="pending-content">
      <span class="pending-icon">${ICONS.clockLg}</span>
      <div class="pending-text"><strong>Pending integration.</strong><br>${esc(ch.summary)}</div>
    </div>
  </section>`;
}

// ---------------------------------------------------------------------------
// Downloads
// ---------------------------------------------------------------------------

function attachDownloads(data) {
  document.querySelectorAll('.btn-download[data-slug]').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault();
      const ch = data.chapters.find(c => c.slug === btn.dataset.slug);
      const dl = ch?.downloads?.[+btn.dataset.dlIdx];
      if (!dl) return;
      const blob = new Blob([dl.content], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement('a'), { href: url, download: dl.filename, style: 'display:none' });
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  });
}

// ---------------------------------------------------------------------------
// Rail Toggle
// ---------------------------------------------------------------------------

function initRailToggle() {
  const toggle = document.getElementById('rail-toggle');
  const inner = document.getElementById('rail-inner');
  toggle.addEventListener('click', () => { const open = inner.classList.toggle('open'); toggle.setAttribute('aria-expanded', open); });
  document.querySelectorAll('.chapter-link').forEach(l => l.addEventListener('click', () => { inner.classList.remove('open'); toggle.setAttribute('aria-expanded','false'); }));
}

// ---------------------------------------------------------------------------
// Render All
// ---------------------------------------------------------------------------

function renderAll(data) {
  renderMasthead(data);
  renderSummaryOverview(data);
  renderDatePicker(availableDates, currentDate);
  renderChapterNav(data.chapters);

  const el = document.getElementById('chapters');
  el.innerHTML = data.chapters.map(ch => ch.status === 'pending' ? renderPending(ch) : renderChapter(ch)).join('');

  attachSorting(el);
  attachDownloads(data);
  initScrollSpy();
  initRailToggle();
}

async function init() {
  availableDates = await loadDates();
  if (!availableDates.includes(currentDate)) currentDate = availableDates[0];
  currentReport = await loadReport(currentDate);
  renderAll(currentReport);
}

document.addEventListener('DOMContentLoaded', init);
