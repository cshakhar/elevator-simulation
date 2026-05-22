import csv
import os
from typing import Dict, List, Optional

from elevator.models import Direction, Elevator, Passenger
from elevator.stats import compute_statistics


class ElevatorSimulation:
    def __init__(
        self,
        num_elevators: int = 3,
        num_floors: int = 60,
        capacity: int = 8,
        algorithm: str = "nearest_car",
        express_config: Optional[Dict[int, List[int]]] = None,
    ):
        self.num_elevators = num_elevators
        self.num_floors = num_floors
        self.capacity = capacity
        self.algorithm = algorithm
        self.current_time = 0

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
            if elevator_id < len(self.elevators):
                self.elevators[elevator_id].express_floors = set(floors)

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
            return ZoneBasedScheduler(self.elevators, self.num_floors)
        return mapping[algorithm](self.elevators)

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def load_requests(self, filepath: str) -> List[Dict]:
        requests = []
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                requests.append(
                    {
                        "time": int(row["time"]),
                        "id": row["id"].strip(),
                        "source": int(row["source"]),
                        "dest": int(row["dest"]),
                    }
                )
        return requests

    def save_position_log(self, filepath: str) -> None:
        if not self.position_log:
            return
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        fieldnames = ["time"] + [f"elevator_{i}" for i in range(self.num_elevators)]
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.position_log)

    # ------------------------------------------------------------------
    # Main simulation loop
    # ------------------------------------------------------------------

    def run(self, requests: List[Dict], verbose: bool = False) -> None:
        self._reset()

        requests_by_time: Dict[int, List[Dict]] = {}
        for req in sorted(requests, key=lambda r: r["time"]):
            requests_by_time.setdefault(req["time"], []).append(req)

        max_request_time = max(requests_by_time) if requests_by_time else 0
        # Safety cap: worst case is all passengers funneled through one elevator
        # one trip at a time; each trip is at most 2 * num_floors ticks.
        max_trips = max(1, (len(requests) + self.capacity - 1) // self.capacity)
        max_sim_time = max_request_time + max_trips * self.num_floors * 2

        while self.current_time <= max_sim_time:
            # 1. Log current elevator positions
            self._log_positions()

            # 2. Dispatch requests that arrive NOW (no peek-ahead)
            if self.current_time in requests_by_time:
                for req in requests_by_time[self.current_time]:
                    self._dispatch(req)

            # 3. Process pickups and dropoffs at each elevator's current floor
            for elevator in self.elevators:
                self._process_floor(elevator)

            # 4. Exit when all passengers are served and no future work remains
            if self._is_done(max_request_time):
                break

            # 5. Move each elevator one floor toward its next stop
            for elevator in self.elevators:
                elevator.move()

            self.current_time += 1

            if verbose:
                self._print_tick()

    def _reset(self) -> None:
        self.current_time = 0
        self.passengers.clear()
        self.position_log.clear()
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
        passenger = Passenger(
            id=req["id"],
            request_time=req["time"],
            source=source,
            dest=dest,
        )
        self.passengers[passenger.id] = passenger

        # Trivial case: same floor, no travel needed
        if source == dest:
            passenger.pickup_time = req["time"]
            passenger.dropoff_time = req["time"]
            return

        elevator_id = self.scheduler.assign(passenger)
        passenger.assigned_elevator = elevator_id
        elevator = self.elevators[elevator_id]
        elevator.add_pickup(source, passenger.id)

    def _process_floor(self, elevator: Elevator) -> None:
        floor = elevator.current_floor
        if floor not in elevator.stops:
            return

        stop = elevator.stops[floor]

        # Drop off riders first to free capacity
        for pid in list(stop["dropoff"]):
            if pid in elevator.passengers:
                elevator.passengers.remove(pid)
                self.passengers[pid].dropoff_time = self.current_time
                stop["dropoff"].remove(pid)

        # Pick up waiting passengers (FIFO, respect capacity)
        for pid in list(stop["pickup"]):
            if elevator.is_full:
                break
            elevator.passengers.append(pid)
            self.passengers[pid].pickup_time = self.current_time
            stop["pickup"].remove(pid)
            elevator.add_dropoff(self.passengers[pid].dest, pid)

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

    def _print_tick(self) -> None:
        parts = [f"[T={self.current_time:>4}]"]
        for e in self.elevators:
            parts.append(
                f"E{e.id}@{e.current_floor:>3}"
                f"({e.direction.value[0]},{len(e.passengers)}p)"
            )
        print("  ".join(parts))

    # ------------------------------------------------------------------
    # Public reporting
    # ------------------------------------------------------------------

    def print_statistics(self) -> None:
        compute_statistics(list(self.passengers.values()))

    def get_statistics(self) -> Dict:
        return compute_statistics(
            list(self.passengers.values()), print_output=False
        )
