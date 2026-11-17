"""Headless missions, portable CSV telemetry, and optional Matplotlib reports."""
import argparse
import csv
import json
import math
from pathlib import Path

from autopilot import ControllerSettings
from recording import FlightRecorder
from simulation import Simulation, DT
from physics import FUEL_CAPACITY

SCENARIOS = [(960, 570), (0, 570), (640, 570), (1200, 570), (960, 450)]


def run_mission(x=960, y=570, settings=None, duration=60, record=True):
    if not all(math.isfinite(value) for value in (x, y, duration)) or duration <= 0:
        raise ValueError('duration must be positive')
    simulation = Simulation(x, y, settings=settings, record=record)
    simulation.launch()
    for _ in range(max(1, int(duration / DT))):
        simulation.step()
        if simulation.state == 'finished':
            break
    rocket = simulation.rocket
    elapsed, recorder = simulation.elapsed, simulation.recorder
    telemetry = rocket.telemetry()
    if record and simulation.state != "finished":
        simulation.record_terminal()
    summary = dict(outcome='landed' if rocket.landed else 'crashed' if rocket.crashed else 'timeout',
                   elapsed=elapsed, landing_error=abs(telemetry['x'] - x),
                   fuel_used=FUEL_CAPACITY - rocket.fuel,
                   approach_speed=max(telemetry['speed'], math.hypot(*rocket._previous_velocity)))
    return summary, recorder


def plot_flight(csv_path, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    with Path(csv_path).open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError('Flight CSV contains no samples')
    def values(key):
        return np.array([float(row[key]) for row in rows])
    t = values('time')
    fig, axes = plt.subplots(3, 2, figsize=(12, 10), constrained_layout=True)
    ax = axes[0, 0]
    ax.plot(values('x'), values('bottom_y'))
    ax.scatter(values('landing_x')[-1], values('surface_y')[-1], marker='x', label='target')
    ax.invert_yaxis()
    ax.set(xlabel='x (px)', ylabel='bottom y (px)', title='Trajectory')
    ax.legend()
    panels = [(axes[0, 1], [('altitude', 'altitude')], 'Altitude (px)'),
              (axes[1, 0], [('vel_x', 'vx'), ('vel_y', 'vy'), ('vy_target', 'vy target')], 'Velocity (px/s)'),
              (axes[1, 1], [('angle', 'angle'), ('angle_target', 'target')], 'Attitude (degrees)'),
              (axes[2, 0], [('throttle', 'throttle')], 'Throttle'),
              (axes[2, 1], [('fuel', 'fuel')], 'Fuel (units)')]
    for ax, series, title in panels:
        for key, label in series:
            data = values(key)
            if key in ('angle', 'angle_target'):
                data = (data + 180) % 360 - 180
            ax.plot(t, data, label=label)
        ax.set(title=title, xlabel='Time (s)')
        ax.grid(alpha=.25)
        ax.legend()
        for i in range(1, len(rows)):
            if rows[i]['phase'] != rows[i-1]['phase']:
                ax.axvline(t[i], color='gray', alpha=.2)
    fig.suptitle('Rocket flight — vertical lines mark guidance phase changes')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--x', type=float, default=960)
    parser.add_argument('--y', type=float, default=570, help='pad base y in pixels')
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--settings', type=Path, help='controller settings JSON from tune_controller.py')
    parser.add_argument('--csv', type=Path, default=Path('reports/flight.csv'))
    parser.add_argument('--plot', type=Path, help='optional output PNG')
    parser.add_argument('--from-csv', type=Path, help='plot a previously recorded flight')
    args = parser.parse_args()
    if args.from_csv:
        if not args.plot:
            parser.error('--from-csv requires --plot')
        plot_flight(args.from_csv, args.plot)
        return
    settings = ControllerSettings(**json.loads(args.settings.read_text())) if args.settings else None
    summary, recorder = run_mission(args.x, args.y, settings, args.duration)
    recorder.save(args.csv)
    print(json.dumps(summary, indent=2))
    if args.plot:
        plot_flight(args.csv, args.plot)


if __name__ == '__main__':
    main()
