"""Data model for pymalloc arena snapshots."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SizeClass:
    idx: int
    size: int  # bytes per block
    pools: int
    used: int  # blocks in use
    avail: int  # available blocks

    @property
    def total(self) -> int:
        return self.used + self.avail

    @property
    def fill_pct(self) -> float:
        return 100.0 * self.used / self.total if self.total else 0.0


@dataclass
class ArenaSnapshot:
    pid: int
    ts: float  # time.monotonic()
    classes: list[SizeClass]
    n_arenas: int
    highwater: int
    arena_bytes: int  # bytes per arena (1 MiB on 64-bit)
    pool_bytes: int  # bytes per pool (16 KiB on 64-bit)
    unused_pools: int  # pools in arenas not yet assigned to any size class

    def to_dict(self) -> dict[str, object]:
        return {
            "pid": self.pid,
            "ts": self.ts,
            "n_arenas": self.n_arenas,
            "highwater": self.highwater,
            "arena_bytes": self.arena_bytes,
            "pool_bytes": self.pool_bytes,
            "unused_pools": self.unused_pools,
            "classes": [
                {
                    "idx": c.idx,
                    "size": c.size,
                    "pools": c.pools,
                    "used": c.used,
                    "avail": c.avail,
                }
                for c in self.classes
            ],
        }
