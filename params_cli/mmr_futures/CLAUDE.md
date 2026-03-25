# MMR Futures - Position Tier CLI

CLI tool for fetching futures/perp position tiers (leverage brackets, maintenance margin rates) from OKX, Binance, and Bybit.

## Setup

```bash
pip install -r requirements.txt
```

Binance API keys are in `.env` (auto-loaded via python-dotenv). OKX and Bybit endpoints are public.

## CLI Commands

### 1. List OKX instruments

```bash
python3 cli.py instruments                  # all perps (SWAP)
python3 cli.py instruments --type FUTURES   # dated futures
python3 cli.py instruments --json-output    # raw JSON
```

### 2. Get position tiers for a specific instrument

```bash
python3 cli.py tiers <exchange> <symbol> [--unit usd|coin|contracts] [--json-output]
```

Examples:
```bash
python3 cli.py tiers okx BTC-USDT-SWAP
python3 cli.py tiers okx ETH-USD-SWAP --unit contracts
python3 cli.py tiers binance BTCUSDT --unit usd
python3 cli.py tiers binance BTCUSD_PERP --unit coin
python3 cli.py tiers bybit BTCUSDT
python3 cli.py tiers bybit BTCUSD --unit coin
```

### 3. Refresh cache (fetch fresh data from exchange)

```bash
python3 cli.py refresh-cache <exchange> [--unit usd|coin|contracts]
```

Examples:
```bash
python3 cli.py refresh-cache okx
python3 cli.py refresh-cache binance --unit usd
python3 cli.py refresh-cache bybit --unit coin
```

### 4. Get ALL position tiers for an exchange

```bash
python3 cli.py all-tiers <exchange> [--unit usd|coin|contracts] [--json-output] [--limit N]
```

Examples:
```bash
python3 cli.py all-tiers okx --unit usd
python3 cli.py all-tiers bybit --unit coin --limit 5
python3 cli.py all-tiers binance --json-output
```

## Symbol formats

| Exchange | Linear (USDT) | Inverse (Coin) | Dated futures |
|----------|--------------|----------------|---------------|
| OKX | `BTC-USDT-SWAP` | `BTC-USD-SWAP` | `BTC-USDT-250328` |
| Binance | `BTCUSDT` | `BTCUSD_PERP` | `BTCUSD_250328` |
| Bybit | `BTCUSDT` | `BTCUSD` | — |

## Unit meanings

- `usd` — notional in USD/USDT (default). For OKX linear, this is base coin qty (multiply by price for USD). For Bybit linear / Binance USDS, it's USDT directly.
- `coin` — base coin quantity (BTC, ETH, etc.)
- `contracts` — raw contract count (mainly useful for OKX)

## Tier output fields

| Field | Description |
|-------|-------------|
| `tier` | Tier number |
| `min_size` / `max_size` | Position size range in the selected unit |
| `mmr` | Maintenance margin rate |
| `imr` | Initial margin rate |
| `max_leverage` | Maximum leverage at this tier |

## Caching

`tiers` and `all-tiers` commands read from local cache (`cache/` directory) by default. If no cache exists, they fetch from the API and cache the result. Use `refresh-cache` to force-fetch fresh data and update the cache.

Cache files are JSON stored in `cache/` (gitignored), keyed by `{exchange}_{symbol}_{unit}.json`.

## Python API (for programmatic use)

```python
from exchanges import okx_fetch_instruments
from tiers import get_position_tiers, get_all_position_tiers, refresh_cache

# List OKX perps
instruments = okx_fetch_instruments("SWAP")

# Single instrument tiers (reads cache if available)
tiers = get_position_tiers("bybit", "BTCUSDT", unit="usd")

# All tiers for an exchange (reads cache if available)
all_tiers = get_all_position_tiers("okx", unit="usd")  # returns {symbol: [tiers...]}

# Force refresh cache from API
refresh_cache("bybit", unit="usd")
```

## File structure

- `cli.py` — CLI entrypoint (click commands)
- `exchanges.py` — Low-level API clients (OKX, Binance, Bybit)
- `tiers.py` — Unified tier logic with unit conversion
- `config.py` — API key loading from `.env`
- `cache/` — Local JSON cache for tier data (gitignored)
