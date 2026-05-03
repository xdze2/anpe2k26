"""Terminal review loop — page through summarized nodes and react."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.padding import Padding
from rich.rule import Rule
from rich.text import Text

from anpe.node_dir import NODES_DIR, NodeDir

console = Console()


def _nodes_to_review() -> list[NodeDir]:
    if not NODES_DIR.exists():
        return []
    dirs = sorted(NODES_DIR.iterdir(), key=lambda p: p.stat().st_ctime)
    nodes = [NodeDir(p.name) for p in dirs if p.is_dir()]
    return [n for n in nodes if n.has_summarize_done() and not n.is_reviewed()]


def _get_next_targets(node: NodeDir) -> list[dict]:  # type: ignore[type-arg]
    """Return new_targets from the latest summarize_done result file."""
    import json

    for ev in reversed(node._load_fetch_events()):
        if ev.get("event") == "summarize_done" and ev.get("result_file"):
            result_path = node._summarize_dir / ev["result_file"]
            if result_path.exists():
                data = json.loads(result_path.read_text(encoding="utf-8"))
                return data.get("new_targets", [])
    return []


def run_review() -> None:
    nodes = _nodes_to_review()
    if not nodes:
        console.print(" [dim]Nothing to review.[/]")
        return

    console.print(f" [dim]{len(nodes)} node(s) to review.  Empty enter = skip.  q = quit.[/]")
    console.print()

    for i, node in enumerate(nodes, 1):
        fm = node.get_frontmatter()
        name = fm.get("name", node.node_id)
        meta_parts = [p for p in [
            fm.get("city"),
            fm.get("headcount") and f"{fm['headcount']} pers.",
            fm.get("naf"),
        ] if p]
        meta = "  ·  ".join(str(p) for p in meta_parts)

        body = node.get_summary_body().strip()

        next_targets = _get_next_targets(node)

        console.print(Rule(f"[bold]{i}/{len(nodes)}[/]  [cyan]{name}[/]  [dim]{meta}[/]"))
        console.print()
        console.print(Padding(Markdown(body), pad=(0, 6)))

        if next_targets:
            console.print()
            targets_text = Text()
            targets_text.append("  next: ", style="dim")
            for j, t in enumerate(next_targets[:3]):
                if j:
                    targets_text.append("  ", style="dim")
                targets_text.append(f"[{t['tool']}] ", style="dim cyan")
                targets_text.append(t["target"][:60], style="dim")
            if len(next_targets) > 3:
                targets_text.append(f"  +{len(next_targets) - 3} more", style="dim")
            console.print(targets_text)

        console.print()

        try:
            reaction = input(" > ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n [dim]Interrupted.[/]")
            return

        if reaction.lower() == "q":
            console.print(" [dim]Quit.[/]")
            return

        node.append_review(reaction)

        if reaction:
            console.print(" [dim]saved.[/]")
        else:
            console.print(" [dim]skipped.[/]")
        console.print()

    console.print(" [green]Review done.[/]")
