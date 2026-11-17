import pygame
import pygame.freetype

pygame.freetype.init()

# Shared mission-control palette. Keep foreground text distinct from scene colors.
PANEL_BG = (17, 25, 38)
CARD_BORDER = (42, 55, 74)
TEXT_PRIMARY = (226, 234, 244)
TEXT_MID = (144, 161, 184)
TEXT_LIGHT = (104, 123, 148)
OK_COL = (88, 221, 183)
WARN_COL = (220, 140, 20)
BAD_COL = (205, 52, 48)


class Fonts:
    def __init__(self):
        self._cache = {}

    def get(self, size, bold=False):
        key = (size, bold)
        if key not in self._cache:
            self._cache[key] = pygame.freetype.SysFont("Helvetica,Arial,Liberation Sans", size, bold=bold)
        return self._cache[key]

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
