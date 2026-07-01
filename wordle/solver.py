"""Entropy-based guess selection (the strategy) and the stateful Solver.

The module-level functions are pure and remain the single implementation of
the strategy. `Solver` is a thin stateful wrapper that drives a whole game by
calling those same functions, so the guesses it chooses are provably identical
to calling the functions directly.
"""

import math
from collections import defaultdict

from .config import DEFAULT_OPENING, MAX_TURNS, PATTERN_CACHE_FILE
from .patterns import PatternTable
from .scoring import score_int, str_to_code
from .words import load_pools


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
# Stateful game driver                                                         #
# --------------------------------------------------------------------------- #
class HintResult:
    """Outcome of applying one hint, for the caller (CLI/sim) to render.

    Exactly one of the terminal flags may be set:
      solved    -- the hint was all-green (22222)
      empty     -- no candidate matches all hints (bad hint or word not listed)
      exhausted -- the 6th guess has been scored without solving
    When none are set, `next_guess`/`ranked`/`remaining` describe the next turn.
    """

    def __init__(self, solved=False, empty=False, exhausted=False,
                 next_guess=None, ranked=None, remaining=0, candidates=None,
                 widened=False):
        self.solved = solved
        self.empty = empty
        self.exhausted = exhausted
        self.next_guess = next_guess
        self.ranked = ranked or []
        self.remaining = remaining
        self.candidates = candidates or []
        # True on the turn the candidate pool was widened from the curated
        # answers to the full guess pool (a rare mid-game recovery).
        self.widened = widened

    @property
    def terminal(self):
        return self.solved or self.empty or self.exhausted


class Solver:
    """Drives a single game: suggest a guess, apply a hint, repeat.

    Holds the word pools, the shared PatternTable, the live candidate set, and
    the turn counter. It delegates all guess selection to `best_guess` /
    `filter_candidates`, so it is a convenience layer over the pure functions,
    not a second implementation of the strategy.
    """

    def __init__(self, answers=None, guess_pool=None, opening=DEFAULT_OPENING,
                 table=None, cache_path=PATTERN_CACHE_FILE):
        if answers is None or guess_pool is None:
            answers, guess_pool = load_pools()
        self.answers = list(answers)
        self.guess_pool = guess_pool
        # Passing guess_pool lets the table load the on-disk matrix cache (if
        # present and in sync), making the first guess instant instead of ~35s.
        # cache_path selects which cache to load (normal vs full-pool), matching
        # how test_solver.benchmark() picks it.
        self.table = (table if table is not None
                      else PatternTable(self.answers, self.guess_pool,
                                        cache_path=cache_path))
        self.candidates = list(self.answers)
        self.opening = opening
        self.turn = 1
        self.current_guess = opening
        # (guess, code) pairs applied so far, so we can replay every hint
        # against the wider pool if the curated candidates ever run out.
        self.history = []
        self.widened = False

    def suggest(self):
        """Return the guess to play on the current turn."""
        return self.current_guess

    def _widen_candidates(self):
        """Re-derive candidates from the full guess pool by replaying all hints.

        Called once, when the curated-answer candidate set is exhausted but the
        real answer might still be an allowed-only word (in the guess pool but
        not the curated list). Reuses the same filtering as normal play.
        """
        cands = list(self.guess_pool)
        for g, c in self.history:
            cands = filter_candidates(cands, g, c)
        return cands

    def apply_hint(self, code):
        """Record the hint for the current guess and advance the game.

        `code` is a validated 5-char '0/1/2' string. Returns a HintResult
        describing the outcome (solved / empty / exhausted) or the next guess.
        """
        guess = self.current_guess

        if code == "2" * len(code):
            return HintResult(solved=True)

        # Record the hint (before filtering) so a later widen can replay it.
        self.history.append((guess, code))

        # Narrow the candidate set with this hint.
        self.candidates = filter_candidates(self.candidates, guess, code)

        # Curated pool exhausted -> widen to the full guess pool once, so a rare
        # answer that lives only in the allowed list stays solvable.
        just_widened = False
        if not self.candidates and not self.widened:
            self.candidates = self._widen_candidates()
            self.widened = True
            just_widened = True

        if not self.candidates:
            return HintResult(empty=True)

        if self.turn >= MAX_TURNS:
            return HintResult(exhausted=True, candidates=self.candidates,
                              widened=just_widened)

        # Choose the guess for the next turn (first full-pool ranking builds the
        # PatternTable rows). Once widened, candidates can include allowed-only
        # words that aren't on the table's (curated) answer axis, so drop the
        # table and use the table-free ranking path to avoid a KeyError.
        next_turn = self.turn + 1
        table = None if self.widened else self.table
        next_guess, ranked = best_guess(
            self.guess_pool, self.candidates, next_turn, table=table
        )
        self.turn = next_turn
        self.current_guess = next_guess
        return HintResult(
            next_guess=next_guess,
            ranked=ranked,
            remaining=len(self.candidates),
            candidates=self.candidates,
            widened=just_widened,
        )
