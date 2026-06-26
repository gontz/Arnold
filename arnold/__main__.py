"""Allow running as ``python -m arnold``."""

from arnold.runtime.utf8_console import ensure_utf8_console

ensure_utf8_console()

from arnold.cli import main

raise SystemExit(main())
