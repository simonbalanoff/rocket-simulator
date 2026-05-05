import math

from rocket import ROCKET_MASS, THRUST_FORCE

G = 980.0
A_THRUST_MAX = THRUST_FORCE / ROCKET_MASS


class KalmanFilter1D:
    def __init__(self, process_var=0.1, measure_var=0.5):
        self.estimate = 0.0
        self.estimate_var = 1.0
        self.process_var = process_var
        self.measure_var = measure_var

    def reset(self):
        self.estimate = 0.0
        self.estimate_var = 1.0

    def update(self, measurement):
        predicted_var = self.estimate_var + self.process_var
        gain = predicted_var / (predicted_var + self.measure_var)
        self.estimate += gain * (measurement - self.estimate)
        self.estimate_var = (1 - gain) * predicted_var
        return self.estimate


class StateEstimator:
    def __init__(self):
        self.alt = KalmanFilter1D(process_var=0.8, measure_var=3.0)
        self.vel_y = KalmanFilter1D(process_var=2.0, measure_var=2.0)
        self.vel_x = KalmanFilter1D(process_var=1.5, measure_var=2.0)
        self.angle = KalmanFilter1D(process_var=0.08, measure_var=0.15)
        self._primed = False

    def reset(self):
        for f in (self.alt, self.vel_y, self.vel_x, self.angle):
            f.reset()
        self._primed = False

    def update(self, raw):
        if not self._primed:
            self.alt.estimate = raw["altitude"]
            self.vel_y.estimate = raw["vel_y"]
            self.vel_x.estimate = raw["vel_x"]
            self.angle.estimate = raw["angle"]
            for f in (self.alt, self.vel_y, self.vel_x, self.angle):
                f.estimate_var = 1.0
            self._primed = True
        return {
            "altitude": self.alt.update(raw["altitude"]),
            "vel_y": self.vel_y.update(raw["vel_y"]),
            "vel_x": self.vel_x.update(raw["vel_x"]),
            "angle": self.angle.update(raw["angle"]),
            "x": raw.get("x", 0.0),
            "bottom_y": raw["bottom_y"],
            "omega_deg_s": raw.get("omega_deg_s", 0.0),
            "fuel": raw["fuel"],
            "landed": raw["landed"],
            "crashed": raw["crashed"],
        }


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

    def __init__(self, landing_surface_y, landing_x, launch_surface_y, launch_x):
        self.landing_surface_y = float(landing_surface_y)
        self.landing_x = float(landing_x)
        self.launch_surface_y = float(launch_surface_y)
        self.launch_x = float(launch_x)
        self.estimator = StateEstimator()
        self.phase = self.IDLE
        self.log = []
        self._t_phase = 0.0
        self._coast_timer = 0.0

    def configure_mission(self, landing_surface_y, landing_x, launch_surface_y, launch_x):
        self.landing_surface_y = float(landing_surface_y)
        self.landing_x = float(landing_x)
        self.launch_surface_y = float(launch_surface_y)
        self.launch_x = float(launch_x)

    def reset(self):
        self.estimator.reset()
        self.phase = self.IDLE
        self.log.clear()
        self._t_phase = 0.0
        self._coast_timer = 0.0

    def attitude_torque(self, angle_deg, omega_deg_s, target_deg, gains):
        kp, kd = gains
        e = signed_angle_error(angle_deg, target_deg)
        return clamp(kp * e + kd * (-omega_deg_s), -1600.0, 1600.0)

    def vertical_throttle(self, vy, vy_ref, cos_tilt, margin=0.02):
        cos_t = max(0.35, min(1.0, abs(cos_tilt)))
        a_eff = A_THRUST_MAX * cos_t
        if a_eff < 1e-3:
            return 0.0
        a_cmd = clamp(3.0 * (vy_ref - vy), -1550.0, 980.0)
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
            if h_land > 350.0:
                vy_ref_est = 60.0
            elif h_land > 180.0:
                vy_ref_est = 30.0
            else:
                vy_ref_est = 20.0
            t_go = max(1.0, h_land / max(vy_ref_est, 1.0))
            vx_des = clamp(rng / t_go, -80.0, 80.0)
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

        state = self.estimator.update(raw)
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
            thrust = self.vertical_throttle(vy, -160.0, cos_tilt)
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
            vy_ref = clamp(8.0 + 0.14 * h_land, 8.0, 33.0)
            thrust = self.vertical_throttle(vy, vy_ref, cos_tilt, margin=0.10)

        if abs(signed_angle_error(angle_deg, 0.0)) > 80.0:
            thrust = min(thrust, 0.10)
        if raw["fuel"] <= 0:
            thrust = 0.0

        self.log.append((self.phase, thrust, torque))
        return AutopilotCommand(thrust=thrust, torque=torque, phase=self.phase)

    def status_lines(self):
        return {"phase": self.phase, "log_len": len(self.log)}
