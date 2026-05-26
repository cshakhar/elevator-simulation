#!/usr/bin/env python3
"""
Optional: plot elevator positions over time.
Requires: pip install matplotlib

Usage
-----
  python visualize.py
  python visualize.py --input output/positions_nearest_car.csv --save chart.png
  python visualize.py --metrics output/metrics.csv
  python visualize.py --pattern office --max-time 300
  python visualize.py --metrics output/metrics.csv --pattern office --max-time 300 --save chart.png
"""
import argparse
import csv
import os
import re
import sys

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.lines import Line2D
except ImportError:
    print("matplotlib is not installed.  Run:  pip install matplotlib")
    sys.exit(1)

# Linestyle per direction: solid=up, dashed=down, dotted=idle
_DIR_STYLES = {1: "-", -1: "--", 0: ":"}
_DIR_LABELS = {1: "Up", -1: "Down", 0: "Idle"}
_DIR_ALPHA   = {1: 0.9, -1: 0.9,  0: 0.45}

# Background phase bands per traffic pattern
_PHASE_DEFS = {
    "office": [
        (0.00, 0.30, "#fff8dc", "Morning rush"),
        (0.30, 0.65, "#e8f4f8", "Midday"),
        (0.65, 1.00, "#fce8e8", "Evening rush"),
    ],
    "residential": [
        (0.00, 0.25, "#fce8e8", "Morning departure"),
        (0.25, 0.70, "#e8f4f8", "Daytime"),
        (0.70, 1.00, "#e8f8ec", "Evening return"),
    ],
}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_positions(path: str):
    times, elevators = [], {}
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for line_num, row in enumerate(csv.DictReader(f), start=2):
                try:
                    times.append(int(row["time"]))
                except KeyError:
                    raise ValueError(f"{path!r} is missing a 'time' column.")
                except ValueError:
                    raise ValueError(f"{path!r} line {line_num}: non-integer value in 'time' column.")
                for k, v in row.items():
                    if k.startswith("elevator_"):
                        try:
                            elevators.setdefault(k, []).append(int(v))
                        except ValueError:
                            raise ValueError(
                                f"{path!r} line {line_num}: non-integer value in column {k!r}."
                            )
    except UnicodeDecodeError:
        raise ValueError(f"{path!r} is not a valid UTF-8 file.")
    return times, elevators


def load_metrics(path: str):
    ticks, queue_depth, utilisation = [], [], []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for line_num, row in enumerate(csv.DictReader(f), start=2):
                try:
                    ticks.append(int(row["tick"]))
                    queue_depth.append(int(row["queue_depth"]))
                    utilisation.append(float(row["elevator_utilisation"]))
                except KeyError as e:
                    raise ValueError(f"{path!r} is missing column {e}.")
                except ValueError:
                    raise ValueError(f"{path!r} line {line_num}: non-numeric value in metrics.")
    except UnicodeDecodeError:
        raise ValueError(f"{path!r} is not a valid UTF-8 file.")
    return ticks, queue_depth, utilisation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _directions(floors: list) -> list:
    """Return a direction int per floor entry: 1=up, -1=down, 0=idle."""
    if len(floors) < 2:
        return [0] * len(floors)
    dirs = []
    for i in range(len(floors) - 1):
        if floors[i + 1] > floors[i]:
            dirs.append(1)
        elif floors[i + 1] < floors[i]:
            dirs.append(-1)
        else:
            dirs.append(0)
    dirs.append(dirs[-1])   # last point inherits last direction
    return dirs


def _algo_name_from_path(path: str) -> str:
    """Extract algorithm name from a filename like positions_nearest_car.csv."""
    stem = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r"(nearest_car|round_robin|zone_based)", stem)
    return m.group(1).replace("_", " ").title() if m else None


def _draw_phase_bands(ax, max_time: int, pattern: str) -> list:
    handles = []
    for start_frac, end_frac, color, label in _PHASE_DEFS.get(pattern, []):
        x0 = int(start_frac * max_time)
        x1 = int(end_frac * max_time)
        ax.axvspan(x0, x1, color=color, alpha=0.55, zorder=0)
        handles.append(mpatches.Patch(color=color, alpha=0.55, label=label))
    return handles


# ---------------------------------------------------------------------------
# Main plot
# ---------------------------------------------------------------------------

