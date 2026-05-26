# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the simulation (default: 3 elevators, 60 floors, sample data)
python main.py

# Run with full options
python main.py --input data/large_requests.csv --elevators 4 --floors 80 \
               --capacity 10 --algorithm zone_based --express --log-level DEBUG \
               --log-format json --stats-output output/passenger_stats.log \
               --metrics-output output/metrics.csv

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

- **`elevator/constants.py`** — single source of truth for all shared defaults, file paths, magic values, and string literals (algorithm names, stop slot keys, express-mode boundaries, logger name)
- **`elevator/models.py`** — `Direction` enum, `Passenger` (lifecycle: waiting → riding → served; carries `request_id` trace token), `Elevator` (manages stops, movement, capacity)
- **`elevator/simulation.py`** — `ElevatorSimulation` orchestrates the main loop: log positions → dispatch new requests → process pickups/dropoffs → move elevators; accepts optional `listeners` list
- **`elevator/stats.py`** — aggregates, formats, prints, and saves statistics; exposes `LONG_WAIT_THRESHOLD = 20`
- **`elevator/metrics.py`** — `SimulationMetrics` collects per-tick counters (assignments, pickups, dropoffs, queue depth, elevator utilisation); `sim.save_metrics(path)` writes a CSV
- **`elevator/events.py`** — `SimulationEventListener` base class with five no-op hooks fired during the simulation loop
- **`elevator/context.py`** — `request_id_var: ContextVar[str]` used to propagate a per-request trace ID through all log calls without explicit passing
- **`elevator/log_filter.py`** — `RequestIdFilter(logging.Filter)` reads `request_id_var` and stamps `record.request_id` on every `LogRecord`; must be added to the root handler after `logging.basicConfig`
- **`elevator/log_formatter.py`** — `JsonFormatter` emits one JSON object per log record; enabled via `--log-format json`
- **`algorithms/base.py`** — abstract `BaseScheduler` with `assign(passenger) → int` and `_fallback` for all-full scenarios
- **`algorithms/nearest_car.py`** — primary algorithm; scores elevators by ETA + pending-stop penalty (`_STOP_PENALTY = 0.01`)
- **`algorithms/round_robin.py`** — strict rotation baseline; skips full elevators
- **`algorithms/zone_based.py`** — divides building into N equal zones, falls back to NearestCar when zone elevator is unavailable

### Simulation loop (online, no peek-ahead)

Each tick: only requests with `time ≤ current_tick` are visible to the scheduler. The sequence within each tick is: begin metrics tick → log positions → assign newly-arrived passengers → process pickups/dropoffs at current floors → end metrics tick → fire `on_tick_complete` → move elevators.

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

`score = estimated_pickup_steps + num_pending_stops × _STOP_PENALTY` (constant `_STOP_PENALTY = 0.01` in `algorithms/nearest_car.py`)

ETA estimation accounts for elevator direction relative to the source floor:
- Idle: `|current_floor - source|`
- Moving toward source: simple distance
- Moving away from source: must reach turnaround point first, then travel back

Full elevators are skipped; if all are full, the passenger is queued on the least-loaded elevator.

### Zone-based algorithm

Zone size is `ceil(num_floors / num_elevators)`. Zone ownership is by index: elevator 0 owns floors 1–zone_size, elevator 1 owns the next zone, etc. If the zone elevator is full, falls back to NearestCar. Zone is a **scheduling preference only** — `serves_floor()` is not checked during the zone assignment so cross-zone destinations and burst overflow are handled correctly. Physical floor restrictions (`express_floors`) are still enforced by the NearestCar fallback.

### Express elevator configuration

The `--express` CLI flag hardcodes: last elevator serves only floor `EXPRESS_LOBBY_FLOOR` (1) and floors `EXPRESS_SKIP_HIGH + 1`+ (11+). For programmatic control, pass `express_config` to `ElevatorSimulation`:

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
3. Add it to the `ALGORITHMS` list in `elevator/constants.py` (this also updates the `--algorithm` choices in `main.py` and `compare_algorithms.py` automatically)

### Logging

Both `main.py` and `compare_algorithms.py` accept `--log-level DEBUG|INFO|WARNING|ERROR` (default `WARNING`) and `--log-format text|json` (default `text`). `_configure_logging()` in `main.py` calls `logging.basicConfig`, installs `RequestIdFilter` on the root handler, and applies `JsonFormatter` when `--log-format json` is set.

Log levels in use:
- `WARNING` — duplicate passenger IDs, empty CSV, invalid `express_config` IDs, unserved passengers at time-cap, combining `zone_based` algorithm with `express_config` (boundaries may conflict)
- `INFO` — simulation start/end summary, express config applied per elevator, zone-elevator-full fallback to NearestCar, all-elevators-full fallback to least-loaded
- `DEBUG` — per-tick elevator state, and one line each when a passenger is assigned, boards, or alights

