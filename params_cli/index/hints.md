# help

Index Price Deviation CLI — monitor index price quality across OKX instruments.

Available Workflows:
  Monitor:            server → ema [INDEX]
  QuickCheck:         snapshot [INDEX]
  SearchIndexes:      search QUERY
  InspectComponents:  components INDEX
  ReviewComponents:   markets COIN → generate-adjustment JSON

Available Methods:
  help                Show workflows and method list
  search              Search indexes by keyword (e.g. search "BTC USDT")
  indexes             List all real OKX indexes (derived from instruments)
  components          Query index component setup (exchange, weight, symbol)
  server              Start/stop/check the index deviation monitor server
  ema                 Query EMA of deviation metrics from server or cache
  snapshot            Quick one-shot fetch of current index quality (no server needed)
  markets             Fetch component alternatives for a coin from CoinGecko
  generate-adjustment Generate index_components CSV from selected components
  refresh-cache       Clear cached data and re-fetch

# search

Search indexes by query string. Multiple tokens are AND-matched.

Usage:
  python3 cli.py search BTC                  # all BTC indexes
  python3 cli.py search "BTC USDT"           # BTC-USDT index(es)
  python3 cli.py search "ETH USD" --limit 5  # ETH-USD indexes, max 5

Returns: index name, base coin, quote currency.

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
  GET /ema                 EMA of deviation metrics for all indexes
  GET /ema/{index}         EMA for a single index
  GET /ema?q=BTC           Filter EMA data by keyword
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

Fetch spot + perpetual markets for a coin from CoinMarketCap.

Usage:
  python3 cli.py markets BTC                             # all supported spot + perp markets
  python3 cli.py markets BTC --category spot             # spot markets only
  python3 cli.py markets BTC --category perpetual        # perpetual markets only
  python3 cli.py markets TSLA --category oracle          # TradFi oracle vendors only
  python3 cli.py markets ETH --all                       # include unsupported exchanges
  python3 cli.py markets SOL --recommend                 # recommended top-5 spot components
  python3 cli.py markets BTC --limit 10                  # limit results

Returns available markets across exchanges with quality metrics:
- price: last trade price
- volume_usd, volume_base: 24h trading volume
- depth_minus2_pct, depth_plus2_pct: ±2% order book depth in USD (spot)
- effective_liquidity: CMC liquidity score (spot)
- exchange_score: our internal exchange quality score (5=best, 1=worst)
- outlier_detected, price_excluded: CMC data quality flags

For TradFi assets, oracle vendors are also included (category=oracle):
- Pyth: Pyth Lazer real-time price feeds (equities, metals, FX)
- Ondo_TICKER: Ondo Global Markets tokenized equities
- dxFeed: dxFeed CFD/FOREX data feeds
- vendor_symbol: the vendor's native symbol identifier
- vendor_state: feed status (e.g. "stable")

Perpetual markets include additional fields:
- open_interest_usd: open interest in USD
- index_price: the exchange's index price
- index_basis: (mark - index) / index
- funding_rate: current funding rate

The --recommend flag picks best spot components:
1. Round 1: Pick best pair from each top-tier exchange (score ≥ 4)
2. Round 2: Fill remaining slots from all other qualified pairs

Data is cached for 6 hours. Use 'refresh-cache --markets COIN' to force update.

# generateAdjustment

Generate an index_components CSV file from selected components.

Usage (simple crypto):
  python3 cli.py generate-adjustment '[
    {"index":"BTC-USD","components":[
      {"exchange":"Binance","symbol":"BTC/USDT"},
      {"exchange":"Coinbase","symbol":"BTC/USD"},
      {"exchange":"OKX","symbol":"BTC/USDT"}
    ]}
  ]'

Usage (TradFi with oracle vendors):
  python3 cli.py generate-adjustment '[
    {"index":"TSLA-USDT","components":[
      {"exchange":"Pyth","symbol":"TSLA/USD","subscribeName":"Equity.US.TSLA/USD"},
      {"exchange":"Ondo_TICKER","symbol":"TSLA/USD"},
      {"exchange":"dxFeed","symbol":"TSLA/USD","subscribeName":"TSLA:USLF24"},
      {"exchange":"Binance_LINEAR_INDEX","symbol":"TSLA/USDT"},
      {"exchange":"Binance_LINEAR_PERPETUAL","symbol":"TSLA/USDT"},
      {"exchange":"OKX_PERPETUAL","symbol":"TSLA/USDT"}
    ]}
  ]'

Required per component:
  - exchange: canonical name (e.g. "Binance", "Pyth", "OKX_PERPETUAL")
  - symbol: trading pair in BASE/QUOTE format (e.g. "BTC/USDT")

