---
name: core-trading-user-risk-analysis
description: "Analyze OKX user accounts for risk signals across 8 dimensions. Produces a self-contained HTML risk report. Trigger this skill whenever the user asks to check a user account, investigate a user, review user risk, or says things like '帮我看下这个用户', '查一下用户', '用户风险分析', 'check this user', 'user risk', '这个用户有没有问题', or provides a user ID / UID and asks to investigate it."
---

# Core Trading — User Risk Analysis Skill

Analyze OKX user accounts for risk signals across 8 dimensions. Produces a
self-contained HTML risk report.

---

## Input

One or more user identifiers. The user may provide any of:
- `uid` (18-digit, e.g. 612133499092760604)
- `master_user_id` (shorter, e.g. 62247621)
- `user_id` (same as master_user_id in most tables)

**ID Resolution:** The `dws_okx_user_master_info_df` table uses `master_user_id`
as primary key and has a `uid` field. Login table uses `user_id` (= master_user_id).
Bill table has both `user_id` and `master_user_id`. Deposit/withdraw table uses
`master_user_id`.

If the input looks like an 18-digit number, assume it's `uid` and resolve to
`master_user_id` first. If it's shorter, assume it's `master_user_id` directly.

---

## Phase 1 — Data Collection

Run all SQL queries via datatools MCP (`submitQuery` → `getQueryResult`).
Project: `ex_offline`. Use `pt` = yesterday's date (YYYYMMDD format) for daily
tables, and appropriate date ranges for hourly tables.

**IMPORTANT:** Submit all independent queries in parallel to minimize wait time.
Use a Haiku agent for data-heavy result extraction if needed.

### Sensitive Fields (BLOCKED — security level >=4)
These fields will return 403. Do NOT include them in queries:
- `dws_okx_user_master_info_df`: register_ip, email, phone_number, nick_name
- `dwd_okx_user_secure_login_df`: ip
- `dwd_okx_depositwithdraw_onchain_order_hf`: ip, address

### Query Templates

**Q1: User Profile** (master info table)
```sql
SELECT master_user_id, uid, register_time, register_client_type,
  register_device_id, register_from_value, register_country_big_region,
  register_province, register_city, phone_area_code,
  is_market_account, is_internal_account,
  kyc_pass_max_level, kyc_pass_nationality_name,
  kyc_pass_resident_country_name,
  first_deposit_time, first_trade_time,
  trade_volume_usdt_sth, fee_volume_usdt_sth,
  all_account_equity_volume_usdt,
  user_fee_level_value, account_level_value,
  first_deposit_type, first_deposit_currency_name,
  first_deposit_volume_usdt,
  first_trade_type, first_trade_currency_name,
  last_deposit_time,
  kyc1_pass_time, kyc2_pass_time,
  final_country_of_residence, user_from,
  is_close_account
FROM ex_offline.dws_okx_user_master_info_df
WHERE pt = '{yesterday}' AND master_user_id = {master_user_id}
```

**Q2: Login History** (secure login table — use user_id = master_user_id)
```sql
SELECT ip_country_code, ip_city_english_name, ip_region_english_name,
  device_id, fingerprint_id, user_agent, create_time
FROM ex_offline.dwd_okx_user_secure_login_df
WHERE pt = '{yesterday}' AND user_id = {master_user_id}
ORDER BY create_time DESC LIMIT 50
```

**Q3: Trading Bills** (bill table)
```sql
SELECT instrument_name, biz_id, order_sell_or_buy,
  volume_usdt, profit_volume_token, fee_volume_usdt,
  order_leverage, create_time, client_source,
  order_system_type, contract_type, opposite_user_id,
  bill_type, margin_mode
FROM ex_offline.dwd_okx_trade_pm_user_bill_hi
WHERE pt >= '{30d_ago}' AND pt <= '{yesterday}'
  AND user_id = {master_user_id}
  AND bill_type IN (1,2,3)
LIMIT 500
```

