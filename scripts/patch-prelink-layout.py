"""Allocate the native __DATA segment past the collection instead of inside it.

The wrong turns are recorded here so they are not repeated:

  1. Pinning __DATA at the collection's original __DATA address ->
     "Native code would collide with collection data" (the retained kext code
     plus native __KLD already reaches that address).
  2. Placing it at align(code_end) -> "Native __DATA overlaps a retained
     segment" (that address falls inside a kept kext).
  3. hole('__DATA', size) -> "No room for 0x214000 bytes in __DATA: the largest
     free run is 0x1e8000 bytes". Growing the __DATA root does not help: the
     widest contiguous run is bounded by a retained kext segment sitting in the
     middle of the mapping.
  4. Allocating __DATA before the __LINKINFO/__LINKEDIT phase -> validate()
     raises "Root mappings overlap": the __LINKEDIT root spans from the
     original __LINKEDIT va to the latest cursor (link['size'] = cursor -
     link['fileoff']), so it swallowed the freshly allocated __DATA root.
     Every segment moved out of the collection must be allocated AFTER that
     phase, exactly like __PRELINK_INFO, __KLDDATA and __BOOTDATA are.

place_kernel moves a segment as one contiguous block
(self.data[at:at+span] = ...), so __DATA cannot be split across runs. It needs
its own space outside the collection's original layout, and its root must be
allocated after the __LINKEDIT root's span is finalized.

fileset_layout already does exactly that for __KLDDATA and __BOOTDATA:

    segment = self.segment(name)
    address = self.allocate(segment['size'])
    self.reserve(name, address)
    self.roots[name] = dict(segment, va=address, fileoff=address - cache.base, ...)

Doing the same for __DATA — after the __KLDDATA/__BOOTDATA loop — gives it a
run past every retained segment and keeps the allocated roots ordered
(LINKEDIT -> PRELINK_INFO -> KLD -> BOOT -> DATA), which is what validate()
requires. Idempotent.

Usage:
    python patch-prelink-layout.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'kits/XnuPrelink/fileset_layout.py'
MARK = "data_address = self.allocate(data_segment['size'])"

OLD_COLLIDE = """        code_end = self.end('__KLD')
        # The old kernel boot segment and prelink XML are replaceable, provided
        # no retained kext uses them. Move XML into its own mapping below.
        if code_end > self.roots['__DATA']['va']:
            raise ValueError('Native code would collide with collection data')
        self.roots.pop('__TEXT_BOOT_EXEC', None)
        code['size'] = code['filesize'] = code_end - code['va']
        self.reserve('__DATA', self.roots['__DATA']['va'])"""

NEW_COLLIDE = """        code_end = self.end('__KLD')
        # The old kernel boot segment and prelink XML are replaceable, provided
        # no retained kext uses them. Move XML into its own mapping below.
        # patch-prelink-layout: the collection's __DATA va is no longer a bound
        # native code can stay below — retained kext code plus native __KLD
        # already reaches past it — and hole() finds only 0x1e8000 contiguous
        # bytes because a retained segment splits the mapping. __DATA is
        # instead allocated past the collection, after the __KLDDATA and
        # __BOOTDATA roots (see below), so the collide check and the old-va
        # reserve are dropped here.
        self.roots.pop('__TEXT_BOOT_EXEC', None)
        code['size'] = code['filesize'] = code_end - code['va']"""

OLD_ALLOC = """        for name in ('__KLDDATA', '__BOOTDATA'):
            segment = self.segment(name)
            address = self.allocate(segment['size'])
            self.reserve(name, address)
            self.roots[name] = dict(segment, va=address, fileoff=address-cache.base,
                                    filesize=segment['size'])
        # Zero-sized markers have distinct semantics even when their old"""

NEW_ALLOC = """        for name in ('__KLDDATA', '__BOOTDATA'):
            segment = self.segment(name)
            address = self.allocate(segment['size'])
            self.reserve(name, address)
            self.roots[name] = dict(segment, va=address, fileoff=address-cache.base,
                                    filesize=segment['size'])
        # patch-prelink-layout: __DATA is allocated here, after the __KLDDATA
        # and __BOOTDATA roots. Allocating it earlier — before the __LINKINFO /
        # __LINKEDIT phase — put the __DATA root inside the __LINKEDIT root's
        # span: that root runs from the original __LINKEDIT va to the latest
        # cursor, so it swallowed the freshly allocated __DATA and validate()
        # raised 'Root mappings overlap'. Allocating after __BOOTDATA keeps
        # every allocated root ordered: LINKEDIT -> PRELINK_INFO -> KLD -> BOOT
        # -> DATA, each exactly adjacent, no overlap.
        data_segment = self.segment('__DATA')
        data_address = self.allocate(data_segment['size'])
        self.reserve('__DATA', data_address)
        self.roots['__DATA'] = dict(data_segment, va=data_address,
                                    fileoff=data_address - cache.base,
                                    filesize=data_segment['size'])
        # Zero-sized markers have distinct semantics even when their old"""


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text(encoding='utf-8')

    if MARK in text:
        print(f'{SCRIPT}: already patched')
        return 0
    if OLD_COLLIDE not in text:
        raise SystemExit(f'{SCRIPT}: collide-check block not found; upstream changed')
    if OLD_ALLOC not in text:
        raise SystemExit(f'{SCRIPT}: __KLDDATA/__BOOTDATA block not found; upstream changed')

    text = text.replace(OLD_COLLIDE, NEW_COLLIDE, 1)
    text = text.replace(OLD_ALLOC, NEW_ALLOC, 1)
    target.write_text(text, encoding='utf-8')
    print(f'{SCRIPT}: native __DATA is allocated after the __BOOTDATA root and registered')
    return 0


if __name__ == '__main__':
    sys.exit(main())
