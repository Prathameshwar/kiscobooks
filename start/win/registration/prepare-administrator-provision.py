"""Create the dedicated Authentik API operator for tenant administrator provisioning."""

from authentik.core.models import Token, TokenIntents, User, UserTypes
from authentik.rbac.models import Role
from guardian.shortcuts import get_perms

role, _ = Role.objects.get_or_create(name="bill-tenant-provision-service")
service, _ = User.objects.get_or_create(
    username="bill-tenant-provision-service",
    defaults={"name": "Bill tenant provision service", "type": UserTypes.SERVICE_ACCOUNT,
              "path": "bill/service-accounts", "is_active": True},
)
allowed = {"authentik_core.add_user", "authentik_core.view_user",
           "authentik_core.change_user", "authentik_core.reset_user_password"}
if (service.type != UserTypes.SERVICE_ACCOUNT or service.ak_groups.exists()
        or service.roles.exclude(pk=role.pk).exists() or set(get_perms(service)) - allowed):
    raise RuntimeError("Provision service has unexpected authority; review before deployment.")
existing = {f"{row.permission.content_type.app_label}.{row.permission.codename}"
            for row in role.rolemodelpermission_set.select_related("permission__content_type")}
if existing - allowed or role.roleobjectpermission_set.exists():
    raise RuntimeError("Provision role has unexpected authority; review before deployment.")
service.set_unusable_password()
service.save(update_fields=["password"])
service.roles.add(role)
role.assign_perms(sorted(allowed))
token, _ = Token.objects.get_or_create(identifier="bill-tenant-provision-service", defaults={
    "user": service, "intent": TokenIntents.INTENT_API, "expiring": False,
})
if token.user_id != service.pk or token.intent != TokenIntents.INTENT_API:
    raise RuntimeError("Provision token belongs to an unexpected user.")
print("BILL_PROVISION_TOKEN=" + token.key)
