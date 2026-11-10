# SPDX-License-Identifier: GPL-3.0-or-later
# ci/zipcheck.py - the checks of the plugin zip, its .sha256 and .contents.tsv files, extraction and listing.
# Usage (ci/package.sh runs it in the python image of ci/legs; stdlib only, Python 3.8 or later):
#   python3 -I ci/zipcheck.py check <zip> <ls-tree.txt> <version> <out-dir>
#   python3 -I ci/zipcheck.py extract <zip> <new dir>
#   python3 -I ci/zipcheck.py list <zip>
# Exit: 0 pass; 1 a check failed; 2 usage, or a file that cannot be read or written.

import collections
import hashlib
import os
import re
import shutil
import stat
import sys
import zipfile
import zlib

PKG = 'fiberq'

USAGE = """\
usage: zipcheck.py check <zip> <ls-tree.txt> <version> <out-dir>
       zipcheck.py extract <zip> <new dir>
       zipcheck.py list <zip>
check    <ls-tree.txt> is the output of "git ls-tree -r <commit> -- fiberq". The check fails on: an entry outside
         fiberq/, or no fiberq/metadata.txt or fiberq/__init__.py; a path component starting with "."; a
         __pycache__ component, or a name ending .pyc or .pyo; an executable bit or a symlink in the zip; a git
         mode other than 100644; a file list that differs from ls-tree's, or a file whose content is not the
         blob ls-tree names; version= in metadata.txt or __version__ in __init__.py other than <version>; an
         entry that fails its CRC (testzip).
         If it passes, it writes fiberq-<version>.sha256 ("<sha256>  fiberq-<version>.zip") and
         fiberq-<version>.contents.tsv (path, git mode, sha256; sorted by path) into <out-dir>, never over a file.
         It prints entries=, files=, dirs=, sha256=, comment=, version= and problems= on stdout, each problem on
         stderr.
extract  writes every entry into <new dir>, which must not exist yet; it refuses unsafe names, never overwrites
         and never sets an executable bit.
list     prints one line per entry: path, size and CRC-32, tab-separated.
Exit: 0 pass; 1 a check failed; 2 usage, or a file that cannot be read or written.
"""

VERSION_ARG = re.compile(r'[A-Za-z0-9_+-][A-Za-z0-9._+-]*')
OBJECT_ID = re.compile(r'[0-9a-f]{40}|[0-9a-f]{64}')
INIT_VERSION = re.compile(r'''^__version__\s*=\s*['"]([^'"]*)['"]''', re.M)
C_ESCAPES = {'a': 7, 'b': 8, 't': 9, 'n': 10, 'v': 11, 'f': 12, 'r': 13, '"': 34, '\\': 92}
READ_ERRORS = (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError, ValueError, OSError)


def say(text):
    sys.stderr.write('zipcheck.py: %s\n' % text)


def unquote(path):
    """A path as git ls-tree prints it, without git's C-style quoting (core.quotePath)."""
    if len(path) < 2 or path[0] != '"' or path[-1] != '"':
        return path
    body = path[1:-1]
    raw = bytearray()
    i = 0
    while i < len(body):
        ch = body[i]
        if ch != '\\':
            raw.extend(ch.encode('utf-8'))
            i += 1
            continue
        esc = body[i + 1:i + 2]
        octal = body[i + 1:i + 4]
        if esc in C_ESCAPES:
            raw.append(C_ESCAPES[esc])
            i += 2
        elif re.fullmatch('[0-3][0-7][0-7]', octal):
            raw.append(int(octal, 8))
            i += 4
        else:
            raise ValueError('bad quoting in %r' % path)
    return raw.decode('utf-8')


def read_ls_tree(path):
    """[(git mode, path, object id)] from a "git ls-tree -r" listing."""
    with open(path, 'rb') as fh:
        text = fh.read().decode('utf-8')
    rows = []
    for line in text.split('\n'):
        if not line:
            continue
        meta, tab, name = line.partition('\t')
        fields = meta.split(' ')
        if not tab or len(fields) != 3 or not OBJECT_ID.fullmatch(fields[2]):
            raise ValueError('not a "git ls-tree -r" line: %r' % line)
        rows.append((fields[0], unquote(name), fields[2]))
    return rows


