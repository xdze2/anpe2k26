"""ANPE CLI."""

from __future__ import annotations

import asyncio
import json
import sys

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.padding import Padding
from rich.rule import Rule
from rich.text import Text

from anpe.node_dir import NodeDir

console = Console()


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """ANPE -- Assistant Numerique Pour l'Emploi."""


# ---------------------------------------------------------------------------
# Prospect group
# ---------------------------------------------------------------------------


@cli.group("prospect")
def prospect_group() -> None:
    """Research and enrich prospected companies."""



@prospect_group.command("list")
def prospect_list() -> None:
    """List all prospect nodes with their current state.

    Example: anpe prospect list
    """
    from anpe.node_dir import all_node_ids_by_ctime

    ids = all_node_ids_by_ctime()
    if not ids:
        console.print(" [dim]No nodes found.[/]")
        return

    _STATUS_STYLE = {
        "put": "yellow",
        "fetch_done": "cyan",
        "fetch_error": "red",
        "not_found": "red",
        "retryable": "yellow",
        "blocked": "red",
        "summarize_done": "green",
        "summarize_not_relevant": "yellow",
        "summarize_error": "red",
    }

    for node_id in ids:
        node = NodeDir(node_id)
        rows = node.get_fetch_history()

        pending = sum(
            1 for r in rows if r["last_event"] in ("put", "summarize_error")
        )

        last_event = rows[-1]["last_event"] if rows else "empty"
        style = _STATUS_STYLE.get(last_event, "white")

        siren = node.get_siren_meta()
        name = siren.get("name") or node_id

        pending_tag = f"  [yellow]{pending} pending[/]" if pending else ""

        review = node.get_latest_review()
        reaction_tag = ""
        if review and review.get("reaction"):
            reaction_tag = f"  [dim green]\"{review['reaction']}\"[/]"

        eval_tag = ""
        eval_result = node.get_latest_eval_result()
        if eval_result:
            _SCORE_STYLE = {
                "good": "bold green",
                "maybe": "yellow",
                "discard": "dim red",
                "enrich": "cyan",
            }
            score = eval_result.get("score", "")
            score_style = _SCORE_STYLE.get(score, "white")
            fit = eval_result.get("fit", "")
            fit_snippet = fit[:60] + "..." if len(fit) > 60 else fit
            eval_tag = f"  [dim]~[/][{score_style}]{score}[/]  [dim]{fit_snippet}[/]"

        console.print(
            f" [bold]{name}[/]  [{style}]{last_event}[/]"
            f"{pending_tag}{reaction_tag}{eval_tag}"
        )



@prospect_group.command("status")
@click.argument("node_id")
def prospect_status(node_id: str) -> None:
    """Show fetch status and history for a node.

    Example: anpe prospect status acme
    """
    node = NodeDir(node_id)
    if not node.exists():
        console.print(f" [bold red]Error[/] node {node_id!r} not found")
        return

    rows = node.get_fetch_history()
    if not rows:
        console.print(f" [dim]node[/] [bold]{node_id}[/]  [dim](no fetch history)[/]")
        return

    console.print(f" [dim]node[/] [bold]{node_id}[/]")
    console.print()

    _STATUS_STYLE = {
        "put": "yellow",
        "fetch_done": "cyan",
        "fetch_error": "red",
        "not_found": "red",
        "retryable": "yellow",
        "blocked": "red",
        "summarize_done": "green",
        "summarize_not_relevant": "yellow",
        "summarize_error": "red",
    }

    for row in rows:
        style = _STATUS_STYLE.get(row["last_event"], "white")
        target_display = row["target"][:50]
        ts = row["put_ts"][:16].replace("T", " ") if row["put_ts"] else ""
        console.print(
            f" [dim]{row['uid']}[/]  [bold]{row['tool']}[/]  {target_display}"
            f"  [{style}]{row['last_event']}[/]  [dim]{ts}[/]"
        )


