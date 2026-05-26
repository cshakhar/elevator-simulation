# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the simulation (default: 3 elevators, 60 floors, sample data)
python main.py

# Run with full options
python main.py --input testdata/large_requests.csv --elevators 4 --floors 80 \
               --capacity 10 --algorithm zone_based --express --log-level DEBUG \
               --log-format json --stats-output output/passenger_stats.log \
               --metrics-output output/metrics.csv

# Run all tests
pytest tests/ -v

# Run a single test
pytest tests/test_models.py::TestElevator::test_move_up -v

# Generate synthetic request data (uniform / office / residential pattern)
python generate_data.py --passengers 200 --floors 60 --max-time 300
python generate_data.py --passengers 200 --floors 60 --max-time 300 --pattern office
python generate_data.py --passengers 200 --floors 60 --max-time 300 --pattern residential

# Compare all three scheduling algorithms side-by-side
python compare_algorithms.py --input testdata/large_requests.csv

# Visualize elevator positions over time (requires matplotlib)
python visualize.py                                         # basic interactive chart
python visualize.py --save chart.png                        # save to file
python visualize.py --metrics output/metrics.csv            # add queue/utilisation panel
python visualize.py --pattern office --max-time 300         # add rush-hour phase bands
python visualize.py --input output/positions_nearest_car.csv --metrics output/metrics.csv --pattern office --max-time 300 --save chart.png
```

**Dependencies:** Python 3.8+ only for the core simulation; `pytest>=7.0` for tests; `matplotlib>=3.5` for visualization.

## Architecture

This is a **tick-based discrete-time elevator simulation** implementing a Destination Dispatch system — passengers specify source and destination at request time and are immediately assigned to a specific elevator.

### Package layout

```
elevator/
├── __init__.py              # exports ElevatorSimulation
├── simulation.py            # orchestrator — owns the main tick loop
├── core/
│   ├── constants.py         # single source of truth for all defaults, keys, and magic values
│   └── models.py            # Direction enum, Passenger dataclass, Elevator class
├── io/
│   └── loader.py            # load_requests(); logger name hard-coded as "elevator.io"
└── observability/
    ├── context.py           # request_id_var ContextVar for trace propagation
    ├── events.py            # SimulationEventListener — five no-op hooks
    ├── filter.py            # RequestIdFilter — stamps request_id on every LogRecord
    ├── formatter.py         # JsonFormatter — one JSON object per log record
    ├── metrics.py           # SimulationMetrics / TickMetrics — per-tick counters
    └── stats.py             # compute_statistics(), print_statistics(), save_statistics()

