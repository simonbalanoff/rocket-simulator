import pygame

from theme import (
    F, draw_rect, shadow_rect,
    WHITE, CARD_BORDER,
    SIM_GREEN, SIM_GREEN_H,
    STOP_AMBER, STOP_AMBER_H,
    RESET_SLATE, RESET_SLATE_H,
    TEXT_DARK, TEXT_MID, TEXT_LIGHT, TEXT_WHITE,
    OK_COL, WARN_COL, BAD_COL, FUEL_COL,
    PHASE_COL,
)

BOTTOM_H = 80
BTN_H = 48
BTN_W = 148
BTN_GAP = 10

TOOL_W = 56
TOOL_H = 50
TOOL_PAD = 6
TOOL_X = 14
TOOL_TOP = 90


class SimControls:
    def __init__(self, screen_width, screen_height):
        self.sw = screen_width
        self.sh = screen_height
        self.state = "stopped"
        self.rects = {}
        self.hovered = None
        self.layout(screen_width, screen_height)
        self.icons = {
            "simulate": pygame.image.load("assets/icons/play.png").convert_alpha(),
            "simulate_white": pygame.image.load("assets/icons/play_white.png").convert_alpha(),
            "stop": pygame.image.load("assets/icons/stop.png").convert_alpha(),
            "stop_white": pygame.image.load("assets/icons/stop_white.png").convert_alpha(),
            "reset": pygame.image.load("assets/icons/reset.png").convert_alpha(),
            "reset_white": pygame.image.load("assets/icons/reset_white.png").convert_alpha(),
        }
        for k in self.icons:
            self.icons[k] = pygame.transform.smoothscale(self.icons[k], (14, 14))

    def layout(self, sw, sh):
        self.sw = sw
        self.sh = sh
        self.panel_rect = pygame.Rect(0, sh - BOTTOM_H, sw, BOTTOM_H)
        total = BTN_W * 3 + BTN_GAP * 2
        sx = (sw - total) // 2
        by = sh - BOTTOM_H + (BOTTOM_H - BTN_H) // 2
        self.rects = {
            "simulate": pygame.Rect(sx, by, BTN_W, BTN_H),
            "stop": pygame.Rect(sx + BTN_W + BTN_GAP, by, BTN_W, BTN_H),
            "reset": pygame.Rect(sx + (BTN_W + BTN_GAP) * 2, by, BTN_W, BTN_H),
        }

    def set_state(self, state):
        self.state = state

    def update(self, dt, mouse_pos, screen_w, screen_h):
        if screen_w != self.sw or screen_h != self.sh:
            self.layout(screen_w, screen_h)
        self.hovered = None
        for name, r in self.rects.items():
            if r.collidepoint(mouse_pos):
                self.hovered = name

    def draw(self, screen):
        for name, rect in self.rects.items():
            self.draw_button(screen, name, rect)

    def draw_button(self, screen, name, rect):
        simulating = self.state == "simulating"
        hovered = self.hovered == name

        if name == "simulate":
            active = not simulating
            base = SIM_GREEN
            hover = SIM_GREEN_H
            label = "Simulate"
            icon = self.icons["simulate_white"] if active else self.icons["simulate"]

        elif name == "stop":
            active = simulating
            base = STOP_AMBER
            hover = STOP_AMBER_H
            label = "Stop"
            icon = self.icons["stop_white"] if active else self.icons["stop"]

        else:
            active = True
            base = RESET_SLATE
            hover = RESET_SLATE_H
            label = "Reset"
            icon = self.icons["reset_white"] if active else self.icons["reset"]

        if not active:
            fill = (230, 232, 238)
            txt_col = TEXT_LIGHT
            bord = CARD_BORDER
            icon_alpha = 120
        elif hovered:
            fill = hover
            txt_col = TEXT_WHITE
            bord = hover
            icon_alpha = 255
        else:
            fill = base
            txt_col = TEXT_WHITE
            bord = base
            icon_alpha = 220

        shadow_rect(screen, rect, radius=10, offset=2, alpha=25)
        draw_rect(screen, fill, rect, radius=10)
        draw_rect(screen, bord, rect, radius=10, border=1)

        icon_surf = icon.copy()
        icon_surf.set_alpha(icon_alpha)

        iw, ih = icon_surf.get_size()
        lw, lh = F.size(label, 13, bold=True)

        spacing = 6
        total_w = iw + spacing + lw

        ix = rect.x + (rect.width - total_w) // 2
        iy_icon = rect.y + (rect.height - ih) // 2
        iy_label = rect.y + (rect.height - lh) // 2 + 1

        screen.blit(icon_surf, (ix, iy_icon))
        F.render_to(screen, (ix + iw + spacing, iy_label), label, 13, txt_col, bold=True)

    def handle_click(self, pos):
        simulating = self.state == "simulating"
        for name, r in self.rects.items():
            if r.collidepoint(pos):
                if name == "simulate" and not simulating:
                    return "simulate"
                if name == "stop" and simulating:
                    return "stop"
                if name == "reset":
                    return "reset"
        return None


