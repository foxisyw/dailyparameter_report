# Risk Intelligence

**Summary:** 4 alert types analyzed. 10 flagged alert(s) parsed. 5 suspicious user(s) highlighted.
**Source document:** [PROD]Index Alarm - 2026-03-27 (00:00 - 23:59)

## Suspicious Users
- 1613911094865920 — T1 — 2x SHORT PROVE-USDT-SWAP (cross+isolated), trade/equity=1,648,982x, 权益$36.7，最近入金2026-03-25，在PROVE OI/限额超112%期间集中加仓
- 143730510437425152 — T1 — SHORT PROVE-USDT-SWAP isolated, trade/equity=741,000x, 权益$58.8，在PROVE OI危机期间建仓
- 567264575365120 — T1 — SHORT PROVE-USDT-SWAP isolated, trade/equity=437,000x, 权益$798, trade vol=$348.9M, 昨日(2026-03-26)入金后维持空头
- 615117494562816 — T1 — 2x SHORT PROVE-USDT-SWAP cross margin, 今日06:20&06:37主动开仓, trade/equity=77,341x, 权益$2,035
- 215133113058201600 — T1 — SHORT PROVE-USDT-SWAP isolated, trade/equity=26,867x, 权益$4,109, 昨日入金后在OI危机期间建仓

## Deep Profiles
- 1613911094865920 — T1 — 老账户（2018年注册）持有2个PROVE-USDT-SWAP空头仓位（同时持有cross+isolated），累计交易量$60.5M但当前权益仅$36.7，trade/equity比例达1,648,982x，典型权益极度耗损特征。账户于2026-03-25有最新入金记录，在PROVE OI/限额超过112%的背景下集中加仓空头，行为高度可疑。
- 143730510437425152 — T1 — 2018年注册H5端账户，累计交易量$43.5M，当前权益仅$58.8 USDT，trade/equity比率约741,000x。持有PROVE-USDT-SWAP空头（isolated），仓位于2026-03-26至2026-03-27建立，在PROVE OI异常期间加仓。权益极度耗损，属高风险操作账户。
- 567264575365120 — T1 — 2017年注册老账户（约8年历史），累计交易量高达$348.9M，但当前权益仅$798 USDT，trade/equity比率约437,000x。于2026-03-26（昨日）有最新入金，并持有PROVE-USDT-SWAP空头（isolated）。在PROVE OI超限背景下，昨日入金后建仓空头，行为高度可疑。
- 615117494562816 — T1 — 2017年注册最老账户之一（约8.5年），累计交易量$157.3M，当前权益仅$2,035 USDT，trade/equity约77,000x。持有2个PROVE-USDT-SWAP空头仓位（均为cross margin），2个仓位分别建立于同一天（2026-03-27早上6时段），属于当日主动加仓。在PROVE OI超过平台限额(112.65%)的情况下同时持有2个cross空头，风险极高。
- 215133113058201600 — T1 — 2018年注册账户，累计交易量$110.4M，当前权益$4,109 USDT，trade/equity约26,900x。于2026-03-26（昨日）有最新入金，持有PROVE-USDT-SWAP空头（isolated）建立于2026-03-26 10:05。昨日入金后立即在PROVE OI超限期间建立空头，结合极端trade/equity比率，属T1高风险账户。