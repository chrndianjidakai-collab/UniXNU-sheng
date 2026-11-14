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
OLD = 'a9f45dc60c035084b95463781538380f4c3606c9'
NEW = '009512d62acc907189648aa51f2066d85940e97d'
MARK = '# sm8550-common needs 009512d6 for Sm8550GeniUart.h'


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / COMPONENTS
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text()

    # Find the Sm8550Platform block and its revision line.
    block = re.search(r'\[\[component\]\]\s*\nid = "Sm8550Platform".*?(?=\[\[component\]\]|\Z)',
                      text, re.S)
    if not block:
        raise SystemExit(f'{COMPONENTS}: no [[component]] id = "Sm8550Platform" block')

    section = block.group(0)
    if NEW in section:
        print(f'{COMPONENTS}: Sm8550Platform already at {NEW[:8]}')
        return 0
    if OLD not in section:
        raise SystemExit(f'{COMPONENTS}: Sm8550Platform does not pin {OLD[:8]}; upstream moved')

    updated = section.replace(
        f'revision = "{OLD}"',
        f'revision = "{NEW}"  {MARK}',
        1,
    )
    text = text[:block.start()] + updated + text[block.end():]
    target.write_text(text)
    print(f'{COMPONENTS}: Sm8550Platform revision {OLD[:8]} -> {NEW[:8]}')
    print('  adds Sm8550GeniUart.c/.h, Sm8550Gcc.c, Sm8550QupDma.c/.h (pure additions)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
