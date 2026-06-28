"""Shared constants and data-file paths for the Wordle solver."""

import os

# Data files live in <project root>/data, one level above this package.
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(_PKG_DIR), "data")
ANSWERS_FILE = os.path.join(DATA_DIR, "answers.txt")
ALLOWED_FILE = os.path.join(DATA_DIR, "allowed.txt")

WORD_LEN = 5
MAX_TURNS = 6

# Cached best opening word (recompute via `test_solver.py --recompute-opening`).
# A fixed opener keeps turn 1 instant instead of scoring every guess x every
# answer on startup. "salet" is the entropy-optimal opener for this list.
DEFAULT_OPENING = "salet"

# Number of distinct feedback patterns: 3 states ^ 5 tiles.
NUM_PATTERNS = 3 ** WORD_LEN  # 243
