# Price Limit Review

**Generated:** 2026-04-15T03:17:28.634309+00:00  
**Status:** critical  
**Instruments scanned:** 1544  
**EMA coverage:** 1544  

**Total issues found:** 18

## Rule 1: Buffer Too Tight
7 issue(s) found.

| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |
|---|---|---|---|
| BNT-EUR | -0.75% | -0.19% | warning |
| BNT-EUR | -0.75% | -0.19% | warning |
| OL-EUR | -38.49% | 1.63% | warning |
| BNT-USD | -3.36% | -1.34% | warning |
| BNT-USD | -3.36% | -1.34% | warning |
| SLP-USD | -0.16% | 0.45% | warning |
| BNT-USDC | -0.60% | 0.02% | warning |

## Rule 2: Asymmetric Basis
2 issue(s) found.

| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |
|---|---|---|---|
| BNT-USD | 3.41% | 5.0% | warning |
| T-USD | 1951.66% | 5.0% | warning |

## Rule 3: Asset-Type Consistency
9 issue(s) found.

| INSTRUMENT | CURRENT Y | CURRENT Z | EXPECTED Y | EXPECTED Z | STATUS |
|---|---|---|---|---|---|
| BTC-USD-260925 | 1.0% | 10.0% | 1% | 2% | warning |
| BTC-USD-261225 | 1.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260417 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260424 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260626 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260925 | 2.0% | 10.0% | 1% | 2% | warning |
| ETH-USD-260925 | 2.0% | 10.0% | 1% | 2% | warning |
| ETH-USD-261225 | 2.0% | 10.0% | 1% | 2% | warning |
| ETH-USDT-260626 | 1.0% | 10.0% | 1% | 2% | warning |

## Rule 4: Z Cap <= Y Cap
All instruments passed.
