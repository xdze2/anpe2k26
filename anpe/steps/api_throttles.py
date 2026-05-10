"""Shared RateGate instances — one per external service.

Import the relevant instance and assign it to `rate_gate` on the step class.
Steps sharing the same external quota (e.g. summarize_ddg and eval both hit
Mistral) share the same instance, so they are throttled as a group.
"""

from anpe.engine.rate_gate import NoGate, RateGate

# Mistral via OpenRouter — free tier is ~30 req/min → 1 call per 2 s
MISTRAL: RateGate = RateGate(min_interval_s=2.0, name="mistral")

# DuckDuckGo scraping — no published limit, conservative 1 call per 1 s
DDG: RateGate = RateGate(min_interval_s=1.0, name="ddg")

# Recherche Entreprises API — public API, 1 call per 1 s
SIREN: RateGate = RateGate(min_interval_s=1.0, name="siren")

# Alias for steps with no external rate limit (pure I/O, local ops)
NONE: NoGate = NoGate()
