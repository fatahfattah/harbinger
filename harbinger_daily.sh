#!/bin/bash
set -euo pipefail

HARBINGER_DIR="$HOME/Desktop/workspace/harbinger"
LOG_DIR="$HARBINGER_DIR/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/daily_$TIMESTAMP.log"

mkdir -p "$LOG_DIR"
cd "$HARBINGER_DIR"

{
  echo "=== Harbinger Daily Scan === $TIMESTAMP ==="
  echo ""

  echo "[1/2] Running full scan with LLM..."
  python3 main.py --universe sp600+ipos --top-n 30 2>&1
  SCAN_EXIT=$?
  echo "Scan exit code: $SCAN_EXIT"
  echo ""

  if [ $SCAN_EXIT -eq 0 ]; then
    echo "[2/2] Checking outcomes..."
    python3 -c "
import sys; sys.path.insert(0, '.')
from tracking.outcomes import check_outcomes
try:
    n = check_outcomes()
    print(f'Checked {n} outcomes')
except Exception as e:
    print(f'Outcomes check skipped: {e}')
" 2>&1
  fi

  echo ""
  echo "=== Done ==="

} >> "$LOG_FILE" 2>&1

# Cleanup old logs (keep 7 days)
find "$LOG_DIR" -name 'daily_*.log' -mtime +7 -delete 2>/dev/null || true
