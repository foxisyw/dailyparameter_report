# Daily Report Runbook — Complete Execution Steps

**This is the single source of truth for running the daily report.**
Claude Code MUST follow ALL steps in order. Do NOT skip any step.
Do NOT proceed to dashboard generation until ALL user profiles are complete.

---

## ⚠️ DATA INTEGRITY RULES — NON-NEGOTIABLE

1. **Never use cached data.** `runner/local/risk_intel_input.json` is deleted before every cron run. You MUST call the MCP tools to get fresh data. If the file already exists, treat it as stale and DO NOT use it.

2. **Never lie about freshness.** If you cannot get fresh data from Lark MCP or Data Query MCP, output `CRON_ABORT: MCP tools not available` and stop completely. Do NOT generate a report, do NOT deploy, do NOT send a Lark notification. An honest failure is better than a false "success" built on stale data.

3. **Never report "complete" if you used cached or invented data.** If steps 1-7 were skipped or approximated, the report is NOT ready. Stop and flag the failure clearly in the log.

4. **Verify MCP tools first.** Before doing any work, confirm that `lark_docx_raw_content` and `submitQuery` are callable. If either is missing, abort immediately.

---

## Trigger

When the user says any of:
- "run daily report", "跑日報", "generate report", "run cron"
- "run-and-deploy", "./run-and-deploy.sh"
- Or at the scheduled cron time

## Step 1: Read Latest Lark Risk Document

### 1a. Browse the Lark folder for the latest risk document
```
Folder URL: https://okg-block.sg.larksuite.com/drive/folder/Wu2Pfktq6lq4t8dWL52lB97pgQb
Folder token: Wu2Pfktq6lq4t8dWL52lB97pgQb

Use: mcp__claude_ai_OKEngine_LARK_MCP__lark_docs_search
  search_key: "每日风控总结"
  count: 10
```
Look through the results and match documents belonging to this folder.

### 1b. Pick the document with the CLOSEST date to today
- Parse the date from each document title (format: `YYYY-MM-DD`)
- Select the one with the most recent date
- If multiple with same date, pick the one modified most recently

### 1c. Read the document content
```
Use: mcp__claude_ai_OKEngine_LARK_MCP__lark_docx_raw_content
  document_id: {the docs_token from step 1b}
```

### 1d. Save the document content
Save to `runner/local/risk_intel_input.json` in this format:
```json
{
  "folder_documents": [{
    "title": "document title",
    "content": "full document text",
    "modified_at": "ISO timestamp",
    "url": "https://okg-block.sg.larksuite.com/docx/{docs_token}"
  }],
  "profiles": {},
  "suspicious_users_override": []
}
```

---

## Step 2: Identify Flagged Assets from Document

Parse the document content to find HIGH RISK assets:
- Look for 🔴 (critical) mentions — these are priority assets
- Extract instrument/coin names: e.g., PROVE, XAU-USD, PIPPIN
- These are the assets we need to investigate

---

## Step 3: Query Position Holders on Flagged Assets

For EACH critical/high-risk asset identified in Step 2:

### 3a. Find latest hourly partition
```
Use: mcp__claude_ai_Data_Query_-_Global__submitQuery
  sql: SELECT pt FROM ex_offline.dwd_okx_asset_user_position_hf
       WHERE pt >= '{yesterday}00' GROUP BY pt ORDER BY pt DESC LIMIT 1
  project: ex_offline
```
Wait 8 seconds, then getQueryResult.

### 3b. Get top position holders
```
Use: mcp__claude_ai_Data_Query_-_Global__submitQuery
  sql: SELECT user_id, instrument_name, position_type, margin_mode, create_time
       FROM ex_offline.dwd_okx_asset_user_position_hf
       WHERE pt = '{latest_hourly_pt}'
         AND instrument_name LIKE '{ASSET}%-USDT-SWAP'
       LIMIT 20
  project: ex_offline
```
Wait 8 seconds, then getQueryResult.

### 3c. Collect unique user_ids
Merge all user_ids from all flagged asset queries.
Remove duplicates. These are our suspicious user candidates.

---

## Step 4: Get Full User Profiles (ALL 5 users — NO EXCEPTIONS)

