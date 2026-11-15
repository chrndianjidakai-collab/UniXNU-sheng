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
  4. Allocating __DATA before the __LINKINFO/__LINKEDIT phase and replacing
     roots['__DATA'] with the new address -> validate() raises "Root mappings
     overlap": the __LINKEDIT root spans from the original __LINKEDIT va to the
     latest cursor (link['size'] = cursor - link['fileoff']), so it swallowed
     the freshly allocated __DATA root.
  5. Allocating __DATA after __BOOTDATA and STILL replacing roots['__DATA'] ->
     rebuild_linkedit raises "Fixup is not within one root mapping": the
     collection's own __DATA chain sites keep their addresses (mapped() only
     covers the kernel entry's segments, and the site's owner is a kext, so the
     site survives), and with roots['__DATA'] moved they no longer match any
     root. The top-level __DATA LC is also rewritten from roots['__DATA'] by
     patch_headers(), so that root must stay at the collection's address.

The working fix keeps roots['__DATA'] untouched and registers the freshly
allocated native __DATA run as an extra __NDATA root:

  - validate(): the native __DATA segment at placements['__DATA'] is covered by
    the __NDATA root ("outside collection mappings" passes), and __NDATA does
    not overlap any other root because it is allocated after __BOOTDATA, like
    every other segment moved out of the collection.
  - rebuild_linkedit(): native chain sites land inside the __NDATA root, the
    collection's own __DATA sites keep matching the untouched roots['__DATA'].
  - emit_images()/patch_headers(): every native segment is appended as a
    separate __N-prefixed top-level segment (extra segments), so the extra root
    needs no LC of its own; the top-level __DATA LC keeps the collection's
    original address.

place_kernel moves a segment as one contiguous block
(self.data[at:at+span] = ...), so __DATA cannot be split across runs. It needs
its own space outside the collection's original layout. Idempotent.

Usage:
    python patch-prelink-layout.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'kits/XnuPrelink/fileset_layout.py'
MARK = "self.roots['__NDATA'] = dict(data_segment"

OLD_SEG = """    def segment(self, name):
        return next(s for s in self.native.segments if s['name'] == name)"""

NEW_SEG = """    def segment(self, name):
        # patch-prelink-layout: __NDATA is the registered root name for the
        # native __DATA run allocated past the collection. patch_headers()
        # looks the source command of every non-original root up by root name
        # (for maxprot/initprot), and a lookup of '__NDATA' in the native
        # segments would raise StopIteration and abort the emit; map it back
        # to the native segment it stands for.
        if name == '__NDATA':
            name = '__DATA'
        return next(s for s in self.native.segments if s['name'] == name)"""

OLD_VALIDATE = """        ordered = sorted((s['va'], s['va'] + s['size']) for s in self.roots.values() if s['size'])
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ValueError('Root mappings overlap')"""

NEW_VALIDATE = """        ordered = sorted((s['va'], s['va'] + s['size']) for s in self.roots.values() if s['size'])
        # patch-prelink-layout: report every root interval and the exact
        # overlapping pair instead of a bare 'Root mappings overlap', so the
        # next failure names its culprits instead of costing a blind rerun.
        overlap = next(((a, b) for a, b in zip(ordered, ordered[1:]) if a[1] > b[0]), None)
        if overlap:
            for name, s in sorted(self.roots.items(), key=lambda kv: kv[1]['va']):
                if s['size']:
                    print(f'  root {name:20s} va={s["va"]:#014x} end={s["va"] + s["size"]:#014x}', flush=True)
            raise ValueError(f'Root mappings overlap: {overlap[0][1]:#x} crosses {overlap[1][0]:#x}')"""

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
        # bytes because a retained segment splits the mapping. The native
        # __DATA segment is instead allocated past the collection, registered
        # as an extra __NDATA root (see below), so the collide check and the
        # old-va reserve are dropped here. roots['__DATA'] itself stays put:
        # the collection's own __DATA chain sites and the top-level __DATA LC
        # (rewritten by patch_headers) both depend on it.
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
        # patch-prelink-layout: the native __DATA segment is allocated here,
        # after the __KLDDATA and __BOOTDATA roots. Ordering constraints that
        # earlier attempts tripped over:
        #  - allocating before the __LINKINFO/__LINKEDIT phase puts the new run
        #    inside the __LINKEDIT root's span (that root runs from the original
        #    __LINKEDIT va to the latest cursor), so validate() raises 'Root
        #    mappings overlap';
        #  - replacing roots['__DATA'] with the new run leaves the collection's
        #    own __DATA chain sites without a root (mapped() only covers the
        #    kernel entry's segments; a site owned by a kext survives) and
        #    rebuild_linkedit raises 'Fixup is not within one root mapping'.
        # So roots['__DATA'] stays at the collection's address, and the fresh
        # run is registered as an extra __NDATA root: validate() sees the native
        # segment covered, rebuild_linkedit() files the native chain sites under
        # it, and emit_images() already appends every native segment as a
        # separate __N-prefixed top-level segment, so no LC of its own is
        # needed. Pinning at the original va collides with the retained kext
        # code + native __KLD; align(code_end) lands inside a kept kext; hole()
        # finds only 0x1e8000 contiguous bytes because a retained segment
        # splits the mapping.
        data_segment = self.segment('__DATA')
        data_address = self.allocate(data_segment['size'])
        self.reserve('__DATA', data_address)
        self.roots['__NDATA'] = dict(data_segment, va=data_address,
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
    if OLD_SEG not in text:
        raise SystemExit(f'{SCRIPT}: segment() lookup not found; upstream changed')
    if OLD_VALIDATE not in text:
        raise SystemExit(f'{SCRIPT}: validate overlap check not found; upstream changed')

    text = text.replace(OLD_COLLIDE, NEW_COLLIDE, 1)
    text = text.replace(OLD_ALLOC, NEW_ALLOC, 1)
    text = text.replace(OLD_SEG, NEW_SEG, 1)
    text = text.replace(OLD_VALIDATE, NEW_VALIDATE, 1)
    target.write_text(text, encoding='utf-8')
    print(f'{SCRIPT}: native __DATA allocated past the collection under an extra __NDATA root')
    return 0


if __name__ == '__main__':
    sys.exit(main())
