# Discounts CLI — Collateral Ratio / Discount Rate Tool

Fetch and query collateral discount-rate tiers from **OKX**, **Binance**, and **Bybit**.

## Location

```
/Users/oker/Documents/params_cli/discounts/discounts_cli.py
```

## CLI Usage

```bash
python3 discounts_cli.py <command> [options]
```

### Commands

#### `list` — List all collateral-eligible coins on an exchange

```bash
python3 discounts_cli.py list <exchange>
```

- `exchange`: `okx` | `binance` | `bybit`
- Output: sorted list of coin symbols printed to stdout.

#### `tiers` — Get discount tiers for a specific coin on a specific exchange

```bash
python3 discounts_cli.py tiers <exchange> <coin> [--terms usd|coin|native]
```

- `exchange`: `okx` | `binance` | `bybit`
- `coin`: symbol (e.g. `BTC`, `ETH`, `SOL`)
- `--terms`: how tier caps are denominated
  - `native` (default) — keeps the exchange's native unit (OKX/Bybit = coin qty, Binance = USD)
  - `usd` — USD denomination label
  - `coin` — coin quantity label
- Output: JSON object `{"coin", "terms", "tiers": [{"cap", "ratio"}, ...]}`. `cap` is the upper bound of the tier; `"unlimited"` means no cap. `ratio` is the collateral/discount rate (0–1).
- Exits with code 1 if the coin is not found.

#### `all` — Get tiers for every collateral coin on an exchange

```bash
python3 discounts_cli.py all <exchange> [--terms usd|coin|native]
```

- Same options as `tiers` but returns a JSON array of all coins.

#### `refresh-cache` — Re-fetch data from APIs and update local cache

```bash
python3 discounts_cli.py refresh-cache [exchange]
```

- `exchange`: `okx` | `binance` | `bybit` | `all` (default: `all`)
- Forces a fresh API call and writes the result to `cache/<exchange>.json`.
- Use this before running queries when you need up-to-date data.

## Caching Behavior

All fetch operations read from local cache files in the `cache/` directory by default:
- **First call**: If no cache exists for an exchange, the CLI fetches from the API and caches the result automatically.
- **Subsequent calls**: Data is served from the local cache (no API call).
- **To get fresh data**: Run `refresh-cache` to re-fetch from APIs and update the cache.

Cache files are stored at `cache/<exchange>.json` (e.g. `cache/okx.json`).

## Python API (importable)

```python
from discounts_cli import (
    fetch_all_collateral_coins,
    get_collateral_tiers,
    get_all_collateral_tiers,
    refresh_cache,
)
```

| Function | Signature | Returns |
|---|---|---|
| `fetch_all_collateral_coins` | `(exchange: str) -> list[str]` | Sorted list of coin symbols |
| `get_collateral_tiers` | `(exchange: str, coin: str, terms: str = "native") -> dict \| None` | `{"coin", "terms", "tiers": [...]}` or `None` |
| `get_all_collateral_tiers` | `(exchange: str, terms: str = "native") -> list[dict]` | List of `{"coin", "terms", "tiers": [...]}` |
| `refresh_cache` | `(exchange: str \| None = None) -> dict` | Re-fetches from API & updates cache. Pass `None` to refresh all exchanges. Returns `{exchange: True}` for each refreshed. |

## Tier cap denomination

| Exchange | Native cap unit | Notes |
|---|---|---|
| OKX | Coin quantity | `maxAmt` from API is coin-denominated |
| Binance | USD | `tierCap` from API is USD-denominated |
| Bybit | Coin quantity | `maxQty` from API is coin-denominated |

## Auth

- **OKX / Bybit**: Public endpoints, no auth required.
- **Binance**: Requires API key + HMAC signature. Credentials are embedded in `discounts_cli.py`.

## Dependencies

- `requests` (HTTP client)
- Python 3.10+
