import csv as csv_mod
import json
import logging

import pytest
from elevator.core.models import Direction, Elevator, Passenger
from elevator.io import load_requests
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
# Elevator model — additional coverage
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
# Simulation — additional coverage
# ---------------------------------------------------------------------------

class TestSimulationExtra:
    def test_dropoff_before_pickup_same_floor(self):
        """A rider drops off at a floor before a new passenger boards, freeing capacity."""
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=1)
        # p1 fills the elevator from floor 1 to floor 5
        # p2 waits at floor 5 and can only board after p1 exits
        sim.run([_req(0, "p1", 1, 5), _req(0, "p2", 5, 9)])
        assert sim.passengers["p1"].is_served
        assert sim.passengers["p2"].is_served
        assert sim.passengers["p2"].pickup_time >= sim.passengers["p1"].dropoff_time

    def test_get_statistics_structure(self):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=8)
        sim.run([_req(0, "p1", 1, 5)])
        stats = sim.get_statistics()
        assert stats["total"] == 1
        assert stats["served"] == 1
        assert stats["unserved"] == 0
        for key in ("wait_time", "travel_time", "total_time"):
            assert key in stats
            for field in ("min", "max", "avg", "count"):
                assert field in stats[key]

    def test_get_statistics_no_passengers(self):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=8)
        sim.run([])
        stats = sim.get_statistics()
        assert stats["total"] == 0
        assert stats["served"] == 0
        assert stats["wait_time"]["avg"] is None

    def test_save_position_log(self, tmp_path):
        sim = ElevatorSimulation(num_elevators=2, num_floors=10, capacity=8)
        sim.run([_req(0, "p1", 1, 3)])
        out = str(tmp_path / "positions.csv")
        sim.save_position_log(out)
        with open(out) as f:
            rows = list(csv_mod.DictReader(f))
        assert len(rows) > 0
        assert "time" in rows[0]
        assert "elevator_0" in rows[0]
        assert "elevator_1" in rows[0]

    def test_express_elevator_skipped_for_unserved_floor(self):
        """Passenger whose floor the express elevator skips gets the open elevator."""
        # Elevator 0 only serves floors 1 and 10; elevator 1 is open
        sim = ElevatorSimulation(
            num_elevators=2, num_floors=10, capacity=8,
            express_config={0: [1, 10]},
        )
        sim.run([_req(0, "p1", 5, 8)])
        assert sim.passengers["p1"].is_served
        assert sim.passengers["p1"].assigned_elevator == 1

    def test_duplicate_passenger_id_warns(self, caplog):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=8)
        reqs = [_req(0, "p1", 1, 5), _req(2, "p1", 3, 7)]
        with caplog.at_level(logging.WARNING, logger="elevator.simulation"):
            sim.run(reqs)
        assert "Duplicate passenger ID" in caplog.text


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_invalid_num_elevators(self):
        with pytest.raises(ValueError, match="num_elevators"):
            ElevatorSimulation(num_elevators=0)

    def test_invalid_num_floors(self):
        with pytest.raises(ValueError, match="num_floors"):
            ElevatorSimulation(num_floors=1)

    def test_invalid_capacity(self):
        with pytest.raises(ValueError, match="capacity"):
            ElevatorSimulation(capacity=0)

    def test_unknown_algorithm(self):
        with pytest.raises(ValueError, match="Unknown algorithm"):
            ElevatorSimulation(algorithm="banana")

    def test_express_config_invalid_elevator_id_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger="elevator.simulation"):
            ElevatorSimulation(num_elevators=2, express_config={99: [1, 10]})
        assert "unknown elevator ID" in caplog.text

    def test_load_requests_missing_columns(self, tmp_path):
        f = tmp_path / "bad.csv"
        f.write_text("time,id\n0,p1\n")
        with pytest.raises(ValueError, match="missing required columns"):
            load_requests(str(f))

    def test_load_requests_malformed_row(self, tmp_path):
        f = tmp_path / "bad.csv"
        f.write_text("time,id,source,dest\n0,p1,abc,10\n")
        with pytest.raises(ValueError, match="line 2"):
            load_requests(str(f))

    def test_load_requests_empty_csv_warns(self, tmp_path, caplog):
        f = tmp_path / "empty.csv"
        f.write_text("time,id,source,dest\n")
        with caplog.at_level(logging.WARNING, logger="elevator.io"):
            result = load_requests(str(f))
        assert "No requests found" in caplog.text
        assert result == []


# ---------------------------------------------------------------------------
# I/O — additional coverage
# ---------------------------------------------------------------------------

