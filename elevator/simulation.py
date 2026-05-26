
import csv
import logging
import os
import uuid
from typing import Dict, List, Optional

from elevator.constants import (
    CSV_COLUMNS,
    DEFAULT_ALGORITHM,
    DEFAULT_CAPACITY,
    DEFAULT_NUM_ELEVATORS,
    DEFAULT_NUM_FLOORS,
    STOP_DROPOFF,
    STOP_PICKUP,
)
from elevator.context import request_id_var
from elevator.events import SimulationEventListener
from elevator.metrics import SimulationMetrics
from elevator.models import Direction, Elevator, Passenger
from elevator.stats import compute_statistics, print_statistics, save_statistics

logger = logging.getLogger(__name__)


class ElevatorSimulation:
    def __init__(
        self,
        num_elevators: int = DEFAULT_NUM_ELEVATORS,
        num_floors: int = DEFAULT_NUM_FLOORS,
        capacity: int = DEFAULT_CAPACITY,
        algorithm: str = DEFAULT_ALGORITHM,
        express_config: Optional[Dict[int, List[int]]] = None,
        listeners: Optional[List[SimulationEventListener]] = None,
    ):
        if num_elevators < 1:
            raise ValueError(f"num_elevators must be >= 1, got {num_elevators}")
        if num_floors < 2:
            raise ValueError(f"num_floors must be >= 2, got {num_floors}")
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")

        self.num_elevators = num_elevators
        self.num_floors = num_floors
        self.capacity = capacity
        self.algorithm = algorithm
        self.current_time = 0
        self._listeners: List[SimulationEventListener] = listeners or []
        self.metrics = SimulationMetrics()

        self.elevators = [
            Elevator(i, num_floors, capacity) for i in range(num_elevators)
        ]
        if express_config:
            self._apply_express_config(express_config)

        self.scheduler = self._create_scheduler(algorithm)
        self.passengers: Dict[str, Passenger] = {}
        self.position_log: List[Dict] = []

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _apply_express_config(self, config: Dict[int, List[int]]) -> None:
        for elevator_id, floors in config.items():
            if elevator_id < 0 or elevator_id >= len(self.elevators):
                logger.warning(
                    "express_config references unknown elevator ID %d "
                    "(only %d elevator(s) exist); skipping.",
                    elevator_id, self.num_elevators,
                )
                continue
            self.elevators[elevator_id].express_floors = set(floors)
            logger.info("E%d restricted to %d express floor(s)", elevator_id, len(floors))

    def _create_scheduler(self, algorithm: str):
        from algorithms.nearest_car import NearestCarScheduler
        from algorithms.round_robin import RoundRobinScheduler
        from algorithms.zone_based import ZoneBasedScheduler

        mapping = {
            "nearest_car": NearestCarScheduler,
            "round_robin": RoundRobinScheduler,
            "zone_based": ZoneBasedScheduler,
        }
        if algorithm not in mapping:
            raise ValueError(
                f"Unknown algorithm {algorithm!r}. "
                f"Choose from: {list(mapping)}"
            )
        if algorithm == "zone_based":
            if any(e.express_floors is not None for e in self.elevators):
                logger.warning(
                    "Combining 'zone_based' algorithm with express_config may cause "
                    "passengers to be unroutable if zone and express boundaries conflict."
                )
            return ZoneBasedScheduler(self.elevators, self.num_floors)
        return mapping[algorithm](self.elevators)

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def load_requests(self, filepath: str) -> List[Dict]:
        requests = []
        required_columns = set(CSV_COLUMNS)
        try:
            with open(filepath, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is not None:
                    missing_cols = required_columns - set(reader.fieldnames)
                    if missing_cols:
                        raise ValueError(
                            f"CSV {filepath!r} is missing required columns: {sorted(missing_cols)}"
                        )
                for line_num, row in enumerate(reader, start=2):
                    try:
                        requests.append(
                            {
                                "time": int(row["time"]),
                                "id": row["id"].strip(),
                                "source": int(row["source"]),
                                "dest": int(row["dest"]),
                            }
                        )
                    except (KeyError, ValueError) as exc:
                        raise ValueError(
                            f"CSV {filepath!r} line {line_num}: could not parse row {dict(row)} — {exc}"
                        ) from exc
        except UnicodeDecodeError as exc:
            raise ValueError(f"CSV {filepath!r} is not valid UTF-8: {exc}") from exc
        if not requests:
            logger.warning("No requests found in %r; simulation will be empty.", filepath)
        return requests

    def save_position_log(self, filepath: str) -> None:
        if not self.position_log:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            fieldnames = ["time"] + [f"elevator_{i}" for i in range(self.num_elevators)]
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.position_log)
        except OSError as exc:
            raise OSError(f"Could not write position log to {filepath!r}: {exc}") from exc

    def save_metrics(self, filepath: str) -> None:
        """Write per-tick metrics (assignments, pickups, dropoffs, queue depth, utilisation) to CSV."""
        self.metrics.save(filepath)

    # ------------------------------------------------------------------
    # Main simulation loop
    # ------------------------------------------------------------------

    def run(self, requests: List[Dict]) -> None:
        self._reset()
        logger.info(
            "Simulation starting: %d elevator(s), %d floors, capacity=%d, algorithm=%s, %d request(s)",
            self.num_elevators, self.num_floors, self.capacity, self.algorithm, len(requests),
        )

        requests_by_time: Dict[int, List[Dict]] = {}
        for req in sorted(requests, key=lambda r: r["time"]):
            requests_by_time.setdefault(req["time"], []).append(req)

        max_request_time = max(requests_by_time) if requests_by_time else 0
        # Safety cap: worst case is all passengers funneled through one elevator
        # one trip at a time; each trip is at most 2 * num_floors ticks.
        max_trips = max(1, (len(requests) + self.capacity - 1) // self.capacity)
        max_sim_time = max_request_time + max_trips * self.num_floors * 2

        seen_ids: Dict[str, int] = {}
        for req in requests:
            pid = req.get("id", "")
            if pid in seen_ids:
                logger.warning(
                    "Duplicate passenger ID %r at time %d (first seen at time %d); "
                    "later entry will overwrite the earlier one.",
                    pid, req["time"], seen_ids[pid],
                )
            seen_ids[pid] = req["time"]

        while self.current_time <= max_sim_time:
            self.metrics.begin_tick(self.current_time)

            # 1. Log current elevator positions
            self._log_positions()

            # 2. Dispatch requests that arrive NOW (no peek-ahead)
            if self.current_time in requests_by_time:
                for req in requests_by_time[self.current_time]:
                    self._dispatch(req)

            # 3. Process pickups and dropoffs at each elevator's current floor
            for elevator in self.elevators:
                self._process_floor(elevator)

            # Snapshot queue depth and utilisation after all activity this tick.
            self.metrics.end_tick(self.elevators, self.passengers)

            for listener in self._listeners:
                listener.on_tick_complete(self.current_time)

            # 4. Exit when all passengers are served and no future work remains
            if self._is_done(max_request_time):
                break

            # 5. Move each elevator one floor toward its next stop
            for elevator in self.elevators:
                elevator.move()

            self.current_time += 1
            self._tick_log()

        served = sum(1 for p in self.passengers.values() if p.is_served)
        total = len(self.passengers)
        unserved = [p.id for p in self.passengers.values() if not p.is_served]
        logger.info(
            "Simulation complete at T=%d: %d/%d passenger(s) served",
            self.current_time, served, total,
        )
        if unserved:
            logger.warning(
                "Simulation ended with %d unserved passenger(s): %s. "
                "The safety time-cap was reached before all passengers could be served.",
                len(unserved), unserved,
            )

        final_stats = self.get_statistics()
        for listener in self._listeners:
            listener.on_simulation_complete(final_stats, self.current_time)

    def _reset(self) -> None:
        self.current_time = 0
        self.passengers.clear()
        self.position_log.clear()
        self.metrics = SimulationMetrics()
        for e in self.elevators:
            e.reset()
        # Rebuild scheduler so round-robin counter resets, etc.
        self.scheduler = self._create_scheduler(self.algorithm)

    # ------------------------------------------------------------------
    # Per-tick helpers
    # ------------------------------------------------------------------

    def _dispatch(self, req: Dict) -> None:
        source = max(1, min(self.num_floors, int(req["source"])))
        dest = max(1, min(self.num_floors, int(req["dest"])))
        # Scope a short request ID to this dispatch so every log record emitted
        # inside (including inside the scheduler) carries the same trace token.
        # try/finally guarantees the var is reset even if assignment raises.
        trace_id = uuid.uuid4().hex[:8]
        token = request_id_var.set(trace_id)
        try:
            passenger = Passenger(
                id=req["id"],
                request_time=req["time"],
                source=source,
                dest=dest,
                request_id=trace_id,  # stored so board/alight logs reuse the same token
            )
            self.passengers[passenger.id] = passenger

            # Trivial case: same floor, no travel needed
            if source == dest:
                passenger.pickup_time = req["time"]
                passenger.dropoff_time = req["time"]
                logger.debug("T=%d: %r served instantly (src==dest=%d)", self.current_time, passenger.id, source)
                return

            elevator_id = self.scheduler.assign(passenger)
            if elevator_id < 0 or elevator_id >= self.num_elevators:
                raise RuntimeError(
                    f"Scheduler returned invalid elevator ID {elevator_id} "
                    f"for passenger {passenger.id!r} (simulation has {self.num_elevators} elevator(s))."
                )
            passenger.assigned_elevator = elevator_id
            elevator = self.elevators[elevator_id]
            elevator.add_pickup(source, passenger.id)
            logger.debug("T=%d: %r assigned to E%d (src=%d dst=%d)", self.current_time, passenger.id, elevator_id, source, dest)

            self.metrics.record_assignment()
            for listener in self._listeners:
                listener.on_passenger_assigned(passenger, elevator_id, self.current_time)
        finally:
            request_id_var.reset(token)

    def _process_floor(self, elevator: Elevator) -> None:
        floor = elevator.current_floor
        if floor not in elevator.stops:
            return

        stop = elevator.stops[floor]

        # Drop off riders first to free capacity
        for pid in list(stop[STOP_DROPOFF]):
            if pid in elevator.passengers:
                elevator.passengers.remove(pid)
                self.passengers[pid].dropoff_time = self.current_time
                stop[STOP_DROPOFF].remove(pid)
                p = self.passengers[pid]
                # Restore the passenger's trace token so the alight log line
                # shares the same request_id as the original dispatch.
                _tok = request_id_var.set(p.request_id or "-")
                try:
                    logger.debug(
                        "T=%d: %r alighted E%d at floor %d (wait=%d travel=%d)",
                        self.current_time, pid, elevator.id, floor, p.wait_time, p.travel_time,
                    )
                    self.metrics.record_dropoff()
                    for listener in self._listeners:
                        listener.on_passenger_alighted(p, elevator, self.current_time)
                finally:
                    request_id_var.reset(_tok)

        # Pick up waiting passengers (FIFO, respect capacity)
        for pid in list(stop[STOP_PICKUP]):
            if elevator.is_full:
                break
            elevator.passengers.append(pid)
            self.passengers[pid].pickup_time = self.current_time
            stop[STOP_PICKUP].remove(pid)
            elevator.add_dropoff(self.passengers[pid].dest, pid)
            p = self.passengers[pid]
            # Same trace restoration as above for board events.
            _tok = request_id_var.set(p.request_id or "-")
            try:
                logger.debug(
                    "T=%d: %r boarded E%d at floor %d (dst=%d)",
                    self.current_time, pid, elevator.id, floor, p.dest,
                )
                self.metrics.record_pickup()
                for listener in self._listeners:
                    listener.on_passenger_boarded(p, elevator, self.current_time)
            finally:
                request_id_var.reset(_tok)

        elevator.remove_stop_if_empty(floor)

    def _is_done(self, max_request_time: int) -> bool:
        if self.current_time < max_request_time:
            return False
        all_served = all(p.is_served for p in self.passengers.values())
        all_idle = all(
            not e.has_stops and not e.passengers for e in self.elevators
        )
        return all_served and all_idle

    def _log_positions(self) -> None:
        entry: Dict = {"time": self.current_time}
        for e in self.elevators:
            entry[f"elevator_{e.id}"] = e.current_floor
        self.position_log.append(entry)

    def _tick_log(self) -> None:
        if not logger.isEnabledFor(logging.DEBUG):
            return
        parts = [f"[T={self.current_time:>4}]"]
        for e in self.elevators:
            parts.append(f"E{e.id}@{e.current_floor:>3}({e.direction.value[0]},{len(e.passengers)}p)")
        logger.debug("  ".join(parts))

    # ------------------------------------------------------------------
    # Public reporting
    # ------------------------------------------------------------------

    def print_statistics(self) -> None:
        stats = compute_statistics(list(self.passengers.values()), self.num_elevators)
        print_statistics(stats)

    def save_statistics(self, filepath: str) -> None:
        stats = compute_statistics(list(self.passengers.values()), self.num_elevators)
        save_statistics(stats, filepath)

    def get_statistics(self) -> Dict:
        return compute_statistics(list(self.passengers.values()), self.num_elevators)
