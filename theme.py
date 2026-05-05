import pygame
import pygame.freetype

pygame.freetype.init()

SANS_R = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SANS_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

BG = (232, 235, 242)
BG_GRID = (215, 219, 230)
BG_AXIS = (195, 202, 218)

WHITE = (255, 255, 255)
PANEL_SHADOW = (200, 204, 215)

CARD_BG = (248, 249, 252)
CARD_BORDER = (218, 222, 232)

SIM_GREEN = (34, 168, 84)
SIM_GREEN_H = (28, 145, 72)
SIM_GREEN_D = (20, 100, 50)

STOP_AMBER = (232, 120, 20)
STOP_AMBER_H = (200, 100, 15)
STOP_AMBER_D = (140, 68, 8)

RESET_SLATE = (88, 110, 165)
RESET_SLATE_H = (70, 90, 140)
RESET_SLATE_D = (52, 66, 105)

TEXT_DARK = (28, 35, 52)
TEXT_MID = (88, 100, 128)
TEXT_LIGHT = (155, 168, 195)
TEXT_WHITE = (248, 250, 255)

OK_COL = (34, 168, 84)
WARN_COL = (220, 140, 20)
BAD_COL = (205, 52, 48)
FUEL_COL = (58, 130, 230)

GIZMO_Y = (40, 200, 80)
GIZMO_Y_HOT = (140, 255, 160)
GIZMO_X = (210, 55, 55)
GIZMO_X_HOT = (255, 155, 155)
GIZMO_ARC = (160, 180, 230)
GIZMO_ARC_A = (255, 200, 60)

PHASE_COL = {
    "idle": TEXT_LIGHT,
    "launch": (215, 90, 120),
    "ascent": (120, 95, 210),
    "coast": (110, 150, 200),
    "descent": (60, 130, 215),
    "terminal": (215, 135, 18),
    "landed": OK_COL,
    "failed": BAD_COL,
}


class Fonts:
    def __init__(self):
        self._cache = {}

    def get(self, size, bold=False):
        key = (size, bold)
        if key not in self._cache:
            path = SANS_B if bold else SANS_R
            self._cache[key] = pygame.freetype.SysFont(path, size)
        return self._cache[key]

    def render(self, text, size, color, bold=False):
        f = self.get(size, bold)
        surf, rect = f.render(text, fgcolor=color)
        return surf, rect

    def render_to(self, surface, pos, text, size, color, bold=False):
        f = self.get(size, bold)
        f.render_to(surface, pos, text, fgcolor=color)

    def size(self, text, size, bold=False):
        f = self.get(size, bold)
        _, rect = f.render(text, fgcolor=(0, 0, 0))
        return rect.width, rect.height


F = Fonts()


def draw_rect(surface, color, rect, radius=0, border=0, border_color=None):
    r = pygame.Rect(rect)
    pygame.draw.rect(surface, color, r, border_radius=radius)
    if border and border_color:
        pygame.draw.rect(surface, border_color, r, width=border, border_radius=radius)


def text_centered(surface, text, size, color, rect, bold=False):
    surf, trect = F.render(text, size, color, bold=bold)
    r = pygame.Rect(rect)
    x = r.x + (r.width - trect.width) // 2
    y = r.y + (r.height - trect.height) // 2
    surface.blit(surf, (x, y))


def shadow_rect(surface, rect, radius=8, offset=3, alpha=40):
    r = pygame.Rect(rect)
    sr = pygame.Rect(r.x + offset, r.y + offset, r.width, r.height)
    s = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
    pygame.draw.rect(s, (0, 0, 0, alpha), (0, 0, r.width, r.height), border_radius=radius)
    surface.blit(s, (sr.x, sr.y))
