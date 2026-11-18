"""Fit training-only parameters for CROWD15's source-reported Lyon proxy.

This ignored experiment helper performs no forecasts or scoring. Run only after
lead review of .planning/m08/crowd15-training-fit.md.
"""
import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/Users/waichong/projects/crowd-crush-warning')
sys.path.insert(0, str(ROOT / 'src'))
from crowd_warning.lyon import read_lyon_topview  # noqa: E402

MEMBER = 'Data_Madras/TopView_trajectories/TopView_1B.txt'
TRAIN_LAST = 2876
COUPLING = 0.15
ROLLING_SECONDS = 1.0
EXPECTED_ARCHIVE_SHA256 = 'efd80ef53dcf124286e5ca280d7d3daf52e0b6b2fe9441afb1d23c9a0baf150c'
EXPECTED_MEMBER_SHA256 = '1419d83a1568c8f6aff82e93af14294c9a4dbbe853c5dc1da97dedf3b497fe0c'


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def git_provenance():
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=Path.cwd(), text=True).strip()
    dirty = subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=no'], cwd=Path.cwd(), text=True
    ).strip()
    return {'tracked_git_sha': head, 'tracked_worktree_clean': not bool(dirty)}


def build_training_proxy(rows):
    # Filter before deriving bounds, points, increments, or proxy values.
    train_rows = [r for r in rows if r['source_frame'] <= TRAIN_LAST]
    if not train_rows:
        raise ValueError('no training rows')
    xs = [r['projected_x_epsg2154_m'] for r in train_rows]
    ys = [r['projected_y_epsg2154_m'] for r in train_rows]
    xmid = (min(xs) + max(xs)) / 2.0
    ymid = (min(ys) + max(ys)) / 2.0
    area = (max(xs) - min(xs)) * (max(ys) - min(ys)) / 4.0
    if not math.isfinite(area) or area <= 0:
        raise ValueError('training tile area is invalid')

    def zone(row):
        return (1 if row['projected_x_epsg2154_m'] >= xmid else 0) + 2 * (
            1 if row['projected_y_epsg2154_m'] >= ymid else 0
        )

    point_counts = defaultdict(int)
    frame_times = {}
    previous_by_trace = {}
    velocity_sums = defaultdict(lambda: [0.0, 0.0, 0])
    for row in train_rows:
        frame = row['source_frame']
        z = zone(row)
        frame_times.setdefault(frame, set()).add(row['source_t_s'])
        point_counts[(frame, z)] += 1
        previous = previous_by_trace.get(row['trace_id'])
        if previous is not None:
            frame_delta = frame - previous['source_frame']
            dt = row['source_t_s'] - previous['source_t_s']
            if frame_delta == 1 and dt > 0:
                key = (frame, z)
                acc = velocity_sums[key]
                acc[0] += (row['projected_x_epsg2154_m'] - previous['projected_x_epsg2154_m']) / dt
                acc[1] += (row['projected_y_epsg2154_m'] - previous['projected_y_epsg2154_m']) / dt
                acc[2] += 1
        previous_by_trace[row['trace_id']] = row

    times = {}
    for frame, values in frame_times.items():
        if len(values) != 1:
            raise ValueError(f'frame {frame} maps to multiple source times')
        times[frame] = next(iter(values))

    proxy = {z: [] for z in range(4)}
    missing = defaultdict(int)
    rolling = {z: deque() for z in range(4)}
    for frame in range(TRAIN_LAST + 1):
        if frame not in times:
            raise ValueError(f'missing training source frame {frame}')
        t = times[frame]
        for z in range(4):
            history = rolling[z]
            while history and history[0][0] < t - ROLLING_SECONDS:
                history.popleft()
            sx, sy, n = velocity_sums[(frame, z)]
            current = (sx / n, sy / n) if n else None
            if current is not None:
                history.append((t, current[0], current[1]))
            if point_counts[(frame, z)] == 0:
                missing[z] += 1
                continue
            if len(history) < 2:
                missing[z] += 1
                continue
            mx = sum(v[1] for v in history) / len(history)
            my = sum(v[2] for v in history) / len(history)
            variance = sum((v[1] - mx) ** 2 + (v[2] - my) ** 2 for v in history) / len(history)
            q = (point_counts[(frame, z)] / area) * variance
            if not math.isfinite(q) or q < 0:
                raise ValueError(f'invalid training proxy at frame {frame}, tile {z}')
            proxy[z].append({
                'source_t_s': t,
                'source_frame': frame,
                'tile': z,
                'q': q,
                'reported_track_rows': point_counts[(frame, z)],
                'current_frame_velocity_increment_count': n,
                'rolling_window_zone_mean_count': len(history),
                'tile_area_source_declared_m2': area,
            })

    bounds = {'x_min': min(xs), 'x_max': max(xs), 'x_mid': xmid,
              'y_min': min(ys), 'y_max': max(ys), 'y_mid': ymid}
    return proxy, area, missing, bounds


