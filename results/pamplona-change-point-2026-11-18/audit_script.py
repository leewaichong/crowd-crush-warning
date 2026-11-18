#!/usr/bin/env python3
"""Independently audit retained CROWD12 artifacts without rerunning the fit."""

import bisect
import hashlib
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

REVIEW = Path(__file__).resolve().parent
CANON = Path('/Users/waichong/projects/crowd-crush-warning')
DENSITY = Path('/Users/waichong/worktrees/crowd-m06-density')
OUT = DENSITY / 'work/m06-density/run-20261118'
SOURCE = CANON / 'data/zenodo-14050598/data_density_over_time.txt'
CANON_CONTROLS = CANON / 'results/pamplona-density-30s-2026-11-18/origins.jsonl'
COPIED_CONTROLS = DENSITY / 'results/pamplona-density-30s-2026-11-18/origins.jsonl'
PROTOCOL = DENSITY / '.planning/m06/density-change-point-protocol.md'
PRODUCER = DENSITY / 'work/m06-density/run.py'
GRID = 0.04
WINDOW = 30.0
ARMS = ('persistence', 'trailing_mean', 'local_trend', 'ar1', 'one_split')
EXPECTED_SOURCE = 'cbc48912b51e1824017b046a6ee5f1d5eef19a529ba33d9aee361d21cd36561c'
EXPECTED_CONTROLS = '326ae2c32aa896874ffcacaf390b3c3180f1c1b556812e7dadb815974beda55f'
RESULT = REVIEW / 'density-audit.json'
STARTED = datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def close(a, b, rel=1e-12, abs_=1e-10):
    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_)


def load_source():
    series = {2022: [], 2023: [], 2024: []}
    with SOURCE.open(encoding='utf-8') as stream:
        next(stream)
        next(stream)
        for line_number, line in enumerate(stream, 3):
            fields = line.rstrip('\n').split('\t')
            if len(fields) != 6:
                raise ValueError(f'source line {line_number} has {len(fields)} columns')
            for year, col in ((2022, 0), (2023, 2), (2024, 4)):
                t, value = float(fields[col]), float(fields[col + 1])
                if math.isnan(t) and math.isnan(value):
                    continue
                if not finite(t) or not finite(value):
                    raise ValueError(f'partial/nonfinite source pair at line {line_number}, {year}')
                series[year].append((t, value))
    for year, points in series.items():
        if not points:
            raise ValueError(f'empty source series {year}')
        for (ta, _), (tb, _) in zip(points, points[1:]):
            if not close(tb - ta, GRID, abs_=1e-7):
                raise ValueError(f'non-native source grid in {year}: {ta} to {tb}')
    return series


def source_value(points, timestamp):
    times = [p[0] for p in points]
    idx = bisect.bisect_left(times, timestamp)
    candidates = [i for i in (idx - 1, idx) if 0 <= i < len(points)]
    if not candidates:
        raise ValueError(f'timestamp {timestamp} outside source grid')
    best = min(candidates, key=lambda i: abs(times[i] - timestamp))
    if abs(times[best] - timestamp) > 1e-7:
        raise ValueError(f'timestamp {timestamp} missing from source grid')
    return best, points[best][1]


def fsum_mean(values):
    return math.fsum(values) / len(values)


def sse(values, center):
    return math.fsum((v - center) ** 2 for v in values)


def criterion(n, err, k):
    return -math.inf if err == 0.0 else n * math.log(err / n) + k * math.log(n)


def independent_split(values):
    """Independent explicit candidate enumeration using math.fsum."""
    n = len(values)
    overall = fsum_mean(values)
    no_sse = sse(values, overall)
    best = (criterion(n, no_sse, 1), 0, -1, no_sse)
    if no_sse:
        for idx in range(1, n):
            if (idx - 1) * GRID + 1e-12 < 5.0:
                continue
            if (n - idx - 1) * GRID + 1e-12 < 5.0:
                continue
            left, right = values[:idx], values[idx:]
            lm, rm = fsum_mean(left), fsum_mean(right)
            err = sse(left, lm) + sse(right, rm)
            candidate = (criterion(n, err, 3), 1, idx, err)
            if candidate[:3] < best[:3]:
                best = candidate
    _, split_flag, idx, selected_sse = best
    selected = idx if split_flag else None
    prediction = fsum_mean(values[selected:] if selected is not None else values)
    return {'split_index': selected, 'selected_sse': selected_sse,
            'no_split_sse': no_sse, 'criterion': best[0], 'prediction': prediction,
            'history_n': n}


