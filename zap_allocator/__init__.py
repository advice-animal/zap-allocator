"""zap-allocator: inspect pymalloc arena statistics of a running Python process."""

from __future__ import annotations

from zap_allocator._collector import ArenaStatsCollector
from zap_allocator._model import ArenaSnapshot, SizeClass
from zap_allocator._render import _render

__all__ = ["ArenaStatsCollector", "ArenaSnapshot", "SizeClass", "_render"]
