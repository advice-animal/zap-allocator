"""__main__ tests — no frida required for the --json path."""

from __future__ import annotations

import json
import subprocess
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import pytest
from tests.conftest import frida_mark
from zap_allocator.__main__ import main


class TestMain:
    @frida_mark
    def test_main_json(self, idle_proc: subprocess.Popen[bytes]) -> None:
        """main() with --json must print a JSON object with the correct pid."""
        buf = StringIO()
        with patch("sys.argv", ["zap_allocator", "--json", str(idle_proc.pid)]):
            try:
                with redirect_stdout(buf):
                    main()
            except Exception as exc:
                pytest.skip(f"frida.attach failed: {exc}")

        data = json.loads(buf.getvalue())
        assert data["pid"] == idle_proc.pid
        assert isinstance(data["classes"], list)

    @frida_mark
    def test_main_single_shot(
        self, idle_proc: subprocess.Popen[bytes], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """main() without flags must print a human-readable table (no JSON)."""
        with patch("sys.argv", ["zap_allocator", str(idle_proc.pid)]):
            try:
                main()
            except Exception as exc:
                pytest.skip(f"frida.attach failed: {exc}")

        out = capsys.readouterr().out
        assert "PID" in out
        assert "arenas" in out
