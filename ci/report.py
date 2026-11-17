# SPDX-License-Identifier: GPL-3.0-or-later
# ci/report.py - the run record (summary.md, record.txt), the JUnit compare of two runs, the detect-secrets count,
# the pure stage's counts, the coverage table and the app stages' JUnit record.
# Usage (stdlib only, Python 3.8 or later):
#   python3 -I ci/report.py summary
#       reads $CI_IN/run.txt and $CI_IN/stages/, writes summary.md, record.txt and result.txt into $CI_OUT
#   python3 -I ci/report.py compare <old run> <new run> <out-dir> [<stage,...>]
#       compares the junit.xml files of two run folders, writes compare.md and result.txt into <out-dir>
#   python3 -I ci/report.py secrets <detect-secrets JSON>
#       prints the number of findings, counted as the plugins.qgis.org scanner counts them
#   python3 -I ci/report.py pure-pin <ci/pure-count>
#       checks a ci/pure-count file and prints its total and its number of test files as result.txt lines
#   python3 -I ci/report.py pure <junit.xml> <pure-files.tsv> <ci/pure-count>
#       prints the pure stage's counts as result.txt lines: files picked and left out, tests deselected, the
#       stage's own skips and the pure items (the tests run, less those skips), and checks each test file's pure
#       items against its line in ci/pure-count
#   python3 -I ci/report.py coverage <coverage JSON> <out-dir>
#       writes coverage-core.tsv and coverage-core.md (the core-logic modules) into <out-dir>, prints the totals
#       as result.txt lines
#   python3 -I ci/report.py app-junit <suite> <junit.xml> (<start> <dir> <exit|none> <seconds> <limit>)...
#       writes the app stage's junit.xml from each QGIS start's records (tests/app/runner.py's report.json, the
#       startup guard's guard.json, steps.jsonl), prints each start's code, then the counts, as result.txt lines
# ci/run-all.sh runs "summary" in the python image of ci/legs (in place: with this Python), ci/compare.sh runs
# "compare" there, ci/lint.sh runs "secrets", ci/test.sh runs "pure-pin", "pure" and "coverage" in their stages,
# ci/app-smoke.sh runs "app-junit" in the app stages.
# A stage's verdict is its status file: exactly one result= line, pass, fail or skip; anything else is invalid and
# counts as a failure, as in ci/common.sh. A skip counts as a failure in a release run, and in a run with --strict
# (strict=yes in run.txt).
# Exit: 0 done (summary: whatever the run's result is; app-junit: junit.xml written, whatever the starts did);
#       1 summary: run.txt has no stages=, or its run_result= differs from the stages' verdicts; compare: a test was
#       lost, or a compared stage is missing from the new run; pure: a test file's pure items differ from
#       ci/pure-count; coverage: the JSON holds no core-logic module; 2 usage, an input that cannot be read or is
#       not valid, (compare) nothing to compare, or (app-junit) junit.xml exists already or cannot be written.

import datetime
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

