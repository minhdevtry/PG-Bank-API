"""Command-line interface for ``pgbank-unofficial``.

Provides the ``pgbank`` command via Typer. Allows users to manage accounts,
query balances, and schedule payments without writing Python code.

Run via:
    $ python -m pgbank_unofficial.cli --help
    $ python -m pgbank_unofficial.cli balance --json
    $ python -m pgbank_unofficial.cli account add --username alice --password xxx --browser-id bid_xxx

Or after install:
    $ pgbank --help
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, Optional

import typer
from rich.console import Console

from pgbank_unofficial.manager import PGBankManager
from pgbank_unofficial.scheduler import (
    AutoPaymentScheduler,
    CronTrigger,
    IntervalTrigger,
    Job,
    TransferAction,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Typer app + shared state
# ──────────────────────────────────────────────────────────────────────────────


app = typer.Typer(
    name="pgbank",
    help="PGBank Unofficial CLI — manage accounts, query balances, and schedule payments.",
    no_args_is_help=True,
    add_completion=False,
)

# Sub-command groups
account_app = typer.Typer(help="Manage PGBank accounts.", no_args_is_help=True)
schedule_app = typer.Typer(help="Manage scheduled payment jobs.", no_args_is_help=True)
app.add_typer(account_app, name="account")
app.add_typer(schedule_app, name="schedule")

# Shared Rich console
_console = Console()


# ──────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ──────────────────────────────────────────────────────────────────────────────


def _build_manager() -> PGBankManager:
    """Construct a :class:`PGBankManager` with the default storage backend."""
    return PGBankManager()


def _format_balance(balance: Any, *, account_label: str) -> str:
    """Format a :class:`Balance` object as a single human-readable line."""
    available = getattr(balance, "available", Decimal("0"))
    total = getattr(balance, "total", Decimal("0"))
    account_number = getattr(balance, "account_number", "—")
    currency = getattr(balance, "currency", "VND") or "VND"
    return (
        f"  {account_label:<24} {account_number}  "
        f"available={_fmt_money(available)}  total={_fmt_money(total)} {currency}"
    )


def _format_balances(balances: dict[str, Any]) -> str:
    """Format a dict of {account_label: Balance} as a multi-line block."""
    if not balances:
        return "  (no accounts registered)\n"
    lines = [f"  {len(balances)} account(s):"]
    for label, bal in balances.items():
        lines.append(_format_balance(bal, account_label=label))
    return "\n".join(lines) + "\n"


def _format_jobs(jobs: list[Any]) -> str:
    """Format a list of scheduled jobs as a multi-line block."""
    if not jobs:
        return ""
    lines = [f"  {len(jobs)} job(s):"]
    for job in jobs:
        next_run = getattr(job, "next_run_at", None) or "—"
        enabled = "enabled" if getattr(job, "enabled", True) else "paused"
        lines.append(f"  • {job.name}  [next: {next_run}]  ({enabled})")
    return "\n".join(lines) + "\n"


def _fmt_money(value: Any) -> str:
    """Format a Decimal as a comma-separated monetary string."""
    if value is None:
        return "—"
    try:
        d = Decimal(str(value))
    except Exception:
        return str(value)
    quantized = d.quantize(Decimal("1"))
    return f"{quantized:,}"


def _emit(
    result: Any,
    *,
    json_mode: bool,
    formatter: Optional[Any] = None,
    console: Optional[Console] = None,
) -> None:
    """Print *result* as JSON or formatted text depending on *json_mode*."""
    con = console or _console
    if json_mode:
        if hasattr(result, "__dict__"):
            payload = {"result": result.__dict__}
        else:
            payload = {"result": str(result)}
        con.print(json.dumps(payload, default=str, ensure_ascii=False, indent=2))
    else:
        if formatter is not None:
            con.print(formatter(result))


def _json_dump(obj: Any) -> str:
    """Serialize *obj* to JSON string with sensible defaults."""
    return json.dumps(obj, default=str, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# Top-level commands
# ──────────────────────────────────────────────────────────────────────────────


@app.command("version")
def version() -> None:
    """Print the pgbank-unofficial version and exit."""
    from pgbank_unofficial import __version__

    _console.print(f"pgbank-unofficial {__version__}")


@app.command("balance")
def balance_cmd(
    account: Optional[str] = typer.Option(
        None, "--account", "-a", help="Account nickname (omit for all)"
    ),
    json_mode: bool = typer.Option(False, "--json", help="Output as JSON for scripting"),
) -> None:
    """Show account balance(s)."""
    mgr = _build_manager()
    nicknames = [account] if account else list(mgr.list_accounts())
    if not nicknames:
        typer.echo("No accounts registered. Use `pgbank account add` first.")
        raise typer.Exit(code=1)

    balances: dict[str, Any] = {}
    for nick in nicknames:
        try:
            client = mgr.get_client(nick)
            balances[nick] = client.get_balance()
        except Exception as exc:
            typer.echo(f"Error fetching balance for {nick}: {exc}", err=True)
            if json_mode:
                _console.print_json(data={"error": str(exc), "account": nick})
            raise typer.Exit(code=2) from exc

    if json_mode:
        payload = {
            nick: {
                "available": str(b.available),
                "total": str(b.total),
                "currency": b.currency,
                "account_number": b.account_number,
                "as_of": str(b.as_of) if hasattr(b, "as_of") else None,
            }
            for nick, b in balances.items()
        }
        _console.print_json(data=payload)
    else:
        _console.print(_format_balances(balances))


# ──────────────────────────────────────────────────────────────────────────────
# account sub-commands
# ──────────────────────────────────────────────────────────────────────────────


@account_app.command("list")
def account_list(
    json_mode: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all registered accounts."""
    mgr = _build_manager()
    nicknames = list(mgr.list_accounts())
    if json_mode:
        _console.print_json(data={"accounts": nicknames})
    else:
        if not nicknames:
            typer.echo("No accounts registered.")
        else:
            for n in nicknames:
                _console.print(f"  • {n}")


