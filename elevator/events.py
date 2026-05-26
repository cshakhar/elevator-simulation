from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from elevator.models import Elevator, Passenger


class SimulationEventListener:
    """
    Hook interface for simulation lifecycle events.
    Override only the methods you care about — all are no-ops by default.
    """

    def on_passenger_assigned(
        self, passenger: "Passenger", elevator_id: int, tick: int
    ) -> None:
        pass

    def on_passenger_boarded(
        self, passenger: "Passenger", elevator: "Elevator", tick: int
    ) -> None:
        pass

    def on_passenger_alighted(
        self, passenger: "Passenger", elevator: "Elevator", tick: int
    ) -> None:
        pass

    def on_tick_complete(self, tick: int) -> None:
        pass

    def on_simulation_complete(self, stats: Dict, tick: int) -> None:
        pass