def fit_parent_diffusion(values):
    if len(values) < 2:
        raise ValueError('tile has fewer than two usable training proxy observations')
    values = sorted(values, key=lambda item: item['source_frame'])
    if any(b['source_t_s'] <= a['source_t_s'] or b['source_frame'] != a['source_frame'] + 1
           for a, b in zip(values, values[1:])):
        raise ValueError('training proxy series has a gap; no interpolation is allowed')
    elapsed = values[-1]['source_t_s'] - values[0]['source_t_s']
    drift = (values[-1]['q'] - values[0]['q']) / elapsed
    residual_sq = 0.0
    total_dt = 0.0
    for a, b in zip(values, values[1:]):
        dt = b['source_t_s'] - a['source_t_s']
        residual_sq += ((b['q'] - a['q']) - drift * dt) ** 2
        total_dt += dt
    diffusion = math.sqrt(residual_sq / total_dt)
    if not math.isfinite(drift) or not math.isfinite(diffusion) or diffusion <= 0:
        raise ValueError('training drift/diffusion is nonfinite or degenerate')
    return {'drift_per_source_second': drift, 'diffusion_per_sqrt_source_second': diffusion,
            'observation_count': len(values),
            'training_time_range_s': [values[0]['source_t_s'], values[-1]['source_t_s']]}


def nearest_rank(values, p):
    ordered = sorted(values)
    if not ordered:
        raise ValueError('no finite training proxy values for threshold')
    rank = math.ceil(p * len(ordered))
    return ordered[rank - 1], rank, len(ordered)


