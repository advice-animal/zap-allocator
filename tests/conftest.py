"""Shared fixtures and subprocess helpers for the zap-allocator test suite."""

from __future__ import annotations

import select
import subprocess
import sys
from collections.abc import Generator

import pytest

try:
    import frida  # noqa: F401

    _FRIDA_AVAILABLE = True
except ImportError:
    _FRIDA_AVAILABLE = False

frida_mark = pytest.mark.skipif(not _FRIDA_AVAILABLE, reason="frida not installed")


def _allow_ptrace() -> None:
    """preexec_fn: allow any process to ptrace this child (Linux Yama workaround).

    With ptrace_scope=1, frida.attach() can only trace processes it spawned.
    PR_SET_PTRACER with PR_SET_PTRACER_ANY opts this specific child out of that
    restriction without requiring root or a global sysctl change.
    """
    import ctypes

    PR_SET_PTRACER = 0x59616D61  # "Yama" as a little-endian int
    PR_SET_PTRACER_ANY = -1
    try:
        ctypes.CDLL("libc.so.6").prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY, 0, 0, 0)
    except Exception:
        pass


def _spawn(cmd: str) -> subprocess.Popen[bytes]:
    """Spawn sys.executable running *cmd*, blocking on stdin.

    stdout=PIPE lets the parent call proc.stdout.read(1) to block until the
    child explicitly closes stdout (sys.stdout.close()), signalling that all
    allocations are done and the process is ready to be sampled.  This avoids
    arbitrary time.sleep() calls.

    preexec_fn is only set on Linux: on macOS there is no ptrace_scope
    restriction, and passing a preexec_fn (even a no-op) disables the
    macOS spawn shortcut, which can cause hangs in some CI environments.
    """
    kwargs: dict[str, object] = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE}
    if sys.platform == "linux":
        kwargs["preexec_fn"] = _allow_ptrace
    return subprocess.Popen([sys.executable, "-c", cmd], **kwargs)  # type: ignore[call-overload]


def _teardown(proc: subprocess.Popen[bytes]) -> None:
    assert proc.stdin is not None
    proc.stdin.close()
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _ready(proc: subprocess.Popen[bytes], timeout: float = 15.0) -> None:
    """Block until the child writes its readiness line to stdout, or timeout.

    The child signals readiness by calling print(flush=True) after all
    allocations are done.  select.select() provides the timeout without
    needing a background thread.
    """
    assert proc.stdout is not None
    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    if not ready:
        proc.kill()
        proc.wait()
        raise TimeoutError(f"child process did not signal ready within {timeout}s")
    proc.stdout.readline()


@pytest.fixture()
def idle_proc() -> Generator[subprocess.Popen[bytes], None, None]:
    """Spawn sys.executable blocking on stdin with no extra allocations."""
    proc = _spawn("import sys; print(flush=True); sys.stdin.read()")
    _ready(proc)
    yield proc
    _teardown(proc)


@pytest.fixture()
def alloc_proc() -> Generator[subprocess.Popen[bytes], None, None]:
    """Spawn sys.executable that allocates 1M ints, frees every other one, then blocks."""
    proc = _spawn(
        "x = list(range(1_000_000)); del x[::2];"
        " import sys; print(flush=True); sys.stdin.read()"
    )
    _ready(proc)
    yield proc
    _teardown(proc)


@pytest.fixture()
def alloc_proc_16() -> Generator[subprocess.Popen[bytes], None, None]:
    """Spawn sys.executable that allocates 1M object()s, frees every other one, then blocks."""
    proc = _spawn(
        "x = [object() for _ in range(1_000_000)]; del x[::2];"
        " import sys; print(flush=True); sys.stdin.read()"
    )
    _ready(proc)
    yield proc
    _teardown(proc)


@pytest.fixture()
def alloc_proc_80() -> Generator[subprocess.Popen[bytes], None, None]:
    """Spawn sys.executable that allocates 1M 47-byte bytes objects, frees every other one, then blocks."""
    proc = _spawn(
        "x = [bytes([0] * 40 + [1, 2, 3, 4, 5, 6, _ % 256]) for _ in range(1_000_000)];"
        " del x[::2]; import sys; print(flush=True); sys.stdin.read()"
    )
    _ready(proc)
    yield proc
    _teardown(proc)


@pytest.fixture()
def alloc_proc_contiguous() -> Generator[subprocess.Popen[bytes], None, None]:
    """Spawn sys.executable that allocates 1M ints, frees the first 500k, then blocks."""
    proc = _spawn(
        "x = list(range(1_000_000)); del x[:500_000];"
        " import sys; print(flush=True); sys.stdin.read()"
    )
    _ready(proc)
    yield proc
    _teardown(proc)