**Q3 date range strategy:** Start with last 30 days. If 0 rows AND first_trade_time
from Q1 is older than 30 days ago, retry with a range covering first_trade_time.
Keep the range to ~1 month max to avoid slow partition scans. The bill table is
hourly-partitioned (`_hi`) — wide ranges (>2 months) may timeout.

**Q4: Deposit & Withdrawal** (onchain order table)
```sql
SELECT business_type, currency_name, volume_token,
  create_time, completed_time, is_inner_address,
  status, status_description, currency_chain_name,
  target_user_id, sender_user_id, type
FROM ex_offline.dwd_okx_depositwithdraw_onchain_order_hf
WHERE pt = '{yesterday}' AND master_user_id = {master_user_id}
ORDER BY create_time DESC LIMIT 100
```

**Q4 known limitations:**
- This hourly table (`_hf`) is massive. Range scans >1 month WILL fail with
  "instance count exceeds limit" errors.
- Single-day pt queries may return 0 rows even for known deposit dates — the
  partition key format or data retention may not match expectations.
- If Q4 returns 0 rows: note "No on-chain data available" in the report. Do NOT
  retry with wide date ranges. The deposit/withdrawal dimension becomes N/A.
- Internal transfers (between OKX accounts) may not appear in this on-chain table.

**Q5: KYC Data** (kyc pass table)
```sql
SELECT kyc_user_type, nationality_code, nationality_name,
  resident_country_code, kyc1_pass_time, kyc2_pass_time,
  kyc3_pass_time, max_pass_kyc_level, kyc_entity_value,
  source_wealth, plan_trade_volume, account_purpose
FROM ex_offline.dwd_okx_user_kyc_pass_data_df
WHERE pt = '{yesterday}' AND user_id = {master_user_id}
```

**Q6 (Optional): Associated Account Detection**
If login data reveals shared device_id or fingerprint_id, run:
```sql
SELECT user_id, ip_country_code, create_time
FROM ex_offline.dwd_okx_user_secure_login_df
WHERE pt = '{yesterday}'
  AND device_id = '{shared_device_id}'
  AND user_id != {master_user_id}
LIMIT 20
```

---

## Phase 2 — Risk Analysis

Analyze each dimension using the OKX internal risk framework. For each dimension,
identify specific risk signals and assign a severity: NONE / LOW / MEDIUM / HIGH / CRITICAL.

### Dimension 1: Registration Profile
**Risk signals:**
- Account age < 30 days → HIGH
- Account age < 90 days → MEDIUM
- Registration to first deposit < 1 hour → MEDIUM
- Registration to first trade < 24 hours → MEDIUM (combined with short age → HIGH)
- KYC delayed > 6 months after registration → MEDIUM
- KYC passed same day as registration → LOW (normal) unless combined with other signals
- Phone area code mismatches KYC nationality → MEDIUM
- user_from indicates sub-account or special registration → note

### Dimension 2: Trading Behavior
**Risk signals:**
- Single instrument concentration > 80% of volume → MEDIUM
- Instrument is low-liquidity / small-cap → HIGH (if concentrated)
- Extreme leverage (>50x sustained) → MEDIUM
- All orders via API (client_source=1) → LOW (common for bots, but note)
- order_system_type=4 (full liquidation) or 5 (market liquidation) present → note frequency
- Taker-heavy trading (bill_type=2 dominant) → MEDIUM if > 80%
- Opposite_user_id concentration — same counterparty > 5 times → HIGH
- Trading only during specific narrow windows → MEDIUM
- Simultaneous spot + perp on same asset → MEDIUM (manipulation signal)

### Dimension 3: Associated Accounts
**Risk signals:**
- Multiple accounts sharing device_id or fingerprint_id → HIGH
- Multiple accounts sharing registration IP → HIGH
- Internal transfers between identified accounts → HIGH
- Sub-account creation burst (many sub-accounts in short time) → MEDIUM
- opposite_user_id is a related account → CRITICAL (self-trading)

