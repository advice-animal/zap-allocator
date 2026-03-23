"""Frida-based arena statistics collector."""

from __future__ import annotations

import sys
import time
from typing import Any

from zap_allocator._agent import _AGENT_JS
from zap_allocator._model import ArenaSnapshot
from zap_allocator._parse import _parse


class ArenaStatsCollector:
    """Attach to a running Python process and sample its pymalloc arena state.

    Usage::

        with ArenaStatsCollector(pid=1234) as col:
            snap = col.collect()
            print(snap.n_arenas, snap.classes[0].fill_pct)
    """

    def __init__(self, pid: int) -> None:
        self._pid: int = pid
        self._session: Any = None
        self._script: Any = None

    def __enter__(self) -> "ArenaStatsCollector":
        import frida  # noqa: PLC0415

        self._session = frida.attach(self._pid)
        self._script = self._session.create_script(_AGENT_JS)
        self._script.on("message", self._on_message)
        self._script.load()
        result = self._script.exports_sync.setup()
        if not result.get("ok"):
            raise RuntimeError(f"agent setup failed: {result.get('error')}")
        return self

    def _on_message(self, msg: dict[str, object], _data: object) -> None:
        if msg.get("type") == "error":
            print(f"[frida_arena] {msg.get('description', msg)}", file=sys.stderr)

    def collect(self) -> ArenaSnapshot:
        """Take one arena snapshot from the target process."""
        result = self._script.exports_sync.collect()
        if not result.get("ok"):
            raise RuntimeError(result.get("error"))
        return _parse(result["text"], self._pid, time.monotonic())

    def __exit__(self, *_: object) -> None:
        if self._script is not None:
            try:
                self._script.unload()
            except Exception:
                pass
        if self._session is not None:
            try:
                self._session.detach()
            except Exception:
                pass
