"""Cross-platform advisory file locking — a drop-in ``fcntl`` replacement.

On Unix this is a thin re-export of the stdlib :mod:`fcntl` module, so
behaviour is byte-identical to the original code.  On Windows (where
``fcntl`` does not exist) it implements the same surface — ``flock``,
``LOCK_EX``, ``LOCK_UN``, ``LOCK_NB`` — on top of :mod:`msvcrt.locking`.

The module exposes exactly the names the codebase already uses:

    from arnold.runtime import filelock as fcntl

    fcntl.flock(fd, fcntl.LOCK_EX)            # blocking exclusive lock
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # non-blocking try
    fcntl.flock(fd, fcntl.LOCK_UN)            # release

Windows implementation notes
----------------------------
``msvcrt.locking`` locks a *range of bytes* starting at the current file
pointer, not the whole file.  To approximate ``flock`` (whole-file advisory
lock) we lock byte 0 with a length of 1 and always seek to 0 before
locking/unlocking.  The lock file must contain at least one byte for
``msvcrt.locking`` to succeed, so callers that open with ``O_CREAT`` on an
empty file should use :func:`ensure_lock_file_has_content` (or simply open
in ``"a+"`` / ``"r+"`` mode after ensuring content — see the helpers below).

``msvcrt.locking`` raises ``OSError`` (``errno=EDEADLK``/``EACCES``) when
the lock is held by another process, which maps cleanly to the
``BlockingIOError``/``OSError`` handling the existing call sites already do.
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Platform selection
# ---------------------------------------------------------------------------

_IS_WINDOWS = sys.platform == "win32"

if not _IS_WINDOWS:
    # Unix — re-export the real fcntl so behaviour is identical.
    import fcntl as _fcntl  # noqa: F401  (re-exported below)

    LOCK_EX = _fcntl.LOCK_EX
    LOCK_UN = _fcntl.LOCK_UN
    LOCK_NB = _fcntl.LOCK_NB
    LOCK_SH = _fcntl.LOCK_SH

    def flock(fd: int, operation: int) -> None:
        """Delegate to :func:`fcntl.flock` on Unix."""
        _fcntl.flock(fd, operation)

else:
    # Windows — implement the flock surface over msvcrt.locking.
    import msvcrt

    # Constants mirroring fcntl's API.  These are our own definitions
    # (Windows has no fcntl module to read them from) but they are only
    # ever passed back to our own ``flock`` below, so the numeric values
    # just need to be bit-flags that combine the way callers expect.
    LOCK_EX = 0x2
    LOCK_SH = 0x1
    LOCK_NB = 0x4
    LOCK_UN = 0x8

    def flock(fd: int, operation: int) -> None:
        """Whole-file advisory lock over ``msvcrt.locking``.

        ``fd`` is an OS-level file descriptor (as returned by
        :func:`os.open` or ``file.fileno()``).  We lock byte 0 (length 1)
        as a proxy for the whole file, matching the pattern already used
        in ``arnold/agent/hermes_cli/auth.py``.

        ``LOCK_UN`` releases the lock.  ``LOCK_NB`` makes the acquire
        non-blocking (raises ``BlockingIOError`` if held).  Without
        ``LOCK_NB`` we poll with a short sleep until the lock is acquired
        — this mirrors ``fcntl.flock``'s blocking behaviour.
        """
        if operation & LOCK_UN:
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                # Already unlocked / fd not lockable — fcntl.flock(LOCK_UN)
                # is also best-effort on an unlocked fd on some systems.
                pass
            return

        blocking = not (operation & LOCK_NB)
        # msvcrt.locking requires the file to have at least 1 byte and the
        # file pointer at position 0.  Ensure both.
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\x00")
                os.lseek(fd, 0, os.SEEK_SET)
        except OSError:
            pass

        if blocking:
            # Poll until acquired — fcntl.flock blocks in-kernel; msvcrt
            # has no blocking mode, so we spin with a short backoff.
            import time

            while True:
                os.lseek(fd, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    return
                except OSError as exc:
                    if exc.errno not in (13, 36):  # EACCES, EDEADLK
                        raise
                    time.sleep(0.02)
        else:
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                # Map to BlockingIOError so call sites that catch
                # BlockingIOError (the common fcntl pattern) keep working.
                if exc.errno in (13, 36):  # EACCES, EDEADLK
                    raise BlockingIOError(
                        exc.errno, "lock held by another process"
                    ) from exc
                raise


def ensure_lock_file_has_content(path: "os.PathLike[str] | str") -> None:
    """Ensure *path* exists and has at least one byte (Windows requirement).

    On Unix this is a no-op.  On Windows ``msvcrt.locking`` fails on a
    zero-length file, so we write a single space if the file is missing or
    empty.  Callers that open lock files with ``"a+"`` after calling this
    helper are guaranteed a lockable file on both platforms.
    """
    if not _IS_WINDOWS:
        return
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists() or p.stat().st_size == 0:
        p.write_text(" ", encoding="utf-8")


__all__ = [
    "LOCK_EX",
    "LOCK_NB",
    "LOCK_SH",
    "LOCK_UN",
    "ensure_lock_file_has_content",
    "flock",
]