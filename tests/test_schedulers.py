import logging

import pytest
from elevator.core.models import Direction, Elevator, Passenger
from elevator.simulation import ElevatorSimulation


# ---------------------------------------------------------------------------
# Scheduler unit tests
# ---------------------------------------------------------------------------

class TestSchedulers:
    def _make_elevator(self, eid, floor, direction=Direction.IDLE):
        e = Elevator(eid, 60, 8)
        e.current_floor = floor
        e.direction = direction
        return e

    def test_nearest_car_picks_closest(self):
        from algorithms.nearest_car import NearestCarScheduler
        elevators = [
            self._make_elevator(0, 1),   # distance 9 to floor 10
            self._make_elevator(1, 8),   # distance 2 to floor 10
        ]
        scheduler = NearestCarScheduler(elevators)
        p = Passenger("p1", 0, 10, 20)
        assert scheduler.assign(p) == 1

    def test_round_robin_rotates(self):
        from algorithms.round_robin import RoundRobinScheduler
        elevators = [self._make_elevator(i, 1) for i in range(3)]
        scheduler = RoundRobinScheduler(elevators)
        ids = [scheduler.assign(Passenger(f"p{i}", 0, 1, 5)) for i in range(6)]
        assert ids == [0, 1, 2, 0, 1, 2]

    def test_zone_based_correct_zone(self):
        from algorithms.zone_based import ZoneBasedScheduler
        # 3 elevators, 30 floors → zones [1-10], [11-20], [21-30]
        elevators = [self._make_elevator(i, 1) for i in range(3)]
        scheduler = ZoneBasedScheduler(elevators, num_floors=30)
        p = Passenger("p1", 0, 15, 25)   # source=15 → zone 1 (elevator 1)
        assert scheduler.assign(p) == 1

    def test_nearest_car_skips_full(self):
        from algorithms.nearest_car import NearestCarScheduler
        e0 = self._make_elevator(0, 1)
        e0.passengers = [f"x{i}" for i in range(8)]  # fill elevator 0
        e1 = self._make_elevator(1, 10)
        scheduler = NearestCarScheduler([e0, e1])
        p = Passenger("p1", 0, 2, 8)
        assert scheduler.assign(p) == 1   # e0 is full, must pick e1

    def test_round_robin_skips_full(self):
        from algorithms.round_robin import RoundRobinScheduler
        e0 = self._make_elevator(0, 1)
        e1 = self._make_elevator(1, 1)
        e0.passengers = [f"x{i}" for i in range(8)]
        scheduler = RoundRobinScheduler([e0, e1])
        assert scheduler.assign(Passenger("p1", 0, 1, 5)) == 1

    def test_zone_based_fallback_when_zone_elevator_full(self):
        from algorithms.zone_based import ZoneBasedScheduler
        e0 = self._make_elevator(0, 1)
        e1 = self._make_elevator(1, 6)
        e0.passengers = [f"x{i}" for i in range(8)]
        scheduler = ZoneBasedScheduler([e0, e1], num_floors=10)
        # source=3 is in zone 0, but e0 is full → NearestCar fallback picks e1
        p = Passenger("p1", 0, 3, 8)
        assert scheduler.assign(p) == 1

    def test_zone_based_cross_zone_destination(self):
        from algorithms.zone_based import ZoneBasedScheduler
        # 3 elevators, 30 floors → zones [1-10], [11-20], [21-30]
        elevators = [self._make_elevator(i, 1) for i in range(3)]
        scheduler = ZoneBasedScheduler(elevators, num_floors=30)
        # source=5 (zone 0), dest=25 (zone 2) — zone 0 elevator should still
        # be assigned; cross-zone destination must not block the zone preference
        p = Passenger("p1", 0, 5, 25)
        assert scheduler.assign(p) == 0

    def test_zone_based_with_express_config_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger="elevator.simulation"):
            ElevatorSimulation(
                num_elevators=2, num_floors=20,
                algorithm="zone_based",
                express_config={0: list(range(1, 11))},
            )
        assert "zone_based" in caplog.text

    def test_fallback_no_elevators_raises(self):
        from algorithms.nearest_car import NearestCarScheduler
        scheduler = NearestCarScheduler([])
        with pytest.raises(RuntimeError, match="no elevators"):
            scheduler._fallback(Passenger("p1", 0, 1, 5))


# ---------------------------------------------------------------------------
# Scheduler factory
# ---------------------------------------------------------------------------

