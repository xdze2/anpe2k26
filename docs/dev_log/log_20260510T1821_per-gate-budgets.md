# Per-rate-gate budgets in the runner

Date: 2026-05-10

## What changed

Replaced the blunt `--budget=N` (items processed) with a proper gate-level budget
system that matches how the user actually thinks about cost.

### engine/rate_gate.py

- `RateGate` gains `set_budget(n: int)` and a `_remaining: int | None` counter.
- Decremented atomically inside the existing lock on every `acquire()`.
- When it reaches zero, `acquire()` raises `BudgetExhausted` (new exception).
- Gates now take an optional `name=` kwarg used in the exception message.

### engine/runner.py

- `BudgetExhausted` caught as a clean stop: item is marked `error_retry` (stays
  in queue for next session), worker returns silently — not counted as an error.
- Race condition fixed: two consecutive `async with self._lock` blocks (budget
  check + `skip_uids` snapshot) collapsed into one atomic block so no worker
  can slip in between.

### steps/api_throttles.py

- Added `name=` to each gate (`"mistral"`, `"ddg"`, `"siren"`).

### cli.py

- `--budget` renamed to `--gate-budget NAME=N` (repeatable) on both `run` and
  `step`. Parsed by `_apply_gate_budgets()` which calls `gate.set_budget()` on
  the matching singleton before the runner starts.
- Old item-count meaning moved to `--max-items` on both commands.

## Budget model

| Option | Cuts at | Semantics |
|---|---|---|
| `--gate-budget mistral=50` | `RateGate.acquire()` | "spend at most 50 Mistral calls this session" |
| `--max-items=10` | runner claim loop | hard cap on total items completed, any gate |

Gate-budgeted items are left retryable in the queue; `--max-items` items that
weren't reached are simply never claimed.

## Usage

```
anpe run --gate-budget mistral=50
anpe run --gate-budget mistral=50 --gate-budget ddg=200
anpe step eval --gate-budget mistral=50 --max-items=10
```

## Status

84/84 tests pass.
