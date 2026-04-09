# Price Limit Review

**Generated:** 2026-04-09T02:57:31.121971+00:00  
**Status:** critical  
**Instruments scanned:** 1537  
**EMA coverage:** 1537  

**Total issues found:** 21

## Rule 1: Buffer Too Tight
7 issue(s) found.

| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |
|---|---|---|---|
| BNT-EUR | -0.60% | 0.12% | warning |
| BNT-USD | -5.33% | -0.52% | warning |
| BNT-USD | -5.33% | -0.52% | warning |
| DGB-USD | -0.49% | -0.44% | warning |
| DGB-USD | -0.49% | -0.44% | warning |
| SLP-USD | -0.03% | 0.58% | warning |
| BNT-USDC | -0.49% | 0.24% | warning |

## Rule 2: Asymmetric Basis
4 issue(s) found.

| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |
|---|---|---|---|
| BNT-USD | 4.94% | 5.0% | warning |
| CATI-USD | 137.19% | 5.0% | warning |
| ONT-USD | 36.07% | 5.0% | warning |
| T-USD | 796809.09% | 5.0% | warning |

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