@prospect_group.command("show")
@click.argument("node_id")
def prospect_show(node_id: str) -> None:
    """Show full summary and eval result for a node.

    Example: anpe prospect show acme_123456789
    """
    node = NodeDir(node_id)
    if not node.exists():
        console.print(f" [bold red]Error[/] node {node_id!r} not found")
        return

    siren = node.get_siren_meta()
    name = siren.get("name") or node_id
    meta_parts = [p for p in [
        siren.get("city"),
        siren.get("headcount") and f"{siren['headcount']} pers.",
        siren.get("naf"),
        siren.get("siren"),
    ] if p]
    meta = "  .  ".join(str(p) for p in meta_parts)

    console.print(Rule(f"[bold]{name}[/]  [dim]{meta}[/]"))

    body = node.get_latest_summary().strip()
    if body:
        console.print()
        console.print(Padding(Markdown(body), pad=(0, 4)))
    else:
        console.print()
        console.print(" [dim]No summary yet.[/]")

    eval_result = node.get_latest_eval_result()
    if eval_result:
        _SCORE_STYLE = {
            "good": "bold green",
            "maybe": "yellow",
            "discard": "dim red",
            "enrich": "cyan",
        }
        score = eval_result.get("score", "")
        score_style = _SCORE_STYLE.get(score, "white")
        console.print()
        console.print(Rule("[dim]eval[/]"))
        uncertainty = eval_result.get("uncertainty", "")
        console.print(f" score: [{score_style}]{score}[/]  uncertainty: [dim]{uncertainty}[/]")
        if eval_result.get("fit"):
            console.print(f" fit:   [dim]{eval_result['fit']}[/]")
        dealbreakers = eval_result.get("dealbreakers", [])
        if dealbreakers:
            console.print(" dealbreakers:")
            for db in dealbreakers:
                console.print(f"   [dim red]. {db}[/]")

    next_targets = node.get_next_targets()
    if next_targets:
        console.print()
        console.print(Rule("[dim]next targets[/]"))
        for t in next_targets:
            console.print(f"   [dim cyan][{t['tool']}][/] [dim]{t['target']}[/]")

    review = node.get_latest_review()
    if review and review.get("reaction"):
        console.print()
        console.print(f" reaction: [dim green]\"{review['reaction']}\"[/]")

    console.print()


@prospect_group.command("review")
def prospect_review() -> None:
    """Page through summarized nodes and record a reaction.

    Empty enter = skip (can be reviewed again later).
    Any text = saved as reaction to reviews.jsonl.
    q = quit.

    Example: anpe prospect review
    """
    # TODO: wire to ReviewStep via runner (prospect/review.py removed)
    from rich.console import Console
    Console().print("[yellow]review command not yet wired to ReviewStep[/]")



