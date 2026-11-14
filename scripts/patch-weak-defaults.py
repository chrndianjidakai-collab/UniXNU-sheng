"""Make weak_defaults cover every diagnostic source and every declaration form,
and emit type-independent definitions.

build-sheng-source-storage.py's weak_defaults() has two defects that make the
iPadOS 27 kernel link (arm64e) fail on undefined weak_import symbols:

  1. It is applied to exactly one source (BootLog.c). LegacyDisplayProbe.cpp and
     BluetoothProbe.cpp declare their own weak_import symbols; nothing provides
     them on iPadOS 27, so the link dies.
  2. Its parser only accepts declarations ending on one line. BootLog.c's
     native_data_io_* block is one declaration folded across six lines with
     trailing commas, so every one of those names is skipped.

The original parser also reused each declaration's C type in the generated file.
That breaks when a type is a struct (incomplete), a typedef (ShengAudioDiag),
bool, or when a multi-declarator statement leaves `__attribute__((weak_import))`
text inside the emitted definition. The C linker matches weak symbols by NAME
only, so this rewrite emits type-independent definitions: `long NAME(void)`
for functions and `char NAME[8]` for data. Hidden visibility keeps the static
kernel link from binding them at run time; a real component definition wins.

Usage:
    python patch-weak-defaults.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'scripts/build-sheng-source-storage.py'

OLD_FUNC = '''def weak_defaults(source):
    """Zero weak definitions for the weak imports of a diagnostic source.

    The kernel link cannot leave weak imports undefined, so components that are
    not built in get these defaults; a component's own definition wins. Data is
    zero, functions report absence: int returns -1, strings "", other scalars 0, pointers NULL.
    Hidden visibility keeps the static kernel link from binding them at run time.
    """
    import re
    lines = []
    for line in source.read_text().splitlines():
        line = line.strip()
        if not (line.startswith('extern ') and line.endswith('__attribute__((weak_import));')):
            continue
        decl = line[len('extern '):-len('__attribute__((weak_import));')].replace('__attribute__((weak_import))', '').strip()
        call = re.match(r'^(.*?[\\s*])([A-Za-z_]\\w*)\\s*\\((.*)\\)$', decl)
        if call and '(*' not in decl.split(call.group(2))[0]:
            ret = call.group(1).strip()
            body = ('' if ret == 'void' else ' return -1;' if ret == 'int' else
                    ' return "";' if ret.replace(' ', '') in ('constchar*', 'char*') else ' return 0;')
            lines.append(f'__attribute__((weak, visibility("hidden"))) {decl} {{{body} }}')
        else:
            lines.append(f'__attribute__((weak, visibility("hidden"))) {decl};')
    # Quoted headers are resolved next to the source, which the generated file is not.
    includes = [l.replace('#include "', f'#include "{source.parent}/') for l in source.read_text().splitlines()
                if l.startswith('#include')]
    # Element types the declarations name are defined in the source itself.
    named = set(re.findall(r'struct (\\w+)', '\\n'.join(lines)))
    includes += [m.group(0) for m in re.finditer(r'^struct (\\w+) \\{[^;{}]*(?:;[^;{}]*)*\\};', source.read_text(), re.M)
                 if m.group(1) in named]
    # The defaults keep the declarations' unnamed parameters.
    pragma = ['#pragma clang diagnostic ignored "-Wc23-extensions"']
    return '\\n'.join(includes + pragma + lines) + '\\n'
'''

NEW_FUNC = '''def weak_defaults(source):
    """Zero weak definitions for the weak imports of the diagnostic sources.

    The kernel link cannot leave weak imports undefined, so components that are
    not built in get these defaults; a component's own definition wins. Hidden
    visibility keeps the static kernel link from binding them at run time.
    Accepts a single source or a list, and parses by declaration so multi-line
    (trailing-comma) and `extern "C"` declarations are covered. The C linker
    matches by name only, so definitions are emitted with fixed simple types
    (`long f(void)` / `char name[8]`) and never reuse the source's types.
    """
    import re
    sources = source if isinstance(source, (list, tuple)) else [source]
    # A declarator may be followed by any number of array brackets or a parameter
    # list before __attribute__((weak_import)); capture the identifier itself.
    decl_re = re.compile(
        r'([A-Za-z_][A-Za-z0-9_]*)\\s*(?:(?:\\[[^\\]]*\\])|(?:\\([^)]*\\)))*\\s*__attribute__\\(\\(weak_import\\)\\)')
    seen = set()
    lines = []
    for src in sources:
        text = src.read_text()
        text = re.sub(r'//[^\\n]*', '', text)
        text = re.sub(r'/\\*.*?\\*/', '', text, flags=re.S)
        # #include / #define have no ';' and would be glued into a declaration.
        text = re.sub(r'^\\s*#.*$', '', text, flags=re.M)
        text = re.sub(r'\\n\\s*', ' ', text)
        for statement in re.split(r';', text):
            if '__attribute__((weak_import))' not in statement:
                continue
            for m in decl_re.finditer(statement):
                name = m.group(1)
                if name in seen:
                    continue
                seen.add(name)
                # Inspect only the declarator suffix (between the name and the
                # attribute). Function prototypes carry a (...) there; data
                # symbols carry array brackets or nothing. The attribute's own
                # parentheses must not be counted.
                suffix = m.group(0)[len(name):m.group(0).index('__attribute__')]
                is_call = '(' in suffix
                if is_call:
                    lines.append(f'__attribute__((weak, visibility("hidden"))) long {name}(void) {{ return 0; }}')
                else:
                    lines.append(f'__attribute__((weak, visibility("hidden"))) char {name}[8];')
    return '\\n'.join(['#include <stdint.h>', '#include <stddef.h>',
                       '#pragma clang diagnostic ignored "-Wc23-extensions"'] + lines) + '\\n'
'''


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text(encoding='utf-8')

    if 'matches by name only, so definitions are emitted' in text:
        print(f'{SCRIPT}: already patched')
        return 0
    if OLD_FUNC not in text:
        raise SystemExit(f'{SCRIPT}: weak_defaults function not found; upstream changed')
    text = text.replace(OLD_FUNC, NEW_FUNC, 1)

    old_call = """    boot_log_defaults = out / 'BootLogDefaults.c'
    boot_log_defaults.write_text(weak_defaults(device_source('BootLog.c')))"""
    new_call = """    boot_log_defaults = out / 'BootLogDefaults.c'
    # patch-weak-defaults.py: defaults for every diagnostic source that declares
    # weak_import symbols, not just BootLog.c.
    boot_log_defaults.write_text(weak_defaults([
        device_source('BootLog.c'),
        device_source('LegacyDisplayProbe.cpp'),
        device_source('BluetoothProbe.cpp'),
    ]))"""
    if old_call not in text:
        raise SystemExit(f'{SCRIPT}: BootLogDefaults call site not found; upstream changed')
    text = text.replace(old_call, new_call, 1)

    target.write_text(text, encoding='utf-8')
    print(f'{SCRIPT}: weak_defaults covers all three sources, parses by declaration, '
          f'emits type-independent weak definitions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