SECRET_SKIP = ('.pyc', '.pyo', '.so', '.dll', '.exe')
STAGE_NAME = re.compile(r'[a-z0-9][a-z0-9-]*')
JUNIT_STAGE = re.compile(r'pure|test-[a-z0-9]+|app-[a-z0-9]+')
# a skip of the pure stage's own: a test that met a hidden module (conftest.py, FIBERQ_PURE=1)
PURE_SKIP = ('pure stage:', '(hidden in the pure stage)')
PURE_KINDS = ('picked', 'left_out', 'deselected')
# a line of ci/pure-count: a test file's pure items, then the file
PIN_LINE = re.compile(r'([1-9][0-9]*)[ \t]+(tests/[^ \t]+\.py)')
# core logic: the modules of these packages of fiberq/, without their __init__.py; the excluded ones (dead code, and
# the licence check of the Pro features) are listed with their note and left out of the in-scope total
CORE_PACKAGES = ('core', 'utils', 'models')
CORE_EXCLUDED = {
    'fiberq/core/config_manager.py': 'dead code',
    'fiberq/utils/layer_names.py': 'dead code',
    'fiberq/models/color_catalogs.py': 'dead code',
    'fiberq/core/license_manager.py': 'licence check of the Pro features',
}
SLOWEST = 25
LISTED = 50
LINT_CHECKS = (
    ('flake8', 'flake8', ''),
    ('bandit', 'Bandit', ''),
    ('detect_secrets', 'detect-secrets', ''),
    ('shellcheck', 'shellcheck', 'shellcheck_files'),
    ('flake8_ci', 'flake8 ci/', 'flake8_ci_files'),
    ('placeholders', 'placeholders', ''),
    ('wrappers', 'forge configs', ''),
)
CASE_RANK = {'passed': 0, 'skipped': 1, 'failed': 2, 'error': 3}
# app-junit: the formats of report.json it reads (its "runner" key). A new format of tests/app/runner.py is added
# here, never put in place of an earlier one, so that a --ref run of an older tree is still read
APP_FORMATS = (1,)
# app-junit: the checks of a start that show it installed and enabled the plugin; ci/app-smoke.sh runs the next
# start only when they passed (<start>_gate=yes). They count among the start's expected checks, declared or not, so
# a start whose records lack one never passes (the tested tree's check ids may drift from these under --ref)
APP_GATE = {'install': ('install.installed', 'install.enabled')}
APP_START = re.compile(r'[a-z0-9_]+')
APP_MESSAGE = 2000   # characters of a failure's message
APP_TEXT = 20000     # characters of a failure's text
APP_LOG_TAIL = 10    # message-log lines in a failed run.ended
# a character that XML 1.0 cannot hold (Char: tab, LF, CR, U+0020-U+D7FF, U+E000-U+FFFD, U+10000-U+10FFFF)
XML_BAD = re.compile('[^\t\n\r\u0020-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]')