@prospect_group.command("map")
def prospect_map() -> None:
    """Display a compact map of all nodes (one glyph per node).

    Glyphs by pipeline state:
      .  pending fetch          (dim)
      !  fetch error            (red)
      o  fetched, not summarized (cyan)
      x  summarize error        (red)
      -  not relevant           (yellow)
      <> summarized, eval pending (cyan)
      !! eval error             (red)
      0  eval discarded         (dim)
      ?  eval: enrich           (blue)
      *  eval: maybe            (yellow)
      @  eval: good             (green)
      X  eval: discard          (dim red)
    Grey background = user has reviewed the node.

    Example: anpe prospect map
    """
    from anpe.node_dir import all_node_ids_by_ctime

    _STATES: dict[str, tuple[str, str, str]] = {
        "put":                   ("·", "dim",          "pending fetch"),
        "fetch_error":           ("!", "bold red",      "fetch error"),
        "fetch_done":            ("○", "cyan",          "fetched"),
        "summarize_error":       ("×", "bold red",      "summarize error"),
        "summarize_not_relevant":("–", "yellow",        "not relevant"),
        "summarize_pending_eval":("◇", "cyan",          "summarized, eval pending"),
        "eval_error":            ("‼", "bold red",      "eval error"),
        "eval_discarded":        ("∅", "dim",           "eval discarded"),
        "eval_enrich":           ("?", "bold blue",     "eval: enrich"),
        "eval_maybe":            ("▪", "bold yellow",   "eval: maybe"),
        "eval_good":             ("●", "bold green",    "eval: good"),
        "eval_discard":          ("✗", "dim red",       "eval: discard"),
    }

    def _node_state(node_id: str) -> str:
        node = NodeDir(node_id)

        puts, latest = node._latest_event_per_uid()
        fetch_state = "put"
        if puts:
            last_events = [latest.get(uid, put)["event"] for uid, put in puts.items()]
            priority = [
                "summarize_done", "summarize_not_relevant",
                "fetch_done", "summarize_error", "fetch_error", "resummarize", "put",
            ]
            fetch_state = max(last_events, key=lambda e: -priority.index(e) if e in priority else -99)
            if fetch_state == "resummarize":
                fetch_state = "put"

        if fetch_state in ("put", "fetch_error", "summarize_error"):
            state = fetch_state
        elif fetch_state == "fetch_done":
            state = "fetch_done"
        elif fetch_state == "summarize_not_relevant":
            state = "summarize_not_relevant"
        elif fetch_state == "summarize_done":
            last_eval = node._last_eval_event()
            if last_eval is None:
                state = "summarize_pending_eval"
            elif last_eval["event"] == "eval_discarded":
                state = "eval_discarded"
            elif last_eval["event"] == "eval_error":
                state = "eval_error"
            elif last_eval["event"] == "put":
                state = "summarize_pending_eval"
            elif last_eval["event"] == "eval_done":
                result = node.get_latest_eval_result()
                score = result.get("score", "") if result else ""
                state = {
                    "good":    "eval_good",
                    "maybe":   "eval_maybe",
                    "enrich":  "eval_enrich",
                    "discard": "eval_discard",
                }.get(score, "summarize_pending_eval")
            else:
                state = "summarize_pending_eval"
        else:
            state = "put"

        return state

    ids = all_node_ids_by_ctime()
    if not ids:
        console.print(" [dim]No nodes found.[/]")
        return

    import math

    width = console.width or 80
    cell_width = 2
    max_cols = (width - 2) // cell_width
    min_rows = 3
    cols = min(max_cols, math.ceil(len(ids) / min_rows))

    row = Text(" ")
    col_count = 0

    for node_id in ids:
        state = _node_state(node_id)
        glyph, style, _ = _STATES.get(state, ("?", "white", state))

        node = NodeDir(node_id)
        reviewed = node.is_reviewed()
        if reviewed:
            style = style + " on grey23"

        row.append(glyph, style=style)
        row.append(" ", style="on grey23" if reviewed else "")
        col_count += 1

        if col_count >= cols:
            console.print(row)
            row = Text(" ")
            col_count = 0

    if col_count:
        console.print(row)

    console.print()
    counts: dict[str, int] = {}
    for node_id in ids:
        s = _node_state(node_id)
        counts[s] = counts.get(s, 0) + 1

    legend = Text(" ")
    for key, (glyph, style, label) in _STATES.items():
        if key not in counts:
            continue
        legend.append(glyph, style=style)
        legend.append(f" {label} ({counts[key]})", style="dim")
        legend.append("   ")
    console.print(legend)
    console.print(f" [dim]{len(ids)} nodes total[/]")


# ---------------------------------------------------------------------------
# Engine commands — scan / put / run / step / steps
# ---------------------------------------------------------------------------

from anpe.engine.registry import STEPS as _STEPS  # noqa: E402

_KNOWN_STEPS = list(_STEPS)


@cli.command("steps")
def cmd_steps() -> None:
    """List all registered engine steps."""
    for name, step in _STEPS.items():
        console.print(f" [bold]{name}[/]  [dim]{step.version}[/]  {step.description}", crop=False, overflow="ignore")


