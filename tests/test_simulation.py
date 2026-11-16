import unittest
from autopilot import AutopilotCommand, StateEstimator
import pymunk
from rocket import Rocket,ROCKET_H
from autopilot import Autopilot
from landing_platform import LandingPlatform

def flight(x=960,y=570):
 s=pymunk.Space(); s.gravity=(0,980)
 for a,b,r in [((-5000,600),(10000,600),5),((255,568),(385,568),2)]:
  seg=pymunk.Segment(s.static_body,a,b,r); seg.friction=1; s.add(seg)
 p=LandingPlatform(s,x,y,600); r=Rocket(s,320,530,600); r.activate_physics(); r.configure_landing_detection(landing_x=x,landing_surface_y=p.get_surface_y(),landing_half_w=150,launch_x=320,launch_surface_y=566,launch_half_w=65)
 ap=Autopilot(p.get_surface_y(),x,566,320)
 for i in range(120*60):
  dt=1/120; r.apply_autopilot(ap.update(r.telemetry(),dt),dt); s.step(dt); r.update(dt,True)
  if r.landed or r.crashed: break
 return r,ap,i/120

class SimulationTests(unittest.TestCase):
    def test_missions_land_on_both_sides_and_at_different_heights(self):
        for x, y in [(960, 570), (0, 570), (640, 570), (1200, 570), (960, 450)]:
            with self.subTest(x=x, y=y):
                rocket, autopilot, elapsed = flight(x, y)
                self.assertTrue(rocket.landed)
                self.assertFalse(rocket.crashed)
                self.assertGreater(rocket.fuel, 0)
                self.assertLess(abs(rocket.body.position.x - x), 139)

    def test_platform_geometry_matches_guidance(self):
        space = pymunk.Space()
        pad = LandingPlatform(space, 960, 570, 600)
        self.assertEqual(pad.get_center_x(), 960)
        self.assertEqual(pad.seg.a.y - pad.seg.radius, pad.get_surface_y())
        self.assertEqual((pad.seg.a.x + pad.seg.b.x) / 2, pad.get_center_x())

    def test_nearby_airborne_rocket_is_not_landed(self):
        space = pymunk.Space()
        rocket = Rocket(space, 960, 500, 600)
        rocket.activate_physics()
        rocket.configure_landing_detection(landing_x=960, landing_surface_y=554,
            landing_half_w=150, launch_x=320, launch_surface_y=566, launch_half_w=65)
        rocket.check_landing()
        self.assertFalse(rocket.landed)
        self.assertFalse(rocket.crashed)

    def test_angle_filter_crosses_zero_without_large_jump(self):
        estimator = StateEstimator()
        raw = Rocket(pymunk.Space(), 0, 0, 600).telemetry()
        raw['angle'] = 359
        estimator.update(raw)
        raw['angle'] = 1
        result = estimator.update(raw)
        self.assertLess(abs((result['angle'] + 180) % 360 - 180), 2)

    def test_fuel_limits_thrust_and_reset_refills(self):
        rocket = Rocket(pymunk.Space(), 0, 0, 600)
        rocket.activate_physics()
        rocket.fuel = 0.01
        rocket.apply_autopilot(AutopilotCommand(thrust=1), 1)
        self.assertEqual(rocket.fuel, 0)
        self.assertAlmostEqual(rocket.body.force.length, 5600 * .01 / 12)
        rocket.update(1 / 120, False)
        self.assertTrue(rocket.thrusting)
        rocket.reset()
        self.assertEqual(rocket.fuel, 300)

    def test_ground_contact_is_a_failure(self):
        space = pymunk.Space()
        space.gravity = (0, 980)
        ground = pymunk.Segment(space.static_body, (-500, 600), (500, 600), 5)
        space.add(ground)
        rocket = Rocket(space, 0, 555, 600)
        rocket.activate_physics()
        rocket.configure_landing_detection(landing_x=960, landing_surface_y=554,
            landing_half_w=150, launch_x=320, launch_surface_y=566, launch_half_w=65)
        for _ in range(120):
            rocket.apply_autopilot(AutopilotCommand(), 1 / 120)
            space.step(1 / 120)
            rocket.update(1 / 120, True)
            if rocket.crashed:
                break
        self.assertTrue(rocket.crashed)
        self.assertFalse(rocket.landed)

if __name__ == '__main__':
    unittest.main()