### Request tracing (`request_id`)

`_dispatch` generates a `uuid4().hex[:8]` token, sets `request_id_var`, and stores the token on `passenger.request_id`. Every log record during dispatch (including inside schedulers) automatically carries the same `request_id`. In `_process_floor`, the token is restored from `p.request_id` before board/alight log calls so the **full passenger journey** — assign → board → alight — shares a single trace token. Records outside any dispatch context (tick logs, warnings) show `"-"`. To trace a single passenger end-to-end, grep logs for its `request_id`.

### Observability

#### Per-tick metrics

`sim.metrics` (`SimulationMetrics`) is populated on every `run()` call. Fields per tick:

| Field | Description |
|---|---|
| `assignments` | Passengers assigned to an elevator this tick |
| `pickups` | Passengers who boarded this tick |
| `dropoffs` | Passengers who alighted this tick |
| `queue_depth` | Passengers still waiting at end of tick |
| `elevator_utilisation` | Fraction of total fleet capacity occupied |

Write to CSV with `sim.save_metrics(filepath)` or use the `--metrics-output` flag. Access in-memory via `sim.metrics.ticks` (list of `TickMetrics` dataclasses).

#### Event hooks

Pass a list of `SimulationEventListener` instances to `ElevatorSimulation(listeners=[...])`. Available hooks:

| Hook | Fires when |
|---|---|
| `on_passenger_assigned(passenger, elevator_id, tick)` | Scheduler assigns a passenger |
| `on_passenger_boarded(passenger, elevator, tick)` | Passenger physically boards |
| `on_passenger_alighted(passenger, elevator, tick)` | Passenger reaches destination |
| `on_tick_complete(tick)` | All activity for the tick is done |
| `on_simulation_complete(stats, tick)` | Simulation ends; receives final stats dict |

### Error handling

`ElevatorSimulation.__init__` raises `ValueError` for `num_elevators < 1`, `num_floors < 2`, `capacity < 1`, or an unknown algorithm name. `load_requests` raises `ValueError` for missing columns, unparseable values (with filename and line number), or a non-UTF-8 file. `save_position_log`, `save_statistics`, and `save_metrics` raise `OSError` if the output path is not writable. `generate_data.py` raises `ValueError` for `num_floors < 2`, `num_passengers < 1`, or `max_time < 0`.

### Programmatic statistics API

`sim.get_statistics()` returns a dict (does not print):

```python
{
  "total": int, "served": int, "unserved": int,
  "service_rate": float|None,          # served / total
  "wait_time":   {                     # same shape for travel_time, total_time
    "min": int|None, "max": int|None,
    "avg": float|None, "median": float|None,
    "p90": float|None, "p95": float|None,
    "stddev": float|None, "count": int,
  },
  "travel_time": { ... },
  "total_time":  { ... },
  "zero_wait_count": int,              # passengers picked up immediately
  "long_wait_count": int,              # passengers who waited > LONG_WAIT_THRESHOLD ticks
  "long_wait_threshold": int,          # value of stats.LONG_WAIT_THRESHOLD (currently 20)
  "wait_buckets": {                    # histogram: label -> passenger count
    "0-5 ticks": int, "6-20 ticks": int, "21-50 ticks": int, "51+ ticks": int,
  },
  "per_elevator": {                    # keyed by elevator ID (int)
    0: {"served": int, "avg_wait": float|None},
    ...
  },
}
```

`sim.print_statistics()` prints the same data formatted to stdout.
`sim.save_statistics(filepath)` writes the same formatted output to a file (raises `OSError` if the path is not writable).
`sim.save_metrics(filepath)` writes per-tick metrics to a CSV (raises `OSError` if the path is not writable).
`compute_statistics(passengers, num_elevators=None)` in `elevator/stats.py` — pass `num_elevators` to ensure all elevators appear in `per_elevator` even if one served zero passengers.

### I/O formats

**Input CSV:**
```
time,id,source,dest
0,passenger1,1,51
10,passenger2,20,1
```

**Position log CSV** (`output/elevator_positions.csv`):
```
time,elevator_0,elevator_1,elevator_2
0,1,1,1
1,2,1,1
```

**Metrics CSV** (`output/metrics.csv`):
```
tick,assignments,pickups,dropoffs,queue_depth,elevator_utilisation
0,2,2,0,0,0.0833
1,0,0,0,0,0.25
```

All elevators start at floor `DEFAULT_START_FLOOR` (1). Floors are integers only. Out-of-range floors in requests are silently clamped to `[1, num_floors]`.
