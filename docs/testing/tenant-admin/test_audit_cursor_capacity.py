"""Reusable regression for the tenant-admin audit/activity paging failure.

Run with apis/audit/.venv/Scripts/python.exe -m pytest <this file>.
No database or service configuration is changed. This should fail until the
audited binding can accommodate an ordinary broad tenant administrator grant.
"""
import datetime as dt
import secrets
import uuid
from types import SimpleNamespace

from audit.api.listing import cursor_codec
from billing_platform.authz import Grant, Scope
from billing_platform.gateway import Actor
from pydantic import SecretStr
from starlette.datastructures import QueryParams


def test_tenant_administrator_grants_fit_audit_pagination_cursor():
    permissions = frozenset(
        {'audit.read', 'activity.read'}
        | {f'catalogue_resource_{index:03}.read' for index in range(200)}
    )
    actor = Actor(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        grants=(Grant(permissions, Scope('tenant'), dt.date(2026, 1, 1)),),
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(
            cursor_signing_secret=SecretStr(secrets.token_hex(32))
        ))),
        query_params=QueryParams('limit=1'),
    )
    codec = cursor_codec(request, 'audit-events', actor)
    token = codec.encode({'occurred_at': '2026-10-29T00:00:00+00:00', 'id': str(uuid.uuid4())})
    assert len(token) <= 4096
    assert codec.decode(token)['occurred_at'] == '2026-10-29T00:00:00+00:00'