@cli.command("scan")
@click.argument("step", type=click.Choice(_KNOWN_STEPS))
@click.option("--min-score", default=None, help="(eval) minimum score: discard|enrich|maybe|good")
@click.option("--exclude-reaction", default=None, help="(eval) skip nodes with this reaction")
@click.option("--naf-prefix", default=None, help="(summarize_ddg) filter by NAF code prefix")
@click.option("--refresh", is_flag=True, default=False, help="(bootstrap) invalidate API cache and re-fetch.")
def cmd_scan(
    step: str,
    min_score: str | None,
    exclude_reaction: str | None,
    naf_prefix: str | None,
    refresh: bool,
) -> None:
    """List candidates for STEP as JSON, one per line.

    \b
    anpe scan eval
    anpe scan eval --min-score=maybe
    anpe scan summarize_ddg --naf-prefix=62
    anpe scan fetch_ddg
    anpe scan bootstrap
    anpe scan bootstrap --refresh
    """
    step_obj = _STEPS[step]

    flags: dict[str, object] = {}
    if min_score is not None:
        flags["min_score"] = min_score
    if exclude_reaction is not None:
        flags["exclude_reaction"] = exclude_reaction
    if naf_prefix is not None:
        flags["naf_prefix"] = naf_prefix
    if refresh:
        flags["refresh"] = refresh

    from anpe.engine.queue import Queue
    from anpe.engine.base import Candidate
    from anpe.engine.vault import Vault
    queue = Queue()
    vault = Vault()
    candidates: list[Candidate] = step_obj.scan(queue, vault, **flags)
    queue.close()

    for c in candidates:
        sys.stdout.write(json.dumps({
            "step": c.step,
            "node_id": c.node_id,
            "args": c.args,
            "context": c.context,
        }) + "\n")


@cli.command("put")
def cmd_put() -> None:
    """Read candidates from stdin and enqueue them.

    Reads JSON lines produced by 'anpe scan'. Each line must have
    step, node_id, and args fields.

    \b
    anpe scan eval | anpe put
    """
    from anpe.engine.queue import Queue

    queue = Queue()
    total = 0
    skipped = 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as e:
            console.print(f" [bold red]Error[/] invalid JSON: {e}", file=sys.stderr)
            continue

        step = item.get("step", "")
        node_id = item.get("node_id", "")
        args = item.get("args", {})
        version = _STEPS[step].version if step in _STEPS else "v1"

        before = queue.pending(step)
        uid = queue.put(node_id, step, version, args)
        after = queue.pending(step)

        if len(after) > len(before):
            console.print(f" [green]queued[/]  {step}  {node_id}  [dim]{uid}[/]")
            total += 1
        else:
            skipped += 1

    queue.close()
    console.print(f"\n [dim]{total} item(s) queued, {skipped} already present.[/]")


@cli.command("run")
@click.option("--step", "step_name", default=None, type=click.Choice(_KNOWN_STEPS),
              help="Restrict to one step (default: all).")
@click.option("--budget", default=None, type=int,
              help="Maximum number of items to run.")
def cmd_run(step_name: str | None, budget: int | None) -> None:
    """Drain the queue and execute pending items.

    \b
    anpe run                          drain all steps
    anpe run --step=eval              only eval items
    anpe run --step=fetch_ddg --budget=5
    """
    from anpe.engine.queue import Queue
    from anpe.engine.runner import Runner
    from anpe.engine.vault import Vault

    queue = Queue()
    vault = Vault()
    runner = Runner(list(_STEPS.values()), queue, vault)

    _STATUS_STYLE = {"done": "green", "error_retry": "yellow", "error_abort": "red"}

    async def _run() -> None:
        results = await runner.run_until_empty(step_name=step_name, budget=budget)
        for r in results:
            style = _STATUS_STYLE.get(r.status, "white")
            console.print(f" [{style}]{r.status}[/]  {r.step}  {r.node_id}  [dim]{r.uid}[/]")
            if r.error:
                console.print(f"   [dim red]{r.error}[/]")
        console.print(f"\n [dim]{len(results)} item(s) processed.[/]")

    asyncio.run(_run())
    queue.close()