class TestIoExtra:
    def test_valid_csv_parses_correctly(self, tmp_path):
        f = tmp_path / "ok.csv"
        f.write_text("time,id,source,dest\n0,p1,1,5\n10,p2,3,8\n")
        result = load_requests(str(f))
        assert len(result) == 2
        assert result[0] == {"time": 0, "id": "p1", "source": 1, "dest": 5}
        assert result[1] == {"time": 10, "id": "p2", "source": 3, "dest": 8}

    def test_id_whitespace_stripped(self, tmp_path):
        f = tmp_path / "ws.csv"
        f.write_text("time,id,source,dest\n0, p1 ,1,5\n")
        result = load_requests(str(f))
        assert result[0]["id"] == "p1"

    def test_unicode_error_raises_value_error(self, tmp_path):
        f = tmp_path / "bad.csv"
        f.write_bytes(b"time,id,source,dest\n0,p1,\xff,5\n")
        with pytest.raises(ValueError, match="not valid UTF-8"):
            load_requests(str(f))


# ---------------------------------------------------------------------------
# Stats module
# ---------------------------------------------------------------------------

class TestStats:
    def _passenger(self, pid, request_time, pickup_time, dropoff_time,
                   source=1, dest=5, elevator_id=0):
        p = Passenger(pid, request_time, source, dest)
        p.assigned_elevator = elevator_id
        p.pickup_time = pickup_time
        p.dropoff_time = dropoff_time
        return p

    def test_percentile_single_value(self):
        from elevator.observability.stats import _percentile
        assert _percentile([10], 50) == 10.0
        assert _percentile([10], 90) == 10.0

    def test_percentile_interpolates(self):
        from elevator.observability.stats import _percentile
        # [0, 10]: idx=0.5 → 0 + 10*0.5 = 5.0
        assert _percentile([0, 10], 50) == 5.0

    def test_percentile_exact_index(self):
        from elevator.observability.stats import _percentile
        # [1, 5, 9]: idx for p50 = 1.0 → sorted[1] = 5
        assert _percentile([1, 5, 9], 50) == 5.0

    def test_summarize_single_value(self):
        from elevator.observability.stats import _summarize
        s = _summarize([8])
        assert s["min"] == 8
        assert s["max"] == 8
        assert s["avg"] == 8.0
        assert s["stddev"] == 0.0
        assert s["count"] == 1

    def test_summarize_multiple_values(self):
        from elevator.observability.stats import _summarize
        # Population stddev of [2,4,4,4,5,5,7,9] = 2.0, avg = 5.0
        s = _summarize([2, 4, 4, 4, 5, 5, 7, 9])
        assert s["min"] == 2
        assert s["max"] == 9
        assert abs(s["avg"] - 5.0) < 1e-9
        assert abs(s["stddev"] - 2.0) < 1e-9
        assert s["count"] == 8

    def test_summarize_empty_returns_none_fields(self):
        from elevator.observability.stats import _summarize
        s = _summarize([])
        assert s["min"] is None
        assert s["max"] is None
        assert s["avg"] is None
        assert s["count"] == 0

    def test_compute_statistics_unserved(self):
        from elevator.observability.stats import compute_statistics
        served = self._passenger("p1", 0, 0, 4)
        unserved = Passenger("p2", 0, 1, 5)  # no pickup/dropoff
        stats = compute_statistics([served, unserved])
        assert stats["total"] == 2
        assert stats["served"] == 1
        assert stats["unserved"] == 1
        assert abs(stats["service_rate"] - 0.5) < 1e-9

    def test_compute_statistics_service_rate_none_when_empty(self):
        from elevator.observability.stats import compute_statistics
        stats = compute_statistics([])
        assert stats["service_rate"] is None
        assert stats["total"] == 0

    def test_compute_statistics_zero_wait_count(self):
        from elevator.observability.stats import compute_statistics
        p = self._passenger("p1", 0, 0, 4)  # wait_time = 0
        stats = compute_statistics([p])
        assert stats["zero_wait_count"] == 1

    def test_compute_statistics_long_wait_count(self):
        from elevator.observability.stats import compute_statistics
        p = self._passenger("p1", 0, 25, 30)  # wait_time = 25 > threshold 20
        stats = compute_statistics([p])
        assert stats["long_wait_count"] == 1

    def test_compute_statistics_wait_buckets(self):
        from elevator.observability.stats import compute_statistics
        p1 = self._passenger("p1", 0, 3, 8, elevator_id=0)    # wait=3  → 0-5
        p2 = self._passenger("p2", 0, 10, 15, elevator_id=0)  # wait=10 → 6-20
        p3 = self._passenger("p3", 0, 30, 35, elevator_id=0)  # wait=30 → 21-50
        p4 = self._passenger("p4", 0, 60, 70, elevator_id=0)  # wait=60 → 51+
        stats = compute_statistics([p1, p2, p3, p4])
        assert stats["wait_buckets"]["0-5 ticks"] == 1
        assert stats["wait_buckets"]["6-20 ticks"] == 1
        assert stats["wait_buckets"]["21-50 ticks"] == 1
        assert stats["wait_buckets"]["51+ ticks"] == 1

    def test_compute_statistics_per_elevator_includes_zero_served(self):
        from elevator.observability.stats import compute_statistics
        p = self._passenger("p1", 0, 0, 4, elevator_id=0)
        # Pass num_elevators=2 so elevator 1 (zero served) still appears
        stats = compute_statistics([p], num_elevators=2)
        assert 0 in stats["per_elevator"]
        assert 1 in stats["per_elevator"]
        assert stats["per_elevator"][1]["served"] == 0
        assert stats["per_elevator"][1]["avg_wait"] is None

    def test_compute_statistics_per_elevator_auto_detect(self):
        from elevator.observability.stats import compute_statistics
        p = self._passenger("p1", 0, 0, 5, elevator_id=2)
        stats = compute_statistics([p])
        assert 2 in stats["per_elevator"]
        assert stats["per_elevator"][2]["served"] == 1

    def test_save_statistics_writes_file(self, tmp_path):
        from elevator.observability.stats import compute_statistics, save_statistics
        p = self._passenger("p1", 0, 1, 5)
        stats = compute_statistics([p])
        out = str(tmp_path / "stats.log")
        save_statistics(stats, out)
        content = open(out, encoding="utf-8").read()
        assert "PASSENGER STATISTICS" in content
        assert "Served" in content

    def test_format_statistics_shows_unserved_warning(self):
        from elevator.observability.stats import compute_statistics, _format_statistics
        served = self._passenger("p1", 0, 0, 4)
        unserved = Passenger("p2", 0, 1, 5)
        stats = compute_statistics([served, unserved])
        output = _format_statistics(stats)
        assert "*** WARNING ***" in output


