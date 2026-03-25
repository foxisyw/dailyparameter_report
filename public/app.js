/* ===================================================================
   Daily Parameter Review Dashboard — app.js
   =================================================================== */

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

/** Set to a Vercel Blob base URL to fetch live data; null = use inline mock. */
const BLOB_BASE_URL = null;

// ---------------------------------------------------------------------------
// SVG Icons (inline, no external library)
// ---------------------------------------------------------------------------

const ICONS = {
  checkCircle: `<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5"/><path d="M5 8.5l2 2 4-4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  alertTriangle: `<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 1.5l6.93 12H1.07L8 1.5z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M8 6.5v3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="8" cy="12" r="0.8" fill="currentColor"/></svg>`,
  xCircle: `<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5"/><path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>`,
  clock: `<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5"/><path d="M8 4.5V8l2.5 2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  download: `<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2.5 11v2.5h11V11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 2v8m0 0l-3-3m3 3l3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  chevronDown: `<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  chevronUp: `<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 10l4-4 4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  clockLg: `<svg width="28" height="28" viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="13" stroke="currentColor" stroke-width="1.5"/><path d="M16 9v7l4.5 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
};

// ---------------------------------------------------------------------------
// Mock Data
// ---------------------------------------------------------------------------

const MOCK_DATES = ['2026-03-26', '2026-03-25', '2026-03-24'];

function buildMockReport(date) {
  return {
    meta: {
      date: date,
      generated_at: `${date}T08:05:00Z`,
      version: '1.0.0',
    },
    summary: {
      overall_status: 'warning',
      instruments_scanned: 142,
      sections_reviewed: 3,
      actions_needed: 4,
    },
    sections: [
      // --- Price Limit (active) ---
      {
        id: 'price_limit',
        title: 'Price Limit',
        status: 'warning',
        type: 'active',
        summary: 'Price limit parameters were checked across 142 SPOT instruments. 5 instruments have cap values outside the expected bands, and 2 instruments are missing EMA reference data.',
        metrics: {
          instruments: { value: 142, label: 'Instruments' },
          ema_coverage: { value: '98.6%', label: 'EMA Coverage' },
          issues: { value: 7, label: 'Issues Found' },
          source: { value: 'OKX API', label: 'Data Source' },
        },
        rules: [
          {
            id: 'rule_1',
            title: 'Rule 1 — Cap Within EMA Band',
            status: 'warning',
            description: 'Every instrument\'s pxLimitCap should be within +/- 2 standard deviations of the 30-day EMA. Instruments outside this band are flagged.',
            evidence: {
              headers: ['INSTRUMENT', 'INST TYPE', 'CAP', 'EMA_30D', 'BAND_LOW', 'BAND_HIGH', 'STATUS'],
              rows: [
                ['SOL-AUD', 'SPOT', '320.00', '285.12', '260.50', '310.00', 'warning'],
                ['XRP-AUD', 'SPOT', '4.800', '3.920', '3.500', '4.350', 'warning'],
                ['BANANA-USDT', 'SPOT', '82.50', '68.40', '58.20', '78.60', 'critical'],
                ['BNB-USDT', 'SPOT', '645.00', '612.80', '580.00', '646.00', 'warning'],
                ['CRV-USDT', 'SPOT', '1.250', '0.982', '0.850', '1.115', 'critical'],
              ],
            },
          },
          {
            id: 'rule_2',
            title: 'Rule 2 — EMA Reference Present',
            status: 'critical',
            description: 'Every active instrument must have a valid EMA-30D reference price. Missing references prevent automated band calculation.',
            evidence: {
              headers: ['INSTRUMENT', 'INST TYPE', 'EMA_30D', 'LAST UPDATED', 'STATUS'],
              rows: [
                ['SOL-AUD', 'SPOT', '—', '—', 'missing'],
                ['XRP-AUD', 'SPOT', '—', '—', 'missing'],
              ],
            },
          },
          {
            id: 'rule_3',
            title: 'Rule 3 — Topcoin Cap Override',
            status: 'warning',
            description: 'Topcoins (BTC, ETH, SOL, XRP, BNB) should use the hardcoded cap schedule. This rule checks that these instruments have the correct override values rather than the auto-calculated band.',
            evidence: {
              headers: ['INSTRUMENT', 'INST TYPE', 'CURRENT CAP', 'EXPECTED CAP', 'SCHEDULE VER', 'STATUS'],
              rows: [
                ['SOL-AUD', 'SPOT', '320.00', '305.00', 'v2.4', 'warning'],
                ['XRP-AUD', 'SPOT', '4.800', '4.200', 'v2.4', 'warning'],
              ],
            },
          },
          {
            id: 'rule_4',
            title: 'Rule 4 — Floor-to-Cap Ratio',
            status: 'pass',
            description: 'The ratio between pxLimitFloor and pxLimitCap should be between 0.3 and 0.7. Ratios outside this range indicate misconfigured bounds.',
            evidence: null,
          },
        ],
        recommended_changes: {
          headers: ['INSTRUMENT', 'CHANGE', 'REASON'],
          rows: [
            ['SOL-AUD', 'Set cap to 305.00 (from 320.00)', 'Topcoin schedule v2.4 override; also outside EMA band'],
            ['XRP-AUD', 'Set cap to 4.200 (from 4.800)', 'Topcoin schedule v2.4 override; also outside EMA band'],
          ],
        },
        adjustment_preview: {
          inst_type: 'SPOT',
          headers: ['INSTRUMENT', 'INST TYPE', 'FIELD', 'OLD VALUE', 'NEW VALUE', 'REASON'],
          rows: [
            ['SOL-AUD', 'SPOT', 'pxLimitCap', '320.00', '305.00', 'Topcoin override v2.4'],
            ['XRP-AUD', 'SPOT', 'pxLimitCap', '4.800', '4.200', 'Topcoin override v2.4'],
          ],
        },
      },
      // --- MMR Futures (pending) ---
      {
        id: 'mmr_futures',
        title: 'MMR Futures',
        status: 'pending',
        type: 'pending',
        expected_date: 'March 28, 2026',
        summary: 'Maintenance margin ratio review for futures instruments.',
      },
      // --- Index (pending) ---
      {
        id: 'index',
        title: 'Index',
        status: 'pending',
        type: 'pending',
        expected_date: 'March 28, 2026',
        summary: 'Index composition and weighting review.',
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Data Loading
// ---------------------------------------------------------------------------

let currentReport = null;
let currentDate = MOCK_DATES[0];

async function loadReport(date) {
  date = date || currentDate;

  if (BLOB_BASE_URL) {
    try {
      const url = `${BLOB_BASE_URL}/reports/${date}/report.json`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn('Blob fetch failed, falling back to mock:', err.message);
      return buildMockReport(date);
    }
  }

  return buildMockReport(date);
}

// ---------------------------------------------------------------------------
// Rendering Helpers
// ---------------------------------------------------------------------------

function esc(str) {
  const d = document.createElement('div');
  d.textContent = String(str);
  return d.innerHTML;
}

function formatDate(iso) {
  const d = new Date(iso);
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${months[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

function formatDateTime(iso) {
  const d = new Date(iso);
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `Generated ${months[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()} ${hh}:${mm} UTC`;
}

// ---------------------------------------------------------------------------
// Status Pill
// ---------------------------------------------------------------------------

function renderStatusPill(status, size) {
  const sizeClass = size === 'lg' ? ' status-pill--lg' : '';
  const label = status.charAt(0).toUpperCase() + status.slice(1);
  let icon = '';
  let cls = '';

  switch (status) {
    case 'pass':
      icon = ICONS.checkCircle;
      cls = 'status-pill--pass';
      break;
    case 'warning':
    case 'watch':
      icon = ICONS.alertTriangle;
      cls = 'status-pill--warning';
      break;
    case 'critical':
      icon = ICONS.xCircle;
      cls = 'status-pill--critical';
      break;
    case 'missing':
      icon = ICONS.xCircle;
      cls = 'status-pill--missing';
      break;
    case 'pending':
      icon = ICONS.clock;
      cls = 'status-pill--pending';
      break;
    case 'info':
      icon = ICONS.checkCircle;
      cls = 'status-pill--info';
      break;
    default:
      icon = '';
      cls = 'status-pill--pending';
  }

  return `<span class="status-pill ${cls}${sizeClass}" aria-label="Status: ${label}">${icon} ${esc(label)}</span>`;
}

// Small dot indicator for nav
function renderNavDot(status) {
  const colorMap = {
    pass: 'var(--status-pass)',
    warning: 'var(--status-warning)',
    critical: 'var(--status-critical)',
    pending: 'var(--status-pending)',
    missing: 'var(--status-critical)',
  };
  const c = colorMap[status] || 'var(--status-pending)';
  return `<span class="nav-status" aria-hidden="true"><svg width="8" height="8"><circle cx="4" cy="4" r="4" fill="${c}"/></svg></span>`;
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function renderHero(report) {
  const ts = document.getElementById('hero-timestamp');
  ts.textContent = formatDateTime(report.meta.generated_at);
  ts.setAttribute('datetime', report.meta.generated_at);

  const metrics = document.getElementById('hero-metrics');
  const s = report.summary;

  metrics.innerHTML = `
    <div class="metric-card metric-card--status">
      ${renderStatusPill(s.overall_status, 'lg')}
      <div>
        <div class="metric-label">Overall Status</div>
      </div>
    </div>
    <div class="metric-card">
      <div class="metric-value">${esc(s.instruments_scanned)}</div>
      <div class="metric-label">Instruments Scanned</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">${esc(s.sections_reviewed)}</div>
      <div class="metric-label">Sections Reviewed</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">${esc(s.actions_needed)}</div>
      <div class="metric-label">Actions Needed</div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Date Picker
// ---------------------------------------------------------------------------

function renderDatePicker(dates, current) {
  const list = document.getElementById('date-list');
  list.innerHTML = dates.map(d => {
    const selected = d === current;
    return `<li>
      <button class="date-btn" role="option"
        aria-selected="${selected}"
        data-date="${esc(d)}">
        ${formatDate(d + 'T00:00:00Z')}
      </button>
    </li>`;
  }).join('');

  list.querySelectorAll('.date-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const date = btn.dataset.date;
      if (date !== currentDate) {
        currentDate = date;
        init();
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Chapter Nav (scrollspy)
// ---------------------------------------------------------------------------

function renderChapterNav(sections) {
  const nav = document.getElementById('chapter-nav');
  nav.innerHTML = sections.map(s => `
    <li>
      <a href="#chapter-${esc(s.id)}" class="chapter-link" data-chapter="${esc(s.id)}">
        <span>${esc(s.title)}</span>
        ${renderNavDot(s.status)}
      </a>
    </li>
  `).join('');
}

let scrollSpyObserver = null;

function initScrollSpy() {
  if (scrollSpyObserver) scrollSpyObserver.disconnect();

  const links = document.querySelectorAll('.chapter-link');
  const sections = document.querySelectorAll('.chapter');

  if (!sections.length) return;

  scrollSpyObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.id.replace('chapter-', '');
        links.forEach(l => {
          l.classList.toggle('active', l.dataset.chapter === id);
        });
      }
    });
  }, {
    rootMargin: '-140px 0px -60% 0px',
    threshold: 0,
  });

  sections.forEach(s => scrollSpyObserver.observe(s));
}

