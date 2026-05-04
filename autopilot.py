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


class Autopilot:
    IDLE = "idle"
    DESCENT = "descent"
    TERMINAL = "terminal"
    LANDED = "landed"
    FAILED = "failed"

    def __init__(self, ground_y, landing_x):
        self.ground_y = ground_y
        self.landing_x = landing_x
        self.estimator = StateEstimator()
        self.phase = self.IDLE
        self.log = []

    def reset(self):
        self.estimator.reset()
        self.phase = self.IDLE
        self.log.clear()

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
        self.phase = self.DESCENT if state["altitude"] > 150 else self.TERMINAL

        return AutopilotCommand(thrust=0.0, torque=0.0, phase=self.phase)

    def status_lines(self):
        return {"phase": self.phase, "log_len": len(self.log)}
