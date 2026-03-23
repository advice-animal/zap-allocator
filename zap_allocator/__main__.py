"""
zap_allocator: pymalloc arena statistics from a live Python process.

Attaches to a running Python process and reports per-size-class block usage
from the CPython small-object allocator (pymalloc).  Each row is one size
class (16, 32, … 512 bytes); idle classes are hidden.

Usage::

    zap-allocator -p <pid>
    zap-allocator <pid> --watch   # refresh every 1 s
    zap-allocator <pid> --watch --interval 0.5

Watch mode clears the terminal each refresh and highlights changes:
  red   — size class is allocating more blocks
  green — size class is freeing blocks
  bold  — change of 1000 blocks since last snapshot
"""

from __future__ import annotations

import argparse
import json
import time

from zap_allocator import ArenaStatsCollector, _render
from zap_allocator._ansi import _CLR


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    ap.add_argument("pid", type=int)
    ap.add_argument(
        "--watch",
        action="store_true",
        help="refresh continuously until Ctrl-C",
    )
    ap.add_argument(
        "--interval",
        type=float,
        default=1.0,
        metavar="S",
        help="seconds between refreshes in watch mode (default 1.0)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="output a JSON object instead of the human-readable table",
    )
    args = ap.parse_args()

    with ArenaStatsCollector(args.pid) as col:
        if not args.watch:
            snap = col.collect()
            if args.json:
                print(json.dumps(snap.to_dict()))
            else:
                print(_render(snap, None, 1))
            return

        prev, n = None, 0
        try:
            while True:
                snap = col.collect()
                n += 1
                print(_CLR + _render(snap, prev, n), end="", flush=True)
                prev = snap
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print()


if __name__ == "__main__":
    main()