### 4a. Query user master info (BATCH all users in one query)
```
Use: mcp__claude_ai_Data_Query_-_Global__submitQuery
  sql: SELECT master_user_id, uid, register_time, register_client_type,
         register_country_big_region, phone_area_code,
         is_market_account, is_internal_account,
         kyc_pass_max_level, kyc_pass_nationality_name,
         first_deposit_time, first_trade_time,
         trade_volume_usdt_sth, all_account_equity_volume_usdt,
         user_fee_level_value, first_deposit_volume_usdt,
         last_deposit_time, kyc1_pass_time, kyc2_pass_time
       FROM ex_offline.dws_okx_user_master_info_df
       WHERE pt = '{yesterday_YYYYMMDD}'
         AND master_user_id IN ('{id1}','{id2}','{id3}',...)
  project: ex_offline
```
Wait 8 seconds, then getQueryResult.

**IMPORTANT:** If some user_ids return 0 rows, they may be sub-account IDs.
Query the FULL position table result (all 20 users from Step 3b) and use the
ones that DO have master_info entries. Pick the TOP 5 by risk severity.

### 4b. For each user, build 8-dimension risk analysis

Use the Core Trading User Risk Skill dimensions:

**Dimension 1: Registration Profile**
- Account age (register_time vs now)
- Registration to first deposit gap
- KYC nationality vs phone area code match
- Region classification

**Dimension 2: Trading Behavior**
- Trade volume vs equity ratio (critical if < 0.01)
- Concentration on flagged asset
- Position type (long=1, short=2)

**Dimension 3: Associated Accounts**
- Try login table: `dwd_okx_user_secure_login_df`
- If 403: mark as "Login table access denied — cannot verify"

**Dimension 4: IP & Geolocation**
- From login table if accessible
- Otherwise: use register_country_big_region

**Dimension 5: Identity Signals**
- KYC level and nationality
- is_market_account, is_internal_account
- Phone area code vs nationality match

**Dimension 6: Profit & Loss**
- Current equity vs total trade volume
- Equity depletion ratio
- First deposit volume

**Dimension 7: Withdrawal Behavior**
- Last deposit time
- If deposit/withdrawal table accessible, check patterns

**Dimension 8: Comprehensive Judgment**
- Combine all signals
- Check against attack patterns (insurance drain, equity inflation)
- Assign overall risk tier: T1/T2/T3/T4

### 4c. VALIDATION — Do NOT proceed until:
- [ ] All 5 users have master_user_id resolved
- [ ] All 5 users have at least 5/8 dimensions filled with real data
- [ ] All 5 users have executive_summary (not "pending")
- [ ] Overall risk tier assigned to each user

---

## Step 5: Save Initial Risk Intel Input

Update `runner/local/risk_intel_input.json` with:
- `folder_documents`: the Lark document from Step 1
- `profiles`: dict keyed by both uid AND master_user_id
- `suspicious_users_override`: list of 5 users with risk_tier, source_alert, reason
- `event_analyses`: [] (placeholder — will be filled in Step 6)
- Verify the JSON is valid before saving

---

## Step 6: Build Event Analyses (RCA) for Each Flagged Asset

**This is the most critical step.** Each 🔴 critical asset from Step 2 needs a complete
Root Cause Analysis event. The report WILL BE REJECTED by validation if this step is skipped.

### 6a. Collect hourly position snapshots (Data Query)

For each flagged asset, query hourly user counts to build a growth table:
```sql
SELECT pt, COUNT(DISTINCT user_id) as total_users,
       SUM(CASE WHEN position_type='1' THEN 1 ELSE 0 END) as longs,
       SUM(CASE WHEN position_type='2' THEN 1 ELSE 0 END) as shorts
FROM ex_offline.dwd_okx_asset_user_position_hf
WHERE pt >= '{today_YYYYMMDD}00' AND pt <= '{today_YYYYMMDD}{current_hour}'
  AND instrument_name = '{ASSET}-USDT-SWAP'
GROUP BY pt ORDER BY pt
```

### 6b. Fetch live market data (OKX REST API)

For each flagged asset, call:
- `GET https://www.okx.com/api/v5/market/ticker?instId={ASSET}-USDT-SWAP`
  → extract: last, open24h, high24h, low24h, volCcy24h
