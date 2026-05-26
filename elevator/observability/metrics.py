import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class TickMetrics:
    tick: int
    assignments: int = 0
    pickups: int = 0
    dropoffs: int = 0
    queue_depth: int = 0          # passengers still waiting (not yet boarded)
    elevator_utilisation: float = 0.0  # fraction of total capacity in use


class SimulationMetrics:
    """Accumulates per-tick counters during a simulation run."""

    def __init__(self) -> None:
        self.ticks: List[TickMetrics] = []
        self._current: Optional[TickMetrics] = None

    def begin_tick(self, tick: int) -> None:
        self._current = TickMetrics(tick=tick)

    def record_assignment(self) -> None:
        if self._current:
            self._current.assignments += 1

    def record_pickup(self) -> None:
        if self._current:
            self._current.pickups += 1

    def record_dropoff(self) -> None:
        if self._current:
            self._current.dropoffs += 1

    def end_tick(self, elevators, passengers: Dict) -> None:
        """Snapshot queue depth and utilisation then close out the tick."""
        if self._current is None:
            return
        self._current.queue_depth = sum(
            1 for p in passengers.values() if p.is_waiting
        )
        total_cap = sum(e.capacity for e in elevators)
        used_cap = sum(len(e.passengers) for e in elevators)
        self._current.elevator_utilisation = (
            round(used_cap / total_cap, 4) if total_cap else 0.0
        )
        self.ticks.append(self._current)
        self._current = None

    def save(self, filepath: str) -> None:
        """Write per-tick metrics to a CSV file."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "tick", "assignments", "pickups", "dropoffs",
                    "queue_depth", "elevator_utilisation",
                ],
            )
            writer.writeheader()
            for t in self.ticks:
                writer.writerow({
                    "tick": t.tick,
                    "assignments": t.assignments,
                    "pickups": t.pickups,
                    "dropoffs": t.dropoffs,
                    "queue_depth": t.queue_depth,
                    "elevator_utilisation": t.elevator_utilisation,
                })
