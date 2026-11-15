"""Fix dependency_closure() in the pinned XnuPrelink submodule.

UniXNU@82b847c pins XnuPrelink@b1888c12456c46a2226d63c794465dfcee08d465. That
revision's dependency_closure() has NO handling for `!`-prefixed exclusions:

    closure, pending = set(), list(roots)
    while pending:
        identifier = pending.pop()
        if identifier in closure:
            continue
        if identifier not in entries:
            raise ValueError(f'Missing prelink dependency: {identifier}')
        ...

emit_prelink.py is invoked with `--root !com.apple.driver.AppleSMC` and
`--root !com.apple.driver.AppleOnboardSerial` (the `!` means "leave this
dependency out"). In this revision those strings are pushed straight into
pending and fail with
`ValueError: Missing prelink dependency: !com.apple.driver.AppleSMC`.

Fix: skip `!`-prefixed identifiers in the loop. Later revisions of the upstream
file implement the same intent with an `excluded` set; here the minimal correct
change is one guard. It also covers `!`-prefixed keys reached through a kext's
OSBundleLibraries. Idempotent.

Usage:
    python patch-prelink-closure.py <UniXNU checkout>
"""
import pathlib
import re
import sys

SCRIPT = 'kits/XnuPrelink/fileset_emit.py'
MARK = 'patch-prelink-closure: skip excluded roots'


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text(encoding='utf-8')

    if MARK in text:
        print(f'{SCRIPT}: already patched')
        return 0

    # Insert the guard right after `identifier = pending.pop()` inside
    # dependency_closure only. Match by the loop's own anchors so a differing
    # surrounding function body does not break the patch.
    pattern = re.compile(
        r'(    while pending:\n'
        r'        identifier = pending\.pop\(\)\n)'
        r'(        if identifier in closure(?:\s+or\s+identifier in excluded)?:\n'
        r'            continue\n)')
    m = pattern.search(text)
    if not m:
        dm = re.search(r'def dependency_closure.*?(?=\ndef )', text, re.S)
        snippet = dm.group(0)[:900] if dm else text[:900]
        raise SystemExit(f'{SCRIPT}: dependency_closure loop not found; '
                        f'actual text:\n{snippet}')

    guard = ('        # patch-prelink-closure: skip excluded roots (also reachable\n'
             '        # through a kext OSBundleLibraries key)\n'
             "        if identifier.startswith('!'):\n"
             '            continue\n')
    replacement = m.group(1) + guard + m.group(2)
    target.write_text(text[:m.start()] + replacement + text[m.end():], encoding='utf-8')
    print(f'{SCRIPT}: dependency_closure skips !-prefixed roots')
    return 0


if __name__ == '__main__':
    sys.exit(main())
