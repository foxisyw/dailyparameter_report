#!/usr/bin/env python3
"""OKX Instrument Tagger CLI — tag instruments by predefined rules.

JSON on stdout, progress/status on stderr.
Shows hints on first call; results on subsequent calls within 5 minutes.
"""

import json
import re
import sys
import time
from pathlib import Path

import click

from tagger import (
    get_all_tagged,
    get_tagged_by_ids,
    get_tagged_by_tag,
    list_rules,
    refresh_cache as do_refresh_cache,
    CACHE_DIR,
)

HINTS_FILE = Path(__file__).parent / "hints.md"
LAST_CALL_FILE = CACHE_DIR / ".last_call.json"
HINTS_TTL = 300  # 5 minutes


# ─────────────── Hints system ───────────────


def _get_last_call(command: str) -> float:
    try:
        with open(LAST_CALL_FILE) as f:
            return json.load(f).get(command, 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0


def _set_last_call(command: str):
    data = {}
    try:
        with open(LAST_CALL_FILE) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    data[command] = time.time()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LAST_CALL_FILE, "w") as f:
        json.dump(data, f)


def _get_hints(section: str) -> str | None:
    if not HINTS_FILE.exists():
        return None
    content = HINTS_FILE.read_text()
    pattern = rf"^# {re.escape(section)}\s*\n(.*?)(?=^# |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _check_hints(command: str) -> bool:
    """If command wasn't called in the last 5 minutes, output hints and return True."""
    now = time.time()
    if now - _get_last_call(command) > HINTS_TTL:
        hints = _get_hints(command)
        if hints:
            _out({
                "STATUS": "HINTS_ONLY",
                "command": command,
                "message": hints,
            })
        _set_last_call(command)
        return bool(hints)
    _set_last_call(command)
    return False


def _out(data, pretty: bool = True):
    """Write JSON to stdout."""
    if pretty:
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        click.echo(json.dumps(data, ensure_ascii=False))


def _error(msg: str, code: int = 1):
    _out({"STATUS": "ERROR", "message": msg})
    sys.exit(code)


# ─────────────── CLI ───────────────


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """OKX Instrument Tagger — tag instruments by predefined rules."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(help_cmd)


@cli.command("help")
def help_cmd():
    """Show workflows and method list."""
    _out({
        "STATUS": "OK",
        "tool": "OKX Instrument Tagger",
        "workflows": {
            "Tag all instruments": "refresh-cache → get-all",
            "Tag specific instruments": "refresh-cache → get [INST_IDS...]",
            "Filter by tag": "refresh-cache → filter-by-tag TAG_NAME",
            "List available rules": "list-rules",
        },
        "methods": {
            "help": "Show workflows and method list",
            "get-all": "Get all instruments with tags (from cache)",
            "get": "Get specified instruments with tags (from cache)",
            "filter-by-tag": "Get all instruments matching a specific tag",
            "list-rules": "List all predefined tagging rules",
            "refresh-cache": "Re-fetch instruments from OKX API",
        },
        "notes": [
            "Data is served from local cache. Run refresh-cache first if cache is empty or stale.",
            "First call to any method returns hints only. Call again within 5 minutes for actual results.",
        ],
    })


@cli.command("get-all")
@click.option("--type", "inst_type", type=click.Choice(["SPOT", "SWAP", "FUTURES", "all"], case_sensitive=False), default="all")
@click.option("--limit", default=0, help="Max rows (0=all)")
@click.option("--live-only", is_flag=True, default=False, help="Only include live instruments")
def get_all_cmd(inst_type: str, limit: int, live_only: bool):
    """Get all instruments with tags applied."""
    if _check_hints("getAll"):
        return

    data = get_all_tagged()
    if live_only:
        data = [d for d in data if d.get("state") == "live"]
    if inst_type.lower() != "all":
        data = [d for d in data if d["instType"] == inst_type.upper()]
    if limit > 0:
        data = data[:limit]
    _out({"STATUS": "OK", "count": len(data), "data": data})


@cli.command("get")
@click.argument("inst_ids", nargs=-1, required=True)
def get_cmd(inst_ids: tuple[str, ...]):
    """Get specified instruments with tags."""
    if _check_hints("get"):
        return

    data = get_tagged_by_ids(list(inst_ids))
    found_ids = {d["instId"] for d in data}
    missing = [i for i in inst_ids if i not in found_ids]
    result = {"STATUS": "OK", "count": len(data), "data": data}
    if missing:
        result["missing"] = missing
    _out(result)


@cli.command("filter-by-tag")
@click.argument("tag_name")
@click.option("--limit", default=0, help="Max rows (0=all)")
def filter_by_tag_cmd(tag_name: str, limit: int):
    """Get all instruments matching a specific tag."""
    if _check_hints("filterByTag"):
        return

    data = get_tagged_by_tag(tag_name)
    if limit > 0:
        data = data[:limit]
    _out({"STATUS": "OK", "tag": tag_name, "count": len(data), "data": data})


@cli.command("list-rules")
def list_rules_cmd():
    """List all predefined tagging rules."""
    if _check_hints("listRules"):
        return

    rules = list_rules()
    _out({"STATUS": "OK", "count": len(rules), "rules": rules})


@cli.command("refresh-cache")
def refresh_cache_cmd():
    """Re-fetch instruments from OKX API and rebuild cache."""
    if _check_hints("refreshCache"):
        return

    result = do_refresh_cache()
    _out({"STATUS": "OK", **result})


if __name__ == "__main__":
    cli()