def blob_id(data, size):
    """git's id of <data> as a blob object: SHA-1 for a 40-hex id, SHA-256 for a 64-hex one."""
    algo = hashlib.sha1 if size == 40 else hashlib.sha256
    return algo(b'blob %d\0' % len(data) + data).hexdigest()


def metadata_version(data):
    """version= from metadata.txt, all whitespace removed (as the Makefile reads it); None if absent."""
    for line in data.decode('utf-8', 'replace').split('\n'):
        if line.startswith('version='):
            return ''.join(line[len('version='):].split())
    return None


def init_version(data):
    """__version__ from __init__.py; None if absent."""
    found = INIT_VERSION.search(data.decode('utf-8', 'replace'))
    if found is None:
        return None
    return found.group(1)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_new(path, text):
    """Write <text> into the new file <path>; an existing file is an error, never overwritten."""
    with open(path, 'xb') as fh:
        fh.write(text.encode('utf-8'))


def entry_problems(info):
    """The layout problems of one zip entry, as a list of texts."""
    name = info.filename
    found = []
    if not name.startswith(PKG + '/'):
        found.append('%s: outside %s/' % (name, PKG))
    parts = [part for part in name.split('/') if part]
    if any(part.startswith('.') for part in parts):
        found.append('%s: a path component starts with "."' % name)
    if '__pycache__' in parts or name.endswith(('.pyc', '.pyo')):
        found.append('%s: compiled Python' % name)
    mode = info.external_attr >> 16
    if mode & 0o111:
        found.append('%s: executable bits (%s)' % (name, oct(mode & 0o777)))
    if stat.S_ISLNK(mode):
        found.append('%s: a symlink' % name)
    if any(ch in name for ch in '\t\n\r'):
        found.append('%r: a tab or line break in the name' % name)
    return found


def check(zpath, lspath, version, outdir):
    if not VERSION_ARG.fullmatch(version):
        say('bad version %r' % version)
        return 2
    if not os.path.isdir(outdir):
        say('no folder %s' % outdir)
        return 2
    try:
        rows = read_ls_tree(lspath)
        zip_hex = file_sha256(zpath)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        say(str(exc))
        return 2
    problems = []
    modes = {}
    blobs = {}
    for mode, name, oid in rows:
        if mode != '100644':
            problems.append('%s: git mode %s (only 100644 may ship)' % (name, mode))
        modes[name] = mode
        blobs[name] = oid
    infos = []
    files = []
    contents = []
    comment = ''
    try:
        with zipfile.ZipFile(zpath) as zf:
            infos = zf.infolist()
            comment = ' '.join(zf.comment.decode('utf-8', 'replace').split())
            for info in infos:
                problems.extend(entry_problems(info))
                if not info.is_dir():
                    files.append(info.filename)
            names = set(files)
            if sorted(files) != sorted(modes):
                for name in sorted(names - set(modes)):
                    problems.append('%s: in the zip, not in ls-tree' % name)
                for name in sorted(set(modes) - names):
                    problems.append('%s: in ls-tree, not in the zip' % name)
                for name, count in sorted(collections.Counter(files).items()):
                    if count > 1:
                        problems.append('%s: %d entries of this name' % (name, count))
            for need in ('metadata.txt', '__init__.py'):
                if '%s/%s' % (PKG, need) not in names:
                    problems.append('%s/%s: missing' % (PKG, need))
            if PKG + '/metadata.txt' in names:
                found = metadata_version(zf.read(PKG + '/metadata.txt'))
                if found != version:
                    problems.append('%s/metadata.txt: version=%s, expected %s' % (PKG, found, version))
            if PKG + '/__init__.py' in names:
                found = init_version(zf.read(PKG + '/__init__.py'))
                if found != version:
                    problems.append('%s/__init__.py: __version__ %s, expected %s' % (PKG, found, version))
            first_bad = zf.testzip()
            if first_bad is not None:
                problems.append('%s: CRC or header error (testzip)' % first_bad)
            for name in sorted(names):
                data = zf.read(name)
                digest = hashlib.sha256(data).hexdigest()
                contents.append((name, modes.get(name, '-'), digest))
                oid = blobs.get(name)
                if oid and blob_id(data, len(oid)) != oid:   # git archive applies export-subst and filters
                    problems.append('%s: the content is not the committed blob %s (an export-subst or filter '
                                    'attribute?)' % (name, oid))
    except READ_ERRORS as exc:
        problems.append('the zip cannot be read through: %s' % exc)
    for text in problems:
        say(text)
    base = '%s-%s' % (PKG, version)
    if not problems:
        lines = ['path\tmode\tsha256'] + ['%s\t%s\t%s' % row for row in contents]
        try:
            write_new(os.path.join(outdir, base + '.sha256'), '%s  %s.zip\n' % (zip_hex, base))
            write_new(os.path.join(outdir, base + '.contents.tsv'), '\n'.join(lines) + '\n')
        except OSError as exc:
            say(str(exc))
            return 2
    dirs = len(infos) - len(files)
    keys = (('entries', len(infos)), ('files', len(files)), ('dirs', dirs), ('sha256', zip_hex),
            ('comment', comment), ('version', version), ('problems', len(problems)))
    for key, value in keys:
        sys.stdout.write('%s=%s\n' % (key, value))
    if problems:
        return 1
    return 0


