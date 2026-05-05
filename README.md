# Rocket Landing Simulator

A 2D rocket landing simulator built with Pygame and Pymunk. A fully autonomous autopilot launches the rocket, navigates it across to a moveable landing platform, and attempts a propulsive vertical landing - all driven by a Kalman-filtered state estimator and a multi-phase guidance controller.

---

## Features

- **Autonomous autopilot** - multi-phase flight controller (launch → ascent → coast → descent → terminal) handles the entire mission without any manual input
- **Kalman state estimator** - filters noisy telemetry for altitude, velocity, and attitude before passing it to the guidance logic
- **Physics simulation** - rigid-body dynamics and collision detection via Pymunk (2D Chipmunk wrapper)
- **Moveable landing pad** - drag the landing platform anywhere before launch; the autopilot recalculates its trajectory accordingly
- **Live telemetry HUD** - altitude, velocity, fuel, angle, and autopilot phase displayed in real time
- **Pannable / zoomable viewport** - scroll-wheel zoom, middle-mouse pan, toolbar zoom buttons
- **Resizable window** - layout adapts to any window size

---

## Project Structure

```
├── main.py               # Entry point, game loop, rendering
├── rocket.py             # Rocket physics body, thrust, telemetry, drawing
├── autopilot.py          # Kalman estimator + multi-phase guidance controller
├── landing_platform.py   # Moveable landing pad - physics segment + drag gizmo
└── ui.py                 # SimControls, Toolbar, TelemetryHUD, AutopilotHUD
```

---

## Requirements

- Python 3.8+
- [Pygame](https://www.pygame.org/) - rendering and input
- [Pymunk](http://www.pymunk.org/) - 2D physics

Install dependencies:

```bash
pip install pygame pymunk
```

---

## Running

```bash
python main.py
```

---

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

**State estimation** - raw telemetry (altitude, vx, vy, angle) is smoothed by four independent 1D Kalman filters before any control decisions are made.

**Flight phases** - the controller moves through phases in sequence, each with its own throttle and attitude targets:

| Phase | Description |
|---|---|
| `launch` | Full thrust, slight lean toward the landing zone |
| `ascent` | Throttles to climb rate target, steers laterally |
| `coast` | Minimal thrust, lets apogee develop |
| `descent` | Throttles to a speed profile keyed to altitude |
| `terminal` | Fine lateral correction, bleeds speed to a soft touchdown |

**Attitude control** - a PD controller computes a torque command from the angle error and angular rate at each phase, with phase-specific gains.

**Throttle** - vertical throttle is computed from the difference between a reference descent rate and the current vertical velocity, corrected for tilt angle so thrust is always sufficient to counteract gravity along the vertical axis.

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
| `FPS` | `main.py` | `60`           | Simulation frame rate |