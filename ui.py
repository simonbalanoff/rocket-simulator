"""Mission-control interface. Geometry is shared by drawing and hit testing."""
from collections import deque
from pathlib import Path

import pygame
from theme import F, draw_rect, TEXT_PRIMARY, TEXT_MID, TEXT_LIGHT, CARD_BORDER, PANEL_BG, OK_COL, WARN_COL, BAD_COL

HEADER_H = 72
BOTTOM_H = 88
SIDEBAR_W = 264
ICON_DIR = Path(__file__).resolve().parent / 'assets' / 'icons'


def panel(screen, rect, color=PANEL_BG):
    draw_rect(screen, color, rect, radius=12, border=1, border_color=CARD_BORDER)


def label(screen, pos, text, size=11, color=TEXT_MID, bold=False):
    F.render_to(screen, pos, str(text), size, color, bold=bold)


def right_text(screen, right, y, text, size=13, color=TEXT_PRIMARY, bold=False):
    label(screen, (right - F.size(str(text), size, bold)[0], y), text, size, color, bold)


def sidebar_rect(sw, sh):
    return pygame.Rect(sw - SIDEBAR_W, HEADER_H, SIDEBAR_W, sh - HEADER_H - BOTTOM_H)


def viewport_rect(sw, sh):
    return pygame.Rect(0, HEADER_H, max(1, sw - SIDEBAR_W), max(1, sh - HEADER_H - BOTTOM_H))


