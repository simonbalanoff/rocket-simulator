import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from rocket import ROCKET_MASS, ROCKET_W, ROCKET_H, THRUST_FORCE

G = 980.0
A_THRUST_MAX = THRUST_FORCE / ROCKET_MASS


class StateEstimator:
    """Constant-velocity Kalman model for x, bottom_y, vx, vy, angle, omega.

    Angle observations are unwrapped against the prediction. Acceleration noise
    allows the velocity model to follow engine and attitude changes.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = np.zeros(6)
        self.covariance = np.eye(6)
        self._primed = False
        self.measurement_covariance = np.diag([3., 3., 2., 2., .15, 1.])

    def update(self, raw, dt=1 / 120):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be finite and positive")
        measured = np.array([raw.get("x", 0.), raw["bottom_y"],
                             raw["vel_x"], raw["vel_y"], raw["angle"],
                             raw.get("omega_deg_s", 0.)], dtype=float)
        if not np.isfinite(measured).all():
            raise ValueError("telemetry must be finite")
        if not self._primed:
            self.state = measured.copy()
            self._primed = True
        else:
            transition = np.eye(6)
            noise = np.zeros((6, 6))
            for position, velocity, density in [(0, 2, 12000.), (1, 3, 40000.), (4, 5, 500.)]:
                transition[position, velocity] = dt
                noise[position, position] = density * dt ** 3 / 3
                noise[position, velocity] = noise[velocity, position] = density * dt ** 2 / 2
                noise[velocity, velocity] = density * dt
            prediction = transition @ self.state
            covariance = transition @ self.covariance @ transition.T + noise
            residual = measured - prediction
            residual[4] = signed_angle_error(prediction[4], measured[4])
            gain = np.linalg.solve(covariance + self.measurement_covariance, covariance.T).T
            self.state = prediction + gain @ residual
            # Joseph form preserves covariance symmetry and positive semidefiniteness.
            remaining = np.eye(6) - gain
            self.covariance = (remaining @ covariance @ remaining.T
                               + gain @ self.measurement_covariance @ gain.T)
        result = dict(raw)
        for key, value in zip(("x", "bottom_y", "vel_x", "vel_y", "angle", "omega_deg_s"), self.state):
            result[key] = float(value)
        result["altitude"] = max(0., raw["altitude"] + raw["bottom_y"] - result["bottom_y"])
        return result


@dataclass(frozen=True)
class ControllerSettings:
    attitude_scale: float = 1.0
    lateral_position_gain: float = 0.35
    vertical_gain: float = 3.0
    terminal_speed: float = 8.0

    def __post_init__(self):
        for name, value in vars(self).items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")


class AutopilotCommand:
    def __init__(self, thrust=0.0, torque=0.0, phase="idle"):
        self.thrust = thrust
        self.torque = torque
        self.phase = phase


def signed_angle_error(current_deg, target_deg=0.0):
    err = (target_deg - current_deg) % 360.0
    if err > 180.0:
        err -= 360.0
    return err


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


class Autopilot:
    IDLE = "idle"
    LAUNCH = "launch"
    ASCENT = "ascent"
    COAST = "coast"
    DESCENT = "descent"
    TERMINAL = "terminal"
    LANDED = "landed"
    FAILED = "failed"

    def __init__(self, landing_surface_y, landing_x, launch_surface_y, launch_x, settings=None):
        self.settings = settings or ControllerSettings()
        self.landing_surface_y = float(landing_surface_y)
        self.landing_x = float(landing_x)
        self.launch_surface_y = float(launch_surface_y)
        self.launch_x = float(launch_x)
        self.targets = {}
        self.estimator = StateEstimator()
        self.phase = self.IDLE
        self.log = deque(maxlen=3600)
        self._t_phase = 0.0
        self._coast_timer = 0.0

    def configure_mission(self, landing_surface_y, landing_x, launch_surface_y, launch_x):
        self.landing_surface_y = float(landing_surface_y)
        self.landing_x = float(landing_x)
        self.launch_surface_y = float(launch_surface_y)
        self.launch_x = float(launch_x)

    def reset(self):
        self.targets = {}
        self.estimator.reset()
        self.phase = self.IDLE
        self.log.clear()
        self._t_phase = 0.0
        self._coast_timer = 0.0

    def attitude_torque(self, angle_deg, omega_deg_s, target_deg, gains):
        kp, kd = gains
        e = signed_angle_error(angle_deg, target_deg)
        moment = ROCKET_MASS * (ROCKET_W ** 2 + ROCKET_H ** 2) / 12
        return clamp(self.settings.attitude_scale * moment * math.radians((kp / 8.0) * e - (kd / 30.0) * omega_deg_s),
                     -20000.0, 20000.0)

    def vertical_throttle(self, vy, vy_ref, cos_tilt, margin=0.02):
        cos_t = max(0.35, min(1.0, abs(cos_tilt)))
        a_eff = A_THRUST_MAX * cos_t
        if a_eff < 1e-3:
            return 0.0
        a_cmd = clamp(self.settings.vertical_gain * (vy_ref - vy), -1550.0, 980.0)
        return clamp((G - a_cmd) / a_eff, margin, 1.0)

    def lateral_angle_target(self, rng, vx, h_land, max_lean_deg=38.0, terminal=False):
        if terminal:
            vx_des = clamp(0.10 * rng, -18.0, 18.0) * clamp(h_land / 180.0, 0.0, 1.0)
            ax_des = clamp(5.5 * (vx_des - vx), -0.55 * G, 0.55 * G)
            lean = math.degrees(math.atan2(ax_des, G))
            needed = abs(math.degrees(math.atan2(min(abs(vx) * 4.5, 0.55 * G), G))) + 4.0
            cap = clamp(needed, 5.0, max_lean_deg)
            return clamp(lean, -cap, cap)
        else:
            vx_des = clamp(self.settings.lateral_position_gain * rng, -80.0, 80.0)
            ax_des = clamp(2.5 * (vx_des - vx), -0.55 * G, 0.55 * G)
            lean = math.degrees(math.atan2(ax_des, G))
            return clamp(lean, -max_lean_deg, max_lean_deg)

    def update(self, raw, dt):
        if self.phase in (self.LANDED, self.FAILED):
            return AutopilotCommand(phase=self.phase)
        if raw["landed"]:
            self.phase = self.LANDED
            return AutopilotCommand(phase=self.phase)
        if raw["crashed"]:
            self.phase = self.FAILED
            return AutopilotCommand(phase=self.phase)

        state = self.estimator.update(raw, dt)
        vy = state["vel_y"]
        vx = state["vel_x"]
        angle_deg = state["angle"]
        x = state["x"]
        bottom_y = state["bottom_y"]
        omega = state["omega_deg_s"]

        angle_rad = math.radians(angle_deg)
        cos_tilt = math.cos(angle_rad)

        h_launch = max(0.0, self.launch_surface_y - bottom_y)
        h_land = max(0.0, self.landing_surface_y - bottom_y)
        rng = self.landing_x - x

        if self.phase == self.IDLE:
            self.phase = self.LAUNCH
            self._t_phase = 0.0

        self._t_phase += dt
        thrust = torque = 0.0
        vy_ref = float("nan")

        if self.phase == self.LAUNCH:
            angle_target = self.lateral_angle_target(rng, vx, h_land, max_lean_deg=14.0)
            torque = self.attitude_torque(angle_deg, omega, angle_target, (88.0, 185.0))
            thrust = 1.0
            if h_launch > 40.0 and vy < -55.0:
                self.phase = self.ASCENT
                self._t_phase = 0.0

        elif self.phase == self.ASCENT:
            angle_target = self.lateral_angle_target(rng, vx, h_land, max_lean_deg=34.0)
            torque = self.attitude_torque(angle_deg, omega, angle_target, (84.0, 195.0))
            vy_ref = -160.0
            thrust = self.vertical_throttle(vy, vy_ref, cos_tilt)
            apogee_floor = max(310.0, min(550.0, 235.0 + 0.40 * abs(rng)))
            if self._t_phase > 0.5 and h_land > apogee_floor and vy < -70.0:
                self.phase = self.COAST
                self._coast_timer = 0.0

        elif self.phase == self.COAST:
            angle_target = self.lateral_angle_target(rng, vx, h_land, max_lean_deg=32.0)
            torque = self.attitude_torque(angle_deg, omega, angle_target, (74.0, 172.0))
            thrust = 0.08 if abs(rng) > 90.0 else 0.0
            self._coast_timer += dt
            if vy > -12.0 or self._coast_timer > 4.5:
                self.phase = self.DESCENT
                self._t_phase = 0.0

        elif self.phase == self.DESCENT:
            angle_target = self.lateral_angle_target(rng, vx, h_land, max_lean_deg=40.0)
            torque = self.attitude_torque(angle_deg, omega, angle_target, (95.0, 220.0))

            if h_land > 450.0:
                vy_ref = 65.0
            elif h_land > 350.0:
                vy_ref = 40.0 + (h_land - 350.0) * (25.0 / 100.0)
            elif h_land > 180.0:
                vy_ref = 28.0 + (h_land - 180.0) * (12.0 / 170.0)
            else:
                vy_ref = 28.0

            thrust = self.vertical_throttle(vy, vy_ref, cos_tilt, margin=0.06)

            rng_ok = abs(rng) < 55.0
            vx_ok = abs(vx) < 30.0
            if (h_land < 180.0 and rng_ok and vx_ok) or h_land < 80.0:
                self.phase = self.TERMINAL
                self._t_phase = 0.0

        elif self.phase == self.TERMINAL:
            angle_target = self.lateral_angle_target(
                rng, vx, h_land, max_lean_deg=28.0, terminal=True
            )
            torque = self.attitude_torque(angle_deg, omega, angle_target, (120.0, 265.0))
            vy_ref = clamp(self.settings.terminal_speed + 0.14 * h_land,
                           self.settings.terminal_speed, 33.0)
            thrust = self.vertical_throttle(vy, vy_ref, cos_tilt, margin=0.10)

        if abs(signed_angle_error(angle_deg, 0.0)) > 80.0:
            thrust = min(thrust, 0.10)
        if raw["fuel"] <= 0:
            thrust = 0.0

        self.targets = {"angle_target": angle_target, "vy_target": vy_ref}
        self.log.append((self.phase, thrust, torque))
        return AutopilotCommand(thrust=thrust, torque=torque, phase=self.phase)

    def status_lines(self):
        return {"phase": self.phase, "log_len": len(self.log)}
