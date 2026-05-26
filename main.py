#!/usr/bin/env python3
"""
Elevator System Simulation — entry point.

Examples
--------
  python main.py
  python main.py --elevators 4 --floors 20 --capacity 10
  python main.py --input data/large_requests.csv --algorithm zone_based
  python main.py --input data/large_requests.csv --express --verbose
  python main.py --log-format json --log-level DEBUG
  python main.py --metrics-output output/metrics.csv
"""
import argparse
import logging
import sys

from elevator.core.constants import (
    ALGORITHMS,
    DEFAULT_ALGORITHM,
    DEFAULT_CAPACITY,
    DEFAULT_INPUT_FILE,
    DEFAULT_NUM_ELEVATORS,
    DEFAULT_NUM_FLOORS,
    DEFAULT_OUTPUT_METRICS,
    DEFAULT_OUTPUT_POSITIONS,
    DEFAULT_OUTPUT_STATS,
    EXPRESS_LOBBY_FLOOR,
    EXPRESS_SKIP_HIGH,
)
from elevator.io import load_requests
from elevator.observability.filter import RequestIdFilter
from elevator.observability.formatter import JsonFormatter
from elevator.simulation import ElevatorSimulation

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Elevator System Simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--input", default=DEFAULT_INPUT_FILE,
        help=f"CSV request file  (default: {DEFAULT_INPUT_FILE})",
    )
    p.add_argument(
        "--output", default=DEFAULT_OUTPUT_POSITIONS,
        help=f"Position log output path  (default: {DEFAULT_OUTPUT_POSITIONS})",
    )
    p.add_argument(
        "--stats-output", default=DEFAULT_OUTPUT_STATS,
        help=f"Passenger statistics log path  (default: {DEFAULT_OUTPUT_STATS})",
    )
    p.add_argument(
        "--metrics-output", default=None, metavar="PATH",
        help=f"Write per-tick metrics CSV to PATH  (e.g. {DEFAULT_OUTPUT_METRICS}); omit to skip",
    )
    p.add_argument(
        "--elevators", type=int, default=DEFAULT_NUM_ELEVATORS,
        help=f"Number of elevators  (default: {DEFAULT_NUM_ELEVATORS})",
    )
    p.add_argument(
        "--floors", type=int, default=DEFAULT_NUM_FLOORS,
        help=f"Number of floors  (default: {DEFAULT_NUM_FLOORS})",
    )
    p.add_argument(
        "--capacity", type=int, default=DEFAULT_CAPACITY,
        help=f"Max passengers per elevator  (default: {DEFAULT_CAPACITY})",
    )
    p.add_argument(
        "--algorithm",
        choices=ALGORITHMS,
        default=DEFAULT_ALGORITHM,
        help=f"Scheduling algorithm  (default: {DEFAULT_ALGORITHM})",
    )
    p.add_argument(
        "--express", action="store_true",
        help=(
            f"Enable express mode: last elevator skips floors {EXPRESS_LOBBY_FLOOR + 1}–{EXPRESS_SKIP_HIGH} "
            f"(serves lobby floor {EXPRESS_LOBBY_FLOOR} and floors {EXPRESS_SKIP_HIGH + 1}+)"
        ),
    )
    p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Logging verbosity; DEBUG prints per-tick state (default: WARNING)",
    )
    p.add_argument(
        "--log-format",
        choices=["text", "json"],
        default="text",
        help="Log output format: human-readable text or JSON objects (default: text)",
    )
    return p.parse_args()


def _configure_logging(log_level: str, log_format: str) -> None:
    logging.basicConfig(level=log_level)
    handler = logging.getLogger().handlers[0]
    handler.addFilter(RequestIdFilter())
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(levelname)s [%(request_id)s] %(name)s: %(message)s")
        )


def main() -> None:
    args = parse_args()
    _configure_logging(args.log_level, args.log_format)

    express_config = None
    if args.express and args.elevators >= 2:
        last_id = args.elevators - 1
        express_floors = {EXPRESS_LOBBY_FLOOR} | set(range(EXPRESS_SKIP_HIGH + 1, args.floors + 1))
        express_config = {last_id: list(express_floors)}
        print(f"  Express mode enabled: elevator {last_id} skips floors {EXPRESS_LOBBY_FLOOR + 1}–{EXPRESS_SKIP_HIGH}")

    try:
        sim = ElevatorSimulation(
            num_elevators=args.elevators,
            num_floors=args.floors,
            capacity=args.capacity,
            algorithm=args.algorithm,
            express_config=express_config,
        )
    except ValueError as e:
        logger.error("invalid configuration: %s", e)
        sys.exit(1)

    print(f"Loading requests from: {args.input}")
    try:
        requests = load_requests(args.input)
    except FileNotFoundError:
        logger.error("input file not found: %s", args.input)
        sys.exit(1)
    except ValueError as e:
        logger.error("%s", e)
        sys.exit(1)

    print(f"  {len(requests)} requests loaded")
    print(f"  Algorithm  : {args.algorithm}")
    print(f"  Elevators  : {args.elevators}  |  Floors: {args.floors}  |  Capacity: {args.capacity}")
    print()
    print("Running simulation…")

    sim.run(requests)

    print(f"Simulation complete at T = {sim.current_time}")
    try:
        sim.save_position_log(args.output)
        print(f"Position log saved to: {args.output}")
    except OSError as e:
        logger.error("%s", e)
    sim.print_statistics()
    try:
        sim.save_statistics(args.stats_output)
        print(f"Passenger stats saved to : {args.stats_output}")
    except OSError as e:
        logger.error("%s", e)
    if args.metrics_output:
        try:
            sim.save_metrics(args.metrics_output)
            print(f"Per-tick metrics saved to: {args.metrics_output}")
        except OSError as e:
            logger.error("%s", e)


if __name__ == "__main__":
    main()
