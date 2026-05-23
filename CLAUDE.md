# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the simulation (default: 3 elevators, 60 floors, sample data)
python main.py

# Run with full options
python main.py --input data/large_requests.csv --elevators 4 --floors 80 \
               --capacity 10 --algorithm zone_based --express --log-level DEBUG

# Run tests
pytest tests/ -v

# Run a single test
pytest tests/test_simulation.py::TestElevator::test_move_up -v

# Generate synthetic request data
python generate_data.py --passengers 200 --floors 60 --max-time 300

# Compare all three scheduling algorithms side-by-side
python compare_algorithms.py --input data/large_requests.csv

# Visualize elevator positions over time (requires matplotlib)
python visualize.py --input output/elevator_positions.csv
python visualize.py --save chart.png
```

**Dependencies:** core simulation requires Python 3.8+ only; `pytest>=7.0` for tests; `matplotlib>=3.5` for visualization.

## Architecture

This is a **tick-based discrete-time elevator simulation** implementing a Destination Dispatch system — passengers specify source and destination at request time and are immediately assigned to a specific elevator.

### Module layout

- **`elevator/models.py`** — `Direction` enum, `Passenger` (lifecycle: waiting → riding → served), `Elevator` (manages stops, movement, capacity)
- **`elevator/simulation.py`** — `ElevatorSimulation` orchestrates the main loop: log positions → dispatch new requests → process pickups/dropoffs → move elevators
- **`elevator/stats.py`** — aggregates and prints wait/travel/total time statistics
- **`algorithms/base.py`** — abstract `BaseScheduler` with `assign(passenger) → int` and `_fallback` for all-full scenarios
- **`algorithms/nearest_car.py`** — primary algorithm; scores elevators by ETA + pending-stop penalty
- **`algorithms/round_robin.py`** — strict rotation baseline; skips full elevators
- **`algorithms/zone_based.py`** — divides building into N equal zones, falls back to NearestCar when zone elevator is unavailable

### Simulation loop (online, no peek-ahead)

Each tick: only requests with `time ≤ current_tick` are visible to the scheduler. The sequence within each tick is: log positions → assign newly-arrived passengers → process pickups/dropoffs at current floors → move elevators.

### Elevator movement: LOOK algorithm

Each elevator runs the LOOK variant of SCAN disk scheduling:
- **Going UP**: serve all pending stops above current floor, then reverse
- **Going DOWN**: serve all pending stops below current floor, then reverse
- **Idle**: move toward nearest pending stop at a *different* floor; the current floor is only targeted if it is the sole remaining stop (prevents deadlock when capacity is exceeded mid-pickup)
- At each floor: drop-offs are processed before pick-ups (frees capacity for boarding); boarding is FIFO up to capacity

### Key behavioral invariants

**Dropoff registered at boarding, not at dispatch.** `_dispatch` only calls `elevator.add_pickup(source)`; `elevator.add_dropoff(dest)` is called inside `_process_floor` the moment the passenger boards. This prevents a ghost dropoff stop at the elevator's current floor from trapping it idle when `dest == current_floor` at assignment time.

**`max_sim_time` scales with passenger count and capacity.** The safety cap is `max_request_time + ⌈num_passengers / capacity⌉ × num_floors × 2`, ensuring enough ticks for all passengers to be served even when capacity is low and multiple trips are needed.

### Nearest Car scoring (default algorithm)

`score = estimated_pickup_steps + num_pending_stops × 0.01`

ETA estimation accounts for elevator direction relative to the source floor:
- Idle: `|current_floor - source|`
- Moving toward source: simple distance
- Moving away from source: must reach turnaround point first, then travel back

Full elevators are skipped; if all are full, the passenger is queued on the least-loaded elevator.

### Zone-based algorithm

Zone size is `ceil(num_floors / num_elevators)`. Zone ownership is by index: elevator 0 owns floors 1–zone_size, elevator 1 owns the next zone, etc. If the zone elevator is full or cannot serve either floor, falls back to NearestCar.

### Express elevator configuration

The `--express` CLI flag hardcodes: last elevator serves only floor 1 and floors 11+. For programmatic control, pass `express_config` to `ElevatorSimulation`:

```python
express_config = {
    0: [1, 10, 20, 30],   # elevator 0 serves only these floors
    2: list(range(1, 61)), # elevator 2 serves all floors (same as None)
}
```

`elevator.serves_floor(f)` returns `True` if `express_floors is None` (open elevator) or `f in express_floors`. Schedulers check this before assigning.

### Adding a new scheduling algorithm

1. Create `algorithms/my_algo.py` with a class extending `BaseScheduler`; implement `assign(passenger) → int`
2. Register it in `ElevatorSimulation._create_scheduler` in `elevator/simulation.py`
3. Add it to the `choices` list in `main.py`'s `--algorithm` argument

### Logging

All runtime diagnostics go through `logging.getLogger("elevator.simulation")`. Both `main.py` and `compare_algorithms.py` accept `--log-level DEBUG|INFO|WARNING|ERROR` (default `WARNING`) and call `logging.basicConfig` at startup.

Log levels in use:
- `WARNING` — duplicate passenger IDs, empty CSV, invalid `express_config` IDs, unserved passengers at time-cap
- `DEBUG` — per-tick elevator state, and one line each when a passenger is assigned, boards, or alights

### Error handling

`ElevatorSimulation.__init__` raises `ValueError` for `num_elevators < 1`, `num_floors < 2`, `capacity < 1`, or an unknown algorithm name. `load_requests` raises `ValueError` for missing columns, unparseable values (with filename and line number), or a non-UTF-8 file. `save_position_log` raises `OSError` if the output path is not writable. `generate_data.py` raises `ValueError` for `num_floors < 2`, `num_passengers < 1`, or `max_time < 0`.

### Programmatic statistics API

`sim.get_statistics()` returns a dict (does not print):

```python
{
  "total": int, "served": int, "unserved": int,
  "wait_time":   {"min": int|None, "max": int|None, "avg": float|None, "count": int},
  "travel_time": {"min": int|None, "max": int|None, "avg": float|None, "count": int},
  "total_time":  {"min": int|None, "max": int|None, "avg": float|None, "count": int},
  "zero_wait_count": int,   # passengers picked up immediately
  "long_wait_count": int,   # passengers who waited > 20 ticks
}
```

`sim.print_statistics()` prints the same data formatted to stdout.

### I/O formats

**Input CSV:**
```
time,id,source,dest
0,passenger1,1,51
10,passenger2,20,1
```

**Output CSV** (`output/elevator_positions.csv`):
```
time,elevator_0,elevator_1,elevator_2
0,1,1,1
1,2,1,1
```

All elevators start at floor 1. Floors are integers only. Out-of-range floors in requests are silently clamped to `[1, num_floors]`.
