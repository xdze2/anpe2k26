"""ANPE CLI — interactive chat + prospect commands."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.text import Text

from anpe.node_dir import NodeDir

if TYPE_CHECKING:
    from anpe.prospect.pipeline import StepLog

console = Console()

_QUIT_WORDS = {"quit", "exit", "q", "quitter", "au revoir", "bye"}


# ---------------------------------------------------------------------------
# Chat helpers
# ---------------------------------------------------------------------------


def _print_header() -> None:
    console.print()
    console.print(" [bold cyan]ANPE[/] — Assistant Numérique Pour l'Emploi")
    console.print(" [dim]tapez 'quitter' pour quitter[/]")
    console.print()


def _print_assistant(text: str) -> None:
    console.print(f" [bold cyan]ANPE[/]  {text}")
    console.print()


async def _chat_loop() -> None:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML
    from pydantic_ai import AgentStreamEvent, FunctionToolCallEvent, RunContext
    from rich.columns import Columns
    from rich.console import Group
    from rich.live import Live
    from rich.spinner import Spinner

    from anpe.agent import agent
    from anpe.config import settings

    def _print_status(tokens_in: int, tokens_out: int) -> None:
        parts = Text()
        parts.append(f" {tokens_in} → {tokens_out} tokens", style="dim")
        parts.append("   ", style="dim")
        parts.append(settings.mistral_model, style="dim")
        console.print(parts)
        console.print()

    async def _run_agent(user_text: str) -> tuple[str, int, int]:
        tool_lines: list[Text] = []
        spinner = Spinner("dots", style="yellow")

        def _renderable() -> Group:
            spinner_line = Columns([spinner, Text("  en attente…", style="dim")])
            return Group(spinner_line, *tool_lines)

        live = Live(_renderable(), console=console, transient=True, refresh_per_second=12)

        async def _handle_events(
            ctx: RunContext[None], events: AsyncIterable[AgentStreamEvent]
        ) -> None:
            async for event in events:
                if isinstance(event, FunctionToolCallEvent):
                    tool_lines.append(Text(f"   ⟳ {event.part.tool_name}", style="yellow"))
                    live.update(_renderable())

        with live:
            result = await agent.run(user_text, event_stream_handler=_handle_events)

        usage = result.usage()
        return result.output, usage.input_tokens or 0, usage.output_tokens or 0

    _print_header()
    _print_assistant("Bonjour ! Comment puis-je vous aider ?")

    session: PromptSession[str] = PromptSession()
    prompt = HTML("<ansigreen><b> ❯</b></ansigreen> ")

    while True:
        try:
            user_input = (await session.prompt_async(prompt)).strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() in _QUIT_WORDS:
            break

        console.print()
        try:
            output, tokens_in, tokens_out = await _run_agent(user_input)
            _print_assistant(output)
            _print_status(tokens_in, tokens_out)
        except Exception as e:
            console.print(f" [bold red]Erreur[/] {e}")
            console.print()


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """ANPE — Assistant Numérique Pour l'Emploi."""


@cli.command("chat")
def chat() -> None:
    """Start the interactive chat."""
    asyncio.run(_chat_loop())


# ---------------------------------------------------------------------------
# Prospect group
# ---------------------------------------------------------------------------


@cli.group("prospect")
def prospect_group() -> None:
    """Research and enrich prospected companies."""


def _print_step_log(log: StepLog) -> None:
    status_style = {
        "ok": "green",
        "not_relevant": "red",
        "no_data": "yellow",
        "fetch_error": "red",
        "summarize_error": "red",
        "empty_queue": "dim",
    }.get(log.status, "white")

    console.print(f" [dim]node[/]   [bold]{log.node_id}[/]")
    if log.tool:
        console.print(f" [dim]fetched[/] [{log.tool}] {log.target}")
    console.print(f" [dim]status[/] [{status_style}]{log.status}[/]")
    for tool, target in log.new_targets:
        console.print(f" [dim]queued[/] [{tool}] {target}")


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

        fm = node.get_frontmatter()
        name = fm.get("name") or node_id

        pending_tag = f"  [yellow]{pending} pending[/]" if pending else ""

        review = node.get_latest_review()
        reaction_tag = ""
        if review and review.get("reaction"):
            reaction_tag = f"  [dim green]\"{review['reaction']}\"[/]"

        console.print(
            f" [bold]{name}[/]  [{style}]{last_event}[/]"
            f"{pending_tag}{reaction_tag}"
        )