- `GET https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId={ASSET}-USDT-SWAP`
  → extract: oi, oiCcy, oiUsd
- `GET https://www.okx.com/api/v5/public/funding-rate?instId={ASSET}-USDT-SWAP`
  → extract: fundingRate (optional, skip if 404)

### 6c. Build causal chain (3-5 steps)

Each step MUST have these fields:
```json
{
  "step": 1,
  "type": "远因|近因|触发事件|风险放大",
  "name": "short title",
  "description": "what happened and why",
  "evidence_strength": 1-5,
  "evidence_label": "e.g. 铁证 · 数仓实查",
  "detail": "optional extra detail",
  "evidence_table": null or {"title", "headers", "rows", "source"},
  "risk_assessment": null
}
```

**Minimum causal chain structure:**
1. **远因** — Structural weakness (e.g. thin liquidity, low float)
2. **近因** — User influx with `evidence_table` from 6a hourly data
3. **触发事件** — The alert trigger (OI breach, price limit hit)
4. **风险放大** — User concentration with `evidence_table` showing top users from Step 4

### 6d. Build user profiles INSIDE each event analysis

For each event's top users (from Step 4), create a profile with **exactly this format**:
```json
{
  "uid": "18-digit uid",
  "master_user_id": "shorter id",
  "overall_risk_tier": "T1|T2|T3|T4",
  "executive_summary": "1-2 sentence summary of this user's risk",
  "dimensions": [
    {"name": "Registration Profile", "severity": "pass|warning|critical|pending", "signals": ["signal text"]},
    {"name": "Trading Behavior", "severity": "...", "signals": ["..."]},
    {"name": "Associated Accounts", "severity": "...", "signals": ["..."]},
    {"name": "IP & Geolocation", "severity": "...", "signals": ["..."]},
    {"name": "Identity Signals", "severity": "...", "signals": ["..."]},
    {"name": "Profit & Loss", "severity": "...", "signals": ["..."]},
    {"name": "Withdrawal Behavior", "severity": "...", "signals": ["..."]},
    {"name": "Comprehensive Judgment", "severity": "...", "signals": ["..."]}
  ],
  "key_evidence": ["evidence1", "evidence2"]
}
```

**CRITICAL:** Each dimension MUST have a `severity` field (not `summary`). Use:
- `"critical"` — strong risk signal
- `"warning"` — moderate risk signal
- `"pass"` — no risk signal
- `"pending"` — data not available (e.g. login table 403)

### 6e. Assemble each event_analyses entry

