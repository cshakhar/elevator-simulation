import logging

import pytest
from elevator.io import load_requests


# ---------------------------------------------------------------------------
# I/O — request loading
# ---------------------------------------------------------------------------

class TestLoadRequests:
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

    def test_missing_columns_raises(self, tmp_path):
        f = tmp_path / "bad.csv"
        f.write_text("time,id\n0,p1\n")
        with pytest.raises(ValueError, match="missing required columns"):
            load_requests(str(f))

    def test_malformed_row_raises_with_line_number(self, tmp_path):
        f = tmp_path / "bad.csv"
        f.write_text("time,id,source,dest\n0,p1,abc,10\n")
        with pytest.raises(ValueError, match="line 2"):
            load_requests(str(f))

    def test_empty_csv_warns(self, tmp_path, caplog):
        f = tmp_path / "empty.csv"
        f.write_text("time,id,source,dest\n")
        with caplog.at_level(logging.WARNING, logger="elevator.io"):
            result = load_requests(str(f))
        assert "No requests found" in caplog.text
        assert result == []
