#!/usr/bin/env python3
"""
Optional: plot elevator positions over time.
Requires: pip install matplotlib

Usage
-----
  python visualize.py
  python visualize.py --input output/positions_nearest_car.csv --save chart.png
"""
import argparse
import csv
import sys

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
except ImportError:
    print("matplotlib is not installed.  Run:  pip install matplotlib")
    sys.exit(1)


def load_log(path: str):
    times, elevators = [], {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            times.append(int(row["time"]))
            for k, v in row.items():
                if k.startswith("elevator_"):
                    elevators.setdefault(k, []).append(int(v))
    return times, elevators


def plot(path: str, save_to: str = None) -> None:
    times, elevators = load_log(path)
    colors = plt.cm.tab10.colors

    fig, ax = plt.subplots(figsize=(14, 6))
    patches = []
    for i, (name, floors) in enumerate(sorted(elevators.items())):
        color = colors[i % len(colors)]
        ax.plot(times, floors, color=color, linewidth=1.5, alpha=0.85)
        patches.append(
            mpatches.Patch(color=color, label=name.replace("_", " ").title())
        )

    ax.set_xlabel("Time Step", fontsize=12)
    ax.set_ylabel("Floor", fontsize=12)
    ax.set_title("Elevator Positions Over Time", fontsize=14, fontweight="bold")
    ax.legend(handles=patches, loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if save_to:
        fig.savefig(save_to, dpi=150, bbox_inches="tight")
        print(f"Chart saved → {save_to}")
    else:
        plt.show()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="output/elevator_positions.csv")
    p.add_argument("--save", default=None, help="Save to file instead of showing")
    args = p.parse_args()
    plot(args.input, args.save)
