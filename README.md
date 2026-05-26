# Elevator System Simulation

A discrete-time simulation of a **Destination Dispatch** elevator system written in Python.
Passengers specify both their origin and destination floor at request time; the controller
immediately assigns them to a specific elevator and routes it optimally.

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Key Concepts](#key-concepts)
- [Solution Overview](#solution-overview)
- [How to Run](#how-to-run)
  - [Prerequisites](#prerequisites)
  - [Quick Start](#quick-start-sample-data-3-elevators-60-floors)
  - [Custom Configuration](#custom-configuration)
  - [Compare All Three Algorithms](#compare-all-three-algorithms)
  - [Generate Synthetic Data](#generate-synthetic-data)
  - [Run Tests](#run-tests)
  - [Visualise Elevator Paths](#visualise-elevator-paths-requires-matplotlib)
- [Input Format](#input-format)
- [Output](#output)
- [Logging & Traceability](#logging--traceability)
- [Observability](#observability)
- [Architecture](#architecture)
- [Scheduling Algorithms](#scheduling-algorithms)
  - [Nearest Car](#nearest-car-default-recommended)
  - [Round Robin](#round-robin)
  - [Zone-Based](#zone-based)
  - [When to Use Each Algorithm](#when-to-use-each-algorithm)
- [Elevator Movement: SCAN / LOOK](#elevator-movement-scan--look)
- [Assumptions & Trade-offs](#assumptions--trade-offs)
- [What I'd Improve with More Time](#what-id-improve-with-more-time)

---

## Problem Statement

In a multi-floor building, passengers arrive continuously at unpredictable times, from unpredictable floors, going to unpredictable destinations. A naive system — one elevator, first-come first-served — causes long wait times, unnecessary floor traversals, and poor throughput as building size or passenger volume grows.

**The core challenge:** given a fleet of elevators with limited capacity, how do you decide in real time which elevator should serve each incoming request, and in what order each elevator should visit its pending floors, so that overall passenger wait and travel time is minimised?

Three interconnected sub-problems must be solved together:

1. **Assignment** — which elevator picks up this passenger? (wrong choice = long waits)
2. **Movement** — in what order does an elevator visit its pending floors? (wrong order = unnecessary backtracking)
3. **Capacity** — what happens when an elevator is full and more passengers are waiting? (no plan = stranded passengers)

The simulation is also **online**: the scheduler has no visibility into future requests. It must make dispatch decisions using only requests that have already arrived, mirroring the constraints of a real building controller.

---

## Key Concepts

| Term | Definition |
|------|------------|
| **Tick** | The base unit of simulation time. One tick = one floor of travel. Door open/close takes zero extra ticks. |
| **Destination Dispatch** | Passengers declare both source and destination when requesting. The controller assigns them to a specific elevator immediately, enabling smarter routing than traditional "press a button" systems. |
| **Online scheduling** | The scheduler sees only requests that have already arrived (time ≤ current tick). It cannot peek at future requests, mirroring real building controllers. |
| **LOOK algorithm** | A sweep-based movement strategy: an elevator travels in one direction serving all pending stops, then reverses — never overshooting unnecessarily. |

---

## Solution Overview

Each sub-problem maps directly to a component in this project:

| Sub-problem | Solution |
|---|---|
| **Assignment** | A pluggable scheduling algorithm (Nearest Car, Round Robin, or Zone-Based) scores each elevator and picks the best one for each incoming request. |
| **Movement** | Every elevator independently runs the LOOK algorithm — sweep in one direction, serve all stops, reverse — eliminating unnecessary backtracking. |
| **Capacity** | Drop-offs are processed before pick-ups at every floor to free space first. If all elevators are full, the passenger queues on the least-loaded one and waits until a slot opens. |

The simulation runs tick by tick, dispatching only what has arrived, so no algorithm has unfair foreknowledge of future requests.

---

## How to Run

### Prerequisites

```bash
pip install pytest          # for tests
pip install matplotlib      # optional, for the position chart
```

Python 3.8+ required. No other third-party dependencies.

### Quick start (sample data, 3 elevators, 60 floors)

```bash
python main.py
```

### Custom configuration

**Bash / macOS / Linux:**
```bash
python main.py \
  --input data/large_requests.csv \
  --elevators 4 \
  --floors 60 \
  --capacity 10 \
  --algorithm nearest_car \
  --output output/positions.csv \
  --metrics-output output/metrics.csv \
  --log-format json \
  --log-level INFO
```

**PowerShell / Windows:**
```powershell
python main.py `
  --input data/large_requests.csv `
  --elevators 4 `
  --floors 60 `
  --capacity 10 `
  --algorithm nearest_car `
  --output output/positions.csv `
  --metrics-output output/metrics.csv `
  --log-format json `
  --log-level INFO
```

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | `data/sample_requests.csv` | CSV request file |
| `--output` | `output/elevator_positions.csv` | Position log output |
| `--stats-output` | `output/passenger_stats.log` | Passenger statistics log output |
| `--metrics-output` | _(omit to skip)_ | Per-tick metrics CSV (assignments, pickups, dropoffs, queue depth, utilisation) |
| `--elevators` | `3` | Number of elevators (1–10) |
| `--floors` | `60` | Number of floors |
| `--capacity` | `8` | Max passengers per elevator |
| `--algorithm` | `nearest_car` | `nearest_car` / `round_robin` / `zone_based` |
| `--express` | off | Designates the last elevator as an express car |
| `--log-level` | `WARNING` | `DEBUG` — per-tick state + every passenger event; `INFO` — simulation lifecycle, scheduler fallbacks, express config; `WARNING`/`ERROR` — anomalies only |
| `--log-format` | `text` | `text` — human-readable; `json` — one JSON object per line for machine ingestion |

#### Express elevator

When `--express` is set, the last elevator is restricted to floors 1 and 11+ (it skips floors 2–10). This models a real high-rise pattern where one car is reserved for upper-floor traffic. The express elevator is assigned only to passengers whose source and destination both fall outside the skipped range; all other passengers are routed to the remaining elevators.

### Compare all three algorithms

```bash
python compare_algorithms.py --input data/large_requests.csv
python compare_algorithms.py --input data/large_requests.csv --log-level DEBUG --log-format json
```

Runs all three algorithms on the same input and prints a side-by-side performance table. Accepts the same `--log-level` and `--log-format` flags as `main.py`; each algorithm run is isolated so a failure in one does not abort the others. Example output:

```
Input: data/large_requests.csv  |  Elevators: 3  |  Floors: 60  |  Capacity: 8

==========================================================================
  ALGORITHM COMPARISON
==========================================================================
Metric                             nearest_car   round_robin    zone_based
--------------------------------------------------------------------------
Served passengers                           52            52            52
Avg wait time                            32.52         43.31         64.44
Max wait time                              142           112           293
Avg travel time                          40.13         50.44         39.06
Avg total time                           72.65         93.75        103.50
Max total time                             184           153           335
--------------------------------------------------------------------------

  Best avg total time: nearest_car
==========================================================================
```

### Generate synthetic data

```bash
python generate_data.py --passengers 200 --floors 60 --max-time 300
```

### Run tests

```bash
# Run all 110 tests
pytest tests/ -v

# Run a specific file
pytest tests/test_simulation.py -v
pytest tests/test_models.py -v
pytest tests/test_schedulers.py -v
pytest tests/test_io.py -v
pytest tests/test_observability.py -v

# Run a single test
pytest tests/test_simulation.py::TestSimulation::test_single_passenger_zero_wait -v
```

### Visualise elevator paths (requires matplotlib)

```bash
python main.py                        # produces output/elevator_positions.csv
python visualize.py                   # interactive chart
python visualize.py --save chart.png  # save to file
```

---

## Input Format

```
time,id,source,dest
0,passenger1,1,51
0,passenger2,1,37
10,passenger3,20,1
```

| Field | Type | Description |
|-------|------|-------------|
| `time` | int | Tick at which the request is submitted |
| `id` | str | Unique passenger identifier |
| `source` | int | Origin floor |
| `dest` | int | Destination floor |

The simulation **never peeks ahead**: at tick *T* only requests with `time ≤ T` are visible.

---

## Output

### 1. Elevator Positions Log (`output/elevator_positions.csv`)

One row per tick, columns `time, elevator_0, elevator_1, …`

```
time,elevator_0,elevator_1,elevator_2
0,1,1,1
1,2,1,1
2,3,2,1
…
```

### 2. Passenger Summary Statistics (stdout + `output/passenger_stats.log`)

```
============================================================
  PASSENGER STATISTICS
============================================================
  Total passengers : 10
  Served           : 10 (100.0%)

  Wait Time   (pickup - request):
    Min     :      0 ticks
    Max     :     79 ticks
    Average :     22.70 ticks
    Median  :      9.00 ticks
    P90     :     69.10 ticks
    P95     :     74.05 ticks
    Std Dev :     27.88 ticks
  ...

  Wait Time Distribution:
    0-5 ticks    :   4 passengers (40.0%)  ####
    6-20 ticks   :   3 passengers (30.0%)  ###
    21-50 ticks  :   1 passengers (10.0%)  #
    51+ ticks    :   2 passengers (20.0%)  ##

  Per-Elevator Breakdown:
  ------------------------------------------------------------
  Elevator       Served     Avg Wait
  ------------------------------------------------------------
  E0                  4  14.25 ticks
  E1                  4  25.50 ticks
  E2                  2  34.00 ticks
  ------------------------------------------------------------
============================================================
```

### 3. Per-Tick Metrics (`--metrics-output output/metrics.csv`)

When `--metrics-output` is provided, a CSV is written with one row per simulation tick:

```
tick,assignments,pickups,dropoffs,queue_depth,elevator_utilisation
0,2,2,0,0,0.0833
1,0,0,0,0,0.25
...
```

| Column | Description |
|--------|-------------|
| `tick` | Simulation tick |
| `assignments` | Passengers assigned to an elevator this tick |
| `pickups` | Passengers who boarded an elevator this tick |
| `dropoffs` | Passengers who alighted this tick |
| `queue_depth` | Passengers still waiting (not yet boarded) at end of tick |
| `elevator_utilisation` | Fraction of total fleet capacity currently occupied |

---

## Logging & Traceability

### Log levels

| Level | What is logged |
|---|---|
| `ERROR` | File not found, unwritable output, bad CSV |
| `WARNING` | Duplicate passenger IDs, unserved passengers at time-cap, conflicting express + zone config |
| `INFO` | Simulation start/end summary, express config applied, scheduler fallback events (zone → NearestCar, all-full → least-loaded) |
| `DEBUG` | Per-tick elevator state, and one line each when a passenger is assigned, boards, or alights |

### Log format

Use `--log-format text` (default) for human-readable output or `--log-format json` to emit one JSON object per line, suitable for ingestion by Loki, Datadog, or ELK:

```json
{"ts": "2026-05-26T10:00:00", "level": "INFO", "request_id": "-", "logger": "elevator.simulation", "msg": "Simulation starting: 3 elevator(s), 60 floors, ..."}
{"ts": "2026-05-26T10:00:00", "level": "DEBUG", "request_id": "3f2a1b9c", "logger": "elevator.simulation", "msg": "T=0: 'passenger1' assigned to E0 (src=1 dst=51)"}
```

### Request tracing with `request_id`

Every passenger dispatch generates a short 8-character UUID (`request_id`) that is stored on the `Passenger` object and automatically stamped on every log record for that passenger's full lifecycle — assignment, boarding, and alighting.

The mechanism uses Python's `contextvars.ContextVar` (`elevator/observability/context.py`) set in `_dispatch` and restored in `_process_floor` for each board/alight event, combined with a `logging.Filter` (`elevator/observability/filter.py`) that injects the value into each `LogRecord`.

Example `--log-level DEBUG` output, filtered to a single `request_id`:

```
DEBUG [3f2a1b9c] elevator.simulation: T=0: 'passenger1' assigned to E0 (src=1 dst=51)
DEBUG [3f2a1b9c] elevator.simulation: T=1: 'passenger1' boarded E0 at floor 1 (dst=51)
DEBUG [3f2a1b9c] elevator.simulation: T=51: 'passenger1' alighted E0 at floor 51 (wait=1 travel=50)
```

Non-request log lines (tick state, warnings) show `[-]` as the `request_id` so they are clearly distinguishable.

---

## Observability

Beyond logs and end-of-run statistics, the simulation exposes two programmatic hooks for external monitoring.

### Per-tick metrics (`SimulationMetrics`)

`sim.metrics` is populated during every `run()` call. Access it programmatically or write it to a file:

```python
sim.run(requests)
sim.save_metrics("output/metrics.csv")   # CSV with one row per tick

# Or access in-memory
for tick in sim.metrics.ticks:
    print(tick.tick, tick.queue_depth, tick.elevator_utilisation)
```

### Event hooks (`SimulationEventListener`)

Register listeners to react to simulation events without modifying simulation internals:

```python
from elevator import ElevatorSimulation
from elevator.observability.events import SimulationEventListener

class MyListener(SimulationEventListener):
    def on_passenger_assigned(self, passenger, elevator_id, tick):
        print(f"T={tick}: {passenger.id} → E{elevator_id}")

    def on_passenger_boarded(self, passenger, elevator, tick):
        print(f"T={tick}: {passenger.id} boarded E{elevator.id}")

    def on_passenger_alighted(self, passenger, elevator, tick):
        print(f"T={tick}: {passenger.id} alighted E{elevator.id} (wait={passenger.wait_time})")

    def on_simulation_complete(self, stats, tick):
        print(f"Done at T={tick}: {stats['served']}/{stats['total']} served")

sim = ElevatorSimulation(listeners=[MyListener()])
sim.run(requests)
```

All five hook methods have no-op defaults so you only override what you need:

| Hook | Fires when |
|---|---|
| `on_passenger_assigned` | Scheduler assigns a passenger to an elevator |
| `on_passenger_boarded` | Passenger physically boards an elevator |
| `on_passenger_alighted` | Passenger reaches their destination and exits |
| `on_tick_complete` | All activity for the current tick is done |
| `on_simulation_complete` | Simulation ends (receives final stats dict) |

---

## Architecture

```
elevator-simulation/
├── elevator/
│   ├── __init__.py              # Package entry point; exports ElevatorSimulation
│   ├── simulation.py            # Tick-based simulation engine (orchestrator)
│   ├── core/
│   │   ├── constants.py         # All shared defaults, paths, and magic values
│   │   └── models.py            # Passenger, Elevator, Direction
│   ├── io/
│   │   └── loader.py            # CSV request loading (load_requests)
│   └── observability/
│       ├── context.py           # ContextVar for per-request trace ID
│       ├── events.py            # Event hook interface (SimulationEventListener)
│       ├── filter.py            # Logging filter that stamps request_id on every record
│       ├── formatter.py         # JsonFormatter for machine-readable log output
│       ├── metrics.py           # Per-tick metrics collection (SimulationMetrics)
│       └── stats.py             # Statistics computation & reporting
├── algorithms/
│   ├── base.py                  # Abstract BaseScheduler + fallback logic
│   ├── factory.py               # Scheduler factory (create_scheduler)
│   ├── nearest_car.py           # Primary algorithm
│   ├── round_robin.py           # Baseline algorithm
│   └── zone_based.py            # Zone-dispatch algorithm
├── data/                        # CSV request files
├── tests/                       # pytest test suite (110 tests across 5 focused files)
│   ├── test_models.py           # Passenger, Elevator, Direction (32 tests)
│   ├── test_simulation.py       # Simulation loop, express config, init errors (25 tests)
│   ├── test_schedulers.py       # NearestCar, RoundRobin, ZoneBased, factory (21 tests)
│   ├── test_io.py               # CSV loading — happy path, malformed, encoding (6 tests)
│   └── test_observability.py    # Stats, metrics, log filter/formatter, event hooks (26 tests)
├── output/                      # Generated position logs, stats, and metrics
├── main.py                      # CLI entry point
├── compare_algorithms.py        # Algorithm comparison tool
├── generate_data.py             # Synthetic data generator
└── visualize.py                 # Optional matplotlib chart
```

### Subpackage responsibilities

| Subpackage | Contents | Responsibility |
|---|---|---|
| `elevator.core` | `constants`, `models` | Domain types and all shared constants — the foundation everything else imports from |
| `elevator.io` | `loader` | Reading passenger request CSVs; extendable for future output writers |
| `elevator.observability` | `context`, `events`, `filter`, `formatter`, `metrics`, `stats` | Everything that monitors or reports on the simulation: trace IDs, event hooks, logging, per-tick counters, and end-of-run statistics |

---

## Scheduling Algorithms

### Nearest Car (default, recommended)

Each incoming request is scored against every available elevator:

```
score = estimated_pickup_steps + number_of_pending_stops × 0.01
```

**`estimated_pickup_steps`** accounts for current floor, travel direction, and the farthest
committed stop (SCAN/LOOK reversal):

| Elevator state | Formula |
|----------------|---------|
| Idle | `|current - source|` |
| Going UP toward source | `source - current` |
| Going UP away from source | `(highest_stop - current) + (highest_stop - source)` |
| Going DOWN toward source | `current - source` |
| Going DOWN away from source | `(current - lowest_stop) + (source - lowest_stop)` |

Full elevators are skipped; if all elevators are full the least-loaded one is chosen
(the passenger waits at the pickup floor until a slot frees up).

### Round Robin

Assigns requests in strict rotation across elevators; skips full elevators. Simple and
fair but ignores proximity — useful as a performance baseline.

### Zone-Based

Divides the building into *N* equal zones (one per elevator). Each elevator owns its zone;
requests are dispatched to the zone elevator. Falls back to Nearest Car when the zone
elevator is full. Zone assignment is a scheduling preference — cross-zone destinations are
handled without penalty, and idle elevators from other zones can absorb burst traffic.

> **Note:** Combining `zone_based` with `--express` is supported but triggers a warning,
> as conflicting floor restrictions can make some passengers unroutable through the zone logic.

### When to Use Each Algorithm

| Scenario | Recommended algorithm |
|---|---|
| General use / unknown traffic pattern | `nearest_car` |
| Benchmarking / fairness comparison | `round_robin` |
| High-rise with distinct floor clusters (lobby, offices, penthouse) | `zone_based` |
| Building with an express elevator | any + `--express` |

---

## Elevator Movement: SCAN / LOOK

Each elevator follows the **LOOK** variant of the SCAN disk-scheduling algorithm:

- While moving UP, stop at every pending floor above; when no more stops are above, reverse.
- While moving DOWN, stop at every pending floor below; when no more stops are below, reverse.
- When idle, move toward the nearest pending stop.

Drop-offs are processed **before** pick-ups at any given floor so that freed capacity is
immediately used for boarding passengers.

---

## Assumptions & Trade-offs

1. **Destination Dispatch only** — passengers cannot change their destination after assignment.
2. **Uniform door time** — opening/closing doors takes zero extra ticks; one tick = one floor of travel.
3. **FIFO boarding** — when multiple passengers are waiting at the same floor, they board in
   the order the simulation enqueued them.
4. **Single start floor** — all elevators start at floor 1. A more realistic model would
   park idle elevators at statistically likely pickup floors.
5. **Capacity over waiting** — when all elevators are full, a passenger is queued on the
   least-loaded elevator rather than being rejected; this guarantees eventual service.
6. **Integer floors** — no fractional floors or inter-floor stops.

---

## What I'd Improve with More Time

- **Predictive positioning**: park idle elevators near historically busy floors during
  rush hours instead of leaving them where they last stopped.
- **Better capacity-aware ETA**: the current estimate ignores the capacity consumed by
  passengers who will board between now and the pickup floor; a future version would
  model this properly.
- **Machine-learning scheduler**: train a model on historical traffic data to predict
  optimal assignment policies.
- **Animation**: a real-time terminal or browser animation of elevator shafts.
- **REST / WebSocket API**: accept requests over HTTP and stream position updates live.
- **Benchmark suite**: systematic comparisons across building sizes, elevator counts,
  and traffic patterns (morning rush, evening rush, random, uniform).

---

## Time Spent

Approximately **4–5 hours** including design, implementation, testing, and documentation.
