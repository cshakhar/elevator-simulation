#!/usr/bin/env python3
"""Generate synthetic request CSV files for testing."""
import csv
import random
import argparse
import os
import sys

from elevator.core.constants import CSV_COLUMNS, DEFAULT_GENERATED_FILE, DEFAULT_NUM_FLOORS

_DEFAULT_NUM_PASSENGERS = 100
_DEFAULT_MAX_TIME = 200
_DEFAULT_SEED = 42

PATTERNS = ["uniform", "office", "residential"]


def _pick_floor(floors: list[int], weights: list[float], rng: random.Random) -> int:
    return rng.choices(floors, weights=weights, k=1)[0]


def _make_floor_weights(num_floors: int, hub_floors: list[int]) -> list[float]:
    """Weight each floor. Hub floors get 8x weight, neighbours get 2x."""
    w = [1.0] * (num_floors + 1)  # index 0 unused
    for h in hub_floors:
        if 1 <= h <= num_floors:
            w[h] = 8.0
            for neighbour in (h - 1, h + 1):
                if 1 <= neighbour <= num_floors:
                    w[neighbour] = max(w[neighbour], 2.0)
    return w


def _generate_office(
    num_passengers: int,
    num_floors: int,
    max_time: int,
    rng: random.Random,
) -> list[dict]:
    """
    Simulates a workday with three phases:
      - Morning rush  (0–30% of max_time): lobby → upper floors
      - Midday        (30–65%): mixed inter-floor + lunch hub
      - Evening rush  (65–100%): upper floors → lobby
    Lobby (floor 1) and a mid-floor cafeteria are hub floors.
    """
    lobby = 1
    cafeteria = max(2, num_floors // 3)
    hub_floors = [lobby, cafeteria]
    floor_list = list(range(1, num_floors + 1))
    floor_weights = _make_floor_weights(num_floors, hub_floors)

    morning_end = int(max_time * 0.30)
    midday_end = int(max_time * 0.65)

    # Spread passengers across three phases with realistic proportions
    n_morning = int(num_passengers * 0.40)
    n_midday = int(num_passengers * 0.25)
    n_evening = num_passengers - n_morning - n_midday

    rows = []

    def add(t: int, src: int, dst: int, idx: int) -> None:
        rows.append({"time": t, "id": f"gen_{idx:04d}", "source": src, "dest": dst})

    idx = 1

    # Morning: lobby → upper, with small jitter so not all at t=0
    for _ in range(n_morning):
        t = rng.randint(0, max(0, morning_end))
        src = lobby
        dst = _pick_floor(floor_list[1:], floor_weights[2:], rng)  # never lobby
        add(t, src, dst, idx)
        idx += 1

    # Midday: inter-floor movement biased toward cafeteria
    for _ in range(n_midday):
        t = rng.randint(morning_end, max(morning_end, midday_end))
        src = _pick_floor(floor_list, floor_weights[1:], rng)
        dst = _pick_floor(floor_list, floor_weights[1:], rng)
        while dst == src:
            dst = _pick_floor(floor_list, floor_weights[1:], rng)
        add(t, src, dst, idx)
        idx += 1

    # Evening: upper floors → lobby
    for _ in range(n_evening):
        t = rng.randint(midday_end, max_time)
        src = _pick_floor(floor_list[1:], floor_weights[2:], rng)  # never lobby
        dst = lobby
        add(t, src, dst, idx)
        idx += 1

    return rows


def _generate_residential(
    num_passengers: int,
    num_floors: int,
    max_time: int,
    rng: random.Random,
) -> list[dict]:
    """
    Simulates a residential building:
      - Morning departure surge (0–25%): upper floors → lobby
      - Scattered daytime (25–70%): light random traffic
      - Evening return surge (70–100%): lobby → upper floors
    No strong cafeteria bias; residents spread across all floors.
    """
    lobby = 1
    floor_list = list(range(1, num_floors + 1))
    flat_weights = [1.0] * num_floors

    morning_end = int(max_time * 0.25)
    daytime_end = int(max_time * 0.70)

    n_morning = int(num_passengers * 0.35)
    n_daytime = int(num_passengers * 0.15)
    n_evening = num_passengers - n_morning - n_daytime

    rows = []
    idx = 1

    def add(t: int, src: int, dst: int) -> None:
        nonlocal idx
        rows.append({"time": t, "id": f"gen_{idx:04d}", "source": src, "dest": dst})
        idx += 1

    for _ in range(n_morning):
        t = rng.randint(0, max(0, morning_end))
        src = _pick_floor(floor_list[1:], flat_weights[1:], rng)
        add(t, src, lobby)

    for _ in range(n_daytime):
        t = rng.randint(morning_end, max(morning_end, daytime_end))
        src = rng.randint(1, num_floors)
        dst = rng.randint(1, num_floors)
        while dst == src:
            dst = rng.randint(1, num_floors)
        add(t, src, dst)

    for _ in range(n_evening):
        t = rng.randint(daytime_end, max_time)
        dst = _pick_floor(floor_list[1:], flat_weights[1:], rng)
        add(t, lobby, dst)

    return rows


def _generate_uniform(
    num_passengers: int,
    num_floors: int,
    max_time: int,
    rng: random.Random,
) -> list[dict]:
    rows = []
    for i in range(num_passengers):
        t = rng.randint(0, max_time)
        src = rng.randint(1, num_floors)
        dst = rng.randint(1, num_floors)
        while dst == src:
            dst = rng.randint(1, num_floors)
        rows.append({"time": t, "id": f"gen_{i+1:04d}", "source": src, "dest": dst})
    return rows


def generate(
    num_passengers: int = _DEFAULT_NUM_PASSENGERS,
    num_floors: int = DEFAULT_NUM_FLOORS,
    max_time: int = _DEFAULT_MAX_TIME,
    seed: int = _DEFAULT_SEED,
    output: str = DEFAULT_GENERATED_FILE,
    pattern: str = "uniform",
) -> None:
    if num_floors < 2:
        raise ValueError(f"num_floors must be >= 2, got {num_floors}")
    if num_passengers < 1:
        raise ValueError(f"num_passengers must be >= 1, got {num_passengers}")
    if max_time < 0:
        raise ValueError(f"max_time must be >= 0, got {max_time}")
    if pattern not in PATTERNS:
        raise ValueError(f"pattern must be one of {PATTERNS}, got {pattern!r}")

    rng = random.Random(seed)

    if pattern == "office":
        rows = _generate_office(num_passengers, num_floors, max_time, rng)
    elif pattern == "residential":
        rows = _generate_residential(num_passengers, num_floors, max_time, rng)
    else:
        rows = _generate_uniform(num_passengers, num_floors, max_time, rng)

    rows.sort(key=lambda r: r["time"])
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Generated {num_passengers} requests ({pattern}) -> {output}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate synthetic elevator requests")
    p.add_argument("--passengers", type=int, default=_DEFAULT_NUM_PASSENGERS)
    p.add_argument("--floors", type=int, default=DEFAULT_NUM_FLOORS)
    p.add_argument("--max-time", type=int, default=_DEFAULT_MAX_TIME)
    p.add_argument("--seed", type=int, default=_DEFAULT_SEED)
    p.add_argument("--output", default=DEFAULT_GENERATED_FILE)
    p.add_argument(
        "--pattern",
        choices=PATTERNS,
        default="uniform",
        help=(
            "uniform: fully random (original behavior); "
            "office: morning/evening rush + lobby and cafeteria bias; "
            "residential: morning departure + evening return surges"
        ),
    )
    args = p.parse_args()
    try:
        generate(args.passengers, args.floors, args.max_time, args.seed, args.output, args.pattern)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
