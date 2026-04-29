"""Read/write the user search profile stored in user_data/profile.md."""

from pathlib import Path

_PROFILE_PATH = Path(__file__).parent.parent / "user_data" / "profile.md"

_EMPTY_PROFILE = """\
# Search Profile

## What I'm looking for
(not yet filled)

## Dealbreakers
(not yet filled)

## Context
(not yet filled)
"""

_MAX_WORDS = 400


def read_profile() -> str:
    if not _PROFILE_PATH.exists():
        return ""
    return _PROFILE_PATH.read_text(encoding="utf-8").strip()


def write_profile(content: str) -> str:
    """Write new profile content. Returns a warning string if too long, else empty."""
    word_count = len(content.split())
    _PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PROFILE_PATH.write_text(content.strip() + "\n", encoding="utf-8")
    if word_count > _MAX_WORDS:
        return f"Warning: profile is {word_count} words (limit is {_MAX_WORDS}). Please condense it."
    return ""


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
