# Wordle Solver (NYT edition)

An interactive command-line solver for the New York Times Wordle game. It
suggests the best guess, you play it in the real game, type back the color hint,
and it suggests the next guess — repeating within the 6-guess limit.

It chooses guesses to **maximize expected information (entropy)** on early turns,
then switches to an **endgame** mode that only guesses real possible answers when
few candidates remain or on the final turns, to maximize the chance of winning.

Benchmarked against all 2,315 NYT answers (opening with `SALET`): **100% solved
within 6 guesses, averaging 3.43 guesses** (distribution — 2: 79, 3: 1205,
4: 983, 5: 46, 6: 2). Reproduce with `python test_solver.py --benchmark`.

## Requirements

- Python 3.8+ (standard library only — no dependencies, no `pip install`).

## Usage

Start the interactive solver:

```sh
python wordle_solver.py
```

It prints a guess. Play that word in Wordle, then enter the hint as a **5-digit
code**, one digit per tile, left to right:

| Digit | Color  | Meaning                                  |
|-------|--------|------------------------------------------|
| `0`   | Gray   | letter not in the word                   |
| `1`   | Yellow | letter in the word, wrong position       |
| `2`   | Green  | correct letter, correct position         |

**Example:** you guess `GUCKS` and the tiles show
Yellow · Gray · Gray · Green · Yellow → type `10021`.

Enter `22222` when you win, or `q` to quit.

### Sample session

```
Guess 1/6:  >>> SALET <<<
  Hint code (or 'q'): 01010
  142 possible answer(s) remain.
    top picks: BEARD (5.61 bits), ...

Guess 2/6:  >>> BEARD <<<
  Hint code (or 'q'): 01210
  ...
```

### Speeding up the first guess (optional)

Choosing the second word requires scoring every allowed guess against every
possible answer — a ~30-million-operation feedback matrix that takes **~35s to
build the first time**. By default this happens lazily, so you feel it as a pause
right after your first hint.

To make the first guess instant, build the matrix once and cache it to disk:

```sh
python test_solver.py --build-matrix      # ~35s, writes data/patterns.bin (~30 MB)
```

After that, the solver loads the cache in well under a second on every run. The
cache is keyed to the exact word lists, so it is ignored automatically (and
rebuilt lazily) if you ever change them. The file is git-ignored and safe to
delete.

## Tests, simulation & benchmarking

Testing and evaluation live in a separate module, `test_solver.py`, which
imports the solver engine:

```sh
python test_solver.py                      # run self-checks (default)
python test_solver.py --test               # run self-checks
python test_solver.py --simulate crane     # auto-play against a known answer
python test_solver.py --benchmark          # run all answers, report stats
python test_solver.py --benchmark 200      # benchmark the first 200 answers
python test_solver.py --recompute-opening  # find the best opening word
python test_solver.py --build-matrix       # cache the pattern matrix to disk
```

## How it works

- **`score(guess, answer)`** computes the `0/1/2` feedback code, with correct
  duplicate-letter handling (greens are assigned first and consume a letter, so a
  repeated guess letter only shows yellow if an unused copy remains). This one
  function is used both to filter candidates and to compute entropy, so the two
  can never disagree.
- After each hint, candidates are filtered to those that would have produced the
  exact code you entered.
- Each turn, the guess with the highest expected information is chosen from the
  full allowed-guess pool — except in the endgame (≤2 candidates, or turns 5–6
  with many candidates remaining), where guesses are restricted to actual
  possible answers so the guess can win outright.
- **Performance:** feedback patterns are packed into a single integer (0–242,
  five base-3 digits) and cached in a `PatternTable` — the precomputed
  `guess × answer` feedback matrix. Entropy then counts array lookups instead of
  re-deriving patterns, so repeated full-pool ranking (the interactive solver's
  heavy turns, and especially the benchmark) is dramatically faster. The matrix
  is built once and reused across all games in a benchmark run, and can be
  cached to disk (see *Speeding up the first guess*) so interactive play never
  pays the build cost.

## Data

- `data/answers.txt` — the NYT answer list (the possible-answer pool).
- `data/allowed.txt` — additional accepted guesses (guessable but never answers).

Sourced from the canonical Wordle word-list gists by
[cfreshman](https://gist.github.com/cfreshman):

- Answers — <https://gist.github.com/cfreshman/a03ef2cba789d8cf00c08f767e0fad7b>
- Allowed guesses (excluding answers) —
  <https://gist.github.com/cfreshman/cdcdf777450c5b5301e439061d29694c>

The solver only reads these local files, so it runs fully offline.

The default opening word is `SALET` (the entropy-optimal opener for this list),
set in `wordle/config.py` so the first turn is instant. Run
`python test_solver.py --recompute-opening` to regenerate it if you change the
word lists.

## Project layout

The engine is a small package split by concern; `wordle_solver.py` is just an
entrypoint:

| Path                 | Purpose                                              |
|----------------------|------------------------------------------------------|
| `wordle_solver.py`   | Thin entrypoint → `wordle.cli.main`                  |
| `wordle/config.py`   | Constants and data-file paths                        |
| `wordle/scoring.py`  | `score` / `score_int` and pattern↔string conversions |
| `wordle/patterns.py` | `PatternTable` (the precomputed feedback matrix)     |
| `wordle/words.py`    | Word-list loading and hint validation                |
| `wordle/solver.py`   | Entropy strategy + the stateful `Solver` class       |
| `wordle/cli.py`      | Interactive command-line interface                   |
| `test_solver.py`     | Self-checks, simulation, benchmarking                |
| `data/answers.txt`   | NYT answer list (possible-answer pool)               |
| `data/allowed.txt`   | Additional accepted guesses                          |

### Using the solver as a library

```python
from wordle import Solver

solver = Solver()
print(solver.suggest())          # 'salet' (the opening word)
result = solver.apply_hint('01010')
print(result.next_guess, result.remaining)
```
