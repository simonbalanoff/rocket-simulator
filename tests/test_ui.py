"""Interaction regressions for the simulator's mission-control interface."""
import csv
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
import pymunk

import main
from landing_platform import LandingPlatform
from ui import SimControls, viewport_rect


class InterfaceTests(unittest.TestCase):
    def test_controls_stay_outside_scene_and_disabled_buttons_do_not_launch(self):
        for width, height in [(800, 680), (1280, 800), (1920, 1080)]:
            controls = SimControls(width, height)
            view = viewport_rect(width, height)
            for rect in controls.rects.values():
                self.assertFalse(view.colliderect(rect))
                self.assertTrue(pygame.Rect(0, 0, width, height).contains(rect))
            controls.set_state('simulating')
            self.assertIsNone(controls.handle_click(controls.rects['simulate'].center))
            self.assertEqual(controls.handle_click(controls.pause_rect.center), 'pause')
            controls.finished = True
            self.assertIsNone(controls.handle_click(controls.pause_rect.center))

    def test_pad_center_drag_moves_both_axes_and_axis_handle_is_constrained(self):
        pad = LandingPlatform(pymunk.Space(), 960, 570, 600)
        pad.handle_mouse_down((960, 570), 0, 0, 1)
        pad.handle_mouse_move((980, 540), 0, 0, 1)
        pad.handle_mouse_up()
        self.assertEqual((pad.x, pad.y), (980, 540))
        pad.handle_mouse_down((1030, 540), 0, 0, 1)
        pad.handle_mouse_move((1050, 520), 0, 0, 1)
        self.assertEqual((pad.x, pad.y), (1000, 540))

    def test_camera_fits_both_pads_at_supported_sizes(self):
        pad = LandingPlatform(pymunk.Space(), 960, 570, 600)
        for width, height in [(800, 680), (1280, 800), (1920, 1080)]:
            px, py, zoom = main.fit_mission(width, height, pad)
            view = viewport_rect(width, height)
            for x, y in [(255, 566), (1110, 554), (320, 20)]:
                self.assertTrue(view.collidepoint(*main.world_to_screen(x, y, px, py, zoom)))

    def test_interactive_pause_resize_help_and_recorded_touchdown(self):
        frames = []
        original_chrome = main.draw_chrome

        class FastClock:
            def tick(self, fps):
                return 100

        def draw(*args):
            frames.append((args[3], args[2]['landed'], args[2]['crashed']))
            original_chrome(*args)

        def flip():
            frame = len(frames)
            key = {1: pygame.K_RETURN, 4: pygame.K_SPACE, 7: pygame.K_SPACE,
                   9: pygame.K_SLASH, 10: pygame.K_ESCAPE, 12: pygame.K_c, 15: pygame.K_f}.get(frame)
            if key is not None:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
            if frame == 11:
                pygame.display.set_mode((800, 680), pygame.RESIZABLE)
            if frames[-1][1] or frames[-1][2] or frame > 300:
                pygame.event.post(pygame.event.Event(pygame.QUIT))

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(pygame.time, 'Clock', FastClock), patch.object(pygame.display, 'flip', flip), patch.object(main, 'draw_chrome', draw):
                main.main(record_dir=directory)
            self.assertEqual(frames[3][0], frames[4][0])
            self.assertEqual(frames[4][0], frames[6][0])
            self.assertTrue(frames[-1][1], 'The interactive mission should land after resuming')
            paths = list(Path(directory).glob('*.csv'))
            self.assertEqual(len(paths), 1)
            with paths[0].open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[-1]['phase'], 'landed')
            self.assertAlmostEqual(float(rows[-1]['time']), frames[-1][0])
