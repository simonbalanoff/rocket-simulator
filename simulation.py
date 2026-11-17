"""The authoritative 120 Hz simulation, independent of any UI or server."""
from collections import deque
from dataclasses import asdict
import math

import pymunk

from autopilot import Autopilot, AutopilotCommand, ControllerSettings
from physics import RocketPhysics, PlatformPhysics, ROCKET_H, PLATFORM_W
from recording import FlightRecorder

DT = 1 / 120
GROUND_Y = 600
LAUNCH_X = 320
LAUNCH_SURFACE_Y = 566
MAX_DURATION = 60


class Simulation:
    def __init__(self, x=960, y=570, settings=None, record=True):
        self.settings = settings or ControllerSettings()
        self.record = record
        self.flight_id = 0
        self.last_recording = None
        self._build(x, y)

    def _build(self, x, y):
        self.space = pymunk.Space()
        self.space.gravity = (0, 980)
        for a, b, radius in [((-5000, GROUND_Y), (10000, GROUND_Y), 5),
                              ((255, 568), (385, 568), 2)]:
            segment = pymunk.Segment(self.space.static_body, a, b, radius)
            segment.friction = 1
            self.space.add(segment)
        self.platform = PlatformPhysics(self.space, x, y, GROUND_Y)
        self.rocket = RocketPhysics(self.space, LAUNCH_X, LAUNCH_SURFACE_Y - ROCKET_H / 2, GROUND_Y)
        self.autopilot = Autopilot(self.platform.get_surface_y(), x, LAUNCH_SURFACE_Y, LAUNCH_X, self.settings)
        self.elapsed = 0.
        self.steps = 0
        self.state = 'placement'
        self.outcome = None
        self.recorder = FlightRecorder()
        self.trail = deque(maxlen=1801)
        self.history = deque(maxlen=1801)
        self.command = AutopilotCommand()

    def configure(self, x, y, settings=None):
        if self.state != 'placement':
            raise ValueError('End the flight before changing the landing pad or controller')
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (x, y)):
            raise ValueError('Pad coordinates must be finite numbers')
        if not -1500 <= x <= 4000 or not 50 <= y <= GROUND_Y:
            raise ValueError('Pad X must be between -1500 and 4000; Y between 50 and 600')
        if settings is not None:
            self.settings = settings
        self._build(x, y)
        self.flight_id += 1

    def launch(self):
        if self.state != 'placement':
            raise ValueError('A flight is already active; end it before launching again')
        self.flight_id += 1
        self.last_recording = None
        self.rocket.activate_physics()
        self.rocket.configure_landing_detection(landing_x=self.platform.x,
            landing_surface_y=self.platform.get_surface_y(), landing_half_w=PLATFORM_W / 2,
            launch_x=LAUNCH_X, launch_surface_y=LAUNCH_SURFACE_Y, launch_half_w=65)
        self.state = 'running'

    def pause(self):
        if self.state not in ('running', 'paused'):
            raise ValueError('Only an active flight can be paused or resumed')
        self.state = 'paused' if self.state == 'running' else 'running'

    def stop(self, reset=False):
        if self.recorder.rows:
            self.last_recording = self.recorder
        x, y = (960, 570) if reset else (self.platform.x, self.platform.y)
        self._build(x, y)
        self.flight_id += 1

    def record_terminal(self):
        self.recorder.record(self.elapsed, self.rocket.telemetry(), self.command, {},
                             self.platform.x, self.platform.get_surface_y())

    def step(self):
        if self.state != 'running':
            return
        self.command = self.autopilot.update(self.rocket.telemetry(), DT)
        if self.record:
            self.recorder.record(self.elapsed, self.rocket.telemetry(), self.command,
                                 self.autopilot.targets, self.platform.x, self.platform.get_surface_y())
        self.rocket.apply_autopilot(self.command, DT)
        self.space.step(DT)
        self.rocket.update(DT, True)
        self.steps += 1
        self.elapsed = self.steps * DT
        if self.steps % 4 == 0:
            self.trail.append([self.rocket.body.position.x, self.rocket.body.position.y])
            self.history.append([self.elapsed, self.rocket.telemetry()['altitude'], self.rocket.body.velocity.y])
        if self.rocket.landed or self.rocket.crashed or self.elapsed >= MAX_DURATION:
            self.state = 'finished'
            self.outcome = 'landed' if self.rocket.landed else 'crashed' if self.rocket.crashed else 'timeout'
            self.command = self.autopilot.update(self.rocket.telemetry(), DT)
            self.rocket.thrusting = False
            if self.outcome == "timeout":
                self.command = AutopilotCommand(phase="timeout")
            if self.record:
                self.record_terminal()

    def export_recorder(self):
        return self.recorder if self.recorder.rows else self.last_recording or self.recorder

    def snapshot(self, include_history=False):
        targets = {key: value if math.isfinite(value) else None
                   for key, value in self.autopilot.targets.items()}
        result = dict(type='state', flight_id=self.flight_id, state=self.state, outcome=self.outcome,
            elapsed=self.elapsed, telemetry=self.rocket.telemetry(), phase=self.autopilot.phase,
            throttle=self.command.thrust, targets=targets,
            platform=dict(x=self.platform.x, y=self.platform.y, width=PLATFORM_W,
                          surface_y=self.platform.get_surface_y()), settings=asdict(self.settings),
            samples=len(self.export_recorder().rows), world=dict(ground_y=GROUND_Y, launch_x=LAUNCH_X,
                                                       launch_surface_y=LAUNCH_SURFACE_Y))
        if include_history:
            result.update(trail=list(self.trail), history=list(self.history))
        return result