@cli.command("step")
@click.argument("step_name", metavar="STEP", type=click.Choice(_KNOWN_STEPS))
@click.option("--min-score", default=None, help="(eval) minimum score")
@click.option("--exclude-reaction", default=None, help="(eval) skip nodes with this reaction")
@click.option("--naf-prefix", default=None, help="(summarize_ddg) filter by NAF code prefix")
@click.option("--refresh", is_flag=True, default=False, help="(bootstrap) invalidate API cache and re-fetch.")
@click.option("--budget", default=None, type=int, help="Maximum items to run.")
def cmd_step(
    step_name: str,
    min_score: str | None,
    exclude_reaction: str | None,
    naf_prefix: str | None,
    refresh: bool,
    budget: int | None,
) -> None:
    """Scan + put + run for one step in one command.

    \b
    anpe step bootstrap
    anpe step bootstrap --refresh
    anpe step eval
    anpe step eval --min-score=maybe --budget=10
    anpe step summarize_ddg --naf-prefix=62
    """
    from anpe.engine.queue import Queue
    from anpe.engine.runner import Runner
    from anpe.engine.vault import Vault

    step_obj = _STEPS[step_name]

    flags: dict[str, object] = {}
    if min_score is not None:
        flags["min_score"] = min_score
    if exclude_reaction is not None:
        flags["exclude_reaction"] = exclude_reaction
    if naf_prefix is not None:
        flags["naf_prefix"] = naf_prefix
    if refresh:
        flags["refresh"] = refresh

    queue = Queue()
    vault = Vault()
    candidates = step_obj.scan(queue, vault, **flags)

    if not candidates:
        console.print(" [dim]No candidates.[/]")
        queue.close()
        return

    console.print(f" [dim]{len(candidates)} candidate(s) found.[/]")

    queued = 0
    version = step_obj.version
    force = bool(flags.get("refresh"))
    for c in candidates:
        before = len(queue.pending(step_name))
        queue.put(c.node_id, step_name, version, c.args, force=force)
        after = len(queue.pending(step_name))
        if after > before:
            queued += 1

    console.print(f" [dim]{queued} item(s) queued ({len(candidates) - queued} already present).[/]")

    if queued == 0 and not queue.stale_claims(step_name):
        queue.close()
        return

    runner = Runner(list(_STEPS.values()), queue, vault)

    _STATUS_STYLE = {"done": "green", "error_retry": "yellow", "error_abort": "red"}

    async def _run() -> None:
        results = await runner.run_until_empty(step_name=step_name, budget=budget)
        for r in results:
            style = _STATUS_STYLE.get(r.status, "white")
            console.print(f" [{style}]{r.status}[/]  {r.node_id}  [dim]{r.uid}[/]")
            if r.error:
                console.print(f"   [dim red]{r.error}[/]")
        console.print(f"\n [dim]{len(results)} item(s) processed.[/]")

    asyncio.run(_run())
    queue.close()


# ---------------------------------------------------------------------------
# Jobs group
# ---------------------------------------------------------------------------


@cli.group("jobs")
def jobs_group() -> None:
    """Inspect the engine job queue."""


@jobs_group.command("status")
@click.option("--step", "step_name", default=None, type=click.Choice(_KNOWN_STEPS),
              help="Filter to one step.")
def jobs_status(step_name: str | None) -> None:
    """Show per-step job counts.

    \b
    anpe jobs status
    anpe jobs status --step=eval
    """
    from anpe.engine.queue import Queue

    queue = Queue()
    all_counts = queue.counts()
    queue.close()

    if step_name:
        all_counts = {k: v for k, v in all_counts.items() if k == step_name}

    if not all_counts:
        console.print(" [dim]Queue is empty.[/]")
        return

    from rich.table import Table

    col_events = ["put", "error_retry", "claimed", "done", "error_abort"]
    _COL_LABEL = {
        "put":         "pending",
        "error_retry": "retry",
        "claimed":     "claimed",
        "done":        "done",
        "error_abort": "abort",
    }
    _COL_STYLE = {
        "put":         "yellow",
        "error_retry": "yellow",
        "claimed":     "cyan",
        "done":        "green",
        "error_abort": "red",
    }

    table = Table(box=None, pad_edge=True, show_header=True, header_style="dim")
    table.add_column("step", style="bold", no_wrap=True)
    for ev in col_events:
        table.add_column(_COL_LABEL[ev], justify="right", style=_COL_STYLE[ev])

    total_pending = 0
    for step, counts in sorted(all_counts.items()):
        cells = []
        for ev in col_events:
            n = counts.get(ev, 0)
            cells.append(str(n) if n else "[dim]–[/]")
        table.add_row(step, *cells)
        total_pending += counts.get("put", 0) + counts.get("error_retry", 0)

    console.print(table)
    console.print(f" [dim]{total_pending} pending total[/]")


@jobs_group.command("history")
@click.argument("node_id")
@click.option("--step", "step_name", default=None, type=click.Choice(_KNOWN_STEPS),
              help="Filter to one step.")
