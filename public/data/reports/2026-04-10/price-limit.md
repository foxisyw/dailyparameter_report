# Price Limit Review

**Generated:** 2026-04-11T06:51:59.257138+00:00  
**Status:** critical  
**Instruments scanned:** 1546  
**EMA coverage:** 1546  

**Total issues found:** 29

## Rule 1: Buffer Too Tight
13 issue(s) found.

| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |
|---|---|---|---|
| BNT-EUR | -1.50% | -0.52% | warning |
| BNT-EUR | -1.50% | -0.52% | warning |
| OFC-TRY | 1.41% | -10.60% | warning |
| PARTI-TRY | 3.43% | -11.91% | warning |
| BNT-USD | -5.44% | -1.01% | warning |
| BNT-USD | -5.44% | -1.01% | warning |
| DGB-USD | -0.04% | -0.04% | warning |
| DGB-USD | -0.04% | -0.04% | warning |
| BNT-USDT | -0.06% | 0.26% | warning |
| BNT-USDC | -1.40% | -0.36% | warning |
| BNT-USDC | -1.40% | -0.36% | warning |
| CRWV-USDT-SWAP | 2.16% | -22.27% | warning |
| OFC-USDT-SWAP | -1.57% | 3.02% | warning |

## Rule 2: Asymmetric Basis
5 issue(s) found.

| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |
|---|---|---|---|
| BNT-USD | 5.06% | 5.0% | warning |
| CATI-USD | 15.74% | 5.0% | warning |
| ONT-USD | 4.14% | 5.0% | warning |
| T-USD | 91555.46% | 5.0% | warning |
| OFC-USDT | 7.74% | 5.0% | warning |

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
2 issue(s) found.

| INSTRUMENT | Y CAP | Z CAP | STATUS |
|---|---|---|---|
| RAVE-USDT-SWAP | 2.0% | 2.0% | critical |
| RAVE-USDT-SWAP | 2.0% | 2.0% | critical |
