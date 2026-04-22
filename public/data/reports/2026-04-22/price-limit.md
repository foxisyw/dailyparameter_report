# Price Limit Review

**Generated:** 2026-04-22T02:43:36.471397+00:00  
**Status:** critical  
**Instruments scanned:** 1547  
**EMA coverage:** 1547  

**Total issues found:** 14

## Rule 1: Buffer Too Tight
3 issue(s) found.

| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |
|---|---|---|---|
| BNT-USD | -0.87% | 0.63% | warning |
| DGB-USD | -1.41% | -1.15% | warning |
| DGB-USD | -1.41% | -1.15% | warning |

## Rule 2: Asymmetric Basis
1 issue(s) found.

| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |
|---|---|---|---|
| TEST01-USDT-SWAP | 37778.03% | 30.0% | warning |

## Rule 3: Asset-Type Consistency
9 issue(s) found.

| INSTRUMENT | CURRENT Y | CURRENT Z | EXPECTED Y | EXPECTED Z | STATUS |
|---|---|---|---|---|---|
| BTC-USD-260925 | 1.0% | 10.0% | 1% | 2% | warning |
| BTC-USD-261225 | 1.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260424 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260501 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260626 | 2.0% | 10.0% | 1% | 2% | warning |
| BTC-USD_UM-260925 | 2.0% | 10.0% | 1% | 2% | warning |
| ETH-USD-260925 | 2.0% | 10.0% | 1% | 2% | warning |
| ETH-USD-261225 | 2.0% | 10.0% | 1% | 2% | warning |
| ETH-USDT-260626 | 1.0% | 10.0% | 1% | 2% | warning |

## Rule 4: Z Cap <= Y Cap
1 issue(s) found.

| INSTRUMENT | Y CAP | Z CAP | STATUS |
|---|---|---|---|
| RAVE-USDT-SWAP | 5.0% | 5.0% | critical |
