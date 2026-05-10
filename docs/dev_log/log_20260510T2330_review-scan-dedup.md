# ReviewStep scan dedup + queue flush/re-put fix

Date: 2026-05-10

## Problem

`anpe jobs stack review` showed duplicate entries for the same node (e.g.
`visiativ_solutions_entreprise_387495799` appearing twice with two different
`summary_uri` values). Root cause: `scan()` iterated over **all** `done`
events for `summarize_ddg`, so if summarize ran twice on the same node it
produced two candidates with distinct content-addressed uids — both passed
`is_done()` and both landed in the queue.

The deeper issue: review's staleness model depends on three inputs
(`summary_uri`, `siren_uri`, `eval_uri`). The scan needed to emit **one
candidate per node** built from the latest of each, not one candidate per
summarize run.

## What changed

### steps/review_step.py

`scan()` rewritten. First pass collects `latest_summary: dict[node_id, uri]`
by iterating `done_events(newest_first=True)` and keeping the first
(= newest) summary uri per node. Second pass builds one candidate per node
from that latest summary uri plus the latest siren and eval outputs.

The content-addressed uid still encodes all three inputs, so any input
changing (new summary, new eval, or both) produces a new uid and surfaces the
node as stale — all three staleness triggers work correctly without any extra
logic.

### engine/queue.py — `put()` re-enqueues after `error_abort`

The idempotency check previously blocked on `SELECT 1 … WHERE uid = ? LIMIT 1`
— any prior event at all. This meant `flush` (which inserts `error_abort`)
permanently blocked re-put of the same uid, making the `flush → scan → put`
reset cycle silently drop everything.

Fixed: the check now reads the **latest** event for the uid. Only active or
completed states (`put`, `claimed`, `error_retry`, `done`) block re-insertion;
`error_abort` is treated as a cleared slot and allows a new `put`.

### engine/queue.py — `pending()` and `claim()` JOIN fixed

The `JOIN events put_ev ON … event = 'put'` matched all `put` rows for a uid.
After a flush + re-put a uid has two `put` rows, causing `pending()` to return
each item twice. Fixed by pinning the join to `MIN(id)` (the first put row).
Same fix applied to both branches of `claim()`.

## Status

84/84 tests pass. Queue has 11 deduplicated pending review items.
