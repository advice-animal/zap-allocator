"""Render arena snapshots as human-readable terminal tables."""

from __future__ import annotations

from typing import Optional

from zap_allocator._ansi import _BOLD, _DIM, _GRN, _LARGE_DELTA, _RED, _RST
from zap_allocator._model import ArenaSnapshot


def _render(snap: ArenaSnapshot, prev: Optional[ArenaSnapshot], n: int) -> str:
    lines: list[str] = []

    # Header
    dt_part = ""
    if prev is not None:
        dt_part = f"  Δt {snap.ts - prev.ts:.1f}s"
    mb = snap.arena_bytes >> 20
    kb = snap.pool_bytes >> 10
    lines.append(
        f"PID {snap.pid}  │  snapshot {n}"
        f"  │  {snap.n_arenas} arenas × {mb} MiB/{kb} KiB  (highwater {snap.highwater})"
        f"{dt_part}"
    )
    lines.append("")

    # Column headers
    has_delta = prev is not None
    col_hdr = f"{'size':>6}  {'pools':>5}  {'in_use':>8}  {'fill%':>6}"
    if has_delta:
        col_hdr += f"  {'Δblocks':>9}"
    lines.append(col_hdr)
    lines.append("─" * len(col_hdr))

    prev_by_idx = {c.idx: c for c in prev.classes} if prev else {}

    shown = 0
    for sc in snap.classes:
        p = prev_by_idx.get(sc.idx)
        delta = (sc.used - p.used) if p is not None else None

        # Skip size classes with no pools and no change
        if sc.pools == 0 and (delta is None or delta == 0):
            continue

        shown += 1
        fill = f"{sc.fill_pct:5.1f}%" if sc.pools else "     -"
        row = f"{sc.size:>6}  {sc.pools:>5}  {sc.used:>8,}  {fill}"

        if has_delta:
            if not delta:
                row += f"  {_DIM}{'':>9}{_RST}"
            else:
                sign = "+" if delta > 0 else ""
                d_str = f"{sign}{delta:,}"
                big = abs(delta) >= _LARGE_DELTA
                color = _RED if delta > 0 else _GRN
                row += f"  {_BOLD if big else ''}{color}{d_str:>9}{_RST}"

        lines.append(row)

    if shown == 0:
        lines.append(f"{_DIM}  (no active size classes){_RST}")

    # Free-pool row (pools in arenas not yet assigned to any size class)
    fp = snap.unused_pools
    fp_prev = prev.unused_pools if prev is not None else None
    if fp or fp_prev:
        row = f"{'free':>6}  {fp:>5}  {fp:>8,}  {'100.0%':>6}"
        if has_delta:
            delta = (fp - fp_prev) if fp_prev is not None else None
            if not delta:
                row += f"  {_DIM}{'':>9}{_RST}"
            else:
                sign = "+" if delta > 0 else ""
                d_str = f"{sign}{delta:,}"
                big = abs(delta) >= _LARGE_DELTA
                color = _RED if delta > 0 else _GRN
                row += f"  {_BOLD if big else ''}{color}{d_str:>9}{_RST}"
        lines.append(row)

    # Total blocks summary
    total_used = sum(c.used for c in snap.classes)
    total_avail = sum(c.avail for c in snap.classes)
    lines.append("")
    summary = f"total: {total_used:,} blocks in use, {total_avail:,} available"
    if has_delta:
        prev_used = sum(c.used for c in prev.classes) if prev else 0
        d = total_used - prev_used
        if d:
            sign = "+" if d > 0 else ""
            color = _RED if d > 0 else _GRN
            summary += f"  ({_BOLD if abs(d) >= _LARGE_DELTA else ''}{color}{sign}{d:,} blocks{_RST})"
    lines.append(summary)

    return "\n".join(lines)
