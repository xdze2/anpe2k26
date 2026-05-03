"""
Fetch available Mistral models and print a CSV table.

Usage:
    uv run python scripts/list_mistral_models.py
"""

import csv
import sys

import httpx

from anpe.config import settings

FIELDS = ["id", "name", "max_context_length", "aliases", "deprecation",
          "completion_chat", "function_calling", "fine_tuning", "vision"]


def main() -> None:
    resp = httpx.get(
        "https://api.mistral.ai/v1/models",
        headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
        timeout=10,
    )
    resp.raise_for_status()
    models = resp.json()["data"]
    models.sort(key=lambda m: m["id"])

    writer = csv.writer(sys.stdout)
    writer.writerow(FIELDS)
    for m in models:
        caps = m.get("capabilities") or {}
        writer.writerow([
            m.get("id", ""),
            m.get("name") or "",
            m.get("max_context_length", ""),
            "|".join(m.get("aliases") or []),
            m.get("deprecation") or "",
            caps.get("completion_chat", False),
            caps.get("function_calling", False),
            caps.get("fine_tuning", False),
            caps.get("vision", False),
        ])


if __name__ == "__main__":
    main()
