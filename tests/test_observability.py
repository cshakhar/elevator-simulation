import csv as csv_mod
import json
import logging

import pytest
from elevator.core.models import Elevator, Passenger
from elevator.simulation import ElevatorSimulation


def _req(time, pid, src, dst):
    return {"time": time, "id": pid, "source": src, "dest": dst}


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
