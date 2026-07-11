#!/usr/bin/env python3
"""Turn-by-turn driver for the wide-mode Wordle solver.

Two modes:

  Incremental (recommended) -- keeps the game on disk so each turn does exactly
  one ranking and applies only the newest hint:
      python wordle_next.py --new                # start a game, print SALET
      python wordle_next.py --hint 01010         # apply one hint, print next
      python wordle_next.py --hint 22222         # 22222 = solved

  Stateless replay (legacy) -- pass every hint so far and it rebuilds the game
  from scratch each call (simpler, but re-ranks all prior turns every time):
      python wordle_next.py                      # first guess, no hints
      python wordle_next.py 01010 01210          # next guess after 2 hints

Both drive the exact same solver, so the guesses are identical. Add --id NAME to
run more than one incremental game at once (defaults to "default").

Hint codes are 5 digits, one per tile: 0=gray, 1=yellow, 2=green.
"""

import argparse
import json
import os
import sys

from wordle.config import (DEFAULT_OPENING, MAX_TURNS, PATTERN_CACHE_FULL_FILE)
from wordle.solver import Solver
from wordle.words import load_pools, valid_code

# Per-game state lives here (git-ignored). Small JSON: the live candidate list,
# turn, last guess, hint history, and the widen flag -- everything needed to
# advance one turn without replaying the whole game.
_STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "games")


def _state_path(game_id):
    return os.path.join(_STATE_DIR, f"{game_id}.json")


def _save_state(game_id, solver):
    os.makedirs(_STATE_DIR, exist_ok=True)
    state = {
        "turn": solver.turn,
        "current_guess": solver.current_guess,
        "candidates": solver.candidates,
        "history": [[g, c] for g, c in solver.history],
        "widened": solver.widened,
    }
    with open(_state_path(game_id), "w", encoding="utf-8") as f:
        json.dump(state, f)


def _clear_state(game_id):
    try:
        os.remove(_state_path(game_id))
    except OSError:
        pass


def _fmt_ranked(ranked):
    return ", ".join(
        f"{w.upper()} ({h:.2f} bits{', possible' if c else ''})"
        for h, c, w in ranked
    )


def _print_next(solver, result):
    """Render the guess to play on the (now current) turn."""
    print(f"[WIDE MODE] Guess {solver.turn}/{MAX_TURNS}:  "
          f"{solver.suggest().upper()}")
    print(f"  {result.remaining} possible answer(s) remain.")
    if result.remaining <= 15:
        print("  candidates: " + ", ".join(sorted(result.candidates)))
    if result.ranked:
        print("  top picks: " + _fmt_ranked(result.ranked))
    print("\nPlay this word, then report the 5-digit hint code "
          "(0=gray, 1=yellow, 2=green; 22222 = solved).")


def _print_terminal(result, guess, turn):
    """Render a terminal outcome. Returns an exit code."""
    if result.solved:
        print(f"SOLVED in {turn} guess(es). The word is {guess.upper()}.")
        return 0
    if result.empty:
        print("NO MATCH: no allowed word is consistent with every hint. A "
              "previous hint code is probably wrong -- double-check them.")
        return 1
    if result.exhausted:
        print("OUT OF GUESSES. Remaining possibilities: "
              + ", ".join(sorted(result.candidates)[:20]))
        return 1
    return 0


def _new_solver():
    """Build a wide-mode solver, building/caching the matrix on first ever run."""
    answers, guess_pool = load_pools(full_pool=True)
    solver = Solver(answers, guess_pool, cache_path=PATTERN_CACHE_FULL_FILE)
    if not solver.table._rows:
        print("First run: building the full-pool matrix (~3.5 min); caching to "
              "disk so future turns are instant...", flush=True)
        solver.table.ensure_cached()
    return solver


