# Daily Parameter Review — 完整設計文檔

> OKX 參數管理團隊 · 每日自動化參數審計系統
> 最後更新：2026-03-26

---

## 目錄

1. [產品概述](#1-產品概述)
2. [問題背景與動機](#2-問題背景與動機)
3. [系統架構設計](#3-系統架構設計)
4. [技術選型與權衡](#4-技術選型與權衡)
5. [前端設計哲學](#5-前端設計哲學)
6. [Review 引擎設計](#6-review-引擎設計)
7. [數據管道](#7-數據管道)
8. [部署與 CI/CD 流程](#8-部署與-cicd-流程)
9. [Lark 通知系統](#9-lark-通知系統)
10. [國際化 (i18n)](#10-國際化-i18n)
11. [遇到的問題與解決方案](#11-遇到的問題與解決方案)
12. [未來規劃](#12-未來規劃)

---

## 1. 產品概述

### 1.1 是什麼？

**Daily Parameter Review** 是一個每日自動運行的風控與參數審計報告系統。它目前有兩個活躍章節：
- **Price Limit Review**：掃描 OKX 上 **1,498+ 個交易幣對**的 X/Y/Z Cap，運行 4 條規則
- **Risk Intelligence**：讀取 Claude Code 本地生成的同日風控快照，整理 4 類 alert、可疑用戶 highlight、以及最多 5 位用戶的深度畫像

系統會把這些輸出統一整理成結構化報告，部署為靜態網站，並透過 Lark 推送精簡摘要通知。

### 1.2 為什麼需要它？

OKX 的 Price Limit 參數（Y Cap = 內帶限制, Z Cap = 外硬限制）與日常 Trading Risk alert 都需要定期審查，以確保：
- 緩衝區不會太窄（價格持續觸及限價）
- 基差不會超過 Z Cap（造成不必要的限價觸發）
- 各資產類型的參數符合預期範圍（如 Topcoins 的 Y 應為 0.5-1%，不應設為 2%）
- Z Cap 始終大於 Y Cap（基本結構性要求）
- 高風險標的會被快速匯總，不再分散在 Lark 原始文檔中
- 可疑用戶可以在同一份日報中被標出，並提供精簡的單用戶深描入口

手動審查 1,498 個幣對的參數，再另外翻 Lark 風控文檔和逐個做用戶分析，是不可持續的。這個系統把參數審查與風險情報匯總放進同一份日報，讓團隊只需要關注真正需要處理的標的與用戶。

### 1.3 誰在用？

- **參數管理團隊**：每日查看報告，根據建議調整參數
- **團隊主管**：快速掃描 Lark 摘要卡片，了解整體狀態
- **相關利益關係人**：通過 Vercel 網站隨時查看歷史報告

### 1.4 關鍵指標

| 指標 | 數值 |
|------|------|
| 掃描幣對數 | 1,498+ |
| Price Limit 規則數 | 4 條 |
| Risk Alert 類型 | 4 類 |
| 單日深描用戶上限 | 5 位 |
| 每日運行次數 | 2 次（9AM + 4:30PM HKT） |
| 端到端耗時 | ~20-25 分鐘 |
| 報告部署時間 | ~90 秒（Vercel 自動部署） |

---

## 2. 問題背景與動機

### 2.1 原有系統的局限

在此項目之前，團隊有一個基於 Vite + Express 的即時看板（`params_dashboard`）。它可以：
- 即時顯示參數數據（通過 WebSocket 連接 OKX）
- 手動選擇幣對進行 Review
- 生成調整建議

**但它有幾個核心問題：**

1. **無法部署到 Vercel**：看板依賴 WebSocket 進行即時數據傳輸。Vercel 是 Serverless 架構，不支持長期運行的 WebSocket 連接。Express server 無法在 Vercel 上運行。

2. **不是報告，而是工具**：原有看板是一個互動式工具，需要操作員手動選擇幣對、點擊 Review。它沒有「每日報告」的概念——沒有固定模板、沒有歷史記錄、沒有自動化。

3. **沒有自動化**：每次 Review 都需要人工觸發，Full Review（所有幣對）需要 ~20 分鐘，但沒有 Cron Job 來自動執行。

4. **沒有通知機制**：Review 結果只存在於本地，沒有推送到 Lark 群組。團隊主管無法在不打開看板的情況下了解每日狀態。

### 2.2 核心設計目標

我們需要的不是一個即時看板，而是一個 **每日自動化審計報告**：

1. **自動運行**：Cron Job 每日定時執行，不需要人工介入
2. **靜態部署**：報告生成後部署為靜態網站，任何人隨時可以查看
3. **Lark 通知**：自動推送摘要到 Lark 群組，主管一眼就能看到狀態
4. **歷史記錄**：保留每日報告，可以通過日期選擇器查看歷史
5. **本地 Claude Code 邊界**：所有需要 MCP 的能力必須在本地先生成標準化快照，再交給報告系統消費
6. **不可跨日回填**：若當日 risk-intel 快照不存在，章節應顯示 pending，而不是冒用舊資料
7. **可擴展**：框架支持新增更多參數類型（如 MMR Futures、Index）

---

## 3. 系統架構設計

### 3.1 高層架構

```
┌──────────────────────────────────────────────────────────────────────┐
│                   Claude Code Local Cron / Manual Run               │
│                                                                      │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐  │
│  │ Lark MCP +   │──▶│ risk-intel   │──▶│ public/data/reports/     │  │
│  │ Data Query   │   │ generator    │   │ YYYY-MM-DD/risk-intel    │  │
│  │ (local only) │   │ (same-day)   │   │ .json                    │  │
│  └──────────────┘   └──────────────┘   └─────────────┬────────────┘  │
│                                                       │               │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐       │               │
│  │ EMA      │──▶│ OKX API  │──▶│ runner.main  │───────┘               │
│  │ Collector│   │ Fetch    │   │ chapter merge│                       │
│  └──────────┘   └──────────┘   └──────┬───────┘                       │
│                                       │                                │
│  ┌────────────────────────────────────▼──────────────────────────────┐ │
│  │ git push ──▶ Vercel auto-deploy ──▶ wait 90s ──▶ notify_lark.py  │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────┐        ┌──────────────┐
│ Vercel (HKG) │        │ Lark Groups  │
│ Static Site  │        │ (2 webhooks) │
│              │        │              │
│ index.html   │        │ Interactive  │
│ /data/       │        │ Card with    │
│ reports/     │        │ chapter summary│
└──────────────┘        └──────────────┘
```

**主流程已改為 local-first。** `.github/workflows/` 仍保留作為歷史參考與 legacy automation，但不再是 Risk Intelligence 的真實執行環境。

### 3.2 項目結構

```
/Daily Parameter Dashboard/Claude Code/
├── .github/workflows/
│   ├── daily-review.yml        # Legacy cron workflow（保留參考）
│   └── lark-notify.yml         # Legacy notification workflow（保留參考）
├── runner/                     # Python 數據管道
│   ├── main.py                 # 主控器：運行所有 adapters，保存報告
│   ├── generate_risk_intel.py  # 本地生成同日 risk-intel.json
│   ├── notify_lark.py          # 從已保存的報告發送 Lark 通知
│   ├── lark.py                 # Lark webhook client + card builder
│   ├── risk_intel_utils.py     # Risk Intelligence 解析/聚合 helpers
│   ├── ema_collector.py        # EMA 數據收集器
│   ├── fixtures/               # 本地 fixture（無 MCP 時用於測試）
│   ├── local/                  # 本地 MCP 快照輸入（git ignore）
│   └── adapters/
│       ├── base.py             # Adapter 抽象基類
│       ├── price_limit.py      # Price Limit Review（4 rules）
│       ├── risk_intel.py       # 讀取 same-day risk-intel.json
│       ├── mmr_futures.py      # Stub（pending integration）
│       └── index_review.py     # Stub（pending integration）
├── params_cli/                 # 從原有項目複製的 CLI 工具
│   └── price_limits/
│       ├── cli.py, fetcher.py, realtime_server.py
│       ├── review_methodology.md, assets_types.md
│       └── ...
├── public/                     # 前端靜態網站
│   ├── index.html              # 報告頁面
│   ├── styles.css              # 設計系統
│   ├── app.js                  # 共用 chapter shell + variant renderer
│   ├── how-it-works.html       # 系統架構說明頁
│   └── data/reports/           # 每日報告 JSON（git tracked）
├── run-and-deploy.sh           # 一鍵本地運行 + 部署腳本
├── tasks/                      # 任務拆解與 lessons
├── package.json                # Vite 構建配置
├── vite.config.js              # Vite 配置
├── vercel.json                 # Vercel 部署配置
└── requirements.txt            # Python 依賴
```

### 3.3 數據流

```
Lark folder + Data Query MCP ──▶ Claude Code local snapshot
                                          │
                                          ▼
                               generate_risk_intel.py
                                          │
                                          ▼
                         public/data/reports/YYYY-MM-DD/risk-intel.json
                                          │
OKX WebSocket API ──▶ EMA Collector ──────┼──────────────┐
                                          │              │
OKX REST API ──▶ instruments + XYZ params ┤              │
                                          │              │
assets_types.md ──▶ asset classification ─┘              │
                                                         ▼
                                                 runner/main.py
                                           ┌─────────┬─────────┐
                                           ▼         ▼         ▼
                                     Price Limit   Risk Intel  Pending stubs
                                           │         │
                                           └────┬────┘
                                                ▼
                              public/data/reports/YYYY-MM-DD/report.json
                                                │
                                      ┌─────────┴─────────┐
                                      ▼                   ▼
                                 Vercel Site         Lark Card
                             (reads /data/)     (reads report.json)
```

---

## 4. 技術選型與權衡

### 4.1 為什麼不用 Vercel Blob？

**最初設計**使用 Vercel Blob Storage 存放報告：
- Runner 生成 JSON → 上傳到 Vercel Blob API
- 前端從 Blob URL 讀取數據

**遇到的問題：**
- Blob API 上傳需要 `BLOB_READ_WRITE_TOKEN`，增加了配置複雜度
- Blob 上傳失敗時很難補救，而且與本地 Claude Code 流程割裂
- 需要額外管理 Blob 存儲和權限

**最終方案：Git Commit 方式**
- Runner 將報告保存到 `public/data/` 目錄
- 本地流程 `git commit + push`
- Vercel 自動檢測到 push 並重新部署

**優勢：**
- 零額外依賴（不需要 Blob token）
- 報告歷史自動保存在 Git 中
- 可靠性更高——Git 操作比 API 調用更穩定
- 本地生成與網站發布使用同一份數據源

### 4.2 為什麼選擇靜態站點而非 SSR？

| 方案 | 優點 | 缺點 |
|------|------|------|
| Express + SSR | 可以動態渲染 | 需要長期運行的服務器，Vercel 不支持 |
| Next.js SSG | 構建時生成 | 過度複雜，這只是一個報告頁面 |
| **Vanilla HTML + Vite** | 最簡單，零框架依賴 | 需要手動管理渲染邏輯 |

我們選擇了 **Vanilla HTML + CSS + JS + Vite**：
- 沒有框架 overhead
- 前端代碼 < 700 行
- 構建時間 < 1 秒
- 任何人都可以閱讀和修改

### 4.3 為什麼 Python Runner 保持輕依賴？

原有的 `daily_review.py` 使用 Python stdlib 的 `urllib`。我們保持一致，避免引入不必要的依賴：
- `urllib.request` 足夠處理 OKX REST API 調用
- `risk-intel` adapter 不直接依賴 MCP，只讀本地已生成的 JSON
- 真正需要 Claude Code MCP 的步驟，被隔離在 `generate_risk_intel.py` 的輸入邊界之外
- SSL 問題通過自定義 `ssl.SSLContext` 解決（見第 11 節）

### 4.4 時區選擇：HKT

所有時間顯示和報告日期都使用 **HKT（UTC+8）**：
- 團隊在香港辦公
- OKX 的參數管理流程以 HKT 為基準
- 報告日期文件夾使用 HKT 日期（`2026-03-26/`），確保同一個 HKT 日期的兩次 Cron Run 覆蓋同一個文件夾
- 前端顯示時間也轉換為 HKT

```python
# runner/main.py
from zoneinfo import ZoneInfo
hkt_now = datetime.now(ZoneInfo("Asia/Hong_Kong"))
date_str = hkt_now.strftime("%Y-%m-%d")
```

```javascript
// app.js — 前端 HKT 轉換
function fmtTime(iso) {
  const d = new Date(iso);
  const hkt = new Date(d.getTime() + 8 * 60 * 60 * 1000);
  // ...
}
```

---

## 5. 前端設計哲學

### 5.1 設計方向：Swiss Financial Report

我們的設計不是一個 SaaS Dashboard，而是一份 **專業金融審計報告**。設計靈感來源：
- Bloomberg Terminal 的報告格式
- McKinsey / BCG 的審計文件風格
- 瑞士平面設計（Swiss Style）的精確排版

**核心原則：**
1. **黑白為主**：只在狀態指示器上使用顏色（綠色=通過，橙色=警告，紅色=嚴重）
2. **數據密度**：信息密集但不擁擠，每一寸空間都有意義
3. **專業感**：像一份印刷的金融報告，不像一個科技產品
4. **最小化裝飾**：沒有漸變、沒有陰影、沒有動畫裝飾

### 5.2 從暗色到亮色的轉變

**第一版（已廢棄）**使用暗色主題：
- 靈感來自交易所操作控制台
- 顏色系統：`#0f1115` 背景, `#1a1d24` 面板, `#5b7ff6` 強調色
- 字體：Space Grotesk + IBM Plex Sans + IBM Plex Mono

**用戶反饋**：暗色主題看起來太像一個「即時看板」，不像一份「報告」。需要更簡潔、更專業的外觀。

**第二版（當前）**切換到亮色主題：
- 白色背景，黑色文字，灰色邊框
- 只在狀態指示器上使用顏色
- 字體改為：DM Sans（正文）+ JetBrains Mono（數據/表格）

### 5.3 排版系統（Typography）

```css
:root {
  --font-sans: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', monospace;
}
```

**為什麼選擇 DM Sans？**
- 現代幾何無襯線體，但不像 Inter/Roboto 那樣「泛濫」
- 設計師群體中有良好聲譽
- 支持多種字重（400-700），適合建立排版層次

**為什麼選擇 JetBrains Mono？**
- 專為數據密集型界面設計的等寬字體
- 數字排列整齊（tabular-nums）
- 區分度高：`0` vs `O`, `1` vs `l` vs `I`
- 在表格和指標中看起來非常專業

**排版層次：**

| 元素 | 字體 | 大小 | 字重 |
|------|------|------|------|
| Masthead 品牌 | JetBrains Mono | 13px | 500, uppercase, letter-spacing: 2.5px |
| 章節標題 | DM Sans | 20px | 700 |
| 規則標題 | DM Sans | 14px | 600 |
| 正文 | DM Sans | 16px (base) | 400 |
| 表格標頭 | JetBrains Mono | 10px | 600, uppercase |
| 表格數據 | JetBrains Mono | 12px | 400 |
| 指標數值 | JetBrains Mono | 28px / 18px | 500 |
| 狀態標籤 | DM Sans | 11px | 600, uppercase |

### 5.4 顏色系統

```css
:root {
  /* 表面 */
  --white: #ffffff;
  --gray-50: #f9fafb;
  --gray-100: #f3f4f6;
  --gray-200: #e5e7eb;
  --gray-500: #6b7280;
  --gray-900: #111827;
  --black: #0a0a0a;

  /* 唯一使用的彩色 — 狀態指示 */
  --pass: #16a34a;        /* 綠色 — Pass, OK */
  --warning: #d97706;     /* 琥珀色 — Warning, Watch */
  --critical: #dc2626;    /* 紅色 — Critical, Missing */
  --pending: #9ca3af;     /* 灰色 — Pending */
}
```

**設計原則：單色 + 語義色**
- 90% 的界面是黑白灰
- 顏色只用於狀態指示，而且永遠搭配文字標籤（不僅靠顏色傳達信息，遵循 WCAG 可訪問性準則）
- 沒有品牌色、沒有裝飾色、沒有漸變

### 5.5 佈局架構

```
┌──────────────────────────────────────────────┐
│  MASTHEAD（固定頂部，2px 黑色下邊框）          │
│  品牌標識 | 日期 | 語言切換                    │
├──────────────────────────────────────────────┤
│  SUMMARY OVERVIEW（中性 KPI + 甜甜圈圖 + 柱狀圖）│
├──────────┬───────────────────────────────────┤
│  LEFT    │  MAIN CONTENT                     │
│  RAIL    │                                   │
│  (220px) │  Chapter: Price Limit             │
│          │    ├─ Metrics                     │
│  Date    │    ├─ Rule blocks                 │
│  Picker  │    ├─ Recommended Changes         │
│          │                                   │
│  Chapter │  Chapter: Risk Intelligence       │
│  Nav     │    ├─ Source document             │
│          │    ├─ Alert overview metrics      │
│          │    ├─ 4 alert blocks              │
│          │    ├─ Suspicious users table      │
│          │    └─ User deep dive (<details>)  │
│          │                                   │
│          │  Chapter: MMR Futures (pending)   │
│          │  Chapter: Index (pending)         │
└──────────┴───────────────────────────────────┘
```

### 5.6 Summary Overview 可視化

頂部的 Summary Overview 包含三個區域：

1. **KPI 卡片**（左側 2x2 網格）：
   - Overall Status（含狀態標籤）
   - Total Findings
   - Active Chapters
   - Report Freshness

2. **甜甜圈圖**（中央，純 CSS/SVG）：
   - 活躍章節中所有 rule block 的狀態分布：Pass / Warning / Critical
   - 中心顯示規則總數
   - 下方圖例

3. **水平柱狀圖**（右側）：
   - 每條規則或 alert block 的 flagged 數量
   - 柱體顏色對應狀態

**所有圖表都是純 CSS + SVG，沒有使用任何圖表庫。** 這保持了零依賴的原則。

### 5.7 組件設計

#### Status Pill（狀態標籤）
```
┌─────────────┐
│ ✓ PASS      │  (綠色背景 12% 透明度 + 綠色文字)
└─────────────┘
┌─────────────┐
│ ⚠ WARNING   │  (琥珀色背景 12% 透明度 + 琥珀色文字)
└─────────────┘
```
- 永遠包含 SVG 圖標 + 文字標籤（不僅靠顏色）
- `border-radius: 3px`（不是 pill shape，更克制）
- 11px, uppercase, 600 weight

#### Rule Block（規則卡片）
- 使用 `<details>` 元素實現摺疊/展開
- 有問題的規則默認展開，通過的規則默認摺疊
- 頭部：規則名稱 + 狀態標籤 + 展開箭頭
- 內容：描述文字 + 數據表格 或 「All instruments pass.」

#### Data Table（數據表格）
- JetBrains Mono 等寬字體
- `font-variant-numeric: tabular-nums` 確保數字對齊
- 表頭：灰色背景，10px uppercase
- 可排序（點擊表頭切換升序/降序）
- 移動端水平滾動

### 5.8 響應式設計

| 斷點 | 佈局變化 |
|------|---------|
| > 1024px | 完整佈局：左側導航 + 主內容 |
| 768-1024px | 左側導航窄化（190px），表格可能需要滾動 |
| < 768px | 左側導航收起為頂部按鈕，Summary 網格變為單列，指標卡片堆疊 |

### 5.9 可訪問性

- 基礎字號 16px（WCAG 建議）
- 所有文字對比度 ≥ 4.5:1
- 狀態指示永遠搭配圖標 + 文字（不僅靠顏色）
- `:focus-visible` 焦點環（2px solid）
- Skip-to-content 鏈接
- 表格使用語義化 `<th>`/`<td>` 和 `aria-sort`
- `prefers-reduced-motion` 支持
- 打印樣式（隱藏導航，白色背景）

### 5.10 反面教材（我們刻意避免的）

根據 ui-ux-pro-max 的 AI Slop Detection 指南：

| 避免 | 原因 |
|------|------|
| 紫色/靛色漸變背景 | 最常見的 AI 生成美學 |
| 三列 feature grid（圖標 + 標題 + 描述） | AI 佈局的標誌性特徵 |
| 彩色圓圈中的圖標 | SaaS 模板風格 |
| 所有東西都居中 | 缺乏設計意圖 |
| 統一的大圓角 | 看起來像玩具 |
| 裝飾性 blob/波浪 | 用裝飾掩蓋內容空洞 |
| Emoji 作為圖標 | 不專業，跨平台不一致 |
| `border-left: 3px solid accent` 卡片 | AI 生成卡片的標誌 |

---

## 6. Review 引擎設計

### 6.1 Adapter 模式

每個參數類型（Price Limit, MMR Futures, Index）實現相同的 Adapter 接口：

```python
class BaseAdapter:
    slug: str       # "price-limit"
    title: str      # "Price Limit Review"

    def execute(self, ema_data: dict) -> dict:
        """返回標準化的章節輸出"""
        return {
            "slug": str,
            "title": str,
            "status": "pass" | "warning" | "critical" | "pending",
            "summary": str,
            "metrics": { ... },
            "render_variant": "rules" | "risk-intel",
            "metric_cards": [ ... ],
            "rule_blocks": [ ... ],
            "recommended_changes": { ... },
            "downloads": [ ... ],
            "source_document": { ... } | None,
            "suspicious_users": [ ... ],
            "user_profiles": [ ... ],
            "markdown": str,
            "error": str | None
        }
```

**為什麼用 Adapter 模式？**
- 新的參數類型只需實現 `execute()` 方法
- 主控器（`main.py`）不需要了解每種參數的細節
- 前端根據 `render_variant` 分流渲染器，而不是把所有章節都當成 Price Limit
- MMR Futures 和 Index 目前是 stub（返回 `status: "pending"`），同事的代碼就緒後直接替換

### 6.2 四條 Review 規則

#### Rule 1: Buffer Too Tight（緩衝區過窄）
- **需要 EMA 數據**
- 計算每個幣對的 `limitUp_buffer` 和 `limitDn_buffer` 的 EMA
- 如果 buffer EMA < 0，說明價格持續觸及限價
- 如果 buffer < Y Cap 的某個比例，標記為 warning

#### Rule 2: Asymmetric Basis（基差不對稱）
- **需要 EMA 數據**
- 計算 basis EMA（mark price - index price）
- 如果 basis 相對 Z Cap 偏大，說明 Z Cap 可能需要加寬

#### Rule 3: Asset-Type Consistency（資產類型一致性）
- **不需要 EMA 數據**（純靜態檢查）
- 載入 `assets_types.md` 的資產分類映射
- 檢查每個幣對的 Y/Z Cap 是否符合其資產類型的預期範圍
- 預期範圍：

| 資產類型 | Y Cap | Z Cap |
|---------|-------|-------|
| Topcoins | 0.5-1% | 1-2% |
| Altcoins | ≤4% | ≤10% |
| Fiat | ~1% | ~2% |
| TradFi | ~2% | ~5% |

#### Rule 4: Z Cap > Y Cap（結構性檢查）
- **不需要 EMA 數據**（純靜態檢查）
- Z Cap（外硬限制）必須大於 Y Cap（內帶限制）
- 如果 Z ≤ Y，這是一個配置錯誤，需要立即修復

### 6.3 EMA 數據收集

EMA（指數移動平均）數據通過 WebSocket 從 OKX 即時市場數據計算得出：

```
realtime_server.py:
  - 連接 OKX WebSocket API (ws://www.okx.com/ws/v5/public)
  - 訂閱所有幣對的 ticker 數據
  - 每 5 秒更新一次
  - 計算 24h EMA: basis, spread, limitUp_buffer, limitDn_buffer
  - 每 5 分鐘自動保存到 ema_state.json
```

EMA Collector（`ema_collector.py`）：
1. 啟動 `realtime_server.py` 作為子進程
2. 每 30 秒輪詢 `/health` 端點
3. 當覆蓋率 > 80% 或超時（15 分鐘）時停止
4. 讀取保存的 `ema_state.json`

### 6.4 調整文件生成

對於被標記的幣對，系統自動生成 OKX 格式的調整 CSV 文件：
- Spot 模板：`Task Object, timeType, openMax/Min, limitMax/Min, indexMax/Min`
- Perp 模板：不同的列名格式
- CSV 可直接在報告頁面下載

### 6.5 Risk Intelligence 章節設計

`Risk Intelligence` 是一個新的 chapter variant，目的不是重做風控系統，而是把本地 Claude Code 已生成的風險情報，壓縮進同一份日報。

**固定三層結構：**
1. **標的問題分析**：4 個固定 alert blocks
   - Index Alarm
   - Price Limit P4
   - Collateral Coin Risk
   - Platform OI
2. **可疑用戶 Highlight**：從 alert 內容抽取 UID / `master_user_id`，合併重複提及，按風險與提及次數排序
3. **單用戶深度畫像**：只對最高優先的 5 位唯一用戶輸出深描卡片，每位卡片固定展示 8 個 dimension

**狀態規則：**
- 任一 alert block 為 `critical`，或任一用戶為 `T4` → chapter `critical`
- 有 `warning` alert block，或任一用戶為 `T2/T3` → chapter `warning`
- 4 類 alert 都無發現，且沒有可疑用戶 → chapter `pass`
- 當日沒有 `risk-intel.json` → chapter `pending`

**公開數據邊界：**
- 會公開：精簡摘要、alert tables、可疑用戶、8 維度畫像摘要
- 不會公開：原始 Lark 全文、完整 SQL 結果、長版 HTML user report

---

## 7. 數據管道

### 7.1 runner/main.py — 主控流程

```python
def local_daily_flow():
    # 0. Claude Code 本地先生成 risk-intel.json（獨立命令）
    #    python3 -m runner.generate_risk_intel

    # 1. 確定報告日期（HKT）
    hkt_now = datetime.now(ZoneInfo("Asia/Hong_Kong"))
    date_str = hkt_now.strftime("%Y-%m-%d")

    # 2. 載入 EMA 緩存（可選）
    ema_data = _load_ema_data()

    # 3. 運行所有 adapters
    for adapter in [
        PriceLimitAdapter(),
        RiskIntelAdapter(),
        MMRFuturesAdapter(),
        IndexReviewAdapter(),
    ]:
        chapter = adapter.execute(ema_data)
        chapters.append(chapter)

    # 4. 構建報告摘要
    report = _build_report(chapters, date_str)

    # 5. 保存到 public/data/reports/{date}/
    _save_report(chapters, report, date_str)
```

`runner.main` 不直接做 MCP 調用。它只消費當日已存在的 `risk-intel.json`，如果沒有就讓章節維持 pending。

### 7.2 報告數據結構

```
public/data/
├── reports/
│   ├── latest.json          # 指向最新報告日期
│   ├── index.json           # 所有報告日期列表
│   └── 2026-03-26/
│       ├── report.json      # 完整報告（report + chapters）
│       ├── risk-intel.json  # 本地生成的風險情報快照
│       ├── price-limit.md   # 章節 Markdown
│       ├── risk-intel.md    # 章節 Markdown
│       └── assets/
│           └── perp_adjustment.csv
```

**report.json 結構：**
```json
{
  "report": {
    "date": "2026-03-26",
    "generated_at": "2026-03-26T07:28:00Z",
    "status": "warning",
    "total_issues": 43,
    "chapters": [{ "slug": "...", "title": "...", "metrics": {...} }]
  },
  "chapters": [
    {
      "slug": "price-limit",
      "render_variant": "rules",
      "metric_cards": [{ "label": "Instruments", "value": "1498" }],
      "rule_blocks": [{ "ruleId": "...", "title": "...", "status": "...", "table": {...} }],
      "recommended_changes": { "headers": [...], "rows": [...] },
      "downloads": [{ "label": "...", "filename": "...", "content": "..." }],
      "source_document": null,
      "suspicious_users": [],
      "user_profiles": []
    },
    {
      "slug": "risk-intel",
      "render_variant": "risk-intel",
      "metric_cards": [{ "label": "Alert Types", "value": "4" }],
      "source_document": {
        "title": "每日风控总结 - 2026-03-26 (00:00 - 23:59)",
        "url": "https://okg-block.sg.larksuite.com/drive/folder/Wu2Pfktq6lq4t8dWL52lB97pgQb",
        "modified_at": "2026-03-26T12:30:00Z",
        "selected_by": "latest_modified_desc"
      },
      "rule_blocks": [{ "ruleId": "index_alarm", "title": "Index Alarm", "status": "warning", "table": {...} }],
      "suspicious_users": [{ "uid": "...", "master_user_id": "...", "risk_tier": "T4", "source_alert": "platform_oi", "reason": "..." }],
      "user_profiles": [{ "uid": "...", "overall_risk_tier": "T4", "executive_summary": "...", "dimensions": [...] }]
    }
  ]
}
```

**risk-intel.json 結構：**
```json
{
  "date": "2026-03-26",
  "generated_at": "2026-03-26T09:15:00Z",
  "chapter": { "...same chapter payload..." }
}
```

### 7.3 前端數據加載

```javascript
// 嘗試載入真實數據，失敗則回退到 mock
async function loadReport(date) {
  try {
    const res = await fetch(`/data/reports/${date}/report.json`);
    if (res.ok) return await res.json();
  } catch (e) {}
  return buildMockReport(date);
}

// 前端根據 render_variant 分流
if (chapter.render_variant === 'risk-intel') {
  return renderRiskIntelChapter(chapter);
}
return renderRulesChapter(chapter);
```

---

## 8. 部署與 CI/CD 流程

### 8.1 本地主流程

正式運行順序如下：

```
python3 -m runner.generate_risk_intel
→ python3 -m runner.main --no-lark
→ git add public/data/ && git commit && git push
→ wait 90s
→ python3 -m runner.notify_lark
```

這條流程的重點是：
- `generate_risk_intel` 必須先跑，因為只有 Claude Code 本地環境能提供 MCP 前置能力
- `runner.main` 只負責合併章節與保存報告，不負責直接讀 Lark / SQL
- Lark 通知一定在 `git push` 與 Vercel 部署之後發送

### 8.2 Legacy GitHub Actions

`.github/workflows/` 仍保留，原因有兩個：
- 保留最初的自動化歷史與 fallback 參考
- Price Limit / 靜態報告流程仍可在無 MCP 的情況下被重放

但它們**不是 Risk Intelligence 的 source of truth**。如果某次運行發生在沒有同日 `risk-intel.json` 的環境，`risk-intel` chapter 應顯示 `pending`。

### 8.3 Vite 構建

```json
// package.json
"build": "vite build && cp -r public/data dist/data 2>/dev/null || true && cp public/how-it-works.html dist/ 2>/dev/null || true"
```

**重要**：Vite 的 `root: 'public'` 配置意味著 `public/data/` 不會自動被複製到 `dist/`。我們通過 post-build `cp` 命令解決（見第 11 節 ISSUE-006）。

### 8.4 Vercel 配置

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "vite",
  "regions": ["hkg1"]     // 香港區域，最低延遲
}
```

### 8.5 本地運行

```bash
./run-and-deploy.sh
# 或手動：
python3 -m runner.generate_risk_intel   # 生成同日 risk-intel snapshot
python3 -m runner.main --no-lark        # 生成完整報告
git add public/data/ && git commit && git push   # 部署
python3 -m runner.notify_lark      # 發送 Lark（可選）
```

---

## 9. Lark 通知系統

### 9.1 架構

- 使用 Lark 的 **Webhook Bot** + **Interactive Card** 格式
- 支持多個 Webhook（目前配置了 2 個 Lark 群組）
- 通過環境變量 `LARK_WEBHOOKS` 可覆蓋默認列表

### 9.2 卡片設計

Lark Interactive Card 使用原生的 `table` 組件（不是 markdown 表格，因為 Lark webhook 不渲染 markdown 表格語法）：

**卡片結構：**
1. **Header**：橙色/綠色/紅色（根據狀態），標題「Daily Parameter Review — 2026-03-26」
2. **Overview（column_set）**：Status | Instruments | Issues | Sections
3. **章節標題**：「Price Limit Review | 1,498 instruments | EMA: 1,472 | 43 issues」
4. **Risk Intelligence 章節標題**：「Risk Intelligence | 4 alert types | 3 suspicious users | Highest T4」
5. **規則表格（native table）**：Rule | Status (colored tag) | Flagged
6. **Pending 章節**：⏳ MMR Futures — Pending integration
7. **按鈕（action）**：[View Full Report] [How It Works]
8. **Footer（note）**：Generated date | OKX Parameter Management

### 9.3 Lark Table 組件

**重要教訓**：Lark webhook 的 `lark_md` 格式 **不支持** markdown 表格語法（`| --- | --- |`）。如果你用 markdown 表格，它會顯示為原始文本。

**正確方式**是使用 Lark 的原生 `table` 組件：
```python
{
    "tag": "table",
    "columns": [
        {"name": "rule", "display_name": "Rule", "data_type": "text"},
        {"name": "status", "display_name": "Status", "data_type": "options"},
        {"name": "flagged", "display_name": "Flagged", "data_type": "number"},
    ],
    "rows": [
        {"rule": "Buffer Too Tight", "status": [{"text": "WARNING", "color": "orange"}], "flagged": 33}
    ]
}
```

`data_type: "options"` 會渲染為帶顏色的標籤，非常適合狀態顯示。

### 9.4 時序保證

**問題**：Lark 通知中的「View Full Report」鏈接指向 Vercel 網站。如果在 git push 之前發送 Lark，用戶點擊時看到的是舊報告。

**解決方案**：
```
generate_risk_intel.py → 生成同日 risk-intel.json
                         ↓
runner.main → 生成報告 → 保存到 public/data/
                ↓
git push → Vercel 開始部署
                ↓
sleep 90  → 等待 Vercel 部署完成
                ↓
notify_lark.py → 讀取已保存的報告 → 發送 Lark 卡片
```

Lark 通知在 Vercel 部署完成後才發送，確保用戶點擊連結時看到的是最新報告。

---

## 10. 國際化 (i18n)

### 10.1 實現方式

由於網站是靜態報告（非 React/Vue），i18n 通過純 JavaScript 翻譯字典實現：

```javascript
const I18N = {
  en: {
    brand: 'PARAMETER REVIEW',
    overallVerdict: 'Overall Verdict',
    instruments: 'Instruments',
    // ... 30+ 翻譯條目
  },
  zh: {
    brand: '參數審查報告',
    overallVerdict: '整體結論',
    instruments: '幣對數量',
    // ...
  },
};

function T(key) { return I18N[currentLang]?.[key] || I18N.en[key]; }
```

### 10.2 切換機制

- Masthead 右上角有語言切換按鈕（「中文」/ 「EN」）
- 點擊後 `currentLang` 切換，整個頁面重新渲染
- 偏好保存在 `localStorage`，刷新頁面後保持

### 10.3 翻譯範圍

**翻譯的**：所有 UI 標籤（標題、按鈕、狀態文字、指標名稱）
**不翻譯的**：報告數據（幣對名稱如 SOL-AUD、百分比、API 欄位名稱）——這些是技術標識符

---

## 11. 遇到的問題與解決方案

### ISSUE-001: Vercel 不支持 WebSocket

**問題**：原有看板使用 Express + WebSocket 進行即時數據傳輸。Vercel 是 Serverless 架構，不支持 WebSocket。

**解決方案**：重新設計為靜態報告模式。數據由本地 Claude Code Cron Job 預先生成，保存為 JSON 文件，部署為靜態網站。Vercel 只負責託管靜態文件。

**影響**：系統從「即時看板」變為「定期報告」。這實際上更符合用戶需求——參數審查本質上是定期任務，不需要即時性。

---

### ISSUE-002: Runner Exit Code 1 不等於業務失敗

**問題**：`runner/main.py` 原本在發現任何 issue 時返回 `exit code 1`（`return 0 if report["status"] == "pass" else 1`）。由於 Review 幾乎總是會發現 issue（這是它的工作），自動化流程幾乎每次都會被標記為 failure。

**解決方案**：Runner 永遠返回 `exit code 0`，除非遇到真正的程序錯誤。發現 issue 是正常行為，不是錯誤。

```python
# Before (wrong):
return 0 if report["status"] == "pass" else 1

# After (correct):
return 0
```

---

### ISSUE-003: macOS Python SSL 證書問題

**問題**：macOS 上的 Python 默認不包含 SSL 根證書，導致 `urllib.request.urlopen()` 對 HTTPS URL 拋出 `ssl.SSLCertVerificationError`。

**解決方案**：創建自定義 SSL context，嘗試載入 `certifi` 證書，如果不可用則禁用驗證：

```python
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX.load_verify_locations(certifi.where())
except Exception:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE
```

**注意**：在某些 Linux 環境中不需要此 workaround，但保留它不會造成問題。

---

### ISSUE-004: Git Push 衝突

**問題**：EMA 收集需要 ~15 分鐘。在此期間，如果用戶從本地 push 了代碼，Cron Job 的 `git push` 會因為 remote 有新的 commit 而失敗。

**解決方案**：在 `git push` 之前執行 `git pull --rebase`，並將 push 失敗設為非致命錯誤：

```yaml
- name: Commit and push report data
  run: |
    git add public/data/
    git diff --cached --quiet && echo "No changes" && exit 0
    git commit -m "Daily review $(date -u +%Y-%m-%d)"
    git pull --rebase origin main || true
    git push || echo "Push failed — report was still generated."
```

---

### ISSUE-005: Vercel Blob API 失敗

**問題**：最初方案使用 Vercel Blob API 上傳報告。API 偶爾返回錯誤，導致報告丟失。Blob token 管理也增加了配置複雜度。

**解決方案**：完全放棄 Vercel Blob，改用 git commit 方式。報告保存到 `public/data/`，通過 git push 觸發 Vercel 重新部署。

**教訓**：最簡單的方案往往最可靠。Git 是已經被驗證了幾十年的工具，比 API 調用更穩定。

---

### ISSUE-006: Vite 構建不包含 data/ 目錄

**問題**：Vite 配置 `root: 'public'` 意味著 `public/` 是源碼目錄，而不是靜態資源目錄。因此 `public/data/` 不會被自動複製到 `dist/`。Vercel 部署後，`/data/reports/latest.json` 返回 404。

**解決方案**：在 `package.json` 的 build script 中添加 post-build copy：

```json
"build": "vite build && cp -r public/data dist/data 2>/dev/null || true && cp public/how-it-works.html dist/ 2>/dev/null || true"
```

**更新 vercel.json**：從 `npx vite build` 改為 `npm run build`，確保 copy 命令被執行。

---

### ISSUE-007: 前端 Schema 與 Runner 輸出不匹配

**問題**：前端的 mock 數據使用 `sections[].rules[].evidence` 格式，但 Runner 輸出使用 `chapters[].rule_blocks[].table` 格式。字段名完全不同，導致前端無法渲染真實數據。

**解決方案**：統一到 Runner 的 schema。重寫前端的 mock 數據和所有渲染函數以匹配 Runner 輸出格式：

```javascript
// Before (wrong): sections[].rules[].evidence.headers
// After (correct): chapters[].rule_blocks[].table.headers
```

---

### ISSUE-008: Lark Webhook 不渲染 Markdown 表格

**問題**：最初嘗試在 Lark card 的 `lark_md` 中使用 markdown 表格語法（`| Rule | Status | Flagged | \n| --- | --- | --- |`）。Lark 將其顯示為原始文本，而不是渲染表格。

**解決方案**：使用 Lark 的原生 `table` 組件，支持 `data_type: "options"` 來渲染帶顏色的狀態標籤。

---

### ISSUE-009: Lark 通知在 Vercel 部署前發送

**問題**：Runner 在 `main.py` 中保存報告後立即發送 Lark 通知。但此時 git push 尚未執行，Vercel 上還是舊報告。用戶點擊「View Full Report」看到的是過期數據。

**解決方案**：將 Lark 通知移到本地工作流的最後一步，在 git push 之後等待 90 秒（Vercel 部署時間）再發送。

---

### ISSUE-011: Risk Intelligence 不能跨日回填

**問題**：如果某天沒有生成同日 `risk-intel.json`，最偷懶的做法是直接沿用前一天的資料，表面上看起來章節沒有空缺，但這會讓風控用戶與 alert 失去日期對應性。

**解決方案**：`runner/adapters/risk_intel.py` 只讀當日 `public/data/reports/YYYY-MM-DD/risk-intel.json`。沒有同日文件時，直接返回 `pending` chapter，摘要明確寫出「當日本地 risk intel 尚未生成」。

**教訓**：風控日報的完整性比表面上的「每天都有內容」更重要。錯日期的風險情報，等於錯報。

---

### ISSUE-010: Emoji 在 Python JSON 序列化中的 Surrogate Pair 問題

**問題**：某些 emoji（如 🔴 `U+1F534`）在 Python 中表示為 surrogate pair（`\ud83d\udd34`）。當使用 `json.dumps()` 序列化並通過 `urllib` 發送時，`encode('utf-8')` 會失敗。

**解決方案**：避免使用需要 surrogate pair 的 emoji，改用 BMP 範圍內的符號：

```python
# Before (broken): "\ud83d\udd34" (🔴)
# After (works):   "\u274c" (❌)
```

---

## 12. 未來規劃

### 12.1 短期（本週內）

- **MMR Futures adapter**：同事的 review 功能就緒後，替換 stub
- **Index adapter**：同上
- **真實 MCP 接入**：將 Claude Code 產出的 Lark/Data Query 結果穩定落到 `runner/local/risk_intel_input.json`
- **EMA 收集穩定性**：本地 Cron 上的 EMA 收集超時策略再優化

### 12.2 中期

- **歷史趨勢圖**：在 Summary Overview 中添加每日 issue 數量的趨勢圖
- **Risk Intelligence 對比**：支持比較兩天之間 alert 與可疑用戶的變化
- **更多 Lark webhook**：支持不同團隊的群組
- **報告對比**：允許對比兩天的報告，突出變化

### 12.3 長期（如果需要）

- **審批流程**：在 Lark 卡片中加入「Approve」按鈕，操作員批准後系統自動逐步調整參數（每 10 秒一步）
- **BOSS API 集成**：自動將調整推送到 OKX 的 BOSS 後台
- **即時監控**：恢復 WebSocket 監控，但部署到支持長期運行的平台（如 Railway/Fly.io）
- **用戶畫像 artifact 中心**：將本地長版 user reports 管理成可追溯的內部資產，而不是散落在臨時文件中

---

## 附錄

### A. 環境要求

- Python 3.12+
- Node.js 18+（Vite 構建）
- Git
- Vercel CLI（可選，用於手動部署）

### B. 常用命令

```bash
# 本地運行完整流程
./run-and-deploy.sh

# 只生成同日 risk intelligence
python3 -m runner.generate_risk_intel

# 只生成報告（不部署不通知）
python3 -m runner.main --dry-run

# 只發送 Lark 通知（使用最新已保存報告）
python3 -m runner.notify_lark

# 本地開發
npm run dev    # http://localhost:5175

# 構建
npm run build  # 輸出到 dist/
```

### C. 配置

| 配置項 | 位置 | 說明 |
|--------|------|------|
| 本地 Cron 時間 | 本地排程器 / Claude Code automation | 9AM + 4:30PM HKT |
| Risk Intel 輸入 | `runner/local/risk_intel_input.json` | 本地 MCP 標準化快照（git ignore） |
| Legacy workflows | `.github/workflows/*.yml` | 保留參考，不作為 risk-intel 主流程 |
| Lark Webhooks | `runner/lark.py` DEFAULT_WEBHOOKS | 可通過 `LARK_WEBHOOKS` 環境變量覆蓋 |
| Vercel 區域 | `vercel.json` regions | `hkg1`（香港） |
| 報告 URL | `runner/lark.py` VERCEL_URL | `https://dailyparameter-report.vercel.app` |

---

*本文檔由 OKX 參數管理團隊維護。最後更新 2026-03-26。*
