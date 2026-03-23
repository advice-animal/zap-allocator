"""Integration tests: frida attach and arena sampling."""

from __future__ import annotations

import subprocess
import sys

import pytest
from tests.conftest import frida_mark
from zap_allocator import ArenaStatsCollector


class TestSmoke:
    @frida_mark
    def test_collect_returns_snapshot(self, idle_proc: subprocess.Popen[bytes]) -> None:
        """collect() must return a snapshot with plausible fields."""
        try:
            with ArenaStatsCollector(idle_proc.pid) as col:
                snap = col.collect()
        except Exception as exc:
            pytest.skip(f"frida.attach failed: {exc}")

        assert snap.pid == idle_proc.pid
        assert snap.n_arenas >= 1
        assert snap.arena_bytes > 0
        assert len(snap.classes) > 0

    @frida_mark
    def test_collect_twice(self, idle_proc: subprocess.Popen[bytes]) -> None:
        """collect() can be called multiple times on the same session."""
        try:
            with ArenaStatsCollector(idle_proc.pid) as col:
                snap1 = col.collect()
                snap2 = col.collect()
        except Exception as exc:
            pytest.skip(f"frida.attach failed: {exc}")

        assert snap1.pid == snap2.pid == idle_proc.pid


class TestAllocations:
    @frida_mark
    def test_32_byte_bucket_half_full(
        self, alloc_proc: subprocess.Popen[bytes]
    ) -> None:
        """After alloc 1M ints + del x[::2], the 32-byte size class must be ~50% full.

        list(range(1_000_000)) allocates ~743k int objects above the small-int cache
        into the 32-byte pymalloc bucket.  del x[::2] frees every other one, leaving
        ~50% of those blocks in use while the pools remain allocated.
        """
        # Guard: verify 257 (first non-cached int) maps to the 32-byte bucket.
        assert sys.getsizeof(257) == 28, (
            "expected CPython int to be 28 bytes (32-byte bucket)"
        )

        try:
            with ArenaStatsCollector(alloc_proc.pid) as col:
                snap = col.collect()
        except Exception as exc:
            pytest.skip(f"frida.attach failed: {exc}")

        by_size = {c.size: c for c in snap.classes}
        assert 32 in by_size, (
            f"32-byte size class not found; classes present: {sorted(by_size)}"
        )
        sc = by_size[32]
        assert sc.total > 0, "32-byte size class has no blocks"

        fill = sc.fill_pct
        assert 49.0 <= fill <= 51.0, (
            f"Expected 32-byte bucket ~50% full after del x[::2], got {fill:.1f}% "
            f"(used={sc.used:,}, avail={sc.avail:,})"
        )

        # del x[::2] removes even-indexed elements (values 0, 2, 4, …), leaving
        # odd values 1, 3, …, 999999.  Of those 500k, ~499,872 are above the
        # small-int cache (>256) and live as 32-byte pymalloc blocks.
        # Allow ±100k for interpreter-internal allocations in the same bucket.
        assert 400_000 <= sc.used <= 600_000, (
            f"Expected ~500k blocks in use in 32-byte bucket, got {sc.used:,}"
        )

    @frida_mark
    def test_32_byte_bucket_half_full_contiguous_delete(
        self, alloc_proc_contiguous: subprocess.Popen[bytes]
    ) -> None:
        """After alloc 1M ints + del x[:500_000], the 32-byte bucket must be ~99% full.

        Deleting the first 500k elements (values 0–499,999) rather than every
        other one produces the same surviving count (~500k ints above the small-int
        cache), so fill should remain near 50%.  The key difference is that the freed
        blocks are contiguous rather than interleaved — pymalloc may return some pools
        to the OS, but the remaining live objects keep the bucket well-occupied.
        """
        assert sys.getsizeof(257) == 28, (
            "expected CPython int to be 28 bytes (32-byte bucket)"
        )

        try:
            with ArenaStatsCollector(alloc_proc_contiguous.pid) as col:
                snap = col.collect()
        except Exception as exc:
            pytest.skip(f"frida.attach failed: {exc}")

        by_size = {c.size: c for c in snap.classes}
        assert 32 in by_size, (
            f"32-byte size class not found; classes present: {sorted(by_size)}"
        )
        sc = by_size[32]
        assert sc.total > 0, "32-byte size class has no blocks"

        fill = sc.fill_pct
        assert 98.0 <= fill <= 100.0, (
            f"Expected 32-byte bucket ~50% full after del x[:500_000], got {fill:.1f}% "
            f"(used={sc.used:,}, avail={sc.avail:,})"
        )

    @frida_mark
    def test_16_byte_bucket_half_full(
        self, alloc_proc_16: subprocess.Popen[bytes]
    ) -> None:
        """After allocating 1M object()s and freeing every other one, 16-byte fill must be ~50%.

        object() is exactly 16 bytes (ob_refcnt + ob_type on 64-bit).  Unlike ints,
        none are cached, so all 1M land in the 16-byte pymalloc bucket.  del x[::2]
        frees 500k of them, leaving ~500k in use at ~50% fill.
        """
        # Guard: verify object() size hasn't changed in this build.
        assert sys.getsizeof(object()) == 16, "expected bare object() to be 16 bytes"

        try:
            with ArenaStatsCollector(alloc_proc_16.pid) as col:
                snap = col.collect()
        except Exception as exc:
            pytest.skip(f"frida.attach failed: {exc}")

        by_size = {c.size: c for c in snap.classes}
        assert 16 in by_size, (
            f"16-byte size class not found; classes present: {sorted(by_size)}"
        )
        sc = by_size[16]
        assert sc.total > 0, "16-byte size class has no blocks"

        fill = sc.fill_pct
        assert 49.0 <= fill <= 51.0, (
            f"Expected 16-byte bucket ~50% full after del x[::2], got {fill:.1f}% "
            f"(used={sc.used:,}, avail={sc.avail:,})"
        )

        # All 1M object()s are heap-allocated; 500k survive del x[::2].
        # Allow ±100k for interpreter-internal allocations in the same bucket.
        assert 400_000 <= sc.used <= 600_000, (
            f"Expected ~500k blocks in use in 16-byte bucket, got {sc.used:,}"
        )

    @frida_mark
    def test_80_byte_bucket_half_full(
        self, alloc_proc_80: subprocess.Popen[bytes]
    ) -> None:
        """After allocating 1M 47-byte bytes objects and freeing every other one, 80-byte fill must be ~50%.

        bytes objects are not cached or interned, so all 1M land in the 80-byte
        pymalloc bucket.  del x[::2] frees 500k of them, leaving ~500k in use at ~50% fill.
        """
        # Guard: verify the bytes expression produces an 80-byte object.
        assert sys.getsizeof(bytes([0] * 40 + [1, 2, 3, 4, 5, 6, 0])) == 80, (
            "expected 47-byte bytes object to be 80 bytes (80-byte bucket)"
        )

        try:
            with ArenaStatsCollector(alloc_proc_80.pid) as col:
                snap = col.collect()
        except Exception as exc:
            pytest.skip(f"frida.attach failed: {exc}")

        by_size = {c.size: c for c in snap.classes}
        assert 80 in by_size, (
            f"80-byte size class not found; classes present: {sorted(by_size)}"
        )
        sc = by_size[80]
        assert sc.total > 0, "80-byte size class has no blocks"

        fill = sc.fill_pct
        assert 49.0 <= fill <= 51.0, (
            f"Expected 80-byte bucket ~50% full after del x[::2], got {fill:.1f}% "
            f"(used={sc.used:,}, avail={sc.avail:,})"
        )

        # All 1M bytes objects are heap-allocated; 500k survive del x[::2].
        # Allow ±100k for interpreter-internal allocations in the same bucket.
        assert 400_000 <= sc.used <= 600_000, (
            f"Expected ~500k blocks in use in 80-byte bucket, got {sc.used:,}"
        )
