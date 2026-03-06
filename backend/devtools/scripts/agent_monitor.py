#!/usr/bin/env python3
"""
Live agent monitoring dashboard.

Usage:
    python -m devtools.scripts.agent_monitor              # default: poll every 5s, last 60 min
    python -m devtools.scripts.agent_monitor --interval 3 # poll every 3s
    python -m devtools.scripts.agent_monitor --minutes 30 # only show last 30 min
    python -m devtools.scripts.agent_monitor --once        # single snapshot, no live refresh
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure backend is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def _format_cost(cost: float) -> Text:
    s = f"${cost:.4f}"
    if cost > 0.10:
        return Text(s, style="bold red")
    if cost > 0.01:
        return Text(s, style="yellow")
    return Text(s, style="green")


def _format_duration(ms: int) -> Text:
    if ms > 30000:
        return Text(f"{ms/1000:.1f}s", style="bold red")
    if ms > 10000:
        return Text(f"{ms/1000:.1f}s", style="yellow")
    return Text(f"{ms/1000:.1f}s", style="green")


def _format_tokens(inp: int, out: int) -> str:
    return f"{inp:,} → {out:,}"


def _agent_color(name: str) -> str:
    colors = {
        "InventoryAgent": "green",
        "OpsAgent": "yellow",
        "FinanceAgent": "magenta",
    }
    base = name.split(":", maxsplit=1)[0]
    return colors.get(base, "white")


def _build_stats_panel(stats: dict) -> Panel:
    totals = stats.get("totals", {})
    hours = stats.get("period_hours", 24)
    total_runs = totals.get("total_runs", 0) or 0
    total_cost = totals.get("total_cost", 0) or 0
    total_in = totals.get("total_input_tokens", 0) or 0
    total_out = totals.get("total_output_tokens", 0) or 0
    avg_dur = totals.get("avg_duration_ms", 0) or 0
    total_errors = totals.get("total_errors", 0) or 0

    lines = [
        f"  Runs: [bold]{total_runs}[/]    Errors: [{'red' if total_errors else 'green'}]{total_errors}[/]",
        f"  Cost: [bold]{_format_cost(total_cost)}[/]",
        f"  Tokens: [dim]{total_in:,}[/] in  [dim]{total_out:,}[/] out",
        f"  Avg latency: {avg_dur/1000:.1f}s",
    ]

    return Panel(
        "\n".join(lines),
        title=f"[bold]Totals ({hours}h)[/]",
        border_style="bright_blue",
        width=45,
    )


def _build_agent_breakdown(stats: dict) -> Panel:
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Agent", style="bold")
    table.add_column("Runs", justify="right")
    table.add_column("Tokens (in→out)", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Avg ms", justify="right")
    table.add_column("Errs", justify="right")

    for row in stats.get("by_agent", []):
        name = row.get("agent_name", "?")
        table.add_row(
            Text(name, style=_agent_color(name)),
            str(row.get("runs", 0)),
            _format_tokens(row.get("total_input_tokens", 0) or 0, row.get("total_output_tokens", 0) or 0),
            _format_cost(row.get("total_cost", 0) or 0),
            str(int(row.get("avg_duration_ms", 0) or 0)),
            Text(str(row.get("errors", 0) or 0), style="red" if row.get("errors") else "green"),
        )

    return Panel(table, title="[bold]By Agent[/]", border_style="bright_blue")


def _build_runs_table(runs: list[dict]) -> Panel:
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Time", width=8)
    table.add_column("Agent", width=16)
    table.add_column("Mode", width=5)
    table.add_column("Tokens", justify="right", width=18)
    table.add_column("Cost", justify="right", width=9)
    table.add_column("Dur", justify="right", width=7)
    table.add_column("Tools", width=30)
    table.add_column("Msg", width=40, no_wrap=True)
    table.add_column("Status", width=7)

    for r in runs:
        created = r.get("created_at", "")
        try:
            t = datetime.fromisoformat(created)
            time_str = t.strftime("%H:%M:%S")
        except (ValueError, TypeError):
            time_str = created[:8] if created else "?"

        agent_name = r.get("agent_name", "?")
        tool_calls = r.get("tool_calls", "[]")
        if isinstance(tool_calls, str):
            try:
                tool_calls = json.loads(tool_calls)
            except (json.JSONDecodeError, TypeError):
                tool_calls = []

        tools_str = ", ".join(tc.get("tool", "?") for tc in tool_calls) if tool_calls else "-"
        if len(tools_str) > 30:
            tools_str = tools_str[:27] + "..."

        msg = (r.get("user_message") or "")[:40]
        error = r.get("error")
        status = Text("ERR", style="bold red") if error else Text("OK", style="green")

        table.add_row(
            time_str,
            Text(agent_name, style=_agent_color(agent_name)),
            r.get("mode", "fast"),
            _format_tokens(r.get("input_tokens", 0), r.get("output_tokens", 0)),
            _format_cost(r.get("cost_usd", 0)),
            _format_duration(r.get("duration_ms", 0)),
            tools_str,
            Text(msg, style="dim"),
            status,
        )

    return Panel(table, title=f"[bold]Recent Runs ({len(runs)})[/]", border_style="bright_blue")


def _build_display(stats: dict, runs: list[dict]) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=1),
        Layout(name="top", size=10),
        Layout(name="runs"),
    )
    layout["header"].update(
        Text(f" SKU-Ops Agent Monitor  •  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style="bold white on blue")
    )
    layout["top"].split_row(
        Layout(_build_stats_panel(stats), name="stats", ratio=1),
        Layout(_build_agent_breakdown(stats), name="agents", ratio=2),
    )
    layout["runs"].update(_build_runs_table(runs))
    return layout


async def _fetch_data(minutes: int, limit: int) -> tuple[dict, list[dict]]:
    from assistant.infrastructure.agent_run_repo import get_stats, list_runs
    stats = await get_stats(hours=max(1, minutes // 60) or 1)
    runs = await list_runs(minutes=minutes, limit=limit)
    return stats, runs


async def _run(interval: int, minutes: int, limit: int, once: bool):
    from shared.infrastructure.database import close_db, init_db
    await init_db()

    try:
        if once:
            stats, runs = await _fetch_data(minutes, limit)
            console.print(_build_display(stats, runs))
            return

        with Live(console=console, refresh_per_second=1, screen=True) as live:
            while True:
                try:
                    stats, runs = await _fetch_data(minutes, limit)
                    live.update(_build_display(stats, runs))
                except Exception as e:
                    live.update(Panel(f"Error fetching data: {e}", style="red"))
                await asyncio.sleep(interval)
    finally:
        await close_db()


def main():
    parser = argparse.ArgumentParser(description="Live agent monitoring dashboard")
    parser.add_argument("--interval", type=int, default=5, help="Refresh interval in seconds (default: 5)")
    parser.add_argument("--minutes", type=int, default=60, help="Show runs from last N minutes (default: 60)")
    parser.add_argument("--limit", type=int, default=30, help="Max runs to show (default: 30)")
    parser.add_argument("--once", action="store_true", help="Single snapshot, no live refresh")
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.interval, args.minutes, args.limit, args.once))
    except KeyboardInterrupt:
        console.print("\n[dim]Monitor stopped.[/]")


if __name__ == "__main__":
    main()
