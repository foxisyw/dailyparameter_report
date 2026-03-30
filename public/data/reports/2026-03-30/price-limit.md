# Price Limit Review

**Generated:** 2026-03-30T10:11:12.005784+00:00  
**Status:** critical  
**Instruments scanned:** 1525  
**EMA coverage:** 1525  

**Total issues found:** 16

## Rule 1: Buffer Too Tight
3 issue(s) found.

| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |
|---|---|---|---|
| SLP-USD | -5.29% | -1.18% | warning |
| SLP-USD | -5.29% | -1.18% | warning |
| UXLINK-USD | -0.16% | 1.21% | warning |

## Rule 2: Asymmetric Basis
3 issue(s) found.

| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |
|---|---|---|---|
| SLP-USD | 4.47% | 5.0% | warning |
| UXLINK-USD | 3.20% | 5.0% | warning |
| UXLINK-USDT | 3.91% | 5.0% | warning |

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
