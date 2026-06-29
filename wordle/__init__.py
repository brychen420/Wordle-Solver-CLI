"""Interactive entropy-based Wordle solver for the NYT Wordle game.

Strategy: maximize expected information (entropy) on early turns, with an
"endgame switch" that restricts guesses to actual possible answers when few
candidates remain or on the final turns -- maximizing the chance to win
rather than gathering information we'll never get to use.

Hint encoding (per digit, left to right):
    0 = gray   (letter not in the word, accounting for duplicates)
    1 = yellow (letter in the word, wrong position)
    2 = green  (correct letter, correct position)

Example: Seeing Yellow Gray Gray Green Yellow -> "10021".

This package is split by concern:
    config   -- constants and data-file paths
    scoring  -- score_int / score and pattern <-> string conversions
    patterns -- PatternTable (the precomputed feedback matrix)
    words    -- word-list loading and hint validation
    solver   -- the entropy strategy and the stateful Solver class
    cli      -- the interactive command-line interface
"""

from .config import (
    ALLOWED_FILE,
    ANSWERS_FILE,
    DATA_DIR,
    DEFAULT_OPENING,
    MAX_TURNS,
    NUM_PATTERNS,
    PATTERN_CACHE_FILE,
    PATTERN_CACHE_FULL_FILE,
    WORD_LEN,
)
from .patterns import PatternTable
from .scoring import code_to_str, score, score_int, str_to_code
from .solver import (
    HintResult,
    Solver,
    best_guess,
    entropy_of_guess,
    filter_candidates,
    rank_guesses,
)
from .words import load_pools, load_words, valid_code

__all__ = [
    # config
    "WORD_LEN",
    "MAX_TURNS",
    "DEFAULT_OPENING",
    "NUM_PATTERNS",
    "DATA_DIR",
    "ANSWERS_FILE",
    "ALLOWED_FILE",
    "PATTERN_CACHE_FILE",
    "PATTERN_CACHE_FULL_FILE",
    # scoring
    "score",
    "score_int",
    "code_to_str",
    "str_to_code",
    # patterns
    "PatternTable",
    # words
    "load_words",
    "load_pools",
    "valid_code",
    # solver
    "filter_candidates",
    "entropy_of_guess",
    "rank_guesses",
    "best_guess",
    "Solver",
    "HintResult",
]