class Toolbar:
    TOOLS = [
        ("move", "Place Pad", "WASD / drag"),
        ("pan", "Pan", "drag"),
        ("zoom_in", "Zoom In", "scroll up"),
        ("zoom_out", "Zoom Out", "scroll down"),
    ]

    def __init__(self, top=TOOL_TOP):
        self.active = "pan"
        self.simulating = False
        self.hovered = None
        self.rects = {}

        for i, (key, label, hint) in enumerate(self.TOOLS):
            y = top + i * (TOOL_H + TOOL_PAD)
            self.rects[key] = pygame.Rect(TOOL_X, y, TOOL_W, TOOL_H)

        self.icons = {
            "move": pygame.image.load("assets/icons/move.png").convert_alpha(),
            "move_white": pygame.image.load("assets/icons/move_white.png").convert_alpha(),
            "pan": pygame.image.load("assets/icons/pan.png").convert_alpha(),
            "pan_white": pygame.image.load("assets/icons/pan_white.png").convert_alpha(),
            "zoom_in": pygame.image.load("assets/icons/zoom_in.png").convert_alpha(),
            "zoom_in_white": pygame.image.load("assets/icons/zoom_in_white.png").convert_alpha(),
            "zoom_out": pygame.image.load("assets/icons/zoom_out.png").convert_alpha(),
            "zoom_out_white": pygame.image.load("assets/icons/zoom_out_white.png").convert_alpha(),
        }

        for k in self.icons:
            self.icons[k] = pygame.transform.smoothscale(self.icons[k], (24, 24))

    def set_simulating(self, v):
        self.simulating = v
        if v:
            self.active = "pan"

    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        self.hovered = None
        for key, rect in self.rects.items():
            if rect.collidepoint(mouse):
                self.hovered = key

    def draw(self, screen):
        count = len(self.TOOLS)
        panel_h = count * (TOOL_H + TOOL_PAD) - TOOL_PAD + 20
        panel_r = pygame.Rect(TOOL_X - 8, TOOL_TOP - 10, TOOL_W + 16, panel_h)

        shadow_rect(screen, panel_r, radius=10, offset=3, alpha=28)
        draw_rect(screen, WHITE, panel_r, radius=10, border=1, border_color=CARD_BORDER)

        for key, rect in self.rects.items():
            _, _, hint = next(t for t in self.TOOLS if t[0] == key)

            locked = self.simulating and key in ("move",)
            is_active = key == self.active
            hovered = self.hovered == key and not locked

            icon = self.icons[key + "_white" if is_active else key].copy()

            if is_active:
                bg = SIM_GREEN if key not in ("zoom_in", "zoom_out") else RESET_SLATE
            elif hovered:
                bg = (238, 240, 248)
            elif locked:
                bg = (245, 246, 250)
            else:
                bg = WHITE

            draw_rect(screen, bg, rect, radius=8, border=1, border_color=CARD_BORDER)

            icon.set_alpha(255 if not locked else 120)

            iw, ih = icon.get_size()
            ix = rect.x + (rect.width - iw) // 2
            iy = rect.y + (rect.height - ih) // 2

            screen.blit(icon, (ix, iy))

        if self.hovered:
            key = self.hovered
            _, label, hint = next(t for t in self.TOOLS if t[0] == key)

            mouse_x, mouse_y = pygame.mouse.get_pos()

            tip_w = 160
            tip_h = 40
            tip_r = pygame.Rect(mouse_x + 15, mouse_y + 10, tip_w, tip_h)

            shadow_rect(screen, tip_r, radius=8, offset=2, alpha=20)
            draw_rect(screen, WHITE, tip_r, radius=8, border=1, border_color=CARD_BORDER)

            font = pygame.font.SysFont("Arial", 10)
            text1 = font.render(label, True, TEXT_DARK)
            text2 = font.render(hint, True, TEXT_MID)

            screen.blit(text1, (tip_r.x + 10, tip_r.y + 6))
            screen.blit(text2, (tip_r.x + 10, tip_r.y + 20))

    def handle_click(self, pos):
        for key, rect in self.rects.items():
            if rect.collidepoint(pos):
                if self.simulating and key in ("move",):
                    return None
                self.active = key
                return key
        return None

    def hit(self, pos):
        return any(r.collidepoint(pos) for r in self.rects.values())


