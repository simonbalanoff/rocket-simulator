# Rocket Landing Simulator

A 2D rocket landing simulator built with Pygame and Pymunk. A fully autonomous autopilot launches the rocket, navigates it across to a moveable landing platform, and attempts a propulsive vertical landing - all driven by a Kalman-filtered state estimator and a multi-phase guidance controller.

---

## Demo
https://github.com/user-attachments/assets/ae00e4d1-776c-4bc3-8fef-9c34b12ced33

*Autonomous rocket landing simulation - Kalman-filtered autopilot, multi-phase guidance controller*

---

## Features

- **Autonomous autopilot** - multi-phase flight controller (launch → ascent → coast → descent → terminal) handles the entire mission without any manual input
- **Kalman state estimator** - filters noisy telemetry for altitude, velocity, and attitude before passing it to the guidance logic
- **Physics simulation** - rigid-body dynamics and collision detection via Pymunk (2D Chipmunk wrapper)
- **Moveable landing pad** - drag the landing platform anywhere before launch; the autopilot recalculates its trajectory accordingly
- **Live telemetry HUD** - altitude, velocity, fuel, angle, and autopilot phase displayed in real time
- **Pannable/zoomable viewport** - scroll-wheel zoom, middle-mouse pan, toolbar zoom buttons
- **Resizable window** - layout adapts to any window size

---

## Project Structure

```
├── main.py               # Entry point, game loop, rendering
├── rocket.py             # Rocket physics body, thrust, telemetry, drawing
├── autopilot.py          # Kalman estimator + multi-phase guidance controller
├── landing_platform.py   # Moveable landing pad - physics segment + drag gizmo
├── ui.py                 # SimControls, Toolbar, TelemetryHUD, AutopilotHUD
├── theme.py              # Shared colors, font cache, drawing helpers
├── requirements.txt      # Runtime dependencies
└── tests/                # Headless physics and guidance regression tests
```

---

## Requirements

