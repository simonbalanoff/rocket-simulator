import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np

from autopilot import ControllerSettings, StateEstimator
from flight_analysis import FlightRecorder, plot_flight, run_mission


class EstimatorTests(unittest.TestCase):
    def test_prediction_couples_position_velocity_and_preserves_covariance(self):
        estimator = StateEstimator()
        raw = dict(x=0., bottom_y=0., vel_x=10., vel_y=-20., angle=359.,
                   omega_deg_s=2., altitude=600.)
        estimator.update(raw, .1)
        for i in range(1, 30):
            raw.update(x=i, bottom_y=-2*i, angle=(359 + i * .2) % 360,
                       altitude=600 + 2*i)
            estimate = estimator.update(raw, .1)
        self.assertAlmostEqual(estimate['x'], 29., places=5)
        self.assertAlmostEqual(estimate['bottom_y'], -58., places=5)
        self.assertAlmostEqual(estimate['angle'], 364.8, places=5)
        self.assertNotEqual(estimator.covariance[0, 2], 0)
        np.testing.assert_allclose(estimator.covariance, estimator.covariance.T, atol=1e-12)
        self.assertGreaterEqual(np.linalg.eigvalsh(estimator.covariance).min(), 0)
        estimator.reset()
        self.assertFalse(estimator._primed)

    def test_filter_reduces_noisy_constant_velocity_position_error(self):
        rng = np.random.default_rng(42)
        estimator = StateEstimator()
        measured_errors, filtered_errors = [], []
        for i in range(300):
            truth = i / 120 * 20
            raw = dict(x=truth + rng.normal(0, 3 ** .5), bottom_y=0.,
                       vel_x=20 + rng.normal(0, 2 ** .5), vel_y=0.,
                       angle=0., omega_deg_s=0., altitude=600.)
            estimate = estimator.update(raw)
            if i > 30:
                measured_errors.append((raw['x'] - truth) ** 2)
                filtered_errors.append((estimate['x'] - truth) ** 2)
        self.assertLess(np.mean(filtered_errors), np.mean(measured_errors) * .5)

    def test_invalid_inputs_are_rejected(self):
        for value in (0, -1, float('nan')):
            with self.assertRaises(ValueError):
                StateEstimator().update({}, value)
        with self.assertRaises(ValueError):
            ControllerSettings(vertical_gain=-1)


class AnalysisTests(unittest.TestCase):
    def test_recorded_mission_is_reproducible_and_has_terminal_sample(self):
        first, recorder = run_mission()
        second, _ = run_mission(record=False)
        self.assertEqual(first, second)
        self.assertEqual(first['outcome'], 'landed')
        self.assertEqual(recorder.rows[-1]['phase'], 'landed')
        self.assertEqual(recorder.rows[-1]['time'], first['elapsed'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'nested' / 'flight.csv'
            recorder.save(path)
            with path.open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), len(recorder.rows))
            self.assertEqual(rows[-1]['landed'], 'True')
            if importlib.util.find_spec('matplotlib'):
                output = Path(directory) / 'flight.png'
                plot_flight(path, output)
                self.assertEqual(output.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')

    def test_timeout_and_empty_recording(self):
        summary, recorder = run_mission(duration=.1)
        self.assertEqual(summary['outcome'], 'timeout')
        self.assertGreater(len(recorder.rows), 1)
        with self.assertRaises(ValueError):
            FlightRecorder().save('unused.csv')

    @unittest.skipUnless(importlib.util.find_spec('scipy'), 'optional SciPy not installed')
    def test_tuning_penalizes_failed_missions(self):
        from tune_controller import evaluate
        good, _ = evaluate(ControllerSettings(), [(960, 570)])
        bad, results = evaluate(ControllerSettings(), [(20000, 570)])
        self.assertNotEqual(results[0]['outcome'], 'landed')
        self.assertGreater(bad, good + 100000)