@account_app.command("add")
def account_add(
    username: str = typer.Option(..., "--username", "-u", help="PGBank username"),
    password: str = typer.Option(..., "--password", "-p", help="PGBank password", hide_input=True),
    browser_id: str = typer.Option(..., "--browser-id", "-b", help="Pre-obtained BrowserID"),
    nickname: Optional[str] = typer.Option(None, "--nickname", "-n", help="Friendly name"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="HTTP proxy URL (optional)"),
    json_mode: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Register a new PGBank account."""
    mgr = _build_manager()
    nick = nickname or username
    try:
        mgr.add_account(
            nickname=nick,
            username=username,
            password=password,
            browser_id=browser_id,
            proxy=proxy,
        )
    except Exception as exc:
        typer.echo(f"Failed to add account: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_mode:
        _console.print_json(data={"added": nick})
    else:
        _console.print(f"✓ Account '{nick}' added.")


@account_app.command("remove")
def account_remove(
    nickname: str = typer.Argument(..., help="Account nickname to remove"),
    json_mode: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Remove a registered account."""
    mgr = _build_manager()
    try:
        mgr.remove_account(nickname)
    except KeyError as exc:
        typer.echo(f"Account not found: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_mode:
        _console.print_json(data={"removed": nickname})
    else:
        _console.print(f"✓ Account '{nickname}' removed.")


# ──────────────────────────────────────────────────────────────────────────────
# schedule sub-commands
# ──────────────────────────────────────────────────────────────────────────────


@schedule_app.command("list")
def schedule_list(
    json_mode: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all scheduled jobs."""
    scheduler = AutoPaymentScheduler(_build_manager())
    jobs = scheduler.list_jobs()
    if json_mode:
        _console.print_json(
            data=[
                {
                    "id": j.id,
                    "name": j.name,
                    "next_run_at": str(j.next_run_at) if j.next_run_at else None,
                    "enabled": j.enabled,
                }
                for j in jobs
            ]
        )
    else:
        if not jobs:
            typer.echo("No scheduled jobs.")
        else:
            _console.print(_format_jobs(jobs))


@schedule_app.command("add")
def schedule_add(
    name: str = typer.Option(..., "--name", help="Job name"),
    cron: Optional[str] = typer.Option(None, "--cron", help="Cron expression (e.g. '0 9 5 * *')"),
    interval: Optional[int] = typer.Option(
        None, "--interval", help="Interval in seconds between runs"
    ),
    account: str = typer.Option(..., "--account", help="Source account nickname"),
    to: str = typer.Option(..., "--to", help="Destination account number"),
    amount: str = typer.Option(..., "--amount", help="Transfer amount in VND"),
    json_mode: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Schedule a recurring transfer job."""
    if cron is None and interval is None:
        typer.echo("Provide either --cron or --interval.", err=True)
        raise typer.Exit(code=1)

    try:
        amount_decimal = Decimal(amount)
    except Exception as exc:
        typer.echo(f"Invalid amount: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    trigger = CronTrigger(cron) if cron else IntervalTrigger(seconds=interval or 60)

    action = TransferAction(to_account=to, amount=amount_decimal)

    job = Job(name=name, trigger=trigger, action=action, account_nickname=account)
    scheduler = AutoPaymentScheduler(_build_manager())
    job_id = scheduler.add_job(job)
    if json_mode:
        _console.print_json(data={"id": job_id, "name": name})
    else:
        _console.print(f"✓ Scheduled job '{name}' (id={job_id}).")


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


#: Alias for clarity (e.g. ``from pgbank_unofficial import pgbank``)
pgbank = app


def main() -> None:
    """Entry point for ``python -m pgbank_unofficial.cli`` and console script."""
    app()


__all__ = ["app", "pgbank", "main"]


if __name__ == "__main__":
    main()
