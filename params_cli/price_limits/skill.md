# Price Limits CLI

Fetch, query, review and adjust OKX price limit parameters (X caps / Y caps / Z caps) and indicators like data of Premium/Basis/B.A spread/limitDn buffer/limitUp buffer. Can search by assets category as well, like TradFi, topcoin, etc.

## Command

```bash
./cli.py
```


### `params` — Query X/Y/Z cap parameters

```bash
./cli.py params                # all instruments
./cli.py params BTC-USDT-SWAP  # specific instrument
./cli.py params --type SWAP    # filter by type
./cli.py params --limit 10     # limit results
```

Returns: instId, instType, upper_X_cap, lower_X_cap, upper_Y_cap, lower_Y_cap, upper_Z_cap, lower_Z_cap

### `search` — Find instruments by keyword

```bash
./cli.py search "BTC USDT"
./cli.py search "ETH SWAP" --limit 5
```

Returns: instId, instType, productType

### `refresh-cache` — Refresh data from OKX API

```bash
./cli.py refresh-cache                              # full refresh
./cli.py refresh-cache BTC-USDT-SWAP ETH-USDT-SWAP  # specific instruments
./cli.py refresh-cache --type SWAP                   # by type
```

### `generate-adjustment` — Generate price limit adjustment CSV

```bash
./cli.py generate-adjustment '[{"symbol":"BTC-USDT-SWAP","z_upper":30,"y_lower":4}]'
```

- Refreshes each symbol's params live before generating
- Unspecified params keep their current values
- Outputs CSV to `output/` directory (split by spot vs perp format)
- Returns file path(s) in the JSON response

Override keys (percentage values): `x_upper`, `x_lower`, `y_upper`, `y_lower`, `z_upper`, `z_lower`

### `review` — Review price limit parameters

```bash
./cli.py review                                    # all instruments
./cli.py review BTC-USDT-SWAP ETH-USDT-SWAP        # specific instruments only
```

Returns three file paths (file_a, file_b, file_c). First call outputs workflow hints.

## Parameter Definitions

| Param | API fields | Meaning |
|-------|-----------|---------|
| X cap | lpX1/lpX2 | Initial Phase — ±X% on first tick |
| Y cap | lpY1/lpY2 | Inner Band — ±Y% deviation from index after opening |
| Z cap | lpZ1/lpZ2 | Outer Hard Cap — max ±Z% deviation from index |

## Data Sources

- **Instruments**: `GET /api/v5/public/instruments?instType={SPOT|SWAP|FUTURES}`
- **XYZ Caps**: `GET /priapi/v5/public/products?instType={type}&instId={ids}&includeType=1` (batched, max 50 per request)

## Caching

- Cache dir: `cache/` (instruments.json, xyz_cap_params.json)
- First call auto-fetches; subsequent calls use cache
- Use `refresh-cache` to force update

## Dependencies

- `click`, `httpx`, Python 3.10+
