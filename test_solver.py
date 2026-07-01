#!/usr/bin/env python3
"""Tests, simulation, and benchmarking for the Wordle solver.

Kept separate from the `wordle` package so the engine stays focused on the
solver and interactive CLI. This file imports the package and exercises it.

Usage:
    python test_solver.py                 # run self-checks (default)
    python test_solver.py --test          # run self-checks
    python test_solver.py --simulate WORD # auto-play against a known answer
    python test_solver.py --simulate WORD --wide  # start against the full pool
    python test_solver.py --benchmark [N] # run all (or first N) answers
    python test_solver.py --recompute-opening  # find the best opening word
    python test_solver.py --build-matrix  # cache the pattern matrix to disk
    python test_solver.py --build-matrix --wide  # cache the full-pool matrix
    python test_solver.py --benchmark --wide     # benchmark the full-pool variant
"""

import sys
from collections import Counter

from wordle import (
    DEFAULT_OPENING,
    MAX_TURNS,
    PATTERN_CACHE_FILE,
    PATTERN_CACHE_FULL_FILE,
    WORD_LEN,
    PatternTable,
    Solver,
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


def simulate(answer, wide=False):
    """Auto-play the real Solver against a known answer, printing each turn.

    Drives the stateful `Solver` (not the standalone `solve_for`) so the run
    reflects exactly what the interactive CLI would do -- including the
    automatic mid-game widening to the full allowed pool when the curated
    candidates run out. With `wide=True`, the solver starts against the full
    ~13k pool from turn 1 (like `wordle_solver.py --wide`).
    """
    answer = answer.strip().lower()

    if wide:
        answers, guess_pool = load_pools(full_pool=True)
        solver = Solver(answers, guess_pool, cache_path=PATTERN_CACHE_FULL_FILE)
    else:
        answers, guess_pool = load_pools()
        solver = Solver(answers, guess_pool)

    if answer not in set(answers) | set(guess_pool):
        print(f"warning: '{answer}' is not in the word lists; simulating anyway.")
    mode = " (wide pool)" if wide else ""
    print(f"Simulating against answer: {answer.upper()}{mode}")

    solved_in = None
    for turn in range(1, MAX_TURNS + 1):
        guess = solver.suggest()
        code = score(guess, answer)
        print(f"  guess {turn}: {guess.upper()} -> {code}")
        if code == "2" * WORD_LEN:
            solved_in = turn
            break
        result = solver.apply_hint(code)
        if result.widened:
            print("  [widening the search to the full allowed-word list]")
        if result.empty:
            print("  ! no words match the hints, even in the full pool "
                  "(inconsistent hints?)")
            break
        if result.exhausted:
            break

    if solved_in is not None:
        print(f"Solved in {solved_in} guess(es).")
    else:
        print("Failed to solve within 6 guesses.")


def benchmark(limit=None, full_pool=False):
    """Benchmark the solver over its target pool.

    In normal mode the candidate pool and the targets are the curated ~2.3k NYT
    answers. With `full_pool`, both are widened to the entire ~13k guess pool:
    the solver both searches over and is graded on every allowed word, treating
    any of them as a possible hidden answer -- a much harder, less-informed
    stress test than realistic NYT play.
    """
    answers, guess_pool = load_pools(full_pool=full_pool)
    cache = PATTERN_CACHE_FULL_FILE if full_pool else PATTERN_CACHE_FILE
    # One table shared across every game. Passing guess_pool + cache_path lets
    # it load the right on-disk cache if present (skipping the build); otherwise
    # rows are built once on the first game's turn-2 ranking and reused.
    table = PatternTable(answers, guess_pool, cache_path=cache)
    if not table._rows:  # cache miss -> warn, since the full build is slow
        print(f"(no cache at {cache}; building rows lazily -- this is slow)")

    # Targets are every word the solver treats as possible: the ~13k guess pool
    # in full-pool mode, the curated ~2.3k answers otherwise.
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
    print(f"mode           : {'FULL POOL (~13k candidates)' if full_pool else 'normal (curated answers)'}")
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
    # Pass guess_pool so the on-disk matrix cache is used if available.
    table = PatternTable(answers, guess_pool)
    print(f"Scoring {len(guess_pool)} guesses against {len(answers)} answers...")
    ranked = rank_guesses(guess_pool, answers, top=10, table=table)
    print("Top openers by entropy:")
    for h, c, w in ranked:
        print(f"   {w.upper()}: {h:.4f} bits{'  (possible answer)' if c else ''}")
    print(f"\nBest opener: {ranked[0][2].upper()} "
          f"(set DEFAULT_OPENING in wordle_solver.py accordingly)")


def build_matrix(full_pool=False):
    """Precompute the pattern matrix and cache it to disk.

    Run this once; afterwards the solver loads the cache in well under a second
    instead of spending ~35s (normal) or ~3.5min (full pool) building it.

    With `full_pool`, the answer axis is the entire ~13k guess pool, producing
    a ~165 MB matrix saved to a separate file.
    """
    import os

    answers, guess_pool = load_pools(full_pool=full_pool)
    path = PATTERN_CACHE_FULL_FILE if full_pool else PATTERN_CACHE_FILE
    table = PatternTable(answers, guess_pool, use_cache=False, cache_path=path)
    approx = "~165 MB" if full_pool else "~30 MB"
    print(f"Building {len(guess_pool)} x {len(answers)} pattern matrix "
          f"({approx})...")

    def progress(done, total):
        print(f"  ...{done}/{total}", flush=True)

    table.build_all(progress=progress)
    table.save_cache(path)
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"Saved cache to {path} ({size_mb:.1f} MB).")
    print("The solver will now load it instead of rebuilding.")


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

    # Wide pool: an allowed-only word (e.g. 'maven') is guessable but is NOT a
    # curated answer, so normal mode can't solve for it -- the --wide pool can.
    answers_w, guess_pool_w = load_pools(full_pool=True)
    allowed_only = "maven"
    check(allowed_only not in set(answers),
          f"curated pool excludes allowed-only word '{allowed_only}'")
    check(allowed_only in set(answers_w),
          f"wide pool includes allowed-only word '{allowed_only}'")
    # End-to-end in wide mode (table-free path -> fast, no full cache needed).
    n = solve_for(allowed_only, answers_w, guess_pool_w)
    check(n <= MAX_TURNS, f"wide mode solves '{allowed_only}' in {n} guesses")

    # Mid-game recovery: a *default* Solver (curated pool) must widen on its own
    # when the curated candidates run out, then still solve the allowed-only
    # answer -- keeping the hints already entered instead of restarting.
    solver = Solver()
    widened_at = None
    solved_in = None
    for turn in range(1, MAX_TURNS + 1):
        g = solver.suggest()
        code = score(g, allowed_only)
        if code == "2" * WORD_LEN:
            solved_in = turn
            break
        r = solver.apply_hint(code)
        if r.widened:
            widened_at = turn
        if r.empty:
            break
    check(widened_at is not None,
          f"default Solver auto-widens on '{allowed_only}' (turn {widened_at})")
    check(solved_in is not None and solved_in <= MAX_TURNS,
          f"default Solver recovers and solves '{allowed_only}' in {solved_in}")
    # A normal curated answer must never trigger widening (regression guard).
    solver = Solver()
    triggered = False
    for _ in range(MAX_TURNS):
        g = solver.suggest()
        code = score(g, "crane")
        if code == "2" * WORD_LEN:
            break
        r = solver.apply_hint(code)
        triggered = triggered or r.widened
        if r.terminal:
            break
    check(not triggered, "normal answer 'crane' never triggers widening")

    print(f"\n{'all tests passed' if failures == 0 else f'{failures} test(s) FAILED'}")
    return failures == 0


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main(argv):
    # --wide is the pool-widening modifier for --simulate/--benchmark/
    # --build-matrix. `--full` is a hidden, deprecated alias (the old name)
    # kept working so existing commands don't break. Pull it out before
    # positional parsing.
    wide = "--wide" in argv or "--full" in argv
    argv = [a for a in argv if a not in ("--wide", "--full")]

    cmd = argv[1] if len(argv) >= 2 else "--test"
    if cmd == "--test":
        sys.exit(0 if run_tests() else 1)
    if cmd == "--simulate":
        if len(argv) < 3:
            print("usage: test_solver.py --simulate WORD [--wide]")
            sys.exit(2)
        simulate(argv[2], wide=wide)
        return
    if cmd == "--benchmark":
        limit = int(argv[2]) if len(argv) >= 3 else None
        benchmark(limit, full_pool=wide)
        return
    if cmd == "--recompute-opening":
        recompute_opening()
        return
    if cmd == "--build-matrix":
        build_matrix(full_pool=wide)
        return
    if cmd in ("-h", "--help"):
        print(__doc__)
        return
    print(f"unknown option: {cmd} (try --help)")
    sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
