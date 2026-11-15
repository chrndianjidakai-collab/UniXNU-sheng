"""Give the native __DATA segment room inside the collection's __DATA mapping.

fileset_layout.Layout pins the native __DATA at the collection's original __DATA
address and refuses to continue when the retained kext code plus the native
__KLD segment has run past it ("Native code would collide with collection
data"). Placing it at align(code_end) is also wrong (that address can sit inside
a retained kext). Using hole() on the __DATA mapping is correct but the iPadOS 27
roots leave too little contiguous room:

    No room for 0x214000 bytes in __DATA: the largest free run is 0x1e8000 bytes

2.08 MB is needed and 1.91 MB is the widest free run: a 0x2c000 (176 KiB)
shortfall. __DATA is moved as one contiguous block by place_kernel
(self.data[at:at+span] = ...), so it cannot be split.

Fix: try hole('__DATA', size); when that fails, extend the __DATA root's own
mapping as far as the next root allows and try again. validate() only rejects
root overlaps, so growing __DATA into unclaimed space below the next root is
legal, and the extension is bounded by that neighbour. When even the extended
mapping cannot hold it, print every root so the shortfall is visible instead of
guesswork. Idempotent.

Usage:
    python patch-prelink-layout.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'kits/XnuPrelink/fileset_layout.py'
MARK = 'patch-prelink-layout: place __DATA into a free run of its mapping'

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
        # patch-prelink-layout: place __DATA into a free run of its mapping.
        # Pinning it at the original va let the retained kext code + native
        # __KLD collide with it; align(code_end) can land inside a retained kext.
        data = self.roots['__DATA']
        data_size = self.segment('__DATA')['size']
        try:
            self.reserve('__DATA', self.hole('__DATA', data_size))
        except ValueError:
            # The mapping is too small for one contiguous run. Grow __DATA up to
            # the next root, which validate()'s overlap rule allows, then retry.
            following = [s['va'] for s in self.roots.values()
                         if s['size'] and s['va'] >= data['va'] + data['size']]
            limit = min(following) if following else data['va'] + data['size'] + data_size
            grow = max(data_size, limit - data['va'])
            print(f'prelink layout: growing __DATA from {data["size"]:#x} to {grow:#x} '
                  f'(limit {limit:#x}) for a {data_size:#x} byte segment', flush=True)
            data['size'] = grow
            try:
                self.reserve('__DATA', self.hole('__DATA', data_size))
            except ValueError as error:
                print('prelink layout: __DATA still does not fit, roots:', flush=True)
                for s in sorted(self.roots.values(), key=lambda s: s['va']):
                    if s['size']:
                        print(f'  {s["name"]:<18} va={s["va"]:#014x} size={s["size"]:#012x} '
                              f'end={s["va"] + s["size"]:#014x}', flush=True)
                for name, address in sorted(self.placements.items()):
                    print(f'  placed {name:<14} va={address:#014x} size={self.span(name):#012x}', flush=True)
                raise error"""


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
    print(f'{SCRIPT}: __DATA is placed in a run, growing its mapping when needed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
