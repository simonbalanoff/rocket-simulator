import asyncio
import csv
import io
import json
import subprocess
import sys
import unittest

from aiohttp.test_utils import TestClient, TestServer

from autopilot import ControllerSettings
from simulation import Simulation, DT
from web_server import apply_command, create_app


class SimulationCoreTests(unittest.TestCase):
    def test_core_does_not_import_pygame(self):
        result = subprocess.run([sys.executable, '-c',
            'import simulation, flight_analysis, web_server, sys; assert "pygame" not in sys.modules'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pause_end_and_reset(self):
        sim = Simulation()
        sim.configure(640, 450)
        sim.launch()
        sim.step()
        sim.pause()
        before = sim.snapshot(True)
        sim.step()
        self.assertEqual(before, sim.snapshot(True))
        sim.pause()
        sim.step()
        self.assertEqual(sim.elapsed, DT * 2)
        sim.stop()
        self.assertEqual(sim.state, 'placement')
        self.assertEqual(sim.platform.x, 640)
        self.assertGreater(sim.snapshot()['samples'], 0)
        self.assertIn('throttle', sim.export_recorder().to_csv())
        sim.stop(reset=True)
        self.assertEqual(sim.platform.x, 960)
        self.assertEqual(sim.platform.y, 570)

    def test_invalid_commands_do_not_mutate_mission(self):
        sim = Simulation()
        before = sim.snapshot(True)
        for message in [None, [], {'action': 'missing'}, {'action': 'configure', 'x': float('nan')},
            {'action': 'configure', 'x': 5000}, {'action': 'configure', 'x': True},
            {'action': 'configure', 'settings': {'vertical_gain': -1}},
            {'action': 'configure', 'settings': {'vertical_gain': True}}]:
            with self.subTest(message=message), self.assertRaises((ValueError, TypeError)):
                apply_command(sim, message)
            self.assertEqual(sim.snapshot(True), before)
        sim.launch()
        with self.assertRaises(ValueError):
            sim.configure(0, 500)
        with self.assertRaises(ValueError):
            sim.launch()

    def test_default_flight_and_recording_are_valid_json_and_csv(self):
        sim = Simulation()
        sim.launch()
        for _ in range(7200):
            sim.step()
            if sim.state == 'finished':
                break
        self.assertEqual(sim.outcome, 'landed')
        snapshot = sim.snapshot(True)
        json.dumps(snapshot, allow_nan=False)
        self.assertGreater(len(snapshot['trail']), 100)
        rows = list(csv.DictReader(io.StringIO(sim.recorder.to_csv())))
        self.assertEqual(rows[-1]['phase'], 'landed')
        self.assertAlmostEqual(float(rows[-1]['time']), sim.elapsed)


class WebServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = TestClient(TestServer(create_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def state(self, socket, predicate=lambda data: True):
        async def receive():
            while True:
                data = await socket.receive_json()
                if data.get('type') == 'state' and predicate(data):
                    return data
        return await asyncio.wait_for(receive(), timeout=5)

    async def test_static_assets_and_local_origin_checks(self):
        response = await self.client.get('/')
        self.assertEqual(response.status, 200)
        self.assertIn('Rocket landing simulator', await response.text())
        self.assertIn('Content-Security-Policy', response.headers)
        response = await self.client.get('/static/app.js')
        self.assertEqual(response.status, 200)
        response = await self.client.get('/', headers={'Host': 'other.example'})
        self.assertEqual(response.status, 403)
        response = await self.client.get('/ws', headers={'Origin': 'https://other.example'})
        self.assertEqual(response.status, 403)
        response = await self.client.get('/static/../../requirements.txt')
        self.assertEqual(response.status, 404)

    async def test_socket_controls_csv_errors_and_tab_isolation(self):
        socket = await self.client.ws_connect('/ws')
        other = await self.client.ws_connect('/ws')
        initial = await self.state(socket)
        self.assertEqual(initial['state'], 'placement')
        await socket.send_json({'action': 'configure', 'x': 640, 'y': 500})
        await self.state(socket, lambda data: data['platform']['x'] == 640)
        await socket.send_json({'action': 'launch'})
        running = await self.state(socket, lambda data: data['elapsed'] > .05)
        self.assertEqual(running['state'], 'running')
        await socket.send_json({'action': 'pause'})
        paused = await self.state(socket, lambda data: data['state'] == 'paused')
        later = await self.state(socket, lambda data: data['state'] == 'paused')
        self.assertEqual(later['elapsed'], paused['elapsed'])
        self.assertEqual((await self.state(other))['state'], 'placement')
        await socket.send_json({'action': 'export'})
        async def csv_message():
            while True:
                data = await socket.receive_json()
                if data['type'] == 'csv':
                    return data
        recording = await asyncio.wait_for(csv_message(), 5)
        self.assertIn('time,x,y', recording['data'])
        await socket.send_str('not json')
        async def error_message():
            while True:
                data = await socket.receive_json()
                if data['type'] == 'error':
                    return data
        self.assertTrue((await asyncio.wait_for(error_message(), 5))['message'])
        await socket.send_json({'action': 'stop'})
        stopped = await self.state(socket, lambda data: data['state'] == 'placement')
        self.assertEqual(stopped['platform']['x'], 640)
        self.assertGreater(stopped['samples'], 0)
        await socket.close()
        await other.close()
