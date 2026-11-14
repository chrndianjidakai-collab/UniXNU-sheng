"""Make weak_defaults cover every diagnostic source and every declaration form,
and emit one uniform, type-independent definition per weak symbol.

build-sheng-source-storage.py's weak_defaults() has two defects that make the
iPadOS 27 kernel link (arm64e) fail on undefined weak_import symbols:
  1. It is applied to exactly one source (BootLog.c); LegacyDisplayProbe.cpp and
     BluetoothProbe.cpp declare their own weak_import symbols that nothing
     provides on iPadOS 27.
  2. Its parser only accepts declarations ending on one line; BootLog.c's
     native_data_io_* block is one declaration folded across six lines.

The C linker matches weak symbols by NAME only. This kernel is a comparison
build that never runs (prelink reads only its layout), and every hidden weak
default is overridden by a real component definition when one exists. So the
simplest correct output is one `char NAME[8];` per symbol, with no reference to
the source's C types at all. That sidesteps every type problem encountered:
incomplete structs, typedefs (ShengAudioDiag), bool, __attribute__ text leaking
into a definition, and function-pointer declarators such as
`extern int (*native_adreno_dram_read32)(...) __attribute__((weak_import))`
where a naive regex captured `int` as the symbol name.

Symbol names are extracted with a keyword blacklist and a dedicated
function-pointer pattern, so no C keyword can become a definition.

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
    Accepts a single source or a list. The C linker matches by name only, so each
    symbol gets one uniform `char NAME[8];` definition and the sources' types are
    never reused (they include incomplete structs, typedefs and function
    pointers). A keyword blacklist and a function-pointer pattern keep C
    keywords out of the symbol set.
    """
    import re
    sources = source if isinstance(source, (list, tuple)) else [source]
    keywords = {
        'int', 'void', 'char', 'long', 'short', 'float', 'double', 'unsigned',
        'signed', 'const', 'volatile', 'static', 'extern', 'struct', 'union',
        'enum', 'bool', 'size_t', 'uint8_t', 'uint16_t', 'uint32_t', 'uint64_t',
        'int8_t', 'int16_t', 'int32_t', 'int64_t', 'intptr_t', 'uintptr_t',
        'return', 'if', 'else', 'for', 'while', 'sizeof', 'typedef', 'register',
        'restrict', '_Bool', 'true', 'false', 'NULL',
    }
    # ordinary declarators: NAME followed by any number of (...) or [...] before
    # __attribute__((weak_import))
    ordinary = re.compile(
        r'([A-Za-z_][A-Za-z0-9_]*)\\s*(?:(?:\\([^)]*\\)|\\[[^\\]]*\\])\\s*)*__attribute__\\(\\(weak_import\\)\\)')
    # function-pointer declarators: (*NAME)(...) __attribute__((weak_import))
    fnptr = re.compile(r'\\(\\s*\\*\\s*([A-Za-z_][A-Za-z0-9_]*)\\s*\\)[^;]*?__attribute__\\(\\(weak_import\\)\\)')
    names = set()
    for src in sources:
        text = src.read_text()
        text = re.sub(r'//[^\\n]*', '', text)
        text = re.sub(r'/\\*.*?\\*/', '', text, flags=re.S)
        text = re.sub(r'^\\s*#.*$', '', text, flags=re.M)
        text = re.sub(r'\\n\\s*', ' ', text)
        for m in ordinary.finditer(text):
            name = m.group(1)
            if name not in keywords:
                names.add(name)
        for m in fnptr.finditer(text):
            name = m.group(1)
            if name not in keywords:
                names.add(name)
    # Strong symbols that libNativeLegacyDisplay.late.a references but whose
    # providing archives are ordered after it in LD_KERNEL_ARCHIVES. On arm64e
    # the one-way archive scan cannot resolve these circular references, so the
    # comparison kernel (which never runs) needs hidden weak fallbacks too.
    names.update({
        'armcpu_spi_share', 'armdt_platform_clock_register',
        'native_adreno_gpu_interrupt', 'native_adreno_pool_add',
        'sheng_bt_firmware_read', 'sheng_bt_firmware_release',
    })
    lines = [f'__attribute__((weak, visibility("hidden"))) char {name}[8];'
             for name in sorted(names)]
    return '\\n'.join(lines) + '\\n' if lines else ''


'''

CALL_OLD = """    boot_log_defaults = out / 'BootLogDefaults.c'
    boot_log_defaults.write_text(weak_defaults(device_source('BootLog.c')))"""

CALL_NEW = """    boot_log_defaults = out / 'BootLogDefaults.c'
    # patch-weak-defaults.py: defaults for every diagnostic source that declares
    # weak_import symbols, not just BootLog.c.
    boot_log_defaults.write_text(weak_defaults([
        device_source('BootLog.c'),
        device_source('LegacyDisplayProbe.cpp'),
        device_source('BluetoothProbe.cpp'),
    ]))"""

MARK = 'symbol gets one uniform `char NAME[8];` definition'


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text(encoding='utf-8')

    if MARK in text:
        print(f'{SCRIPT}: already patched')
        return 0
    if OLD_FUNC not in text:
        raise SystemExit(f'{SCRIPT}: weak_defaults function not found; upstream changed')
    if CALL_OLD not in text:
        raise SystemExit(f'{SCRIPT}: BootLogDefaults call site not found; upstream changed')

    text = text.replace(OLD_FUNC, NEW_FUNC, 1)
    text = text.replace(CALL_OLD, CALL_NEW, 1)
    target.write_text(text, encoding='utf-8')
    print(f'{SCRIPT}: weak_defaults covers all three sources and emits uniform '
          f'type-independent weak definitions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
