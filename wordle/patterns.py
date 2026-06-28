"""Precomputed feedback matrix that makes repeated entropy ranking fast.

The matrix (`pattern[guess][answer]`) is ~30M entries and takes ~35s to build
in pure Python. To avoid paying that on the first interactive guess, it can be
built once and cached to disk (`data/patterns.bin`); the cache is keyed to the
exact word lists, so it is ignored automatically if either list changes.
"""

import hashlib
import math
import struct
from array import array

from .config import NUM_PATTERNS, PATTERN_CACHE_FILE
from .scoring import score_int

# Binary cache header: magic + format version. Bump VERSION if the on-disk
# layout ever changes so old caches are rejected rather than misread.
_MAGIC = b"WPAT"
_VERSION = 1


def _fingerprint(answers, guesses):
    """A digest of the exact word lists (order included) the matrix was built
    for. The cache is only used when this matches the current lists."""
    h = hashlib.sha256()
    h.update(struct.pack("<II", len(answers), len(guesses)))
    h.update("\n".join(answers).encode("utf-8"))
    h.update(b"\x00")
    h.update("\n".join(guesses).encode("utf-8"))
    return h.digest()


class PatternTable:
    """Caches feedback patterns so entropy never recomputes `score_int`.

    Conceptually it is the matrix `pattern[guess][answer]`. Rows are byte
    arrays (each pattern fits in one byte, 0..242). They are filled in one of
    three ways, cheapest first:
      * loaded in bulk from the on-disk cache (if present and in sync), or
      * built eagerly for the whole guess pool via `build_all()`, or
      * built lazily per guess on first use (the original behavior).
    Once a row exists, entropy is pure array lookups + counting.
    """

    def __init__(self, answers, guess_pool=None, use_cache=True):
        # The answer axis is fixed: entropy is always measured over candidates,
        # which are a subset of the answer pool. We index answers by position.
        self.answers = list(answers)
        self.answer_id = {w: i for i, w in enumerate(self.answers)}
        self.guess_pool = list(guess_pool) if guess_pool is not None else None
        self._rows = {}  # guess word -> array('B') of patterns vs each answer
        self._scratch = [0] * NUM_PATTERNS  # reusable bucket counts for entropy

        # Try to populate every row from the disk cache up front. If it is
        # missing or stale, rows just build lazily as before -- no error.
        if use_cache and self.guess_pool is not None:
            self.load_cache()

    # --- row access ------------------------------------------------------- #
    def row(self, guess):
        """Return (and cache) the pattern array for `guess` vs every answer."""
        r = self._rows.get(guess)
        if r is None:
            r = array("B", (score_int(guess, a) for a in self.answers))
            self._rows[guess] = r
        return r

    def build_all(self, progress=None):
        """Eagerly build every row for the guess pool (the ~35s computation).

        `progress` is an optional callback receiving (done, total) every so
        often, for printing a build progress bar.
        """
        if self.guess_pool is None:
            raise ValueError("build_all requires a guess_pool")
        total = len(self.guess_pool)
        answers = self.answers
        rows = self._rows
        for i, g in enumerate(self.guess_pool, 1):
            if g not in rows:
                rows[g] = array("B", (score_int(g, a) for a in answers))
            if progress is not None and i % 500 == 0:
                progress(i, total)
        if progress is not None:
            progress(total, total)

    # --- entropy ---------------------------------------------------------- #
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

    # --- disk cache ------------------------------------------------------- #
    def save_cache(self, path=PATTERN_CACHE_FILE):
        """Write the full matrix to disk. Builds any missing rows first."""
        if self.guess_pool is None:
            raise ValueError("save_cache requires a guess_pool")
        self.build_all()
        n_ans = len(self.answers)
        fp = _fingerprint(self.answers, self.guess_pool)
        guesses_blob = "\n".join(self.guess_pool).encode("utf-8")
        with open(path, "wb") as f:
            # Header: magic, version, fingerprint, counts, guess-list length.
            f.write(_MAGIC)
            f.write(struct.pack("<B", _VERSION))
            f.write(fp)  # 32 bytes
            f.write(struct.pack("<III", len(self.guess_pool), n_ans,
                                len(guesses_blob)))
            f.write(guesses_blob)
            # Rows, in guess-pool order; each is exactly n_ans bytes.
            for g in self.guess_pool:
                self._rows[g].tofile(f)

    def load_cache(self, path=PATTERN_CACHE_FILE):
        """Populate rows from the disk cache if it exists and is in sync.

        Returns True on a successful load, False otherwise (caller then falls
        back to lazy / eager building). Never raises on a bad/stale cache.
        """
        try:
            with open(path, "rb") as f:
                if f.read(4) != _MAGIC:
                    return False
                (version,) = struct.unpack("<B", f.read(1))
                if version != _VERSION:
                    return False
                fp = f.read(32)
                if fp != _fingerprint(self.answers, self.guess_pool):
                    return False  # word lists changed -> stale cache
                n_guess, n_ans, blob_len = struct.unpack("<III", f.read(12))
                if n_ans != len(self.answers) or n_guess != len(self.guess_pool):
                    return False
                guesses = f.read(blob_len).decode("utf-8").split("\n")
                if guesses != self.guess_pool:
                    return False
                for g in guesses:
                    r = array("B")
                    r.frombytes(f.read(n_ans))
                    if len(r) != n_ans:
                        return False  # truncated file
                    self._rows[g] = r
            return True
        except (OSError, ValueError, struct.error):
            return False
