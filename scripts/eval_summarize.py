"""
Compare llm_summarize across models and fixtures.

Usage:
    uv run python scripts/eval_summarize.py

Results are printed to stdout and saved to scripts/eval_results/<timestamp>.jsonl
"""

import asyncio
import json
import time
import traceback
from datetime import datetime
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.providers.mistral import MistralProvider

from anpe.config import settings
from anpe.steps.summarize_fn import _SYSTEM, SummarizeResult

MODELS = [
    "ministral-8b-2512",
    "mistral-small-2603",
    "ministral-14b-2512",
    "mistral-medium-2604",
]

CALL_DELAY_S = 3.0  # pause between API calls to stay within per-minute rate limits

FIXTURES_DIR = Path(__file__).parent / "eval_fixtures"

FIXTURES: list[dict] = json.loads((FIXTURES_DIR / "fixtures.json").read_text())


def make_agent(model_slug: str) -> Agent:
    model = MistralModel(
        model_slug,
        provider=MistralProvider(api_key=settings.mistral_api_key),
    )
    return Agent(model, output_type=SummarizeResult, system_prompt=_SYSTEM)


async def run_one(
    agent: Agent, raw_data: str, company_profile: str, previous_summary: str
) -> tuple[SummarizeResult, float]:
    prompt = ""
    if company_profile:
        prompt += f"## Company profile\n\n{company_profile}\n\n"
    if previous_summary:
        prompt += f"## Previous summary\n\n{previous_summary}\n\n"
    prompt += f"## New data\n\n{raw_data}"

    t0 = time.monotonic()
    result = await agent.run(prompt)
    elapsed = time.monotonic() - t0
    return result.output, elapsed


async def main() -> None:
    results_dir = Path(__file__).parent / "eval_results"
    results_dir.mkdir(exist_ok=True)
    out_file = results_dir / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}.jsonl"

    with out_file.open("w") as f:
        for fixture in FIXTURES:
            raw_data = (FIXTURES_DIR / fixture["file"]).read_text()
            print(f"\n{'='*60}")
            print(f"FIXTURE: {fixture['id']}  —  {fixture['note']}")

            for model_slug in MODELS:
                print(f"\n  model: {model_slug}")
                agent = make_agent(model_slug)
                try:
                    result, elapsed = await run_one(
                        agent,
                        raw_data,
                        fixture.get("company_profile", ""),
                        fixture["previous_summary"],
                    )
                    row = {
                        "fixture": fixture["id"],
                        "model": model_slug,
                        "status": result.status,
                        "new_targets": [t.model_dump() for t in result.new_targets],
                        "summary_len": len(result.summary),
                        "elapsed_s": round(elapsed, 2),
                        "summary": result.summary,
                        "error": None,
                    }
                    print(
                        f"    status={result.status}  targets={len(result.new_targets)}  "
                        f"summary_len={len(result.summary)}  elapsed={elapsed:.1f}s"
                    )
                    for t in result.new_targets:
                        print(f"      -> [{t.tool}] {t.target}")
                except Exception:
                    error_msg = traceback.format_exc()
                    row = {
                        "fixture": fixture["id"],
                        "model": model_slug,
                        "status": "ERROR",
                        "new_targets": [],
                        "summary_len": 0,
                        "elapsed_s": None,
                        "summary": "",
                        "error": error_msg,
                    }
                    print(f"    ERROR: {error_msg}")

                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  [delay {CALL_DELAY_S:.0f}s]")
                await asyncio.sleep(CALL_DELAY_S)

    print(f"\n\nResults saved to {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