# ---------------------------------------------------------------------------
# Metrics module
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_tick_accumulates_counters(self):
        from elevator.observability.metrics import SimulationMetrics
        m = SimulationMetrics()
        m.begin_tick(0)
        m.record_assignment()
        m.record_assignment()
        m.record_pickup()
        m.record_dropoff()
        e = Elevator(0, 10, 8)
        e.passengers = ["p1", "p2"]
        m.end_tick([e], {})
        assert len(m.ticks) == 1
        t = m.ticks[0]
        assert t.tick == 0
        assert t.assignments == 2
        assert t.pickups == 1
        assert t.dropoffs == 1

    def test_elevator_utilisation(self):
        from elevator.observability.metrics import SimulationMetrics
        m = SimulationMetrics()
        m.begin_tick(0)
        e0 = Elevator(0, 10, 4)
        e0.passengers = ["p1", "p2"]   # 2/4
        e1 = Elevator(1, 10, 4)        # 0/4
        m.end_tick([e0, e1], {})
        # total capacity=8, used=2 → 0.25
        assert abs(m.ticks[0].elevator_utilisation - 0.25) < 1e-4

    def test_queue_depth_counts_waiting_only(self):
        from elevator.observability.metrics import SimulationMetrics
        m = SimulationMetrics()
        m.begin_tick(0)
        waiting = Passenger("p1", 0, 1, 5)          # no pickup_time → is_waiting
        riding = Passenger("p2", 0, 1, 5)
        riding.pickup_time = 0                       # is_riding
        e = Elevator(0, 10, 8)
        m.end_tick([e], {"p1": waiting, "p2": riding})
        assert m.ticks[0].queue_depth == 1

    def test_record_before_begin_tick_is_noop(self):
        from elevator.observability.metrics import SimulationMetrics
        m = SimulationMetrics()
        m.record_assignment()   # no active tick — must not raise
        m.record_pickup()
        m.record_dropoff()
        assert m.ticks == []

    def test_save_metrics_csv(self, tmp_path):
        from elevator.observability.metrics import SimulationMetrics
        m = SimulationMetrics()
        e = Elevator(0, 10, 8)
        m.begin_tick(0)
        m.record_assignment()
        m.end_tick([e], {})
        m.begin_tick(1)
        m.end_tick([e], {})
        out = str(tmp_path / "metrics.csv")
        m.save(out)
        with open(out) as f:
            rows = list(csv_mod.DictReader(f))
        assert len(rows) == 2
        assert rows[0]["tick"] == "0"
        assert rows[0]["assignments"] == "1"
        assert rows[1]["tick"] == "1"
        assert rows[1]["assignments"] == "0"


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
# Log filter and formatter
# ---------------------------------------------------------------------------