// ---------------------------------------------------------------------------
// Table Rendering with Sorting
// ---------------------------------------------------------------------------

function instrumentTagClass(instType) {
  switch ((instType || '').toUpperCase()) {
    case 'SPOT': return 'inst-tag--spot';
    case 'SWAP': return 'inst-tag--swap';
    case 'FUTURES': return 'inst-tag--futures';
    default: return '';
  }
}

function renderCellContent(value, header) {
  const h = header.toUpperCase();
  if (h === 'STATUS') {
    return renderStatusPill(value);
  }
  if (h === 'INST TYPE') {
    return `<span class="inst-tag ${instrumentTagClass(value)}">${esc(value)}</span>`;
  }
  if (h === 'INSTRUMENT') {
    return `<span class="inst-tag">${esc(value)}</span>`;
  }
  return esc(value);
}

function renderTable(headers, rows, tableId) {
  const id = tableId || 'tbl-' + Math.random().toString(36).slice(2, 8);

  // We store the original rows on the wrapper for sorting
  const html = `
    <div class="table-wrap" data-table-id="${id}">
      <table class="data-table" aria-label="Data table">
        <thead>
          <tr>
            ${headers.map((h, i) => `<th class="sortable" data-col="${i}" role="columnheader" aria-sort="none">${esc(h)} <span class="sort-indicator">\u2195</span></th>`).join('')}
          </tr>
        </thead>
        <tbody>
          ${rows.map(row => `<tr>${row.map((cell, i) => `<td>${renderCellContent(cell, headers[i])}</td>`).join('')}</tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;

  return html;
}

