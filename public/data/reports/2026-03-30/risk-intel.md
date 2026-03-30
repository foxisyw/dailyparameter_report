# Risk Intelligence

**Summary:** 4 alert types analyzed. 8 flagged alert(s) parsed. 5 suspicious user(s) highlighted.
**Source document:** 每日风控总结 - 2026-03-30 00:00:00 ~ 2026-03-30 23:59:59

## Suspicious Users
- 566647412895744 — T1 — CORE short, trade volume $475.2M vs equity $65.51 — ratio 7.25M:1. Extreme equity depletion. 12-year-old account reactivated for volatile event.
- 3148760259637248 — T1 — CORE short, equity $0.037 — total depletion from $1,522 first deposit (99.998% loss). $21.1M volume with near-zero residual.
- 564715436777472 — T1 — SOPH 2x short, trade volume $187.4M vs equity $10.84 — ratio 17.3M:1. Near-zero equity on isolated margin.
- 1638848958439424 — T1 — CORE long into -48.7% crash, equity $0.17. 12-year-old account with near-total depletion. Counter-trend position on isolated margin.
- 6727149969092608 — T1 — SOPH 2x short, equity $0.057. Region mismatch (CIS_MEA_LA registration but CN phone/KYC). 12-year-old account with 99.86% equity loss.

## Deep Profiles
- 566647412895744 — T4 — 12-year-old CN account with $475M cumulative trade volume but only $65 equity — trade/equity ratio 7.25Mx. Opened CORE-USDT-SWAP short on 2026-03-30 just after fresh deposit, consistent with equity depletion cycling.
- 3148760259637248 — T4 — 8-year CN account with $21.1M trade volume and zero equity ($0.037). CORE-USDT-SWAP short since 2026-03-24. Total equity depletion with active trading signals drain pattern.
- 564715436777472 — T3 — 9-year CN account with $187M trade volume and $10.84 equity — 17.3Mx ratio. 2x SOPH-USDT-SWAP short (isolated), latest opened 2026-03-30. Severe equity depletion.
- 1638848958439424 — T3 — 12-year CN account with $13.4M trade volume and $0.17 equity. CORE-USDT-SWAP long (isolated) opened 2026-03-29. Near-zero equity with active derivatives.
- 6727149969092608 — T3 — 12-year account in CIS_MEA_LA region but CN phone 86 — region mismatch. $8.6M volume, $0.057 equity. 2x SOPH short (cross). Region inconsistency plus severe depletion.