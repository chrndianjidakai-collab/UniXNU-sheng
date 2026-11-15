"""Fix dependency_closure() in the pinned XnuPrelink submodule.

The kernel now links and reaches prelink. emit_prelink.py is invoked with
--root !com.apple.driver.AppleSMC / !com.apple.driver.AppleOnboardSerial, where
`!` marks a dependency to exclude. dependency_closure() handles the `!` prefix
for the ROOT list only:

    excluded = {root[1:] for root in roots if root.startswith('!')}
    closure, pending = set(), [root for root in roots if not root.startswith('!')]

But excluded holds the names WITHOUT `!`, and pending is later extended with
every retained kext's OSBundleLibraries keys. Some kext in the iPadOS 27
kernelcache names such a dependency literally as `!com.apple.driver.AppleSMC`,
so that string enters pending, is not equal to any excluded entry, and is not a
CFBundleIdentifier -> `ValueError: Missing prelink dependency:
!com.apple.driver.AppleSMC`.

The fix normalizes every identifier popped from pending: strip a leading `!`,
then skip excluded names. This is idempotent.

Usage:
    python patch-prelink-closure.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'kits/XnuPrelink/fileset_emit.py'

OLD = """    while pending:
        identifier = pending.pop()
        if identifier in closure or identifier in excluded:
            continue
        if identifier not in entries:
            raise ValueError(f'Missing prelink dependency: {identifier}')
        closure.add(identifier)
        pending.extend(entries[identifier].get('OSBundleLibraries') or {})"""

NEW = """    while pending:
        identifier = pending.pop()
        # patch-prelink-closure.py: a `!`-prefixed dependency can also arrive
        # from a retained kext's OSBundleLibraries, not only from --root. The
        # excluded set stores bare names, so normalize before comparing.
        bare = identifier[1:] if identifier.startswith('!') else identifier
        if bare in closure or bare in excluded:
            continue
        if bare not in entries:
            raise ValueError(f'Missing prelink dependency: {identifier}')
        closure.add(bare)
        pending.extend(entries[bare].get('OSBundleLibraries') or {})"""

MARK = 'patch-prelink-closure.py: a `!`-prefixed dependency'


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
        raise SystemExit(f'{SCRIPT}: dependency_closure loop not found; upstream changed')

    target.write_text(text.replace(OLD, NEW, 1), encoding='utf-8')
    print(f'{SCRIPT}: dependency_closure normalizes !-prefixed dependencies')
    return 0


if __name__ == '__main__':
    sys.exit(main())
