# help

Index Price Deviation CLI — monitor index price quality across OKX instruments.

Available Workflows:
  Monitor:          server → (subscribe via WS/HTTP endpoints)
  QuickCheck:       snapshot [INDEX]
  ReviewComponents: markets COIN → generate-adjustment JSON

Available Methods:
  help                Show workflows and method list
  indexes             List all real OKX indexes (derived from instruments)
  server              Start/stop/check the index deviation monitor server
  snapshot            Quick one-shot fetch of current index quality (no server needed)
  markets             Fetch component alternatives for a coin from CoinGecko
  generate-adjustment Generate index_components CSV from selected components
  refresh-cache       Clear cached data and re-fetch

# indexes

List all real OKX indexes derived from SPOT and SWAP instruments.

Usage:
  python3 cli.py indexes                   # all indexes
  python3 cli.py indexes --coin BTC        # filter by base coin
  python3 cli.py indexes --limit 20        # limit results
  python3 cli.py indexes --refresh         # force refresh from OKX API

The index list is derived from actual OKX trading instruments (SPOT + SWAP),
not from the index-tickers API (which includes many unused indexes).

Rules:
  - Spot "BTC-USDT" → index "BTC-USDT"
  - Swap "TSLA-USDT-SWAP" → strip "-SWAP" → "TSLA-USDT"
  - Swap "BTC-USD_UM-SWAP" → strip "-SWAP" then "_UM" → "BTC-USD"

Cached for 24 hours. Use --refresh to force update.

# server

Start the index price deviation monitor server in background.

Usage:
  python3 cli.py server                     # start server (or show links if running)
  python3 cli.py server --port 8785         # custom port (HTTP on port+1)
  python3 cli.py server --interval 10       # polling interval in seconds
  python3 cli.py server --stop              # stop a running server

Behavior:
1. Checks if server is already running on the target port
2. If running → returns subscription links (WS + HTTP endpoints)
3. If not running → boots server in background, waits for first data cycle, returns links
4. With --stop → sends SIGTERM to running server process

The server streams only real OKX indexes (derived from instruments), with:
- Index prices and component exchange prices
- Quality metrics: component_count, avg_update_lag_s, max_deviation_pct, avg_deviation_pct, stale_components

HTTP endpoints (on port+1):
  GET /health              Server status
  GET /snapshot            All indexes with quality metrics
  GET /snapshot/{index}    Single index with full component breakdown
  GET /search?q=BTC        Filter indexes by keyword
  GET /alerts              Indexes with high deviation or stale components
  GET /alerts?threshold=1  Custom deviation threshold (default: 2%)

WebSocket (on port):
  Connect → receives periodic snapshot broadcasts
  Send {"type":"query","filter":"BTC"} → filtered response

# snapshot

One-shot fetch of index quality metrics without running a server.

Usage:
  python3 cli.py snapshot                    # all indexes
  python3 cli.py snapshot BTC-USDT           # specific index
  python3 cli.py snapshot --limit 10         # limit results

Output fields: index, idxPx, component_count, avg_deviation_pct, max_deviation_pct

# markets

Fetch component alternatives for a coin from CoinGecko.

Usage:
  python3 cli.py markets BTC                           # all supported markets for BTC
  python3 cli.py markets ETH --all                     # include unsupported exchanges
  python3 cli.py markets SOL --recommend               # recommended top-5 components
  python3 cli.py markets BTC --limit 10                # limit results

Returns available trading pairs across exchanges with quality metrics:
- volume, volume_usd: trading volume
- bid_ask_spread_pct: bid-ask spread percentage
- trust_score: CoinGecko trust score (green/yellow/red)
- exchange_score: our internal exchange quality score (5=best, 1=worst)
- is_anomaly, is_stale: data quality flags

The --recommend flag runs the two-round component selection algorithm:
1. Round 1: Pick best pair from each top-tier exchange (score ≥ 4)
2. Round 2: Fill remaining slots from all other qualified pairs

Data is cached for 6 hours. Use 'refresh-cache --markets COIN' to force update.

# generateAdjustment

Generate an index_components CSV file from selected components.

Usage:
  python3 cli.py generate-adjustment '[
    {"index":"BTC-USD","components":[
      {"exchange":"Binance","pair":"BTC-USDT"},
      {"exchange":"Coinbase","pair":"BTC-USD"},
      {"exchange":"OKX","pair":"BTC-USDT"}
    ]},
    {"index":"ETH-USDT","components":[
      {"exchange":"Binance","pair":"ETH-USDT"},
      {"exchange":"OKX","pair":"ETH-USDT"}
    ]}
  ]'

Input: JSON array where each item has:
  - index: the OKX index name (e.g. "BTC-USD", "ETH-USDT")
  - components: array of {exchange, pair} selections

Output CSV includes:
  - Automatic conversion type detection (0=no conversion, 1=multiply, 2=divide)
  - Conversion index derivation (e.g. USDT-USD for BTC/USDT → BTC-USD)
  - Tier value from exchange scores (4=top, 3=good, 2=acceptable)
  - Full template fields matching OKX index_components format

Workflow: Use 'markets COIN --recommend' to find best pairs, then pass selections here.

# refreshCache

Clear cached data and re-fetch from APIs.

Usage:
  python3 cli.py refresh-cache                  # refresh index list from OKX instruments
  python3 cli.py refresh-cache --markets BTC    # refresh CoinGecko markets for BTC
  python3 cli.py refresh-cache --markets all    # refresh markets for ALL coins (slow, ~6s/coin)
  python3 cli.py refresh-cache --clear-all      # wipe all cache files (no re-fetch)

Cache locations (in ./cache/):
  indexes.json               — OKX index list (24h TTL)
  coingecko_coins_list.json  — symbol→CoinGecko ID mapping (24h TTL)
  {COIN}_markets.json        — per-coin CoinGecko markets (6h TTL)

Note: --markets all fetches markets for every coin in the index list.
This calls CoinGecko API with rate limiting (~6s between calls + pagination),
so for 378 coins it takes ~40 minutes. Use for batch pre-warming or daily refresh.
