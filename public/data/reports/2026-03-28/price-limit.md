# Price Limit Review

**Generated:** 2026-03-28T05:52:29.582197+00:00  
**Status:** critical  
**Instruments scanned:** 1496  
**EMA coverage:** 1496  

**Total issues found:** 17

## Rule 1: Buffer Too Tight
6 issue(s) found.

| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |
|---|---|---|---|
| DGB-USD | 0.20% | -0.15% | warning |
| SLP-USD | -4.90% | -1.00% | warning |
| SLP-USD | -4.90% | -1.00% | warning |
| T-USD | -0.16% | -0.61% | warning |
| T-USD | -0.16% | -0.61% | warning |
| T-USDC | -1.37% | 0.74% | warning |

## Rule 2: Asymmetric Basis
1 issue(s) found.

| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |
|---|---|---|---|
| SLP-USD | 4.00% | 5.0% | warning |

## Rule 3: Asset-Type Consistency
10 issue(s) found.

| INSTRUMENT | CURRENT Y | CURRENT Z | EXPECTED Y | EXPECTED Z | STATUS |
|---|---|---|---|---|---|
| BTC-USD-260626 | 1.0% | 10.0% | 1% | 2% | warning |
| BTC-USD-260925 | 1.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260403 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260410 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260626 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260925 | 2.0% | 10.0% | 1% | 2% | warning |
| ETH-USD-260626 | 2.0% | 10.0% | 1% | 2% | warning |
| ETH-USD-260925 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USDT-260626 | 2.0% | 10.0% | 1% | 2% | warning |
| ETH-USDT-260626 | 1.0% | 10.0% | 1% | 2% | warning |

## Rule 4: Z Cap <= Y Cap
All instruments passed.