USAGE = """\
usage: report.py summary
       report.py compare <old run> <new run> <out-dir> [<stage,...>]
       report.py secrets <detect-secrets JSON>
       report.py pure-pin <ci/pure-count>
       report.py pure <junit.xml> <pure-files.tsv> <ci/pure-count>
       report.py coverage <coverage JSON> <out-dir>
       report.py app-junit <suite> <junit.xml> (<start> <dir> <exit|none> <seconds> <limit>)...
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
pure-pin prints pure_count= (the total) and pure_count_files= of a ci/pure-count file: "#" lines, blank lines,
         and one "<number> tests/<file>.py" line per test file, the number 1 or more. It exits 2 on any other
         line, a file listed twice, or no file.
pure     prints files=, files_left_out=, deselected=, pure_skips=, pure_items=, pure_files= and pure_differ=
         from the pure stage's junit.xml and pure-files.tsv (conftest.py writes it). A pure skip is one whose
         reason holds "pure stage:" or "(hidden in the pure stage)"; pure_items is the junit tests less the pure
         skips, counted per test file. It exits 1, naming each file, when a file's pure items differ from its
         line in ci/pure-count, or a file has pure items and no line, or a line names a file without them.
coverage writes coverage-core.tsv and coverage-core.md, one row per core-logic module (fiberq/core, utils and
         models, without __init__.py), and prints the totals; it exits 1 when the JSON holds no such module.
app-junit one group per QGIS start of an app stage, in order: its name, its records folder, its exit status (none
         when it did not run), how long it ran and its time limit, in seconds. It reads each start's report.json
         (every format in APP_FORMATS), guard.json and steps.jsonl, and writes the new <junit.xml>: one test case
         app.<start>::<check id> per check, a failure when it failed, then app.<start>::run.ended, which fails when
         the start ended other than with exit 0 or 1, when its exit status is not the report's, or when a check the
         report declared ("expected"), or one of the start's APP_GATE checks, did not run, and is skipped for a
         start that did not run. It prints <start>_code= for each start (and <start>_gate= for those in APP_GATE)
         before it writes the file, then checks=, checks_failed=, checks_skipped= and, per start, _checks, _failed,
         _failed_ids, _report, _report_exit, _verdict and _reason. A start's code comes from its evidence: 0 a raw 0
         whose report passed; the raw 1, 3, 4 or 5 when the report ended with it; 3 a raw 3 with guard.json; 4 a
         raw 124 or 137 at or past the time limit; else 6; 0 for a start that did not run. It exits 0 once the file
         is written.
Exit: 0 done; 1 see above; 2 usage, or an input that cannot be read (app-junit: or junit.xml cannot be written).
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
    if stage == 'test-coverage':
        return '42'
    if stage.startswith('test-') and stage != 'test-local':
        return stage[len('test-'):]
    if stage.startswith('app-'):
        return stage[len('app-'):]
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
        # in place, no junit.xml and skipped=: a test leg off its own QGIS, test-coverage, or an app stage
        if not stage.has_junit and info.get('skipped'):
            text = 'skipped: %s' % info['skipped']
        extra = []
        if name == 'pure' and 'pure_items' in info:
            text_pure = '%s files picked (%s left out), %s tests deselected; pure items %s in %s files' % (
                info.get('files', '?'), info.get('files_left_out', '?'), info.get('deselected', '?'),
                info['pure_items'], info.get('pure_files', '?'))
            text_pure += ' (ci/pure-count %s in %s files)' % (
                info.get('pure_count', '?'), info.get('pure_count_files', '?'))
            if to_int(info.get('pure_differ')):
                text_pure += '; files that differ: %s' % info['pure_differ']
            extra.append(text_pure)
            keys = keys + [(key, info[key]) for key in ('files', 'deselected', 'pure_items', 'pure_count')
                           if key in info]
        if name.startswith('app-') and 'zip_entries' in info:
            parts = ['zip %s entries' % info['zip_entries']]
            for start in ('install', 'workflow'):
                exit_code = info.get(start + '_exit', '')
                if exit_code in ('', 'none'):
                    parts.append('%s not run' % start)
                elif info.get(start + '_verdict') == 'pass' and exit_code == '0':
                    parts.append('%s pass (%s s)' % (start, info.get(start + '_seconds', '?')))
                else:
                    parts.append('%s exit %s (%s s)' % (start, exit_code, info.get(start + '_seconds', '?')))
            parts.append('%s screenshots' % info.get('screenshots', '?'))
            extra.append('; '.join(parts))
            keys = keys + [(key, info[key]) for key in ('zip_entries', 'install_exit', 'workflow_exit', 'screenshots')
                           if key in info]
        if name == 'test-coverage' and 'core_percent' in info:
            extra.append('core logic %s%% of %s statements (%s modules; in scope %s%%); %s data files, %s '
                         'measured processes' % (
                             info['core_percent'], info.get('core_statements', '?'), info.get('core_modules', '?'),
                             info.get('scope_percent', '?'), info.get('data_files', '?'),
                             info.get('processes_measured', '?')))
            keys = keys + [(key, info[key]) for key in ('core_percent', 'core_statements', 'scope_percent')
                           if key in info]
        for key, label in (('python', 'Python'), ('qgis', 'QGIS'), ('uid', 'uid')):
            if info.get(key):
                shown = '%s %s' % (label, info[key])
                if key == 'qgis' and name == 'pure' and info[key] != 'none':
                    shown += ' (hidden by the stage)'
                extra.append(shown)
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


def read_pin(path):
    """{test file: pure items} of a ci/pure-count file, or a str that says what is wrong with it."""
    try:
        text = read_text(path)
    except OSError as exc:
        return str(exc)
    pins = {}
    for number, line in enumerate(text.split('\n'), 1):
        line = line.rstrip()
        if not line or line.startswith('#'):
            continue
        found = PIN_LINE.fullmatch(line)
        if not found:
            return '%s:%d: not "<number> tests/<file>.py" (the number 1 or more): %s' % (path, number, line)
        if found.group(2) in pins:
            return '%s:%d: %s is listed twice' % (path, number, found.group(2))
        pins[found.group(2)] = int(found.group(1))
    if not pins:
        return '%s: no "<number> tests/<file>.py" line' % path
    return pins


def pure_pin(path):
    """The total and the number of test files of a ci/pure-count file, as result.txt lines on stdout."""
    pins = read_pin(path)
    if isinstance(pins, str):
        say(pins)
        return 2
    sys.stdout.write('pure_count=%d\npure_count_files=%d\n' % (sum(pins.values()), len(pins)))
    return 0


def pure_counts(junit_path, files_path, pin_path):
    """The pure stage's counts, as result.txt lines on stdout; each test file's pure items checked against its line
    in ci/pure-count, every difference on stderr."""
    pins = read_pin(pin_path)
    if isinstance(pins, str):
        say(pins)
        return 2
    try:
        root = ET.parse(junit_path).getroot()
        rows = [line.split('\t') for line in read_text(files_path).split('\n') if line]
    except (OSError, ET.ParseError, ValueError) as exc:
        say(str(exc))
        return 2
    if any(len(row) != 3 or row[0] not in PURE_KINDS for row in rows):
        say('%s: every line holds picked, left_out or deselected, a name and a reason, tab-separated' % files_path)
        return 2
    kinds = [row[0] for row in rows]
    # each test file of the record, by its junit name: tests/test_x.py is tests.test_x
    reason = dict((row[1], row[2]) for row in rows if row[0] != 'deselected')
    dotted = dict((name[:-len('.py')].replace('/', '.'), name) for name in reason if name.endswith('.py'))
    # one per test: a test's subtests add to its suite's tests= but not to its test cases
    tests = sum(1 for _case in root.iter('testcase'))
    own = 0
    found = {}
    for case in root.iter('testcase'):
        # the reason is in the message of a test's skip, in the text of a whole file's ("collection skipped")
        said = ' '.join('%s %s' % (child.get('message', ''), child.text or '') for child in case
                        if child.tag == 'skipped')
        if any(mark in said for mark in PURE_SKIP):
            own += 1
            continue
        where = case.get('classname') or case.get('name', '')   # a whole file's skip has no classname
        owners = [module for module in dotted if where == module or where.startswith(module + '.')]
        if not owners:
            say('%s: %s is in no test file of %s' % (junit_path, where, files_path))
            return 2
        owner = dotted[max(owners, key=len)]
        found[owner] = found.get(owner, 0) + 1
    if own + sum(found.values()) != tests:
        say('%s: %d test cases, but %d tests' % (junit_path, own + sum(found.values()), tests))
        return 2
    differ = []
    for name in sorted(set(found) | set(pins)):
        have, want = found.get(name, 0), pins.get(name, 0)
        if have == want:
            continue
        plural = '' if have == 1 else 's'
        if name not in pins:
            text = '%s: %d pure item%s, and no line in ci/pure-count' % (name, have, plural)
        else:
            text = '%s: %d pure item%s, ci/pure-count says %d' % (name, have, plural, want)
        if name not in reason:
            text += ' (no such test file)'
        elif reason[name]:
            text += ' (left out: %s)' % reason[name]
        differ.append((have < want, text))
    for key, value in (('files', kinds.count('picked')), ('files_left_out', kinds.count('left_out')),
                       ('deselected', kinds.count('deselected')), ('pure_skips', own),
                       ('pure_items', tests - own), ('pure_files', len(found)), ('pure_differ', len(differ))):
        sys.stdout.write('%s=%d\n' % (key, value))
    for _fewer, text in differ:
        say('pure: %s' % text)
    if any(fewer for fewer, _text in differ):
        say('pure: fewer pure items in a file: a test there stopped importing without QGIS, was removed or renamed, '
            'or now needs QGIS, or a skip that depends on the machine comes before its QGIS import '
            '(pure-files.tsv lists every file picked or left out, with the reason). The total in ci/pure-count '
            'may only rise: a change that lowers it needs the maintainer\'s approval in its pull request')
    if any(not fewer for fewer, _text in differ):
        say('pure: more pure items in a file, or a new file: set its line in ci/pure-count to its count in the '
            'same change')
    if differ:
        return 1
    return 0


def percent(covered, statements):
    if not statements:
        return 'n/a'
    return '%.1f' % (100.0 * covered / statements)


def coverage_table(json_path, outdir):
    """coverage-core.tsv and coverage-core.md from coverage's JSON report; the totals as result.txt lines."""
    try:
        with open(json_path, 'rb') as fh:
            files = json.loads(fh.read().decode('utf-8'))['files']
        rows = []
        for name in sorted(files):
            parts = name.replace('\\', '/').split('/')
            if len(parts) != 3 or parts[0] != 'fiberq' or parts[1] not in CORE_PACKAGES:
                continue
            if not parts[2].endswith('.py') or parts[2] == '__init__.py':
                continue
            summ = files[name]['summary']
            module = '/'.join(parts)
            rows.append((module, int(summ['num_statements']), int(summ['covered_lines']),
                         CORE_EXCLUDED.get(module, '')))
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
        say('%s: %s' % (json_path, exc))
        return 2
    if not rows:
        say('%s: no core-logic module (fiberq/core, utils or models)' % json_path)
        return 1
    scope = [row for row in rows if not row[3]]
    totals = []
    for label, chosen in (('in scope (%d modules)' % len(scope), scope), ('core logic (%d modules)' % len(rows), rows)):
        totals.append((label, sum(row[1] for row in chosen), sum(row[2] for row in chosen)))
    tsv = ['module\tstatements\tcovered\tmissed\tpercent\tnote']
    md = ['| module | statements | covered | percent | note |', '|---|---:|---:|---:|---|']
    for module, statements, covered, note in rows:
        cover = percent(covered, statements)
        tsv.append('%s\t%d\t%d\t%d\t%s\t%s' % (module, statements, covered, statements - covered, cover, note))
        md.append('| `%s` | %d | %d | %s | %s |' % (module[len('fiberq/'):], statements, covered, cover, note or '-'))
    for label, statements, covered in totals:
        cover = percent(covered, statements)
        tsv.append('TOTAL %s\t%d\t%d\t%d\t%s\t' % (label, statements, covered, statements - covered, cover))
        md.append('| **%s** | %d | %d | **%s** | |' % (label, statements, covered, cover))
    never = [row[0][len('fiberq/'):] for row in rows if row[2] == 0]
    md.extend(['', 'Never run (no statement covered): %d modules%s' % (
        len(never), ': ' + ', '.join('`%s`' % name for name in never) if never else '')])
    try:
        write_new(os.path.join(outdir, 'coverage-core.tsv'), tsv)
        write_new(os.path.join(outdir, 'coverage-core.md'), md)
    except OSError as exc:
        say(str(exc))
        return 2
    (_label, scope_st, scope_cov), (_label, core_st, core_cov) = totals
    for key, value in (('core_modules', len(rows)), ('core_statements', core_st), ('core_covered', core_cov),
                       ('core_percent', percent(core_cov, core_st)), ('scope_modules', len(scope)),
                       ('scope_statements', scope_st), ('scope_covered', scope_cov),
                       ('scope_percent', percent(scope_cov, scope_st)), ('core_never_run', len(never))):
        sys.stdout.write('%s=%s\n' % (key, value))
    return 0


