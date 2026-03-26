#!/bin/bash
# Full flow: review → deploy → wait → Lark
# Usage: ./run-and-deploy.sh

set -e
cd "$(dirname "$0")"

echo "=== Running daily parameter review ==="
python3 -m runner.main --no-lark

echo ""
echo "=== Committing and pushing to GitHub ==="
git add public/data/
if git diff --cached --quiet; then
  echo "No changes to commit."
else
  git commit -m "Daily review $(date +%Y-%m-%d) — local run with full EMA"
  git push
  echo ""
  echo "=== Waiting 90s for Vercel to deploy ==="
  sleep 90
fi

echo ""
echo "=== Sending Lark notification ==="
python3 -m runner.notify_lark

echo ""
echo "=== Done ==="
echo "Report: https://dailyparameter-report.vercel.app"