### Dimension 4: IP & Geolocation
**Risk signals:**
- FATF blacklist countries (Myanmar, Syria, Yemen, South Sudan) → CRITICAL (floor: 60)
- IP country mismatches KYC nationality → MEDIUM
- Rapid country switching (>3 countries in 7 days) → HIGH
- Login from known high-risk regions → MEDIUM
- Multiple distinct device_ids with same fingerprint → LOW (browser reset)
- Login exclusively from data-center IPs (hard to detect without raw IP) → note if user_agent suggests automated

### Dimension 5: Email & Identity Patterns
**Limited by sensitive field restrictions.** Analyze what's available:
- phone_area_code vs KYC nationality mismatch → MEDIUM
- KYC nationality in high-risk jurisdiction → MEDIUM
- Enterprise account (kyc_user_type=1) with unusual trading → note
- source_wealth or plan_trade_volume inconsistent with actual behavior → MEDIUM

### Dimension 6: Profit & Loss
**Risk signals:**
- Abnormally high win rate (>80% of trades profitable) → MEDIUM
- Total profit >> total deposit (especially with leverage) → MEDIUM
- Profit concentrated in single instrument → HIGH (if small-cap)
- Equity significantly higher than cumulative deposits → investigate source
- Rapid equity growth followed by withdrawal → HIGH

### Dimension 7: Withdrawal Behavior
**Risk signals:**
- Withdrawal immediately after profit (< 30 minutes) → HIGH
- Total withdrawals >> Total deposits → MEDIUM
- No on-chain deposits, only internal transfers in → MEDIUM (if combined with withdrawals out)
- Withdrawal timing clusters with price spike events → HIGH
- All withdrawals to same external address → LOW (normal)
- Withdrawals to many different addresses → MEDIUM
- Internal transfer in → immediate on-chain withdrawal → HIGH

### Dimension 8: Comprehensive Judgment

**Attack Pattern Matching** — Check against the 4 known attack types:

| Pattern | Key Signals |
|---------|------------|
| Insurance Fund Drain | Isolated margin, opposite positions on related accounts, repeated liquidation on same orderbook, withdrawal >> deposit |
| Equity Inflation | Far-price limit orders inflating equity, transfers between core + satellite accounts, identical position structures |
| Liquidation Distribution | Multiple accounts same direction same leverage, liquidation prices clustered, position sizes similar across accounts |
| Market Manipulation | Small-cap concentration, high taker ratio, large OI%, simultaneous spot+perp, price moves before competitors |

**Scoring guidance** (reference only — give qualitative judgment, not a numeric score):
- T1 Low Risk (0-25): No significant signals across any dimension
- T2 Medium Risk (26-50): 1-2 moderate signals, no pattern match
- T3 High Risk (51-75): Multiple signals or partial pattern match
- T4 Critical Risk (76-100): Clear pattern match or hard-floor trigger

**Hard floors (auto-escalate):**
- FATF blacklist country → minimum T3
- Unverified KYC + deposits > $10K → minimum T3
- OI >= 50% + price move >= 20% in < 30 min → T4 CONFIRMED
- Known attacker UID match → T4 regardless of score

---

## Phase 3 — HTML Report Generation

Generate a **self-contained HTML file** with inline CSS. Save to:
`~/WorkSpace/user-risk-reports/{uid}_risk_report.html`

### Canonical Template

**Read `references/report_template.html` before generating any report.** This file
contains the exact CSS, HTML structure, class names, and section ordering that ALL
reports must follow. The template uses `{{VARIABLE}}` placeholders — replace them
with actual data, but do NOT modify the CSS or structural HTML.

### Hard Rules

1. **CSS is frozen.** Copy the entire `<style>` block from the template verbatim.
   Do not add, remove, or modify any CSS rules.

2. **Section order is fixed:**
   Header → Executive Summary → Timeline → Dimension Cards (D1-D8 in grid) →
   Login Summary → Trading Summary → Footer.

