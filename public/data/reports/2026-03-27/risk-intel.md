# Risk Intelligence

**Summary:** 4 alert types analyzed. 6 flagged alert(s) parsed. 5 suspicious user(s) highlighted.
**Source document:** [PROD]Index Alarm - 2026-03-27 (00:00 - 23:59)

## Suspicious Users
- 573261155016704 — T1 — PROVE-USDT-SWAP SHORT cross, trade/equity=109,722,000x, equity=$2.63, deposit 2026-03-26
- 211349316600729600 — T1 — PROVE-USDT-SWAP LONG cross, trade/equity=45,266,000x, equity=$1.69, deposit 2026-03-26
- 25882071633371136 — T1 — PROVE-USDT-SWAP SHORT cross, trade/equity=16,152,000x, equity=$3.38, deposit 2026-03-26
- 8986687749369856 — T1 — PROVE-USDT-SWAP SHORT cross, trade/equity=1,240,843x, equity=$187.86, deposit 2026-03-26
- 213151826617438208 — T1 — PROVE-USDT-SWAP LONG cross, trade/equity=813,649x, equity=$217.42, deposit 2026-03-26

## Deep Profiles
- 573261155016704 — T1 — 2017-06-20 PC registration, CN (+86), KYC3 China. Trade volume $288.5M vs equity $2.63 yields an extreme trade/equity ratio of 109,722,000x. SHORT cross on PROVE-USDT-SWAP with last deposit 2026-03-26. Equity is virtually zero — classic shell-account pattern used for OI manipulation.
- 211349316600729600 — T1 — 2017-02-08 PC registration, CN (+86), KYC3 China. Trade volume $76.5M vs equity $1.69 — trade/equity ratio 45,266,000x. LONG cross on PROVE-USDT-SWAP, last deposit 2026-03-26. Only long holder among the top 5, but equity exhaustion is equally extreme.
- 25882071633371136 — T1 — 2016-07-05 APP registration, CN (+86), KYC3 China. Trade volume $54.6M vs equity $3.38 — trade/equity ratio 16,152,000x. SHORT cross on PROVE-USDT-SWAP, last deposit 2026-03-26. Oldest account in the cohort (~9.7 years) with near-zero equity.
- 8986687749369856 — T1 — 2018-02-28 H5 registration, CN (+86), KYC3 China. Trade volume $233.1M vs equity $187.86 — trade/equity ratio 1,240,843x. SHORT cross on PROVE-USDT-SWAP, last deposit 2026-03-26. Higher equity than top-3 but ratio still extremely abnormal.
- 213151826617438208 — T1 — 2018-03-05 PC registration, CN (+86), KYC3 China. Trade volume $176.9M vs equity $217.42 — trade/equity ratio 813,649x. LONG cross on PROVE-USDT-SWAP, last deposit 2026-03-26. Second long holder in top-5; may function as counter-party or wash component.