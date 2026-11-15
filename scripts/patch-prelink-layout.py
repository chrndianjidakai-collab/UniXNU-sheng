"""Place the native __DATA segment into a free run of the collection's __DATA.

fileset_layout.Layout.__init__ pins the native __DATA at the ORIGINAL address of
the collection's __DATA and then refuses to continue when the retained kext code
plus the native __KLD segment has already run past it:

    code_end = self.end('__KLD')
    if code_end > self.roots['__DATA']['va']:
        raise ValueError('Native code would collide with collection data')
    self.reserve('__DATA', self.roots['__DATA']['va'])

With the iPadOS 27 prelink roots (the 44 the board lists: the profile's 31 plus
the USB device and host stacks) the retained kext code is large enough to reach
that address, so the pinned __DATA cannot hold.

Every native segment is placed through Layout.placements and read back through
translate(); the fixups are rewritten, so the address may move. __LINKINFO,
__LINKEDIT, __PRELINK_INFO, __KLDDATA and __BOOTDATA are already allocated
dynamically. __DATA is the last segment still pinned, and that pinning is what
the collision trips on.

Fix: reserve __DATA through the existing hole() walker, which returns the first
free run in the __DATA mapping that is wide enough and, when none fits, already
reports the largest free run. Placing it at align(code_end) instead was wrong:
that address can sit inside a retained kext segment, which validate() then
rejects with "Native __DATA overlaps a retained segment".

Idempotent.

Usage:
    python patch-prelink-layout.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'kits/XnuPrelink/fileset_layout.py'
MARK = 'patch-prelink-layout: __DATA goes into a free run'

OLD = """        code_end = self.end('__KLD')
        # The old kernel boot segment and prelink XML are replaceable, provided
        # no retained kext uses them. Move XML into its own mapping below.
        if code_end > self.roots['__DATA']['va']:
            raise ValueError('Native code would collide with collection data')
        self.roots.pop('__TEXT_BOOT_EXEC', None)
        code['size'] = code['filesize'] = code_end - code['va']
        self.reserve('__DATA', self.roots['__DATA']['va'])"""

NEW = """        code_end = self.end('__KLD')
        # The old kernel boot segment and prelink XML are replaceable, provided
        # no retained kext uses them. Move XML into its own mapping below.
        self.roots.pop('__TEXT_BOOT_EXEC', None)
        code['size'] = code['filesize'] = code_end - code['va']
        # patch-prelink-layout: __DATA goes into a free run of the collection's
        # own __DATA mapping instead of its original va. Pinning it there made
        # the retained kext code + native __KLD collide with it. Placing it at
        # align(code_end) is also wrong: that address can fall inside a retained
        # kext segment. hole() walks the retained segments and returns the first
        # run wide enough, and reports the largest free run when none fits.
        self.reserve('__DATA', self.hole('__DATA', self.segment('__DATA')['size']))"""


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
        raise SystemExit(f'{SCRIPT}: Layout.__init__ block not found; upstream changed')

    target.write_text(text.replace(OLD, NEW, 1), encoding='utf-8')
    print(f'{SCRIPT}: native __DATA is placed into a free run of its mapping')
    return 0


if __name__ == '__main__':
    sys.exit(main())
