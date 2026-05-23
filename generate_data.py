#!/usr/bin/env python3
"""Generate synthetic request CSV files for testing."""
import csv
import random
import argparse
import os
import sys


def generate(
    num_passengers: int = 100,
    num_floors: int = 60,
    max_time: int = 200,
    seed: int = 42,
    output: str = "data/generated_requests.csv",
) -> None:
    if num_floors < 2:
        raise ValueError(f"num_floors must be >= 2, got {num_floors}")
    if num_passengers < 1:
        raise ValueError(f"num_passengers must be >= 1, got {num_passengers}")
    if max_time < 0:
        raise ValueError(f"max_time must be >= 0, got {max_time}")

    random.seed(seed)
    rows = []
    for i in range(num_passengers):
        t = random.randint(0, max_time)
        src = random.randint(1, num_floors)
        dst = random.randint(1, num_floors)
        while dst == src:
            dst = random.randint(1, num_floors)
        rows.append({"time": t, "id": f"gen_{i+1:04d}", "source": src, "dest": dst})

    rows.sort(key=lambda r: r["time"])
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["time", "id", "source", "dest"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Generated {num_passengers} requests → {output}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate synthetic elevator requests")
    p.add_argument("--passengers", type=int, default=100)
    p.add_argument("--floors", type=int, default=60)
    p.add_argument("--max-time", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", default="data/generated_requests.csv")
    args = p.parse_args()
    try:
        generate(args.passengers, args.floors, args.max_time, args.seed, args.output)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