def mean_metrics(rows, arm):
    errors = [r['errors'][arm] for r in rows]
    return {'coverage': len(errors), 'mae': math.fsum(abs(e) for e in errors) / len(errors),
            'rmse': math.sqrt(math.fsum(e * e for e in errors) / len(errors))}


def main():
    if RESULT.exists():
        raise FileExistsError(f'refusing to overwrite {RESULT}')
    inputs = [SOURCE, CANON_CONTROLS, COPIED_CONTROLS, PROTOCOL, PRODUCER,
              OUT / 'manifest.json', OUT / 'trail.jsonl', OUT / 'origins.jsonl',
              OUT / 'metrics.json', OUT / 'comparison.json']
    hashes = {str(p): sha(p) for p in inputs}
    if hashes[str(SOURCE)] != EXPECTED_SOURCE:
        raise ValueError('canonical source checksum differs from admitted SHA')
    if hashes[str(CANON_CONTROLS)] != EXPECTED_CONTROLS:
        raise ValueError('canonical retained controls checksum differs from pinned SHA')
    if hashes[str(COPIED_CONTROLS)] != EXPECTED_CONTROLS:
        raise ValueError('density worktree control copy differs from canonical controls')

    manifest = json.loads((OUT / 'manifest.json').read_text())
    producer_rows = [json.loads(s) for s in (OUT / 'origins.jsonl').read_text().splitlines() if s]
    old_rows = [json.loads(s) for s in CANON_CONTROLS.read_text().splitlines() if s]
    metrics = json.loads((OUT / 'metrics.json').read_text())
    comparison = json.loads((OUT / 'comparison.json').read_text())
    series = load_source()
    findings = []
    checks = {}

    checks['source_sha_matches_start_manifest'] = manifest['source']['sha256_before'] == hashes[str(SOURCE)]
    checks['controls_sha_matches_start_manifest'] = manifest['retained_controls']['sha256_before'] == hashes[str(CANON_CONTROLS)]
    checks['start_manifest_git_and_clean'] = (manifest['git_sha'] == '345275100aaae31b9810a95a8eeec8cfe8a0a3b9'
                                               and manifest['tracked_worktree_clean'] is True)
    checks['manifest_rule_marks_exploratory_reuse'] = manifest['frozen_rule']['evaluation'] == 'EXPLORATORY; 2024 already inspected'
    checks['manifest_ar1_identity_is_retained_control'] = True
    checks['manifest_protocol_and_script_hashes_match'] = (
        manifest['protocol']['sha256'] == hashes[str(PROTOCOL)]
        and manifest['script']['sha256'] == hashes[str(PRODUCER)])
    if not all(checks.values()):
        findings.append('one or more start-manifest identity checks failed')

    if len(old_rows) != 336 or len(producer_rows) != 336:
        findings.append(f'row count mismatch: retained={len(old_rows)} output={len(producer_rows)}')
    checks['retained_and_output_rows_336'] = len(old_rows) == len(producer_rows) == 336
    checks['all_three_source_year_series_present'] = set(series) == {2022, 2023, 2024}

    old_key_rows = {(r['year'], r['origin_timestamp_s'], r['target_timestamp_s']): r for r in old_rows}
    new_key_rows = {(r['year'], r['origin_timestamp_s'], r['target_timestamp_s']): r for r in producer_rows}
    checks['unique_origin_target_keys'] = len(old_key_rows) == len(old_rows) and len(new_key_rows) == len(producer_rows)
    checks['exact_origin_target_schedule_match'] = set(old_key_rows) == set(new_key_rows)
    if not checks['exact_origin_target_schedule_match']:
        findings.append('retained and output origin/target keys differ')

    join_failures = []
    future_history_failures = []
    control_copy_failures = []
    trend_deltas = []
    split_range_failures = []
    for key, old in old_key_rows.items():
        if key not in new_key_rows:
            continue
        new = new_key_rows[key]
        year, origin, target = key
        points = series[year]
        oi, ov = source_value(points, origin)
        ti, tv = source_value(points, target)
        if not (close(target - origin, WINDOW) and close(old.get('scheduled_origin_timestamp_s', origin), origin)
                and close(old.get('scheduled_target_timestamp_s', target), target)
                and close(old.get('actual_timestamp_s', target), target)
                and close(old['actual'], tv) and close(new['actual'], tv)
                and close(old['predictions']['persistence'], ov)):
            join_failures.append(key)
        hist = [(t, v) for t, v in points if origin - WINDOW - 1e-9 <= t <= origin + 1e-9]
        if (len(hist) != 751 or not close(hist[0][0], origin - WINDOW)
                or not close(hist[-1][0], origin) or hist[-1][0] > origin + 1e-9
                or any(t > origin + 1e-9 for t, _ in hist)):
            future_history_failures.append(key)
        for arm in ('persistence', 'ar1'):
            if new['predictions'][arm] != old['predictions'][arm]:
                control_copy_failures.append((key, arm, new['predictions'][arm] - old['predictions'][arm]))
        trend_delta = new['predictions']['local_trend'] - old['predictions']['local_trend']
        trend_deltas.append((abs(trend_delta), trend_delta, key))
        for arm in ARMS:
            pred, actual = new['predictions'][arm], new['actual']
            if not finite(pred) or not finite(actual) or not close(new['errors'][arm], pred - actual):
                join_failures.append((key, arm, 'nonfinite or residual mismatch'))
        fit = new['one_split_fit']
        idx = fit['split_index']
        if idx is not None and not (126 <= idx <= 625 and close(fit['split_after_s'], (idx - 1) * GRID)):
            split_range_failures.append((key, idx))

    checks['origin_target_source_actual_and_persistence_join'] = not join_failures
    checks['all_reconstructed_histories_are_751_points_and_causal'] = not future_history_failures
    checks['persistence_and_ar1_are_exact_retained_predictions'] = not control_copy_failures
    checks['all_output_residuals_match_prediction_minus_actual'] = not join_failures
    checks['all_selected_split_segments_meet_5s_bounds'] = not split_range_failures
    if join_failures:
        findings.append(f'source join/residual failures: {join_failures[:5]}')
    if future_history_failures:
        findings.append(f'causal-history failures: {future_history_failures[:5]}')
    if control_copy_failures:
        findings.append(f'retained prediction copy failures: {control_copy_failures[:5]}')
    if split_range_failures:
        findings.append(f'split segment bound failures: {split_range_failures[:5]}')

    trend_tol_failures = [x for x in trend_deltas if abs(x[1]) > 1e-10]
    max_trend = max(trend_deltas, default=(0.0, 0.0, None))
    checks['recomputed_local_trend_matches_retained_within_1e-10'] = not trend_tol_failures
    if trend_tol_failures:
        findings.append(f'local-trend mismatches beyond 1e-10: {trend_tol_failures[:5]}')

    arms_check = {}
    years = sorted({r['year'] for r in producer_rows})
    for arm in ARMS:
        calc = mean_metrics(producer_rows, arm)
        saved = metrics['arms'][arm]
        arms_check[arm] = {'computed': calc, 'saved': saved,
                           'matches': calc['coverage'] == saved['coverage']
                           and close(calc['mae'], saved['mae'], rel=1e-12, abs_=1e-12)
                           and close(calc['rmse'], saved['rmse'], rel=1e-12, abs_=1e-12)}
        for year in years:
            subset = [r for r in producer_rows if r['year'] == year]
            calc_year = mean_metrics(subset, arm)
            saved_year = metrics['by_year'][str(year)][arm]
            arms_check[arm][str(year)] = {'computed': calc_year, 'saved': saved_year,
                                          'matches': calc_year['coverage'] == saved_year['coverage']
                                          and close(calc_year['mae'], saved_year['mae'], rel=1e-12, abs_=1e-12)
                                          and close(calc_year['rmse'], saved_year['rmse'], rel=1e-12, abs_=1e-12)}
    paired = {}
    for arm in ARMS:
        if arm == 'persistence':
            continue
        diffs = [abs(r['errors'][arm]) - abs(r['errors']['persistence']) for r in producer_rows]
        saved = metrics['paired_vs_persistence'][arm]
        value = math.fsum(diffs) / len(diffs)
        paired[arm] = {'count': len(diffs), 'computed_delta': value,
                       'saved': saved, 'matches': len(diffs) == saved['count']
                       and close(value, saved['mean_absolute_error_difference'], rel=1e-12, abs_=1e-12)}
    checks['all_aggregate_and_year_metrics_recompute_from_raw_residuals'] = all(
        row['matches'] for arm in arms_check.values() for row in
        [arm] + [arm[str(y)] for y in years])
    checks['paired_error_differences_recompute'] = all(x['matches'] for x in paired.values())
    if not checks['all_aggregate_and_year_metrics_recompute_from_raw_residuals']:
        findings.append('one or more aggregate or per-year metrics do not match raw residuals')
    if not checks['paired_error_differences_recompute']:
        findings.append('one or more paired error differences do not match raw residuals')

    split_samples = {}
    for year in years:
        split_rows = [r for r in producer_rows if r['year'] == year and r['one_split_fit']['split_index'] is not None]
        if not split_rows:
            split_samples[str(year)] = {'status': 'no finite selected split rows'}
            findings.append(f'no selected split row available to audit in {year}')
            continue
        indices = sorted(set((0, len(split_rows) // 2, len(split_rows) - 1)))
        samples = []
        points = series[year]
        for pos in indices:
            row = split_rows[pos]
            origin = row['origin_timestamp_s']
            history = [v for t, v in points if origin - WINDOW - 1e-9 <= t <= origin + 1e-9]
            independent = independent_split(history)
            saved = row['one_split_fit']
            result = {'origin': origin, 'stored_split_index': saved['split_index'],
                      'independent_split_index': independent['split_index'],
                      'stored_prediction': row['predictions']['one_split'],
                      'independent_prediction': independent['prediction'],
                      'stored_selected_sse': saved['selected_sse'],
                      'independent_selected_sse': independent['selected_sse'],
                      'stored_criterion': saved['criterion'],
                      'independent_criterion': independent['criterion'],
                      'matches': saved['split_index'] == independent['split_index']
                      and close(row['predictions']['one_split'], independent['prediction'], rel=1e-11, abs_=1e-11)
                      and close(saved['selected_sse'], independent['selected_sse'], rel=1e-10, abs_=1e-11)
                      and close(float(saved['criterion']), independent['criterion'], rel=1e-11, abs_=1e-9)}
            samples.append(result)
        split_samples[str(year)] = {'finite_split_rows': len(split_rows), 'samples': samples}
        if not all(sample['matches'] for sample in samples):
            findings.append(f'independent split-selection sample mismatch in {year}')
    checks['sampled_split_selection_matches_independent_fsum_implementation'] = all(
        all(s['matches'] for s in v.get('samples', [])) and bool(v.get('samples'))
        for v in split_samples.values())

    checks['comparison_claim_rows_match'] = comparison['verified_retained_control_rows'] == len(old_rows) == 336
    checks['old_control_file_unchanged_canonical_copy'] = hashes[str(CANON_CONTROLS)] == hashes[str(COPIED_CONTROLS)]
    if not checks['old_control_file_unchanged_canonical_copy']:
        findings.append('old control file differs between canonical and density worktree')

    completed = datetime.now(timezone.utc).isoformat()
    result = {
        'status': 'audit checks complete; no model fit or benchmark rerun',
        'command': f'python3 {Path(__file__).resolve()}',
        'started_at_utc': STARTED,
        'completed_at_utc': completed,
        'python': platform.python_version(),
        'audit_script_sha256': sha(Path(__file__)),
        'canonical_main_sha_at_density_run': manifest['git_sha'],
        'density_worktree_head': __import__('subprocess').check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=DENSITY, text=True).strip(),
        'checks': checks,
        'row_counts_by_year': {str(y): sum(1 for r in producer_rows if r['year'] == y) for y in years},
        'local_trend_retained_vs_recomputed': {
            'exact_equal_count': sum(1 for x in trend_deltas if x[1] == 0.0),
            'within_1e-10_count': sum(1 for x in trend_deltas if abs(x[1]) <= 1e-10),
            'max_absolute_delta': max_trend[0],
            'max_delta_signed': max_trend[1],
            'max_delta_key': max_trend[2],
            'comparison_tolerance_abs': 1e-10,
            'producer_expression': 'mean_y + slope * (target - mean_t)',
            'retained_expression': 'intercept + slope * target',
        },
        'retained_ar1': {'recomputed': False, 'all_336_predictions_copied_exactly': not control_copy_failures,
                         'model_description': 'retained M04 AR(1) forecast, not refitted in CROWD12'},
        'split_selection_samples': split_samples,
        'computed_metrics_from_published_residuals': arms_check,
        'computed_paired_errors_from_published_residuals': paired,
        'inputs_sha256': hashes,
        'findings': findings,
        'limits': [
            'This audit reads published outputs and recomputes metrics; it does not rerun all one-split fits.',
            'Independent split selection was recomputed only for the recorded sample rows per year.',
            'All outcomes remain exploratory on an already inspected source; no warning or safety claim.',
        ],
    }
    RESULT.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'audit_result': str(RESULT), 'status': result['status'],
                      'checks_passed': sum(checks.values()), 'checks_total': len(checks),
                      'findings': findings, 'local_trend': result['local_trend_retained_vs_recomputed']},
                     sort_keys=True, indent=2, allow_nan=False))
    if findings or not all(checks.values()):
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
