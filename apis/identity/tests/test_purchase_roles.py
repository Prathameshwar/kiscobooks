"""Who can do the untaxed account (expense) Purchase work, and who cannot.

docs/purchase-e2e-review.md decision D4 found that no shipped role could record, post and
print a Purchase: the poster could not read the supplier, the clerk could not read the
Accounting masters the page loads, and the approver could not render the bill it approves.
docs/roles-permissions.md records the decision (2026-11-01). Every permission here was
traced to the route or domain check that demands it; this file pins the outcome, and
pins what the roles must *not* hold, which is the half a grant list never shows.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

import pytest
from billing_platform.authz import Grant, Scope, ScopePath, has_permission, resolve_permissions
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import unfiltered
from billing_platform.permissions import PERMISSIONS, separation_of_duties_conflicts
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.authorization import Actor, assert_role_composition_allowed
from identity.domain.system_roles import SYSTEM_ROLE_KEYS, SYSTEM_ROLES, SystemRole, get
from identity.models import Role, RolePermission
from identity.seeds import roles as role_seed

TODAY = dt.date(2026, 11, 1)
COMPANY_A, COMPANY_B = uuid.uuid4(), uuid.uuid4()

#: Exactly what recording, posting and printing an untaxed account Purchase needs, and the
#: check that demands each key. A key is here because something refuses without it.
PURCHASE_CLERK = frozenset(
    {
        # Console shell and Vouchers' own company-scoped routes.
        "company.read",
        "vouchers.read",
        "vouchers.create",
        "vouchers.edit",  # also invoice-acceptance, which writes the accepted hash
        "vouchers.submit",
        "vouchers.cancel",  # a draft or submitted bill, and a pending posting execution
        "vouchers.post",
        "vouchers.history.read",
        "vouchers.operation.read",
        "vouchers.operation.recover",
        "vouchers.artifact.create",
        "vouchers.artifact.read",
        "vouchers.import.read",
        "vouchers.import.manage",
        "vouchers.import.commit",
        # Accounting masters the page loads and the posting re-reads under this actor.
        "accounting.party.read",
        "accounting.account.read",
        "accounting.group.read",
        "accounting.head.read",
        # Even an untaxed bill's calculation proves each expense account's dated tax
        # default is NON_GST (invoice_tax._defaults), so tax.read is demanded of every actor.
        "accounting.tax.read",
        # A supplier's accounting policy and credit policy are read only when one exists.
        "accounting.policy.read",
        "accounting.credit.read",
        # Supplier advances (open items and their balances); a plain bill posts without it.
        "ledger.read",
        "ledger.post_journal",
        # The financial-year chip, and assert_postable's OPEN-period check.
        "period.read",
        "period.post",
    }
)

#: What the Purchase flow looked as if it needed, and verifiably does not.
NOT_NEEDED = frozenset(
    {
        "accounting.finance.read",  # only company readiness and year generation read it
        "accounting.setup.read",  # only the chart and template administration read it
        "report.read",  # no Reports call in the Purchase flow
        "item.read",  # an account bill has no items; goods Purchases are out of scope (D8)
        "design.render.record",  # print layout is resolved service to service, not as the actor
    }
)

AUTHORITY_THE_CLERK_MUST_NEVER_HOLD = frozenset(
    {
        "vouchers.approve",
        "vouchers.reject",
        "vouchers.reverse",
        "vouchers.issue",
        "vouchers.share",
        "vouchers.expire",
        "vouchers.export",
        "vouchers.type.manage",
        "vouchers.configuration.manage",
        "vouchers.configuration.publish",
        "vouchers.series.manage",
        "vouchers.template.manage",
        "vouchers.field.adopt",
        "accounting.party.manage",
        "accounting.account.manage",
        "accounting.group.manage",
        "accounting.policy.manage",
        "accounting.credit.manage",
        "accounting.credit.override_approve",
        "accounting.finance.manage",
        "accounting.finance.initialize",
        "period.manage",
        "period.close",
        "period.reopen",
        "period.lock",
        "period.post_adjustment",
        "opening_balance.manage",
        "opening_balance.initialize_zero",
        "role.assign",
        "role.manage",
        "audit.read_security",
        "user.impersonate",
        "payment.refund_approve",
        "invoice.approve",
    }
)

APPROVER_READS_ADDED = frozenset(
    {
        "accounting.party.read",
        "accounting.account.read",
        "accounting.group.read",
        "accounting.head.read",
        "vouchers.operation.read",
    }
)
STOCK_OPERATOR_ADDED = frozenset(
    {
        "accounting.party.read",
        "accounting.tax.read",
        "vouchers.artifact.create",
        "vouchers.artifact.read",
    }
)


def test_purchase_clerk_is_a_company_scoped_shipped_role_with_a_valid_key() -> None:
    role = get("purchase_clerk")
    assert role.name == "Purchase Clerk"
    assert role.scope_hint == "company"
    assert "purchase_clerk" in SYSTEM_ROLE_KEYS
    assert role.description and "approve" in role.description.lower()
    assert role.permissions <= PERMISSIONS
    assert len(SYSTEM_ROLES) == len(SYSTEM_ROLE_KEYS) == 14


def test_purchase_clerk_holds_exactly_the_purchase_recording_set() -> None:
    held = get("purchase_clerk").permissions
    assert held == PURCHASE_CLERK, {
        "missing": sorted(PURCHASE_CLERK - held),
        "unexpected": sorted(held - PURCHASE_CLERK),
    }
    assert not NOT_NEEDED & held


def test_purchase_clerk_records_and_posts_but_cannot_approve_or_close_or_administer() -> None:
    held = get("purchase_clerk").permissions
    assert not AUTHORITY_THE_CLERK_MUST_NEVER_HOLD & held
    assert not any(key.endswith(".manage") and key.startswith("accounting.") for key in held)
    assert not separation_of_duties_conflicts(held)
    # The pair that is the whole point: record and post, never decide.
    assert {"vouchers.create", "vouchers.post"} <= held
    assert not {"vouchers.approve", "vouchers.reject"} & held


def test_purchase_clerk_passes_the_import_time_catalogue_validation() -> None:
    """`_validate_catalogue` runs at import; call it again so a failure names this role."""
    from identity.domain.system_roles import _validate_catalogue

    _validate_catalogue()
    broken = SystemRole(
        key="purchase_clerk_and_approver",
        name="Broken",
        description="A clerk that also approves is refused at boot.",
        scope_hint="company",
        permissions=get("purchase_clerk").permissions | {"vouchers.approve"},
    )
    with pytest.raises(ValueError, match="combines duties"):
        _validate_catalogue((*SYSTEM_ROLES, broken))


def test_only_the_intended_roles_post_and_approve() -> None:
    assert {r.key for r in SYSTEM_ROLES if "vouchers.post" in r.permissions} == {
        "stock_operator",
        "purchase_clerk",
    }
    assert {r.key for r in SYSTEM_ROLES if "vouchers.approve" in r.permissions} == {
        "billing_approver",
        "controller",
    }
    for role in SYSTEM_ROLES:
        assert not {"vouchers.create", "vouchers.approve"} <= role.permissions, role.key


def test_billing_approver_can_render_a_bill_but_still_cannot_record_it() -> None:
    held = get("billing_approver").permissions
    assert APPROVER_READS_ADDED <= held
    assert {"vouchers.approve", "vouchers.reject", "vouchers.read"} <= held
    assert (
        not {
            "vouchers.create",
            "vouchers.edit",
            "vouchers.submit",
            "vouchers.post",
            "vouchers.artifact.create",
            "vouchers.operation.recover",
            "accounting.party.manage",
            "accounting.account.manage",
            "accounting.credit.read",
            "ledger.post_journal",
            "period.post",
        }
        & held
    )
    assert not separation_of_duties_conflicts(held)


def test_stock_operator_gains_the_supplier_name_and_printing_but_not_credit_or_approval() -> None:
    held = get("stock_operator").permissions
    assert STOCK_OPERATOR_ADDED <= held
    assert (
        not {
            "accounting.credit.read",
            "accounting.credit.manage",
            "vouchers.approve",
            "vouchers.reject",
            "period.close",
            "period.reopen",
            "period.lock",
            "accounting.finance.manage",
        }
        & held
    )
    assert not separation_of_duties_conflicts(held)


def test_billing_clerk_stays_the_sales_role() -> None:
    """Decision 2026-11-01: Purchase gets its own role; the Sales clerk is not widened."""
    held = get("billing_clerk").permissions
    assert (
        not {
            "vouchers.post",
            "accounting.party.read",
            "accounting.account.read",
            "accounting.group.read",
            "accounting.head.read",
            "accounting.credit.read",
            "ledger.post_journal",
        }
        & held
    )


def test_a_purchase_clerk_at_company_a_has_nothing_at_company_b_or_tenant_wide() -> None:
    grant = Grant(
        get("purchase_clerk").permissions, Scope("company", COMPANY_A), dt.date(2026, 1, 1)
    )
    mine, theirs, tenant = (
        ScopePath(company_id=COMPANY_A),
        ScopePath(company_id=COMPANY_B),
        ScopePath(),
    )
    assert resolve_permissions([grant], target=mine, on_date=TODAY) == PURCHASE_CLERK
    for permission in ("vouchers.create", "vouchers.post", "accounting.party.read"):
        assert has_permission([grant], permission, target=mine, on_date=TODAY)
        assert not has_permission([grant], permission, target=theirs, on_date=TODAY)
        assert not has_permission([grant], permission, target=tenant, on_date=TODAY)
    assert resolve_permissions([grant], target=theirs, on_date=TODAY) == frozenset()


def test_a_revoked_or_expired_purchase_clerk_grant_reaches_nothing() -> None:
    permissions = get("purchase_clerk").permissions
    start = dt.date(2026, 1, 1)
    target = ScopePath(company_id=COMPANY_A)
    for grant in (
        Grant(permissions, Scope("company", COMPANY_A), start, is_active=False),
        Grant(permissions, Scope("company", COMPANY_A), start, dt.date(2026, 10, 31)),
    ):
        assert not has_permission([grant], "vouchers.post", target=target, on_date=TODAY)


def test_combining_purchase_clerk_with_billing_approver_in_a_tenant_role_is_reported() -> None:
    """The warning machinery works on one role's composition (there is no per-user union
    check): a tenant role built from both reports the create/approve pair, so the UI can
    warn and the `admin`-category audit event can record it (docs/roles-permissions.md §1.4)."""
    union = get("purchase_clerk").permissions | get("billing_approver").permissions
    assert separation_of_duties_conflicts(union) == (("vouchers.create", "vouchers.approve"),)
    designer = Actor(
        user_id=uuid.uuid4(),
        grants=(Grant(union | {"role.manage"}, Scope("tenant", SCOPE_ALL), dt.date(2026, 1, 1)),),
    )
    conflicts = assert_role_composition_allowed(
        union, actor=designer, target=ScopePath(), on_date=TODAY
    )
    assert conflicts == (("vouchers.create", "vouchers.approve"),)
    # Each shipped role alone is clean, which is what lets them be assigned separately.
    for key in ("purchase_clerk", "billing_approver"):
        assert not separation_of_duties_conflicts(get(key).permissions)


# --- existing installations -------------------------------------------------------------


def _catalogue_before_this_decision() -> tuple[SystemRole, ...]:
    """The shipped catalogue as it stood before 2026-11-01 (no purchase_clerk, narrower roles)."""
    withdrawn = {
        "billing_approver": APPROVER_READS_ADDED,
        "stock_operator": STOCK_OPERATOR_ADDED,
    }
    return tuple(
        dataclasses.replace(role, permissions=role.permissions - withdrawn[role.key])
        if role.key in withdrawn
        else role
        for role in SYSTEM_ROLES
        if role.key != "purchase_clerk"
    )


@pytest.mark.asyncio
async def test_an_existing_installation_gains_the_role_and_the_grants_and_reseed_is_a_noop(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _catalogue_before_this_decision()
    with monkeypatch.context() as patch:
        patch.setattr(role_seed, "SYSTEM_ROLES", before)
        patch.setattr(role_seed, "SYSTEM_ROLE_KEYS", frozenset(role.key for role in before))
        await role_seed.seed_system_roles(session)
    with unfiltered():
        ids_before = dict((await session.execute(select(Role.key, Role.id))).tuples().all())
        grants_before = set(
            (
                await session.execute(select(RolePermission.role_id, RolePermission.permission_key))
            ).all()
        )
    assert "purchase_clerk" not in ids_before

    roles, grants = await role_seed.seed_system_roles(session)
    assert (roles.inserted, roles.updated, roles.deactivated) == (1, 0, 0)
    assert grants.inserted == (
        len(get("purchase_clerk").permissions)
        + len(APPROVER_READS_ADDED)
        + len(STOCK_OPERATOR_ADDED)
    )
    assert grants.revoked == 0

    with unfiltered():
        ids_after = dict((await session.execute(select(Role.key, Role.id))).tuples().all())
        retained = set(
            (
                await session.execute(
                    select(RolePermission.role_id, RolePermission.permission_key).where(
                        RolePermission.role_id.in_(ids_before.values())
                    )
                )
            ).all()
        )
        installed = set(
            await session.scalars(
                select(RolePermission.permission_key).where(
                    RolePermission.role_id == ids_after["purchase_clerk"]
                )
            )
        )
    # Existing role identities (assignments reference them) and every earlier grant survive.
    assert {k: v for k, v in ids_after.items() if k != "purchase_clerk"} == ids_before
    assert grants_before <= retained
    assert installed == PURCHASE_CLERK

    repeated_roles, repeated_grants = await role_seed.seed_system_roles(session)
    assert not repeated_roles.changed and not repeated_grants.changed