class TelemetryHUD:
    ROWS = [
        ("ALT", "altitude", "m", False),
        ("VX", "vel_x", "m/s", True),
        ("VY", "vel_y", "m/s", True),
        ("SPD", "speed", "m/s", False),
        ("ANG", "angle", "°", False),
    ]
    W = 175
    PAD = 12

    def __init__(self, sw, sh):
        self.sw = sw
        self.sh = sh
        self.visible = False

    def update(self, dt):
        pass

    def draw(self, screen, telem, sw=None, sh=None):
        if not self.visible:
            return
        if sw: self.sw = sw
        if sh: self.sh = sh

        row_h = 36
        pad = self.PAD
        panel_h = pad + 20 + 6 + len(self.ROWS) * row_h + 10 + 60 + 10 + 34 + pad
        px = self.sw - self.W - 14
        py = 14

        shadow_rect(screen, (px, py, self.W, panel_h), radius=10, offset=3, alpha=28)
        draw_rect(screen, WHITE, (px, py, self.W, panel_h), radius=10, border=1, border_color=CARD_BORDER)

        F.render_to(screen, (px + pad, py + pad), "TELEMETRY", 9, TEXT_MID, bold=True)
        pygame.draw.line(screen, CARD_BORDER, (px + 6, py + pad + 18), (px + self.W - 6, py + pad + 18), 1)

        y = py + pad + 26
        for label, key, unit, signed in self.ROWS:
            val = telem.get(key, 0.0)
            if key == "speed":
                vc = OK_COL if val < 40 else (WARN_COL if val < 80 else BAD_COL)
            elif key == "angle":
                a = val if val <= 180 else 360 - val
                vc = OK_COL if a < 10 else (WARN_COL if a < 25 else BAD_COL)
            else:
                vc = TEXT_DARK

            row_r = pygame.Rect(px + 4, y + 1, self.W - 8, row_h - 3)
            draw_rect(screen, (244, 246, 251), row_r, radius=5)

            F.render_to(screen, (px + pad, y + 10), label, 9, TEXT_MID, bold=True)
            fmt = f"{val:+.1f}" if signed else f"{val:.1f}"
            vw, _ = F.size(fmt, 13, bold=True)
            uw, _ = F.size(unit, 9)
            F.render_to(screen, (px + self.W - pad - uw - vw - 4, y + 6), fmt, 13, vc, bold=True)
            F.render_to(screen, (px + self.W - pad - uw, y + 10), unit, 9, TEXT_LIGHT)
            y += row_h

        pygame.draw.line(screen, CARD_BORDER, (px + 6, y + 4), (px + self.W - 6, y + 4), 1)
        y += 12

        fp = telem.get("fuel_pct", 1.0)
        fc = FUEL_COL if fp > 0.2 else WARN_COL
        F.render_to(screen, (px + pad, y), "FUEL", 9, TEXT_MID, bold=True)
        fv = f"{telem.get('fuel', 0):.0f} kg"
        fw, _ = F.size(fv, 11, bold=True)
        F.render_to(screen, (px + self.W - pad - fw, y), fv, 11, fc, bold=True)
        y += 16
        bar = pygame.Rect(px + pad, y, self.W - pad * 2, 6)
        draw_rect(screen, (225, 228, 238), bar, radius=3)
        fill_w = int(bar.width * fp)
        if fill_w > 0:
            draw_rect(screen, fc, (bar.x, bar.y, fill_w, bar.height), radius=3)
        y += 14

        ec = OK_COL if telem.get("thrusting") else TEXT_LIGHT
        F.render_to(screen, (px + pad, y), "● ENGINE", 9, ec, bold=True)
        y += 20

        pygame.draw.line(screen, CARD_BORDER, (px + 6, y + 2), (px + self.W - 6, y + 2), 1)
        y += 10

        if telem.get("landed"):
            sc, st = OK_COL, "LANDED ✓"
        elif telem.get("crashed"):
            sc, st = BAD_COL, "CRASHED ✕"
        else:
            sc, st = TEXT_MID, "IN FLIGHT"
        sw2, sh2 = F.size(st, 11, bold=True)
        F.render_to(screen, (px + (self.W - sw2) // 2, y + 4), st, 11, sc, bold=True)


class AutopilotHUD:
    W = 175
    PAD = 12

    def __init__(self, sw, sh):
        self.sw = sw
        self.sh = sh
        self.visible = False

    def update(self, dt):
        pass

    def draw(self, screen, status, sw=None, sh=None):
        if not self.visible:
            return
        if sw: self.sw = sw
        if sh: self.sh = sh

        phase = status.get("phase", "idle").lower()
        phase_col = PHASE_COL.get(phase, TEXT_MID)
        log_len = status.get("log_len", 0)

        tel_h = 12 + 20 + 6 + 5 * 36 + 10 + 60 + 10 + 34 + 12
        panel_h = self.PAD * 2 + 18 + 6 + 26 + 14
        px = self.sw - self.W - 14
        py = 14 + tel_h + 8

        shadow_rect(screen, (px, py, self.W, panel_h), radius=10, offset=3, alpha=28)
        draw_rect(screen, WHITE, (px, py, self.W, panel_h), radius=10, border=1, border_color=CARD_BORDER)

        F.render_to(screen, (px + self.PAD, py + self.PAD), "AUTOPILOT", 9, TEXT_MID, bold=True)
        pygame.draw.line(screen, CARD_BORDER, (px + 6, py + self.PAD + 18), (px + self.W - 6, py + self.PAD + 18), 1)

        pw, _ = F.size(phase.upper(), 13, bold=True)
        F.render_to(screen, (px + (self.W - pw) // 2, py + self.PAD + 26), phase.upper(), 13, phase_col, bold=True)

        lv = f"steps: {log_len}"
        lw, _ = F.size(lv, 9)
        F.render_to(screen, (px + (self.W - lw) // 2, py + self.PAD + 46), lv, 9, TEXT_LIGHT)
