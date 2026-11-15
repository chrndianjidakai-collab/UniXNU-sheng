"""Allocate the native __DATA segment past the collection instead of inside it.

Two earlier attempts failed for the same underlying reason, and both are recorded
here so the wrong turns are not repeated:

  1. Pinning __DATA at the collection's original __DATA address ->
     "Native code would collide with collection data" (the retained kext code
     plus native __KLD already reaches that address).
  2. Placing it at align(code_end) -> "Native __DATA overlaps a retained
     segment" (that address falls inside a kept kext).
  3. hole('__DATA', size) -> "No room for 0x214000 bytes in __DATA: the largest
     free run is 0x1e8000 bytes". Growing the __DATA root does not help: the
     widest contiguous run is bounded by a retained kext segment sitting in the
     middle of the mapping, so a bigger root still yields the same 0x1e8000.

place_kernel moves a segment as one contiguous block
(self.data[at:at+span] = ...), so __DATA cannot be split across runs. It needs
its own space outside the collection's original layout.

fileset_layout already does exactly that for __KLDDATA and __BOOTDATA:

    segment = self.segment(name)
    address = self.allocate(segment['size'])
    self.reserve(name, address)
    self.roots[name] = dict(segment, va=address, fileoff=address - cache.base, ...)

Doing the same for __DATA gives it a run past every retained segment, and
registering the root keeps validate()'s "outside collection mappings" and root
overlap checks satisfied. Idempotent.

Usage:
    python patch-prelink-layout.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'kits/XnuPrelink/fileset_layout.py'
MARK = 'patch-prelink-layout: __DATA is allocated past the collection'

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
        # patch-prelink-layout: __DATA is allocated past the collection, the
        # same way __KLDDATA and __BOOTDATA below are. Pinning it at the original
        # va collides with the retained kext code + native __KLD; align(code_end)
        # lands inside a kept kext; hole() finds only 0x1e8000 contiguous bytes
        # because a retained segment splits the mapping, and growing the root
        # does not change that. place_kernel moves a segment as one block, so
        # __DATA needs its own run outside the original layout. Registering the
        # root keeps validate()'s coverage and overlap checks satisfied.
        data_segment = self.segment('__DATA')
        data_address = self.allocate(data_segment['size'])
        self.reserve('__DATA', data_address)
        self.roots['__DATA'] = dict(data_segment, va=data_address,
                                    fileoff=data_address - cache.base,
                                    filesize=data_segment['size'])"""


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
    print(f'{SCRIPT}: native __DATA is allocated past the collection and registered')
    return 0


if __name__ == '__main__':
    sys.exit(main())
