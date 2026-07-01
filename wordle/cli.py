"""Interactive command-line interface for the Wordle solver."""

import sys

from . import __doc__ as PACKAGE_DOC
from .config import MAX_TURNS, PATTERN_CACHE_FULL_FILE
from .solver import Solver
from .words import load_pools, valid_code

HELP = """Usage:
  python wordle_solver.py          run the interactive solver
  python wordle_solver.py --wide   widen the candidate pool to all ~13k allowed
                                   words (for rare answers outside the curated
                                   NYT list; guesses may be slightly weaker)

Tests, simulation, and benchmarking live in test_solver.py:
  python test_solver.py --test
  python test_solver.py --simulate WORD
  python test_solver.py --benchmark [N]
  python test_solver.py --recompute-opening"""


def _read_hint():
    """Prompt for a hint code until a valid one (or a quit) is entered.

    Returns the validated 5-char code, or None if the user chose to quit.
    """
    while True:
        try:
            raw = input("  Hint code (or 'q'): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            return None
        if raw in ("q", "quit", "exit"):
            print("bye.")
            return None
        if valid_code(raw):
            return raw
        print("  ! Enter exactly 5 digits, each 0/1/2.")


def play_interactive(wide=False):
    if wide:
        answers, guess_pool = load_pools(full_pool=True)
        solver = Solver(answers, guess_pool, cache_path=PATTERN_CACHE_FULL_FILE)
    else:
        solver = Solver()

    print("=" * 56)
    print(" Wordle solver  --  NYT edition")
    if wide:
        print(" [WIDE MODE] Candidate pool = all ~13k allowed words.")
        print(" Use this when the answer isn't a common NYT word; guesses")
        print(" may be a little weaker than in normal mode.")
    print(" Enter the hint after each guess as a 5-digit code:")
    print("   0 = gray (absent)   1 = yellow (wrong spot)   2 = green")
    print("   e.g. GUCKS -> Yellow Gray Gray Green Yellow -> 10021")
    print("   type 'q' to quit at any prompt.")
    print("=" * 56)

    for turn in range(1, MAX_TURNS + 1):
        guess = solver.suggest()
        print(f"\nGuess {turn}/{MAX_TURNS}:  >>> {guess.upper()} <<<")

        code = _read_hint()
        if code is None:
            return

        result = solver.apply_hint(code)

        if result.solved:
            print(f"\nSolved in {turn} guess(es). The word is {guess.upper()}.")
            return

        if result.empty:
            print("\n  ! No words match all hints so far -- even against the")
            print("    full allowed-word list. A previous hint likely has a")
            print("    typo; restart and double-check your hints.")
            return

        # The curated pool ran out but the answer may be an allowed-only word;
        # the solver just widened the search. Let the user know why the pool
        # (and the suggested guesses) suddenly changed.
        if result.widened:
            print("\n  (No curated NYT answer matched -- widening the search to")
            print("   the full ~13k allowed-word list. Guesses may be weaker.)")

        if result.exhausted:
            print("\n  Out of guesses. Remaining possibilities:")
            print("   ", ", ".join(sorted(result.candidates)[:20]))
            return

        # Otherwise, report progress and loop to the next suggested guess.
        print(f"  {result.remaining} possible answer(s) remain.")
        if result.remaining <= 15:
            print("    candidates:", ", ".join(sorted(result.candidates)))
        print("    top picks: " + ", ".join(
            f"{w.upper()} ({h:.2f} bits{', possible' if c else ''})"
            for h, c, w in result.ranked
        ))


def main(argv):
    # --wide is a modifier for interactive play; pull it out before parsing the
    # rest (mirrors how test_solver.main handles --full).
    wide = "--wide" in argv
    rest = [a for a in argv[1:] if a != "--wide"]
    if rest:
        cmd = rest[0]
        if cmd in ("-h", "--help"):
            print(PACKAGE_DOC)
            print(HELP)
            return
        print(f"unknown option: {cmd} (try --help)")
        sys.exit(2)
    play_interactive(wide=wide)
