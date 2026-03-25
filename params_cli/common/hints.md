# getAll

Get all OKX instruments with predefined tags applied (from local cache).

Usage:
  ./cli.py get-all                  # all instruments
  ./cli.py get-all --type SWAP      # filter by type (SPOT/SWAP/FUTURES)
  ./cli.py get-all --limit 10       # limit results
  ./cli.py get-all --live-only      # only live instruments

Output fields: instId, instType, productType, state, baseCcy, quoteCcy, settleCcy, listTime, tags

Tags are assigned by predefined rules in `rules.json`. Use `list-rules` to see all available tags.

Data source: local cache. Run `refresh-cache` first if cache is empty or stale.

# get

Get specified instruments with tags applied (from local cache).

Usage:
  ./cli.py get BTC-USDT-SWAP                    # single instrument
  ./cli.py get BTC-USDT-SWAP ETH-USDT-SWAP      # multiple instruments

Pass one or more instrument IDs as arguments. Missing instruments are reported in the `missing` field.

Output fields: instId, instType, productType, state, baseCcy, quoteCcy, settleCcy, listTime, tags

Data source: local cache. Run `refresh-cache` first if cache is empty or stale.

# filterByTag

Get all instruments that have a specific tag assigned.

Usage:
  ./cli.py filter-by-tag um_perp           # all USDT/USDC-margined perpetual swaps
  ./cli.py filter-by-tag btc_base          # all BTC-based instruments
  ./cli.py filter-by-tag stablecoin_pair   # stablecoin-to-stablecoin pairs
  ./cli.py filter-by-tag not_live          # instruments not currently live

Use `list-rules` to see all available tag names and their descriptions.

Data source: local cache. Run `refresh-cache` first if cache is empty or stale.

# listRules

List all predefined tagging rules with their names and descriptions.

Usage:
  ./cli.py list-rules

Each rule defines conditions that, when matched, assign a tag to an instrument. Rules are defined in `rules.json` and can be customized by editing that file.

Rule conditions support operators: eq, neq, in, not_in, contains, not_contains, startswith, endswith, regex.

# refreshCache

Refresh the local instrument cache from OKX public API.

Usage:
  ./cli.py refresh-cache

What it does:
1. Clears all cached data files
2. Fetches all instruments from OKX API (SPOT, SWAP, FUTURES)
3. Saves to local cache for subsequent queries

Run this when:
- First time using the tool (no cache exists yet)
- Data appears stale or you need the latest instrument list
- New instruments have been listed on OKX
