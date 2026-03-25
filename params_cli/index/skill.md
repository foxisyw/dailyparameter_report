# Index Price Deviation CLI

Monitor OKX index price quality — component counts, update frequency, price deviation. Also fetch component alternatives from CoinGecko and generate index component adjustment files.

## Quick Start

```bash
cd /Users/oker/Documents/params_dashboard/params_cli/index
python3 cli.py help
```

## Workflows

### Monitor (real-time)
1. `python3 cli.py server` — start background monitor server
2. Subscribe to endpoints returned by the server command
3. `python3 cli.py server --stop` — stop the server

### Review Components
1. `python3 cli.py indexes --coin BTC` — list indexes for a coin
2. `python3 cli.py markets BTC --recommend` — get recommended component alternatives
3. `python3 cli.py generate-adjustment '[...]'` — generate CSV with selected components

### Quick Check
```bash
python3 cli.py snapshot BTC-USDT   # single index with component details
python3 cli.py snapshot             # all index tickers
```

## Hints

Every method shows hints on first call (STATUS: HINTS_ONLY). Call again within 5 minutes for actual results.

## Dependencies

- Python 3.10+
- httpx
- click
- websockets