def jobs_history(node_id: str, step_name: str | None) -> None:
    """Show all queue events for NODE_ID.

    \b
    anpe jobs history acme_123456789
    anpe jobs history acme_123456789 --step=eval
    """
    from anpe.engine.queue import Queue

    queue = Queue()
    events = queue.node_history(node_id, step=step_name)
    queue.close()

    if not events:
        console.print(f" [dim]No events for node {node_id!r}.[/]")
        return

    _EVENT_STYLE = {
        "put":          "yellow",
        "claimed":      "cyan",
        "done":         "green",
        "error_retry":  "yellow",
        "error_abort":  "red",
    }

    console.print(f" [dim]node[/] [bold]{node_id}[/]")
    console.print()

    for ev in events:
        ts = ev["ts"][:16].replace("T", " ") if ev["ts"] else ""
        style = _EVENT_STYLE.get(ev["event"], "white")
        uid_short = ev["uid"][:8] if ev["uid"] else ""
        detail = ""
        if ev["event"] == "put" and ev["args"]:
            try:
                args = json.loads(ev["args"])
                detail = "  " + "  ".join(f"[dim]{k}=[/]{str(v)[:40]}" for k, v in args.items())
            except Exception:
                pass
        elif ev["event"] == "done" and ev["outputs"]:
            try:
                outputs = json.loads(ev["outputs"])
                detail = "  → " + "  ".join(f"[dim]{k}=[/]{str(v)[:40]}" for k, v in outputs.items())
            except Exception:
                pass
        elif ev["error"]:
            detail = f"  [dim red]{ev['error']}[/]"
        elif ev["worker_id"]:
            detail = f"  [dim]worker={ev['worker_id']}[/]"

        console.print(
            f" [dim]{ts}[/]  [{style}]{ev['event']:<14}[/{style}]"
            f"  [dim]{ev['step']:<16}[/]  [dim]{uid_short}[/]{detail}"
        )

    console.print()


# ---------------------------------------------------------------------------
# Profile group
# ---------------------------------------------------------------------------


@cli.group("profile")
def profile_group() -> None:
    """Manage the user search profile."""


@profile_group.command("update")
@click.option("--dry-run", is_flag=True, default=False, help="Print the LLM prompt without calling the API.")
def profile_update(dry_run: bool) -> None:
    """Synthesize new reactions into an updated search profile.

    With --dry-run, prints the prompt you can paste into a web AI.

    Example: anpe profile update --dry-run
    """
    from anpe.node_dir import all_node_ids_by_ctime
    from anpe.profile import read_profile

    reactions: list[str] = []
    for node_id in all_node_ids_by_ctime():
        node = NodeDir(node_id)
        review = node.get_latest_review()
        if not review or not review.get("reaction"):
            continue
        siren = node.get_siren_meta()
        name = siren.get("name") or node_id
        parts = [p for p in [siren.get("city"), siren.get("headcount")] if p]
        meta = " . ".join(str(p) for p in parts)
        reaction = review["reaction"]
        summary = node.get_latest_summary().strip()
        summary_snippet = " ".join(summary.split())[:150] if summary else ""
        line = f"- [{name}] {meta} -- \"{reaction}\""
        if summary_snippet:
            line += f"\n  {summary_snippet}"
        reactions.append(line)

    if not reactions:
        console.print(" [dim]No reactions recorded yet.[/]")
        return

    profile = read_profile()
    profile_block = profile if profile.strip() else "(empty -- not yet filled)"

    prompt = f"""\
You are updating a job-search profile based on the user's reactions to company summaries.
Be conservative -- only update what the reactions clearly support.
Return the full updated profile text.

Current profile:
{profile_block}

Recent reactions:
{chr(10).join(reactions)}

Update the profile to reflect what these reactions reveal about what the user is and isn't looking for.\
"""

    if dry_run:
        console.print()
        console.print(prompt)
        console.print()
        console.print(f" [dim]{len(reactions)} reaction(s) included.[/]")
    else:
        console.print(" [yellow]Live profile update not yet implemented. Use --dry-run to print the prompt.[/]")



def run() -> None:
    cli()