- Python 3.10+
- [Pygame](https://www.pygame.org/) - rendering and input
- [Pymunk](http://www.pymunk.org/) - 2D physics
- NumPy - coupled state estimation
- Optional: SciPy and Matplotlib - tuning and analysis

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

---

## Running

```bash
python main.py
```

---

## Validation

```bash
python -m unittest discover -s tests -v
```

The headless regression suite checks complete missions on both sides of the launch
pad and at different elevations, contact-based landing detection, fuel limits,
platform geometry, and angle filtering across zero. GitHub Actions runs the suite
on Python 3.10, 3.12, and 3.13.

Physics and guidance use a fixed 120 Hz timestep, independent of rendering speed.
Long frames are capped at 100 ms to avoid unstable catch-up after a window stall.
A landing requires actual contact with the target deck, an approach speed below
30 px/s, an attitude within 10 degrees of upright, and the rocket body inside the
deck edges. Ground contact is a failed mission. Completed flights freeze for review;
Stop returns to placement and Reset restores the original pad and camera.

Coordinates, velocities, and gravity use pixels and seconds; fuel uses arbitrary
units. This is a simplified 2D guidance demonstrator, not a real-world flight model.
Very distant or elevated pads may exceed the rocket's fuel or thrust envelope.

## Controls

### Placement mode (before launch)

| Input | Action |
|---|---|
| Drag landing pad gizmo | Move landing pad (X / Y axes) |
| WASD | Nudge landing pad |
| Scroll wheel | Zoom in / out |
| Middle mouse drag | Pan camera |
| Enter | Launch |

### Simulation mode

| Input | Action |
|---|---|
| R | Stop simulation, return to placement |
| Scroll wheel | Zoom in / out |
| Middle mouse drag | Pan camera |
| Escape | Quit |

UI buttons on screen handle Simulate / Stop / Reset as well.

---

## How the Autopilot Works

The autopilot runs a closed-loop guidance cycle every frame (`autopilot.update(telemetry, dt)`):

**State estimation** - a NumPy Kalman filter jointly estimates horizontal position, rocket-bottom height, both velocities, attitude, and angular velocity. Its time-dependent motion model couples position to velocity, unwraps angle measurements across zero, and propagates covariance using the Joseph update. Altitude is derived from the filtered bottom height.

**Flight phases** - the controller moves through phases in sequence, each with its own throttle and attitude targets:

| Phase | Description |
|---|---|
| `launch` | Full thrust, slight lean toward the landing zone |
| `ascent` | Throttles to climb rate target, steers laterally |
| `coast` | Minimal thrust, lets apogee develop |
| `descent` | Throttles to a speed profile keyed to altitude |
| `terminal` | Fine lateral correction, bleeds speed to a soft touchdown |

**Attitude control** - a PD controller computes a torque command from the angle error and angular rate at each phase, with phase-specific gains.

**Throttle** - vertical throttle is computed from the difference between a reference descent rate and the current vertical velocity, corrected for tilt angle, so thrust is always sufficient to counteract gravity along the vertical axis.

---

## Key Constants

Defined at the top of each file -- easy to tune:

| Constant | File | Default        | Effect |
|---|---|----------------|---|
| `ROCKET_MASS` | `rocket.py` | `5.0`          | Affects thrust-to-weight ratio |
| `THRUST_FORCE` | `rocket.py` | `5600.0`       | Peak engine thrust |
| `FUEL_CAPACITY` | `rocket.py` | `300.0`        | Total fuel units |
| `FUEL_BURN` | `rocket.py` | `12.0`         | Fuel burn rate per second at full throttle |
| `GROUND_Y` | `main.py` | `HEIGHT - 200` | World ground level in pixels |
| `FPS` | `main.py` | `60`           | Rendering frame rate |

## Recording and flight analysis

Install the optional analysis tools:

```bash
python -m pip install -r requirements-analysis.txt
```

Run a reproducible headless mission and create a CSV plus a six-panel plot:

```bash
python flight_analysis.py --x 960 --y 570 --csv reports/flight.csv --plot reports/flight.png
```

`--y` is the pad base coordinate, increasing downward; the deck surface is 16 px
above it. The mission prints outcome, duration, lateral error, fuel used, and
approach speed. `--duration` sets a simulation-time limit (default 60 seconds).
No Pygame window is opened. CSV recording only needs the runtime requirements.
Plots show trajectory, altitude, actual and target vertical velocity, actual and
target attitude, commanded throttle, and fuel. Gray lines mark phase transitions;
velocity targets are blank during phases without a velocity reference.

Record interactive flights, including partial flights when stopped or closed:

```bash
python main.py --record-dir reports/flights
python flight_analysis.py --from-csv reports/flights/flight-TIMESTAMP.csv --plot reports/replay.png
```

Each flight gets its own timestamped CSV. Samples contain timestamps, telemetry,
commands, controller targets, and landing-pad coordinates. The final sample marks
landed or crashed flights. Throttle is the commanded fraction; fuel exhaustion can
limit the force actually delivered.

## Controller tuning

```bash
python tune_controller.py --iterations 10 --population 5 --seed 42 --output reports/controller.json
python flight_analysis.py --settings reports/controller.json --plot reports/tuned.png
python main.py --settings reports/controller.json
```

SciPy differential evolution searches attitude strength, lateral position gain,
vertical velocity gain, and terminal descent speed. The score averages a large
failure penalty plus lateral error, fuel consumption, and approach-speed costs
across five training missions. The baseline is included in the search and retained
if the candidate does not improve its score. A separate `.report.json` contains
baseline and candidate results, optimizer status, and three holdout missions.
Holdouts are reported without influencing selection; review them before adopting
settings. The built-in defaults are never overwritten.

Tuning runs many complete simulations and can take several minutes. A quick
pipeline check is `--iterations 0 --population 1`; this evaluates the initial
population only. A better training score does not guarantee better results for
every placement, particularly pads overlapping the launch support or missions
outside the fuel envelope. Tune files contain only the four controller settings
and can be inspected or edited as JSON.
