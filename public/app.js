/* ==========================================================================
   Daily Parameter Review
   Shared chapter shell + chapter-specific renderers
   ========================================================================== */

const DATA_BASE = '/data'

let currentLang = localStorage.getItem('lang') || 'en'

const I18N = {
  en: {
    brand: 'PARAMETER REVIEW',
    subtitle: 'Daily Automated Audit',
    generated: 'Generated',
    reportDate: 'Report Date',
    sections: 'Sections',
    navigation: 'Navigation',
    overallVerdict: 'Overall Verdict',
    totalFindings: 'Total Findings',
    activeChapters: 'Active Chapters',
    reportFreshness: 'Report Freshness',
    instruments: 'Instruments',
    emaCoverage: 'EMA Coverage',
    issues: 'Issues',
    source: 'Source',
    pass: 'Pass',
    warning: 'Warning',
    critical: 'Critical',
    missing: 'Missing',
    pending: 'Pending',
    watch: 'Watch',
    rules: 'Rules',
    findingsByRule: 'Findings by Rule',
    parameterAlarm: 'Parameter Alarm',
    parameterAlarmDesc: 'Daily risk alert summary — Index Alarm, Price Limit P4, Collateral Coin, and Platform OI.',
    forwardLooking: 'Outlook',
    causalChain: 'Causal Chain',
    recommendedChanges: 'Recommended Changes',
    downloadCsv: 'Download CSV',
    allPass: 'All checks passed.',
    pendingIntegration: 'Pending integration.',
    footerOrg: 'OKX Parameter Management',
    footerAuto: 'Automated Daily Review',
    sourceDocument: 'Source Document',
    selectedBy: 'Selection Rule',
    suspiciousUsers: 'Suspicious Users',
    suspiciousUsersEmpty: 'No suspicious users were highlighted.',
    userDeepDive: 'User Deep Dive',
    userProfilesEmpty: 'No user profiles were generated.',
    riskLevel: 'Risk',
    sourceAlert: 'Source Alert',
    reason: 'Reason',
    action: 'Action',
    viewProfile: 'View Profile',
    profileUnavailable: 'Unavailable',
    executiveSummary: 'Executive Summary',
    keyEvidence: 'Key Evidence',
    localArtifact: 'Local Artifact',
    uid: 'UID',
    masterUserId: 'Master ID',
    noEvidence: 'No evidence attached.',
  },
  zh: {
    brand: '參數審查報告',
    subtitle: '每日自動化審計',
    generated: '生成時間',
    reportDate: '報告日期',
    sections: '章節',
    navigation: '導航',
    overallVerdict: '整體結論',
    totalFindings: '總發現數',
    activeChapters: '有效章節',
    reportFreshness: '報告新鮮度',
    instruments: '幣對數量',
    emaCoverage: 'EMA 覆蓋',
    issues: '問題數',
    source: '來源',
    pass: '通過',
    warning: '警告',
    critical: '嚴重',
    missing: '缺失',
    pending: '待接入',
    watch: '關注',
    rules: '規則',
    findingsByRule: '各規則發現數量',
    parameterAlarm: '參數報警',
    parameterAlarmDesc: '每日風控報警匯總 — 指數報警、限價報警、小幣抵押、平台OI。',
    forwardLooking: '前瞻性判斷',
    causalChain: '因果鏈條',
    recommendedChanges: '建議調整',
    downloadCsv: '下載 CSV',
    allPass: '所有檢查通過。',
    pendingIntegration: '待接入整合。',
    footerOrg: 'OKX 參數管理',
    footerAuto: '自動化每日審查',
    sourceDocument: '來源文檔',
    selectedBy: '選取規則',
    suspiciousUsers: '可疑用戶',
    suspiciousUsersEmpty: '今日沒有高亮可疑用戶。',
    userDeepDive: '單用戶深描',
    userProfilesEmpty: '今日沒有生成用戶畫像。',
    riskLevel: '風險',
    sourceAlert: '來源警報',
    reason: '原因',
    action: '操作',
    viewProfile: '查看畫像',
    profileUnavailable: '暫無',
    executiveSummary: '綜合判斷',
    keyEvidence: '關鍵證據',
    localArtifact: '本地產物',
    uid: 'UID',
    masterUserId: '主賬號 ID',
    noEvidence: '沒有附帶證據。',
  },
}

const ICONS = {
  check: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M3 8.5l3.5 3.5L13 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  alert: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2l6.93 12H1.07L8 2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 7v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="12.5" r="0.7" fill="currentColor"/></svg>`,
  x: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/><path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>`,
  clock: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/><path d="M8 5v3l2 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  download: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M3 11v2.5h10V11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 2.5v7.5m0 0l-2.5-2.5M8 10l2.5-2.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  chevron: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  clockLg: `<svg width="24" height="24" viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="12" stroke="currentColor" stroke-width="1.5"/><path d="M16 10v6l3.5 2.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
}

function T(key) {
  return I18N[currentLang]?.[key] || I18N.en[key] || key
}

function esc(value) {
  const node = document.createElement('div')
  node.textContent = String(value ?? '')
  return node.innerHTML
}

