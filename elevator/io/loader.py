import csv
import logging
from typing import Dict, List

from elevator.core.constants import CSV_COLUMNS

# Explicit logger name keeps it stable regardless of module path.
logger = logging.getLogger("elevator.io")


def load_requests(filepath: str) -> List[Dict]:
    """Parse a passenger request CSV and return a list of request dicts."""
    requests = []
    required_columns = set(CSV_COLUMNS)
    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is not None:
                missing_cols = required_columns - set(reader.fieldnames)
                if missing_cols:
                    raise ValueError(
                        f"CSV {filepath!r} is missing required columns: {sorted(missing_cols)}"
                    )
            for line_num, row in enumerate(reader, start=2):
                try:
                    requests.append(
                        {
                            "time": int(row["time"]),
                            "id": row["id"].strip(),
                            "source": int(row["source"]),
                            "dest": int(row["dest"]),
                        }
                    )
                except (KeyError, ValueError) as exc:
                    raise ValueError(
                        f"CSV {filepath!r} line {line_num}: could not parse row {dict(row)} — {exc}"
                    ) from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"CSV {filepath!r} is not valid UTF-8: {exc}") from exc
    if not requests:
        logger.warning("No requests found in %r; simulation will be empty.", filepath)
    return requests