@prospect_group.command("seed")
@click.option("--count", default=10, show_default=True, help="Number of new nodes to create.")
def prospect_seed(count: int) -> None:
    """Pick N new companies from the listing and create prospect nodes.

    Reads user_data/company_listing.csv, skips companies that already have a
    node, and creates up to COUNT new nodes each with an initial DDG target.

    Example: anpe prospect seed --count 5
    """
    from anpe.node_dir import USER_DATA_DIR
    from anpe.prospect.seed import seed_from_listing

    csv_path = USER_DATA_DIR / "company_listing.csv"
    if not csv_path.exists():
        console.print(f" [bold red]Error[/] listing not found: {csv_path}")
        return

    created = seed_from_listing(csv_path, count)

    if not created:
        console.print(" [dim]No new companies to seed (all already have nodes, or listing is empty).[/]")
        return

    for node_id in created:
        console.print(f" [green]created[/] [bold]{node_id}[/]")
    console.print(f"\n [dim]{len(created)} node(s) created.[/]")


@prospect_group.command("run")
@click.argument("node_ids", nargs=-1, metavar="[NODE_ID]...")
@click.option("-n", "budget", default=1, show_default=True,
              help="Total step budget across all nodes.")
@click.option("--all-nodes", is_flag=True, help="Run on all existing nodes.")
@click.option("--until-done", is_flag=True,
              help="Run until all queues empty (ignores -n). Use with caution.")
def prospect_run(
    node_ids: tuple[str, ...], budget: int, all_nodes: bool, until_done: bool
) -> None:
    """Run the prospect pipeline (depth-first, total step budget).

    \b
    anpe prospect run                       1 step, all nodes
    anpe prospect run -n 10                 10 steps total
    anpe prospect run -n 5 node1 node2      5 steps on specific nodes
    anpe prospect run --all-nodes -n 10     explicit node selection
    anpe prospect run --all-nodes --until-done
    """
    from anpe.node_dir import all_node_ids_by_ctime
    from anpe.prospect.pipeline import run_batch

    if node_ids and all_nodes:
        raise click.UsageError("NODE_IDs and --all-nodes are mutually exclusive.")
    if until_done and budget != 1:
        raise click.UsageError("-n and --until-done are mutually exclusive.")

    if all_nodes:
        ids = all_node_ids_by_ctime()
    elif node_ids:
        ids = list(node_ids)
    else:
        ids = all_node_ids_by_ctime()

    if not ids:
        console.print(" [dim]No nodes found.[/]")
        return

    missing = [nid for nid in ids if not NodeDir(nid).exists()]
    if missing:
        for nid in missing:
            console.print(f" [bold red]Error[/] node {nid!r} not found")
        return

    effective_budget = None if until_done else budget

    async def _run() -> None:
        async for log in run_batch(ids, effective_budget):
            if log.status == "empty_queue":
                continue
            _print_step_log(log)
            if log.status == "blocked":
                console.print(" [bold red]blocked[/] — stopping run")

    asyncio.run(_run())


@prospect_group.command("add_target")
@click.argument("node_id")
@click.argument("tool")
@click.argument("keyword")
def add_target(node_id: str, tool: str, keyword: str) -> None:
    """Append a fetch target to a node's queue.

    Example: anpe prospect add_target acme ddg "Acme Corp France"
    """
    from anpe.prospect.registry import FETCH_TOOLS

    if tool not in FETCH_TOOLS:
        raise click.BadParameter(
            f"must be one of {list(FETCH_TOOLS)}", param_hint="TOOL"
        )
    node = NodeDir(node_id)
    if not node.exists():
        console.print(f" [bold red]Error[/] node {node_id!r} not found — use 'prospect seed' to create nodes")
        return
    node.append_target(tool, keyword)
    console.print(f" [dim]node[/] [bold]{node_id}[/]")
    console.print(f" [dim]queued[/] [{tool}] {keyword}")



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


