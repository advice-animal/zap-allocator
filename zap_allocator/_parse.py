"""Parse sys._debugmallocstats() output into arena snapshots."""

from __future__ import annotations

import re

from zap_allocator._model import ArenaSnapshot, SizeClass

_RE_SIZE_CLASS = re.compile(
    r"^\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
    re.MULTILINE,
)
_RE_N_ARENAS = re.compile(r"arenas allocated current\s*=\s*([\d,]+)")
_RE_HIGHWATER = re.compile(r"arenas highwater mark\s*=\s*([\d,]+)")
_RE_ARENA_BYTES = re.compile(r"\d+ arenas \* ([\d,]+) bytes/arena")
_RE_POOL = re.compile(r"(\d+) unused pools \* ([\d,]+) bytes")


def _parse(text: str, pid: int, ts: float) -> ArenaSnapshot:
    classes: list[SizeClass] = []
    # Size-class table: "    0     16           1             100           406"
    for m in _RE_SIZE_CLASS.finditer(text):
        idx, size, pools, used, avail = (int(x) for x in m.groups())
        classes.append(SizeClass(idx, size, pools, used, avail))

    def _find_int(pattern: re.Pattern[str]) -> int:
        m = pattern.search(text)
        return int(m.group(1).replace(",", "")) if m else 0

    n_arenas = _find_int(_RE_N_ARENAS)
    highwater = _find_int(_RE_HIGHWATER)
    arena_m = _RE_ARENA_BYTES.search(text)
    arena_bytes = int(arena_m.group(1).replace(",", "")) if arena_m else (1 << 20)
    pool_m = _RE_POOL.search(text)
    unused_pools = int(pool_m.group(1)) if pool_m else 0
    pool_bytes = int(pool_m.group(2).replace(",", "")) if pool_m else 0

    return ArenaSnapshot(
        pid, ts, classes, n_arenas, highwater, arena_bytes, pool_bytes, unused_pools
    )
