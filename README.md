# Elevator System Simulation

A discrete-time simulation of a **Destination Dispatch** elevator system written in Python.
Passengers specify both their origin and destination floor at request time; the controller
immediately assigns them to a specific elevator and routes it optimally.

---

## Key Concepts

| Term | Definition |
|------|------------|
| **Tick** | The base unit of simulation time. One tick = one floor of travel. Door open/close takes zero extra ticks. |
| **Destination Dispatch** | Passengers declare both source and destination when requesting. The controller assigns them to a specific elevator immediately, enabling smarter routing than traditional "press a button" systems. |
| **Online scheduling** | The scheduler sees only requests that have already arrived (time ≤ current tick). It cannot peek at future requests, mirroring real building controllers. |
| **LOOK algorithm** | A sweep-based movement strategy: an elevator travels in one direction serving all pending stops, then reverses — never overshooting unnecessarily. |

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
  --output output/positions.csv
```

**PowerShell / Windows:**
```powershell
python main.py `
  --input data/large_requests.csv `
  --elevators 4 `
  --floors 60 `
  --capacity 10 `
  --algorithm nearest_car `
  --output output/positions.csv
```

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | `data/sample_requests.csv` | CSV request file |
| `--output` | `output/elevator_positions.csv` | Position log output |
| `--elevators` | `3` | Number of elevators (1–10) |
| `--floors` | `60` | Number of floors |
| `--capacity` | `8` | Max passengers per elevator |
| `--algorithm` | `nearest_car` | `nearest_car` / `round_robin` / `zone_based` |
| `--express` | off | Designates the last elevator as an express car |
| `--log-level` | `WARNING` | Logging verbosity: `DEBUG` prints per-tick state and passenger events, `INFO`/`WARNING`/`ERROR` for progressively less output |

#### Express elevator

When `--express` is set, the last elevator is restricted to floors 1 and 11+ (it skips floors 2–10). This models a real high-rise pattern where one car is reserved for upper-floor traffic. The express elevator is assigned only to passengers whose source and destination both fall outside the skipped range; all other passengers are routed to the remaining elevators.

### Compare all three algorithms

```bash
python compare_algorithms.py --input data/large_requests.csv
```

Runs all three algorithms on the same input and prints a side-by-side performance table. Example output:

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
pytest tests/ -v
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

### 2. Passenger Summary Statistics (printed to stdout)

```
====================================================
  PASSENGER STATISTICS
====================================================
  Total passengers : 10
  Served           : 10

  Wait Time   (pickup - request):
    Min     : 0
    Max     : 15
    Average : 4.30

  Travel Time (dropoff - pickup):
    Min     : 9
    Max     : 50
    Average : 29.60

  Total Time  (dropoff - request):
    Min     : 9
    Max     : 63
    Average : 33.90
====================================================
```

---

## Architecture

```
elevator-simulation/
├── elevator/
│   ├── models.py       # Passenger, Elevator, Direction
│   ├── simulation.py   # Tick-based simulation engine
│   └── stats.py        # Statistics computation & printing
├── algorithms/
│   ├── base.py         # Abstract BaseScheduler
│   ├── nearest_car.py  # Primary algorithm
│   ├── round_robin.py  # Baseline algorithm
│   └── zone_based.py   # Zone-dispatch algorithm
├── data/               # CSV request files
├── tests/              # pytest test suite
├── output/             # Generated position logs
├── main.py             # CLI entry point
├── compare_algorithms.py  # Algorithm comparison tool
├── generate_data.py    # Synthetic data generator
└── visualize.py        # Optional matplotlib chart
```

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
elevator is full or unavailable.

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
