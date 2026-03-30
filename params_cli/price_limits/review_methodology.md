# Price Limit Parameters Review Methodology

## Background

OKX applies price limit parameters (Y caps and Z caps) to all trading instruments to constrain how far an order price can deviate from the index price. The Y cap defines an inner (softer) band; the Z cap defines an outer hard cap. These parameters are set per instrument and should reflect its asset class, liquidity, and basis profile. This document describes a systematic review process to identify misconfigurations and generate adjustment recommendations.

## Objective

Review all OKX instruments' price limit parameters (Y/Z caps) to identify improper or risky configurations, and generate adjustment recommendations.

## Input Data

The data source file (file C) is a CSV containing per-instrument:

- **instType**: SPOT, SWAP, or FUTURES
- **instId**: instrument identifier (e.g. BTC-USDT-SWAP)
- **upper_Y_cap / lower_Y_cap**: inner band ±Y% from index price
- **upper_Z_cap / lower_Z_cap**: outer hard cap ±Z% from index price
- **assetsType**: TradFi, Topcoins, Fiat, or Altcoins (derived from base currency)
- **basis_ema**: 24h EMA of (mid / index - 1), represents persistent premium/discount
- **spread_ema**: 24h EMA of bid-ask spread ratio
- **limitUp_buffer_ema**: 24h EMA of (buyLmt / bestAsk - 1), how far price is from upper limit
- **limitDn_buffer_ema**: 24h EMA of (bidPx / sellLmt - 1), how far price is from lower limit
- **volCcy24h_ema**: 24h EMA of 24-hour trading volume in quote currency (USD equivalent)

## Review Rules

### Rule 1: Insufficient Buffer — Diagnostic Triage

**Trigger**: `limitUp_buffer_ema < 0` or `limitDn_buffer_ema < 0` (price persistently near or beyond a limit).

When triggered, diagnose the root cause using the following decision tree:

**Step 1 — Check B/A spread:**
If `spread_ema > 0.50%` (50 bps), the insufficient buffer is caused by poor liquidity / wide quotes, not by cap misconfiguration.
- **Action**: Flag as "liquidity issue". Recommend enhancing liquidity (e.g. onboard MM, adjust incentives). **No parameter adjustment needed.**

**Step 2 — Check 24h volume (only if spread ≤ 50 bps):**
If `volCcy24h_ema < 5000` (i.e. < $5k daily volume), the market is quoted tightly but barely traded — the limit breach is likely caused by a stale or misquoted index/mark price.
- **Action**: Flag as "mispricing". Recommend the MM to take misquote orders to correct the price. **No parameter adjustment needed.**

**Step 3 — Severe buffer breach (spread ≤ 50 bps AND volume ≥ $5k):**
The instrument is actively traded with healthy liquidity, yet the price is persistently hitting the limit. This is a genuine cap misconfiguration.
- **Action**: Widen the Z cap on the affected side. Use the basis direction to determine which side:
  - If `limitUp_buffer_ema < 0`: widen `upper_Z_cap`
  - If `limitDn_buffer_ema < 0`: widen `lower_Z_cap`
  - Set the new Z cap to at least `|basis_ema| + spread_ema + 2%` buffer, rounded up to a clean percentage, and no less than the asset-type default from Rule 3.

### Rule 2: Asymmetric Basis with Symmetric Caps

**Trigger**: The basis is persistently large relative to the Z cap on one side.

Specifically, flag when:
- `basis_ema > 0` and `basis_ema > upper_Z_cap * 0.5` (basis consuming >50% of the upper Z cap headroom)
- `basis_ema < 0` and `|basis_ema| > lower_Z_cap * 0.5` (basis consuming >50% of the lower Z cap headroom)

Apply the same diagnostic triage as Rule 1 before recommending a Z cap adjustment:

1. If `spread_ema > 0.50%` → flag as "liquidity issue", recommend enhancing liquidity. No adjustment.
2. If `spread_ema ≤ 0.50%` and `volCcy24h_ema < 5000` → flag as "mispricing", recommend MM to take misquote orders. No adjustment.
3. If `spread_ema ≤ 0.50%` and `volCcy24h_ema ≥ 5000` → widen the Z cap on the affected side:
   - If basis positive: set `upper_Z_cap` to at least `basis_ema + spread_ema + 2%` buffer
   - If basis negative: set `lower_Z_cap` to at least `|basis_ema| + spread_ema + 2%` buffer
   - Round up to a clean percentage, and no less than the asset-type default from Rule 3.

### Rule 3: Asset-Type or instType Consistency

Check that instruments of the same assetsType have consistent cap ranges:

- **TradFi**: Y caps typically 2%, Z caps typically 5%
- **Topcoins**: Y caps typically 0.5–1%, Z caps typically 1–2%
- **Fiat**: Y caps typically 0.5–1%, Z caps typically 1%~2%
- **Altcoins**: for perp: Y caps typically <= 4%, Z caps typically 10% for upper cap, 30% for lower cap. for spot, Z caps typically <= 5%, Y caps typically smaller than Z cap 

For the instruments under the same 'instType' with the same base coin, their Y cap and Z cap should be the same.

For 'instType' = FUTURES, its Z cap should be greater than basis plus a extra buffer.


### Rule 4: Z Cap Must Be Greater Than Y Cap

If `upper_Z_cap <= upper_Y_cap` or `lower_Z_cap <= lower_Y_cap`, the outer band is not wider than the inner band, which is misconfigured.

**Action**: Refer to rule 3 to set a default Y cap and Z cap

## Output Format

### 1. Review Summary

Output a single structured markdown report. Group findings by rule, then by verdict. Use tables — not prose — for listing instruments.

**Format per rule:**

```
### Rule N: <Rule Name>

**<Verdict>** — <count> instrument(s)

| instId | instType | spread_ema | volCcy24h_ema | basis_ema | current cap | proposed cap | reason |
|--------|----------|------------|---------------|-----------|-------------|--------------|--------|
| ...    | ...      | ...        | ...           | ...       | ...         | ...          | ...    |

```

Verdicts are one of:
- **Adjust** — parameter change needed (include proposed values)
- **Liquidity issue** — wide spread, recommend enhancing liquidity
- **Mispricing** — tight spread but no volume, recommend MM take misquote orders
- **Consistency fix** — caps deviate from asset-type defaults or same-coin peers

Rules that find no issues: output `**No issues found.**` and move on. Do not list clean instruments.

Keep commentary to one sentence per verdict group explaining the pattern. No per-instrument narratives.

### 2. Adjustment File

For all instruments with verdict **Adjust** or **Consistency fix**, call `./cli.py generate-adjustment` with the proposed values to generate the CSV file. Output the file path at the end.