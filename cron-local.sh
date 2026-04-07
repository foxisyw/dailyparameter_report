#!/bin/bash
# Automated daily report — run by macOS launchd at 9:30 AM HKT
# This script ONLY writes a trigger file.
# The actual pipeline runs in your interactive Claude Code session (where MCPs are already connected).
# See: DAILY_REPORT_RUNBOOK.md for the full pipeline steps.

LOG="/tmp/paramreview-cron.log"
WORKDIR="/Users/stevensze/Documents/Daily Parameter Dashboard/Claude Code"
TRIGGER_DIR="$HOME/.paramreview"

echo "=== Daily Report Cron $(TZ=Asia/Hong_Kong date '+%Y-%m-%d %H:%M:%S') HKT ===" >> "$LOG" 2>&1

# Delete yesterday's stale input file so the loop condition passes
rm -f "$WORKDIR/runner/local/risk_intel_input.json"

# Write today's HKT date into the trigger file (uses ~/.paramreview/ to avoid macOS TCC)
# Your interactive Claude Code /loop watcher picks this up and runs the full pipeline
mkdir -p "$TRIGGER_DIR"
TZ=Asia/Hong_Kong date '+%Y-%m-%d' > "$TRIGGER_DIR/.cron_trigger"

echo "=== Trigger written: $(cat "$TRIGGER_DIR/.cron_trigger") ===" >> "$LOG" 2>&1
echo "=== Waiting for interactive Claude Code session to pick up the trigger ===" >> "$LOG" 2>&1
