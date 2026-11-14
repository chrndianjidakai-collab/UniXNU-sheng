"""Stage the proprietary firmware blobs before the build needs them.

`proprietary-files.txt` lists three paths with SHA-256 digests and an `@fetch`
base (the public ianchb/sheng-firmware mirror):

    novatek/novatek_nt36532_n81a_fw_csot.bin   Touch
    nanosic/MCU_Upgrade.bin                    Keyboard
    qcom/sm8550/sheng/vpu30_4v.mbn             Video

`scripts/extract-files.py` writes them to `<device>/.cache/firmware/<name>`.
The iPadOS 27 build reaches the keyboard one late, inside
build-gop-legacy-display-27.py, and dies with

    nanosic/MCU_Upgrade.bin: run scripts/extract-files.py --section Keyboard
                                            in the device repository

after ~35 minutes of compilation. The default fetch path in extract-files.py is
raw.githubusercontent.com, which is not reachable from this network, so this
script pulls the same bytes through the GitHub API instead and verifies every
digest against proprietary-files.txt before writing.

Usage:
    python stage-proprietary.py <device repo> [--check]
"""
import base64
import hashlib
import json
import os
import pathlib
import sys
import urllib.request

LIST = 'proprietary-files.txt'


def parse(device):
    path = device / LIST
    if not path.is_file():
        raise SystemExit(f'{path} missing')
    base, rows = None, []
    for line in path.read_text().splitlines():
        text = line.strip()
        if text.startswith('@fetch '):
            base = text.split(None, 1)[1].rstrip('/') + '/'
        elif text.startswith('#') or not text:
            continue
        else:
            name, _, digest = text.partition('|')
            if len(digest) != 64:
                raise SystemExit(f'{LIST}: expected path|sha256 in {text!r}')
            rows.append((name.lstrip('-'), digest, name.startswith('-')))
    return base, rows


def api_get(url):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'unixnu-stage-proprietary',
        'Accept': 'application/vnd.github+json',
    })
    with urllib.request.urlopen(request, timeout=180) as reply:
        return json.loads(reply.read())


def fetch_via_api(base, name):
    """The @fetch base is a raw.githubusercontent URL pinned to a commit. GitHub's
    contents API needs owner/repo/ref, and for files over 1 MiB it returns an
    empty content field, so the blob API is used when that happens."""
    # .../<owner>/<repo>/<commit>/<prefix>
    tail = base.rstrip('/')
    marker = '://raw.githubusercontent.com/'
    if marker not in tail:
        raise SystemExit(f'unsupported @fetch base: {base}')
    owner, repo, commit, *rest = tail.split(marker, 1)[1].split('/')
    prefix = '/'.join(rest)

    contents = api_get(f'https://api.github.com/repos/{owner}/{repo}/contents/'
                       f'{prefix + name}?ref={commit}')
    if contents.get('content'):
        return base64.b64decode(contents['content'])

    # Large file: resolve the blob SHA and take the blob endpoint, which always
    # returns base64 even above the 1 MiB inline limit.
    tree = api_get(f'https://api.github.com/repos/{owner}/{repo}/git/trees/{commit}?recursive=1')
    wanted = prefix + name
    entry = next((item for item in tree.get('tree', []) if item['path'] == wanted), None)
    if entry is None:
        raise SystemExit(f'{wanted} is not in {owner}/{repo}@{commit[:8]}')
    blob = api_get(f'https://api.github.com/repos/{owner}/{repo}/git/blobs/{entry["sha"]}')
    return base64.b64decode(blob['content'])


def fetch(name, base):
    """Plain HTTP first: on a GitHub runner raw.githubusercontent.com is direct
    and needs no token. The API path is the fallback for hosts where raw is not
    reachable, and it uses GITHUB_TOKEN when the environment provides one so the
    anonymous rate limit does not apply."""
    try:
        request = urllib.request.Request(base + name, headers={
            'User-Agent': 'unixnu-stage-proprietary',
        })
        token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
        if token:
            request.add_header('Authorization', 'Bearer ' + token)
        with urllib.request.urlopen(request, timeout=180) as reply:
            return reply.read()
    except Exception as raw_error:
        print(f'  raw fetch failed ({raw_error}); trying the GitHub API')
        return fetch_via_api(base, name)


def main():
    device = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    check_only = '--check' in sys.argv
    base, rows = parse(device)
    if not base:
        raise SystemExit(f'{LIST} has no @fetch base')

    out = device / '.cache/firmware'
    failed = 0
    for name, digest, optional in rows:
        target = out / name
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            print(f'ok        {name}')
            continue
        if check_only:
            print(f'{"optional " if optional else "MISSING  "}{name}')
            failed += not optional
            continue
        try:
            data = fetch(name, base)
        except Exception as error:
            print(f'{"optional " if optional else "FAILED   "}{name}: {error}')
            failed += not optional
            continue
        if hashlib.sha256(data).hexdigest() != digest:
            print(f'FAILED    {name}: sha256 differs, not kept')
            failed += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print(f'staged    {name} ({len(data)} bytes)')

    if failed:
        print(f'{failed} required file(s) missing', file=sys.stderr)
        return 1
    print('all listed proprietary files present with matching digests')
    return 0


if __name__ == '__main__':
    sys.exit(main())
