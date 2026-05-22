from algorithms.base import BaseScheduler
from elevator.models import Passenger


class RoundRobinScheduler(BaseScheduler):
    """
    Simple baseline: assigns requests to elevators in strict rotation.
    Skips elevators that are full or cannot serve both floors.
    """

    def __init__(self, elevators):
        super().__init__(elevators)
        self._counter = 0

    def assign(self, passenger: Passenger) -> int:
        n = len(self.elevators)
        for _ in range(n):
            elevator = self.elevators[self._counter % n]
            self._counter += 1
            if (
                not elevator.is_full
                and elevator.serves_floor(passenger.source)
                and elevator.serves_floor(passenger.dest)
            ):
                return elevator.id
        return self._fallback(passenger)
