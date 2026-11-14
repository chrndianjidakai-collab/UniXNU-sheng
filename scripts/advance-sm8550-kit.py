"""Advance the pinned sm8550-common kit so BluetoothProbe.cpp can compile.

`package/BluetoothProbe.cpp` (device repository) includes

    #include "Sm8550GeniUart.h"

and calls `sm8550_geni_uart14_vote()` / `sm8550_geni_uart14_source()`.
`scripts/build-gop-legacy-display-27.py` compiles it with

    -I <tree>/kits/Sm8550Platform

`components.toml` pins Sm8550Platform to

    https://github.com/UniXNU/UniXNU-sm8550-common.git  a9f45dc60c03...

whose `kits/Sm8550Platform/` holds only the GPU sources:

    ShengGmu.c/.h  ShengGmuCommandDb.c/.h  ShengGmuVotes.h  ShengGpuSmmu.c/.h

The GENI UART files arrive one commit later, 009512d62acc:

    added kits/Sm8550Platform/Sm8550Gcc.c        +50
    added kits/Sm8550Platform/Sm8550GeniUart.c   +36
    added kits/Sm8550Platform/Sm8550GeniUart.h   +28
    added kits/Sm8550Platform/Sm8550QupDma.c     +73
    added kits/Sm8550Platform/Sm8550QupDma.h     +31

so the iPadOS 27 build dies with

    fatal error: 'Sm8550GeniUart.h' file not found

This script rewrites the Sm8550Platform `revision` in a checkout of the UniXNU
repository to 009512d62acc. The step is purely additive upstream (218 added
lines, nothing removed or changed), so the kit keeps every file the old pin
had.

Usage:
    python advance-sm8550-kit.py <UniXNU checkout>
"""
import pathlib
import re
import sys

COMPONENTS = 'components.toml'
LOCK = 'unixnu.lock'
FEEDS = 'feeds.toml'
OLD = 'a9f45dc60c035084b95463781538380f4c3606c9'
NEW = '009512d62acc907189648aa51f2066d85940e97d'
MARK = '# sm8550-common needs 009512d6 for Sm8550GeniUart.h'


def patch_components(root):
    target = root / COMPONENTS
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text()

    block = re.search(r'\[\[component\]\]\s*\nid = "Sm8550Platform".*?(?=\[\[component\]\]|\Z)',
                      text, re.S)
    if not block:
        raise SystemExit(f'{COMPONENTS}: no [[component]] id = "Sm8550Platform" block')

    section = block.group(0)
    if NEW in section:
        print(f'{COMPONENTS}: Sm8550Platform already at {NEW[:8]}')
        return
    if OLD not in section:
        raise SystemExit(f'{COMPONENTS}: Sm8550Platform does not pin {OLD[:8]}; upstream moved')

    updated = section.replace(f'revision = "{OLD}"',
                              f'revision = "{NEW}"  {MARK}', 1)
    target.write_text(text[:block.start()] + updated + text[block.end():])
    print(f'{COMPONENTS}: Sm8550Platform revision {OLD[:8]} -> {NEW[:8]}')


def patch_lock(root):
    """The lock records resolved git sources. schema_version 2 prefers the
    revision in components.toml, but a stale lock entry is a second thing that
    can disagree, so rewrite it too."""
    target = root / LOCK
    if not target.is_file():
        print(f'{LOCK}: absent, nothing to do')
        return
    text = target.read_text()
    if f'commit = "{OLD}"' not in text:
        print(f'{LOCK}: no {OLD[:8]} entry')
        return
    target.write_text(text.replace(f'commit = "{OLD}"', f'commit = "{NEW}"'))
    print(f'{LOCK}: [source."sm8550"] {OLD[:8]} -> {NEW[:8]}')


def patch_feeds(root, device):
    """feeds.toml lives in the device repository and declares the sm8550 SOC
    source. build-gop-legacy-display-27.py reaches kits/Sm8550Platform through
    that SOC checkout, so its commit has to move with the component pin."""
    target = device / FEEDS
    if not target.is_file():
        print(f'{FEEDS}: absent in {device}, nothing to do')
        return
    text = target.read_text()
    if f'commit = "{OLD}"' not in text:
        print(f'{FEEDS}: no {OLD[:8]} entry')
        return
    target.write_text(text.replace(f'commit = "{OLD}"', f'commit = "{NEW}"'))
    print(f'{FEEDS}: [source] sm8550 {OLD[:8]} -> {NEW[:8]}')


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    # default: the device repository is the parent of the UniXNU checkout
    device = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else root.parent
    patch_components(root)
    patch_lock(root)
    patch_feeds(root, device)
    print('  adds Sm8550GeniUart.c/.h, Sm8550Gcc.c, Sm8550QupDma.c/.h (pure additions)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