def unsafe(info):
    """Why the entry cannot be extracted safely, or ''."""
    name = info.filename
    parts = name.split('/')
    if info.is_dir():
        parts = parts[:-1]
    if not parts or name.startswith('/'):
        return 'an empty or absolute name'
    if '\\' in name or ':' in name or '\x00' in name:
        return 'a backslash, colon or NUL in the name'
    for part in parts:
        if part in ('', '.', '..'):
            return 'an empty, "." or ".." path component'
    if stat.S_ISLNK(info.external_attr >> 16):
        return 'a symlink'
    return ''


def extract(zpath, dest):
    try:
        os.mkdir(dest)
    except OSError as exc:
        say('%s (the folder must be new)' % exc)
        return 2
    try:
        with zipfile.ZipFile(zpath) as zf:
            for info in zf.infolist():
                why = unsafe(info)
                if why:
                    say('refusing %r: %s' % (info.filename, why))
                    return 1
                parts = [part for part in info.filename.split('/') if part]
                target = os.path.join(dest, *parts)
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, 'xb') as dst:
                    shutil.copyfileobj(src, dst)
    except FileExistsError as exc:
        say('%s (two entries of one name, or a file where a folder goes)' % exc)
        return 1
    except zipfile.BadZipFile as exc:
        say('the zip cannot be read through: %s' % exc)
        return 1
    except READ_ERRORS as exc:
        say(str(exc))
        return 2
    return 0


def listing(zpath):
    try:
        with zipfile.ZipFile(zpath) as zf:
            for info in zf.infolist():
                sys.stdout.write('%s\t%d\t%08x\n' % (info.filename, info.file_size, info.CRC))
    except zipfile.BadZipFile as exc:
        say('not a zip file: %s' % exc)
        return 1
    except OSError as exc:
        say(str(exc))
        return 2
    return 0


def main(argv):
    if len(argv) == 2 and argv[1] in ('-h', '--help'):
        sys.stdout.write(USAGE)
        return 0
    if len(argv) == 6 and argv[1] == 'check':
        return check(argv[2], argv[3], argv[4], argv[5])
    if len(argv) == 4 and argv[1] == 'extract':
        return extract(argv[2], argv[3])
    if len(argv) == 3 and argv[1] == 'list':
        return listing(argv[2])
    sys.stderr.write(USAGE)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
