#!/usr/bin/env python3
"""Run a local check with Cargo artifacts confined to this worktree's target/."""
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def main():
    if len(sys.argv) < 2:
        print("usage: with_worktree_target.py COMMAND [ARG ...]", file=sys.stderr)
        return 2
    env = dict(os.environ, CARGO_TARGET_DIR=str(ROOT / "target"))
    os.chdir(ROOT)
    try:
        os.execvpe(sys.argv[1], sys.argv[1:], env)
    except FileNotFoundError:
        print(f"command not found: {sys.argv[1]}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main())