function fmtDate(iso) {
  const date = new Date(iso)
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${months[date.getUTCMonth()]} ${date.getUTCDate()}, ${date.getUTCFullYear()}`
}

function fmtTime(iso) {
  const date = new Date(iso)
  const hkt = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  const hh = String(hkt.getUTCHours()).padStart(2, '0')
  const mm = String(hkt.getUTCMinutes()).padStart(2, '0')
  return `${hh}:${mm} HKT`
}

function statusLabel(status) {
  const map = { pass: 'pass', warning: 'warning', critical: 'critical', missing: 'missing', pending: 'pending', watch: 'watch' }
  return T(map[status] || status)
}

function statusPill(status, large = false) {
  const size = large ? ' status-pill--lg' : ''
  const label = statusLabel(status)
  const map = {
    pass: ['status-pill--pass', ICONS.check],
    warning: ['status-pill--warning', ICONS.alert],
    watch: ['status-pill--warning', ICONS.alert],
    critical: ['status-pill--critical', ICONS.x],
    missing: ['status-pill--missing', ICONS.x],
    pending: ['status-pill--pending', ICONS.clock],
    info: ['status-pill--info', ICONS.check],
  }
  const [cls, icon] = map[status] || ['status-pill--pending', ICONS.clock]
  return `<span class="status-pill ${cls}${size}" aria-label="Status: ${esc(label)}">${icon} ${esc(label)}</span>`
}

function navDot(status) {
  const color = { pass: '#16a34a', warning: '#d97706', critical: '#dc2626', pending: '#9ca3af', missing: '#dc2626' }[status] || '#9ca3af'
  return `<span class="nav-status" aria-hidden="true"><svg width="7" height="7"><circle cx="3.5" cy="3.5" r="3.5" fill="${color}"/></svg></span>`
}

function normalizeRenderVariant(chapter) {
  return chapter.render_variant || (chapter.slug === 'risk-intel' ? 'risk-intel' : 'rules')
}

function deriveMetricCards(chapter) {
  if (chapter.metric_cards?.length) return chapter.metric_cards
  const metrics = chapter.metrics || {}
  return [
    { label: T('instruments'), value: metrics.instruments_scanned ?? 0 },
    { label: T('emaCoverage'), value: metrics.ema_coverage ?? 0 },
    { label: T('issues'), value: metrics.issues_found ?? 0 },
    { label: T('source'), value: metrics.source ?? 'n/a' },
  ]
}

function sourceAlertLabel(value) {
  const map = {
    index_alarm: 'Index Alarm',
    price_limit_p4: 'Price Limit P4',
    collateral_coin: 'Collateral Coin',
    platform_oi: 'Platform OI',
  }
  return map[value] || value
}

function riskTierToStatus(value) {
  const tier = String(value || '').toUpperCase()
  if (tier === 'T4' || tier === 'CRITICAL') return 'critical'
  if (tier === 'T2' || tier === 'T3' || tier === 'HIGH' || tier === 'MEDIUM') return 'warning'
  if (tier === 'PENDING') return 'pending'
  return 'pass'
}

function riskTierText(value) {
  return String(value || 'T1').toUpperCase()
}

function fmtFreshness(iso) {
  return fmtTime(iso)
}

function chapterProfileId(chapterSlug, key) {
  const safe = String(key || 'unknown').replace(/[^a-zA-Z0-9_-]/g, '-')
  return `profile-${chapterSlug}-${safe}`
}

const MOCK_DATES = ['2026-03-26', '2026-03-25', '2026-03-24']

function buildMockReport(date) {
  return {
    report: {
      date,
      generated_at: `${date}T09:15:00Z`,
      status: 'critical',
      total_issues: 20,
      chapters: [
        {
          slug: 'price-limit',
          title: 'Price Limit Review',
          status: 'warning',
          summary: '7 issues found across 1472 instruments.',
          metrics: { instruments_scanned: 1472, ema_coverage: 1472, issues_found: 7, source: 'OKX API', generated_at: `${date}T08:05:00Z` },
        },
        {
          slug: 'risk-intel',
          title: 'Risk Intelligence',
          status: 'critical',
          summary: '4 alert types analyzed. 11 flagged alerts. 3 suspicious users highlighted.',
          metrics: { instruments_scanned: 11, ema_coverage: 4, issues_found: 14, source: '每日风控总结', generated_at: `${date}T09:15:00Z` },
        },
        {
          slug: 'mmr-futures',
          title: 'MMR Futures Review',
          status: 'pending',
          summary: 'Integration pending — ETA March 28, 2026.',
          metrics: { instruments_scanned: 0, ema_coverage: 0, issues_found: 0, source: 'n/a', generated_at: `${date}T08:05:00Z` },
        },
        {
          slug: 'index-review',
          title: 'Index Review',
          status: 'pending',
          summary: 'Integration pending — ETA March 28, 2026.',
          metrics: { instruments_scanned: 0, ema_coverage: 0, issues_found: 0, source: 'n/a', generated_at: `${date}T08:05:00Z` },
        },
      ],
    },
    chapters: [
      {
        slug: 'price-limit',
        title: 'Price Limit Review',
        render_variant: 'rules',
        status: 'warning',
        summary: '7 issues found across 1472 instruments. 5 instruments have buffers marginally thin, 2 have asset-type consistency issues.',
        metrics: { instruments_scanned: 1472, ema_coverage: 1472, issues_found: 7, source: 'OKX API (live)', generated_at: `${date}T08:05:00Z` },
        metric_cards: [
          { label: 'Instruments', value: '1472' },
          { label: 'EMA Coverage', value: '1472' },
          { label: 'Issues', value: '7' },
          { label: 'Source', value: 'OKX API' },
        ],
        rule_blocks: [
          {
            ruleId: 'buffer_tight',
            title: 'Buffer Too Tight',
            status: 'warning',
            description: 'Checks if limit price buffers are persistently too thin.',
            table: {
              headers: ['INSTRUMENT', 'LIMITUP_BUFFER', 'LIMITDN_BUFFER', 'STATUS'],
              rows: [
                ['BNB-USDT', '0.84%', '0.16%', 'warning'],
                ['CRV-USDT', '1.57%', '0.42%', 'warning'],
              ],
            },
            note: null,
          },
          {
            ruleId: 'consistency',
            title: 'Asset-Type Consistency',
            status: 'warning',
            description: 'Flags caps that drift from the target range for the asset class.',
            table: {
              headers: ['INSTRUMENT', 'CURRENT Y', 'CURRENT Z', 'EXPECTED Y', 'EXPECTED Z', 'STATUS'],
              rows: [
                ['SOL-AUD', '2%', '5%', '1%', '2%', 'warning'],
                ['XRP-AUD', '2%', '5%', '1%', '2%', 'warning'],
              ],
            },
            note: null,
          },
          {
            ruleId: 'basis_asymmetric',
            title: 'Asymmetric Basis',
            status: 'pass',
            description: 'No asymmetric basis exception crossed the current threshold.',
            table: null,
            note: null,
          },
          {
            ruleId: 'z_gt_y',
            title: 'Z Cap > Y Cap',
            status: 'pass',
            description: 'No structural cap hierarchy break was found.',
            table: null,
            note: null,
          },
        ],
        recommended_changes: {
          headers: ['INSTRUMENT', 'CHANGE', 'REASON'],
          rows: [
            ['SOL-AUD', 'Y: 2%→1%, Z: 5%→2%', 'Topcoins standard'],
            ['XRP-AUD', 'Y: 2%→1%, Z: 5%→2%', 'Topcoins standard'],
          ],
        },
        downloads: [],
        markdown: '',
        error: null,
        source_document: null,
        suspicious_users: [],
        user_profiles: [],
      },
      {
        slug: 'risk-intel',
        title: 'Risk Intelligence',
        render_variant: 'risk-intel',
        status: 'critical',
        summary: '4 alert types analyzed. 11 flagged alerts. 3 suspicious users highlighted.',
        metrics: { instruments_scanned: 11, ema_coverage: 4, issues_found: 14, source: '每日风控总结', generated_at: `${date}T09:15:00Z` },
        metric_cards: [
          { label: 'Alert Types', value: '4' },
          { label: 'Flagged Alerts', value: '11' },
          { label: 'Suspicious Users', value: '3' },
          { label: 'Highest Risk', value: 'T4' },
        ],
        source_document: {
          title: `每日风控总结 - ${date} (00:00 - 23:59)`,
          url: 'https://okg-block.sg.larksuite.com/drive/folder/Wu2Pfktq6lq4t8dWL52lB97pgQb',
          modified_at: `${date}T12:30:00Z`,
          selected_by: 'latest_modified_desc',
        },
        rule_blocks: [
          {
            ruleId: 'index_alarm',
            title: 'Index Alarm',
            status: 'critical',
            description: 'CRCL index components drifted materially during the afternoon window.',
            table: {
              headers: ['ASSET', 'DETAILS', 'USERS', 'STATUS'],
              rows: [
                ['CRCL', 'Index component price divergence exceeded 4.2% during 15:00-16:00 HKT.', '—', 'critical'],
                ['ONT', 'Index quote briefly disappeared before self-healing.', '—', 'warning'],
              ],
            },
            note: null,
          },
          {
            ruleId: 'price_limit_p4',
            title: 'Price Limit P4',
            status: 'critical',
            description: 'CRCL hit Z-cap hard tops while ONT repeatedly touched its inner band.',
            table: {
              headers: ['ASSET', 'DETAILS', 'USERS', 'STATUS'],
              rows: [
                ['CRCL-USDT-SWAP', 'Hard-top trigger twice; review quote protection and participant behavior.', 'UID 612133499092760604 / MID 62247621', 'critical'],
                ['ONT-USDT-SWAP', 'Repeated inner-band proximity in the same session.', 'UID 612133499092760605 / MID 62247622', 'warning'],
              ],
            },
            note: null,
          },
          {
            ruleId: 'collateral_coin',
            title: 'Collateral Coin Risk',
            status: 'warning',
            description: 'Collateral pressure is concentrated in BANANA and ZENT.',
            table: {
              headers: ['ASSET', 'DETAILS', 'USERS', 'STATUS'],
              rows: [
                ['BANANA', 'borrow/limit reached 96.2% with order restrictions in effect.', 'UID 612133499092760604', 'warning'],
                ['ZENT', 'borrow/limit reached 84.1%; monitor for further deterioration.', 'UID 612133499092760606 / MID 62247623', 'warning'],
              ],
            },
            note: null,
          },
          {
            ruleId: 'platform_oi',
            title: 'Platform OI',
            status: 'critical',
            description: 'CRCL carried both OI deviation and platform-limit pressure. ONT was a smaller follow-on risk.',
            table: {
              headers: ['ASSET', 'DETAILS', 'USERS', 'STATUS'],
              rows: [
                ['CRCL', 'OI deviated 56.15% vs the 24H average.', 'UID 612133499092760604 / MID 62247621', 'critical'],
                ['CRCL', 'OI / platform limit reached 82%.', 'UID 612133499092760606 / MID 62247623', 'critical'],
                ['ONT', 'OI / circulating market cap reached 13.4%.', 'UID 612133499092760605 / MID 62247622', 'warning'],
              ],
            },
            note: null,
          },
        ],
        recommended_changes: null,
        downloads: [],
        markdown: '',
        error: null,
        suspicious_users: [
          { uid: '612133499092760604', master_user_id: '62247621', risk_tier: 'T4', source_alert: 'price_limit_p4', reason: 'Repeated CRCL appearances across Price Limit, Collateral, and Platform OI alerts.' },
          { uid: '612133499092760606', master_user_id: '62247623', risk_tier: 'T4', source_alert: 'platform_oi', reason: 'Secondary CRCL OI concentration aligned with platform-limit pressure.' },
          { uid: '612133499092760605', master_user_id: '62247622', risk_tier: 'T3', source_alert: 'platform_oi', reason: 'ONT concentration persists across Platform OI and Price Limit signals.' },
        ],
        user_profiles: [
          {
            uid: '612133499092760604',
            master_user_id: '62247621',
            overall_risk_tier: 'T4',
            executive_summary: 'Newer account with fast trading activation, concentrated CRCL exposure, and repeated appearance across stress signals.',
            key_evidence: [
              'Registration-to-first-trade latency under 24 hours.',
              'CRCL concentration exceeded 80% of visible activity.',
            ],
            local_artifact_ref: 'local://user-risk/612133499092760604.html',
            dimensions: [
              { name: 'Registration Profile', severity: 'warning', signals: ['Account age under 30 days.', 'First trade happened on registration day.'] },
              { name: 'Trading Behavior', severity: 'critical', signals: ['CRCL concentration exceeded 80%.', 'Price-limit and OI-linked behavior repeated.'] },
              { name: 'Associated Accounts', severity: 'warning', signals: ['Related-account screening recommended for same-day CRCL timing.'] },
              { name: 'IP & Geolocation', severity: 'warning', signals: ['Region changed twice within the review window.'] },
              { name: 'Identity Signals', severity: 'warning', signals: ['Profile information needs consistency review against the activity pattern.'] },
              { name: 'Profit & Loss', severity: 'warning', signals: ['Profit concentration skews heavily to the stressed instrument.'] },
              { name: 'Withdrawal Behavior', severity: 'warning', signals: ['Withdrawal timing clusters after CRCL volatility windows.'] },
              { name: 'Comprehensive Judgment', severity: 'critical', signals: ['Pattern fits a high-priority manipulation review candidate.'] },
            ],
          },
          {
            uid: '612133499092760606',
            master_user_id: '62247623',
            overall_risk_tier: 'T2',
            executive_summary: 'Cross-appears in collateral and OI alerts, but the current evidence strength remains moderate.',
            key_evidence: ['Secondary CRCL OI alert plus one collateral pressure event.'],
            local_artifact_ref: 'local://user-risk/612133499092760606.html',
            dimensions: [
              { name: 'Registration Profile', severity: 'pass', signals: ['No abnormal onboarding timing detected.'] },
              { name: 'Trading Behavior', severity: 'warning', signals: ['Activity clusters around CRCL event windows.'] },
              { name: 'Associated Accounts', severity: 'pass', signals: ['No direct related-account signal in this snapshot.'] },
              { name: 'IP & Geolocation', severity: 'pass', signals: ['No high-risk region indicator in this snapshot.'] },
              { name: 'Identity Signals', severity: 'pass', signals: ['No strong identity inconsistency surfaced.'] },
              { name: 'Profit & Loss', severity: 'warning', signals: ['Profit is concentrated in a small number of risk events.'] },
              { name: 'Withdrawal Behavior', severity: 'pass', signals: ['No suspicious withdrawal timing pattern was attached.'] },
              { name: 'Comprehensive Judgment', severity: 'warning', signals: ['Keep on watch but no T3/T4 escalation yet.'] },
            ],
          },
          {
            uid: '612133499092760605',
            master_user_id: '62247622',
            overall_risk_tier: 'T3',
            executiveSummary: 'ONT-linked alerts are narrower in scope but still show concentration and repeated inner-band pressure.',
            executive_summary: 'ONT-linked alerts are narrower in scope but still show concentration and repeated inner-band pressure.',
            key_evidence: ['Appears in both Price Limit P4 and Platform OI sections.'],
            local_artifact_ref: 'local://user-risk/612133499092760605.html',
            dimensions: [
              { name: 'Registration Profile', severity: 'pass', signals: ['Account age and onboarding speed are within normal bounds.'] },
              { name: 'Trading Behavior', severity: 'warning', signals: ['ONT dominates recent visible activity.', 'Execution is taker-heavy around alert windows.'] },
              { name: 'Associated Accounts', severity: 'warning', signals: ['Needs related-account screening due to concurrent ONT timing.'] },
              { name: 'IP & Geolocation', severity: 'pass', signals: ['No material geo anomaly surfaced in the latest snapshot.'] },
              { name: 'Identity Signals', severity: 'pass', signals: ['No strong identity inconsistency was surfaced.'] },
              { name: 'Profit & Loss', severity: 'warning', signals: ['PnL remains concentrated in a single stressed asset.'] },
              { name: 'Withdrawal Behavior', severity: 'pass', signals: ['No acute withdrawal stress signal was captured.'] },
              { name: 'Comprehensive Judgment', severity: 'warning', signals: ['Escalate if ONT concentration persists across multiple days.'] },
            ],
          },
        ],
      },
      {
        slug: 'mmr-futures',
        title: 'MMR Futures Review',
        render_variant: 'rules',
        status: 'pending',
        summary: 'Integration pending — ETA March 28, 2026.',
        metrics: { instruments_scanned: 0, ema_coverage: 0, issues_found: 0, source: 'n/a', generated_at: `${date}T08:05:00Z` },
        metric_cards: [
          { label: 'Instruments', value: '0' },
          { label: 'EMA Coverage', value: '0' },
          { label: 'Issues', value: '0' },
          { label: 'Source', value: 'n/a' },
        ],
        rule_blocks: [],
        recommended_changes: null,
        downloads: [],
        markdown: '',
        error: null,
        source_document: null,
        suspicious_users: [],
        user_profiles: [],
      },
      {
        slug: 'index-review',
        title: 'Index Review',
        render_variant: 'rules',
        status: 'pending',
        summary: 'Integration pending — ETA March 28, 2026.',
        metrics: { instruments_scanned: 0, ema_coverage: 0, issues_found: 0, source: 'n/a', generated_at: `${date}T08:05:00Z` },
        metric_cards: [
          { label: 'Instruments', value: '0' },
          { label: 'EMA Coverage', value: '0' },
          { label: 'Issues', value: '0' },
          { label: 'Source', value: 'n/a' },
        ],
        rule_blocks: [],
        recommended_changes: null,
        downloads: [],
        markdown: '',
        error: null,
        source_document: null,
        suspicious_users: [],
        user_profiles: [],
      },
    ],
  }
}

let currentReport = null
let currentDate = MOCK_DATES[0]
let availableDates = [...MOCK_DATES]
let activeTab = 'risk-intel'  // default tab

async function loadReport(date) {
  try {
    const response = await fetch(`${DATA_BASE}/reports/${date}/report.json`)
    if (response.ok) return await response.json()
  } catch (error) {
    console.warn('Failed to load report:', error.message)
  }
  return buildMockReport(date)
}

async function loadDates() {
  try {
    const response = await fetch(`${DATA_BASE}/reports/index.json`)
    if (response.ok) {
      const data = await response.json()
      if (data.dates?.length) return data.dates
    }
  } catch (error) {}
  return [...MOCK_DATES]
}

function renderSummaryOverview(data) {
  const report = data.report
  const riskChapter = data.chapters.find(ch => ch.slug === 'risk-intel')
  const allChapters = data.chapters.filter(ch => ch.status !== 'pending')
  const suspiciousUsers = riskChapter?.suspicious_users || []
  const alertBlocks = riskChapter?.rule_blocks || []

  // Count alert severities from risk intel (primary) + other chapters
  let passCount = 0, warnCount = 0, critCount = 0
  allChapters.forEach(ch => {
    ;(ch.rule_blocks || []).forEach(rule => {
      if (rule.status === 'pass') passCount++
      else if (rule.status === 'warning' || rule.status === 'watch') warnCount++
      else if (rule.status === 'critical' || rule.status === 'missing') critCount++
    })
  })

  const totalRules = passCount + warnCount + critCount || 1
  const circumference = 2 * Math.PI * 50
  const passArc = (passCount / totalRules) * circumference
  const warnArc = (warnCount / totalRules) * circumference
  const critArc = (critCount / totalRules) * circumference

  // KPIs focus on risk intelligence
  const highestTier = suspiciousUsers.reduce((max, u) => {
    const rank = { T4: 4, T3: 3, T2: 2, T1: 1 }
    return (rank[u.risk_tier] || 0) > (rank[max] || 0) ? u.risk_tier : max
  }, 'T1')

  document.getElementById('summary-kpis').innerHTML = `
    <div class="kpi-card kpi-card--status">
      ${statusPill(report.status, true)}
      <div><div class="kpi-label">${T('overallVerdict')}</div></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value">${esc(report.total_issues)}</div>
      <div class="kpi-label">${T('totalFindings')}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value">${suspiciousUsers.length}</div>
      <div class="kpi-label">${T('suspiciousUsers')}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value">${esc(fmtFreshness(report.generated_at))}</div>
      <div class="kpi-label">${T('reportFreshness')}</div>
    </div>
  `

  document.getElementById('summary-donut').innerHTML = `
    <div class="donut-ring">
      <svg viewBox="0 0 140 140">
        <circle stroke="#e5e7eb" stroke-dasharray="${circumference}" stroke-dashoffset="0" />
        <circle stroke="#16a34a" stroke-dasharray="${passArc} ${circumference - passArc}" stroke-dashoffset="0" />
        <circle stroke="#d97706" stroke-dasharray="${warnArc} ${circumference - warnArc}" stroke-dashoffset="${-passArc}" />
        <circle stroke="#dc2626" stroke-dasharray="${critArc} ${circumference - critArc}" stroke-dashoffset="${-(passArc + warnArc)}" />
      </svg>
      <div class="donut-center">
        <div class="donut-center-value">${passCount + warnCount + critCount}</div>
        <div class="donut-center-label">${T('rules')}</div>
      </div>
    </div>
    <div class="donut-legend">
      <div class="donut-legend-item"><span class="donut-legend-dot" style="background:#16a34a"></span><span class="donut-legend-label">${T('pass')}</span><span class="donut-legend-count">${passCount}</span></div>
      <div class="donut-legend-item"><span class="donut-legend-dot" style="background:#d97706"></span><span class="donut-legend-label">${T('warning')}</span><span class="donut-legend-count">${warnCount}</span></div>
      <div class="donut-legend-item"><span class="donut-legend-dot" style="background:#dc2626"></span><span class="donut-legend-label">${T('critical')}</span><span class="donut-legend-count">${critCount}</span></div>
    </div>
  `

  // Bar chart: show risk alert types first, then other rules
  const bars = []
  // Risk intel alert types first
  alertBlocks.forEach(rule => {
    const count = rule.table?.rows?.length || 0
    const color = rule.status === 'pass' ? 'pass' : rule.status === 'warning' || rule.status === 'watch' ? 'warning' : 'critical'
    bars.push({ label: rule.title, count, color })
  })
  // Then other chapter rules
  allChapters.filter(ch => ch.slug !== 'risk-intel').forEach(ch => {
    ;(ch.rule_blocks || []).forEach(rule => {
      const count = rule.table?.rows?.length || 0
      const color = rule.status === 'pass' ? 'pass' : rule.status === 'warning' || rule.status === 'watch' ? 'warning' : 'critical'
      bars.push({ label: rule.title, count, color })
    })
  })
  const maxCount = Math.max(...bars.map(bar => bar.count), 1)

  document.getElementById('summary-bars').innerHTML = `
    <div class="bar-chart-title">${T('findingsByRule')}</div>
    ${bars.map(bar => `
      <div class="bar-row">
        <div class="bar-label">${esc(bar.label)}</div>
        <div class="bar-track">
          <div class="bar-fill bar-fill--${bar.color}" style="width:${Math.max((bar.count / maxCount) * 100, bar.count > 0 ? 4 : 0)}%"></div>
        </div>
        <div class="bar-count">${bar.count}</div>
      </div>
    `).join('')}
  `
}

function renderMasthead(data) {
  const report = data.report
  document.querySelector('.masthead-brand').textContent = T('brand')
  document.querySelector('.masthead-sub').textContent = T('subtitle')
  document.getElementById('footer-date').textContent = fmtDate(`${report.date}T00:00:00Z`)
  document.querySelector('.report-footer span:first-child').textContent = T('footerOrg')
  document.querySelectorAll('.report-footer span')[2].textContent = T('footerAuto')
}

function renderDateDropdown(dates, current) {
  const dropdown = document.getElementById('date-dropdown')
  dropdown.innerHTML = dates.map(d =>
    `<option value="${esc(d)}"${d === current ? ' selected' : ''}>${fmtDate(`${d}T00:00:00Z`)}</option>`
  ).join('')
  dropdown.onchange = () => {
    if (dropdown.value !== currentDate) {
      currentDate = dropdown.value
      init()
    }
  }
}

let activeSection = null  // tracks which sub-section is active within a tab

function buildSectionList(chapter) {
  const variant = normalizeRenderVariant(chapter)
  const sections = []
  const colors = { critical: '#dc2626', warning: '#d97706', pass: '#16a34a', pending: '#9ca3af' }

  if (variant === 'risk-intel') {
    // Each event analysis is its own section (includes its users + profiles)
    const events = chapter.event_analyses || []
    events.forEach(e => {
      sections.push({ id: `event-${e.asset}`, label: e.asset, color: colors[e.severity] || '#9ca3af', type: 'event' })
    })
    // Combined parameter alarm section (all rule_blocks)
    if ((chapter.rule_blocks || []).length) {
      const worstStatus = chapter.rule_blocks.reduce((w, rb) => rb.status === 'critical' ? 'critical' : rb.status === 'warning' && w !== 'critical' ? 'warning' : w, 'pass')
      sections.push({ id: 'parameter-alarm', label: T('parameterAlarm') || 'Parameter Alarm', color: colors[worstStatus] || '#9ca3af', type: 'alarm' })
    }
  } else {
    // Price Limit etc: rule blocks + recommended changes + downloads
    ;(chapter.rule_blocks || []).forEach(rb => {
      sections.push({ id: `rule-${rb.ruleId}`, label: rb.title, color: colors[rb.status] || '#9ca3af', type: 'rule' })
    })
    if (chapter.recommended_changes?.rows?.length) {
      sections.push({ id: 'recommended-changes', label: T('recommendedChanges') || 'Recommended Changes', color: '#6b7280', type: 'rule' })
    }
    if (chapter.downloads?.length) {
      sections.push({ id: 'downloads', label: T('downloads') || 'Downloads', color: '#6b7280', type: 'rule' })
    }
  }

  return sections
}

function renderSectionNav(data) {
  const chapter = data.chapters.find(ch => ch.slug === activeTab)
  const nav = document.getElementById('section-nav')
  const label = document.getElementById('rail-label')

  if (!chapter || chapter.status === 'pending') {
    nav.innerHTML = ''
    label.textContent = T('sections')
    activeSection = null
    return
  }

  label.textContent = chapter.title
  const sections = buildSectionList(chapter)

  // Default to first section
  if (!activeSection || !sections.find(s => s.id === activeSection)) {
    activeSection = sections.length ? sections[0].id : null
  }

  nav.innerHTML = sections.map(s => `
    <li><button class="section-link${s.id === activeSection ? ' active' : ''}" data-section="${esc(s.id)}">
      <span class="section-dot" style="background:${s.color}"></span>
      <span>${esc(s.label)}</span>
    </button></li>
  `).join('')

  const variant = normalizeRenderVariant(chapter)
  nav.querySelectorAll('.section-link').forEach(btn => {
    btn.addEventListener('click', () => {
      if (variant === 'risk-intel') {
        // Risk Intel: switch section (replace content)
        activeSection = btn.dataset.section
        renderAll(currentReport)
      } else {
        // Price Limit etc: scroll to section
        const target = document.getElementById(btn.dataset.section)
        if (target) {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' })
          if (target.tagName === 'DETAILS') target.open = true
        }
        nav.querySelectorAll('.section-link').forEach(b => b.classList.remove('active'))
        btn.classList.add('active')
      }
    })
  })
}

function renderChapterNav(chapters) {
  document.getElementById('chapter-nav').innerHTML = chapters.map(chapter => `
    <li><a href="#chapter-${esc(chapter.slug)}" class="chapter-link" data-chapter="${esc(chapter.slug)}">
      <span>${esc(chapter.title)}</span>${navDot(chapter.status)}
    </a></li>
  `).join('')
}

let scrollObserver = null

function initScrollSpy() {
  if (scrollObserver) scrollObserver.disconnect()
  const links = document.querySelectorAll('.chapter-link')
  const sections = document.querySelectorAll('.chapter')
  if (!sections.length) return
  scrollObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.id.replace('chapter-', '')
        links.forEach(link => link.classList.toggle('active', link.dataset.chapter === id))
      }
    })
  }, { rootMargin: '-80px 0px -60% 0px', threshold: 0 })
  sections.forEach(section => scrollObserver.observe(section))
}

function cellContent(value, header) {
  const normalized = header.toUpperCase()
  if (normalized === 'STATUS') return statusPill(value)
  if (normalized === 'INSTRUMENT' || normalized === 'ASSET') return `<span class="inst-tag">${esc(value)}</span>`
  return esc(value)
}

function renderTable(headers, rows) {
  return `<div class="table-wrap"><table class="data-table" aria-label="Data table">
    <thead><tr>${headers.map((header, index) => `<th class="sortable" data-col="${index}" role="columnheader" aria-sort="none">${esc(header)} <span class="sort-indicator">↕</span></th>`).join('')}</tr></thead>
    <tbody>${rows.map(row => `<tr>${row.map((cell, index) => `<td>${cellContent(cell, headers[index])}</td>`).join('')}</tr>`).join('')}</tbody>
  </table></div>`
}

function attachSorting(container) {
  container.querySelectorAll('.data-table').forEach(table => {
    table.querySelectorAll('th.sortable').forEach(th => {
      th.addEventListener('click', () => {
        const columnIndex = Number(th.dataset.col)
        const direction = th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending'
        table.querySelectorAll('th').forEach(header => {
          header.setAttribute('aria-sort', 'none')
          header.classList.remove('sort-asc', 'sort-desc')
          header.querySelector('.sort-indicator').textContent = '↕'
        })
        th.setAttribute('aria-sort', direction)
        th.classList.add(direction === 'ascending' ? 'sort-asc' : 'sort-desc')
        th.querySelector('.sort-indicator').textContent = direction === 'ascending' ? '↑' : '↓'
        const tbody = table.querySelector('tbody')
        const rows = Array.from(tbody.querySelectorAll('tr'))
        rows.sort((rowA, rowB) => {
          const a = rowA.children[columnIndex].textContent.trim()
          const b = rowB.children[columnIndex].textContent.trim()
          const numA = parseFloat(a)
          const numB = parseFloat(b)
          const cmp = !Number.isNaN(numA) && !Number.isNaN(numB) ? numA - numB : a.localeCompare(b)
          return direction === 'ascending' ? cmp : -cmp
        })
        rows.forEach(row => tbody.appendChild(row))
      })
    })
  })
}

function renderRuleBlock(rule) {
  const hasRows = rule.table?.rows?.length > 0
  let body = ''
  if (rule.description) body += `<p class="rule-description">${esc(rule.description)}</p>`
  if (rule.note) body += `<p class="rule-description">${esc(rule.note)}</p>`
  if (hasRows) body += renderTable(rule.table.headers, rule.table.rows)
  else body += `<div class="empty-state">${ICONS.check} ${T('allPass')}</div>`
  return `<details class="rule-block" id="rule-${esc(rule.ruleId)}"${hasRows ? ' open' : ''}>
    <summary class="rule-header">
      <span class="rule-header-left"><span class="rule-title">${esc(rule.title)}</span></span>
      <span class="rule-header-right">${statusPill(rule.status)}<span class="rule-chevron" aria-hidden="true">${ICONS.chevron}</span></span>
    </summary>
    <div class="rule-body">${body}</div>
  </details>`
}

function renderMetricCards(chapter) {
  const cards = deriveMetricCards(chapter)
  if (!cards.length) return ''
  return `<div class="chapter-metrics">
    ${cards.map(card => `
      <div class="chapter-metric">
        <div class="metric-value">${esc(card.value)}</div>
        <div class="metric-label">${esc(card.label)}</div>
      </div>
    `).join('')}
  </div>`
}

function renderSourceDocument(chapter) {
  const doc = chapter.source_document
  if (!doc) return ''
  return `<div class="source-document">
    <div class="source-document-title">${T('sourceDocument')}</div>
    <div class="source-document-body">
      <a href="${esc(doc.url)}" target="_blank" rel="noreferrer">${esc(doc.title)}</a>
      <span>${esc(fmtTime(doc.modified_at))}</span>
      <span>${T('selectedBy')}: ${esc(doc.selected_by || 'latest_modified_desc')}</span>
    </div>
  </div>`
}

function renderRecommendations(chapter) {
  if (!chapter.recommended_changes?.rows?.length) return ''
  return `<details class="section-block" id="recommended-changes">
    <summary class="section-block-title" style="cursor:pointer;display:flex;align-items:center;justify-content:space-between">
      ${T('recommendedChanges')} (${chapter.recommended_changes.rows.length})
      <span class="chapter-collapse-chevron" aria-hidden="true">${ICONS.chevron}</span>
    </summary>
    <div style="padding-top:8px">${renderTable(chapter.recommended_changes.headers, chapter.recommended_changes.rows)}</div>
  </details>`
}

function renderDownloads(chapter) {
  if (!chapter.downloads?.length) return ''
  return chapter.downloads.map((download, index) => `
    <div class="section-block" id="downloads">
      <div class="adj-preview-header">
        <span class="adj-preview-label">${esc(download.label)}</span>
        <button class="btn-download" data-dl-idx="${index}" data-slug="${esc(chapter.slug)}">${ICONS.download} ${T('downloadCsv')}</button>
      </div>
    </div>
  `).join('')
}

function renderChapterShell(chapter, innerHtml, includeHeader = true) {
  const header = includeHeader
    ? `<div class="chapter-header"><h2 class="chapter-title">${esc(chapter.title)}</h2>${statusPill(chapter.status)}</div>`
    : ''
  return `<section class="chapter" id="chapter-${esc(chapter.slug)}">
    ${header}
    <p class="chapter-summary">${esc(chapter.summary)}</p>
    ${renderMetricCards(chapter)}
    ${innerHtml}
  </section>`
}

function renderRulesChapter(chapter) {
  const rulesHtml = (chapter.rule_blocks || []).map(renderRuleBlock).join('')
  // No header — the collapsible wrapper provides it
  return renderChapterShell(chapter, `${rulesHtml}${renderRecommendations(chapter)}${renderDownloads(chapter)}`, false)
}

function renderSuspiciousUsers(chapter) {
  const users = chapter.suspicious_users || []
  const profiles = new Map((chapter.user_profiles || []).map(profile => [profile.uid || profile.master_user_id, profile]))
  if (!users.length) {
    return `<div class="section-block"><div class="section-block-title">${T('suspiciousUsers')}</div><div class="empty-state">${ICONS.check} ${T('suspiciousUsersEmpty')}</div></div>`
  }
  return `<div class="section-block" id="suspicious-users">
    <div class="section-block-title">${T('suspiciousUsers')}</div>
    <div class="table-wrap">
      <table class="data-table risk-table" aria-label="Suspicious users">
        <thead>
          <tr>
            <th>${T('masterUserId')}</th>
            <th>${T('relatedPair') || 'PAIR'}</th>
            <th>${T('riskLevel')}</th>
            <th>${T('reason')}</th>
            <th>${T('action')}</th>
          </tr>
        </thead>
        <tbody>
          ${users.map(user => {
            const profileKey = user.uid || user.master_user_id
            const hasProfile = profiles.has(profileKey)
            return `<tr>
              <td><span class="inst-tag">${esc(user.master_user_id || user.uid || '—')}</span></td>
              <td><span class="inst-tag" style="font-size:11px">${esc(user.related_pair || sourceAlertLabel(user.source_alert))}</span></td>
              <td>${statusPill(riskTierToStatus(user.risk_tier))} <span class="risk-tier-label">${esc(riskTierText(user.risk_tier))}</span></td>
              <td style="white-space:normal;max-width:300px">${esc(user.reason || '—')}</td>
              <td>${hasProfile ? `<button class="btn-profile-link" data-profile-target="${esc(chapterProfileId(chapter.slug, profileKey))}">${T('viewProfile')}</button>` : `<span class="profile-unavailable">${T('profileUnavailable')}</span>`}</td>
            </tr>`
          }).join('')}
        </tbody>
      </table>
    </div>
  </div>`
}

function renderUserProfiles(chapter) {
  const profiles = chapter.user_profiles || []
  if (!profiles.length) {
    return `<div class="section-block"><div class="section-block-title">${T('userDeepDive')}</div><div class="empty-state">${ICONS.clock} ${T('userProfilesEmpty')}</div></div>`
  }
  return `<div class="section-block" id="user-profiles">
    <div class="section-block-title">${T('userDeepDive')}</div>
    <div class="user-profiles">
      ${profiles.map(profile => {
        const key = profile.uid || profile.master_user_id
        const summary = profile.executive_summary || profile.executiveSummary || ''
        return `<details class="user-profile" id="${esc(chapterProfileId(chapter.slug, key))}">
          <summary class="user-profile-summary">
            <div class="user-profile-heading">
              <strong>${esc(profile.uid || profile.master_user_id || 'Unknown')}</strong>
              <span class="user-profile-meta">${T('masterUserId')}: ${esc(profile.master_user_id || '—')}</span>
            </div>
            <div class="user-profile-badges">
              ${statusPill(riskTierToStatus(profile.overall_risk_tier))}
              <span class="risk-tier-chip">${esc(riskTierText(profile.overall_risk_tier))}</span>
              <span class="rule-chevron" aria-hidden="true">${ICONS.chevron}</span>
            </div>
          </summary>
          <div class="user-profile-body">
            <div class="user-profile-summary-block">
              <div class="user-profile-section-label">${T('executiveSummary')}</div>
              <p>${esc(summary || '—')}</p>
            </div>
            <div class="dimension-grid">
              ${(profile.dimensions || []).map(dimension => `
                <div class="dimension-card">
                  <div class="dimension-card-header">
                    <div class="dimension-card-title">${esc(dimension.name)}</div>
                    ${statusPill(dimension.severity)}
                  </div>
                  <ul class="dimension-signals">
                    ${(dimension.signals || []).slice(0, 3).map(signal => `<li>${esc(signal)}</li>`).join('')}
                  </ul>
                </div>
              `).join('')}
            </div>
            <div class="user-profile-summary-block">
              <div class="user-profile-section-label">${T('keyEvidence')}</div>
              <ul class="evidence-list">
                ${(profile.key_evidence?.length ? profile.key_evidence : [T('noEvidence')]).map(item => `<li>${esc(item)}</li>`).join('')}
              </ul>
            </div>
            ${profile.local_artifact_ref ? `
              <div class="user-profile-summary-block">
                <div class="user-profile-section-label">${T('localArtifact')}</div>
                <div class="artifact-ref">${esc(profile.local_artifact_ref)}</div>
              </div>
            ` : ''}
          </div>
        </details>`
      }).join('')}
    </div>
  </div>`
}

function renderChainLink(link) {
  const stars = '\u2605'.repeat(link.evidence_strength) + '\u2606'.repeat(5 - link.evidence_strength)

  let detailHtml = ''
  if (link.detail) {
    detailHtml += `<div class="cl-detail">${esc(link.detail)}</div>`
  }
  if (link.evidence_table) {
    const et = link.evidence_table
    detailHtml += `<div class="cl-evidence">
      <div class="cl-evidence-label">${esc(et.title || 'Evidence')}</div>
      <div class="table-wrap"><table class="data-table">
        <thead><tr>${et.headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead>
        <tbody>${(et.rows || []).map(row => `<tr>${row.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody>
      </table></div>
      ${et.source ? `<div class="cl-source">${esc(et.source)}</div>` : ''}
    </div>`
  }
  if (link.risk_assessment) {
    detailHtml += `<div class="cl-assessment">${esc(link.risk_assessment)}</div>`
  }

  return `<tr class="cl-row">
    <td class="cl-step">${link.step}</td>
    <td class="cl-type">${esc(link.type)}</td>
    <td>
      <div class="cl-name">${esc(link.name)}</div>
      <div class="cl-desc">${esc(link.description)}</div>
      ${detailHtml}
    </td>
    <td class="cl-stars">${stars}<br><span class="cl-stars-label">${esc(link.evidence_label)}</span></td>
  </tr>`
}

function renderEventAnalyses(chapter) {
  const events = chapter.event_analyses || []
  if (!events.length) return ''

  return `<div class="section-block">
    <div class="section-block-title">${T('eventAnalysis') || 'Event Analysis'}</div>
    ${events.map(event => {
      const snap = event.market_snapshot || {}
      const snapCards = snap.price ? `
        <div class="ev-metrics">
          <div class="ev-metric"><span class="ev-metric-val">\$${esc(snap.price)}</span><span class="ev-metric-lbl">PRICE</span></div>
          <div class="ev-metric"><span class="ev-metric-val">${esc(snap.change_24h)}</span><span class="ev-metric-lbl">24H</span></div>
          <div class="ev-metric"><span class="ev-metric-val">${parseFloat(snap.funding_rate) ? (parseFloat(snap.funding_rate) * 100).toFixed(3) + '%' : '\u2014'}</span><span class="ev-metric-lbl">FUNDING</span></div>
          <div class="ev-metric"><span class="ev-metric-val">${parseFloat(snap.open_interest) ? (parseFloat(snap.open_interest)/1000).toFixed(0) + 'K' : '\u2014'}</span><span class="ev-metric-lbl">OI</span></div>
        </div>` : ''

      const chainRows = (event.causal_chain || []).map(link => renderChainLink(link)).join('')

      return `<details class="ev-card" id="event-${esc(event.asset)}" open>
        <summary class="ev-header">
          <div class="ev-header-left">
            <span class="ev-asset">${esc(event.asset)}</span>
            ${statusPill(event.severity)}
          </div>
          <span class="chapter-collapse-chevron" aria-hidden="true">${ICONS.chevron}</span>
        </summary>
        <div class="ev-body">
          ${snapCards}
          <div class="ev-summary">${esc(event.executive_summary)}</div>
          ${event.forward_looking ? `<div class="ev-outlook"><strong>${T('forwardLooking') || 'Outlook'}:</strong> ${esc(event.forward_looking)}</div>` : ''}
          ${chainRows ? `
            <div class="ev-chain-header">${T('causalChain') || 'Causal Chain'}</div>
            <div class="table-wrap">
              <table class="data-table ev-chain-table">
                <thead><tr><th>#</th><th>${T('chainType') || 'TYPE'}</th><th>${T('chainDetail') || 'DETAIL'}</th><th>${T('chainEvidence') || 'EVIDENCE'}</th></tr></thead>
                <tbody>${chainRows}</tbody>
              </table>
            </div>` : ''}
        </div>
      </details>`
    }).join('')}
  </div>`
}

function renderRiskIntelChapter(chapter) {
  const eventsHtml = renderEventAnalyses(chapter)
  const rulesHtml = (chapter.rule_blocks || []).map(renderRuleBlock).join('')
  return renderChapterShell(chapter, `${renderSourceDocument(chapter)}${eventsHtml}${rulesHtml}${renderSuspiciousUsers(chapter)}${renderUserProfiles(chapter)}`)
}

function renderPending(chapter) {
  // No header — the collapsible wrapper provides it
  return `<section class="chapter chapter--pending" id="chapter-${esc(chapter.slug)}">
    <div class="pending-content">
      <span class="pending-icon">${ICONS.clockLg}</span>
      <div class="pending-text"><strong>${T('pendingIntegration')}</strong><br>${esc(chapter.summary)}</div>
    </div>
  </section>`
}

function wrapCollapsible(chapter, html) {
  // Risk Intelligence is always expanded. All other sections are collapsed by default.
  const variant = normalizeRenderVariant(chapter)
  if (variant === 'risk-intel') return html
  return `<details class="chapter-collapsible" id="collapsible-${esc(chapter.slug)}">
    <summary class="chapter-collapse-header">
      <div class="chapter-collapse-left">
        <h2 class="chapter-title">${esc(chapter.title)}</h2>
        ${statusPill(chapter.status)}
      </div>
      <span class="chapter-collapse-chevron" aria-hidden="true">${ICONS.chevron}</span>
    </summary>
    <div class="chapter-collapse-body">${html}</div>
  </details>`
}

function renderChapter(chapter) {
  const variant = normalizeRenderVariant(chapter)
  if (chapter.status === 'pending') return wrapCollapsible(chapter, renderPending(chapter))
  if (variant === 'risk-intel') return renderRiskIntelChapter(chapter)
  return wrapCollapsible(chapter, renderRulesChapter(chapter))
}

function attachDownloads(data) {
  document.querySelectorAll('.btn-download[data-slug]').forEach(button => {
    button.addEventListener('click', event => {
      event.preventDefault()
      const chapter = data.chapters.find(item => item.slug === button.dataset.slug)
      const download = chapter?.downloads?.[Number(button.dataset.dlIdx)]
      if (!download) return
      const blob = new Blob([download.content], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const link = Object.assign(document.createElement('a'), { href: url, download: download.filename, style: 'display:none' })
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    })
  })
}

function attachProfileLinks() {
  document.querySelectorAll('.btn-profile-link[data-profile-target]').forEach(button => {
    button.addEventListener('click', event => {
      event.preventDefault()
      const target = document.getElementById(button.dataset.profileTarget)
      if (!target) return
      target.open = true
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  })
}

function initRailToggle() {
  const toggle = document.getElementById('rail-toggle')
  const inner = document.getElementById('rail-inner')
  toggle.addEventListener('click', () => {
    const open = inner.classList.toggle('open')
    toggle.setAttribute('aria-expanded', open)
  })
  document.querySelectorAll('.chapter-link').forEach(link => {
    link.addEventListener('click', () => {
      inner.classList.remove('open')
      toggle.setAttribute('aria-expanded', 'false')
    })
  })
}

function renderTabBar(data) {
  const tabBar = document.getElementById('tab-bar')
  const statusColors = { pass: '#16a34a', warning: '#d97706', critical: '#dc2626', pending: '#9ca3af' }

  tabBar.innerHTML = data.chapters.map(ch => {
    const isActive = ch.slug === activeTab
    const color = statusColors[ch.status] || '#9ca3af'
    return `<button class="tab-btn${isActive ? ' active' : ''}" role="tab" aria-selected="${isActive}" data-tab="${esc(ch.slug)}">
      <span class="tab-dot" style="background:${color}"></span>
      ${esc(ch.title)}
    </button>`
  }).join('')

  tabBar.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      activeTab = btn.dataset.tab
      renderAll(currentReport)
    })
  })
}

function renderTabSummary(data) {
  const chapter = data.chapters.find(ch => ch.slug === activeTab)
  if (!chapter) return

  const variant = normalizeRenderVariant(chapter)

  if (variant === 'risk-intel') {
    renderRiskIntelSummary(data, chapter)
  } else if (chapter.status === 'pending') {
    renderPendingSummary(chapter)
  } else {
    renderPriceLimitSummary(data, chapter)
  }
}

function renderRiskIntelSummary(data, chapter) {
  const events = chapter.event_analyses || []
  const users = chapter.suspicious_users || []
  const blocks = chapter.rule_blocks || []

  document.getElementById('summary-kpis').innerHTML = `
    <div class="kpi-card kpi-card--status">${statusPill(chapter.status, true)}<div><div class="kpi-label">${T('overallVerdict')}</div></div></div>
    <div class="kpi-card"><div class="kpi-value">${events.length}</div><div class="kpi-label">${T('eventAnalysis') || 'EVENTS'}</div></div>
    <div class="kpi-card"><div class="kpi-value">${users.length}</div><div class="kpi-label">${T('suspiciousUsers')}</div></div>
    <div class="kpi-card"><div class="kpi-value">${esc(fmtFreshness(data.report.generated_at))}</div><div class="kpi-label">${T('reportFreshness')}</div></div>
  `

  // No pie chart — replaced with empty space or hidden
  document.getElementById('summary-donut').innerHTML = ''

  const bars = blocks.map(b => ({
    label: b.title,
    count: b.table?.rows?.length || 0,
    color: b.status === 'pass' ? 'pass' : b.status === 'warning' ? 'warning' : 'critical',
  }))
  const maxCount = Math.max(...bars.map(b => b.count), 1)

  document.getElementById('summary-bars').innerHTML = `
    <div class="bar-chart-title">${T('parameterAlarmFindings') || 'Parameter Alarm Findings'}</div>
    ${bars.map(b => `<div class="bar-row">
      <div class="bar-label">${esc(b.label)}</div>
      <div class="bar-track"><div class="bar-fill bar-fill--${b.color}" style="width:${Math.max((b.count / maxCount) * 100, b.count > 0 ? 4 : 0)}%"></div></div>
      <div class="bar-count">${b.count}</div>
    </div>`).join('')}
  `
}

function renderPriceLimitSummary(data, chapter) {
  const blocks = chapter.rule_blocks || []
  let critCount = 0, warnCount = 0, passCount = 0
  blocks.forEach(b => {
    if (b.status === 'critical' || b.status === 'missing') critCount++
    else if (b.status === 'warning' || b.status === 'watch') warnCount++
    else passCount++
  })
  const metrics = chapter.metrics || {}

  document.getElementById('summary-kpis').innerHTML = `
    <div class="kpi-card kpi-card--status">${statusPill(chapter.status, true)}<div><div class="kpi-label">${T('overallVerdict')}</div></div></div>
    <div class="kpi-card"><div class="kpi-value">${esc(metrics.instruments_scanned || 0)}</div><div class="kpi-label">${T('instruments')}</div></div>
    <div class="kpi-card"><div class="kpi-value">${esc(metrics.issues_found || 0)}</div><div class="kpi-label">${T('issuesFound')}</div></div>
    <div class="kpi-card"><div class="kpi-value">${esc(fmtFreshness(data.report.generated_at))}</div><div class="kpi-label">${T('reportFreshness')}</div></div>
  `

  document.getElementById('summary-donut').innerHTML = ''

  const bars = blocks.map(b => ({
    label: b.title,
    count: b.table?.rows?.length || 0,
    color: b.status === 'pass' ? 'pass' : b.status === 'warning' ? 'warning' : 'critical',
  }))
  const maxCount = Math.max(...bars.map(b => b.count), 1)

  document.getElementById('summary-bars').innerHTML = `
    <div class="bar-chart-title">${T('findingsByRule')}</div>
    ${bars.map(b => `<div class="bar-row">
      <div class="bar-label">${esc(b.label)}</div>
      <div class="bar-track"><div class="bar-fill bar-fill--${b.color}" style="width:${Math.max((b.count / maxCount) * 100, b.count > 0 ? 4 : 0)}%"></div></div>
      <div class="bar-count">${b.count}</div>
    </div>`).join('')}
  `
}

function renderPendingSummary(chapter) {
  document.getElementById('summary-kpis').innerHTML = `
    <div class="kpi-card kpi-card--status">${statusPill('pending', true)}<div><div class="kpi-label">${T('overallVerdict')}</div></div></div>
    <div class="kpi-card"><div class="kpi-value">0</div><div class="kpi-label">${T('instruments')}</div></div>
    <div class="kpi-card"><div class="kpi-value">0</div><div class="kpi-label">${T('issuesFound')}</div></div>
    <div class="kpi-card"><div class="kpi-value">\u2014</div><div class="kpi-label">${T('reportFreshness')}</div></div>
  `
  document.getElementById('summary-donut').innerHTML = '<div style="text-align:center;color:var(--gray-400);font-size:13px;padding:40px 0">' + T('pendingIntegration') + '</div>'
  document.getElementById('summary-bars').innerHTML = ''
}

function renderQuantitativeImpact(event) {
  const qi = event.quantitative_impact
  if (!qi || !qi.metrics || !qi.metrics.length) return ''
  return `<div class="section-block">
    <div class="section-block-title">${esc(qi.title || T('quantitativeImpact') || 'Quantitative Impact')}</div>
    <div class="impact-grid">
      ${qi.metrics.map(m => `<div class="impact-card">
        <div class="impact-val">${esc(m.value)}</div>
        <div class="impact-label">${esc(m.label)}</div>
        ${m.detail ? `<div class="impact-detail">${esc(m.detail)}</div>` : ''}
      </div>`).join('')}
    </div>
  </div>`
}

function renderOIAttribution(event) {
  const oia = event.oi_attribution
  if (!oia || !oia.user_hourly_table) return ''
  const t = oia.user_hourly_table
  return `<div class="section-block">
    <div class="section-block-title">${esc(oia.title || 'OI Attribution')}</div>
    ${oia.description ? `<p class="ev-summary" style="margin-bottom:10px">${esc(oia.description)}</p>` : ''}
    <div class="table-wrap"><table class="data-table">
      <thead><tr>${t.headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead>
      <tbody>${(t.rows || []).map(row => `<tr>${row.map((c, i) => {
        const isFlip = i > 0 && c && row[i] !== row[Math.max(1, i-1)] && c !== '—' && c !== '0'
        return `<td${isFlip ? ' class="oi-flip"' : ''}>${esc(c)}</td>`
      }).join('')}</tr>`).join('')}</tbody>
    </table></div>
  </div>`
}

function renderRiskAssessment(event) {
  const ra = event.risk_assessment
  if (!ra || !ra.actions || !ra.actions.length) return ''
  const prioColors = { P0: 'var(--critical)', P1: 'var(--warning)', P2: 'var(--gray-500)' }
  return `<div class="section-block">
    <div class="section-block-title">${esc(ra.title || T('riskAssessment') || 'Risk Assessment')}</div>
    <div class="action-list">
      ${ra.actions.map(a => `<div class="action-item action-item--${a.priority.toLowerCase()}">
        <span class="action-prio" style="background:${prioColors[a.priority] || 'var(--gray-500)'}">${esc(a.priority)}</span>
        <div class="action-body">
          <div class="action-text">${esc(a.action)}</div>
          ${a.reason ? `<div class="action-reason">${esc(a.reason)}</div>` : ''}
        </div>
      </div>`).join('')}
    </div>
  </div>`
}

function renderInvolvedUsersBrief(event) {
  const iub = event.involved_users_brief
  if (!iub || !iub.rows || !iub.rows.length) return ''
  return `<div class="section-block">
    <div class="section-block-title">${esc(iub.title || T('involvedUsers') || 'Involved Users')}</div>
    <div class="table-wrap"><table class="data-table">
      <thead><tr>${iub.headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead>
      <tbody>${iub.rows.map(row => `<tr>${row.map((c, i) => {
        const h = iub.headers[i]?.toUpperCase() || ''
        if (h === 'RISK') return `<td>${statusPill(c === 'T3' || c === 'T4' ? 'critical' : c === 'T2' ? 'warning' : 'pass')}</td>`
        return `<td>${esc(c)}</td>`
      }).join('')}</tr>`).join('')}</tbody>
    </table></div>
  </div>`
}

function renderSingleEventSection(chapter, event) {
  const snap = event.market_snapshot || {}
  const snapCards = snap.price ? `
    <div class="ev-metrics">
      <div class="ev-metric"><span class="ev-metric-val">\$${esc(snap.price)}</span><span class="ev-metric-lbl">PRICE</span></div>
      <div class="ev-metric"><span class="ev-metric-val">${esc(snap.change_24h)}</span><span class="ev-metric-lbl">24H</span></div>
      <div class="ev-metric"><span class="ev-metric-val">${parseFloat(snap.funding_rate) ? (parseFloat(snap.funding_rate) * 100).toFixed(3) + '%' : '\u2014'}</span><span class="ev-metric-lbl">FUNDING</span></div>
      <div class="ev-metric"><span class="ev-metric-val">${parseFloat(snap.open_interest) ? (parseFloat(snap.open_interest)/1000).toFixed(0) + 'K' : '\u2014'}</span><span class="ev-metric-lbl">OI</span></div>
    </div>` : ''

  const chainRows = (event.causal_chain || []).map(link => renderChainLink(link)).join('')

  // Each event has its OWN user_profiles — NOT shared from chapter
  const eventProfiles = event.user_profiles || []

  return `<section class="chapter" id="event-${esc(event.asset)}">
    <div class="chapter-header"><h2 class="chapter-title">${esc(event.asset)}</h2>${statusPill(event.severity)}</div>
    ${snapCards}
    ${renderQuantitativeImpact(event)}
    <div class="section-block">
      <div class="section-block-title">${T('executiveSummary') || 'Executive Summary'}</div>
      <div class="ev-summary">${esc(event.executive_summary)}</div>
      ${event.forward_looking ? `<div class="ev-outlook"><strong>${T('forwardLooking') || 'Outlook'}:</strong> ${esc(event.forward_looking)}</div>` : ''}
    </div>
    ${chainRows ? `<div class="section-block">
      <div class="section-block-title">${T('causalChain') || 'Causal Chain'}</div>
      <div class="table-wrap"><table class="data-table ev-chain-table">
        <thead><tr><th>#</th><th>${T('chainType') || 'TYPE'}</th><th>${T('chainDetail') || 'DETAIL'}</th><th>${T('chainEvidence') || 'EVIDENCE'}</th></tr></thead>
        <tbody>${chainRows}</tbody>
      </table></div>
    </div>` : ''}
    ${renderOIAttribution(event)}
    ${renderRiskAssessment(event)}
    ${renderInvolvedUsersBrief(event)}
    ${eventProfiles.length ? renderUserProfiles({ user_profiles: eventProfiles, slug: event.asset }) : ''}
  </section>`
}

function renderParameterAlarmSection(chapter) {
  // Combined view of all rule_blocks (Index Alarm, Price Limit P4, Collateral Coin, Platform OI)
  const rulesHtml = (chapter.rule_blocks || []).map(renderRuleBlock).join('')
  return `<section class="chapter" id="parameter-alarm">
    <div class="chapter-header"><h2 class="chapter-title">${T('parameterAlarm') || 'Parameter Alarm'}</h2></div>
    <p class="chapter-summary">${T('parameterAlarmDesc') || 'Daily risk alert summary from the Trading Risk Bot — Index Alarm, Price Limit, Collateral Coin, and Platform OI.'}</p>
    ${rulesHtml}
  </section>`
}

function renderActiveTabContent(data) {
  const chapter = data.chapters.find(ch => ch.slug === activeTab)
  const chaptersNode = document.getElementById('chapters')

  if (!chapter) {
    chaptersNode.innerHTML = '<div style="padding:40px;text-align:center;color:var(--gray-400)">No data</div>'
    return
  }

  if (chapter.status === 'pending') {
    chaptersNode.innerHTML = renderPending(chapter)
    return
  }

  const variant = normalizeRenderVariant(chapter)

  if (variant === 'risk-intel') {
    // Section-based rendering: show only the active section
    if (activeSection && activeSection.startsWith('event-')) {
      const assetId = activeSection.replace('event-', '')
      const event = (chapter.event_analyses || []).find(e => e.asset === assetId)
      if (event) {
        chaptersNode.innerHTML = renderSingleEventSection(chapter, event)
      } else {
        chaptersNode.innerHTML = '<div style="padding:40px;color:var(--gray-400)">Event not found</div>'
      }
    } else if (activeSection === 'parameter-alarm') {
      chaptersNode.innerHTML = renderParameterAlarmSection(chapter)
    } else {
      // Default: show first event
      const events = chapter.event_analyses || []
      if (events.length) {
        chaptersNode.innerHTML = renderSingleEventSection(chapter, events[0])
      } else {
        chaptersNode.innerHTML = renderParameterAlarmSection(chapter)
      }
    }
  } else {
    // Non-risk-intel tabs: show full chapter
    chaptersNode.innerHTML = renderRulesChapter(chapter)
  }

  attachSorting(chaptersNode)
  attachDownloads(data)
  attachProfileLinks()
}

function renderAll(data) {
  document.querySelectorAll('.rail-label').forEach((element, index) => {
    element.textContent = T('reportDate')
  })
  document.querySelector('.rail-toggle span').textContent = T('navigation')
  document.documentElement.lang = currentLang === 'zh' ? 'zh-Hant' : 'en'
  const langButton = document.getElementById('lang-toggle')
  if (langButton) langButton.textContent = currentLang === 'en' ? '中文' : 'EN'

  renderMasthead(data)
  renderDateDropdown(availableDates, currentDate)
  renderTabBar(data)
  renderTabSummary(data)
  renderActiveTabContent(data)
  renderSectionNav(data)
  initRailToggle()
}

let isFirstLoad = true

async function init() {
  availableDates = await loadDates()
  // Only default to latest date on FIRST load — not when user switches dates
  if (isFirstLoad) {
    currentDate = availableDates[0] || currentDate
    isFirstLoad = false
  }
  // Ensure currentDate is valid
  if (!availableDates.includes(currentDate)) {
    currentDate = availableDates[0] || currentDate
  }
  currentReport = await loadReport(currentDate)
  renderAll(currentReport)
}

function initLangToggle() {
  const button = document.getElementById('lang-toggle')
  button.addEventListener('click', () => {
    currentLang = currentLang === 'en' ? 'zh' : 'en'
    localStorage.setItem('lang', currentLang)
    if (currentReport) renderAll(currentReport)
  })
}

document.addEventListener('DOMContentLoaded', () => {
  initLangToggle()
  init()
})
