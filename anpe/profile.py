"""Read/write the user search profile stored in user_data/."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

_USER_DATA_DIR = Path(__file__).parent.parent / "user_data"

_MAX_WORDS = 400


def _profile_dir() -> Path:
    return _USER_DATA_DIR


def active_profile_file() -> Path | None:
    """Return the Path of the most recent profile_<timestamp>.md, or None."""
    candidates = sorted(_profile_dir().glob("profile_*.md"))
    return candidates[-1] if candidates else None


def read_profile() -> str:
    path = active_profile_file()
    if path is None:
        return ""
    return path.read_text(encoding="utf-8").strip()


def write_profile_snapshot(content: str) -> tuple[Path, str]:
    """Write a new timestamped profile snapshot.

    Returns (path, warning) where warning is non-empty if over word limit.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = _profile_dir() / f"profile_{ts}.md"
    _profile_dir().mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    word_count = len(content.split())
    warning = (
        f"Warning: profile is {word_count} words (limit is {_MAX_WORDS}). Please condense it."
        if word_count > _MAX_WORDS
        else ""
    )
    return path, warning


def profile_system_prompt() -> str:
    content = read_profile()
    if not content:
        return (
            "No search profile exists yet. "
            "At the start of the session, ask the user a few short questions to understand "
            "what kinds of companies or projects they are targeting, then call update_search_profile "
            "to save their answers."
        )
    return f"Here is the user's current search profile:\n\n{content}"
