"""Typed exceptions for external service clients."""

from __future__ import annotations


class FetchNotFoundError(Exception):
    """404, empty result, no hits — log and move on."""


class FetchRetryableError(Exception):
    """Network error, rate limit — retry later."""


class FetchBlockedError(Exception):
    """Cloudflare, CAPTCHA — surface to user."""
