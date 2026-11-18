#!/usr/bin/env python3
"""Run the frozen, one-split exploratory density forecast comparison."""

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = Path('/Users/waichong/projects/crowd-crush-warning')
SOURCE = CANONICAL / 'data/zenodo-14050598/data_density_over_time.txt'
CONTROLS = ROOT / 'results/pamplona-density-30s-2026-11-18/origins.jsonl'
OUT = ROOT / 'work/m06-density/run-20261118'
EXPECTED_SOURCE_SHA = 'cbc48912b51e1824017b046a6ee5f1d5eef19a529ba33d9aee361d21cd36561c'
GRID = 0.04
WINDOW = 30.0
MIN_SPAN = 5.0
ARMS = ('persistence', 'trailing_mean', 'local_trend', 'ar1', 'one_split')


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def dump(path, data):
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')


def event(path, name, **fields):
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'event': name, 'time_utc': now(), **fields}, sort_keys=True, allow_nan=False) + '\n')


def mean(values):
    result = sum(values) / len(values)
    if not math.isfinite(result):
        raise ValueError('nonfinite mean')
    return result


def sse(values, center):
    total = 0.0
    for value in values:
        d = value - center
        total += d * d
        if not math.isfinite(total):
            raise ValueError('nonfinite SSE')
    return total


def score(n, error, k):
    return -math.inf if error == 0.0 else n * math.log(error / n) + k * math.log(n)


def fit_one_split(values):
    n = len(values)
    full_mean = mean(values)
    full_sse = sse(values, full_mean)
    best = (score(n, full_sse, 1), 0, None, full_sse)
    if full_sse == 0.0:
        return {'split_index': None, 'split_after_s': None, 'segments': 1,
                'selected_sse': 0.0, 'no_split_sse': 0.0, 'criterion': '-Infinity',
                'prediction': full_mean}
    for index in range(1, n):
        if (index - 1) * GRID + 1e-12 < MIN_SPAN or (n - index - 1) * GRID + 1e-12 < MIN_SPAN:
            continue
        left, right = values[:index], values[index:]
        left_mean, right_mean = mean(left), mean(right)
        total_sse = sse(left, left_mean) + sse(right, right_mean)
        candidate = (score(n, total_sse, 3), 1, index, total_sse)
        # Tuple ordering gives simpler model first, then earliest split on exact ties.
        if candidate[:3] < best[:3]:
            best = candidate
    _, segments_minus_one, index, selected_sse = best
    prediction = mean(values[index:] if index is not None else values)
    return {'split_index': index, 'split_after_s': (index - 1) * GRID if index is not None else None,
            'segments': segments_minus_one + 1, 'selected_sse': selected_sse,
            'no_split_sse': full_sse,
            'criterion': '-Infinity' if best[0] == -math.inf else best[0],
            'prediction': prediction}


def local_trend(history, origin, target):
    mx = mean([t for t, _ in history])
    my = mean([v for _, v in history])
    denom = sum((t - mx) ** 2 for t, _ in history)
    if denom == 0:
        raise ValueError('undefined local trend')
    slope = sum((t - mx) * (v - my) for t, v in history) / denom
    value = my + slope * (target - mx)
    if not math.isfinite(value):
        raise ValueError('nonfinite local trend')
    return value


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-10)


def smoke():
    constant = fit_one_split([3.0] * 100)
    step = fit_one_split([1.0] * 126 + [4.0] * 126)
    assert constant['split_index'] is None and constant['prediction'] == 3.0
    assert step['split_index'] == 126 and step['prediction'] == 4.0
    print(json.dumps({'status': 'software smoke passed', 'constant_split': constant['split_index'],
                      'step_split_index': step['split_index'], 'step_prediction': step['prediction']}))