@prospect_group.command("review")
def prospect_review() -> None:
    """Page through summarized nodes and record a reaction.

    Empty enter = skip (can be reviewed again later).
    Any text = saved as reaction to reviews.jsonl.
    q = quit.

    Example: anpe prospect review
    """
    from anpe.prospect.review import run_review

    run_review()


@prospect_group.command("resummarize")
@click.argument("node_ids", nargs=-1, metavar="[NODE_ID]...")
@click.option("--all-nodes", is_flag=True, help="Check all existing nodes.")
def prospect_resummarize(node_ids: tuple[str, ...], all_nodes: bool) -> None:
    """Queue stale summaries for re-summarization on the next run.

    Scans nodes for summarize_done entries whose summarize_version no longer
    matches the current constant (model or prompt changed). Appends a
    resummarize event — the next 'anpe prospect run' will re-summarize them
    without re-fetching.

    \b
    anpe prospect resummarize                  check all nodes
    anpe prospect resummarize node1 node2      check specific nodes
    """
    from anpe.node_dir import all_node_ids_by_ctime
    from anpe.prospect.registry import FETCH_TOOLS

    if node_ids and all_nodes:
        raise click.UsageError("NODE_IDs and --all-nodes are mutually exclusive.")

    ids = list(node_ids) if node_ids else all_node_ids_by_ctime()

    if not ids:
        console.print(" [dim]No nodes found.[/]")
        return

    tool_versions = {slug: tool.version for slug, tool in FETCH_TOOLS.items()}

    total = 0
    for node_id in ids:
        node = NodeDir(node_id)
        if not node.exists():
            console.print(f" [bold red]Error[/] node {node_id!r} not found")
            continue
        stale = node.get_stale_summarize_uids(tool_versions)
        for uid in stale:
            node.mark_resummarize(uid, reason="version_change")
            console.print(f" [dim]node[/] [bold]{node_id}[/]  [yellow]resummarize[/] uid={uid}")
            total += 1

    if total == 0:
        console.print(" [dim]All summaries are up to date.[/]")
    else:
        console.print(f"\n [dim]{total} uid(s) queued for re-summarization.[/]")


@prospect_group.command("eval")
@click.argument("node_ids", nargs=-1, metavar="[NODE_ID]...")
@click.option("-n", "budget", default=1, show_default=True,
              help="Total eval steps across all nodes.")
@click.option("--all-nodes", is_flag=True, help="Run on all existing nodes.")
@click.option("--until-done", is_flag=True,
              help="Run until all eval queues empty (ignores -n).")
