#!/usr/bin/env python3
"""CLI for fetching futures/perp position tiers from OKX, Binance, Bybit."""

import json
import sys

import click
from tabulate import tabulate

from exchanges import okx_fetch_instruments
from tiers import get_all_position_tiers, get_position_tiers, refresh_cache


def _format_number(n: float) -> str:
    if n == 0:
        return "0"
    if n >= 1_000_000:
        return f"{n:,.0f}"
    if n >= 1:
        return f"{n:,.2f}"
    return f"{n:.6f}"


def _print_tiers(tiers: list[dict], symbol: str) -> None:
    if not tiers:
        click.echo(f"No tiers found for {symbol}")
        return

    unit = tiers[0].get("unit", "")
    headers = [
        "Tier",
        f"Min Size ({unit})",
        f"Max Size ({unit})",
        "MMR",
        "IMR",
        "Max Leverage",
    ]
    rows = [
        [
            t["tier"],
            _format_number(t["min_size"]),
            _format_number(t["max_size"]),
            f"{t['mmr']:.4%}",
            f"{t['imr']:.4%}",
            f"{t['max_leverage']:.0f}x",
        ]
        for t in tiers
    ]
    click.echo(f"\n  {symbol}")
    click.echo(tabulate(rows, headers=headers, tablefmt="simple"))
    click.echo()


@click.group()
def cli():
    """Fetch futures/perp position tiers from OKX, Binance, Bybit."""


@cli.command("instruments")
@click.option(
    "--type",
    "inst_type",
    type=click.Choice(["SWAP", "FUTURES"], case_sensitive=False),
    default="SWAP",
    help="Instrument type (SWAP=perps, FUTURES=dated futures)",
)
@click.option("--json-output", is_flag=True, help="Output raw JSON")
def instruments_cmd(inst_type: str, json_output: bool):
    """List all OKX futures/perp instruments."""
    data = okx_fetch_instruments(inst_type.upper())
    live = [d for d in data if d["state"] == "live"]

    if json_output:
        click.echo(json.dumps(live, indent=2))
        return

    headers = ["instId", "ctType", "ctVal", "ctValCcy", "settleCcy", "maxLever", "lotSz"]
    rows = [[d.get(h, "") for h in headers] for d in live]
    click.echo(f"\nOKX {inst_type.upper()} instruments ({len(live)} live):\n")
    click.echo(tabulate(rows, headers=headers, tablefmt="simple"))
    click.echo()


@cli.command("tiers")
@click.argument("exchange", type=click.Choice(["okx", "binance", "bybit"], case_sensitive=False))
@click.argument("symbol")
@click.option(
    "--unit",
    type=click.Choice(["usd", "coin", "contracts"], case_sensitive=False),
    default="usd",
    help="Unit for position sizes (default: usd)",
)
@click.option("--json-output", is_flag=True, help="Output raw JSON")
def tiers_cmd(exchange: str, symbol: str, unit: str, json_output: bool):
    """Get position tiers for a specific instrument.

    \b
    Examples:
      python cli.py tiers okx BTC-USDT-SWAP
      python cli.py tiers binance BTCUSDT --unit usd
      python cli.py tiers bybit BTCUSDT --unit coin
      python cli.py tiers okx ETH-USD-SWAP --unit contracts
    """
    tiers = get_position_tiers(exchange.lower(), symbol, unit.lower())

    if json_output:
        click.echo(json.dumps(tiers, indent=2))
        return

    _print_tiers(tiers, f"{exchange.upper()} {symbol}")


@cli.command("all-tiers")
@click.argument("exchange", type=click.Choice(["okx", "binance", "bybit"], case_sensitive=False))
@click.option(
    "--unit",
    type=click.Choice(["usd", "coin", "contracts"], case_sensitive=False),
    default="usd",
    help="Unit for position sizes (default: usd)",
)
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.option("--limit", default=0, help="Max number of instruments to show (0=all)")
def all_tiers_cmd(exchange: str, unit: str, json_output: bool, limit: int):
    """Get position tiers for ALL instruments on an exchange.

    \b
    Examples:
      python cli.py all-tiers okx --unit usd
      python cli.py all-tiers bybit --unit coin --limit 5
      python cli.py all-tiers binance --json-output
    """
    click.echo(f"Fetching all tiers from {exchange.upper()}... (this may take a while)")
    all_data = get_all_position_tiers(exchange.lower(), unit.lower())

    if json_output:
        click.echo(json.dumps(all_data, indent=2))
        return

    symbols = sorted(all_data.keys())
    if limit > 0:
        symbols = symbols[:limit]

    click.echo(f"\n{exchange.upper()}: {len(all_data)} instruments total, showing {len(symbols)}\n")
    for sym in symbols:
        _print_tiers(all_data[sym], f"{exchange.upper()} {sym}")


@cli.command("refresh-cache")
@click.argument("exchange", type=click.Choice(["okx", "binance", "bybit"], case_sensitive=False))
@click.option(
    "--unit",
    type=click.Choice(["usd", "coin", "contracts"], case_sensitive=False),
    default="usd",
    help="Unit for position sizes (default: usd)",
)
def refresh_cache_cmd(exchange: str, unit: str):
    """Fetch fresh data from exchange and update local cache.

    \b
    Examples:
      python cli.py refresh-cache okx
      python cli.py refresh-cache binance --unit usd
      python cli.py refresh-cache bybit --unit coin
    """
    click.echo(f"Refreshing cache for {exchange.upper()} (unit={unit})...")
    refresh_cache(exchange.lower(), unit.lower())
    click.echo("Cache refreshed.")


if __name__ == "__main__":
    cli()
