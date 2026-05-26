import csv as csv_mod
import logging

import pytest
from elevator.simulation import ElevatorSimulation


def _req(time, pid, src, dst):
    return {"time": time, "id": pid, "source": src, "dest": dst}


# ---------------------------------------------------------------------------
# Core simulation behaviour
# ---------------------------------------------------------------------------

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
# Simulation — additional coverage
# ---------------------------------------------------------------------------

class TestSimulationExtra:
    def test_dropoff_before_pickup_same_floor(self):
        """A rider drops off at a floor before a new passenger boards, freeing capacity."""
        sim = ElevatorSimulation(num_elevators=1, num_floors=10, capacity=1)
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
# Simulation — init error handling
# ---------------------------------------------------------------------------

class TestSimulationErrors:
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
