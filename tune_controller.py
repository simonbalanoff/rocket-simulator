"""Search controller settings against a fixed training suite; never overwrite defaults."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from scipy.optimize import differential_evolution

from autopilot import ControllerSettings
from flight_analysis import SCENARIOS, run_mission

NAMES = tuple(asdict(ControllerSettings()))
BOUNDS = [(0.6, 1.5), (0.15, 0.55), (2., 5.), (5., 12.)]


def evaluate(settings, scenarios=SCENARIOS):
    results = [run_mission(x, y, settings, record=False)[0] for x, y in scenarios]
    score = sum((0 if row['outcome'] == 'landed' else 100000)
                + row['landing_error'] * 10 + row['fuel_used']
                + row['approach_speed'] * 5 for row in results) / len(results)
    return score, results


def objective(vector):
    return evaluate(ControllerSettings(**dict(zip(NAMES, vector))))[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=10)
    parser.add_argument('--population', type=int, default=5, help='population multiplier per parameter')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', type=Path, default=Path('reports/controller.json'))
    args = parser.parse_args()
    if args.iterations < 0 or args.population < 1:
        parser.error('iterations must be nonnegative and population positive')
    baseline = ControllerSettings()
    initial_score, initial_results = evaluate(baseline)
    result = differential_evolution(objective, BOUNDS, maxiter=args.iterations,
        popsize=args.population, seed=args.seed, x0=list(asdict(baseline).values()), polish=False)
    candidate = ControllerSettings(**dict(zip(NAMES, map(float, result.x))))
    score, results = evaluate(candidate)
    selected = candidate if score < initial_score else baseline
    # Holdouts are reported separately and never used to select parameters.
    holdout_score, holdouts = evaluate(selected, [(160, 500), (1100, 500), (800, 400)])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(asdict(selected), indent=2) + '\n')
    report = dict(seed=args.seed, evaluations=int(result.nfev),
                  baseline_score=initial_score, candidate_score=score,
                  baseline=initial_results, candidate=results,
                  holdout_score=holdout_score, holdouts=holdouts,
                  selected=asdict(selected), optimizer_message=str(result.message))
    args.output.with_suffix('.report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