Each event analysis object MUST use these EXACT field formats (the frontend will not render
sections that don't match). Copy-paste this template and fill in the values:

```json
{
  "asset": "PROVE-USDT-SWAP",
  "severity": "critical",
  "executive_summary": "2-3 sentence overview with key numbers",
  "forward_looking": "What to watch + recommended actions",
  "causal_chain": [/* from 6c — at least 3 steps */],

  "market_snapshot": {
    "price": "0.2676",
    "change_24h": "-2.5%",
    "open_interest": "5694911",
    "funding_rate": "-0.00075",
    "vol_24h": "253052895",
    "timestamp": "2026-03-27T16:39 HKT"
  },

  "key_users": [{"user_id": "8446803", "side": "short", "positions": 2, "note": "..."}],

  "quantitative_impact": {
    "title": "Quantitative Impact",
    "metrics": [
      {"value": "112.65%", "label": "OI/Limit Ratio", "detail": "threshold 80%"},
      {"value": "188.16%", "label": "OI 24H Deviation", "detail": "threshold 20%"}
    ]
  },

  "oi_attribution": {
    "title": "OI Attribution",
    "description": "optional text description",
    "user_hourly_table": {
      "headers": ["Time(HKT)", "Total Users", "Long", "Short", "Net Change"],
      "rows": [["00:00", "6813", "3384", "4124", "—"], ["06:00", "7838", "3830", "5000", "+983"]]
    }
  },

  "risk_assessment": {
    "title": "Risk Assessment",
    "actions": [
      {"priority": "P0", "action": "action text here", "reason": "reason text here"},
      {"priority": "P1", "action": "...", "reason": "..."},
      {"priority": "P2", "action": "...", "reason": "..."}
    ]
  },

  "involved_users_brief": {
    "title": "Involved Users",
    "headers": ["Master ID", "Side", "RISK", "Note"],
    "rows": [["8446803", "SHORT", "T1", "2x cross+iso, trade/equity=1.65Mx"]]
  },

  "user_profiles": [/* from 6d — full 8-dimension profiles for each key user */]
}
```

**FIELD NAME GOTCHAS (frontend will silently fail if wrong):**
- `market_snapshot.change_24h` NOT `price_24h_change`
- `market_snapshot.open_interest` NOT `oi`
- `market_snapshot.funding_rate` as decimal NOT percentage string
- `quantitative_impact.metrics` array NOT flat key-values
- `oi_attribution.user_hourly_table` nested object NOT flat values
- `risk_assessment.actions[].action` NOT `text`
- `involved_users_brief.headers` + `rows` table format NOT array of objects

**RISK TIER MAPPING (frontend):** T1=CRITICAL(red), T2/T3=WARNING(orange), T4=PASS(green)

### 6f. Save event_analyses to risk_intel_input.json

Add the `event_analyses` array to `runner/local/risk_intel_input.json` alongside the existing
`folder_documents`, `profiles`, and `suspicious_users_override`.

**The final JSON MUST have all 4 top-level keys:**
```json
{
  "folder_documents": [/* from Step 1 */],
  "profiles": {/* from Step 4, keyed by uid AND master_user_id */},
  "suspicious_users_override": [/* from Step 4, top 5 */],
  "event_analyses": [/* from Step 6, one per critical asset */]
}
```

### 6g. VALIDATION GATE

`generate_risk_intel.py` will **reject and abort** if:
- `event_analyses` is empty (when there are 🔴 assets)
- Any event is missing `user_profiles`
- Any user profile has fewer than 4/8 dimensions with severity filled
- Any suspicious user is missing `executive_summary`

Do NOT proceed to Step 7 until this validation passes.

---

## Step 7: Generate Report

```bash
cd "/Users/stevensze/Documents/Daily Parameter Dashboard/Claude Code"
python3 -m runner.generate_risk_intel --date $(date +%Y-%m-%d)
python3 -m runner.main --no-lark
```

If `generate_risk_intel` exits non-zero, **STOP** — go back to Step 6 and fix the data.

Verify output:
- Risk Intelligence chapter is NOT "pending"
- Event analyses count > 0
- All 4-5 suspicious users have filled profiles
- Price Limit chapter has real data

---

## Step 8: Deploy to Vercel

```bash
git add public/data/
git commit -m "Daily review $(date +%Y-%m-%d) — full MCP pipeline"
git push
```

Wait 90 seconds for Vercel to deploy.

---

## Step 9: Send Lark Notification

```bash
python3 -m runner.notify_lark
```

---

## Known Table Access Issues

| Table | Status | Workaround |
|-------|--------|-----------|
| `dws_okx_user_master_info_df` | ✅ Works | Primary user profile source |
| `dwd_okx_asset_user_position_hf` | ✅ Works | Position data, use position_type not position_side |
| `dwd_okx_user_secure_login_df` | ❌ 403 | Cannot verify device/IP — mark dimension as "access denied" |
| `dwd_okx_depositwithdraw_onchain_order_hf` | ⚠️ Slow | Skip in automated mode, mark as "data limited" |
| `dwd_okx_user_kyc_pass_data_df` | ✅ Works | KYC details |

## Column Name Reference (VERIFIED)

Position table (`dwd_okx_asset_user_position_hf`):
- `user_id` (= master_user_id), `instrument_name`, `position_type` (1=long, 2=short)
- `margin_mode` (2=cross, 3=isolated), `create_time`
- Partition: `YYYYMMDDHH`

User master info (`dws_okx_user_master_info_df`):
- `master_user_id`, `uid`, `register_time`, `kyc_pass_max_level`
- `kyc_pass_nationality_name`, `trade_volume_usdt_sth`, `all_account_equity_volume_usdt`
- `is_market_account`, `is_internal_account`, `phone_area_code`
- Partition: `YYYYMMDD`, latest is usually T-1