def main():
    run_started = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--freeze-manifest', required=True, type=Path)
    args = parser.parse_args()
    q_path = args.output.with_name(args.output.stem + '-q-values.jsonl')
    if args.output.exists() or q_path.exists():
        raise FileExistsError('fit output path already exists; refusing to overwrite')
    freeze = json.loads(args.freeze_manifest.read_text())
    git_before = git_provenance()
    if git_before['tracked_git_sha'] != freeze['tracked_git_sha'] or not git_before['tracked_worktree_clean']:
        raise ValueError('tracked Git state does not match the pre-run freeze')
    for path, expected in freeze['frozen_file_sha256'].items():
        if sha256_file(path) != expected:
            raise ValueError(f'frozen input changed before fit: {path}')
    table = read_lyon_topview(args.archive, member=MEMBER)
    if table['provenance']['archive_sha256'] != EXPECTED_ARCHIVE_SHA256:
        raise ValueError('archive SHA-256 does not match approved input')
    if table['provenance']['member_sha256'] != EXPECTED_MEMBER_SHA256:
        raise ValueError('member SHA-256 does not match approved input')
    proxy, tile_area, missing, bounds = build_training_proxy(table['rows'])
    q_path.parent.mkdir(parents=True, exist_ok=True)
    with q_path.open('x') as out:
        for z in range(4):
            for item in proxy[z]:
                out.write(json.dumps(item, sort_keys=True) + '\n')

    parameters = {str(z): fit_parent_diffusion(proxy[z]) for z in range(4)}
    threshold, rank, n = nearest_rank([item['q'] for series in proxy.values() for item in series], .95)

    after_table = read_lyon_topview(args.archive, member=MEMBER)
    archive_after = sha256_file(args.archive)
    if archive_after != EXPECTED_ARCHIVE_SHA256 or after_table['provenance']['member_sha256'] != EXPECTED_MEMBER_SHA256:
        raise ValueError('source archive/member changed during fit; preserving q-values artifact')
    git_after = git_provenance()
    run_ended = datetime.now(timezone.utc)
    if git_after['tracked_git_sha'] != freeze['tracked_git_sha'] or not git_after['tracked_worktree_clean']:
        raise ValueError('tracked Git state changed during fit; preserving q-values artifact')
    result = {
        'status': 'fitted-exploratory training-only parameters; no forecasts or scores',
        'statistical_model_identity': 'local offline fixed-parameter adapter using coupled-zone-first-passage-v1 equations',
        'endpoint': None,
        'input': table['provenance'],
        'source_terms': {
            'record_doi': '10.5281/zenodo.13830435',
            'license': 'CC BY 4.0 at record scope',
            'article': 'Dufour et al., Dense Crowd Dynamics and Pedestrian Trajectories: A Multiscale Field Dataset from the Festival of Lights in Lyon, Scientific Data 12, 718 (2025), DOI 10.1038/s41597-025-04732-3',
        },
        'member': MEMBER,
        'training_frames_inclusive': [0, TRAIN_LAST],
        'zone_rule': 'four equal-area tiles from training-only projected-coordinate bounding box',
        'tile_bounds_source_declared_m_private': bounds,
        'tile_area_m2_source_declared': tile_area,
        'feature_definition': 'training reported trajectory rows per tile area times population variance of available causal tile-mean source-coordinate rates in inclusive trailing [t-1s,t] window',
        'feature_unit': 'reported-track-record m^-2 times source-declared (m/s)^2; statistical proxy only',
        'missing_proxy_frame_cells_by_tile': {str(k): v for k, v in missing.items()},
        'aggregate_training_q_values': {'path': str(q_path), 'sha256': sha256_file(q_path),
                                        'row_count': sum(len(v) for v in proxy.values())},
        'threshold': {'rule': 'nearest-rank pooled training proxy 95th percentile', 'value': threshold, 'rank': rank, 'sample_count': n},
        'fitted_parameters': parameters,
        'fixed_model_settings': {'coupling': COUPLING, 'jump_rate_per_s': 0.0, 'jump_scale': 0.0},
        'provenance': {
            'exact_command': freeze['exact_command'],
            'command_argv': sys.argv,
            'started_at_utc': run_started.isoformat(),
            'ended_at_utc': run_ended.isoformat(),
            'python': sys.version,
            'platform': platform.platform(),
            'archive_sha256': sha256_file(args.archive),
            'prepared_script_sha256': sha256_file(__file__),
            'protocol_sha256': sha256_file('.planning/m08/crowd15-training-fit.md'),
            'freeze_manifest_sha256': sha256_file(args.freeze_manifest),
            'frozen_file_sha256': freeze['frozen_file_sha256'],
            'git_before': git_before['tracked_git_sha'],
            'git_after': git_after['tracked_git_sha'],
            'tracked_worktree_clean_before': git_before['tracked_worktree_clean'],
            'tracked_worktree_clean_after': git_after['tracked_worktree_clean'],
            'source_archive_sha256_after': archive_after,
            'source_member_sha256_after': after_table['provenance']['member_sha256'],
            'endpoint': None,
        },
        'caveat': 'Source-reported tracks are not a complete occupancy census. Coordinates and time use source declarations; independent calibration is unverified. No force, danger, harm, or calibrated probability interpretation.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as out:
        out.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output),
                      'input_sha256': result['input']['archive_sha256'],
                      'training_frames': result['training_frames_inclusive']}, indent=2))


if __name__ == '__main__':
    main()
