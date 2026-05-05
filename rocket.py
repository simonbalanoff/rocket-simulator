import pymunk
import pygame
import math
import random

AXIS_LEN = 70
AXIS_HIT_R = 14
ARC_R = 48

ROCKET_W = 22
ROCKET_H = 72
ROCKET_MASS = 5.0

THRUST_FORCE = 5600.0
FUEL_CAPACITY = 300.0
FUEL_BURN = 12.0
PARTICLE_LIFE = 0.35


def world_to_screen(wx, wy, pan_x, pan_y, zoom):
    return wx * zoom + pan_x, wy * zoom + pan_y


def screen_to_world(sx, sy, pan_x, pan_y, zoom):
    return (sx - pan_x) / zoom, (sy - pan_y) / zoom


def local_y(angle):
    return math.sin(angle), -math.cos(angle)


def local_x(angle):
    return math.cos(angle), math.sin(angle)


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def draw_arrow(surf, start, end, color, label=None, width=2, head=11):
    sx, sy = int(start[0]), int(start[1])
    ex, ey = int(end[0]), int(end[1])
    pygame.draw.line(surf, color, (sx, sy), (ex, ey), width)
    ang = math.atan2(ey - sy, ex - sx)
    for side in (0.4, -0.4):
        hx = ex - head * math.cos(ang - side)
        hy = ey - head * math.sin(ang - side)
        pygame.draw.line(surf, color, (ex, ey), (int(hx), int(hy)), width)
    if label:
        font = pygame.font.SysFont("Helvetica", 12, bold=True)
        s = font.render(label, True, color)
        px = -(ey - sy);
        py = (ex - sx)
        mag = math.hypot(px, py) or 1
        surf.blit(s, (ex + int(px / mag * 16) - 5, ey + int(py / mag * 16) - 7))