// Post-render: attach sort handlers
function attachTableSorting(container) {
  container.querySelectorAll('.data-table').forEach(table => {
    const headers = table.querySelectorAll('th.sortable');
    const tbody = table.querySelector('tbody');
    const thHeaders = Array.from(table.querySelectorAll('thead th'));

    headers.forEach(th => {
      th.addEventListener('click', () => {
        const colIndex = parseInt(th.dataset.col, 10);
        const currentSort = th.getAttribute('aria-sort');
        let direction = 'ascending';
        if (currentSort === 'ascending') direction = 'descending';

        // Reset all
        headers.forEach(h => {
          h.setAttribute('aria-sort', 'none');
          h.classList.remove('sort-asc', 'sort-desc');
          h.querySelector('.sort-indicator').textContent = '\u2195';
        });

        th.setAttribute('aria-sort', direction);
        th.classList.add(direction === 'ascending' ? 'sort-asc' : 'sort-desc');
        th.querySelector('.sort-indicator').textContent = direction === 'ascending' ? '\u2191' : '\u2193';

        const rowEls = Array.from(tbody.querySelectorAll('tr'));
        rowEls.sort((a, b) => {
          const aText = a.children[colIndex].textContent.trim();
          const bText = b.children[colIndex].textContent.trim();
          const aNum = parseFloat(aText);
          const bNum = parseFloat(bText);

          let cmp;
          if (!isNaN(aNum) && !isNaN(bNum)) {
            cmp = aNum - bNum;
          } else {
            cmp = aText.localeCompare(bText);
          }
          return direction === 'ascending' ? cmp : -cmp;
        });

        rowEls.forEach(r => tbody.appendChild(r));
      });
    });
  });
}

