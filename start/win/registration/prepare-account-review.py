"""Run in Authentik's administrative shell during deployment, never inside Identity."""
from authentik.core.models import Token, TokenIntents, User, UserTypes
from authentik.rbac.models import Role

role, _ = Role.objects.get_or_create(name="bill-account-review-service")
service, created = User.objects.get_or_create(username="bill-account-review-service", defaults={
    "name": "Bill account review service", "type": UserTypes.SERVICE_ACCOUNT,
    "path": "bill/service-accounts", "is_active": True,
})
if service.type != UserTypes.SERVICE_ACCOUNT or service.ak_groups.exists():
    raise RuntimeError("Existing review service account needs an operator security review.")
from guardian.shortcuts import get_perms
if get_perms(service) or get_perms(role):
    raise RuntimeError("Review service must not hold global permissions.")
if service.roles.exclude(pk=role.pk).exists():
    raise RuntimeError("Review service has unexpected roles.")
service.set_unusable_password()
service.save(update_fields=["password"])
service.roles.add(role)
# Keep an empty applicant queue readable without granting global user listing.
# The adapter excludes this service-account object from its applicant projection.
role.assign_perms(["authentik_core.view_user"], service)
for user in User.objects.filter(path="bill/pending-registration", type=UserTypes.EXTERNAL).iterator(chunk_size=100):
    if user.ak_groups.exists() or user.roles.exists():
        continue
    role.assign_perms(["authentik_core.view_user", "authentik_core.change_user"], user)
token, _ = Token.objects.get_or_create(identifier="bill-account-review-service", defaults={
    "user": service, "intent": TokenIntents.INTENT_API, "expiring": False,
})
if token.user_id != service.pk or token.intent != TokenIntents.INTENT_API:
    raise RuntimeError("Existing service token does not match the restricted review account.")
# Captured privately by the preparation script; never printed to its console.
print("BILL_REVIEW_TOKEN=" + token.key)
