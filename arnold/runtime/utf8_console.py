"""Ensure stdout/stderr use UTF-8 on Windows.

On Windows the default console encoding is cp1252 (or similar), which
crashes with ``UnicodeEncodeError`` when the CLI prints Unicode characters
(arrows ``→``, ellipsis ``…``, check marks ``✓``, etc.) that are common
in pipeline descriptions and skill docs.

This module reconfigures ``sys.stdout`` / ``sys.stderr`` to use UTF-8
with ``errors="replace"`` so the CLI never crashes on a Unicode print.
On Unix this is a no-op (stdout is already UTF-8).

Call ``ensure_utf8_console()`` as early as possible in every CLI entry
point — before any ``print()`` runs.
"""

from __future__ import annotations

import sys


def ensure_utf8_console() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows (no-op on Unix)."""
    if sys.platform != "win32":
        return
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        # Python 3.7+ supports reconfigure on TextIOWrapper.
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, TypeError, OSError):
                pass