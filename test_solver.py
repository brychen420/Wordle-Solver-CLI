#!/usr/bin/env python3
"""Tests, simulation, and benchmarking for the Wordle solver.

Kept separate from the `wordle` package so the engine stays focused on the
solver and interactive CLI. This file imports the package and exercises it.

Usage:
    python test_solver.py                 # run self-checks (default)
    python test_solver.py --test          # run self-checks
    python test_solver.py --simulate WORD # auto-play against a known answer
    python test_solver.py --benchmark [N] # run all (or first N) answers
    python test_solver.py --recompute-opening  # find the best opening word
"""

import sys
from collections import Counter

from wordle import (
    DEFAULT_OPENING,
    MAX_TURNS,
    WORD_LEN,
    PatternTable,
    best_guess,
    filter_candidates,
    load_pools,
    rank_guesses,
    score,
)


# --------------------------------------------------------------------------- #
# Auto-play a single known answer                                             #
# --------------------------------------------------------------------------- #
def solve_for(answer, answers, guess_pool, verbose=False, table=None):
    """Auto-play the solver against a known answer. Return number of guesses
    used, or MAX_TURNS + 1 if it failed within the limit. Pass a shared
    PatternTable to reuse the precomputed feedback matrix across games."""
    candidates = list(answers)
    guess = DEFAULT_OPENING
    for turn in range(1, MAX_TURNS + 1):
        code = score(guess, answer)
        if verbose:
            print(f"  guess {turn}: {guess.upper()} -> {code}")
        if code == "2" * WORD_LEN:
            return turn
        candidates = filter_candidates(candidates, guess, code)
        if not candidates:
            return MAX_TURNS + 1
        if turn < MAX_TURNS:
            guess, _ = best_guess(guess_pool, candidates, turn + 1, table=table)
    return MAX_TURNS + 1


def simulate(answer):
    answers, guess_pool = load_pools()
    table = PatternTable(answers)
    answer = answer.strip().lower()
    if answer not in set(answers) | set(guess_pool):
        print(f"warning: '{answer}' is not in the word lists; simulating anyway.")
    print(f"Simulating against answer: {answer.upper()}")
    n = solve_for(answer, answers, guess_pool, verbose=True, table=table)
    if n <= MAX_TURNS:
        print(f"Solved in {n} guess(es).")
    else:
        print("Failed to solve within 6 guesses.")


def benchmark(limit=None):
    answers, guess_pool = load_pools()
    # One table shared across every game: the ~13k pattern rows are built once
    # (on the first game's turn-2 ranking) and reused for all the rest.
    table = PatternTable(answers)
    targets = answers if limit is None else answers[:limit]
    total = len(targets)
    dist = Counter()
    fails = []
    sum_guesses = 0
    for i, answer in enumerate(targets, 1):
        n = solve_for(answer, answers, guess_pool, table=table)
        dist[n] += 1
        if n <= MAX_TURNS:
            sum_guesses += n
        else:
            fails.append(answer)
        if i % 200 == 0:
            print(f"  ...{i}/{total}", flush=True)
    solved = total - len(fails)
    print("\n--- benchmark ---")
    print(f"answers tested : {total}")
    print(f"solved <= 6    : {solved} ({100 * solved / total:.2f}%)")
    avg = sum_guesses / solved if solved else 0
    print(f"avg guesses    : {avg:.4f} (over solved)")
    print("distribution   :")
    for g in range(1, MAX_TURNS + 1):
        print(f"   {g}: {dist.get(g, 0)}")
    if fails:
        print(f"   X (>6): {len(fails)}  e.g. {', '.join(fails[:10])}")


def recompute_opening():
    """Compute the entropy-optimal opening word over the full pools."""
    answers, guess_pool = load_pools()
    table = PatternTable(answers)
    print(f"Scoring {len(guess_pool)} guesses against {len(answers)} answers...")
    ranked = rank_guesses(guess_pool, answers, top=10, table=table)
    print("Top openers by entropy:")
    for h, c, w in ranked:
        print(f"   {w.upper()}: {h:.4f} bits{'  (possible answer)' if c else ''}")
    print(f"\nBest opener: {ranked[0][2].upper()} "
          f"(set DEFAULT_OPENING in wordle_solver.py accordingly)")


# --------------------------------------------------------------------------- #
# Self-tests                                                                   #
# --------------------------------------------------------------------------- #
def run_tests():
    failures = 0

    def check(cond, msg):
        nonlocal failures
        status = "ok  " if cond else "FAIL"
        if not cond:
            failures += 1
        print(f"  [{status}] {msg}")

    # Green/gray/yellow basics.
    check(score("crane", "crane") == "22222", "all green when guess == answer")
    check(score("aaaaa", "bbbbb") == "00000", "all gray when no overlap")

    # score() is a pure function -> deterministic.
    check(score("allol", "lolly") == score("allol", "lolly"),
          "score is deterministic")

    # Duplicate handling: guess "geese" vs answer "those".
    #   answer t-h-o-s-e. greens: s/s (idx3) and e/e (idx4).
    #   remaining non-green answer letters: t,h,o
    #   yellows for g,e,e at idx0,1,2: g absent->0; the only e was green->0,0.
    #   => "00022".
    check(score("geese", "those") == "00022",
          "duplicate e's handled (geese/those)")

    # The user's agreed example: GUCKS -> 10021 (Y G G G Y). Constructed answer
    # "sghkx" (s,g,h,k,x): K green at idx3; G present (idx1) -> yellow at idx0;
    # S present (idx0) -> yellow at idx4; U,C absent.
    check(score("gucks", "sghkx") == "10021",
          "user's example: GUCKS -> 10021 (Y G G G Y)")

    # A hand-built clean case for digit meaning:
    #   guess "abcde", answer "xbxxa": b green at idx1, a present at idx4
    #   (yellow at idx0), rest gray.
    check(score("abcde", "xbxxa") == "12000",
          "a yellow(1), b green(2), rest gray(0)")

    # Filtering keeps the true answer and shrinks (never grows) the set.
    answers, guess_pool = load_pools()
    sample = "crane"
    code = score("salet", sample)
    filtered = filter_candidates(answers, "salet", code)
    check(sample in filtered, "true answer survives filtering")
    check(len(filtered) <= len(answers), "filtering does not grow the set")

    # End-to-end: solver solves a handful of known answers within 6.
    for w in ["crane", "pizza", "fluff", "vivid", "mamma"]:
        if w in set(answers) | set(guess_pool):
            n = solve_for(w, answers, guess_pool)
            check(n <= MAX_TURNS, f"solves '{w}' in {n} guesses")

    print(f"\n{'all tests passed' if failures == 0 else f'{failures} test(s) FAILED'}")
    return failures == 0


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main(argv):
    cmd = argv[1] if len(argv) >= 2 else "--test"
    if cmd == "--test":
        sys.exit(0 if run_tests() else 1)
    if cmd == "--simulate":
        if len(argv) < 3:
            print("usage: test_solver.py --simulate WORD")
            sys.exit(2)
        simulate(argv[2])
        return
    if cmd == "--benchmark":
        limit = int(argv[2]) if len(argv) >= 3 else None
        benchmark(limit)
        return
    if cmd == "--recompute-opening":
        recompute_opening()
        return
    if cmd in ("-h", "--help"):
        print(__doc__)
        return
    print(f"unknown option: {cmd} (try --help)")
    sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