def xml_safe(value, limit):
    """<value> as text that XML 1.0 can hold, at most <limit> characters: each character it cannot hold becomes a
    visible #xNN (as pytest's junit.xml writes it), before the text is cut."""
    text = XML_BAD.sub(lambda found: '#x%02X' % ord(found.group()), str(value))
    if len(text) > limit:
        return text[:limit - 3] + '...'
    return text


def app_json(value):
    """A recorded value as JSON text."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def app_is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def app_shape(report):
    """What is wrong with a report.json of format 1, or ''."""
    if not app_is_int(report.get('exit')):
        return 'its exit is not a whole number'
    checks = report.get('checks')
    if not isinstance(checks, list):
        return 'its checks are not a list'
    for check in checks:
        if not isinstance(check, dict):
            return 'a check is not an object'
        if not isinstance(check.get('id'), str) or not isinstance(check.get('ok'), bool):
            return 'a check has no id or no ok'
    expected = report.get('expected', [])
    if not isinstance(expected, list) or not all(isinstance(cid, str) for cid in expected):
        return 'its expected checks are not a list of ids'
    if not isinstance(report.get('windows', []), list):
        return 'its windows are not a list'
    if not isinstance(report.get('log', []), list):
        return 'its log is not a list'
    return ''


def app_report(folder):
    """(report, problem) of a start's report.json: (the report, '') when it is in a format of APP_FORMATS, else
    (None, what is wrong)."""
    path = os.path.join(folder, 'report.json')
    if not os.path.isfile(path):
        return None, 'no report.json'
    try:
        report = json.loads(read_text(path))
    except (OSError, ValueError) as exc:
        return None, 'report.json does not parse: %s' % one_line(exc)
    if not isinstance(report, dict):
        return None, 'report.json is not a JSON object'
    fmt = report.get('runner')
    if not app_is_int(fmt) or fmt not in APP_FORMATS:
        return None, 'report.json is runner format %s; this ci/ reads %d..%d' % (
            app_json(fmt), min(APP_FORMATS), max(APP_FORMATS))
    problem = app_shape(report)
    if problem:
        return None, 'report.json is not runner format %d: %s' % (fmt, problem)
    return report, ''


def app_guard(folder):
    """guard.json of a start, as a dict; None when there is none, or it does not parse."""
    try:
        guard = json.loads(read_text(os.path.join(folder, 'guard.json')))
    except (OSError, ValueError):
        return None
    if isinstance(guard, dict):
        return guard
    return None


def app_last_step(folder):
    """The step of the last line of steps.jsonl that parses; '' when there is none (a line cut short by a crash,
    or a missing file, is passed over)."""
    try:
        text = read_text(os.path.join(folder, 'steps.jsonl'))
    except OSError:
        return ''
    last = ''
    for line in text.split('\n'):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and isinstance(event.get('step'), str):
            last = event['step']
    return last


def app_log_tail(lines):
    """The last APP_LOG_TAIL message-log lines, one per line of text; none when <lines> is not a list (guard.json
    has no shape check)."""
    if not isinstance(lines, list):
        return []
    shown = []
    for entry in lines[-APP_LOG_TAIL:]:
        if isinstance(entry, dict):
            shown.append('[%s] %s: %s' % (entry.get('t', '?'), entry.get('tag', '?'), entry.get('message', '')))
    return shown


def app_start(name, folder, raw, seconds, limit, previous):
    """One start's test cases, code and keys, as a dict. <raw> is its exit status, None when it did not run;
    <previous> is the dict of the start before it, or None."""
    classname = 'app.' + name
    found = {'name': name, 'raw': raw, 'gate': None, 'report': 'none', 'report_exit': '', 'cases': []}
    if raw is None:
        why = 'not run'
        if previous is not None and previous['raw'] is None:
            why = 'not run: %s did not run' % previous['name']
        elif previous is not None and previous['gate'] == 'no':
            why = 'not run: FiberQ was not installed (%s ended with exit %s)' % (previous['name'], previous['raw'])
        elif previous is not None:
            why = 'not run: %s ended with exit %s' % (previous['name'], previous['raw'])
        found.update(code=0, verdict='none', reason=why, failed_ids=[])
        found['cases'].append((classname, 'run.ended', 0.0, 'skipped', why, ''))
        return found
    report, problem = app_report(folder)
    guard = app_guard(folder)
    if report is None:
        found['report'] = 'no' if problem == 'no report.json' else 'bad'
        if problem == 'no report.json':
            message = 'QGIS ended with exit %d and wrote no report.json' % raw
        else:
            message = 'QGIS ended with exit %d; %s' % (raw, problem)
        message += ' (last step: %s)' % (app_last_step(folder) or 'none recorded')
        extra = []
        if guard is not None:
            message += '; the startup guard ended QGIS (%s): %s' % (guard.get('kind', '?'), guard.get('title', ''))
            extra = ['', str(guard.get('text', ''))] + app_log_tail(guard.get('log_tail'))
        if raw in (124, 137):
            if seconds >= limit:
                message += '; stopped by its time limit (%d s)' % limit
            else:
                message += '; killed after %d s, before its time limit (%d s)' % (seconds, limit)
        found['cases'].append((classname, 'run.ended', 0.0, 'failure', message, '\n'.join([message] + extra)))
        passing = False
        reason = message
    else:
        found['report'] = 'yes'
        found['report_exit'] = report['exit']
        ran = set()
        failed = 0
        for check in report['checks']:
            ran.add(check['id'])
            took = to_float(check.get('seconds'))
            if check['ok']:
                found['cases'].append((classname, check['id'], took, 'passed', '', ''))
                continue
            failed += 1
            message = '%s: expected %s, seen %s' % (check.get('what') or check['id'], app_json(check.get('expected')),
                                                    app_json(check.get('seen')))
            found['cases'].append((classname, check['id'], took, 'failure', message, message))
        wanted = list(report.get('expected', []))
        wanted += [cid for cid in APP_GATE.get(name, ()) if cid not in wanted]
        missing = [cid for cid in wanted if cid not in ran]
        reason = one_line(report.get('exit_reason') or 'exit %d' % report['exit'])
        message = reason
        text = [reason]
        if report['exit'] == 3:
            windows = [w for w in report.get('windows') or [] if isinstance(w, dict) and w.get('kind') != 'expected']
            if windows:
                text += ['', '%s: %s' % (windows[-1].get('class', '?'), windows[-1].get('title', '')),
                         str(windows[-1].get('text', ''))]
                message += ': %s' % one_line(windows[-1].get('text', ''))[:300]
        if report.get('error'):
            lines = [line for line in str(report['error']).split('\n') if line.strip()]
            text += [''] + lines
            message += ' (%s)' % ' / '.join(line.strip() for line in lines[-3:])
        if raw != report['exit']:
            note = 'QGIS ended with exit %d, but the report says %d' % (raw, report['exit'])
            message += '; ' + note
            reason += '; ' + note
            text += ['', note]
        if missing:
            note = '%d expected check%s did not run' % (len(missing), '' if len(missing) == 1 else 's')
            message += '; %s: %s' % (note, ', '.join(missing))
            reason += '; ' + note
            text += ['', note + ':'] + missing
        text += [''] + app_log_tail(report.get('log'))
        ended = report['exit'] in (0, 1) and raw == report['exit'] and not missing
        if ended:
            found['cases'].append((classname, 'run.ended', 0.0, 'passed', '', ''))
        else:
            found['cases'].append((classname, 'run.ended', 0.0, 'failure', message, '\n'.join(text)))
        passing = report['exit'] == 0 and failed == 0 and not missing
        if name in APP_GATE:
            oks = dict((check['id'], check['ok']) for check in report['checks'])
            installed = report['exit'] in (0, 1) and all(oks.get(cid) is True for cid in APP_GATE[name])
            found['gate'] = 'yes' if installed else 'no'
    if name in APP_GATE and found['gate'] is None:
        found['gate'] = 'no'
    if raw == 0 and passing:
        code = 0
    elif report is not None and report['exit'] == raw and raw in (1, 3, 4, 5):
        code = raw
    elif raw == 3 and guard is not None:
        code = 3
    elif raw in (124, 137) and seconds >= limit:
        code = 4
    else:
        code = 6
    found.update(code=code, verdict='pass' if raw == 0 and passing else 'fail', reason=one_line(reason),
                 failed_ids=[case[1] for case in found['cases'] if case[3] == 'failure'])
    return found


def app_junit(suite, junit_path, groups):
    """The app stage's junit.xml from its starts' records, and its result.txt lines (see USAGE)."""
    # a record from elsewhere can hold a lone surrogate, which no encoding writes: a backslash escape instead
    sys.stdout.reconfigure(errors='backslashreplace')
    if not STAGE_NAME.fullmatch(suite):
        say('app-junit: bad suite name %r' % suite)
        return 2
    starts = []
    for at in range(0, len(groups), 5):
        name, folder, raw, seconds, limit = groups[at:at + 5]
        if not APP_START.fullmatch(name) or name in [start[0] for start in starts]:
            say('app-junit: a start is named [a-z0-9_]+, once: %r' % name)
            return 2
        if raw != 'none' and not raw.isdigit():
            say('app-junit: the exit status of %s is a whole number or none, not %r' % (name, raw))
            return 2
        if not seconds.isdigit() or not limit.isdigit():
            say('app-junit: the seconds and the time limit of %s are whole numbers: %r %r' % (name, seconds, limit))
            return 2
        starts.append((name, folder, None if raw == 'none' else int(raw), int(seconds), int(limit)))
    if os.path.lexists(junit_path):
        say('app-junit: %s exists; it writes a new file only' % junit_path)
        return 2
    results = []
    previous = None
    for name, folder, raw, seconds, limit in starts:
        previous = app_start(name, folder, raw, seconds, limit, previous)
        results.append(previous)
    for found in results:   # the codes first: ci/app-smoke.sh still has them if the file cannot be written
        sys.stdout.write('%s_code=%d\n' % (found['name'], found['code']))
        if found['gate'] is not None:
            sys.stdout.write('%s_gate=%s\n' % (found['name'], found['gate']))
    sys.stdout.flush()
    cases = [case for found in results for case in found['cases']]
    failures = sum(1 for case in cases if case[3] == 'failure')
    skipped = sum(1 for case in cases if case[3] == 'skipped')
    root = ET.Element('testsuites')
    tree = ET.SubElement(root, 'testsuite', {
        'name': suite, 'tests': str(len(cases)), 'failures': str(failures), 'errors': '0', 'skipped': str(skipped),
        'time': '%.3f' % sum(case[2] for case in cases)})
    for classname, name, took, kind, message, text in cases:
        case = ET.SubElement(tree, 'testcase', {'classname': xml_safe(classname, APP_MESSAGE),
                                                'name': xml_safe(name, APP_MESSAGE), 'time': '%.3f' % took})
        if kind == 'failure':
            child = ET.SubElement(case, 'failure', {'message': xml_safe(message, APP_MESSAGE)})
            child.text = xml_safe(text or message, APP_TEXT)
        elif kind == 'skipped':
            ET.SubElement(case, 'skipped', {'message': xml_safe(message, APP_MESSAGE)})
    try:
        with open(junit_path, 'xb') as fh:
            fh.write(ET.tostring(root, encoding='utf-8'))
    except OSError as exc:
        say('app-junit: %s' % exc)
        return 2
    lines = ['checks=%d' % len(cases), 'checks_failed=%d' % failures, 'checks_skipped=%d' % skipped]
    for found in results:
        name = found['name']
        lines += ['%s_checks=%d' % (name, len(found['cases'])),
                  '%s_failed=%d' % (name, len(found['failed_ids'])),
                  '%s_failed_ids=%s' % (name, ','.join(found['failed_ids'])),
                  '%s_report=%s' % (name, found['report']),
                  '%s_report_exit=%s' % (name, found['report_exit']),
                  '%s_verdict=%s' % (name, found['verdict']),
                  '%s_reason=%s' % (name, one_line(found['reason']))]
    sys.stdout.write('\n'.join(lines) + '\n')
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
    if len(argv) == 3 and argv[1] == 'pure-pin':
        return pure_pin(argv[2])
    if len(argv) == 5 and argv[1] == 'pure':
        return pure_counts(argv[2], argv[3], argv[4])
    if len(argv) == 4 and argv[1] == 'coverage':
        return coverage_table(argv[2], argv[3])
    if len(argv) >= 9 and (len(argv) - 4) % 5 == 0 and argv[1] == 'app-junit':
        return app_junit(argv[2], argv[3], argv[4:])
    sys.stderr.write(USAGE)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
