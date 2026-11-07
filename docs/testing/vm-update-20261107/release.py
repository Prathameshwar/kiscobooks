"""Stage and verify a VM release; activation is a separate explicit phase."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shlex
import socket
import subprocess
import sys
import tarfile
import time

SERVICES = ('identity', 'audit', 'catalog', 'accounting', 'vouchers', 'reports', 'notification', 'design')
label, phase = sys.argv[1:3]
assert re.fullmatch(r'latest-build-\d{8}-\d{6}', label)
assert socket.gethostname() == 'srv2111154' and os.geteuid() == 0
root = pathlib.Path('/opt/kiscobooks/releases') / label
state = pathlib.Path('/tmp') / (label + '-state.json')
evidence_file = root / '.deployment/evidence.json'
evidence = json.loads(evidence_file.read_text()) if evidence_file.exists() else {'label': label, 'checks': {}}


def status(step, result='running'):
    state.write_text(json.dumps({'phase': phase, 'step': step, 'status': result, 'time': time.time()}))
    print(step, result, flush=True)


def save():
    evidence_file.write_text(json.dumps(evidence, indent=2))


def environment(service):
    values = dict(os.environ)
    for line in pathlib.Path('/etc/kiscobooks', service + '.env').read_text().splitlines():
        if not line.strip() or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.removeprefix('export ')] = shlex.split(value)[0] if value else ''
    values.update(NEXT_TELEMETRY_DISABLED='1', NODE_OPTIONS='--max-old-space-size=4096', CI='1')
    return values


def run(name, command, cwd=None, env=None):
    status(name)
    log = root / '.deployment' / (name + '.log')
    started = time.time()
    with log.open('w') as output:
        process = subprocess.run(command, cwd=cwd or root, env=env, stdout=output, stderr=subprocess.STDOUT)
    evidence['checks'][name] = {'exit_code': process.returncode, 'seconds': round(time.time()-started, 2), 'log': str(log)}
    save()
    if process.returncode:
        status(name, 'failed')
        raise RuntimeError(name + ' failed; see ' + str(log))
    return log


def prepare():
    archive = pathlib.Path('/tmp', label + '.tar.gz')
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == sys.argv[3], 'Archive hash mismatch'
    root.mkdir(mode=0o755)
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            target = (root / member.name).resolve()
            assert target.is_relative_to(root), 'Archive path outside candidate'
            assert member.isfile() or member.isdir(), 'Unsupported archive member'
        bundle.extractall(root, filter='data')
    (root / '.deployment').mkdir(mode=0o700)
    previous = pathlib.Path('/opt/kiscobooks/current').resolve()
    evidence['previous'] = str(previous)
    evidence['archive_sha256'] = sys.argv[3]
    manifest = json.loads((root / 'release-source-manifest.json').read_text())['files']
    old = json.loads((previous / 'release-source-manifest.json').read_text())['files']
    changed = []
    for name, facts in manifest.items():
        digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
        assert digest == facts['sha256'], 'Source hash mismatch: ' + name
        prior = old.get(name)
        prior_hash = prior.get('sha256') if isinstance(prior, dict) else prior
        if digest != prior_hash:
            changed.append(name)
    evidence['source_count'], evidence['changed'] = len(manifest), changed
    save()
    for service in SERVICES:
        run('dependencies-' + service, ['uv', 'sync', '--frozen'], root / 'apis' / service)
        script = 'import pathlib,' + service + ',billing_platform; root=pathlib.Path(' + repr(str(root)) + '); assert pathlib.Path(' + service + '.__file__).resolve().is_relative_to(root); assert pathlib.Path(billing_platform.__file__).resolve().is_relative_to(root)'
        run('source-path-' + service, [str(root / 'apis' / service / '.venv/bin/python'), '-c', script])
    run('dependencies-web', ['pnpm', 'install', '--frozen-lockfile'], root / 'mfes', {**os.environ, 'CI': '1'})


def migrate():
    backup = pathlib.Path('/root/kiscobooks-backups') / label
    backup.mkdir(mode=0o700, exist_ok=True)
    dump = backup / 'databases.sql'
    status('database-backup')
    if 'backup' in evidence:
        assert hashlib.sha256(dump.read_bytes()).hexdigest() == evidence['backup']['sha256'], 'Backup changed'
    else:
        with dump.open('xb') as output:
            os.chmod(dump, 0o600)
            subprocess.run(['mysqldump', '--single-transaction', '--set-gtid-purged=OFF', '--routines', '--events', '--triggers', '--databases', *SERVICES], stdout=output, check=True)
    assert dump.stat().st_size > 1000
    evidence['backup'] = {'path': str(dump), 'size': dump.stat().st_size, 'sha256': hashlib.sha256(dump.read_bytes()).hexdigest()}
    save()
    migration_env = environment('migration')
    evidence['migrations'] = {}
    for service in SERVICES:
        query = 'SELECT version_num FROM ' + service + '.alembic_version'
        before = subprocess.check_output(['mysql', '-N', '-e', query], text=True).strip()
        python = str(root / 'apis' / service / '.venv/bin/python')
        command = [python, '-m', 'alembic', '-c', str(root / 'dbs' / service / 'alembic.ini')]
        heads = run('migration-heads-' + service, command + ['heads'], cwd=root / 'dbs' / service, env=migration_env).read_text().strip()
        run('migration-upgrade-' + service, command + ['upgrade', 'head'], cwd=root / 'dbs' / service, env=migration_env)
        after = subprocess.check_output(['mysql', '-N', '-e', query], text=True).strip()
        assert set(after.splitlines()) == {line.split()[0] for line in heads.splitlines() if '(head)' in line}, 'Database not at source head'
        evidence['migrations'][service] = {'before': before, 'after': after}
        save()


def verify():
    changed = evidence['changed']
    for service in SERVICES:
        python = str(root / 'apis' / service / '.venv/bin/python')
        run('compile-' + service, [python, '-m', 'compileall', '-q', str(root / 'apis' / service / 'src')])
        tests = [name.removeprefix('apis/' + service + '/') for name in changed if name.startswith('apis/' + service + '/tests/test_') and name.endswith('.py')]
        if tests:
            run('tests-' + service, [python, '-m', 'pytest', '-q', '-m', 'not mysql', *tests], root / 'apis' / service)
    for package, folder in (('ui', 'packages/ui'), ('auth', 'apps/auth'), ('console', 'apps/console')):
        cwd = root / 'mfes' / folder
        run('typecheck-' + package, ['pnpm', 'typecheck'], cwd)
        if package == 'console':
            tests = [name.removeprefix('mfes/apps/console/') for name in changed if name.startswith('mfes/apps/console/tests/') and re.search(r'\.test\.(ts|tsx)$', name) and '.browser.test.' not in name]
        else:
            tests = []
        command = ['pnpm', 'exec', 'vitest', 'run', '--maxWorkers=2', '--minWorkers=1']
        run('tests-' + package, command + tests, cwd)
    for service in ('auth', 'console'):
        run('build-' + service, ['pnpm', 'build'], root / 'mfes/apps' / service, environment(service))
    run('ownership', ['chown', '-R', 'kiscobooks:kiscobooks', str(root)])


try:
    {'prepare': prepare, 'migrate': migrate, 'verify': verify}[phase]()
    status('phase-complete', 'passed')
except Exception as error:
    status(type(error).__name__ + ': ' + str(error), 'failed')
    raise SystemExit(1)
