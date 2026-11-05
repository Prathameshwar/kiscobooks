"""Deploy in Authentik's administrative shell. Output is captured privately."""
from authentik.brands.models import Brand
from authentik.core.models import Token, TokenIntents, User, UserTypes
from authentik.flows.models import Flow
from authentik.lib.config import CONFIG
from authentik.rbac.models import Role
from authentik.stages.email.models import EmailStage
from guardian.shortcuts import get_perms
from types import SimpleNamespace
from authentik.policies.expression.evaluator import PolicyEvaluator
from authentik.policies.expression.models import ExpressionPolicy
from authentik.policies.types import PolicyRequest

flow = Flow.objects.get(slug="bill-administrator-recovery")
brand = Brand.objects.get(default=True)
if brand.flow_recovery_id and brand.flow_recovery_id != flow.pk:
    raise RuntimeError("An existing recovery flow is configured; preserve it and review the brand configuration.")
role, _ = Role.objects.get_or_create(name="bill-administrator-recovery-service")
service, _ = User.objects.get_or_create(username="bill-administrator-recovery-service", defaults={
    "name": "Bill administrator recovery service", "type": UserTypes.SERVICE_ACCOUNT,
    "path": "bill/service-accounts", "is_active": True,
})
if (service.type != UserTypes.SERVICE_ACCOUNT or service.ak_groups.exists()
        or service.roles.exclude(pk=role.pk).exists() or get_perms(service) or get_perms(role)):
    raise RuntimeError("Recovery service has unexpected authority; review before deployment.")
service.set_unusable_password()
service.save(update_fields=["password"])
service.roles.add(role)
role.assign_perms(["authentik_core.view_user"], service)
for user in User.objects.filter(path="bill/pending-registration", type=UserTypes.EXTERNAL).iterator(chunk_size=100):
    if not user.ak_groups.exists() and not user.roles.exists() and not user.is_superuser:
        role.assign_perms(["authentik_core.view_user", "authentik_core.add_user", "authentik_core.reset_user_password"], user)
# Backfill existing platform-created accounts using the same guarded policy as
# future native creation/update events. Never grant global user authority.
provisioner = User.objects.filter(username="bill-tenant-provision-service").first()
if provisioner is not None:
    policy = ExpressionPolicy.objects.get(name="bill-administrator-recovery-provision-handoff")
    for user in User.objects.filter(path="bill/tenant-administrators", type=UserTypes.EXTERNAL).iterator(chunk_size=100):
        request = PolicyRequest(provisioner)
        request.context["event"] = SimpleNamespace(action="model_created", user={"pk": provisioner.pk}, context={
            "model": {"app": "authentik_core", "model_name": "user", "pk": user.pk},
        })
        evaluator = PolicyEvaluator("bill-recovery-permission-backfill")
        evaluator.set_policy_request(request)
        evaluator.evaluate(policy.expression)
email, _ = EmailStage.objects.get_or_create(name="bill-administrator-recovery-email", defaults={
    "use_global_settings": True, "subject": "Reset your KiscoBooks password", "token_expiry": "minutes=10",
})
role.assign_perms(["authentik_stages_email.view_emailstage"], email)
brand.flow_recovery = flow
brand.save(update_fields=["flow_recovery"])
token, _ = Token.objects.get_or_create(identifier="bill-administrator-recovery-service", defaults={
    "user": service, "intent": TokenIntents.INTENT_API, "expiring": False,
})
if token.user_id != service.pk or token.intent != TokenIntents.INTENT_API:
    raise RuntimeError("Existing recovery token does not match its restricted service account.")
host = CONFIG.get("email.host", "") if email.use_global_settings else email.host
sender = CONFIG.get("email.from", "") if email.use_global_settings else email.from_address
configured = bool(host and host not in ("localhost", "127.0.0.1") and sender and not sender.endswith("@authentik.local"))
print("BILL_RECOVERY_TOKEN=" + token.key)
print("BILL_RECOVERY_EMAIL_STAGE=" + (str(email.pk) if configured else "disabled"))
