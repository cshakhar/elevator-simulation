import math
from typing import Dict, List, Optional

from elevator.models import Passenger

LONG_WAIT_THRESHOLD = 20
_WAIT_BUCKETS: List[tuple] = [(0, 5), (6, 20), (21, 50), (51, None)]
_WIDTH = 60


def _percentile(sorted_vals: List[int], pct: float) -> float:
    # Fractional index into sorted list; linearly interpolate between the two
    # surrounding values so results are smooth rather than step-wise.
    idx = pct / 100 * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def _summarize(values: List[int]) -> Dict:
    if not values:
        return {
            "min": None, "max": None, "avg": None, "median": None,
            "p90": None, "p95": None, "stddev": None, "count": 0,
        }
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    avg = sum(values) / n
    # Population stddev (divide by n, not n-1) — we have the full passenger set,
    # not a sample, so Bessel's correction does not apply.
    stddev = math.sqrt(sum((v - avg) ** 2 for v in values) / n)
    return {
        "min": sorted_vals[0],
        "max": sorted_vals[-1],
        "avg": avg,
        "median": _percentile(sorted_vals, 50),
        "p90": _percentile(sorted_vals, 90),
        "p95": _percentile(sorted_vals, 95),
        "stddev": stddev,
        "count": n,
    }


def compute_statistics(
    passengers: List[Passenger],
    num_elevators: Optional[int] = None,
) -> Dict:
    served = [p for p in passengers if p.is_served]
    total = len(passengers)
    served_count = len(served)

    wait_times   = [p.wait_time   for p in served if p.wait_time   is not None]
    travel_times = [p.travel_time for p in served if p.travel_time is not None]
    total_times  = [p.total_time  for p in served if p.total_time  is not None]

    zero_wait  = sum(1 for p in served if p.wait_time == 0)
    long_wait  = sum(1 for p in served if (p.wait_time or 0) > LONG_WAIT_THRESHOLD)

    wait_buckets: Dict[str, int] = {}
    for lo, hi in _WAIT_BUCKETS:
        label = f"{lo}-{hi} ticks" if hi is not None else f"{lo}+ ticks"
        wait_buckets[label] = sum(
            1 for p in served
            if p.wait_time is not None
            and p.wait_time >= lo
            and (hi is None or p.wait_time <= hi)
        )

    elevator_ids = (
        set(range(num_elevators)) if num_elevators is not None
        else {p.assigned_elevator for p in served if p.assigned_elevator is not None}
    )
    per_elevator: Dict[int, Dict] = {}
    for e_id in sorted(elevator_ids):
        e_served = [p for p in served if p.assigned_elevator == e_id]
        e_waits  = [p.wait_time for p in e_served if p.wait_time is not None]
        per_elevator[e_id] = {
            "served":   len(e_served),
            "avg_wait": sum(e_waits) / len(e_waits) if e_waits else None,
        }

    return {
        "total":    total,
        "served":   served_count,
        "unserved": total - served_count,
        "service_rate": served_count / total if total else None,
        "wait_time":    _summarize(wait_times),
        "travel_time":  _summarize(travel_times),
        "total_time":   _summarize(total_times),
        "zero_wait_count":  zero_wait,
        "long_wait_count":  long_wait,
        "long_wait_threshold": LONG_WAIT_THRESHOLD,
        "wait_buckets":  wait_buckets,
        "per_elevator":  per_elevator,
    }


def _pct(count: int, total: int) -> str:
    return f"{count / total * 100:.1f}%" if total else "—"


def _format_time_block(label: str, s: Dict) -> List[str]:
    lines = [f"\n  {label}:"]
    if not s["count"]:
        lines.append("    No data")
        return lines
    lines += [
        f"    Min     : {s['min']:>6} ticks",
        f"    Max     : {s['max']:>6} ticks",
        f"    Average : {s['avg']:>9.2f} ticks",
        f"    Median  : {s['median']:>9.2f} ticks",
        f"    P90     : {s['p90']:>9.2f} ticks",
        f"    P95     : {s['p95']:>9.2f} ticks",
        f"    Std Dev : {s['stddev']:>9.2f} ticks",
    ]
    return lines


def _format_statistics(stats: Dict) -> str:
    sep = "=" * _WIDTH
    thin = "-" * _WIDTH
    lines = ["\n" + sep, "  PASSENGER STATISTICS", sep]

    # --- Service summary ---
    total   = stats["total"]
    served  = stats["served"]
    unserved = stats["unserved"]
    rate    = f" ({_pct(served, total)})" if total else ""
    lines.append(f"  Total passengers : {total}")
    lines.append(f"  Served           : {served}{rate}")
    if unserved:
        lines.append(f"  Unserved         : {unserved} ({_pct(unserved, total)})  *** WARNING ***")

    # --- Time breakdowns ---
    for label, key in [
        ("Wait Time   (pickup - request)",  "wait_time"),
        ("Travel Time (dropoff - pickup)",  "travel_time"),
        ("Total Time  (dropoff - request)", "total_time"),
    ]:
        lines += _format_time_block(label, stats[key])

    # --- Wait time distribution ---
    lines.append(f"\n  Wait Time Distribution:")
    for bucket_label, count in stats["wait_buckets"].items():
        bar = "#" * count
        lines.append(
            f"    {bucket_label:<12} : {count:>3} passengers ({_pct(count, served)})  {bar}"
        )

    # --- Quick-look flags ---
    lines.append(f"\n  Passengers with zero wait               : "
                 f"{stats['zero_wait_count']:>3} ({_pct(stats['zero_wait_count'], served)})")
    lines.append(f"  Passengers with wait > {stats['long_wait_threshold']} ticks (long wait) : "
                 f"{stats['long_wait_count']:>3} ({_pct(stats['long_wait_count'], served)})")

    # --- Per-elevator breakdown ---
    if stats["per_elevator"]:
        lines.append(f"\n  Per-Elevator Breakdown:")
        lines.append(f"  {thin}")
        lines.append(f"  {'Elevator':<12} {'Served':>8} {'Avg Wait':>12}")
        lines.append(f"  {thin}")
        for e_id, data in stats["per_elevator"].items():
            avg_w = f"{data['avg_wait']:.2f} ticks" if data["avg_wait"] is not None else "—"
            lines.append(f"  E{e_id:<11} {data['served']:>8} {avg_w:>12}")
        lines.append(f"  {thin}")

    lines.append(sep)
    return "\n".join(lines)


def print_statistics(stats: Dict) -> None:
    print(_format_statistics(stats))


def save_statistics(stats: Dict, filepath: str) -> None:
    import os
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_format_statistics(stats))
        f.write("\n")
