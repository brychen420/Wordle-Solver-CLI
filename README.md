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

**Rare answers:** the curated NYT answer list (`data/answers.txt`) occasionally
omits a word the game actually uses that day — one that lives only in the
larger allowed-guess list. When the curated candidates run out mid-game, the
solver **automatically widens** its search to the full ~13k allowed pool,
replaying the hints you've already entered, and continues from there (it tells
you when this happens). No restart needed.

The wider pool is less informed, so guesses after widening may be slightly
weaker. If you already know the answer is an obscure word, you can start in wide
mode from the first guess:

```sh
python wordle_solver.py --wide
```

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

### The feedback matrix (built automatically on first run)

Choosing each guess requires scoring every allowed guess against every possible
answer — a ~30-million-operation feedback matrix that takes **~35s to build the
first time** (~3.5 min for `--wide`, which is ~5× larger).

The **first time you run the solver on a fresh clone**, it builds this matrix
once — showing a progress bar up front — and caches it to disk
(`data/patterns.bin`, ~30 MB; `data/patterns_full.bin`, ~165 MB for `--wide`).
Every run after that loads the cache in well under a second, so you never wait
again. The cache is keyed to the exact word lists, so it is rebuilt
automatically if you ever change them. The files are git-ignored and safe to
delete (they just rebuild on the next run).

You can also build the cache ahead of time without playing:

```sh
python test_solver.py --build-matrix          # writes data/patterns.bin
python test_solver.py --build-matrix --full   # writes data/patterns_full.bin (~165 MB)
```

## Tests, simulation & benchmarking

Testing and evaluation live in a separate module, `test_solver.py`, which
imports the solver engine:

```sh
python test_solver.py                      # run self-checks (default)
python test_solver.py --test               # run self-checks
python test_solver.py --simulate crane     # auto-play against a known answer
python test_solver.py --simulate maven --wide  # ...starting from the full pool
python test_solver.py --benchmark          # run all answers, report stats
python test_solver.py --benchmark 200      # benchmark the first 200 answers
python test_solver.py --recompute-opening  # find the best opening word
python test_solver.py --build-matrix       # cache the pattern matrix to disk
```

`--simulate` drives the same stateful solver as the interactive CLI, so it also
**auto-widens to the full allowed pool** when the curated candidates run out —
letting you replay a puzzle whose answer is an allowed-only word (e.g. `maven`).
Add `--wide` to start from the full pool on turn 1 instead.

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