# --------------------------------------------------------------------------- #
# Incremental mode                                                            #
# --------------------------------------------------------------------------- #
def cmd_new(game_id):
    """Start a game. Turn 1 is always the fixed opener, so skip loading the
    165 MB matrix entirely -- just record the starting state and print it."""
    answers, _ = load_pools(full_pool=True)
    # Seed state to match a fresh Solver's initial state without touching the
    # matrix: full candidate pool, opener queued, no history.
    os.makedirs(_STATE_DIR, exist_ok=True)
    state = {
        "turn": 1,
        "current_guess": DEFAULT_OPENING,
        "candidates": list(answers),
        "history": [],
        "widened": False,
    }
    with open(_state_path(game_id), "w", encoding="utf-8") as f:
        json.dump(state, f)
    print(f"[WIDE MODE] Guess 1/{MAX_TURNS}:  {DEFAULT_OPENING.upper()}")
    print("\nPlay this word, then report the 5-digit hint code "
          "(0=gray, 1=yellow, 2=green; 22222 = solved).")
    return 0


def cmd_hint(game_id, code):
    if not valid_code(code):
        print(f"ERROR: invalid hint code {code!r} -- need exactly 5 digits, "
              "each 0/1/2.")
        return 2
    path = _state_path(game_id)
    if not os.path.exists(path):
        print(f"ERROR: no game in progress (id={game_id!r}). Start one with "
              "`python wordle_next.py --new`.")
        return 2
    with open(path, encoding="utf-8") as f:
        state = json.load(f)

    solver = _new_solver()
    # Restore the game exactly where it left off, so apply_hint does one step
    # and one ranking -- no replay of earlier turns.
    solver.turn = state["turn"]
    solver.current_guess = state["current_guess"]
    solver.candidates = state["candidates"]
    solver.history = [tuple(pair) for pair in state["history"]]
    solver.widened = state["widened"]

    guess, turn = solver.current_guess, solver.turn
    result = solver.apply_hint(code)

    if result.widened:
        print("(Curated NYT answers exhausted -- widened to the full ~13k "
              "allowed pool. Guesses may be weaker.)")
    if result.terminal:
        _clear_state(game_id)
        return _print_terminal(result, guess, turn)

    _save_state(game_id, solver)
    _print_next(solver, result)
    return 0


# --------------------------------------------------------------------------- #
# Legacy stateless replay                                                     #
# --------------------------------------------------------------------------- #
def cmd_replay(codes):
    for c in codes:
        if not valid_code(c):
            print(f"ERROR: invalid hint code {c!r} -- need exactly 5 digits, "
                  "each 0/1/2.")
            return 2
    if not codes:
        # No hints yet: turn 1 is the fixed opener; no need to load the matrix.
        print(f"[WIDE MODE] Guess 1/{MAX_TURNS}:  {DEFAULT_OPENING.upper()}")
        print("\nPlay this word, then report the 5-digit hint code "
              "(0=gray, 1=yellow, 2=green; 22222 = solved).")
        return 0

    solver = _new_solver()
    result = None
    for i, code in enumerate(codes, start=1):
        guess = solver.suggest()
        result = solver.apply_hint(code)
        if result.widened:
            print("(Curated NYT answers exhausted -- widened to the full ~13k "
                  "allowed pool. Guesses may be weaker.)")
        if result.terminal:
            return _print_terminal(result, guess, i)
    _print_next(solver, result)
    return 0


def main(argv):
    parser = argparse.ArgumentParser(add_help=True, description=__doc__)
    parser.add_argument("--new", action="store_true",
                        help="start a new incremental game")
    parser.add_argument("--hint", metavar="CODE",
                        help="apply one hint to the incremental game")
    parser.add_argument("--id", default="default",
                        help="game id for concurrent incremental games")
    parser.add_argument("codes", nargs="*",
                        help="legacy stateless mode: all hint codes so far")
    args = parser.parse_args(argv[1:])

    if args.new and args.hint is not None:
        print("ERROR: use --new or --hint, not both.")
        return 2
    if (args.new or args.hint is not None) and args.codes:
        print("ERROR: don't mix positional codes with --new/--hint.")
        return 2

    if args.new:
        return cmd_new(args.id)
    if args.hint is not None:
        return cmd_hint(args.id, args.hint)
    return cmd_replay(args.codes)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
