import argparse
from collections import deque
from datetime import datetime
import json
import math
from pathlib import Path

import pygame
import pymunk

from rocket import Rocket, ROCKET_H
from autopilot import Autopilot, ControllerSettings
from recording import FlightRecorder
from landing_platform import LandingPlatform, PLATFORM_W
from ui import (SimControls, Toolbar, TelemetryHUD, AutopilotHUD,
                draw_chrome, viewport_rect, label, HEADER_H, BOTTOM_H)

WIDTH = 1280
HEIGHT = 800
FPS = 60
PHYSICS_DT = 1.0 / 120.0
MAX_FRAME_DT = 0.1
GROUND_Y = HEIGHT - 200

PLACEMENT = "placement"
SIMULATING = "simulating"

LAUNCH_PAD_X = WIDTH // 4
LAUNCH_PAD_Y = GROUND_Y

DEFAULT_LAND_X = (WIDTH * 3) // 4
DEFAULT_LAND_Y = GROUND_Y - 30

LAUNCH_PAD_W = 130
LAUNCH_PAD_H = 14
LAUNCH_PAD_LEG = 22


def world_to_screen(wx, wy, pan_x, pan_y, zoom):
    return wx * zoom + pan_x, wy * zoom + pan_y


def zoom_at(mouse_pos, factor, pan_x, pan_y, zoom):
    mx, my = mouse_pos
    new_zoom = max(0.1, min(8.0, zoom * factor))
    scale = new_zoom / zoom
    return new_zoom, mx - scale * (mx - pan_x), my - scale * (my - pan_y)


def fit_mission(width, height, platform):
    """Fit launch, target, and expected ascent inside the unobstructed canvas."""
    view = viewport_rect(width, height)
    left = min(LAUNCH_PAD_X - 100, platform.x - PLATFORM_W / 2) - 65
    right = max(LAUNCH_PAD_X + 100, platform.x + PLATFORM_W / 2) + 65
    top = min(0, platform.get_surface_y() - 580)
    bottom = GROUND_Y + 65
    zoom = max(.1, min(1.5, (view.width - 140) / (right - left),
                              (view.height - 120) / (bottom - top)))
    return (view.centerx + 25 - (left + right) / 2 * zoom,
            view.centery - 10 - (top + bottom) / 2 * zoom, zoom)


def draw_background(screen, pan_x, pan_y, zoom, W, H):
    screen.fill((11, 18, 29))
    grid_size = 60 * zoom
    if grid_size < 4:
        return
    grid_col = (23, 35, 51)
    ox = pan_x % grid_size
    oy = pan_y % grid_size
    x = -grid_size
    while x < W + grid_size:
        pygame.draw.line(screen, grid_col, (int(x + ox), 0), (int(x + ox), H))
        x += grid_size
    y = -grid_size
    while y < H + grid_size:
        pygame.draw.line(screen, grid_col, (0, int(y + oy)), (W, int(y + oy)))
        y += grid_size
    axis_col = (35, 51, 70)
    pygame.draw.line(screen, axis_col, (int(pan_x), 0), (int(pan_x), H))
    pygame.draw.line(screen, axis_col, (0, int(pan_y)), (W, int(pan_y)))


def draw_ground(screen, ground_seg, pan_x, pan_y, zoom, W, H):
    _, ground = world_to_screen(0, GROUND_Y, pan_x, pan_y, zoom)
    if ground >= H:
        return
    top = max(0, int(ground))
    pygame.draw.rect(screen, (18, 28, 40), (0, top, W, H - top))
    pygame.draw.line(screen, (63, 84, 98), (0, int(ground)), (W, int(ground)), 2)
    # Sparse survey marks give scale without distracting from the vehicle.
    spacing = 60 * zoom
    x = pan_x % spacing
    while x < W:
        pygame.draw.line(screen, (40, 57, 72), (int(x), int(ground)),
                         (int(x - 16 * zoom), int(ground + 20 * zoom)), 1)
        x += spacing


