"""Allow running as ``python -m arnold_pipelines.megaplan``."""

from arnold.runtime.utf8_console import ensure_utf8_console

ensure_utf8_console()

from arnold_pipelines.megaplan.cli import main
import sys

sys.exit(main())
