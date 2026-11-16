"""Raise the cargo build bound for the Adreno Metal bridge.

Older UniXNU checkouts bound `cargo build` for the Rust standard library
(`-Z build-std`) at 1800 s, which a cold hosted-runner build exceeded; the run
died with subprocess.TimeoutExpired and reported only "returned non-zero exit
status 1".

Upstream later raised the bound itself, so this script now accepts three
states and only fails when the source is neither patched, nor already raised,
nor recognisably the old shape:

    already patched by us      -> "already patched"
    upstream raised it         -> "upstream already raised the bound"  (no change)
    old 1800 s shape found     -> raise it
    anything else              -> fail, so an upstream rewrite is noticed

Idempotent.

Usage:
    python patch-metal-bridge-timeout.py <UniXNU checkout>
"""
import pathlib
import re
import sys

SCRIPT = 'scripts/build-adreno-metal-bridge.py'
MARK = 'patch-metal-bridge-timeout'
BOUND = 5400


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        print(f'{SCRIPT}: not present in this checkout; nothing to do')
        return 0
    text = target.read_text(encoding='utf-8')

    if MARK in text:
        print(f'{SCRIPT}: already patched')
        return 0

    # The bound appears on the subprocess.run that invokes cargo. Take whatever
    # timeout it carries and only replace it when it is below BOUND, so an
    # upstream value that is already large enough is left alone.
    matches = list(re.finditer(r'timeout=(\d+)\)', text))
    cargo = [m for m in matches
             if 'cargo' in text[max(0, m.start() - 600):m.start()]
             and 'build' in text[max(0, m.start() - 600):m.start()]]
    if not cargo:
        raise SystemExit(f'{SCRIPT}: no cargo subprocess.run timeout; upstream changed')

    current = int(cargo[0].group(1))
    if current >= BOUND:
        print(f'{SCRIPT}: upstream already raised the bound to {current}s; no change')
        return 0

    at = cargo[0].start(1)
    end = cargo[0].end(1)
    text = text[:at] + str(BOUND) + text[end:]
    # Record why, next to the value.
    line_start = text.rfind('\n', 0, at) + 1
    text = (text[:line_start]
            + f'    # {MARK}: {BOUND} s. A cold hosted-runner build of the Rust '
              f'standard library exceeded the old {current} s; the bound is a '
              f'safety net, not a budget.\n'
            + text[line_start:])
    target.write_text(text, encoding='utf-8')
    print(f'{SCRIPT}: cargo timeout {current}s -> {BOUND}s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
