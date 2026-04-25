"""Windows global dictation hotkeys — stub until a pynput-based agent is implemented."""
from __future__ import annotations

import logging
import sys

_LOG = logging.getLogger("hotkey_agent")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _LOG.info(
        "Voice dictation hotkey agent is not implemented on this platform (%s). Exiting.",
        sys.platform,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
