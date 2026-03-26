# Risk Intelligence Layer

- [x] Define the risk-intel generation boundary and fixture-backed local workflow
- [x] Implement `runner/generate_risk_intel.py` and supporting parsing/profile helpers
- [x] Add `runner/adapters/risk_intel.py` and wire it into `runner/main.py`
- [x] Extend adapter output schema for `render_variant`, `metric_cards`, risk-intel fields
- [x] Update frontend rendering for shared chapter shell and risk-intel drill-down UI
- [x] Update Lark notification summary for the new risk-intel chapter
- [x] Update `run-and-deploy.sh` for the new local-first workflow
- [x] Update `DESIGN_DOC.md` and `public/how-it-works.html`
- [x] Verify fixture generation, report generation, and frontend build

## Review

- `python3 -m runner.generate_risk_intel --fixture runner/fixtures/risk_intel_fixture.json` created a same-day `risk-intel.json` successfully during verification.
- `python3 -m runner.main --dry-run` on HKT `2026-03-27` loaded the generated risk-intel chapter and reported `risk-intel: critical`, `4` rule blocks, `3` suspicious users, `3` user profiles.
- `npm run build` completed successfully with the updated frontend and architecture page.
- The verification-only `public/data/reports/2026-03-27/risk-intel.json` file was removed after testing so fixture data is not left behind as published output.
