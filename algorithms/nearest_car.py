from typing import List

from algorithms.base import BaseScheduler
from elevator.models import Elevator, Passenger

_STOP_PENALTY = 0.01  # tiebreak: prefer elevators with fewer pending stops


class NearestCarScheduler(BaseScheduler):
    """
    Destination Dispatch scheduler: assigns each request to the elevator
    that can reach the pickup floor soonest.

    Scoring:
      primary   — estimated steps to pickup floor (lower is better)
      tiebreak  — number of pending stops (prefer less busy elevators)

    Elevators that are full or cannot serve either floor are skipped.
    """

    def assign(self, passenger: Passenger) -> int:
        best_id: int = -1
        best_score: float = float("inf")

        for elevator in self.elevators:
            if elevator.is_full:
                continue
            if not elevator.serves_floor(passenger.source):
                continue
            if not elevator.serves_floor(passenger.dest):
                continue

            eta = elevator.estimate_pickup_time(passenger.source)
            score = eta + len(elevator.stops) * _STOP_PENALTY

            if score < best_score:
                best_score = score
                best_id = elevator.id

        return best_id if best_id >= 0 else self._fallback(passenger)