class TestLogFilter:
    def test_stamps_request_id_from_context(self):
        from elevator.observability.context import request_id_var
        from elevator.observability.filter import RequestIdFilter
        token = request_id_var.set("abc123")
        try:
            record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
            RequestIdFilter().filter(record)
            assert record.request_id == "abc123"
        finally:
            request_id_var.reset(token)

    def test_default_dash_when_no_context(self):
        from elevator.observability.filter import RequestIdFilter
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        RequestIdFilter().filter(record)
        assert record.request_id == "-"

    def test_filter_always_returns_true(self):
        from elevator.observability.filter import RequestIdFilter
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert RequestIdFilter().filter(record) is True


class TestJsonFormatter:
    def test_format_produces_valid_json_with_expected_keys(self):
        from elevator.observability.formatter import JsonFormatter
        record = logging.LogRecord("mylogger", logging.WARNING, "", 0, "hello", (), None)
        record.request_id = "xyz"
        data = json.loads(JsonFormatter().format(record))
        assert data["level"] == "WARNING"
        assert data["logger"] == "mylogger"
        assert data["msg"] == "hello"
        assert data["request_id"] == "xyz"
        assert "ts" in data

    def test_format_missing_request_id_defaults_to_dash(self):
        from elevator.observability.formatter import JsonFormatter
        record = logging.LogRecord("mylogger", logging.INFO, "", 0, "msg", (), None)
        data = json.loads(JsonFormatter().format(record))
        assert data["request_id"] == "-"


# ---------------------------------------------------------------------------
# Event listeners
# ---------------------------------------------------------------------------

class TestEventListeners:
    def test_all_hooks_fire_with_correct_args(self):
        from elevator.observability.events import SimulationEventListener
        events = []

        class Recorder(SimulationEventListener):
            def on_passenger_assigned(self, passenger, elevator_id, tick):
                events.append(("assigned", passenger.id, elevator_id))
            def on_passenger_boarded(self, passenger, elevator, tick):
                events.append(("boarded", passenger.id, elevator.id))
            def on_passenger_alighted(self, passenger, elevator, tick):
                events.append(("alighted", passenger.id))
            def on_tick_complete(self, tick):
                events.append(("tick",))
            def on_simulation_complete(self, stats, tick):
                events.append(("complete", stats["served"]))

        sim = ElevatorSimulation(
            num_elevators=1, num_floors=10, capacity=8, listeners=[Recorder()]
        )
        sim.run([_req(0, "p1", 1, 5)])

        types = {e[0] for e in events}
        assert types == {"assigned", "boarded", "alighted", "tick", "complete"}

        assigned = next(e for e in events if e[0] == "assigned")
        assert assigned[1] == "p1"
        assert assigned[2] == 0

        complete = next(e for e in events if e[0] == "complete")
        assert complete[1] == 1


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


# ---------------------------------------------------------------------------
# Elevator model — edge cases
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


# ---------------------------------------------------------------------------
# Simulation — metrics integration
# ---------------------------------------------------------------------------

class TestSimulationMetricsIntegration:
    def test_per_tick_metrics_accumulated(self):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=8)
        sim.run([_req(0, "p1", 1, 5)])
        assert len(sim.metrics.ticks) > 0
        assert sum(t.assignments for t in sim.metrics.ticks) == 1
        assert sum(t.pickups for t in sim.metrics.ticks) == 1
        assert sum(t.dropoffs for t in sim.metrics.ticks) == 1

    def test_save_metrics_produces_valid_csv(self, tmp_path):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=8)
        sim.run([_req(0, "p1", 1, 5)])
        out = str(tmp_path / "metrics.csv")
        sim.save_metrics(out)
        with open(out) as f:
            rows = list(csv_mod.DictReader(f))
        assert len(rows) > 0
        assert {"tick", "assignments", "pickups", "dropoffs",
                "queue_depth", "elevator_utilisation"} <= rows[0].keys()
        assert sum(int(r["assignments"]) for r in rows) == 1

    def test_save_statistics_writes_formatted_output(self, tmp_path):
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=8)
        sim.run([_req(0, "p1", 1, 5)])
        out = str(tmp_path / "stats.log")
        sim.save_statistics(out)
        content = open(out, encoding="utf-8").read()
        assert "PASSENGER STATISTICS" in content
        assert "Served" in content
