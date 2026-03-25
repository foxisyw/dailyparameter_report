# Price Limit Parameters Review Methodology

## Background

OKX applies price limit parameters (Y caps and Z caps) to all trading instruments to constrain how far an order price can deviate from the index price. The Y cap defines an inner (softer) band; the Z cap defines an outer hard cap. These parameters are set per instrument and should reflect its asset class, liquidity, and basis profile. This document describes a systematic review process to identify misconfigurations and generate adjustment recommendations.

## Objective

Review all OKX instruments' price limit parameters (Y/Z caps) to identify improper or risky configurations, and generate adjustment recommendations.

## Objective

Review all OKX instruments' price limit parameters (Y/Z caps) to identify improper or risky configurations, and generate adjustment recommendations.

## Input Data

The data source file (file C) is a markdown table containing per-instrument:

- **instType**: SPOT, SWAP, or FUTURES
- **instId**: instrument identifier (e.g. BTC-USDT-SWAP)
- **upper_Y_cap / lower_Y_cap**: inner band ±Y% from index price
- **upper_Z_cap / lower_Z_cap**: outer hard cap ±Z% from index price
- **assetsType**: TradFi, Topcoins, Fiat, or Altcoins (derived from base currency)
- **basis_ema**: 24h EMA of (mid / index - 1), represents persistent premium/discount
- **spread_ema**: 24h EMA of bid-ask spread ratio
- **limitUp_buffer_ema**: 24h EMA of (buyLmt / bestAsk - 1), how far price is from upper limit
- **limitDn_buffer_ema**: 24h EMA of (bidPx / sellLmt - 1), how far price is from lower limit

## Review Rules

### Rule 1: Buffer Too Tight

If `limitUp_buffer_ema < 0` or `limitDn_buffer_ema < 0`, the price is persistently close to a limit. Compare the B/A spread with Y cap spread (Y upper cap to lower cap). If Y cap is too tight or even smaller than B/A spread, widen the Y cap properly

### Rule 2: Asymmetric Basis with Symmetric Caps

Compare the basis with the Z cap, if basis is positive, then compare with upper Z cap, if negative, compare with lower Z cap. if basis is too large, widen the Z cap properly

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

1. **Review summary** (markdown): generate a review summary for each step, eg, what instruments' params are incorrect and why, and what's the proposed changes.
2. **Adjustment file**: for instruments that need changes, call the `./cli.py generate-adjustment` to generate the adjustment file