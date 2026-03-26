# Daily Report Runbook — Complete Execution Steps

**This is the single source of truth for running the daily report.**
Claude Code MUST follow ALL steps in order. Do NOT skip any step.
Do NOT proceed to dashboard generation until ALL user profiles are complete.

---

## Trigger

When the user says any of:
- "run daily report", "跑日報", "generate report", "run cron"
- "run-and-deploy", "./run-and-deploy.sh"
- Or at the scheduled cron time

## Step 1: Read Latest Lark Risk Document

### 1a. Search for the latest risk document
```
Use: mcp__claude_ai_OKEngine_LARK_MCP__lark_docs_search
  search_key: "每日风控总结"
  count: 10
```

### 1b. Pick the document with the CLOSEST date to today
- Parse the date from each document title (format: `YYYY-MM-DD`)
- Select the one with the most recent date
- If multiple with same date, pick the one modified most recently

### 1c. Read the document content
```
Use: mcp__claude_ai_OKEngine_LARK_MCP__lark_docx_raw_content
  document_id: {the docs_token from step 1a}
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

## Step 5: Save Complete Risk Intel Input

Update `runner/local/risk_intel_input.json` with:
- `profiles`: dict keyed by both uid AND master_user_id
- `suspicious_users_override`: list of 5 users with risk_tier, source_alert, reason
- Verify the JSON is valid before saving

---

## Step 6: Generate Report

```bash
cd "/Users/stevensze/Documents/Daily Parameter Dashboard/Claude Code"
python3 -m runner.generate_risk_intel --date $(date +%Y-%m-%d)
python3 -m runner.main --no-lark
```

Verify output:
- Risk Intelligence chapter is NOT "pending"
- All 4-5 suspicious users have filled profiles
- Price Limit chapter has real data

---

## Step 7: Deploy to Vercel

```bash
git add public/data/
git commit -m "Daily review $(date +%Y-%m-%d) — full MCP pipeline"
git push
```

Wait 90 seconds for Vercel to deploy.

---

## Step 8: Send Lark Notification

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
