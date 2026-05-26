import pytest
from elevator.core.models import Direction, Elevator, Passenger


# ---------------------------------------------------------------------------
# Passenger
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
# Elevator
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
# Elevator — additional coverage
# ---------------------------------------------------------------------------

class TestElevatorExtra:
    def test_next_stop_going_down_below(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 7
        e.direction = Direction.DOWN
        e.add_pickup(5, "p1")
        e.add_pickup(3, "p2")
        assert e.get_next_stop() == 5   # closest below

    def test_next_stop_going_down_reversal(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 3
        e.direction = Direction.DOWN
        e.add_pickup(7, "p1")           # only stop is above → reverse
        assert e.get_next_stop() == 7

    def test_next_stop_no_stops_returns_none(self):
        e = Elevator(0, 10, 8)
        assert e.get_next_stop() is None

    def test_highest_and_lowest_stop(self):
        e = Elevator(0, 10, 8)
        e.add_pickup(3, "p1")
        e.add_pickup(7, "p2")
        assert e.lowest_stop == 3
        assert e.highest_stop == 7

    def test_highest_lowest_stop_when_empty(self):
        e = Elevator(0, 10, 8)
        assert e.highest_stop is None
        assert e.lowest_stop is None

    def test_available_capacity_partial(self):
        e = Elevator(0, 10, 4)
        e.passengers = ["p1", "p2"]
        assert e.available_capacity == 2
        assert not e.is_full

    def test_remove_stop_kept_when_one_list_nonempty(self):
        e = Elevator(0, 10, 8)
        e.add_pickup(3, "p1")
        e.add_dropoff(3, "p2")
        e.stops[3]["pickup"].remove("p1")
        e.remove_stop_if_empty(3)
        assert 3 in e.stops   # dropoff still pending

    def test_estimate_going_down_opposite(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 5
        e.direction = Direction.DOWN
        e.add_dropoff(2, "px")   # lowest stop = 2
        # source=8 > 5: must reach 2 first, then reverse up to 8 = 3 + 6 = 9
        assert e.estimate_pickup_time(8) == 9

    def test_reset_clears_all_state(self):
        e = Elevator(0, 10, 8)
        e.current_floor = 6
        e.direction = Direction.UP
        e.passengers = ["p1"]
        e.add_pickup(9, "p2")
        e.reset()
        assert e.current_floor == 1
        assert e.direction == Direction.IDLE
        assert e.passengers == []
        assert not e.stops

    def test_has_stops_true_and_false(self):
        e = Elevator(0, 10, 8)
        assert not e.has_stops
        e.add_pickup(5, "p1")
        assert e.has_stops


# ---------------------------------------------------------------------------
# Elevator — edge cases
# ---------------------------------------------------------------------------

class TestModelEdgeCases:
    def test_get_next_stop_idle_sole_stop_is_current_floor(self):
        """IDLE: when only the current floor is in stops, return it."""
        e = Elevator(0, 10, 8)
        e.current_floor = 3
        e.add_pickup(3, "p1")
        assert e.get_next_stop() == 3

    def test_get_next_stop_up_sole_stop_is_current_floor(self):
        """Going UP with only the current floor as stop returns it (capacity overflow edge case)."""
        e = Elevator(0, 10, 8)
        e.current_floor = 5
        e.direction = Direction.UP
        e.add_pickup(5, "p1")
        assert e.get_next_stop() == 5

    def test_get_next_stop_down_sole_stop_is_current_floor(self):
        """Going DOWN with only the current floor as stop returns it."""
        e = Elevator(0, 10, 8)
        e.current_floor = 5
        e.direction = Direction.DOWN
        e.add_pickup(5, "p1")
        assert e.get_next_stop() == 5
