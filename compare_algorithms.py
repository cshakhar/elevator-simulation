#!/usr/bin/env python3
"""
Bonus: compare all three scheduling algorithms on the same request set
and print a side-by-side summary table.

Usage
-----
  python compare_algorithms.py
  python compare_algorithms.py --input data/large_requests.csv --elevators 4
"""
import argparse
import logging
import sys

from elevator.log_filter import RequestIdFilter
from elevator.simulation import ElevatorSimulation

logger = logging.getLogger(__name__)

ALGORITHMS = ["nearest_car", "round_robin", "zone_based"]


def run_all(
    input_file: str,
    num_elevators: int = 3,
    num_floors: int = 60,
    capacity: int = 8,
) -> dict:
    results = {}
    for algo in ALGORITHMS:
        sim = ElevatorSimulation(
            num_elevators=num_elevators,
            num_floors=num_floors,
            capacity=capacity,
            algorithm=algo,
        )
        try:
            requests = sim.load_requests(input_file)
            sim.run(requests)
        except FileNotFoundError:
            logger.error("[%s] FAILED: input file not found: %r", algo, input_file)
            results[algo] = None
            continue
        except Exception as e:
            logger.error("[%s] FAILED: %s", algo, e)
            results[algo] = None
            continue
        stats = sim.get_statistics()
        results[algo] = stats
        try:
            sim.save_position_log(f"output/positions_{algo}.csv")
        except OSError as e:
            logger.warning("[%s] could not save position log: %s", algo, e)
        print(f"  [{algo}] done in {sim.current_time} steps — "
              f"avg total time: {stats['total_time']['avg']:.1f}")
    return results


def print_table(results: dict) -> None:
    col = 14
    metrics = [
        ("Served passengers",  lambda s: s["served"]),
        ("Avg wait time",      lambda s: f"{s['wait_time']['avg']:.2f}" if s['wait_time']['avg'] is not None else "-"),
        ("Max wait time",      lambda s: s["wait_time"]["max"] or "-"),
        ("Avg travel time",    lambda s: f"{s['travel_time']['avg']:.2f}" if s['travel_time']['avg'] is not None else "-"),
        ("Avg total time",     lambda s: f"{s['total_time']['avg']:.2f}" if s['total_time']['avg'] is not None else "-"),
        ("Max total time",     lambda s: s["total_time"]["max"] or "-"),
    ]

    header = f"{'Metric':<32}" + "".join(f"{a:>{col}}" for a in ALGORITHMS)
    sep = "-" * (32 + col * len(ALGORITHMS))
    print("\n" + "=" * (32 + col * len(ALGORITHMS)))
    print("  ALGORITHM COMPARISON")
    print("=" * (32 + col * len(ALGORITHMS)))
    print(header)
    print(sep)
    for label, fn in metrics:
        row = f"{'Metric' if False else label:<32}"
        for a in ALGORITHMS:
            val = "FAILED" if results[a] is None else str(fn(results[a]))
            row += f"{val:>{col}}"
        print(row)
    print(sep)

    available = {a: r for a, r in results.items() if r is not None}
    if available:
        best = min(available, key=lambda a: available[a]["total_time"]["avg"] or float("inf"))
        print(f"\n  Best avg total time: {best}")
    else:
        print("\n  No algorithms completed successfully.")
    print("=" * (32 + col * len(ALGORITHMS)))


def main() -> None:
    p = argparse.ArgumentParser(description="Compare elevator scheduling algorithms")
    p.add_argument("--input", default="data/sample_requests.csv")
    p.add_argument("--elevators", type=int, default=3)
    p.add_argument("--floors", type=int, default=60)
    p.add_argument("--capacity", type=int, default=8)
    p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Logging verbosity (default: WARNING)",
    )
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s [%(request_id)s] %(name)s: %(message)s")
    logging.getLogger().handlers[0].addFilter(RequestIdFilter())

    print(f"Input: {args.input}  |  Elevators: {args.elevators}  "
          f"|  Floors: {args.floors}  |  Capacity: {args.capacity}\n")

    results = run_all(args.input, args.elevators, args.floors, args.capacity)
    print_table(results)
    print("\nPer-algorithm position logs written to output/positions_<algo>.csv")


if __name__ == "__main__":
    main()
