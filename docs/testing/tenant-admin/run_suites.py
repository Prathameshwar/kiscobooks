"""Run existing tenant-admin UI and service suites; never change application code."""
from __future__ import annotations
import argparse
import concurrent.futures
import csv
import datetime as dt
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICE_PATTERNS = {
    'identity': ['test_api_*.py', 'test_company*.py', 'test_department*.py', 'test_role*.py', 'test_user*.py', 'test_session*.py', 'test_tenant*.py', 'test_catalog_authorizations.py', 'test_catalog_enrollment.py', 'test_accounting_policy_api.py', 'test_access*.py', 'test_gap_custom*.py', 'test_gap_children.py', 'test_gap_invitations.py', 'test_field_policy_domain.py'],
    'catalog': ['test_*api*.py', 'test_*configuration*.py', 'test_*defaults*.py', 'test_*readiness*.py', 'test_*authorization*.py', 'test_*field*.py', 'test_*import*.py', 'test_*hierarchy*.py', 'test_*lifecycle*.py'],
    'accounting': ['test_*api*.py', 'test_*configuration*.py', 'test_*setup*.py', 'test_*authorization*.py', 'test_*completion*.py', 'test_*opening*.py', 'test_*import*.py', 'test_*fiscal*.py'],
    'reports': ['test_*api*.py', 'test_*security*.py', 'test_*definition*.py', 'test_*financial*.py', 'test_*export*.py'],
    'notification': ['test_management.py', 'test_configuration*.py', 'test_security.py', 'test_*tenant*.py'],
    'design': ['test_*api*.py', 'test_*security*.py', 'test_*routing*.py', 'test_*template*.py'],
    'vouchers': ['test_*api*.py', 'test_*configuration*.py', 'test_*admission*.py', 'test_*authorization*.py'],
    'audit': ['test_*api*.py', 'test_read_boundaries.py', 'test_*actor*.py', 'test_*tenant*.py'],
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.test_artifacts/tenant-admin-20261029/suites')
    parser.add_argument('--suite', default='all')
    parser.add_argument('--failed-from', type=Path, help='Console JUnit report; rerun only its failed files with one worker')
    parser.add_argument('--timeout-seconds', type=int, default=10800)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    jobs = []
    for service, patterns in SERVICE_PATTERNS.items():
        cwd = ROOT / 'apis' / service
        files = sorted({p for pattern in patterns for p in (cwd / 'tests').glob(pattern) if 'mysql' not in p.name and 'native' not in p.name})
        jobs.append((service, cwd, [str(cwd / '.venv/Scripts/python.exe'), '-m', 'pytest', '-vv', *[str(p.relative_to(cwd)) for p in files]]))
    for name in ['console', 'auth']:
        cwd = ROOT / 'mfes/apps' / name
        jobs.append((name, cwd, ['pnpm.cmd', 'exec', 'vitest', 'run', '--maxWorkers=2', '--minWorkers=1']))
    if args.failed_from:
        failed_files=sorted({case.get('classname','') for case in ET.parse(args.failed_from).iter('testcase') if any(child.tag in ('failure','error') for child in case)})
        assert all(file.startswith('tests/') and file.endswith(('.test.ts','.test.tsx')) for file in failed_files)
        cwd=ROOT/'mfes/apps/console'
        jobs=[('console',cwd,['pnpm.cmd','exec','vitest','run','--maxWorkers=1','--minWorkers=1',*failed_files])]
    jobs = [j for j in jobs if args.suite in ('all', j[0])]
    def run(job):
        name, cwd, command = job
        report = args.output.resolve() / (name + '.xml')
        command += [f'--junitxml={report}'] if name in SERVICE_PATTERNS else ['--reporter=default', '--reporter=junit', f'--outputFile={report}']
        started = dt.datetime.now(dt.timezone.utc).isoformat()
        with (args.output / (name + '.log')).open('w', encoding='utf-8') as log:
            try:
                result = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout_seconds)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 'TIMEOUT'
        rows = []
        tree = None
        if report.exists():
            try:
                tree = ET.parse(report)
            except ET.ParseError:
                code = 'INCOMPLETE_XML'
        if tree is not None:
            for case in tree.iter('testcase'):
                issue = next((c for c in case if c.tag in ('failure', 'error', 'skipped')), None)
                rows.append({'suite': name, 'test': case.get('classname', '') + '::' + case.get('name', ''), 'status': 'PASS' if issue is None else 'SKIP' if issue.tag == 'skipped' else 'FAIL', 'execution_level': 'isolated component/API regression; not live E2E', 'seconds': case.get('time', ''), 'actual': '' if issue is None else (issue.get('message', '') + ' ' + (issue.text or ''))[:5000], 'started_utc': started, 'evidence': str(report.relative_to(ROOT)).replace('\\', '/')})
        with (args.output / (name + '-results.csv')).open('w', newline='', encoding='utf-8-sig') as out:
            writer = csv.DictWriter(out, fieldnames=['suite', 'test', 'status', 'execution_level', 'seconds', 'actual', 'started_utc', 'evidence'])
            writer.writeheader(); writer.writerows(rows)
        summary = {'suite': name, 'exit_code': code, 'pass': sum(r['status'] == 'PASS' for r in rows), 'fail': sum(r['status'] == 'FAIL' for r in rows), 'skip': sum(r['status'] == 'SKIP' for r in rows)}
        print(json.dumps(summary), flush=True)
        return summary
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        summaries = list(executor.map(run, jobs))
    (args.output / 'summary.json').write_text(json.dumps(summaries, indent=2), encoding='utf-8')
    return int(any(s['exit_code'] != 0 for s in summaries))

if __name__ == '__main__':
    raise SystemExit(main())
