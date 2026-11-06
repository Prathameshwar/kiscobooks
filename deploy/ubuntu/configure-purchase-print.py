"""Idempotently enroll native companies in the private Purchase PDF runtime.

Run as root with the Vouchers virtualenv. Secrets stay in restricted environment
files and broker/MySQL stdin; command arguments and output contain no passwords.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pwd
import grp
import secrets
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from billing_platform.db import create_engine
from sqlalchemy import text


CONFIG = Path('/etc/kiscobooks')
API = CONFIG / 'vouchers.env'
DESIGN = CONFIG / 'design.env'
RUNTIME = CONFIG / 'vouchers-print.env'
KEY = CONFIG / 'purchase-print.key'
ROOT = Path('/var/lib/kiscobooks-print')
BROKER_USER = 'kisco-print'
BROKER_VHOST = 'kiscobooks-print'
DB_USER = 'vouchers_print'


def env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#') and '=' in line:
            name, value = line.split('=', 1)
            result[name] = value[1:-1] if value and value[0] in "\"'" and value[-1] == value[0] else value
    return result


def update(path: Path, changes: dict[str, str | None], *, group: str = 'kiscobooks') -> bool:
    before = path.read_text(encoding='utf-8') if path.exists() else ''
    lines = [line for line in before.splitlines() if line.split('=', 1)[0] not in changes]
    lines.extend(f'{name}={value}' for name, value in changes.items() if value is not None)
    after = '\n'.join(lines) + '\n'
    if after == before:
        return False
    temporary = path.with_name(path.name + '.new')
    temporary.write_text(after, encoding='utf-8')
    os.chmod(temporary, 0o640)
    os.chown(temporary, 0, grp.getgrnam(group).gr_gid)
    temporary.replace(path)
    return True


def run(*arguments: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        arguments, input=input_text, text=True, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    return result.stdout


def broker_password(existing: dict[str, str]) -> str:
    configured = existing.get('VOUCHERS_PRINT_BROKER_URL')
    password = None
    if configured:
        parsed = urlsplit(configured)
        if parsed.username != BROKER_USER or parsed.path != '/' + BROKER_VHOST:
            raise RuntimeError('Existing Purchase print broker identity needs review')
        password = unquote(parsed.password or '')
        if not password:
            raise RuntimeError('Existing Purchase print broker credential is incomplete')
    vhosts = {line.strip() for line in run('rabbitmqctl', 'list_vhosts', '-q').splitlines()}
    if BROKER_VHOST not in vhosts:
        run('rabbitmqctl', 'add_vhost', BROKER_VHOST)
    users = {line.split()[0] for line in run('rabbitmqctl', 'list_users', '-q').splitlines() if line.split()}
    if BROKER_USER not in users:
        password = password or secrets.token_hex(32)
        # RabbitMQ reads an omitted add_user password from stdin. Never use argv.
        run('rabbitmqctl', 'add_user', BROKER_USER, input_text=password + '\n')
    elif password is None:
        raise RuntimeError('Unowned Purchase print broker user needs review')
    permission = r'^vouchers\.purchase\.print$'
    run('rabbitmqctl', 'set_permissions', '-p', BROKER_VHOST, BROKER_USER,
        permission, permission, permission)
    return password


def database_url(existing: dict[str, str]) -> str:
    if RUNTIME.exists():
        value = env(RUNTIME).get('VOUCHERS_DATABASE_URL')
        if value:
            return value
    users = run('mysql', '-N', '-B', '-e',
                "SELECT user FROM mysql.user WHERE user='vouchers_print' AND host='127.0.0.1'")
    if users.strip():
        raise RuntimeError('Unowned Purchase print database user needs review')
    password = secrets.token_hex(32)
    sql = (
        f"CREATE USER IF NOT EXISTS '{DB_USER}'@'127.0.0.1' IDENTIFIED BY '{password}';\n"
        f"GRANT SELECT, UPDATE ON vouchers.voucher_print_job TO '{DB_USER}'@'127.0.0.1';\n"
        f"GRANT SELECT, INSERT, UPDATE ON vouchers.outbox TO '{DB_USER}'@'127.0.0.1';\n"
    )
    run('mysql', input_text=sql)
    source = urlsplit(existing['VOUCHERS_DATABASE_URL'])
    return (f'{source.scheme}://{DB_USER}:{quote(password)}@'
            f'{source.hostname}:{source.port or 3306}/{source.path.lstrip("/")}')


async def companies(url: str) -> list[dict[str, str]]:
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            rows = (await connection.execute(text(
                'SELECT tenant_id, company_id FROM voucher_company_guard '
                'ORDER BY tenant_id, company_id LIMIT 1001'
            ))).all()
        if len(rows) > 1000:
            raise RuntimeError('Purchase print company scope limit exceeded')
        return [
            {'tenant_id': str(uuid.UUID(bytes=row.tenant_id)),
             'company_id': str(uuid.UUID(bytes=row.company_id))}
            for row in rows
        ]
    finally:
        await engine.dispose()


def layout_secret(vouchers: dict[str, str], design: dict[str, str]) -> str:
    existing = []
    if KEY.exists():
        existing.append(KEY.read_text(encoding='utf-8').strip())
    for value in (vouchers.get('VOUCHERS_PRINT_LAYOUT_OWNER'), design.get('DESIGN_PRINT_SOURCE')):
        if value:
            existing.append(json.loads(value)['secret'])
    if len(set(existing)) > 1:
        raise RuntimeError('Purchase print layout credentials disagree')
    secret = existing[0] if existing else secrets.token_urlsafe(48)
    if not KEY.exists():
        KEY.write_text(secret + '\n', encoding='utf-8')
        os.chmod(KEY, 0o600)
    return secret


def storage() -> None:
    if not ROOT.exists():
        ROOT.mkdir(mode=0o750)
    os.chown(ROOT, pwd.getpwnam(BROKER_USER).pw_uid, grp.getgrnam('kiscobooks').gr_gid)
    os.chmod(ROOT, 0o750)
    for name in ('pdfs', 'browsers'):
        path = ROOT / name
        path.mkdir(mode=0o750, exist_ok=True)
        os.chown(path, pwd.getpwnam(BROKER_USER).pw_uid, grp.getgrnam('kiscobooks').gr_gid)
        os.chmod(path, 0o2750 if name == 'pdfs' else 0o750)


def repair_existing_pdfs() -> None:
    # Run at install/update time, never in the frequent enrollment timer.
    for path in (ROOT / 'pdfs').rglob('*'):
        if path.is_symlink():
            raise RuntimeError('Purchase print storage contains a link')
        if path.is_dir():
            os.chown(path, pwd.getpwnam(BROKER_USER).pw_uid,
                     grp.getgrnam('kiscobooks').gr_gid)
            os.chmod(path, 0o2750)
        elif path.is_file():
            os.chown(path, pwd.getpwnam(BROKER_USER).pw_uid,
                     grp.getgrnam('kiscobooks').gr_gid)
            os.chmod(path, 0o640)


def preserve_existing_pdfs(existing: dict[str, str]) -> None:
    old = existing.get('VOUCHERS_PRINT_FILE_ROOT')
    if not old or Path(old) == ROOT / 'pdfs' or not Path(old).exists():
        return
    source = Path(old).resolve(strict=True)
    if source != Path('/var/lib/kiscobooks/vouchers/prints'):
        raise RuntimeError('Unexpected existing Purchase print root needs review')
    for path in source.rglob('*'):
        if path.is_symlink():
            raise RuntimeError('Existing Purchase print storage contains a link')
        relative = path.relative_to(source)
        target = ROOT / 'pdfs' / relative
        if path.is_dir():
            target.mkdir(exist_ok=True, parents=True)
            os.chown(target, pwd.getpwnam(BROKER_USER).pw_uid,
                     grp.getgrnam('kiscobooks').gr_gid)
        elif path.is_file() and not target.exists():
            target.parent.mkdir(exist_ok=True, parents=True)
            shutil.copy2(path, target)
            os.chown(target, pwd.getpwnam(BROKER_USER).pw_uid, grp.getgrnam('kiscobooks').gr_gid)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--restart', action='store_true')
    parser.add_argument('--repair-storage', action='store_true')
    args = parser.parse_args()
    vouchers = env(API)
    design = env(DESIGN)
    storage()
    preserve_existing_pdfs(vouchers)
    if args.repair_storage:
        repair_existing_pdfs()
    broker = broker_password(vouchers)
    db = database_url(vouchers)
    scopes = asyncio.run(companies(vouchers['VOUCHERS_DATABASE_URL']))
    scope_json = json.dumps(scopes, separators=(',', ':'))
    secret = layout_secret(vouchers, design)
    owner = json.dumps({
        'origin': 'http://127.0.0.1:8014', 'secret': secret, 'scopes': scopes,
    }, separators=(',', ':')) if scopes else None
    source = json.dumps({'secret': secret, 'scopes': scopes}, separators=(',', ':')) if scopes else None
    broker_url = f'amqp://{BROKER_USER}:{quote(broker)}@127.0.0.1:5672/{BROKER_VHOST}'
    changed = update(API, {
        'VOUCHERS_PRINT_FILE_ROOT': str(ROOT / 'pdfs'),
        'VOUCHERS_PRINT_BROKER_URL': broker_url,
        'VOUCHERS_PRINT_SCOPES': scope_json,
        'VOUCHERS_PRINT_LAYOUT_OWNER': owner,
    })
    changed |= update(DESIGN, {'DESIGN_PRINT_SOURCE': source})
    changed |= update(RUNTIME, {
        'VOUCHERS_DATABASE_URL': db,
        'VOUCHERS_PRINT_FILE_ROOT': str(ROOT / 'pdfs'),
        'VOUCHERS_PRINT_BROKER_URL': broker_url,
        'VOUCHERS_PRINT_SCOPES': scope_json,
        'PLAYWRIGHT_BROWSERS_PATH': str(ROOT / 'browsers'),
        'VOUCHERS_ENVIRONMENT': 'production',
        'PYTHONDONTWRITEBYTECODE': '1',
    }, group=BROKER_USER)
    if changed and args.restart:
        for unit in ('kiscobooks-api@design.service', 'kiscobooks-api@vouchers.service',
                     'kiscobooks-vouchers-print-dispatcher.service',
                     'kiscobooks-vouchers-print-worker.service'):
            run('systemctl', 'try-restart', unit)
    print(f'Purchase print configured for {len(scopes)} enrolled companies; changed={changed}')


if __name__ == '__main__':
    main()
