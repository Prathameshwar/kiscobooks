"""Compatibility imports; field access resolution is shared mechanism."""

from billing_platform.field_policy import (
    READ as READ,
)
from billing_platform.field_policy import (
    WRITE as WRITE,
)
from billing_platform.field_policy import (
    FieldPolicyRule as FieldPolicyRule,
)
from billing_platform.field_policy import (
    assert_fields_writable as assert_fields_writable,
)
from billing_platform.field_policy import (
    denied_fields as denied_fields,
)
from billing_platform.field_policy import (
    resolve_field_effect as resolve_field_effect,
)
