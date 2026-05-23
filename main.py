#!/usr/bin/env python3
"""
Elevator System Simulation — entry point.

Examples
--------
  python main.py
  python main.py --elevators 4 --floors 20 --capacity 10
  python main.py --input data/large_requests.csv --algorithm zone_based
  python main.py --input data/large_requests.csv --express --verbose
"""
import argparse
import logging
import sys

from elevator.simulation import ElevatorSimulation


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Elevator System Simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--input", default="data/sample_requests.csv",
        help="CSV request file  (default: data/sample_requests.csv)",
    )
    p.add_argument(
        "--output", default="output/elevator_positions.csv",
        help="Position log output path  (default: output/elevator_positions.csv)",
    )
    p.add_argument(
        "--elevators", type=int, default=3,
        help="Number of elevators  (default: 3)",
    )
    p.add_argument(
        "--floors", type=int, default=60,
        help="Number of floors  (default: 60)",
    )
    p.add_argument(
        "--capacity", type=int, default=8,
        help="Max passengers per elevator  (default: 8)",
    )
    p.add_argument(
        "--algorithm",
        choices=["nearest_car", "round_robin", "zone_based"],
        default="nearest_car",
        help="Scheduling algorithm  (default: nearest_car)",
    )
    p.add_argument(
        "--express", action="store_true",
        help=(
            "Enable express mode: last elevator skips floors 2–10 "
            "(serves lobby floor 1 and floors 11+)"
        ),
    )
    p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Logging verbosity; DEBUG prints per-tick state (default: WARNING)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(levelname)s %(name)s: %(message)s",
    )

    express_config = None
    if args.express and args.elevators >= 2:
        last_id = args.elevators - 1
        express_floors = {1} | set(range(11, args.floors + 1))
        express_config = {last_id: list(express_floors)}
        print(f"  Express mode enabled: elevator {last_id} skips floors 2–10")

    sim = ElevatorSimulation(
        num_elevators=args.elevators,
        num_floors=args.floors,
        capacity=args.capacity,
        algorithm=args.algorithm,
        express_config=express_config,
    )

    print(f"Loading requests from: {args.input}")
    try:
        requests = sim.load_requests(args.input)
    except FileNotFoundError:
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"  {len(requests)} requests loaded")
    print(f"  Algorithm  : {args.algorithm}")
    print(f"  Elevators  : {args.elevators}  |  Floors: {args.floors}  |  Capacity: {args.capacity}")
    print()
    print("Running simulation…")

    sim.run(requests)

    print(f"Simulation complete at T = {sim.current_time}")
    sim.save_position_log(args.output)
    print(f"Position log saved to: {args.output}")
    sim.print_statistics()


if __name__ == "__main__":
    main()
