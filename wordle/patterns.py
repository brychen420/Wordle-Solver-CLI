"""Precomputed feedback matrix that makes repeated entropy ranking fast."""

import math
from array import array

from .config import NUM_PATTERNS
from .scoring import score_int


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
