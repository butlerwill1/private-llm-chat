"""Local-file implementation for optional private conversation instructions."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FileConversationInstructionsProvider:
    """Read a local instructions file once; its contents are never logged."""

    def __init__(self, path: Path | None) -> None:
        self._instructions: str | None = None
        if path is None:
            return
        try:
            content = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            logger.warning("Conversation instructions file is unavailable; starting without it")
            return
        if content:
            self._instructions = content
        else:
            logger.warning("Conversation instructions file is empty; starting without it")

    def instructions(self) -> str | None:
        return self._instructions
