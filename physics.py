"""Rendering-independent rocket and landing-platform physics."""
import math
import pymunk

ROCKET_W = 22
ROCKET_H = 72
ROCKET_MASS = 5.0
THRUST_FORCE = 5600.0
FUEL_CAPACITY = 300.0
FUEL_BURN = 12.0
PLATFORM_W = 300
PLATFORM_H = 16


def local_y(angle):
    return math.sin(angle), -math.cos(angle)


class RocketPhysics:
    def __init__(self, space, x, y, ground_y):
        self.space = space
        self.ground_y = ground_y
        self.width = ROCKET_W
        self.height = ROCKET_H

        self.original_x = float(x)
        self.original_y = float(y)
        self.placement_x = float(x)
        self.placement_y = float(y)
        self.placement_angle = 0.0

        self.thrusting = False
        self.fuel = FUEL_CAPACITY
        self.landed = False
        self.crashed = False
        self._landing_detection = None
        self._previous_velocity = (0.0, 0.0)

        self.body = None
        self.shape = None
        self.build_kinematic(x, y)

    def build_kinematic(self, x, y):
        if self.body is not None and self.shape in self.space.shapes:
            self.space.remove(self.shape, self.body)
        self.body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        self.body.position = (x, y)
        self.body.angle = self.placement_angle
        self.shape = pymunk.Poly.create_box(self.body, (self.width, self.height))
        self.shape.friction = 0.9
        self.shape.elasticity = 0.05
        self.space.add(self.body, self.shape)

    def activate_physics(self):
        x, y = self.body.position
        angle = self.body.angle
        if self.shape in self.space.shapes:
            self.space.remove(self.shape, self.body)
        moment = pymunk.moment_for_box(ROCKET_MASS, (self.width, self.height))
        self.body = pymunk.Body(ROCKET_MASS, moment)
        self.body.position = (x, y)
        self.body.angle = angle
        self.shape = pymunk.Poly.create_box(self.body, (self.width, self.height))
        self.shape.friction = 0.9
        self.shape.elasticity = 0.05
        self.space.add(self.body, self.shape)
        self.landed = False
        self.crashed = False
        self.fuel = FUEL_CAPACITY

    def save_placement(self):
        self.placement_x = float(self.body.position.x)
        self.placement_y = float(self.body.position.y)
        self.placement_angle = self.body.angle

    def reset(self, to_original=False):
        if to_original:
            self.placement_x = self.original_x
            self.placement_y = self.original_y
            self.placement_angle = 0.0
        self.thrusting = False
        self.fuel = FUEL_CAPACITY
        self.landed = False
        self.crashed = False
        self._landing_detection = None
        self.build_kinematic(self.placement_x, self.placement_y)

    def configure_landing_detection(
            self,
            *,
            landing_x,
            landing_surface_y,
            landing_half_w,
            launch_x,
            launch_surface_y,
            launch_half_w,
    ):
        self._landing_detection = {
            "landing_x": float(landing_x),
            "landing_surface_y": float(landing_surface_y),
            "landing_half_w": float(landing_half_w),
            "launch_x": float(launch_x),
            "launch_surface_y": float(launch_surface_y),
            "launch_half_w": float(launch_half_w),
        }

    def apply_autopilot(self, command, dt):
        self.thrusting = False
        self._previous_velocity = tuple(self.body.velocity)
        if self.landed or self.crashed or dt <= 0:
            return
        throttle = max(0.0, min(1.0, command.thrust))
        throttle = min(throttle, self.fuel / (FUEL_BURN * dt))
        if throttle > 0:
            self.thrusting = True
            self.fuel = max(0.0, self.fuel - FUEL_BURN * dt * throttle)
            dx, dy = local_y(self.body.angle)
            f = THRUST_FORCE * throttle
            self.body.apply_force_at_world_point((f * dx, f * dy), self.body.position)
            self.spawn_particles()
        self.body.torque += command.torque

    def update(self, dt, simulating):
        if simulating and not self.landed and not self.crashed:
            self.check_landing()

    def spawn_particles(self):
        """Optional hook for a renderer; it never affects dynamics."""

    def check_landing(self):
        # Contact is required: proximity alone must never complete a mission.
        contacts = []
        self.body.each_arbiter(lambda arbiter: contacts.append(arbiter))
        if not contacts:
            return
        bx, by = self.body.position
        angle = abs((self.body.angle + math.pi) % math.tau - math.pi)
        bottom_y = by + (self.height / 2) * math.cos(self.body.angle)
        speed = max(self.body.velocity.length, math.hypot(*self._previous_velocity))
        ld = self._landing_detection
        if ld is None:
            self.crashed = True
            return
        # Ignore the launch support while the engine lifts off.
        if (abs(bx - ld["launch_x"]) <= ld["launch_half_w"]
                and abs(bottom_y - ld["launch_surface_y"]) < 6
                and self.thrusting):
            return
        on_target = (
            abs(bx - ld["landing_x"]) + self.width / 2 <= ld["landing_half_w"]
            and abs(bottom_y - ld["landing_surface_y"]) < 6
        )
        if on_target and speed < 30 and angle < math.radians(10):
            self.landed = True
            self.thrusting = False
            self.body.velocity = (0, 0)
            self.body.angular_velocity = 0
        else:
            self.crashed = True
            self.thrusting = False

    def telemetry(self):
        bx, by = self.body.position
        vx, vy = self.body.velocity
        speed = math.hypot(vx, vy)
        bottom_y = by + (self.height / 2) * math.cos(self.body.angle)
        alt = max(0.0, self.ground_y - bottom_y)
        angle_d = math.degrees(self.body.angle) % 360
        omega_deg_s = math.degrees(float(self.body.angular_velocity))
        return {
            "x": bx,
            "y": by,
            "bottom_y": bottom_y,
            "altitude": alt,
            "vel_x": vx,
            "vel_y": vy,
            "speed": speed,
            "angle": angle_d,
            "omega_deg_s": omega_deg_s,
            "fuel": self.fuel,
            "fuel_pct": self.fuel / FUEL_CAPACITY,
            "thrusting": self.thrusting,
            "landed": self.landed,
            "crashed": self.crashed,
        }

class PlatformPhysics:
    def __init__(self, space, x, y, ground_y):
        self.space = space
        self.ground_y = ground_y
        self.width = PLATFORM_W
        self.height = PLATFORM_H

        self.x = float(x)
        self.y = float(y)

        self.original_x = float(x)
        self.original_y = float(y)

        self.seg = None
        self.build_seg()

    def build_seg(self):
        if self.seg is not None:
            if self.seg in self.space.shapes:
                self.space.remove(self.seg)
        half = self.width / 2
        self.seg = pymunk.Segment(
            self.space.static_body,
            (self.x - half, self.get_surface_y() + 4),
            (self.x + half, self.get_surface_y() + 4),
            4,
        )
        self.seg.friction = 1.0
        self.seg.elasticity = 0.02
        self.space.add(self.seg)

    def rebuild_seg(self):
        self.build_seg()

    def remove_seg(self):
        if self.seg is not None:
            if self.seg in self.space.shapes:
                self.space.remove(self.seg)
            self.seg = None

    def reset(self, to_original=False):
        if to_original:
            self.x = self.original_x
            self.y = self.original_y
        self.build_seg()

    def get_center_x(self):
        return self.x

    def get_surface_y(self):
        return self.y - self.height
