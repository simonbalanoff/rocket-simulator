import pygame
import pymunk
import math

PLATFORM_W = 300
PLATFORM_H = 16
PLATFORM_LEG_H = 128

AXIS_LEN = 70
AXIS_HIT_R = 14


def world_to_screen(wx, wy, pan_x, pan_y, zoom):
    return wx * zoom + pan_x, wy * zoom + pan_y


def screen_to_world(sx, sy, pan_x, pan_y, zoom):
    return (sx - pan_x) / zoom, (sy - pan_y) / zoom


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
        px2 = -(ey - sy)
        py2 = (ex - sx)
        mag = math.hypot(px2, py2) or 1
        surf.blit(s, (ex + int(px2 / mag * 16) - 5, ey + int(py2 / mag * 16) - 7))


class LandingPlatform:
    def __init__(self, space, x, y, ground_y):
        self.space = space
        self.ground_y = ground_y
        self.width = PLATFORM_W
        self.height = PLATFORM_H

        self.x = float(x)
        self.y = float(y)

        self.original_x = float(x)
        self.original_y = float(y)

        self.drag_mode = None
        self.drag_origin = None
        self.drag_start = None

        self.seg = None
        self.build_seg()

    def build_seg(self):
        if self.seg is not None:
            try:
                self.space.remove(self.seg)
            except Exception:
                pass
        half = self.width / 2
        self.seg = pymunk.Segment(
            self.space.static_body,
            (self.x - half, self.y - self.height - 10),
            (self.x + half, self.y - self.height - 10),
            4,
        )
        self.seg.friction = 1.0
        self.seg.elasticity = 0.02
        self.space.add(self.seg)

    def rebuild_seg(self):
        self.build_seg()

    def remove_seg(self):
        if self.seg is not None:
            try:
                self.space.remove(self.seg)
            except Exception:
                pass
            self.seg = None

    def reset(self, to_original=False):
        if to_original:
            self.x = self.original_x
            self.y = self.original_y
        self.build_seg()

    def get_center_x(self):
        return self.x

    def get_surface_y(self):
        return self.y

    def x_tip(self, pan_x, pan_y, zoom):
        sx, sy = world_to_screen(self.x, self.y, pan_x, pan_y, zoom)
        return sx + AXIS_LEN * zoom, sy

    def y_tip(self, pan_x, pan_y, zoom):
        sx, sy = world_to_screen(self.x, self.y, pan_x, pan_y, zoom)
        return sx, sy - AXIS_LEN * zoom

    def hit_axis(self, screen_pos, pan_x, pan_y, zoom):
        sx, sy = float(screen_pos[0]), float(screen_pos[1])
        cx, cy = world_to_screen(self.x, self.y, pan_x, pan_y, zoom)
        xt = self.x_tip(pan_x, pan_y, zoom)
        yt = self.y_tip(pan_x, pan_y, zoom)
        if seg_dist(sx, sy, cx, cy, *xt) < AXIS_HIT_R:
            return "x"
        if seg_dist(sx, sy, cx, cy, *yt) < AXIS_HIT_R:
            return "y"
        bw = self.width * zoom / 2
        bh = (PLATFORM_H + PLATFORM_LEG_H) * zoom
        if abs(sx - cx) < bw and abs(sy - cy) < bh:
            return "x"
        return None

    def handle_mouse_down(self, screen_pos, pan_x, pan_y, zoom):
        axis = self.hit_axis(screen_pos, pan_x, pan_y, zoom)
        if axis:
            self.drag_mode = axis
            self.drag_origin = screen_pos
            self.drag_start = (self.x, self.y)

    def handle_mouse_move(self, screen_pos, pan_x, pan_y, zoom):
        if not self.drag_mode:
            return
        sx, sy = float(screen_pos[0]), float(screen_pos[1])
        ox, oy = self.drag_origin
        dx_s = sx - ox
        dy_s = sy - oy
        bx, by = self.drag_start
        if self.drag_mode == "x":
            self.x = bx + dx_s / zoom
        elif self.drag_mode == "y":
            self.y = by + dy_s / zoom
        self.build_seg()

    def handle_mouse_up(self):
        self.drag_mode = None
        self.drag_origin = None
        self.drag_start = None

    def handle_keys(self, keys, speed=3.0):
        moved = False
        if keys[pygame.K_a]:
            self.x -= speed
            moved = True
        if keys[pygame.K_d]:
            self.x += speed
            moved = True
        if keys[pygame.K_w]:
            self.y -= speed
            moved = True
        if keys[pygame.K_s]:
            self.y += speed
            moved = True
        if moved:
            self.build_seg()

    def draw(self, screen, pan_x, pan_y, zoom):
        cx, cy = world_to_screen(self.x, self.y, pan_x, pan_y, zoom)
        pw = self.width * zoom
        ph = PLATFORM_H * zoom
        leg_h = self.ground_y
        leg_w = max(4, 10 * zoom)

        leg_offsets = [-pw * 0.35, pw * 0.35]
        for lx_off in leg_offsets:
            lx = int(cx + lx_off)
            leg_top = int(cy)
            leg_bot = int(cy + leg_h)
            pygame.draw.line(screen, (80, 95, 120), (lx, leg_top), (lx, leg_bot), max(1, int(leg_w)))

        deck_rect = pygame.Rect(int(cx - pw / 2), int(cy - ph), int(pw), int(ph))
        pygame.draw.rect(screen, (52, 64, 90), deck_rect, border_radius=max(1, int(3 * zoom)))
        stripe_rect = pygame.Rect(int(cx - pw / 2 + 4 * zoom), int(cy - ph + 3 * zoom),
                                  int(pw - 8 * zoom), max(2, int(3 * zoom)))
        pygame.draw.rect(screen, (90, 110, 150), stripe_rect)

        font_size = max(8, int(10 * zoom))
        try:
            font = pygame.font.SysFont("Helvetica", font_size)
            lbl = font.render("LANDING PAD", True, (160, 200, 240))
            if lbl.get_width() > 0:
                screen.blit(lbl, (int(cx - lbl.get_width() / 2), int(cy + leg_h + 20)))
        except pygame.error:
            pass

    def draw_gizmo(self, screen, pan_x, pan_y, zoom):
        cx, cy = world_to_screen(self.x, self.y, pan_x, pan_y, zoom)
        xt = self.x_tip(pan_x, pan_y, zoom)
        yt = self.y_tip(pan_x, pan_y, zoom)

        x_hot = self.drag_mode == "x"
        y_hot = self.drag_mode == "y"

        draw_arrow(screen, (cx, cy), xt,
                   (255, 160, 160) if x_hot else (210, 55, 55), label="X")
        draw_arrow(screen, (cx, cy), yt,
                   (160, 255, 160) if y_hot else (55, 210, 75), label="Y")

        icx, icy = int(cx), int(cy)
        pygame.draw.circle(screen, (12, 14, 22), (icx, icy), int(8 * zoom))
        pygame.draw.circle(screen, (225, 230, 242), (icx, icy), int(5 * zoom))
