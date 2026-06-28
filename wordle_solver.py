#!/usr/bin/env python3
"""Entrypoint for the Wordle solver. The implementation lives in the `wordle`
package; this thin wrapper keeps `python wordle_solver.py` working."""

import sys

from wordle.cli import main

if __name__ == "__main__":
    main(sys.argv)
