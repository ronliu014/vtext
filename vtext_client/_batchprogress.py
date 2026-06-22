"""Two-line live progress renderer for batch transcription.

click-only (no rich/tqdm) to respect the client dependency rule. In a TTY it
redraws two lines in place with ANSI control sequences; in a non-TTY (pipe or
redirect) it falls back to one milestone line per finished file and never
spams per-percent lines — see the reverted commit bbe062b for why.
"""

from __future__ import annotations

import shutil
import sys
import threading
import time
from typing import IO, Callable


class BatchProgress:
    """Tracks per-file progress for a concurrent batch and renders it.

    Line 1: the most-recently-active file and its percentage.
    Line 2: overall progress (average % across all files) with a done/total count.
    """

    def __init__(
        self,
        names: list[str],
        stream: IO[str] | None = None,
        bar_width: int = 22,
        min_interval: float = 0.1,
    ) -> None:
        self.names = list(names)
        self.total = len(names)
        self.stream = stream or sys.stderr
        self.isatty = getattr(self.stream, "isatty", lambda: False)()
        self.bar_width = bar_width
        self.min_interval = min_interval

        self._lock = threading.Lock()
        self._pct = [0] * self.total
        self._done = [False] * self.total
        self._current = -1
        self._last_render = 0.0
        self._lines_drawn = 0
        self._started = False

        if self.isatty:
            self._enable_vt()

    # -- public API ---------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            if self.isatty:
                self._render(force=True)
            else:
                self._write_line(f"Transcribing {self.total} file(s)...")

    def update(self, idx: int, pct: int) -> None:
        """Record a progress update for file ``idx`` (0-100). Thread-safe."""
        with self._lock:
            if not (0 <= idx < self.total) or self._done[idx]:
                return
            self._pct[idx] = max(self._pct[idx], min(100, int(pct)))
            self._current = idx
            if self.isatty:
                self._render()

    def file_done(
        self,
        idx: int,
        ok: bool = True,
        out_name: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            if 0 <= idx < self.total:
                self._done[idx] = True
                if ok:
                    self._pct[idx] = 100
            done_count = sum(self._done)
            name = self.names[idx] if 0 <= idx < self.total else "?"
            if self.isatty:
                self._render(force=True)
            elif ok:
                extra = f" -> {out_name}" if out_name else ""
                self._write_line(f"  Done ({done_count}/{self.total}): {name}{extra}")
            else:
                msg = f": {error}" if error else ""
                self._write_line(f"  Failed ({done_count}/{self.total}): {name}{msg}")

    def finish(self) -> None:
        with self._lock:
            if self.isatty and self._lines_drawn:
                self.stream.write("\n")
                self.stream.flush()

    # -- internals ----------------------------------------------------------

    def _overall(self) -> int:
        if self.total == 0:
            return 0
        return sum(self._pct) // self.total

    def _render(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_render < self.min_interval:
            return
        self._last_render = now
        cols = shutil.get_terminal_size((80, 24)).columns
        done_count = sum(self._done)
        overall = self._overall()

        bar1 = (
            self._bar(self._pct[self._current]) if self._current >= 0 else self._bar(0)
        )
        name = self.names[self._current] if self._current >= 0 else "(waiting)"
        cpct = self._pct[self._current] if self._current >= 0 else 0
        prefix1 = "当前: "
        name_budget = max(10, cols - len(prefix1) - len(bar1) - 5)
        line1 = f"{prefix1}{self._truncate(name, name_budget)} {bar1} {cpct:3d}%"

        bar2 = self._bar(overall)
        line2 = f"总进度 {bar2} {overall:3d}%  ({done_count}/{self.total} 完成)"

        parts: list[str] = []
        if self._lines_drawn:
            parts.append("\033[2A")  # cursor up 2 lines
        parts.append("\r\033[K" + line1 + "\n")
        parts.append("\r\033[K" + line2 + "\n")
        self.stream.write("".join(parts))
        self.stream.flush()
        self._lines_drawn = 2

    def _bar(self, pct: int) -> str:
        filled = round(self.bar_width * max(0, min(100, pct)) / 100)
        return "[" + "#" * filled + "-" * (self.bar_width - filled) + "]"

    @staticmethod
    def _truncate(s: str, width: int) -> str:
        if width <= 3:
            return s[:width]
        if len(s) <= width:
            return s
        return s[: width - 1] + "…"

    def _write_line(self, s: str) -> None:
        self.stream.write(s + "\n")
        self.stream.flush()

    @staticmethod
    def _enable_vt() -> None:
        """On Windows, enable ANSI VT processing on the stderr console."""
        if sys.platform != "win32":
            return
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            STD_ERROR_HANDLE = -12
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            handle = kernel32.GetStdHandle(STD_ERROR_HANDLE)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(
                    handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
                )
        except Exception:
            pass


def make_callback(prog: BatchProgress, idx: int) -> Callable[[int], None]:
    """Build an on_progress callback bound to (prog, idx)."""

    def _cb(pct: int) -> None:
        prog.update(idx, pct)

    return _cb
