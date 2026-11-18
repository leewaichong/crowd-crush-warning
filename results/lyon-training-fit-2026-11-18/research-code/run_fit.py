"""Run one frozen CROWD15 fit command with a finite timeout and captured logs."""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', required=True, type=Path)
    parser.add_argument('--stdout', required=True, type=Path)
    parser.add_argument('--stderr', required=True, type=Path)
    parser.add_argument('--timeout-seconds', required=True, type=int)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == '--' else args.command
    if not command:
        raise ValueError('fit command is required')
    for path in (args.record, args.stdout, args.stderr):
        if path.exists():
            raise FileExistsError(f'refusing to overwrite run artifact: {path}')
    for path in (args.record.parent, args.stdout.parent, args.stderr.parent):
        path.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc)
    timed_out = False
    returncode = None
    try:
        with args.stdout.open('x') as stdout, args.stderr.open('x') as stderr:
            completed = subprocess.run(command, stdout=stdout, stderr=stderr,
                                       timeout=args.timeout_seconds, check=False)
            returncode = completed.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
    ended = datetime.now(timezone.utc)
    record = {
        'command_argv': command,
        'timeout_seconds': args.timeout_seconds,
        'started_at_utc': started.isoformat(),
        'ended_at_utc': ended.isoformat(),
        'timed_out': timed_out,
        'returncode': returncode,
        'stdout_path': str(args.stdout),
        'stderr_path': str(args.stderr),
    }
    with args.record.open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(record, indent=2, sort_keys=True))
    if timed_out:
        return 124
    return returncode if returncode is not None else 1


if __name__ == '__main__':
    sys.exit(main())
