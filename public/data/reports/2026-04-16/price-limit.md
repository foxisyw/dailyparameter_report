# Price Limit Review

**Generated:** 2026-04-16T07:11:08.392987+00:00  
**Status:** critical  
**Instruments scanned:** 1543  
**EMA coverage:** 1543  

**Total issues found:** 18

## Rule 1: Buffer Too Tight
8 issue(s) found.

| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |
|---|---|---|---|
| BNT-EUR | -0.52% | -0.35% | warning |
| BNT-EUR | -0.52% | -0.35% | warning |
| OL-EUR | -10.74% | 1.70% | warning |
| BNT-USD | -1.66% | -0.79% | warning |
| BNT-USD | -1.66% | -0.79% | warning |
| T-USD | -2.50% | 0.11% | warning |
| BNT-USDC | -0.37% | -0.13% | warning |
| BNT-USDC | -0.37% | -0.13% | warning |

## Rule 2: Asymmetric Basis
1 issue(s) found.

| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |
|---|---|---|---|
| T-USD | 611.94% | 5.0% | warning |

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
