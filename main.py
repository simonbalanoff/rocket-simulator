import pygame
import pymunk

from rocket import Rocket
from autopilot import Autopilot
from ui import SimControls, Toolbar, TelemetryHUD, AutopilotHUD

WIDTH = 1280
HEIGHT = 800
FPS = 60
GROUND_Y = HEIGHT - 80

PLACEMENT = "placement"
SIMULATING = "simulating"


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


def draw_ground(screen, ground_seg, pan_x, pan_y, zoom, landing_x, W, H):
    body = ground_seg.body
    gx1, gy1 = world_to_screen(ground_seg.a.x + body.position.x,
                               ground_seg.a.y + body.position.y,
                               pan_x, pan_y, zoom)
    gx2, gy2 = world_to_screen(ground_seg.b.x + body.position.x,
                               ground_seg.b.y + body.position.y,
                               pan_x, pan_y, zoom)

    thick = max(1, int(ground_seg.radius * 2 * zoom) + 4)
    pygame.draw.line(screen, (178, 190, 210), (gx1, gy1), (gx2, gy2),
                     thick + 2)
    pygame.draw.line(screen, (115, 135, 170), (gx1, gy1), (gx2, gy2),
                     thick)

    lx, ly = world_to_screen(landing_x,
                             ground_seg.a.y + body.position.y,
                             pan_x, pan_y, zoom)
    zone_w = int(120 * zoom)
    liy = int(ly)
    liz = int(lx)
    pygame.draw.line(screen, (32, 165, 85),
                     (liz - zone_w // 2, liy),
                     (liz + zone_w // 2, liy), 2)
    pygame.draw.line(screen, (32, 165, 85),
                     (liz, liy - 6),
                     (liz, liy + 6), 1)
    font = pygame.font.SysFont("Helvetica", 9)
    lbl = font.render("LANDING ZONE", True, (32, 140, 78))
    screen.blit(lbl, (liz - lbl.get_width() // 2, liy + 5))


def start_sim(rocket, autopilot, controls, toolbar, hud, ap_hud):
    rocket.save_placement()
    rocket.activate_physics()
    rocket.handle_mouse_up()
    autopilot.reset()
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


def full_reset(rocket, autopilot, controls, toolbar, hud, ap_hud, pan, zoom):
    rocket.reset(to_original=True)
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
    space.gravity = (0, 500)

    ground_seg = pymunk.Segment(
        space.static_body,
        (0, GROUND_Y),
        (WIDTH * 4, GROUND_Y),
        5
    )
    ground_seg.friction = 1.0
    ground_seg.elasticity = 0.05
    space.add(ground_seg)

    landing_x = WIDTH // 2
    rocket = Rocket(space, WIDTH // 2, HEIGHT // 3, GROUND_Y)
    autopilot = Autopilot(ground_y=GROUND_Y, landing_x=landing_x)
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
                    stop_sim(rocket, autopilot, controls,
                             toolbar, hud, ap_hud)
                    state = PLACEMENT
                elif event.key == pygame.K_RETURN and state == PLACEMENT:
                    start_sim(rocket, autopilot, controls,
                              toolbar, hud, ap_hud)
                    state = SIMULATING

            if event.type == pygame.MOUSEBUTTONDOWN:
                pos = event.pos
                if event.button == 4:
                    zoom, pan_x, pan_y = zoom_at(pos, 1.1,
                                                 pan_x, pan_y, zoom)
                elif event.button == 5:
                    zoom, pan_x, pan_y = zoom_at(pos, 1 / 1.1,
                                                 pan_x, pan_y, zoom)
                elif event.button == 2:
                    panning = True
                    pan_start = pos
                    pan_origin = (pan_x, pan_y)
                elif event.button == 1:
                    sim_click = controls.handle_click(pos)
                    if sim_click == "simulate" and state == PLACEMENT:
                        start_sim(rocket, autopilot, controls,
                                  toolbar, hud, ap_hud)
                        state = SIMULATING
                    elif sim_click == "stop" and state == SIMULATING:
                        stop_sim(rocket, autopilot, controls,
                                 toolbar, hud, ap_hud)
                        state = PLACEMENT
                    elif sim_click == "reset":
                        pan_x, pan_y, zoom = full_reset(rocket, autopilot,
                                                        controls, toolbar,
                                                        hud, ap_hud,
                                                        (pan_x, pan_y), zoom)
                        state = PLACEMENT
                    else:
                        tb = toolbar.handle_click(pos)
                        if tb == "zoom_in":
                            zoom, pan_x, pan_y = zoom_at((W // 2, H // 2),
                                                         1.15,
                                                         pan_x, pan_y, zoom)
                        elif tb == "zoom_out":
                            zoom, pan_x, pan_y = zoom_at((W // 2, H // 2),
                                                         1 / 1.15,
                                                         pan_x, pan_y, zoom)
                        elif not tb:
                            if toolbar.active == "pan":
                                panning = True
                                pan_start = pos
                                pan_origin = (pan_x, pan_y)
                            elif toolbar.active in ("move", "rotate"):
                                if state == PLACEMENT:
                                    rocket.handle_mouse_down(
                                        pos, toolbar.active,
                                        pan_x, pan_y, zoom)

            if event.type == pygame.MOUSEMOTION:
                if panning:
                    dx = event.pos[0] - pan_start[0]
                    dy = event.pos[1] - pan_start[1]
                    pan_x = pan_origin[0] + dx
                    pan_y = pan_origin[1] + dy
                elif toolbar.active in ("move", "rotate"):
                    if state == PLACEMENT:
                        rocket.handle_mouse_move(
                            event.pos,
                            pan_x, pan_y, zoom)

            if event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2):
                panning = False
                rocket.handle_mouse_up()

        if state == PLACEMENT and toolbar.active in ("move", "rotate"):
            rocket.handle_keys(keys)

        if state == SIMULATING:
            tel = rocket.telemetry()
            command = autopilot.update(tel, dt)
            rocket.apply_autopilot(command, dt)
            rocket.update(dt, simulating=True, keys=keys)
            space.step(dt)
        else:
            rocket.update(dt, simulating=False)

        draw_background(screen, pan_x, pan_y, zoom, W, H)
        draw_ground(screen, ground_seg, pan_x, pan_y, zoom, landing_x, W, H)

        rocket.draw(screen, pan_x, pan_y, zoom)
        if state == PLACEMENT:
            rocket.draw_axes(screen, toolbar.active, pan_x, pan_y, zoom)

        controls.draw(screen)
        toolbar.draw(screen)

        if state == SIMULATING:
            tel = rocket.telemetry()
            hud.draw(screen, tel, W, H)
            ap_hud.draw(screen, autopilot.status_lines(), W, H)

        title = font_title.render("ROCKET LANDING SIMULATOR",
                                  True,
                                  (75, 95, 138))
        screen.blit(title, (14, 14))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
