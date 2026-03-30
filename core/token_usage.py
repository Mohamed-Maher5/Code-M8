import threading
from collections import defaultdict
from typing import Any, Dict

from rich.table import Table


_lock = threading.Lock()
_stages: Dict[str, Dict[str, int]] = defaultdict(
    lambda: {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_input_tokens": 0,
    }
)


def reset_turn_usage() -> None:
    with _lock:
        _stages.clear()


def record_usage(stage: str, response: Any) -> None:
    usage = getattr(response, "usage_metadata", None) or {}
    if not usage:
        return

    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    total_tokens = int(usage.get("total_tokens", 0) or 0)
    input_details = usage.get("input_token_details", {}) or {}
    cached_read = int(input_details.get("cache_read", 0) or 0)

    with _lock:
        bucket = _stages[stage]
        bucket["calls"] += 1
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        bucket["total_tokens"] += total_tokens
        bucket["cached_input_tokens"] += cached_read


def build_usage_table() -> Table | None:
    with _lock:
        if not _stages:
            return None
        snapshot = dict(_stages)

    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Stage")
    table.add_column("Calls", justify="right")
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Cached", justify="right")

    total_calls = 0
    total_in = 0
    total_out = 0
    total_all = 0
    total_cached = 0

    for stage in sorted(snapshot.keys()):
        item = snapshot[stage]
        total_calls += item["calls"]
        total_in += item["input_tokens"]
        total_out += item["output_tokens"]
        total_all += item["total_tokens"]
        total_cached += item["cached_input_tokens"]
        table.add_row(
            stage,
            str(item["calls"]),
            f"{item['input_tokens']:,}",
            f"{item['output_tokens']:,}",
            f"{item['total_tokens']:,}",
            f"{item['cached_input_tokens']:,}",
        )

    table.add_section()
    table.add_row(
        "TOTAL",
        str(total_calls),
        f"{total_in:,}",
        f"{total_out:,}",
        f"{total_all:,}",
        f"{total_cached:,}",
    )
    return table
