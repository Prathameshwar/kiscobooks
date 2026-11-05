"""Run with native `ak shell` after a QA provision; read-only permission checks."""

import unittest
from types import SimpleNamespace

from authentik.core.models import User
from authentik.rbac.permissions import ObjectPermissions


class RecoveryPermissions(unittest.TestCase):
    def setUp(self):
        self.service = User.objects.get(username="bill-administrator-recovery-service")
        self.target = User.objects.filter(
            path="bill/tenant-administrators", email__startswith="qa-platform-"
        ).order_by("-pk").first()
        self.assertIsNotNone(self.target, "Create a disposable QA administrator first")
        self.permissions = ObjectPermissions()
        self.view = SimpleNamespace(queryset=User.objects.all(), kwargs={"pk": self.target.pk}, lookup_field="pk")

    def object_allowed(self, method, target):
        request = SimpleNamespace(method=method, user=self.service)
        try:
            return self.permissions.has_object_permission(request, self.view, target)
        except Exception:
            return False

    def test_native_post_gate_and_reset_permission_allow_target(self):
        self.assertTrue(self.object_allowed("POST", self.target))
        self.assertTrue(self.service.has_perm("authentik_core.reset_user_password", self.target))

    def test_no_global_create_or_profile_change_or_delete_authority(self):
        for permission in ("add_user", "change_user", "delete_user", "reset_user_password"):
            self.assertFalse(self.service.has_perm("authentik_core." + permission))
        self.assertFalse(self.object_allowed("PATCH", self.target))
        self.assertFalse(self.object_allowed("DELETE", self.target))

    def test_unrelated_service_account_cannot_be_reset(self):
        target = User.objects.get(username="bill-tenant-provision-service")
        self.assertFalse(self.object_allowed("POST", target))
        self.assertFalse(self.service.has_perm("authentik_core.reset_user_password", target))


result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryPermissions))
if not result.wasSuccessful():
    raise RuntimeError("Native recovery permission regression failed")
print("Native recovery permission checks passed; no account or token writes.")