class SimControls:
    def __init__(self, screen_width, screen_height):
        self.state = 'stopped'
        self.hovered = None
        self.paused = False
        self.finished = False
        self.layout(screen_width, screen_height)

    def layout(self, sw, sh):
        self.sw, self.sh = sw, sh
        self.panel_rect = pygame.Rect(0, sh - BOTTOM_H, sw, BOTTOM_H)
        width = min(156, (sw - SIDEBAR_W - 64) // 3)
        self.rects = {name: pygame.Rect(24 + i * (width + 10), sh - BOTTOM_H + 20, width, 46)
                      for i, name in enumerate(('simulate', 'stop', 'reset'))}
        self.pause_rect = pygame.Rect(sw - SIDEBAR_W + 18, sh - BOTTOM_H + 20, SIDEBAR_W - 36, 46)

    def set_state(self, state):
        self.state = state

    def update(self, dt, mouse_pos, screen_w, screen_h):
        if (screen_w, screen_h) != (self.sw, self.sh):
            self.layout(screen_w, screen_h)
        self.hovered = next((key for key, rect in self.rects.items() if rect.collidepoint(mouse_pos)), None)

    def draw(self, screen):
        pygame.draw.rect(screen, PANEL_BG, self.panel_rect)
        pygame.draw.line(screen, CARD_BORDER, self.panel_rect.topleft, self.panel_rect.topright)
        active = self.state == 'simulating'
        for name, rect in self.rects.items():
            enabled = name == 'reset' or (name == 'simulate' and not active) or (name == 'stop' and active)
            fill = OK_COL if name == 'simulate' and enabled else (35, 47, 65)
            if not enabled:
                fill = (20, 29, 42)
            elif self.hovered == name:
                fill = tuple(min(255, c + 15) for c in fill)
            draw_rect(screen, fill, rect, radius=8, border=1, border_color=CARD_BORDER)
            text = {'simulate': 'Launch  /  Enter', 'stop': 'End flight  /  R', 'reset': 'Reset scene'}[name]
            color = (8, 25, 25) if name == 'simulate' and enabled else TEXT_PRIMARY if enabled else TEXT_LIGHT
            label(screen, (rect.x + 12, rect.y + 16), text, 12, color, True)
        draw_rect(screen, (28, 39, 55), self.pause_rect, radius=8, border=1, border_color=CARD_BORDER)
        label(screen, (self.pause_rect.x + 20, self.pause_rect.y + 16),
              'Flight complete' if self.finished else ('Resume' if self.paused else 'Pause') + '  /  Space', 12,
              TEXT_PRIMARY if active and not self.finished else TEXT_LIGHT, True)

    def handle_click(self, pos):
        active = self.state == 'simulating'
        if active and not self.finished and self.pause_rect.collidepoint(pos):
            return 'pause'
        for name, rect in self.rects.items():
            if rect.collidepoint(pos):
                if name == 'reset' or (name == 'simulate' and not active) or (name == 'stop' and active):
                    return name
        return None


class Toolbar:
    TOOLS = [('move', 'Place pad', 'V'), ('pan', 'Pan view', 'H'),
             ('zoom_in', 'Zoom in', '+'), ('zoom_out', 'Zoom out', '-'),
             ('fit', 'Fit mission', 'F'), ('follow', 'Follow rocket', 'C'), ('help', 'Controls', '?')]

    def __init__(self):
        self.active = 'move'
        self.simulating = False
        self.follow = False
        self.help = False
        self.hovered = None
        self.rects = {key: pygame.Rect(18, HEADER_H + 22 + i * 48, 40, 40)
                      for i, (key, _, _) in enumerate(self.TOOLS)}
        self.icons = {key: pygame.transform.smoothscale(pygame.image.load(str(ICON_DIR / f'{key}_white.png')).convert_alpha(), (18, 18))
                      for key in ('move', 'pan', 'zoom_in', 'zoom_out')}

    def set_simulating(self, value):
        self.simulating = value
        self.active = 'pan' if value else 'move'

    def update(self, dt):
        self.hovered = next((key for key, rect in self.rects.items() if rect.collidepoint(pygame.mouse.get_pos())), None)

    def draw(self, screen):
        panel(screen, pygame.Rect(10, HEADER_H + 14, 56, len(self.TOOLS) * 48 + 8))
        for key, title, shortcut in self.TOOLS:
            rect = self.rects[key]
            selected = self.active == key or (key == 'follow' and self.follow) or (key == 'help' and self.help)
            locked = key == 'move' and self.simulating
            if selected or self.hovered == key:
                draw_rect(screen, (38, 70, 75) if selected else (34, 46, 63), rect, radius=7)
            if key in self.icons:
                icon = self.icons[key].copy()
                icon.set_alpha(65 if locked else 235)
                screen.blit(icon, (rect.x + 11, rect.y + 11))
            else:
                label(screen, (rect.x + 14, rect.y + 12), {'fit': 'F', 'follow': 'C', 'help': '?'}[key], 15, OK_COL if selected else TEXT_PRIMARY, True)
        if self.hovered:
            _, title, shortcut = next(tool for tool in self.TOOLS if tool[0] == self.hovered)
            text = 'Locked during flight' if self.hovered == 'move' and self.simulating else f'{title}  [{shortcut}]'
            rect = self.rects[self.hovered]
            width = F.size(text, 12)[0] + 24
            panel(screen, (76, rect.y + 3, width, 34))
            label(screen, (88, rect.y + 14), text, 12, TEXT_PRIMARY)

    def handle_click(self, pos):
        for key, rect in self.rects.items():
            if rect.collidepoint(pos):
                if key == 'move' and self.simulating:
                    return 'locked'
                if key in ('move', 'pan'):
                    self.active = key
                return key
        return None

    def hit(self, pos):
        return pygame.Rect(10, HEADER_H + 14, 56, len(self.TOOLS) * 48 + 8).collidepoint(pos)


class TelemetryHUD:
    def __init__(self, sw, sh):
        self.visible = False
        self.history = deque(maxlen=180)
        self._sample_time = 0.0

    def update(self, dt):
        self._sample_time += dt

    def draw(self, screen, telem, sw=None, sh=None):
        # The sidebar remains useful before launch, too.
        sw, sh = screen.get_size()
        x = sw - SIDEBAR_W + 20
        y = HEADER_H + 22
        label(screen, (x, y), 'FLIGHT TELEMETRY', 10, TEXT_MID, True)
        label(screen, (x, y + 31), f"{telem.get('altitude', 0):.1f}", 36, TEXT_PRIMARY, True)
        label(screen, (x + 150, y + 51), 'px ALT', 10, TEXT_MID)
        y += 86
        for title, key, unit in [('Vertical speed', 'vel_y', 'px/s'), ('Horizontal speed', 'vel_x', 'px/s'),
                                 ('Attitude', 'angle', 'deg')]:
            value = telem.get(key, 0)
            if key == 'angle':
                value = (value + 180) % 360 - 180
            label(screen, (x, y), title, 12)
            right_text(screen, sw - 20, y, f'{value:+.1f} {unit}', 12)
            pygame.draw.line(screen, CARD_BORDER, (x, y + 25), (sw - 20, y + 25))
            y += 40
        y += 2
        fuel = max(0, min(1, telem.get('fuel_pct', 1)))
        color = OK_COL if fuel > .2 else WARN_COL
        label(screen, (x, y), 'PROPELLANT', 10, TEXT_MID, True)
        right_text(screen, sw - 20, y, f'{fuel * 100:.0f}%', 12, color, True)
        draw_rect(screen, (33, 46, 64), (x, y + 25, SIDEBAR_W - 40, 6), radius=3)
        if fuel:
            draw_rect(screen, color, (x, y + 25, int((SIDEBAR_W - 40) * fuel), 6), radius=3)
        label(screen, (x, y + 44), 'ENGINE FIRING' if telem.get('thrusting') else 'ENGINE IDLE', 10,
              OK_COL if telem.get('thrusting') else TEXT_LIGHT, True)
        if self._sample_time >= .1:
            self._sample_time = 0
            self.history.append(telem.get('vel_y', 0))
        if sh >= 800:
            chart = pygame.Rect(x, HEADER_H + 460, SIDEBAR_W - 40, 58)
            label(screen, (x, chart.y), 'VERTICAL SPEED HISTORY', 9, TEXT_MID, True)
            if len(self.history) > 1:
                scale = max(50, max(abs(v) for v in self.history))
                baseline = chart.y + 40
                pygame.draw.line(screen, CARD_BORDER, (x, baseline), (chart.right, baseline))
                points = [(chart.x + i / 179 * chart.width, baseline - value / scale * 18)
                          for i, value in enumerate(self.history)]
                pygame.draw.aalines(screen, OK_COL, False, points)



class AutopilotHUD:
    def __init__(self, sw, sh):
        self.visible = False

    def update(self, dt):
        pass

    def draw(self, screen, status, sw=None, sh=None):
        sw, sh = screen.get_size()
        x, y = sw - SIDEBAR_W + 20, HEADER_H + 348
        label(screen, (x, y), 'GUIDANCE SEQUENCE', 10, TEXT_MID, True)
        phase = status.get('phase', 'idle')
        phases = ['launch', 'ascent', 'coast', 'descent', 'terminal']
        index = phases.index(phase) if phase in phases else 5 if phase == 'landed' else -1
        for i, name in enumerate(phases):
            cx = x + 8 + i * 48
            col = OK_COL if i <= index else (48, 61, 80)
            if i < 4:
                pygame.draw.line(screen, col, (cx, y + 34), (cx + 48, y + 34), 2)
            pygame.draw.circle(screen, col, (cx, y + 34), 5)
        for i, title in enumerate(('IGN', 'ASC', 'CST', 'DSC', 'TCH')):
            label(screen, (x + i * 48, y + 46), title, 8, TEXT_LIGHT)
        label(screen, (x, y + 68), phase.upper() if phase != 'idle' else 'AWAITING LAUNCH', 16,
              BAD_COL if phase == 'failed' else OK_COL if index >= 0 else TEXT_PRIMARY, True)


def draw_chrome(screen, simulating, telemetry, elapsed, platform, toolbar, zoom, paused, recording):
    sw, sh = screen.get_size()
    pygame.draw.rect(screen, PANEL_BG, (0, 0, sw, HEADER_H))
    pygame.draw.line(screen, CARD_BORDER, (0, HEADER_H - 1), (sw, HEADER_H - 1))
    pygame.draw.rect(screen, PANEL_BG, sidebar_rect(sw, sh))
    pygame.draw.line(screen, CARD_BORDER, (sw - SIDEBAR_W, HEADER_H), (sw - SIDEBAR_W, sh - BOTTOM_H))
    label(screen, (24, 25), 'Rocket landing simulator', 19, TEXT_PRIMARY, True)
    outcome = 'LANDED' if telemetry['landed'] else 'MISSION FAILED' if telemetry['crashed'] else 'PAUSED' if paused else 'IN FLIGHT' if simulating else 'MISSION SETUP'
    color = BAD_COL if telemetry['crashed'] else WARN_COL if paused else OK_COL
    status_x = sw - SIDEBAR_W + 20
    pygame.draw.circle(screen, color, (status_x + 4, 30), 4)
    label(screen, (status_x + 16, 25), outcome, 11, color, True)
    label(screen, (status_x, 49), f'T+ {elapsed:06.2f} s' if simulating else 'AUTONOMOUS GUIDANCE', 10)
    view = viewport_rect(sw, sh)
    label(screen, (88, HEADER_H + 20), 'FLIGHT VIEW' if simulating else 'MISSION WORKSPACE', 10, TEXT_MID, True)
    right_text(screen, view.right - 20, HEADER_H + 20, f'{zoom * 100:.0f}%  /  ' + ('FOLLOW' if toolbar.follow else 'FREE VIEW'), 10, TEXT_MID)
    # Scene information stays away from interactive controls.
    if sh >= 760:
        x, y = sw - SIDEBAR_W + 20, sh - BOTTOM_H - 102
        pygame.draw.line(screen, CARD_BORDER, (x, y), (sw - 20, y))
        label(screen, (x, y + 18), 'TARGET DECK', 10, TEXT_MID, True)
        label(screen, (x, y + 40), f'X {platform.x:.0f}   /   Y {platform.get_surface_y():.0f} px', 13, TEXT_PRIMARY)
        label(screen, (x, y + 65), 'CSV RECORDING ENABLED' if recording else 'AUTOPILOT READY' if not simulating else 'GUIDANCE ACTIVE', 9, OK_COL)
    if not simulating:
        hint = 'Drag the pad or use WASD. Press Enter to launch.'
    elif telemetry['landed']:
        hint = 'Touchdown confirmed. Press R to set up another flight.'
    elif telemetry['crashed']:
        hint = 'Flight ended. Press R to adjust the landing pad and retry.'
    elif paused:
        hint = 'Simulation paused. Press Space to resume.'
    else:
        hint = 'Space to pause   /   C to follow rocket   /   F to fit mission'
    size = 12 if view.width >= 800 else 10
    tw = F.size(hint, size)[0]
    panel(screen, (view.centerx - tw // 2 - 16, view.bottom - 48, tw + 32, 32))
    label(screen, (view.centerx - tw // 2, view.bottom - 37), hint, size, TEXT_PRIMARY)
    if toolbar.help:
        rect = pygame.Rect(view.centerx - 210, HEADER_H + 72, 420, 284)
        panel(screen, rect, (24, 36, 52))
        label(screen, (rect.x + 24, rect.y + 22), 'FLIGHT CONTROLS', 17, TEXT_PRIMARY, True)
        for i, (keys, text) in enumerate([('Enter / R', 'Launch / end flight'), ('Space', 'Pause or resume'),
            ('V / H', 'Place pad / pan tool'), ('WASD / drag', 'Move landing pad before launch'),
            ('Scroll / + / -', 'Zoom around pointer'), ('F / C', 'Fit mission / toggle follow'), ('? / Esc', 'Toggle help / close help or quit')]):
            label(screen, (rect.x + 24, rect.y + 63 + i * 28), keys, 12, OK_COL, True)
            label(screen, (rect.x + 163, rect.y + 63 + i * 28), text, 11, TEXT_PRIMARY)