class TestFactory:
    def _elevators(self, n=2, floors=20):
        return [Elevator(i, floors, 8) for i in range(n)]

    def test_creates_nearest_car(self):
        from algorithms.factory import create_scheduler
        from algorithms.nearest_car import NearestCarScheduler
        assert isinstance(create_scheduler("nearest_car", self._elevators(), 20), NearestCarScheduler)

    def test_creates_round_robin(self):
        from algorithms.factory import create_scheduler
        from algorithms.round_robin import RoundRobinScheduler
        assert isinstance(create_scheduler("round_robin", self._elevators(), 20), RoundRobinScheduler)

    def test_creates_zone_based(self):
        from algorithms.factory import create_scheduler
        from algorithms.zone_based import ZoneBasedScheduler
        assert isinstance(create_scheduler("zone_based", self._elevators(), 20), ZoneBasedScheduler)

    def test_unknown_algorithm_raises(self):
        from algorithms.factory import create_scheduler
        with pytest.raises(ValueError, match="Unknown algorithm"):
            create_scheduler("banana", self._elevators(), 20)

    def test_zone_based_express_config_warns(self, caplog):
        from algorithms.factory import create_scheduler
        elevators = [
            Elevator(0, 20, 8, express_floors={1, 10, 20}),
            Elevator(1, 20, 8),
        ]
        with caplog.at_level(logging.WARNING, logger="elevator.simulation"):
            create_scheduler("zone_based", elevators, 20)
        assert "zone_based" in caplog.text


# ---------------------------------------------------------------------------
# Scheduler — additional coverage
# ---------------------------------------------------------------------------

class TestSchedulerExtra:
    def _make_elevator(self, eid, floor, express_floors=None):
        e = Elevator(eid, 20, 8, express_floors=express_floors)
        e.current_floor = floor
        return e

    def test_nearest_car_stop_penalty_tiebreaks(self):
        """When ETAs are equal, elevator with fewer pending stops wins."""
        from algorithms.nearest_car import NearestCarScheduler
        e0 = self._make_elevator(0, 5)              # distance 5 to floor 10
        e1 = self._make_elevator(1, 5)              # same distance, but has a stop
        e1.add_pickup(8, "existing")
        scheduler = NearestCarScheduler([e0, e1])
        assert scheduler.assign(Passenger("p1", 0, 10, 1)) == 0

    def test_nearest_car_skips_ineligible_floor(self):
        """Elevator that cannot serve source falls back to _fallback."""
        from algorithms.nearest_car import NearestCarScheduler
        e0 = self._make_elevator(0, 1, express_floors={1, 20})   # can't serve floor 5
        e1 = self._make_elevator(1, 1)
        scheduler = NearestCarScheduler([e0, e1])
        assert scheduler.assign(Passenger("p1", 0, 5, 8)) == 1

    def test_round_robin_skips_ineligible_floor(self):
        """Express elevator that cannot serve the source is skipped in rotation."""
        from algorithms.round_robin import RoundRobinScheduler
        e0 = self._make_elevator(0, 1, express_floors={1, 20})   # can't serve floor 5
        e1 = self._make_elevator(1, 1)
        scheduler = RoundRobinScheduler([e0, e1])
        assert scheduler.assign(Passenger("p1", 0, 5, 8)) == 1

    def test_zone_based_single_elevator_covers_all_floors(self):
        """With one elevator the only zone spans the entire building."""
        from algorithms.zone_based import ZoneBasedScheduler
        elevators = [Elevator(0, 10, 8)]
        scheduler = ZoneBasedScheduler(elevators, num_floors=10)
        assert scheduler.assign(Passenger("p1", 0, 7, 3)) == 0

    def test_zone_based_full_zone_elevator_logs_info_and_falls_back(self, caplog):
        """Full zone elevator logs INFO and NearestCar picks the available one."""
        from algorithms.zone_based import ZoneBasedScheduler
        e0 = self._make_elevator(0, 1)
        e0.passengers = [f"x{i}" for i in range(8)]  # full
        e1 = self._make_elevator(1, 1)
        # 2 elevators, 10 floors → zone 0: 1-5, zone 1: 6-10
        scheduler = ZoneBasedScheduler([e0, e1], num_floors=10)
        p = Passenger("p1", 0, 3, 8)   # source=3 in zone 0, e0 full
        with caplog.at_level(logging.INFO, logger="elevator.simulation"):
            result = scheduler.assign(p)
        assert result == 1
        assert "NearestCar" in caplog.text


# ---------------------------------------------------------------------------
# Scheduler fallback — base.py
# ---------------------------------------------------------------------------

class TestSchedulerFallback:
    def test_fallback_logs_info_when_all_elevators_full(self, caplog):
        from algorithms.nearest_car import NearestCarScheduler
        e0 = Elevator(0, 10, 1)
        e0.passengers = ["x"]   # full
        e1 = Elevator(1, 10, 1)
        e1.passengers = ["y"]   # full
        scheduler = NearestCarScheduler([e0, e1])
        with caplog.at_level(logging.INFO, logger="elevator.simulation"):
            result = scheduler.assign(Passenger("p1", 0, 1, 5))
        assert "fallback" in caplog.text.lower()
        assert result in (0, 1)

    def test_fallback_prefers_eligible_over_ineligible(self):
        """_fallback picks an elevator that can serve both floors over one that cannot."""
        from algorithms.base import BaseScheduler

        class DummyScheduler(BaseScheduler):
            def assign(self, passenger):
                return self._fallback(passenger)

        e0 = Elevator(0, 10, 8, express_floors={1, 10})   # cannot serve floor 5
        e1 = Elevator(1, 10, 8)                            # open
        assert DummyScheduler([e0, e1])._fallback(Passenger("p1", 0, 5, 8)) == 1
