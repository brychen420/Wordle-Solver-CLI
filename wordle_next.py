#!/usr/bin/env python3
"""Stateless one-turn driver for the wide-mode Wordle solver.

The interactive CLI (`python wordle_solver.py --wide`) holds a live process open
and reads hint codes from stdin in a loop. That's awkward to drive one turn at a
time from an assistant conversation. This helper does the same thing statelessly:
given the sequence of hint codes entered so far (one per guess already played),
it rebuilds the game by replaying them and prints the guess to play next.

Because the solver is deterministic and records its hint history, replaying the
codes reproduces the exact same state the live session would be in -- including
the automatic widen to the full allowed pool when curated candidates run out.

Usage:
  python wordle_next.py                 # first guess, no hints yet
  python wordle_next.py 01010           # next guess after 1 hint
  python wordle_next.py 01010 01210     # next guess after 2 hints

Each positional argument is a 5-digit hint code (0=gray, 1=yellow, 2=green) for
the guess this tool printed on the previous turn, in order.
"""

import sys

from wordle.config import MAX_TURNS, PATTERN_CACHE_FULL_FILE
from wordle.solver import Solver
from wordle.words import load_pools, valid_code


def _fmt_ranked(ranked):
    return ", ".join(
        f"{w.upper()} ({h:.2f} bits{', possible' if c else ''})"
        for h, c, w in ranked
    )


def main(argv):
    codes = argv[1:]
    for c in codes:
        if not valid_code(c):
            print(f"ERROR: invalid hint code {c!r} -- need exactly 5 digits, "
                  "each 0/1/2.")
            return 2

    answers, guess_pool = load_pools(full_pool=True)
    solver = Solver(answers, guess_pool, cache_path=PATTERN_CACHE_FULL_FILE)
    # Build+cache the full-pool matrix if this clone has none yet (~3.5 min the
    # first time; instant on every run after).
    if not solver.table._rows:
        print("First run: building the full-pool matrix (~3.5 min); caching to "
              "disk so future turns are instant...", flush=True)
        solver.table.ensure_cached()

    # Replay every hint recorded so far to reach the current turn.
    result = None
    for i, code in enumerate(codes, start=1):
        guess = solver.suggest()
        result = solver.apply_hint(code)

        if result.solved:
            print(f"SOLVED in {i} guess(es). The word is {guess.upper()}.")
            return 0
        if result.empty:
            print("NO MATCH: no allowed word is consistent with every hint. A "
                  "previous hint code is probably wrong -- double-check them.")
            return 1
        if result.widened:
            print("(Curated NYT answers exhausted -- widened to the full ~13k "
                  "allowed pool. Guesses may be weaker.)")
        if result.exhausted:
            print("OUT OF GUESSES. Remaining possibilities: "
                  + ", ".join(sorted(result.candidates)[:20]))
            return 1

    # Report the guess to play on the current turn.
    turn = solver.turn
    guess = solver.suggest()
    print(f"[WIDE MODE] Guess {turn}/{MAX_TURNS}:  {guess.upper()}")
    if result is not None:
        print(f"  {result.remaining} possible answer(s) remain.")
        if result.remaining <= 15:
            print("  candidates: " + ", ".join(sorted(result.candidates)))
        if result.ranked:
            print("  top picks: " + _fmt_ranked(result.ranked))
    print("\nPlay this word, then report the 5-digit hint code "
          "(0=gray, 1=yellow, 2=green; 22222 = solved).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