def draw_launch_pad(screen, pad_x, pad_y, pan_x, pan_y, zoom):
    pw = LAUNCH_PAD_W * zoom
    ph = LAUNCH_PAD_H * zoom
    leg = LAUNCH_PAD_LEG * zoom
    leg_w = max(2, int(5 * zoom))

    cx, cy = world_to_screen(pad_x, pad_y, pan_x, pan_y, zoom)
    cy -= (20 * zoom)

    for off in (-0.3, 0.3):
        lx = int(cx + pw * off)
        pygame.draw.line(screen, (70, 85, 110), (lx, int(cy)), (lx, int(cy + leg)), leg_w)

    deck = pygame.Rect(int(cx - pw / 2), int(cy - ph), int(pw), int(ph))
    pygame.draw.rect(screen, (48, 58, 80), deck, border_radius=max(1, int(3 * zoom)))
    stripe = pygame.Rect(int(cx - pw / 2 + 4 * zoom), int(cy - ph + 3 * zoom),
                         int(pw - 8 * zoom), max(2, int(3 * zoom)))
    pygame.draw.rect(screen, (80, 100, 140), stripe)

    font_size = max(8, int(10 * zoom))
    try:
        font = pygame.font.SysFont("Helvetica", font_size)
        lbl = font.render("LAUNCH PAD", True, (160, 200, 160))
        if lbl.get_width() > 0:
            screen.blit(lbl, (int(cx - lbl.get_width() / 2), int(cy + leg + 20)))
    except pygame.error:
        pass


def start_sim(rocket, platform, autopilot, controls, toolbar, hud, ap_hud, launch_surface_y, launch_x):
    autopilot.configure_mission(
        landing_surface_y=platform.get_surface_y(),
        landing_x=platform.get_center_x(),
        launch_surface_y=launch_surface_y,
        launch_x=float(launch_x),
    )
    autopilot.reset()
    rocket.activate_physics()
    rocket.configure_landing_detection(
        landing_x=platform.get_center_x(),
        landing_surface_y=platform.get_surface_y(),
        landing_half_w=PLATFORM_W / 2,
        launch_x=float(launch_x),
        launch_surface_y=launch_surface_y,
        launch_half_w=LAUNCH_PAD_W / 2,
    )
    rocket.handle_mouse_up()
    platform.handle_mouse_up()
    controls.set_state("simulating")
    toolbar.set_simulating(True)
    hud.history.clear()
    hud.visible = True
    ap_hud.visible = True


def stop_sim(rocket, autopilot, controls, toolbar, hud, ap_hud):
    rocket.reset()
    autopilot.reset()
    controls.set_state("stopped")
    toolbar.set_simulating(False)
    hud.visible = False
    ap_hud.visible = False


def full_reset(rocket, platform, autopilot, controls, toolbar, hud, ap_hud):
    rocket.reset(to_original=True)
    platform.reset(to_original=True)
    autopilot.reset()
    controls.set_state("stopped")
    toolbar.set_simulating(False)
    hud.visible = False
    ap_hud.visible = False
    return 0.0, 0.0, 1.0


