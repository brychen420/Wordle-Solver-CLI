"""Feedback scoring: the single source of truth for guess/answer patterns.

A pattern is the per-tile color code. Internally it is an integer 0..242 (five
ternary digits, 0=gray/1=yellow/2=green, packed little-endian); the string form
("0/1/2" per tile) is what the user types and reads.
"""

from .config import WORD_LEN

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
