"""Word-list loading and hint-code validation."""

from .config import ALLOWED_FILE, ANSWERS_FILE, WORD_LEN


def load_words(path):
    with open(path, encoding="utf-8") as f:
        return [w.strip().lower() for w in f if w.strip()]


def load_pools():
    answers = load_words(ANSWERS_FILE)
    allowed_extra = load_words(ALLOWED_FILE)
    # Guess pool is the union; answers are the candidate (possible-answer) pool.
    guess_pool = sorted(set(answers) | set(allowed_extra))
    return answers, guess_pool


def valid_code(code):
    return len(code) == WORD_LEN and all(c in "012" for c in code)