def main(record_dir=None, settings=None):
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Rocket Landing Simulator")
    clock = pygame.time.Clock()

    space = pymunk.Space()
    space.gravity = (0, 980)

    ground_seg = pymunk.Segment(
        space.static_body,
        (-WIDTH * 4, GROUND_Y),
        (WIDTH * 8, GROUND_Y),
        5,
    )
    ground_seg.friction = 1.0
    ground_seg.elasticity = 0.05
    space.add(ground_seg)

    pad_top_y = GROUND_Y - 20 - LAUNCH_PAD_H
    pad_physics = pymunk.Segment(
        space.static_body,
        (LAUNCH_PAD_X - LAUNCH_PAD_W // 2, pad_top_y + 2),
        (LAUNCH_PAD_X + LAUNCH_PAD_W // 2, pad_top_y + 2),
        2
    )
    pad_physics.friction = 1.0
    pad_physics.elasticity = 0.1
    space.add(pad_physics)

    rocket_start_x = float(LAUNCH_PAD_X)
    rocket_start_y = pad_top_y - (ROCKET_H / 2)

    rocket = Rocket(space, rocket_start_x, rocket_start_y, GROUND_Y)

    platform = LandingPlatform(space, DEFAULT_LAND_X, DEFAULT_LAND_Y, GROUND_Y)

    autopilot = Autopilot(
        landing_surface_y=platform.get_surface_y(),
        landing_x=platform.get_center_x(),
        launch_surface_y=pad_top_y,
        launch_x=float(LAUNCH_PAD_X),
        settings=settings,
    )

    controls = SimControls(WIDTH, HEIGHT)
    toolbar = Toolbar()
    hud = TelemetryHUD(WIDTH, HEIGHT)
    ap_hud = AutopilotHUD(WIDTH, HEIGHT)
    controls.set_state("stopped")

    state = PLACEMENT
    pan_x, pan_y, zoom = fit_mission(WIDTH, HEIGHT, platform)
    paused = False
    trail = deque(maxlen=2400)
    last_size = (WIDTH, HEIGHT)
    last_state = PLACEMENT
    panning = False
    pan_start = (0, 0)
    pan_origin = (0.0, 0.0)

    accumulator = 0.0
    flight_time = 0.0
    recorder = None

    def save_recording():
        if recorder is not None and recorder.rows:
            filename = datetime.now().strftime("flight-%Y%m%d-%H%M%S-%f.csv")
            recorder.save(Path(record_dir) / filename)

    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, MAX_FRAME_DT)
        W, H = screen.get_size()
        if (W, H) != last_size:
            W, H = max(800, W), max(680, H)
            screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
            pan_x, pan_y, zoom = fit_mission(W, H, platform)
            last_size = (W, H)
        keys = pygame.key.get_pressed()

        mouse_pos = pygame.mouse.get_pos()
        controls.update(dt, mouse_pos, W, H)
        toolbar.update(dt)
        hud.update(dt)
        ap_hud.update(dt)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if toolbar.help:
                        toolbar.help = False
                    else:
                        running = False
                elif event.key == pygame.K_SPACE and state == SIMULATING and not (rocket.landed or rocket.crashed):
                    paused = not paused
                elif event.key == pygame.K_f:
                    pan_x, pan_y, zoom = fit_mission(W, H, platform)
                    toolbar.follow = False
                elif event.key == pygame.K_c:
                    toolbar.follow = not toolbar.follow
                elif event.key == pygame.K_v and state == PLACEMENT:
                    toolbar.active = "move"
                elif event.key == pygame.K_h:
                    toolbar.active = "pan"
                elif event.key in (pygame.K_SLASH, pygame.K_QUESTION):
                    toolbar.help = not toolbar.help
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_MINUS):
                    view = viewport_rect(W, H)
                    zoom, pan_x, pan_y = zoom_at(view.center, 1 / 1.15 if event.key == pygame.K_MINUS else 1.15, pan_x, pan_y, zoom)
                    toolbar.follow = False
                elif event.key == pygame.K_r:
                    stop_sim(rocket, autopilot, controls, toolbar, hud, ap_hud)
                    state = PLACEMENT
                elif event.key == pygame.K_RETURN and state == PLACEMENT:
                    start_sim(
                        rocket, platform, autopilot, controls,
                        toolbar, hud, ap_hud, pad_top_y, LAUNCH_PAD_X,
                    )
                    state = SIMULATING

            if event.type == pygame.MOUSEWHEEL and viewport_rect(W, H).collidepoint(mouse_pos) and not toolbar.help:
                zoom, pan_x, pan_y = zoom_at(mouse_pos, 1.1 ** event.y, pan_x, pan_y, zoom)

            if event.type == pygame.MOUSEBUTTONDOWN:
                pos = event.pos
                if toolbar.help:
                    toolbar.help = False
                    continue
                over_scene = viewport_rect(W, H).collidepoint(pos) and not toolbar.hit(pos)
                if event.button == 4 and over_scene:
                    zoom, pan_x, pan_y = zoom_at(pos, 1.1, pan_x, pan_y, zoom)
                elif event.button == 5 and over_scene:
                    zoom, pan_x, pan_y = zoom_at(pos, 1 / 1.1, pan_x, pan_y, zoom)
                elif event.button == 2 and over_scene:
                    panning = True
                    toolbar.follow = False
                    pan_start = pos
                    pan_origin = (pan_x, pan_y)
                elif event.button == 1:
                    sim_click = controls.handle_click(pos)
                    if sim_click == "pause":
                        if not (rocket.landed or rocket.crashed):
                            paused = not paused
                    elif sim_click == "simulate" and state == PLACEMENT:
                        start_sim(
                            rocket, platform, autopilot, controls,
                            toolbar, hud, ap_hud, pad_top_y, LAUNCH_PAD_X,
                        )
                        state = SIMULATING
                    elif sim_click == "stop" and state == SIMULATING:
                        stop_sim(rocket, autopilot, controls, toolbar, hud, ap_hud)
                        state = PLACEMENT
                    elif sim_click == "reset":
                        pan_x, pan_y, zoom = full_reset(
                            rocket, platform, autopilot,
                            controls, toolbar, hud, ap_hud)
                        state = PLACEMENT
                        pan_x, pan_y, zoom = fit_mission(W, H, platform)
                        toolbar.follow = False
                    elif controls.panel_rect.collidepoint(pos):
                        continue
                    else:
                        tb = toolbar.handle_click(pos)
                        if tb == "zoom_in":
                            zoom, pan_x, pan_y = zoom_at(
                                viewport_rect(W, H).center, 1.15, pan_x, pan_y, zoom)
                        elif tb == "zoom_out":
                            zoom, pan_x, pan_y = zoom_at(
                                viewport_rect(W, H).center, 1 / 1.15, pan_x, pan_y, zoom)
                        elif tb == "fit":
                            pan_x, pan_y, zoom = fit_mission(W, H, platform)
                            toolbar.follow = False
                        elif tb == "follow":
                            toolbar.follow = not toolbar.follow
                        elif tb == "help":
                            toolbar.help = not toolbar.help
                        elif not tb and over_scene:
                            if toolbar.active == "pan":
                                panning = True
                                toolbar.follow = False
                                pan_start = pos
                                pan_origin = (pan_x, pan_y)
                            elif toolbar.active == "move" and state == PLACEMENT:
                                platform.handle_mouse_down(pos, pan_x, pan_y, zoom)

            if event.type == pygame.MOUSEMOTION:
                if panning:
                    dx = event.pos[0] - pan_start[0]
                    dy = event.pos[1] - pan_start[1]
                    pan_x = pan_origin[0] + dx

                    pan_y = pan_origin[1] + dy
                elif toolbar.active == "move" and state == PLACEMENT:
                    platform.handle_mouse_move(event.pos, pan_x, pan_y, zoom)

            if event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2):
                panning = False
                platform.handle_mouse_up()

        if state != last_state:
            panning = False
            paused = False
            flight_time = 0.0
            trail.clear()
            last_state = state

        if state == PLACEMENT and toolbar.active == "move" and not toolbar.help:
            platform.handle_keys(keys, speed=180.0 * dt)

        if state != SIMULATING and recorder is not None:
            save_recording()
            recorder = None

        if state == SIMULATING:
            if record_dir is not None and recorder is None and not (rocket.landed or rocket.crashed):
                recorder = FlightRecorder()
                flight_time = 0.0
            accumulator += 0.0 if paused else dt
            while accumulator >= PHYSICS_DT:
                if not (rocket.landed or rocket.crashed):
                    command = autopilot.update(rocket.telemetry(), PHYSICS_DT)
                    if recorder is not None:
                        recorder.record(flight_time, rocket.telemetry(), command, autopilot.targets,
                                        platform.get_center_x(), platform.get_surface_y())
                    rocket.apply_autopilot(command, PHYSICS_DT)
                    space.step(PHYSICS_DT)
                    rocket.update(PHYSICS_DT, simulating=True)
                    flight_time += PHYSICS_DT
                    if len(trail) == 0 or flight_time - trail[-1][0] >= 1 / 30:
                        trail.append((flight_time, tuple(rocket.body.position)))
                    if rocket.landed or rocket.crashed:
                        final = autopilot.update(rocket.telemetry(), PHYSICS_DT)
                        if recorder is not None:
                            recorder.record(flight_time, rocket.telemetry(), final, {},
                                            platform.get_center_x(), platform.get_surface_y())
                            save_recording()
                            recorder = None
                accumulator -= PHYSICS_DT
            if rocket.landed or rocket.crashed:
                rocket.update(dt, simulating=False)
        else:
            accumulator = 0.0
            rocket.update(dt, simulating=False)

        view = viewport_rect(W, H)
        if toolbar.follow:
            target_x = view.centerx - rocket.body.position.x * zoom
            target_y = view.centery - rocket.body.position.y * zoom
            blend = 1 - math.exp(-6 * dt)
            pan_x += (target_x - pan_x) * blend
            pan_y += (target_y - pan_y) * blend
        screen.set_clip(view)
        draw_background(screen, pan_x, pan_y, zoom, W, H)
        platform.draw(screen, pan_x, pan_y, zoom)
        draw_ground(screen, ground_seg, pan_x, pan_y, zoom, W, H)
        draw_launch_pad(screen, LAUNCH_PAD_X, GROUND_Y, pan_x, pan_y, zoom)

        if state == PLACEMENT and toolbar.active == "move":
            platform.draw_gizmo(screen, pan_x, pan_y, zoom)

        if len(trail) > 1:
            points = [world_to_screen(*position, pan_x, pan_y, zoom) for _, position in trail]
            pygame.draw.aalines(screen, (54, 121, 121), False, points)
        rocket.draw(screen, pan_x, pan_y, zoom)
        # Target centerline and a consistent world-space scale reference.
        tx, ty = world_to_screen(platform.x, platform.get_surface_y(), pan_x, pan_y, zoom)
        pygame.draw.line(screen, (88, 221, 183), (int(tx) - 9, int(ty) - 8), (int(tx) + 9, int(ty) - 8), 2)
        pygame.draw.line(screen, (88, 221, 183), (int(tx), int(ty) - 17), (int(tx), int(ty) - 1), 1)
        sx, sy = world_to_screen(*rocket.body.position, pan_x, pan_y, zoom)
        if not view.inflate(-40, -40).collidepoint(sx, sy):
            marker_x = max(view.left + 88, min(view.right - 88, sx))
            marker_y = max(view.top + 60, min(view.bottom - 80, sy))
            pygame.draw.circle(screen, (88, 221, 183), (int(marker_x), int(marker_y)), 9, 2)
            label(screen, (marker_x - 36, marker_y + 18), 'ROCKET / C', 10, (88, 221, 183), True)
        screen.set_clip(None)
        draw_chrome(screen, state == SIMULATING, rocket.telemetry(), flight_time,
                    platform, toolbar, zoom, paused, record_dir is not None)
        controls.finished = rocket.landed or rocket.crashed
        controls.paused = paused
        controls.draw(screen)
        toolbar.draw(screen)
        if not toolbar.help:
            over_button = (any(rect.collidepoint(mouse_pos) for rect in controls.rects.values())
                           or controls.pause_rect.collidepoint(mouse_pos) or toolbar.hit(mouse_pos))
            try:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if over_button else
                                        pygame.SYSTEM_CURSOR_SIZEALL if panning else pygame.SYSTEM_CURSOR_ARROW)
            except pygame.error:
                pass  # Some headless/window-system drivers do not support cursors.

        hud.draw(screen, rocket.telemetry(), W, H)
        ap_hud.draw(screen, autopilot.status_lines(), W, H)

        pygame.display.flip()

    save_recording()
    pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interactive rocket landing simulator")
    parser.add_argument('--record-dir', type=Path, help='save each flight as CSV in this directory')
    parser.add_argument('--settings', type=Path, help='controller settings JSON from tune_controller.py')
    args = parser.parse_args()
    settings = ControllerSettings(**json.loads(args.settings.read_text())) if args.settings else None
    main(record_dir=args.record_dir, settings=settings)
