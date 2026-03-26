#!/bin/bash
# Run full review locally (with complete EMA data), deploy to Vercel, send Lark.
# Usage: ./run-and-deploy.sh

set -e
cd "$(dirname "$0")"

echo "=== Running daily parameter review ==="
python3 -m runner.main

echo ""
echo "=== Committing and pushing to GitHub ==="
git add public/data/
git diff --cached --quiet && echo "No changes to commit." && exit 0
git commit -m "Daily review $(date +%Y-%m-%d) — local run with full EMA"
git push

echo ""
echo "=== Done. Vercel will auto-deploy in ~1 minute. ==="
echo "=== Lark notification sent. ==="
echo "=== Report: https://dailyparameter-report.vercel.app ==="
