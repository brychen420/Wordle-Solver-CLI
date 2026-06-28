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
from array import array
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
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


# --------------------------------------------------------------------------- #
# Core: feedback pattern                                                      #
# --------------------------------------------------------------------------- #
# Place values for packing 5 ternary digits little-endian (3**0 .. 3**4).
_POW3 = (1, 3, 9, 27, 81)


def score_int(guess, answer):
    """Return the feedback as an integer 0..242 (the single source of truth).

    Each tile contributes a ternary digit (0=gray, 1=yellow, 2=green), packed
    little-endian: code = sum(digit_i * 3**i). Duplicate letters use the
    standard two-pass rule -- greens are assigned first and consume a letter
    from the answer's pool; a non-green guess letter is yellow only if an
    unconsumed copy still remains.

    Hot path: uses a fixed 26-slot letter-count array instead of a Counter,
    since this is called ~30M times when building the pattern matrix.
    """
    code = 0
    # Count answer letters not matched green (indexed by letter a-z).
    counts = [0] * 26
    greens = [False] * WORD_LEN
    a0 = 97  # ord('a')
    for i in range(WORD_LEN):
        g = guess[i]
        a = answer[i]
        if g == a:
            greens[i] = True
            code += 2 * _POW3[i]
        else:
            counts[ord(a) - a0] += 1
    # Second pass: yellows (only if a copy is still available).
    for i in range(WORD_LEN):
        if greens[i]:
            continue
        gi = ord(guess[i]) - a0
        if counts[gi] > 0:
            code += _POW3[i]
            counts[gi] -= 1
    return code


def code_to_str(code):
    """Convert an integer pattern (0..242) back to its '0/1/2' string."""
    out = []
    for _ in range(WORD_LEN):
        out.append(str(code % 3))
        code //= 3
    return "".join(out)


def str_to_code(s):
    """Convert a '0/1/2' string to its integer pattern (0..242)."""
    code = 0
    for i, ch in enumerate(s):
        code += int(ch) * (3 ** i)
    return code


def score(guess, answer):
    """Return the 5-char '0/1/2' feedback code for `guess` against `answer`.

    Thin string wrapper over `score_int` so the integer scorer remains the
    one source of truth shared by filtering, entropy, and the interactive CLI.
    """
    return code_to_str(score_int(guess, answer))


# --------------------------------------------------------------------------- #
# Pattern table (precomputed feedback matrix)                                 #
# --------------------------------------------------------------------------- #
class PatternTable:
    """Caches feedback patterns so entropy never recomputes `score_int`.

    Conceptually it is the matrix `pattern[guess][answer]`, but rows are built
    lazily (only when a guess is first ranked) and stored as a byte array --
    each pattern fits in one byte (0..242). For a full-pool ranking, the first
    call materializes ~13k rows of ~2.3k bytes (~30 MB) once; every later
    ranking is pure array lookups + counting, which is the whole speedup.
    """

    def __init__(self, answers):
        # The answer axis is fixed: entropy is always measured over candidates,
        # which are a subset of the answer pool. We index answers by position.
        self.answers = list(answers)
        self.answer_id = {w: i for i, w in enumerate(self.answers)}
        self._rows = {}  # guess word -> array('B') of patterns vs each answer
        self._scratch = [0] * NUM_PATTERNS  # reusable bucket counts for entropy

    def row(self, guess):
        """Return (and cache) the pattern array for `guess` vs every answer."""
        r = self._rows.get(guess)
        if r is None:
            r = array("B", (score_int(guess, a) for a in self.answers))
            self._rows[guess] = r
        return r

    def entropy(self, guess, candidate_ids):
        """Expected information (bits) of `guess` over the given answer ids.

        Reuses one scratch bucket array across calls and clears only the slots
        actually touched, avoiding 243-slot allocation + full scan per guess
        (this method is the inner loop of full-pool ranking).
        """
        row = self.row(guess)
        counts = self._scratch
        seen = []
        for aid in candidate_ids:
            p = row[aid]
            if counts[p] == 0:
                seen.append(p)
            counts[p] += 1
        total = len(candidate_ids)
        h = 0.0
        for p in seen:
            c = counts[p]
            counts[p] = 0  # reset for next call
            prob = c / total
            h -= prob * math.log2(prob)
        return h


# --------------------------------------------------------------------------- #
# Filtering                                                                   #
# --------------------------------------------------------------------------- #
def filter_candidates(candidates, guess, code):
    """Keep only candidates consistent with seeing `code` for `guess`."""
    target = str_to_code(code)
    return [w for w in candidates if score_int(guess, w) == target]


# --------------------------------------------------------------------------- #
# Entropy                                                                     #
# --------------------------------------------------------------------------- #
def entropy_of_guess(guess, candidates):
    """Expected information (bits) of `guess` over the current candidates.

    Standalone (table-free) version, kept for direct use and tests.
    """
    buckets = defaultdict(int)
    for ans in candidates:
        buckets[score_int(guess, ans)] += 1
    total = len(candidates)
    h = 0.0
    for count in buckets.values():
        p = count / total
        h -= p * math.log2(p)
    return h


def rank_guesses(guess_pool, candidates, top=None, table=None):
    """Return guesses sorted by (entropy desc, is-candidate, alphabetical).

    Preferring a guess that is itself a possible answer breaks entropy ties in
    favor of a word that could win outright this turn.

    If `table` (a PatternTable over the answer pool) is supplied, entropy is
    computed from the precomputed matrix -- dramatically faster when ranking
    the full guess pool repeatedly. Without it, falls back to direct scoring.
    """
    candidate_set = set(candidates)
    scored = []
    if table is not None:
        candidate_ids = [table.answer_id[w] for w in candidates]
        for g in guess_pool:
            h = table.entropy(g, candidate_ids)
            scored.append((h, g in candidate_set, g))
    else:
        for g in guess_pool:
            h = entropy_of_guess(g, candidates)
            scored.append((h, g in candidate_set, g))
    # sort key: higher entropy first; among ties, prefer a real candidate,
    # then alphabetical for determinism.
    scored.sort(key=lambda t: (-t[0], not t[1], t[2]))
    if top is not None:
        scored = scored[:top]
    return scored  # list of (entropy, is_candidate, word)


# --------------------------------------------------------------------------- #
# Guess selection with the endgame switch                                     #
# --------------------------------------------------------------------------- #
def best_guess(guess_pool, candidates, turn, table=None):
    """Pick the next guess, applying the endgame switch.

    Returns (word, ranked_list) where ranked_list is the top few for display.
    Pass a PatternTable as `table` to use the precomputed feedback matrix.
    """
    n = len(candidates)

    # Trivially small candidate set: just guess one of them.
    if n <= 2:
        word = sorted(candidates)[0]
        ranked = rank_guesses(candidates, candidates, top=3, table=table)
        return word, ranked

    # Endgame: on the last turn, and on turn 5 when many candidates remain,
    # we only have room to win -- restrict guesses to actual candidates so the
    # guess has a real chance of being correct (and best splits for turn 6).
    last_turn = turn >= MAX_TURNS
    penultimate_with_many = turn == MAX_TURNS - 1 and n > 2
    if last_turn or penultimate_with_many:
        ranked = rank_guesses(candidates, candidates, top=3, table=table)
        return ranked[0][2], ranked

    # Early/mid game: full entropy over the entire guess pool.
    ranked = rank_guesses(guess_pool, candidates, top=3, table=table)
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
    table = PatternTable(answers)

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

        # Choose the next guess (first full-pool ranking builds the table).
        next_turn = turn + 1
        guess, ranked = best_guess(guess_pool, candidates, next_turn, table=table)

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