def prospect_eval(
    node_ids: tuple[str, ...], budget: int, all_nodes: bool, until_done: bool
) -> None:
    """Run the eval pipeline (score summaries against the user profile).

    \b
    anpe prospect eval                       1 step, all nodes
    anpe prospect eval -n 10                 10 steps total
    anpe prospect eval -n 5 node1 node2      5 steps on specific nodes
    anpe prospect eval --all-nodes --until-done
    """
    from anpe.node_dir import all_node_ids_by_ctime
    from anpe.prospect.eval_pipeline import EvalStepLog, run_eval_batch

    if node_ids and all_nodes:
        raise click.UsageError("NODE_IDs and --all-nodes are mutually exclusive.")
    if until_done and budget != 1:
        raise click.UsageError("-n and --until-done are mutually exclusive.")

    if all_nodes:
        ids = all_node_ids_by_ctime()
    elif node_ids:
        ids = list(node_ids)
    else:
        ids = all_node_ids_by_ctime()

    if not ids:
        console.print(" [dim]No nodes found.[/]")
        return

    missing = [nid for nid in ids if not NodeDir(nid).exists()]
    if missing:
        for nid in missing:
            console.print(f" [bold red]Error[/] node {nid!r} not found")
        return

    _SCORE_STYLE = {
        "good": "green",
        "maybe": "yellow",
        "discard": "red",
        "enrich": "cyan",
    }

    def _print_eval_log(log: EvalStepLog) -> None:
        if log.status == "empty_queue":
            return
        status_style = {"ok": "green", "eval_error": "red", "no_profile": "red",
                        "no_summary": "yellow"}.get(log.status, "white")
        console.print(f" [dim]node[/]   [bold]{log.node_id}[/]")
        if log.score:
            score_style = _SCORE_STYLE.get(log.score, "white")
            console.print(f" [dim]score[/]  [{score_style}]{log.score}[/]  {log.fit}")
        else:
            console.print(f" [dim]status[/] [{status_style}]{log.status}[/]")

    effective_budget = None if until_done else budget

    async def _run() -> None:
        async for log in run_eval_batch(ids, effective_budget):
            _print_eval_log(log)

    asyncio.run(_run())


@prospect_group.command("map")
def prospect_map() -> None:
    """Display a compact map of all nodes (one glyph per node).

    Glyphs by pipeline state:
      ·  pending fetch          (dim)
      !  fetch error            (red)
      ○  fetched, not summarized (cyan)
      ×  summarize error        (red)
      –  not relevant           (yellow)
      ◇  summarized, eval pending (cyan)
      ‼  eval error             (red)
      ∅  eval discarded         (dim)
      ?  eval: enrich           (blue)
      ▪  eval: maybe            (yellow)
      ●  eval: good             (green)
      ✗  eval: discard          (dim red)
    Grey background = user has reviewed the node.

    Example: anpe prospect map
    """
    from anpe.node_dir import all_node_ids_by_ctime

    # (glyph, style, label)
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

        # Derive fetch state from fetch.jsonl
        puts, latest = node._latest_event_per_uid()
        fetch_state = "put"
        if puts:
            last_events = [latest.get(uid, put)["event"] for uid, put in puts.items()]
            # Pick worst/most-advanced state across all uids
            priority = [
                "summarize_done", "summarize_not_relevant",
                "fetch_done", "summarize_error", "fetch_error", "resummarize", "put",
            ]
            # Best state = furthest along the pipeline
            fetch_state = max(last_events, key=lambda e: -priority.index(e) if e in priority else -99)
            # Collapse resummarize → treat like put (pending)
            if fetch_state == "resummarize":
                fetch_state = "put"

        # Map fetch state to display state
        if fetch_state in ("put", "fetch_error", "summarize_error"):
            state = fetch_state
        elif fetch_state == "fetch_done":
            state = "fetch_done"
        elif fetch_state == "summarize_not_relevant":
            state = "summarize_not_relevant"
        elif fetch_state == "summarize_done":
            # Check eval queue
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
    from rich.text import Text

    width = console.width or 80
    cell_width = 2  # glyph + space
    max_cols = (width - 2) // cell_width
    # at least 3 rows
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

    # Counts by state
    console.print()
    counts: dict[str, int] = {}
    for node_id in ids:
        s = _node_state(node_id)
        counts[s] = counts.get(s, 0) + 1

    # Legend — only show states that appear
    legend = Text(" ")
    for key, (glyph, style, label) in _STATES.items():
        if key not in counts:
            continue
        legend.append(glyph, style=style)
        legend.append(f" {label} ({counts[key]})", style="dim")
        legend.append("   ")
    console.print(legend)
    console.print(f" [dim]{len(ids)} nodes total[/]")