3. **Badge classes must match tier:**
   - T1: `badge-t1`, text "T1 LOW RISK"
   - T2: `badge-t2`, text "T2 MEDIUM RISK"
   - T3: `badge-t3`, text "T3 HIGH RISK" (CSS adds pulse animation)
   - T4: `badge-t4`, text "T4 CRITICAL RISK" (CSS adds faster pulse)

4. **Severity badges on dimension cards:** Use `sev-none`, `sev-low`, `sev-medium`,
   `sev-high`, `sev-critical`. Text labels: NONE / LOW / MEDIUM / HIGH / CRITICAL.

5. **Color classes for inline text:**
   - `.safe` (green) — no risk signal
   - `.warn` (yellow) — medium risk signal
   - `.danger` (red) — high/critical risk signal
   - `.highlight` (accent yellow) — emphasis, not risk-related

6. **D8 card is always full-width:** `style="grid-column: 1 / -1;"`

7. **Timeline dot colors:**
   - Default `var(--accent)` — normal event
   - `var(--t3)` — anomalous/risky event
   - `var(--t2)` — notable but not alarming
   - `var(--muted)` — dormant period or placeholder

8. **Conditional sections:** Alert boxes, counterparty tables, device history,
   perpetrator-vs-victim analysis — include only when data warrants it.
   Omit cleanly (no empty divs or placeholder text).

9. **Footer must always include:**
   - Data sources with table names and pt ranges
   - Data gaps (what was unavailable and why)
   - Disclaimer line
   - Signature: `Report by Nova · Hongyi's AI Assistant · YYYY-MM-DD`
   - One-liner witty quip from Nova (match tone to severity — dark humor for
     serious cases, light for routine ones)

10. **`.mono` class** for all IDs, numeric values, dates, and technical identifiers.

11. **`<details>` collapsible sections** for: top counterparties, device history,
    raw data dumps. Do NOT put primary analysis inside collapsibles.

12. **Print stylesheet** is built into the CSS. No additional print handling needed.

### Adapt, Don't Rigidly Fill

The template shows ALL possible sections and rows. Not every report needs every row.
- If a dimension has no data: keep the card, show "N/A" severity, explain what's missing
- If a dimension has no risk signals: keep the card, show "NONE" severity, note why
- If data is partial: note what's available vs missing in the analysis paragraph
- Add dimension-specific rows as needed (the template rows are examples, not exhaustive)
- The executive summary paragraph and analysis paragraphs are free-form — write them
  to match the specific user's risk profile

---

## Multi-User Mode

When multiple user IDs are provided:
1. Run Phase 1 for all users in parallel (batch queries where possible)
2. Run Phase 2 for each user independently
3. Generate ONE HTML report with a tab/section per user + a comparison summary
4. Highlight any cross-user connections (shared devices, IPs, counterparty relationships)

---

## Error Handling

- If a query returns 0 rows: note "No data available" for that dimension, do not skip it
- If a query fails (403 sensitive field): remove the field and retry automatically
- If pt for yesterday has no data: try pt = day before yesterday
- If master_user_id resolution fails: try querying by uid field directly
- Always report what data was and wasn't available in the footer

---

## Lessons Learned from Production Usage (Updated 2026-03-27)

### Data Query MCP — Critical Gotchas

**1. Partition format matters:**
- Daily tables (`_df`): pt format is `YYYYMMDD` (e.g., `20260325`)
- Hourly tables (`_hf`, `_hi`): pt format is `YYYYMMDDHH` (e.g., `2026032500`)
- Latest partition for daily tables is usually **yesterday** (T-1), not today
- To find latest partition: `SELECT pt FROM table WHERE pt >= '20260324' GROUP BY pt ORDER BY pt DESC LIMIT 5`

**2. No INFORMATION_SCHEMA access:**
- `SELECT * FROM INFORMATION_SCHEMA.COLUMNS` returns 403 — cannot introspect table schemas
- Use the reference tables in this skill file or the risk-rca-report skill for column names
- If a column doesn't exist, the error message often suggests the correct name (e.g., `position_volume` → "Did you mean position_type?")

