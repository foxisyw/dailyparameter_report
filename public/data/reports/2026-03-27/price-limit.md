# Price Limit Review

**Generated:** 2026-03-27T11:25:36.813694+00:00  
**Status:** critical  
**Instruments scanned:** 1496  
**EMA coverage:** 1496  

**Total issues found:** 15

## Rule 1: Buffer Too Tight
4 issue(s) found.

| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |
|---|---|---|---|
| DGB-USD | 1.15% | -0.07% | warning |
| SLP-USD | -2.14% | -1.17% | warning |
| SLP-USD | -2.14% | -1.17% | warning |
| ZEUS-USD | -0.04% | 1.13% | warning |

## Rule 2: Asymmetric Basis
1 issue(s) found.

| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |
|---|---|---|---|
| SLP-USD | 2.72% | 5.0% | warning |

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
