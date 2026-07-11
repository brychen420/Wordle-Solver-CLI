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

## Where this runs

This is a **Claude Code** skill and only works in a Claude Code surface (the
CLI, the claude.ai/code web app, the desktop app, or an IDE extension) running
with this repo checked out. It shells out to `python wordle_next.py`, so it
needs the repo files, a Python interpreter, and the local pattern-matrix cache
on disk. It does **not** work in a plain claude.ai chat — that surface can't
load a project's `.claude/skills/` or run local commands.

## The tool

Everything runs through `wordle_next.py` at the project root. Use its
**incremental** mode: the game is kept on disk between turns, so you pass only
the *newest* hint each turn (not the whole history) and each turn does a single
ranking.

```sh
python wordle_next.py --new           # start a game, prints the first word
python wordle_next.py --hint 01010    # apply one hint, prints the next word
python wordle_next.py --hint 22222    # 22222 = solved
```

Run it from the project root (`/home/user/Wordle-Solver-CLI`). One game runs at
a time by default; add `--id NAME` to `--new`/`--hint` to run several at once.

> A legacy stateless mode also exists — `python wordle_next.py 01010 01210`
> (every code so far, in order) — but prefer the incremental mode above: it's
> faster and you can't drop or misorder a code.

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

1. **Start.** Run `python wordle_next.py --new` and tell the user the suggested
   first word (it will be `SALET`). Ask them to play it and report the hint.
   `--new` is instant — it doesn't load the matrix.
   - Note: the *first `--hint`* on a fresh clone may spend ~3.5 min building and
     caching the pattern matrix (unless the SessionStart hook already did it),
     then every turn after is instant. Tell the user if that happens.
2. **Each turn.** When the user reports a hint, convert it to a 5-digit code and
   run `python wordle_next.py --hint <that one code>`. Relay the next suggested
   word (and, briefly, how many candidates remain). You do **not** track the
   history — the tool does.
3. **Terminal states**, printed by the tool:
   - `SOLVED in N guess(es)` → congratulate and stop.
   - `NO MATCH` → a hint was likely mistyped; ask the user to double-check the
     codes so far, then start over with `--new` and re-enter them.
   - `OUT OF GUESSES` → report the remaining possibilities it lists.
   - A `(widened...)` note just means the curated pool ran out mid-game and the
     search expanded; keep going normally.

## Notes

- Keep replies short: the current guess, remaining count, and a prompt for the
  next hint. Don't dump the full top-picks list unless the user asks.
- To start a fresh game, just run `--new` again — it resets the saved state.
- If the user wants normal (curated NYT) mode instead of wide, point them to
  `python wordle_solver.py` — this skill is specifically the wide pool.