// ---------------------------------------------------------------------------
// Rule Block
// ---------------------------------------------------------------------------

function renderRuleBlock(rule) {
  const hasIssues = rule.evidence && rule.evidence.rows && rule.evidence.rows.length > 0;
  const openAttr = hasIssues ? ' open' : '';

  let bodyContent = '';

  if (rule.description) {
    bodyContent += `<p class="rule-description">${esc(rule.description)}</p>`;
  }

  if (hasIssues) {
    bodyContent += renderTable(rule.evidence.headers, rule.evidence.rows, rule.id);
  } else {
    bodyContent += `
      <div class="empty-state">
        ${ICONS.checkCircle}
        All instruments pass.
      </div>
    `;
  }

  return `
    <details class="rule-block" id="rule-${esc(rule.id)}"${openAttr}>
      <summary class="rule-header" aria-expanded="${hasIssues}">
        <span class="rule-header-left">
          <span class="rule-title">${esc(rule.title)}</span>
        </span>
        <span class="rule-header-right">
          ${renderStatusPill(rule.status)}
          <span class="rule-chevron" aria-hidden="true">${ICONS.chevronDown}</span>
        </span>
      </summary>
      <div class="rule-body">
        ${bodyContent}
      </div>
    </details>
  `;
}

// ---------------------------------------------------------------------------
// Active Chapter
// ---------------------------------------------------------------------------

