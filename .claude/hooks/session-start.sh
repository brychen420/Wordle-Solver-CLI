#!/bin/bash
# SessionStart hook: pre-warm the wide-mode (~13k) pattern-matrix cache so the
# /wordle-wide skill plays instantly instead of pausing ~3.5 min mid-game.
#
# Runs async: the session becomes interactive immediately and the build happens
# in the background. Idempotent: if the cache already exists it exits at once,
# so resumes and repeat startups cost nothing.
set -euo pipefail

# First stdout line tells Claude Code to start the session without waiting; the
# rest of this script keeps running in the background. Timeout generous enough
# for the ~3.5-4 min full-pool build on a cold container.
echo '{"async": true, "asyncTimeout": 600000}'

# Only relevant in the ephemeral web environment: every new container is a fresh
# clone with no cache. Local checkouts keep their cache across runs, so don't
# spend CPU rebuilding there.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

CACHE="data/patterns_full.bin"
if [ -f "$CACHE" ]; then
  echo "wide-mode matrix cache already present ($CACHE); nothing to build."
  exit 0
fi

echo "Prebuilding wide-mode matrix cache ($CACHE) in the background (~3.5 min)..."
python test_solver.py --build-matrix --wide
echo "wide-mode matrix cache ready ($CACHE)."
