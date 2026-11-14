"""Advance the pinned sm8550-common kit so the iPadOS 27 board sources compile.

`package/BluetoothProbe.cpp` and `build-gop-legacy-display-27.py` compile against
`<tree>/kits/Sm8550Platform`, which the sm8550 SOC checkout provides. That kit
grew over several commits, and the upstream pin in this repository predates all
of them, so the build stops at whichever source it needs first:

  a9f45dc6  upstream pin — GPU only
            ShengGmu.c/.h  ShengGmuCommandDb.c/.h  ShengGmuVotes.h  ShengGpuSmmu.c/.h
            -> BluetoothProbe.cpp:17 fatal error: 'Sm8550GeniUart.h' file not found

  009512d6  + GENI UART and QUP DMA (Bluetooth)
            Sm8550Gcc.c  Sm8550GeniUart.c/.h  Sm8550QupDma.c/.h
            -> clang: error: no such file or directory: '.../Sm8550VideoCc.c'

  f04fd8b1  + video clock controller and apps SMMU (Video)
            Sm8550VideoCc.c/.h  Sm8550AppsSmmu.c/.h
            and a small fix to Sm8550QupDma.c (+17 -6)

f04fd8b1 is the revision whose kit carries every file the iPadOS 27 recipes
reference, so this helper advances the pin to it.

The pin lives in three places and all of them must agree:
  UniXNU/components.toml   [[component]] id = "Sm8550Platform"   revision
  UniXNU/unixnu.lock       [source."sm8550"]                     commit  (may be absent)
  device/feeds.toml        [[source]] name = "sm8550"            commit

Usage:
    python advance-sm8550-kit.py <UniXNU checkout> [<device checkout>]
"""
import pathlib
import re
import sys

COMPONENTS = 'components.toml'
LOCK = 'unixnu.lock'
FEEDS = 'feeds.toml'

# Every revision this helper has advanced away from, oldest first. A checkout may
# be on the upstream pin or on a value a previous run already wrote.
SUPERSEDED = [
    'a9f45dc60c035084b95463781538380f4c3606c9',   # upstream: GPU files only
    '009512d62acc907189648aa51f2066d85940e97d',   # + GENI UART; still no video CC / apps SMMU
]
NEW = 'f04fd8b13e929bf5dd4fea0f40fa7f971a02de0d'
MARK = '# sm8550-common needs f04fd8b1 for the GENI UART, video CC and apps SMMU sources'


def patch_components(root):
    target = root / COMPONENTS
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text(encoding='utf-8')

    block = re.search(r'\[\[component\]\]\s*\nid = "Sm8550Platform".*?(?=\[\[component\]\]|\Z)',
                      text, re.S)
    if not block:
        raise SystemExit(f'{COMPONENTS}: no [[component]] id = "Sm8550Platform" block')

    section = block.group(0)
    if NEW in section:
        print(f'{COMPONENTS}: Sm8550Platform already at {NEW[:8]}')
        return

    previous = next((old for old in SUPERSEDED if old in section), None)
    if previous is None:
        raise SystemExit(f'{COMPONENTS}: Sm8550Platform pins none of '
                         f'{", ".join(o[:8] for o in SUPERSEDED)}; upstream moved')

    # Replace the whole revision line so any earlier marker comment is dropped.
    updated = re.sub(r'revision = "[0-9a-f]{40}".*',
                     f'revision = "{NEW}"  {MARK}',
                     section, count=1)
    target.write_text(text[:block.start()] + updated + text[block.end():], encoding='utf-8')
    print(f'{COMPONENTS}: Sm8550Platform revision {previous[:8]} -> {NEW[:8]}')


def _rewrite(target, label):
    if not target.is_file():
        print(f'{target.name}: absent, nothing to do')
        return
    text = target.read_text(encoding='utf-8')
    if f'commit = "{NEW}"' in text:
        print(f'{target.name}: already at {NEW[:8]}')
        return
    for old in SUPERSEDED:
        if f'commit = "{old}"' in text:
            target.write_text(text.replace(f'commit = "{old}"', f'commit = "{NEW}"'), encoding='utf-8')
            print(f'{target.name}: {label} {old[:8]} -> {NEW[:8]}')
            return
    print(f'{target.name}: no superseded sm8550 entry')


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    # default: the device repository is the parent of the UniXNU checkout
    device = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else root.parent
    patch_components(root)
    # unixnu.lock only exists after "unixnu fetch"; absent in a fresh checkout
    _rewrite(root / LOCK, '[source."sm8550"]')
    _rewrite(device / FEEDS, '[source] sm8550')
    print('  kit now carries ShengGmu*, ShengGpuSmmu*, Sm8550Gcc.c, Sm8550GeniUart.*,'
          ' Sm8550QupDma.*, Sm8550VideoCc.*, Sm8550AppsSmmu.*')
    return 0


if __name__ == '__main__':
    sys.exit(main())
