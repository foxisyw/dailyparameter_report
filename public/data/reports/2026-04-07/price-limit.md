# Price Limit Review

**Generated:** 2026-04-07T08:37:28.399532+00:00  
**Status:** critical  
**Instruments scanned:** 1536  
**EMA coverage:** 1536  

**Total issues found:** 18

## Rule 1: Buffer Too Tight
5 issue(s) found.

| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |
|---|---|---|---|
| DGB-USD | -0.35% | -0.37% | warning |
| DGB-USD | -0.35% | -0.37% | warning |
| RPL-USD | 1.45% | -0.13% | warning |
| SLP-USD | -4.18% | -1.60% | warning |
| SLP-USD | -4.18% | -1.60% | warning |

## Rule 2: Asymmetric Basis
3 issue(s) found.

| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |
|---|---|---|---|
| CATI-USD | 801.12% | 5.0% | warning |
| ONT-USD | 210.86% | 5.0% | warning |
| SLP-USD | 3.67% | 5.0% | warning |

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
