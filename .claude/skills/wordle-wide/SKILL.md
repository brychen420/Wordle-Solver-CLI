---
name: wordle-wide
description: Interactively solve a Wordle puzzle in WIDE mode (full ~13k allowed-word pool, for rare/obscure answers). Use when the user wants to play or solve Wordle, get the next guess, or run the wordle solver in wide mode by conversing turn-by-turn — they type the color hint after each guess and you reply with the next word to play.
---

# Wordle Solver — Wide Mode (conversational)

Drive the wide-mode Wordle solver one turn at a time through chat. You suggest a
word; the user plays it in the real game and reports the color hint; you suggest
the next word. Repeat until solved (or 6 guesses run out).

"Wide mode" means the candidate pool is the entire ~13k allowed-word list rather
than the curated ~2.3k NYT answers — use it for rare/obscure answers. It's what
`python wordle_solver.py --wide` does; this skill just makes it conversational.

## The tool

Everything runs through `wordle_next.py` at the project root. It is **stateless**:
you pass it every hint code entered *so far*, in order, and it prints the guess to
play next. So **you** are responsible for keeping the running list of hint codes.

```sh
python wordle_next.py                 # first guess (no hints yet)
python wordle_next.py 01010           # after the user's 1st hint
python wordle_next.py 01010 01210     # after the 1st and 2nd hints
```

Run it from the project root (`/home/user/Wordle-Solver-CLI`).

## Hint codes

The hint is a 5-digit code, one digit per tile, left to right:

| Digit | Tile color | Meaning                          |
|-------|------------|----------------------------------|
| `0`   | Gray       | letter not in the word           |
| `1`   | Yellow     | letter in the word, wrong spot   |
| `2`   | Green      | correct letter and position      |

`22222` means solved. Accept the user's hint however they phrase it (a raw code
like `10021`, or colors like "yellow gray gray green yellow") and convert it to
the 5-digit code yourself before adding it to the list.

## How to run a session

1. **Start.** Maintain an ordered list of hint codes for this game, initially
   empty. Run `python wordle_next.py` and tell the user the suggested first word
   (it will be `SALET`). Ask them to play it and report the hint.
   - Note: the very first run on a fresh clone spends ~3.5 min building and
     caching the pattern matrix, then every run after is instant. Tell the user
     if that happens so they know why it's slow.
2. **Each turn.** When the user reports a hint, convert it to a 5-digit code,
   append it to your list, and run `python wordle_next.py <all codes so far>`.
   Relay the next suggested word (and, briefly, how many candidates remain).
3. **Terminal states**, printed by the tool:
   - `SOLVED in N guess(es)` → congratulate and stop.
   - `NO MATCH` → a hint was likely mistyped; ask the user to double-check the
     codes so far, correct the list, and re-run.
   - `OUT OF GUESSES` → report the remaining possibilities it lists.
   - A `(widened...)` note just means the curated pool ran out mid-game and the
     search expanded; keep going normally.

## Notes

- Keep replies short: the current guess, remaining count, and a prompt for the
  next hint. Don't dump the full top-picks list unless the user asks.
- Always pass the **complete** history each turn — the tool rebuilds state by
  replaying it. If you drop a code, the suggestion will be wrong.
- If the user wants normal (curated NYT) mode instead of wide, point them to
  `python wordle_solver.py` — this skill is specifically the wide pool.
