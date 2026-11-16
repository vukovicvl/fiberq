# SPDX-License-Identifier: GPL-3.0-or-later
# ci/report.py - the run record (summary.md, record.txt), the JUnit compare of two runs, the detect-secrets count.
# Usage (stdlib only, Python 3.8 or later):
#   python3 -I ci/report.py summary
#       reads $CI_IN/run.txt and $CI_IN/stages/, writes summary.md, record.txt and result.txt into $CI_OUT
#   python3 -I ci/report.py compare <old run> <new run> <out-dir> [<stage,...>]
#       compares the junit.xml files of two run folders, writes compare.md and result.txt into <out-dir>
#   python3 -I ci/report.py secrets <detect-secrets JSON>
#       prints the number of findings, counted as the plugins.qgis.org scanner counts them
# ci/run-all.sh runs "summary" in the python image of ci/legs (in place: with this Python), ci/compare.sh runs
# "compare" there, ci/lint.sh runs "secrets".
# A stage's verdict is its status file: exactly one result= line, pass, fail or skip; anything else is invalid and
# counts as a failure, as in ci/common.sh. A skip counts as a failure in a release run, and in a run with --strict
# (strict=yes in run.txt).
# Exit: 0 done (summary: whatever the run's result is); 1 summary: run.txt has no stages=, or its run_result=
#       differs from the stages' verdicts; compare: a test was lost, or a compared stage is missing from the new
#       run; 2 usage, an input that cannot be read, or (compare) nothing to compare.

import datetime
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

SECRET_SKIP = ('.pyc', '.pyo', '.so', '.dll', '.exe')
STAGE_NAME = re.compile(r'[a-z0-9][a-z0-9-]*')
JUNIT_STAGE = re.compile(r'pure|test-[a-z0-9]+')
SLOWEST = 25
LISTED = 50
LINT_CHECKS = (
    ('flake8', 'flake8', ''),
    ('bandit', 'Bandit', ''),
    ('detect_secrets', 'detect-secrets', ''),
    ('shellcheck', 'shellcheck', 'shellcheck_files'),
    ('flake8_ci', 'flake8 ci/', 'flake8_ci_files'),
    ('placeholders', 'placeholders', ''),
)
CASE_RANK = {'passed': 0, 'skipped': 1, 'failed': 2, 'error': 3}

USAGE = """\
usage: report.py summary
       report.py compare <old run> <new run> <out-dir> [<stage,...>]
       report.py secrets <detect-secrets JSON>
summary  reads $CI_IN/run.txt and $CI_IN/stages/<stage>/{status,out/,deps-freeze.txt}; writes summary.md,
         record.txt and result.txt into $CI_OUT. It exits 1 when run.txt has no stages=, or when the stages'
         verdicts give another result than run.txt's run_result=.
compare  a test is lost when it passed in the old run and is absent, failed, errored or skipped in the new one.
         Without <stage,...> it compares every stage of the old run that has a junit.xml; a compared stage that
         the new run lacks, or ran without a junit.xml, loses all its old passes. Tests skipped or absent in the
         old run that fail or error in the new one are listed as now failing; they do not change the exit status.
         It exits 1 if anything was lost or missing, 2 if a run has no stages=, a named stage has no junit.xml in
         the old run, or no stage of the old run has one (nothing to compare).
secrets  prints the number of findings under "results", skipping files that end .pyc .pyo .so .dll .exe.
Exit: 0 done; 1 see above; 2 usage, or an input that cannot be read.
"""


def say(text):
    sys.stderr.write('report.py: %s\n' % text)


def one_line(value):
    return str(value).replace('\r', ' ').replace('\n', ' ')


def cell(value):
    """A value as one markdown table cell."""
    text = one_line(value).replace('|', '\\|')
    if not text:
        return '-'
    return text


def code(value):
    """A value as inline code in a table cell."""
    text = one_line(value)
    if not text:
        return '-'
    return '`%s`' % text.replace('`', "'").replace('|', '\\|')


def read_text(path):
    with open(path, 'rb') as fh:
        return fh.read().decode('utf-8', 'replace')


