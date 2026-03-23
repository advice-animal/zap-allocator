"""Parse sys._debugmallocstats() output into arena snapshots."""

from __future__ import annotations

import re

from zap_allocator._model import ArenaSnapshot, SizeClass


def _parse(text: str, pid: int, ts: float) -> ArenaSnapshot:
    classes: list[SizeClass] = []
    # Size-class table: "    0     16           1             100           406"
    for m in re.finditer(
        r"^\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
        text,
        re.MULTILINE,
    ):
        idx, size, pools, used, avail = (int(x) for x in m.groups())
        classes.append(SizeClass(idx, size, pools, used, avail))

    def _find_int(pattern: str) -> int:
        m = re.search(pattern, text)
        return int(m.group(1).replace(",", "")) if m else 0

    n_arenas = _find_int(r"arenas allocated current\s*=\s*([\d,]+)")
    highwater = _find_int(r"arenas highwater mark\s*=\s*([\d,]+)")
    arena_m = re.search(r"\d+ arenas \* ([\d,]+) bytes/arena", text)
    arena_bytes = int(arena_m.group(1).replace(",", "")) if arena_m else (1 << 20)

    return ArenaSnapshot(pid, ts, classes, n_arenas, highwater, arena_bytes)
