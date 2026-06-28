#!/usr/bin/env python3
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
"""

import math
import os
import sys
from collections import Counter, defaultdict

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
ANSWERS_FILE = os.path.join(DATA_DIR, "answers.txt")
ALLOWED_FILE = os.path.join(DATA_DIR, "allowed.txt")

WORD_LEN = 5
MAX_TURNS = 6

# Cached best opening word (recompute via `test_solver.py --recompute-opening`).
# A fixed opener keeps turn 1 instant instead of scoring every guess x every
# answer on startup. "salet" is the entropy-optimal opener for this list.
DEFAULT_OPENING = "salet"


# --------------------------------------------------------------------------- #
# Core: feedback pattern                                                      #
# --------------------------------------------------------------------------- #
def score(guess, answer):
    """Return the 5-char '0/1/2' feedback code for `guess` against `answer`.

    Handles duplicate letters with the standard two-pass rule: greens are
    assigned first and consume a letter from the answer's pool; a non-green
    guess letter is yellow only if an unconsumed copy still remains.
    """
    result = ["0"] * WORD_LEN
    # Count answer letters that are not already matched green.
    remaining = Counter()
    for g, a in zip(guess, answer):
        if g == a:
            # green; consumed below, do not add to the yellow pool
            pass
        else:
            remaining[a] += 1
    # First pass: greens.
    for i, (g, a) in enumerate(zip(guess, answer)):
        if g == a:
            result[i] = "2"
    # Second pass: yellows (only if a copy is still available).
    for i, (g, a) in enumerate(zip(guess, answer)):
        if result[i] == "2":
            continue
        if remaining[g] > 0:
            result[i] = "1"
            remaining[g] -= 1
    return "".join(result)


# --------------------------------------------------------------------------- #
# Filtering                                                                   #
# --------------------------------------------------------------------------- #
def filter_candidates(candidates, guess, code):
    """Keep only candidates consistent with seeing `code` for `guess`."""
    return [w for w in candidates if score(guess, w) == code]


# --------------------------------------------------------------------------- #
# Entropy                                                                     #
# --------------------------------------------------------------------------- #
def entropy_of_guess(guess, candidates):
    """Expected information (bits) of `guess` over the current candidates."""
    buckets = defaultdict(int)
    for ans in candidates:
        buckets[score(guess, ans)] += 1
    total = len(candidates)
    h = 0.0
    for count in buckets.values():
        p = count / total
        h -= p * math.log2(p)
    return h


def rank_guesses(guess_pool, candidates, top=None):
    """Return guesses sorted by (entropy desc, is-candidate, alphabetical).

    Preferring a guess that is itself a possible answer breaks entropy ties in
    favor of a word that could win outright this turn.
    """
    candidate_set = set(candidates)
    scored = []
    for g in guess_pool:
        h = entropy_of_guess(g, candidates)
        # sort key: higher entropy first; among ties, prefer a real candidate,
        # then alphabetical for determinism.
        scored.append((h, g in candidate_set, g))
    scored.sort(key=lambda t: (-t[0], not t[1], t[2]))
    if top is not None:
        scored = scored[:top]
    return scored  # list of (entropy, is_candidate, word)


# --------------------------------------------------------------------------- #
# Guess selection with the endgame switch                                     #
# --------------------------------------------------------------------------- #
def best_guess(guess_pool, candidates, turn):
    """Pick the next guess, applying the endgame switch.

    Returns (word, ranked_list) where ranked_list is the top few for display.
    """
    n = len(candidates)

    # Trivially small candidate set: just guess one of them.
    if n <= 2:
        word = sorted(candidates)[0]
        ranked = rank_guesses(candidates, candidates, top=3)
        return word, ranked

    # Endgame: on the last turn, and on turn 5 when many candidates remain,
    # we only have room to win -- restrict guesses to actual candidates so the
    # guess has a real chance of being correct (and best splits for turn 6).
    last_turn = turn >= MAX_TURNS
    penultimate_with_many = turn == MAX_TURNS - 1 and n > 2
    if last_turn or penultimate_with_many:
        ranked = rank_guesses(candidates, candidates, top=3)
        return ranked[0][2], ranked

    # Early/mid game: full entropy over the entire guess pool.
    ranked = rank_guesses(guess_pool, candidates, top=3)
    return ranked[0][2], ranked


# --------------------------------------------------------------------------- #
# Word lists                                                                  #
# --------------------------------------------------------------------------- #
def load_words(path):
    with open(path, encoding="utf-8") as f:
        return [w.strip().lower() for w in f if w.strip()]


def load_pools():
    answers = load_words(ANSWERS_FILE)
    allowed_extra = load_words(ALLOWED_FILE)
    # Guess pool is the union; answers are the candidate (possible-answer) pool.
    guess_pool = sorted(set(answers) | set(allowed_extra))
    return answers, guess_pool


# --------------------------------------------------------------------------- #
# Input validation                                                            #
# --------------------------------------------------------------------------- #
def valid_code(code):
    return len(code) == WORD_LEN and all(c in "012" for c in code)


# --------------------------------------------------------------------------- #
# Interactive loop                                                            #
# --------------------------------------------------------------------------- #
def play_interactive():
    answers, guess_pool = load_pools()
    candidates = list(answers)

    print("=" * 56)
    print(" Wordle solver  --  NYT edition")
    print(" Enter the hint after each guess as a 5-digit code:")
    print("   0 = gray (absent)   1 = yellow (wrong spot)   2 = green")
    print("   e.g. GUCKS -> Yellow Gray Gray Green Yellow -> 10021")
    print("   type 'q' to quit at any prompt.")
    print("=" * 56)

    guess = DEFAULT_OPENING
    for turn in range(1, MAX_TURNS + 1):
        print(f"\nGuess {turn}/{MAX_TURNS}:  >>> {guess.upper()} <<<")

        # Read and validate the hint.
        while True:
            try:
                raw = input("  Hint code (or 'q'): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nbye.")
                return
            if raw in ("q", "quit", "exit"):
                print("bye.")
                return
            if valid_code(raw):
                code = raw
                break
            print("  ! Enter exactly 5 digits, each 0/1/2.")

        if code == "2" * WORD_LEN:
            print(f"\nSolved in {turn} guess(es). The word is {guess.upper()}.")
            return

        # Narrow the candidate set.
        candidates = filter_candidates(candidates, guess, code)

        if not candidates:
            print("\n  ! No words match all hints so far.")
            print("  ! A previous hint may have a typo, or the answer isn't in")
            print("    the bundled list. Restart and double-check your hints.")
            return

        if turn == MAX_TURNS:
            print("\n  Out of guesses. Remaining possibilities:")
            print("   ", ", ".join(sorted(candidates)[:20]))
            return

        # Choose the next guess.
        next_turn = turn + 1
        guess, ranked = best_guess(guess_pool, candidates, next_turn)

        print(f"  {len(candidates)} possible answer(s) remain.")
        if len(candidates) <= 15:
            print("    candidates:", ", ".join(sorted(candidates)))
        print("    top picks: " + ", ".join(
            f"{w.upper()} ({h:.2f} bits{', possible' if c else ''})"
            for h, c, w in ranked
        ))


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
def main(argv):
    if len(argv) >= 2:
        cmd = argv[1]
        if cmd in ("-h", "--help"):
            print(__doc__)
            print("Usage:")
            print("  python wordle_solver.py        run the interactive solver")
            print()
            print("Tests, simulation, and benchmarking live in test_solver.py:")
            print("  python test_solver.py --test")
            print("  python test_solver.py --simulate WORD")
            print("  python test_solver.py --benchmark [N]")
            print("  python test_solver.py --recompute-opening")
            return
        print(f"unknown option: {cmd} (try --help)")
        sys.exit(2)
    play_interactive()


if __name__ == "__main__":
    main(sys.argv)
