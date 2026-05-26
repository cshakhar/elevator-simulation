# Elevator Simulation — Diagrams

The diagrams below show the full execution flow from CLI invocation through to statistics output.

## Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant main as main.py
    participant loader as elevator.io
    participant sim as ElevatorSimulation
    participant factory as algorithms/factory
    participant sched as Scheduler
    participant elev as Elevator(s)
    participant metrics as SimulationMetrics
    participant stats as stats.py

    User->>main: python main.py [args]
    main->>sim: ElevatorSimulation(elevators, floors, capacity, algorithm)
    sim->>elev: Elevator(id, num_floors, capacity) × N
    sim->>factory: create_scheduler(algorithm, elevators, num_floors)
    factory-->>sim: Scheduler instance

    main->>loader: load_requests(filepath)
    loader-->>main: List[Dict] requests

    main->>sim: run(requests)
    sim->>sim: _reset() — clear passengers, logs, rebuild scheduler

    loop each tick (current_time ≤ max_sim_time)
        sim->>metrics: begin_tick(current_time)
        sim->>sim: _log_positions()
        alt requests arrive at current_time
            sim->>sim: _dispatch(req)
            sim->>sched: assign(passenger)
            sched-->>sim: elevator_id
            sim->>elev: add_pickup(source, passenger_id)
        end
        loop for each elevator
            sim->>sim: _process_floor(elevator)
            Note over sim,elev: Drop off riders → set dropoff_time
            Note over sim,elev: Board waiting passengers up to capacity<br/>set pickup_time, call add_dropoff(dest)
        end
        sim->>metrics: end_tick(elevators, passengers)
        sim->>sim: fire on_tick_complete listeners
        sim->>sim: _is_done() → break if all served & all elevators idle
        loop for each elevator
            elev->>elev: move() — LOOK algorithm
        end
        sim->>sim: current_time += 1
    end

    sim->>sim: fire on_simulation_complete listeners
    main->>sim: save_position_log(output_path)
    main->>sim: print_statistics() / save_statistics()
    sim->>stats: compute_statistics(passengers)
    stats-->>User: wait / travel / total time summary
    opt --metrics-output provided
        main->>sim: save_metrics(path)
    end
```

## Passenger State Machine

```mermaid
stateDiagram-v2
    [*] --> Waiting : request arrives (dispatch)
    Waiting --> Riding : pickup_time set\n(elevator arrives at source floor)
    Riding --> Served : dropoff_time set\n(elevator arrives at dest floor)
    Served --> [*]
```

## Scheduler Decision Flow

```mermaid
flowchart TD
    A[New passenger request] --> B{Algorithm?}

    B -->|nearest_car| C[Score every elevator\nscore = ETA + stops × 0.01]
    C --> D{Any non-full\nelevator?}
    D -->|Yes| E[Pick lowest score]
    D -->|No| F[Fallback: least-loaded elevator]

    B -->|round_robin| G[Next elevator in rotation]
    G --> H{Full or\ncannot serve floor?}
    H -->|Yes| G
    H -->|No| E

    B -->|zone_based| I[Find zone containing source floor]
    I --> J{Zone elevator\navailable?}
    J -->|Yes| E
    J -->|No| C

    E --> K[elevator.add_pickup]
    F --> K
```
