from typing import Dict, List
from elevator.models import Passenger


def _summarize(values: List[int]) -> Dict:
    if not values:
        return {"min": None, "max": None, "avg": None, "count": 0}
    return {
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
        "count": len(values),
    }


def compute_statistics(passengers: List[Passenger]) -> Dict:
    served = [p for p in passengers if p.is_served]

    wait_times = [p.wait_time for p in served if p.wait_time is not None]
    travel_times = [p.travel_time for p in served if p.travel_time is not None]
    total_times = [p.total_time for p in served if p.total_time is not None]

    return {
        "total": len(passengers),
        "served": len(served),
        "unserved": len(passengers) - len(served),
        "wait_time": _summarize(wait_times),
        "travel_time": _summarize(travel_times),
        "total_time": _summarize(total_times),
        "zero_wait_count": sum(1 for p in served if p.wait_time == 0),
        "long_wait_count": sum(1 for p in served if (p.wait_time or 0) > 20),
    }


def _format_statistics(stats: Dict) -> str:
    lines = ["\n" + "=" * 52, "  PASSENGER STATISTICS", "=" * 52]
    lines.append(f"  Total passengers : {stats['total']}")
    lines.append(f"  Served           : {stats['served']}")
    if stats["unserved"]:
        lines.append(f"  Unserved         : {stats['unserved']}  *** WARNING ***")

    for label, key in [
        ("Wait Time   (pickup - request)", "wait_time"),
        ("Travel Time (dropoff - pickup)", "travel_time"),
        ("Total Time  (dropoff - request)", "total_time"),
    ]:
        s = stats[key]
        lines.append(f"\n  {label}:")
        if s["count"]:
            lines.append(f"    Min     : {s['min']}")
            lines.append(f"    Max     : {s['max']}")
            lines.append(f"    Average : {s['avg']:.2f}")
        else:
            lines.append("    No data")

    if stats["served"]:
        lines.append(f"\n  Passengers with zero wait   : {stats['zero_wait_count']}")
        if stats["long_wait_count"]:
            lines.append(f"  Passengers with wait > 20   : {stats['long_wait_count']}")

    lines.append("=" * 52)
    return "\n".join(lines)


def print_statistics(stats: Dict) -> None:
    print(_format_statistics(stats))


def save_statistics(stats: Dict, filepath: str) -> None:
    import os
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_format_statistics(stats))
        f.write("\n")
