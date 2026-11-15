"""Place the native __DATA segment after __KLD and report the layout.

fileset_layout.Layout.__init__ pins the native __DATA segment at the ORIGINAL
address of the collection's __DATA and then refuses to continue when the
retained kext code plus the native __KLD segment has already run past it:

    code_end = self.end('__KLD')
    if code_end > self.roots['__DATA']['va']:
        raise ValueError('Native code would collide with collection data')
    self.reserve('__DATA', self.roots['__DATA']['va'])

With the iPadOS 27 prelink roots (the 44 the board lists: the profile's 31 plus
the USB device and host stacks) the retained kext code is large enough to reach
that address, so the pinned __DATA cannot hold.

Every native segment is placed through Layout.placements and read back through
translate(); relocate/fixup rewrites the pointers, and __LINKINFO, __LINKEDIT,
__PRELINK_INFO, __KLDDATA and __BOOTDATA are already allocated dynamically after
the retained mapping. __DATA is the last segment still pinned, so this patch
allocates it after __KLD like the others, keeps it inside the collection's
__DATA mapping when that mapping has room, and prints the full segment table
plus the overrun when it still does not fit.

Idempotent.

Usage:
    python patch-prelink-layout.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'kits/XnuPrelink/fileset_layout.py'
MARK = 'patch-prelink-layout: __DATA after __KLD'

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
        # patch-prelink-layout: __DATA after __KLD, inside the collection's own
        # __DATA mapping when it has room. Pinning __DATA at its original va made
        # the retained kext code + native __KLD collide with it. Every native
        # segment is placed through self.placements and read back with
        # translate(), and the fixups are rewritten, so the address may move.
        data_root = self.roots['__DATA']
        data_size = self.segment('__DATA')['size']
        data_at = align(code_end)
        if data_at + data_size > data_root['va'] + data_root['size'] or data_at < data_root['va']:
            print('prelink layout: __DATA does not fit behind __KLD, reporting:', flush=True)
            for name, address in sorted(self.placements.items()):
                print(f'  {name:<18} va={address:#014x} size={self.span(name):#012x} '
                      f'end={self.placements[name] + self.span(name):#014x}', flush=True)
            print(f'  __DATA mapping      va={data_root["va"]:#014x} size={data_root["size"]:#012x} '
                  f'end={data_root["va"] + data_root["size"]:#014x}', flush=True)
            print(f'  __DATA wanted at    {data_at:#014x} size={data_size:#012x} '
                  f'end={data_at + data_size:#014x}', flush=True)
            print(f'  __KLD end / overrun {code_end:#014x} / {code_end - data_root["va"]:#x} bytes', flush=True)
            raise ValueError('Native code would collide with collection data')
        self.reserve('__DATA', data_at)"""


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
    print(f'{SCRIPT}: native __DATA is placed after __KLD inside the collection mapping')
    return 0


if __name__ == '__main__':
    sys.exit(main())
