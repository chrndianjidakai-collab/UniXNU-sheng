"""Make weak_defaults cover every diagnostic source and every declaration form.

build-sheng-source-storage.py's weak_defaults() has two defects that make the
iPadOS 27 kernel link (arm64e) fail on undefined weak_import symbols:

  1. It is applied to exactly one source (BootLog.c). LegacyDisplayProbe.cpp and
     BluetoothProbe.cpp declare their own weak_import symbols:
       _sheng_ethernet_probe / _sheng_software_aes_probe   (macOS-only providers)
       _sheng_bt_firmware_read / _sheng_bt_firmware_release (conditional)
       _native_legacy_formats / _native_legacy_request_layout
     On iPadOS 27 nothing provides them, so the link dies.

  2. Its parser only accepts declarations ending on one line. BootLog.c's
     native_data_io_* block is one declaration folded across six lines with
     trailing commas, so every one of those names is skipped.

This patch replaces the whole function: generate defaults for all three sources
(merged), parse by declaration instead of by line, strip comments, accept
`extern "C"` and plain `extern`, and resolve quoted includes per source.

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
    not built in get these defaults; a component's own definition wins. Data is
    zero, functions report absence: int returns -1, strings "", other scalars 0, pointers NULL.
    Hidden visibility keeps the static kernel link from binding them at run time.
    Accepts a single source or a list, and parses by declaration so multi-line
    (trailing-comma) and `extern "C"` declarations are covered.
    """
    import re
    sources = source if isinstance(source, (list, tuple)) else [source]
    lines = []
    for src in sources:
        text = src.read_text()
        text = re.sub(r'//[^\\n]*', '', text)
        text = re.sub(r'/\\*.*?\\*/', '', text, flags=re.S)
        # #include directives have no ';' and would otherwise be glued into the
        # preceding/succeeding declaration when we split on ';'. Strip them (and
        # all preprocessor lines) before folding continuations.
        text = re.sub(r'^\\s*#.*$', '', text, flags=re.M)
        text = re.sub(r'\\n\\s*', ' ', text)
        for statement in re.split(r';', text):
            statement = statement.strip()
            if '__attribute__((weak_import))' not in statement:
                continue
            names = re.findall(r'([A-Za-z_]\\w*)\\s*(?:\\[[^\\]]*\\]|\\([^)]*\\))?\\s*__attribute__\\(\\(weak_import\\)\\)', statement)
            if not names:
                continue
            # strip linkage spec, 'extern', and any stray closing braces left over
            # from a preceding scope when the declaration was folded onto one line
            without_extern = re.sub(r'^extern\\s+"C"\\s*', '', statement)
            without_extern = re.sub(r'^extern\\s+', '', without_extern)
            without_extern = re.sub(r'^[}\\s]+', '', without_extern)
            first = names[0]
            base = without_extern[:without_extern.index(first)].strip()
            # A base type that still carries C++ linkage/scope junk cannot be a
            # valid C declaration; fall back to 'int' for such rare cases.
            if not base or re.search(r'\\b(class|public|namespace|template)\\b|extern "C"|[{}]', base):
                base = 'int'
            for name in names:
                tail = statement[statement.index(name) + len(name):]
                is_call = tail.lstrip().startswith('(') and '(*' not in statement[:statement.index(name)]
                if is_call:
                    params = re.match(r'\\s*\\(([^)]*)\\)', tail)
                    params = (params.group(1) if params else '').strip()
                    body = ('' if base == 'void' else ' return -1;' if base == 'int' else
                            ' return "";' if base.replace(' ', '') in ('constchar*', 'char*') else ' return 0;')
                    lines.append(f'__attribute__((weak, visibility("hidden"))) {base} {name}({params}) {{{body} }}')
                else:
                    lines.append(f'__attribute__((weak, visibility("hidden"))) {base} {name};')
    # The generated file needs only the fixed-width integer typedefs; copying the
    # sources' #include lines in (especially the C++ probe headers such as qbt.h
    # and the IOKit C++ headers) makes a pure C file fail with
    # "unknown type name 'class'" and hundreds of follow-on errors. Keep the two
    # C standard headers the emitted declarations actually need, plus the pragma
    # that silences the C23 extension warning on unnamed parameters.
    headers = ['#include <stdint.h>', '#include <stddef.h>']
    pragma = ['#pragma clang diagnostic ignored "-Wc23-extensions"']
    return '\\n'.join(headers + pragma + lines) + '\\n'
'''


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text(encoding='utf-8')

    if 'parses by declaration so multi-line' in text:
        print(f'{SCRIPT}: already patched')
        return 0
    if OLD_FUNC not in text:
        raise SystemExit(f'{SCRIPT}: weak_defaults function not found; upstream changed')

    # 1. Replace the function.
    text = text.replace(OLD_FUNC, NEW_FUNC, 1)

    # 2. Point the call site at all three sources.
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
    print(f'{SCRIPT}: weak_defaults covers BootLog, LegacyDisplayProbe and BluetoothProbe, '
          f'parses multi-line and extern "C" declarations')
    return 0


if __name__ == '__main__':
    sys.exit(main())
