# Rocket Landing Simulator

A local 2D rocket landing simulator with a browser interface and a Python/Pymunk physics engine. The original Pygame desktop interface remains available. A fully autonomous autopilot launches the rocket, navigates it across to a moveable landing platform, and attempts a propulsive vertical landing - all driven by a Kalman-filtered state estimator and a multi-phase guidance controller.

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
- **Mission-control interface** - dark flight workspace, persistent telemetry sidebar, fuel gauge, live velocity history, and guidance sequence
- **Flight tools** - pause/resume, smooth camera follow, fit-to-mission framing, and trajectory trail
- **Pannable/zoomable viewport** - scroll-wheel zoom, middle-mouse pan, toolbar zoom buttons
- **Resizable window** - layout adapts from 800×680 upward, with compact layouts for smaller windows

---

## Project Structure

```
├── web_server.py         # Local HTTP / WebSocket server
├── web/                  # Browser UI: HTML, CSS, canvas rendering
├── simulation.py         # Authoritative fixed-step mission lifecycle
├── physics.py            # Pygame-free rocket and platform dynamics
├── recording.py          # Shared CSV recording
├── main.py               # Optional desktop entry point, game loop, rendering
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
- aiohttp - local web server and live state connection
- Optional: [Pygame](https://www.pygame.org/) - desktop rendering and input
- [Pymunk](http://www.pymunk.org/) - 2D physics
- NumPy - coupled state estimation
- Optional: SciPy and Matplotlib - tuning and analysis

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements-web.txt
```

---

## Running in the browser

```bash
python web_server.py --open
```

Open **http://127.0.0.1:8000** if the browser does not open automatically.
Use `--port 8001` if the default port is occupied, or
`--settings reports/controller.json` to start with a tuned controller.
Stop the server with Ctrl+C.

The server binds only to `127.0.0.1`. The interface uses local HTML, CSS, and
JavaScript with no Node installation, build step, CDN, accounts, or hosted services.
Python owns the simulation at 120 Hz; the browser receives state at approximately
30 Hz and renders it on a canvas. State history is refreshed twice per second.
Neither the browser nor the display frame rate controls the physics timestep.

Each tab has an independent simulation. Closing or reloading a tab discards that
session; a reconnect starts a new session. Export CSV before leaving to keep the
recording. End flight preserves the last recording for export until the next launch.
Flights stop after 60 simulated seconds if they have not landed or crashed.

Drag the landing pad before launch or enter its coordinates and click Apply.
Drag empty canvas space to pan; scroll to zoom. Fit (F) restores the mission view;
Follow (C) keeps the vehicle centered. The sidebar shows live telemetry, guidance,
and pad configuration. Controller settings JSON files from the tuning script can
be loaded through the expandable settings section. The altitude graph and flight
path remain visible after touchdown. Keyboard shortcuts are listed in the header.

## Optional desktop interface

```bash
python -m pip install -r requirements.txt
python main.py
```

---

## Validation

```bash
python -m pip install -r requirements-analysis.txt -r requirements-web.txt
python -m unittest discover -s tests -v
node --check web/app.js  # Optional JavaScript syntax check
```

The headless regression suite checks complete missions on both sides of the launch
pad and at different elevations, contact-based landing detection, fuel limits,
platform geometry, and angle filtering across zero. Interface tests also cover
control boundaries, pad dragging, camera fitting, pause/resume, resizing, help,
and a complete recorded interactive flight. GitHub Actions runs the suite
on Python 3.10, 3.12, and 3.13. Server tests cover WebSocket controls,
CSV export, independent tab sessions, and localhost/origin validation. The core
is also checked to run without importing Pygame.

Physics and guidance use a fixed 120 Hz timestep, independent of rendering speed.
Long frames are capped at 100 ms to avoid unstable catch-up after a window stall.
A landing requires actual contact with the target deck, an approach speed below
30 px/s, an attitude within 10 degrees of upright, and the rocket body inside the
deck edges. Ground contact is a failed mission. Completed flights freeze for review;
End flight returns to placement and Reset restores the original pad.

Coordinates, velocities, and gravity use pixels and seconds; fuel uses arbitrary
units. This is a simplified 2D guidance demonstrator, not a real-world flight model.
Very distant or elevated pads may exceed the rocket's fuel or thrust envelope.

## Desktop controls

### Placement mode (before launch)

| Input | Action |
|---|---|
| Drag pad / center handle | Move landing pad freely |
| Drag X / Y handle | Move along one axis |
| WASD | Nudge landing pad |
| Scroll wheel | Zoom in / out |
| Middle mouse drag | Pan camera |
| Enter | Launch |
| V / H | Select pad placement / pan tool |

### Simulation mode

| Input | Action |
|---|---|
| R | End flight, return to placement |
| Space | Pause / resume |
| C | Toggle smooth camera follow |
| F | Fit launch pad, landing pad, and ascent area |
| + / - | Zoom around viewport center |
| ? | Toggle controls guide |
| Scroll wheel | Zoom in / out |
| Middle mouse drag | Pan camera |
| Escape | Close controls guide, or quit |

The launch bar provides Launch, End flight, Reset scene, and Pause controls.
The left toolbar provides placement, pan, zoom, fit, follow, and help. Scroll-wheel
zoom stays anchored to the pointer. Manual panning exits follow mode.
Completed missions stay visible for review, with a touchdown or failure status.

---

## How the Autopilot Works

The autopilot runs a closed-loop guidance cycle every physics step (`autopilot.update(telemetry, dt)`):

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
