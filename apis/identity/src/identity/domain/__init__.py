"""``identity`` domain rules.

Business rules and no framework (CLAUDE.md §4): nothing here imports FastAPI, and
nothing here touches a session. Callers hand in plain values and get a decision
back, which is what lets these be tested with no database at all.
"""

from identity.domain.authorization import (
    ROLE_ASSIGN,
    ROLE_MANAGE,
    SUBJECT_TYPES,
    Actor,
    AssignmentChange,
    assert_assignment_change_allowed,
    assert_not_own_assignment,
    assert_permissions_held,
    assert_role_composition_allowed,
    assert_role_editable,
    assert_scope_within_actors_own,
)
from identity.domain.company_features import (
    FeatureState,
    assert_disable_allowed,
    assert_enabled,
    plan_enable,
    plan_lock,
    resolve_enabled,
)
from identity.domain.company_immutability import (
    IMMUTABLE_AFTER_POSTING,
    assert_company_fields_mutable,
    assert_update_allowed,
    changed_fields,
)
from identity.domain.company_jurisdiction import (
    assert_cash_receipt_limit_allowed,
    assert_jurisdiction_code_allowed,
    assert_required_statutory_ids_present,
    assert_statutory_row_storable,
    plan_statutory_id,
)
from identity.domain.company_registration import (
    REGISTRATION_IMMUTABLE_FIELDS,
    assert_licence_writable,
    assert_registration_coexists,
    assert_registration_writable,
    assert_single_primary,
    registration_changes,
    registration_class_of,
)
from identity.domain.system_roles import (
    READS_WITHHELD_FROM_AUDITOR,
    SYSTEM_ROLE_KEYS,
    SYSTEM_ROLES,
    SystemRole,
    read_permissions,
)

__all__ = [
    "IMMUTABLE_AFTER_POSTING",
    "READS_WITHHELD_FROM_AUDITOR",
    "REGISTRATION_IMMUTABLE_FIELDS",
    "ROLE_ASSIGN",
    "ROLE_MANAGE",
    "SUBJECT_TYPES",
    "SYSTEM_ROLES",
    "SYSTEM_ROLE_KEYS",
    "Actor",
    "AssignmentChange",
    "FeatureState",
    "SystemRole",
    "assert_assignment_change_allowed",
    "assert_cash_receipt_limit_allowed",
    "assert_company_fields_mutable",
    "assert_disable_allowed",
    "assert_enabled",
    "assert_jurisdiction_code_allowed",
    "assert_licence_writable",
    "assert_not_own_assignment",
    "assert_permissions_held",
    "assert_registration_coexists",
    "assert_registration_writable",
    "assert_required_statutory_ids_present",
    "assert_role_composition_allowed",
    "assert_role_editable",
    "assert_scope_within_actors_own",
    "assert_single_primary",
    "assert_statutory_row_storable",
    "assert_update_allowed",
    "changed_fields",
    "plan_enable",
    "plan_lock",
    "plan_statutory_id",
    "read_permissions",
    "registration_changes",
    "registration_class_of",
    "resolve_enabled",
]
