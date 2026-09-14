"""Local-file implementation for optional private conversation instructions."""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

STANDARD_PROMPT = (
    "You are a helpful, thoughtful assistant. Answer clearly and accurately, "
    "acknowledge uncertainty, and adapt to the user's needs."
)


class FileConversationInstructionsProvider:
    """Read a local instructions file once; its contents are never logged."""

    def __init__(self, path: Path | None, modes_dir: Path | None = None) -> None:
        self._modes = {"standard": ("Standard", STANDARD_PROMPT)}
        if modes_dir is not None:
            for file in sorted(modes_dir.glob("*.json")):
                try:
                    value = json.loads(file.read_text(encoding="utf-8-sig"))
                    if (
                        not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", file.stem)
                        or file.stem in {"standard", "local-instructions"}
                        or not isinstance(value, dict)
                        or not isinstance(value.get("label"), str)
                        or not 1 <= len(value["label"].strip()) <= 100
                        or not isinstance(value.get("prompt"), str)
                        or not 1 <= len(value["prompt"].strip()) <= 32_000
                    ):
                        raise ValueError("Invalid local mode")
                    self._modes[file.stem] = (value["label"].strip(), value["prompt"].strip())
                except (OSError, UnicodeError, ValueError):
                    logger.warning("Skipped an unreadable or invalid local prompt mode")
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
            self._modes["local-instructions"] = ("Local instructions", content)
        else:
            logger.warning("Conversation instructions file is empty; starting without it")

    def options(self) -> tuple[dict[str, str], ...]:
        """Expose labels and IDs only, never private prompt text."""
        return tuple({"id": key, "label": value[0]} for key, value in self._modes.items())

    def instructions(self, mode_id: str | None = None) -> str | None:
        if mode_id is None:
            return self._instructions
        if mode_id not in self._modes:
            raise ValueError("The selected prompt mode is unavailable. Choose another mode.")
        return self._modes[mode_id][1]
