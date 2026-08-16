#!/usr/bin/env bash
# Run every regression test. From the repo root:  bot/tests/run.sh
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m tests.test_rotation
echo
python3 -m tests.test_wiring