class Particle:
    def __init__(self, x, y, vx, vy):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = PARTICLE_LIFE
        self.max_life = PARTICLE_LIFE
        self.size = random.uniform(2, 5)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 60 * dt
        self.life -= dt
        return self.life > 0

    def draw(self, screen, pan_x, pan_y, zoom):
        t = self.life / self.max_life
        alpha = int(t * 200)
        g = max(0, int(180 * t))
        b = max(0, int(60 * t))
        s = max(1, int(self.size * zoom * t))
        sx = int(self.x * zoom + pan_x)
        sy = int(self.y * zoom + pan_y)
        surf = pygame.Surface((s * 2 + 2, s * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (255, g, b, alpha), (s + 1, s + 1), s)
        screen.blit(surf, (sx - s - 1, sy - s - 1))


class Rocket:
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

        self.drag_mode = None
        self.drag_axis = None
        self.drag_origin = None
        self.drag_body_start = None
        self.rotate_start_mouse = None
        self.rotate_start_angle = 0.0

        self.thrusting = False
        self.fuel = FUEL_CAPACITY
        self.particles = []
        self.landed = False
        self.crashed = False
        self._landing_detection = None

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
        self.particles.clear()
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
        if command.thrust > 0 and self.fuel > 0:
            self.thrusting = True
            self.fuel = max(0.0, self.fuel - FUEL_BURN * dt * command.thrust)
            dx, dy = local_y(self.body.angle)
            f = THRUST_FORCE * command.thrust
            self.body.apply_force_at_world_point((f * dx, f * dy), self.body.position)
            self.spawn_particles()
        if command.torque != 0:
            self.body.torque += command.torque

    def update(self, dt, simulating):
        self.thrusting = False
        if simulating and not self.landed and not self.crashed:
            self.check_landing()
        self.particles = [p for p in self.particles if p.update(dt)]

    def spawn_particles(self):
        angle = self.body.angle
        nx = self.body.position.x - (self.height / 2 + 4) * math.sin(angle)
        ny = self.body.position.y + (self.height / 2 + 4) * math.cos(angle)
        dx, dy = local_y(angle)
        for _ in range(3):
            spread = random.uniform(-30, 30)
            px, py = local_x(angle)
            vx = -dx * random.uniform(80, 140) + px * spread + self.body.velocity.x * 0.3
            vy = -dy * random.uniform(80, 140) + py * spread + self.body.velocity.y * 0.3
            self.particles.append(Particle(nx, ny, vx, vy))

    def check_landing(self):
        bx, by = self.body.position
        speed = self.body.velocity.length
        angle = self.body.angle % (2 * math.pi)
        if angle > math.pi:
            angle = 2 * math.pi - angle
        bottom_y = by + (self.height / 2) * math.cos(self.body.angle)

        ld = self._landing_detection
        if ld is not None:
            if (
                    abs(bx - ld["launch_x"]) <= ld["launch_half_w"] + 18
                    and abs(bottom_y - ld["launch_surface_y"]) < 26
                    and speed < 45
            ):
                return

            on_landing_deck = (
                    abs(bottom_y - ld["landing_surface_y"]) < 50
                    and abs(bx - ld["landing_x"]) <= ld["landing_half_w"] + 25
            )
            stopped_on_landing_deck = (
                    on_landing_deck
                    and speed < 30
                    and abs(self.body.velocity.y) < 25
            )
        else:
            near_surface = bottom_y >= self.ground_y - 8
            stopped_on_landing_deck = (
                    speed < 30
                    and abs(self.body.velocity.y) < 25
                    and bottom_y < self.ground_y - 12
            )
            if near_surface or stopped_on_landing_deck:
                if speed < 80 and angle < math.radians(20):
                    self.landed = True
                elif speed >= 80 or angle >= math.radians(35):
                    self.crashed = True
            return

        near_surface = bottom_y >= self.ground_y - 8
        if near_surface or stopped_on_landing_deck:
            if speed < 80 and angle < math.radians(20):
                self.landed = True
                self.body.velocity = (0, 0)
                self.body.angular_velocity = 0
            elif speed >= 80 or angle >= math.radians(35):
                self.crashed = True

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

    def draw(self, screen, pan_x=0.0, pan_y=0.0, zoom=1.0):
        for p in self.particles:
            p.draw(screen, pan_x, pan_y, zoom)

        cx, cy = world_to_screen(self.body.position.x, self.body.position.y, pan_x, pan_y, zoom)
        angle = self.body.angle
        w = self.width * zoom
        h = self.height * zoom
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        def rot(x, y):
            return cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a

        if self.landed:
            body_col = (80, 200, 120)
            accent_col = (55, 155, 85)
        elif self.crashed:
            body_col = (200, 70, 60)
            accent_col = (155, 45, 35)
        else:
            body_col = (210, 215, 225)
            accent_col = (135, 148, 168)

        body_pts = [rot(-w / 2, -h / 2), rot(w / 2, -h / 2), rot(w / 2, h / 2), rot(-w / 2, h / 2)]
        pygame.draw.polygon(screen, body_col, body_pts)

        nose_pts = [rot(-w / 2, -h / 2), rot(w / 2, -h / 2), rot(0, -h / 2 - w * 1.2)]
        pygame.draw.polygon(screen, accent_col, nose_pts)

        stripe_pts = [rot(-w / 4, -h / 6), rot(w / 4, -h / 6), rot(w / 4, h / 6), rot(-w / 4, h / 6)]
        pygame.draw.polygon(screen, (28, 32, 48), stripe_pts)

        for side in (-1, 1):
            fin_pts = [
                rot(side * w / 2, h / 2),
                rot(side * (w / 2 + w * 0.55), h / 2 + h * 0.22),
                rot(side * w / 2, h / 2 - h * 0.07),
            ]
            pygame.draw.polygon(screen, accent_col, fin_pts)

        bell_pts = [rot(-w / 3, h / 2), rot(w / 3, h / 2), rot(w / 2, h / 2 + w * 0.5), rot(-w / 2, h / 2 + w * 0.5)]
        pygame.draw.polygon(screen, (75, 82, 100), bell_pts)

        if self.thrusting and self.fuel > 0:
            self.draw_flame(screen, cx, cy, angle, w, h)

        pygame.draw.polygon(screen, (45, 50, 65), body_pts, 1)

    def draw_flame(self, screen, cx, cy, angle, w, h):
        t = pygame.time.get_ticks() / 1000.0
        flicker = 0.8 + 0.2 * math.sin(t * 40) + 0.1 * math.sin(t * 73)
        fl = h * 0.9 + h * 0.4 * flicker
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        base_y = h / 2 + w * 0.5

        def rot(x, y):
            return cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a

        surf = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(surf, (255, 140, 30, 150),
                            [rot(-w * 0.45, base_y), rot(0, base_y + fl), rot(w * 0.45, base_y)])
        pygame.draw.polygon(surf, (255, 240, 160, 200),
                            [rot(-w * 0.22, base_y), rot(0, base_y + fl * 0.6), rot(w * 0.22, base_y)])
        screen.blit(surf, (0, 0))

    def axis_tip_screen(self, axis, pan_x, pan_y, zoom):
        cx, cy = world_to_screen(self.body.position.x, self.body.position.y, pan_x, pan_y, zoom)
        dx, dy = local_y(self.body.angle) if axis == "y" else local_x(self.body.angle)
        return cx + AXIS_LEN * zoom * dx, cy + AXIS_LEN * zoom * dy

    def hit_axis_screen(self, sx, sy, pan_x, pan_y, zoom):
        cx, cy = world_to_screen(self.body.position.x, self.body.position.y, pan_x, pan_y, zoom)
        for axis in ("y", "x"):
            tx, ty = self.axis_tip_screen(axis, pan_x, pan_y, zoom)
            if seg_dist(sx, sy, cx, cy, tx, ty) < AXIS_HIT_R:
                return axis
        return None

    def handle_mouse_down(self, screen_pos, mode, pan_x, pan_y, zoom):
        sx, sy = float(screen_pos[0]), float(screen_pos[1])
        if mode == "move":
            axis = self.hit_axis_screen(sx, sy, pan_x, pan_y, zoom)
            if axis:
                self.drag_mode = "axis"
                self.drag_axis = axis
                self.drag_origin = (sx, sy)
                self.drag_body_start = (float(self.body.position.x), float(self.body.position.y))
        elif mode == "rotate":
            self.drag_mode = "rotate"
            self.rotate_start_mouse = (sx, sy)
            self.rotate_start_angle = self.body.angle

    def handle_mouse_move(self, screen_pos, pan_x, pan_y, zoom):
        if not self.drag_mode:
            return
        sx, sy = float(screen_pos[0]), float(screen_pos[1])

        if self.drag_mode == "axis":
            osx, osy = self.drag_origin
            bx, by = self.drag_body_start
            dsx, dsy = sx - osx, sy - osy
            angle = self.body.angle
            ax, ay = local_y(angle) if self.drag_axis == "y" else local_x(angle)
            proj = (dsx * ax + dsy * ay) / zoom
            self.body.position = (bx + proj * ax, by + proj * ay)

        elif self.drag_mode == "rotate":
            dx = sx - self.rotate_start_mouse[0]
            self.body.angle = self.rotate_start_angle + math.radians(dx * 0.5)

    def handle_mouse_up(self):
        self.drag_mode = None
        self.drag_axis = None
        self.drag_origin = None
        self.rotate_start_mouse = None

    def handle_keys(self, keys):
        speed = 3.0
        rot = math.radians(2.0)
        bx, by = self.body.position
        if keys[pygame.K_w]: self.body.position = (bx, by - speed)
        if keys[pygame.K_s]: self.body.position = (bx, by + speed)
        if keys[pygame.K_a]: self.body.position = (bx - speed, by)
        if keys[pygame.K_d]: self.body.position = (bx + speed, by)
        if keys[pygame.K_q]: self.body.angle -= rot
        if keys[pygame.K_e]: self.body.angle += rot

    def draw_axes(self, screen, mode, pan_x=0.0, pan_y=0.0, zoom=1.0):
        cx, cy = world_to_screen(self.body.position.x, self.body.position.y, pan_x, pan_y, zoom)
        ytip = self.axis_tip_screen("y", pan_x, pan_y, zoom)
        xtip = self.axis_tip_screen("x", pan_x, pan_y, zoom)
        icx, icy = int(cx), int(cy)

        if mode == "move":
            y_hot = self.drag_mode == "axis" and self.drag_axis == "y"
            x_hot = self.drag_mode == "axis" and self.drag_axis == "x"
            draw_arrow(screen, (cx, cy), ytip,
                       (160, 255, 160) if y_hot else (55, 210, 75), label="Y")
            draw_arrow(screen, (cx, cy), xtip,
                       (255, 160, 160) if x_hot else (210, 55, 55), label="X")
            pygame.draw.circle(screen, (12, 14, 22), (icx, icy), int(8 * zoom))
            pygame.draw.circle(screen, (225, 230, 242), (icx, icy), int(5 * zoom))

        elif mode == "rotate":
            active = self.drag_mode == "rotate"
            pygame.draw.circle(screen, (12, 14, 22), (icx, icy), int(8 * zoom))
            dot_col = (255, 210, 80) if active else (175, 190, 225)
            pygame.draw.circle(screen, dot_col, (icx, icy), int(5 * zoom))

            pad = 4
            size = ARC_R * 2 + pad * 2
            arc_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            arc_rect = pygame.Rect(pad, pad, ARC_R * 2, ARC_R * 2)
            ctr = ARC_R + pad
            ring_col = (255, 210, 80, 150) if active else (115, 135, 175, 40)
            pygame.draw.arc(arc_surf, ring_col, arc_rect, 0, math.tau, 2 if active else 1)

            ref = math.pi / 2
            current = math.pi / 2 - self.body.angle
            r1x = ctr + ARC_R * math.cos(current)
            r1y = ctr - ARC_R * math.sin(current)
            tick_col = (255, 210, 80, 255) if active else (175, 195, 235, 200)
            r0x = ctr + ARC_R * math.cos(ref)
            r0y = ctr - ARC_R * math.sin(ref)
            pygame.draw.line(arc_surf, (150, 160, 200, 100), (ctr, ctr), (int(r0x), int(r0y)), 1)
            if abs(self.body.angle) > 0.01:
                a0 = min(ref, current)
                a1 = max(ref, current)
                fill = (255, 210, 80, 140) if active else (165, 135, 245, 110)
                pygame.draw.arc(arc_surf, fill, arc_rect, a0, a1, 2)
            pygame.draw.line(arc_surf, tick_col, (ctr, ctr), (int(r1x), int(r1y)), 2)
            pygame.draw.circle(arc_surf, tick_col, (int(r1x), int(r1y)), 3)
            screen.blit(arc_surf, (icx - ctr, icy - ctr))

            deg = math.degrees(self.body.angle) % 360
            font = pygame.font.SysFont("Helvetica", 10)
            lbl = font.render(f"{deg:.1f}", True, (155, 175, 215))
            screen.blit(lbl, (icx + ARC_R + 8, icy - 7))