@prospect_group.command("reeval")
@click.argument("node_ids", nargs=-1, metavar="[NODE_ID]...")
@click.option("--all-nodes", is_flag=True, help="Check all existing nodes.")
def prospect_reeval(node_ids: tuple[str, ...], all_nodes: bool) -> None:
    """Sync the eval queue: enqueue any summarized node that has no current eval.

    Covers two cases:
    - Never enqueued (summarized before eval existed, or eval was never run).
    - Stale (last eval used an older profile or eval_version).

    Appends a new eval put for each affected node. The next 'anpe prospect eval'
    run picks them up.

    \b
    anpe prospect reeval                  check all nodes
    anpe prospect reeval node1 node2      check specific nodes
    """
    from anpe.node_dir import all_node_ids_by_ctime
    from anpe.profile import active_profile_file
    from anpe.prospect.eval import EVAL_VERSION

    if node_ids and all_nodes:
        raise click.UsageError("NODE_IDs and --all-nodes are mutually exclusive.")

    ids = list(node_ids) if node_ids else all_node_ids_by_ctime()

    if not ids:
        console.print(" [dim]No nodes found.[/]")
        return

    profile_path = active_profile_file()
    if profile_path is None:
        console.print(" [bold red]Error[/] no profile file found — run 'anpe profile update' first")
        return

    total = 0
    for node_id in ids:
        node = NodeDir(node_id)
        if not node.exists():
            console.print(f" [bold red]Error[/] node {node_id!r} not found")
            continue
        sum_file = node.get_latest_sum_file()
        if sum_file is None:
            continue  # not yet summarized — nothing to eval
        if node.is_eval_stale(str(profile_path), EVAL_VERSION):
            node.append_eval_put(f"summarize/{sum_file}", str(profile_path))
            console.print(f" [dim]node[/] [bold]{node_id}[/]  [yellow]queued[/]")
            total += 1

    if total == 0:
        console.print(" [dim]All evals are up to date.[/]")
    else:
        console.print(f"\n [dim]{total} node(s) queued for re-eval.[/]")


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
        fm = node.get_frontmatter()
        name = fm.get("name") or node_id
        parts = [p for p in [fm.get("city"), fm.get("headcount")] if p]
        meta = " · ".join(str(p) for p in parts)
        reaction = review["reaction"]
        summary = node.get_summary_body().strip()
        summary_snippet = " ".join(summary.split())[:150] if summary else ""
        line = f"- [{name}] {meta} — \"{reaction}\""
        if summary_snippet:
            line += f"\n  {summary_snippet}"
        reactions.append(line)

    if not reactions:
        console.print(" [dim]No reactions recorded yet.[/]")
        return

    profile = read_profile()
    profile_block = profile if profile.strip() else "(empty — not yet filled)"

    prompt = f"""\
You are updating a job-search profile based on the user's reactions to company summaries.
Be conservative — only update what the reactions clearly support.
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


@cli.group("bootstrap")
def bootstrap_group() -> None:
    """Generate company listing from SIRENE API."""


@bootstrap_group.command("run")
@click.option("--refresh", is_flag=True, default=False, help="Invalidate cache and re-fetch all pairs.")
def bootstrap_run(refresh: bool) -> None:
    """Build user_data/company_listing.csv from user_profile.yaml.

    Reads user_data/user_profile.yaml from the project root.
    Writes output to user_data/company_listing.csv.
    Re-running is safe — cache is reused unless --refresh is passed.
    """
    import logging
    from pathlib import Path

    from anpe.bootstrap.pipeline import run as bootstrap_pipeline

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    root = Path.cwd()
    profile_path = root / "user_data" / "user_profile.yaml"
    output_path = root / "user_data" / "company_listing.csv"
    cache_dir = root / "cache_data" / "bootstrap_cache"

    if not profile_path.exists():
        raise click.ClickException(f"user_profile.yaml not found at {profile_path}")

    console.print(f" [dim]profile[/] {profile_path}")
    console.print(f" [dim]output[/]  {output_path}")
    if refresh:
        console.print(" [yellow]--refresh: cache will be invalidated[/]")

    count = bootstrap_pipeline(profile_path, output_path, cache_dir, refresh=refresh)
    console.print(f" [bold green]✓[/] {count} companies written to {output_path}")


def run() -> None:
    cli()
