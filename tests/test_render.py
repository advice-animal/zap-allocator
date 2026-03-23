"""Render tests — no frida required."""

from __future__ import annotations

import json

from zap_allocator import ArenaSnapshot, SizeClass, _render


def _make_snap(
    pid: int = 1,
    classes: list[SizeClass] | None = None,
    n_arenas: int = 3,
) -> ArenaSnapshot:
    if classes is None:
        classes = [
            SizeClass(0, 16, 1, 50, 462),
            SizeClass(1, 32, 2, 100, 28),
            SizeClass(2, 64, 0, 0, 0),  # no pools — hidden in render
        ]
    return ArenaSnapshot(
        pid=pid,
        ts=1.0,
        classes=classes,
        n_arenas=n_arenas,
        highwater=n_arenas,
        arena_bytes=1 << 20,
    )


class TestRender:
    def test_render_single_snapshot(self) -> None:
        """_render with no prev must include pid and size class rows."""
        snap = _make_snap(pid=42)
        out = _render(snap, None, 1)
        assert "PID 42" in out
        assert "snapshot 1" in out
        # size classes with pools should appear
        assert "16" in out
        assert "32" in out
        # class with no pools and no delta should be hidden
        assert out.count("64") == 0

    def test_render_with_delta(self) -> None:
        """_render with a prev snapshot must include a Δblocks column."""
        prev = _make_snap(
            classes=[SizeClass(0, 16, 1, 40, 472), SizeClass(1, 32, 2, 80, 48)]
        )
        snap = _make_snap(
            classes=[SizeClass(0, 16, 1, 50, 462), SizeClass(1, 32, 2, 100, 28)]
        )
        out = _render(snap, prev, 2)
        assert "Δblocks" in out
        assert "Δt" in out
        assert "+10" in out  # 50 - 40 = +10 for size class 16
        assert "+20" in out  # 100 - 80 = +20 for size class 32

    def test_render_no_active_classes(self) -> None:
        """_render must show the empty-state message when no classes have pools."""
        snap = _make_snap(classes=[SizeClass(0, 16, 0, 0, 0)])
        out = _render(snap, None, 1)
        assert "no active size classes" in out

    def test_render_large_delta_bold(self) -> None:
        """A delta >= 1000 blocks must appear in the output (bold/colour escape codes)."""
        prev = _make_snap(classes=[SizeClass(0, 32, 10, 0, 4096)])
        snap = _make_snap(classes=[SizeClass(0, 32, 10, 2000, 2096)])
        out = _render(snap, prev, 2)
        assert "+2,000" in out

    def test_to_dict_round_trips_json(self) -> None:
        """to_dict() must produce JSON-serialisable data that round-trips cleanly."""
        snap = _make_snap(pid=99)
        text = json.dumps(snap.to_dict())
        data = json.loads(text)
        assert data["pid"] == 99
        assert data["n_arenas"] == 3
        assert len(data["classes"]) == 3
        assert data["classes"][0] == {
            "idx": 0,
            "size": 16,
            "pools": 1,
            "used": 50,
            "avail": 462,
        }
