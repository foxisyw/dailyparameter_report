# Price Limit Review

**Generated:** 2026-04-13T02:28:08.590801+00:00  
**Status:** critical  
**Instruments scanned:** 1546  
**EMA coverage:** 1546  

**Total issues found:** 23

## Rule 1: Buffer Too Tight
10 issue(s) found.

| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |
|---|---|---|---|
| BNT-EUR | -1.58% | -1.13% | warning |
| BNT-EUR | -1.58% | -1.13% | warning |
| OFC-TRY | 1.58% | -0.44% | warning |
| PARTI-TRY | 1.94% | -0.56% | warning |
| BNT-USD | -3.82% | -1.80% | warning |
| BNT-USD | -3.82% | -1.80% | warning |
| SLP-USD | -0.58% | 0.35% | warning |
| BNT-USDC | -1.41% | -0.83% | warning |
| BNT-USDC | -1.41% | -0.83% | warning |
| CRWV-USDT-SWAP | 2.02% | -1.99% | warning |

## Rule 2: Asymmetric Basis
3 issue(s) found.

| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |
|---|---|---|---|
| BNT-USD | 3.46% | 5.0% | warning |
| CATI-USD | 2.61% | 5.0% | warning |
| T-USD | 14903.40% | 5.0% | warning |

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
