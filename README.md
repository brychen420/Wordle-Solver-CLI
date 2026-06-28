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
  is built once and reused across all games in a benchmark run.

## Data

- `data/answers.txt` — the NYT answer list (the possible-answer pool).
- `data/allowed.txt` — additional accepted guesses (guessable but never answers).

Sourced from the canonical Wordle word-list gists by cfreshman. The solver only
reads these local files, so it runs fully offline.

The default opening word is `SALET` (the entropy-optimal opener for this list),
hardcoded in `wordle_solver.py` so the first turn is instant. Run
`python test_solver.py --recompute-opening` to regenerate it if you change the
word lists.

## Files

| File               | Purpose                                            |
|--------------------|----------------------------------------------------|
| `wordle_solver.py` | Solver engine + interactive CLI                    |
| `test_solver.py`   | Self-checks, simulation, benchmarking              |
| `data/answers.txt` | NYT answer list (possible-answer pool)             |
| `data/allowed.txt` | Additional accepted guesses                        |
