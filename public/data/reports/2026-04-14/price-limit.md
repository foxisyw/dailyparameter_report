# Price Limit Review

**Generated:** 2026-04-14T02:58:31.984682+00:00  
**Status:** critical  
**Instruments scanned:** 1544  
**EMA coverage:** 1544  

**Total issues found:** 19

## Rule 1: Buffer Too Tight
7 issue(s) found.

| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |
|---|---|---|---|
| BNT-EUR | -0.77% | -0.36% | warning |
| BNT-EUR | -0.77% | -0.36% | warning |
| BNT-USD | -3.81% | -0.92% | warning |
| BNT-USD | -3.81% | -0.92% | warning |
| SLP-USD | -0.24% | 0.39% | warning |
| BNT-USDC | -0.68% | -0.15% | warning |
| BNT-USDC | -0.68% | -0.15% | warning |

## Rule 2: Asymmetric Basis
2 issue(s) found.

| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |
|---|---|---|---|
| BNT-USD | 3.87% | 5.0% | warning |
| T-USD | 5373.49% | 5.0% | warning |

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
1 issue(s) found.

| INSTRUMENT | Y CAP | Z CAP | STATUS |
|---|---|---|---|
| RAVE-USDT-SWAP | 2.0% | 2.0% | critical |
