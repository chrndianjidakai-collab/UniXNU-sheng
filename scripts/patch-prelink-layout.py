"""Instrument the fileset layout collision so the real numbers are visible.

fileset_layout.Layout.__init__ raises
    ValueError: Native code would collide with collection data
when the retained kext code plus the native __KLD segment runs past the
collection's original __DATA address:

    code_end = self.end('__KLD')
    if code_end > self.roots['__DATA']['va']:
        raise ValueError('Native code would collide with collection data')

The message carries no numbers, so the size of the overrun is unknown and a fix
would be guesswork. This patch keeps the failure but prints the segment layout
first: each native segment's placed address and size, the __DATA limit, and the
signed overrun. Idempotent.

Usage:
    python patch-prelink-layout.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'kits/XnuPrelink/fileset_layout.py'
MARK = 'patch-prelink-layout: report the overrun'

OLD = """        code_end = self.end('__KLD')
        # The old kernel boot segment and prelink XML are replaceable, provided
        # no retained kext uses them. Move XML into its own mapping below.
        if code_end > self.roots['__DATA']['va']:
            raise ValueError('Native code would collide with collection data')"""

NEW = """        code_end = self.end('__KLD')
        # The old kernel boot segment and prelink XML are replaceable, provided
        # no retained kext uses them. Move XML into its own mapping below.
        if code_end > self.roots['__DATA']['va']:
            # patch-prelink-layout: report the overrun so a fix is not guesswork.
            print('prelink layout before the collision:', flush=True)
            for name, address in sorted(self.placements.items()):
                print(f'  {name:<18} va={address:#014x} size={self.span(name):#012x} '
                      f'end={self.placements[name] + self.span(name):#014x}', flush=True)
            print(f'  __DATA limit        va={self.roots["__DATA"]["va"]:#014x}', flush=True)
            print(f'  __TEXT_EXEC start   va={self.roots["__TEXT_EXEC"]["va"]:#014x} '
                  f'size={self.roots["__TEXT_EXEC"]["size"]:#012x}', flush=True)
            kept = [end for begin, end in self.occupied
                    if self.roots['__TEXT_EXEC']['va'] <= begin < self.roots['__TEXT_EXEC']['va'] + self.roots['__TEXT_EXEC']['size']]
            print(f'  retained kext ends  max={max(kept) if kept else 0:#014x} count={len(kept)}', flush=True)
            print(f'  overrun             {code_end - self.roots["__DATA"]["va"]:#x} bytes', flush=True)
            raise ValueError('Native code would collide with collection data')"""


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
    print(f'{SCRIPT}: the collision now reports the segment layout and overrun')
    return 0


if __name__ == '__main__':
    sys.exit(main())
