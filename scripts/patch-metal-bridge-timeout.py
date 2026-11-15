"""Raise the cargo timeout in build-adreno-metal-bridge.py.

The GPU Metal bridge is built by cargo with `-Z build-std=std,panic_unwind` for
--target ios27, which compiles the Rust standard library from source on every
cold cache. The script hard-codes

    subprocess.run(cargo + [...], timeout=1800)

30 minutes is not enough on a hosted macOS runner for the first build, so the
run dies with:

    subprocess.TimeoutExpired: Command '['cargo', '+1.98.0', '-Z',
      'build-std=std,panic_unwind', 'build', '--release', ...]
      timed out after 1800 seconds

and that surfaces as "build-adreno-metal-bridge.py returned non-zero exit
status 1", far from the real cause. The wait is a safety bound, not a budget:
the build is deterministic and a longer bound only costs time when the build is
genuinely stuck. Raise it to 5400 seconds (90 minutes), which covers a cold
build-std run with margin. Idempotent.

Usage:
    python patch-metal-bridge-timeout.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'scripts/build-adreno-metal-bridge.py'
MARK = 'patch-metal-bridge-timeout: 5400'

OLD = """    result = subprocess.run(cargo + ['build', '--release', '--manifest-path', manifest, '--target', triple,
                             '--target-dir', target_dir], env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1800)"""

NEW = """    # patch-metal-bridge-timeout: 5400. --target ios27 passes
    # -Z build-std=std,panic_unwind, so the Rust standard library is compiled
    # from source on a cold cache; 1800 s was not enough on a hosted macOS
    # runner and the run died with subprocess.TimeoutExpired, which surfaced
    # only as "returned non-zero exit status 1". This is a safety bound, not a
    # budget: a longer bound costs time only when the build is truly stuck.
    result = subprocess.run(cargo + ['build', '--release', '--manifest-path', manifest, '--target', triple,
                             '--target-dir', target_dir], env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=5400)"""


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text(encoding='utf-8')

    if MARK in text:
        print(f'{SCRIPT}: already patched')
        return 0
    if OLD not in text:
        raise SystemExit(f'{SCRIPT}: cargo subprocess.run not found; upstream changed')

    target.write_text(text.replace(OLD, NEW, 1), encoding='utf-8')
    print(f'{SCRIPT}: the cargo build bound is 5400 s instead of 1800 s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
