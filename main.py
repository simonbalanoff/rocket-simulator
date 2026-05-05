import pygame
import pymunk

from rocket import Rocket, ROCKET_H
from autopilot import Autopilot
from landing_platform import LandingPlatform, PLATFORM_W
from ui import SimControls, Toolbar, TelemetryHUD, AutopilotHUD

WIDTH = 1280
HEIGHT = 800
FPS = 60
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


def draw_background(screen, pan_x, pan_y, zoom, W, H):
    screen.fill((228, 232, 242))
    grid_size = 60 * zoom
    if grid_size < 4:
        return
    grid_col = (210, 216, 230)
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
    axis_col = (188, 198, 218)
    pygame.draw.line(screen, axis_col, (int(pan_x), 0), (int(pan_x), H))
    pygame.draw.line(screen, axis_col, (0, int(pan_y)), (W, int(pan_y)))


def draw_ground(screen, ground_seg, pan_x, pan_y, zoom, W, H):
    body = ground_seg.body
    gx1, gy1 = world_to_screen(ground_seg.a.x + body.position.x,
                               ground_seg.a.y + body.position.y,
                               pan_x, pan_y, zoom)
    if gy1 < H:
        ground_rect = pygame.Rect(0, int(gy1), W, H - int(gy1))
        pygame.draw.rect(screen, (128, 86, 65), ground_rect)

    thick = max(2, int(8 * zoom))
    pygame.draw.line(screen, (34, 139, 34), (0, gy1), (W, gy1), thick)

    pygame.draw.line(screen, (50, 205, 50), (0, gy1 - 1), (W, gy1 - 1), max(1, thick // 3))


def draw_launch_pad(screen, pad_x, pad_y, pan_x, pan_y, zoom):
    pw = LAUNCH_PAD_W * zoom
    ph = LAUNCH_PAD_H * zoom
    leg = LAUNCH_PAD_LEG * zoom
    leg_w = max(4, int(10 * zoom))

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
    controls.set_state("simulating")
    toolbar.set_simulating(True)
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


def main():
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

    pad_top_y = GROUND_Y - 35 - LAUNCH_PAD_H
    pad_physics = pymunk.Segment(
        space.static_body,
        (LAUNCH_PAD_X - LAUNCH_PAD_W // 2, pad_top_y),
        (LAUNCH_PAD_X + LAUNCH_PAD_W // 2, pad_top_y),
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
    )

    controls = SimControls(WIDTH, HEIGHT)
    toolbar = Toolbar()
    hud = TelemetryHUD(WIDTH, HEIGHT)
    ap_hud = AutopilotHUD(WIDTH, HEIGHT)
    controls.set_state("stopped")

    state = PLACEMENT
    zoom = 1.0
    pan_x = 0.0
    pan_y = 0.0
    panning = False
    pan_start = (0, 0)
    pan_origin = (0.0, 0.0)

    font_title = pygame.font.SysFont("Helvetica", 24, bold=True)
    font_hint = pygame.font.SysFont("Helvetica", 13)

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        W, H = screen.get_size()
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
                    running = False
                elif event.key == pygame.K_r:
                    stop_sim(rocket, autopilot, controls, toolbar, hud, ap_hud)
                    state = PLACEMENT
                elif event.key == pygame.K_RETURN and state == PLACEMENT:
                    start_sim(
                        rocket, platform, autopilot, controls,
                        toolbar, hud, ap_hud, pad_top_y, LAUNCH_PAD_X,
                    )
                    state = SIMULATING

            if event.type == pygame.MOUSEBUTTONDOWN:
                pos = event.pos
                if event.button == 4:
                    zoom, pan_x, pan_y = zoom_at(pos, 1.1, pan_x, pan_y, zoom)
                elif event.button == 5:
                    zoom, pan_x, pan_y = zoom_at(pos, 1 / 1.1, pan_x, pan_y, zoom)
                elif event.button == 2:
                    panning = True
                    pan_start = pos
                    pan_origin = (pan_x, pan_y)
                elif event.button == 1:
                    sim_click = controls.handle_click(pos)
                    if sim_click == "simulate" and state == PLACEMENT:
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
                    else:
                        tb = toolbar.handle_click(pos)
                        if tb == "zoom_in":
                            zoom, pan_x, pan_y = zoom_at(
                                (W // 2, H // 2), 1.15, pan_x, pan_y, zoom)
                        elif tb == "zoom_out":
                            zoom, pan_x, pan_y = zoom_at(
                                (W // 2, H // 2), 1 / 1.15, pan_x, pan_y, zoom)
                        elif not tb:
                            if toolbar.active == "pan":
                                panning = True
                                pan_start = pos
                                pan_origin = (pan_x, pan_y)
                            elif toolbar.active == "move" and state == PLACEMENT:
                                platform.handle_mouse_down(pos, pan_x, pan_y, zoom)

            if event.type == pygame.MOUSEMOTION:
                if panning:
                    dx = event.pos[0] - pan_start[0]
                    dy = event.pos[1] - pan_start[1]
                    pan_x = pan_origin[0] + dx

                    target_y = pan_origin[1] + dy
                    min_pan_y = -GROUND_Y * zoom + 400
                    max_pan_y = H * 0.7
                    pan_y = max(min_pan_y, min(max_pan_y, target_y))
                elif toolbar.active == "move" and state == PLACEMENT:
                    platform.handle_mouse_move(event.pos, pan_x, pan_y, zoom)

            if event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2):
                panning = False
                platform.handle_mouse_up()

        if state == PLACEMENT and toolbar.active == "move":
            platform.handle_keys(keys)

        if state == SIMULATING:
            if not rocket.landed and not rocket.crashed:
                rocket.check_landing()
            tel = rocket.telemetry()
            command = autopilot.update(tel, dt)
            rocket.apply_autopilot(command, dt)
            space.step(dt)
            rocket.update(dt, simulating=True)
        else:
            rocket.update(dt, simulating=False)

        draw_background(screen, pan_x, pan_y, zoom, W, H)
        platform.draw(screen, pan_x, pan_y, zoom)
        draw_launch_pad(screen, LAUNCH_PAD_X, GROUND_Y, pan_x, pan_y, zoom)
        draw_ground(screen, ground_seg, pan_x, pan_y, zoom, W, H)

        if state == PLACEMENT and toolbar.active == "move":
            platform.draw_gizmo(screen, pan_x, pan_y, zoom)

        rocket.draw(screen, pan_x, pan_y, zoom)
        controls.draw(screen)
        toolbar.draw(screen)

        if state == SIMULATING:
            tel = rocket.telemetry()
            hud.draw(screen, tel, W, H)
            ap_hud.draw(screen, autopilot.status_lines(), W, H)

        title = font_title.render("ROCKET LANDING SIMULATOR", True, (75, 95, 138))
        screen.blit(title, (14, 14))

        if state == PLACEMENT:
            hint_text = "Move landing pad: drag gizmo or WASD  |  Enter / Simulate to launch"
            hint = font_hint.render(hint_text, True, (110, 130, 170))
            hint_y = H - BOTTOM_H - 28 if (H - BOTTOM_H - 28) > 50 else 50
            screen.blit(hint, (W // 2 - hint.get_width() // 2, hint_y))

        pygame.display.flip()

    pygame.quit()


BOTTOM_H = 80

if __name__ == "__main__":
    main()
