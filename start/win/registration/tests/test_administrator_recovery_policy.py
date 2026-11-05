"""Execute the deployed expressions with isolated provider objects; no native writes."""

import hashlib
import sys
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml


def test_completion_prompt_supplies_visible_static_content():
    blueprint = yaml.load(
        (
            Path(__file__).parents[1] / "authentik-administrator-recovery.yaml"
        ).read_text(),
        Loader=yaml.BaseLoader,
    )
    prompt = next(
        entry["attrs"]
        for entry in blueprint["entries"]
        if entry["identifiers"].get("name") == "bill-administrator-recovery-success"
    )
    # Static prompts display their value; placeholder-only copy leaves a blank stage.
    assert "Your password has been changed" in prompt["initial_value"]


@pytest.fixture
def policy(monkeypatch):
    blueprint = yaml.load(
        (
            Path(__file__).parents[1] / "authentik-administrator-recovery.yaml"
        ).read_text(),
        Loader=yaml.BaseLoader,
    )
    expressions = {
        entry["identifiers"]["name"]: entry["attrs"]["expression"]
        for entry in blueprint["entries"]
        if entry["model"] == "authentik_policies_expression.expressionpolicy"
    }
    role = SimpleNamespace(assign_perms=Mock())
    user = SimpleNamespace(
        pk=42,
        email="qa@example.invalid",
        type="external",
        path="bill/tenant-administrators",
        username="bill-admin-" + hashlib.sha256(b"qa@example.invalid").hexdigest()[:32],
        attributes={
            "billing_email_verified": True,
            "billing_tenant_provision_command": str(uuid.uuid4()),
        },
        is_active=True,
        is_superuser=False,
        ak_groups=Mock(),
        roles=Mock(),
        has_usable_password=lambda: True,
    )
    user.ak_groups.exists.return_value = user.roles.exists.return_value = False
    actor = SimpleNamespace(
        pk=7,
        username="bill-tenant-provision-service",
        type="service_account",
        is_active=True,
    )
    event = SimpleNamespace(
        action="model_created",
        user={"pk": 7},
        context={
            "model": {"app": "authentik_core", "model_name": "user", "pk": 42},
        },
    )
    request = SimpleNamespace(
        user=actor, context={"event": event, "pending_user": user}
    )
    for name in ("authentik", "authentik.core", "authentik.rbac", "authentik.flows"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    core = ModuleType("authentik.core.models")
    core.User = SimpleNamespace(objects=Mock())
    core.User.objects.filter.return_value.first.return_value = user
    rbac = ModuleType("authentik.rbac.models")
    rbac.Role = SimpleNamespace(objects=Mock())
    rbac.Role.objects.filter.return_value.first.return_value = role
    planner = ModuleType("authentik.flows.planner")
    planner.PLAN_CONTEXT_PENDING_USER = "pending_user"
    for module in (core, rbac, planner):
        monkeypatch.setitem(sys.modules, module.__name__, module)

    def evaluate(name):
        namespace = {"request": request}
        code = "def evaluate():\n" + "\n".join(
            "    " + line for line in expressions[name].splitlines()
        )
        exec(compile(code, name, "exec"), namespace)
        return namespace["evaluate"]()

    return evaluate, request, user, role, core.User


def test_native_provision_handoff_is_object_scoped_and_sends_nothing(policy):
    evaluate, _, user, role, users = policy
    assert evaluate("bill-administrator-recovery-provision-handoff") is False
    users.objects.filter.assert_called_once_with(
        pk=42, path="bill/tenant-administrators", type="external"
    )
    role.assign_perms.assert_called_once_with(
        [
            "authentik_core.view_user",
            "authentik_core.add_user",
            "authentik_core.reset_user_password",
        ],
        user,
    )


@pytest.mark.parametrize(
    "fault",
    [
        "actor",
        "actor_type",
        "actor_disabled",
        "event_actor",
        "action",
        "model",
        "groups",
        "roles",
        "superuser",
        "verified",
        "marker",
        "username",
        "missing_user",
    ],
)
def test_handoff_refuses_untrusted_events_and_accounts(policy, fault):
    evaluate, request, user, role, users = policy
    event = request.context["event"]
    if fault == "actor":
        request.user.username = "someone-else"
    if fault == "actor_type":
        request.user.type = "external"
    if fault == "actor_disabled":
        request.user.is_active = False
    if fault == "event_actor":
        event.user["pk"] = 8
    if fault == "action":
        event.action = "login"
    if fault == "model":
        event.context["model"]["model_name"] = "group"
    if fault == "groups":
        user.ak_groups.exists.return_value = True
    if fault == "roles":
        user.roles.exists.return_value = True
    if fault == "superuser":
        user.is_superuser = True
    if fault == "verified":
        user.attributes["billing_email_verified"] = False
    if fault == "marker":
        user.attributes["billing_tenant_provision_command"] = "invalid"
    if fault == "username":
        user.username = "unrelated"
    if fault == "missing_user":
        users.objects.filter.return_value.first.return_value = None
    assert evaluate("bill-administrator-recovery-provision-handoff") is False
    role.assign_perms.assert_not_called()


@pytest.mark.parametrize(
    "path,allowed",
    [
        ("bill/tenant-administrators", True),
        ("bill/pending-registration", True),
        ("users", False),
    ],
)
def test_recovery_flow_scope(policy, path, allowed):
    evaluate, _, user, _, _ = policy
    user.path = path
    assert evaluate("bill-administrator-recovery-account") is allowed


@pytest.mark.parametrize("fault", ["inactive", "marker", "roles", "verified"])
def test_recovery_flow_rechecks_eligibility(policy, fault):
    evaluate, _, user, _, _ = policy
    if fault == "inactive":
        user.is_active = False
    if fault == "marker":
        user.attributes.clear()
    if fault == "roles":
        user.roles.exists.return_value = True
    if fault == "verified":
        user.attributes["billing_email_verified"] = False
    assert evaluate("bill-administrator-recovery-account") is False
