# Instrument Tagger CLI

Tag OKX instruments with predefined labels based on configurable rules.

## Location

```
/Users/oker/Documents/params_dashboard/params_cli/common/cli.py
```

## Commands

```bash
cd /Users/oker/Documents/params_dashboard/params_cli/common
```

### `help` — Show workflows and method list

```bash
./cli.py help
```

### `get-all` — Get all instruments with tags

```bash
./cli.py get-all                  # all instruments
./cli.py get-all --type SWAP      # filter by type
./cli.py get-all --limit 10       # limit results
./cli.py get-all --live-only      # only live instruments
```

Returns: instId, instType, productType, state, baseCcy, quoteCcy, settleCcy, listTime, tags

### `get` — Get specific instruments with tags

```bash
./cli.py get BTC-USDT-SWAP
./cli.py get BTC-USDT-SWAP ETH-USDT-SWAP
```

### `filter-by-tag` — Filter instruments by tag name

```bash
./cli.py filter-by-tag um_perp
./cli.py filter-by-tag btc_base --limit 5
```

### `list-rules` — List available tagging rules

```bash
./cli.py list-rules
```

### `refresh-cache` — Refresh data from OKX API

```bash
./cli.py refresh-cache
```

## Tagging Rules

Rules are defined in `rules.json`. Each rule specifies:
- `name`: tag name assigned to matching instruments
- `description`: human-readable description
- `match`: "all" (AND) or "any" (OR) for conditions
- `conditions`: array of `{field, op, value}` checks

Supported operators: `eq`, `neq`, `in`, `not_in`, `contains`, `not_contains`, `startswith`, `endswith`, `regex`

## Predefined Tags

| Tag | Description |
|-----|------------|
| stablecoin_pair | Both base and quote are stablecoins |
| um_perp | USDT/USDC-margined perpetual swap |
| cm_perp | Coin-margined perpetual swap |
| um_futures | USDT/USDC-margined expiry futures |
| cm_futures | Coin-margined expiry futures |
| btc_base | BTC as base currency |
| eth_base | ETH as base currency |
| usdt_quoted | Quoted in USDT |
| usdc_quoted | Quoted in USDC |
| spot | Spot trading pair |
| perp | Perpetual swap (any margin) |
| futures | Expiry futures (any margin) |
| not_live | Not in live state |

## Data Source

- **Instruments**: `GET /api/v5/public/instruments?instType={SPOT|SWAP|FUTURES}`

## Caching

- Cache dir: `cache/` (instruments.json)
- First `get-all`/`get` auto-fetches if no cache exists
- Use `refresh-cache` to force update

## Dependencies

- `click`, `httpx`, Python 3.10+