def read_lines(path):
    """The non-empty lines of a text file; [] when it cannot be read."""
    try:
        text = read_text(path)
    except OSError:
        return []
    return [line for line in text.split('\n') if line.strip()]


def read_kv(path):
    """key=value lines as a dict (a later line wins); None when the file cannot be read."""
    try:
        text = read_text(path)
    except OSError:
        return None
    data = {}
    for line in text.split('\n'):
        key, sep, value = line.partition('=')
        if sep and key:
            data[key] = value
    return data


def read_status(path):
    """(verdict, keys) of a status file. The verdict is pass, fail or skip when the file holds exactly one
    result= line with one of those values (as ci_result_of in ci/common.sh), else invalid."""
    try:
        text = read_text(path)
    except OSError:
        return 'invalid', {}
    keys = {}
    results = []
    for line in text.split('\n'):
        key, sep, value = line.partition('=')
        if not sep:
            continue
        if key == 'result':
            results.append(value)
        else:
            keys[key] = value
    if len(results) == 1 and results[0] in ('pass', 'fail', 'skip'):
        return results[0], keys
    return 'invalid', keys


def write_new(path, lines):
    """Write the lines into the new file <path>; an existing file is an error, never overwritten."""
    with open(path, 'xb') as fh:
        fh.write(('\n'.join(lines) + '\n').encode('utf-8'))


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def junit_read(path):
    """(totals, cases) of a pytest junit.xml, or None when it is absent or unreadable.
    totals: tests, failures, errors, skipped and passed over all test suites.
    cases: [(classname::name, passed|failed|error|skipped, seconds)]."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError, ValueError):
        return None
    if root.tag == 'testsuite':
        suites = [root]
    else:
        suites = list(root.iter('testsuite'))
    totals = {'tests': 0, 'failures': 0, 'errors': 0, 'skipped': 0}
    for suite in suites:
        for key in totals:
            totals[key] += to_int(suite.get(key))
    totals['passed'] = totals['tests'] - totals['failures'] - totals['errors'] - totals['skipped']
    cases = []
    for case in root.iter('testcase'):
        kinds = set(child.tag for child in case)
        if 'failure' in kinds:
            status = 'failed'
        elif 'error' in kinds:
            status = 'error'
        elif 'skipped' in kinds:
            status = 'skipped'
        else:
            status = 'passed'
        test_id = '%s::%s' % (case.get('classname', ''), case.get('name', ''))
        cases.append((test_id, status, to_float(case.get('time'))))
    return totals, cases


def case_status(cases):
    """{test id: status}; an id that appears more than once keeps its worst status."""
    found = {}
    for test_id, status, _seconds in cases:
        if test_id not in found or CASE_RANK[status] > CASE_RANK[found[test_id]]:
            found[test_id] = status
    return found


def now_failing(old_cases, new_cases):
    """[(test id, status)] of the tests that fail or error in the new run and were skipped or absent in the old one
    (a test that passed before is lost instead)."""
    found = []
    for test_id, status in sorted(new_cases.items()):
        if status in ('failed', 'error') and old_cases.get(test_id, 'absent') in ('skipped', 'absent'):
            found.append((test_id, status))
    return found


def role_of(stage):
    """The ci/legs role whose image runs <stage> (as ci_role_of in ci/common.sh); '' for host-only stages."""
    if stage in ('pure', 'lint', 'package', 'summary'):
        return 'python'
    if stage == 'qt6':
        return 'checker'
    if stage == 'floor':
        return 'floor'
    if stage.startswith('test-') and stage != 'test-local':
        return stage[len('test-'):]
    return ''


class Stage:
    """One stage of a run folder: its verdict and status keys, result.txt, junit.xml, the freeze of its tools."""

    def __init__(self, root, name):
        self.name = name
        folder = os.path.join(root, 'stages', name)
        self.out = os.path.join(folder, 'out')
        self.verdict, self.status = read_status(os.path.join(folder, 'status'))
        self.info = read_kv(os.path.join(self.out, 'result.txt')) or {}
        junit_path = os.path.join(self.out, 'junit.xml')
        self.has_junit = os.path.isfile(junit_path)
        self.junit = None
        if self.has_junit:
            self.junit = junit_read(junit_path)
        self.freeze = read_lines(os.path.join(folder, 'deps-freeze.txt'))

    def recorded(self):
        """pass, fail or skip for record.txt (an invalid verdict is a failure)."""
        if self.verdict == 'invalid':
            return 'fail'
        return self.verdict

    def shown(self):
        if self.verdict == 'invalid':
            return 'fail (no valid verdict)'
        return self.verdict

    def reason(self):
        reason = self.status.get('reason', '')
        if self.verdict == 'invalid' and not reason:
            return 'no valid verdict in its status file'
        return reason


def junit_counts(stage):
    """(text, [(record key, value)]) for a pytest stage."""
    if stage.junit is None:
        if stage.has_junit:
            return 'junit.xml unreadable', []
        return 'no junit.xml', []
    totals = stage.junit[0]
    text = '%d passed, %d failed, %d errors, %d skipped' % (
        totals['passed'], totals['failures'], totals['errors'], totals['skipped'])
    keys = [('tests', totals['tests']), ('passed', totals['passed']), ('failed', totals['failures']),
            ('errors', totals['errors']), ('skipped', totals['skipped'])]
    return text, keys


def stage_counts(stage):
    """(text for the Stages table, [(record key, value)]) of one stage, from its result files."""
    info = stage.info
    name = stage.name
    if JUNIT_STAGE.fullmatch(name):
        text, keys = junit_counts(stage)
        if not stage.has_junit and info.get('skipped'):   # in place, a test leg off its own QGIS
            text = 'skipped: %s' % info['skipped']
        extra = []
        for key, label in (('python', 'Python'), ('qgis', 'QGIS'), ('uid', 'uid')):
            if info.get(key):
                extra.append('%s %s' % (label, info[key]))
        return '; '.join([text] + extra), keys
    if not info:
        return 'no result.txt', []
    if name == 'lint':
        parts = []
        keys = []
        for key, label, files in LINT_CHECKS:
            if key not in info:
                continue
            text = '%s %s' % (label, info[key])
            if files and info.get(files):
                text += ' on %s files' % info[files]
            parts.append(text)
            keys.append((key, info[key]))
        return '; '.join(parts), keys
    if name == 'qt6':
        if info.get('skipped'):
            return 'skipped: %s' % info['skipped'], []
        text = 'findings %s; seed findings %s (min_seed %s); checker %s' % (
            info.get('findings', '?'), info.get('seed_findings', '?'), info.get('min_seed', '?'),
            info.get('checker', '?'))
        if info.get('checker_sha256'):
            text += ' (sha256 %s...)' % info['checker_sha256'][:16]
        keys = [(key, info[key]) for key in ('findings', 'seed_findings') if key in info]
        return text, keys
    if name == 'floor':
        if info.get('skipped'):   # in place, off the floor's QGIS
            return 'skipped: %s' % info['skipped'], []
        text = 'modules %s; findings %s; seeds %s; QGIS %s vs qgisMinimumVersion %s (%s)' % (
            info.get('modules', '?'), info.get('findings', '?'), info.get('seeds', '?'), info.get('qgis', '?'),
            info.get('qgis_minimum', '?'), info.get('version_check', '?'))
        keys = [(key, info[key]) for key in ('modules', 'findings', 'seeds') if key in info]
        return text, keys
    if name == 'package':
        parts = []
        if info.get('sha256'):
            parts.append('sha256 %s' % info['sha256'])
        if 'entries' in info:
            sizes = (info['entries'], info.get('files', '?'), info.get('dirs', '?'))
            parts.append('%s entries (%s files, %s dirs)' % sizes)
        if info.get('fiberq_commit'):
            parts.append('fiberq/ commit %s' % info['fiberq_commit'])
        if 'qm_warnings' in info:
            parts.append('%s .qm warnings' % info['qm_warnings'])
        if info.get('zip_matches_tree') == 'no':
            parts.append('zip_matches_tree=no')
        if stage.status.get('dist'):
            parts.append('dist: %s' % stage.status['dist'])
        if info.get('failed') and info['failed'] != 'none':
            parts.append('failed: %s' % info['failed'])
        keys = [(key, info[key]) for key in ('entries', 'files') if key in info]
        return '; '.join(parts), keys
    if name == 'release-check':
        parts = ['config.ini %s' % info.get('config_ini', '?'),
                 'GenAI headings %s' % info.get('genai_headings', '?')]
        assisted = info.get('assisted_by', '?')
        if assisted == 'listed':
            parts.append('Assisted-by: %s of %s commits since %s lack it (%s of them merges)' % (
                info.get('commits_without_trailer', '?'), info.get('commits', '?'), info.get('since', '?'),
                info.get('merges_among_them', '?')))
        else:
            parts.append('Assisted-by: %s' % assisted)
        keys = [(key, info[key]) for key in ('commits_without_trailer', 'merges_among_them') if info.get(key)]
        return '; '.join(parts), keys
    return '; '.join('%s=%s' % (key, value) for key, value in sorted(info.items())), []


def failure_lines(stage, run_dir):
    """The Failures entry of a red stage."""
    lines = ['### %s: %s' % (stage.name, one_line(stage.reason()) or stage.shown()), '']
    lines.append('- log: %s' % code(os.path.join(run_dir, stage.name + '.log')))
    if JUNIT_STAGE.fullmatch(stage.name):
        if stage.junit is None:
            if stage.has_junit:
                lines.append('- junit.xml is unreadable')
            else:
                lines.append('- no junit.xml')
        else:
            bad = sorted(test_id for test_id, status in case_status(stage.junit[1]).items()
                         if status in ('failed', 'error'))
            lines.append('- failing tests: %d' % len(bad))
            for test_id in bad[:LISTED]:
                lines.append('  - %s' % code(test_id))
            if len(bad) > LISTED:
                lines.append('  - ... and %d more (see junit.xml)' % (len(bad) - LISTED))
    elif stage.name == 'release-check':
        for line in read_lines(os.path.join(stage.out, 'release-check.txt'))[:LISTED]:
            lines.append('- %s' % one_line(line))
    elif stage.name == 'qt6':
        found = read_lines(os.path.join(stage.out, 'qt6-fiberq.txt'))
        for line in found[:LISTED]:
            lines.append('- %s' % code(line))
    if stage.info.get('failed') and stage.info['failed'] != 'none':
        lines.append('- failed checks: %s' % one_line(stage.info['failed']))
    lines.append('')
    return lines


def header_warnings(run, stages, overrides):
    """The WARNING lines of the header: dist/ kept another build, a zip of committed fiberq/ only, image
    overrides, .qm warnings."""
    found = []
    pkg = stages.get('package')
    if pkg is not None:
        dist = pkg.status.get('dist', '')
        if dist.startswith('kept:'):
            found.append('WARNING: dist/ was left as it is (%s); this build is in package/ of the run folder.'
                         % dist[len('kept:'):].strip())
        if pkg.info.get('zip_matches_tree') == 'no':
            found.append('WARNING: the zip holds committed fiberq/ only (commit %s), not the working tree.'
                         % pkg.info.get('fiberq_commit', '?'))
        for line in read_lines(os.path.join(pkg.out, 'qm-warnings.txt')):
            if line.startswith('WARNING'):
                found.append(one_line(line))
            else:
                found.append('WARNING: %s' % one_line(line))
    for role in overrides:
        found.append('WARNING: image override for %s: %s (CI_IMAGE_%s); such a run never authorizes a tag.'
                     % (role, run.get('image.' + role, '?'), role.upper()))
    return found


def summary():
    cin = os.environ.get('CI_IN', '')
    cout = os.environ.get('CI_OUT', '')
    if not cin or not cout or not os.path.isdir(cout):
        say('summary reads $CI_IN and writes into the folder $CI_OUT; ci/run-all.sh sets both')
        return 2
    run = read_kv(os.path.join(cin, 'run.txt'))
    if run is None:
        say('no run.txt in %s' % cin)
        return 1
    names = run.get('stages', '').split()
    if not names:
        say('run.txt has no stages= (or lists none); the stage list comes from there')
        return 1
    for name in names:
        if not STAGE_NAME.fullmatch(name):
            say('run.txt names a bad stage %r' % name)
            return 1
    skip_fails = run.get('set') == 'release' or run.get('strict') == 'yes'
    stages = [Stage(cin, name) for name in names]
    by_name = dict((stage.name, stage) for stage in stages)
    result = 'pass'
    red = []
    skips = []
    for stage in stages:
        if stage.verdict == 'skip':
            skips.append(stage.name)
        if stage.verdict == 'pass':
            continue
        if stage.verdict == 'skip' and not skip_fails:
            continue
        red.append(stage)
        result = 'fail'
    recorded = run.get('run_result')
    if recorded != result:
        say('the stages give run result %s, but run.txt has run_result=%s'
            % (result, '(none)' if recorded is None else recorded))
        return 1

    host = run.get('mode', 'host') == 'host'
    run_dir = run.get('run_dir', '')
    roles = sorted(key[len('image.'):] for key in run if key.startswith('image.'))
    overrides = [role for role in roles if run.get('image_override.' + role) == 'yes']
    finished = utc_now()
    counted = dict((stage.name, stage_counts(stage)) for stage in stages)

    if result == 'pass':
        shown = '**PASS**'
        if skips:
            shown += ' (skipped: %s)' % ', '.join(skips)
    else:
        shown = '**FAIL**: %d of %d stages (%s)' % (len(red), len(stages), ', '.join(s.name for s in red))
    commit = run.get('commit', '')
    if run.get('ref'):
        commit += ' (--ref %s)' % run['ref']
    lines = ['# Pipeline run %s' % run.get('run', '?'), '', '| | |', '|---|---|']
    rows = (
        ('result', shown),
        ('set', run.get('set', '')),
        ('only', run.get('only') or '(full set)'),
        ('strict', run.get('strict', 'no')),
        ('commit', commit),
        ('root tree', run.get('root_tree', '')),
        ('fiberq/ tree', run.get('fiberq_tree', '')),
        ('tests/ tree', run.get('tests_tree', '')),
        ('ci/ tree (tested)', run.get('ci_tree', '')),
        ('ci/ tree (runner)', run.get('runner_ci_tree', '')),
        ('dirty / runner_dirty', '%s / %s' % (run.get('dirty', '?'), run.get('runner_dirty', '?'))),
        ('shallow', run.get('shallow', '')),
        ('mode', run.get('mode', '')),
        ('engine', run.get('engine', '')),
        ('host', run.get('host', '')),
        ('git', run.get('git', '')),
        ('started (UTC)', run.get('started', '')),
        ('finished (UTC)', finished),
        ('container user' if host else 'user', run.get('user', '')),
    )
    for key, value in rows:
        lines.append('| %s | %s |' % (key, value if key == 'result' else cell(value)))
    lines.append('')
    for line in header_warnings(run, by_name, overrides):
        lines.extend([line, ''])

    lines.extend(['## Images', ''])
    if roles:
        lines.extend(['| role | reference | stages | override |', '|---|---|---|---|'])
        for role in roles:
            used = [name for name in names + ['summary'] if role_of(name) == role]
            flag = 'yes' if role in overrides else 'no'
            row = (role, code(run.get('image.' + role, '')), cell(', '.join(used)), flag)
            lines.append('| %s | %s | %s | %s |' % row)
    elif host:
        lines.append('No images recorded in run.txt.')
    else:
        lines.append('In place: the stages ran in this environment (Python %s), without images, each with its own'
                     ' HOME (stages/<stage>/work/home).' % run.get('python', '?'))
    lines.append('')

    lines.extend(['## Stages', '', '| stage | result | counts | time | reason |', '|---|---|---|---|---|'])
    for stage in stages:
        seconds = stage.status.get('seconds', '')
        took = '%s s' % seconds if seconds else ''
        row = (stage.name, stage.shown(), cell(counted[stage.name][0]), cell(took), cell(stage.reason()))
        lines.append('| %s | %s | %s | %s | %s |' % row)
    lines.append('')

    lines.extend(['## Tools', ''])
    keys = {}
    for name in names:
        key = run.get('deps.' + name)
        if key:
            keys.setdefault(key, []).append(name)
    if keys:
        lines.extend(['| deps key | stages | pinned packages |', '|---|---|---|'])
        for key in sorted(keys):
            freeze = []
            for name in keys[key]:
                freeze = by_name[name].freeze
                if freeze:
                    break
            packages = ', '.join(freeze) if freeze else '(no freeze.txt)'
            lines.append('| %s | %s | %s |' % (code(key), cell(', '.join(keys[key])), cell(packages)))
    else:
        lines.append('No stage of this run uses pinned tools.')
    lines.append('')

    zip_name = ''
    zip_sha = ''
    dist = ''
    fiberq_commit = ''
    pkg = by_name.get('package')
    lines.extend(['## Package', ''])
    if pkg is None:
        lines.append('The package stage did not run.')
    else:
        dist = pkg.status.get('dist', '')
        fiberq_commit = pkg.info.get('fiberq_commit', '')
        if pkg.info.get('version'):
            zip_name = 'fiberq-%s.zip' % pkg.info['version']
        zip_sha = pkg.info.get('sha256', '')
        if zip_name and zip_sha:
            contents = 'fiberq-%s.contents.tsv' % pkg.info['version']
            count = len(read_lines(os.path.join(pkg.out, contents)))
            lines.extend(['| zip | sha256 | contents |', '|---|---|---|'])
            shown_contents = '%s: %d lines' % (contents, count) if count else 'none'
            row = (code(os.path.join(run_dir, 'package', zip_name)), code(zip_sha), cell(shown_contents))
            lines.append('| %s | %s | %s |' % row)
            if dist:
                lines.extend(['', 'dist/: %s' % one_line(dist)])
        else:
            lines.append('No zip: %s' % (pkg.reason() or pkg.shown()))
    lines.append('')

    lines.extend(['## Failures', ''])
    if red:
        for stage in red:
            lines.extend(failure_lines(stage, run_dir))
    else:
        lines.extend(['None.', ''])

    lines.extend(['## Slowest tests', ''])
    timed = [stage for stage in stages if JUNIT_STAGE.fullmatch(stage.name) and stage.junit is not None]
    if not timed:
        lines.extend(['No junit.xml in this run.', ''])
    for stage in timed:
        cases = sorted(stage.junit[1], key=lambda case: (-case[2], case[0]))[:SLOWEST]
        lines.extend(['### %s' % stage.name, '', '| seconds | test |', '|---:|---|'])
        for test_id, _status, seconds in cases:
            lines.append('| %.3f | %s |' % (seconds, code(test_id)))
        lines.append('')

    record = [
        ('run', run.get('run', '')),
        ('set', run.get('set', '')),
        ('only', run.get('only', '')),
        ('stages', ' '.join(names)),
        ('overrides', ','.join(overrides) if overrides else 'none'),
        ('result', result),
        ('mode', run.get('mode', '')),
        ('commit', run.get('commit', '')),
        ('ref', run.get('ref', '')),
        ('root_tree', run.get('root_tree', '')),
        ('dirty', run.get('dirty', '')),
        ('runner_dirty', run.get('runner_dirty', '')),
        ('shallow', run.get('shallow', '')),
        ('zip_sha256', zip_sha),
        ('zip_name', zip_name),
        ('fiberq_commit', fiberq_commit),
        ('dist', dist),
    ]
    record.extend(('stage.%s' % stage.name, stage.recorded()) for stage in stages)
    for stage in stages:
        record.extend(('count.%s.%s' % (stage.name, key), value) for key, value in counted[stage.name][1])
    for key in ('engine', 'git', 'host', 'user', 'started'):
        record.append((key, run.get(key, '')))
    record.append(('finished', finished))
    result_txt = [
        'run_result=%s' % result,
        'stages=%d' % len(stages),
        'failed=%s' % (' '.join(stage.name for stage in red) or 'none'),
        'skips=%s' % (' '.join(skips) or 'none'),
    ]
    try:
        write_new(os.path.join(cout, 'summary.md'), lines)
        write_new(os.path.join(cout, 'record.txt'), ['%s=%s' % (key, one_line(value)) for key, value in record])
        write_new(os.path.join(cout, 'result.txt'), result_txt)
    except OSError as exc:
        say(str(exc))
        return 2
    sys.stdout.write('report.py: summary of %d stages, run result %s\n' % (len(stages), result))
    return 0


def run_folder(path):
    """(run.txt keys, stage names) of a run folder, or None when run.txt has no stages=."""
    run = read_kv(os.path.join(path, 'run.txt'))
    if run is None or 'stages' not in run:
        return None
    return run, run['stages'].split()


def stage_image(path, run, stage):
    """The image a run used for <stage>: image= of its status, else image.<role> of run.txt."""
    _verdict, keys = read_status(os.path.join(path, 'stages', stage, 'status'))
    if keys.get('image'):
        return keys['image']
    return run.get('image.' + role_of(stage), '')


def compare(old, new, outdir, wanted):
    if not os.path.isdir(outdir):
        say('no folder %s' % outdir)
        return 2
    runs = []
    for which, path in (('old', old), ('new', new)):
        found = run_folder(path)
        if found is None:
            say('the %s run has no run.txt with stages= (not a run folder of ci/run-all.sh)' % which)
            return 2
        runs.append(found)
    (old_run, old_names), (new_run, new_names) = runs

    def junit_path(root, stage):
        return os.path.join(root, 'stages', stage, 'out', 'junit.xml')

    with_junit = [name for name in old_names if os.path.isfile(junit_path(old, name))]
    if wanted:
        compared = []
        for name in wanted.split(','):
            if not name:
                continue
            if not STAGE_NAME.fullmatch(name):
                say('bad stage name %r' % name)
                return 2
            if name not in with_junit:
                say('%s has no junit.xml in the old run' % name)
                return 2
            if name not in compared:
                compared.append(name)
        if not compared:
            say('no stage named in %r' % wanted)
            return 2
        left_out = [name for name in with_junit if name not in compared]
    else:
        compared = with_junit
        left_out = []
        if not compared:
            say('nothing to compare: no stage of the old run has a junit.xml')
            return 2
    no_junit = [name for name in old_names if name not in with_junit]

    lost = {}
    gained = {}
    failing = {}
    missing = []
    passes = {}
    rows = []
    for name in compared:
        old_read = junit_read(junit_path(old, name))
        if old_read is None:
            say('the junit.xml of %s in the old run cannot be read' % name)
            return 2
        old_cases = case_status(old_read[1])
        passed = sorted(test_id for test_id, status in old_cases.items() if status == 'passed')
        passes[name] = len(passed)
        new_read = None
        if name in new_names:
            new_read = junit_read(junit_path(new, name))
        if new_read is None:
            missing.append(name)
            lost[name] = [(test_id, 'absent') for test_id in passed]
            gained[name] = []
            failing[name] = []
        else:
            new_cases = case_status(new_read[1])
            lost[name] = [(test_id, new_cases.get(test_id, 'absent')) for test_id in passed
                          if new_cases.get(test_id) != 'passed']
            gained[name] = sorted((test_id, new_cases[test_id]) for test_id in set(new_cases) - set(old_cases))
            failing[name] = now_failing(old_cases, new_cases)
        old_image = stage_image(old, old_run, name)
        new_image = stage_image(new, new_run, name)
        rows.append((name, old_image, new_image))

    total_lost = sum(len(found) for found in lost.values())
    total_gained = sum(len(found) for found in gained.values())
    total_failing = sum(len(found) for found in failing.values())
    lines = ['# JUnit compare', '', '| | old run | new run |', '|---|---|---|']
    for key in ('run', 'commit', 'ref', 'set', 'only', 'mode', 'started'):
        lines.append('| %s | %s | %s |' % (key, cell(old_run.get(key, '')), cell(new_run.get(key, ''))))
    lines.extend(['', '## Stages compared', '',
                  '| stage | old passes | lost | now failing | new ids | old image | new image |',
                  '|---|---|---|---|---|---|---|'])
    for name, old_image, new_image in rows:
        mark = ''
        if old_image != new_image:
            mark = ' (differs)'
        new_cell = code(new_image) + mark
        if name in missing:
            new_cell = 'not run or no junit.xml'
        row = (name, passes[name], len(lost[name]), len(failing[name]), len(gained[name]), code(old_image), new_cell)
        lines.append('| %s | %d | %d | %d | %d | %s | %s |' % row)
    lines.append('')
    if left_out:
        lines.extend(['Left out by --stages (they have a junit.xml in the old run): %s' % ', '.join(left_out), ''])
    if no_junit:
        lines.extend(['Not compared, no junit.xml in the old run: %s' % ', '.join(no_junit), ''])
    differ = [name for name, old_image, new_image in rows if old_image != new_image and name not in missing]
    if differ:
        lines.extend(['The runs used different images for: %s. A compare across versions needs the same digests.'
                      % ', '.join(differ), ''])

    lines.extend(['## Lost', ''])
    if total_lost == 0 and not missing:
        lines.extend(['None: every test that passed in the old run passes in the new one.', ''])
    for name in compared:
        if name in missing:
            lines.extend(['### %s: not run or no junit.xml in the new run' % name, '',
                          'All %d passes of the old run count as lost.' % passes[name], ''])
        elif lost[name]:
            lines.extend(['### %s' % name, ''])
        else:
            continue
        for test_id, status in lost[name]:
            lines.append('- %s (%s)' % (code(test_id), status))
        lines.append('')

    lines.extend(['## Now failing (skipped or absent in the old run, failed or errored in the new one)', ''])
    if total_failing == 0:
        lines.extend(['None.', ''])
    for name in compared:
        if not failing[name]:
            continue
        lines.extend(['### %s' % name, ''])
        for test_id, status in failing[name]:
            lines.append('- %s (%s)' % (code(test_id), status))
        lines.append('')

    lines.extend(['## New ids (in the new run, not in the old one)', ''])
    if total_gained == 0:
        lines.extend(['None.', ''])
    for name in compared:
        if not gained[name]:
            continue
        lines.extend(['### %s' % name, ''])
        for test_id, status in gained[name]:
            lines.append('- %s (%s)' % (code(test_id), status))
        lines.append('')
    verdict = 'no test lost'
    if total_lost or missing:
        verdict = '%d lost' % total_lost
        if missing:
            verdict += '; not run or no junit.xml in the new run: %s' % ', '.join(missing)
    if total_failing:
        verdict += '; %d now failing (listed, not counted as lost)' % total_failing
    plural = '' if len(compared) == 1 else 's'
    lines.extend(['Result: %s (%d stage%s compared).' % (verdict, len(compared), plural)])
    result_txt = [
        'compared=%s' % ','.join(compared),
        'left_out=%s' % (','.join(left_out) or 'none'),
        'lost=%d' % total_lost,
        'now_failing=%d' % total_failing,
        'new_ids=%d' % total_gained,
        'missing=%s' % (','.join(missing) or 'none'),
    ]
    try:
        write_new(os.path.join(outdir, 'compare.md'), lines)
        write_new(os.path.join(outdir, 'result.txt'), result_txt)
    except OSError as exc:
        say(str(exc))
        return 2
    sys.stdout.write('report.py: compare: %s\n' % verdict)
    if total_lost or missing:
        return 1
    return 0


def secrets(path):
    try:
        with open(path, 'rb') as fh:
            data = json.loads(fh.read().decode('utf-8'))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        say('%s: %s' % (path, exc))
        return 2
    results = None
    if isinstance(data, dict):
        results = data.get('results')
    if not isinstance(results, dict):
        say('%s: no "results" object' % path)
        return 2
    count = 0
    for name, found in results.items():
        if name.endswith(SECRET_SKIP):
            continue
        if not isinstance(found, list):
            say('%s: the results of %s are not a list' % (path, name))
            return 2
        count += len(found)
    sys.stdout.write('%d\n' % count)
    return 0


def main(argv):
    if len(argv) == 2 and argv[1] in ('-h', '--help'):
        sys.stdout.write(USAGE)
        return 0
    if len(argv) == 2 and argv[1] == 'summary':
        return summary()
    if len(argv) in (5, 6) and argv[1] == 'compare':
        wanted = ''
        if len(argv) == 6:
            wanted = argv[5]
        return compare(argv[2], argv[3], argv[4], wanted)
    if len(argv) == 3 and argv[1] == 'secrets':
        return secrets(argv[2])
    sys.stderr.write(USAGE)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
