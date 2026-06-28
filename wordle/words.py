"""Word-list loading and hint-code validation."""

from .config import ALLOWED_FILE, ANSWERS_FILE, WORD_LEN


def load_words(path):
    with open(path, encoding="utf-8") as f:
        return [w.strip().lower() for w in f if w.strip()]


def load_pools(full_pool=False):
    """Return (answers, guess_pool).

    By default `answers` is the curated NYT answer list (the possible-answer
    pool, ~2.3k) and `guess_pool` is every word you may type (~13k = answers
    ∪ allowed). With `full_pool=True`, the answer pool is widened to the entire
    guess pool -- i.e. the solver assumes the hidden word could be *any* allowed
    word. This is a much harder, less-informed problem; it exists for
    experimentation, not normal play.
    """
    answers = load_words(ANSWERS_FILE)
    allowed_extra = load_words(ALLOWED_FILE)
    # Guess pool is the union; answers are the candidate (possible-answer) pool.
    guess_pool = sorted(set(answers) | set(allowed_extra))
    if full_pool:
        return list(guess_pool), guess_pool
    return answers, guess_pool


def valid_code(code):
    return len(code) == WORD_LEN and all(c in "012" for c in code)
