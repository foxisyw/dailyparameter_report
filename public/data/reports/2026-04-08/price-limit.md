# Price Limit Review

**Generated:** 2026-04-08T02:34:16.964329+00:00  
**Status:** critical  
**Instruments scanned:** 1536  
**EMA coverage:** 1536  

**Total issues found:** 20

## Rule 1: Buffer Too Tight
7 issue(s) found.

| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |
|---|---|---|---|
| BNT-EUR | -0.91% | 0.68% | warning |
| BNT-USD | -1.48% | 0.34% | warning |
| DGB-USD | -0.13% | -0.13% | warning |
| DGB-USD | -0.13% | -0.13% | warning |
| SLP-USD | -1.69% | -0.25% | warning |
| SLP-USD | -1.69% | -0.25% | warning |
| BNT-USDC | -0.87% | 0.72% | warning |

## Rule 2: Asymmetric Basis
3 issue(s) found.

| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |
|---|---|---|---|
| CATI-USD | 378.83% | 5.0% | warning |
| ONT-USD | 99.67% | 5.0% | warning |
| T-USD | 2200731.81% | 5.0% | warning |

## Rule 3: Asset-Type Consistency
10 issue(s) found.

| INSTRUMENT | CURRENT Y | CURRENT Z | EXPECTED Y | EXPECTED Z | STATUS |
|---|---|---|---|---|---|
| BTC-USD-260626 | 1.0% | 10.0% | 1% | 2% | warning |
| BTC-USD-260925 | 1.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260410 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260417 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260626 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260925 | 2.0% | 10.0% | 1% | 2% | warning |
| ETH-USD-260626 | 2.0% | 10.0% | 1% | 2% | warning |
| ETH-USD-260925 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USDT-260626 | 2.0% | 10.0% | 1% | 2% | warning |
| ETH-USDT-260626 | 1.0% | 10.0% | 1% | 2% | warning |

## Rule 4: Z Cap <= Y Cap
All instruments passed.
