import pytest
from elevator.models import Direction, Elevator, Passenger
from elevator.simulation import ElevatorSimulation


# ---------------------------------------------------------------------------
# Passenger model
# ---------------------------------------------------------------------------

class TestPassenger:
    def test_times(self):
        p = Passenger("p1", request_time=0, source=1, dest=10)
        p.pickup_time = 5
        p.dropoff_time = 14
        assert p.wait_time == 5
        assert p.travel_time == 9
        assert p.total_time == 14

    def test_is_served_lifecycle(self):
        p = Passenger("p1", 0, 1, 10)
        assert not p.is_served
        assert p.is_waiting
        p.pickup_time = 3
        assert not p.is_served
        assert p.is_riding
        p.dropoff_time = 12
        assert p.is_served

    def test_travel_direction(self):
        assert Passenger("a", 0, 1, 5).travel_direction == Direction.UP
        assert Passenger("b", 0, 5, 1).travel_direction == Direction.DOWN


# ---------------------------------------------------------------------------
# Elevator model
# ---------------------------------------------------------------------------

class TestElevator:
    def test_initial_state(self):
        e = Elevator(0, 10, 8)
        assert e.current_floor == 1
        assert e.direction == Direction.IDLE
        assert not e.is_full
        assert not e.has_stops

    def test_capacity(self):
        e = Elevator(0, 10, 2)
        e.passengers = ["p1", "p2"]
        assert e.is_full
        assert e.available_capacity == 0

    def test_add_stops(self):
        e = Elevator(0, 10, 8)
        e.add_pickup(3, "p1")
        e.add_dropoff(7, "p1")
        assert 3 in e.stops
        assert 7 in e.stops

    def test_remove_stop_if_empty(self):
        e = Elevator(0, 10, 8)
        e.add_pickup(3, "p1")
        e.stops[3]["pickup"].remove("p1")
        e.remove_stop_if_empty(3)
        assert 3 not in e.stops

    def test_serves_floor_open(self):
        e = Elevator(0, 10, 8)
        assert e.serves_floor(1)
        assert e.serves_floor(10)

    def test_serves_floor_express(self):
        e = Elevator(0, 10, 8, express_floors={1, 5, 10})
        assert e.serves_floor(1)
        assert e.serves_floor(5)
        assert not e.serves_floor(3)
        assert not e.serves_floor(7)

    def test_next_stop_idle(self):
        e = Elevator(0, 10, 8)
        e.add_pickup(5, "p1")
        assert e.get_next_stop() == 5

    def test_next_stop_going_up_above(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 3
        e.direction = Direction.UP
        e.add_pickup(5, "p1")
        e.add_pickup(8, "p2")
        assert e.get_next_stop() == 5   # closest above

    def test_next_stop_scan_reversal(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 6
        e.direction = Direction.UP
        e.add_pickup(3, "p1")           # only stop is below → reverse
        assert e.get_next_stop() == 3

    def test_estimate_idle(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 3
        assert e.estimate_pickup_time(7) == 4

    def test_estimate_going_up_same_direction(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 3
        e.direction = Direction.UP
        e.add_pickup(8, "px")
        assert e.estimate_pickup_time(5) == 2   # 5 > 3

    def test_estimate_going_up_opposite(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 3
        e.direction = Direction.UP
        e.add_pickup(8, "px")           # highest stop = 8
        # source=1 < 3: must go to 8, then down to 1 = 5 + 7 = 12
        assert e.estimate_pickup_time(1) == 12

    def test_estimate_going_down_same_direction(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 8
        e.direction = Direction.DOWN
        e.add_dropoff(2, "px")
        assert e.estimate_pickup_time(5) == 3   # 5 < 8

    def test_move_up(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 3
        e.add_pickup(6, "p1")
        e.move()
        assert e.current_floor == 4
        assert e.direction == Direction.UP

    def test_move_down(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 6
        e.add_pickup(2, "p1")
        e.move()
        assert e.current_floor == 5
        assert e.direction == Direction.DOWN

    def test_no_move_when_no_stops(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 4
        e.move()
        assert e.current_floor == 4
        assert e.direction == Direction.IDLE


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def _req(time, pid, src, dst):
    return {"time": time, "id": pid, "source": src, "dest": dst}


class TestSimulation:
    def test_single_passenger_zero_wait(self):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=8)
        sim.run([_req(0, "p1", 1, 5)])
        p = sim.passengers["p1"]
        assert p.is_served
        assert p.wait_time == 0   # elevator starts at floor 1
        assert p.travel_time == 4

    def test_same_floor_instant_serve(self):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=8)
        sim.run([_req(0, "p1", 5, 5)])
        p = sim.passengers["p1"]
        assert p.is_served
        assert p.total_time == 0

    def test_passenger_arrives_later(self):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=8)
        sim.run([_req(5, "p1", 7, 3)])
        p = sim.passengers["p1"]
        assert p.is_served
        assert p.pickup_time >= 5   # not picked up before request time

    def test_no_peek_ahead(self):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=8)
        # First request at T=0, second far in the future
        sim.run([_req(0, "p1", 1, 2), _req(100, "p2", 9, 10)])
        assert sim.passengers["p2"].pickup_time >= 100

    def test_capacity_respected(self):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=2)
        reqs = [_req(0, f"p{i}", 1, 10) for i in range(5)]
        sim.run(reqs)
        for i in range(5):
            assert sim.passengers[f"p{i}"].is_served

    def test_multiple_elevators(self):
        sim = ElevatorSimulation(num_elevators=3, num_floors=20, capacity=8)
        reqs = [
            _req(0, "p1", 1, 10),
            _req(0, "p2", 20, 5),
            _req(0, "p3", 10, 1),
        ]
        sim.run(reqs)
        for pid in ["p1", "p2", "p3"]:
            assert sim.passengers[pid].is_served

    def test_two_passengers_same_direction(self):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=8)
        sim.run([_req(0, "p1", 1, 5), _req(0, "p2", 1, 8)])
        assert sim.passengers["p1"].is_served
        assert sim.passengers["p2"].is_served

    def test_position_log_format(self):
        sim = ElevatorSimulation(num_elevators=2, num_floors=10, capacity=8)
        sim.run([_req(0, "p1", 1, 5)])
        assert len(sim.position_log) > 0
        first = sim.position_log[0]
        assert "time" in first
        assert "elevator_0" in first
        assert "elevator_1" in first

    def test_all_algorithms_serve_all(self):
        reqs = [
            _req(0, "p1", 1, 5),
            _req(0, "p2", 3, 8),
            _req(2, "p3", 7, 2),
        ]
        for algo in ["nearest_car", "round_robin", "zone_based"]:
            sim = ElevatorSimulation(num_elevators=2, num_floors=10, capacity=8, algorithm=algo)
            sim.run(reqs)
            for pid in ["p1", "p2", "p3"]:
                assert sim.passengers[pid].is_served, f"{algo}: {pid} not served"

    def test_floor_clamping(self):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=8)
        sim.run([_req(0, "p1", 0, 15)])  # 0 → clamped to 1, 15 → clamped to 10
        assert sim.passengers["p1"].is_served

    def test_nearest_car_beats_round_robin_simple(self):
        """Nearest-car should not be worse than round-robin on avg total time."""
        reqs = [
            _req(0, "p1", 1, 50),
            _req(0, "p2", 1, 30),
            _req(5, "p3", 60, 5),
        ]
        results = {}
        for algo in ["nearest_car", "round_robin"]:
            sim = ElevatorSimulation(
                num_elevators=2, num_floors=60, capacity=8, algorithm=algo
            )
            sim.run(reqs)
            results[algo] = sim.get_statistics()["total_time"]["avg"]
        assert results["nearest_car"] <= results["round_robin"] + 5  # reasonable margin


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
        # Should rotate 0,1,2,0,1,2
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