algorithms/
├── base.py                  # abstract BaseScheduler + _fallback (least-loaded)
├── factory.py               # create_scheduler(algorithm, elevators, num_floors) — logger "elevator.simulation"
├── nearest_car.py           # primary algorithm; _STOP_PENALTY = 0.01
├── round_robin.py           # strict rotation baseline
└── zone_based.py            # zone-preference dispatch, falls back to NearestCar
```

Each subpackage `__init__.py` re-exports its public symbols. External code imports from `elevator.core.constants`, `elevator.observability.*`, etc.; `from elevator import ElevatorSimulation` also works.

### Simulation loop (online, no peek-ahead)

Tick sequence in `ElevatorSimulation.run()`:
1. `metrics.begin_tick` → log positions → dispatch newly-arrived requests → process pickups/dropoffs → `metrics.end_tick` → fire `on_tick_complete` → move elevators.

Only requests with `time ≤ current_tick` are dispatched. The safety cap is `max_request_time + ⌈num_passengers / capacity⌉ × num_floors × 2`.

### Key behavioral invariants

**Dropoff registered at boarding, not dispatch.** `_dispatch` calls only `elevator.add_pickup(source)`; `elevator.add_dropoff(dest)` is added in `_process_floor` the moment the passenger boards. This prevents a ghost dropoff stop from trapping the elevator idle when `dest == current_floor` at assignment time.

**Drop-offs before pick-ups.** At each floor, riders alight first (freeing capacity) before waiting passengers board.

**LOOK algorithm.** Going UP: serve all stops above, then reverse. Going DOWN: serve all stops below, then reverse. Idle: move toward the nearest stop at a *different* floor; the current floor is targeted only if it is the sole remaining stop (prevents deadlock when capacity is exceeded mid-pickup).

### Nearest Car scoring

`score = estimated_pickup_steps + len(elevator.stops) × 0.01`

ETA accounts for direction and turnaround: idle → `|current - source|`; moving toward source → simple distance; moving away → reach turnaround first, then travel back. Full elevators are skipped; if all are full, `_fallback` picks the least-loaded one.

### Zone-based algorithm

Zone size = `ceil(num_floors / num_elevators)`. Zone is a **scheduling preference only** — `serves_floor()` is intentionally not checked during zone assignment, so cross-zone destinations and burst overflow work correctly. Physical restrictions (`express_floors`) are enforced by the NearestCar fallback.

### Request tracing (`request_id`)

`_dispatch` generates a `uuid4().hex[:8]` token, sets `request_id_var` (in `elevator/observability/context.py`), and stores the token on `passenger.request_id`. `RequestIdFilter` (in `elevator/observability/filter.py`) automatically stamps every `LogRecord` with this value. In `_process_floor`, the token is restored from `p.request_id` before board/alight log calls so **all three events — assign → board → alight — share one trace token**. Grep logs for a `request_id` to trace a single passenger end-to-end. Records outside a dispatch context show `"-"`.

### Adding a new scheduling algorithm

1. Create `algorithms/my_algo.py` extending `BaseScheduler`; implement `assign(passenger) → int`.
2. Register it in `algorithms/factory.py` (`create_scheduler` mapping).
3. Add the name to `ALGORITHMS` in `elevator/core/constants.py` — this automatically updates `--algorithm` choices in `main.py` and `compare_algorithms.py`.

### Observability

`sim.metrics` (`SimulationMetrics`) is populated on every `run()`. Access in-memory via `sim.metrics.ticks` (list of `TickMetrics` dataclasses) or write to CSV with `sim.save_metrics(path)` / `--metrics-output`.

Event hooks: pass `listeners=[...]` to `ElevatorSimulation(...)`. Available hooks on `SimulationEventListener`: `on_passenger_assigned`, `on_passenger_boarded`, `on_passenger_alighted`, `on_tick_complete`, `on_simulation_complete`.

### Logging

`--log-level` default is `WARNING`. Levels in use:
- `WARNING` — duplicate IDs, unserved passengers at time-cap, empty CSV, invalid express config IDs, zone+express boundary conflict
- `INFO` — simulation start/end, express config applied, scheduler fallback events
- `DEBUG` — per-tick elevator state; one line each when a passenger is assigned, boards, or alights

`--log-format json` uses `JsonFormatter`; each record includes `ts`, `level`, `request_id`, `logger`, `msg`.

### Error handling

`ElevatorSimulation.__init__` raises `ValueError` for `num_elevators < 1`, `num_floors < 2`, `capacity < 1`, or an unknown algorithm. `load_requests` raises `ValueError` for missing columns, unparseable rows (with filename + line number), or non-UTF-8 files. Save methods raise `OSError` on unwritable paths.

### Programmatic statistics API

`sim.get_statistics()` returns a dict:

```python
{
  "total": int, "served": int, "unserved": int, "service_rate": float|None,
  "wait_time":  {"min", "max", "avg", "median", "p90", "p95", "stddev", "count"},
  "travel_time": { … },   # same shape
  "total_time":  { … },   # same shape
  "zero_wait_count": int, "long_wait_count": int, "long_wait_threshold": int,
  "wait_buckets": {"0-5 ticks": int, "6-20 ticks": int, "21-50 ticks": int, "51+ ticks": int},
  "per_elevator": {0: {"served": int, "avg_wait": float|None}, …},
}
```

Pass `num_elevators` to `compute_statistics()` to ensure zero-served elevators appear in `per_elevator`. Percentiles use fractional-index linear interpolation; stddev is population (÷n, not ÷n−1).