def plot(
    path: str,
    save_to: str = None,
    metrics_path: str = None,
    pattern: str = None,
    max_time: int = None,
) -> None:
    times, elevators = load_positions(path)
    if not times:
        raise ValueError(f"{path!r} contains no data rows.")

    has_metrics = metrics_path is not None
    fig, axes = plt.subplots(
        2 if has_metrics else 1,
        1,
        figsize=(14, 9 if has_metrics else 6),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]} if has_metrics else None,
    )
    ax_pos = axes[0] if has_metrics else axes
    ax_met = axes[1] if has_metrics else None

    colors = plt.cm.tab10.colors
    t_max = max_time if max_time is not None else max(times)

    # --- Phase bands (drawn first so they sit behind lines) ---
    phase_handles = []
    if pattern in _PHASE_DEFS:
        phase_handles = _draw_phase_bands(ax_pos, t_max, pattern)
        if ax_met:
            _draw_phase_bands(ax_met, t_max, pattern)

    # --- Elevator position lines ---
    elevator_handles = []
    for i, (name, floors) in enumerate(sorted(elevators.items())):
        color = colors[i % len(colors)]
        dirs = _directions(floors)
        label = name.replace("_", " ").title()

        # Draw runs of the same direction as separate line segments
        # so each segment gets the matching linestyle.
        j = 0
        while j < len(floors):
            k = j + 1
            while k < len(floors) and dirs[k] == dirs[j]:
                k += 1
            # include one overlap point so segments visually connect
            end = min(k, len(floors) - 1) + 1
            d = dirs[j]
            ax_pos.plot(
                times[j:end],
                floors[j:end],
                color=color,
                linewidth=1.8,
                linestyle=_DIR_STYLES[d],
                alpha=_DIR_ALPHA[d],
            )
            j = k

        # Reversal markers: dots where direction flips (up<->down)
        rev_t, rev_f = [], []
        for idx in range(1, len(dirs)):
            prev, curr = dirs[idx - 1], dirs[idx]
            if prev != 0 and curr != 0 and curr != prev:
                rev_t.append(times[idx])
                rev_f.append(floors[idx])
        if rev_t:
            ax_pos.scatter(rev_t, rev_f, color=color, s=35, zorder=5, marker="o", linewidths=0)

        elevator_handles.append(
            Line2D([0], [0], color=color, linewidth=2.5, linestyle="-", label=label)
        )

    # --- Legend ---
    dir_handles = [
        Line2D([0], [0], color="black", linewidth=2, linestyle=_DIR_STYLES[d], label=_DIR_LABELS[d])
        for d in (1, -1, 0)
    ]
    ax_pos.legend(
        handles=elevator_handles + dir_handles + phase_handles,
        loc="upper right",
        fontsize=9,
        framealpha=0.85,
    )

    # --- Title ---
    algo = _algo_name_from_path(path)
    title = "Elevator Positions Over Time"
    if algo:
        title += f"  —  {algo}"
    ax_pos.set_title(title, fontsize=14, fontweight="bold")
    ax_pos.set_ylabel("Floor", fontsize=12)
    ax_pos.grid(True, alpha=0.3)
    if not has_metrics:
        ax_pos.set_xlabel("Time Step", fontsize=12)

    # --- Metrics panel ---
    if ax_met is not None:
        ticks, queue_depth, utilisation = load_metrics(metrics_path)
        c_queue = "#e67e22"
        c_util  = "#2980b9"

        ax_met.bar(ticks, queue_depth, color=c_queue, alpha=0.45, width=1.0, label="Queue depth")
        ax_met.set_ylabel("Queue depth", fontsize=10, color=c_queue)
        ax_met.tick_params(axis="y", labelcolor=c_queue)
        ax_met.grid(True, alpha=0.2)

        ax2 = ax_met.twinx()
        ax2.plot(ticks, utilisation, color=c_util, linewidth=1.5, label="Fleet utilisation")
        ax2.set_ylabel("Fleet utilisation", fontsize=10, color=c_util)
        ax2.set_ylim(0, 1)
        ax2.tick_params(axis="y", labelcolor=c_util)

        met_handles = [
            mpatches.Patch(color=c_queue, alpha=0.45, label="Queue depth"),
            Line2D([0], [0], color=c_util, linewidth=1.5, label="Fleet utilisation"),
        ]
        ax_met.legend(handles=met_handles, loc="upper right", fontsize=9, framealpha=0.85)
        ax_met.set_xlabel("Time Step", fontsize=12)

    fig.tight_layout()

    if save_to:
        fig.savefig(save_to, dpi=150, bbox_inches="tight")
        print(f"Chart saved -> {save_to}")
    else:
        plt.show()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Visualise elevator simulation output")
    p.add_argument("--input", default="output/elevator_positions.csv",
                   help="Position log CSV (default: output/elevator_positions.csv)")
    p.add_argument("--save", default=None,
                   help="Save chart to file instead of opening an interactive window")
    p.add_argument("--metrics", default=None, metavar="PATH",
                   help="Per-tick metrics CSV (e.g. output/metrics.csv) — "
                        "adds a queue-depth / fleet-utilisation panel below the position chart")
    p.add_argument("--pattern", choices=list(_PHASE_DEFS), default=None,
                   help="Traffic pattern used when generating the data — "
                        "draws labelled phase bands on the chart (office or residential)")
    p.add_argument("--max-time", type=int, default=None,
                   help="Max time used when generating data; required for accurate phase-band "
                        "boundaries when --pattern is set (defaults to the last tick in the CSV)")
    args = p.parse_args()
    try:
        plot(args.input, args.save, args.metrics, args.pattern, args.max_time)
    except FileNotFoundError as e:
        print(f"ERROR: file not found: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
