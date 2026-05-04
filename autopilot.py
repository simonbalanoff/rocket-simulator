import math


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
        self.alt = KalmanFilter1D(process_var=0.5, measure_var=2.0)
        self.vel_y = KalmanFilter1D(process_var=1.0, measure_var=1.0)
        self.vel_x = KalmanFilter1D(process_var=1.0, measure_var=1.0)
        self.angle = KalmanFilter1D(process_var=0.05, measure_var=0.1)

    def reset(self):
        for f in (self.alt, self.vel_y, self.vel_x, self.angle):
            f.reset()

    def update(self, raw):
        return {
            "altitude": self.alt.update(raw["altitude"]),
            "vel_y": self.vel_y.update(raw["vel_y"]),
            "vel_x": self.vel_x.update(raw["vel_x"]),
            "angle": self.angle.update(raw["angle"]),
            "x": raw.get("x", 0.0),
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


class PDController:
    def __init__(self, kp, kd, out_min=-1.0, out_max=1.0):
        self.kp = kp
        self.kd = kd
        self.out_min = out_min
        self.out_max = out_max
        self.prev_error = None

    def reset(self):
        self.prev_error = None

    def update(self, error, dt):
        derivative = (
            0.0 if (self.prev_error is None or dt <= 0)
            else (error - self.prev_error) / dt
        )
        self.prev_error = error
        raw = self.kp * error + self.kd * derivative
        return max(self.out_min, min(self.out_max, raw))


class Autopilot:
    IDLE = "idle"
    DESCENT = "descent"
    TERMINAL = "terminal"
    LANDED = "landed"
    FAILED = "failed"

    TERMINAL_ALT = 160.0

    DESCENT_VEL_TARGET = -50.0
    TERMINAL_VEL_TARGET = -12.0
    FLARE_VEL_TARGET = -4.0
    FLARE_ALT = 35.0

    # hover_thrust = mass * gravity / THRUST_FORCE = 5 * 980 / 2800 ≈ 0.175
    GRAVITY_COMP = 0.175

    def __init__(self, ground_y, landing_x):
        self.ground_y = ground_y
        self.landing_x = landing_x
        self.estimator = StateEstimator()
        self.phase = self.IDLE
        self.log = []

        self.torque_descent = PDController(kp=60.0, kd=150.0, out_min=-1200, out_max=1200)
        self.torque_terminal = PDController(kp=80.0, kd=180.0, out_min=-1200, out_max=1200)

        self.thrust_descent = PDController(kp=0.010, kd=0.018, out_min=0.0, out_max=1.0)
        self.thrust_terminal = PDController(kp=0.022, kd=0.016, out_min=0.0, out_max=1.0)

    def reset(self):
        self.estimator.reset()
        self.phase = self.IDLE
        self.log.clear()
        for c in (self.torque_descent, self.torque_terminal,
                  self.thrust_descent, self.thrust_terminal):
            c.reset()

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
        alt = state["altitude"]
        vel_y = state["vel_y"]
        vel_x = state["vel_x"]
        angle_deg = state["angle"]
        x = state["x"]

        self.phase = self.DESCENT if alt > self.TERMINAL_ALT else self.TERMINAL

        if self.phase == self.DESCENT:
            thrust, torque = self.run_descent(dt, x, vel_y, vel_x, angle_deg)
        else:
            thrust, torque = self.run_terminal(dt, x, vel_y, vel_x, angle_deg, alt)

        if raw["fuel"] <= 0:
            thrust = 0.0

        self.log.append((self.phase, thrust, torque))
        return AutopilotCommand(thrust=thrust, torque=torque, phase=self.phase)

    def run_descent(self, dt, x, vel_y, vel_x, angle_deg):
        horiz_lean = -math.degrees(math.atan2(vel_x * 0.04, 1.0))
        horiz_lean = max(-22.0, min(22.0, horiz_lean))

        pad_err_deg = math.degrees(math.atan2((self.landing_x - x) * 0.003, 1.0))
        pad_err_deg = max(-15.0, min(15.0, pad_err_deg))

        angle_target = horiz_lean + pad_err_deg
        torque = self.torque_descent.update(
            signed_angle_error(angle_deg, angle_target), dt
        )

        brake_demand = self.DESCENT_VEL_TARGET - vel_y
        if brake_demand > 0:
            thrust = self.thrust_descent.update(brake_demand, dt) + self.GRAVITY_COMP * 0.35
            thrust = max(0.0, min(1.0, thrust))
        else:
            thrust = 0.0

        if abs(signed_angle_error(angle_deg, 0.0)) > 90.0:
            thrust = min(0.12, thrust)

        return thrust, torque

    def run_terminal(self, dt, x, vel_y, vel_x, angle_deg, alt):
        pad_err_deg = math.degrees(math.atan2((self.landing_x - x) * 0.007, 1.0))
        pad_err_deg = max(-10.0, min(10.0, pad_err_deg))

        horiz_lean = -math.degrees(math.atan2(vel_x * 0.07, 1.0))
        horiz_lean = max(-10.0, min(10.0, horiz_lean))

        angle_target = pad_err_deg + horiz_lean
        torque = self.torque_terminal.update(
            signed_angle_error(angle_deg, angle_target), dt
        )

        if alt < self.FLARE_ALT:
            vel_target = self.FLARE_VEL_TARGET
        else:
            vel_target = self.TERMINAL_VEL_TARGET

        brake_demand = vel_target - vel_y

        if brake_demand > 0:
            thrust = self.thrust_terminal.update(brake_demand, dt) + self.GRAVITY_COMP
        else:
            thrust = self.GRAVITY_COMP + brake_demand * 0.02
            thrust = max(0.0, thrust)

        thrust = min(1.0, thrust)

        if abs(signed_angle_error(angle_deg, 0.0)) > 40.0:
            thrust = min(0.18, thrust)

        return thrust, torque

    def status_lines(self):
        return {"phase": self.phase, "log_len": len(self.log)}