Optional per component (auto-derived if omitted):
  - weight: component weight (empty = OKX auto-assigns)
  - subscribeName: vendor feed ID (e.g. "Equity.US.TSLA/USD" for Pyth, "TSLA:USLF24" for dxFeed)
  - emaLagMs: EMA lag in milliseconds (default 0)
  - priceMultiple: price multiplier (default 1)
  - conversionType: 0=none, 1=multiply, 2=divide (auto-derived from symbol vs index quote)
  - conversionIndex: e.g. "USDT-USD" (auto-derived)
  - tier: tier value (auto-derived from exchange score)
  - uniqueExchangeAlias: exchange alias
  - conversionCheck: "TRUE" or "FALSE" (default "TRUE")
  - sharesMultiplierSource / sharesMultiplierToken / sharesMultiplierBenchmark: auto-derived for
    Ondo token pairs (base ending in "ON", e.g. TSLAON → Ondo/TSLA/1.001)
  - chainId, tokenAddress, poolAddress, baseTokenAddress, quoteTokenAddress: on-chain fields

Output CSV matches the OKX index_components template format with all 20 columns.

Workflow: Use 'markets COIN' to find alternatives, then pass selections here.

# refreshCache

Clear cached data and re-fetch from APIs.

Usage:
  python3 cli.py refresh-cache                  # refresh index list from OKX instruments
  python3 cli.py refresh-cache --markets BTC    # refresh CoinGecko markets for BTC
  python3 cli.py refresh-cache --markets all    # refresh markets for ALL coins (slow, ~6s/coin)
  python3 cli.py refresh-cache --clear-all      # wipe all cache files (no re-fetch)

Cache locations (in ./cache/):
  indexes.json               — OKX index list (24h TTL)
  cmc_coin_map.json          — symbol→CoinMarketCap slug mapping (24h TTL)
  {COIN}_markets.json        — per-coin CMC spot + perpetual markets (6h TTL)

Note: --markets all fetches markets for every coin in the index list.
CMC is faster than CoinGecko (no strict rate limiting), but batch refresh
for all coins still takes several minutes due to pagination.

# ema

Query EMA (exponential moving average) of deviation metrics from the running server.

Usage:
  python3 cli.py ema                          # all indexes
  python3 cli.py ema BTC-USDT                 # specific index(es)
  python3 cli.py ema BTC-USDT ETH-USDT        # multiple indexes

The server tracks EMA (τ=24h) of these metrics per index:
  - avg_deviation: average component-to-index price deviation (%)
  - max_deviation: maximum component deviation (%)
  - avg_update_lag: average seconds since last component price change
  - stale_ratio: percentage of components considered stale (>60s no update)

Falls back to cached EMA state on disk if the server is not running.
Start the server first: python3 cli.py server

# components

Query current index component configuration from OKX.

Usage:
  python3 cli.py components BTC-USDT            # single index — full details
  python3 cli.py components --coin ETH           # all ETH-* indexes
  python3 cli.py components --limit 5            # first 5 indexes

Returns per component: exchange, symbol, weight, symPx, cnvPx.

For a single index, returns detailed component data including current prices.
For batch queries, returns a summary per index with component list.

Note: batch queries call OKX API per-index with rate limiting (~0.15s between calls).

# review

Review index component quality for problematic configurations.

Usage:
  ./cli.py review                                    # all indexes (auto-filtered, batched)
  ./cli.py review BTC-USDT ETH-USDT                  # specific indexes only
  ./cli.py review --type TradFi                       # only TradFi indexes
  ./cli.py review --type Altcoins --batch 20          # Altcoins, 20 per batch
  ./cli.py review --type Altcoins --offset 20         # next 20 Altcoins

Options:
  --batch N     Max indexes per output (default 30, 0=unlimited)
  --offset N    Skip first N flagged indexes (for pagination)
  --type TYPE   Filter by asset type: TradFi, Topcoins, Fiat, Altcoins

When running a full review (no specific index IDs), healthy Topcoins and Fiat indexes
are automatically skipped. Only indexes with potential issues are included.

Output includes `next_offset` and `remaining` when more batches are available.
Call again with `--offset <next_offset>` to continue.

This command outputs three file paths:
- **file_a**: Methodology and review rules document
- **file_b**: Python script path (placeholder for agent-generated review script)
- **file_c**: Index quality data with EMA indicators (JSON)

Workflow:
1. Read file_a (methodology) to understand the review rules
2. Read file_c (JSON) — contains only flagged indexes with components + alternatives
3. Apply rules from methodology, output review summary per index
4. For indexes needing changes: `./cli.py generate-adjustment '<json>'`
5. If `remaining > 0` in output: run review again with `--offset` for next batch

Requires: running server with EMA data (run `./cli.py server` first).
