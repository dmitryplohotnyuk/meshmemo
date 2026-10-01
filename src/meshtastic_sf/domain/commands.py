"""Reserved chat commands, shared by capture and replay selection."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class HistoryCommand:
    # None means a reserved command with invalid arguments; never archive it.
    hours: int | None


def history_command(payload: bytes) -> HistoryCommand | None:
    text = payload.decode("utf-8", errors="replace").strip()
    parts = text.split()
    if not parts or parts[0].casefold() != "/history":
        return None
    if len(payload) > 237 or len(parts) != 2 or not re.fullmatch(r"[0-9]{1,6}", parts[1]):
        return HistoryCommand(None)
    hours = int(parts[1])
    return HistoryCommand(hours if hours > 0 else None)


def reserved_command(payload: bytes) -> bool:
    parts = payload.decode('utf-8', errors='replace').strip().split()
    return bool(parts and parts[0].casefold() in ('/history', '/channel'))
