"""Independent arithmetic audit of retained CROWD45/58 v2r1 outputs."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path('/Users/waichong/worktrees/crowd-m06-controlled')
PROTOCOL = REPO / '.planning/m06/controlled-head-lag-protocol-v2r1.md'
PRODUCER = REPO / 'work/m06-controlled/v2r1/controlled_head_lag_v2r1.py'
PRODUCER_OUT = REPO / 'work/m06-controlled/v2r1/lag_profiles.json'
ARCHIVE = Path('/Users/waichong/projects/crowd-crush-warning/.planning/milestone03-worktree-archive/crowd-m03-controlled-data/data/source/2022impulse_crowd_trajectories_txt.zip')
MEMBER = '2022impulse_crowd_trajectories_txt/1A11_240_n10_fs_d0_p+.txt'
EXPECTED_ARCHIVE = '1a197b0fd068f7b9bea3ac53118a31f7fc698f90167d871bb44b8de34b10030f'
EXPECTED_MEMBER = '3f5bfdaf2d9c4a07b22b489f8cef3c7d8b3fdc16c9d5a37a32e74ed8b6f627a1'
EXPECTED_PROTOCOL = '66f9715c8c67f19ad27dd1782d2e703f8739f14b6e219c853e18db3c81a55315'
EXPECTED_PRODUCER = '497e0eba205dc5eee077031d4a22f1625f14e2c988777eb99ec4aaf15f625940'
EXPECTED_OUTPUT = '940d1100945dd301be53bca022d954c6f769478d7978c3e545f9f443e949d31a'
LAGS = tuple(range(-10, 11))
ANCHORS = tuple(range(10, 91))
TOLERANCE = 1e-12


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    return sha(path.read_bytes())


def tracked_state() -> dict:
    head = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    status = subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain'], text=True)
    return {'head': head, 'tracked_clean': not status.strip()}


def parse_source(data: bytes):
    lines = data.decode('utf-8').splitlines()
    if len(lines) < 5 or not all(line.startswith('# ') for line in lines[:4]):
        raise ValueError('source metadata preamble mismatch')
    if lines[4] != '# id frame x/m y/m z/m markerID':
        raise ValueError('source header mismatch')
    if len(lines[5:]) != 1122:
        raise ValueError('source data row count mismatch')
    traces = {}
    for line in lines[5:]:
        fields = line.split()
        if len(fields) != 6:
            raise ValueError('source row field count mismatch')
        # Read only ID, frame, x, y, and marker. Field 5 (z) is not parsed.
        tid, frame, x, y, marker = int(fields[0]), int(fields[1]), float(fields[2]), float(fields[3]), int(fields[5])
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError('nonfinite source x/y')
        trace = traces.setdefault(tid, {'marker': marker, 'xy': {}})
        if trace['marker'] != marker or frame in trace['xy']:
            raise ValueError('duplicate frame or inconsistent role marker')
        trace['xy'][frame] = (x, y)
    frames = tuple(range(102))
    if len(traces) != 11 or any(tuple(sorted(t['xy'])) != frames for t in traces.values()):
        raise ValueError('trace count or frame continuity mismatch')
    bag_ids = [tid for tid, t in traces.items() if t['marker'] == 778]
    head_ids = sorted(tid for tid, t in traces.items() if t['marker'] != 778)
    if len(bag_ids) != 1 or len(head_ids) != 10:
        raise ValueError('role counts mismatch')
    # Match producer's documented sorted numeric trace-ID ordinal order.
    return traces[bag_ids[0]]['xy'], [traces[tid]['xy'] for tid in head_ids]


def steps(track):
    return [(track[t + 1][0] - track[t][0], track[t + 1][1] - track[t][1]) for t in range(101)]


def mag(v):
    return math.hypot(v[0], v[1])


def pearson(xs, ys):
    if len(xs) != len(ys) or len(xs) < 2:
        return {'value': None, 'reason': 'insufficient paired values'}
    mx, my = math.fsum(xs) / len(xs), math.fsum(ys) / len(ys)
    dx, dy = [x - mx for x in xs], [y - my for y in ys]
    xx, yy = math.fsum(x * x for x in dx), math.fsum(y * y for y in dy)
    if xx == 0 or yy == 0:
        return {'value': None, 'reason': 'constant input series'}
    return {'value': math.fsum(x * y for x, y in zip(dx, dy)) / math.sqrt(xx * yy), 'reason': None}


def profile(bag, head):
    rows = []
    for lag in LAGS:
        xs = [bag[t] for t in ANCHORS]
        ys = [head[t + lag] for t in ANCHORS]
        rows.append({'lag_frames': lag, 'n': len(ANCHORS), **pearson(xs, ys)})
    vals = [r for r in rows if r['value'] is not None]
    if not vals:
        return {'profile': rows, 'max_abs_lag_frames': None, 'ties': []}
    best = max(abs(r['value']) for r in vals)
    ties = [r['lag_frames'] for r in vals if abs(r['value']) == best]
    return {'profile': rows, 'max_abs_lag_frames': ties[0] if len(ties) == 1 else None, 'ties': ties}


def calculate(bag_track, heads):
    bag_steps = steps(bag_track)
    head_steps = [steps(h) for h in heads]
    common = [(math.fsum(h[t][0] for h in head_steps) / 10,
               math.fsum(h[t][1] for h in head_steps) / 10) for t in range(101)]
    bag_q = [mag(v) for v in bag_steps]
    raw_q = [[mag(v) for v in h] for h in head_steps]
    residual_q = [[mag((h[t][0] - common[t][0], h[t][1] - common[t][1])) for t in range(101)] for h in head_steps]
    common_q = [mag(v) for v in common]
    return {
        'common_mode_magnitude': profile(bag_q, common_q),
        'raw_head_magnitude': {f'head_{i:02d}': profile(bag_q, q) for i, q in enumerate(raw_q, 1)},
        'residual_head_magnitude': {f'head_{i:02d}': profile(bag_q, q) for i, q in enumerate(residual_q, 1)},
    }


def reject_constant(token):
    raise ValueError(f'nonfinite JSON constant: {token}')


def comparisons(recomputed, produced):
    entries = []
    for family in ('raw_head_magnitude', 'residual_head_magnitude'):
        for i in range(1, 11):
            name = f'head_{i:02d}'
            entries.append((f'{family}/{name}', recomputed[family][name], produced[family][name]))
    entries.append(('common_mode_magnitude', recomputed['common_mode_magnitude'], produced['common_mode_magnitude']))
    deltas = []
    failures = []
    tie_checks = 0
    unavailable = 0
    finite_values = 0
    boundary_extrema = []
    for label, expected, actual in entries:
        if len(expected['profile']) != 21 or len(actual.get('profile', [])) != 21:
            failures.append(label + ': profile length != 21')
            continue
        for e, a in zip(expected['profile'], actual['profile']):
            loc = f'{label}@{e["lag_frames"]:+d}'
            if e['lag_frames'] != a.get('lag_frames') or e['n'] != a.get('n') or e['n'] != 81:
                failures.append(loc + ': lag/count mismatch')
            if e['value'] is None:
                unavailable += 1
                if a.get('value') is not None or a.get('reason') != e['reason']:
                    failures.append(loc + ': unavailable state mismatch')
            else:
                finite_values += 1
                value = a.get('value')
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    failures.append(loc + ': output value is nonfinite or unavailable')
                else:
                    delta = abs(e['value'] - value)
                    deltas.append((delta, loc, e['value'], value))
                    if delta > TOLERANCE:
                        failures.append(loc + ': value delta exceeds tolerance')
                if a.get('reason') is not None:
                    failures.append(loc + ': finite value has unavailable reason')
        if expected['ties'] != actual.get('ties') or expected['max_abs_lag_frames'] != actual.get('max_abs_lag_frames'):
            failures.append(label + ': maximum/tie mismatch')
        tie_checks += 1
        if any(lag in (-10, 10) for lag in expected['ties']):
            boundary_extrema.append(label)
    max_delta = max(deltas, default=(0.0, None, None, None))
    return {'series_count': len(entries), 'profile_value_count': finite_values + unavailable,
            'finite_value_count': finite_values, 'unavailable_count': unavailable,
            'tie_summary_checks': tie_checks, 'max_abs_delta': max_delta[0],
            'max_delta_location': max_delta[1], 'recomputed_at_max_delta': max_delta[2],
            'producer_at_max_delta': max_delta[3], 'absolute_tolerance': TOLERANCE,
            'boundary_extrema_series': boundary_extrema, 'failures': failures}


def main():
    started = datetime.now(timezone.utc).isoformat()
    pre_state = tracked_state()
    protocol_before, producer_before, output_before = map(file_sha, (PROTOCOL, PRODUCER, PRODUCER_OUT))
    archive_bytes_before = ARCHIVE.read_bytes()
    archive_before = sha(archive_bytes_before)
    if archive_before != EXPECTED_ARCHIVE:
        raise ValueError('archive digest differs from frozen digest')
    with zipfile.ZipFile(ARCHIVE) as zf:
        data = zf.read(MEMBER)
    member_before = sha(data)
    if member_before != EXPECTED_MEMBER:
        raise ValueError('member digest differs from frozen digest')
    bag, heads = parse_source(data)
    independent = calculate(bag, heads)
    producer_obj = json.loads(PRODUCER_OUT.read_text(encoding='utf-8'), parse_constant=reject_constant)
    comparisons_result = comparisons(independent, producer_obj)
    # Check redundant lag-zero controls against the retained profiles.
    control_diffs = []
    families = [('raw_head_magnitude', 'raw_head'), ('residual_head_magnitude', 'residual_head')]
    for family, control_family in families:
        for i in range(1, 11):
            name = f'head_{i:02d}'
            control = producer_obj['lag_zero_controls'][control_family][name]
            lag_zero = producer_obj[family][name]['profile'][10]
            if control != lag_zero:
                control_diffs.append(f'{control_family}/{name}: redundant lag-zero mismatch')
    common_control = producer_obj['lag_zero_controls']['common_mode']
    if common_control != producer_obj['common_mode_magnitude']['profile'][10]:
        control_diffs.append('common_mode: redundant lag-zero mismatch')
    # Validate declared aggregate metadata against source and actual output.
    checks = producer_obj['input_checks']
    metadata_failures = []
    expected_checks = {'archive_sha256_before': EXPECTED_ARCHIVE, 'archive_sha256_after': EXPECTED_ARCHIVE,
                       'member_sha256': EXPECTED_MEMBER, 'member_bytes': len(data), 'metadata_lines': 4,
                       'data_rows': 1122, 'frame_range': [0, 101], 'trace_count': 11,
                       'bag_count': 1, 'head_count': 10, 'z_used': False,
                       'source_rows_written': False}
    for key, value in expected_checks.items():
        if checks.get(key) != value:
            metadata_failures.append(f'input_checks.{key} mismatch')
    if producer_obj.get('lags_frames') != list(LAGS) or producer_obj.get('anchor_support') != {'first_step_index': 10, 'last_step_index': 90, 'n_per_lag': 81}:
        metadata_failures.append('lag/support metadata mismatch')
    if producer_obj.get('positive_lag') != 'head later' or producer_obj.get('head_trace_count') != 10:
        metadata_failures.append('role/lag metadata mismatch')
    try:
        json.dumps(producer_obj, allow_nan=False)
    except (ValueError, TypeError) as exc:
        metadata_failures.append('producer output is not finite JSON: ' + str(exc))
    archive_after = sha(ARCHIVE.read_bytes())
    with zipfile.ZipFile(ARCHIVE) as zf:
        member_after = sha(zf.read(MEMBER))
    protocol_after, producer_after, output_after = map(file_sha, (PROTOCOL, PRODUCER, PRODUCER_OUT))
    post_state = tracked_state()
    if (protocol_before, producer_before, output_before) != (protocol_after, producer_after, output_after):
        metadata_failures.append('frozen protocol/script/output changed during audit')
    if protocol_before != EXPECTED_PROTOCOL or producer_before != EXPECTED_PRODUCER or output_before != EXPECTED_OUTPUT:
        metadata_failures.append('frozen protocol/script/output hash differs from manifest')
    if archive_after != archive_before or member_after != member_before:
        metadata_failures.append('source changed during audit')
    if pre_state != post_state:
        metadata_failures.append('producer tracked git state changed during audit')
    independent_obj = {'scope': 'independent numerical recomputation of retained run; not a new experiment',
                       'positive_lag': 'head later', 'anchor_support': {'first_step_index': 10, 'last_step_index': 90, 'n_per_lag': 81},
                       **independent}
    profile_path = HERE / 'independent-profiles.json'
    profile_path.write_text(json.dumps(independent_obj, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    ended = datetime.now(timezone.utc).isoformat()
    audit = {
        'audit_status': 'pass' if not (comparisons_result['failures'] or control_diffs or metadata_failures) else 'fail',
        'audit_command': 'python3 work/m06-calibration-review/audit.py',
        'audit_started_utc': started, 'audit_ended_utc': ended,
        'audit_script_sha256': file_sha(Path(__file__)),
        'source_archive_sha256_before_after': [archive_before, archive_after],
        'source_member': MEMBER, 'source_member_sha256_before_after': [member_before, member_after],
        'source_member_bytes': len(data), 'source_rows': len(data.decode('utf-8').splitlines()) - 5,
        'source_roles': {'bag_count': 1, 'head_count': 10, 'frames_per_trace': 102,
                         'head_ordinal_order': 'ascending numeric source trace ID, matching producer selection; IDs omitted'},
        'producer_tracked_state_before_after': [pre_state, post_state],
        'frozen_protocol_sha256_before_after': [protocol_before, protocol_after],
        'frozen_producer_script_sha256_before_after': [producer_before, producer_after],
        'producer_profile_sha256_before_after': [output_before, output_after],
        'profile_comparison': comparisons_result,
        'lag_zero_control_failures': control_diffs,
        'metadata_failures': metadata_failures,
        'independent_profiles_sha256': file_sha(profile_path),
        'limitations': ['single previously viewed controlled trial', 'common vector subtraction also removes real shared motion and is not a background reference',
                        'native frame index only; no physical clock, force, arrival, propagation, mechanism, or warning inference']
    }
    audit_path = HERE / 'audit.json'
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'audit_status': audit['audit_status'], 'audit_sha256': file_sha(audit_path),
                      'profiles_sha256': file_sha(profile_path), 'max_abs_delta': comparisons_result['max_abs_delta'],
                      'delta_location': comparisons_result['max_delta_location'],
                      'value_count': comparisons_result['profile_value_count'],
                      'failures': comparisons_result['failures'] + control_diffs + metadata_failures}, sort_keys=True))
    if audit['audit_status'] != 'pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