def run(command):
    if OUT.exists():
        raise ValueError(f'run output already exists: {OUT}')
    protocol = ROOT / '.planning/m06/density-change-point-protocol.md'
    if not protocol.is_file() or not SOURCE.is_file() or not CONTROLS.is_file():
        raise ValueError('protocol, source, or retained controls missing')
    source_sha, control_sha = sha(SOURCE), sha(CONTROLS)
    if source_sha != EXPECTED_SOURCE_SHA:
        raise ValueError('canonical density source checksum mismatch')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('actual run requires a clean tracked worktree')
    git_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    script = Path(__file__).resolve()
    protocol_sha, script_sha = sha(protocol), sha(script)
    OUT.mkdir(parents=True)
    trail = OUT / 'trail.jsonl'
    manifest = {
        'status': 'started', 'git_sha': git_sha, 'tracked_worktree_clean': True,
        'command': command, 'started_at_utc': now(), 'python': platform.python_version(),
        'dependencies': 'Python standard library plus tracked repository density reader',
        'source': {'path': str(SOURCE), 'sha256_before': source_sha, 'size_bytes': SOURCE.stat().st_size},
        'retained_controls': {'path': str(CONTROLS), 'sha256_before': control_sha, 'rows_expected': 336},
        'protocol': {'path': str(protocol), 'sha256': protocol_sha},
        'script': {'path': str(script), 'sha256': script_sha},
        'model_identity': 'local one-split piecewise-constant density forecast',
        'local_endpoint': None,
        'frozen_rule': {'grid_s': GRID, 'history_s': WINDOW, 'horizon_s': WINDOW,
                        'minimum_segment_span_s': MIN_SPAN, 'criterion': 'n*log(SSE/n)+k*log(n), k=1 or 3',
                        'split_ties': 'simpler then earliest', 'zero_sse_score': '-Infinity',
                        'comparison': list(ARMS), 'evaluation': 'EXPLORATORY; 2024 already inspected'},
    }
    dump(OUT / 'manifest.json', manifest)
    event(trail, 'started', git_sha=git_sha, source_sha256=source_sha,
          controls_sha256=control_sha, protocol_sha256=protocol_sha, script_sha256=script_sha)
    try:
        sys.path.insert(0, str(ROOT / 'src'))
        from crowd_warning.density import read_density_table
        table = read_density_table(SOURCE)
        series = {entry['year']: entry['points'] for entry in table['series']}
        old = [json.loads(line) for line in CONTROLS.read_text(encoding='utf-8').splitlines() if line]
        if len(old) != 336:
            raise ValueError(f'expected 336 retained rows, found {len(old)}')
        by_year = {year: [] for year in series}
        for row in old:
            by_year[row['year']].append(row)
        rows = []
        for year, controls in by_year.items():
            points = series[year]
            times = [p[0] for p in points]
            for row in controls:
                origin, target = row['origin_timestamp_s'], row['target_timestamp_s']
                oi, ti = round((origin - times[0]) / GRID), round((target - times[0]) / GRID)
                if oi < 0 or ti >= len(points) or not close(times[oi], origin) or not close(times[ti], target):
                    raise ValueError(f'{year} retained origin or target is off source grid')
                if not close(row['actual'], points[ti][1]) or not close(row['predictions']['persistence'], points[oi][1]):
                    raise ValueError(f'{year} retained actual or persistence disagrees with source')
                if not close(target - origin, WINDOW) or not close(row['scheduled_origin_timestamp_s'], origin):
                    raise ValueError(f'{year} retained schedule differs from frozen 30-second schedule')
                for arm, prediction in row['predictions'].items():
                    if prediction is None or not math.isfinite(prediction) or not close(row['errors'][arm], prediction - row['actual']):
                        raise ValueError(f'{year} retained {arm} control is missing, nonfinite, or inconsistent')
                history = [(t, value) for t, value in points if origin - WINDOW - 1e-9 <= t <= origin + 1e-9]
                if not history or not close(history[-1][0], origin) or not close(history[0][0], origin - WINDOW):
                    raise ValueError(f'{year} {origin} history does not span exact 30 seconds')
                fit = fit_one_split([v for _, v in history])
                predictions = {'persistence': points[oi][1], 'trailing_mean': mean([v for _, v in history]),
                               'local_trend': local_trend(history, origin, target),
                               'ar1': row['predictions']['ar1'], 'one_split': fit['prediction']}
                errors = {arm: predictions[arm] - points[ti][1] for arm in ARMS}
                rows.append({'year': year, 'origin_timestamp_s': origin, 'target_timestamp_s': target,
                             'actual': points[ti][1], 'predictions': predictions, 'errors': errors,
                             'one_split_fit': {k: v for k, v in fit.items() if k != 'prediction'}})
        if len(rows) != 336:
            raise ValueError(f'expected all 336 schedule rows, found {len(rows)}')
        if sha(SOURCE) != source_sha or sha(CONTROLS) != control_sha:
            raise ValueError('input checksum changed during run')
        event(trail, 'inputs_verified_and_fit_completed', rows=len(rows), years={str(y): len(by_year[y]) for y in by_year})
        with (OUT / 'origins.jsonl').open('x', encoding='utf-8') as f:
            for row in rows:
                f.write(json.dumps(row, sort_keys=True, allow_nan=False) + '\n')
        metrics = {'status': 'descriptive exploratory comparison; no warning, safety, or promotion claim',
                   'row_count': len(rows), 'arms': {}, 'paired_vs_persistence': {}}
        for arm in ARMS:
            e = [r['errors'][arm] for r in rows]
            metrics['arms'][arm] = {'coverage': len(e), 'mae': sum(abs(x) for x in e) / len(e),
                                    'rmse': math.sqrt(sum(x*x for x in e) / len(e))}
            if arm != 'persistence':
                d = [abs(r['errors'][arm]) - abs(r['errors']['persistence']) for r in rows]
                metrics['paired_vs_persistence'][arm] = {'count': len(d), 'mean_absolute_error_difference': sum(d)/len(d)}
        metrics['by_year'] = {}
        for year in by_year:
            yr = [r for r in rows if r['year'] == year]
            metrics['by_year'][str(year)] = {arm: {
                'coverage': len(yr), 'mae': sum(abs(r['errors'][arm]) for r in yr)/len(yr),
                'rmse': math.sqrt(sum(r['errors'][arm]**2 for r in yr)/len(yr))} for arm in ARMS}
        dump(OUT / 'metrics.json', metrics)
        dump(OUT / 'comparison.json', {'verified_retained_control_rows': len(old),
                                       'source_origin_target_actual_persistence_local_trend_ar1_checks': 'passed',
                                       'note': 'Trailing mean is recomputed under the stated 30-second history rule.'})
        artifacts = ['manifest.json', 'origins.jsonl', 'metrics.json', 'comparison.json']
        hashes = {name: sha(OUT / name) for name in artifacts}
        event(trail, 'completed', exit_status=0, artifacts=hashes,
              source_sha256_after=sha(SOURCE), controls_sha256_after=sha(CONTROLS))
        print(json.dumps({'status': 'completed', 'output': str(OUT), 'rows': len(rows), 'artifacts': hashes}))
    except Exception as exc:
        event(trail, 'failed', error_type=type(exc).__name__, reason=str(exc))
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.smoke == args.run:
        parser.error('select exactly one of --smoke or --run')
    smoke() if args.smoke else run([sys.executable, str(Path(__file__).resolve()), '--run'])


if __name__ == '__main__':
    main()