**3. No `SELECT *` allowed:**
- Must list specific columns. `SELECT *` returns 400 error.

**4. Position table column names:**
- Table: `dwd_okx_asset_user_position_hf`
- **WRONG**: `position_volume`, `position_side`
- **CORRECT**: `position_type` (1=long, 2=short), `margin_mode` (2=cross, 3=isolated)
- **user_id** in position table = `master_user_id` in user_master_info table
- Partition: hourly format `YYYYMMDDHH`

**5. Query wait time:**
- After `submitQuery`, wait **8 seconds** before `getQueryResult` (not 3-5 as docs say)
- Simple queries (single partition, small result): ~5-8 seconds
- Complex queries (multi-partition, aggregation): 10-30 seconds
- If `IN_PROGRESS` after first try, wait another 5 seconds and retry

**6. All result values are strings:**
- Numbers come back as strings (e.g., `"583173.771632669225"`)
- Booleans come back as Chinese strings (e.g., `"普通用户"`, `"普通账户"`)
- Timestamps come back as full ISO with timezone (e.g., `"2024-04-19T21:07:47+08:00[Asia/Shanghai]"`)

**7. Table access verified (as of 2026-03-27):**

| Table | Access | Partition | Notes |
|-------|--------|-----------|-------|
| `dws_okx_user_master_info_df` | ✅ | YYYYMMDD | User profile, KYC, trade volume |
| `dwd_okx_asset_user_position_hf` | ✅ | YYYYMMDDHH | Position snapshots. Use `position_type` not `position_side` |
| `dwd_okx_user_secure_login_df` | ✅ | YYYYMMDD | Login history. Sensitive: `ip` field blocked |
| `dwd_okx_user_kyc_pass_data_df` | ✅ | YYYYMMDD | KYC details |
| `dwd_okx_trade_pm_user_bill_hi` | ⚠️ | YYYYMMDDHH | Bill table — may need auth. Hourly partitioned, wide ranges timeout |
| `dwd_okx_depositwithdraw_onchain_order_hf` | ⚠️ | YYYYMMDDHH | Massive table. Single-day queries may return 0 rows |

**8. Efficient querying pattern for flagged-asset investigation:**
```
Step 1: Get position holders on flagged asset
  → SELECT user_id, instrument_name, position_type, margin_mode, create_time
    FROM dwd_okx_asset_user_position_hf
    WHERE pt = '{latest_hourly_pt}' AND instrument_name LIKE '{ASSET}%'
    LIMIT 10

Step 2: Get user profiles for position holders (batch)
  → SELECT master_user_id, uid, register_time, kyc_pass_max_level,
      kyc_pass_nationality_name, trade_volume_usdt_sth,
      all_account_equity_volume_usdt, user_fee_level_value,
      is_market_account, is_internal_account,
      first_deposit_time, first_trade_time
    FROM dws_okx_user_master_info_df
    WHERE pt = '{yesterday_daily_pt}'
      AND master_user_id IN ('id1','id2','id3','id4','id5')

Step 3: Quick risk signals from profile data (no additional queries needed)
  - equity vs trade_volume ratio → extreme drawdown signal
  - register_time age → new account risk
  - kyc_nationality vs trade pattern → jurisdiction mismatch
  - is_market_account/is_internal_account → filter out known accounts
  - first_deposit_time vs register_time → delayed funding signal
```

**9. Performance tips:**
- Submit independent queries in parallel (multiple `submitQuery` calls, then batch `getQueryResult`)
- For position holders: query with `LIMIT 10` first, only profile top 5
- For user profiles: batch all user_ids in one `IN (...)` clause instead of individual queries
- Skip Q4 (deposit/withdrawal) in automated pipeline — it's slow and often returns 0 rows
- For automated daily reports, 2 queries are usually enough: positions + user profiles