function renderChapter(section) {
  const m = section.metrics;

  let metricsHtml = '';
  if (m) {
    metricsHtml = `
      <div class="chapter-metrics">
        ${Object.values(m).map(metric => `
          <div class="chapter-metric">
            <div class="metric-value">${esc(metric.value)}</div>
            <div class="metric-label">${esc(metric.label)}</div>
          </div>
        `).join('')}
      </div>
    `;
  }

  let rulesHtml = '';
  if (section.rules) {
    rulesHtml = section.rules.map(r => renderRuleBlock(r)).join('');
  }

  let recommendedHtml = '';
  if (section.recommended_changes && section.recommended_changes.rows.length > 0) {
    recommendedHtml = `
      <div class="section-block">
        <div class="section-block-title">Recommended Changes</div>
        ${renderTable(section.recommended_changes.headers, section.recommended_changes.rows, section.id + '-rec')}
      </div>
    `;
  }

  let previewHtml = '';
  if (section.adjustment_preview && section.adjustment_preview.rows.length > 0) {
    const ap = section.adjustment_preview;
    const rowCount = ap.rows.length;
    previewHtml = `
      <div class="section-block">
        <div class="section-block-title">Adjustment Preview</div>
        <div class="adj-preview-header">
          <span class="adj-preview-label">${esc(ap.inst_type)} adjustment (${rowCount} row${rowCount !== 1 ? 's' : ''})</span>
          <button class="btn-download" data-csv-section="${esc(section.id)}" aria-label="Download adjustment CSV">
            ${ICONS.download}
            Download CSV
          </button>
        </div>
        ${renderTable(ap.headers, ap.rows, section.id + '-adj')}
      </div>
    `;
  }

  return `
    <section class="chapter" id="chapter-${esc(section.id)}" aria-labelledby="chapter-title-${esc(section.id)}">
      <div class="chapter-header">
        <h2 class="chapter-title" id="chapter-title-${esc(section.id)}">${esc(section.title)}</h2>
        ${renderStatusPill(section.status)}
      </div>
      <p class="chapter-summary">${esc(section.summary)}</p>
      ${metricsHtml}
      ${rulesHtml}
      ${recommendedHtml}
      ${previewHtml}
    </section>
  `;
}

// ---------------------------------------------------------------------------
// Pending Chapter
// ---------------------------------------------------------------------------

function renderPendingChapter(section) {
  return `
    <section class="chapter chapter--pending" id="chapter-${esc(section.id)}" aria-labelledby="chapter-title-${esc(section.id)}">
      <div class="chapter-header">
        <h2 class="chapter-title" id="chapter-title-${esc(section.id)}">${esc(section.title)}</h2>
        ${renderStatusPill('pending')}
      </div>
      <div class="pending-content">
        <span class="pending-icon" aria-hidden="true">${ICONS.clockLg}</span>
        <div class="pending-text">
          <strong>Pending integration.</strong> Expected by ${esc(section.expected_date)}.<br>
          ${esc(section.summary)}
        </div>
      </div>
    </section>
  `;
}

// ---------------------------------------------------------------------------
// CSV Download
// ---------------------------------------------------------------------------

function generateCSV(headers, rows) {
  const escape = (val) => {
    const s = String(val);
    if (s.includes(',') || s.includes('"') || s.includes('\n')) {
      return '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
  };

  const lines = [
    headers.map(escape).join(','),
    ...rows.map(row => row.map(escape).join(',')),
  ];

  return lines.join('\n');
}

function downloadCSV(filename, csvContent) {
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function attachCSVDownloads(report) {
  document.querySelectorAll('.btn-download[data-csv-section]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const sectionId = btn.dataset.csvSection;
      const section = report.sections.find(s => s.id === sectionId);
      if (!section || !section.adjustment_preview) return;

      const ap = section.adjustment_preview;
      const csv = generateCSV(ap.headers, ap.rows);
      const date = report.meta.date;
      downloadCSV(`${sectionId}_adjustment_${date}.csv`, csv);
    });
  });
}

// ---------------------------------------------------------------------------
// Rail Toggle (mobile)
// ---------------------------------------------------------------------------

function initRailToggle() {
  const toggle = document.getElementById('rail-toggle');
  const inner = document.getElementById('rail-inner');

  toggle.addEventListener('click', () => {
    const isOpen = inner.classList.toggle('open');
    toggle.setAttribute('aria-expanded', isOpen);
  });

  // Close rail when a chapter link is clicked (mobile)
  document.querySelectorAll('.chapter-link').forEach(link => {
    link.addEventListener('click', () => {
      inner.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
    });
  });
}

// ---------------------------------------------------------------------------
// Main Render Pipeline
// ---------------------------------------------------------------------------

function renderAll(report) {
  renderHero(report);
  renderDatePicker(MOCK_DATES, currentDate);
  renderChapterNav(report.sections);

  const chaptersEl = document.getElementById('chapters');
  chaptersEl.innerHTML = report.sections.map(section => {
    if (section.type === 'pending') {
      return renderPendingChapter(section);
    }
    return renderChapter(section);
  }).join('');

  // Post-render hooks
  attachTableSorting(chaptersEl);
  attachCSVDownloads(report);
  initScrollSpy();
  initRailToggle();
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  currentReport = await loadReport(currentDate);
  renderAll(currentReport);
}

document.addEventListener('DOMContentLoaded', init);
