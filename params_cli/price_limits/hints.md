# default

Price Limits CLI — fetch, query, review and adjust OKX price limit parameters (X/Y/Z caps).

Available commands:
  ./cli.py params [INST_ID] [--type SWAP] [--limit 10]   — Query X/Y/Z cap parameters
  ./cli.py search "QUERY" [--limit 20]                    — Find instruments by keyword
  ./cli.py refresh-cache [INST_IDS...] [--type SWAP]      — Refresh data from OKX API
  ./cli.py generate-adjustment '<json>'                    — Generate adjustment CSV
  ./cli.py review [INST_IDS...]                            — Review price limit parameters
  ./cli.py realtime [--port 8765] [--stop]                 — Start/stop real-time server to refresh data of Premium/Basis/B.A spread/limitDn buffer/limitUp buffer
  ./cli.py ema [INST_IDS...] [--type SWAP]                 — Query Premium/Basis/B.A spread/buffer for limitDn or limitUp values

Run any command to get detailed hints on first use.
For every commands, run the command for first time, you get the hints only, run the command for second time you get the actual result.


# params

Fetch XYZ cap parameters for OKX instruments.

Usage:
  ./cli.py params                # all instruments
  ./cli.py params BTC-USDT       # specific instrument
  ./cli.py params --type SWAP    # filter by type (SPOT/SWAP/FUTURES)
  ./cli.py params --limit 10     # limit results

Output fields: instId, instType, upper_X_cap, lower_X_cap, upper_Y_cap, lower_Y_cap, upper_Z_cap, lower_Z_cap

Parameter definitions:
- X cap (lpX1/lpX2): Initial Phase — allows price to move ±X% on first tick
- Y cap (lpY1/lpY2): Inner Band — after opening, allows ±Y% deviation from index
- Z cap (lpZ1/lpZ2): Outer Hard Cap — maximum ±Z% deviation from index

Data source: OKX priapi products endpoint (cached locally after first fetch or refresh-cache).

# search

Search for instruments by keyword. Query is split into tokens on any non-alphanumeric character. All tokens must appear as substrings in the instrument's "{instId}-{instType}-{assetsType}" string (case-insensitive).

Usage:
  ./cli.py search "BTC USDT"         # find all BTC-USDT instruments
  ./cli.py search "ETH SWAP"         # find ETH perpetual swaps
  ./cli.py search "BTC-USDC SWAP"    # tokens: BTC, USDC, SWAP
  ./cli.py search "Meme"             # find all Meme-type instruments
  ./cli.py search "SOL" --limit 5    # limit results (default: 20)

Output fields: instId, instType, assetsType

Matches against instId, instType, and assetsType (from assets_types.md). Use this to find the exact instId before calling `params`.

# refreshCache

Refresh cached data from OKX API. Supports full, selective, or type-filtered refresh.

Usage:
  ./cli.py refresh-cache                              # full refresh (all instruments)
  ./cli.py refresh-cache BTC-USDT-SWAP ETH-USDT-SWAP  # specific instruments only
  ./cli.py refresh-cache --type SWAP                   # all instruments of a type

What it refreshes:
- Full: clears all cache, re-fetches instruments + xyz_cap_params
- Selective/type: fetches only specified instruments and merges into existing cache

Use when data appears stale or you need the latest price limit parameters.

# generateAdjustment

Generate a price limit adjustment CSV file from a JSON array of overrides.

Usage:
  ./cli.py generate-adjustment '[{"symbol":"BTC-USDT-SWAP","z_upper":30,"y_lower":4}]'

Each item in the array must have:
- symbol: instrument ID (e.g. "BTC-USDT-SWAP", "ETH-USDT")
- Optional override keys (percentage values):
  x_upper, x_lower, y_upper, y_lower, z_upper, z_lower

Behavior:
1. For each symbol, refreshes its params live from OKX API
2. Merges overrides onto current values (unspecified params keep current values)
3. Converts percentages to multipliers (e.g. z_upper=30 -> 1.3)
4. Writes CSV to output/ directory, split by spot vs perp format

Output CSV format matches OKX templates:
- Spot: Task Object, timeType, Effective Time, openMaxThresholdRate, ...
- Perp: Task Object, timeType, Effective Time, openUpperLimit, ...

# review

Review instruments' price limit parameters for improper configurations.

Usage:
  ./cli.py review                                    # all instruments
  ./cli.py review BTC-USDT-SWAP ETH-USDT-SWAP        # specific instruments only

This command outputs three file paths:
- **file_a**: Methodology and guidance document for reviews
- **file_b**: Python script path — named by hash of methodology content
- **file_c**: Latest params data & indicators data (CSV format)

Workflow after calling this command:
1. Read the review methodology file (file_a) to understand the task — **skip this step if you already have a specific adjustment task in mind**
2. Read file_c (CSV) to understand the current data structure
3. Generate a Python script at file_b path that implements the review rules from file_a or implements your own review logic if you have a specific adjustment task in mind
4. Run the review script, 
5. As long as any adjustment proposed, run: `./cli.py generate-adjustment '<json>'` to generate the file
6. Output the review summary, present findings, and output the path to the generated adjustment file 


Requires: cached xyz_cap_params.json and ema_state.json (if they don't exist, `./cli.py refresh-cache` first to build xyz_cap_params.json, run `./cli.py realtime` first to build EMA data).
